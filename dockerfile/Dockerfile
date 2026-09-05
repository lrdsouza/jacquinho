# syntax=docker/dockerfile:1.7
#
# Image for the Jacquinho MCP servers (FastMCP + openpyxl).
#
# This does NOT build Hermes. The official `nousresearch/hermes-agent` image
# compiles SQLite from source because of the Debian WAL-reset bug, and the
# agent's FTS5 memory depends on it. Rebuilding that here would swap a correct
# image for a broken one. See dockerfile/docker-compose.yaml.
#
# Build from the REPO ROOT:
#   docker build -f dockerfile/Dockerfile -t jacquinho-mcp:local .

FROM python:3.13-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY dockerfile/requirements.txt ./requirements.txt
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/
COPY tests/ ./tests/
COPY pytest.ini ./pytest.ini

# The spreadsheet is mounted read-only and state lives in a named volume:
# none of Dona Maria's data is baked into the image.
ENV PANTRY_XLSX=/data/despensa_dona_maria.xlsx \
    POSTGRES_DSN=postgresql://jacquinho:jacquinho@postgres:5432/jacquinho \
    TOP_UP_BUDGET=80 \
    PLATFORM_FEE=0.10 \
    SEARCH_PROVIDER=auto \
    MCP_HOST=0.0.0.0 \
    MCP_PORT=8000

RUN useradd --uid 10001 --create-home --shell /usr/sbin/nologin app \
    && mkdir -p /data \
    && chown -R app:app /app
USER app

EXPOSE 8000

# The MCP endpoint answers 406/400 to a plain GET (it expects session
# negotiation), so the healthcheck only proves the port accepts connections.
HEALTHCHECK --interval=15s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import socket,os,sys; s=socket.create_connection(('127.0.0.1', int(os.environ['MCP_PORT'])), 2); s.close()" || exit 1

CMD ["python", "-m", "app.mcps.server"]
