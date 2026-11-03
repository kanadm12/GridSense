"""Fixtures for PostgreSQL integration tests.

The suite runs only when ``GRIDSENSE_INTEGRATION_DATABASE_URL`` points at a
disposable PostgreSQL database. Each session creates its own schema, applies the
complete Alembic chain inside it, and drops it at the end. Tests never touch the
default SQLite database or any schema outside the one created here.
"""

from __future__ import annotations

import os
import subprocess
import sys
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session, sessionmaker

ENV_VAR = "GRIDSENSE_INTEGRATION_DATABASE_URL"
CONFIRM_ENV_VAR = "GRIDSENSE_INTEGRATION_CONFIRM_DATABASE"
ALLOW_SUPERUSER_ENV_VAR = "GRIDSENSE_INTEGRATION_ALLOW_SUPERUSER"
BACKEND_DIR = Path(__file__).resolve().parents[2]


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "integration: requires a disposable PostgreSQL database")


def _validated_admin_url() -> str:
    """Return the configured URL only if it names an explicitly confirmed disposable database."""
    raw = os.environ.get(ENV_VAR)
    if not raw:
        pytest.skip(f"{ENV_VAR} not set; PostgreSQL integration profile not executed")

    url = make_url(raw)
    if not url.drivername.startswith("postgresql"):
        raise pytest.UsageError(f"{ENV_VAR} must be a PostgreSQL URL, got {url.drivername!r}")
    database = (url.database or "").lower()
    if "test" not in database or database in {"gridsense", "gridsense_test_prod"}:
        raise pytest.UsageError(
            f"Refusing to run integration tests against database {url.database!r}; "
            "the name must be an explicitly disposable test database containing 'test'."
        )
    if os.environ.get(CONFIRM_ENV_VAR, "") != url.database:
        raise pytest.UsageError(
            f"Set {CONFIRM_ENV_VAR} to the exact database name {url.database!r} to confirm "
            "that it is disposable."
        )
    return raw


def _redact(message: str, raw_url: str) -> str:
    """Remove the password from any text that may be echoed in a failure message."""
    password = make_url(raw_url).password
    return message.replace(password, "***") if password else message


def _assert_restricted_role(engine: Engine) -> None:
    """Refuse superuser roles unless explicitly accepted, because they can modify any schema."""
    with engine.connect() as conn:
        is_super = conn.execute(
            text("SELECT rolsuper FROM pg_roles WHERE rolname = current_user")
        ).scalar_one()
    if is_super and os.environ.get(ALLOW_SUPERUSER_ENV_VAR) != "1":
        raise pytest.UsageError(
            "The integration role is a superuser and could modify unrelated schemas. "
            f"Use a restricted role, or set {ALLOW_SUPERUSER_ENV_VAR}=1 to accept this risk."
        )


@pytest.fixture(scope="session")
def pg_schema_name() -> Iterator[str]:
    """Create an isolated schema, verify ownership, migrate it to head, and drop it afterwards."""
    admin_url = _validated_admin_url()
    admin_engine: Engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    _assert_restricted_role(admin_engine)
    schema = f"gs_it_{uuid.uuid4().hex[:12]}"

    with admin_engine.connect() as conn:
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        owner_matches = conn.execute(
            text(
                "SELECT pg_get_userbyid(nspowner) = current_user "
                "FROM pg_namespace WHERE nspname = :schema"
            ),
            {"schema": schema},
        ).scalar_one()
    if not owner_matches:
        admin_engine.dispose()
        raise AssertionError("created test schema is not owned by the integration role")

    schema_url = make_url(admin_url).update_query_dict({"options": f"-csearch_path={schema}"})
    env = os.environ.copy()
    env["DATABASE_URL"] = schema_url.render_as_string(hide_password=False)
    try:
        result = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=BACKEND_DIR,
            env=env,
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )
        if result.returncode != 0:
            # Only the tail is kept, with the password removed, so the URL never leaks.
            tail = "\n".join(result.stderr.strip().splitlines()[-20:])
            raise RuntimeError(
                f"alembic upgrade head failed (exit {result.returncode}):\n"
                f"{_redact(tail, admin_url)}"
            )
        yield schema
    finally:
        # Drop only the schema this session created and verified above.
        with admin_engine.connect() as conn:
            conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        admin_engine.dispose()


@pytest.fixture(scope="session")
def pg_schema_url(pg_schema_name: str) -> str:
    admin_url = _validated_admin_url()
    search_path = f"-csearch_path={pg_schema_name}"
    schema_url = make_url(admin_url).update_query_dict({"options": search_path})
    return schema_url.render_as_string(hide_password=False)


@pytest.fixture(scope="session")
def pg_engine(pg_schema_url: str) -> Iterator[Engine]:
    engine = create_engine(pg_schema_url, pool_pre_ping=True)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture(scope="session")
def pg_session_factory(pg_engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(autocommit=False, autoflush=False, bind=pg_engine)


@pytest.fixture
def pg_db(
    pg_engine: Engine, pg_schema_name: str, pg_session_factory: sessionmaker[Session]
) -> Iterator[Session]:
    """Provide a clean schema per test by truncating application tables in that schema only."""
    from app.models.base import Base

    tables = [t.name for t in Base.metadata.sorted_tables if t.name != "alembic_version"]
    with pg_engine.begin() as conn:
        active_schema = conn.execute(text("SELECT current_schema()")).scalar_one()
        if active_schema != pg_schema_name:
            raise AssertionError(
                f"refusing to truncate: connection schema {active_schema!r} "
                f"!= expected test schema {pg_schema_name!r}"
            )
        if tables:
            joined = ", ".join(f'"{pg_schema_name}"."{name}"' for name in tables)
            conn.execute(text(f"TRUNCATE TABLE {joined} RESTART IDENTITY CASCADE"))

    session = pg_session_factory()
    try:
        yield session
    finally:
        session.close()

    if pg_engine.pool.checkedout() != 0:
        raise AssertionError(
            f"{pg_engine.pool.checkedout()} PostgreSQL connection(s) still checked out after test"
        )


@pytest.fixture
def client(pg_session_factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch):
    """TestClient wired to the PostgreSQL schema with deterministic background work."""
    from fastapi.testclient import TestClient
    from slowapi import Limiter
    from slowapi.util import get_remote_address

    import app.tasks as tasks
    from app.api import upload as upload_module
    from app.database import get_db
    from app.main import app
    from app.rate_limit import limiter

    limiter.reset()
    unlimited = Limiter(key_func=get_remote_address, default_limits=[])
    monkeypatch.setattr(app.state, "limiter", unlimited)

    def override_get_db() -> Iterator[Session]:
        db = pg_session_factory()
        try:
            yield db
        finally:
            db.close()

    monkeypatch.setitem(app.dependency_overrides, get_db, override_get_db)
    monkeypatch.setattr(upload_module, "SessionLocal", pg_session_factory)
    monkeypatch.setattr(tasks, "SessionLocal", pg_session_factory)

    def _queue_unavailable(*_args, **_kwargs):
        raise ConnectionError("integration profile: Redis queue disabled; using in-process import")

    monkeypatch.setattr(tasks, "enqueue_import", _queue_unavailable)

    with TestClient(app) as test_client:
        yield test_client

    limiter.reset()
