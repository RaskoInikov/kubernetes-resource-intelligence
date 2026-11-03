"""Run one opt-in real M12 inference from a retained M9 artifact."""

import argparse
import json
from pathlib import Path

from kri.config import load_settings
from kri.contracts import InferenceOptions, InferenceStatus, RAGMode
from kri.inference import InferenceRunner, InferenceStore, OllamaClient
from kri.llm_input import LLMInputStore


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument(
        "--package-directory", type=Path, default=Path("results/llm-inputs")
    )
    result.add_argument("--package-id", required=True)
    result.add_argument(
        "--output-directory", type=Path, default=Path("results/inference")
    )
    result.add_argument("--run-id", required=True)
    result.add_argument("--rag-mode", choices=tuple(RAGMode), default=RAGMode.ON)
    return result


def main() -> int:
    arguments = parser().parse_args()
    settings = load_settings()
    if settings.ollama_model_digest is None:
        raise SystemExit(
            "KRI_OLLAMA_MODEL_DIGEST is required for reproducible real M12 verification"
        )
    source = LLMInputStore(arguments.package_directory).load_artifact(
        arguments.package_id
    )
    options = InferenceOptions(
        temperature=settings.llm_temperature,
        seed=settings.llm_seed,
        context_tokens=settings.llm_context_tokens,
        max_output_tokens=settings.llm_max_output_tokens,
    )
    client = OllamaClient(
        str(settings.ollama_url), timeout_seconds=settings.ollama_timeout_seconds
    )
    runner = InferenceRunner(
        client,
        str(settings.ollama_url),
        settings.ollama_model,
        expected_model_digest=settings.ollama_model_digest,
    )
    artifact = runner.run(
        source,
        arguments.run_id,
        RAGMode(arguments.rag_mode),
        options,
    )
    store = InferenceStore(arguments.output_directory)
    path = store.save(artifact)
    summary = store.inspect(arguments.run_id)
    print(
        json.dumps(
            {
                "path": str(path),
                "summary": summary.model_dump(mode="json"),
                "failure": (
                    artifact.failure.model_dump(mode="json")
                    if artifact.failure is not None
                    else None
                ),
                "issues": (
                    [
                        item.model_dump(mode="json")
                        for item in artifact.validation.issues
                    ]
                    if artifact.validation is not None
                    else []
                ),
            },
            indent=2,
        )
    )
    return 0 if artifact.status is InferenceStatus.ACCEPTED else 1


if __name__ == "__main__":
    raise SystemExit(main())
