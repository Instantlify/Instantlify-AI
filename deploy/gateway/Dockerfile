# Pin the inspected Nginx 1.30.6 / Brotli 1.2.1 base image.
FROM nginx:stable-alpine@sha256:583b7f2fce1cdb8da5ad5c39ebd3c33b98b87d493190e548bdee1fa8c619c311

# The base still ships libxslt 1.1.43-r3; require the newer Alpine package.
RUN apk upgrade --no-cache \
    && apk add --no-cache 'libxslt>=1.1.43-r4' 'zlib>=1.4-r0' \
    && nginx -t
