# GridSense Production Deployment Guide

## Prerequisites

### Required Software
- Docker 24+ and Docker Compose 2.20+
- PostgreSQL 16+ (if not using Docker)
- Redis 7+ (if not using Docker)
- Python 3.11+ (for local development)

### Required Secrets
- `SECRET_KEY`: Strong random key for JWT signing (32+ characters)
- `DATABASE_URL`: PostgreSQL connection string
- `REDIS_URL`: Redis connection string
- `OPENAI_API_KEY`: Optional, for AI assistant
- `HOME_ASSISTANT_TOKEN`: Optional, for device automation

### Environment Configuration

Create a `.env` file for production:

```env
# Application
APP_NAME="GridSense"
DEBUG=false
API_V1_PREFIX="/api/v1"

# Database
DATABASE_URL=postgresql://gridsense:STRONG_PASSWORD@db:5432/gridsense_prod

# Security
SECRET_KEY=<generate with: openssl rand -hex 32>
CORS_ORIGINS=["https://app.gridsense.example.com"]

# Redis & Background Jobs
REDIS_URL=redis://redis:6379/0

# Email (choose provider)
EMAIL_PROVIDER=smtp  # or resend
EMAIL_FROM="GridSense <no-reply@gridsense.example.com>"

# SMTP Configuration (if EMAIL_PROVIDER=smtp)
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USER=no-reply@gridsense.example.com
SMTP_PASSWORD=<smtp password>
SMTP_TLS=true

# Resend Configuration (if EMAIL_PROVIDER=resend)
RESEND_API_KEY=<resend api key>

# Password Reset
FRONTEND_RESET_URL=https://app.gridsense.example.com/reset-password

# Optional: OpenAI for AI Assistant
OPENAI_API_KEY=<openai api key>

# Optional: Home Assistant Integration
AUTOMATION_PROVIDER=home_assistant  # or simulator
HOME_ASSISTANT_URL=http://homeassistant:8123
HOME_ASSISTANT_TOKEN=<long lived access token>
```

## Deployment Methods

### Option 1: Docker Compose (Recommended)

**Step 1: Clone and configure**
```bash
git clone <repo> gridsense
cd gridsense
cp .env.example .env
# Edit .env with production values
```

**Step 2: Run migrations**
```bash
docker compose run --rm api alembic upgrade head
```

**Step 3: Start services**
```bash
docker compose up -d
```

**Step 4: Verify health**
```bash
curl https://api.gridsense.example.com/health/ready
```

### Option 2: Standalone Python (Advanced)

**Step 1: Install dependencies**
```bash
cd backend
python3.11 -m venv venv
source venv/bin/activate
pip install -e .
```

**Step 2: Run migrations**
```bash
alembic upgrade head
```

**Step 3: Start services**
```bash
# Terminal 1: API
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4

# Terminal 2: Worker
python -m app.worker

# Terminal 3: Scheduler
python -m app.scheduler
```

## Service Architecture

```
┌─────────────┐
│   Nginx     │ → HTTPS termination, static files
│   (Proxy)   │
└─────┬───────┘
      │
┌─────▼────────────────────────────────────┐
│         Docker Compose Stack             │
├──────────────────────────────────────────┤
│  ┌────────┐  ┌────────┐  ┌───────────┐  │
│  │   API  │  │ Worker │  │ Scheduler │  │
│  │ (×4)   │  │  (×2)  │  │   (×1)    │  │
│  └───┬────┘  └───┬────┘  └─────┬─────┘  │
│      │           │             │         │
│  ┌───▼───────────▼─────────────▼──────┐  │
│  │         PostgreSQL 16               │  │
│  │      (Persistent Volume)            │  │
│  └─────────────────────────────────────┘  │
│  ┌─────────────────────────────────────┐  │
│  │         Redis 7                      │  │
│  │    (Job Queue + Locks)              │  │
│  └─────────────────────────────────────┘  │
└──────────────────────────────────────────┘
```

## Health Checks

### Liveness Probe
```bash
curl https://api.gridsense.example.com/health/live
```
Returns 200 if API process is running.

### Readiness Probe
```bash
curl https://api.gridsense.example.com/health/ready
```
Returns 200 if API can connect to database.

### Worker Health (Authenticated)
```bash
curl -H "Authorization: Bearer <token>" \
  https://api.gridsense.example.com/health/worker
```
Returns worker count, queue depth, failed jobs.

## Scaling

### Horizontal Scaling
- **API**: Scale to N workers: `docker compose up -d --scale api=4`
- **Worker**: Scale to M workers: `docker compose up -d --scale worker=2`
- **Scheduler**: Keep exactly 1 (Redis locks prevent duplicate execution)

### Vertical Scaling
Adjust Docker resource limits in `docker-compose.yml`:
```yaml
services:
  api:
    deploy:
      resources:
        limits:
          cpus: '2.0'
          memory: 2G
        reservations:
          cpus: '0.5'
          memory: 512M
```

## Monitoring

### Structured Logs
All logs are output as JSON to stdout:
```json
{
  "timestamp": "2026-08-18T12:34:56.789Z",
  "level": "INFO",
  "logger": "app.api.upload",
  "module": "upload",
  "function": "upload_nem12",
  "event": "api_request",
  "method": "POST",
  "path": "/api/v1/upload",
  "user_id": 123
}
```

