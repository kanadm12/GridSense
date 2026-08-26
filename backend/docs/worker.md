# Running the RQ worker (development)

This project includes a lightweight RQ-based worker proof-of-concept to run NEM12 import jobs outside the FastAPI process.

Prerequisites:
- Docker (recommended) or a local Redis instance.

Start Redis with Docker:

```bash
# start Redis in background
docker run -d --name gridsense-redis -p 6379:6379 redis:7
```

Start an RQ worker from the project root:

```bash
# Activate virtualenv, then
python -m app.worker
```

Or run using `rq` CLI (requires `rq` installed in the env):

```bash
# from backend/ directory
rq worker default --url redis://localhost:6379/0
```

Notes:
- The upload endpoint will attempt to enqueue jobs in Redis; if Redis is not available, it falls back to FastAPI `BackgroundTasks` and processes imports in-process.
- The upload status endpoint now returns `rq_job_id` and `rq_job_status` when available.

Cleanup Redis container:

```bash
docker stop gridsense-redis && docker rm gridsense-redis
```
