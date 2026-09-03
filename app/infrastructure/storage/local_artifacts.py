"""Optional local copies of processed document artifacts for developer inspection."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from uuid import UUID

from app.core.config import Settings

LocalDocumentKind = Literal["rfp", "knowledge"]


class LocalArtifactExporter:
    """Write processed artifacts beneath a deterministic, document-scoped directory."""

    def __init__(self, settings: Settings) -> None:
        self.enabled = settings.local_artifact_export_enabled
        self.root = settings.local_artifact_export_dir

    def export(
        self,
        *,
        kind: LocalDocumentKind,
        document_id: UUID | str,
        original_filename: str,
        artifacts: Mapping[str, str],
        metadata: Mapping[str, Any] | None = None,
    ) -> Path | None:
        if not self.enabled:
            return None

        canonical_id = UUID(str(document_id))
        root = self.root.expanduser().resolve()
        target = (root / kind / str(canonical_id)).resolve()
        if not target.is_relative_to(root):
            raise ValueError("local artifact target escapes the configured export directory")
        target.mkdir(parents=True, exist_ok=True)

        exported_files: list[str] = []
        for filename, content in artifacts.items():
            self._validate_filename(filename)
            self._write_text_atomic(target / filename, content)
            exported_files.append(filename)

        manifest = {
            "schema_version": "1.0",
            "document_type": kind,
            "document_id": str(canonical_id),
            "original_filename": original_filename,
            "exported_at": datetime.now(UTC).isoformat(),
            "files": sorted(exported_files),
            "metadata": dict(metadata or {}),
        }
        self._write_text_atomic(
            target / "manifest.json",
            f"{json.dumps(manifest, ensure_ascii=False, indent=2)}\n",
        )
        return target

    @staticmethod
    def _validate_filename(filename: str) -> None:
        path = Path(filename)
        if not filename or path.name != filename or filename in {".", "..", "manifest.json"}:
            raise ValueError(f"invalid local artifact filename: {filename!r}")

    @staticmethod
    def _write_text_atomic(path: Path, content: str) -> None:
        temporary = path.with_name(f".{path.name}.tmp")
        temporary.write_text(content, encoding="utf-8", newline="\n")
        temporary.replace(path)
