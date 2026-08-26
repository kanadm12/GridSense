"""Chat session and message management service."""

from sqlalchemy.orm import Session

from app.models.chat import ChatSession, ChatMessage
from app.models.meter import Meter


class ChatService:
    """Service for managing chat sessions and messages."""

    def __init__(self, db: Session):
        self.db = db

    def create_session(self, user_id: int, meter_id: int | None, title: str) -> ChatSession:
        """Create a new chat session."""
        session = ChatSession(user_id=user_id, meter_id=meter_id, title=title)
        self.db.add(session)
        self.db.commit()
        self.db.refresh(session)
        return session

    def get_session(self, session_id: int, user_id: int) -> ChatSession | None:
        """Get a chat session by ID, verifying user ownership."""
        return (
            self.db.query(ChatSession)
            .filter(ChatSession.id == session_id, ChatSession.user_id == user_id)
            .first()
        )

    def list_sessions(self, user_id: int, limit: int = 20, offset: int = 0) -> list[ChatSession]:
        """List chat sessions for a user."""
        return (
            self.db.query(ChatSession)
            .filter(ChatSession.user_id == user_id)
            .order_by(ChatSession.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

    def add_message(self, session_id: int, role: str, content: str, tokens_used: int | None = None) -> ChatMessage:
        """Add a message to a chat session."""
        message = ChatMessage(session_id=session_id, role=role, content=content, tokens_used=tokens_used)
        self.db.add(message)
        self.db.commit()
        self.db.refresh(message)
        return message

    def get_session_messages(self, session_id: int, user_id: int) -> list[ChatMessage]:
        """Get all messages in a session, verifying user ownership."""
        session = self.get_session(session_id, user_id)
        if not session:
            return []
        return (
            self.db.query(ChatMessage)
            .filter(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created_at.asc())
            .all()
        )

    def update_session_summary(self, session_id: int, user_id: int, summary: str) -> bool:
        """Update session summary after conversation."""
        session = self.get_session(session_id, user_id)
        if session:
            session.summary = summary
            self.db.add(session)
            self.db.commit()
            return True
        return False

    def delete_session(self, session_id: int, user_id: int) -> bool:
        """Delete a chat session and its messages."""
        session = self.get_session(session_id, user_id)
        if session:
            self.db.delete(session)
            self.db.commit()
            return True
        return False
