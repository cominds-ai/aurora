from pydantic import BaseModel

from app.domain.models.auth import AuthToken, AuthUser


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    token: AuthToken
    user: AuthUser
