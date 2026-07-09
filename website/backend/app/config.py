from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/bestfreeaifor"
    jwt_secret_key: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expiration_minutes: int = 60 * 24
    aws_region: str = "us-east-1"
    aws_account_id: str = ""
    zen_api_key: str = ""
    zen_model: str = "zen-1"
    environment: str = "development"
    site_url: str = "https://bestfreeaifor.com"
    sentry_dsn: str = ""
    slack_webhook_url: str = ""
    ses_from_email: str = "noreply@bestfreeaifor.com"
    admin_api_key: str = ""
    admin_emails: str = ""

    model_config = {"env_prefix": "APP_"}


settings = Settings()
