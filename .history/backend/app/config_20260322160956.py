"""Application configuration via pydantic-settings."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables or .env file."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # 인증
    MY_ID: str = "admin"
    MY_PW: str = "admin"
    SECRET_KEY: str = ""

    # 서버
    APP_PORT: int = 8000
    APP_HOST: str = "0.0.0.0"
    APP_VERSION: str = "2.0.0"

    # DB
    DATABASE_URL: str = "sqlite+aiosqlite:///./metadata/app.db"

    # yt-dlp
    PROXY: str = ""
    DOWNLOAD_DIR: str = "./downfolder"

    # 기능 플래그
    TERMS_ACCEPTED: bool = False


settings = Settings()
