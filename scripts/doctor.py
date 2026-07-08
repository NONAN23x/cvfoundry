#!/usr/bin/env python3

from __future__ import annotations

import json
import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from profile_config import DEFAULT_PROFILE, ProfileConfigError, load_profile, resolve_effective_policy


ROOT = Path(__file__).resolve().parents[1]


def command_version(command: str, *arguments: str) -> tuple[bool, str]:
    resolved = shutil.which(command)
    if not resolved:
        return False, "missing"
    result = subprocess.run(
        [resolved, *arguments], capture_output=True, text=True, check=False
    )
    output = (result.stdout or result.stderr).strip().splitlines()
    return result.returncode == 0, output[0] if output else resolved


def main() -> int:
    parser = argparse.ArgumentParser(description="Check jobs-tailor runtime and profile dependencies.")
    parser.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    args = parser.parse_args()
    checks: dict[str, dict[str, object]] = {}
    checks["python"] = {
        "ok": sys.version_info >= (3, 11),
        "detail": sys.version.split()[0],
    }
    try:
        import uno  # noqa: F401

        checks["pythonUno"] = {"ok": True, "detail": "available"}
    except ImportError as error:
        checks["pythonUno"] = {"ok": False, "detail": str(error)}
    for name, version_args in (
        ("libreoffice", ("--version",)),
        ("pdfinfo", ("-v",)),
        ("pdftotext", ("-v",)),
        ("pdffonts", ("-v",)),
        ("pdftoppm", ("-v",)),
        ("fc-scan", ("--version",)),
    ):
        ok, detail = command_version(name, *version_args)
        checks[name] = {"ok": ok, "detail": detail}

    try:
        profile = load_profile(args.profile)
        effective_policy = resolve_effective_policy(profile)
        font_files = [Path(path) for path in profile["theme"]["font"]["files"].values()]
        checks["profile"] = {
            "ok": True,
            "detail": {
                "path": str(profile["root"]),
                "candidate": profile["cv"]["basics"]["name"],
                "enabledSections": effective_policy["enabledSections"],
                "targetPages": effective_policy["targetPages"],
                "maxPages": effective_policy["maxPages"],
            },
        }
        checks["themeFonts"] = {
            "ok": len(font_files) == 4
            and all(path.is_file() and path.stat().st_size > 0 for path in font_files),
            "detail": {
                "family": profile["theme"]["font"]["family"],
                "files": [str(path) for path in font_files],
            },
        }
    except (OSError, ProfileConfigError, ValueError) as error:
        checks["profile"] = {"ok": False, "detail": str(error)}

    generator = ROOT / "assets" / "generate-resume.sh"
    checks["generatorExecutable"] = {
        "ok": generator.exists() and os.access(generator, os.X_OK),
        "detail": str(generator),
    }
    try:
        output_dir = ROOT / "output"
        output_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=output_dir):
            pass
        checks["outputWritable"] = {"ok": True, "detail": str(output_dir)}
    except OSError as error:
        checks["outputWritable"] = {"ok": False, "detail": str(error)}

    result = {"ok": all(bool(check["ok"]) for check in checks.values()), "checks": checks}
    print(json.dumps(result, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
