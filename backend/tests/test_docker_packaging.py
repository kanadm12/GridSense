"""Static regression checks for the container build: packaging resources, lock use, ignore rules."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
LOCK = "requirements-dev.lock"

MUST_EXCLUDE = [
    ".env",
    ".env.local",
    "gridsense.db",
    "tests/scratch.sqlite3",
    "file",
    "filetests_db",
    "fileinsights_tests_db",
    ".coverage",
    "coverage.xml",
    "reports/forecast_evaluation/summary.csv",
    "graphify-out/graph.json",
    "docs/graphify-out/graph.json",
    ".claude/worktrees/a/b.py",
    "app/__pycache__/main.cpython-311.pyc",
    "app/stray.pyc",
    ".pytest_cache/v/cache/lastfailed",
    ".ruff_cache/0.1/x",
    ".venv311/lib/site.py",
    ".git/config",
]
MUST_INCLUDE = [
    "Dockerfile",
    "pyproject.toml",
    "README.md",
    LOCK,
    "alembic.ini",
    "alembic/env.py",
    "app/main.py",
    "app/file_utils.py",
    "app/data/aer_retailer_uris_2026_01.json",
    "scripts/staging_smoke.py",
    "tests/sample_nem12.csv",
    "security/risk-acceptances.json",
]


def _force_include_sources() -> list[str]:
    config = tomllib.loads((BACKEND / "pyproject.toml").read_text(encoding="utf-8"))
    return list(config["tool"]["hatch"]["build"]["targets"]["wheel"]["force-include"])


def _dockerfile_instructions() -> list[tuple[str, str]]:
    text = re.sub(r"\\\r?\n", " ", (BACKEND / "Dockerfile").read_text(encoding="utf-8"))
    instructions = []
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            keyword, _, rest = line.partition(" ")
            instructions.append((keyword.upper(), rest.strip()))
    return instructions


def _copy_sources(arguments: str) -> list[str]:
    tokens = [token for token in arguments.split() if not token.startswith("--")]
    return tokens[:-1]


def _first_project_install_index(instructions: list[tuple[str, str]]) -> int:
    for index, (keyword, rest) in enumerate(instructions):
        if keyword == "RUN" and re.search(r"-e\s+\.", rest):
            return index
    raise AssertionError("Dockerfile has no editable project install")


def _pattern_regex(pattern: str) -> re.Pattern[str]:
    parts: list[str] = []
    index = 0
    while index < len(pattern):
        if pattern.startswith("**/", index):
            parts.append("(?:.*/)?")
            index += 3
        elif pattern.startswith("**", index):
            parts.append(".*")
            index += 2
        elif pattern[index] == "*":
            parts.append("[^/]*")
            index += 1
        elif pattern[index] == "?":
            parts.append("[^/]")
            index += 1
        else:
            parts.append(re.escape(pattern[index]))
            index += 1
    return re.compile("^" + "".join(parts) + "$")


def _ignore_rules() -> list[tuple[bool, re.Pattern[str]]]:
    rules = []
    for raw in (BACKEND / ".dockerignore").read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line and not line.startswith("#"):
            negated = line.startswith("!")
            rules.append((negated, _pattern_regex(line.lstrip("!").lstrip("/"))))
    return rules


def _is_ignored(path: str, rules: list[tuple[bool, re.Pattern[str]]]) -> bool:
    segments = path.split("/")
    prefixes = ["/".join(segments[: n + 1]) for n in range(len(segments))]
    ignored = False
    for negated, regex in rules:
        if any(regex.match(prefix) for prefix in prefixes):
            ignored = not negated
    return ignored


def test_force_included_resources_exist_in_the_source_tree():
    sources = _force_include_sources()
    assert sources, "pyproject.toml no longer force-includes any resource"
    for source in sources:
        assert (BACKEND / source).is_file(), f"force-include source is missing: {source}"


def test_runtime_registry_path_matches_the_packaged_resource():
    source = (BACKEND / "app" / "services" / "aer_prd.py").read_text(encoding="utf-8")
    assert "aer_retailer_uris_2026_01.json" in source
    assert "app/data/aer_retailer_uris_2026_01.json" in _force_include_sources()


def test_dockerfile_copies_force_included_resources_before_the_project_install():
    instructions = _dockerfile_instructions()
    install_index = _first_project_install_index(instructions)
    copied = {
        source
        for keyword, rest in instructions[:install_index]
        if keyword == "COPY"
        for source in _copy_sources(rest)
    }
    for source in ["pyproject.toml", *_force_include_sources()]:
        assert source in copied, f"{source} must be COPY'd before the editable install"


def test_dockerfile_installs_the_hash_locked_dependency_set():
    instructions = _dockerfile_instructions()
    install_index = _first_project_install_index(instructions)
    run_install = instructions[install_index][1]
    assert f"--require-hashes -r {LOCK}" in run_install
    assert "--no-deps" in run_install
    copied = [s for k, r in instructions[:install_index] if k == "COPY" for s in _copy_sources(r)]
    assert LOCK in copied
    assert (BACKEND / LOCK).is_file()


@pytest.mark.parametrize("path", MUST_EXCLUDE)
def test_dockerignore_excludes_secrets_databases_and_generated_output(path: str):
    assert _is_ignored(path, _ignore_rules()), f"{path} would be copied into the image"


@pytest.mark.parametrize("path", MUST_INCLUDE)
def test_dockerignore_keeps_files_the_image_needs(path: str):
    assert not _is_ignored(path, _ignore_rules()), f"{path} would be missing from the image"


def test_required_include_paths_exist_except_synthetic_examples():
    synthetic = {"app/file_utils.py"}
    for path in MUST_INCLUDE:
        if path not in synthetic:
            assert (BACKEND / path).exists(), f"{path} no longer exists"
