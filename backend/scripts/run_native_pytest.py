"""Run pytest in a child process while preserving native crash diagnostics."""

from __future__ import annotations

import argparse
import ctypes.util
import hashlib
import importlib
import importlib.metadata
import json
import os
import platform
import re
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import BinaryIO

NATIVE_DIAGNOSTIC = re.compile(
    r"windows fatal exception|access violation", re.IGNORECASE
)
TEST_NODE_ID = re.compile(r"([^\s:]+\.py::[^\s]+)")
PACKAGE_NAMES = (
    "SQLAlchemy",
    "pytest",
    "pytest-asyncio",
    "greenlet",
    "pysqlite3-binary",
)


def package_versions() -> dict[str, str | None]:
    versions: dict[str, str | None] = {}
    for package in PACKAGE_NAMES:
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = None
    return versions


def runtime_details(dbapi_module_name: str) -> dict[str, object]:
    dbapi = importlib.import_module(dbapi_module_name)
    connection = dbapi.connect(":memory:")
    try:
        compile_options = [
            row[0] for row in connection.execute("PRAGMA compile_options")
        ]
    finally:
        connection.close()

    return {
        "executable": sys.executable,
        "python": sys.version.replace("\n", " "),
        "python_compiler": platform.python_compiler(),
        "platform": platform.platform(),
        "architecture": platform.architecture()[0],
        "sqlite_dbapi_module": dbapi_module_name,
        "sqlite_runtime": dbapi.sqlite_version,
        "sqlite_module": dbapi.version,
        "sqlite_threadsafety": dbapi.threadsafety,
        "sqlite_extension": getattr(dbapi, "__file__", None),
        "sqlite_system_library": ctypes.util.find_library("sqlite3"),
        "sqlite_compile_options": compile_options,
        "packages": package_versions(),
        "python_faulthandler": os.environ.get("PYTHONFAULTHANDLER"),
        "python_malloc": os.environ.get("PYTHONMALLOC"),
    }


