import hashlib
import hmac
import logging
from datetime import datetime, timedelta, timezone

import jwt

from app.application.errors.exceptions import NotFoundError
from app.domain.models.auth import AuthToken, AuthUser, LoginResult
from app.domain.models.user import User
from app.domain.repositories.uow import IUnitOfWork
from core.config import get_settings

logger = logging.getLogger(__name__)


class AuthService:
    """账号认证服务"""

    def __init__(self, uow_factory: callable) -> None:
        self._uow_factory = uow_factory
        self._settings = get_settings()

    def _hash_password(self, password: str) -> str:
        payload = f"{self._settings.auth_password_salt}:{password}".encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    def _verify_password(self, password: str, password_hash: str) -> bool:
        return hmac.compare_digest(self._hash_password(password), password_hash)

    def _build_token(self, user: User) -> str:
        expire_at = datetime.now(timezone.utc) + timedelta(hours=self._settings.auth_token_expire_hours)
        return jwt.encode(
            {"sub": user.id, "username": user.username, "exp": expire_at},
            self._settings.auth_jwt_secret,
            algorithm="HS256",
        )

    async def login(self, username: str, password: str) -> LoginResult:
        async with self._uow_factory() as uow:
            user = await uow.user.get_by_username(username)
            if not user:
                user = User(
                    username=username,
                    display_name=username,
                    password_hash=self._hash_password(self._settings.default_login_password),
                )
                await uow.user.save(user)
                await uow.user_config.save(user.id, await uow.user_config.load(user.id))

            if not self._verify_password(password, user.password_hash):
                raise NotFoundError("用户名或密码错误")

        token = AuthToken(access_token=self._build_token(user))
        return LoginResult(
            token=token,
            user=AuthUser(id=user.id, username=user.username, display_name=user.display_name),
        )

    async def get_user_by_token(self, token: str) -> User:
        try:
            payload = jwt.decode(
                token,
                self._settings.auth_jwt_secret,
                algorithms=["HS256"],
            )
        except Exception as exc:
            logger.warning("认证令牌校验失败: %s", exc)
            raise NotFoundError("登录已失效，请重新登录")

        user_id = payload.get("sub")
        if not user_id:
            raise NotFoundError("登录已失效，请重新登录")

        async with self._uow_factory() as uow:
            user = await uow.user.get_by_id(user_id)
        if not user:
            raise NotFoundError("当前用户不存在")
        return user
