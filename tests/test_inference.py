"""Offline M12 local inference, validation, transport, and persistence tests."""

import json
from collections.abc import Mapping, Sequence
from datetime import datetime
from email.message import Message
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError

import pytest
from pydantic import ValidationError

import kri.inference as inference_module
from kri.contracts import (
    CitationSource,
    GeneratedCitation,
    GeneratedUncertainty,
    InferenceArtifactEnvelope,
    InferenceFailure,
    InferenceOptions,
    InferenceRunArtifact,
    InferenceStatus,
    LLMInputArtifact,
    LLMInputPackage,
    LLMOutputCandidate,
    LLMRetrievalStatus,
    LLMValidationReport,
    NumericalClaim,
    ProblemExplanation,
    RAGMode,
    RecommendationExplanation,
)
from kri.inference import (
    InferenceError,
    InferenceRunner,
    InferenceStore,
    InferenceStoreError,
    LLMOutputValidator,
    OllamaClient,
    OllamaError,
    OllamaGeneration,
    _request_json,
    canonical_digest,
    compact_response_schema,
    messages_digest,
    render_messages,
    text_digest,
)
from kri.llm_input import LLMInputBuilder, LLMInputStore, package_digest
from tests.test_llm_input import NOW, analysis, build, evidence

MODEL_DIGEST = "1" * 64


def source_artifact(*, with_hits: bool = True) -> LLMInputArtifact:
    package = (
        build()
        if with_hits
        else LLMInputBuilder(clock=lambda: NOW).build(
            analysis(), evidence(hits=()), package_id="llm-without-hits"
        )
    )
    return LLMInputArtifact(package_sha256=package_digest(package), package=package)


def no_findings_artifact() -> LLMInputArtifact:
    payload = build().model_dump(mode="json")
    payload.update(
        statistics=[],
        conditions=[],
        recommendations=[],
        analysis_evidence=[],
        retrieval_status=LLMRetrievalStatus.NO_FINDINGS,
        retrieval_queries=[],
        retrieval_hits=[],
        evidence_excerpts=[],
    )
    package = LLMInputPackage.model_validate(payload)
    return LLMInputArtifact(package_sha256=package_digest(package), package=package)


def valid_candidate(
    artifact: LLMInputArtifact,
    *,
    run_id: str = "run-m12",
    rag_mode: RAGMode = RAGMode.ON,
) -> LLMOutputCandidate:
    knowledge = (
        (
            GeneratedCitation(
                source=CitationSource.KNOWLEDGE_CHUNK,
                source_id=artifact.package.evidence_excerpts[0].chunk_id,
            ),
        )
        if rag_mode is RAGMode.ON
        else ()
    )
    return LLMOutputCandidate(
        run_id=run_id,
        package_id=artifact.package.package_id,
        package_sha256=artifact.package_sha256,
        rag_mode=rag_mode,
        summary="Measured throttling supports a bounded CPU adjustment.",
        problems=(
            ProblemExplanation(
                condition_id="cpu-throttling-app-a",
                explanation="The measured throttled-period ratio crosses policy.",
                numerical_claims=(
                    NumericalClaim(
                        claim_id="throttle-ratio",
                        statistic_id="s-throttle",
                        value=0.3333333333333333,
                        unit="ratio",
                    ),
                ),
                citations=(
                    GeneratedCitation(
                        source=CitationSource.ANALYSIS_EVIDENCE,
                        source_id="e-series",
                    ),
                    *knowledge,
                ),
            ),
        ),
        recommendations=(
            RecommendationExplanation(
                recommendation_id="increase-cpu-limit",
                explanation="Increase the CPU limit within deterministic bounds.",
                resource="cpu_limit",
                current_value="100m",
                recommended_value="140m",
                citations=(
                    GeneratedCitation(
                        source=CitationSource.ANALYSIS_EVIDENCE,
                        source_id="e-config",
                    ),
                    GeneratedCitation(
                        source=CitationSource.ANALYSIS_EVIDENCE,
                        source_id="e-series",
                    ),
                    *knowledge,
                ),
            ),
        ),
        uncertainties=tuple(
            GeneratedUncertainty(
                uncertainty_id=f"uncertainty-{index}",
                source_text=text,
                explanation="This limitation remains unresolved.",
            )
            for index, text in enumerate(
                artifact.package.risks_and_uncertainties, start=1
            )
        ),
        approval_required=True,
    )


