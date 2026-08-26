"""Database connection and session management."""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings

settings = get_settings()

# Configure engine based on database type
connect_args = {}
if settings.database_url.startswith("sqlite"):
    connect_args = {"check_same_thread": False}
    engine = create_engine(settings.database_url, connect_args=connect_args)
else:
    engine = create_engine(
        settings.database_url,
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=20,
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    """Dependency that provides a database session."""
    db = SessionLocal()
    # Ensure tables exist for the bound engine (helps in-memory SQLite used in tests)
    try:
        from app.models import Base  # noqa: E402

        bind = db.get_bind()
        if bind is not None:
            Base.metadata.create_all(bind=bind)
    except Exception:
        # If models can't be imported or creation fails, continue and let callers handle errors
        pass
    try:
        yield db
    finally:
        db.close()
