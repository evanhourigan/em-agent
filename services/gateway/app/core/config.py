from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, case_sensitive=False)

    env: str = "development"
    app_name: str = "EM Agent Gateway"
    app_version: str = "0.9.0"  # Read from VERSION file in production

    # CORS Configuration
    # In development: ["*"] is acceptable for convenience
    # In production: Set to specific origins like ["https://yourdomain.com", "https://app.yourdomain.com"]
    cors_allow_origins: list[str] = ["*"]
    cors_allow_credentials: bool = True
    cors_allow_methods: list[str] = ["*"]
    cors_allow_headers: list[str] = ["*"]
    cors_max_age: int = 600  # Cache preflight requests for 10 minutes

    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/postgres"
    rag_url: str = "http://rag:8000"
    slack_signing_secret: str | None = None
    slack_signing_required: bool = False
    slack_webhook_url: str | None = None
    slack_bot_token: str | None = None
    slack_default_channel: str | None = None

    # Tracing
    otel_enabled: bool = False
    otel_exporter_otlp_endpoint: str | None = None

    # Agent LLM (optional)
    agent_llm_enabled: bool = False
    openai_api_key: str | None = None
    openai_base_url: str | None = None
    openai_model: str = "gpt-4o-mini"

    # Safety limits
    rate_limit_per_min: int = 120  # Default rate limit (requests per minute)
    rate_limit_enabled: bool = True  # Enable/disable rate limiting
    max_payload_bytes: int = 1024 * 1024
    # Cost caps / quotas
    max_daily_slack_posts: int = 1000
    max_daily_rag_searches: int = 5000

    # OPA
    opa_url: str | None = None

    # Authentication
    jwt_secret_key: str | None = None
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 60  # 1 hour
    jwt_refresh_token_expire_days: int = 7  # 7 days
    auth_enabled: bool = False  # Feature flag to enable/disable auth

    # Integration Feature Flags (v0.5.0+)
    # Core integrations (already in production)
    integrations_github_enabled: bool = True
    integrations_jira_enabled: bool = True
    integrations_shortcut_enabled: bool = True
    integrations_linear_enabled: bool = True
    integrations_pagerduty_enabled: bool = True
    integrations_slack_enabled: bool = True

    # New integrations (default disabled for gradual rollout)
    integrations_github_actions_enabled: bool = True  # Enabled in v0.5.0
    integrations_datadog_enabled: bool = True  # Enabled in v0.6.0
    integrations_sentry_enabled: bool = True  # Enabled in v0.6.0
    integrations_circleci_enabled: bool = True  # Enabled in v0.7.0
    integrations_jenkins_enabled: bool = True  # Enabled in v0.7.0
    integrations_gitlab_enabled: bool = True  # Enabled in v0.7.0
    integrations_argocd_enabled: bool = True  # Enabled in v0.8.0
    integrations_kubernetes_enabled: bool = True  # Enabled in v0.8.0
    integrations_ecs_enabled: bool = True  # Enabled in v0.8.0
    integrations_heroku_enabled: bool = True  # Enabled in v0.8.0
    integrations_codecov_enabled: bool = True  # Enabled in v0.9.0
    integrations_sonarqube_enabled: bool = True  # Enabled in v0.9.0
    integrations_newrelic_enabled: bool = False
    integrations_prometheus_enabled: bool = False
    integrations_cloudwatch_enabled: bool = False


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def validate_settings(settings: Settings) -> None:
    """Basic runtime validation for reliability and secret hygiene."""
    # Database must be set
    if not (settings.database_url or "").strip():
        raise ValueError("DATABASE_URL is required")
    # Slack signing enforcement requires secret
    if (
        settings.slack_signing_required
        and not (settings.slack_signing_secret or "").strip()
    ):
        raise ValueError(
            "SLACK_SIGNING_REQUIRED=true but SLACK_SIGNING_SECRET is not set"
        )
    # JWT auth enabled requires secret key
    if settings.auth_enabled and not (settings.jwt_secret_key or "").strip():
        raise ValueError("AUTH_ENABLED=true but JWT_SECRET_KEY is not set")
    if settings.auth_enabled and len(settings.jwt_secret_key or "") < 32:
        raise ValueError("JWT_SECRET_KEY must be at least 32 characters for security")
    # OTel enabled should have endpoint
    if (
        settings.otel_enabled
        and not (settings.otel_exporter_otlp_endpoint or "").strip()
    ):
        # non-fatal, but warn via print to avoid logger import cycle
        print("[warn] OTEL_ENABLED=true but OTEL_EXPORTER_OTLP_ENDPOINT is not set")
    # RAG URL should be reachable format
    if not (settings.rag_url or "").startswith("http"):
        print(
            "[warn] RAG_URL does not look like an http URL; set to service URL if using RAG"
        )
    # CORS security check for production
    if (
        settings.env in ("production", "prod", "staging")
        and "*" in settings.cors_allow_origins
    ):
        print(
            "[SECURITY WARNING] CORS allows all origins (*) in production environment. "
            "Set CORS_ALLOW_ORIGINS to specific domains for security."
        )
