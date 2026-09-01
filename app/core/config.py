from functools import lru_cache

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
    kafka_rfp_worker_group: str = "dealflow-rfp-workers"
    kafka_requirement_worker_group: str = "dealflow-requirement-workers"
    kafka_capability_worker_group: str = "dealflow-capability-workers"
    kafka_proposal_worker_group: str = "dealflow-proposal-workers"
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "dealflow_knowledge_glm"
    qdrant_search_top_k: int = 5
    qdrant_score_threshold: float | None = 0.25

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

    max_rfp_upload_size_bytes: int = 50 * 1024 * 1024
    rfp_lock_ttl_seconds: int = 300
    rfp_lock_acquire_timeout_seconds: float = 10.0

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
    capability_max_output_tokens: int = 2_000
    capability_lock_ttl_seconds: int = 1_800
    capability_prompt_version: str = "capability-v1"
    proposal_max_output_tokens: int = 12_000
    proposal_evidence_max_chars: int = 1_200
    proposal_lock_ttl_seconds: int = 1_800
    proposal_prompt_version: str = "proposal-v1"

    healthcheck_timeout_seconds: float = 5.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