def compact_response(candidate: LLMOutputCandidate) -> dict[str, Any]:
    return {
        "run_id": candidate.run_id,
        "package_id": candidate.package_id,
        "package_sha256": candidate.package_sha256,
        "rag_mode": candidate.rag_mode,
        "summary": candidate.summary,
        "problem_explanations": [item.explanation for item in candidate.problems],
        "problem_knowledge_citation_ids": [
            [
                citation.source_id
                for citation in item.citations
                if citation.source is CitationSource.KNOWLEDGE_CHUNK
            ]
            for item in candidate.problems
        ],
        "recommendation_explanations": [
            item.explanation for item in candidate.recommendations
        ],
        "recommendation_knowledge_citation_ids": [
            [
                citation.source_id
                for citation in item.citations
                if citation.source is CitationSource.KNOWLEDGE_CHUNK
            ]
            for item in candidate.recommendations
        ],
        "uncertainty_explanations": [
            item.explanation for item in candidate.uncertainties
        ],
        "approval_required": candidate.approval_required,
    }


class FakeClient:
    def __init__(
        self,
        content: str,
        *,
        digest: str = MODEL_DIGEST,
        error: OllamaError | None = None,
    ) -> None:
        self.content = content
        self.digest = digest
        self.error = error
        self.messages: Sequence[Mapping[str, str]] = ()

    def model_digest(self, model_name: str) -> str:
        if self.error:
            raise self.error
        assert model_name == "qwen3:test"
        return self.digest

    def generate(
        self,
        model_name: str,
        messages: Sequence[Mapping[str, str]],
        options: InferenceOptions,
        response_schema: Mapping[str, Any],
    ) -> OllamaGeneration:
        assert model_name == "qwen3:test"
        assert options.seed == 42
        assert response_schema["title"] == "_CompactLLMResponse"
        self.messages = messages
        return OllamaGeneration(self.content, 100, 50, 1234)


def runner(client: FakeClient, **kwargs: Any) -> InferenceRunner:
    return InferenceRunner(
        client,
        "http://ollama.test:11434",
        "qwen3:test",
        expected_model_digest=kwargs.pop("expected_model_digest", MODEL_DIGEST),
        clock=kwargs.pop("clock", lambda: NOW),
        **kwargs,
    )


def test_accepted_rag_on_and_off_runs_are_reproducible_and_persisted(
    tmp_path: Path,
) -> None:
    artifact = source_artifact()
    candidate = valid_candidate(artifact)
    client = FakeClient(candidate.model_dump_json())

    result = runner(client).run(artifact, "run-m12", RAGMode.ON)

    assert result.status is InferenceStatus.ACCEPTED
    assert result.model_digest == MODEL_DIGEST
    assert result.validation is not None and result.validation.passed
    assert result.accepted_output is not None
    assert result.raw_response_sha256 == text_digest(candidate.model_dump_json())
    assert result.prompt_eval_count == 100
    assert result.eval_count == 50
    assert result.total_duration_ns == 1234
    assert result.prompt_sha256 == messages_digest(client.messages)
    assert "cpu-runbook-section-1" in client.messages[1]["content"]

    off_candidate = valid_candidate(
        artifact, run_id="run-m12-off", rag_mode=RAGMode.OFF
    )
    off_client = FakeClient(off_candidate.model_dump_json())
    off = runner(off_client).run(artifact, "run-m12-off", RAGMode.OFF)
    assert off.status is InferenceStatus.ACCEPTED
    assert '"knowledge_excerpts":[]' in off_client.messages[1]["content"]
    assert off.prompt_sha256 != result.prompt_sha256

    store = InferenceStore(tmp_path)
    path = store.save(result)
    assert path.name == "run-m12.json"
    assert store.load("run-m12") == result
    envelope = store.load_envelope("run-m12")
    assert envelope.artifact_sha256 == canonical_digest(result)
    summary = store.inspect("run-m12")
    assert summary.status is InferenceStatus.ACCEPTED
    assert summary.issue_count == 0
    with pytest.raises(InferenceStoreError, match="already exists"):
        store.save(result)


