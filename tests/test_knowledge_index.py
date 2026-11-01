"""Offline tests for deterministic M7 Qdrant indexing and inspection."""

import hashlib
import json
import math
import sys
from collections.abc import Callable
from email.message import Message
from pathlib import Path
from types import ModuleType
from typing import Any
from urllib.error import HTTPError, URLError

import pytest
from pydantic import ValidationError

from kri.contracts import (
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeDocumentType,
    KnowledgeIndexStatus,
    KnowledgeIndexSummary,
    KnowledgeRetrievalHit,
    KnowledgeRetrievalResult,
    KnowledgeVerificationStatus,
)
from kri.knowledge import KnowledgeRepository
from kri.knowledge_index import (
    DISTANCE,
    EMBEDDING_MODEL,
    INDEX_OWNER,
    INDEX_SCHEMA_VERSION,
    VECTOR_DIMENSION,
    DeterministicKnowledgeChunker,
    EmbeddingVector,
    KnowledgeIndexer,
    KnowledgeIndexError,
    KnowledgeInspectionAPI,
    QdrantCollectionInfo,
    QdrantGatewayError,
    QdrantHttpGateway,
    QdrantPoint,
    QdrantScoredPoint,
    SemanticTextEmbedder,
    _load_embedding_model,
)

KNOWLEDGE_ROOT = Path(__file__).parents[1] / "knowledge"


class FakeVector:
    def __init__(self, values: list[float]) -> None:
        self.values = values

    def tolist(self) -> list[float]:
        return self.values


class FakeSemanticModel:
    """Deterministic model double; offline tests never download model weights."""

    def embed(self, documents: list[str]) -> tuple[EmbeddingVector, ...]:
        vectors: list[EmbeddingVector] = []
        for document in documents:
            values = [0.0] * VECTOR_DIMENSION
            for token in document.lower().split():
                digest = hashlib.sha256(token.encode()).digest()
                values[int.from_bytes(digest[:2]) % VECTOR_DIMENSION] += 1.0
            vectors.append(FakeVector(values))
        return tuple(vectors)


def offline_embedder() -> SemanticTextEmbedder:
    return SemanticTextEmbedder(model=FakeSemanticModel())


def offline_indexer(
    gateway: "FakeQdrantGateway",
    collection: str = "kubernetes_knowledge",
    chunker: DeterministicKnowledgeChunker | None = None,
) -> KnowledgeIndexer:
    return KnowledgeIndexer(
        repository(),
        gateway,
        collection,
        chunker=chunker,
        embedder=offline_embedder(),
    )


def offline_api(
    gateway: "FakeQdrantGateway", collection: str = "kubernetes_knowledge"
) -> KnowledgeInspectionAPI:
    return KnowledgeInspectionAPI(
        repository(), gateway, collection, embedder=offline_embedder()
    )


def _matches(payload: dict[str, Any], payload_filter: dict[str, Any]) -> bool:
    for condition in payload_filter.get("must", []):
        key = condition["key"]
        match = condition["match"]
        if "value" in match and payload.get(key) != match["value"]:
            return False
        if "any" in match and payload.get(key) not in match["any"]:
            return False
    return True


