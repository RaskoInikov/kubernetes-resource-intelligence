"""Opt-in real Qdrant verification for M8 evidence retrieval and evaluation."""

import argparse
import json
from pathlib import Path

from kri.contracts import AnalysisReport
from kri.knowledge import KnowledgeRepository
from kri.knowledge_index import (
    KnowledgeIndexer,
    KnowledgeInspectionAPI,
    QdrantHttpGateway,
)
from kri.rag import (
    AnalysisEvidenceRetriever,
    RetrievalEvaluator,
    load_evaluation_dataset,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify M8 against one isolated Qdrant collection"
    )
    parser.add_argument("--url", required=True)
    parser.add_argument("--collection", required=True)
    parser.add_argument("--analysis", type=Path, required=True)
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path("evaluation/m8-retrieval-v1.json"),
    )
    parser.add_argument("--knowledge-root", type=Path, default=Path("knowledge"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    analysis = AnalysisReport.model_validate_json(
        args.analysis.read_text(encoding="utf-8")
    )
    dataset = load_evaluation_dataset(args.dataset)
    repository = KnowledgeRepository(args.knowledge_root)
    gateway = QdrantHttpGateway(args.url, timeout_seconds=30)
    indexer = KnowledgeIndexer(repository, gateway, args.collection)
    indexer.sync()
    knowledge = KnowledgeInspectionAPI(
        repository,
        gateway,
        args.collection,
        embedder=indexer.embedder,
    )

    evidence = AnalysisEvidenceRetriever(knowledge).retrieve(analysis)
    evaluation = RetrievalEvaluator(knowledge).evaluate(dataset)
    print(
        json.dumps(
            {
                "analysis_id": evidence.analysis_id,
                "observation_id": evidence.observation_id,
                "evidence_queries": [
                    {
                        "query_id": bundle.query_id,
                        "condition_ids": bundle.condition_ids,
                        "statistic_ids": bundle.statistic_ids,
                        "analysis_evidence_ids": bundle.analysis_evidence_ids,
                        "retrieved_chunk_ids": [
                            hit.chunk.chunk_id for hit in bundle.retrieval.hits
                        ],
                    }
                    for bundle in evidence.bundles
                ],
                "evaluation": evaluation.model_dump(mode="json"),
            },
            indent=2,
            sort_keys=True,
        )
    )
    if not evaluation.passed:
        raise SystemExit("retrieval evaluation did not meet its fixed thresholds")


if __name__ == "__main__":
    main()
