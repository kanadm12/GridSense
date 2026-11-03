"""Approval-policy tests for scripts/security_gate.py.

All reports and register entries are synthetic. They exercise the gate's
decision rules only and do not record any real acceptance.
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import pytest

from scripts import security_gate

TODAY = date(2026, 11, 3)
PKG = "examplepkg"
VERSION = "9.9.9"
ADVISORY = "SYN-0001"


def _write_json(path: Path, data: object) -> Path:
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _approved_entry(**overrides: object) -> dict:
    entry: dict = {
        "id": "SYN-RA-001",
        "scanner": "pip-audit",
        "package": PKG,
        "installed_version": VERSION,
        "advisory_ids": [ADVISORY],
        "scope": "synthetic package version only",
        "status": "APPROVED",
        "approved_by": "Synthetic Reviewer",
        "approved_on": "2026-10-01",
        "review_by": "2026-12-31",
        "evidence": "backend/tests/test_security_gate.py",
    }
    entry.update(overrides)
    return entry


def _pip_audit_report(
    *, vuln_id: str = ADVISORY, name: str = PKG, version: str = VERSION
) -> dict:
    return {
        "dependencies": [
            {"name": name, "version": version, "vulns": [{"id": vuln_id}]},
        ]
    }


def _trivy_report(
    *,
    severity: str = "CRITICAL",
    vuln_id: str = ADVISORY,
    name: str = PKG,
    version: str = VERSION,
) -> dict:
    return {
        "Results": [
            {
                "Vulnerabilities": [
                    {
                        "Severity": severity,
                        "VulnerabilityID": vuln_id,
                        "PkgName": name,
                        "InstalledVersion": version,
                        "FixedVersion": "",
                    }
                ]
            }
        ]
    }


def _run_gate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    entries: list[dict],
    pip_audit: dict | None = None,
    trivy: dict | None = None,
    lock_packages: list[str] | None = None,
    today: date = TODAY,
    capsys: pytest.CaptureFixture[str],
) -> tuple[int, str]:
    names = [PKG] if lock_packages is None else lock_packages
    lock = tmp_path / "requirements-dev.lock"
    lock.write_text("".join(f"{name}=={VERSION} \\\n    --hash=sha256:0\n" for name in names))
    register = _write_json(tmp_path / "register.json", {"acceptances": entries})
    pip_path = _write_json(tmp_path / "pip-audit.json", pip_audit or {"dependencies": []})
    trivy_path = _write_json(tmp_path / "trivy.json", trivy or {"Results": []})
    packages_path = _write_json(
        tmp_path / "trivy-packages.json",
        {"Results": [{"Packages": [{"Name": name} for name in names]}]},
    )
    argv = [
        "security_gate.py",
        "--lock",
        str(lock),
        "--register",
        str(register),
        "--pip-audit",
        str(pip_path),
        "--trivy",
        str(trivy_path),
        "--trivy-packages",
        str(packages_path),
        "--today",
        today.isoformat(),
    ]
    monkeypatch.setattr(sys, "argv", argv)
    code = security_gate.main()
    return code, capsys.readouterr().out


def test_proposed_entry_does_not_suppress_findings(tmp_path, monkeypatch, capsys):
    entry = _approved_entry(status="PROPOSED")
    code, out = _run_gate(
        tmp_path, monkeypatch, entries=[entry], pip_audit=_pip_audit_report(), capsys=capsys
    )
    assert code == 1
    assert "FAIL" in out


@pytest.mark.parametrize(
    "overrides",
    [
        {"approved_by": None},
        {"approved_by": ""},
        {"approved_by": "Project maintainer — approval pending"},
        {"approved_by": "TBD"},
        {"approved_by": "none"},
        {"approved_on": None},
        {"approved_on": "not-a-date"},
        {"evidence": ""},
        {"evidence": None},
        {"scope": ""},
        {"review_by": None},
        {"review_by": "2026-13-45"},
    ],
)
def test_invalid_approval_is_rejected_and_reported(tmp_path, monkeypatch, capsys, overrides):
    entry = _approved_entry(**overrides)
    code, out = _run_gate(
        tmp_path, monkeypatch, entries=[entry], pip_audit=_pip_audit_report(), capsys=capsys
    )
    assert code == 1
    assert "REJECTED register entry" in out
    assert "SYN-RA-001" in out


def test_expired_approval_is_rejected(tmp_path, monkeypatch, capsys):
    entry = _approved_entry(review_by="2026-11-02")
    code, out = _run_gate(
        tmp_path, monkeypatch, entries=[entry], pip_audit=_pip_audit_report(), capsys=capsys
    )
    assert code == 1
    assert "expired on 2026-11-02" in out


def test_approval_expiring_today_is_still_honoured(tmp_path, monkeypatch, capsys):
    entry = _approved_entry(review_by=TODAY.isoformat())
    code, _ = _run_gate(
        tmp_path, monkeypatch, entries=[entry], pip_audit=_pip_audit_report(), capsys=capsys
    )
    assert code == 0


def test_correct_precisely_scoped_approval_passes(tmp_path, monkeypatch, capsys):
    code, out = _run_gate(
        tmp_path,
        monkeypatch,
        entries=[_approved_entry()],
        pip_audit=_pip_audit_report(),
        capsys=capsys,
    )
    assert code == 0
    assert "PASS" in out
    assert "REJECTED" not in out


def test_correct_trivy_scoped_approval_passes(tmp_path, monkeypatch, capsys):
    entry = _approved_entry(scanner="trivy")
    code, out = _run_gate(
        tmp_path,
        monkeypatch,
        entries=[entry],
        trivy=_trivy_report(),
        capsys=capsys,
    )
    assert code == 0
    assert "PASS" in out


@pytest.mark.parametrize(
    "pip_audit, trivy",
    [
        (_pip_audit_report(name="otherpkg"), None),
        (_pip_audit_report(version="9.9.8"), None),
        (_pip_audit_report(vuln_id="SYN-0002"), None),
        (None, _trivy_report(name="otherpkg")),
        (None, _trivy_report(version="9.9.8")),
        (None, _trivy_report(vuln_id="SYN-0002")),
    ],
)
def test_approval_does_not_match_other_package_version_or_advisory(
    tmp_path, monkeypatch, capsys, pip_audit, trivy
):
    code, out = _run_gate(
        tmp_path,
        monkeypatch,
        entries=[_approved_entry()],
        pip_audit=pip_audit,
        trivy=trivy,
        capsys=capsys,
    )
    assert code == 1
    assert "Unaccepted findings: 1" in out


def test_scanner_must_match(tmp_path, monkeypatch, capsys):
    # A pip-audit approval must not suppress a Trivy finding for the same advisory.
    code, out = _run_gate(
        tmp_path,
        monkeypatch,
        entries=[_approved_entry(scanner="pip-audit")],
        trivy=_trivy_report(),
        capsys=capsys,
    )
    assert code == 1
    assert "trivy CRITICAL SYN-0001" in out


def test_unknown_new_vulnerability_still_fails(tmp_path, monkeypatch, capsys):
    code, out = _run_gate(
        tmp_path,
        monkeypatch,
        entries=[_approved_entry()],
        pip_audit=_pip_audit_report(),
        trivy=_trivy_report(vuln_id="SYN-9999", severity="HIGH"),
        capsys=capsys,
    )
    assert code == 1
    assert "SYN-9999" in out


@pytest.mark.parametrize("severity", ["UNKNOWN", "MEDIUM", "HIGH", "CRITICAL"])
def test_trivy_findings_block_unless_approved(tmp_path, monkeypatch, capsys, severity):
    code, _ = _run_gate(
        tmp_path, monkeypatch, entries=[], trivy=_trivy_report(severity=severity), capsys=capsys
    )
    assert code == 1


def test_trivy_low_severity_is_non_blocking(tmp_path, monkeypatch, capsys):
    code, _ = _run_gate(
        tmp_path, monkeypatch, entries=[], trivy=_trivy_report(severity="LOW"), capsys=capsys
    )
    assert code == 0


def test_clean_scan_passes_with_no_entries(tmp_path, monkeypatch, capsys):
    code, out = _run_gate(tmp_path, monkeypatch, entries=[], capsys=capsys)
    assert code == 0
    assert "PASS" in out


def test_lock_pin_missing_from_trivy_recognition_fails(tmp_path, monkeypatch, capsys):
    # Trivy recognises only `examplepkg`, but the lock also pins `missingpkg`.
    lock_names = [PKG, "missingpkg"]
    lock = tmp_path / "requirements-dev.lock"
    lock.write_text("".join(f"{n}=={VERSION}\n" for n in lock_names))
    packages = _write_json(
        tmp_path / "trivy-packages.json", {"Results": [{"Packages": [{"Name": PKG}]}]}
    )
    register = _write_json(tmp_path / "register.json", {"acceptances": []})
    empty = _write_json(tmp_path / "empty.json", {"Results": []})
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "security_gate.py",
            "--lock",
            str(lock),
            "--register",
            str(register),
            "--pip-audit",
            str(empty),
            "--trivy",
            str(empty),
            "--trivy-packages",
            str(packages),
        ],
    )
    assert security_gate.main() == 1
    assert "missingpkg" in capsys.readouterr().out


def test_empty_trivy_recognition_fails(tmp_path, monkeypatch, capsys):
    code, out = _run_gate(
        tmp_path, monkeypatch, entries=[], lock_packages=[], capsys=capsys
    )
    assert code == 1
    assert "did not recognise" in out


def test_load_approvals_returns_version_bound_tuples(tmp_path):
    register = _write_json(tmp_path / "register.json", {"acceptances": [_approved_entry()]})
    approvals, rejected = security_gate.load_approvals(register, TODAY)
    assert approvals == {("pip-audit", ADVISORY, PKG, VERSION)}
    assert rejected == []
