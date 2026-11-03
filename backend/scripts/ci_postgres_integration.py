"""Provision and verify the disposable, restricted PostgreSQL database used by CI integration tests.

``provision`` connects as the service-container administrator (libpq ``PG*`` environment
variables), creates a non-superuser role and a disposable database, and writes
``GRIDSENSE_INTEGRATION_DATABASE_URL`` / ``GRIDSENSE_INTEGRATION_CONFIRM_DATABASE`` to the
given env file (``$GITHUB_ENV`` in Actions). The role password is generated at run time,
registered as a masked value when running inside GitHub Actions, and never printed.

``verify-teardown`` re-connects as the administrator and fails if the test session left any
disposable schema behind, touched the guard schema, or if the role's privileges changed.

Nothing here targets an existing database: provisioning refuses to reuse a role or database
that already exists.
"""

from __future__ import annotations

import argparse
import os
import secrets
import sys
from pathlib import Path

import psycopg2
from psycopg2 import sql
from sqlalchemy.engine import URL

ROLE = "gs_it_ci"
DATABASE = "gridsense_it_ci_test"
GUARD_SCHEMA = "gs_unrelated_guard"
SESSION_SCHEMA_PATTERN = r"gs\_it\_%"
ROLE_PRIVILEGE_FLAGS = (
    "rolsuper",
    "rolcreatedb",
    "rolcreaterole",
    "rolbypassrls",
    "rolreplication",
)
SUPERUSER_BYPASS_ENV = "GRIDSENSE_INTEGRATION_ALLOW_SUPERUSER"
SUPPORTED_SERVER_VERSION = (160000, 170000)


class ProvisionError(RuntimeError):
    """A safety condition for the disposable integration database was not met."""


def role_privilege_violations(attributes: dict[str, bool]) -> list[str]:
    """Return privilege flags that are not explicitly False (a missing flag is a violation)."""
    return [flag for flag in ROLE_PRIVILEGE_FLAGS if attributes.get(flag) is not False]


def refuse_superuser_bypass(environ: dict[str, str] | None = None) -> None:
    env = os.environ if environ is None else environ
    if env.get(SUPERUSER_BYPASS_ENV):
        raise ProvisionError(f"{SUPERUSER_BYPASS_ENV} must not be set in CI")


def _connect(database: str, **overrides: str):
    return psycopg2.connect(dbname=database, connect_timeout=15, **overrides)


def _role_attributes(cur, role: str) -> dict[str, bool] | None:
    columns = ", ".join(ROLE_PRIVILEGE_FLAGS)
    cur.execute(f"SELECT {columns} FROM pg_roles WHERE rolname = %s", (role,))
    row = cur.fetchone()
    return None if row is None else dict(zip(ROLE_PRIVILEGE_FLAGS, row, strict=True))


