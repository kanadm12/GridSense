FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install the hash-locked dependency set that CI tests, then the project itself.
# pyproject.toml force-includes the AER retailer registry, so that file must exist
# before the editable build.
COPY pyproject.toml README.md requirements-dev.lock ./
COPY app/data/aer_retailer_uris_2026_01.json app/data/aer_retailer_uris_2026_01.json
RUN pip install --no-cache-dir --require-hashes -r requirements-dev.lock \
    && pip install --no-cache-dir --no-deps -e .

# Copy application code
COPY . .

# Run the application
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
