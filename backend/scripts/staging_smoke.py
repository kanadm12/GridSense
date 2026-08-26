#!/usr/bin/env python3
"""Smoke-test the GridSense API against a staging or local environment."""

from __future__ import annotations

import argparse
import csv
import os
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path

import httpx


DEFAULT_BASE_URL = os.getenv("GRID_SENSE_BASE_URL", "http://localhost:8000")


class SmokeTestError(RuntimeError):
    """Raised when a smoke-test expectation is not met."""


def _json_error(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except Exception:
        return response.text
    detail = payload.get("detail") if isinstance(payload, dict) else payload
    return str(detail) if detail else response.text


def _assert_ok(response: httpx.Response, context: str) -> None:
    if response.is_error:
        raise SmokeTestError(f"{context} failed with {response.status_code}: {_json_error(response)}")


def register_user(client: httpx.Client, base_url: str, email: str | None = None) -> tuple[str, str]:
    unique_email = email or f"smoke-{uuid.uuid4().hex[:8]}@example.com"
    payload = {
        "email": unique_email,
        "password": "Testpass123!",
        "full_name": "Smoke Test User",
    }
    response = client.post(f"{base_url}/api/v1/auth/register", json=payload)
    if response.status_code == 201:
        return unique_email, payload["password"]
    if response.status_code == 400 and "already registered" in _json_error(response).lower():
        return unique_email, payload["password"]
    _assert_ok(response, "register")
    return unique_email, payload["password"]


def login_user(client: httpx.Client, base_url: str, email: str, password: str) -> str:
    response = client.post(
        f"{base_url}/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    _assert_ok(response, "login")
    payload = response.json()
    token = payload.get("access_token")
    if not token:
        raise SmokeTestError(f"Login response was missing access_token: {payload}")
    return token


def authenticate(client: httpx.Client, base_url: str) -> tuple[str, str]:
    email, password = register_user(client, base_url)
    token = login_user(client, base_url, email, password)
    return token, email


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def get_nem12_date_range(path: Path) -> tuple[str, str] | None:
    """Return the earliest and latest interval dates in a NEM12 CSV file."""
    dates = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.reader(handle):
            if len(row) > 1 and row[0] == "300":
                try:
                    dates.append(datetime.strptime(row[1], "%Y%m%d").date())
                except ValueError:
                    continue
    if not dates:
        return None
    return min(dates).isoformat(), max(dates).isoformat()


def wait_for_upload_status(client: httpx.Client, base_url: str, token: str, upload_id: int, timeout_seconds: int = 90) -> dict:
    deadline = time.time() + timeout_seconds
    last_status = None

    while time.time() < deadline:
        response = client.get(
            f"{base_url}/api/v1/upload/{upload_id}",
            headers=_auth_headers(token),
        )
        _assert_ok(response, f"upload status for {upload_id}")
        payload = response.json()
        last_status = payload.get("status")
        if last_status == "completed":
            return payload
        if last_status == "failed":
            raise SmokeTestError(f"Upload {upload_id} failed: {payload.get('errors') or payload}")
        time.sleep(2)

    raise SmokeTestError(f"Upload {upload_id} did not complete within {timeout_seconds}s; last status={last_status}")


def wait_for_device_state(
    client: httpx.Client,
    base_url: str,
    token: str,
    device_id: int,
    expected_power: str,
    timeout_seconds: int,
) -> None:
    deadline = time.time() + timeout_seconds

    while time.time() < deadline:
        response = client.get(
            f"{base_url}/api/v1/automation/devices/{device_id}",
            headers=_auth_headers(token),
        )
        _assert_ok(response, f"device status for {device_id}")
        if response.json().get("current_state", {}).get("power") == expected_power:
            return
        time.sleep(2)

    raise SmokeTestError(f"Device {device_id} did not reach power={expected_power} within {timeout_seconds}s")


def validate_authenticated_workflows(
    client: httpx.Client,
    base_url: str,
    token: str,
    meter_id: int,
    timeout_seconds: int,
    start_date: str | None = None,
    end_date: str | None = None,
) -> None:
    headers = _auth_headers(token)

    usage_params = {key: value for key, value in {"start_date": start_date, "end_date": end_date}.items() if value}
    usage_response = client.get(
        f"{base_url}/api/v1/usage/summary/{meter_id}",
        params=usage_params,
        headers=headers,
    )
    _assert_ok(usage_response, "usage summary")
    if usage_response.json().get("meter_id") != meter_id:
        raise SmokeTestError("Usage summary returned a different meter")

    recommendations_response = client.get(f"{base_url}/api/v1/recommendations/{meter_id}", headers=headers)
    _assert_ok(recommendations_response, "recommendations")
    if "recommendations" not in recommendations_response.json():
        raise SmokeTestError("Recommendations response was missing recommendations")

    device_response = client.post(
        f"{base_url}/api/v1/automation/devices",
        headers=headers,
        json={
            "name": "Smoke Test Plug",
            "device_type": "smart_plug",
            "integration_type": "simulator",
            "is_controllable": True,
        },
    )
    _assert_ok(device_response, "create simulator device")
    device_id = device_response.json().get("id")
    if device_id is None:
        raise SmokeTestError("Simulator device response was missing id")

    try:
        command_response = client.post(
            f"{base_url}/api/v1/automation/devices/{device_id}/command",
            headers=headers,
            json={"command": "on"},
        )
        _assert_ok(command_response, "send simulator device command")

        rule_response = client.post(
            f"{base_url}/api/v1/automation/rules",
            headers=headers,
            json={
                "device_id": device_id,
                "name": "Smoke Test Rule",
                "trigger_type": "manual",
                "trigger_conditions": {},
                "action": {"command": "off"},
            },
        )
        _assert_ok(rule_response, "create automation rule")
        rule_id = rule_response.json().get("id")
        if rule_id is None:
            raise SmokeTestError("Automation rule response was missing id")

        run_response = client.post(f"{base_url}/api/v1/automation/rules/{rule_id}/run", headers=headers)
        _assert_ok(run_response, "run automation rule")
        if run_response.json().get("status") != "queued":
            raise SmokeTestError("Automation rule was not queued")
        wait_for_device_state(client, base_url, token, int(device_id), "off", timeout_seconds)
    finally:
        delete_response = client.delete(f"{base_url}/api/v1/automation/devices/{device_id}", headers=headers)
        _assert_ok(delete_response, "delete simulator device")

    welcome_response = client.get(f"{base_url}/api/v1/chat/welcome", headers=headers)
    _assert_ok(welcome_response, "chat welcome")

    chat_response = client.post(
        f"{base_url}/api/v1/chat/message",
        headers=headers,
        json={"message": "How can I reduce my electricity bill?", "meter_id": meter_id},
    )
    _assert_ok(chat_response, "chat message")
    session_id = chat_response.json().get("session_id")
    if session_id is None or not chat_response.json().get("message"):
        raise SmokeTestError("Chat response was missing a session id or message")

    history_response = client.get(
        f"{base_url}/api/v1/chat/history",
        params={"session_id": session_id},
        headers=headers,
    )
    _assert_ok(history_response, "chat history")
    if len(history_response.json().get("messages", [])) < 2:
        raise SmokeTestError("Chat history did not persist the user and assistant messages")


def run_smoke_test(base_url: str, sample_file: str | None = None, timeout_seconds: int = 90) -> int:
    base_url = base_url.rstrip("/")
    client = httpx.Client(timeout=30.0, trust_env=False)

    try:
        live = client.get(f"{base_url}/health/live")
        _assert_ok(live, "liveness probe")

        ready = client.get(f"{base_url}/health/ready")
        _assert_ok(ready, "readiness probe")

        token, _ = authenticate(client, base_url)

        meters_response = client.get(
            f"{base_url}/api/v1/meters",
            headers=_auth_headers(token),
        )
        _assert_ok(meters_response, "list meters")

        if sample_file:
            path = Path(sample_file)
            if not path.exists():
                raise SmokeTestError(f"Sample file not found: {path}")
            sample_date_range = get_nem12_date_range(path)
            with path.open("rb") as handle:
                upload_response = client.post(
                    f"{base_url}/api/v1/upload",
                    files={"file": (path.name, handle.read(), "text/csv")},
                    headers={"Authorization": f"Bearer {token}"},
                )
            _assert_ok(upload_response, "NEM12 upload")
            upload_payload = upload_response.json()
            upload_id = upload_payload.get("upload_id")
            if upload_id is None:
                raise SmokeTestError(f"Upload response missing upload_id: {upload_payload}")
            wait_for_upload_status(client, base_url, token, int(upload_id), timeout_seconds=timeout_seconds)

            meters_response = client.get(f"{base_url}/api/v1/meters", headers=_auth_headers(token))
            _assert_ok(meters_response, "list imported meters")
            meters = meters_response.json()
            if not meters or meters[0].get("id") is None:
                raise SmokeTestError("No meter was created from the NEM12 upload")
            validate_authenticated_workflows(
                client,
                base_url,
                token,
                int(meters[0]["id"]),
                timeout_seconds,
                *(sample_date_range or (None, None)),
            )

        print(f"Smoke test passed against {base_url}")
        return 0
    except Exception as exc:  # pragma: no cover - CLI error path
        print(f"Smoke test failed: {exc}", file=sys.stderr)
        return 1
    finally:
        client.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a smoke test against the GridSense API.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="API base URL, e.g. http://localhost:8000")
    parser.add_argument(
        "--sample-file",
        default=str((Path(__file__).resolve().parents[1] / "tests" / "sample_nem12.csv")),
        help="Optional NEM12 sample file to upload during the smoke test.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=90,
        help="How long to wait for upload processing before failing.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    return run_smoke_test(
        base_url=args.base_url,
        sample_file=args.sample_file,
        timeout_seconds=args.timeout_seconds,
    )


if __name__ == "__main__":
    raise SystemExit(main())
