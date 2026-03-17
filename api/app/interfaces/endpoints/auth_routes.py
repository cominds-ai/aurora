from fastapi import APIRouter, Depends

from app.application.services.auth_service import AuthService
from app.domain.models.auth import AuthUser
from app.interfaces.schemas import Response
from app.interfaces.schemas.auth import LoginRequest, LoginResponse
from app.interfaces.service_dependencies import get_auth_service, get_current_user

router = APIRouter(prefix="/auth", tags=["认证模块"])


@router.post(
    path="/login",
    response_model=Response[LoginResponse],
    summary="登录或自动注册",
)
async def login(
        request: LoginRequest,
        auth_service: AuthService = Depends(get_auth_service),
) -> Response[LoginResponse]:
    result = await auth_service.login(request.username, request.password)
    return Response.success(data=LoginResponse(token=result.token, user=result.user))


@router.get(
    path="/me",
    response_model=Response[AuthUser],
    summary="当前登录用户",
)
async def me(
        current_user=Depends(get_current_user),
) -> Response[AuthUser]:
    return Response.success(
        data=AuthUser(
            id=current_user.id,
            username=current_user.username,
            display_name=current_user.display_name,
        )
    )
