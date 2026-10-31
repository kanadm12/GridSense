"""Regression tests for the Alembic migration chain."""

from pathlib import Path

from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session

from alembic import command
from app.config import get_settings
from app.models.upload import NEM12Upload
from app.models.user import User


def test_clean_database_migrates_to_head(tmp_path, monkeypatch):
    database_path = tmp_path / "migration-test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{database_path.as_posix()}")
    get_settings.cache_clear()

    backend_dir = Path(__file__).resolve().parents[1]
    config = Config(str(backend_dir / "alembic.ini"))
    command.upgrade(config, "head")

    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    try:
        inspector = inspect(engine)
        assert "is_active" in {column["name"] for column in inspector.get_columns("meters")}
        with engine.connect() as connection:
            revision = connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one()
        assert revision == "f6a7b8c9d0e1"
        assert "uq_nem12_upload_user_file_hash" in {
            index["name"] for index in inspector.get_indexes("nem12_uploads")
        }

        command.downgrade(config, "e6f168c90ff8")
        assert "uq_nem12_upload_user_file_hash" not in {
            index["name"] for index in inspect(engine).get_indexes("nem12_uploads")
        }
        assert "is_active" not in {
            column["name"] for column in inspect(engine).get_columns("meters")
        }
        assert "register_id" not in {
            column["name"] for column in inspect(engine).get_columns("meters")
        }
        assert "direction" not in {
            column["name"] for column in inspect(engine).get_columns("readings")
        }
        assert "interval_minutes" not in {
            column["name"] for column in inspect(engine).get_columns("readings")
        }
        assert "feed_in_rate_cents_kwh" not in {
            column["name"] for column in inspect(engine).get_columns("tariffs")
        }

        with Session(engine) as db:
            user = User(
                email="legacy-duplicate@example.com",
                hashed_password="not-a-real-password",
                full_name="Migration Test",
            )
            db.add(user)
            db.flush()
            test_user_id = user.id
            db.add_all(
                [
                    NEM12Upload(
                        user_id=user.id,
                        filename="older.csv",
                        file_hash="same-content-hash",
                        status="failed",
                    ),
                    NEM12Upload(
                        user_id=user.id,
                        filename="completed.csv",
                        file_hash="same-content-hash",
                        status="completed",
                    ),
                ]
            )
            db.commit()

        command.upgrade(config, "head")
        assert "is_active" in {column["name"] for column in inspect(engine).get_columns("meters")}
        assert "register_id" in {column["name"] for column in inspect(engine).get_columns("meters")}
        assert "interval_minutes" in {
            column["name"] for column in inspect(engine).get_columns("readings")
        }
        assert "rates_include_gst" in {
            column["name"] for column in inspect(engine).get_columns("tariffs")
        }
        with Session(engine) as db:
            uploads = (
                db.query(NEM12Upload)
                .filter(NEM12Upload.user_id == test_user_id)
                .order_by(NEM12Upload.id)
                .all()
            )
            assert [upload.file_hash for upload in uploads] == [
                None,
                "same-content-hash",
            ]
    finally:
        engine.dispose()
        get_settings.cache_clear()
