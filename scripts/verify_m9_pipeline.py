"""Verify the real M5 -> M8 -> M9 pipeline against isolated Qdrant."""

import argparse
import json
from pathlib import Path
from typing import Any

from kri.analysis import DeterministicAnalyzer
from kri.knowledge import KnowledgeRepository
from kri.knowledge_index import (
    KnowledgeIndexer,
    KnowledgeInspectionAPI,
    QdrantHttpGateway,
)
from kri.llm_input import LLMInputBuilder, LLMInputStore
from kri.observations import ObservationStore
from kri.rag import (
    AnalysisEvidenceRetriever,
    RetrievalEvaluator,
    load_evaluation_dataset,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify M5 through M9 using a retained real observation"
    )
    parser.add_argument("--url", required=True)
    parser.add_argument("--collection", required=True)
    parser.add_argument("--observation-directory", type=Path, required=True)
    parser.add_argument("--observation-id", required=True)
    parser.add_argument("--analysis-id", required=True)
    parser.add_argument("--package-id", required=True)
    parser.add_argument("--output-directory", type=Path, required=True)
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path("evaluation/m8-retrieval-v1.json"),
    )
    parser.add_argument("--knowledge-root", type=Path, default=Path("knowledge"))
    return parser.parse_args()


def write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def main() -> None:
    args = parse_args()
    args.output_directory.mkdir(parents=True, exist_ok=True)

    observation_store = ObservationStore(args.observation_directory)
    observation = observation_store.replay(args.observation_id)
    analysis = DeterministicAnalyzer().analyze_saved(
        observation_store,
        args.observation_id,
        analysis_id=args.analysis_id,
    )

    repository = KnowledgeRepository(args.knowledge_root)
    gateway = QdrantHttpGateway(args.url, timeout_seconds=30)
    indexer = KnowledgeIndexer(repository, gateway, args.collection)
    synchronization = indexer.sync()
    knowledge = KnowledgeInspectionAPI(
        repository,
        gateway,
        args.collection,
        embedder=indexer.embedder,
    )
    index_status = knowledge.index_status()

    evidence = AnalysisEvidenceRetriever(knowledge).retrieve(analysis)
    dataset = load_evaluation_dataset(args.dataset)
    evaluation = RetrievalEvaluator(knowledge).evaluate(dataset)
    if not evaluation.passed:
        raise RuntimeError("real M8 retrieval did not meet fixed quality thresholds")
    if any(not bundle.retrieval.hits for bundle in evidence.bundles):
        raise RuntimeError("an M8 evidence query returned no verified knowledge")

    package = LLMInputBuilder().build(
        analysis,
        evidence,
        package_id=args.package_id,
    )
    package_store = LLMInputStore(args.output_directory / "llm-inputs")
    package_path = package_store.save(package)
    loaded = package_store.load(package.package_id)
    if loaded != package:
        raise RuntimeError("persisted M9 package did not round-trip exactly")
    inspection = package_store.inspect(package.package_id)

    analysis_path = args.output_directory / f"{analysis.analysis_id}.json"
    evidence_path = args.output_directory / "operational-evidence.json"
    evaluation_path = args.output_directory / "retrieval-evaluation.json"
    write_json(analysis_path, analysis.model_dump(mode="json"))
    write_json(evidence_path, evidence.model_dump(mode="json"))
    write_json(evaluation_path, evaluation.model_dump(mode="json"))

    result = {
        "source_observation": {
            "observation_id": observation.observation_id,
            "identity": observation.workload_snapshot.identity.model_dump(mode="json"),
            "quality_status": observation.quality_report.status,
            "quality_issue_count": len(observation.quality_report.issues),
            "normalized_series_count": len(observation.normalized_series),
            "sample_count": sum(
                len(series.samples) for series in observation.normalized_series
            ),
            "source_digest_sha256": (observation.provenance.source_digest_sha256),
        },
        "analysis": {
            "path": str(analysis_path),
            "analysis_id": analysis.analysis_id,
            "sufficiency": analysis.sufficiency,
            "statistic_count": len(analysis.statistics),
            "condition_count": len(analysis.conditions),
            "recommendation_count": len(analysis.recommendations),
            "uncertainty_count": len(analysis.risks_and_uncertainties),
        },
        "qdrant": {
            "url": args.url,
            "collection": args.collection,
            "synchronization": synchronization.model_dump(mode="json"),
            "status": index_status.model_dump(mode="json"),
        },
        "retrieval": {
            "path": str(evidence_path),
            "bundle_count": len(evidence.bundles),
            "queries": [
                {
                    "query_id": bundle.query_id,
                    "hit_count": len(bundle.retrieval.hits),
                    "top_chunk_id": bundle.retrieval.hits[0].chunk.chunk_id,
                    "top_score": bundle.retrieval.hits[0].score,
                }
                for bundle in evidence.bundles
            ],
            "evaluation_path": str(evaluation_path),
            "evaluation_passed": evaluation.passed,
            "mean_recall_at_k": evaluation.mean_recall_at_k,
            "mean_reciprocal_rank_at_k": evaluation.mean_reciprocal_rank_at_k,
            "mean_ndcg_at_k": evaluation.mean_ndcg_at_k,
        },
        "llm_input": {
            "artifact_path": str(package_path),
            "inspection": inspection.model_dump(mode="json"),
            "analysis_digest_sha256": package.analysis_digest_sha256,
            "operational_evidence_digest_sha256": (
                package.operational_evidence_digest_sha256
            ),
            "round_trip_exact": loaded == package,
        },
    }
    summary_path = args.output_directory / "verification-summary.json"
    write_json(summary_path, result)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
