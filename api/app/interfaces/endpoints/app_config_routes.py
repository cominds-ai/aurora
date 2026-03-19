import logging
from typing import Optional, Dict

from fastapi import APIRouter, Depends, Body, HTTPException

from app.application.services.app_config_service import AppConfigService
from app.application.services.sandbox_service import SandboxService
from app.domain.models.system_config import SystemConfig
from app.domain.models.app_config import LLMConfig, AgentConfig, MCPConfig, SearchConfig, SandboxPreference
from app.domain.models.user import User
from app.interfaces.schemas.app_config import ListMCPServerResponse, ListA2AServerResponse, ListSandboxOptionResponse, \
    SandboxOptionItem, SandboxPreferenceStatusResponse, LLMConfigResponse, SearchConfigResponse, \
    SystemSandboxPoolResponse
from app.interfaces.schemas.base import Response
from app.interfaces.service_dependencies import get_app_config_service, get_sandbox_service, get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/app-config", tags=["设置模块"])


def ensure_sandbox_pool_admin(current_user: User) -> None:
    if current_user.username != "fh":
        raise HTTPException(status_code=403, detail="当前用户无权管理沙箱池")


@router.get(
    path="/llm",
    response_model=Response[LLMConfigResponse],
    summary="获取LLM配置信息",
    description="包含LLM提供商的base_url、temperature、model_name、max_tokens"
)
async def get_llm_config(
        app_config_service: AppConfigService = Depends(get_app_config_service)
) -> Response[LLMConfigResponse]:
    """获取LLM配置信息"""
    llm_config = await app_config_service.get_llm_config()
    return Response.success(data=LLMConfigResponse(
        **llm_config.model_dump(mode="json", exclude={"api_key"}),
        api_key_configured=bool(llm_config.api_key.strip()),
    ))


@router.post(
    path="/llm",
    response_model=Response[LLMConfigResponse],
    summary="更新LLM配置信息",
    description="更新LLM配置信息，当api_key为空的时候表示不更新该字段"
)
async def update_llm_config(
        new_llm_config: LLMConfig,
        app_config_service: AppConfigService = Depends(get_app_config_service)
) -> Response[LLMConfigResponse]:
    """更新LLM配置信息"""
    updated_llm_config = await app_config_service.update_llm_config(new_llm_config)
    return Response.success(
        msg="更新LLM信息配置成功",
        data=LLMConfigResponse(
            **updated_llm_config.model_dump(mode="json", exclude={"api_key"}),
            api_key_configured=bool(updated_llm_config.api_key.strip()),
        )
    )


@router.get(
    path="/search",
    response_model=Response[SearchConfigResponse],
    summary="获取搜索配置",
)
async def get_search_config(
        app_config_service: AppConfigService = Depends(get_app_config_service),
) -> Response[SearchConfigResponse]:
    search_config = await app_config_service.get_search_config()
    return Response.success(data=SearchConfigResponse(
        **search_config.model_dump(mode="json", exclude={"api_key"}),
        api_key_configured=bool(search_config.api_key.strip()),
    ))


@router.post(
    path="/search",
    response_model=Response[SearchConfigResponse],
    summary="更新搜索配置",
)
async def update_search_config(
        new_search_config: SearchConfig,
        app_config_service: AppConfigService = Depends(get_app_config_service),
) -> Response[SearchConfigResponse]:
    updated_search_config = await app_config_service.update_search_config(new_search_config)
    return Response.success(
        data=SearchConfigResponse(
            **updated_search_config.model_dump(mode="json", exclude={"api_key"}),
            api_key_configured=bool(updated_search_config.api_key.strip()),
        ),
        msg="更新搜索配置成功",
    )


@router.get(
    path="/agent",
    response_model=Response[AgentConfig],
    summary="获取Agent通用配置信息",
    description="包含最大迭代次数、最大重试次数、最大搜索结果数"
)
async def get_agent_config(
        app_config_service: AppConfigService = Depends(get_app_config_service)
) -> Response[AgentConfig]:
    """获取Agent通用配置信息"""
    agent_config = await app_config_service.get_agent_config()
    return Response.success(data=agent_config.model_dump())


@router.post(
    path="/agent",
    response_model=Response[AgentConfig],
    summary="更新Agent通用配置信息",
    description="更新Agent通用配置信息"
)
async def update_llm_config(
        new_agent_config: AgentConfig,
        app_config_service: AppConfigService = Depends(get_app_config_service)
) -> Response[AgentConfig]:
    """更新Agent配置信息"""
    updated_agent_config = await app_config_service.update_agent_config(new_agent_config)
    return Response.success(
        msg="更新Agent信息配置成功",
        data=updated_agent_config.model_dump()
    )