Collect logs with:
- Docker: `docker compose logs -f`
- ELK Stack: Configure Filebeat to ship to Elasticsearch
- Cloud: Send to CloudWatch/Stackdriver/Datadog

### Metrics to Monitor
- **API Response Time**: Track P50, P95, P99 latencies
- **Worker Queue Depth**: Alert if > 100 jobs pending
- **Database Connections**: Monitor active/idle connections
- **Upload Processing Time**: Track NEM12 import duration
- **ML Training Success Rate**: Monitor failed training jobs
- **Notification Delivery Rate**: Track Expo push success/failure

## Security Checklist

- [ ] Set `DEBUG=false` in production
- [ ] Use strong `SECRET_KEY` (32+ random characters)
- [ ] Enable HTTPS (TLS 1.2+)
- [ ] Set restrictive `CORS_ORIGINS`
- [ ] Use strong database passwords
- [ ] Rotate secrets quarterly
- [ ] Enable database backups (see backup guide)
- [ ] Limit network access (firewall rules)
- [ ] Review logs for exposed secrets
- [ ] Set up rate limiting (already configured for auth)
- [ ] Enable database connection pooling
- [ ] Use encrypted environment variables

## Troubleshooting

### API Won't Start
```bash
# Check logs
docker compose logs api

# Common issues:
# - Database not ready → wait for health check
# - Migration not applied → run `alembic upgrade head`
# - Port conflict → check port 8000 availability
```

### Worker Not Processing Jobs
```bash
# Check worker logs
docker compose logs worker

# Check Redis connection
docker compose exec redis redis-cli ping

# Check queue depth
curl -H "Authorization: Bearer <token>" \
  https://api.gridsense.example.com/health/worker
```

### Staging Acceptance Gate

Run this after the API, worker, scheduler, PostgreSQL, and Redis are healthy:

```bash
python backend/scripts/staging_smoke.py \
  --base-url https://api.staging.gridsense.example.com \
  --sample-file backend/tests/sample_nem12.csv \
  --timeout-seconds 90
```

The smoke test creates an isolated user and verifies liveness, readiness, registration,
login, NEM12 import completion, usage analytics, recommendations, simulator automation
execution, and persisted fallback chat. Treat any non-zero result as a release blocker.

For a local Compose stack, use `http://localhost:8000` as the base URL. The script ignores
host proxy settings so local requests are sent directly to the target API.

### Database Connection Errors
```bash
# Check database health
docker compose exec db pg_isready -U postgres

# Check connection string
docker compose exec api env | grep DATABASE_URL

# Test connection manually
docker compose exec api python -c "from app.database import engine; engine.connect()"
```

### High Memory Usage
```bash
# Check Prophet model size
docker compose exec api du -sh app/models/*.joblib

# Adjust worker concurrency in docker-compose.yml:
command: python -m app.worker --burst --max-jobs 50
```

## Production Checklist

Before going live:
- [ ] Run full test suite: `pytest`
- [ ] Apply all migrations: `alembic upgrade head`
- [ ] Verify `docker compose ps` reports database, Redis, and API as healthy
- [ ] Run the staging acceptance gate with the target environment URL
- [ ] Verify `/health/worker` has at least one worker and no failed jobs after the smoke run
- [ ] Verify HTTPS certificate
- [ ] Test a representative large NEM12 upload and background completion time
- [ ] Test ML model training
- [ ] Test email delivery (password reset)
- [ ] Test notification delivery (Expo push)
- [ ] Configure monitoring and alerting
- [ ] Set up automated backups
- [ ] Document rollback procedure
- [ ] Load test API endpoints
- [ ] Review security settings
- [ ] Test disaster recovery procedure

## Rolling Updates

### Zero-Downtime Deployment
```bash
# 1. Pull latest code
git pull origin main

# 2. Build new images
docker compose build

# 3. Run migrations (safe for running systems)
docker compose run --rm api alembic upgrade head

# 4. Rolling restart API (one at a time)
for i in {1..4}; do
  docker compose up -d --no-deps --scale api=$i api
  sleep 10
done

# 5. Restart workers (safe to restart all at once)
docker compose restart worker

# 6. Restart scheduler (brief downtime acceptable)
docker compose restart scheduler
```

## Rollback Procedure

### If Deployment Fails
```bash
# 1. Preserve diagnostics before changing the stack
docker compose ps
docker compose logs --tail=200 api worker scheduler

# 2. Deploy the previously verified image or revision
git checkout <previous-commit>
docker compose up -d --build

# 3. Reverse a migration only when its downgrade is reviewed and data-safe
docker compose run --rm api alembic downgrade -1

# 4. Confirm service and workflow recovery
curl -f https://api.gridsense.example.com/health/ready
python backend/scripts/staging_smoke.py \
  --base-url https://api.gridsense.example.com \
  --sample-file backend/tests/sample_nem12.csv \
  --timeout-seconds 90
```

Do not run a database downgrade as a reflex. Prefer restoring a verified database backup when
the failed release introduced destructive schema or data changes. Record the deployed revision,
migration revision, smoke-test output, and rollback decision in the release incident log.