def pump_stream(
    pipe: BinaryIO,
    log_path: Path,
    stream_name: str,
    active_test_path: Path,
    active_test: dict[str, str | None],
    active_test_lock: threading.Lock,
    diagnostics: list[dict[str, object]],
    diagnostics_lock: threading.Lock,
    node_ids: list[str],
    node_ids_lock: threading.Lock,
    start_time: float,
) -> None:
    console = sys.stdout.buffer if stream_name == "stdout" else sys.stderr.buffer
    with log_path.open("wb") as log:
        while chunk := pipe.readline():
            log.write(chunk)
            log.flush()
            console.write(chunk)
            console.flush()

            line = chunk.decode("utf-8", errors="replace").rstrip("\r\n")
            node_match = TEST_NODE_ID.search(line)
            if node_match:
                node_id = node_match.group(1)
                with active_test_lock:
                    active_test["node_id"] = node_id
                with node_ids_lock:
                    if not node_ids or node_ids[-1] != node_id:
                        node_ids.append(node_id)

            if NATIVE_DIAGNOSTIC.search(line):
                try:
                    current_test = active_test_path.read_text(encoding="utf-8")
                except (FileNotFoundError, PermissionError):
                    with active_test_lock:
                        current_test = active_test["node_id"]
                with diagnostics_lock:
                    diagnostics.append(
                        {
                            "stream": stream_name,
                            "line": line,
                            "active_test": current_test,
                            "seconds_from_start": round(time.monotonic() - start_time, 3),
                        }
                    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run pytest in a fresh child process and retain stdout, stderr, "
            "native diagnostics, and runtime metadata."
        )
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        type=Path,
        help="Explicit directory for per-run stdout, stderr, and JSON summaries.",
    )
    parser.add_argument(
        "--capture",
        choices=("fd", "sys", "tee-sys", "no"),
        default="fd",
        help="pytest capture mode; use 'no' for the equivalent of pytest -s.",
    )
    parser.add_argument(
        "--sqlite-dbapi",
        choices=("sqlite3", "pysqlite3"),
        default="sqlite3",
        help="SQLite DBAPI module used by SQLAlchemy in the pytest child.",
    )
    parser.add_argument(
        "pytest_args",
        nargs=argparse.REMAINDER,
        help="Pytest selectors/options after '--'.",
    )
    args = parser.parse_args()

    pytest_args = list(args.pytest_args)
    if pytest_args and pytest_args[0] == "--":
        pytest_args.pop(0)

    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    run_id = f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
    run_dir = output_dir / run_id
    run_dir.mkdir()
    stdout_path = run_dir / "stdout.log"
    stderr_path = run_dir / "stderr.log"
    active_test_path = run_dir / "active-test.txt"
    collected_nodes_path = run_dir / "collected-nodeids.json"
    summary_path = run_dir / "summary.json"

    capture_args = ["--capture=no" if args.capture == "no" else f"--capture={args.capture}"]
    pytest_command = ["-vv", *capture_args, *pytest_args]
    sqlite_bootstrap = (
        "import pysqlite3, sys; sys.modules['sqlite3'] = pysqlite3; "
        if args.sqlite_dbapi == "pysqlite3"
        else ""
    )
    bootstrap = (
        f"{sqlite_bootstrap}"
        "import json, os, pathlib, pytest, sys; "
        "marker_path = pathlib.Path(sys.argv[1]); "
        "collection_path = pathlib.Path(sys.argv[2]); "
        "class_source = \"class ActiveTestMarker:\\n"
        " def pytest_runtest_logstart(self, nodeid, location):\\n"
        "  marker_path.write_text(nodeid, encoding='utf-8')\\n"
        " def pytest_collection_finish(self, session):\\n"
        "  nodeids = [item.nodeid for item in session.items]\\n"
        "  temp_path = collection_path.with_suffix('.tmp')\\n"
        "  temp_path.write_text(json.dumps(nodeids), encoding='utf-8')\\n"
        "  os.replace(temp_path, collection_path)\\n"
        "\"; "
        "exec(class_source); "
        "raise SystemExit(pytest.main(sys.argv[3:], plugins=[ActiveTestMarker()]))"
    )
    command = [
        sys.executable,
        "-X",
        "faulthandler",
        "-c",
        bootstrap,
        str(active_test_path),
        str(collected_nodes_path),
        *pytest_command,
    ]
    started_at = datetime.now(timezone.utc).isoformat()
    start_time = time.monotonic()
    active_test: dict[str, str | None] = {"node_id": None}
    active_test_lock = threading.Lock()
    diagnostics: list[dict[str, object]] = []
    diagnostics_lock = threading.Lock()
    node_ids: list[str] = []
    node_ids_lock = threading.Lock()

    process = subprocess.Popen(
        command,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        bufsize=0,
    )
    assert process.stdout is not None
    assert process.stderr is not None
    stdout_thread = threading.Thread(
        target=pump_stream,
        args=(
            process.stdout,
            stdout_path,
            "stdout",
            active_test_path,
            active_test,
            active_test_lock,
            diagnostics,
            diagnostics_lock,
            node_ids,
            node_ids_lock,
            start_time,
        ),
        daemon=True,
    )
    stderr_thread = threading.Thread(
        target=pump_stream,
        args=(
            process.stderr,
            stderr_path,
            "stderr",
            active_test_path,
            active_test,
            active_test_lock,
            diagnostics,
            diagnostics_lock,
            node_ids,
            node_ids_lock,
            start_time,
        ),
        daemon=True,
    )
    stdout_thread.start()
    stderr_thread.start()
    exit_code = process.wait()
    stdout_thread.join()
    stderr_thread.join()
    duration = round(time.monotonic() - start_time, 3)

    stdout_bytes = stdout_path.read_bytes()
    stderr_bytes = stderr_path.read_bytes()
    node_ids_digest = hashlib.sha256(
        "\n".join(node_ids).encode("utf-8")
    ).hexdigest()
    try:
        collected_node_ids = json.loads(collected_nodes_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        collected_node_ids = None
    collection_fingerprint = (
        hashlib.sha256("\n".join(collected_node_ids).encode("utf-8")).hexdigest()
        if collected_node_ids is not None
        else None
    )
    summary = {
        "run_id": run_id,
        "started_at": started_at,
        "duration_seconds": duration,
        "working_directory": str(Path.cwd()),
        "command": command,
        "capture_mode": args.capture,
        "sqlite_dbapi_module": args.sqlite_dbapi,
        "exit_code": exit_code,
        "native_diagnostic_detected": bool(diagnostics),
        "native_diagnostics": diagnostics,
        "last_observed_test": active_test["node_id"],
        "observed_test_node_ids": len(node_ids),
        "observed_test_node_ids_sha256": node_ids_digest,
        "collected_test_node_ids": len(collected_node_ids)
        if collected_node_ids is not None
        else None,
        "collection_fingerprint_sha256": collection_fingerprint,
        "collected_nodeids_file": str(collected_nodes_path)
        if collected_node_ids is not None
        else None,
        "stdout_log": str(stdout_path),
        "stderr_log": str(stderr_path),
        "stdout_bytes": len(stdout_bytes),
        "stderr_bytes": len(stderr_bytes),
        "runtime": runtime_details(args.sqlite_dbapi),
    }
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"\nNative diagnostic: {'YES' if diagnostics else 'no'}")
    print(f"Child exit code: {exit_code}")
    print(f"Observed test node IDs: {len(node_ids)}")
    print(f"Machine summary: {summary_path}")
    return 1 if exit_code != 0 or diagnostics else 0


if __name__ == "__main__":
    raise SystemExit(main())
