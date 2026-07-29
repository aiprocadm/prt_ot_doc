from __future__ import annotations

import json
import logging
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from shutil import which
from typing import Annotated, Final, Literal

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from pydantic import (
    AliasChoices,
    BeforeValidator,
    Field,
    PrivateAttr,
    ValidationInfo,
    field_validator,
    model_validator,
)
from pydantic.fields import FieldInfo
from pydantic_core import PydanticUndefined, PydanticUndefinedType
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic_settings import sources as settings_sources

from app.core.i18n import configure_runtime_locale

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RuntimeConfig:
    """Runtime mode toggles for different environments."""

    environment: Literal["development", "staging", "production", "test"]
    debug: bool

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def is_development(self) -> bool:
        return self.environment == "development"


@dataclass(frozen=True)
class ApplicationConfig:
    """Top-level application toggles and HTTP metadata."""

    name: str
    environment: Literal["development", "staging", "production", "test"]
    debug: bool
    secret_key: str
    api_prefix: str
    api_v1_prefix: str
    allowed_hosts: list[str]
    allowed_origins: list[str]
    default_locale: str
    default_timezone: str

    @property
    def runtime(self) -> RuntimeConfig:
        return RuntimeConfig(environment=self.environment, debug=self.debug)


@dataclass(frozen=True)
class DatabaseConfig:
    """Database connection parameters for SQLAlchemy and Alembic."""

    url: str
    alembic_url: str
    echo: bool
    host: str
    port: int
    name: str
    user: str
    password: str


@dataclass(frozen=True)
class BrokerConfig:
    """Message broker endpoints for Celery and rate limiting."""

    broker_url: str
    result_url: str
    rate_limit_storage_uri: str

    @property
    def has_dedicated_result_backend(self) -> bool:
        return self.result_url != self.broker_url


@dataclass(frozen=True)
class CeleryConfig:
    """Celery queues and execution limits."""

    worker_queues: list[str]
    pdf_queue: str
    task_soft_time_limit: int
    task_time_limit: int
    task_max_retries: int
    retry_backoff_seconds: int
    retry_backoff_max_seconds: int


@dataclass(frozen=True)
class LoggingConfig:
    """Logging format toggles."""

    level: str
    json_enabled: bool


def _generate_dev_keypair() -> tuple[str, str]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")
    public_pem = (
        key.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode("utf-8")
    )
    return private_pem, public_pem


DEV_PRIVATE_KEY, DEV_PUBLIC_KEY = _generate_dev_keypair()


JSON_MAX_DEFAULT: Final[int] = 1_048_576
MAX_UPLOAD_SIZE_DEFAULT: Final[int] = 20_971_520
DEFAULT_ALLOWED_HOSTS: Final[list[str]] = ["localhost", "127.0.0.1", "::1", "testserver"]
DEFAULT_ALLOWED_ORIGINS: Final[list[str]] = [
    "http://localhost",
    "http://localhost:5173",
    "http://localhost:8080",
    "http://127.0.0.1",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:8080",
]

DEFAULT_ALLOWED_FILE_MIME: Final[list[str]] = [
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/plain",
    "image/png",
    "image/jpeg",
]

DEFAULT_ALLOWED_FILE_EXTENSIONS: Final[list[str]] = [
    "pdf",
    "doc",
    "docx",
    "txt",
    "png",
    "jpg",
    "jpeg",
]


def _parse_file_allowed_mime(value: object) -> list[str]:
    items = split_csv(value, default=DEFAULT_ALLOWED_FILE_MIME)  # type: ignore[arg-type]
    normalized: list[str] = []
    for item in items:
        candidate = str(item).strip().lower()
        if not candidate:
            continue
        if candidate not in normalized:
            normalized.append(candidate)
    return normalized or list(DEFAULT_ALLOWED_FILE_MIME)


def _parse_file_allowed_extensions(value: object) -> list[str]:
    items = split_csv(value, default=DEFAULT_ALLOWED_FILE_EXTENSIONS)  # type: ignore[arg-type]
    normalized: list[str] = []
    for item in items:
        candidate = str(item).strip().lower().lstrip(".")
        if not candidate:
            continue
        if not candidate.isascii():
            continue
        canonical = {"jpeg": "jpg"}.get(candidate, candidate)
        if canonical not in normalized:
            normalized.append(canonical)
    return normalized or list(DEFAULT_ALLOWED_FILE_EXTENSIONS)


CsvMimeList = Annotated[list[str], BeforeValidator(_parse_file_allowed_mime)]
CsvExtensionList = Annotated[list[str], BeforeValidator(_parse_file_allowed_extensions)]
CsvUrlList = Annotated[list[str], BeforeValidator(lambda value: split_csv(value, default=()))]


def _tolerant_json_loads(value: str, *args, **kwargs) -> object:
    """Parse JSON values while tolerating plain strings."""

    try:
        return json.loads(value, *args, **kwargs)
    except (json.JSONDecodeError, TypeError):  # pragma: no cover - defensive fallback
        if args or kwargs:
            raise
        return value


def _decode_complex_value_with_fallback(
    self: settings_sources.PydanticBaseSettingsSource,
    field_name: str,
    field: FieldInfo,
    value: object,
) -> object:
    if isinstance(value, (str, bytes, bytearray)):
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return value
    return value


# NOTE: patching pydantic-settings is brittle across upgrades; prefer a custom
# SettingsSource when bumping pydantic-settings major versions.
settings_sources.PydanticBaseSettingsSource.decode_complex_value = (  # type: ignore[method-assign]
    _decode_complex_value_with_fallback
)


