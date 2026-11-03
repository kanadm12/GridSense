"""Release security gate for pip-audit and Trivy results.

Fails when any reported vulnerability is not covered by an APPROVED,
unexpired entry in the risk-acceptance register. It also fails when Trivy
does not list every package pinned in the application lock, so an empty or
partial dependency scan can never pass as clean.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

BLOCKING_TRIVY_SEVERITIES_EXEMPT = {"LOW"}
LOCK_PIN = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)==")


def normalize(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def load_lock_packages(lock_path: Path) -> set[str]:
    names = set()
    for line in lock_path.read_text(encoding="utf-8").splitlines():
        match = LOCK_PIN.match(line)
        if match:
            names.add(normalize(match.group(1)))
    return names


PLACEHOLDER_REVIEWER = re.compile(
    r"\b(pending|tbd|todo|placeholder|unknown|none|approval)\b", re.IGNORECASE
)
# (scanner, advisory ID, normalised package, installed version)
Finding = tuple[str, str, str, str]


def _valid_date(value: object) -> bool:
    try:
        date.fromisoformat(str(value))
    except ValueError:
        return False
    return True


def approval_problem(entry: dict, today: date) -> str | None:
    """Return why an APPROVED entry cannot suppress findings, or None if it can."""
    reviewer = str(entry.get("approved_by") or "").strip()
    if not reviewer:
        return "missing approved_by"
    if PLACEHOLDER_REVIEWER.search(reviewer):
        return "approved_by is a placeholder"
    if not _valid_date(entry.get("approved_on")):
        return "missing or invalid approved_on date"
    if not str(entry.get("evidence") or "").strip():
        return "missing evidence"
    if not str(entry.get("scope") or "").strip():
        return "missing scope"
    if not str(entry.get("installed_version") or "").strip():
        return "missing installed_version"
    if not _valid_date(entry.get("review_by")):
        return "missing or invalid review_by date"
    if date.fromisoformat(str(entry["review_by"])) < today:
        return f"expired on {entry['review_by']}"
    if not isinstance(entry.get("advisory_ids"), list) or not entry["advisory_ids"]:
        return "no advisory_ids"
    return None


def load_approvals(register_path: Path, today: date) -> tuple[set[Finding], list[str]]:
    data = json.loads(register_path.read_text(encoding="utf-8"))
    approved: set[Finding] = set()
    rejected: list[str] = []
    for entry in data.get("acceptances", []):
        if entry.get("status") != "APPROVED":
            continue
        problem = approval_problem(entry, today)
        if problem:
            rejected.append(f"{entry.get('id', '<no id>')}: {problem}")
            continue
        for advisory in entry["advisory_ids"]:
            approved.add(
                (
                    entry["scanner"],
                    advisory,
                    normalize(entry["package"]),
                    entry["installed_version"],
                )
            )
    return approved, rejected


def pip_audit_findings(report_path: Path) -> list[Finding]:
    data = json.loads(report_path.read_text(encoding="utf-8"))
    findings: list[Finding] = []
    for dep in data.get("dependencies", []):
        for vuln in dep.get("vulns", []):
            findings.append(
                ("pip-audit", vuln["id"], normalize(dep["name"]), str(dep.get("version", "")))
            )
    return findings


def trivy_findings(report_path: Path) -> list[tuple[str, str, str, str, str]]:
    """Return (severity, advisory, package, installed version, fixed version)."""
    data = json.loads(report_path.read_text(encoding="utf-8"))
    findings = []
    for result in data.get("Results", []):
        for vuln in result.get("Vulnerabilities", []):
            findings.append(
                (
                    vuln.get("Severity", "UNKNOWN"),
                    vuln["VulnerabilityID"],
                    normalize(vuln["PkgName"]),
                    str(vuln.get("InstalledVersion", "")),
                    vuln.get("FixedVersion", ""),
                )
            )
    return findings


def trivy_package_names(packages_path: Path) -> set[str]:
    data = json.loads(packages_path.read_text(encoding="utf-8"))
    names = set()
    for result in data.get("Results", []):
        for pkg in result.get("Packages", []):
            names.add(normalize(pkg["Name"]))
    return names


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lock", required=True, type=Path)
    parser.add_argument("--register", required=True, type=Path)
    parser.add_argument("--pip-audit", required=True, type=Path)
    parser.add_argument("--trivy", required=True, type=Path)
    parser.add_argument("--trivy-packages", required=True, type=Path)
    parser.add_argument("--today", type=date.fromisoformat, default=date.today())
    args = parser.parse_args()

    lock_packages = load_lock_packages(args.lock)
    scanned_packages = trivy_package_names(args.trivy_packages)
    missing = sorted(lock_packages - scanned_packages)
    print(f"Lock pins: {len(lock_packages)}; Trivy recognised packages: {len(scanned_packages)}")
    if not scanned_packages or missing:
        print(f"FAIL: Trivy did not recognise {len(missing)} locked package(s): {missing[:20]}")
        return 1

    approvals, rejected = load_approvals(args.register, args.today)
    for item in rejected:
        print(f"REJECTED register entry (does not suppress findings): {item}")
    unaccepted: list[str] = []

    for scanner, advisory, package, version in pip_audit_findings(args.pip_audit):
        if (scanner, advisory, package, version) not in approvals:
            unaccepted.append(f"pip-audit {advisory} {package} {version}")

    # Unknown severities fail closed. Only LOW is non-blocking.
    for severity, advisory, package, version, fixed in trivy_findings(args.trivy):
        if severity in BLOCKING_TRIVY_SEVERITIES_EXEMPT:
            continue
        if ("trivy", advisory, package, version) not in approvals:
            unaccepted.append(
                f"trivy {severity} {advisory} {package} {version} (fixed={fixed or 'none'})"
            )

    print(f"Unaccepted findings: {len(unaccepted)}")
    for item in unaccepted:
        print(f"  - {item}")
    if unaccepted:
        print("FAIL: unaccepted vulnerabilities block the security gate.")
        return 1
    print("PASS: every reported finding is covered by an approved, unexpired exception.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
