#!/usr/bin/env python3

from __future__ import annotations

import argparse
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNNER_NAME = "generate-resume.sh"


def runner_wrapper() -> str:
    return """#!/usr/bin/env bash
set -euo pipefail

OUTPUT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$OUTPUT_DIR/../.." && pwd)"

exec "$ROOT/assets/generate-resume.sh" "$OUTPUT_DIR"
"""


def install_runner(output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    runner_path = output_dir / RUNNER_NAME
    runner_path.write_text(runner_wrapper(), encoding="utf8")
    runner_path.chmod(runner_path.stat().st_mode | 0o111)
    return runner_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Install a thin regeneration wrapper into one or more output folders."
    )
    parser.add_argument("output_dirs", nargs="+", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    installed = [str(install_runner(path.resolve())) for path in args.output_dirs]
    print("\n".join(installed))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
