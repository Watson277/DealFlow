from types import SimpleNamespace

from app.rag.retrieval import expand_parent_evidence
from app.rag.vector_store import RetrievedEvidence


def _evidence(
    *,
    point_id: str,
    document_id: str,
    parent_id: str | None,
    text: str,
    score: float,
) -> RetrievedEvidence:
    return RetrievedEvidence(
        point_id=point_id,
        document_id=document_id,
        title="Security Guide",
        version="1.0",
        category="security",
        page_number=None,
        text=text,
        score=score,
        parent_id=parent_id,
    )


async def test_parent_evidence_is_loaded_from_mysql_and_deduplicated(monkeypatch) -> None:
    evidence = [
        _evidence(
            point_id="child-1",
            document_id="document-1",
            parent_id="parent-1",
            text="SAML is supported.",
            score=0.99,
        ),
        _evidence(
            point_id="child-2",
            document_id="document-1",
            parent_id="parent-1",
            text="OIDC is supported.",
            score=0.95,
        ),
        _evidence(
            point_id="child-3",
            document_id="deleted-document",
            parent_id="parent-2",
            text="This document is inactive.",
            score=0.90,
        ),
    ]

    class FakeDocumentRepository:
        def __init__(self, session: object) -> None:
            pass

        async def active_knowledge_ids(self, document_ids: list[str]) -> set[str]:
            assert document_ids == ["document-1", "deleted-document"]
            return {"document-1"}

    class FakeChunkRepository:
        def __init__(self, session: object) -> None:
            pass

        async def get_parents(self, parent_ids: list[str]) -> dict[str, object]:
            assert parent_ids == ["parent-1", "parent-1"]
            return {"parent-1": SimpleNamespace(text="Complete authentication section.")}

    monkeypatch.setattr("app.rag.retrieval.DocumentRepository", FakeDocumentRepository)
    monkeypatch.setattr("app.rag.retrieval.KnowledgeChunkRepository", FakeChunkRepository)

    expanded = await expand_parent_evidence(object(), evidence, limit=5)  # type: ignore[arg-type]

    assert len(expanded) == 1
    assert expanded[0].point_id == "child-1"
    assert expanded[0].text == "Complete authentication section."
    assert expanded[0].matched_child_text == "SAML is supported."


async def test_missing_parent_keeps_child_for_backward_compatibility(monkeypatch) -> None:
    evidence = [
        _evidence(
            point_id="legacy-child",
            document_id="document-1",
            parent_id="missing-parent",
            text="Legacy child text.",
            score=0.8,
        )
    ]

    class FakeDocumentRepository:
        def __init__(self, session: object) -> None:
            pass

        async def active_knowledge_ids(self, document_ids: list[str]) -> set[str]:
            return {"document-1"}

    class FakeChunkRepository:
        def __init__(self, session: object) -> None:
            pass

        async def get_parents(self, parent_ids: list[str]) -> dict[str, object]:
            return {}

    monkeypatch.setattr("app.rag.retrieval.DocumentRepository", FakeDocumentRepository)
    monkeypatch.setattr("app.rag.retrieval.KnowledgeChunkRepository", FakeChunkRepository)

    expanded = await expand_parent_evidence(object(), evidence, limit=5)  # type: ignore[arg-type]

    assert expanded[0].text == "Legacy child text."
    assert expanded[0].matched_child_text is None
