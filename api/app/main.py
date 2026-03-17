import asyncio
import os
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.infrastructure.logging import setup_logging
from app.infrastructure.storage.oss import get_oss
from app.infrastructure.storage.postgres import get_postgres
from app.infrastructure.storage.redis import get_redis
from app.infrastructure.external.task.redis_stream_task import RedisStreamTask
from app.interfaces.endpoints.routes import router
from app.interfaces.errors.exception_handlers import register_exception_handlers
from core.config import get_settings

# 1.加载配置信息
settings = get_settings()
API_ROOT = Path(__file__).resolve().parents[1]
ALEMBIC_INI_PATH = API_ROOT / "alembic.ini"
SKIP_STARTUP_MIGRATIONS = os.getenv("SKIP_STARTUP_MIGRATIONS", "").lower() in {"1", "true", "yes"}

# 2.初始化日志系统
setup_logging()
logger = logging.getLogger()

# 3.定义FastAPI路由tags标签
openapi_tags = [
    {
        "name": "状态模块",
        "description": "包含 **状态监测** 等API 接口，用于监测系统的运行状态。"
    }
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    """创建FastAPI应用生命周期上下文管理器"""
    # 0.重新初始化日志系统(uvicorn启动时dictConfig会影响根日志处理器，需要在此重新配置)
    setup_logging()

    # 1.日志打印代码已经开始执行了
    logger.info("Aurora正在初始化")

    # 2.运行数据库迁移(将数据同步到生产环境)
    if SKIP_STARTUP_MIGRATIONS:
        logger.info("Aurora跳过启动阶段数据库迁移")
    else:
        logger.info("Aurora正在执行数据库迁移")
        alembic_cfg = Config(str(ALEMBIC_INI_PATH))
        command.upgrade(alembic_cfg, "head")
        logger.info("Aurora数据库迁移完成")

    # 3.初始化Redis/Postgres/OSS客户端
    logger.info("Aurora正在初始化Redis")
    await get_redis().init()
    logger.info("Aurora正在初始化Postgres")
    await get_postgres().init()
    logger.info("Aurora正在初始化OSS")
    await get_oss().init()
    logger.info("Aurora基础依赖初始化完成")

    try:
        # 4.lifespan分界点
        yield
    finally:
        try:
            # 5.等待agent服务关闭
            logger.info("Aurora正在关闭")
            await asyncio.wait_for(RedisStreamTask.destroy(), timeout=30.0)
            logger.info("Agent服务成功关闭")
        except asyncio.TimeoutError:
            logger.warning("Agent服务关闭超时, 强制关闭, 部分任务将被释放")
        except Exception as e:
            logger.error(f"Agent服务关闭期间出现错误: {str(e)}")

        # 6.关闭其他应用
        await get_redis().shutdown()
        await get_postgres().shutdown()
        await get_oss().shutdown()

        logger.info("Aurora应用关闭成功")


# 4.创建Aurora应用实例
app = FastAPI(
    title="Aurora 智能体平台",
    description="Aurora 是一个支持多用户、多沙箱和 A2A/MCP 扩展的智能体平台。",
    lifespan=lifespan,
    openapi_tags=openapi_tags,
    version="1.0.0",
)

# 5.配置CORS中间件，解决跨域问题
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 6.注册错误处理器
register_exception_handlers(app)

# 7.集成路由
app.include_router(router, prefix="/api")
