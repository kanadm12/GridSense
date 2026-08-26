"""Convenience script to run an RQ worker programmatically.

Usage: python -m app.worker
"""
from redis import Redis
from rq import Queue, Worker

from app.config import get_settings


def main():
    settings = get_settings()
    redis_url = getattr(settings, "redis_url", "redis://localhost:6379/0")
    conn = Redis.from_url(redis_url)
    q = Queue("default", connection=conn)
    worker = Worker([q], connection=conn)
    worker.work()


if __name__ == "__main__":
    main()
