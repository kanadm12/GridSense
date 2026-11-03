"""Tests for NEM12 upload endpoint and importer."""

from datetime import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import get_db
from app.main import app
from app.models.base import Base
from app.models.meter import Meter
from app.models.reading import Reading
from app.models.upload import NEM12Upload
from app.models.user import User
from app.rate_limit import limiter
from app.services.auth import AuthService
from app.services.nem12_importer import NEM12Importer

# Test database setup (shared in-memory)
engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True)
def setup_database():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client(monkeypatch):
    rate_limit_was_enabled = limiter.enabled
    limiter.enabled = False
    # create a test user and override dependencies
    db = TestingSessionLocal()
    test_user = User(
        email="upload@example.com",
        hashed_password=AuthService.hash_password("password"),
        full_name="Upload User",
    )
    db.add(test_user)
    db.commit()
    db.refresh(test_user)
    db.close()

    def _override_get_current_user():
        # return the user by querying a fresh session
        db = TestingSessionLocal()
        user = db.query(User).filter(User.email == "upload@example.com").first()
        db.close()
        return user

    app.dependency_overrides[get_db] = override_get_db
    monkeypatch.setattr("app.api.upload.SessionLocal", TestingSessionLocal)
    # import the dependency function used by endpoints
    from app.api.deps import get_current_user

    app.dependency_overrides[get_current_user] = _override_get_current_user

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
    limiter.enabled = rate_limit_was_enabled


def test_upload_endpoint_creates_pending_upload(client):
    # Read sample NEM12 file from tests
    with open("tests/sample_nem12.csv", "rb") as f:
        files = {"file": ("sample_nem12.csv", f, "text/csv")}
        resp = client.post("/api/v1/upload", files=files)

    assert resp.status_code == 200
    body = resp.json()
    assert "upload_id" in body

    # Check upload record in DB
    db = TestingSessionLocal()
    upload = db.query(NEM12Upload).filter(NEM12Upload.id == body["upload_id"]).first()
    assert upload is not None
    assert upload.status in ("pending", "processing", "completed")
    db.close()


def test_duplicate_upload_requests_share_one_job_and_allow_failed_retry(client, monkeypatch):
    queue_calls = []

    def enqueue(content, user_id, filename, upload_id):
        queue_calls.append((user_id, filename, upload_id))
        return f"job-{len(queue_calls)}"

    monkeypatch.setattr("app.tasks.enqueue_import", enqueue)
    monkeypatch.setattr("app.tasks.get_job_status", lambda job_id: "queued")
    sample = Path("tests/sample_nem12.csv").read_bytes()
    first = client.post(
        "/api/v1/upload",
        files={"file": ("sample_nem12.csv", sample, "text/csv")},
    )
    duplicate = client.post(
        "/api/v1/upload",
        files={"file": ("same-content.nem12", sample, "text/csv")},
    )

    assert first.status_code == duplicate.status_code == 200
    upload_id = first.json()["upload_id"]
    assert duplicate.json()["upload_id"] == upload_id
    assert len(queue_calls) == 1

    db = TestingSessionLocal()
    upload = db.get(NEM12Upload, upload_id)
    upload.status = "processing"
    db.commit()
    db.close()
    monkeypatch.setattr("app.tasks.get_job_status", lambda job_id: "failed")

    retried = client.post(
        "/api/v1/upload",
        files={"file": ("sample_nem12.csv", sample, "text/csv")},
    )
    assert retried.status_code == 200
    assert retried.json()["upload_id"] == upload_id
    assert len(queue_calls) == 2


def test_unavailable_redis_uses_request_independent_fallback_session(client, monkeypatch):
    def unavailable(*args, **kwargs):
        raise ConnectionError("Redis unavailable")

    monkeypatch.setattr("app.tasks.enqueue_import", unavailable)
    sample = Path("tests/sample_nem12.csv").read_bytes()
    response = client.post(
        "/api/v1/upload",
        files={"file": ("sample_nem12.csv", sample, "text/csv")},
    )

    assert response.status_code == 200
    db = TestingSessionLocal()
    upload = db.get(NEM12Upload, response.json()["upload_id"])
    assert upload is not None
    assert upload.status == "completed"
    assert upload.total_readings == 336
    assert db.query(Reading).count() == 336
    db.close()


