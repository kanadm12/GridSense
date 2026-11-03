"""Guards that stop the PostgreSQL integration profile from touching non-test data.

These tests do not connect to any database. They exercise the URL validator with
misconfigured values and confirm that it refuses each one before any DDL runs.
"""

from __future__ import annotations

import pytest

from tests.integration.conftest import (
    ALLOW_SUPERUSER_ENV_VAR,
    CONFIRM_ENV_VAR,
    ENV_VAR,
    _assert_restricted_role,
    _redact,
    _validated_admin_url,
)


@pytest.mark.parametrize(
    "url",
    [
        "postgresql+psycopg2://gs:pw@127.0.0.1:55432/gridsense",
        "postgresql+psycopg2://gs:pw@127.0.0.1:55432/gridsense_test_prod",
        "postgresql+psycopg2://gs:pw@127.0.0.1:55432/production",
        "postgresql+psycopg2://gs:pw@127.0.0.1:55432/postgres",
    ],
)
def test_non_disposable_database_names_are_refused(
    monkeypatch: pytest.MonkeyPatch, url: str
) -> None:
    monkeypatch.setenv(ENV_VAR, url)
    with pytest.raises(pytest.UsageError, match="Refusing to run integration tests"):
        _validated_admin_url()


def test_non_postgresql_driver_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ENV_VAR, "sqlite:///C:/tmp/gridsense_test.sqlite3")
    with pytest.raises(pytest.UsageError, match="must be a PostgreSQL URL"):
        _validated_admin_url()


def test_explicit_disposable_database_is_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    url = "postgresql+psycopg2://gs_test:pw@127.0.0.1:55432/gridsense_test"
    monkeypatch.setenv(ENV_VAR, url)
    monkeypatch.setenv(CONFIRM_ENV_VAR, "gridsense_test")
    assert _validated_admin_url() == url


def test_missing_confirmation_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ENV_VAR, "postgresql+psycopg2://gs_test:x@127.0.0.1:55432/gridsense_test")
    monkeypatch.delenv(CONFIRM_ENV_VAR, raising=False)
    with pytest.raises(pytest.UsageError, match=CONFIRM_ENV_VAR):
        _validated_admin_url()


def test_mismatched_confirmation_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ENV_VAR, "postgresql+psycopg2://gs_test:x@127.0.0.1:55432/gridsense_test")
    monkeypatch.setenv(CONFIRM_ENV_VAR, "gridsense_test_other")
    with pytest.raises(pytest.UsageError, match="exact database name"):
        _validated_admin_url()


def test_redaction_removes_password_from_failure_text() -> None:
    raw = "postgresql+psycopg2://gs_test:s3cret-pw@127.0.0.1:55432/gridsense_test"
    redacted = _redact(f"could not connect using {raw} and password s3cret-pw", raw)
    assert "s3cret-pw" not in redacted
    assert "***" in redacted


def test_superuser_role_is_refused_without_explicit_acceptance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Result:
        def scalar_one(self) -> bool:
            return True

    class _Conn:
        def __enter__(self):
            return self

        def __exit__(self, *_exc) -> None:
            return None

        def execute(self, *_args, **_kwargs):
            return _Result()

    class _Engine:
        def connect(self) -> _Conn:
            return _Conn()

    monkeypatch.delenv(ALLOW_SUPERUSER_ENV_VAR, raising=False)
    with pytest.raises(pytest.UsageError, match="superuser"):
        _assert_restricted_role(_Engine())  # type: ignore[arg-type]


def test_unset_variable_skips_instead_of_connecting(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(ENV_VAR, raising=False)
    with pytest.raises(pytest.skip.Exception):
        _validated_admin_url()
