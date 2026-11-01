"""Opt-in real Qdrant verification for M7 semantic indexing and inspection."""

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from kri.knowledge import KnowledgeRepository
from kri.knowledge_index import (
    EMBEDDING_MODEL,
    KnowledgeIndexer,
    KnowledgeInspectionAPI,
    QdrantHttpGateway,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Mutate one isolated Qdrant collection and verify M7"
    )
    parser.add_argument("--url", required=True)
    parser.add_argument("--collection", required=True)
    parser.add_argument("--knowledge-root", type=Path, default=Path("knowledge"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    repository = KnowledgeRepository(args.knowledge_root)
    gateway = QdrantHttpGateway(args.url, timeout_seconds=30)
    indexer = KnowledgeIndexer(repository, gateway, args.collection)
    api = KnowledgeInspectionAPI(
        repository,
        gateway,
        args.collection,
        embedder=indexer.embedder,
    )

    first_sync = indexer.sync()
    first_chunks = api.chunks(limit=1000)
    second_sync = indexer.sync()
    second_chunks = api.chunks(limit=1000)
    documents = api.documents()
    status = api.index_status()
    cpu = api.retrieve(
        "Why is a Kubernetes container throttled when it reaches its CPU limit?",
        limit=5,
    )
    memory = api.retrieve(
        "How should memory requests be adjusted after observing working set usage?",
        limit=5,
    )

    first_ids = tuple(str(chunk.point_id) for chunk in first_chunks)
    second_ids = tuple(str(chunk.point_id) for chunk in second_chunks)
    if len(documents) != first_sync.document_count:
        raise RuntimeError("document inspection count does not match synchronization")
    if status.point_count != first_sync.chunk_count:
        raise RuntimeError("Qdrant point count does not match generated chunks")
    if first_ids != second_ids:
        raise RuntimeError("point identities changed during idempotent synchronization")
    if second_sync.deleted_stale_point_count != 0:
        raise RuntimeError("second synchronization unexpectedly deleted points")
    if not cpu.hits or not memory.hits:
        raise RuntimeError("semantic retrieval returned no verified knowledge")
    if any(chunk.embedding_model != EMBEDDING_MODEL for chunk in second_chunks):
        raise RuntimeError("indexed chunks do not identify the configured model")

    print(
        json.dumps(
            {
                "verified_at": datetime.now(UTC).isoformat(),
                "qdrant_url": args.url,
                "collection": args.collection,
                "embedding_model": EMBEDDING_MODEL,
                "first_sync": first_sync.model_dump(mode="json"),
                "second_sync": second_sync.model_dump(mode="json"),
                "index_status": status.model_dump(mode="json"),
                "documents": [item.model_dump(mode="json") for item in documents],
                "chunk_count": len(second_chunks),
                "point_ids_stable": first_ids == second_ids,
                "cpu_retrieval": cpu.model_dump(mode="json"),
                "memory_retrieval": memory.model_dump(mode="json"),
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
