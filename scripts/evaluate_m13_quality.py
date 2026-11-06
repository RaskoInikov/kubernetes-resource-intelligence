"""Run or replay the fixed M13 paired RAG-on/off Qwen3 evaluation."""

import argparse
import json
import os
import platform
from pathlib import Path

from kri.config import load_settings
from kri.contracts import RAGMode
from kri.inference import InferenceRunner, InferenceStore, OllamaClient
from kri.llm_input import LLMInputStore
from kri.quality_evaluation import (
    QualityEvaluationStore,
    QualityEvaluator,
    inference_run_id,
    load_quality_dataset,
)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument(
        "--dataset", type=Path, default=Path("evaluation/m13-quality-v1.json")
    )
    result.add_argument(
        "--package-directory", type=Path, default=Path("results/llm-inputs")
    )
    result.add_argument(
        "--inference-directory", type=Path, default=Path("results/m13-inference")
    )
    result.add_argument(
        "--output-directory", type=Path, default=Path("results/m13-evaluation")
    )
    result.add_argument("--evaluation-id", required=True)
    result.add_argument(
        "--run-real",
        action="store_true",
        help="Run every planned local Ollama trial before evaluating it.",
    )
    return result


def main() -> int:
    arguments = parser().parse_args()
    envelope = load_quality_dataset(arguments.dataset)
    dataset = envelope.dataset
    package_store = LLMInputStore(arguments.package_directory)
    packages = {
        case.package_id: package_store.load_artifact(case.package_id)
        for case in dataset.cases
    }
    inference_store = InferenceStore(arguments.inference_directory)
    if arguments.run_real:
        settings = load_settings()
        if settings.ollama_model != dataset.model_name:
            raise SystemExit("configured Ollama model does not match the M13 dataset")
        runner = InferenceRunner(
            OllamaClient(
                str(settings.ollama_url),
                timeout_seconds=settings.ollama_timeout_seconds,
            ),
            str(settings.ollama_url),
            dataset.model_name,
            expected_model_digest=dataset.model_digest,
        )
        for case in dataset.cases:
            source = packages[case.package_id]
            for repetition in range(1, dataset.trial_count + 1):
                # Alternate order so warm-cache and thermal effects are not
                # assigned systematically to either RAG configuration.
                modes = (
                    (RAGMode.OFF, RAGMode.ON)
                    if repetition % 2
                    else (RAGMode.ON, RAGMode.OFF)
                )
                for mode in modes:
                    run_id = inference_run_id(
                        arguments.evaluation_id, case.case_id, repetition, mode
                    )
                    artifact = runner.run(source, run_id, mode, dataset.options)
                    path = inference_store.save(artifact)
                    print(
                        json.dumps(
                            {
                                "saved": str(path),
                                "status": artifact.status,
                                "failure": (
                                    artifact.failure.code if artifact.failure else None
                                ),
                                "duration_seconds": (
                                    artifact.total_duration_ns / 1_000_000_000
                                    if artifact.total_duration_ns is not None
                                    else None
                                ),
                            }
                        ),
                        flush=True,
                    )
    runs = {
        inference_run_id(arguments.evaluation_id, case.case_id, repetition, mode): (
            inference_store.load(
                inference_run_id(
                    arguments.evaluation_id, case.case_id, repetition, mode
                )
            )
        )
        for case in dataset.cases
        for repetition in range(1, dataset.trial_count + 1)
        for mode in (RAGMode.OFF, RAGMode.ON)
    }
    report = QualityEvaluator().evaluate(
        arguments.evaluation_id,
        envelope,
        packages,
        runs,
        evidence_class="fresh-real" if arguments.run_real else "offline-recorded",
        environment={
            "hostname": platform.node(),
            "platform": platform.platform(),
            "python": platform.python_version(),
            "cpu_count": str(os.cpu_count()),
        },
    )
    path = QualityEvaluationStore(arguments.output_directory).save(report)
    print(
        json.dumps(
            {
                "saved": str(path),
                "dataset_sha256": report.dataset_sha256,
                "trial_count": len(report.trials),
                "failure_count": sum(
                    trial.failure_code is not None for trial in report.trials
                ),
                "comparisons": [
                    item.model_dump(mode="json") for item in report.comparisons
                ],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
