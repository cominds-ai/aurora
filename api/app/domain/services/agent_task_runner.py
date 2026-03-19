import asyncio
import io
import logging
import uuid
from typing import List, AsyncGenerator, Callable, BinaryIO, Optional

from fastapi import UploadFile
from pydantic import TypeAdapter

from app.application.errors.exceptions import AppException
from app.application.services.sandbox_service import SandboxService
from app.domain.external.browser import Browser
from app.domain.external.file_storage import FileStorage
from app.domain.external.json_parser import JSONParser
from app.domain.external.llm import LLM
from app.domain.external.sandbox import Sandbox
from app.domain.external.search import SearchEngine
from app.domain.external.task import TaskRunner, Task
from app.domain.models.app_config import AgentConfig, MCPConfig, A2AConfig
from app.domain.models.event import ErrorEvent, Event, MessageEvent, BaseEvent, ToolEvent, ToolEventStatus, \
    BrowserToolContent, SearchToolContent, ShellToolContent, FileToolContent, MCPToolContent, A2AToolContent, \
    TitleEvent, WaitEvent, DoneEvent
from app.domain.models.file import File
from app.domain.models.message import Message, MessageAttachment
from app.domain.models.search import SearchResults
from app.domain.models.session import SessionStatus
from app.domain.models.tool_result import ToolResult
from app.domain.repositories.uow import IUnitOfWork
from app.domain.services.flows.planner_react import PlannerReActFlow
from app.domain.services.tools.a2a import A2ATool
from app.domain.services.tools.mcp import MCPTool
from app.domain.models.app_config import SandboxPreference

logger = logging.getLogger(__name__)


class LazySandboxProxy:
    """按需初始化的沙箱代理，首次调用时才真正分配用户沙箱"""

    def __init__(self, owner: "AgentTaskRunner") -> None:
        self._owner = owner

    async def exec_command(self, session_id: str, exec_dir: str, command: str) -> ToolResult:
        return await (await self._owner._acquire_sandbox()).exec_command(session_id, exec_dir, command)

    async def read_shell_output(self, session_id: str, console: bool = False) -> ToolResult:
        return await (await self._owner._acquire_sandbox()).read_shell_output(session_id, console)

    async def wait_process(self, session_id: str, seconds: Optional[int] = None) -> ToolResult:
        return await (await self._owner._acquire_sandbox()).wait_process(session_id, seconds)

    async def write_shell_input(self, session_id: str, input_text: str, press_enter: bool = True) -> ToolResult:
        return await (await self._owner._acquire_sandbox()).write_shell_input(session_id, input_text, press_enter)

    async def kill_process(self, session_id: str) -> ToolResult:
        return await (await self._owner._acquire_sandbox()).kill_process(session_id)

    async def write_file(
            self,
            filepath: str,
            content: str,
            append: bool = False,
            leading_newline: bool = False,
            trailing_newline: bool = False,
            sudo: bool = False,
    ) -> ToolResult:
        return await (await self._owner._acquire_sandbox()).write_file(
            filepath=filepath,
            content=content,
            append=append,
            leading_newline=leading_newline,
            trailing_newline=trailing_newline,
            sudo=sudo,
        )

    async def read_file(
            self,
            filepath: str,
            start_line: Optional[int] = None,
            end_line: Optional[int] = None,
            sudo: bool = False,
            max_length: int = 10000,
    ) -> ToolResult:
        return await (await self._owner._acquire_sandbox()).read_file(
            filepath=filepath,
            start_line=start_line,
            end_line=end_line,
            sudo=sudo,
            max_length=max_length,
        )

    async def check_file_exists(self, filepath: str) -> ToolResult:
        return await (await self._owner._acquire_sandbox()).check_file_exists(filepath)

    async def delete_file(self, filepath: str) -> ToolResult:
        return await (await self._owner._acquire_sandbox()).delete_file(filepath)

    async def list_files(self, dir_path: str) -> ToolResult:
        return await (await self._owner._acquire_sandbox()).list_files(dir_path)

    async def replace_in_file(self, filepath: str, old_str: str, new_str: str, sudo: bool = False) -> ToolResult:
        return await (await self._owner._acquire_sandbox()).replace_in_file(filepath, old_str, new_str, sudo)

    async def search_in_file(self, filepath: str, regex: str, sudo: bool = False) -> ToolResult:
        return await (await self._owner._acquire_sandbox()).search_in_file(filepath, regex, sudo)

    async def find_files(self, dir_path: str, glob_pattern: str) -> ToolResult:
        return await (await self._owner._acquire_sandbox()).find_files(dir_path, glob_pattern)

    async def upload_file(self, file_data: BinaryIO, filepath: str, filename: str = None) -> ToolResult:
        return await (await self._owner._acquire_sandbox()).upload_file(file_data, filepath, filename)

    async def download_file(self, filepath: str) -> BinaryIO:
        return await (await self._owner._acquire_sandbox()).download_file(filepath)

    async def ensure_sandbox(self) -> None:
        await (await self._owner._acquire_sandbox()).ensure_sandbox()

    async def destroy(self) -> bool:
        sandbox = self._owner._sandbox
        if sandbox is None:
            return True
        return await sandbox.destroy()

    async def get_browser(self) -> Browser:
        return await self._owner._acquire_browser()

    @property
    def id(self) -> str:
        sandbox = self._owner._sandbox
        return sandbox.id if sandbox else ""

    @property
    def cdp_url(self) -> str:
        sandbox = self._owner._sandbox
        return sandbox.cdp_url if sandbox else ""

    @property
    def vnc_url(self) -> str:
        sandbox = self._owner._sandbox
        return sandbox.vnc_url if sandbox else ""


