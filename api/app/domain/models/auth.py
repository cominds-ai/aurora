from pydantic import BaseModel


class AuthToken(BaseModel):
    """认证令牌"""

    access_token: str
    token_type: str = "bearer"


class AuthUser(BaseModel):
    """登录态用户信息"""

    id: str
    username: str
    display_name: str


class LoginResult(BaseModel):
    """登录结果"""

    token: AuthToken
    user: AuthUser
