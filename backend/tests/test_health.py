import pytest
from fastapi import HTTPException
from rq import Worker

from app.api import health


def test_worker_health_reports_queue_state_when_redis_is_available(monkeypatch):
    class FailedJobRegistry:
        count = 2

    class QueueStub:
        count = 3
        failed_job_registry = FailedJobRegistry()

    monkeypatch.setattr("app.tasks.get_redis_conn", lambda: object())
    monkeypatch.setattr(health, "Queue", lambda name, connection: QueueStub())
    monkeypatch.setattr(Worker, "all", lambda connection, queue: [object()])

    result = health.worker_health(current_user={})

    assert result["status"] == "ok"
    assert result["workers"] == 1
    assert result["jobs_queued"] == 3
    assert result["jobs_failed"] == 2


def test_worker_health_reports_no_running_worker(monkeypatch):
    class FailedJobRegistry:
        count = 0

    class QueueStub:
        count = 0
        failed_job_registry = FailedJobRegistry()

    monkeypatch.setattr("app.tasks.get_redis_conn", lambda: object())
    monkeypatch.setattr(health, "Queue", lambda name, connection: QueueStub())
    monkeypatch.setattr(Worker, "all", lambda connection, queue: [])

    with pytest.raises(HTTPException) as error:
        health.worker_health(current_user={})

    assert error.value.status_code == 503
    assert error.value.detail == {
        "status": "unavailable",
        "worker": "not_running",
        "workers": 0,
    }


def test_worker_health_reports_unavailable_when_redis_is_unreachable(monkeypatch):
    def fail_to_connect():
        raise ConnectionError("Redis unavailable")

    monkeypatch.setattr("app.tasks.get_redis_conn", fail_to_connect)

    with pytest.raises(HTTPException) as error:
        health.worker_health(current_user={})

    assert error.value.status_code == 503
    assert error.value.detail == {"status": "unavailable", "worker": "unreachable"}
