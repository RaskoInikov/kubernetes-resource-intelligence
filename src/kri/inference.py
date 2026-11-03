"""M12 local Qwen3 inference, independent validation, and immutable storage."""

import hashlib
import json
import os
import re
from collections.abc import Callable, Mapping, Sequence
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol, cast
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import uuid4

from pydantic import BaseModel, ValidationError

from kri.contracts import (
    OBSERVATION_ID_PATTERN,
    AcceptedLLMOutput,
    CitationSource,
    GeneratedCitation,
    InferenceArtifactEnvelope,
    InferenceFailure,
    InferenceOptions,
    InferenceRunArtifact,
    InferenceRunSummary,
    InferenceStatus,
    LLMInputArtifact,
    LLMOutputCandidate,
    LLMValidationReport,
    RAGMode,
    ValidationIssue,
)

ADAPTER_VERSION = "1.0"
PROMPT_VERSION = "1.0"
VALIDATOR_VERSION = "1.0"
_NUMBER_IN_PROSE = re.compile(r"(?<![A-Za-z0-9])[-+]?(?:\d+(?:\.\d*)?|\.\d+)")
_GENERATE = "__GENERATE__"


class InferenceError(RuntimeError):
    """M12 inference could not be configured or completed safely."""


class InferenceStoreError(RuntimeError):
    """An immutable M12 run could not be stored or loaded."""


