"""Offline tests for the canonical M6 knowledge repository."""

import hashlib
import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, cast

import pytest
from pydantic import ValidationError

from kri.contracts import (
    KnowledgeDocument,
    KnowledgeDocumentType,
    KnowledgeManifestEntry,
    KnowledgeRepositoryManifest,
    KnowledgeSource,
    KnowledgeVerificationStatus,
)
from kri.knowledge import KnowledgeRepository, KnowledgeRepositoryError

CANONICAL_ROOT = Path(__file__).parents[1] / "knowledge"


def copied_repository(tmp_path: Path) -> Path:
    target = tmp_path / "knowledge"
    shutil.copytree(CANONICAL_ROOT, target)
    return target


def manifest_payload(root: Path) -> dict[str, Any]:
    return cast(
        dict[str, Any],
        json.loads((root / "manifest.json").read_text(encoding="utf-8")),
    )


def write_manifest(root: Path, payload: dict[str, Any]) -> None:
    (root / "manifest.json").write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8"
    )


def update_digest(root: Path, payload: dict[str, Any], index: int) -> None:
    content = (root / payload["documents"][index]["path"]).read_bytes()
    payload["documents"][index]["content_sha256"] = hashlib.sha256(content).hexdigest()


def test_canonical_repository_loads_lists_and_gets_verified_documents() -> None:
    repository = KnowledgeRepository(CANONICAL_ROOT)

    manifest = repository.load_manifest()
    documents = repository.load_all()
    summaries = repository.inspect()
    selected = repository.get("runbook-cpu-throttling")

    assert manifest.schema_version == "1.0"
    assert manifest.repository_version == "1.0.0"
    assert len(documents) == 6
    assert [item.document_id for item in documents] == sorted(
        item.document_id for item in documents
    )
    assert {item.document_type for item in documents} == set(KnowledgeDocumentType)
    assert all(
        item.verification_status is KnowledgeVerificationStatus.VERIFIED
        for item in documents
    )
    assert all(item.verified_at is not None and item.verified_by for item in documents)
    assert all(item.sources for item in documents)
    assert all(
        source.uri.startswith(("https://", "repo://"))
        for item in documents
        for source in item.sources
    )
    assert len(summaries) == 6
    assert summaries[0].source_count == 2
    assert selected.content.startswith("# Runbook: Diagnose CPU Throttling\n")
    assert "bounded comparable load" in selected.content


def test_repository_reports_missing_manifest_and_document(tmp_path: Path) -> None:
    with pytest.raises(KnowledgeRepositoryError, match="manifest does not exist"):
        KnowledgeRepository(tmp_path).load_manifest()

    root = copied_repository(tmp_path)
    with pytest.raises(KnowledgeRepositoryError, match="does not exist"):
        KnowledgeRepository(root).get("unknown-document")


def test_repository_rejects_malformed_or_unreadable_manifest(tmp_path: Path) -> None:
    root = tmp_path / "malformed"
    root.mkdir()
    (root / "manifest.json").write_text("not json", encoding="utf-8")
    with pytest.raises(KnowledgeRepositoryError, match="invalid knowledge manifest"):
        KnowledgeRepository(root).load_manifest()

    directory_root = tmp_path / "directory-manifest"
    (directory_root / "manifest.json").mkdir(parents=True)
    with pytest.raises(KnowledgeRepositoryError, match="invalid knowledge manifest"):
        KnowledgeRepository(directory_root).load_manifest()


