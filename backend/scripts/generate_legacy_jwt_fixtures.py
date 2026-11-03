"""Generate legacy python-jose JWT fixtures for PyJWT compatibility tests.

Run only in a scratch environment that has python-jose==3.5.0 installed; it is
not a runtime dependency. The signing key is a synthetic fixture value that is
not used by any runtime configuration, so the generated tokens carry no secret.

Usage: python generate_legacy_jwt_fixtures.py <output.json>
"""

import json
import sys
from importlib.metadata import version
from pathlib import Path

from jose import JWTError
from jose import jwt as jose_jwt

FIXTURE_KEY = "gridsense-legacy-fixture-key-not-a-secret-0123456789"
FAR_FUTURE = 4102444800  # 2100-01-01T00:00:00Z
PAST = 978307200  # 2001-01-01T00:00:00Z

CASES = [
    {
        "name": "access_str_sub",
        "alg": "HS256",
        "claims": {"sub": "42", "type": "access", "exp": FAR_FUTURE},
    },
    {
        "name": "refresh_str_sub",
        "alg": "HS256",
        "claims": {
            "sub": "42",
            "type": "refresh",
            "exp": FAR_FUTURE,
            "iat": 1767225600,
            "jti": "fixture-refresh-0001",
        },
    },
    {
        "name": "access_without_type",
        "alg": "HS256",
        "claims": {"sub": "42", "exp": FAR_FUTURE},
    },
    {
        "name": "access_int_sub",
        "alg": "HS256",
        "claims": {"sub": 42, "type": "access", "exp": FAR_FUTURE},
    },
    {
        "name": "refresh_int_sub",
        "alg": "HS256",
        "claims": {
            "sub": 42,
            "type": "refresh",
            "exp": FAR_FUTURE,
            "iat": 1767225600,
            "jti": "fixture-refresh-0002",
        },
    },
    {
        "name": "access_expired",
        "alg": "HS256",
        "claims": {"sub": "42", "type": "access", "exp": PAST},
    },
    {
        "name": "access_hs512",
        "alg": "HS512",
        "claims": {"sub": "42", "type": "access", "exp": FAR_FUTURE},
    },
    {
        "name": "access_missing_sub",
        "alg": "HS256",
        "claims": {"type": "access", "exp": FAR_FUTURE},
    },
]


def _python_jose_verdict(token: str) -> dict:
    try:
        decoded = jose_jwt.decode(token, FIXTURE_KEY, algorithms=["HS256"])
    except JWTError as exc:
        return {"accepted": False, "error": type(exc).__name__}
    sub = decoded.get("sub")
    return {"accepted": True, "sub": sub, "sub_type": type(sub).__name__}


def main(output_path: str) -> None:
    records = []
    for case in CASES:
        token = jose_jwt.encode(case["claims"], FIXTURE_KEY, algorithm=case["alg"])
        records.append(
            {
                "name": case["name"],
                "algorithm": case["alg"],
                "token": token,
                "python_jose_verdict": _python_jose_verdict(token),
            }
        )
    document = {
        "generator": f"python-jose {version('python-jose')}",
        "fixture_key_label": "synthetic-legacy-v1",
        "cases": records,
    }
    Path(output_path).write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main(sys.argv[1])
