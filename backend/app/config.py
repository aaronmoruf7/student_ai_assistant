from typing import Optional

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str
    google_client_id: Optional[str] = None
    google_client_secret: Optional[str] = None
    openai_api_key: Optional[str] = None

    class Config:
        env_file = ".env"


settings = Settings()
