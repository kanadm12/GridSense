"""PyJWT verification against python-jose-issued legacy tokens.

The fixtures in fixtures/auth/legacy_jose_tokens.json were produced by
scripts/generate_legacy_jwt_fixtures.py with python-jose 3.5.0 using a
synthetic key that exists only in this test module.
"""

import json
from pathlib import Path

import pytest

from app.services import auth as auth_module
from app.services.auth import AuthService

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "auth" / "legacy_jose_tokens.json"
FIXTURE_KEY = "gridsense-legacy-fixture-key-not-a-secret-0123456789"

# (requested token type, expected user_id) when PyJWT must accept; None when it must reject.
EXPECTED = {
    "access_str_sub": ("access", 42),
    "refresh_str_sub": ("refresh", 42),
    "access_without_type": ("access", 42),
    "access_int_sub": None,
    "refresh_int_sub": None,
    "access_expired": None,
    "access_hs512": None,
    "access_missing_sub": None,
}


def _load_cases() -> dict:
    document = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    return {case["name"]: case for case in document["cases"]}


@pytest.fixture
def legacy_key(monkeypatch):
    monkeypatch.setattr(auth_module.settings, "secret_key", FIXTURE_KEY)
    monkeypatch.setattr(auth_module.settings, "algorithm", "HS256")


def test_fixture_file_was_produced_by_python_jose():
    document = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    assert document["generator"].startswith("python-jose 3.5.0")
    assert set(_load_cases()) == set(EXPECTED)


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_pyjwt_decodes_legacy_token_as_expected(legacy_key, name):
    case = _load_cases()[name]
    expected = EXPECTED[name]
    if expected is None:
        token_type = "refresh" if "refresh" in name else "access"
        assert AuthService.decode_token(case["token"], expected_type=token_type) is None
        return
    token_type, user_id = expected
    data = AuthService.decode_token(case["token"], expected_type=token_type)
    assert data is not None
    assert data.user_id == user_id
    assert data.token_type == token_type


def test_legacy_string_subject_refresh_rotates_to_new_tokens(legacy_key):
    case = _load_cases()["refresh_str_sub"]
    rotated = AuthService.refresh_access_token(case["token"])
    assert rotated is not None
    new_access, new_refresh = rotated
    # Rotated tokens are issued by PyJWT under the same synthetic key and must verify.
    assert AuthService.decode_token(new_access, "access").user_id == 42
    assert AuthService.decode_token(new_refresh, "refresh").user_id == 42


def test_python_jose_and_pyjwt_agree_on_every_fixture(legacy_key):
    """Parity check: the acceptance decision matches python-jose 3.5.0 for each token."""
    for name, case in _load_cases().items():
        verdict = case["python_jose_verdict"]
        token_type = "refresh" if "refresh" in name else "access"
        pyjwt_accepts = (
            AuthService.decode_token(case["token"], expected_type=token_type) is not None
        )
        if name == "access_without_type":
            # python-jose returns the token; the service defaults a missing type to "access".
            assert pyjwt_accepts is True
            continue
        if name == "access_missing_sub":
            # Both libraries accept the signature; the service rejects a missing subject.
            assert verdict["accepted"] is True and pyjwt_accepts is False
            continue
        assert pyjwt_accepts == verdict["accepted"], name