class FakeQdrantGateway:
    """In-memory gateway that applies the subset of Qdrant filters used by M7."""

    def __init__(self) -> None:
        self.collection: QdrantCollectionInfo | None = None
        self.points: dict[str, tuple[tuple[float, ...], dict[str, Any]]] = {}
        self.created: list[tuple[str, int, str]] = []
        self.upsert_calls: list[tuple[str, ...]] = []
        self.deleted: list[str] = []
        self.search_override: tuple[QdrantScoredPoint, ...] | None = None

    def get_collection(self, collection: str) -> QdrantCollectionInfo | None:
        if self.collection is None:
            return None
        return QdrantCollectionInfo(
            self.collection.vector_size,
            self.collection.distance,
            len(self.points),
        )

    def create_collection(
        self, collection: str, vector_size: int, distance: str
    ) -> None:
        self.created.append((collection, vector_size, distance))
        self.collection = QdrantCollectionInfo(vector_size, distance, 0)

    def upsert_points(
        self,
        collection: str,
        points: tuple[tuple[str, tuple[float, ...], dict[str, Any]], ...],
    ) -> None:
        self.upsert_calls.append(tuple(point[0] for point in points))
        for point_id, vector, payload in points:
            self.points[point_id] = (vector, payload)

    def delete_points(self, collection: str, point_ids: tuple[str, ...]) -> None:
        self.deleted.extend(point_ids)
        for point_id in point_ids:
            self.points.pop(point_id, None)

    def scroll_points(
        self,
        collection: str,
        payload_filter: dict[str, Any],
        limit: int,
        offset: str | int | None = None,
    ) -> tuple[tuple[QdrantPoint, ...], str | int | None]:
        values = [
            QdrantPoint(point_id, payload)
            for point_id, (_, payload) in sorted(self.points.items())
            if _matches(payload, payload_filter)
        ]
        start = int(offset or 0)
        page = tuple(values[start : start + limit])
        next_offset = start + limit if start + limit < len(values) else None
        return page, next_offset

    def search_points(
        self,
        collection: str,
        vector: tuple[float, ...],
        payload_filter: dict[str, Any],
        limit: int,
    ) -> tuple[QdrantScoredPoint, ...]:
        if self.search_override is not None:
            return self.search_override
        values = [
            QdrantScoredPoint(
                point_id,
                sum(left * right for left, right in zip(vector, stored, strict=True)),
                payload,
            )
            for point_id, (stored, payload) in self.points.items()
            if _matches(payload, payload_filter)
        ]
        return tuple(sorted(values, key=lambda item: item.score, reverse=True)[:limit])


def repository() -> KnowledgeRepository:
    return KnowledgeRepository(KNOWLEDGE_ROOT)


def synced_gateway() -> FakeQdrantGateway:
    gateway = FakeQdrantGateway()
    offline_indexer(gateway).sync()
    return gateway


def test_chunking_is_deterministic_bounded_and_provenance_complete() -> None:
    repo = repository()
    manifest = repo.load_manifest()
    chunker = DeterministicKnowledgeChunker()

    first = chunker.chunk(repo.load_all(), manifest.repository_version)
    second = chunker.chunk(repo.load_all(), manifest.repository_version)

    assert first == second
    assert len(first) == 26
    assert all(0 < len(item.text) <= 1200 for item in first)
    assert all(item.repository_version == "1.0.0" for item in first)
    assert all(item.sources and item.tags for item in first)
    assert all(item.content_sha256 for item in first)
    assert all(str(item.point_id) for item in first)
    by_document: dict[str, list[int]] = {}
    for chunk in first:
        by_document.setdefault(chunk.document_id, []).append(chunk.ordinal)
    assert all(
        ordinals == list(range(len(ordinals))) for ordinals in by_document.values()
    )


def test_chunker_splits_on_paragraph_space_and_hard_boundaries() -> None:
    document = repository().get("runbook-cpu-throttling")
    long_content = (
        f"# {document.title}\n\n## Long\n" + ("alpha " * 250) + "\n\n" + ("b" * 1300)
    )
    modified = document.model_copy(update={"content": long_content})

    chunks = DeterministicKnowledgeChunker().chunk((modified,), "1.0.0")

    assert len(chunks) >= 3
    assert all(len(item.text) <= 1200 for item in chunks)
    assert chunks[0].section == "Long"


def test_chunker_handles_heading_first_empty_and_empty_parts() -> None:
    document = repository().get("runbook-cpu-throttling")
    heading_first = document.model_copy(
        update={"content": f"# {document.title}\n## First\nBody"}
    )
    empty = document.model_copy(update={"content": f"# {document.title}"})

    assert DeterministicKnowledgeChunker._sections(heading_first) == (
        ("First", "## First\nBody"),
    )
    assert DeterministicKnowledgeChunker._sections(empty) == ()
    assert DeterministicKnowledgeChunker._bounded_parts("") == ()


def test_semantic_embedder_is_deterministic_normalized_and_rejects_blank() -> None:
    embedder = offline_embedder()

    first = embedder.embed("CPU throttling and request limits")
    second = embedder.embed("CPU throttling and request limits")

    assert first == second
    assert len(first) == VECTOR_DIMENSION
    assert math.sqrt(sum(value * value for value in first)) == pytest.approx(1.0)
    assert embedder.embed("memory request") != first
    with pytest.raises(KnowledgeIndexError, match="blank"):
        embedder.embed(" ")


