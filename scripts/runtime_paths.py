from __future__ import annotations

import sysconfig
from pathlib import Path


def _resource_root() -> Path:
    source_root = Path(__file__).resolve().parents[1]
    if (source_root / "config" / "resume-policy.json").is_file():
        return source_root

    installed_root = Path(sysconfig.get_path("data")) / "cvfoundry"
    if (installed_root / "config" / "resume-policy.json").is_file():
        return installed_root

    raise RuntimeError(
        "CvFoundry runtime resources are unavailable. Reinstall the package or run from a source checkout."
    )


ROOT = _resource_root()
