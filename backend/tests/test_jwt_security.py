"""JWT validation regression tests for the PyJWT-based AuthService."""

import base64
import hashlib
import hmac
import json
from datetime import timedelta

import jwt
import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app
from app.services.auth import AuthService

settings = get_settings()


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _unsigned_token(payload: dict, alg: str = "none") -> str:
    header = _b64url(json.dumps({"alg": alg, "typ": "JWT"}).encode())
    body = _b64url(json.dumps(payload).encode())
    return f"{header}.{body}."


def _tamper_signature(token: str) -> str:
    head, body, sig = token.split(".")
    flipped = "A" if sig[-1] != "A" else "B"
    return f"{head}.{body}.{sig[:-1]}{flipped}"


class TestTokenRoundTrip:
    def test_access_token_round_trip(self):
        token = AuthService.create_access_token(data={"sub": "42"})
        data = AuthService.decode_token(token, expected_type="access")
        assert data is not None
        assert data.user_id == 42
        assert data.token_type == "access"

    def test_refresh_token_carries_claims(self):
        token = AuthService.create_refresh_token(data={"sub": "7"})
        claims = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        assert claims["type"] == "refresh"
        assert isinstance(claims["iat"], int)
        assert claims["jti"]
        data = AuthService.decode_token(token, expected_type="refresh")
        assert data is not None and data.user_id == 7

    def test_refresh_token_rejected_as_access(self):
        token = AuthService.create_refresh_token(data={"sub": "7"})
        assert AuthService.decode_token(token, expected_type="access") is None

    def test_access_token_rejected_as_refresh(self):
        token = AuthService.create_access_token(data={"sub": "7"})
        assert AuthService.decode_token(token, expected_type="refresh") is None

    def test_refresh_rotation_still_works(self):
        refresh = AuthService.create_refresh_token(data={"sub": "9"})
        rotated = AuthService.refresh_access_token(refresh)
        assert rotated is not None
        new_access, new_refresh = rotated
        assert AuthService.decode_token(new_access, "access").user_id == 9
        assert AuthService.decode_token(new_refresh, "refresh").user_id == 9


class TestInvalidTokens:
    def test_expired_access_token_rejected(self):
        token = AuthService.create_access_token(
            data={"sub": "1"}, expires_delta=timedelta(minutes=-5)
        )
        assert AuthService.decode_token(token) is None

    def test_expired_refresh_token_rejected(self):
        token = jwt.encode(
            {"sub": "1", "type": "refresh", "exp": 1, "iat": 1, "jti": "x"},
            settings.secret_key,
            algorithm=settings.algorithm,
        )
        assert AuthService.decode_token(token, expected_type="refresh") is None

    def test_tampered_signature_rejected(self):
        token = AuthService.create_access_token(data={"sub": "1"})
        assert AuthService.decode_token(_tamper_signature(token)) is None

    def test_tampered_payload_rejected(self):
        token = AuthService.create_access_token(data={"sub": "1"})
        head, _, sig = token.split(".")
        forged_body = _b64url(
            json.dumps({"sub": "2", "type": "access", "exp": 4102444800}).encode()
        )
        assert AuthService.decode_token(f"{head}.{forged_body}.{sig}") is None

    def test_wrong_secret_rejected(self):
        token = jwt.encode(
            {"sub": "1", "type": "access", "exp": 4102444800},
            "a-different-secret-that-is-long-enough-1234567890",
            algorithm=settings.algorithm,
        )
        assert AuthService.decode_token(token) is None

    def test_alg_none_rejected(self):
        token = _unsigned_token({"sub": "1", "type": "access", "exp": 4102444800})
        assert AuthService.decode_token(token) is None

    def test_hs512_not_in_allowlist_rejected(self):
        token = jwt.encode(
            {"sub": "1", "type": "access", "exp": 4102444800},
            settings.secret_key,
            algorithm="HS512",
        )
        assert AuthService.decode_token(token) is None

    def test_missing_subject_rejected(self):
        token = jwt.encode(
            {"type": "access", "exp": 4102444800},
            settings.secret_key,
            algorithm=settings.algorithm,
        )
        assert AuthService.decode_token(token) is None

    def test_non_string_subject_rejected(self):
        token = jwt.encode(
            {"sub": 5, "type": "access", "exp": 4102444800},
            settings.secret_key,
            algorithm=settings.algorithm,
        )
        assert AuthService.decode_token(token) is None

    @pytest.mark.parametrize(
        "token",
        ["", "not-a-jwt", "a.b.c", "a.b", "....", "eyJhbGciOiJIUzI1NiJ9.!!!.sig"],
    )
    def test_malformed_tokens_rejected(self, token):
        assert AuthService.decode_token(token) is None

    def test_standard_hs256_token_accepted(self):
        """A standards-conformant HS256 token with the configured secret is accepted."""
        header = _b64url(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
        body = _b64url(json.dumps({"sub": "3", "type": "access", "exp": 4102444800}).encode())
        signing_input = f"{header}.{body}".encode()
        digest = hmac.new(settings.secret_key.encode(), signing_input, hashlib.sha256).digest()
        sig = _b64url(digest)
        data = AuthService.decode_token(f"{header}.{body}.{sig}")
        assert data is not None and data.user_id == 3


class TestProtectedEndpointRejections:
    """Invalid credentials must yield 401 at the protected endpoint boundary."""

    @pytest.mark.parametrize(
        "token",
        [
            "not-a-jwt",
            _unsigned_token({"sub": "1", "type": "access", "exp": 4102444800}),
            _tamper_signature(AuthService.create_access_token(data={"sub": "1"})),
            AuthService.create_access_token(data={"sub": "1"}, expires_delta=timedelta(minutes=-5)),
            AuthService.create_refresh_token(data={"sub": "1"}),
        ],
        ids=["malformed", "alg-none", "tampered", "expired", "refresh-as-access"],
    )
    def test_me_rejects_invalid_bearer(self, token):
        with TestClient(app) as client:
            response = client.get(
                "/api/v1/auth/me",
                headers={"Authorization": f"Bearer {token}"},
            )
        assert response.status_code == 401
