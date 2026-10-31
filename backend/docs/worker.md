# Running the RQ worker (development)

The RQ worker runs NEM12 imports outside the FastAPI process. API startup and
the core demo do not require Redis; the Compose API service can start without
the Redis service.

## Start the worker

The worker requires a reachable Redis instance. From the repository root:

```powershell
docker compose up -d redis
Push-Location backend
..\.venv311\Scripts\python.exe -m app.worker
Pop-Location
```

The worker consumes the `default` queue. For a local Redis installation, set
`REDIS_URL` to the reachable server before starting the API and worker.

## Idempotency and recovery

- An upload's SHA-256 hash is unique per user. Repeated content returns the
 existing upload rather than creating a second import record.
- A failed RQ job can be retried by submitting the same file again. The API
 reuses its upload row when the queue reports a terminal failure.
- Import retries skip meter timestamps already committed by an earlier attempt,
 so a worker interruption after a committed chunk does not duplicate those
 readings.
- Optional alert publication and ML-training enqueue failures are logged and do
 not convert a successfully imported file into a failed import.

## Redis-unavailable fallback and its durability risk

If RQ enqueue fails, FastAPI runs the import as an in-process background task
with its own database session. This avoids reusing the request-scoped session
and lets a small local demo continue without Redis. The fallback is **not
durable**: a process restart can interrupt it, and there is no persistent
outbox or automatic recovery if the process dies before the upload row is
updated. Use Redis/RQ for long-running or production imports. A repeated upload
can retry a failed queue job; it cannot prove or recover work lost by an
in-process process crash.

The status endpoint returns `rq_job_status: "unavailable"` when the job state
cannot be checked because Redis is unavailable; this is distinct from a missing
or failed job.

## Operational checks

The unit test suite covers duplicate requests, a failed RQ job retry, a
Redis-unavailable fallback with an independent session, and an importer
interruption after a committed chunk followed by a deduplicating retry. A real
Compose worker-kill/restart check must still be run in staging when Docker and
Redis are available.