def test_compact_response_is_deterministically_expanded_and_rejected_safely() -> None:
    artifact = source_artifact()
    candidate = valid_candidate(artifact)
    compact = compact_response(candidate)
    raw = json.dumps(compact)

    result = runner(FakeClient(raw)).run(artifact, "run-m12", RAGMode.ON)

    assert result.status is InferenceStatus.ACCEPTED
    assert result.raw_response == raw
    assert result.candidate is not None
    assert result.candidate.summary == candidate.summary
    assert result.candidate.problems[0].numerical_claims[0].statistic_id == "s-throttle"
    assert result.candidate.recommendations[0].recommended_value == "140m"

    identity_changes: tuple[tuple[str, Any], ...] = (
        ("run_id", "other-run"),
        ("package_id", "other-package"),
        ("package_sha256", "2" * 64),
        ("rag_mode", "off"),
        ("approval_required", False),
        ("problem_explanations", []),
        ("problem_knowledge_citation_ids", []),
        ("recommendation_explanations", []),
        ("recommendation_knowledge_citation_ids", []),
        ("uncertainty_explanations", []),
    )
    for index, (field, value) in enumerate(identity_changes, start=1):
        expected_run_id = f"run-bad-{index}"
        changed = {**compact, "run_id": expected_run_id, field: value}
        failed = runner(FakeClient(json.dumps(changed))).run(
            artifact, expected_run_id, RAGMode.ON
        )
        assert failed.failure is not None
        assert failed.failure.code == "malformed_output"

    bad_citations = (
        ["cpu-runbook-section-1", "cpu-runbook-section-1"],
        ["unknown-chunk"],
    )
    for index, values in enumerate(bad_citations, start=1):
        changed = json.loads(json.dumps(compact))
        changed["run_id"] = f"run-citation-{index}"
        changed["problem_knowledge_citation_ids"][0] = values
        failed = runner(FakeClient(json.dumps(changed))).run(
            artifact, f"run-citation-{index}", RAGMode.ON
        )
        assert failed.failure is not None
        assert failed.failure.code == "malformed_output"

    off_candidate = valid_candidate(artifact, run_id="run-off", rag_mode=RAGMode.OFF)
    off_compact = compact_response(off_candidate)
    off_compact["problem_knowledge_citation_ids"][0] = ["cpu-runbook-section-1"]
    off_failed = runner(FakeClient(json.dumps(off_compact))).run(
        artifact, "run-off", RAGMode.OFF
    )
    assert off_failed.failure is not None
    assert off_failed.failure.code == "malformed_output"


