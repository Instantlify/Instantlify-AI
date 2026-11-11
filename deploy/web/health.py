"""Require both dependency readiness and a responding frontend before cutover."""

import os
import urllib.request


def check():
    headers = {"Host": os.environ["APP_DOMAIN"], "X-Forwarded-Proto": "https"}
    for url in (
        "http://127.0.0.1:8080/health/ready/",
        "http://127.0.0.1:3000/",
    ):
        request = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(request, timeout=2) as response:
            if response.status != 200:
                raise RuntimeError("Web image is not ready")


if __name__ == "__main__":
    check()
