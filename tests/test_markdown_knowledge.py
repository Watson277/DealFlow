import pytest

from app.core.config import Settings
from app.core.exceptions import KnowledgeIndexError
from app.infrastructure.storage.minio import (
    KNOWLEDGE_ALLOWED_EXTENSIONS,
    RFP_ALLOWED_EXTENSIONS,
)
from app.rag.markdown import MarkdownKnowledgeChunker, parse_markdown_units


def test_markdown_upload_is_limited_to_knowledge_documents() -> None:
    assert {".md", ".markdown"}.issubset(KNOWLEDGE_ALLOWED_EXTENSIONS)
    assert ".md" not in RFP_ALLOWED_EXTENSIONS
    assert ".markdown" not in RFP_ALLOWED_EXTENSIONS


def test_markdown_parser_preserves_headings_tables_code_and_lists() -> None:
    markdown = """# Platform

Introduction.

## Security

- SAML 2.0
- SCIM 2.0

| Capability | Status |
| --- | --- |
| Audit | Supported |

```json
{"private_deployment": true}
```
"""

    units = parse_markdown_units(markdown)

    assert [unit.block_type for unit in units] == ["text", "list", "table", "code"]
    assert units[0].section_path == ("Platform",)
    assert all(unit.section_path == ("Platform", "Security") for unit in units[1:])
    assert [unit.block_id for unit in units] == [
        "md_b0001",
        "md_b0002",
        "md_b0003",
        "md_b0004",
    ]
    assert units[2].atomic is True
    assert units[3].atomic is True


def test_markdown_parser_supports_setext_peer_headings() -> None:
    markdown = """Enterprise Guide
================

Security
--------

SAML is supported.

Operations
----------

Monitoring is supported.
"""

    units = parse_markdown_units(markdown)

    assert [unit.section_path for unit in units] == [
        ("Enterprise Guide", "Security"),
        ("Enterprise Guide", "Operations"),
    ]


def test_markdown_chunker_adds_document_and_section_context() -> None:
    chunker = MarkdownKnowledgeChunker(
        Settings(knowledge_chunk_size_chars=500, knowledge_chunk_overlap_chars=20)
    )
    chunks = chunker.split(
        "# Platform\n\n## Security\n\nSAML 2.0 is supported.",
        document_title="Enterprise Guide",
        document_version="1.2",
    )

    assert len(chunks) == 1
    assert chunks[0].page_number is None
    assert chunks[0].text == (
        "Document: Enterprise Guide\n"
        "Version: 1.2\n"
        "Section: Platform > Security\n\n"
        "SAML 2.0 is supported."
    )


def test_markdown_chunker_keeps_tables_and_code_as_separate_chunks() -> None:
    chunker = MarkdownKnowledgeChunker(
        Settings(knowledge_chunk_size_chars=500, knowledge_chunk_overlap_chars=20)
    )
    markdown = """# Operations

Before the table.

| Capability | Status |
| --- | --- |
| Monitoring | Supported |

```yaml
monitoring: true
```

After the code.
"""

    chunks = chunker.split(markdown)

    assert len(chunks) == 4
    assert chunks[0].text.endswith("Before the table.")
    assert chunks[1].text.endswith("| Monitoring | Supported |")
    assert chunks[2].text.endswith("```yaml\nmonitoring: true\n```")
    assert chunks[3].text.endswith("After the code.")


def test_markdown_chunker_rejects_heading_only_documents() -> None:
    chunker = MarkdownKnowledgeChunker(Settings())

    with pytest.raises(KnowledgeIndexError, match="no indexable Markdown"):
        chunker.split("# Heading only")
