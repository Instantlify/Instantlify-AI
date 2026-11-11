FROM ghcr.io/astral-sh/uv:0.13.7 AS uv
FROM python:3.13.18-slim-bookworm AS dependencies

COPY --from=uv /uv /usr/local/bin/uv

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# ffmpeg converts inbox voice notes recorded in the browser (WebM/OGG) to M4A, which
# every messaging channel accepts.
RUN apt-get update \
    && apt-get upgrade -y \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --uid 10001 app && chown app:app /app
USER app

RUN uv venv /app/.venv
COPY --chown=app:app requirements.txt pyproject.toml ./
RUN uv pip install --no-cache -r requirements.txt

COPY --chown=app:app config ./config
COPY --chown=app:app apps ./apps
COPY --chown=app:app manage.py ./

FROM dependencies AS runtime
USER root
# Dependency installers are build tools, not application runtime dependencies.
RUN rm /usr/local/bin/uv \
    && python -m pip uninstall -y pip
USER app

EXPOSE 8000
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000"]

FROM dependencies AS test
COPY --chown=app:app tests ./tests
RUN pip install --no-cache-dir pytest pytest-django
CMD ["python", "-m", "pytest", "-q"]

