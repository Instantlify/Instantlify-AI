FROM ghcr.io/astral-sh/uv:0.10.11 AS uv
FROM python:3.12-slim AS runtime
COPY --from=uv /uv /usr/local/bin/uv
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PATH="/app/.venv/bin:$PATH"
WORKDIR /app
RUN useradd --create-home --uid 10001 app && chown app:app /app
USER app
COPY --chown=app:app pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev
COPY --chown=app:app config ./config
COPY --chown=app:app apps ./apps
COPY --chown=app:app manage.py ./
EXPOSE 8000
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000"]

FROM runtime AS test
COPY --chown=app:app tests ./tests
RUN uv sync --frozen
CMD ["python", "-m", "pytest", "-q"]
