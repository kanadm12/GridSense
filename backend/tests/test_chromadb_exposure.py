"""Guards the ChromaDB accepted exception (PYSEC-2026-311/3813/3814/3815).

The advisories affect ChromaDB's HTTP server, tenancy and RBAC paths and
trust_remote_code model loading. GridSense must only use the in-process,
non-persistent vector store. If any of these server or remote-code paths
appear in application code, the accepted exception no longer holds.
"""

from pathlib import Path

import pytest

APP_DIR = Path(__file__).resolve().parents[1] / "app"

FORBIDDEN = [
    "HttpClient",
    "AsyncHttpClient",
    "PersistentClient",
    "persist_directory",
    "trust_remote_code",
    "chroma run",
    "/api/v2/tenants",
]


def _app_sources():
    return [p for p in APP_DIR.rglob("*.py") if "__pycache__" not in p.parts]


@pytest.mark.parametrize("pattern", FORBIDDEN)
def test_app_does_not_use_chroma_server_or_remote_code(pattern):
    offenders = [
        str(p.relative_to(APP_DIR))
        for p in _app_sources()
        if pattern in p.read_text(encoding="utf-8", errors="ignore")
    ]
    assert offenders == [], (
        f"'{pattern}' found in {offenders}; the ChromaDB accepted exception "
        "in .github/workflows/ci.yml must be re-evaluated."
    )


def test_chroma_usage_is_in_memory_only():
    rag = (APP_DIR / "services" / "rag_engine.py").read_text(encoding="utf-8")
    assert "Chroma.from_texts(" in rag
    assert "persist_directory" not in rag