def test_validator_reports_all_unsupported_content_without_repair() -> None:
    artifact = source_artifact()
    duplicate = GeneratedCitation(
        source=CitationSource.ANALYSIS_EVIDENCE, source_id="not-source"
    )
    candidate = LLMOutputCandidate(
        run_id="wrong-run",
        package_id="wrong-package",
        package_sha256="2" * 64,
        rag_mode=RAGMode.OFF,
        summary="Observed 99 unsupported events.",
        problems=(
            ProblemExplanation(
                condition_id="cpu-throttling-app-a",
                explanation="Ratio 9 is unsupported.",
                numerical_claims=(
                    NumericalClaim(
                        claim_id="same-claim",
                        statistic_id="s-throttle",
                        value=9,
                        unit="bytes",
                    ),
                    NumericalClaim(
                        claim_id="same-claim",
                        statistic_id="unknown-statistic",
                        value=1,
                        unit="ratio",
                    ),
                ),
                citations=(
                    duplicate,
                    duplicate,
                    GeneratedCitation(
                        source=CitationSource.KNOWLEDGE_CHUNK,
                        source_id="unknown-chunk",
                    ),
                ),
            ),
            ProblemExplanation(
                condition_id="unknown-condition",
                explanation="Unsupported condition.",
                numerical_claims=(),
                citations=(duplicate,),
            ),
        ),
        recommendations=(
            RecommendationExplanation(
                recommendation_id="increase-cpu-limit",
                explanation="Use 999 units.",
                resource="memory_limit",
                current_value="1Mi",
                recommended_value="2Mi",
                citations=(duplicate,),
            ),
            RecommendationExplanation(
                recommendation_id="unknown-recommendation",
                explanation="Unsupported recommendation.",
                resource="cpu_limit",
                current_value="1m",
                recommended_value="2m",
                citations=(duplicate,),
            ),
        ),
        uncertainties=(
            GeneratedUncertainty(
                uncertainty_id="uncertainty-1",
                source_text="changed source",
                explanation="Risk 7 was altered.",
            ),
        ),
        approval_required=True,
    )

    report = LLMOutputValidator(clock=lambda: NOW).validate(
        candidate, artifact, "run-m12", RAGMode.ON
    )

    assert not report.passed
    codes = {issue.code for issue in report.issues}
    assert {
        "source_mismatch",
        "undeclared_number",
        "condition_coverage",
        "statistic_coverage",
        "numerical_mismatch",
        "unknown_statistic",
        "analysis_citation_coverage",
        "unknown_citation",
        "duplicate_citation",
        "unknown_condition",
        "recommendation_coverage",
        "recommendation_mismatch",
        "unknown_recommendation",
        "duplicate_claim",
        "uncertainty_coverage",
    }.issubset(codes)
    assert candidate.summary == "Observed 99 unsupported events."
    assert tuple(report.issues) == tuple(
        sorted(report.issues, key=lambda item: (item.location, item.code))
    )

    off_candidate = valid_candidate(artifact, rag_mode=RAGMode.OFF)
    off_problem = off_candidate.problems[0].model_copy(
        update={
            "citations": (
                *off_candidate.problems[0].citations,
                GeneratedCitation(
                    source=CitationSource.KNOWLEDGE_CHUNK,
                    source_id=artifact.package.evidence_excerpts[0].chunk_id,
                ),
            )
        }
    )
    off_candidate = off_candidate.model_copy(update={"problems": (off_problem,)})
    off_report = LLMOutputValidator(clock=lambda: NOW).validate(
        off_candidate, artifact, "run-m12", RAGMode.OFF
    )
    assert "rag_off_citation" in {issue.code for issue in off_report.issues}
    placeholder = valid_candidate(artifact).model_copy(
        update={"summary": "__GENERATE__"}
    )
    placeholder_report = LLMOutputValidator(clock=lambda: NOW).validate(
        placeholder, artifact, "run-m12", RAGMode.ON
    )
    assert "unfilled_placeholder" in {issue.code for issue in placeholder_report.issues}


