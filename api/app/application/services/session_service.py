import logging
from typing import List, Callable

from app.application.errors.exceptions import NotFoundError, ServerRequestsError
from app.domain.models.file import File
from app.domain.models.app_config import SandboxPreference
from app.domain.models.session import Session, SessionStatus
from app.domain.models.user import User
from app.domain.repositories.uow import IUnitOfWork
from app.interfaces.schemas.session import FileReadResponse, ShellReadResponse
from .sandbox_service import SandboxService

logger = logging.getLogger(__name__)


class SessionService:
    """会话服务"""

    def __init__(
            self,
            uow_factory: Callable[[], IUnitOfWork],
            sandbox_service: SandboxService,
            current_user: User,
    ) -> None:
        """构造函数，完成会话服务初始化"""
        self._uow_factory = uow_factory
        self._uow = uow_factory()
        self._sandbox_service = sandbox_service
        self._current_user = current_user

    async def _get_sandbox_preference(self) -> SandboxPreference:
        async with self._uow_factory() as uow:
            app_config = await uow.user_config.load(self._current_user.id)
        return app_config.sandbox_preference

    async def create_session(self) -> Session:
        """创建一个空白的新任务会话"""
        logger.info(f"创建一个空白新任务会话")
        session = Session(title="新对话", user_id=self._current_user.id)
        async with self._uow:
            await self._uow.session.save(session)
        logger.info(f"成功创建一个新任务会话: {session.id}")
        return session

    async def _attach_queue_state(self, session: Session) -> Session:
        queue_status = await self._sandbox_service.get_queue_status(session.id)
        binding = await self._sandbox_service.get_binding(session.id)
        session.waiting_reason = None
        session.sandbox_queue_position = None
        session.sandbox_queue_size = 0
        session.sandbox_active = binding is not None
        session.sandbox_status_text = "未占用"

        if queue_status is not None:
            session.status = SessionStatus.WAITING
            session.waiting_reason = "sandbox"
            session.sandbox_queue_position = queue_status.position
            session.sandbox_queue_size = queue_status.size
            if queue_status.position > 1:
                session.sandbox_status_text = f"排队中，前方 {queue_status.position - 1} 个对话"
            else:
                session.sandbox_status_text = "排队中，当前队首"
            return session

        if binding is not None:
            session.sandbox_status_text = "沙箱占用中"
            return session

        if session.status == SessionStatus.WAITING:
            session.waiting_reason = "user"
            session.sandbox_status_text = "沙箱已释放"
        elif session.status == SessionStatus.COMPLETED:
            session.sandbox_status_text = "沙箱已释放"
        return session

    async def _attach_queue_states(self, sessions: List[Session]) -> List[Session]:
        queue_statuses = await self._sandbox_service.list_queue_statuses()
        for session in sessions:
            binding = await self._sandbox_service.get_binding(session.id)
            queue_status = queue_statuses.get(session.id)
            session.waiting_reason = None
            session.sandbox_queue_position = None
            session.sandbox_queue_size = 0
            session.sandbox_active = binding is not None
            session.sandbox_status_text = "未占用"
            if queue_status is not None:
                session.status = SessionStatus.WAITING
                session.waiting_reason = "sandbox"
                session.sandbox_queue_position = queue_status.position
                session.sandbox_queue_size = queue_status.size
                if queue_status.position > 1:
                    session.sandbox_status_text = f"排队中，前方 {queue_status.position - 1} 个对话"
                else:
                    session.sandbox_status_text = "排队中，当前队首"
            elif binding is not None:
                session.sandbox_status_text = "沙箱占用中"
            elif session.status == SessionStatus.WAITING:
                session.waiting_reason = "user"
                session.sandbox_status_text = "沙箱已释放"
            elif session.status == SessionStatus.COMPLETED:
                session.sandbox_status_text = "沙箱已释放"
        return sessions

    async def get_all_sessions(self) -> List[Session]:
        """获取项目所有任务会话列表"""
        async with self._uow:
            sessions = await self._uow.session.get_all(self._current_user.id)
        return await self._attach_queue_states(sessions)

    async def clear_unread_message_count(self, session_id: str) -> None:
        """清空指定会话未读消息数"""
        logger.info(f"清除会话[{session_id}]未读消息数")
        async with self._uow:
            await self._uow.session.update_unread_message_count(session_id, 0)

    async def delete_session(self, session_id: str) -> None:
        """根据传递的会话id删除任务会话"""
        # 1.先检查会话是否存在
        logger.info(f"正在删除会话, 会话id: {session_id}")
        async with self._uow:
            session = await self._uow.session.get_by_id(session_id)
        if not session or session.user_id != self._current_user.id:
            logger.error(f"会话[{session_id}]不存在, 删除失败")
            raise NotFoundError(f"会话[{session_id}]不存在, 删除失败")

        # 2.根据传递的会话id删除会话
        await self._sandbox_service.release_session_binding(session_id)
        async with self._uow:
            await self._uow.session.delete_by_id(session_id)
        logger.info(f"删除会话[{session_id}]成功")

    async def get_session(self, session_id: str) -> Session:
        """获取指定会话详情信息"""
        async with self._uow:
            session = await self._uow.session.get_by_id(session_id)
        if session and session.user_id == self._current_user.id:
            return await self._attach_queue_state(session)
        return None

    async def get_session_files(self, session_id: str) -> List[File]:
        """根据传递的会话id获取指定会话的文件列表信息"""
        logger.info(f"获取指定会话[{session_id}]下的文件列表信息")
        async with self._uow:
            session = await self._uow.session.get_by_id(session_id)
        if not session or session.user_id != self._current_user.id:
            raise RuntimeError(f"当前会话不存在[{session_id}], 请核实后重试")
        return session.files

    async def read_file(self, session_id: str, filepath: str) -> FileReadResponse:
        """根据传递的信息查看会话中指定文件的内容"""
        # 1.检查会话是否存在
        logger.info(f"获取会话[{session_id}]中的文件内容, 文件路径: {filepath}")
        async with self._uow:
            session = await self._uow.session.get_by_id(session_id)
        if not session or session.user_id != self._current_user.id:
            raise RuntimeError(f"当前会话不存在[{session_id}], 请核实后重试")

        # 2.根据沙箱id获取沙箱并判断是否存在
        if not session.sandbox_id:
            raise NotFoundError("当前会话无沙箱环境")
        sandbox_preference = await self._get_sandbox_preference()
        sandbox = await self._sandbox_service.get_session_sandbox(
            self._current_user.id,
            session.id,
            sandbox_preference,
        )
        if not sandbox:
            raise NotFoundError("当前会话沙箱不存在或已销毁")

        # 3.调用沙箱读取文件内容
        result = await sandbox.read_file(filepath)
        if result.success:
            return FileReadResponse(**result.data)

        raise ServerRequestsError(result.message)

    async def read_shell_output(self, session_id: str, shell_session_id: str) -> ShellReadResponse:
        """根据传递的任务会话id+Shell会话id获取Shell执行结果"""
        # 1.检查会话是否存在
        logger.info(f"获取会话[{session_id}]中的Shell内容输出, Shell标识符: {shell_session_id}")
        async with self._uow:
            session = await self._uow.session.get_by_id(session_id)
        if not session or session.user_id != self._current_user.id:
            raise RuntimeError(f"当前会话不存在[{session_id}], 请核实后重试")

        # 2.根据沙箱id获取沙箱并判断是否存在
        if not session.sandbox_id:
            raise NotFoundError("当前会话无沙箱环境")
        sandbox_preference = await self._get_sandbox_preference()
        sandbox = await self._sandbox_service.get_session_sandbox(
            self._current_user.id,
            session.id,
            sandbox_preference,
        )
        if not sandbox:
            raise NotFoundError("当前会话沙箱不存在或已销毁")

        # 3.调用沙箱查看shell内容
        result = await sandbox.read_shell_output(session_id=shell_session_id, console=True)
        if result.success:
            return ShellReadResponse(**result.data)

        raise ServerRequestsError(result.message)

    async def get_vnc_url(self, session_id: str) -> str:
        """获取指定会话的vnc链接"""
        # 1.检查会话是否存在
        logger.info(f"获取会话[{session_id}]的VNC链接")
        async with self._uow:
            session = await self._uow.session.get_by_id(session_id)
        if not session or session.user_id != self._current_user.id:
            raise RuntimeError(f"当前会话不存在[{session_id}], 请核实后重试")

        # 2.根据沙箱id获取沙箱并判断是否存在
        if not session.sandbox_id:
            raise NotFoundError("当前会话无沙箱环境")
        sandbox_preference = await self._get_sandbox_preference()
        sandbox = await self._sandbox_service.get_session_sandbox(
            self._current_user.id,
            session.id,
            sandbox_preference,
        )
        if not sandbox:
            raise NotFoundError("当前会话沙箱不存在或已销毁")

        return sandbox.vnc_url
