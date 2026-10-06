"""Central configuration loaded from environment variables / .env."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "TenderBot AI"
    app_version: str = "1.0.0"
    database_url: str = "sqlite:///./tenderbot.db"
    public_base_url: str = "http://localhost:8000"
    admin_api_key: str = ""

    openai_api_key: str = ""
    openai_model: str = "gpt-4o"

    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_whatsapp_from: str = "whatsapp:+14155238886"
    twilio_voice_from: str = ""
    twilio_approval_content_sid: str = ""
    validate_twilio_signature: bool = False

    trial_days: int = 15
    basic_price: int = 999
    vip_price: int = 5000
    min_history_samples: int = 3
    expiry_alert_days: int = 30
    gst_rate_percent: float = 18.0
    gst_tds_rate_percent: float = 2.0
    gst_tds_threshold: float = 250000.0
    enable_scheduler: bool = True
    vault_check_interval_hours: int = 24

    submission_webhook_url: str = ""
    allowed_scrape_hosts: str = "mahatenders.gov.in,eprocure.gov.in,etenders.gov.in"

    @property
    def twilio_configured(self) -> bool:
        return bool(self.twilio_account_sid and self.twilio_auth_token)

    @property
    def scrape_hosts(self) -> list[str]:
        return [h.strip().lower() for h in self.allowed_scrape_hosts.split(",") if h.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
