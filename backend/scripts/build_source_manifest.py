"""Build a source-only checkpoint manifest from the live Git worktree.

Candidate set = tracked files (git ls-files) plus untracked, non-ignored files
(git status), minus the exclusion rules below. The script reads Git state only;
it never stages, commits or modifies tracked files.

Usage (from the repository root):
    python backend/scripts/build_source_manifest.py --out <directory outside the tracked tree>

Secret-scan output reports file, line and pattern name only; matched values are never printed.
"""

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

EXCLUDED_SEGMENTS = {
    "__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache", "node_modules",
    ".venv", "venv", "dist", "build", ".expo", ".claude", "coverage", "graphify-out",
}
EXCLUDED_SUFFIXES = {
    ".sqlite3", ".sqlite", ".db", ".db-journal", ".log", ".zip", ".tar", ".gz", ".pyc",
}


def git(*args: str) -> bytes:
    return subprocess.run(["git", "-c", "core.quotepath=off", *args], cwd=REPO, check=True,
                          capture_output=True).stdout


def exclusion_reason(path: str) -> str | None:
    parts = path.split("/")
    if parts[0] == "files":
        return "local evidence folder (repo-root files/)"
    if re.match(r"^backend/file", path):
        return "legacy backend/file* artifact"
    if path == "graphify-out" or path.startswith("graphify-out/") or "/graphify-out/" in path:
        return "Graphify-generated output"
    if path.rsplit("/", 1)[-1] == ".env":
        return "environment file (may contain secrets)"
    for seg in parts[:-1]:
        if seg in EXCLUDED_SEGMENTS:
            return f"generated/cache/environment directory ({seg})"
    name = parts[-1]
    if Path(name).suffix.lower() in EXCLUDED_SUFFIXES:
        return f"database/log/archive/bytecode artifact ({Path(name).suffix})"
    return None


def parse_status(raw: bytes) -> dict[str, str]:
    entries = raw.split(b"\0")
    result: dict[str, str] = {}
    i = 0
    while i < len(entries):
        item = entries[i].decode("utf-8", "surrogateescape")
        i += 1
        if len(item) < 4:
            continue
        code, path = item[:2], item[3:]
        if "R" in code or "C" in code:
            i += 1  # skip origin path of a rename/copy
        result[path] = code
    return result


SECRET_PATTERNS = {
    "private-key-block": re.compile(r"-----BEGIN (RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
    "aws-access-key-id": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "github-token": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b"),
    "url-with-embedded-password": re.compile(r"[a-z][a-z0-9+.-]*://[^:/\s'\"]+:[^@\s/'\"]{4,}@"),
    "jwt-like-token": re.compile(
        r"\beyJ[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{10,}"
    ),
    "assigned-secret-literal": re.compile(
        r"(?i)\b(secret[_-]?key|api[_-]?key|password|passwd|client[_-]?secret|access[_-]?token)"
        r"\s*[:=]\s*['\"][^'\"\s]{12,}['\"]"
    ),
}


def _state(path: str, untracked: set[str], modified: set[str]) -> str:
    if path in untracked:
        return "untracked"
    return "modified" if path in modified else "tracked-unchanged"


def secret_scan(data: bytes) -> list[tuple[int, str]]:
    hits: list[tuple[int, str]] = []
    text = data.decode("utf-8", "replace")
    for lineno, line in enumerate(text.splitlines(), start=1):
        for name, pat in SECRET_PATTERNS.items():
            if pat.search(line):
                hits.append((lineno, name))
    return hits


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", required=True, type=Path,
                        help="output directory for the three manifest files")
    args = parser.parse_args()
    out: Path = args.out.resolve()
    if REPO == out or REPO in out.parents:
        parser.error("--out must be outside the repository tree so manifests are never tracked")
    out.mkdir(parents=True, exist_ok=True)

    tracked = [p for p in git("ls-files").decode().split("\n") if p]
    status = parse_status(git("status", "--porcelain=v1", "-z", "-uall"))
    deleted = {p for p, c in status.items() if "D" in c}
    untracked = {p for p, c in status.items() if c == "??"}
    modified = {p for p, c in status.items() if c != "??" and "D" not in c}

    candidates = (set(tracked) | untracked) - deleted
    included: list[str] = []
    excluded: dict[str, str] = {}
    for path in sorted(candidates):
        reason = exclusion_reason(path)
        if reason:
            excluded[path] = reason
        elif (REPO / path).is_file():
            included.append(path)
        else:
            excluded[path] = "not a regular file on disk"

    records = []
    secret_hits = []
    binary_paths = []
    for path in included:
        data = (REPO / path).read_bytes()
        is_binary = b"\0" in data[:8000]
        if is_binary:
            binary_paths.append(path)
        else:
            for lineno, name in secret_scan(data):
                secret_hits.append({"path": path, "line": lineno, "pattern": name})
        records.append({
            "path": path,
            "state": _state(path, untracked, modified),
            "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
            "binary": is_binary,
        })

    # git status omits git-ignored files, so enumerate them separately. Ignored files
    # under files/ are excluded evidence and are listed by name. Other ignored files
    # (dependency, cache and local environment trees) are summarised by top-level folder.
    ignored_raw = git("ls-files", "--others", "--ignored", "--exclude-standard")
    ignored = [p for p in ignored_raw.decode().split("\n") if p]
    ignored_evidence = sorted(p for p in ignored if p.startswith("files/"))
    for path in ignored_evidence:
        excluded.setdefault(path, "git-ignored local evidence (repo-root files/)")
    ignored_other: dict[str, int] = {}
    for path in ignored:
        if not path.startswith("files/"):
            top = path.split("/", 1)[0]
            ignored_other[top] = ignored_other.get(top, 0) + 1

    reasons: dict[str, int] = {}
    for reason in excluded.values():
        key = reason.split(" (")[0]
        reasons[key] = reasons.get(key, 0) + 1

    manifest = {
        "repo": "kanadm12/GridSense",
        "head": git("rev-parse", "HEAD").decode().strip(),
        "included_count": len(records),
        "included_by_state": {
            s: sum(1 for r in records if r["state"] == s)
            for s in ("tracked-unchanged", "modified", "untracked")
        },
        "deleted_in_worktree": sorted(deleted),
        "excluded_count": len(excluded),
        "excluded_by_reason": reasons,
        "git_ignored_total": len(ignored),
        "git_ignored_evidence_files": ignored_evidence,
        "git_ignored_other_by_top_level": dict(
            sorted(ignored_other.items(), key=lambda kv: -kv[1])
        ),
        "secret_scan_hits": secret_hits,
        "files": records,
    }

    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    (out / "included-files.txt").write_text("\n".join(included) + "\n", encoding="utf-8")
    (out / "excluded-files.json").write_text(
        json.dumps(dict(sorted(excluded.items())), indent=2) + "\n", encoding="utf-8")

    print(f"HEAD {manifest['head'][:7]}")
    print(f"included {len(records)} {manifest['included_by_state']}")
    print(f"excluded {len(excluded)} {reasons}")
    print(f"deleted_in_worktree {len(deleted)}")
    print(f"git_ignored_total {len(ignored)}; ignored evidence files {len(ignored_evidence)}")
    print(f"binary (hashed, not text-scanned) {len(binary_paths)}")
    print(f"secret_scan_hits {len(secret_hits)}")
    for hit in secret_hits:
        print(f"  HIT {hit['path']}:{hit['line']} [{hit['pattern']}]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
