from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    neo4j_uri: str = Field(validation_alias="NEO4J_URI")
    neo4j_username: str = Field(validation_alias="NEO4J_USERNAME")
    neo4j_password: str = Field(validation_alias="NEO4J_PASSWORD")

    qwen_api_key: str = Field(validation_alias="QWEN_API_KEY")
    qwen_base_url: Optional[str] = Field(
        default=None, validation_alias="QWEN_BASE_URL"
    )
    qwen_model: str = Field(default="qwen-plus", validation_alias="QWEN_MODEL")

    service_host: str = Field(default="0.0.0.0", validation_alias="SERVICE_HOST")
    service_port: int = Field(default=8000, validation_alias="SERVICE_PORT")

    model_config = SettingsConfigDict(env_file=(".env", "backend/.env"), case_sensitive=False, extra="ignore")
