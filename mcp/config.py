from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(_ENV_FILE), extra="ignore")

    MODE: str = "local"  # "local" or "hosted"
    WORKSPACE_PATH: str = "."

    DATABASE_URL: str = ""
    VOYAGE_API_KEY: str = ""
    TURBOPUFFER_API_KEY: str = ""
    EMBEDDING_MODEL: str = "bge-m3"
    EMBEDDING_DIM: int = 1024
    OLLAMA_URL: str = ""  # vacío => search_chunks solo léxico
    # Presupuesto de contexto para el batch-read (aprox. en tokens; ~4 chars/token).
    # 30000 tokens ≈ 120_000 chars = comportamiento previo.
    READ_MAX_TOKENS: int = 30000
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    AWS_REGION: str = "us-east-1"
    S3_BUCKET: str = "supavault-documents"
    LOGFIRE_TOKEN: str = ""
    STAGE: str = "dev"
    APP_URL: str = "http://localhost:3000"
    API_URL: str = "http://localhost:8000"
    MCP_URL: str = "http://localhost:1501"
    SENTRY_DSN: str = ""
    SERVER_FILES_ROOT: str = "/home/ubuntu/wiki/files"


settings = Settings()