class LazyBrowserProxy:
    """按需初始化的浏览器代理，首次浏览器操作时才申请沙箱浏览器"""

    def __init__(self, owner: "AgentTaskRunner") -> None:
        self._owner = owner

    async def view_page(self) -> ToolResult:
        return await (await self._owner._acquire_browser()).view_page()

    async def navigate(self, url: str) -> ToolResult:
        return await (await self._owner._acquire_browser()).navigate(url)

    async def restart(self, url: str) -> ToolResult:
        return await (await self._owner._acquire_browser()).restart(url)

    async def click(self, index: Optional[int] = None, coordinate_x: Optional[float] = None,
                    coordinate_y: Optional[float] = None) -> ToolResult:
        return await (await self._owner._acquire_browser()).click(index, coordinate_x, coordinate_y)

    async def input(
            self,
            text: str,
            press_enter: bool,
            index: Optional[int] = None,
            coordinate_x: Optional[float] = None,
            coordinate_y: Optional[float] = None,
    ) -> ToolResult:
        return await (await self._owner._acquire_browser()).input(
            text,
            press_enter,
            index,
            coordinate_x,
            coordinate_y,
        )

    async def move_mouse(self, coordinate_x: float, coordinate_y: float) -> ToolResult:
        return await (await self._owner._acquire_browser()).move_mouse(coordinate_x, coordinate_y)

    async def press_key(self, key: str) -> ToolResult:
        return await (await self._owner._acquire_browser()).press_key(key)

    async def select_option(self, index: int, option: int) -> ToolResult:
        return await (await self._owner._acquire_browser()).select_option(index, option)

    async def scroll_up(self, to_top: Optional[bool] = None) -> ToolResult:
        return await (await self._owner._acquire_browser()).scroll_up(to_top)

    async def scroll_down(self, to_down: Optional[bool] = None) -> ToolResult:
        return await (await self._owner._acquire_browser()).scroll_down(to_down)

    async def screenshot(self, full_page: Optional[bool] = None) -> bytes:
        return await (await self._owner._acquire_browser()).screenshot(full_page)

    async def console_exec(self, javascript: str) -> ToolResult:
        return await (await self._owner._acquire_browser()).console_exec(javascript)

    async def console_view(self, max_lines: Optional[int] = None) -> ToolResult:
        return await (await self._owner._acquire_browser()).console_view(max_lines)