@pytest.mark.parametrize(
    ("vectors", "message"),
    [
        ((), "exactly one"),
        ((FakeVector([1.0] * VECTOR_DIMENSION),) * 2, "exactly one"),
        ((FakeVector([1.0]),), "invalid vector"),
        (
            (FakeVector([math.nan] + [1.0] * (VECTOR_DIMENSION - 1)),),
            "invalid vector",
        ),
        ((FakeVector([0.0] * VECTOR_DIMENSION),), "zero vector"),
    ],
)
def test_semantic_embedder_rejects_invalid_model_output(
    vectors: tuple[EmbeddingVector, ...], message: str
) -> None:
    class FixedModel:
        def embed(self, documents: list[str]) -> tuple[EmbeddingVector, ...]:
            return vectors

    with pytest.raises(KnowledgeIndexError, match=message):
        SemanticTextEmbedder(model=FixedModel()).embed("valid text")


def test_semantic_embedder_loads_backend_once() -> None:
    loads = 0

    def loader() -> FakeSemanticModel:
        nonlocal loads
        loads += 1
        return FakeSemanticModel()

    embedder = SemanticTextEmbedder(model_loader=loader)
    embedder.embed("first")
    embedder.embed("second")

    assert loads == 1


def test_fastembed_loader_uses_the_pinned_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = ModuleType("fastembed")
    requested: list[str] = []

    def text_embedding(*, model_name: str) -> FakeSemanticModel:
        requested.append(model_name)
        return FakeSemanticModel()

    module.TextEmbedding = text_embedding  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "fastembed", module)

    assert isinstance(_load_embedding_model(), FakeSemanticModel)
    assert requested == [EMBEDDING_MODEL]


def test_sync_creates_collection_upserts_and_is_idempotent() -> None:
    gateway = FakeQdrantGateway()
    indexer = offline_indexer(gateway)

    first = indexer.sync()
    point_ids = set(gateway.points)
    second = indexer.sync()

    assert gateway.created == [("kubernetes_knowledge", VECTOR_DIMENSION, DISTANCE)]
    assert first.document_count == 6
    assert first.chunk_count == 26
    assert first.upserted_point_count == 26
    assert first.deleted_stale_point_count == 0
    assert set(gateway.points) == point_ids
    assert second.deleted_stale_point_count == 0
    assert len(gateway.upsert_calls) == 2
    assert all(
        payload["index_owner"] == INDEX_OWNER
        and payload["index_schema_version"] == INDEX_SCHEMA_VERSION
        and payload["embedding_model"] == EMBEDDING_MODEL
        for _, payload in gateway.points.values()
    )


def test_sync_accepts_an_empty_chunk_set() -> None:
    class EmptyChunker(DeterministicKnowledgeChunker):
        def chunk(
            self,
            documents: tuple[KnowledgeDocument, ...],
            repository_version: str,
        ) -> tuple[KnowledgeChunk, ...]:
            return ()

    gateway = FakeQdrantGateway()
    indexer = offline_indexer(gateway, chunker=EmptyChunker())

    summary = indexer.sync()

    assert summary.chunk_count == 0
    assert summary.upserted_point_count == 0
    assert gateway.points == {}


def test_sync_deletes_only_stale_owned_points() -> None:
    gateway = synced_gateway()
    zero = (0.0,) * VECTOR_DIMENSION
    gateway.points["stale-owned"] = (
        zero,
        {"index_owner": INDEX_OWNER, "repository_version": "0.9.0"},
    )
    gateway.points["foreign"] = (
        zero,
        {"index_owner": "another-project", "repository_version": "0.9.0"},
    )

    summary = offline_indexer(gateway).sync()

    assert summary.deleted_stale_point_count == 1
    assert gateway.deleted == ["stale-owned"]
    assert "foreign" in gateway.points


@pytest.mark.parametrize(
    "collection",
    [
        QdrantCollectionInfo(128, DISTANCE, 0),
        QdrantCollectionInfo(VECTOR_DIMENSION, "Dot", 0),
    ],
)
def test_sync_rejects_incompatible_collection(
    collection: QdrantCollectionInfo,
) -> None:
    gateway = FakeQdrantGateway()
    gateway.collection = collection

    with pytest.raises(KnowledgeIndexError, match="incompatible"):
        offline_indexer(gateway).sync()


