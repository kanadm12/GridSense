"""Create a reproducible artificial demo account in a dedicated SQLite database."""

from __future__ import annotations

import argparse
import math
import os
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models import Base
from app.models.meter import Meter
from app.models.reading import Reading
from app.models.tariff import Tariff
from app.models.user import User
from app.services.auth import AuthService
from app.services.nem12_importer import NEM12Importer
from app.services.tariff import market_bounds_for_local_dates

DEMO_EMAIL = "demo.synthetic@example.com"
DEMO_SCHEDULING_EMAIL = "demo.scheduling@example.com"
DATABASE_FILENAME = "gridsense-demo.db"
DEMO_TIMEZONE = ZoneInfo("Australia/Melbourne")
DEMO_TODAY = datetime.now(DEMO_TIMEZONE).date()
DEMO_DAY = DEMO_TODAY - timedelta(days=1)
DEMO_EFFECTIVE_FROM = DEMO_TODAY.replace(day=1)


def _demo_user(db: Session, email: str, password: str, full_name: str) -> User:
    user = db.query(User).filter(User.email == email).first()
    if user is None:
        user = User(
            email=email,
            hashed_password=AuthService.hash_password(password),
            full_name=full_name,
            is_active=True,
        )
        db.add(user)
        db.flush()
    return user


def seed_demo_database(database_path: Path, reset: bool = False) -> None:
    """Create synthetic analytics and time-of-use scheduling demo accounts."""
    resolved_path = database_path.resolve()
    if resolved_path.name != DATABASE_FILENAME:
        raise ValueError(f"Demo data may only target a file named {DATABASE_FILENAME}")
    password = os.getenv("GRIDSENSE_DEMO_PASSWORD")
    if not password or len(password) < 8:
        raise ValueError("Set GRIDSENSE_DEMO_PASSWORD to a value of at least 8 characters")

    engine = create_engine(f"sqlite:///{resolved_path}")
    try:
        if reset:
            Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        with Session(engine) as db:
            user = _demo_user(db, DEMO_EMAIL, password, "Synthetic Demo User")
            meter = db.query(Meter).filter(Meter.user_id == user.id).first()
            if meter is None:
                meter = Meter(
                    user_id=user.id,
                    nmi="0000000001",
                    meter_serial="SYNTHETIC-001",
                    register_id="E1",
                    suffix="E1",
                    unit_of_measure="kWh",
                    interval_minutes=30,
                    state="VIC",
                    postcode="3000",
                    name="Synthetic demo meter",
                    is_active=True,
                )
                db.add(meter)
                db.flush()

                market_start, _ = market_bounds_for_local_dates(DEMO_DAY, DEMO_DAY, "VIC")
                for interval in range(48):
                    hour = interval / 2
                    demand_kwh = 0.24 + 0.06 * math.sin(hour / 24 * 2 * math.pi) ** 2
                    db.add(
                        Reading(
                            meter_id=meter.id,
                            timestamp=market_start + timedelta(minutes=(interval + 1) * 30),
                            interval_minutes=30,
                            value=round(demand_kwh, 4),
                            source_value=round(demand_kwh, 4),
                            source_unit="kWh",
                            provenance_kind="synthetic",
                            source_time_basis="fixed_utc_plus_10",
                            quality="A",
                            register_type="E",
                            direction="import",
                        )
                    )

            if db.query(Tariff).filter(Tariff.user_id == user.id).first() is None:
                db.add(
                    Tariff(
                        user_id=user.id,
                        tariff_type="flat",
                        retailer_name="Synthetic demo flat rate",
                        flat_rate_cents_kwh=30.0,
                        daily_supply_charge_cents=0.0,
                        is_preset=False,
                        rates_include_gst=True,
                        effective_from=DEMO_EFFECTIVE_FROM,
                    )
                )

            scheduling_user = _demo_user(
                db,
                DEMO_SCHEDULING_EMAIL,
                password,
                "Synthetic Scheduling Demo",
            )
            if db.query(Meter).filter(Meter.user_id == scheduling_user.id).first() is None:
                db.add(
                    Meter(
                        user_id=scheduling_user.id,
                        nmi="0000000002",
                        meter_serial="SYNTHETIC-TOU-001",
                        register_id="E1",
                        suffix="E1",
                        unit_of_measure="kWh",
                        interval_minutes=30,
                        state="VIC",
                        postcode="3000",
                        name="Synthetic TOU scheduling meter",
                        is_active=True,
                    )
                )

            if db.query(Tariff).filter(Tariff.user_id == scheduling_user.id).first() is None:
                days = list(range(7))
                db.add(
                    Tariff(
                        user_id=scheduling_user.id,
                        tariff_type="tou",
                        retailer_name="Synthetic scheduling TOU (not a retail offer)",
                        off_peak_rate_cents_kwh=10.0,
                        shoulder_rate_cents_kwh=25.0,
                        peak_rate_cents_kwh=55.0,
                        periods=[
                            {
                                "name": "Off-peak overnight",
                                "start_minute": 0,
                                "end_minute": 420,
                                "rate_cents_kwh": 10.0,
                                "days": days,
                            },
                            {
                                "name": "Shoulder daytime",
                                "start_minute": 420,
                                "end_minute": 960,
                                "rate_cents_kwh": 25.0,
                                "days": days,
                            },
                            {
                                "name": "Peak evening",
                                "start_minute": 960,
                                "end_minute": 1260,
                                "rate_cents_kwh": 55.0,
                                "days": days,
                            },
                            {
                                "name": "Off-peak late",
                                "start_minute": 1260,
                                "end_minute": 1440,
                                "rate_cents_kwh": 10.0,
                                "days": days,
                            },
                        ],
                        daily_supply_charge_cents=0.0,
                        is_preset=False,
                        rates_include_gst=True,
                        effective_from=DEMO_EFFECTIVE_FROM,
                    )
                )
            db.commit()
            NEM12Importer().generate_daily_aggregates(db, meter.id)
            print(
                f"Seeded synthetic analytics account {DEMO_EMAIL} and TOU scheduling "
                f"account {DEMO_SCHEDULING_EMAIL} in {resolved_path}."
            )
    finally:
        engine.dispose()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Seed/reset a dedicated synthetic SQLite demo database."
    )
    parser.add_argument(
        "--database-path",
        type=Path,
        default=Path(DATABASE_FILENAME),
        help=f"Dedicated local SQLite path; filename must be {DATABASE_FILENAME}.",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Drop and recreate all tables in the dedicated synthetic demo database.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        seed_demo_database(args.database_path, reset=args.reset)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
