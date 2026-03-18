import uuid
from enum import Enum
from typing import Dict, Optional, List, Any

from pydantic import AnyHttpUrl, BaseModel, Field, ConfigDict, model_validator, field_validator


class LLMConfig(BaseModel):
    """LLM提供商配置"""
    base_url: AnyHttpUrl = "https://codex.ysaikeji.cn/v1"  # 模型基础URL地址
    api_key: str = ""  # 模型API秘钥
    model_name: str = "gpt-5.4"  # 模型名字
    temperature: float = Field(0.7)  # 温度，默认设置为0.7
    max_tokens: int = Field(8192, ge=0)  # 最大输出token数
    vision_enabled: bool = True  # 是否允许直接读取图片


class AgentConfig(BaseModel):
    """Agent通用配置"""
    max_iterations: int = Field(default=100, gt=0, lt=1000)  # Agent最大迭代次数
    max_retries: int = Field(default=3, gt=1, lt=10)  # 最大重试次数
    max_search_results: int = Field(default=10, gt=1, lt=30)  # 最大搜索结果条数


class SearchProvider(str, Enum):
    """搜索提供商"""
    SERPAPI_GOOGLE = "serpapi_google"


class SearchConfig(BaseModel):
    """搜索配置"""
    provider: SearchProvider = SearchProvider.SERPAPI_GOOGLE
    api_key: str = ""
    engine: str = "google"
    gl: str = "cn"
    hl: str = "zh-cn"


class SandboxPreference(BaseModel):
    """用户沙箱偏好配置"""
    preferred_sandbox_host: Optional[str] = None

    @field_validator("preferred_sandbox_host", mode="before")
    @classmethod
    def normalize_optional_string(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        value = value.strip()
        return value or None


class MCPTransport(str, Enum):
    """MCP传输类型枚举"""
    STDIO = "stdio"  # 本地输入输出
    SSE = "sse"  # 流式事件
    STREAMABLE_HTTP = "streamable_http"  # 流式HTTP


class MCPServerConfig(BaseModel):
    """MCP服务配置"""
    # 通用配置字段
    transport: MCPTransport = MCPTransport.STREAMABLE_HTTP  # 传输协议
    enabled: bool = True  # 是否开启，默认为True
    description: Optional[str] = None  # 服务器描述
    env: Optional[Dict[str, Any]] = None  # 环境变量配置

    # stdio配置
    command: Optional[str] = None  # 启用命令
    args: Optional[List[str]] = None  # 命令参数

    # streamable_http&sse配置
    url: Optional[str] = None  # MCP服务URL地址
    headers: Optional[Dict[str, Any]] = None  # MCP服务请求头

    model_config = ConfigDict(extra="allow")

    @model_validator(mode="after")
    def validate_mcp_server_config(self):
        """校验mcp_server_config的相关信息，包含url+command"""
        # 1.判断transport是否为sse/streamable_http
        if self.transport in [MCPTransport.SSE, MCPTransport.STREAMABLE_HTTP]:
            # 2.这两种模式需要传递url
            if not self.url:
                raise ValueError("在sse或streamable_http模式下必须传递url")

        # 3.判断transport是否为stdio类型
        if self.transport == MCPTransport.STDIO:
            # 4.stdio类型必须传递command
            if not self.command:
                raise ValueError("在stdio模式下必须传递command")

        return self


class MCPConfig(BaseModel):
    """应用MCP配置"""
    mcpServers: Dict[str, MCPServerConfig] = Field(default_factory=dict)

    model_config = ConfigDict(extra="allow", arbitrary_types_allowed=True)


class A2AServerConfig(BaseModel):
    """A2A服务配置"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))  # 唯一标识
    base_url: str  # 服务基础URL
    enabled: bool = True  # 服务是否开启


class A2AConfig(BaseModel):
    """A2A配置"""
    a2a_servers: List[A2AServerConfig] = Field(default_factory=list)


class AppConfig(BaseModel):
    """应用配置信息，包含Agent配置、LLM提供商配置、搜索、MCP、A2A和沙箱偏好"""
    llm_config: LLMConfig  # 语言模型配置
    agent_config: AgentConfig  # Agent通用配置
    search_config: SearchConfig = Field(default_factory=SearchConfig)
    mcp_config: MCPConfig  # MCP服务配置
    a2a_config: A2AConfig  # A2A服务配置
    sandbox_preference: SandboxPreference = Field(default_factory=SandboxPreference)

    # Pydantic配置，允许传递额外的字段初始化
    model_config = ConfigDict(extra="allow")