def test_sync_rejects_foreign_filtered_point_and_repeated_offset() -> None:
    class ForeignGateway(FakeQdrantGateway):
        def scroll_points(
            self,
            collection: str,
            payload_filter: dict[str, Any],
            limit: int,
            offset: str | int | None = None,
        ) -> tuple[tuple[QdrantPoint, ...], str | int | None]:
            return (QdrantPoint("foreign", {"index_owner": "other"}),), None

    foreign = ForeignGateway()
    foreign.collection = QdrantCollectionInfo(VECTOR_DIMENSION, DISTANCE, 1)
    with pytest.raises(KnowledgeIndexError, match="foreign owned"):
        offline_indexer(foreign, "collection").sync()

    class RepeatingGateway(FakeQdrantGateway):
        def scroll_points(
            self,
            collection: str,
            payload_filter: dict[str, Any],
            limit: int,
            offset: str | int | None = None,
        ) -> tuple[tuple[QdrantPoint, ...], str | int | None]:
            return (), "same"

    repeating = RepeatingGateway()
    repeating.collection = QdrantCollectionInfo(VECTOR_DIMENSION, DISTANCE, 0)
    with pytest.raises(KnowledgeIndexError, match="offset repeated"):
        offline_indexer(repeating, "collection").sync()


def test_sync_wraps_gateway_failure_and_rejects_collection_name() -> None:
    class FailingGateway(FakeQdrantGateway):
        def get_collection(self, collection: str) -> QdrantCollectionInfo | None:
            raise QdrantGatewayError("unavailable")

    with pytest.raises(KnowledgeIndexError, match="unavailable"):
        offline_indexer(FailingGateway(), "collection").sync()
    with pytest.raises(KnowledgeIndexError, match="collection name"):
        offline_indexer(FakeQdrantGateway(), "not safe!")
    with pytest.raises(KnowledgeIndexError, match="collection name"):
        offline_api(FakeQdrantGateway(), "not safe!")


def test_read_only_api_inspects_documents_status_chunks_and_retrieval() -> None:
    gateway = synced_gateway()
    api = offline_api(gateway)

    documents = api.documents()
    status = api.index_status()
    chunks = api.chunks(limit=100)
    cpu_chunks = api.chunks("runbook-cpu-throttling")
    selected = api.chunk(cpu_chunks[0].chunk_id)
    result = api.retrieve("CPU throttling limit request", limit=4)
    runbooks = api.retrieve(
        "memory request limit",
        limit=5,
        document_types=(KnowledgeDocumentType.DIAGNOSTIC_RUNBOOK,),
    )

    assert len(documents) == 6
    assert status.exists is True
    assert status.vector_dimension == VECTOR_DIMENSION
    assert status.distance == DISTANCE
    assert status.point_count == 26
    assert len(chunks) == 26
    assert len(cpu_chunks) == 5
    assert selected == cpu_chunks[0]
    assert len(result.hits) == 4
    assert [item.score for item in result.hits] == sorted(
        (item.score for item in result.hits), reverse=True
    )
    assert all(
        hit.chunk.verification_status is KnowledgeVerificationStatus.VERIFIED
        and hit.chunk.sources
        for hit in result.hits
    )
    assert all(
        hit.chunk.document_type is KnowledgeDocumentType.DIAGNOSTIC_RUNBOOK
        for hit in runbooks.hits
    )


def test_read_only_api_reports_absent_collection_and_validates_bounds() -> None:
    gateway = FakeQdrantGateway()
    api = offline_api(gateway, "collection")

    assert api.index_status() == KnowledgeIndexStatus(
        collection_name="collection", exists=False
    )
    for limit in (0, 1001):
        with pytest.raises(KnowledgeIndexError, match="inspection limit"):
            api.chunks(limit=limit)
    for limit in (0, 21):
        with pytest.raises(KnowledgeIndexError, match="retrieval limit"):
            api.retrieve("cpu", limit=limit)
    with pytest.raises(KnowledgeIndexError, match="blank"):
        api.retrieve("  ")
    with pytest.raises(KnowledgeIndexError, match="does not exist"):
        api.chunks()
    with pytest.raises(KnowledgeIndexError, match="does not exist"):
        api.retrieve("cpu")