def test_runner_records_configuration_dependency_parse_and_validation_failures() -> (
    None
):
    artifact = source_artifact()
    with pytest.raises(InferenceError, match="Qwen3"):
        InferenceRunner(FakeClient("{}"), "http://ollama", "llama:test")
    with pytest.raises(InferenceError, match="digest"):
        InferenceRunner(
            FakeClient("{}"),
            "http://ollama",
            "qwen3:test",
            expected_model_digest="invalid",
        )
    with pytest.raises(InferenceError, match="run ID"):
        runner(FakeClient("{}")).run(artifact, "BAD", RAGMode.ON)

    missing = runner(FakeClient("{}")).run(
        source_artifact(with_hits=False), "run-no-rag", RAGMode.ON
    )
    assert missing.status is InferenceStatus.FAILED
    assert missing.failure is not None
    assert missing.failure.code == "rag_evidence_missing"

    unavailable = runner(
        FakeClient("{}", error=OllamaError("ollama_unavailable", "connection refused"))
    ).run(artifact, "run-unavailable", RAGMode.ON)
    assert unavailable.status is InferenceStatus.FAILED
    assert unavailable.failure is not None
    assert unavailable.failure.code == "ollama_unavailable"
    assert unavailable.model_digest is None

    mismatch = runner(FakeClient("{}", digest="3" * 64)).run(
        artifact, "run-mismatch", RAGMode.ON
    )
    assert mismatch.failure is not None
    assert mismatch.failure.code == "ollama_model_mismatch"
    assert mismatch.model_digest == "3" * 64

    malformed = runner(FakeClient("not json")).run(
        artifact, "run-malformed", RAGMode.ON
    )
    assert malformed.status is InferenceStatus.FAILED
    assert malformed.failure is not None
    assert malformed.failure.code == "malformed_output"
    assert malformed.raw_response == "not json"
    assert malformed.prompt_eval_count == 100

    rejected_candidate = valid_candidate(artifact).model_copy(
        update={"summary": "Unsupported 4 value."}
    )
    rejected = runner(FakeClient(rejected_candidate.model_dump_json())).run(
        artifact, "run-m12", RAGMode.ON
    )
    assert rejected.status is InferenceStatus.REJECTED
    assert rejected.accepted_output is None
    assert rejected.validation is not None and not rejected.validation.passed


def test_naive_clocks_and_invalid_source_artifact_are_rejected() -> None:
    artifact = source_artifact()
    naive = datetime(2026, 1, 1)
    with pytest.raises(InferenceError, match="inference clock"):
        runner(FakeClient("{}"), clock=lambda: naive).run(
            artifact, "run-naive", RAGMode.ON
        )
    validator = LLMOutputValidator(clock=lambda: naive)
    with pytest.raises(InferenceError, match="validator clock"):
        validator.validate(valid_candidate(artifact), artifact, "run-m12", RAGMode.ON)
    invalid = LLMInputArtifact.model_construct(
        package_sha256="0" * 64, package=artifact.package
    )
    with pytest.raises(InferenceError, match="invalid M9"):
        runner(FakeClient("{}")).run(invalid, "run-invalid", RAGMode.ON)


def test_ollama_client_validates_model_and_generation_responses() -> None:
    calls: list[tuple[str, str, Mapping[str, Any] | None, float]] = []

    def request(
        method: str, url: str, payload: Mapping[str, Any] | None, timeout: float
    ) -> dict[str, Any]:
        calls.append((method, url, payload, timeout))
        if url.endswith("/api/tags"):
            return {
                "models": [
                    "foreign",
                    {"name": "other", "digest": MODEL_DIGEST},
                    {"name": "qwen3:test", "digest": MODEL_DIGEST},
                ]
            }
        return {
            "message": {"content": "{}"},
            "done": True,
            "done_reason": "stop",
            "prompt_eval_count": 2,
            "eval_count": 1,
            "total_duration": 3,
        }

    client = OllamaClient("http://ollama.test/", 12, request)
    assert client.model_digest("qwen3:test") == MODEL_DIGEST
    generated = client.generate(
        "qwen3:test",
        ({"role": "user", "content": "test"},),
        InferenceOptions(),
        {"type": "object"},
    )
    assert generated == OllamaGeneration("{}", 2, 1, 3)
    payload = calls[1][2]
    assert payload is not None
    assert payload["stream"] is False
    assert payload["format"] == {"type": "object"}

    def response(value: dict[str, Any]) -> OllamaClient:
        return OllamaClient("http://ollama", request_json=lambda *_: value)

    with pytest.raises(OllamaError, match="model list"):
        response({}).model_digest("qwen3:test")
    with pytest.raises(OllamaError, match="digest"):
        response({"models": [{"name": "qwen3:test", "digest": "bad"}]}).model_digest(
            "qwen3:test"
        )
    with pytest.raises(OllamaError, match="not installed"):
        response({"models": []}).model_digest("qwen3:test")

    options = InferenceOptions()
    messages = ({"role": "user", "content": "test"},)
    invalid_responses = (
        ({"error": "context overflow"}, "context overflow"),
        ({"message": {}, "done": True}, "content is missing"),
        ({"message": {"content": "{}"}, "done": False}, "did not complete"),
        (
            {
                "message": {"content": "{"},
                "done": True,
                "done_reason": "length",
            },
            "reason: length",
        ),
        (
            {"message": {"content": "{}"}, "done": True, "done_reason": "load"},
            "reason: load",
        ),
        (
            {
                "message": {"content": "{}"},
                "done": True,
                "prompt_eval_count": True,
            },
            "prompt_eval_count",
        ),
    )
    for value, message in invalid_responses:
        with pytest.raises(OllamaError, match=message):
            response(value).generate(
                "qwen3:test", messages, options, {"type": "object"}
            )
    none_metadata = response({"message": {"content": "{}"}, "done": True}).generate(
        "qwen3:test", messages, options, {"type": "object"}
    )
    assert none_metadata.prompt_eval_count is None
    complete_at_limit = response(
        {"message": {"content": "{}"}, "done": True, "done_reason": "length"}
    ).generate("qwen3:test", messages, options, {"type": "object"})
    assert complete_at_limit.content == "{}"


