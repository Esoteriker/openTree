from __future__ import annotations

import json
import os


def _read_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _read_json_dict(name: str) -> dict[str, str]:
    raw = os.getenv(name, "").strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    if not isinstance(parsed, dict):
        return {}
    return {str(k): str(v) for k, v in parsed.items()}


class Settings:
    parser_service_url: str = os.getenv("PARSER_SERVICE_URL", "http://127.0.0.1:8102")
    graph_service_url: str = os.getenv("GRAPH_SERVICE_URL", "http://127.0.0.1:8103")
    suggestion_service_url: str = os.getenv("SUGGESTION_SERVICE_URL", "http://127.0.0.1:8104")

    default_tenant_id: str = os.getenv("DEFAULT_TENANT_ID", "public")
    auth_required: bool = _read_bool("AUTH_REQUIRED", default=False)
    auth_mode: str = os.getenv("AUTH_MODE", "none")
    tenant_api_keys: dict[str, str] = _read_json_dict("TENANT_API_KEYS_JSON")
    jwt_secret: str = os.getenv("JWT_SECRET", "dev-only-secret-change-me")
    jwt_algorithm: str = os.getenv("JWT_ALGORITHM", "HS256")
    jwt_audience: str | None = os.getenv("JWT_AUDIENCE")
    jwt_issuer: str | None = os.getenv("JWT_ISSUER")

    content_encryption_key: str | None = os.getenv("CONTENT_ENCRYPTION_KEY")

    parser_backend: str = os.getenv("PARSER_BACKEND", "transformer")
    transformer_inference_url: str | None = os.getenv("TRANSFORMER_INFERENCE_URL")
    transformer_timeout_seconds: float = float(os.getenv("TRANSFORMER_TIMEOUT_SECONDS", "5.0"))

    graph_backend: str = os.getenv("GRAPH_BACKEND", "memory")
    neo4j_uri: str = os.getenv("NEO4J_URI", "bolt://127.0.0.1:7687")
    neo4j_username: str = os.getenv("NEO4J_USERNAME", "neo4j")
    neo4j_password: str = os.getenv("NEO4J_PASSWORD", "password")
    elasticsearch_url: str = os.getenv("ELASTICSEARCH_URL", "http://127.0.0.1:9200")
    elasticsearch_index_name: str = os.getenv("ELASTICSEARCH_INDEX_NAME", "opentree-evidence")

    event_bus_backend: str = os.getenv("EVENT_BUS_BACKEND", "inmemory")
    event_bus_consumer_group: str = os.getenv("EVENT_BUS_CONSUMER_GROUP", "dialogue-service")
    redis_url: str = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")
    redis_stream_prefix: str = os.getenv("REDIS_STREAM_PREFIX", "opentree")
    async_pipeline_enabled: bool = _read_bool("ASYNC_PIPELINE_ENABLED", default=False)
    async_retry_max_attempts: int = int(os.getenv("ASYNC_RETRY_MAX_ATTEMPTS", "3"))
    async_retry_base_delay_seconds: float = float(os.getenv("ASYNC_RETRY_BASE_DELAY_SECONDS", "0.25"))
    async_job_ttl_seconds: int = int(os.getenv("ASYNC_JOB_TTL_SECONDS", "86400"))

    session_store_backend: str = os.getenv("SESSION_STORE_BACKEND", "memory")
    job_store_backend: str = os.getenv("JOB_STORE_BACKEND", "memory")
    postgres_dsn: str = os.getenv(
        "POSTGRES_DSN",
        "dbname=opentree user=opentree password=opentree host=127.0.0.1 port=5432",
    )


settings = Settings()