def test_chunk_lookup_reports_missing_and_duplicate() -> None:
    gateway = synced_gateway()
    api = offline_api(gateway, "collection")

    with pytest.raises(KnowledgeIndexError, match="does not exist"):
        api.chunk("missing")

    chunk = api.chunks(limit=1)[0]
    original_id = str(chunk.point_id)
    vector, payload = gateway.points[original_id]
    duplicate_payload = {**payload, "point_id": "00000000-0000-0000-0000-000000000001"}
    gateway.points["00000000-0000-0000-0000-000000000001"] = (
        vector,
        duplicate_payload,
    )
    with pytest.raises(KnowledgeIndexError, match="not unique"):
        api.chunk(chunk.chunk_id)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (
            lambda payload: payload.update(index_schema_version="1.0"),
            "incompatible index schema",
        ),
        (lambda payload: payload.update(text="tampered"), "invalid Qdrant"),
        (
            lambda payload: payload.update(
                point_id="00000000-0000-0000-0000-000000000001"
            ),
            "does not match",
        ),
    ],
)
def test_inspection_rejects_invalid_qdrant_payload(
    mutation: Callable[[dict[str, Any]], None], message: str
) -> None:
    gateway = synced_gateway()
    point_id = next(iter(gateway.points))
    vector, original = gateway.points[point_id]
    payload = {**original}
    mutation(payload)
    gateway.points = {point_id: (vector, payload)}
    api = offline_api(gateway, "collection")

    with pytest.raises(KnowledgeIndexError, match=message):
        api.chunks()


def test_retrieval_rejects_unverified_unordered_duplicate_and_invalid_score() -> None:
    gateway = synced_gateway()
    api = offline_api(gateway, "collection")
    point_id = next(iter(gateway.points))
    _, payload = gateway.points[point_id]

    foreign = {**payload, "index_owner": "foreign"}
    gateway.search_override = (QdrantScoredPoint(point_id, 0.5, foreign),)
    with pytest.raises(KnowledgeIndexError, match="not owned"):
        api.retrieve("cpu")

    unverified = {**payload, "verification_status": "needs_review"}
    gateway.search_override = (QdrantScoredPoint(point_id, 0.5, unverified),)
    with pytest.raises(KnowledgeIndexError, match="verified"):
        api.retrieve("cpu")

    second_id = next(value for value in gateway.points if value != point_id)
    _, second_payload = gateway.points[second_id]
    gateway.search_override = (
        QdrantScoredPoint(point_id, 0.2, payload),
        QdrantScoredPoint(second_id, 0.8, second_payload),
    )
    with pytest.raises(KnowledgeIndexError, match="descending"):
        api.retrieve("cpu")

    gateway.search_override = (
        QdrantScoredPoint(point_id, 0.8, payload),
        QdrantScoredPoint(point_id, 0.2, payload),
    )
    with pytest.raises(KnowledgeIndexError, match="unique point"):
        api.retrieve("cpu")

    gateway.search_override = (QdrantScoredPoint(point_id, 2.0, payload),)
    with pytest.raises(KnowledgeIndexError, match="less than or equal to 1"):
        api.retrieve("cpu")


def test_inspection_wraps_gateway_failures_and_repeated_scroll_offset() -> None:
    class FailingGateway(FakeQdrantGateway):
        def get_collection(self, collection: str) -> QdrantCollectionInfo | None:
            raise QdrantGatewayError("offline")

    failing = offline_api(FailingGateway(), "collection")
    with pytest.raises(KnowledgeIndexError, match="offline"):
        failing.index_status()
    with pytest.raises(KnowledgeIndexError, match="offline"):
        failing.chunks()
    with pytest.raises(KnowledgeIndexError, match="offline"):
        failing.retrieve("cpu")

    class RepeatingGateway(FakeQdrantGateway):
        def scroll_points(
            self,
            collection: str,
            payload_filter: dict[str, Any],
            limit: int,
            offset: str | int | None = None,
        ) -> tuple[tuple[QdrantPoint, ...], str | int | None]:
            return (), "same"

    repeating = RepeatingGateway()
    repeating.collection = QdrantCollectionInfo(VECTOR_DIMENSION, DISTANCE, 0)
    with pytest.raises(KnowledgeIndexError, match="offset repeated"):
        offline_api(repeating, "collection").chunks()