class FakeHTTPResponse:
    def __init__(self, value: bytes) -> None:
        self.value = value

    def __enter__(self) -> "FakeHTTPResponse":
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def read(self) -> bytes:
        return self.value


def test_request_json_handles_transport_and_schema_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        inference_module,
        "urlopen",
        lambda *_args, **_kwargs: FakeHTTPResponse(b'{"ok":1}'),
    )
    assert _request_json("POST", "http://ollama/api", {"x": 1}, 1) == {"ok": 1}
    assert _request_json("GET", "http://ollama/api", None, 1) == {"ok": 1}

    monkeypatch.setattr(
        inference_module, "urlopen", lambda *_args, **_kwargs: FakeHTTPResponse(b"[]")
    )
    with pytest.raises(OllamaError, match="must be an object"):
        _request_json("GET", "http://ollama", None, 1)
    monkeypatch.setattr(
        inference_module, "urlopen", lambda *_args, **_kwargs: FakeHTTPResponse(b"bad")
    )
    with pytest.raises(OllamaError, match="invalid JSON"):
        _request_json("GET", "http://ollama", None, 1)

    def http_error(*_args: object, **_kwargs: object) -> FakeHTTPResponse:
        raise HTTPError("http://ollama", 500, "error", Message(), BytesIO())

    monkeypatch.setattr(inference_module, "urlopen", http_error)
    with pytest.raises(OllamaError, match="HTTP 500"):
        _request_json("GET", "http://ollama", None, 1)

    def unavailable(*_args: object, **_kwargs: object) -> FakeHTTPResponse:
        raise URLError("refused")

    monkeypatch.setattr(inference_module, "urlopen", unavailable)
    with pytest.raises(OllamaError, match="refused"):
        _request_json("GET", "http://ollama", None, 1)


def test_store_rejects_missing_corrupt_invalid_and_write_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = InferenceStore(tmp_path)
    with pytest.raises(InferenceStoreError, match="invalid inference run ID"):
        store.load("BAD")
    with pytest.raises(InferenceStoreError, match="does not exist"):
        store.load("missing")

    artifact = runner(
        FakeClient(valid_candidate(source_artifact()).model_dump_json())
    ).run(source_artifact(), "run-m12", RAGMode.ON)
    invalid_artifact = artifact.model_construct(
        **{**artifact.__dict__, "model_name": ""}
    )
    with pytest.raises(InferenceStoreError, match="invalid inference artifact"):
        store.save(invalid_artifact)
    store.save(artifact)
    path = tmp_path / "run-m12.json"
    payload = json.loads(path.read_text())
    payload["artifact"]["model_name"] = "changed"
    path.write_text(json.dumps(payload))
    with pytest.raises(InferenceStoreError, match="invalid inference artifact"):
        store.load("run-m12")
    with pytest.raises(ValidationError, match="digest"):
        InferenceArtifactEnvelope(artifact_sha256="0" * 64, artifact=artifact)

    other_store = InferenceStore(tmp_path / "other")
    original_write = Path.write_text

    def fail_write(
        self: Path,
        data: str,
        encoding: str | None = None,
        errors: str | None = None,
        newline: str | None = None,
    ) -> int:
        if self.parent == other_store.directory:
            raise OSError("disk unavailable")
        return original_write(
            self, data, encoding=encoding, errors=errors, newline=newline
        )

    monkeypatch.setattr(Path, "write_text", fail_write)
    with pytest.raises(InferenceStoreError, match="disk unavailable"):
        other_store.save(artifact)


