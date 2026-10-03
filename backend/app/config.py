from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    #every value can be overridden from the environment (see .env.example)
    model_config = SettingsConfigDict(extra="ignore")

    app_name: str = "Resolvr"
    environment: str = "dev"
    log_level: str = "INFO"
    app_timezone: str = "Asia/Kolkata"
    frontend_url: str = "http://localhost:5174"
    cors_origins: str = "http://localhost:5174"

    database_url: str = "postgresql+psycopg2://resolvr:resolvr@db:5432/resolvr"
    redis_url: str = "redis://redis:6379/0"

    jwt_secret: str = "dev-only-secret-please-override-in-env"
    jwt_expire_minutes: int = 600

    #llm
    llm_provider: str = "gemini"
    google_api_key: str = ""
    #drafting + chat
    gemini_model_name: str = "gemini-3.8-flash"
    #cheaper model for classification and the eval judge, empty means use the main one
    gemini_fast_model_name: str = "gemini-3.5-flash-lite"
    llm_timeout_seconds: int = 60
    llm_max_retries: int = 2
    #usd per 1M tokens, only used for cost estimates on the dashboard
    llm_input_cost_per_1m: float = 0.75
    llm_output_cost_per_1m: float = 3.75
    #gap between rows in batch jobs / evals so we stay under the free tier requests-per-minute limit
    llm_min_interval_ms: int = 6000

    #embeddings + retrieval
    embedding_model: str = "BAAI/bge-base-en-v1.5"
    embedding_dim: int = 768
    reranker_enabled: bool = True
    reranker_model: str = "BAAI/bge-reranker-base"
    #the laptop cpu has 4 performance cores, 8 threads was faster than using all 18
    torch_threads: int = 8
    retrieval_candidates: int = 10
    retrieval_top_k: int = 6
    #floor on the best cosine similarity, below it nothing in the history is close enough to use
    #(calibrated on the eval set: in-scope complaints never went under ~0.64 with bge-base)
    abstain_threshold: float = 0.55

    #comma separated list of severities that need an admin to sign off
    approval_severities: str = "critical"
    review_sla_minutes: int = 30

    #outage detector
    outage_window_minutes: int = 60
    outage_min_count: int = 4
    outage_similarity: float = 0.80

    #notifications
    ntfy_base_url: str = "https://ntfy.sh"
    ntfy_admin_topic: str = ""
    ntfy_agent_topic: str = ""
    ntfy_token: str = ""

    smtp_host: str = "mailpit"
    smtp_port: int = 1025
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from: str = "Resolvr <reports@resolvr.local>"
    smtp_use_tls: bool = False
    admin_emails: str = ""

    #daily digest (local time in app_timezone)
    digest_hour: int = 21
    digest_minute: int = 0

    #limits
    max_complaint_chars: int = 4000
    max_csv_rows: int = 200
    max_upload_mb: int = 2
    rate_limit_analyze_per_min: int = 20
    rate_limit_chat_per_min: int = 30
    rate_limit_batch_per_min: int = 3
    rate_limit_default_per_min: int = 240

    webhook_secret: str = ""
    seed_user_password: str = "resolvr123"
    auto_seed: bool = True

    @property
    def approval_severity_list(self) -> list[str]:
        return [s.strip() for s in self.approval_severities.split(",") if s.strip()]

    @property
    def admin_email_list(self) -> list[str]:
        return [e.strip() for e in self.admin_emails.split(",") if e.strip()]

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
