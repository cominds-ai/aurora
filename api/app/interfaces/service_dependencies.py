import logging

from fastapi import Depends, HTTPException, WebSocket
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.services.auth_service import AuthService
from app.application.services.agent_service import AgentService
from app.application.services.app_config_service import AppConfigService
from app.application.services.file_service import FileService
from app.application.services.sandbox_service import SandboxService
from app.application.services.session_service import SessionService
from app.application.services.status_service import StatusService
from app.domain.models.user import User
from app.infrastructure.external.file_storage.oss_file_storage import OSSFileStorage
from app.infrastructure.external.health_checker.postgres_health_checker import PostgresHealthChecker
from app.infrastructure.external.health_checker.redis_health_checker import RedisHealthChecker
from app.infrastructure.external.json_parser.repair_json_parser import RepairJSONParser
from app.infrastructure.external.task.redis_stream_task import RedisStreamTask
from app.infrastructure.storage.postgres import get_db_session, get_uow
from app.infrastructure.storage.redis import RedisClient, get_redis
from app.infrastructure.storage.oss import OSS, get_oss
from core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()
bearer_scheme = HTTPBearer(auto_error=False)


def get_auth_service() -> AuthService:
    return AuthService(uow_factory=get_uow)


async def get_current_user(
        credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
        auth_service: AuthService = Depends(get_auth_service),
) -> User:
    if not credentials:
        raise HTTPException(status_code=401, detail="未登录")
    return await auth_service.get_user_by_token(credentials.credentials)


async def get_websocket_current_user(
        websocket: WebSocket,
        auth_service: AuthService = Depends(get_auth_service),
) -> User:
    token = websocket.query_params.get("access_token")
    if not token:
        auth_header = websocket.headers.get("authorization", "")
        if auth_header.lower().startswith("bearer "):
            token = auth_header[7:].strip()

    if not token:
        raise HTTPException(status_code=401, detail="未登录")
    return await auth_service.get_user_by_token(token)


def get_app_config_service(current_user: User = Depends(get_current_user)) -> AppConfigService:
    return AppConfigService(uow_factory=get_uow, user_id=current_user.id)


def get_sandbox_service() -> SandboxService:
    return SandboxService(uow_factory=get_uow)


def get_status_service(
        db_session: AsyncSession = Depends(get_db_session),
        redis_client: RedisClient = Depends(get_redis),
) -> StatusService:
    """获取状态服务"""
    # 1.初始化postgres和redis健康检查
    postgres_checker = PostgresHealthChecker(db_session)
    redis_checker = RedisHealthChecker(redis_client)

    # 2.创建服务并返回
    logger.info("加载获取StatusService")
    return StatusService(checkers=[postgres_checker, redis_checker])


def get_file_service(
        current_user: User = Depends(get_current_user),
        oss: OSS = Depends(get_oss),
) -> FileService:
    file_storage = OSSFileStorage(
        oss=oss,
        uow_factory=get_uow,
        user_id=current_user.id,
    )

    return FileService(
        uow_factory=get_uow,
        file_storage=file_storage,
        user_id=current_user.id,
    )


def get_session_service(
        current_user: User = Depends(get_current_user),
        sandbox_service: SandboxService = Depends(get_sandbox_service),
) -> SessionService:
    return SessionService(uow_factory=get_uow, sandbox_service=sandbox_service, current_user=current_user)


def get_websocket_session_service(
        current_user: User = Depends(get_websocket_current_user),
        sandbox_service: SandboxService = Depends(get_sandbox_service),
) -> SessionService:
    return SessionService(uow_factory=get_uow, sandbox_service=sandbox_service, current_user=current_user)


def get_agent_service(
        current_user: User = Depends(get_current_user),
        oss: OSS = Depends(get_oss),
        sandbox_service: SandboxService = Depends(get_sandbox_service),
) -> AgentService:
    file_storage = OSSFileStorage(
        oss=oss,
        uow_factory=get_uow,
        user_id=current_user.id,
    )

    return AgentService(
        uow_factory=get_uow,
        current_user=current_user,
        sandbox_service=sandbox_service,
        task_cls=RedisStreamTask,
        json_parser=RepairJSONParser(),
        file_storage=file_storage,
    )
