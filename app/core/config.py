from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        populate_by_name=True,
    )

    app_name: str = "DealFlow"
    app_version: str = "0.1.0"
    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    log_level: str = "INFO"
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:5173"]

    database_url: str = "mysql+aiomysql://dealflow:dealflow_mysql_change_me@localhost:3307/dealflow"
    redis_url: str = "redis://:dealflow_redis_change_me@localhost:6380/0"
    kafka_bootstrap_servers: str = "localhost:9092"
    kafka_client_id: str = "dealflow-api"
    kafka_rfp_topic: str = "rfp.uploaded"
    kafka_rfp_completed_topic: str = "rfp.completed"
    kafka_rfp_failed_topic: str = "rfp.failed"
    kafka_requirements_extracted_topic: str = "rfp.requirements.extracted"
    kafka_capabilities_evaluated_topic: str = "rfp.capabilities.evaluated"
    kafka_proposal_generated_topic: str = "proposal.generated"
    kafka_proposal_approved_topic: str = "proposal.approved"
    kafka_knowledge_ingestion_topic: str = "knowledge.ingestion.requested"
    kafka_rfp_worker_group: str = "dealflow-rfp-workers"
    kafka_requirement_worker_group: str = "dealflow-requirement-workers"
    kafka_capability_worker_group: str = "dealflow-capability-workers"
    kafka_proposal_worker_group: str = "dealflow-proposal-workers"
    kafka_knowledge_worker_group: str = "dealflow-knowledge-workers"
    outbox_relay_poll_interval_seconds: float = Field(default=1.0, gt=0.0, le=60.0)
    outbox_relay_batch_size: int = Field(default=50, ge=1, le=1_000)
    outbox_relay_initial_backoff_seconds: float = Field(default=1.0, gt=0.0, le=3_600.0)
    outbox_relay_max_backoff_seconds: float = Field(default=300.0, gt=0.0, le=86_400.0)
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "dealflow_knowledge_v2"
    qdrant_search_top_k: int = 5
    qdrant_score_threshold: float | None = 0.25
    qdrant_dense_vector_name: str = "dense"
    qdrant_sparse_vector_name: str = "bm25"
    qdrant_bm25_model: str = "qdrant/bm25"
    qdrant_dense_prefetch_top_k: int = Field(default=40, ge=1)
    qdrant_sparse_prefetch_top_k: int = Field(default=40, ge=1)
    qdrant_hybrid_fusion_top_k: int = Field(default=30, ge=1)

    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = Field(
        default="dealflow_admin",
        validation_alias=AliasChoices("MINIO_ACCESS_KEY", "DEALFLOW_MINIO_ROOT_USER"),
    )
    minio_secret_key: str = Field(
        default="dealflow_minio_change_me",
        validation_alias=AliasChoices("MINIO_SECRET_KEY", "DEALFLOW_MINIO_ROOT_PASSWORD"),
    )
    minio_secure: bool = False
    minio_bucket: str = Field(
        default="dealflow",
        validation_alias=AliasChoices("MINIO_BUCKET", "DEALFLOW_MINIO_BUCKET"),
    )

    local_artifact_export_enabled: bool = False
    local_artifact_export_dir: Path = Path("data/processed-documents")

    max_rfp_upload_size_bytes: int = 50 * 1024 * 1024
    pdf_parser_version: str = Field(
        default="page-routing-layout-2.1",
        min_length=1,
        max_length=64,
    )
    pdf_max_pages: int = Field(default=500, ge=1, le=10_000)
    pdf_text_min_effective_chars: int = Field(default=20, ge=1)
    pdf_text_max_garbled_ratio: float = Field(default=0.10, ge=0.0, le=1.0)
    pdf_scanned_image_coverage_threshold: float = Field(default=0.60, ge=0.0, le=1.0)
    pdf_mixed_image_coverage_threshold: float = Field(default=0.35, ge=0.0, le=1.0)
    pdf_ocr_enabled: bool = True
    pdf_ocr_dpi: int = Field(default=250, ge=72, le=600)
    pdf_ocr_languages: str = Field(default="chi_sim+eng", min_length=1, max_length=128)
    pdf_ocr_timeout_seconds: float = Field(default=120.0, gt=0.0, le=600.0)
    pdf_ocr_executable: str = Field(default="tesseract", min_length=1, max_length=512)
    pdf_ocr_page_segmentation_mode: int = Field(default=3, ge=0, le=13)
    pdf_layout_enabled: bool = True
    pdf_layout_detect_tables: bool = True
    pdf_layout_header_footer_margin_ratio: float = Field(default=0.12, gt=0.0, lt=0.5)
    pdf_layout_repeated_region_min_fraction: float = Field(default=0.60, gt=0.0, le=1.0)
    pdf_layout_column_gap_ratio: float = Field(default=0.06, gt=0.0, lt=1.0)
    pdf_layout_paragraph_gap_multiplier: float = Field(default=1.40, gt=0.0, le=5.0)
    pdf_layout_title_font_ratio: float = Field(default=1.25, gt=1.0, le=5.0)
    pdf_layout_detection_enabled: bool = True
    pdf_layout_detection_dpi: int = Field(default=250, ge=72, le=600)
    pdf_layout_min_region_area_ratio: float = Field(default=0.001, gt=0.0, lt=1.0)
    pdf_tsr_enabled: bool = True
    pdf_tsr_max_cells: int = Field(default=200, ge=1, le=5_000)
    pdf_vlm_enabled: bool = False
    pdf_vlm_model: str | None = None
    pdf_vlm_base_url: str | None = None
    pdf_vlm_api_key: SecretStr | None = None
    pdf_vlm_timeout_seconds: float = Field(default=60.0, gt=0.0, le=600.0)
    pdf_vlm_max_tokens: int = Field(default=512, ge=64, le=8_192)
    pdf_fusion_iou_threshold: float = Field(default=0.55, ge=0.0, le=1.0)
    pdf_fusion_text_similarity_threshold: float = Field(default=0.88, ge=0.0, le=1.0)
    pdf_fusion_table_text_overlap_threshold: float = Field(default=0.50, ge=0.0, le=1.0)
    pdf_page_parallel_enabled: bool = True
    pdf_page_workers: int = Field(default=4, ge=1, le=16)
    pdf_page_parallel_min_pages: int = Field(default=4, ge=2, le=10_000)
    rfp_lock_ttl_seconds: int = 300
    rfp_lock_acquire_timeout_seconds: float = 10.0
    redis_lock_watchdog_enabled: bool = True
    redis_lock_watchdog_interval_seconds: float = Field(default=30.0, gt=0.0, le=300.0)

    llm_api_key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "LLM_API_KEY",
            "ZAI_API_KEY",
            "OPENAI_API_KEY",
            "openai_api_key",
        ),
    )
    llm_base_url: str = Field(
        default="https://open.bigmodel.cn/api/paas/v4/",
        validation_alias=AliasChoices("LLM_BASE_URL", "OPENAI_BASE_URL", "openai_base_url"),
    )
    llm_model: str = Field(
        default="glm-5.3-flash",
        validation_alias=AliasChoices("LLM_MODEL", "OPENAI_MODEL", "openai_model"),
    )
    llm_timeout_seconds: float = Field(
        default=120.0,
        validation_alias=AliasChoices(
            "LLM_TIMEOUT_SECONDS",
            "OPENAI_TIMEOUT_SECONDS",
            "openai_timeout_seconds",
        ),
    )
    llm_temperature: float = 1.0
    llm_top_p: float = 0.95
    llm_reasoning_effort: str = "max"
    llm_max_retries: int = Field(default=2, ge=0, le=10)
    requirement_chunk_size_chars: int = 60_000
    requirement_max_chunks: int = 20
    requirement_max_output_tokens: int = 12_000
    requirement_lock_ttl_seconds: int = 1_800
    embedding_model: str = "embedding-3"
    embedding_dimensions: int = 1_024
    embedding_batch_size: int = 64
    knowledge_chunk_size_chars: int = 1_500
    knowledge_chunk_overlap_chars: int = 200
    knowledge_tokenizer_encoding: str = Field(default="cl100k_base", min_length=1, max_length=64)
    knowledge_parent_chunk_size_tokens: int = Field(default=1_200, ge=100)
    knowledge_child_chunk_size_tokens: int = Field(default=350, ge=50)
    knowledge_child_overlap_tokens: int = Field(default=40, ge=0)
    capability_max_output_tokens: int = 2_000
    capability_lock_ttl_seconds: int = 1_800
    capability_prompt_version: str = "capability-v1"
    capability_reranker_enabled: bool = False
    capability_reranker_model: str = "BAAI/bge-reranker-v2-m3"
    capability_reranker_device: Literal["auto", "cuda", "cpu"] = "auto"
    capability_reranker_batch_size: int = Field(default=4, ge=1, le=128)
    capability_reranker_query_max_tokens: int = Field(default=128, ge=16, le=2_048)
    capability_reranker_knowledge_max_tokens: int = Field(default=512, ge=64, le=8_192)
    capability_reranker_fallback_enabled: bool = True
    proposal_max_output_tokens: int = 12_000
    proposal_evidence_max_chars: int = 1_200
    proposal_lock_ttl_seconds: int = 1_800
    proposal_prompt_version: str = "proposal-v1"

    healthcheck_timeout_seconds: float = 5.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
