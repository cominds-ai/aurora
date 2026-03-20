import os
import json
from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


def _resolve_env_files() -> tuple[str, ...]:
    project_root = Path(__file__).resolve().parents[2]
    env = os.getenv("ENV")
    default_secrets_file = project_root.parent / ".aurora-secrets.env"
    secrets_file = os.getenv("AURORA_SECRETS_FILE")
    primary_env_file = project_root / ".env"
    fallback_env_file = project_root / ".env.example"

    if env:
        env = env.lower()
        if env == "production" and primary_env_file.exists():
            env_files = [str(primary_env_file)]
        elif fallback_env_file.exists():
            env_files = [str(fallback_env_file)]
        else:
            env_files = []
    elif primary_env_file.exists():
        env_files = [str(primary_env_file)]
    elif fallback_env_file.exists():
        env_files = [str(fallback_env_file)]
    else:
        env_files = []

    if secrets_file:
        env_files.append(secrets_file)
    elif default_secrets_file.exists():
        env_files.append(str(default_secrets_file))

    return tuple(env_files)


class Settings(BaseSettings):
    """Aurora后端中控配置信息，从.env或者环境变量中加载数据"""

    # 项目基础配置
    env: str = "development"
    log_level: str = "INFO"

    # 数据库相关配置
    sqlalchemy_database_uri: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/aurora"

    # Redis缓存配置
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: str | None = None

    # 阿里云OSS配置
    oss_endpoint: str = ""
    oss_access_key_id: str = ""
    oss_access_key_secret: str = ""
    oss_bucket_name: str = ""
    oss_scheme: str = "https"

    # 默认模型配置
    default_llm_base_url: str = "https://codex.ysaikeji.cn/v1"
    default_llm_model_name: str = "gpt-5.4"
    aurora_official_default_gemini3_api_key: str = ""
    aurora_official_default_claude_api_key: str = ""

    # 认证配置
    auth_jwt_secret: str = "aurora-dev-secret"
    auth_password_salt: str = "aurora-password-salt"
    auth_token_expire_hours: int = 72
    default_login_password: str = "123456"

    # Sandbox配置
    sandbox_mode: str = "docker"
    sandbox_address: Optional[str] = None
    sandbox_image: Optional[str] = None
    sandbox_name_prefix: Optional[str] = "aurora-sandbox"
    sandbox_ttl_minutes: Optional[int] = 60
    sandbox_network: Optional[str] = "aurora-network"
    sandbox_chrome_args: Optional[str] = ""
    sandbox_https_proxy: Optional[str] = None
    sandbox_http_proxy: Optional[str] = None
    sandbox_no_proxy: Optional[str] = None
    sandbox_binding_ttl_hours: int = 48
    sandbox_registry_json: str = "[]"

    # 使用pydantic v2的写法来完成环境变量信息的告知
    model_config = SettingsConfigDict(
        env_file=_resolve_env_files(),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def sandbox_registry(self) -> list[dict]:
        try:
            return json.loads(self.sandbox_registry_json)
        except Exception:
            return []


@lru_cache()
def get_settings() -> Settings:
    """获取当前Aurora项目的配置信息，并对内容进行缓存，避免重复读取"""
    settings = Settings()
    return settings
