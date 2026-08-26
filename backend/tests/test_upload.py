"""Tests for NEM12 upload endpoint and importer."""

import io
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.database import get_db
from app.models.base import Base
from app.models.user import User
from app.models.upload import NEM12Upload
from app.services.nem12_importer import NEM12Importer
from app.services.auth import AuthService


# Test database setup (shared in-memory)
SQLALCHEMY_TEST_DATABASE_URL = "sqlite:///file:tests_db_upload?mode=memory&cache=shared"
engine = create_engine(
    SQLALCHEMY_TEST_DATABASE_URL, connect_args={"check_same_thread": False, "uri": True}
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
def client():
    # create a test user and override dependencies
    db = TestingSessionLocal()
    test_user = User(email="upload@example.com", hashed_password=AuthService.hash_password("password"), full_name="Upload User")
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
    # import the dependency function used by endpoints
    from app.api.deps import get_current_user

    app.dependency_overrides[get_current_user] = _override_get_current_user

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


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


def test_importer_persists_readings_and_aggregates():
    # Use importer directly to run synchronously
    db = TestingSessionLocal()
    # create user
    user = User(email="imp@example.com", hashed_password=AuthService.hash_password("password"), full_name="Importer")
    db.add(user)
    db.commit()
    db.refresh(user)

    with open("tests/sample_nem12.csv", "rb") as f:
        content = f.read()

    importer = NEM12Importer()
    result = importer.import_file(db, user.id, content, filename="sample_nem12.csv")

    assert result.total_readings > 0

    # verify upload record
    upload = db.query(NEM12Upload).filter(NEM12Upload.user_id == user.id).order_by(NEM12Upload.id.desc()).first()
    assert upload is not None
    assert upload.status == "completed"
    assert upload.total_readings and upload.total_readings > 0

    # check aggregates exist
    from app.models.aggregate import DailyAggregate

    agg = db.query(DailyAggregate).first()
    assert agg is not None
    assert agg.total_kwh >= 0

    db.close()
