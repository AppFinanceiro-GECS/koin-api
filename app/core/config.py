from decimal import Decimal
from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    # Use SQLite para dev: sqlite+aiosqlite:///./financeiro.db
    # Use PostgreSQL para prod: postgresql+asyncpg://user:pass@host/db
    database_url: str = "sqlite+aiosqlite:///./financeiro.db"
    use_sqlite: bool = True  # Detectado automaticamente pela URL

    # JWT
    secret_key: str = "dev-secret-key-change-in-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    # App
    debug: bool = False  # SQL echo desabilitado por padrao para performance
    sql_echo: bool = False  # SQL echo separado do debug geral
    environment: str = "development"
    app_name: str = "App Financeiro"
    api_v1_prefix: str = "/api/v1"

    # CORS - origens permitidas (separadas por vírgula)
    cors_origins: str = "http://localhost:3000"

    # Document Processing
    max_upload_size_mb: int = 10
    allowed_extensions: list[str] = ["jpg", "jpeg", "png", "pdf", "csv", "xlsx", "xls"]

    # Storage
    upload_dir: str = "./uploads"

    # LLM/Vision API (para OCR inteligente e Chat)
    # Providers suportados: google (gratuito), mistral (melhor custo-benefício)
    vision_provider: str = "google"  # google é gratuito!
    google_api_key: str | None = None  # Gemini - GRÁTIS
    # Modelos em https://ai.google.dev/gemini-api/docs/models (a família 2.0 foi desligada em 01/06/2026).
    # Trocar de modelo é só mudar a variável de ambiente; nenhum outro lugar do código fixa o nome.
    vision_model: str = "gemini-3.5-flash-lite"  # extração de faturas e cupons (imagem/PDF)
    classifier_model: str = "gemini-3.5-flash-lite"  # tipo de documento e intenção do chat

    ai_prices_file: str = "config/ai_prices.json"
    ai_daily_budget_usd: Decimal | None = Field(default=None, ge=0)
    ai_call_reservation_usd: Decimal = Field(default=Decimal("0.10"), gt=0)

    @field_validator("ai_daily_budget_usd", mode="before")
    @classmethod
    def empty_daily_budget(cls, value):
        return None if value == "" else value

    # Mistral AI (melhor custo-benefício para OCR de faturas)
    mistral_api_key: str | None = None
    mistral_ocr_model: str = "mistral-ocr-latest"
    mistral_llm_model: str = "mistral-small-latest"

    # SMTP Configuration (Hostinger)
    smtp_host: str = "smtp.hostinger.com"
    smtp_port: int = 465
    smtp_use_ssl: bool = True
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_from_name: str = "Koin"
    smtp_from_email: str | None = None

    # Frontend URL (para links nos emails)
    frontend_url: str = "https://biveto.com"

    # Koin API Key (para integrações internas)
    koin_api_key: str | None = None

    # Chat provider (separate from vision/extraction provider)
    # Default: uses vision_provider. Override to use cheaper model for text-only chat.
    chat_provider: str | None = None  # None = same as vision_provider
    chat_model: str | None = None  # None = same as vision_model

    # Google PDF processing mode: "text" (extract text, send as string) or "native" (send PDF directly)
    google_pdf_mode: str = (
        "text"  # "text" = extract text with PyMuPDF then send to LLM, "native" = direct PDF upload
    )

    # Scheduler (APScheduler — replaces Celery Beat)
    scheduler_dry_run: bool = False  # When True, log what would be sent but don't send

    class Config:
        env_file = ".env"
        case_sensitive = False
        # .env também carrega variáveis só de infra (POSTGRES_*, API_DOMAIN...)
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
