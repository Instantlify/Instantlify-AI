"""Forward Stripe test webhooks locally without printing API/signing secrets.

Run with the backend virtualenv: python tools/stripe_local.py
Keep this process running while testing local billing. Ctrl+C stops forwarding.
"""

import json
import logging
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import stripe
from dotenv import dotenv_values, set_key

ROOT = Path(__file__).resolve().parents[1]
EVENTS = ",".join(
    [
        "customer.subscription.created",
        "customer.subscription.updated",
        "customer.subscription.deleted",
        "invoice.paid",
        "invoice.payment_failed",
        "checkout.session.completed",
        "checkout.session.async_payment_succeeded",
        "checkout.session.async_payment_failed",
    ]
)


def emit(data):
    print(json.dumps(data), flush=True)


def main():
    logging.getLogger("stripe").setLevel(logging.WARNING)
    values = dotenv_values(ROOT / ".env")
    key = values.get("STRIPE_SECRET_KEY", "")
    if not isinstance(key, str) or not re.fullmatch(r"(?:sk|rk)_test_[A-Za-z0-9]+", key):
        raise RuntimeError("A Stripe test secret key is required in the local environment.")
    if stripe.Balance.retrieve(api_key=key).livemode:
        raise RuntimeError("Live Stripe accounts are not accepted by this local helper.")
    cli = shutil.which("stripe")
    if not cli:
        raise RuntimeError("Install Stripe CLI before starting local forwarding.")
    port = int(values.get("INSTANTLIFY_BACKEND_PORT") or 8000)
    if not 1 <= port <= 65535:
        raise RuntimeError("Invalid local backend port.")
    target = f"http://127.0.0.1:{port}/webhooks/stripe/"
    child_env = {**os.environ, "STRIPE_API_KEY": key}
    hidden = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    common = [cli, "listen", "--skip-update", "--color", "off"]
    result = subprocess.run(
        common + ["--print-secret"],
        env=child_env,
        capture_output=True,
        text=True,
        timeout=45,
        creationflags=hidden,
    )
    match = re.search(r"whsec_[A-Za-z0-9]+", result.stdout + result.stderr)
    if result.returncode or not match:
        raise RuntimeError("Could not obtain the local listener signing secret.")
    set_key(str(ROOT / ".env"), "STRIPE_WEBHOOK_SECRET", match.group(0), quote_mode="auto")
    emit(
        {
            "event": "local_signing_secret_configured",
            "mode": "test",
            "forward_to": target,
            "next_step": "Recreate the local backend to load its updated environment.",
        }
    )
    cache = ROOT / ".cache" / "stripe-local"
    cache.mkdir(parents=True, exist_ok=True)
    process = subprocess.Popen(
        common + ["--events", EVENTS, "--forward-to", target],
        env=child_env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        stdin=subprocess.DEVNULL,
        creationflags=hidden,
    )
    (cache / "listener.json").write_text(
        json.dumps({"wrapper_pid": os.getpid(), "stripe_pid": process.pid, "target": target}),
        encoding="utf-8",
    )
    try:
        with (cache / "events.jsonl").open("a", encoding="utf-8") as log:
            for line in process.stdout:
                data = None
                if "Ready!" in line:
                    data = {"event": "listener_ready", "mode": "test", "forward_to": target}
                received = re.search(r"-->\s+([a-z_.]+)\s+\[(evt_[A-Za-z0-9]+)\]", line)
                delivered = re.search(r"\[(\d{3})\].*?\[(evt_[A-Za-z0-9]+)\]", line)
                if received:
                    data = {
                        "event": "stripe_event_received",
                        "type": received.group(1),
                        "id": received.group(2),
                    }
                if delivered:
                    data = {
                        "event": "forward_result",
                        "status": int(delivered.group(1)),
                        "id": delivered.group(2),
                    }
                # Raw CLI output can contain a signing secret or customer payload: never relay it.
                if data:
                    emit(data)
                    log.write(json.dumps(data) + "\n")
                    log.flush()
        if process.wait():
            raise RuntimeError("Stripe forwarding stopped unexpectedly.")
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
        (cache / "listener.json").unlink(missing_ok=True)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        emit({"event": "listener_stopped"})
    except Exception as error:
        # Do not expose provider bodies, keys or captured CLI output in failure traces.
        emit({"event": "listener_failed", "error_type": type(error).__name__})
        sys.exit(1)
