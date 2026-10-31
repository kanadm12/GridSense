# Synthetic demo data

The local demo seed creates artificial data only; it does not ingest a real
customer file or represent a consenting participant. It is isolated to a
dedicated SQLite database named exactly `gridsense-demo.db` and refuses other
filenames or database engines.

From `backend/`, set a local password without putting it in the command line:

```powershell
$env:GRIDSENSE_DEMO_PASSWORD = "choose-a-local-demo-password"
..\.venv311\Scripts\python.exe scripts\demo_seed.py
```

The script creates two synthetic accounts with the same locally supplied
password. `demo.synthetic@example.com` has one clearly labeled meter, 48
half-hour import readings for the previous `Australia/Melbourne` calendar day
at seed time, and a synthetic 30 c/kWh flat tariff.
`demo.scheduling@example.com` has a separate meter and an invented, all-week
time-of-use tariff, but no meter readings. Its 0.8 kW baseline is supplied as a
synthetic scheduling request input. The separate profiles preserve the
analytics tariff because the current model allows one tariff per user. The
seed is idempotent when either demo account already exists. The password is
not hard-coded or printed. Point the local API at this same file before
starting it:

```powershell
$env:DATABASE_URL = "sqlite:///./gridsense-demo.db"
```

To reset and reseed that dedicated database, explicitly run:

```powershell
..\.venv311\Scripts\python.exe scripts\demo_seed.py --reset
```

`--reset` drops all tables in `gridsense-demo.db`; it must never be pointed at a
developer, staging, or production database. The script's filename guard is an
additional safeguard, not a substitute for checking the resolved path first.
The seed uses SQLAlchemy metadata for a quick local demo; it does not certify
Alembic deployment migrations. Run `tests\test_migrations.py` for the isolated
clean-schema migration check.
