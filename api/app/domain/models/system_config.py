from typing import List, Optional
from urllib.parse import urlparse

from pydantic import BaseModel, Field, field_validator


class SandboxPoolItem(BaseModel):
    host: str
    label: Optional[str] = None

    @field_validator("host", mode="before")
    @classmethod
    def normalize_host(cls, value: str) -> str:
        if value is None:
            raise ValueError("sandbox host is required")

        raw_value = str(value).strip()
        if not raw_value:
            raise ValueError("sandbox host is required")

        if "://" in raw_value:
            parsed = urlparse(raw_value)
            host = parsed.hostname
            if not host:
                raise ValueError("invalid sandbox host")
            return host

        host = raw_value.split("/", 1)[0].strip()
        if host.startswith("[") and "]" in host:
            return host[1:host.index("]")]

        if ":" in host:
            host_candidate, port_candidate = host.rsplit(":", 1)
            if port_candidate.isdigit():
                return host_candidate

        return host

    @field_validator("label", mode="before")
    @classmethod
    def normalize_label(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        label = str(value).strip()
        return label or None


class SystemConfig(BaseModel):
    sandbox_pool: List[SandboxPoolItem] = Field(default_factory=list)

