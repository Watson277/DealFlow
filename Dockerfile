FROM ghcr.io/astral-sh/uv:0.8.17-python3.11-bookworm-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH=/app

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,id=dealflow-uv,target=/root/.cache/uv,sharing=locked \
    uv sync --frozen --no-dev --no-install-project --extra local-embeddings

COPY alembic.ini ./
COPY alembic ./alembic
COPY app ./app

RUN groupadd --system dealflow \
    && useradd --system --gid dealflow --home-dir /app dealflow \
    && mkdir -p /app/.cache/huggingface \
    && chown -R dealflow:dealflow /app/.cache /app/app /app/alembic \
    && chown dealflow:dealflow /app/alembic.ini

USER dealflow

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
