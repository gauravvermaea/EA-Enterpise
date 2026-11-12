# EA Explorer API image (ours): Flask API + background job runner, one container
FROM python:3.12-slim

# PYTHONPATH: command-line tools (alembic, procrastinate) must find our eax package
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app

# the Debian packages' own fixes, when there are any (R2.24)
RUN apt-get update && apt-get upgrade -y && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
RUN chmod +x /app/entrypoint.sh \
 && useradd --system --uid 10001 --home /app eax \
 && mkdir -p /data/imports /data/exports && chown -R eax /data

USER eax
EXPOSE 8000 8001
ENTRYPOINT ["/app/entrypoint.sh"]
