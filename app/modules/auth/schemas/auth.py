"""
Schemas de autenticacao: login, tokens e payloads.
"""

from pydantic import BaseModel

from app.core.email_address import NormalizedEmail


class LoginRequest(BaseModel):
    email: NormalizedEmail
    password: str


class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class TokenPayload(BaseModel):
    sub: str
    type: str
    exp: int
