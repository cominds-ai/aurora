import os
from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import field_validator
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
    server_timeout_minutes: Optional[int] = 60  # 服务超时时间单位为分钟, <=0 表示关闭自动销毁

    @field_validator("server_timeout_minutes", mode="before")
    @classmethod
    def normalize_server_timeout_minutes(cls, value: object) -> Optional[int]:
        if value is None:
            return None
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return None
            if stripped.lower() in {"none", "null", "false", "off"}:
                return None
            value = stripped

        timeout_minutes = int(value)
        if timeout_minutes <= 0:
            return None
        return timeout_minutes

    # 使用pydantic v2提供的写法完成环境变量信息的声明
    model_config = SettingsConfigDict(
        env_file=_resolve_env_file(),
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache()
def get_settings() -> Settings:
    return Settings()
