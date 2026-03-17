from datetime import datetime, timedelta
from typing import Optional

from pydantic import BaseModel, Field


class SandboxBinding(BaseModel):
    """用户沙箱绑定"""

    user_id: str
    sandbox_id: str
    sandbox_label: str
    base_url: str
    cdp_url: str
    vnc_url: str
    last_active_at: datetime = Field(default_factory=datetime.now)
    expires_at: datetime = Field(default_factory=lambda: datetime.now() + timedelta(days=3))

    @property
    def expired(self) -> bool:
        return self.expires_at <= datetime.now()

    def touch(self, ttl_hours: int) -> None:
        now = datetime.now()
        self.last_active_at = now
        self.expires_at = now + timedelta(hours=ttl_hours)
