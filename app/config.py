from functools import lru_cache
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict
from sqlalchemy.engine import make_url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    app_name: str = "ScanTheDoc"
    app_env: str = "development"
    database_url: str = (
        "postgresql+asyncpg://scanthedoc:scanthedoc@localhost:5432/scanthedoc"
    )
    database_url_unpooled: str = ""
    redis_url: str = "redis://localhost:6379/0"
    frontend_url: str = "http://localhost:3000"
    max_upload_mb: int = Field(default=25, ge=1)
    public_operations_per_hour: int = Field(default=30, ge=1)
    public_storage_mb: int = Field(default=500, ge=1)
    default_retention_days: int = Field(default=30, ge=1)
    local_storage_path: str = ".data/documents"
    aws_endpoint_url_s3: str = ""
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    aws_region: str = ""
    s3_bucket: str = "documents"
    tesseract_cmd: str = ""
    clerk_secret_key: str = ""
    clerk_jwt_key: str = ""
    clerk_webhook_signing_secret: str = ""
    clerk_authorized_parties: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:3000"]
    )

    @field_validator("clerk_authorized_parties", mode="before")
    @classmethod
    def parse_authorized_parties(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator("clerk_jwt_key", mode="after")
    @classmethod
    def restore_pem_newlines(cls, value: str) -> str:
        return value.replace("\\n", "\n")

    @field_validator("database_url", "database_url_unpooled", mode="after")
    @classmethod
    def use_asyncpg(cls, value: str) -> str:
        if value.startswith("postgresql://"):
            value = value.replace("postgresql://", "postgresql+asyncpg://", 1)
        elif value.startswith("postgres://"):
            value = value.replace("postgres://", "postgresql+asyncpg://", 1)
        if not value:
            return value
        url = make_url(value)
        ssl_mode = url.query.get("sslmode")
        url = url.difference_update_query(["channel_binding", "sslmode"])
        if ssl_mode:
            url = url.update_query_dict({"ssl": ssl_mode})
        return url.render_as_string(hide_password=False)

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
