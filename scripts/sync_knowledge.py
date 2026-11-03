"""Explicitly synchronize canonical knowledge into configured local Qdrant."""

import json

from kri.config import PROJECT_ROOT, load_settings
from kri.knowledge import KnowledgeRepository
from kri.knowledge_index import KnowledgeIndexer, QdrantHttpGateway


def main() -> None:
    settings = load_settings()
    summary = KnowledgeIndexer(
        KnowledgeRepository(PROJECT_ROOT / "knowledge"),
        QdrantHttpGateway(str(settings.qdrant_url), timeout_seconds=30),
        settings.qdrant_collection,
    ).sync()
    print(json.dumps(summary.model_dump(mode="json"), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
