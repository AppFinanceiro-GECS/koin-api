"""
Schemas de autenticacao: login, tokens e payloads.
"""

from datetime import datetime

from pydantic import BaseModel, Field

from app.core.email_address import NormalizedEmail


class LoginRequest(BaseModel):
    email: NormalizedEmail
    password: str
    # Nome mostrado em "aparelhos conectados" (ex.: "iPhone de Ana")
    device_name: str | None = Field(None, max_length=100)


class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class TokenPayload(BaseModel):
    sub: str
    type: str
    exp: int


class RefreshRequest(BaseModel):
    refresh_token: str


class SessionResponse(BaseModel):
    id: str
    device_name: str | None
    created_at: datetime
    last_used_at: datetime
    expires_at: datetime
    current: bool = False
