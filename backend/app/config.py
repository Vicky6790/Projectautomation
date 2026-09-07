from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

CookieSameSite = Literal["lax", "strict", "none"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    auth_mode: str = "disabled"
    auth_bootstrap_user: str = "admin"
    auth_bootstrap_password: str = ""
    session_idle_hours: int = 8
    data_dir: Path = Path("./data")
    cors_origins: str = "http://localhost:5173"
    cookie_samesite: str = "lax"
    cookie_secure: bool = False
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o-mini"
    openai_timeout_seconds: float = 60
    ai_stub: bool = False
    max_upload_bytes: int = 52_428_800
    wsr_go_live_markers: str = "go-live,go live"
    wsr_client_owner_markers: str = ""
    wsr_internal_owner_markers: str = ""
    wsr_upcoming_days: int = 7
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
    def cookie_samesite_value(self) -> CookieSameSite:
        value = self.cookie_samesite.lower().strip()
        if value == "strict":
            return "strict"
        if value == "none":
            return "none"
        return "lax"

    @property
    def cookie_secure_flag(self) -> bool:
        if self.cookie_samesite_value == "none":
            return True
        return self.cookie_secure

    @property
    def auth_required(self) -> bool:
        return self.auth_mode.lower() == "required"


settings = Settings()
