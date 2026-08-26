"""Chat API endpoints."""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.rate_limit import limiter
from app.api.ownership import verify_meter_ownership
from app.database import get_db
from app.models.meter import Meter
from app.models.user import User
from app.schemas.chat import ChatRequest, ChatResponse, ChatWelcome, QuickAction
from app.services.ai_assistant import get_ai_assistant
from app.services.chat_service import ChatService

router = APIRouter(prefix="/chat", tags=["chat"])


@router.get("/welcome", response_model=ChatWelcome)
async def get_welcome(
    current_user: User = Depends(get_current_user),
) -> ChatWelcome:
    """Get welcome message with quick action suggestions."""
    # Determine time-based greeting
    hour = datetime.now().hour
    if hour < 12:
        greeting = "Good morning"
    elif hour < 17:
        greeting = "Good afternoon"
    else:
        greeting = "Good evening"

    return ChatWelcome(
        greeting=f"{greeting}, {current_user.email.split('@')[0]}! I'm your energy assistant. How can I help you today?",
        quick_actions=[
            QuickAction(
                label="Check my usage",
                prompt="How much energy did I use this week?",
                icon="bolt",
            ),
            QuickAction(
                label="Why is my bill high?",
                prompt="Why was my electricity bill high last week?",
                icon="help-circle",
            ),
            QuickAction(
                label="Saving tips",
                prompt="How can I reduce my electricity bill?",
                icon="piggy-bank",
            ),
            QuickAction(
                label="Best time to run appliances",
                prompt="When is the best time to run my dishwasher and washing machine?",
                icon="clock",
            ),
            QuickAction(
                label="Solar rebates",
                prompt="What solar rebates are available in Victoria?",
                icon="sun",
            ),
        ],
    )


@router.post("/message", response_model=ChatResponse)
@limiter.limit("20/minute")
async def send_message(
    request: Request,
    payload: ChatRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ChatResponse:
    """Send a message to the AI assistant.

    The assistant uses:
    - RAG for Victorian energy knowledge
    - User's actual usage data for personalized responses
    """
    assistant = get_ai_assistant(db)
    chat_service = ChatService(db)

    if payload.meter_id is not None:
        verify_meter_ownership(db, payload.meter_id, current_user.id)

    session = None
    if payload.session_id is not None:
        session = chat_service.get_session(payload.session_id, current_user.id)
        if session is None:
            raise HTTPException(status_code=404, detail="Chat session not found")
    else:
        session = chat_service.create_session(
            user_id=current_user.id,
            meter_id=payload.meter_id,
            title=payload.message[:80],
        )

    # Convert conversation history to dict format
    history = None
    if payload.conversation_history:
        history = [
            {"role": msg.role.value, "content": msg.content}
            for msg in payload.conversation_history
        ]
    elif session:
        history = [
            {"role": message.role, "content": message.content}
            for message in chat_service.get_session_messages(session.id, current_user.id)
        ]

    chat_service.add_message(session.id, "user", payload.message)

    try:
        response_text = await assistant.chat(
            user_id=current_user.id,
            message=payload.message,
            conversation_history=history,
            meter_id=payload.meter_id,
        )

        # Check if response references user data
        data_referenced = any(
            phrase in response_text.lower()
            for phrase in ["your usage", "you used", "your bill", "your data", "last week", "yesterday"]
        )

        # Generate follow-up suggestions based on the response
        suggestions = []
        response_lower = response_text.lower()
        
        if "peak" in response_lower or "off-peak" in response_lower:
            suggestions.append("What appliances use the most energy?")
        if "solar" in response_lower:
            suggestions.append("How much could I save with solar panels?")
        if "bill" in response_lower or "cost" in response_lower:
            suggestions.append("Show me my usage breakdown by time of day")
        if "save" in response_lower or "reduce" in response_lower:
            suggestions.append("Set up an automation to help me save")

        chat_service.add_message(session.id, "assistant", response_text)

        return ChatResponse(
            message=response_text,
            session_id=session.id,
            suggestions=suggestions[:3] if suggestions else None,
            data_referenced=data_referenced,
        )

    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to process message: {str(e)}"
        )


@router.get("/history")
async def get_chat_history(
    session_id: int | None = None,
    limit: int = 50,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Get recent persisted chat history for the user."""
    chat_service = ChatService(db)
    if session_id is not None:
        session = chat_service.get_session(session_id, current_user.id)
        if session is None:
            raise HTTPException(status_code=404, detail="Chat session not found")
        messages = chat_service.get_session_messages(session_id, current_user.id)
    else:
        sessions = chat_service.list_sessions(current_user.id, limit=limit, offset=0)
        messages = [message for session in sessions for message in session.messages]

    messages = messages[-limit:]
    return {
        "messages": [
            {
                "id": message.id,
                "session_id": message.session_id,
                "role": message.role,
                "content": message.content,
                "timestamp": message.created_at,
            }
            for message in messages
        ],
        "has_more": len(messages) == limit,
    }
