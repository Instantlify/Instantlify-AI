ARG BACKEND_IMAGE=instantlify-backend:local
FROM node:22-bookworm-slim AS frontend
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN --mount=type=cache,target=/root/.npm npm ci
COPY frontend/ ./
ARG NEXT_PUBLIC_WS_URL=wss://dev.instantlify.com
ARG INSTANTLIFY_PRIVACY_URL=https://dev.instantlify.com/privacy/
ARG INSTANTLIFY_TERMS_URL=https://dev.instantlify.com/terms/
ARG INSTANTLIFY_SUPPORT_EMAIL=support@instantlify.com
ARG INSTANTLIFY_PRIVACY_EMAIL=support@instantlify.com
ENV BACKEND_INTERNAL_URL=http://127.0.0.1:8000 NEXT_TELEMETRY_DISABLED=1
ENV NEXT_PUBLIC_WS_URL=$NEXT_PUBLIC_WS_URL INSTANTLIFY_PRIVACY_URL=$INSTANTLIFY_PRIVACY_URL INSTANTLIFY_TERMS_URL=$INSTANTLIFY_TERMS_URL INSTANTLIFY_SUPPORT_EMAIL=$INSTANTLIFY_SUPPORT_EMAIL INSTANTLIFY_PRIVACY_EMAIL=$INSTANTLIFY_PRIVACY_EMAIL
RUN npm run build

FROM ${BACKEND_IMAGE} AS web
USER root
RUN apt-get update && apt-get install -y --no-install-recommends nginx libstdc++6 && rm -rf /var/lib/apt/lists/*
COPY --from=frontend /usr/local/bin/node /usr/local/bin/node
COPY --from=frontend --chown=app:app /web/.next/standalone /app/web
COPY --from=frontend --chown=app:app /web/.next/static /app/web/.next/static
COPY --from=frontend --chown=app:app /web/public /app/web/public
COPY --chown=app:app deploy/web/run.py deploy/web/health.py /app/deploy/
COPY --chown=app:app deploy/coolify-nginx.conf.template /app/deploy/nginx.template
ENV NODE_ENV=production PORT=3000 HOSTNAME=127.0.0.1 BACKEND_INTERNAL_URL=http://127.0.0.1:8000
USER app
WORKDIR /app
EXPOSE 8080
STOPSIGNAL SIGTERM
HEALTHCHECK --interval=5s --timeout=5s --start-period=60s --retries=12 CMD ["python", "/app/deploy/health.py"]
CMD ["python", "/app/deploy/run.py"]
