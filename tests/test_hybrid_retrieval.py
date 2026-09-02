from uuid import NAMESPACE_URL, uuid5

from qdrant_client import AsyncQdrantClient

from app.core.config import Settings
from app.rag.chunking import KnowledgeChunk
from app.rag.vector_store import QdrantKnowledgeStore


async def test_v2_collection_supports_dense_sparse_and_rrf(monkeypatch) -> None:
    client = AsyncQdrantClient(":memory:")
    monkeypatch.setattr("app.rag.vector_store.AsyncQdrantClient", lambda **kwargs: client)
    settings = Settings(
        _env_file=None,
        qdrant_collection="hybrid-test",
        qdrant_score_threshold=None,
        qdrant_search_top_k=2,
        qdrant_dense_prefetch_top_k=5,
        qdrant_sparse_prefetch_top_k=5,
        qdrant_hybrid_fusion_top_k=5,
    )
    store = QdrantKnowledgeStore(settings)
    try:
        await store.index_document(
            document_id="lexical-document",
            title="Lexical Guide",
            version=None,
            category="security",
            chunks=[
                KnowledgeChunk(
                    chunk_index=0,
                    text="支持 SAML 2.0 单点登录",
                    page_number=None,
                )
            ],
            vectors=[[0.0, 1.0]],
        )
        await store.index_document(
            document_id="semantic-document",
            title="Semantic Guide",
            version=None,
            category="security",
            chunks=[
                KnowledgeChunk(
                    chunk_index=0,
                    text="Federated identity access",
                    page_number=None,
                )
            ],
            vectors=[[1.0, 0.0]],
        )
        await store.index_document(
            document_id="inactive-document",
            title="Inactive Guide",
            version=None,
            category="security",
            chunks=[KnowledgeChunk(chunk_index=0, text="SAML identity", page_number=None)],
            vectors=[[1.0, 0.0]],
        )
        await client.set_payload(
            collection_name=settings.qdrant_collection,
            payload={"status": "DELETED"},
            points=[str(uuid5(NAMESPACE_URL, "dealflow:inactive-document:0"))],
            wait=True,
        )

        evidence = await store.search(
            [1.0, 0.0],
            query_text="SAML 单点登录",
            mode="hybrid",
            limit=2,
        )
        collection = await client.get_collection(settings.qdrant_collection)

        assert settings.qdrant_dense_vector_name in collection.config.params.vectors
        assert settings.qdrant_sparse_vector_name in collection.config.params.sparse_vectors
        assert {item.document_id for item in evidence} == {
            "lexical-document",
            "semantic-document",
        }
        assert all(item.retrieval_mode == "hybrid" for item in evidence)
    finally:
        await store.close()
