"""Schemas do cadastro pelo código de evento."""

from typing import Literal

from pydantic import BaseModel, Field

from app.core.email_address import NormalizedEmail


class EventSignupCreate(BaseModel):
    code: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=2, max_length=100)
    email: NormalizedEmail
    password: str = Field(min_length=8, max_length=72)
    accept_terms: Literal[True]
    marketing_opt_in: bool = False


class EventSignupVerify(BaseModel):
    code: str = Field(pattern=r"^\d{6}$")


class EventSignupStatus(BaseModel):
    source: str
    ticket_number: int
    name: str
    email: str
    email_verified: bool
    marketing_opt_in: bool
    gift_delivered: bool
