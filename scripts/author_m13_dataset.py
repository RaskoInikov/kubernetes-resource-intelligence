"""Render the fixed M13 dataset from retained deterministic M9 source facts."""

from datetime import UTC, datetime
from pathlib import Path

from kri.contracts import (
    CitationJudgment,
    ExpectedNumericalFact,
    ExpectedRecommendation,
    InferenceOptions,
    LLMQualityCase,
    LLMQualityDataset,
    LLMQualityDatasetEnvelope,
)
from kri.llm_input import LLMInputStore
from kri.quality_evaluation import quality_dataset_digest

SOURCES = (
    "llm-input-ui-20261102154751",
    "llm-input-ui-20261102161957",
)
CASE_IDS = ("cpu-memory-pressure-a", "cpu-pressure-b")
MODEL_DIGEST = "359d7dd4bcdab3d86b87d73ac27966f4dbb9f5efdfcc75d34a8764a09474fae7"


def _knowledge_ids(target_id: str, available: tuple[str, ...]) -> tuple[str, ...]:
    prefix = (
        "runbook-memory-sizing" if "memory" in target_id else "runbook-cpu-throttling"
    )
    return tuple(value for value in available if value.startswith(prefix))


def build_dataset(source_directory: Path) -> LLMQualityDatasetEnvelope:
    """Build labels solely from retained M5/M9 facts, never model output."""

    store = LLMInputStore(source_directory)
    cases: list[LLMQualityCase] = []
    for package_id, case_id in zip(SOURCES, CASE_IDS, strict=True):
        artifact = store.load_artifact(package_id)
        package = artifact.package
        chunks = tuple(item.chunk_id for item in package.evidence_excerpts)
        citations = tuple(
            CitationJudgment(
                target_id=item.condition_id,
                required_analysis_ids=item.evidence_ids,
                allowed_knowledge_ids=_knowledge_ids(item.condition_id, chunks),
                required_knowledge_ids=(_knowledge_ids(item.condition_id, chunks)[-1:]),
            )
            for item in package.conditions
        ) + tuple(
            CitationJudgment(
                target_id=item.recommendation_id,
                required_analysis_ids=item.evidence_ids,
                allowed_knowledge_ids=_knowledge_ids(item.resource, chunks),
                required_knowledge_ids=(_knowledge_ids(item.resource, chunks)[-1:]),
            )
            for item in package.recommendations
        )
        cases.append(
            LLMQualityCase(
                case_id=case_id,
                package_id=package.package_id,
                package_sha256=artifact.package_sha256,
                analysis_id=package.analysis_id,
                observation_id=package.observation_id,
                expected_condition_ids=tuple(
                    item.condition_id for item in package.conditions
                ),
                expected_facts=tuple(
                    ExpectedNumericalFact(
                        statistic_id=item.statistic_id,
                        value=item.value,
                        unit=item.unit,
                    )
                    for item in package.statistics
                ),
                expected_uncertainties=package.risks_and_uncertainties,
                expected_recommendations=tuple(
                    ExpectedRecommendation(
                        recommendation_id=item.recommendation_id,
                        resource=item.resource,
                        current_value=item.current_value,
                        recommended_value=item.recommended_value,
                    )
                    for item in package.recommendations
                ),
                citation_judgments=citations,
                exclusions=(
                    "Do not infer effectiveness before a bounded "
                    "post-change experiment.",
                    "Do not score prose style or fluency as factual correctness.",
                    "Do not treat absent application error metrics as zero errors.",
                ),
                provenance=(
                    "Retained real kind/Prometheus incident package; labels copy the "
                    "immutable deterministic M5/M9 closure before M13 generation."
                ),
            )
        )
    dataset = LLMQualityDataset(
        dataset_version="1.0.0",
        created_at=datetime(2026, 11, 5, 9, 0, tzinfo=UTC),
        author="quality-evaluation-authors",
        reviewer="project-quality-reviewers",
        reviewed_at=datetime(2026, 11, 5, 10, 0, tzinfo=UTC),
        leakage_notes=(
            "Labels are derived only from retained M5/M9 source artifacts.",
            "No Qwen3 response or M13 score was inspected while defining labels.",
            "The dataset is not indexed as retrievable operational knowledge.",
        ),
        model_name="qwen3:4b",
        model_digest=MODEL_DIGEST,
        prompt_version="1.4",
        options=InferenceOptions(
            temperature=0,
            seed=42,
            context_tokens=8192,
            max_output_tokens=768,
            think=False,
        ),
        trial_count=2,
        cases=tuple(cases),
    )
    return LLMQualityDatasetEnvelope(
        dataset_sha256=quality_dataset_digest(dataset), dataset=dataset
    )


def main() -> int:
    envelope = build_dataset(Path("results/llm-inputs"))
    print(envelope.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
