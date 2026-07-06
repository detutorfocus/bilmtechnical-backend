FROM python:3.12-slim

WORKDIR /app

# ── System deps ────────────────────────────────────────────────────────────
# Fixed: apt-get now uses retries + shorter timeouts so a single flaky
# connection to a Debian mirror doesn't stall the build for 30 minutes.
# If a mirror is unreachable, apt fails fast (20s) and retries (5x)
# instead of hanging on "delayed item" for nearly half an hour.
RUN apt-get update -o Acquire::Retries=5 -o Acquire::http::Timeout=20 -o Acquire::https::Timeout=20 && \
    apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
        curl \
        -o Acquire::Retries=5 -o Acquire::http::Timeout=20 -o Acquire::https::Timeout=20 && \
    rm -rf /var/lib/apt/lists/*

# Copy requirements first — Docker layer cache is tied to this file.
# As long as requirements.txt doesn't change, this apt-get layer is
# NEVER re-run on subsequent builds — it's cached permanently.
COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt && \
    python -c "import bcrypt; h=bcrypt.hashpw(b'test',bcrypt.gensalt()); print('bcrypt OK:', bcrypt.checkpw(b'test',h))" && \
    python -c "import email_validator; print('email_validator OK')"

COPY . .
RUN mkdir -p app/static

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
