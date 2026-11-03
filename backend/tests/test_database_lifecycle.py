"""Regression tests for the request-scoped database session lifecycle."""

from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session, sessionmaker

from app import database


def test_get_db_does_not_issue_schema_ddl_and_releases_connection(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{(tmp_path / 'lifecycle.sqlite3').as_posix()}")
    factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    monkeypatch.setattr(database, "SessionLocal", factory)

    generator: Iterator[Session] = database.get_db()
    try:
        session = next(generator)
        assert session.get_bind() is engine
        assert inspect(engine).get_table_names() == []
    finally:
        generator.close()

    try:
        assert engine.pool.checkedout() == 0
        assert inspect(engine).get_table_names() == []
    finally:
        engine.dispose()


def test_get_db_closes_session_when_request_raises(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{(tmp_path / 'lifecycle_error.sqlite3').as_posix()}")
    factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    monkeypatch.setattr(database, "SessionLocal", factory)

    generator = database.get_db()
    next(generator)
    with pytest.raises(RuntimeError):
        generator.throw(RuntimeError("request failed"))
    try:
        assert engine.pool.checkedout() == 0
    finally:
        engine.dispose()