@router.get(
    path="/sandbox-preference",
    response_model=Response[SandboxPreference],
    summary="获取沙箱偏好配置",
)
async def get_sandbox_preference(
        app_config_service: AppConfigService = Depends(get_app_config_service),
) -> Response[SandboxPreference]:
    sandbox_preference = await app_config_service.get_sandbox_preference()
    return Response.success(data=sandbox_preference.model_dump())


@router.get(
    path="/sandbox-preference/status",
    response_model=Response[SandboxPreferenceStatusResponse],
    summary="获取沙箱偏好配置状态",
)
async def get_sandbox_preference_status(
        current_user: User = Depends(get_current_user),
        app_config_service: AppConfigService = Depends(get_app_config_service),
        sandbox_service: SandboxService = Depends(get_sandbox_service),
) -> Response[SandboxPreferenceStatusResponse]:
    sandbox_preference = await app_config_service.get_sandbox_preference()
    status = await sandbox_service.inspect_preference(current_user.id, sandbox_preference)
    if status.needs_reconfigure and sandbox_preference.preferred_sandbox_host:
        await app_config_service.update_sandbox_preference(SandboxPreference())
        status.preferred_sandbox_host = None
        status.configured = False

    return Response.success(
        data=SandboxPreferenceStatusResponse(
            preferred_sandbox_host=status.preferred_sandbox_host,
            configured=status.configured,
            connected=status.connected,
            needs_reconfigure=status.needs_reconfigure,
            message=status.message,
        )
    )


@router.post(
    path="/sandbox-preference",
    response_model=Response[SandboxPreference],
    summary="更新沙箱偏好配置",
)
async def update_sandbox_preference(
        sandbox_preference: SandboxPreference,
        current_user: User = Depends(get_current_user),
        app_config_service: AppConfigService = Depends(get_app_config_service),
        sandbox_service: SandboxService = Depends(get_sandbox_service),
) -> Response[SandboxPreference]:
    normalized_preference = SandboxPreference(
        preferred_sandbox_host=sandbox_preference.preferred_sandbox_host
    )
    if normalized_preference.preferred_sandbox_host:
        await sandbox_service.validate_manual_host(normalized_preference.preferred_sandbox_host)

    updated = await app_config_service.update_sandbox_preference(normalized_preference)
    return Response.success(data=updated.model_dump(), msg="更新沙箱偏好成功")


@router.get(
    path="/sandboxes",
    response_model=Response[ListSandboxOptionResponse],
    summary="获取可选沙箱列表",
)
async def list_sandboxes(
        sandbox_service: SandboxService = Depends(get_sandbox_service),
) -> Response[ListSandboxOptionResponse]:
    sandboxes = await sandbox_service.list_sandbox_pool_status()
    return Response.success(
        data=ListSandboxOptionResponse(
            sandboxes=[
                SandboxOptionItem(
                    sandbox_id=item.sandbox_id,
                    label=item.label,
                    host=item.host,
                    available=item.available,
                    healthy=item.healthy,
                    bound_user_id=item.bound_user_id,
                    bound_session_id=item.bound_session_id,
                )
                for item in sandboxes
            ]
        )
    )


@router.get(
    path="/system/sandbox-pool",
    response_model=Response[SystemSandboxPoolResponse],
    summary="获取系统沙箱池配置",
)
async def get_system_sandbox_pool(
        current_user: User = Depends(get_current_user),
        sandbox_service: SandboxService = Depends(get_sandbox_service),
) -> Response[SystemSandboxPoolResponse]:
    ensure_sandbox_pool_admin(current_user)
    system_config = await sandbox_service.get_system_sandbox_pool()
    return Response.success(data=SystemSandboxPoolResponse(sandbox_pool=system_config.sandbox_pool))


@router.post(
    path="/system/sandbox-pool",
    response_model=Response[SystemSandboxPoolResponse],
    summary="更新系统沙箱池配置",
)
async def update_system_sandbox_pool(
        request: SystemSandboxPoolResponse,
        current_user: User = Depends(get_current_user),
        sandbox_service: SandboxService = Depends(get_sandbox_service),
) -> Response[SystemSandboxPoolResponse]:
    ensure_sandbox_pool_admin(current_user)
    system_config = await sandbox_service.update_system_sandbox_pool(request.sandbox_pool)
    return Response.success(
        msg="系统沙箱池配置更新成功",
        data=SystemSandboxPoolResponse(sandbox_pool=system_config.sandbox_pool),
    )


