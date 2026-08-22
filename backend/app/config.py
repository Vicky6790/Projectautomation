from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    auth_mode: str = "disabled"
    data_dir: Path = Path("./data")
    cors_origins: str = "http://localhost:5173"
    openai_api_key: str = ""
    max_upload_bytes: int = 52_428_800

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    @property
    def auth_required(self) -> bool:
        return self.auth_mode.lower() == "required"


settings = Settings()
