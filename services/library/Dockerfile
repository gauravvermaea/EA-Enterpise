# EA Explorer library service image (phase 15.2, D346): the organisation's and the projects' libraries, a service of its
# own with its own database (eaxlibrary), migrations and API (/api/library/v1)
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
RUN chmod +x /app/entrypoint.sh \
 && useradd --system --uid 10002 --home /app eaxlib

USER eaxlib
EXPOSE 8100
ENTRYPOINT ["/app/entrypoint.sh"]