def test_readiness_failure_is_503_without_database_error_details(client):
    class FailedDatabase:
        def execute(self, statement):
            raise RuntimeError("private connection details")

    def failed_db():
        yield FailedDatabase()

    app.dependency_overrides[get_db] = failed_db
    response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json()["detail"] == {
        "status": "not_ready",
        "database": "disconnected",
    }
    assert "private connection details" not in response.text


def test_upload_rejects_files_over_50_mib(client):
    oversized_content = b"x" * (50 * 1024 * 1024 + 1)
    response = client.post(
        "/api/v1/upload",
        files={"file": ("oversized.csv", oversized_content, "text/csv")},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "File too large (max 50MB)"


def test_importer_persists_readings_and_aggregates():
    # Use importer directly to run synchronously
    db = TestingSessionLocal()
    # create user
    user = User(
        email="imp@example.com",
        hashed_password=AuthService.hash_password("password"),
        full_name="Importer",
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    with open("tests/sample_nem12.csv", "rb") as f:
        content = f.read()

    importer = NEM12Importer()
    result = importer.import_file(db, user.id, content, filename="sample_nem12.csv")

    assert result.total_readings > 0

    # verify upload record
    upload = (
        db.query(NEM12Upload)
        .filter(NEM12Upload.user_id == user.id)
        .order_by(NEM12Upload.id.desc())
        .first()
    )
    assert upload is not None
    assert upload.status == "completed"
    assert upload.total_readings and upload.total_readings > 0

    # Unresolved direction is intentionally excluded from consumption aggregates.
    from app.models.aggregate import DailyAggregate

    agg = db.query(DailyAggregate).first()
    assert agg is None

    meter = db.query(Meter).filter(Meter.register_id == "E1").first()
    assert meter.mdm_data_stream_identifier == "N1"
    first_reading = (
        db.query(Reading)
        .filter(Reading.meter_id == meter.id)
        .order_by(Reading.timestamp)
        .first()
    )
    assert first_reading.source_interval_date == datetime(2025, 4, 1).date()
    assert first_reading.source_interval_number == 1
    assert first_reading.source_nmi_configuration == "E1"
    assert first_reading.source_record_quality_method == "A"
    assert first_reading.source_time_basis == "unverified_nem12_clock_basis"
    db.add(
        Reading(
            meter_id=meter.id,
            timestamp=datetime(2025, 4, 1, 0, 30),
            value=1.25,
            source_value=1.25,
            source_unit="kWh",
            provenance_kind="measured",
            source_time_basis="fixed_utc_plus_10",
            quality="A",
            register_type="B",
            direction="import",
        )
    )
    db.commit()
    importer.generate_daily_aggregates(db, meter.id)
    agg = db.query(DailyAggregate).filter(DailyAggregate.meter_id == meter.id).first()
    assert agg is not None
    assert agg.total_kwh == 1.25

    db.close()


def test_import_keeps_same_timestamp_channels_separate_by_data_stream_identifier():
    db = TestingSessionLocal()
    user = User(
        email="multi-stream@example.com",
        hashed_password=AuthService.hash_password("password"),
        full_name="Multi Stream",
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    values = ",".join(["0.5"] * 48)
    content = (
        "100,NEM12,202512021200,TEST,AEMO\n"
        "200,1234567890,E1,1,E1,N1,SERIAL,kWh,30,\n"
        f"300,20251201,{values},A,,,\n"
        "200,1234567890,E1,1,E1,N2,SERIAL,kWh,30,\n"
        f"300,20251201,{values},A,,,\n"
        "900\n"
    )

    result = NEM12Importer().import_file(
        db, user.id, content, filename="multiple-streams.csv"
    )

    meters = (
        db.query(Meter)
        .filter(Meter.user_id == user.id)
        .order_by(Meter.mdm_data_stream_identifier)
        .all()
    )
    assert len(result.meters) == 2
    assert [meter.mdm_data_stream_identifier for meter in meters] == ["N1", "N2"]
    assert db.query(Reading).filter(Reading.meter_id == meters[0].id).count() == 48
    assert db.query(Reading).filter(Reading.meter_id == meters[1].id).count() == 48
    db.close()


def test_repeated_import_does_not_duplicate_readings():
    db = TestingSessionLocal()
    user = User(
        email="repeat@example.com",
        hashed_password=AuthService.hash_password("password"),
        full_name="Repeat",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    content = Path("tests/sample_nem12.csv").read_bytes()

    importer = NEM12Importer()
    importer.import_file(db, user.id, content, filename="sample_nem12.csv")
    initial_count = db.query(Reading).count()
    importer.import_file(db, user.id, content, filename="sample_nem12.csv")

    assert initial_count == 336
    assert db.query(Reading).count() == initial_count
    assert db.query(Meter).filter(Meter.register_id == "E1").count() == 1
    db.close()


def test_retry_after_committed_chunk_imports_only_missing_readings():
    db = TestingSessionLocal()
    user = User(
        email="retry@example.com",
        hashed_password=AuthService.hash_password("password"),
        full_name="Retry",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    content = Path("tests/sample_nem12.csv").read_bytes()
    importer = NEM12Importer()
    importer.CHUNK_SIZE = 100

    def simulate_worker_restart(current, total):
        raise RuntimeError(f"simulated interruption after {current} of {total}")

    with pytest.raises(RuntimeError, match="simulated interruption"):
        importer.import_file(
            db,
            user.id,
            content,
            filename="sample_nem12.csv",
            progress_callback=simulate_worker_restart,
        )

    upload = (
        db.query(NEM12Upload)
        .filter(NEM12Upload.user_id == user.id)
        .order_by(NEM12Upload.id.desc())
        .first()
    )
    assert upload is not None
    assert upload.status == "failed"
    assert db.query(Reading).count() == 100

    result = importer.import_file(
        db,
        user.id,
        content,
        filename="sample_nem12.csv",
        upload_id=upload.id,
    )

    assert result.total_readings == 336
    assert upload.status == "completed"
    assert upload.total_readings == 336
    assert db.query(Reading).count() == 336
    db.close()


def test_rq_task_can_retry_after_interrupted_committed_chunk(monkeypatch):
    db = TestingSessionLocal()
    user = User(
        email="worker-retry@example.com",
        hashed_password=AuthService.hash_password("password"),
        full_name="Worker Retry",
    )
    db.add(user)
    db.flush()
    upload = NEM12Upload(
        user_id=user.id,
        filename="sample_nem12.csv",
        file_hash="worker-retry-hash",
        status="pending",
    )
    db.add(upload)
    db.commit()
    upload_id = upload.id
    user_id = user.id
    db.close()

    content = Path("tests/sample_nem12.csv").read_bytes()
    importer = NEM12Importer()
    importer.CHUNK_SIZE = 100

    class InterruptedImporter:
        def import_file(self, *args, **kwargs):
            def stop_after_commit(current, total):
                raise RuntimeError(f"simulated worker restart after {current} of {total}")

            return importer.import_file(
                *args,
                **kwargs,
                progress_callback=stop_after_commit,
            )

    monkeypatch.setattr("app.tasks.SessionLocal", TestingSessionLocal)
    monkeypatch.setattr("app.tasks.NEM12Importer", InterruptedImporter)
    monkeypatch.setattr("app.tasks.publish_after_import", lambda *args: 0)
    monkeypatch.setattr("app.tasks.enqueue_ml_training", lambda *args: None)

    from app.tasks import import_nem12_task

    with pytest.raises(RuntimeError, match="simulated worker restart"):
        import_nem12_task(upload_id, user_id, content, "sample_nem12.csv")
    with TestingSessionLocal() as partial_db:
        assert partial_db.query(Reading).count() == 100

    monkeypatch.setattr("app.tasks.NEM12Importer", NEM12Importer)
    outcome = import_nem12_task(upload_id, user_id, content, "sample_nem12.csv")
    verify_db = TestingSessionLocal()
    completed_upload = verify_db.get(NEM12Upload, upload_id)
    assert outcome["status"] == "completed"
    assert completed_upload.status == "completed"
    assert verify_db.query(Reading).count() == 336
    verify_db.close()
