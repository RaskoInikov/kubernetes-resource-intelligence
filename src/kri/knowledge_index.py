"""Deterministic M7 chunking, Qdrant indexing, inspection, and retrieval."""

import hashlib
import json
import math
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any, Protocol, cast
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen
from uuid import UUID, uuid5

from pydantic import ValidationError

from kri.contracts import (
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeDocumentSummary,
    KnowledgeDocumentType,
    KnowledgeIndexStatus,
    KnowledgeIndexSummary,
    KnowledgeRetrievalHit,
    KnowledgeRetrievalResult,
)
from kri.knowledge import KnowledgeRepository

INDEX_OWNER = "kubernetes-resource-intelligence"
INDEX_SCHEMA_VERSION = "2.0"
CHUNKER_VERSION = "1.0"
EMBEDDER_VERSION = "2.0"
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
VECTOR_DIMENSION = 384
DISTANCE = "Cosine"
MAX_CHUNK_CHARACTERS = 1200
POINT_NAMESPACE = UUID("b97ef2d6-2bca-54a5-8293-5afbf2787ccb")
COLLECTION_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")


class KnowledgeIndexError(RuntimeError):
    """Knowledge indexing or inspection could not be completed safely."""


class QdrantGatewayError(RuntimeError):
    """Qdrant transport or response failure."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class QdrantCollectionInfo:
    """Minimal collection metadata required by M7."""

    vector_size: int
    distance: str
    point_count: int


@dataclass(frozen=True)
class QdrantPoint:
    """Stored Qdrant point without a vector."""

    point_id: str
    payload: dict[str, Any]


@dataclass(frozen=True)
class QdrantScoredPoint:
    """Stored Qdrant point returned by vector search."""

    point_id: str
    score: float
    payload: dict[str, Any]


class QdrantGateway(Protocol):
    """Narrow Qdrant boundary used by indexing and read-only inspection."""

    def get_collection(self, collection: str) -> QdrantCollectionInfo | None: ...

    def create_collection(
        self, collection: str, vector_size: int, distance: str
    ) -> None: ...

    def upsert_points(
        self,
        collection: str,
        points: tuple[tuple[str, tuple[float, ...], dict[str, Any]], ...],
    ) -> None: ...

    def delete_points(self, collection: str, point_ids: tuple[str, ...]) -> None: ...

    def scroll_points(
        self,
        collection: str,
        payload_filter: dict[str, Any],
        limit: int,
        offset: str | int | None = None,
    ) -> tuple[tuple[QdrantPoint, ...], str | int | None]: ...

    def search_points(
        self,
        collection: str,
        vector: tuple[float, ...],
        payload_filter: dict[str, Any],
        limit: int,
    ) -> tuple[QdrantScoredPoint, ...]: ...


class QdrantHttpGateway:
    """Small JSON/HTTP implementation of the M7 Qdrant gateway."""

    def __init__(self, base_url: str, timeout_seconds: float = 10.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def get_collection(self, collection: str) -> QdrantCollectionInfo | None:
        try:
            response = self._request("GET", self._collection_path(collection))
        except QdrantGatewayError as error:
            if error.status_code == 404:
                return None
            raise
        result = self._mapping(response, "result")
        config = self._mapping(result, "config")
        params = self._mapping(config, "params")
        vectors = self._mapping(params, "vectors")
        size = vectors.get("size")
        distance = vectors.get("distance")
        point_count = result.get("points_count")
        if (
            not isinstance(size, int)
            or not isinstance(distance, str)
            or not isinstance(point_count, int)
        ):
            raise QdrantGatewayError("malformed Qdrant collection metadata")
        return QdrantCollectionInfo(size, distance, point_count)

    def create_collection(
        self, collection: str, vector_size: int, distance: str
    ) -> None:
        self._request(
            "PUT",
            self._collection_path(collection),
            {"vectors": {"size": vector_size, "distance": distance}},
        )

    def upsert_points(
        self,
        collection: str,
        points: tuple[tuple[str, tuple[float, ...], dict[str, Any]], ...],
    ) -> None:
        self._request(
            "PUT",
            f"{self._collection_path(collection)}/points?wait=true",
            {
                "points": [
                    {"id": point_id, "vector": vector, "payload": payload}
                    for point_id, vector, payload in points
                ]
            },
        )

    def delete_points(self, collection: str, point_ids: tuple[str, ...]) -> None:
        self._request(
            "POST",
            f"{self._collection_path(collection)}/points/delete?wait=true",
            {"points": point_ids},
        )

    def scroll_points(
        self,
        collection: str,
        payload_filter: dict[str, Any],
        limit: int,
        offset: str | int | None = None,
    ) -> tuple[tuple[QdrantPoint, ...], str | int | None]:
        request: dict[str, Any] = {
            "filter": payload_filter,
            "limit": limit,
            "with_payload": True,
            "with_vector": False,
        }
        if offset is not None:
            request["offset"] = offset
        response = self._request(
            "POST", f"{self._collection_path(collection)}/points/scroll", request
        )
        result = self._mapping(response, "result")
        raw_points = result.get("points")
        next_offset = result.get("next_page_offset")
        if not isinstance(raw_points, list) or not (
            next_offset is None or isinstance(next_offset, (str, int))
        ):
            raise QdrantGatewayError("malformed Qdrant scroll response")
        return tuple(self._point(value) for value in raw_points), next_offset

    def search_points(
        self,
        collection: str,
        vector: tuple[float, ...],
        payload_filter: dict[str, Any],
        limit: int,
    ) -> tuple[QdrantScoredPoint, ...]:
        response = self._request(
            "POST",
            f"{self._collection_path(collection)}/points/search",
            {
                "vector": vector,
                "filter": payload_filter,
                "limit": limit,
                "with_payload": True,
                "with_vector": False,
            },
        )
        raw_points = response.get("result")
        if not isinstance(raw_points, list):
            raise QdrantGatewayError("malformed Qdrant search response")
        result: list[QdrantScoredPoint] = []
        for value in raw_points:
            point = self._point(value)
            score = value.get("score") if isinstance(value, dict) else None
            if not isinstance(score, (int, float)) or not math.isfinite(score):
                raise QdrantGatewayError("malformed Qdrant search score")
            result.append(
                QdrantScoredPoint(point.point_id, float(score), point.payload)
            )
        return tuple(result)

    @staticmethod
    def _mapping(value: dict[str, Any], key: str) -> dict[str, Any]:
        item = value.get(key)
        if not isinstance(item, dict):
            raise QdrantGatewayError(f"malformed Qdrant response field: {key}")
        return item

    @staticmethod
    def _point(value: object) -> QdrantPoint:
        if not isinstance(value, dict):
            raise QdrantGatewayError("malformed Qdrant point")
        point_id = value.get("id")
        payload = value.get("payload")
        if not isinstance(point_id, (str, int)) or not isinstance(payload, dict):
            raise QdrantGatewayError("malformed Qdrant point")
        return QdrantPoint(str(point_id), payload)

    @staticmethod
    def _collection_path(collection: str) -> str:
        return f"/collections/{quote(collection, safe='')}"

    def _request(
        self, method: str, path: str, payload: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        data = None if payload is None else json.dumps(payload).encode()
        request = Request(
            f"{self.base_url}{path}",
            data=data,
            headers={"Content-Type": "application/json"},
            method=method,
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                parsed = json.loads(response.read().decode())
        except HTTPError as error:
            raise QdrantGatewayError(
                f"Qdrant HTTP error {error.code}", error.code
            ) from error
        except (URLError, OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise QdrantGatewayError(f"Qdrant request failed: {error}") from error
        if not isinstance(parsed, dict):
            raise QdrantGatewayError("Qdrant response must be a JSON object")
        return parsed


class DeterministicKnowledgeChunker:
    """Split canonical Markdown sections into stable bounded chunks."""

    def chunk(
        self, documents: tuple[KnowledgeDocument, ...], repository_version: str
    ) -> tuple[KnowledgeChunk, ...]:
        result: list[KnowledgeChunk] = []
        for document in documents:
            ordinal = 0
            for section, text in self._sections(document):
                for part in self._bounded_parts(text):
                    digest = hashlib.sha256(part.encode()).hexdigest()
                    chunk_id = f"{document.document_id}-chunk-{ordinal:03d}"
                    point_id = uuid5(
                        POINT_NAMESPACE,
                        ":".join(
                            (
                                repository_version,
                                document.document_id,
                                document.version,
                                CHUNKER_VERSION,
                                str(ordinal),
                                digest,
                            )
                        ),
                    )
                    result.append(
                        KnowledgeChunk(
                            chunk_id=chunk_id,
                            point_id=point_id,
                            repository_version=repository_version,
                            document_id=document.document_id,
                            document_type=document.document_type,
                            document_title=document.title,
                            document_version=document.version,
                            verification_status=document.verification_status,
                            tags=document.tags,
                            sources=document.sources,
                            section=section,
                            ordinal=ordinal,
                            text=part,
                            content_sha256=digest,
                        )
                    )
                    ordinal += 1
        return tuple(result)

    @staticmethod
    def _sections(document: KnowledgeDocument) -> tuple[tuple[str, str], ...]:
        sections: list[tuple[str, str]] = []
        heading = document.title
        lines: list[str] = []
        for index, line in enumerate(document.content.splitlines()):
            if index == 0 and line == f"# {document.title}":
                continue
            if line.startswith("## "):
                if lines:
                    sections.append((heading, "\n".join(lines).strip()))
                heading = line[3:].strip()
                lines = [line]
            else:
                lines.append(line)
        if lines:
            sections.append((heading, "\n".join(lines).strip()))
        return tuple((name, text) for name, text in sections if text)

    @staticmethod
    def _bounded_parts(text: str) -> tuple[str, ...]:
        result: list[str] = []
        remaining = text.strip()
        while remaining:
            if len(remaining) <= MAX_CHUNK_CHARACTERS:
                result.append(remaining)
                break
            boundary = remaining.rfind("\n\n", 0, MAX_CHUNK_CHARACTERS + 1)
            if boundary <= 0:
                boundary = remaining.rfind(" ", 0, MAX_CHUNK_CHARACTERS + 1)
            if boundary <= 0:
                boundary = MAX_CHUNK_CHARACTERS
            result.append(remaining[:boundary].strip())
            remaining = remaining[boundary:].strip()
        return tuple(result)


class EmbeddingVector(Protocol):
    """Array-like vector returned by a semantic embedding backend."""

    def tolist(self) -> list[float]: ...


class EmbeddingModel(Protocol):
    """Narrow FastEmbed-compatible model boundary used by offline tests."""

    def embed(self, documents: list[str]) -> Iterable[EmbeddingVector]: ...


def _load_embedding_model() -> EmbeddingModel:
    try:
        from fastembed import TextEmbedding
    except ImportError as error:  # pragma: no cover - declared runtime dependency
        raise KnowledgeIndexError(
            "FastEmbed is required for semantic embeddings"
        ) from error
    return cast(EmbeddingModel, TextEmbedding(model_name=EMBEDDING_MODEL))


class SemanticTextEmbedder:
    """Local pretrained semantic embedding with validated normalized output."""

    def __init__(
        self,
        model: EmbeddingModel | None = None,
        model_loader: Callable[[], EmbeddingModel] = _load_embedding_model,
    ) -> None:
        self._model = model
        self._model_loader = model_loader

    def embed(self, text: str) -> tuple[float, ...]:
        if not text.strip():
            raise KnowledgeIndexError("embedding text must not be blank")
        if self._model is None:
            self._model = self._model_loader()
        raw_vectors = tuple(self._model.embed([text]))
        if len(raw_vectors) != 1:
            raise KnowledgeIndexError("semantic model must return exactly one vector")
        values = raw_vectors[0].tolist()
        if len(values) != VECTOR_DIMENSION or not all(
            isinstance(value, (int, float)) and math.isfinite(value) for value in values
        ):
            raise KnowledgeIndexError("semantic model returned an invalid vector")
        norm = math.sqrt(sum(float(value) * float(value) for value in values))
        if norm == 0:
            raise KnowledgeIndexError("semantic model returned a zero vector")
        return tuple(float(value) / norm for value in values)


def _must_filter(*conditions: dict[str, Any]) -> dict[str, Any]:
    return {"must": list(conditions)}


def _match(key: str, value: object) -> dict[str, Any]:
    return {"key": key, "match": {"value": value}}


class KnowledgeIndexer:
    """Explicitly synchronize canonical M6 knowledge into derived Qdrant state."""

    def __init__(
        self,
        repository: KnowledgeRepository,
        gateway: QdrantGateway,
        collection_name: str,
        chunker: DeterministicKnowledgeChunker | None = None,
        embedder: SemanticTextEmbedder | None = None,
    ) -> None:
        _validate_collection_name(collection_name)
        self.repository = repository
        self.gateway = gateway
        self.collection_name = collection_name
        self.chunker = chunker or DeterministicKnowledgeChunker()
        self.embedder = embedder or SemanticTextEmbedder()

    def sync(self) -> KnowledgeIndexSummary:
        try:
            manifest = self.repository.load_manifest()
            documents = self.repository.load_all()
            chunks = self.chunker.chunk(documents, manifest.repository_version)
            collection = self.gateway.get_collection(self.collection_name)
            if collection is None:
                self.gateway.create_collection(
                    self.collection_name, VECTOR_DIMENSION, DISTANCE
                )
            else:
                _validate_collection_schema(collection)
            existing = self._owned_points()
            current_ids = {str(chunk.point_id) for chunk in chunks}
            stale_ids = tuple(sorted(set(existing) - current_ids))
            if stale_ids:
                self.gateway.delete_points(self.collection_name, stale_ids)
            points = tuple(
                (
                    str(chunk.point_id),
                    self.embedder.embed(self._embedding_text(chunk)),
                    _chunk_payload(chunk),
                )
                for chunk in chunks
            )
            if points:
                self.gateway.upsert_points(self.collection_name, points)
        except (QdrantGatewayError, ValidationError, OSError) as error:
            raise KnowledgeIndexError(str(error)) from error
        return KnowledgeIndexSummary(
            collection_name=self.collection_name,
            repository_version=manifest.repository_version,
            document_count=len(documents),
            chunk_count=len(chunks),
            upserted_point_count=len(points),
            deleted_stale_point_count=len(stale_ids),
        )

    def _owned_points(self) -> dict[str, QdrantPoint]:
        result: dict[str, QdrantPoint] = {}
        offset: str | int | None = None
        seen_offsets: set[str | int] = set()
        while True:
            points, next_offset = self.gateway.scroll_points(
                self.collection_name,
                _must_filter(_match("index_owner", INDEX_OWNER)),
                100,
                offset,
            )
            for point in points:
                if point.payload.get("index_owner") != INDEX_OWNER:
                    raise KnowledgeIndexError("Qdrant returned a foreign owned point")
                result[point.point_id] = point
            if next_offset is None:
                return result
            if next_offset in seen_offsets:
                raise KnowledgeIndexError("Qdrant scroll offset repeated")
            seen_offsets.add(next_offset)
            offset = next_offset

    @staticmethod
    def _embedding_text(chunk: KnowledgeChunk) -> str:
        return "\n".join(
            (
                chunk.document_title,
                chunk.section,
                " ".join(chunk.tags),
                chunk.text,
            )
        )


class KnowledgeInspectionAPI:
    """Read-only document, index, chunk, metadata, and retrieval inspection."""

    def __init__(
        self,
        repository: KnowledgeRepository,
        gateway: QdrantGateway,
        collection_name: str,
        embedder: SemanticTextEmbedder | None = None,
    ) -> None:
        _validate_collection_name(collection_name)
        self.repository = repository
        self.gateway = gateway
        self.collection_name = collection_name
        self.embedder = embedder or SemanticTextEmbedder()

    def documents(self) -> tuple[KnowledgeDocumentSummary, ...]:
        return self.repository.inspect()

    def index_status(self) -> KnowledgeIndexStatus:
        try:
            collection = self.gateway.get_collection(self.collection_name)
        except QdrantGatewayError as error:
            raise KnowledgeIndexError(str(error)) from error
        if collection is None:
            return KnowledgeIndexStatus(
                collection_name=self.collection_name,
                exists=False,
            )
        return KnowledgeIndexStatus(
            collection_name=self.collection_name,
            exists=True,
            vector_dimension=collection.vector_size,
            distance=collection.distance,
            point_count=collection.point_count,
        )

    def chunks(
        self, document_id: str | None = None, limit: int = 100
    ) -> tuple[KnowledgeChunk, ...]:
        if not 1 <= limit <= 1000:
            raise KnowledgeIndexError(
                "chunk inspection limit must be between 1 and 1000"
            )
        repository_version = self.repository.load_manifest().repository_version
        conditions = [
            _match("index_owner", INDEX_OWNER),
            _match("repository_version", repository_version),
        ]
        if document_id is not None:
            conditions.append(_match("document_id", document_id))
        points = self._scroll(_must_filter(*conditions), limit)
        chunks = tuple(self._chunk_from_point(point) for point in points)
        return tuple(sorted(chunks, key=lambda item: (item.document_id, item.ordinal)))

    def chunk(self, chunk_id: str) -> KnowledgeChunk:
        repository_version = self.repository.load_manifest().repository_version
        points = self._scroll(
            _must_filter(
                _match("index_owner", INDEX_OWNER),
                _match("repository_version", repository_version),
                _match("chunk_id", chunk_id),
            ),
            2,
        )
        if not points:
            raise KnowledgeIndexError(f"indexed chunk does not exist: {chunk_id}")
        if len(points) != 1:
            raise KnowledgeIndexError(f"indexed chunk is not unique: {chunk_id}")
        return self._chunk_from_point(points[0])

    def retrieve(
        self,
        query: str,
        limit: int = 5,
        document_types: tuple[KnowledgeDocumentType, ...] = (),
    ) -> KnowledgeRetrievalResult:
        if not query.strip():
            raise KnowledgeIndexError("retrieval query must not be blank")
        if not 1 <= limit <= 20:
            raise KnowledgeIndexError("retrieval limit must be between 1 and 20")
        manifest = self.repository.load_manifest()
        conditions = [
            _match("index_owner", INDEX_OWNER),
            _match("repository_version", manifest.repository_version),
            _match("verification_status", "verified"),
        ]
        if document_types:
            conditions.append(
                {
                    "key": "document_type",
                    "match": {"any": [item.value for item in document_types]},
                }
            )
        try:
            _require_collection(self.gateway.get_collection(self.collection_name))
            raw_hits = self.gateway.search_points(
                self.collection_name,
                self.embedder.embed(query),
                _must_filter(*conditions),
                limit,
            )
            hits = tuple(
                KnowledgeRetrievalHit(
                    score=point.score,
                    chunk=self._chunk_from_scored_point(point),
                )
                for point in raw_hits
            )
            return KnowledgeRetrievalResult(
                query=query,
                limit=limit,
                collection_name=self.collection_name,
                repository_version=manifest.repository_version,
                hits=hits,
            )
        except (QdrantGatewayError, ValidationError) as error:
            raise KnowledgeIndexError(str(error)) from error

    def _scroll(
        self, payload_filter: dict[str, Any], limit: int
    ) -> tuple[QdrantPoint, ...]:
        try:
            _require_collection(self.gateway.get_collection(self.collection_name))
            result: list[QdrantPoint] = []
            offset: str | int | None = None
            seen_offsets: set[str | int] = set()
            while len(result) < limit:
                points, next_offset = self.gateway.scroll_points(
                    self.collection_name,
                    payload_filter,
                    min(100, limit - len(result)),
                    offset,
                )
                result.extend(points)
                if next_offset is None:
                    break
                if next_offset in seen_offsets:
                    raise KnowledgeIndexError("Qdrant scroll offset repeated")
                seen_offsets.add(next_offset)
                offset = next_offset
            return tuple(result[:limit])
        except QdrantGatewayError as error:
            raise KnowledgeIndexError(str(error)) from error

    @staticmethod
    def _chunk_from_point(point: QdrantPoint) -> KnowledgeChunk:
        return _validated_chunk_payload(point.point_id, point.payload)

    @staticmethod
    def _chunk_from_scored_point(point: QdrantScoredPoint) -> KnowledgeChunk:
        return _validated_chunk_payload(point.point_id, point.payload)


def _chunk_payload(chunk: KnowledgeChunk) -> dict[str, Any]:
    return {
        "index_owner": INDEX_OWNER,
        "index_schema_version": INDEX_SCHEMA_VERSION,
        **chunk.model_dump(mode="json"),
    }


def _validated_chunk_payload(point_id: str, payload: dict[str, Any]) -> KnowledgeChunk:
    if payload.get("index_owner") != INDEX_OWNER:
        raise KnowledgeIndexError("Qdrant point is not owned by this project")
    if payload.get("index_schema_version") != INDEX_SCHEMA_VERSION:
        raise KnowledgeIndexError("Qdrant point has an incompatible index schema")
    try:
        chunk = KnowledgeChunk.model_validate(
            {
                key: value
                for key, value in payload.items()
                if key not in {"index_owner", "index_schema_version"}
            }
        )
    except ValidationError as error:
        raise KnowledgeIndexError(
            f"invalid Qdrant knowledge payload: {error}"
        ) from error
    if str(chunk.point_id) != point_id:
        raise KnowledgeIndexError("Qdrant point ID does not match its payload")
    return chunk


def _validate_collection_name(collection_name: str) -> None:
    if COLLECTION_PATTERN.fullmatch(collection_name) is None:
        raise KnowledgeIndexError("invalid Qdrant collection name")


def _validate_collection_schema(collection: QdrantCollectionInfo) -> None:
    if collection.vector_size != VECTOR_DIMENSION or collection.distance != DISTANCE:
        raise KnowledgeIndexError(
            "existing Qdrant collection has an incompatible vector schema"
        )


def _require_collection(
    collection: QdrantCollectionInfo | None,
) -> QdrantCollectionInfo:
    if collection is None:
        raise KnowledgeIndexError("Qdrant knowledge collection does not exist")
    _validate_collection_schema(collection)
    return collection