@router.get(
    path="/mcp-servers",
    response_model=Response[ListMCPServerResponse],
    summary="获取MCP服务器工具列表",
    description="获取当前系统的MCP服务器列表，包含MCP服务名字、工具列表、启用状态等",
)
async def get_mcp_servers(
        app_config_service: AppConfigService = Depends(get_app_config_service),
) -> Response[ListMCPServerResponse]:
    """获取当前系统的MCP服务器工具列表"""
    mcp_servers = await app_config_service.get_mcp_servers()
    return Response.success(
        msg="获取mcp服务器列表成功",
        data=ListMCPServerResponse(mcp_servers=mcp_servers)
    )


@router.post(
    path="/mcp-servers",
    response_model=Response[Optional[Dict]],
    summary="新增MCP服务配置，支持传递一个或者多个配置",
    description="传递MCP配置信息为系统新增MCP工具",
)
async def create_mcp_servers(
        mcp_config: MCPConfig,
        app_config_service: AppConfigService = Depends(get_app_config_service),
) -> Response[Optional[Dict]]:
    """根据传递的配置信息创建mcp服务"""
    await app_config_service.update_and_create_mcp_servers(mcp_config)
    return Response.success(msg="新增MCP服务配置成功")


@router.post(
    path="/mcp-servers/{server_name}/delete",
    response_model=Response[Optional[Dict]],
    summary="删除MCP服务配置",
    description="根据传递的MCP服务名字删除指定的MCP服务",
)
async def delete_mcp_server(
        server_name: str,
        app_config_service: AppConfigService = Depends(get_app_config_service),
) -> Response[Optional[Dict]]:
    """根据服务名字删除MCP服务器"""
    await app_config_service.delete_mcp_server(server_name)
    return Response.success(msg="删除MCP服务配置成功")


@router.post(
    path="/mcp-servers/{server_name}/enabled",
    response_model=Response[Optional[Dict]],
    summary="更新MCP服务的启用状态",
    description="根据传递的server_name+enabled更新指定MCP服务的启用状态",
)
async def set_mcp_server_enabled(
        server_name: str,
        enabled: bool = Body(..., embed=True),
        app_config_service: AppConfigService = Depends(get_app_config_service),
) -> Response[Optional[Dict]]:
    """根据传递的server_name+enabled更新服务的启用状态"""
    await app_config_service.set_mcp_server_enabled(server_name, enabled)
    return Response.success(msg="更新MCP服务启用状态成功")


@router.get(
    path="/a2a-servers",
    response_model=Response[ListA2AServerResponse],
    summary="获取a2a服务器列表",
    description="获取Aurora项目中的所有已配置的a2a服务列表",
)
async def get_a2a_servers(
        app_config_service: AppConfigService = Depends(get_app_config_service),
) -> Response[ListA2AServerResponse]:
    """获取a2a服务列表"""
    a2a_servers = await app_config_service.get_a2a_servers()
    return Response.success(
        msg="获取a2a服务列表成功",
        data=ListA2AServerResponse(a2a_servers=a2a_servers)
    )


@router.post(
    path="/a2a-servers",
    response_model=Response[Optional[Dict]],
    summary="新增a2a服务器",
    description="为Aurora项目新增a2a服务器",
)
async def create_a2a_server(
        base_url: str = Body(..., embed=True),
        app_config_service: AppConfigService = Depends(get_app_config_service),
) -> Response[Optional[Dict]]:
    """新增a2a服务器"""
    await app_config_service.create_a2a_server(base_url)
    return Response.success(msg="新增A2A服务配置成功")


@router.post(
    path="/a2a-servers/{a2a_id}/delete",
    response_model=Response[Optional[Dict]],
    summary="删除a2a服务器",
    description="根据A2A服务id标识删除指定的A2A服务"
)
async def delete_a2a_server(
        a2a_id: str,
        app_config_service: AppConfigService = Depends(get_app_config_service),
) -> Response[Optional[Dict]]:
    """删除a2a服务器"""
    await app_config_service.delete_a2a_server(a2a_id)
    return Response.success(msg="删除a2a服务器成功")


@router.post(
    path="/a2a-servers/{a2a_id}/enabled",
    response_model=Response[Optional[Dict]],
    summary="更新A2A服务的启用状态",
    description="启动or禁用A2A服务的状态",
)
async def set_a2a_server_enabled(
        a2a_id: str,
        enabled: bool = Body(..., embed=True),
        app_config_service: AppConfigService = Depends(get_app_config_service),
) -> Response[Optional[Dict]]:
    """更新A2A服务的启用状态"""
    await app_config_service.set_a2a_server_enabled(a2a_id, enabled)
    return Response.success(msg="更新a2a服务器启用状态成功")