class SettingsError(RuntimeError):
    """Raised when critical configuration is missing."""


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        populate_by_name=True,
        extra="ignore",
    )

    _application: ApplicationConfig | None = PrivateAttr(default=None)
    _runtime: RuntimeConfig | None = PrivateAttr(default=None)
    _database: DatabaseConfig | None = PrivateAttr(default=None)
    _broker: BrokerConfig | None = PrivateAttr(default=None)
    _celery: CeleryConfig | None = PrivateAttr(default=None)
    _logging: LoggingConfig | None = PrivateAttr(default=None)

    app_name: str = Field("prt-ot-doc", alias="APP_NAME")
    app_env: Literal["development", "staging", "production", "test"] = Field(
        "development", alias="APP_ENV"
    )
    app_run_mode: Literal["docker", "dockerless"] = Field("docker", alias="APP_RUN_MODE")
    debug: bool = Field(False, alias="APP_DEBUG")
    audit_enabled: bool = Field(True, alias="AUDIT_ENABLED")

    api_prefix: str = Field("/api", alias="API_PREFIX")
    api_v1_prefix: str = Field("/api/v1", alias="API_V1_PREFIX")

    allowed_hosts: list[str] = Field(
        default_factory=lambda: list(DEFAULT_ALLOWED_HOSTS),
        alias="APP_TRUSTED_HOSTS",
        validation_alias=AliasChoices("APP_TRUSTED_HOSTS", "ALLOWED_HOSTS"),
    )
    allowed_origins: list[str] = Field(
        default_factory=lambda: list(DEFAULT_ALLOWED_ORIGINS),
        alias="APP_CORS_ORIGINS",
        validation_alias=AliasChoices("APP_CORS_ORIGINS", "ALLOWED_ORIGINS"),
    )
    cors_allow_credentials: bool = Field(True, alias="APP_CORS_ALLOW_CREDENTIALS")

    database_url_env: str | None = Field(default=None, alias="DATABASE_URL")
    # SEC-65: Alembic needs the owner role (ENABLE/FORCE ROW LEVEL SECURITY is an
    # owner-only DDL), while the runtime must connect as a NOSUPERUSER
    # NOBYPASSRLS role or the policies are inert. Keep them separable.
    migration_database_url_env: str | None = Field(default=None, alias="MIGRATION_DATABASE_URL")
    rls_require_unprivileged_db_role_env: bool | None = Field(
        default=None, alias="RLS_REQUIRE_UNPRIVILEGED_DB_ROLE"
    )
    postgres_host: str = Field("postgres", alias="POSTGRES_HOST")
    postgres_port: int = Field(5432, alias="POSTGRES_PORT")
    postgres_db: str = Field("documents", alias="POSTGRES_DB")
    postgres_user: str = Field("app", alias="POSTGRES_USER")
    postgres_password: str = Field("change_me", alias="POSTGRES_PASSWORD")
    database_echo: bool = Field(False, alias="DATABASE_ECHO")
    default_tenant_slug: str = Field("public", alias="DEFAULT_TENANT_SLUG")
    shared_schema: str = Field("public", alias="SHARED_SCHEMA")
    runtime_schema_bootstrap: bool = Field(False, alias="RUNTIME_SCHEMA_BOOTSTRAP")

    storage_backend: Literal["local", "s3", "memory"] = Field("memory", alias="STORAGE_BACKEND")
    storage_root: str = Field("./.local_storage", alias="STORAGE_ROOT")
    s3_backend: Literal["memory", "minio", "local"] = Field("memory", alias="S3_BACKEND")
    s3_endpoint: str = Field("http://minio:9000", alias="S3_ENDPOINT")
    s3_bucket: str = Field("documents", alias="S3_BUCKET")
    s3_access_key: str = Field("prt_local_access", alias="S3_ACCESS_KEY")
    s3_secret_key: str = Field("prt_local_secret", alias="S3_SECRET_KEY")
    s3_secure: bool = Field(False, alias="S3_SECURE")
    presign_download_ttl_seconds: int = Field(
        900,
        alias="PRESIGN_DOWNLOAD_TTL_SECONDS",
        ge=60,
        le=3600,
    )

    secret_key: str = Field("change-me", alias="SECRET_KEY")
    portal_token_salt: str = Field("portal-salt", alias="PORTAL_TOKEN_SALT")

    admin_bootstrap: bool = Field(False, alias="ADMIN_BOOTSTRAP")
    admin_email: str = Field("admin@example.com", alias="ADMIN_EMAIL")
    admin_password: str = Field("", alias="ADMIN_PASSWORD")
    admin_tenant: str = Field("public", alias="ADMIN_TENANT")
    # Managing ("platform") tenant: the only tenant whose admins may provision, suspend
    # and re-quota other tenants. Empty -> falls back to ``admin_tenant``.
    platform_tenant_slug: str = Field("", alias="PLATFORM_TENANT_SLUG")
    webhook_notification_url: str | None = Field(None, alias="WEBHOOK_NOTIFICATION_URL")
    # RC-011 notification delivery (feature-flagged; default OFF -> no external send).
    notifications_delivery_enabled: bool = Field(
        False, alias="NOTIFICATIONS_DELIVERY_ENABLED"
    )
    notifications_max_delivery_attempts: int = Field(
        3, alias="NOTIFICATIONS_MAX_DELIVERY_ATTEMPTS"
    )
    smtp_host: str = Field("", alias="SMTP_HOST")
    smtp_port: int = Field(587, alias="SMTP_PORT")
    smtp_username: str = Field("", alias="SMTP_USERNAME")
    smtp_password: str = Field("", alias="SMTP_PASSWORD")
    smtp_from: str = Field("", alias="SMTP_FROM")
    smtp_use_tls: bool = Field(True, alias="SMTP_USE_TLS")
    telegram_bot_token: str = Field("", alias="TELEGRAM_BOT_TOKEN")
    demo_bootstrap: bool = Field(False, alias="DEMO_BOOTSTRAP")
    demo_tenant_id: str = Field("demo", alias="DEMO_TENANT_ID")
    demo_company_name: str = Field("ООО Демо Строй", alias="DEMO_COMPANY_NAME")
    demo_site_name: str = Field("Площадка Север", alias="DEMO_SITE_NAME")
    jwt_issuer: str = Field("prt-ot-doc", alias="JWT_ISSUER")
    jwt_audience: str = Field("prt-ot-doc-clients", alias="JWT_AUDIENCE")
    jwt_algorithm: str = Field("RS256", alias="JWT_ALG")
    jwt_access_ttl_minutes: int = Field(30, alias="JWT_ACCESS_TTL_MIN")
    jwt_refresh_ttl_days: int = Field(7, alias="JWT_REFRESH_TTL_D")
    jwt_private_key_pem: str = Field("", alias="PRIVATE_KEY_PEM")
    jwt_public_key_pem: str = Field("", alias="PUBLIC_KEY_PEM")

    libreoffice_bin: str = Field("soffice", alias="LIBREOFFICE_BIN")
    pdf_fallback: Literal["auto", "always", "never"] = Field("auto", alias="PDF_FALLBACK_MODE")
    pdf_libreoffice_timeout_seconds: int = Field(120, alias="PDF_LIBREOFFICE_TIMEOUT_SECONDS")
    pdf_libreoffice_max_attempts: int = Field(4, alias="PDF_LIBREOFFICE_MAX_ATTEMPTS")
    pdf_libreoffice_retry_backoff_seconds: float = Field(
        1.0, alias="PDF_LIBREOFFICE_RETRY_BACKOFF_SECONDS"
    )
    pdf_libreoffice_retry_backoff_max_seconds: float = Field(
        30.0, alias="PDF_LIBREOFFICE_RETRY_BACKOFF_MAX_SECONDS"
    )
    pdf_worker_queue: str = Field("pdf", alias="PDF_WORKER_QUEUE")
    pdf_worker_concurrency: int = Field(2, alias="PDF_WORKER_CONCURRENCY")
    doc_pipeline_enable_qr: bool = Field(False, alias="DOC_PIPELINE_ENABLE_QR")
    doc_pipeline_enable_watermark: bool = Field(False, alias="DOC_PIPELINE_ENABLE_WATERMARK")
    doc_pipeline_letterhead_auto: bool = Field(False, alias="DOC_PIPELINE_LETTERHEAD_AUTO")
    doc_pipeline_watermark_text: str = Field("CONFIDENTIAL", alias="DOC_PIPELINE_WATERMARK_TEXT")

    redis_url: str = Field("redis://localhost:6379/0", alias="REDIS_URL")
    redis_result_url_env: str | None = Field(None, alias="REDIS_RESULT_URL")
    worker_queues: list[str] = Field(default_factory=lambda: ["default"], alias="WORKER_QUEUES")
    celery_task_soft_time_limit: int = Field(300, alias="CELERY_TASK_SOFT_TIME_LIMIT")
    celery_task_time_limit: int = Field(600, alias="CELERY_TASK_TIME_LIMIT")
    # SEC-64 (разд. 64.2 «изоляция обработки ... с ограничением ресурсов»):
    # предел по времени уже был, предела по ПАМЯТИ не было. Патологический документ
    # или конвертация LibreOffice раздувают RSS в пределах отведённых 300 секунд и
    # роняют хост по OOM — вместе с соседними контейнерами. Celery перезапускает
    # дочерний процесс, превысивший порог, ПОСЛЕ завершения текущей задачи.
    celery_worker_max_memory_mb: int = Field(1024, alias="CELERY_WORKER_MAX_MEMORY_MB")
    celery_worker_max_tasks_per_child: int = Field(
        100, alias="CELERY_WORKER_MAX_TASKS_PER_CHILD"
    )
    celery_task_max_retries: int = Field(5, alias="CELERY_TASK_MAX_RETRIES")
    celery_retry_backoff_seconds: int = Field(5, alias="CELERY_RETRY_BACKOFF_SECONDS")
    celery_retry_backoff_max_seconds: int = Field(300, alias="CELERY_RETRY_BACKOFF_MAX_SECONDS")
    celery_eager: bool = Field(False, alias="CELERY_EAGER")
    outbox_poll_interval: float = Field(5.0, alias="OUTBOX_POLL_INTERVAL")
    outbox_in_progress_timeout_seconds: float = Field(
        900.0,
        alias="OUTBOX_IN_PROGRESS_TIMEOUT_SECONDS",
    )
    outbox_max_attempts: int = Field(10, alias="OUTBOX_MAX_ATTEMPTS")
    outbox_retry_backoff_seconds: float = Field(5.0, alias="OUTBOX_RETRY_BACKOFF_SECONDS")
    outbox_retry_backoff_max_seconds: float = Field(600.0, alias="OUTBOX_RETRY_BACKOFF_MAX_SECONDS")
    # Default OFF on purpose: until now nothing scheduled an outbox drain, so an
    # existing deployment may hold a large backlog. Enabling the beat entry would
    # flush all of it to subscriber endpoints on the first tick.
    outbox_dispatch_schedule_enabled: bool = Field(
        False, alias="OUTBOX_DISPATCH_SCHEDULE_ENABLED"
    )
    outbox_dispatch_schedule_minutes: int = Field(5, alias="OUTBOX_DISPATCH_SCHEDULE_MINUTES")
    webhook_document_created_urls: CsvUrlList = Field(
        default_factory=list, alias="WEBHOOK_URLS_DOCUMENT_CREATED"
    )
    webhook_document_generated_urls: CsvUrlList = Field(
        default_factory=list, alias="WEBHOOK_URLS_DOCUMENT_GENERATED"
    )
    webhook_document_signed_urls: CsvUrlList = Field(
        default_factory=list, alias="WEBHOOK_URLS_DOCUMENT_SIGNED"
    )
    webhook_signed_urls: CsvUrlList = Field(default_factory=list, alias="WEBHOOK_URLS_SIGNED")
    webhook_document_exported_urls: CsvUrlList = Field(
        default_factory=list, alias="WEBHOOK_URLS_DOCUMENT_EXPORTED"
    )
    webhook_exported_urls: CsvUrlList = Field(default_factory=list, alias="WEBHOOK_URLS_EXPORTED")
    webhook_risk_assessed_urls: CsvUrlList = Field(
        default_factory=list, alias="WEBHOOK_URLS_RISK_ASSESSED"
    )
    webhook_ppe_issued_urls: CsvUrlList = Field(
        default_factory=list, alias="WEBHOOK_URLS_PPE_ISSUED"
    )
    webhook_ppe_returned_urls: CsvUrlList = Field(
        default_factory=list, alias="WEBHOOK_URLS_PPE_RETURNED"
    )
    webhook_training_completed_urls: CsvUrlList = Field(
        default_factory=list, alias="WEBHOOK_URLS_TRAINING_COMPLETED"
    )
    webhook_training_assigned_urls: CsvUrlList = Field(
        default_factory=list, alias="WEBHOOK_URLS_TRAINING_ASSIGNED"
    )
    webhook_timeout_seconds: float = Field(10.0, alias="WEBHOOK_TIMEOUT_SECONDS")
    # SEC-67: master key (base64/hex, 32 bytes) for encrypting webhook HMAC secrets at
    # rest (AES-256-GCM, core/secret_cipher.py). Required in production/staging; in
    # development/test a deterministic key is derived from SECRET_KEY.
    secret_encryption_key: str = Field("", alias="APP_SECRET_ENCRYPTION_KEY")
    # SEC-67: связка ключей для ротации без простоя — пары ``kid:key`` через запятую.
    # Старый одиночный APP_SECRET_ENCRYPTION_KEY продолжает работать под kid "v1".
    secret_encryption_keys: str = Field("", alias="APP_SECRET_ENCRYPTION_KEYS")
    secret_encryption_active_kid: str = Field("", alias="APP_SECRET_ENCRYPTION_ACTIVE_KID")
    # SEC-64 §64.3: guard outbound webhooks against SSRF (internal/private targets).
    # Default on; operator kill-switch. Enforcement is environment-aware (strict in
    # production/staging, permissive in development/test) — see core/ssrf_guard.py.
    webhook_ssrf_guard_enabled: bool = Field(True, alias="WEBHOOK_SSRF_GUARD_ENABLED")
    inbound_webhook_hmac_secret: str = Field("", alias="INBOUND_WEBHOOK_HMAC_SECRET")
    log_level: str = Field("INFO", alias="LOG_LEVEL")
    log_json: bool = Field(True, alias="LOG_JSON")

    @classmethod
    def model_validate(cls, obj: object, **kwargs) -> "Settings":  # noqa: PYI034
        if isinstance(obj, dict):
            data = dict(obj)
            data.setdefault("APP_ENV", cls.model_fields["app_env"].default)
            return super().model_validate(data, **kwargs)
        return super().model_validate(obj, **kwargs)

    rate_limit_enabled: bool = Field(True, alias="RATE_LIMIT_ENABLED")
    rate_limit_storage_uri: str = Field("memory://", alias="RATE_LIMIT_STORAGE_URI")
    rate_limit_login_per_identity: str = Field("5/minute", alias="RATE_LIMIT_LOGIN_PER_IDENTITY")
    rate_limit_upload_per_tenant: str = Field("10/minute", alias="RATE_LIMIT_UPLOAD_PER_TENANT")
    rate_limit_generate_per_tenant: str = Field("20/minute", alias="RATE_LIMIT_GENERATE_PER_TENANT")
    # SEC-68: внешний контур жёстче внутреннего (разд. 68.2). Счётчик неудачных
    # попыток отдельный и гораздо строже: успешные запросы его не тратят, поэтому
    # низкий порог ловит перебор, не мешая легитимному клиенту.
    portal_rate_limit_per_ip: str = Field("60/minute", alias="PORTAL_RATE_LIMIT_PER_IP")
    portal_auth_failures_per_ip: str = Field("10/hour", alias="PORTAL_AUTH_FAILURES_PER_IP")
    # Срок жизни magic link. Потолок не даёт выдать «вечную» ссылку (разд. 68.1).
    portal_token_ttl_hours: int = Field(24, alias="PORTAL_TOKEN_TTL_HOURS")
    portal_token_max_ttl_hours: int = Field(168, alias="PORTAL_TOKEN_MAX_TTL_HOURS")
    # SEC-64 (разд. 64.2): пороги безопасного вскрытия загруженных офисных архивов.
    # Абсолютные лимиты — основной рубеж против zip-бомб; отношение сжатия
    # намеренно высокое, XML легитимно сжимается в десятки раз.
    archive_max_entries: int = Field(2000, alias="ARCHIVE_MAX_ENTRIES")
    archive_max_uncompressed_bytes: int = Field(
        209_715_200, alias="ARCHIVE_MAX_UNCOMPRESSED_BYTES"
    )
    archive_max_entry_bytes: int = Field(104_857_600, alias="ARCHIVE_MAX_ENTRY_BYTES")
    archive_max_compression_ratio: float = Field(500.0, alias="ARCHIVE_MAX_COMPRESSION_RATIO")
    # SEC-64 (разд. 64.1): заголовки безопасности на уровне приложения.
    # CSP пустой = строгая политика по умолчанию (default-src 'none' для JSON-API).
    security_headers_enabled: bool = Field(True, alias="SECURITY_HEADERS_ENABLED")
    security_csp: str = Field("", alias="SECURITY_CSP")
    # HSTS шлём только в production/staging: за TLS-терминирующим прокси приложение
    # видит http, и заголовок из dev-запуска закрепил бы https-редирект на localhost.
    security_hsts_max_age: int = Field(31_536_000, alias="SECURITY_HSTS_MAX_AGE")

    use_1c_integration: bool = Field(False, alias="USE_1C_INTEGRATION")
    use_edo_integration: bool = Field(False, alias="USE_EDO_INTEGRATION")
    use_frdo_integration: bool = Field(False, alias="USE_FRDO_INTEGRATION")
    use_eisot_integration: bool = Field(False, alias="USE_EISOT_INTEGRATION")

    edo_integration_base_url: str | None = Field(None, alias="EDO_INTEGRATION_BASE_URL")
    edo_integration_api_token: str | None = Field(None, alias="EDO_INTEGRATION_API_TOKEN")
    edo_integration_timeout_seconds: float = Field(30.0, alias="EDO_INTEGRATION_TIMEOUT_SECONDS")
    edo_integration_outbound_path: str = Field(
        "/v1/outbound/documents",
        alias="EDO_INTEGRATION_OUTBOUND_PATH",
    )

    json_max_bytes: int = Field(JSON_MAX_DEFAULT, alias="JSON_MAX")
    max_upload_size: int = Field(
        MAX_UPLOAD_SIZE_DEFAULT,
        alias="MAX_UPLOAD_SIZE",
        validation_alias=AliasChoices("MAX_UPLOAD_SIZE", "MAX_UPLOAD_BYTES"),
    )
    document_payload_max_bytes: int = Field(
        JSON_MAX_DEFAULT,
        alias="DOCUMENT_PAYLOAD_MAX_BYTES",
    )
    document_batch_max_rows: int = Field(500, alias="DOCUMENT_BATCH_MAX_ROWS")
    idempotency_ttl_days: int = Field(30, alias="IDEMPOTENCY_TTL_DAYS")
    file_allowed_mime: CsvMimeList = Field(
        default_factory=lambda: list(DEFAULT_ALLOWED_FILE_MIME),
        alias="FILE_ALLOWED_MIME",
    )
    file_allowed_extensions: CsvExtensionList = Field(
        default_factory=lambda: list(DEFAULT_ALLOWED_FILE_EXTENSIONS),
        alias="FILE_ALLOWED_EXTENSIONS",
    )

    clamav_queue_url: str = Field("memory://", alias="CLAMAV_QUEUE_URL")
    clamav_quarantine_queue: str = Field("clamav.quarantine", alias="CLAMAV_QUARANTINE_QUEUE")
    clamav_scan_queue: str = Field("clamav.scan", alias="CLAMAV_SCAN_QUEUE")
    # SEC-64 (разд. 64.2): «ClamAV в upload pipeline — обязательный gate, а не опция».
    # false = сканирование симулируется по имени файла (только dev/test); в
    # production/staging выключенный антивирус ловит scripts/ci/check_av_gate.py.
    av_enabled: bool = Field(False, alias="AV_ENABLED")
    clamav_host: str = Field("clamav", alias="CLAMAV_HOST")
    clamav_port: int = Field(3310, alias="CLAMAV_PORT")
    clamav_timeout: float = Field(30.0, alias="CLAMAV_TIMEOUT")
    clamav_unix_socket: str | None = Field(None, alias="CLAMAV_UNIX_SOCKET")

    enable_metrics: bool = Field(True, alias="ENABLE_METRICS")
    enable_openapi_docs: bool = Field(True, alias="ENABLE_OPENAPI_DOCS")
    enable_gzip: bool = Field(True, alias="ENABLE_GZIP")
    enable_files_legacy_routes: bool = Field(True, alias="ENABLE_FILES_LEGACY_ROUTES")
    health_check_comprehensive_enabled: bool = Field(
        False, alias="HEALTH_CHECK_COMPREHENSIVE_ENABLED"
    )
    health_check_cache_ttl_seconds: int = Field(60, alias="HEALTH_CHECK_CACHE_TTL_SECONDS")
    health_check_timeout_per_check_seconds: float = Field(
        5.0, alias="HEALTH_CHECK_TIMEOUT_PER_CHECK_SECONDS"
    )
    max_request_body_bytes: int = Field(1_048_576, alias="MAX_REQUEST_BODY_BYTES")
    request_timeout_seconds: float = Field(15.0, alias="REQUEST_TIMEOUT_SECONDS")
    trace_header_name: str = Field("X-Correlation-Id", alias="TRACE_HEADER_NAME")
    default_locale: str = Field("ru-RU", alias="DEFAULT_LOCALE")
    default_timezone: str = Field("Europe/Moscow", alias="DEFAULT_TIMEZONE")

    @field_validator(
        "migration_database_url_env", "rls_require_unprivileged_db_role_env", mode="before"
    )
    @classmethod
    def _blank_to_none(cls, value: object) -> object:
        """Treat an empty env var as "unset" (``.env.example`` ships both keys blank)."""

        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("allowed_hosts", "allowed_origins", "worker_queues", mode="before")
    @classmethod
    def _coerce_sequence(
        cls,
        value: str | Sequence[str] | PydanticUndefinedType | None,
        info: ValidationInfo,
    ) -> list[str]:
        defaults = {
            "allowed_hosts": list(DEFAULT_ALLOWED_HOSTS),
            "allowed_origins": list(DEFAULT_ALLOWED_ORIGINS),
            "worker_queues": ["default"],
        }

        default = defaults.get(info.field_name or "", [])
        return split_csv(value, default=default)

    @field_validator("libreoffice_bin")
    @classmethod
    def _validate_libreoffice_bin(cls, value: str) -> str:
        candidate = value.strip()
        if not candidate:
            raise ValueError("LIBREOFFICE_BIN cannot be empty")

        if not binary_exists(candidate):
            logger.warning(
                "LibreOffice binary '%s' not found in PATH or at provided location", candidate
            )

        return candidate

    @field_validator("default_tenant_slug")
    @classmethod
    def _validate_default_tenant_slug(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not normalized:
            msg = "DEFAULT_TENANT_SLUG must not be empty"
            raise ValueError(msg)
        allowed = set("abcdefghijklmnopqrstuvwxyz0123456789-_")
        if any(ch not in allowed for ch in normalized):
            msg = "DEFAULT_TENANT_SLUG contains invalid characters"
            raise ValueError(msg)
        return normalized

    @field_validator("shared_schema")
    @classmethod
    def _validate_shared_schema(cls, value: str) -> str:
        candidate = value.strip()
        if not candidate:
            msg = "SHARED_SCHEMA must not be empty"
            raise ValueError(msg)
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", candidate):
            msg = (
                "SHARED_SCHEMA must start with a letter or underscore "
                "and contain only alphanumerics or underscores"
            )
            raise ValueError(msg)
        return candidate

    @field_validator(
        "json_max_bytes",
        "max_upload_size",
        "celery_task_soft_time_limit",
        "celery_task_time_limit",
        "celery_task_max_retries",
        "celery_retry_backoff_seconds",
        "celery_retry_backoff_max_seconds",
        "pdf_libreoffice_timeout_seconds",
        "pdf_libreoffice_max_attempts",
        "pdf_worker_concurrency",
        "document_payload_max_bytes",
        "document_batch_max_rows",
        "idempotency_ttl_days",
    )
    @classmethod
    def _validate_positive_sizes(cls, value: int, info: ValidationInfo) -> int:
        if value <= 0:
            raise ValueError(f"{(info.field_name or '').upper()} must be greater than zero")
        return value

    @field_validator(
        "pdf_libreoffice_retry_backoff_seconds",
        "pdf_libreoffice_retry_backoff_max_seconds",
        mode="before",
    )
    @classmethod
    def _validate_positive_float(cls, value: float, info: ValidationInfo) -> float:
        if isinstance(value, str):
            value = float(value)
        if value <= 0:
            raise ValueError(f"{(info.field_name or '').upper()} must be greater than zero")
        return float(value)

    @field_validator("pdf_worker_queue")
    @classmethod
    def _validate_pdf_worker_queue(cls, value: str) -> str:
        candidate = value.strip()
        if not candidate:
            raise ValueError("PDF_WORKER_QUEUE must not be empty")
        return candidate

    @model_validator(mode="after")
    def _ensure_worker_queues(self) -> "Settings":
        queues = []
        for queue in self.worker_queues:
            normalized = queue.strip()
            if normalized and normalized not in queues:
                queues.append(normalized)
        if self.pdf_worker_queue not in queues:
            queues.append(self.pdf_worker_queue)
        self.worker_queues = queues
        return self

    @model_validator(mode="after")
    def _validate_cors_settings(self) -> "Settings":
        origins: list[str] = []
        for origin in self.allowed_origins:
            normalized = origin.strip()
            if normalized and normalized not in origins:
                origins.append(normalized)
        self.allowed_origins = origins or list(DEFAULT_ALLOWED_ORIGINS)

        if self.cors_allow_credentials and "*" in self.allowed_origins:
            raise ValueError(
                "APP_CORS_ORIGINS cannot contain '*' when APP_CORS_ALLOW_CREDENTIALS is enabled"
            )
        return self

    @model_validator(mode="after")
    def _apply_storage_backend(self) -> "Settings":
        if self.storage_backend == "local" and self.s3_backend == "memory":
            self.s3_backend = "local"
        elif self.storage_backend == "s3" and self.s3_backend == "memory":
            self.s3_backend = "minio"
        return self

    @model_validator(mode="after")
    def _ensure_jwt_keys(self) -> Settings:
        private_key = self.jwt_private_key_pem.strip()
        public_key = self.jwt_public_key_pem.strip()

        if self.app_env in ("production", "staging"):
            if not private_key or not public_key:
                raise SettingsError(
                    "PRIVATE_KEY_PEM and PUBLIC_KEY_PEM must be configured in staging/production"
                )
            if private_key == DEV_PRIVATE_KEY.strip() or public_key == DEV_PUBLIC_KEY.strip():
                raise SettingsError(
                    "Staging/production must not use bundled development JWT key pair"
                )
            self.jwt_private_key_pem = private_key
            self.jwt_public_key_pem = public_key
            return self

        if private_key and public_key:
            self.jwt_private_key_pem = private_key
            self.jwt_public_key_pem = public_key
            return self

        logger.warning(
            (
                "Using bundled development RSA key pair for JWT signing; configure "
                "PRIVATE_KEY_PEM/PUBLIC_KEY_PEM in production"
            )
        )
        self.jwt_private_key_pem = DEV_PRIVATE_KEY
        self.jwt_public_key_pem = DEV_PUBLIC_KEY
        return self

    @model_validator(mode="after")
    def _validate_edo_integration_base_url(self) -> Settings:
        base = (self.edo_integration_base_url or "").strip()
        if not base:
            return self
        from app.core.integration_url_validation import (
            UnsafeIntegrationURLError,
            assert_safe_http_base_url,
        )

        try:
            assert_safe_http_base_url(base, app_env=self.app_env)
        except UnsafeIntegrationURLError as exc:
            raise ValueError(str(exc)) from exc
        return self

    @model_validator(mode="after")
    def _ensure_production_secrets(self) -> Settings:
        if self.app_env not in ("production", "staging"):
            return self

        missing: list[str] = []
        if not self.secret_key or self.secret_key == "change-me":
            missing.append("SECRET_KEY")
        if self.postgres_password == "change_me":
            missing.append("POSTGRES_PASSWORD")
        if self.s3_access_key == "prt_local_access":
            missing.append("S3_ACCESS_KEY")
        if self.s3_secret_key == "prt_local_secret":
            missing.append("S3_SECRET_KEY")
        if self.s3_backend == "memory":
            missing.append("S3_BACKEND")
        if not self.inbound_webhook_hmac_secret.strip():
            missing.append("INBOUND_WEBHOOK_HMAC_SECRET")

        if missing:
            raise SettingsError(
                f"{self.app_env.title()} configuration must override defaults: "
                + ", ".join(missing)
            )
        return self

    @model_validator(mode="after")
    def _disable_openapi_in_production(self) -> Settings:
        """Production must not expose interactive OpenAPI/Swagger (override ENABLE_OPENAPI_DOCS)."""

        if self.app_env == "production":
            self.enable_openapi_docs = False
            self.enable_files_legacy_routes = False
        return self

    @property
    def managing_tenant_slug(self) -> str:
        """Slug of the tenant allowed to manage the tenant fleet."""

        return (self.platform_tenant_slug or self.admin_tenant).strip().lower()

    @property
    def application(self) -> ApplicationConfig:
        if self._application is None:
            self._application = ApplicationConfig(
                name=self.app_name,
                environment=self.app_env,
                debug=self.debug,
                secret_key=self.secret_key,
                api_prefix=self.api_prefix,
                api_v1_prefix=self.api_v1_prefix,
                allowed_hosts=list(self.allowed_hosts),
                allowed_origins=list(self.allowed_origins),
                default_locale=self.default_locale,
                default_timezone=self.default_timezone,
            )
        return self._application

    @property
    def runtime(self) -> RuntimeConfig:
        if self._runtime is None:
            self._runtime = self.application.runtime
        return self._runtime

    @property
    def database(self) -> DatabaseConfig:
        if self._database is None:
            self._database = DatabaseConfig(
                url=self.database_url,
                alembic_url=self.alembic_database_url,
                echo=self.database_echo,
                host=self.postgres_host,
                port=self.postgres_port,
                name=self.postgres_db,
                user=self.postgres_user,
                password=self.postgres_password,
            )
        return self._database

    @property
    def broker(self) -> BrokerConfig:
        if self._broker is None:
            self._broker = BrokerConfig(
                broker_url=self.redis_url,
                result_url=self.redis_result_url,
                rate_limit_storage_uri=self.rate_limit_storage_uri,
            )
        return self._broker

    @property
    def redis(self) -> BrokerConfig:
        """Backward compatible accessor for Redis/Celery broker settings."""

        return self.broker

    @property
    def celery(self) -> CeleryConfig:
        if self._celery is None:
            self._celery = CeleryConfig(
                worker_queues=list(self.worker_queues),
                pdf_queue=self.pdf_worker_queue,
                task_soft_time_limit=self.celery_task_soft_time_limit,
                task_time_limit=self.celery_task_time_limit,
                task_max_retries=self.celery_task_max_retries,
                retry_backoff_seconds=self.celery_retry_backoff_seconds,
                retry_backoff_max_seconds=self.celery_retry_backoff_max_seconds,
            )
        return self._celery

    @property
    def logging(self) -> LoggingConfig:
        if self._logging is None:
            self._logging = LoggingConfig(level=self.log_level, json_enabled=self.log_json)
        return self._logging

    @property
    def database_url(self) -> str:
        if self.database_url_env:
            return self.database_url_env
        return (
            "postgresql+asyncpg://"
            f"{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def rls_enforce_unprivileged_db_role(self) -> bool:
        """Whether startup must fail when the runtime role bypasses RLS (SEC-65).

        Staging/production enforce by default; development and tests only warn so
        a local bootstrap superuser keeps working. ``RLS_REQUIRE_UNPRIVILEGED_DB_ROLE``
        overrides either way.
        """

        if self.rls_require_unprivileged_db_role_env is not None:
            return self.rls_require_unprivileged_db_role_env
        return self.app_env in ("production", "staging")

    @property
    def migration_database_url(self) -> str:
        """Async DSN Alembic connects with.

        ``MIGRATION_DATABASE_URL`` lets migrations run as the table owner while the
        runtime connects as the unprivileged, RLS-enforced role (SEC-65):
        ``ENABLE``/``FORCE ROW LEVEL SECURITY`` is owner-only DDL, and the owner is
        exactly the role RLS must not apply to. Falls back to ``DATABASE_URL``.
        """

        return self.migration_database_url_env or self.database_url

    @property
    def alembic_database_url(self) -> str:
        """Synchronous form of :attr:`migration_database_url` (offline mode)."""

        url = self.migration_database_url
        if url.startswith("sqlite+aiosqlite"):
            return url.replace("+aiosqlite", "")
        if url.startswith("postgresql+asyncpg"):
            return url.replace("+asyncpg", "+psycopg2")
        return url

    @property
    def redis_result_url(self) -> str:
        """Return Celery result backend URL, defaulting to the broker URL."""

        return self.redis_result_url_env or self.redis_url

    @property
    def storage_root_path(self) -> Path:
        """Return normalized storage root path for local storage backends."""

        return Path(self.storage_root).expanduser().resolve()

    @property
    def redis_enabled(self) -> bool:
        """Return True when Redis-backed features should be used."""

        if self.app_run_mode == "dockerless" or self.celery_eager:
            return False
        return not self.redis_url.startswith("memory://")

    def redacted(self) -> dict[str, object]:
        """Return settings payload safe for structured logging."""

        payload = self.model_dump()
        for key in (
            "secret_key",
            "postgres_password",
            "s3_access_key",
            "s3_secret_key",
            "admin_password",
            "jwt_private_key_pem",
            "portal_token_salt",
            "inbound_webhook_hmac_secret",
            # DSNs carry the database password inline.
            "database_url_env",
            "migration_database_url_env",
            "secret_encryption_key",
            "secret_encryption_keys",
        ):
            if key in payload and payload[key]:
                payload[key] = "***"
        return payload


@lru_cache
def _load_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]  # pydantic-settings loads fields from env vars


def get_settings(*, force_reload: bool = False) -> Settings:
    """Return cached application settings, reloading when requested."""

    if force_reload:
        _load_settings.cache_clear()
    return _load_settings()


def bootstrap(role: Literal["api", "worker"]) -> Settings:
    settings = get_settings(force_reload=True)
    required_values = {
        "SECRET_KEY": settings.secret_key,
        "DATABASE_URL": settings.database_url,
        "REDIS_URL": settings.redis_url,
        "S3_ACCESS_KEY": settings.s3_access_key,
        "S3_SECRET_KEY": settings.s3_secret_key,
        "S3_BUCKET": settings.s3_bucket,
    }
    missing = [name for name, value in required_values.items() if not str(value).strip()]
    if missing:
        raise SettingsError(
            "Missing required environment variables for " f"{role}: {', '.join(sorted(missing))}"
        )
    configure_runtime_locale(
        locale_name=settings.application.default_locale,
        timezone_name=settings.application.default_timezone,
    )
    if settings.app_env in ("production", "staging") and (
        not settings.application.secret_key or settings.application.secret_key == "change-me"
    ):
        raise SettingsError("SECRET_KEY must be configured for production and staging")
    return settings


def reset_settings_cache() -> None:
    """Clear cached settings to force reload on next access."""

    _load_settings.cache_clear()


# Provide compatibility attribute used in tests expecting an lru_cache-style API.
get_settings.cache_clear = reset_settings_cache  # type: ignore[attr-defined]


__all__ = ["Settings", "SettingsError", "get_settings", "bootstrap", "reset_settings_cache"]


def split_csv(
    value: str | Sequence[str] | PydanticUndefinedType | None,
    *,
    default: Sequence[str],
) -> list[str]:
    """Normalize comma separated values to a list of strings."""

    if value is None or value is PydanticUndefined:
        return list(default)

    if isinstance(value, str):
        raw_items: Iterable[object] = value.split(",")
    elif isinstance(value, Sequence):
        raw_items = value
    else:
        try:
            raw_items = list(value)  # type: ignore[call-overload]
        except TypeError as exc:  # pragma: no cover - defensive programming
            raise TypeError("Expected string or sequence of strings") from exc

    normalized: list[str] = []
    for item in raw_items:
        if item is None:
            continue
        candidate = str(item).strip()
        if candidate:
            normalized.append(candidate)

    return normalized or list(default)


def binary_exists(candidate: str) -> bool:
    """Check whether the provided binary exists on disk or in ``PATH``."""

    path = Path(candidate)

    # Explicit path (absolute or contains directory components)
    if path.is_absolute() or path.name != candidate:
        return path.exists()

    resolved = which(candidate)
    if resolved is not None:
        return True

    import os
    import sys

    if sys.platform == "win32":
        path_dirs = os.environ.get("PATH", "").split(os.pathsep)
        for path_dir in path_dirs:
            if not path_dir:
                continue
            candidate_path = Path(path_dir) / candidate
            if candidate_path.exists():
                return True

    return path.exists()
