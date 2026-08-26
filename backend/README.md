# GridSense Backend

Grid-Aware Energy Copilot API for Victorian Households.

## Quick Start

### Prerequisites
- Python 3.11+
- PostgreSQL 16+
- uv or pip

### Installation

```bash
# Install dependencies
pip install -e .

# Or with uv
uv pip install -e .
```

### Environment Setup

Create a `.env` file:

```env
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/gridsense
SECRET_KEY=your-super-secret-key-change-this
DEBUG=true
EMAIL_PROVIDER=local
FRONTEND_RESET_URL=gridsense://reset-password
```

Password reset uses the local provider in development, which logs a reset link
when `DEBUG=true`. Configure `EMAIL_PROVIDER=smtp` and the `SMTP_*` settings in
production; reset tokens are hashed before being stored in the database.

Automation uses the simulator provider by default. To control a Home Assistant
entity, set `AUTOMATION_PROVIDER=home_assistant`, configure `HOME_ASSISTANT_URL`
and `HOME_ASSISTANT_TOKEN`, then create a device with `integration_type` set to
`home_assistant` and its Home Assistant entity ID in `device_id`.

### Database Setup

```bash
# Start PostgreSQL (Docker)
docker run -d --name gridsense-db -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=gridsense -p 5432:5432 postgres:16

# Apply versioned database migrations
cd backend
alembic upgrade head
```

### Running the Server

```bash
# Development API
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Background worker (requires Redis)
python -m app.worker

# Automation scheduler (enqueues due schedules once per minute)
python -m app.scheduler

# Optional ML training for one meter
python -m app.ml.cli train-meter --meter-id 1

ML models are trained automatically after imports once a meter has at least 20
daily aggregates. The Prophet forecast and IsolationForest anomaly detector are
optional enhancements; deterministic billing and anomaly rules remain available
when data is insufficient or training fails.

The scheduler also manages:
- Weekly ML retraining: Sunday 3am UTC
- Weekly energy summaries: Sunday 8am UTC
- Daily bill forecast checks: Daily 6pm UTC
- Alert notifications for anomalies and high-priority recommendations

See `docs/alerts.md` for complete alert system documentation.

# Production
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

### API Documentation

Once running, visit:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## API Endpoints

### Authentication
- `POST /api/v1/auth/register` - Create account
- `POST /api/v1/auth/login` - Get access token
- `GET /api/v1/auth/me` - Get current user

### Meters
- `GET /api/v1/meters` - List meters
- `POST /api/v1/meters` - Create meter
- `GET /api/v1/meters/{id}` - Get meter
- `DELETE /api/v1/meters/{id}` - Delete meter

### Upload
- `POST /api/v1/upload` - Upload NEM12 file
- `GET /api/v1/upload/status/{job_id}` - Check background processing status

### Usage
- `GET /api/v1/usage/summary/{meter_id}` - Usage summary
- `GET /api/v1/usage/daily/{meter_id}` - Daily breakdown
- `GET /api/v1/usage/hourly/{meter_id}` - Hourly pattern
- `GET /api/v1/usage/weekly/{meter_id}` - Weekly pattern

### Recommendations
- `GET /api/v1/recommendations` - All recommendations
- `GET /api/v1/recommendations/{meter_id}` - Meter recommendations

## NEM12 File Format

NEM12 is the standard format for smart meter data in Australia's National Electricity Market. You can obtain your NEM12 file from:

1. Your energy retailer's online portal
2. Request from your distribution network (e.g., AusNet, United Energy)
3. Some retailers email monthly NEM12 exports

## Project Structure

```
backend/
├── app/
│   ├── main.py              # FastAPI application
│   ├── config.py            # Settings
│   ├── database.py          # DB connection
│   ├── models/              # SQLAlchemy models
│   ├── schemas/             # Pydantic schemas
│   ├── api/                 # API routes
│   └── services/            # Business logic
├── tests/                   # Test suite
└── pyproject.toml           # Dependencies
```

## License

MIT
