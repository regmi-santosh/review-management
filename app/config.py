from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    confidence_threshold: float = 0.85

    google_client_mode: str = "mock"  # "mock" or "live"
    google_oauth_client_id: str = ""
    google_oauth_client_secret: str = ""
    google_oauth_refresh_token: str = ""
    google_business_account_id: str = ""
    google_business_location_id: str = ""

    slack_webhook_url: str = ""

    business_name: str = "Brows & Threading City"

    database_url: str = "sqlite:///./review_management.db"


settings = Settings()
