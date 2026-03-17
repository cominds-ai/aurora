import os
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


def _resolve_env_file() -> str:
    env = os.getenv("ENV", "development").lower()
    project_root = Path(__file__).resolve().parents[3]
    if env == "production":
        return str(project_root / ".env")
    return str(project_root / ".env.example")


class Settings(BaseSettings):
    """沙箱API服务基础配置信息"""
    log_level: str = "INFO"  # 日志等级
    server_timeout_minutes: int = 60  # 服务超时时间单位为分钟

    # 使用pydantic v2提供的写法完成环境变量信息的声明
    model_config = SettingsConfigDict(
        env_file=_resolve_env_file(),
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache()
def get_settings() -> Settings:
    return Settings()
