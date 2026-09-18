#!/usr/bin/env python3
"""Validate and release the Zapier app, the n8n community node and the Make app.

    python connectors/scripts/publish.py check                 # all three, no network
    python connectors/scripts/publish.py zapier --version 1.1.0 [--push]
    python connectors/scripts/publish.py n8n --version 1.1.0 [--publish]
    python connectors/scripts/publish.py make                  # validate + zip bundle

Without --push / --publish every command is a dry run: tests, validation and packaging
run, nothing leaves the machine. Releasing needs credentials in the environment:
ZAPIER_DEPLOY_KEY for `zapier push`, NPM_TOKEN for `npm publish`. Make has no publishing
CLI: the bundle is uploaded in Make's developer platform, whose review lists it.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEMVER = re.compile(r"^\d+\.\d+\.\d+$")
NPM = "npm.cmd" if os.name == "nt" else "npm"
NPX = "npx.cmd" if os.name == "nt" else "npx"
# The CLI is not a package dependency; pin its major to zapier-platform-core's.
ZAPIER_CLI = ("--yes", "zapier-platform-cli@17")


class Failure(Exception):
    pass


def run(*command, cwd, env=None):
    print(f"$ {' '.join(command)}  ({cwd.relative_to(ROOT.parent)})", flush=True)
    result = subprocess.run(command, cwd=cwd, env={**os.environ, **(env or {})})
    if result.returncode:
        raise Failure(f"{command[0]} {command[1] if len(command) > 1 else ''} failed")


def read_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise Failure(f"{path.relative_to(ROOT)}: {exc}") from None


def set_version(package_dir, version):
    """Write the release version into package.json (and the lockfile's root entry)."""
    if not SEMVER.match(version):
        raise Failure(f"version must look like 1.2.3, got {version!r}")
    for name in ["package.json", "package-lock.json"]:
        path = package_dir / name
        if not path.exists():
            continue
        data = read_json(path)
        data["version"] = version
        if name == "package-lock.json" and "" in data.get("packages", {}):
            data["packages"][""]["version"] = version
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


# ------------------------------------------------------------------------ Zapier


def zapier(version=None, push=False):
    path = ROOT / "zapier"
    if version:
        set_version(path, version)
    run(NPM, "ci", cwd=path)
    run(NPM, "test", cwd=path)
    run(NPX, *ZAPIER_CLI, "validate", cwd=path)
    if push:
        if not os.environ.get("ZAPIER_DEPLOY_KEY"):
            raise Failure("ZAPIER_DEPLOY_KEY is not set")
        if not (path / ".zapierapprc").exists():
            raise Failure("connectors/zapier/.zapierapprc missing: run `zapier register` once")
        # Pushes a private version. Promoting it to users is a separate, deliberate step
        # (`zapier promote <version>`), and the public listing goes through Zapier review.
        run(NPX, *ZAPIER_CLI, "push", cwd=path)


# --------------------------------------------------------------------------- n8n


def check_n8n_package(path):
    package = read_json(path / "package.json")
    problems = []
    if not package.get("name", "").startswith(("n8n-nodes-", "@")):
        problems.append("name must start with n8n-nodes- (or be scoped) to install by name")
    if "n8n-community-node-package" not in package.get("keywords", []):
        problems.append('keywords must include "n8n-community-node-package"')
    declared = package.get("n8n", {}).get("credentials", []) + package.get("n8n", {}).get(
        "nodes", []
    )
    if not declared:
        problems.append("package.json n8n section lists no nodes or credentials")
    shipped = package.get("files", [])
    for entry in declared:
        if not (path / entry).exists():
            problems.append(f"{entry} is declared but was not built")
        if not any(entry == item or entry.startswith(item.rstrip("/") + "/") for item in shipped):
            problems.append(f"{entry} is not covered by package.json files")
    if problems:
        raise Failure("n8n package: " + "; ".join(problems))


def n8n(version=None, publish=False):
    path = ROOT / "n8n"
    if version:
        set_version(path, version)
    run(NPM, "ci", cwd=path)
    run(NPM, "run", "lint", cwd=path)
    run(NPM, "run", "build", cwd=path)
    check_n8n_package(path)
    run(NPM, "pack", "--dry-run", cwd=path)
    if publish:
        if not os.environ.get("NPM_TOKEN"):
            raise Failure("NPM_TOKEN is not set")
        run(NPM, "publish", "--access", "public", cwd=path)


# -------------------------------------------------------------------------- Make

MODULE_TYPES = {"action", "search", "trigger", "instant_trigger", "responder", "universal"}


def check_make_app(path):
    problems = []
    base = read_json(path / "base.json")
    if "{{connection.apiKey}}" not in json.dumps(base.get("headers", {})):
        problems.append("base.json must send the connection's API key")
    connections = {p.stem: read_json(p) for p in (path / "connections").glob("*.json")}
    webhooks = {p.stem: read_json(p) for p in (path / "webhooks").glob("*.json")}
    modules = {p.stem: read_json(p) for p in (path / "modules").glob("*.json")}
    if not connections or not modules:
        problems.append("need at least one connection and one module")
    for name, connection in connections.items():
        if not {"type", "label", "parameters"} <= set(connection):
            problems.append(f"connections/{name}.json needs type, label and parameters")
    for name, hook in webhooks.items():
        if hook.get("connection") not in connections:
            problems.append(f"webhooks/{name}.json uses unknown connection")
    for name, module in modules.items():
        where = f"modules/{name}.json"
        if module.get("name") != name:
            problems.append(f"{where}: name must match the file name")
        if module.get("type") not in MODULE_TYPES:
            problems.append(f"{where}: unknown type {module.get('type')!r}")
        if module.get("connection") and module["connection"] not in connections:
            problems.append(f"{where}: unknown connection {module['connection']!r}")
        if module.get("webhook") and module["webhook"] not in webhooks:
            problems.append(f"{where}: unknown webhook {module['webhook']!r}")
        if not module.get("label"):
            problems.append(f"{where}: needs a label")
        if module.get("type") != "instant_trigger" and not module.get("communication"):
            problems.append(f"{where}: needs a communication block")
        url = (module.get("communication") or {}).get("url", "")
        if url and not url.startswith("/api/v1/"):
            problems.append(f"{where}: must call the public API (/api/v1/), got {url}")
    if problems:
        raise Failure("Make app: " + "; ".join(problems))
    return len(modules)


def make(bundle=True):
    path = ROOT / "make"
    count = check_make_app(path)
    print(f"Make app valid: {count} modules")
    if bundle:
        out = ROOT / "dist"
        out.mkdir(exist_ok=True)
        target = out / "nemio-make-app.zip"
        with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
            for file in sorted(path.rglob("*.json")):
                archive.write(file, file.relative_to(path))
        print(f"Bundle for Make's developer platform: {target.relative_to(ROOT.parent)}")


# ---------------------------------------------------------------------------- CLI


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="target", required=True)
    sub.add_parser("check", help="validate all three packages, no publishing")
    z = sub.add_parser("zapier")
    z.add_argument("--version")
    z.add_argument("--push", action="store_true")
    n = sub.add_parser("n8n")
    n.add_argument("--version")
    n.add_argument("--publish", action="store_true")
    sub.add_parser("make")
    args = parser.parse_args(argv)
    if not shutil.which(NPM) and args.target != "make":
        print("npm is required", file=sys.stderr)
        return 2
    try:
        if args.target == "check":
            zapier()
            n8n()
            make(bundle=False)
        elif args.target == "zapier":
            zapier(args.version, args.push)
        elif args.target == "n8n":
            n8n(args.version, args.publish)
        else:
            make()
    except Failure as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
