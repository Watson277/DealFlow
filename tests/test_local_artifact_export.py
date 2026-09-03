import json
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.infrastructure.storage.local_artifacts import LocalArtifactExporter


def test_local_artifact_exporter_writes_document_scoped_files(tmp_path) -> None:
    document_id = uuid4()
    exporter = LocalArtifactExporter(
        Settings(
            local_artifact_export_enabled=True,
            local_artifact_export_dir=tmp_path,
        )
    )

    directory = exporter.export(
        kind="knowledge",
        document_id=document_id,
        original_filename="企业知识.pdf",
        artifacts={
            "parsed.md": "# Parsed\n",
            "document-ir.v1.json": "{}\n",
            "knowledge-chunks.v1.json": "{}\n",
        },
        metadata={"parsed_text_object_key": "knowledge/example/parsed.txt"},
    )

    assert directory == tmp_path / "knowledge" / str(document_id)
    assert (directory / "parsed.md").read_text(encoding="utf-8") == "# Parsed\n"
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["document_id"] == str(document_id)
    assert manifest["original_filename"] == "企业知识.pdf"
    assert manifest["files"] == [
        "document-ir.v1.json",
        "knowledge-chunks.v1.json",
        "parsed.md",
    ]
    assert manifest["metadata"]["parsed_text_object_key"] == "knowledge/example/parsed.txt"


def test_local_artifact_exporter_is_noop_when_disabled(tmp_path) -> None:
    exporter = LocalArtifactExporter(
        Settings(
            local_artifact_export_enabled=False,
            local_artifact_export_dir=tmp_path,
        )
    )

    result = exporter.export(
        kind="rfp",
        document_id=uuid4(),
        original_filename="rfp.pdf",
        artifacts={"parsed.md": "content"},
    )

    assert result is None
    assert not any(tmp_path.iterdir())


def test_local_artifact_exporter_rejects_nested_artifact_filename(tmp_path) -> None:
    exporter = LocalArtifactExporter(
        Settings(
            local_artifact_export_enabled=True,
            local_artifact_export_dir=tmp_path,
        )
    )

    with pytest.raises(ValueError, match="invalid local artifact filename"):
        exporter.export(
            kind="rfp",
            document_id=uuid4(),
            original_filename="rfp.pdf",
            artifacts={"../outside.txt": "unsafe"},
        )