def provision(env_file: Path) -> None:
    refuse_superuser_bypass()
    host = os.environ.get("PGHOST", "localhost")
    port = int(os.environ.get("PGPORT", "5432"))
    password = secrets.token_hex(24)

    admin = _connect("postgres")
    admin.autocommit = True
    try:
        with admin.cursor() as cur:
            cur.execute("SHOW server_version_num")
            version = int(cur.fetchone()[0])
            low, high = SUPPORTED_SERVER_VERSION
            if not low <= version < high:
                raise ProvisionError(f"PostgreSQL 16 is required, server_version_num={version}")
            cur.execute("SELECT current_user")
            admin_user = cur.fetchone()[0]
            if _role_attributes(cur, ROLE) is not None:
                raise ProvisionError(f"role {ROLE} already exists; refusing to reuse it")
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (DATABASE,))
            if cur.fetchone() is not None:
                raise ProvisionError(f"database {DATABASE} already exists; refusing to reuse it")

            cur.execute(
                sql.SQL(
                    "CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS "
                    "NOREPLICATION NOINHERIT PASSWORD {}"
                ).format(sql.Identifier(ROLE), sql.Literal(password))
            )
            cur.execute(
                sql.SQL("CREATE DATABASE {} OWNER {}").format(
                    sql.Identifier(DATABASE), sql.Identifier(admin_user)
                )
            )
            cur.execute(
                sql.SQL("REVOKE ALL ON DATABASE {} FROM PUBLIC").format(sql.Identifier(DATABASE))
            )
            # CREATE on the database lets the role make its own session schemas, nothing else.
            cur.execute(
                sql.SQL("GRANT CONNECT, CREATE ON DATABASE {} TO {}").format(
                    sql.Identifier(DATABASE), sql.Identifier(ROLE)
                )
            )
    finally:
        admin.close()

    guard = _connect(DATABASE)
    guard.autocommit = True
    try:
        with guard.cursor() as cur:
            cur.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(GUARD_SCHEMA)))
            cur.execute(
                sql.SQL("CREATE TABLE {}.sentinel (id integer)").format(
                    sql.Identifier(GUARD_SCHEMA)
                )
            )
    finally:
        guard.close()

    role_conn = _connect(DATABASE, user=ROLE, password=password, host=host, port=str(port))
    try:
        with role_conn.cursor() as cur:
            attributes = _role_attributes(cur, ROLE)
            violations = role_privilege_violations(attributes or {})
            if violations:
                raise ProvisionError(f"role {ROLE} has forbidden privileges: {violations}")
            cur.execute("SELECT current_user")
            if cur.fetchone()[0] != ROLE:
                raise ProvisionError("integration connection is not the restricted role")
            cur.execute(
                "SELECT has_database_privilege(current_user, %s, 'CREATE'), "
                "has_schema_privilege(current_user, 'public', 'CREATE'), "
                "(SELECT count(*) FROM pg_auth_members WHERE member = "
                "(SELECT oid FROM pg_roles WHERE rolname = current_user))",
                (DATABASE,),
            )
            can_create_schema, can_create_in_public, memberships = cur.fetchone()
            if not can_create_schema or can_create_in_public or memberships:
                raise ProvisionError(
                    "unexpected grants: "
                    f"create_schema={can_create_schema} create_in_public={can_create_in_public} "
                    f"role_memberships={memberships}"
                )
    finally:
        role_conn.close()

    url = URL.create(
        "postgresql+psycopg2",
        username=ROLE,
        password=password,
        host=host,
        port=port,
        database=DATABASE,
    )
    if os.environ.get("GITHUB_ACTIONS") == "true":
        print(f"::add-mask::{password}")
    with env_file.open("a", encoding="utf-8") as handle:
        handle.write(f"GRIDSENSE_INTEGRATION_DATABASE_URL={url.render_as_string(hide_password=False)}\n")
        handle.write(f"GRIDSENSE_INTEGRATION_CONFIRM_DATABASE={DATABASE}\n")
    print(
        f"Provisioned disposable database {DATABASE!r} (PostgreSQL {version // 10000}) "
        f"with restricted role {ROLE!r}: {', '.join(f'{f}=false' for f in ROLE_PRIVILEGE_FLAGS)}; "
        f"guard schema {GUARD_SCHEMA!r} created."
    )


def verify_teardown() -> None:
    admin = _connect(DATABASE)
    admin.autocommit = True
    try:
        with admin.cursor() as cur:
            cur.execute("SELECT nspname FROM pg_namespace WHERE nspname LIKE %s",
                        (SESSION_SCHEMA_PATTERN,))
            leftovers = sorted(row[0] for row in cur.fetchall())
            if leftovers:
                raise ProvisionError(f"disposable schemas were not cleaned up: {leftovers}")

            cur.execute("SELECT current_user")
            admin_user = cur.fetchone()[0]
            cur.execute(
                "SELECT pg_get_userbyid(nspowner) FROM pg_namespace WHERE nspname = %s",
                (GUARD_SCHEMA,),
            )
            owner = cur.fetchone()
            if owner is None or owner[0] != admin_user:
                raise ProvisionError("guard schema is missing or changed owner")
            cur.execute("SELECT tablename FROM pg_tables WHERE schemaname = %s ORDER BY 1",
                        (GUARD_SCHEMA,))
            guard_tables = [row[0] for row in cur.fetchall()]
            if guard_tables != ["sentinel"]:
                raise ProvisionError(f"guard schema contents changed: {guard_tables}")
            cur.execute("SELECT count(*) FROM pg_tables WHERE schemaname = 'public'")
            public_tables = cur.fetchone()[0]
            if public_tables:
                raise ProvisionError(f"{public_tables} table(s) appeared in the public schema")

            violations = role_privilege_violations(_role_attributes(cur, ROLE) or {})
            if violations:
                raise ProvisionError(f"role {ROLE} gained forbidden privileges: {violations}")
    finally:
        admin.close()
    print(
        "Teardown verified: no gs_it_* schemas remain, guard schema untouched, "
        "public schema empty, role still unprivileged."
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    provision_parser = commands.add_parser("provision")
    provision_parser.add_argument("--env-file", type=Path, required=True,
                                  help="file to append KEY=VALUE lines to (use $GITHUB_ENV)")
    commands.add_parser("verify-teardown")
    args = parser.parse_args(argv)
    try:
        if args.command == "provision":
            provision(args.env_file)
        else:
            verify_teardown()
    except (ProvisionError, psycopg2.Error) as exc:
        message = str(exc).strip().splitlines()[0] if str(exc).strip() else type(exc).__name__
        print(f"ERROR ({type(exc).__name__}): {message}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
