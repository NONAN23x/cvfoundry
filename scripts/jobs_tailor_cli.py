#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from check_resume_quality import analyze_output_dir
from generate_fit_summary import build_summary, render_markdown
from generate_resume import generate
from install_output_runner import install_runner
from payload_v3 import from_legacy_payload
from profile_assembly import assemble_profile_resume
from profile_config import (
    DEFAULT_PROFILE,
    ProfileConfigError,
    load_profile,
    resolve_effective_policy,
)


ROOT = Path(__file__).resolve().parents[1]


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf8")


def _decision_report(
    policy: dict[str, Any],
    *,
    stage: str,
    payload: dict[str, Any] | None = None,
    layout: dict[str, Any] | None = None,
) -> dict[str, Any]:
    selected = {
        section["sourceId"]: [item["sourceId"] for item in section.get("items", [])]
        for section in (payload or {}).get("sections", [])
    }
    return {
        "schemaVersion": 1,
        "stage": stage,
        "document": policy["document"],
        "sections": [
            {
                "sourceId": section["sourceId"],
                "selectionMode": section["selectionMode"],
                "availableEntryCount": section["availableEntryCount"],
                "resolvedEntryCount": section["effectiveEntryCount"],
                "resolvedBulletCounts": section["effectiveBulletCounts"],
                "requiredSourceIds": section["requiredSourceIds"],
                "excludedSourceIds": section["excludedSourceIds"],
                "selectedSourceIds": selected.get(section["sourceId"]),
            }
            for section in policy["sections"]
        ],
        "layout": (
            {
                "pageCount": layout.get("pageCount"),
                "targetStatus": layout.get("targetStatus"),
                "spacingLevel": layout.get("spacingLevel"),
                "pageBottomWhitespaceMm": layout.get("pageBottomWhitespaceMm"),
                "pageUsedHeightPercent": layout.get("pageUsedHeightPercent"),
                "suggestions": layout.get("suggestions", []),
            }
            if layout
            else None
        ),
    }


def command_init(args: argparse.Namespace) -> dict[str, Any]:
    destination = args.profile.resolve()
    if destination.exists() and any(destination.iterdir()):
        raise ValueError(f"Profile directory is not empty: {destination}")
    destination.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / "templates" / "profile" / "CV.md", destination / "CV.md")
    shutil.copy2(ROOT / "templates" / "profile" / "Writing-Style.md", destination / "Writing-Style.md")
    shutil.copy2(ROOT / "templates" / "profile" / "resume.json", destination / "resume.json")
    return {"ok": True, "profile": str(destination)}


def command_validate(args: argparse.Namespace) -> dict[str, Any]:
    profile = load_profile(args.profile)
    effective_policy = resolve_effective_policy(profile)
    return {
        "ok": True,
        "profile": str(profile["root"]),
        "candidate": profile["cv"]["basics"]["name"],
        "sections": [item["sourceId"] for item in profile["config"]["sections"]],
        "hashes": profile["hashes"],
        "effectivePolicy": effective_policy,
    }


def command_prepare(args: argparse.Namespace) -> dict[str, Any]:
    profile = load_profile(args.profile)
    effective_policy = resolve_effective_policy(profile)
    job_text = args.job.read_text(encoding="utf8")
    output = args.out.resolve()
    output.mkdir(parents=True, exist_ok=True)
    shutil.copy2(args.job, output / "job-description.md")
    fit = build_summary(job_text, profile["cv"])
    enabled = {section["sourceId"] for section in profile["config"]["sections"]}
    if "projects" not in enabled:
        fit["projectRanking"] = []
        fit["recommendedProjectIds"] = []
    if "experience" not in enabled:
        fit["experienceRanking"] = []
    fit["sectionRankings"] = {
        section_id: ranking
        for section_id, ranking in fit.get("sectionRankings", {}).items()
        if section_id in enabled
    }
    _write_json(output / "fit-summary.json", fit)
    (output / "fit-summary.md").write_text(render_markdown(fit), encoding="utf8")
    brief = {
        "schemaVersion": 3,
        "profileHashes": profile["hashes"],
        "document": profile["config"]["document"],
        "effectivePolicy": effective_policy,
        "eligibleSections": profile["config"]["sections"],
        "fit": fit,
        "instructions": {
            "facts": "Use only source IDs and facts from CV.md.",
            "pageTarget": "Use preferred budgets for one page and expand toward maximum budgets for two pages.",
            "payload": "Write tailoring-payload.json using schemaVersion 3.",
        },
    }
    _write_json(output / "tailoring-brief.json", brief)
    _write_json(output / "effective-policy.json", effective_policy)
    _write_json(
        output / "decision-report.json",
        _decision_report(effective_policy, stage="prepared"),
    )
    install_runner(output)
    return {"ok": True, "outputDir": str(output), "brief": str(output / "tailoring-brief.json")}


