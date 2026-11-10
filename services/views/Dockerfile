# EA Explorer views service image (phases 28 and 29, D405): the models' drawn views (draw.io files and their versions) and
# their own generated-view definitions, a service of its own with its own database (eaxviews) and API (/api/views/v1)
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
 && useradd --system --uid 10003 --home /app eaxviews

USER eaxviews
EXPOSE 8110
ENTRYPOINT ["/app/entrypoint.sh"]
