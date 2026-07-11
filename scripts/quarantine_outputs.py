#!/usr/bin/env python3

from __future__ import annotations

import json
import shutil
from pathlib import Path

from check_resume_quality import analyze_output_dir
from runtime_paths import ROOT


OUTPUT = ROOT / "output"
QUARANTINE = OUTPUT / "_quarantine"


def main() -> int:
    QUARANTINE.mkdir(exist_ok=True)
    moved: list[str] = []
    kept: list[str] = []
    for directory in sorted(OUTPUT.iterdir()):
        if not directory.is_dir() or directory.name.startswith("_"):
            continue
        report = analyze_output_dir(directory, reinspect_pdf=False)
        if report["ok"]:
            kept.append(directory.name)
            continue
        destination = QUARANTINE / directory.name
        if destination.exists():
            raise RuntimeError(f"Quarantine destination already exists: {destination}")
        shutil.move(str(directory), destination)
        (destination / "quarantine-report.json").write_text(
            json.dumps(report, indent=2) + "\n", encoding="utf8"
        )
        moved.append(directory.name)
    print(json.dumps({"moved": moved, "kept": kept}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