def test_repository_rejects_checksum_heading_and_missing_file(tmp_path: Path) -> None:
    checksum_root = copied_repository(tmp_path / "checksum")
    first = KnowledgeRepository(checksum_root).load_manifest().documents[0]
    (checksum_root / first.path).write_text("changed\n", encoding="utf-8")
    with pytest.raises(KnowledgeRepositoryError, match="checksum mismatch"):
        KnowledgeRepository(checksum_root).load_all()

    heading_root = copied_repository(tmp_path / "heading")
    payload = manifest_payload(heading_root)
    first_path = heading_root / payload["documents"][0]["path"]
    first_path.write_text("# Wrong title\n", encoding="utf-8")
    update_digest(heading_root, payload, 0)
    write_manifest(heading_root, payload)
    with pytest.raises(KnowledgeRepositoryError, match="heading must match"):
        KnowledgeRepository(heading_root).load_all()

    missing_root = copied_repository(tmp_path / "missing")
    missing = KnowledgeRepository(missing_root).load_manifest().documents[0]
    (missing_root / missing.path).unlink()
    with pytest.raises(KnowledgeRepositoryError, match="cannot read"):
        KnowledgeRepository(missing_root).load_all()


def test_repository_rejects_invalid_utf8_escape_and_unregistered_markdown(
    tmp_path: Path,
) -> None:
    encoding_root = copied_repository(tmp_path / "encoding")
    payload = manifest_payload(encoding_root)
    document_path = encoding_root / payload["documents"][0]["path"]
    document_path.write_bytes(b"\xff\xfe")
    update_digest(encoding_root, payload, 0)
    write_manifest(encoding_root, payload)
    with pytest.raises(KnowledgeRepositoryError, match="cannot read"):
        KnowledgeRepository(encoding_root).load_all()

    escape_root = copied_repository(tmp_path / "escape")
    escape_payload = manifest_payload(escape_root)
    outside = tmp_path / "outside.md"
    outside.write_text("# Outside\n", encoding="utf-8")
    registered = escape_root / escape_payload["documents"][0]["path"]
    registered.unlink()
    registered.symlink_to(outside)
    escape_payload["documents"][0]["content_sha256"] = hashlib.sha256(
        outside.read_bytes()
    ).hexdigest()
    write_manifest(escape_root, escape_payload)
    with pytest.raises(KnowledgeRepositoryError, match="escapes repository root"):
        KnowledgeRepository(escape_root).load_all()

    extra_root = copied_repository(tmp_path / "extra")
    (extra_root / "documents" / "extra.md").write_text("# Extra\n", encoding="utf-8")
    with pytest.raises(KnowledgeRepositoryError, match="unregistered"):
        KnowledgeRepository(extra_root).load_all()


def test_repository_wraps_document_discovery_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = copied_repository(tmp_path)

    def fail_discovery(self: Path, pattern: str) -> list[Path]:
        raise OSError("discovery failed")

    monkeypatch.setattr(Path, "rglob", fail_discovery)
    with pytest.raises(KnowledgeRepositoryError, match="discovery failed"):
        KnowledgeRepository(root).load_all()


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("document_id", "NOT-SAFE", "document ID"),
        ("version", "1.0", "semantic"),
        ("path", "../outside.md", "safe relative"),
        ("path", "/outside.md", "safe relative"),
        ("path", "documents\\outside.md", "safe relative"),
        ("path", "documents/outside.txt", "safe relative"),
        ("content_sha256", "not-a-digest", "string_pattern"),
    ],
)
def test_manifest_entry_rejects_invalid_identity_version_path_and_digest(
    field: str, value: object, message: str
) -> None:
    payload = manifest_payload(CANONICAL_ROOT)["documents"][0]
    payload[field] = value

    with pytest.raises(ValidationError, match=message):
        KnowledgeManifestEntry.model_validate(payload)


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda value: value.update(verified_at=None),
            "requires verifier metadata",
        ),
        (
            lambda value: value.update(verified_at=datetime(2026, 11, 1)),
            "verification time must include a timezone",
        ),
        (
            lambda value: value.update(
                verification_status="needs_review",
                verified_at="2026-11-01T12:00:00Z",
            ),
            "cannot claim verification",
        ),
        (
            lambda value: value.update(tags=("z", "a")),
            "must be sorted",
        ),
        (
            lambda value: value.update(tags=("same", "same")),
            "must be unique",
        ),
        (
            lambda value: value.update(tags=("Not-Safe",)),
            "lowercase stable",
        ),
        (
            lambda value: value.update(sources=(value["sources"][0],) * 2),
            "source IDs must be unique",
        ),
    ],
)
def test_manifest_entry_rejects_invalid_verification_tags_and_sources(
    mutate: Any, message: str
) -> None:
    payload = manifest_payload(CANONICAL_ROOT)["documents"][0]
    mutate(payload)

    with pytest.raises(ValidationError, match=message):
        KnowledgeManifestEntry.model_validate(payload)


