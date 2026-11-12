# Rebuild the privilege-drop helper with patched Go and module dependencies.
FROM golang:1.26.11-bookworm AS gosu
WORKDIR /src
ADD https://github.com/tianon/gosu.git#1.20 .
RUN go get golang.org/x/sys@v0.44.0 \
    && CGO_ENABLED=0 go build -trimpath -o /out/gosu .

# Retain PostgreSQL 17 and Bookworm for the existing data directory.
FROM pgvector/pgvector:0.8.7-pg17-bookworm
RUN apt-get update && apt-get upgrade -y && rm -rf /var/lib/apt/lists/*
COPY --from=gosu /out/gosu /usr/local/bin/gosu
RUN gosu nobody true
