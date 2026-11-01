"""Read-only validation and inspection for the canonical M6 knowledge repository."""

import hashlib
from pathlib import Path

from pydantic import ValidationError

from kri.contracts import (
    KnowledgeDocument,
    KnowledgeDocumentSummary,
    KnowledgeManifestEntry,
    KnowledgeRepositoryManifest,
)


class KnowledgeRepositoryError(RuntimeError):
    """The canonical knowledge repository is missing, unsafe, or inconsistent."""


class KnowledgeRepository:
    """Load checksum-validated Markdown registered by a versioned manifest."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def load_manifest(self) -> KnowledgeRepositoryManifest:
        path = self.root / "manifest.json"
        try:
            return KnowledgeRepositoryManifest.model_validate_json(
                path.read_text(encoding="utf-8")
            )
        except FileNotFoundError as error:
            raise KnowledgeRepositoryError(
                "knowledge manifest does not exist"
            ) from error
        except (OSError, ValidationError) as error:
            raise KnowledgeRepositoryError(
                f"invalid knowledge manifest: {error}"
            ) from error

    def load_all(self) -> tuple[KnowledgeDocument, ...]:
        manifest = self.load_manifest()
        documents = tuple(self._load_entry(entry) for entry in manifest.documents)
        registered = {entry.path for entry in manifest.documents}
        try:
            discovered = {
                path.relative_to(self.root).as_posix()
                for path in (self.root / "documents").rglob("*.md")
                if path.is_file()
            }
        except OSError as error:
            raise KnowledgeRepositoryError(str(error)) from error
        extras = sorted(discovered - registered)
        if extras:
            raise KnowledgeRepositoryError(
                f"unregistered knowledge Markdown: {', '.join(extras)}"
            )
        return documents

    def get(self, document_id: str) -> KnowledgeDocument:
        documents = self.load_all()
        try:
            return next(
                document
                for document in documents
                if document.document_id == document_id
            )
        except StopIteration as error:
            raise KnowledgeRepositoryError(
                f"knowledge document does not exist: {document_id}"
            ) from error

    def inspect(self) -> tuple[KnowledgeDocumentSummary, ...]:
        return tuple(
            KnowledgeDocumentSummary(
                document_id=document.document_id,
                document_type=document.document_type,
                title=document.title,
                version=document.version,
                verification_status=document.verification_status,
                tags=document.tags,
                source_count=len(document.sources),
            )
            for document in self.load_all()
        )

    def _load_entry(self, entry: KnowledgeManifestEntry) -> KnowledgeDocument:
        root = self.root.resolve()
        path = (self.root / entry.path).resolve()
        if not path.is_relative_to(root):
            raise KnowledgeRepositoryError(
                f"knowledge path escapes repository root: {entry.path}"
            )
        try:
            content_bytes = path.read_bytes()
            content = content_bytes.decode("utf-8")
        except (OSError, UnicodeDecodeError) as error:
            raise KnowledgeRepositoryError(
                f"cannot read knowledge document {entry.document_id}: {error}"
            ) from error
        digest = hashlib.sha256(content_bytes).hexdigest()
        if digest != entry.content_sha256:
            raise KnowledgeRepositoryError(
                f"knowledge checksum mismatch: {entry.document_id}"
            )
        try:
            return KnowledgeDocument.model_validate(
                {
                    **entry.model_dump(),
                    "content": content,
                }
            )
        except ValidationError as error:
            raise KnowledgeRepositoryError(
                f"invalid knowledge document {entry.document_id}: {error}"
            ) from error
