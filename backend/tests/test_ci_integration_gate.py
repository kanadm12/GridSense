"""Policy tests for the CI integration-test helpers (synthetic reports; no database needed)."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts import ci_postgres_integration as pg
from scripts import verify_pytest_report as vr

ENV_OK = {
    vr.DATABASE_ENV: "postgresql+psycopg2://role:pw@localhost:5432/gridsense_it_ci_test",
    vr.CONFIRM_ENV: "gridsense_it_ci_test",
}
MODULES = ["tests/integration/test_a.py", "tests/integration/test_b.py"]
COLLECTED = [
    "tests/integration/test_a.py::test_one",
    "tests/integration/test_a.py::TestGroup::test_two[param::x]",
    "tests/integration/test_b.py::test_three",
]


def _cases(overrides: dict[str, str] | None = None, extra: list[vr.Case] | None = None):
    overrides = overrides or {}
    cases = []
    for node in COLLECTED:
        classname, name = vr.junit_key(node)
        cases.append(vr.Case(classname, name, overrides.get(node, "passed")))
    cases.append(vr.Case("tests.test_unit", "test_other", "passed"))
    return cases + (extra or [])


def _evaluate(cases=None, collected=None, modules=None, environ=None):
    return vr.evaluate(
        COLLECTED if collected is None else collected,
        _cases() if cases is None else cases,
        MODULES if modules is None else modules,
        ENV_OK if environ is None else environ,
    )


def test_all_integration_tests_passing_is_accepted():
    verdict = _evaluate()
    assert verdict.ok, verdict.problems
    assert verdict.integration_expected == 3
    assert verdict.integration_passed == 3
    assert verdict.skipped == 0


def test_junit_key_mirrors_pytest_naming_for_classes_and_parameters():
    assert vr.junit_key("tests/integration/test_a.py::test_one") == (
        "tests.integration.test_a",
        "test_one",
    )
    assert vr.junit_key("tests/integration/test_a.py::TestGroup::test_two[param::x]") == (
        "tests.integration.test_a.TestGroup",
        "test_two[param::x]",
    )


def test_skipped_integration_test_fails_the_gate():
    verdict = _evaluate(_cases({COLLECTED[0]: "skipped"}))
    assert not verdict.ok
    assert any("skipped" in problem for problem in verdict.problems)


def test_skip_outside_integration_directory_also_fails():
    extra = [vr.Case("tests.test_unit", "test_skipped", "skipped")]
    assert not _evaluate(_cases(extra=extra)).ok


@pytest.mark.parametrize("outcome", ["failed", "error"])
def test_failed_or_errored_integration_test_fails(outcome: str):
    assert not _evaluate(_cases({COLLECTED[2]: outcome})).ok


def test_collected_integration_test_missing_from_report_fails():
    cases = [case for case in _cases() if case.name != "test_three"]
    verdict = _evaluate(cases)
    assert any("missing from report" in problem for problem in verdict.problems)


def test_no_collected_integration_tests_fails():
    verdict = _evaluate(collected=[], cases=[vr.Case("tests.test_unit", "test_x", "passed")])
    assert any("no integration tests were collected" in p for p in verdict.problems)


def test_integration_module_that_contributes_nothing_fails():
    verdict = _evaluate(modules=[*MODULES, "tests/integration/test_c.py"])
    assert any("test_c.py" in problem for problem in verdict.problems)


def test_missing_restricted_database_environment_fails():
    verdict = _evaluate(environ={})
    assert not verdict.ok
    assert sum("is not set" in problem for problem in verdict.problems) == 2


def test_superuser_bypass_flag_fails_even_when_every_test_passes():
    verdict = _evaluate(environ={**ENV_OK, vr.SUPERUSER_BYPASS_ENV: "1"})
    assert any("bypass" in problem for problem in verdict.problems)


def test_junit_parser_classifies_outcomes():
    xml = (
        "<testsuites><testsuite>"
        '<testcase classname="a" name="p"/>'
        '<testcase classname="a" name="s"><skipped message="x"/></testcase>'
        '<testcase classname="a" name="f"><failure message="x"/></testcase>'
        '<testcase classname="a" name="e"><error message="x"/></testcase>'
        "</testsuite></testsuites>"
    )
    outcomes = {case.name: case.outcome for case in vr.parse_junit(xml)}
    assert outcomes == {"p": "passed", "s": "skipped", "f": "failed", "e": "error"}


def test_collection_parser_ignores_summary_lines():
    text = "\n".join([*COLLECTED, "", "3 tests collected in 0.01s", "warnings summary"])
    assert vr.parse_collected(text) == COLLECTED


def test_cli_exit_code_reflects_verdict(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    integration_dir = tmp_path / "tests" / "integration"
    integration_dir.mkdir(parents=True)
    (integration_dir / "test_a.py").write_text("", encoding="utf-8")
    collected = tmp_path / "collected.txt"
    collected.write_text("tests/integration/test_a.py::test_one\n", encoding="utf-8")
    junit = tmp_path / "junit.xml"
    junit.write_text(
        '<testsuites><testcase classname="tests.integration.test_a" name="test_one"/></testsuites>',
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    for key, value in ENV_OK.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv(vr.SUPERUSER_BYPASS_ENV, raising=False)
    argv = ["--junit", str(junit), "--collected", str(collected)]
    assert vr.main(argv) == 0
    junit.write_text(
        '<testsuites><testcase classname="tests.integration.test_a" name="test_one">'
        '<skipped message="x"/></testcase></testsuites>',
        encoding="utf-8",
    )
    assert vr.main(argv) == 1


def test_role_privilege_check_accepts_only_fully_unprivileged_role():
    clean = dict.fromkeys(pg.ROLE_PRIVILEGE_FLAGS, False)
    assert pg.role_privilege_violations(clean) == []


@pytest.mark.parametrize("flag", pg.ROLE_PRIVILEGE_FLAGS)
def test_role_privilege_check_rejects_each_forbidden_flag(flag: str):
    attributes = dict.fromkeys(pg.ROLE_PRIVILEGE_FLAGS, False) | {flag: True}
    assert pg.role_privilege_violations(attributes) == [flag]


def test_role_privilege_check_treats_missing_flags_as_violations():
    assert set(pg.role_privilege_violations({})) == set(pg.ROLE_PRIVILEGE_FLAGS)


def test_forbidden_privileges_include_createdb_createrole_and_bypassrls():
    assert {"rolcreatedb", "rolcreaterole", "rolbypassrls", "rolsuper"} <= set(
        pg.ROLE_PRIVILEGE_FLAGS
    )


def test_provisioning_refuses_superuser_bypass_flag():
    with pytest.raises(pg.ProvisionError):
        pg.refuse_superuser_bypass({pg.SUPERUSER_BYPASS_ENV: "1"})
    pg.refuse_superuser_bypass({})
