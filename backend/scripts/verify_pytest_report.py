"""Fail CI unless every collected PostgreSQL integration test actually ran and passed.

Inputs are machine-readable: the pytest JUnit XML for the full run, and the node ids printed
by ``pytest tests/integration --collect-only -q`` (one ``path::name`` per line). The expected
integration cases are whatever the collection step reports, so the check keeps working as the
suite grows; it never hardcodes a test count.

Fails when:
  * no integration test was collected, or an ``integration/test_*.py`` module contributed none;
  * a collected integration case is missing from the report or did not pass;
  * any test anywhere in the run was skipped, failed or errored;
  * the restricted-database environment is absent, or the superuser bypass flag is set.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

DATABASE_ENV = "GRIDSENSE_INTEGRATION_DATABASE_URL"
CONFIRM_ENV = "GRIDSENSE_INTEGRATION_CONFIRM_DATABASE"
SUPERUSER_BYPASS_ENV = "GRIDSENSE_INTEGRATION_ALLOW_SUPERUSER"
NODE_ID = re.compile(r"^(?P<path>[^\s:][^:\[]*\.py)::\S.*$")


@dataclass(frozen=True)
class Case:
    classname: str
    name: str
    outcome: str  # passed | skipped | failed | error


@dataclass
class Verdict:
    total: int = 0
    passed: int = 0
    skipped: int = 0
    failed: int = 0
    errors: int = 0
    integration_expected: int = 0
    integration_passed: int = 0
    problems: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems


def junit_key(node_id: str) -> tuple[str, str]:
    """Mirror pytest's JUnit naming so collected node ids can be matched to report entries."""
    path, bracket, params = node_id.partition("[")
    names = path.split("::")
    names[0] = re.sub(r"\.py$", "", names[0].replace("/", "."))
    names[-1] += bracket + params
    return ".".join(names[:-1]), names[-1]


def parse_collected(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if NODE_ID.match(line.strip())]


def parse_junit(xml_text: str) -> list[Case]:
    cases = []
    for element in ET.fromstring(xml_text).iter("testcase"):
        if element.find("skipped") is not None:
            outcome = "skipped"
        elif element.find("failure") is not None:
            outcome = "failed"
        elif element.find("error") is not None:
            outcome = "error"
        else:
            outcome = "passed"
        cases.append(Case(element.get("classname", ""), element.get("name", ""), outcome))
    return cases


def evaluate(
    collected: list[str],
    cases: list[Case],
    integration_modules: list[str],
    environ: dict[str, str],
) -> Verdict:
    verdict = Verdict(total=len(cases))
    for case in cases:
        if case.outcome == "passed":
            verdict.passed += 1
        elif case.outcome == "skipped":
            verdict.skipped += 1
        elif case.outcome == "failed":
            verdict.failed += 1
        else:
            verdict.errors += 1
    if verdict.skipped:
        verdict.problems.append(f"{verdict.skipped} test(s) were skipped; zero skips are allowed")
    if verdict.failed or verdict.errors:
        verdict.problems.append(f"{verdict.failed} failed and {verdict.errors} errored test(s)")

    if not environ.get(DATABASE_ENV):
        verdict.problems.append(f"{DATABASE_ENV} is not set; integration tests cannot have run")
    if not environ.get(CONFIRM_ENV):
        verdict.problems.append(f"{CONFIRM_ENV} is not set")
    if environ.get(SUPERUSER_BYPASS_ENV):
        verdict.problems.append(f"{SUPERUSER_BYPASS_ENV} is set; the superuser bypass is forbidden")

    integration_ids = [node for node in collected if "/integration/" in f"/{node}"]
    verdict.integration_expected = len(integration_ids)
    if not integration_ids:
        verdict.problems.append("no integration tests were collected")
    collected_modules = {node.split("::", 1)[0] for node in integration_ids}
    for module in sorted(set(integration_modules) - collected_modules):
        verdict.problems.append(f"integration module {module} contributed no collected tests")

    by_key = {(case.classname, case.name): case for case in cases}
    for node in integration_ids:
        case = by_key.get(junit_key(node))
        if case is None:
            verdict.problems.append(f"expected integration test missing from report: {node}")
        elif case.outcome != "passed":
            verdict.problems.append(f"integration test {case.outcome}: {node}")
        else:
            verdict.integration_passed += 1
    return verdict


def render_summary(verdict: Verdict) -> str:
    status = "PASS" if verdict.ok else "FAIL"
    lines = [
        f"Pytest report verification: {status}",
        f"- total={verdict.total} passed={verdict.passed} skipped={verdict.skipped} "
        f"failed={verdict.failed} errors={verdict.errors}",
        f"- integration expected={verdict.integration_expected} "
        f"passed={verdict.integration_passed}",
    ]
    lines.extend(f"- PROBLEM: {problem}" for problem in verdict.problems[:50])
    if len(verdict.problems) > 50:
        lines.append(f"- ... and {len(verdict.problems) - 50} more problems")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--junit", type=Path, required=True)
    parser.add_argument("--collected", type=Path, required=True)
    parser.add_argument("--integration-dir", type=Path, default=Path("tests/integration"))
    args = parser.parse_args(argv)

    modules = sorted(path.as_posix() for path in args.integration_dir.glob("test_*.py"))
    verdict = evaluate(
        parse_collected(args.collected.read_text(encoding="utf-8")),
        parse_junit(args.junit.read_text(encoding="utf-8")),
        modules,
        dict(os.environ),
    )
    summary = render_summary(verdict)
    print(summary)
    summary_file = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_file:
        with open(summary_file, "a", encoding="utf-8") as handle:
            handle.write(summary + "\n")
    return 0 if verdict.ok else 1


if __name__ == "__main__":
    sys.exit(main())