class _HttpResponse:
    def __init__(self, payload: object) -> None:
        self.payload = json.dumps(payload).encode()

    def __enter__(self) -> "_HttpResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return self.payload


def test_http_gateway_success_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    responses = iter(
        (
            {
                "result": {
                    "config": {
                        "params": {
                            "vectors": {"size": VECTOR_DIMENSION, "distance": DISTANCE}
                        }
                    },
                    "points_count": 1,
                }
            },
            {"result": True},
            {"result": True},
            {"result": True},
            {
                "result": {
                    "points": [{"id": 1, "payload": {"value": "stored"}}],
                    "next_page_offset": "next",
                }
            },
            {"result": [{"id": "id", "score": 0.5, "payload": {"value": "stored"}}]},
        )
    )
    requests: list[tuple[str, str, dict[str, object] | None]] = []

    def fake_urlopen(request: Any, timeout: float) -> _HttpResponse:
        body = None if request.data is None else json.loads(request.data)
        requests.append((request.method, request.full_url, body))
        assert timeout == 3
        return _HttpResponse(next(responses))

    monkeypatch.setattr("kri.knowledge_index.urlopen", fake_urlopen)
    gateway = QdrantHttpGateway("http://qdrant.test/", timeout_seconds=3)

    assert gateway.get_collection("collection") == QdrantCollectionInfo(
        VECTOR_DIMENSION, DISTANCE, 1
    )
    gateway.create_collection("collection", VECTOR_DIMENSION, DISTANCE)
    gateway.upsert_points("collection", (("id", (1.0,), {"a": 1}),))
    gateway.delete_points("collection", ("id",))
    points, offset = gateway.scroll_points("collection", {"must": []}, 1, "old")
    hits = gateway.search_points("collection", (1.0,), {"must": []}, 1)

    assert points == (QdrantPoint("1", {"value": "stored"}),)
    assert offset == "next"
    assert hits == (QdrantScoredPoint("id", 0.5, {"value": "stored"}),)
    assert requests[0][:2] == (
        "GET",
        "http://qdrant.test/collections/collection",
    )
    scroll_body = requests[4][2]
    assert scroll_body is not None
    assert scroll_body["offset"] == "old"


def test_http_gateway_404_and_transport_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gateway = QdrantHttpGateway("http://qdrant.test")

    def missing(*args: object, **kwargs: object) -> None:
        raise HTTPError("url", 404, "missing", Message(), None)

    monkeypatch.setattr("kri.knowledge_index.urlopen", missing)
    assert gateway.get_collection("missing") is None

    def forbidden(*args: object, **kwargs: object) -> None:
        raise HTTPError("url", 403, "forbidden", Message(), None)

    monkeypatch.setattr("kri.knowledge_index.urlopen", forbidden)
    with pytest.raises(QdrantGatewayError, match="403"):
        gateway.get_collection("forbidden")

    def unavailable(*args: object, **kwargs: object) -> None:
        raise URLError("offline")

    monkeypatch.setattr("kri.knowledge_index.urlopen", unavailable)
    with pytest.raises(QdrantGatewayError, match="request failed"):
        gateway.create_collection("collection", VECTOR_DIMENSION, DISTANCE)


@pytest.mark.parametrize(
    ("operation", "response", "message"),
    [
        ("collection", [], "JSON object"),
        ("collection", {"result": []}, "field: result"),
        ("collection", {"result": {"config": []}}, "field: config"),
        (
            "collection",
            {"result": {"config": {"params": []}}},
            "field: params",
        ),
        (
            "collection",
            {"result": {"config": {"params": {"vectors": []}}}},
            "field: vectors",
        ),
        (
            "collection",
            {
                "result": {
                    "config": {"params": {"vectors": {"size": "bad"}}},
                    "points_count": 0,
                }
            },
            "collection metadata",
        ),
        ("scroll", {"result": {"points": "bad"}}, "scroll response"),
        (
            "scroll",
            {"result": {"points": [], "next_page_offset": []}},
            "scroll response",
        ),
        ("scroll", {"result": {"points": ["bad"]}}, "point"),
        (
            "scroll",
            {"result": {"points": [{"id": [], "payload": {}}]}},
            "point",
        ),
        ("search", {"result": {}}, "search response"),
        (
            "search",
            {"result": [{"id": "id", "payload": {}, "score": "bad"}]},
            "search score",
        ),
    ],
)
def test_http_gateway_rejects_malformed_responses(
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
    response: object,
    message: str,
) -> None:
    monkeypatch.setattr(
        "kri.knowledge_index.urlopen",
        lambda *args, **kwargs: _HttpResponse(response),
    )
    gateway = QdrantHttpGateway("http://qdrant.test")

    with pytest.raises(QdrantGatewayError, match=message):
        if operation == "collection":
            gateway.get_collection("collection")
        elif operation == "scroll":
            gateway.scroll_points("collection", {"must": []}, 1)
        else:
            gateway.search_points("collection", (1.0,), {"must": []}, 1)


