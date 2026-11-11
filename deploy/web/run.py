"""Run the web tier as one health-gated Coolify rolling application.

Workers, scheduler, PostgreSQL and Redis intentionally run outside this process.
"""

import os
import signal
import subprocess
import time
from pathlib import Path


def nginx_config(template, app_domain, admin_host):
    if not app_domain or not admin_host:
        raise ValueError("APP_DOMAIN and PLATFORM_ADMIN_HOST are required")
    for hostname in (app_domain, admin_host):
        if any(
            char not in "abcdefghijklmnopqrstuvwxyz0123456789.-" for char in hostname
        ):
            raise ValueError("Use a lowercase hostname without scheme or port")
    routes = template.replace("${APP_DOMAIN}", app_domain).replace(
        "${PLATFORM_ADMIN_HOST}", admin_host
    )
    routes = routes.replace("listen 80;", "listen 8080;")
    routes = routes.replace("backend:8000", "127.0.0.1:8000")
    routes = routes.replace("frontend:3000", "127.0.0.1:3000")
    return (
        "pid /tmp/instantlify-nginx.pid;\n"
        "error_log /dev/stderr warn;\nevents {}\nhttp {\n"
        "include /etc/nginx/mime.types;\n"
        "client_body_temp_path /tmp/instantlify-body;\n"
        "proxy_temp_path /tmp/instantlify-proxy;\n"
        "fastcgi_temp_path /tmp/instantlify-fastcgi;\n"
        "uwsgi_temp_path /tmp/instantlify-uwsgi;\n"
        "scgi_temp_path /tmp/instantlify-scgi;\n" + routes + "\n}\n"
    )


def migrate():
    """Serialize concurrent replica starts without changing live database identity."""
    import django

    django.setup()
    from django.core.management import call_command
    from django.db import connection

    if connection.vendor != "postgresql":
        raise RuntimeError("Rolling web deployments require PostgreSQL")
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_lock(913714521)")
        try:
            call_command("migrate", interactive=False)
        finally:
            cursor.execute("SELECT pg_advisory_unlock(913714521)")
    connection.close()


def stop(process, sig, seconds):
    if process.poll() is None:
        process.send_signal(sig)
        try:
            process.wait(timeout=seconds)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


def main():
    if os.environ.get("DJANGO_SETTINGS_MODULE") != "config.settings.production":
        raise RuntimeError("Configure production Django settings for this web image")
    config = nginx_config(
        Path("/app/deploy/nginx.template").read_text(),
        os.environ.get("APP_DOMAIN", ""),
        os.environ.get("PLATFORM_ADMIN_HOST", ""),
    )
    Path("/tmp/instantlify-nginx.conf").write_text(config)
    if os.environ.get("MIGRATE_ON_START", "true").lower() == "true":
        migrate()
    shutting_down = False

    def request_stop(*_):
        nonlocal shutting_down
        shutting_down = True

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    children = []
    nginx = None
    failed = False
    try:
        children.append(
            subprocess.Popen(
                [
                    "uvicorn",
                    "config.asgi:application",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    "8000",
                    "--workers",
                    "2",
                    "--no-access-log",
                    "--timeout-graceful-shutdown",
                    "15",
                ]
            )
        )
        children.append(subprocess.Popen(["node", "server.js"], cwd="/app/web"))
        nginx = subprocess.Popen(
            [
                "nginx",
                "-c",
                "/tmp/instantlify-nginx.conf",
                "-g",
                "daemon off;",
            ]
        )
        while not shutting_down:
            if any(child.poll() is not None for child in [*children, nginx]):
                failed = True
                break
            time.sleep(0.25)
    finally:
        # Drain proxy requests before terminating the processes serving them.
        if nginx:
            stop(nginx, signal.SIGQUIT, 35)
        for child in children:
            stop(child, signal.SIGTERM, 10)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
