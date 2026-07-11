#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROFILE = "profiles/local"
DEFAULT_IMAGE = "cvfoundry:latest"
FINGERPRINT_PATHS = ("Dockerfile", "pyproject.toml", "uv.lock", "src", "scripts", "assets", "config", "templates", "themes", "profiles")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Warm CvFoundry before an agent tailors a resume."
    )
    parser.add_argument(
        "--profile",
        default=DEFAULT_PROFILE,
        help=f"profile directory to validate (default: {DEFAULT_PROFILE})",
    )
    parser.add_argument(
        "--image",
        default=DEFAULT_IMAGE,
        help=f"Docker renderer image tag to check/build (default: {DEFAULT_IMAGE})",
    )
    parser.add_argument(
        "--skip-docker",
        action="store_true",
        help="skip Docker image check/build",
    )
    parser.add_argument(
        "--rebuild-docker",
        action="store_true",
        help="rebuild the Docker image even if it already exists",
    )
    return parser.parse_args()


def say(message: str) -> None:
    print(f"\n==> {message}", flush=True)


def env() -> dict[str, str]:
    values = os.environ.copy()
    values.setdefault("UV_CACHE_DIR", ".uv-cache")
    return values


def run(
    command: list[str],
    *,
    check: bool = True,
    capture: bool = False,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=ROOT,
        env=env(),
        check=check,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
    )


def require_command(name: str) -> None:
    try:
        run([name, "--version"], capture=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        raise SystemExit(f"error: required command not found or unusable: {name}")


def check_venv_writable() -> None:
    venv = ROOT / ".venv"
    if not venv.exists():
        if not os.access(ROOT, os.W_OK):
            raise SystemExit(f"error: repository is not writable: {ROOT}")
        return
    if not venv.is_dir():
        raise SystemExit("error: .venv exists but is not a directory")
    probe = venv / ".cvfoundry-preflight-write-test"
    try:
        probe.write_text("ok", encoding="utf8")
        probe.unlink()
    except OSError as exc:
        raise SystemExit(
            "error: .venv is not writable by this user. Fix ownership, then rerun:\n"
            f"  sudo chown -R $(id -u):$(id -g) {venv}\n"
            f"details: {exc}"
        )


def load_json_from(command: list[str]) -> dict[str, object]:
    result = run(command, capture=True)
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        print(result.stdout, file=sys.stderr)
        print(result.stderr, file=sys.stderr)
        raise SystemExit(f"error: expected JSON from {' '.join(command)}: {exc}")


def ensure_profile_ready(profile: str) -> None:
    say("Running profile first-run")
    first_run = load_json_from(["uv", "run", "jobs-tailor", "first-run", "--profile", profile])
    if not first_run.get("ok") or not first_run.get("ready"):
        print(json.dumps(first_run, indent=2), file=sys.stderr)
        raise SystemExit("error: profile first-run failed; finish profile setup before tailoring.")
    print(f"profile ready: {first_run.get('profile')}")

    say("Validating profile")
    validation = load_json_from(["uv", "run", "jobs-tailor", "validate", "--profile", profile])
    if not validation.get("ok"):
        print(json.dumps(validation, indent=2), file=sys.stderr)
        raise SystemExit("error: profile validation failed.")
    sections = validation.get("sections") or []
    if isinstance(sections, list):
        print("validated sections: " + ", ".join(str(section) for section in sections))


def source_fingerprint() -> str:
    digest = hashlib.sha256()
    excluded = {".git", ".venv", ".agent-venv", ".uv-cache", "output", "knowledge-base", "private", "local"}
    paths: list[Path] = []
    for name in FINGERPRINT_PATHS:
        path = ROOT / name
        if path.is_file():
            paths.append(path)
        elif path.is_dir():
            paths.extend(candidate for candidate in path.rglob("*") if candidate.is_file())
    for path in sorted(paths):
        relative = path.relative_to(ROOT)
        if any(part in excluded for part in relative.parts):
            continue
        digest.update(str(relative).encode("utf8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def docker_image_fingerprint(image: str) -> str | None:
    result = run(["docker", "image", "inspect", image], check=False, capture=True)
    if result.returncode != 0:
        return None
    try:
        images = json.loads(result.stdout)
        labels = images[0].get("Config", {}).get("Labels") or {}
        value = labels.get("org.opencontainers.image.revision")
        return value if isinstance(value, str) else None
    except (IndexError, TypeError, json.JSONDecodeError):
        return None


def ensure_docker_image(image: str, rebuild: bool) -> None:
    fingerprint = source_fingerprint()
    current_fingerprint = docker_image_fingerprint(image)
    if rebuild or current_fingerprint != fingerprint:
        say(f"Building Docker renderer image {image}")
        run(
            [
                "docker",
                "build",
                "--build-arg",
                f"CVFOUNDRY_SOURCE_SHA256={fingerprint}",
                "-t",
                image,
                ".",
            ]
        )
    else:
        say(f"Docker renderer image matches the current source: {image}")


def main() -> int:
    args = parse_args()
    os.chdir(ROOT)

    say("Checking required commands")
    require_command("uv")
    if not args.skip_docker:
        require_command("docker")

    say("Checking .venv writability")
    check_venv_writable()

    say("Syncing Python environment")
    run(["uv", "sync", "--frozen"])

    ensure_profile_ready(args.profile)

    if not args.skip_docker:
        ensure_docker_image(args.image, args.rebuild_docker)

    say("Preflight complete")
    print("Use this environment variable for agent uv commands:")
    print(f"  UV_CACHE_DIR={env()['UV_CACHE_DIR']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
