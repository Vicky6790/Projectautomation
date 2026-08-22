from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    auth_mode: str = "disabled"
    data_dir: Path = Path("./data")
    cors_origins: str = "http://localhost:5173"
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o-mini"
    openai_timeout_seconds: float = 60
    ai_stub: bool = False
    max_upload_bytes: int = 52_428_800
    request_ttl_hours: int = 24

    def ensure_storage(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        probe = self.data_dir / ".write_probe"
        try:
            probe.write_text("ok", encoding="utf-8")
            probe.unlink(missing_ok=True)
        except OSError as exc:
            raise RuntimeError(f"DATA_DIR is not writable: {self.data_dir}") from exc

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    @property
    def auth_required(self) -> bool:
        return self.auth_mode.lower() == "required"


settings = Settings()
