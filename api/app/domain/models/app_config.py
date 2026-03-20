import uuid
from copy import deepcopy
from enum import Enum
from typing import Dict, Optional, List, Any

from pydantic import AnyHttpUrl, BaseModel, Field, ConfigDict, model_validator, field_validator


BUILTIN_GEMINI3_PROVIDER_ID = "builtin-gemini3"
BUILTIN_CLAUDE_PROVIDER_ID = "builtin-claude"


class LLMProviderType(str, Enum):
    """模型提供商类型"""
    OPENAI_COMPATIBLE = "openai_compatible"
    GEMINI3 = "gemini3"
    CLAUDE = "claude"


class LLMProviderConfig(BaseModel):
    """单个LLM提供商配置"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    provider: LLMProviderType = LLMProviderType.OPENAI_COMPATIBLE
    name: str = "默认模型提供商"
    base_url: AnyHttpUrl = "https://codex.ysaikeji.cn/v1"
    api_key: str = ""
    model_name: str = "gpt-5.4"
    temperature: float = Field(0.7)
    max_tokens: int = Field(8192, ge=0)
    vision_enabled: bool = True
    builtin: bool = False

    @field_validator("id", "name", "api_key", "model_name", mode="before")
    @classmethod
    def normalize_string(cls, value: Any) -> Any:
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator("name")
    @classmethod
    def ensure_name(cls, value: str) -> str:
        return value or "默认模型提供商"


class LLMConfig(BaseModel):
    """LLM多提供商配置"""
    active_provider_id: Optional[str] = None
    providers: List[LLMProviderConfig] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def migrate_legacy_single_provider(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        if "providers" in value:
            return value

        legacy_provider = LLMProviderConfig(
            id=value.get("id") or "legacy-openai-compatible",
            provider=value.get("provider") or LLMProviderType.OPENAI_COMPATIBLE,
            name=value.get("name") or "历史默认提供商",
            base_url=value.get("base_url", "https://codex.ysaikeji.cn/v1"),
            api_key=value.get("api_key", ""),
            model_name=value.get("model_name", "gpt-5.4"),
            temperature=value.get("temperature", 0.7),
            max_tokens=value.get("max_tokens", 8192),
            vision_enabled=value.get("vision_enabled", True),
            builtin=False,
        )
        return {
            "active_provider_id": legacy_provider.id,
            "providers": [legacy_provider.model_dump()],
        }

    @model_validator(mode="after")
    def validate_provider_config(self) -> "LLMConfig":
        if not self.providers:
            raise ValueError("至少需要配置一个LLM提供商")

        provider_ids = [provider.id for provider in self.providers]
        if len(provider_ids) != len(set(provider_ids)):
            raise ValueError("LLM提供商ID不能重复")

        if not self.active_provider_id or self.active_provider_id not in provider_ids:
            self.active_provider_id = self.providers[0].id
        return self

    def get_active_provider(self) -> LLMProviderConfig:
        for provider in self.providers:
            if provider.id == self.active_provider_id:
                return provider
        return self.providers[0]


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


def build_builtin_llm_providers(
        gemini3_api_key: str = "",
        claude_api_key: str = "",
) -> List[LLMProviderConfig]:
    return [
        LLMProviderConfig(
            id=BUILTIN_GEMINI3_PROVIDER_ID,
            provider=LLMProviderType.GEMINI3,
            name="官方默认gemini3",
            base_url="https://runway.devops.rednote.life/openai/google/v1:generateContent",
            api_key=gemini3_api_key,
            model_name="gemini-3-pro",
            temperature=0.7,
            max_tokens=8192,
            vision_enabled=True,
            builtin=True,
        ),
        LLMProviderConfig(
            id=BUILTIN_CLAUDE_PROVIDER_ID,
            provider=LLMProviderType.CLAUDE,
            name="官方默认claude",
            base_url="https://api.getgoapi.com/v1",
            api_key=claude_api_key,
            model_name="claude-opus-4-5-20251101-thinking",
            temperature=0.7,
            max_tokens=8192,
            vision_enabled=True,
            builtin=True,
        ),
    ]


def build_default_llm_config(
        gemini3_api_key: str = "",
        claude_api_key: str = "",
) -> LLMConfig:
    providers = build_builtin_llm_providers(
        gemini3_api_key=gemini3_api_key,
        claude_api_key=claude_api_key,
    )
    return LLMConfig(
        active_provider_id=providers[0].id,
        providers=providers,
    )


def ensure_builtin_llm_providers(
        llm_config: LLMConfig,
        gemini3_api_key: str = "",
        claude_api_key: str = "",
) -> LLMConfig:
    providers_by_id = {provider.id: provider for provider in llm_config.providers}
    for builtin_provider in build_builtin_llm_providers(
            gemini3_api_key=gemini3_api_key,
            claude_api_key=claude_api_key,
    ):
        if builtin_provider.id not in providers_by_id:
            llm_config.providers.append(deepcopy(builtin_provider))
            continue

        existing = providers_by_id[builtin_provider.id]
        existing.builtin = True
        existing.provider = builtin_provider.provider
        if not existing.name:
            existing.name = builtin_provider.name
        if not existing.base_url:
            existing.base_url = builtin_provider.base_url
        if not existing.model_name:
            existing.model_name = builtin_provider.model_name
        if not existing.api_key.strip():
            existing.api_key = builtin_provider.api_key

    active_provider_ids = {provider.id for provider in llm_config.providers}
    if not llm_config.active_provider_id or llm_config.active_provider_id not in active_provider_ids:
        llm_config.active_provider_id = llm_config.providers[0].id
    return llm_config
