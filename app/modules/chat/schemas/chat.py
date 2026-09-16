"""Schemas para o Agente IA Financeiro"""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class MessageRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class ChatMessage(BaseModel):
    role: MessageRole
    content: str
    timestamp: datetime = Field(default_factory=datetime.now)


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    conversation_id: str | None = None


class ChatResponse(BaseModel):
    message: str
    conversation_id: str
    suggestions: list[str] = []
    data_used: list[str] = []  # Lista de dados usados para gerar resposta


class ConversationSummary(BaseModel):
    conversation_id: str
    title: str
    last_message: str
    created_at: datetime
    updated_at: datetime
    message_count: int
