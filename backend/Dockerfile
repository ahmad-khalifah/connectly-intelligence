# Connectly Intelligence API.
#   docker build -t connectly-api backend
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Wheels for GeoPandas, pyogrio (bundled GDAL), Shapely, pyproj and psycopg include their
# native libraries, so no system GIS packages are needed.
COPY pyproject.toml ./
COPY connectly ./connectly
COPY alembic ./alembic
COPY alembic.ini ./
# Editable install: the code stays in /app next to alembic.ini, where the CLI expects it.
RUN pip install -e . \
    && useradd --create-home --uid 10001 connectly \
    && mkdir -p /data \
    && chown connectly /data

USER connectly
ENV CONNECTLY_DATA_DIR=/data \
    CONNECTLY_ENVIRONMENT=production
EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=5 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4).status == 200 else 1)"

# Apply migrations, then serve. Data loading is a separate, explicit step (see README).
CMD ["sh", "-c", "connectly db upgrade && exec uvicorn connectly.api.main:app --host 0.0.0.0 --port 8000 --workers ${WEB_CONCURRENCY:-2}"]