def test_http_gateway_rejects_invalid_json(monkeypatch: pytest.MonkeyPatch) -> None:
    response = _HttpResponse({})
    response.payload = b"not-json"
    monkeypatch.setattr("kri.knowledge_index.urlopen", lambda *args, **kwargs: response)

    with pytest.raises(QdrantGatewayError, match="request failed"):
        QdrantHttpGateway("http://qdrant.test").get_collection("collection")


def test_m7_contracts_reject_invalid_chunk_index_and_retrieval_content() -> None:
    gateway = synced_gateway()
    point_id = next(iter(gateway.points))
    _, payload = gateway.points[point_id]
    chunk_data = {
        key: value
        for key, value in payload.items()
        if key not in {"index_owner", "index_schema_version"}
    }

    with pytest.raises(ValidationError, match="digest"):
        KnowledgeChunk.model_validate({**chunk_data, "content_sha256": "0" * 64})
    with pytest.raises(ValidationError, match="semantic"):
        KnowledgeChunk.model_validate({**chunk_data, "repository_version": "1"})
    with pytest.raises(ValidationError, match="document ID"):
        KnowledgeChunk.model_validate({**chunk_data, "document_id": "BAD"})
    with pytest.raises(ValidationError, match="semantic"):
        KnowledgeIndexSummary.model_validate(
            {
                "collection_name": "collection",
                "repository_version": "bad",
                "document_count": 0,
                "chunk_count": 0,
                "upserted_point_count": 0,
                "deleted_stale_point_count": 0,
            }
        )
    with pytest.raises(ValidationError, match="requires collection metadata"):
        KnowledgeIndexStatus(collection_name="collection", exists=True)
    with pytest.raises(ValidationError, match="cannot contain"):
        KnowledgeIndexStatus(
            collection_name="collection",
            exists=False,
            vector_dimension=VECTOR_DIMENSION,
            distance="Cosine",
            point_count=0,
        )

    chunk = KnowledgeChunk.model_validate(chunk_data)
    unverified = chunk.model_copy(
        update={"verification_status": KnowledgeVerificationStatus.NEEDS_REVIEW}
    )
    with pytest.raises(ValidationError, match="verified knowledge"):
        KnowledgeRetrievalHit(score=0.5, chunk=unverified)

    hit = KnowledgeRetrievalHit(score=0.5, chunk=chunk)
    other = hit.model_copy(update={"score": 0.8})
    base = {
        "query": "cpu",
        "limit": 2,
        "collection_name": "collection",
        "repository_version": "1.0.0",
    }
    with pytest.raises(ValidationError, match="descending"):
        KnowledgeRetrievalResult(**base, hits=(hit, other))
    with pytest.raises(ValidationError, match="unique point"):
        KnowledgeRetrievalResult(**base, hits=(other, hit))
    second_payload = list(gateway.points.values())[1][1]
    second_chunk = KnowledgeChunk.model_validate(
        {
            key: value
            for key, value in second_payload.items()
            if key not in {"index_owner", "index_schema_version"}
        }
    )
    second_hit = KnowledgeRetrievalHit(score=0.4, chunk=second_chunk)
    with pytest.raises(ValidationError, match="cannot exceed"):
        KnowledgeRetrievalResult(**{**base, "limit": 1}, hits=(hit, second_hit))
    with pytest.raises(ValidationError, match="blank"):
        KnowledgeRetrievalResult(**{**base, "query": " "}, hits=())
    with pytest.raises(ValidationError, match="semantic"):
        KnowledgeRetrievalResult(**{**base, "repository_version": "bad"}, hits=())
