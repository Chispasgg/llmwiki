from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file="../.env", extra="ignore")

    MODE: Literal["local", "hosted"] = "local"
    WORKSPACE_PATH: str = "."

    DATABASE_URL: str = ""
    VOYAGE_API_KEY: str = ""
    TURBOPUFFER_API_KEY: str = ""
    EMBEDDING_MODEL: str = "voyage-4-lite"
    EMBEDDING_DIM: int = 512
    LOGFIRE_TOKEN: str = ""
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    AWS_REGION: str = "us-east-1"
    S3_BUCKET: str = "supavault-documents"
    MISTRAL_API_KEY: str = ""
    PDF_BACKEND: str = "opendataloader"  # "opendataloader" or "mistral"
    STAGE: str = "dev"
    APP_URL: str = "http://localhost:3000"
    API_URL: str = "http://localhost:8000"

    QUOTA_MAX_PAGES: int = 500  # per-user page limit (free tier)
    QUOTA_MAX_PAGES_PER_DOC: int = 300  # max pages per single document
    QUOTA_MAX_STORAGE_BYTES: int = 1_073_741_824  # 1 GB per user

    CONVERTER_URL: str = ""
    CONVERTER_SECRET: str = ""

    GLOBAL_OCR_ENABLED: bool = True
    GLOBAL_MAX_PAGES: int = 1_000_000
    GLOBAL_MAX_USERS: int = 10_000

    SENTRY_DSN: str = ""
    ADMIN_USER_IDS: list[str] = []
    MISTRAL_OCR_URL: str = "https://api.mistral.ai/v1/ocr"
    WATCHER_MAX_HASH_BYTES: int = 100_000_000  # 100 MB — ficheros más grandes no se hashean

    @field_validator("ADMIN_USER_IDS", mode="before")
    @classmethod
    def _parse_admin_ids(cls, v):
        # Soporta tanto JSON (["id1","id2"]) como CSV (id1,id2) en .env
        if isinstance(v, str):
            v = v.strip()
            if not v:
                return []
            if v.startswith("["):
                import json
                return json.loads(v)
            return [uid.strip() for uid in v.split(",") if uid.strip()]
        return v

    SERVER_FILES_ROOT: str = "/home/ubuntu/wiki/files"
    SERVER_DATA_ROOT: str = "/home/ubuntu/wiki/data"
    USAGE_LOG_FILE: str = ""  # absolute path to JSONL audit log; empty = disabled
    SESSION_EXPIRE_SECONDS: int = 86400
    COOKIE_SECURE: bool = False
    MCP_URL: str = "http://localhost:1501"

    ARGON2_TIME_COST: int = 3
    ARGON2_MEMORY_COST: int = 65536  # 64 MB — OWASP Argon2id minimum
    ARGON2_PARALLELISM: int = 4

    LATEX_TEMPLATE_PATH: str = "config/wiki-export.tex"


settings = Settings()