class AgentTaskRunner(TaskRunner):
    """基于Agent智能体的任务运行器"""

    def __init__(
            self,
            uow_factory: Callable[[], IUnitOfWork],  # uow模块
            llm: LLM,  # 大语言模型
            agent_config: AgentConfig,  # 智能体配置
            mcp_config: MCPConfig,  # mcp配置
            a2a_config: A2AConfig,  # a2a配置
            session_id: str,  # 会话id
            user_id: str,  # 用户id
            sandbox_preference: SandboxPreference,  # 沙箱偏好
            file_storage: FileStorage,  # 文件存储桶
            json_parser: JSONParser,  # json解析器
            search_engine: SearchEngine,  # 搜索引擎
            sandbox_service: SandboxService,  # 沙箱服务
    ) -> None:
        """构造函数，完成Agent任务运行器的创建"""
        self._uow_factory = uow_factory
        self._uow = uow_factory()
        self._session_id = session_id
        self._user_id = user_id
        self._sandbox_preference = sandbox_preference
        self._sandbox_service = sandbox_service
        self._sandbox: Optional[Sandbox] = None
        self._browser: Optional[Browser] = None
        self._sandbox_lock = asyncio.Lock()
        sandbox_proxy = LazySandboxProxy(self)
        browser_proxy = LazyBrowserProxy(self)
        self._mcp_config = mcp_config
        self._mcp_tool = MCPTool()
        self._a2a_config = a2a_config
        self._a2a_tool = A2ATool()
        self._file_storage = file_storage
        self._flow = PlannerReActFlow(
            uow_factory=uow_factory,
            llm=llm,
            agent_config=agent_config,
            session_id=session_id,
            json_parser=json_parser,
            browser=browser_proxy,
            sandbox=sandbox_proxy,
            search_engine=search_engine,
            mcp_tool=self._mcp_tool,
            a2a_tool=self._a2a_tool,
        )

    async def _acquire_sandbox(self) -> Sandbox:
        if self._sandbox is not None:
            return self._sandbox

        async with self._sandbox_lock:
            if self._sandbox is not None:
                return self._sandbox

            sandbox = await self._sandbox_service.get_session_sandbox(
                user_id=self._user_id,
                session_id=self._session_id,
                sandbox_preference=self._sandbox_preference,
            )
            await sandbox.ensure_sandbox()
            self._sandbox = sandbox

            async with self._uow_factory() as uow:
                session = await uow.session.get_by_id(self._session_id)
                if session is not None:
                    session.sandbox_id = sandbox.id
                    await uow.session.save(session)

            await self._sync_existing_session_files_to_sandbox()
            return sandbox

    async def _acquire_browser(self) -> Browser:
        if self._browser is not None:
            return self._browser

        sandbox = await self._acquire_sandbox()

        async with self._sandbox_lock:
            if self._browser is not None:
                return self._browser
            browser = await sandbox.get_browser()
            if not browser:
                raise RuntimeError(f"获取沙箱[{sandbox.id}]中的浏览器实例失败")
            self._browser = browser
            return browser

    async def _put_and_add_event(self, task: Task, event: Event) -> None:
        """往指定任务的消息队列中添加事件"""
        # 1.往任务的输出消息队列中新增事件
        event_id = await task.output_stream.put(event.model_dump_json())
        event.id = event_id

        # 2.将事件添加到对应的会话中
        async with self._uow:
            await self._uow.session.add_event(self._session_id, event)

    @classmethod
    async def _pop_event(cls, task: Task) -> tuple[str | None, Event | None]:
        """从任务的输入流中获取事件信息"""
        # 1.从任务task中读取数据
        event_id, event_str = await task.input_stream.pop()
        if event_str is None:
            logger.warning(f"AgentTaskRunner接收到空消息")
            return event_id, None

        # 2.使用pydantic+type类型将字符串转换成事件
        event = TypeAdapter(Event).validate_json(event_str)
        event.id = event_id

        return event_id, event

    async def _sync_file_to_sandbox(self, file_id: str) -> File:
        """根据文件id将文件同步到沙箱中"""
        try:
            # 1.调用文件存储下载文件信息
            file_data, file = await self._file_storage.download_file(file_id)

            # 2.组装沙箱文件路径
            filepath = f"{SandboxService.get_upload_dir(self._session_id)}/{file.filename}"

            # 3.调用沙箱将文件上传至沙箱
            tool_result = await self._sandbox.upload_file(
                file_data=file_data,
                filepath=filepath,
                filename=file.filename
            )

            # 4.判断是否上传成功
            if tool_result.success:
                file.filepath = filepath
                async with self._uow:
                    await self._uow.file.save(file)  # 可以更新也可以不更新
                return file
        except AppException:
            raise
        except Exception as e:
            logger.exception(f"AgentTaskRunner同步文件[{file_id}]失败: {str(e)}")

    async def _sync_existing_session_files_to_sandbox(self) -> None:
        """确保当前会话历史文件在本轮执行前可被继续访问"""
        try:
            async with self._uow_factory() as uow:
                session = await uow.session.get_by_id(self._session_id)
            if session is None or not session.files:
                return

            for file in session.files:
                if not file.filepath:
                    continue
                exists_result = await self._sandbox.check_file_exists(file.filepath)
                if exists_result.success and bool((exists_result.data or {}).get("exists")):
                    continue

                try:
                    file_data, latest_file = await self._file_storage.download_file(file.id)
                    tool_result = await self._sandbox.upload_file(
                        file_data=file_data,
                        filepath=file.filepath,
                        filename=latest_file.filename or file.filename,
                    )
                    if tool_result.success:
                        continue
                    logger.warning("会话[%s]历史文件重新同步失败: %s", self._session_id, file.filepath)
                except Exception as exc:
                    logger.warning("会话[%s]历史文件重新同步异常, filepath=%s, error=%s",
                                   self._session_id, file.filepath, exc)
        except Exception as e:
            logger.warning("会话[%s]历史文件预同步失败: %s", self._session_id, e)

    async def _sync_message_attachments_to_sandbox(self, event: MessageEvent) -> None:
        """将消息事件中的附件同步到沙箱中"""
        # 1.定义附件列表
        attachments: List[str] = []

        try:
            # 2.判断消息中是否存在附件
            if event.attachments:
                # 3.循环遍历所有的消息附件
                for attachment in event.attachments:
                    # 4.根据同步文件的id将数据同步到沙箱中
                    file = await self._sync_file_to_sandbox(attachment.id)

                    # 5.文件是否同步成功
                    if file:
                        attachments.append(file)
                        async with self._uow:
                            await self._uow.session.add_file(self._session_id, file)

            # 6.更新消息事件中的attachments
            event.attachments = attachments
        except AppException:
            raise
        except Exception as e:
            logger.exception(f"AgentTaskRunner同步消息附件到沙箱失败: {str(e)}")

    @classmethod
    def _get_stream_size(cls, f: BinaryIO) -> int:
        """根据传递的文件流，获取计算文件的大小"""
        # 1.记录当前文件指针位置
        current_pos = f.tell()

        # 2.将指针移动到文件末尾, seek，0: 偏移量、2: 相对文件末尾
        f.seek(0, 2)

        # 3.获取当前位置，也就是文件大小
        size = f.tell()

        # 4.恢复指针到原始位置
        f.seek(current_pos)

        return size

    async def _sync_file_to_storage(self, filepath: str) -> File:
        """将沙箱中指定的文件路径数据同步到存储桶中"""
        try:
            # 1.根据文件路径从会话中查找文件数据
            async with self._uow:
                file = await self._uow.session.get_file_by_path(self._session_id, filepath)

            # 2.从沙箱中下载文件
            file_data = await self._sandbox.download_file(filepath)

            # 3.判断会话中的文件是否存在
            if file:
                async with self._uow:
                    await self._uow.session.remove_file(self._session_id, file.filepath)

            # 4.提取文件名字、文件信息并更新文件路径
            filename = filepath.split("/")[-1]
            upload_file = UploadFile(
                file=file_data,
                filename=filename,
                size=self._get_stream_size(file_data),
            )

            # 5.上传文件到文件存储桶
            file = await self._file_storage.upload_file(upload_file)
            file.filepath = filepath

            # 6.往会话中新增一个文件信息
            async with self._uow:
                await self._uow.session.add_file(self._session_id, file)
            return file
        except Exception as e:
            logger.exception(f"AgentTaskRunner同步消息附件到文件存储桶失败: {str(e)}")

    async def _sync_message_attachments_to_storage(self, event: MessageEvent) -> None:
        """将消息事件的附件同步到文件存储桶中"""
        # 1.定义附件列表存储数据
        attachments: List[File] = []

        try:
            # 2.判断消息中是否存在附件
            if event.attachments:
                # 3.循环遍历所有附件
                for attachment in event.attachments:
                    # 4.根据文件路径将数据同步到文件存储桶
                    file = await self._sync_file_to_storage(attachment.filepath)
                    if file:
                        attachments.append(file)

            # 5.更新时间中的附件列表资源
            event.attachments = attachments
        except Exception as e:
            logger.exception(f"AgentTaskRunner同步消息附件到存储桶失败: {str(e)}")

    async def _get_browser_screenshot(self) -> str:
        """获取浏览器截图并返回截图文件对应的在线URL"""
        # 1.调用浏览器完成截图
        screenshot = await self._browser.screenshot()

        # 2.将浏览器截图上传到文件存储中
        file = await self._file_storage.upload_file(UploadFile(
            file=io.BytesIO(screenshot),
            filename=f"{str(uuid.uuid4())}.png",
            # bugfix:添加size尺寸
            size=self._get_stream_size(io.BytesIO(screenshot)),
        ))

        # 3.返回模型可直接消费的URL
        return await self._file_storage.get_file_url(file)

    async def _handle_tool_event(self, event: ToolEvent) -> None:
        """额外处理工具消息，使其前端交互更友好"""
        try:
            # 1.如果事件状态为已调用则执行以下代码
            if event.status == ToolEventStatus.CALLED:
                # 2.工具为浏览器则补全工具浏览器工具内容
                if event.tool_name == "browser":
                    event.tool_content = BrowserToolContent(
                        screenshot=await self._get_browser_screenshot(),
                    )
                elif event.tool_name == "search":
                    # 3.工具为搜索则添加搜索工具内容
                    search_results: ToolResult[SearchResults] = event.function_result
                    logger.info(f"搜索工具结果: {search_results}")
                    event.tool_content = SearchToolContent(results=search_results.data.results)
                elif event.tool_name == "shell":
                    # 4.工具为shell则生成shell工具内容
                    if "session_id" in event.function_args:
                        shell_result = await self._sandbox.read_shell_output(
                            event.function_args["session_id"],
                            console=True,
                        )
                        event.tool_content = ShellToolContent(
                            console=(shell_result.data or {}).get("console_records", [])
                        )
                    else:
                        event.tool_content = ShellToolContent(console="(No console)")
                elif event.tool_name == "file":
                    # 5.工具为file则将文件同步到对象存储
                    if "filepath" in event.function_args:
                        filepath = event.function_args["filepath"]
                        file_read_result = await self._sandbox.read_file(filepath)
                        file_content: str = (file_read_result.data or {}).get("content", "")
                        event.tool_content = FileToolContent(content=file_content)
                        # bugfix:修改为同步文件到storage
                        await self._sync_file_to_storage(filepath)
                    else:
                        event.tool_content = FileToolContent(content="(No Content)")
                elif event.tool_name in ["mcp", "a2a"]:
                    # 6.工具为mcp/a2a则处理调用结果
                    logger.info(f"处理MCP/A2A工具事件, function_result: {event.function_result}")
                    if event.function_result:
                        # 7.如果结果包含data则提取data
                        if hasattr(event.function_result, "data") and event.function_result.data:
                            logger.info(f"MCP/A2A工具调用结果: {event.function_result.data}")
                            event.tool_content = MCPToolContent(result=event.function_result.data) \
                                if event.tool_name == "mcp" \
                                else A2AToolContent(a2a_result=event.function_result.data)
                        elif hasattr(event.function_result, "success") and event.function_result.success:
                            # 8.mcp/a2a工具调用正常，但是无结果产生
                            logger.info(f"MCP/A2A工具调用成功返回，但无结果: {event.function_result}")
                            result_data = event.function_result.model_dump() \
                                if hasattr(event.function_result, "model_dump") \
                                else str(event.function_result)
                            event.tool_content = MCPToolContent(result=result_data) \
                                if event.tool_name == "mcp" \
                                else A2AToolContent(a2a_result=result_data)
                        else:
                            # 9.其他情况将结果转换成字符串进行传递
                            logger.info(f"MCP/A2A工具额记过: {event.function_result}")
                            event.tool_content = MCPToolContent(result=str(event.function_result)) \
                                if event.tool_name == "mcp" \
                                else A2AToolContent(a2a_result=str(event.function_result))
                    else:
                        logger.warning("MCP/A2A工具调用结果未发现")
                        event.tool_content = MCPToolContent(result="(MCP工具无可用结果)") \
                            if event.tool_name == "mcp" \
                            else A2AToolContent(a2a_result="(A2A智能体无可用结果)")
        except Exception as e:
            logger.exception(f"AgentTaskRunner生成工具内容失败: {str(e)}")

    async def _run_flow(self, message: Message) -> AsyncGenerator[BaseEvent, None]:
        """根据消息对象运行PlannerReActFlow"""
        # 1.判断传递的消息是否为空
        if not message.message:
            logger.warning(f"AgentTaskRunner接收了一条空消息")
            yield ErrorEvent(error="空消息错误")
            return

        # 2.调用流并运行获取事件信息
        async for event in self._flow.invoke(message):
            # 3.判断是否为工具事件，如果是则额外处理
            if isinstance(event, ToolEvent):
                await self._handle_tool_event(event)
            elif isinstance(event, MessageEvent):
                # 4.如果是消息事件则将AI消息事件中的附件同步到存储中
                await self._sync_message_attachments_to_storage(event)

            # 5.将事件直接返回
            yield event

    async def _cleanup_tools(self) -> None:
        """清理MCP和A2A工具资源，确保在同一任务上下文中释放

        注意：该方法必须在初始化MCP/A2A的同一个asyncio Task中调用，
        否则anyio的cancel scope会检测到任务上下文切换并抛出RuntimeError。
        """
        try:
            if self._mcp_tool:
                await self._mcp_tool.cleanup()
        except Exception as e:
            logger.warning(f"清理MCP工具资源时出错: {e}")
        try:
            if self._a2a_tool:
                await self._a2a_tool.manager.cleanup()
        except Exception as e:
            logger.warning(f"清理A2A工具资源时出错: {e}")

    async def invoke(self, task: Task) -> None:
        """根据传递的任务处理agent消息队列并运行agent流"""
        try:
            # 1.确保沙箱、mcp、a2a均初始化完成
            logger.info(f"AgentTaskRunner任务处理开始")
            await self._mcp_tool.initialize(self._mcp_config)
            await self._a2a_tool.initialize(self._a2a_config)

            # 2.循环读取任务中的输入消息队列
            while not await task.input_stream.is_empty():
                # 3.从输入流中获取数据
                input_event_id, event = await self._pop_event(task)
                if event is None:
                    if input_event_id:
                        await task.input_stream.ack(input_event_id)
                    continue

                message = ""
                should_wait_for_user = False

                # 4.判断事件类型是否为消息事件，如果是则处理消息并将附件同步到沙箱中
                if isinstance(event, MessageEvent):
                    message = event.message or ""
                    await self._sync_message_attachments_to_sandbox(event)
                    logger.info(f"AgentTaskRunner接收到新消息: {message[:50]}...")

                # 5.将消息事件转换称消息对象
                message_obj = Message(
                    message=message,
                    attachments=[
                        MessageAttachment(
                            filepath=attachment.filepath,
                            filename=attachment.filename,
                            mime_type=attachment.mime_type,
                            url=await self._file_storage.get_file_url(attachment),
                        )
                        for attachment in event.attachments
                    ]
                )

                # 6.传递消息对象并运行PlannerReActFlow
                async for event in self._run_flow(message_obj):
                    # 7.将得到的事件添加到消息队列中
                    await self._put_and_add_event(task, event)

                    # 8.如果事件类型为标题事件则更新会话标题
                    if isinstance(event, TitleEvent):
                        async with self._uow:
                            await self._uow.session.update_title(self._session_id, event.title)
                    elif isinstance(event, MessageEvent):
                        # 9.如果事件为消息事件，则更新最新消息并新增未读消息数
                        async with self._uow:
                            await self._uow.session.update_latest_message(
                                self._session_id,
                                event.message,
                                event.created_at,
                            )
                            await self._uow.session.increment_unread_message_count(self._session_id)
                    elif isinstance(event, WaitEvent):
                        # 10.如果事件为等待，则更新会话状态并终止程序
                        async with self._uow:
                            await self._uow.session.update_status(self._session_id, SessionStatus.WAITING)
                        should_wait_for_user = True
                        break

                    # 11.当前输入消息在ACK前仍会留在stream里。
                    # 只有出现“额外的新消息”时才中断当前处理，避免第一条输出后被提前截断。
                    if await task.input_stream.size() > 1:
                        break

                if input_event_id:
                    await task.input_stream.ack(input_event_id)

                if should_wait_for_user:
                    return

            # 12.更新会话状态为已完成
            async with self._uow:
                await self._uow.session.update_status(self._session_id, SessionStatus.COMPLETED)
        except asyncio.CancelledError:
            # 13.异步任务被取消，推送结束事件并跟新状态
            logger.info(f"AgentTaskRunner任务运行取消")
            await self._put_and_add_event(task, DoneEvent())
            async with self._uow:
                await self._uow.session.update_status(self._session_id, SessionStatus.COMPLETED)
            raise
        except Exception as e:
            # 14.记录日志并往任务队列/消息队列中写入异常事件并更新会话状态
            logger.exception(f"AgentTaskRunner运行出错: {str(e)}")
            error_message = e.msg if isinstance(e, AppException) else f"AgentTaskRunner出错: {str(e)}"
            await self._put_and_add_event(task, ErrorEvent(error=error_message))
            async with self._uow:
                await self._uow.session.update_status(self._session_id, SessionStatus.COMPLETED)
        finally:
            # 15.在同一个asyncio Task上下文中清理MCP/A2A工具资源
            # 这是关键：streamablehttp_client内部使用anyio.create_task_group()，
            # 要求在同一个Task中进入和退出cancel scope，
            # 所以必须在invoke()的finally块（即初始化MCP的同一个Task）中清理
            await self._cleanup_tools()

    async def destroy(self) -> None:
        """销毁任务运行器并释放资源"""
        # 1.清除沙箱
        logger.info(f"开始清除销毁AgentTaskRunner资源")
        if self._sandbox:
            logger.info("销毁AgentTaskRunner中的沙箱环境")
            await self._sandbox.destroy()

        # 2.清除mcp和a2a工具（幂等操作，如果invoke()中已清理则不会重复执行）
        await self._cleanup_tools()

    async def on_done(self, task: Task) -> None:
        """任务结束时执行的回调函数"""
        logger.info(f"AgentTaskRunner任务执行结束")
        try:
            if self._sandbox:
                await self._sandbox.destroy()
        except Exception as e:
            logger.warning(f"关闭会话[{self._session_id}]沙箱客户端失败: {e}")

        try:
            async with self._uow_factory() as uow:
                session = await uow.session.get_by_id(self._session_id)
                if session is not None:
                    session.task_id = None
                    await uow.session.save(session)
        except Exception as e:
            logger.warning(f"清理会话[{self._session_id}]沙箱状态失败: {e}")