def test_prompt_and_text_digests_are_stable() -> None:
    artifact = source_artifact()
    first = render_messages(artifact, "run-m12", RAGMode.ON)
    second = render_messages(artifact, "run-m12", RAGMode.ON)
    assert first == second
    assert messages_digest(first) == messages_digest(second)
    assert text_digest("value") != text_digest("Value")
    no_findings = render_messages(no_findings_artifact(), "run-empty", RAGMode.OFF)
    assert '"conditions_in_output_order":[]' in no_findings[1]["content"]
    assert "post-change experiment" in no_findings[1]["content"]

    on_schema = compact_response_schema(artifact, RAGMode.ON)
    properties = on_schema["properties"]
    assert properties["summary"]["pattern"] == r"^[A-Za-z ,.':;()/-]{1,120}$"
    assert properties["problem_explanations"]["items"] == {
        "type": "string",
        "minLength": 1,
        "maxLength": 72,
        "pattern": r"^[A-Za-z ,.':;()/-]{1,72}$",
    }
    off_schema = compact_response_schema(artifact, RAGMode.OFF)
    assert (
        off_schema["properties"]["problem_knowledge_citation_ids"]["items"]["maxItems"]
        == 0
    )


def test_inference_contracts_reject_inconsistent_states(tmp_path: Path) -> None:
    source = source_artifact()
    accepted = runner(FakeClient(valid_candidate(source).model_dump_json())).run(
        source, "run-m12", RAGMode.ON
    )
    assert accepted.validation is not None
    assert accepted.accepted_output is not None

    def invalid(**updates: object) -> None:
        changed = accepted.model_copy(update=updates)
        with pytest.raises(ValidationError):
            InferenceRunArtifact.model_validate(changed.model_dump(mode="json"))

    bad_report = accepted.validation.model_copy(update={"passed": False, "issues": ()})
    with pytest.raises(ValidationError, match="passes exactly"):
        LLMValidationReport.model_validate(bad_report.model_dump(mode="json"))
    naive_report = accepted.validation.model_copy(
        update={"validated_at": datetime(2026, 1, 1)}
    )
    with pytest.raises(ValidationError, match="timezone"):
        LLMValidationReport.model_validate(naive_report.model_dump(mode="json"))

    invalid(requested_at=datetime(2026, 1, 1))
    invalid(ended_at=datetime(2020, 1, 1, tzinfo=NOW.tzinfo))
    invalid(raw_response_sha256=None)
    invalid(raw_response_sha256="0" * 64)
    invalid(candidate=None)
    invalid(validation=None)
    invalid(
        accepted_output=accepted.accepted_output.model_copy(
            update={"validation_sha256": "0" * 64}
        )
    )
    invalid(status=InferenceStatus.REJECTED)
    invalid(status=InferenceStatus.FAILED)

    failed = accepted.model_copy(
        update={
            "status": InferenceStatus.FAILED,
            "candidate": None,
            "validation": None,
            "accepted_output": None,
            "failure": InferenceFailure(code="test_failure", message="failed"),
        }
    )
    assert InferenceRunArtifact.model_validate(failed.model_dump(mode="json")) == failed

    input_store = LLMInputStore(tmp_path / "inputs")
    input_store.save(source.package)
    assert input_store.load_artifact(source.package.package_id) == source
