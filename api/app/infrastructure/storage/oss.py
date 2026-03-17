import logging
from functools import lru_cache
from typing import Optional
from urllib.parse import urlsplit, urlunsplit

import oss2

from core.config import Settings, get_settings

logger = logging.getLogger(__name__)


class OSS:
    """阿里云OSS对象存储"""

    def __init__(self) -> None:
        self._settings: Settings = get_settings()
        self._client: Optional[oss2.Bucket] = None

    async def init(self) -> None:
        if self._client is not None:
            logger.warning("OSS已初始化，无需重复操作")
            return

        if not self.is_configured:
            logger.warning("OSS未配置，跳过初始化；上传和文件预览相关能力将不可用")
            return

        auth = oss2.Auth(self._settings.oss_access_key_id, self._settings.oss_access_key_secret)
        endpoint = f"{self._settings.oss_scheme}://{self._settings.oss_endpoint}"
        self._client = oss2.Bucket(auth, endpoint, self._settings.oss_bucket_name)
        logger.info("OSS初始化成功")

    async def shutdown(self) -> None:
        self._client = None
        get_oss.cache_clear()

    @property
    def client(self) -> oss2.Bucket:
        if self._client is None:
            if not self.is_configured:
                raise RuntimeError("OSS未配置")
            raise RuntimeError("OSS未初始化")
        return self._client

    @property
    def is_configured(self) -> bool:
        return all(
            [
                self._settings.oss_endpoint,
                self._settings.oss_access_key_id,
                self._settings.oss_access_key_secret,
                self._settings.oss_bucket_name,
            ]
        )

    @property
    def public_base_url(self) -> str:
        return (
            f"{self._settings.oss_scheme}://"
            f"{self._settings.oss_bucket_name}.{self.public_endpoint}"
        )

    @property
    def public_endpoint(self) -> str:
        return self._settings.oss_endpoint.replace("-internal", "")

    def get_object_url(self, key: str, expires: int = 3600) -> str:
        signed_url = self.client.sign_url("GET", key, expires)
        parsed = urlsplit(signed_url)
        public_netloc = f"{self._settings.oss_bucket_name}.{self.public_endpoint}"
        return urlunsplit((parsed.scheme, public_netloc, parsed.path, parsed.query, parsed.fragment))


@lru_cache()
def get_oss() -> OSS:
    return OSS()
