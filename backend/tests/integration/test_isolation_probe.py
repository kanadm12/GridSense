"""Runtime proof that integration tests stay inside the schema this session created."""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Engine


def _attempt_ddl(engine: Engine, statement: str) -> str | None:
    """Run one DDL statement in a rolled-back transaction; return the error, or None on success."""
    with engine.connect() as conn:
        trans = conn.begin()
        try:
            conn.execute(text(statement))
        except Exception as exc:  # noqa: BLE001 - the error text is the evidence
            trans.rollback()
            return str(exc).splitlines()[0]
        trans.rollback()
        return None


def test_session_schema_is_owned_by_integration_role(pg_engine: Engine, pg_schema_name: str):
    with pg_engine.connect() as conn:
        owner_matches = conn.execute(
            text(
                "SELECT pg_get_userbyid(nspowner) = current_user "
                "FROM pg_namespace WHERE nspname = :schema"
            ),
            {"schema": pg_schema_name},
        ).scalar_one()
        search_schema = conn.execute(text("SELECT current_schema()")).scalar_one()
    assert owner_matches is True
    assert search_schema == pg_schema_name


def test_integration_role_is_not_superuser_and_cannot_manage_roles_or_databases(pg_engine: Engine):
    with pg_engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT rolsuper, rolcreatedb, rolcreaterole, rolbypassrls "
                "FROM pg_roles WHERE rolname = current_user"
            )
        ).one()
    assert row == (False, False, False, False), f"unexpected role attributes: {row}"
    role_error = _attempt_ddl(pg_engine, "CREATE ROLE gs_probe_intruder LOGIN")
    assert role_error is not None and "permission denied" in role_error


def test_role_cannot_write_to_public_or_any_schema_it_does_not_own(pg_engine: Engine):
    with pg_engine.connect() as conn:
        foreign = conn.execute(
            text(
                "SELECT nspname FROM pg_namespace "
                "WHERE nspname NOT LIKE 'pg\\_%' AND nspname <> 'information_schema' "
                "AND pg_get_userbyid(nspowner) <> current_user ORDER BY nspname"
            )
        ).scalars().all()
    targets = sorted(set(foreign) | {"public"})
    assert "public" in targets
    unexpected = []
    for schema in targets:
        error = _attempt_ddl(pg_engine, f'CREATE TABLE "{schema}".gs_isolation_probe (id int)')
        if error is None or "permission denied" not in error:
            unexpected.append(f"{schema}: {error}")
    assert not unexpected, f"restricted role could create tables in: {unexpected}"
