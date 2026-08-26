"""Chat-related schemas."""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class MessageRole(str, Enum):
    """Role of the message sender."""
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class ChatMessage(BaseModel):
    """A single chat message."""
    role: MessageRole
    content: str
    timestamp: datetime | None = None


class ChatRequest(BaseModel):
    """Request to send a chat message."""
    message: str = Field(..., min_length=1, max_length=2000)
    conversation_history: list[ChatMessage] | None = None
    meter_id: int | None = Field(None, description="Specific meter to analyze")
    session_id: int | None = Field(None, description="Existing chat session")


class ChatResponse(BaseModel):
    """Response from the AI assistant."""
    message: str
    session_id: int | None = None
    suggestions: list[str] | None = None
    data_referenced: bool = False
    timestamp: datetime = Field(default_factory=datetime.now)


class QuickAction(BaseModel):
    """A quick action suggestion."""
    label: str
    prompt: str
    icon: str | None = None


class ChatWelcome(BaseModel):
    """Welcome message with quick actions."""
    greeting: str
    quick_actions: list[QuickAction]