class OllamaError(RuntimeError):
    """Ollama returned an unavailable, malformed, or incomplete result."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def canonical_digest(value: BaseModel) -> str:
    """Return the canonical SHA-256 digest of one validated contract."""

    encoded = json.dumps(
        value.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def text_digest(value: str) -> str:
    """Return the exact UTF-8 digest of prompt or response text."""

    return hashlib.sha256(value.encode()).hexdigest()


@dataclass(frozen=True)
class OllamaGeneration:
    """Validated subset of one non-streaming Ollama chat response."""

    content: str
    prompt_eval_count: int | None
    eval_count: int | None
    total_duration_ns: int | None


class LocalModelClient(Protocol):
    """Injectable boundary used by offline tests and the local Ollama client."""

    def model_digest(self, model_name: str) -> str: ...

    def generate(
        self,
        model_name: str,
        messages: Sequence[Mapping[str, str]],
        options: InferenceOptions,
    ) -> OllamaGeneration: ...


def _request_json(
    method: str, url: str, payload: Mapping[str, Any] | None, timeout: float
) -> dict[str, Any]:
    body = None if payload is None else json.dumps(payload).encode()
    request = Request(
        url,
        data=body,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read().decode()
    except HTTPError as error:
        raise OllamaError("ollama_http_error", f"Ollama HTTP {error.code}") from error
    except (URLError, TimeoutError, OSError) as error:
        raise OllamaError("ollama_unavailable", str(error)) from error
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as error:
        raise OllamaError(
            "ollama_invalid_json", "Ollama returned invalid JSON"
        ) from error
    if not isinstance(parsed, dict):
        raise OllamaError(
            "ollama_invalid_response", "Ollama response must be an object"
        )
    return cast(dict[str, Any], parsed)


class OllamaClient:
    """Small synchronous client for a configured local Ollama service."""

    def __init__(
        self,
        base_url: str,
        timeout_seconds: float = 180,
        request_json: Callable[
            [str, str, Mapping[str, Any] | None, float], dict[str, Any]
        ] = _request_json,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.request_json = request_json

    def model_digest(self, model_name: str) -> str:
        response = self.request_json(
            "GET", f"{self.base_url}/api/tags", None, self.timeout_seconds
        )
        models = response.get("models")
        if not isinstance(models, list):
            raise OllamaError("ollama_invalid_response", "model list is missing")
        for item in models:
            if isinstance(item, dict) and item.get("name") == model_name:
                digest = item.get("digest")
                if isinstance(digest, str) and re.fullmatch(r"[0-9a-f]{64}", digest):
                    return digest
                raise OllamaError(
                    "ollama_invalid_response", "configured model digest is invalid"
                )
        raise OllamaError(
            "ollama_model_missing", f"configured model is not installed: {model_name}"
        )

    def generate(
        self,
        model_name: str,
        messages: Sequence[Mapping[str, str]],
        options: InferenceOptions,
    ) -> OllamaGeneration:
        response = self.request_json(
            "POST",
            f"{self.base_url}/api/chat",
            {
                "model": model_name,
                "messages": list(messages),
                "stream": False,
                "think": options.think,
                "format": "json",
                "options": {
                    "temperature": options.temperature,
                    "seed": options.seed,
                    "num_ctx": options.context_tokens,
                    "num_predict": options.max_output_tokens,
                },
            },
            self.timeout_seconds,
        )
        if isinstance(response.get("error"), str):
            raise OllamaError("ollama_generation_error", response["error"])
        message = response.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str) or not content.strip():
            raise OllamaError("ollama_invalid_response", "generated content is missing")
        if response.get("done") is not True:
            raise OllamaError("ollama_interrupted", "generation did not complete")
        done_reason = response.get("done_reason")
        if done_reason not in (None, "stop"):
            raise OllamaError(
                "ollama_incomplete", f"generation ended with reason: {done_reason}"
            )
        return OllamaGeneration(
            content=content,
            prompt_eval_count=_optional_nonnegative_int(
                response.get("prompt_eval_count"), "prompt_eval_count"
            ),
            eval_count=_optional_nonnegative_int(
                response.get("eval_count"), "eval_count"
            ),
            total_duration_ns=_optional_nonnegative_int(
                response.get("total_duration"), "total_duration"
            ),
        )


def _optional_nonnegative_int(value: object, name: str) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise OllamaError("ollama_invalid_response", f"{name} must be non-negative")
    return value


def render_messages(
    artifact: LLMInputArtifact, run_id: str, rag_mode: RAGMode
) -> tuple[dict[str, str], ...]:
    """Render deterministic, source-bounded Qwen3 messages for one run."""

    package = artifact.package
    uncertainties = [
        {"uncertainty_id": f"uncertainty-{index}", "source_text": text}
        for index, text in enumerate(package.risks_and_uncertainties, start=1)
    ]
    statistics = {item.statistic_id: item for item in package.statistics}
    output_template = {
        "schema_version": "1.0",
        "run_id": run_id,
        "package_id": package.package_id,
        "package_sha256": artifact.package_sha256,
        "rag_mode": rag_mode.value,
        "summary": (
            _GENERATE
            if package.conditions or package.recommendations
            else "No deterministic resource findings or recommendations were supplied; "
            "review every listed uncertainty."
        ),
        "problems": [
            {
                "condition_id": condition.condition_id,
                "explanation": _GENERATE,
                "numerical_claims": [
                    {
                        "claim_id": f"claim-{condition_index}-{statistic_index}",
                        "statistic_id": statistic_id,
                        "value": statistics[statistic_id].value,
                        "unit": statistics[statistic_id].unit,
                    }
                    for statistic_index, statistic_id in enumerate(
                        condition.statistic_ids, start=1
                    )
                ],
                "citations": [
                    {"source": "analysis_evidence", "source_id": evidence_id}
                    for evidence_id in condition.evidence_ids
                ],
            }
            for condition_index, condition in enumerate(package.conditions, start=1)
        ],
        "recommendations": [
            {
                "recommendation_id": recommendation.recommendation_id,
                "explanation": _GENERATE,
                "resource": recommendation.resource,
                "current_value": recommendation.current_value,
                "recommended_value": recommendation.recommended_value,
                "citations": [
                    {"source": "analysis_evidence", "source_id": evidence_id}
                    for evidence_id in recommendation.evidence_ids
                ],
            }
            for recommendation in package.recommendations
        ],
        "uncertainties": [
            {
                **uncertainty,
                "explanation": (
                    _GENERATE
                    if package.conditions or package.recommendations
                    else "This source uncertainty limits interpretation."
                ),
            }
            for uncertainty in uncertainties
        ],
        "approval_required": True,
    }
    source = {
        "run_id": run_id,
        "package_id": package.package_id,
        "package_sha256": artifact.package_sha256,
        "rag_mode": rag_mode.value,
        "workload_identity": package.identity.model_dump(mode="json"),
        "sufficiency": package.sufficiency.value,
        "statistics": [item.model_dump(mode="json") for item in package.statistics],
        "conditions": [item.model_dump(mode="json") for item in package.conditions],
        "recommendations": [
            item.model_dump(mode="json") for item in package.recommendations
        ],
        "analysis_evidence": [
            item.model_dump(mode="json") for item in package.analysis_evidence
        ],
        "uncertainties": uncertainties,
        "knowledge_excerpts": (
            [item.model_dump(mode="json") for item in package.evidence_excerpts]
            if rag_mode is RAGMode.ON
            else []
        ),
        "instructions": package.instructions,
    }
    system = (
        "You are an evidence-grounded Kubernetes resource explanation renderer. "
        "Return only JSON matching the supplied schema. Explain every supplied "
        "condition and recommendation without adding diagnoses or resource values. "
        "Put every number in numerical_claims, copy its exact statistic value/unit, "
        "and keep prose free of digits. Copy every non-empty field from "
        "output_template exactly except replace every __GENERATE__ sentinel with "
        "clear prose. Cite "
        "exact analysis evidence IDs; cite only "
        "supplied knowledge chunks when RAG is on. Copy every uncertainty source_text "
        "exactly. Never claim that a recommendation was applied or validated."
    )
    user = (
        "EVIDENCE INPUT — DO NOT RETURN THIS OBJECT:\n"
        + json.dumps(source, sort_keys=True, separators=(",", ":"))
        + "\nREQUIRED OUTPUT TEMPLATE — RETURN ONLY THIS OBJECT AFTER REPLACING "
        "EVERY __GENERATE__ SENTINEL:\n"
        + json.dumps(output_template, sort_keys=True, separators=(",", ":"))
    )
    return ({"role": "system", "content": system}, {"role": "user", "content": user})


def messages_digest(messages: Sequence[Mapping[str, str]]) -> str:
    """Digest the exact ordered role/content messages sent to Ollama."""

    return hashlib.sha256(
        json.dumps(list(messages), sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


class LLMOutputValidator:
    """Validate generated structure against M9 without repairing any output."""

    def __init__(
        self, clock: Callable[[], datetime] = lambda: datetime.now(UTC)
    ) -> None:
        self.clock = clock

    def validate(
        self,
        candidate: LLMOutputCandidate,
        artifact: LLMInputArtifact,
        run_id: str,
        rag_mode: RAGMode,
    ) -> LLMValidationReport:
        issues: list[ValidationIssue] = []
        package = artifact.package

        def issue(code: str, location: str, message: str) -> None:
            issues.append(
                ValidationIssue(code=code, location=location, message=message)
            )

        if candidate.run_id != run_id:
            issue("source_mismatch", "run_id", "candidate run ID does not match")
        if (
            candidate.package_id != package.package_id
            or candidate.package_sha256 != artifact.package_sha256
        ):
            issue(
                "source_mismatch",
                "package",
                "candidate package identity does not match",
            )
        if candidate.rag_mode is not rag_mode:
            issue("source_mismatch", "rag_mode", "candidate RAG mode does not match")
        self._check_prose(candidate.summary, "summary", issue)

        conditions = {item.condition_id: item for item in package.conditions}
        problem_ids = [item.condition_id for item in candidate.problems]
        if problem_ids != sorted(conditions):
            issue(
                "condition_coverage",
                "problems",
                "candidate must explain every condition exactly once in ID order",
            )
        statistics = {item.statistic_id: item for item in package.statistics}
        evidence_ids = {item.evidence_id for item in package.analysis_evidence}
        excerpt_ids = {item.chunk_id for item in package.evidence_excerpts}
        claim_ids: list[str] = []
        for index, problem in enumerate(candidate.problems):
            location = f"problems[{index}]"
            self._check_prose(problem.explanation, f"{location}.explanation", issue)
            condition = conditions.get(problem.condition_id)
            if condition is None:
                issue("unknown_condition", location, "condition ID is not in M9 input")
                continue
            claim_ids.extend(claim.claim_id for claim in problem.numerical_claims)
            if [claim.statistic_id for claim in problem.numerical_claims] != list(
                condition.statistic_ids
            ):
                issue(
                    "statistic_coverage",
                    f"{location}.numerical_claims",
                    "claims must match the condition statistic IDs in source order",
                )
            for claim_index, claim in enumerate(problem.numerical_claims):
                statistic = statistics.get(claim.statistic_id)
                if statistic is None:
                    issue(
                        "unknown_statistic",
                        f"{location}.numerical_claims[{claim_index}]",
                        "statistic ID is not in M9 input",
                    )
                elif claim.value != statistic.value or claim.unit != statistic.unit:
                    issue(
                        "numerical_mismatch",
                        f"{location}.numerical_claims[{claim_index}]",
                        "claim value or unit differs from its M5 statistic",
                    )
            self._check_citations(
                problem.citations,
                set(condition.evidence_ids),
                evidence_ids,
                excerpt_ids,
                rag_mode,
                f"{location}.citations",
                issue,
            )

        recommendations = {
            item.recommendation_id: item for item in package.recommendations
        }
        recommendation_ids = [
            item.recommendation_id for item in candidate.recommendations
        ]
        if recommendation_ids != sorted(recommendations):
            issue(
                "recommendation_coverage",
                "recommendations",
                "candidate must explain every recommendation exactly once in ID order",
            )
        for index, generated in enumerate(candidate.recommendations):
            location = f"recommendations[{index}]"
            self._check_prose(generated.explanation, f"{location}.explanation", issue)
            recommendation = recommendations.get(generated.recommendation_id)
            if recommendation is None:
                issue(
                    "unknown_recommendation",
                    location,
                    "recommendation ID is not in M9 input",
                )
                continue
            if (
                generated.resource != recommendation.resource
                or generated.current_value != recommendation.current_value
                or generated.recommended_value != recommendation.recommended_value
            ):
                issue(
                    "recommendation_mismatch",
                    location,
                    "resource or quantity differs from the M5 recommendation",
                )
            self._check_citations(
                generated.citations,
                set(recommendation.evidence_ids),
                evidence_ids,
                excerpt_ids,
                rag_mode,
                f"{location}.citations",
                issue,
            )

        if len(claim_ids) != len(set(claim_ids)):
            issue("duplicate_claim", "problems", "numerical claim IDs must be unique")
        expected_uncertainties = [
            (f"uncertainty-{index}", text)
            for index, text in enumerate(package.risks_and_uncertainties, start=1)
        ]
        actual_uncertainties = [
            (item.uncertainty_id, item.source_text) for item in candidate.uncertainties
        ]
        if actual_uncertainties != expected_uncertainties:
            issue(
                "uncertainty_coverage",
                "uncertainties",
                "candidate must preserve every uncertainty ID and source text in order",
            )
        for index, uncertainty in enumerate(candidate.uncertainties):
            self._check_prose(
                uncertainty.explanation,
                f"uncertainties[{index}].explanation",
                issue,
            )

        validated_at = self.clock()
        if validated_at.tzinfo is None:
            raise InferenceError("validator clock returned a naive timestamp")
        ordered = tuple(sorted(issues, key=lambda item: (item.location, item.code)))
        return LLMValidationReport(
            run_id=run_id,
            package_id=package.package_id,
            package_sha256=artifact.package_sha256,
            candidate_sha256=canonical_digest(candidate),
            validated_at=validated_at,
            passed=not ordered,
            issues=ordered,
        )

    @staticmethod
    def _check_prose(
        value: str,
        location: str,
        issue: Callable[[str, str, str], None],
    ) -> None:
        if value == _GENERATE:
            issue(
                "unfilled_placeholder",
                location,
                "generated prose placeholder was not replaced",
            )
        if _NUMBER_IN_PROSE.search(value):
            issue(
                "undeclared_number",
                location,
                "generated prose contains a number outside numerical_claims",
            )

    @staticmethod
    def _check_citations(
        citations: tuple[GeneratedCitation, ...],
        required_analysis: set[str],
        all_analysis: set[str],
        excerpts: set[str],
        rag_mode: RAGMode,
        location: str,
        issue: Callable[[str, str, str], None],
    ) -> None:
        keys = [(item.source, item.source_id) for item in citations]
        if len(keys) != len(set(keys)):
            issue("duplicate_citation", location, "citations must be unique")
        cited_analysis = {
            item.source_id
            for item in citations
            if item.source is CitationSource.ANALYSIS_EVIDENCE
        }
        if cited_analysis != required_analysis:
            issue(
                "analysis_citation_coverage",
                location,
                "analysis citations must exactly cover source evidence IDs",
            )
        for citation in citations:
            if (
                citation.source is CitationSource.ANALYSIS_EVIDENCE
                and citation.source_id not in all_analysis
            ):
                issue("unknown_citation", location, "analysis citation is not in M9")
            if citation.source is CitationSource.KNOWLEDGE_CHUNK:
                if rag_mode is RAGMode.OFF:
                    issue(
                        "rag_off_citation",
                        location,
                        "knowledge citations are forbidden when RAG is off",
                    )
                elif citation.source_id not in excerpts:
                    issue(
                        "unknown_citation", location, "knowledge citation is not in M9"
                    )


class InferenceRunner:
    """Orchestrate one source-bound local generation and independent validation."""

    def __init__(
        self,
        client: LocalModelClient,
        ollama_url: str,
        model_name: str,
        expected_model_digest: str | None = None,
        validator: LLMOutputValidator | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        if "qwen3" not in model_name.lower():
            raise InferenceError("M12 requires a configured Qwen3 model")
        if (
            expected_model_digest is not None
            and re.fullmatch(r"[0-9a-f]{64}", expected_model_digest) is None
        ):
            raise InferenceError(
                "expected model digest must be 64 lowercase hex characters"
            )
        self.client = client
        self.ollama_url = ollama_url
        self.model_name = model_name
        self.expected_model_digest = expected_model_digest
        self.validator = validator or LLMOutputValidator(clock=clock)
        self.clock = clock

    def run(
        self,
        artifact: LLMInputArtifact,
        run_id: str,
        rag_mode: RAGMode,
        options: InferenceOptions | None = None,
    ) -> InferenceRunArtifact:
        if OBSERVATION_ID_PATTERN.fullmatch(run_id) is None:
            raise InferenceError("invalid inference run ID")
        try:
            source = LLMInputArtifact.model_validate(artifact.model_dump(mode="json"))
        except ValidationError as error:
            raise InferenceError(f"invalid M9 input artifact: {error}") from error
        chosen = options or InferenceOptions()
        requested_at = self._now("inference clock returned a naive timestamp")
        messages = render_messages(source, run_id, rag_mode)
        prompt_sha256 = messages_digest(messages)
        if rag_mode is RAGMode.ON and not source.package.evidence_excerpts:
            return self._failed(
                source,
                run_id,
                rag_mode,
                chosen,
                requested_at,
                prompt_sha256,
                "rag_evidence_missing",
                "RAG-on inference requires at least one M9 evidence excerpt",
            )
        model_digest: str | None = None
        try:
            model_digest = self.client.model_digest(self.model_name)
            if (
                self.expected_model_digest is not None
                and model_digest != self.expected_model_digest
            ):
                raise OllamaError(
                    "ollama_model_mismatch",
                    "installed model digest does not match configured digest",
                )
            generated = self.client.generate(self.model_name, messages, chosen)
        except OllamaError as error:
            return self._failed(
                source,
                run_id,
                rag_mode,
                chosen,
                requested_at,
                prompt_sha256,
                error.code,
                str(error),
                model_digest=model_digest,
            )

        raw = generated.content
        try:
            candidate = LLMOutputCandidate.model_validate_json(raw)
        except ValidationError as error:
            return self._failed(
                source,
                run_id,
                rag_mode,
                chosen,
                requested_at,
                prompt_sha256,
                "malformed_output",
                f"generated output does not match the M12 schema: {error}",
                model_digest=model_digest,
                raw_response=raw,
                generation=generated,
            )
        validation = self.validator.validate(candidate, source, run_id, rag_mode)
        accepted = (
            AcceptedLLMOutput(
                candidate_sha256=validation.candidate_sha256,
                validation_sha256=canonical_digest(validation),
            )
            if validation.passed
            else None
        )
        return InferenceRunArtifact(
            run_id=run_id,
            status=(InferenceStatus.ACCEPTED if accepted else InferenceStatus.REJECTED),
            requested_at=requested_at,
            started_at=requested_at,
            ended_at=self._now("inference clock returned a naive timestamp"),
            package_id=source.package.package_id,
            package_sha256=source.package_sha256,
            rag_mode=rag_mode,
            ollama_url=self.ollama_url,
            model_name=self.model_name,
            model_digest=model_digest,
            options=chosen,
            prompt_sha256=prompt_sha256,
            raw_response=raw,
            raw_response_sha256=text_digest(raw),
            prompt_eval_count=generated.prompt_eval_count,
            eval_count=generated.eval_count,
            total_duration_ns=generated.total_duration_ns,
            candidate=candidate,
            validation=validation,
            accepted_output=accepted,
        )

    def _failed(
        self,
        source: LLMInputArtifact,
        run_id: str,
        rag_mode: RAGMode,
        options: InferenceOptions,
        requested_at: datetime,
        prompt_sha256: str,
        code: str,
        message: str,
        *,
        model_digest: str | None = None,
        raw_response: str | None = None,
        generation: OllamaGeneration | None = None,
    ) -> InferenceRunArtifact:
        return InferenceRunArtifact(
            run_id=run_id,
            status=InferenceStatus.FAILED,
            requested_at=requested_at,
            started_at=requested_at,
            ended_at=self._now("inference clock returned a naive timestamp"),
            package_id=source.package.package_id,
            package_sha256=source.package_sha256,
            rag_mode=rag_mode,
            ollama_url=self.ollama_url,
            model_name=self.model_name,
            model_digest=model_digest,
            options=options,
            prompt_sha256=prompt_sha256,
            raw_response=raw_response,
            raw_response_sha256=(
                text_digest(raw_response) if raw_response is not None else None
            ),
            prompt_eval_count=(
                generation.prompt_eval_count if generation is not None else None
            ),
            eval_count=generation.eval_count if generation is not None else None,
            total_duration_ns=(
                generation.total_duration_ns if generation is not None else None
            ),
            failure=InferenceFailure(code=code, message=message),
        )

    def _now(self, message: str) -> datetime:
        value = self.clock()
        if value.tzinfo is None:
            raise InferenceError(message)
        return value.astimezone(UTC)


class InferenceStore:
    """Immutable atomic persistence for accepted, rejected, and failed M12 runs."""

    def __init__(self, directory: Path) -> None:
        self.directory = directory

    def _path(self, run_id: str) -> Path:
        if OBSERVATION_ID_PATTERN.fullmatch(run_id) is None:
            raise InferenceStoreError("invalid inference run ID")
        return self.directory / f"{run_id}.json"

    def save(self, artifact: InferenceRunArtifact) -> Path:
        try:
            validated = InferenceRunArtifact.model_validate(
                artifact.model_dump(mode="json")
            )
        except ValidationError as error:
            raise InferenceStoreError(f"invalid inference artifact: {error}") from error
        digest = canonical_digest(validated)
        envelope = InferenceArtifactEnvelope(artifact_sha256=digest, artifact=validated)
        path = self._path(validated.run_id)
        temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            temporary.write_text(
                envelope.model_dump_json(indent=2) + "\n", encoding="utf-8"
            )
            os.link(temporary, path)
            temporary.unlink()
        except FileExistsError as error:
            self._discard(temporary)
            raise InferenceStoreError(
                f"inference run already exists: {validated.run_id}"
            ) from error
        except OSError as error:
            self._discard(temporary)
            raise InferenceStoreError(str(error)) from error
        return path

    @staticmethod
    def _discard(path: Path) -> None:
        with suppress(OSError):
            path.unlink(missing_ok=True)

    def load_envelope(self, run_id: str) -> InferenceArtifactEnvelope:
        try:
            return InferenceArtifactEnvelope.model_validate_json(
                self._path(run_id).read_text(encoding="utf-8")
            )
        except FileNotFoundError as error:
            raise InferenceStoreError(
                f"inference run does not exist: {run_id}"
            ) from error
        except (OSError, ValidationError) as error:
            raise InferenceStoreError(f"invalid inference artifact: {error}") from error

    def load(self, run_id: str) -> InferenceRunArtifact:
        return self.load_envelope(run_id).artifact

    def inspect(self, run_id: str) -> InferenceRunSummary:
        envelope = self.load_envelope(run_id)
        artifact = envelope.artifact
        return InferenceRunSummary(
            run_id=artifact.run_id,
            status=artifact.status,
            package_id=artifact.package_id,
            rag_mode=artifact.rag_mode,
            model_name=artifact.model_name,
            model_digest=artifact.model_digest,
            requested_at=artifact.requested_at,
            ended_at=artifact.ended_at,
            issue_count=(len(artifact.validation.issues) if artifact.validation else 0),
            artifact_sha256=envelope.artifact_sha256,
        )
