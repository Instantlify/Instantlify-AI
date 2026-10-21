FROM ghcr.io/astral-sh/uv:0.10.11 AS uv
FROM python:3.12-slim AS runtime

COPY --from=uv /uv /usr/local/bin/uv

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

RUN useradd --create-home --uid 10001 app && chown app:app /app
USER app

RUN uv venv /app/.venv
COPY --chown=app:app requirements.txt pyproject.toml ./
RUN uv pip install --no-cache -r requirements.txt

COPY --chown=app:app config ./config
COPY --chown=app:app apps ./apps
COPY --chown=app:app manage.py ./

EXPOSE 8000
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000"]

FROM runtime AS test
COPY --chown=app:app tests ./tests
RUN pip install --no-cache-dir pytest pytest-django
CMD ["python", "-m", "pytest", "-q"]