def test_type_specific_provenance_is_required() -> None:
    payload = manifest_payload(CANONICAL_ROOT)
    incident = payload["documents"][0]
    incident["sources"][0]["source_type"] = "official_documentation"
    incident["sources"][1]["source_type"] = "official_documentation"
    with pytest.raises(ValidationError, match="project provenance"):
        KnowledgeManifestEntry.model_validate(incident)

    documentation = payload["documents"][2]
    for source in documentation["sources"]:
        source["source_type"] = "project_documentation"
    with pytest.raises(ValidationError, match="official source"):
        KnowledgeManifestEntry.model_validate(documentation)


def test_needs_review_entry_without_verification_metadata_is_valid() -> None:
    payload = manifest_payload(CANONICAL_ROOT)["documents"][0]
    payload.update(
        verification_status="needs_review",
        verified_at=None,
        verified_by=None,
    )

    entry = KnowledgeManifestEntry.model_validate(payload)

    assert entry.verification_status is KnowledgeVerificationStatus.NEEDS_REVIEW


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("source_id", "BAD", "source ID"),
        ("uri", "http://example.com", "https"),
        ("uri", "https://example.com/has space", "https"),
        ("accessed_at", datetime(2026, 11, 1), "timezone"),
    ],
)
def test_knowledge_source_rejects_invalid_provenance(
    field: str, value: object, message: str
) -> None:
    payload = manifest_payload(CANONICAL_ROOT)["documents"][0]["sources"][0]
    payload[field] = value

    with pytest.raises(ValidationError, match=message):
        KnowledgeSource.model_validate(payload)


def test_manifest_rejects_version_time_order_duplicates_and_missing_types() -> None:
    original = manifest_payload(CANONICAL_ROOT)
    for field, value, message in (
        ("repository_version", "1", "semantic"),
        ("released_at", datetime(2026, 11, 1), "timezone"),
    ):
        payload = {**original, field: value}
        with pytest.raises(ValidationError, match=message):
            KnowledgeRepositoryManifest.model_validate(payload)

    payload = manifest_payload(CANONICAL_ROOT)
    payload["documents"] = list(reversed(payload["documents"]))
    with pytest.raises(ValidationError, match="sorted"):
        KnowledgeRepositoryManifest.model_validate(payload)

    payload = manifest_payload(CANONICAL_ROOT)
    payload["documents"][1]["document_id"] = payload["documents"][0]["document_id"]
    with pytest.raises(ValidationError, match="IDs must be unique"):
        KnowledgeRepositoryManifest.model_validate(payload)

    payload = manifest_payload(CANONICAL_ROOT)
    payload["documents"][1]["path"] = payload["documents"][0]["path"]
    with pytest.raises(ValidationError, match="paths must be unique"):
        KnowledgeRepositoryManifest.model_validate(payload)

    payload = manifest_payload(CANONICAL_ROOT)
    payload["documents"] = payload["documents"][2:]
    with pytest.raises(ValidationError, match="every document type"):
        KnowledgeRepositoryManifest.model_validate(payload)


def test_document_contract_rejects_mismatched_heading() -> None:
    entry = KnowledgeManifestEntry.model_validate(
        manifest_payload(CANONICAL_ROOT)["documents"][0]
    )
    with pytest.raises(ValidationError, match="heading must match"):
        KnowledgeDocument.model_validate(
            {**entry.model_dump(), "content": "# Different\n"}
        )