def command_build(args: argparse.Namespace) -> dict[str, Any]:
    profile = load_profile(args.profile)
    payload = json.loads(args.payload.read_text(encoding="utf8"))
    if payload.get("schemaVersion") != 3:
        payload = from_legacy_payload(payload)
    policy = resolve_effective_policy(profile)
    tailored = assemble_profile_resume(
        payload, profile["cv"], policy, profile["sections"]
    )
    tailored.update(
        {
            "schemaVersion": 3,
            "sourceResumeConfigSha256": profile["hashes"]["resumeConfig"],
            "sourceThemeSha256": profile["hashes"]["theme"],
            "document": profile["config"]["document"],
        }
    )
    output = args.out.resolve()
    output.mkdir(parents=True, exist_ok=True)
    assembled_path = output / "tailored-resume.json"
    _write_json(assembled_path, tailored)
    _write_json(output / "tailoring-payload.json", payload)
    _write_json(output / "effective-policy.json", policy)
    report = generate(
        assembled_path,
        output,
        profile["cvPath"],
        policy=policy,
        theme=profile["theme"],
        resume_config=profile["config"],
    )
    _write_json(
        output / "decision-report.json",
        _decision_report(policy, stage="built", payload=payload, layout=report),
    )
    return {"ok": report["ok"], "outputDir": str(output), "layout": report}


def command_check(args: argparse.Namespace) -> dict[str, Any]:
    profile = load_profile(args.profile)
    policy = resolve_effective_policy(profile)
    result = analyze_output_dir(
        args.out.resolve(),
        max_pages=profile["config"]["document"]["maxPages"],
        cv_path=profile["cvPath"],
        reinspect_pdf=args.reinspect,
        policy=policy,
        theme=profile["theme"],
        resume_config=profile["config"],
    )
    result["effectivePolicy"] = {
        "targetPages": policy["targetPages"],
        "maxPages": policy["maxPages"],
        "enabledSections": policy["enabledSections"],
    }
    return result


def command_migrate(args: argparse.Namespace) -> dict[str, Any]:
    payload = json.loads(args.payload.read_text(encoding="utf8"))
    migrated = from_legacy_payload(payload)
    destination = args.out.resolve()
    if destination.exists() and json.loads(destination.read_text(encoding="utf8")) == migrated:
        return {"ok": True, "changed": False, "output": str(destination)}
    _write_json(destination, migrated)
    return {"ok": True, "changed": True, "output": str(destination)}


def command_doctor(args: argparse.Namespace) -> dict[str, Any]:
    profile_result = command_validate(args)
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "doctor.py"),
            "--profile",
            str(args.profile),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    try:
        runtime = json.loads(completed.stdout)
    except json.JSONDecodeError:
        runtime = {"ok": False, "error": completed.stderr or completed.stdout}
    return {
        "ok": bool(profile_result["ok"] and runtime.get("ok")),
        "profile": profile_result,
        "runtime": runtime,
    }


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(prog="jobs-tailor", description="Profile-driven resume tailoring and deterministic rendering.")
    result.add_argument("--json", action="store_true", help=argparse.SUPPRESS)
    commands = result.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init")
    init.add_argument("profile", type=Path)
    init.set_defaults(handler=command_init)
    for name, handler in (("validate", command_validate), ("doctor", command_doctor)):
        item = commands.add_parser(name)
        item.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
        item.set_defaults(handler=handler)
    prepare = commands.add_parser("prepare")
    prepare.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    prepare.add_argument("--job", type=Path, required=True)
    prepare.add_argument("--out", type=Path, required=True)
    prepare.set_defaults(handler=command_prepare)
    build = commands.add_parser("build")
    build.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    build.add_argument("--payload", type=Path, required=True)
    build.add_argument("--out", type=Path, required=True)
    build.set_defaults(handler=command_build)
    check = commands.add_parser("check")
    check.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    check.add_argument("--out", type=Path, required=True)
    check.add_argument("--reinspect", action="store_true")
    check.set_defaults(handler=command_check)
    migrate = commands.add_parser("migrate-v2")
    migrate.add_argument("--payload", type=Path, required=True)
    migrate.add_argument("--out", type=Path, required=True)
    migrate.set_defaults(handler=command_migrate)
    return result


def main() -> int:
    args = parser().parse_args()
    try:
        result = args.handler(args)
    except (OSError, ValueError, ProfileConfigError) as error:
        print(json.dumps({"ok": False, "error": str(error)}, separators=(",", ":")))
        return 1
    print(json.dumps(result, indent=None if args.json else 2, separators=(",", ":") if args.json else None))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
