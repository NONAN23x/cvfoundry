#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from artifact_names import final_pdf_filename
from check_resume_quality import analyze_output_dir
from generate_fit_summary import build_summary, render_markdown
from install_output_runner import install_runner
from payload_v3 import from_legacy_payload
from profile_assembly import assemble_profile_resume
from profile_config import (
    DEFAULT_PROFILE,
    ProfileConfigError,
    RESUME_CONFIG_FILENAME,
    load_profile,
    normalize_resume_toml,
    resolve_effective_policy,
    validate_resume_config,
)


ROOT = Path(__file__).resolve().parents[1]
PIPELINE_LOCK_ENV = "JOBS_TAILORING_PIPELINE_LOCK"


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf8")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _relative(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path)


def _git_ignored(path: Path) -> bool:
    completed = subprocess.run(
        ["git", "check-ignore", "-q", str(path)],
        cwd=ROOT,
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return completed.returncode == 0


def _locked_policy_sections(policy: dict[str, Any]) -> list[dict[str, Any]]:
    locked_ids = {"education"}
    return [
        {
            "sourceId": section["sourceId"],
            "mode": section["selectionMode"],
            "resolvedEntryCount": section["effectiveEntryCount"],
            "reason": "deterministic CV-order expansion",
        }
        for section in policy["sections"]
        if section["selectionMode"] == "ordered" or section["sourceId"] in locked_ids
    ]


def _same_path(left: Path, right: Path) -> bool:
    try:
        return left.samefile(right)
    except FileNotFoundError:
        return left.resolve() == right.resolve()


def _container_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return "/workspace/" + str(resolved.relative_to(ROOT))
    except ValueError as error:
        raise ValueError(f"Docker renderer paths must live under {ROOT}: {path}") from error


def _can_render_locally() -> bool:
    return bool(shutil.which("libreoffice") or shutil.which("soffice")) and importlib.util.find_spec("uno") is not None


def _run_docker_build(args: argparse.Namespace) -> dict[str, Any]:
    image = os.environ.get("CVFOUNDRY_DOCKER_IMAGE", "cvfoundry:latest")
    command = [
        "docker",
        "run",
        "--rm",
        "-u",
        f"{os.getuid()}:{os.getgid()}",
        "-v",
        f"{ROOT}:/workspace",
        "-w",
        "/workspace",
        image,
        "build",
        "--renderer",
        "local",
        "--profile",
        _container_path(args.profile),
        "--payload",
        _container_path(args.payload),
        "--out",
        _container_path(args.out),
    ]
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        raise ValueError((completed.stderr or completed.stdout).strip())
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise ValueError(completed.stdout.strip()) from error


def _toml_string(value: str) -> str:
    return json.dumps(value)


def _inline_array(values: list[str]) -> str:
    return "[" + ", ".join(_toml_string(item) for item in values) + "]"


def _inline_budget(budget: dict[str, int]) -> str:
    return (
        "{ "
        f"one_page = {budget['preferred']}, "
        f"two_page = {budget['max']}, "
        f"minimum = {budget['min']} "
        "}"
    )


def legacy_json_config_to_toml(config: dict[str, Any]) -> str:
    normalized = validate_resume_config(config, Path("resume.json"))
    lines = [
        "version = 4",
        f"theme = {_toml_string(normalized['theme'])}",
        "",
        "[document]",
        f"paper = {_toml_string(normalized['document']['pageSize'])}",
        f"target_pages = {normalized['document']['targetPages']}",
        f"max_pages = {normalized['document']['maxPages']}",
        "",
        "[header]",
        f"contact = {_inline_array(normalized.get('header', {}).get('contactFields', []))}",
        "",
        "[quality]",
    ]
    layout = normalized.get("layout", {})
    quality_fields = [
        ("contact_lines", "requiredContactLines"),
        ("bottom_whitespace_min_mm", "minimumBottomWhitespaceMm"),
        ("bottom_whitespace_max_mm", "maximumBottomWhitespaceMm"),
        ("intermediate_page_whitespace_max_mm", "maximumIntermediatePageWhitespaceMm"),
    ]
    for toml_name, json_name in quality_fields:
        if json_name in layout:
            lines.append(f"{toml_name} = {layout[json_name]}")
    for section in normalized["sections"]:
        selection = section.get("selection", {})
        lines.extend(
            [
                "",
                "[[sections]]",
                f"id = {_toml_string(section['sourceId'])}",
                f"kind = {_toml_string(section['type'])}",
                f"priority = {section.get('priority', 0)}",
                f"mode = {_toml_string(selection.get('mode', 'all'))}",
                f"rewrite = {_toml_string(section.get('rewrite', 'none'))}",
            ]
        )
        if section["type"] == "summary" and "maximumSummaryLines" in layout:
            lines.append(f"lines = {layout['maximumSummaryLines']}")
        if "entries" in selection:
            lines.append(f"entries = {_inline_budget(selection['entries'])}")
        if "bulletsPerEntry" in selection:
            lines.append(f"bullets = {_inline_budget(selection['bulletsPerEntry'])}")
            if "maximumBulletLines" in layout:
                lines.append(f"bullet_lines = {layout['maximumBulletLines']}")
        if "itemsPerEntry" in selection:
            lines.append(f"items_per_category = {_inline_budget(selection['itemsPerEntry'])}")
            if "maximumReplacementsPerCategory" in selection:
                lines.append(
                    f"replacement_limit = {selection['maximumReplacementsPerCategory']}"
                )
            if "maximumSkillRowLines" in layout:
                lines.append(f"skill_row_lines = {layout['maximumSkillRowLines']}")
        if selection.get("requiredSourceIds"):
            lines.append(f"required = {_inline_array(selection['requiredSourceIds'])}")
        if selection.get("excludedSourceIds"):
            lines.append(f"excluded = {_inline_array(selection['excludedSourceIds'])}")
    return "\n".join(lines) + "\n"


class OutputLock:
    def __init__(self, output_dir: Path) -> None:
        self.path = output_dir / ".generate.lock"
        self.fd: int | None = None

    def __enter__(self) -> "OutputLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError as error:
            raise RuntimeError(
                f"Another resume generation appears active in {self.path.parent}. "
                f"Delete {self.path.name} only if no run is active."
            ) from error
        os.write(self.fd, f"pid={os.getpid()} started={time.time()}\n".encode("utf8"))
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        if self.fd is not None:
            os.close(self.fd)
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass


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


def _payload_skeleton(
    profile: dict[str, Any],
    policy: dict[str, Any],
    fit: dict[str, Any],
    locked_ids: set[str],
) -> dict[str, Any]:
    rankings = {
        "experience": fit.get("experienceRanking", []),
        "projects": fit.get("projectRanking", []),
        **fit.get("sectionRankings", {}),
    }

    def ordered_ids(section: dict[str, Any]) -> list[str]:
        ranked_ids = [item["id"] for item in rankings.get(section["sourceId"], [])]
        available = section["availableSourceIds"]
        if section["selectionMode"] == "ranked" and ranked_ids:
            selected = [item_id for item_id in ranked_ids if item_id in available]
            selected.extend(item_id for item_id in available if item_id not in selected)
            return selected[: section["effectiveEntryCount"]]
        return available[: section["effectiveEntryCount"]]

    sections: list[dict[str, Any]] = []
    for section in policy["sections"]:
        source_id = section["sourceId"]
        if source_id in locked_ids or source_id == "summary":
            continue
        canonical = {item["id"]: item for item in profile["sections"][source_id].get("items", [])}
        items: list[dict[str, Any]] = []
        for item_id in ordered_ids(section):
            source = canonical[item_id]
            item: dict[str, Any] = {"sourceId": item_id}
            if source.get("bullets") is not None:
                item["bullets"] = [
                    {"sourceId": bullet["id"], "sourceText": bullet["text"], "text": ""}
                    for bullet in source["bullets"][: section["effectiveBulletCounts"].get(item_id, 0)]
                ]
            elif source_id == "technical-skills":
                item["priorityItems"] = []
                item["availableItems"] = source.get("items", [])
            else:
                item["sourceText"] = " ".join(
                    str(value) if not isinstance(value, list) else " ".join(value)
                    for key, value in source.items()
                    if key != "id"
                )
            items.append(item)
        sections.append({"sourceId": source_id, "items": items})
    return {
        "schemaVersion": 3,
        "jobTitle": "",
        "summary": {"text": "", "sourceIds": [profile["cv"]["summarySourceId"]]},
        "sections": sections,
    }


def command_init(args: argparse.Namespace) -> dict[str, Any]:
    destination = args.profile.resolve()
    if destination.exists() and any(destination.iterdir()):
        raise ValueError(f"Profile directory is not empty: {destination}")
    destination.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / "templates" / "profile" / "CV.md", destination / "CV.md")
    shutil.copy2(ROOT / "templates" / "profile" / "Writing-Style.md", destination / "Writing-Style.md")
    shutil.copy2(ROOT / "templates" / "profile" / RESUME_CONFIG_FILENAME, destination / RESUME_CONFIG_FILENAME)
    return {"ok": True, "profile": str(destination)}


def command_first_run(args: argparse.Namespace) -> dict[str, Any]:
    profile_dir = args.profile.resolve()
    issues: list[str] = []
    required = [profile_dir / "CV.md", profile_dir / "Writing-Style.md", profile_dir / RESUME_CONFIG_FILENAME]
    missing = [_relative(path) for path in required if not path.is_file()]
    if missing:
        issues.append(
            "Missing profile files: "
            + ", ".join(missing)
            + f". Run 'uv run jobs-tailor init {profile_dir}' first."
        )

    profile: dict[str, Any] | None = None
    policy: dict[str, Any] | None = None
    if not missing:
        try:
            profile = load_profile(profile_dir)
            policy = resolve_effective_policy(profile)
        except (OSError, ValueError, ProfileConfigError) as error:
            issues.append(str(error))

    template_cv = ROOT / "templates" / "profile" / "CV.md"
    cv_path = profile_dir / "CV.md"
    if cv_path.is_file() and template_cv.is_file() and _sha256(cv_path) == _sha256(template_cv):
        issues.append("CV.md still matches the scaffold. Replace it with your own CV before tailoring.")

    private_roots = {"local", "private"}
    if profile_dir.parent == ROOT / "profiles" and profile_dir.name in private_roots:
        exposed = [_relative(path) for path in required if path.exists() and not _git_ignored(path)]
        if exposed:
            issues.append("Private profile files are not ignored by Git: " + ", ".join(exposed))

    renderer = {
        "libreOffice": bool(shutil.which("libreoffice") or shutil.which("soffice")),
        "pythonUno": importlib.util.find_spec("uno") is not None,
        "docker": bool(shutil.which("docker")),
    }
    ready = not issues
    return {
        "ok": ready,
        "ready": ready,
        "profile": str(profile_dir),
        "candidate": profile["cv"]["basics"]["name"] if profile else None,
        "issues": issues,
        "rules": (
            {
                "targetPages": policy["targetPages"],
                "maxPages": policy["maxPages"],
                "enabledSections": policy["enabledSections"],
                "lockedSections": _locked_policy_sections(policy),
            }
            if policy
            else None
        ),
        "renderer": renderer,
        "next": (
            "Paste/save a job description, then run: "
            "uv run jobs-tailor prepare --job <job-description.md> --out output/<company-role-date>"
            if ready
            else "Fix the issues above, then rerun: uv run jobs-tailor first-run"
        ),
    }


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


def command_explain_rules(args: argparse.Namespace) -> dict[str, Any]:
    profile = load_profile(args.profile)
    policy = resolve_effective_policy(profile)
    return {
        "ok": True,
        "profile": str(profile["root"]),
        "rulesFile": str(profile["resumePath"]),
        "targetPages": policy["targetPages"],
        "maxPages": policy["maxPages"],
        "pageSize": policy["pageSize"],
        "enabledSections": policy["enabledSections"],
        "sections": policy["sections"],
    }


def command_prepare(args: argparse.Namespace) -> dict[str, Any]:
    profile = load_profile(args.profile)
    effective_policy = resolve_effective_policy(profile)
    job_text = args.job.read_text(encoding="utf8")
    output = args.out.resolve()
    output.mkdir(parents=True, exist_ok=True)
    job_copy = output / "job-description.md"
    if not _same_path(args.job, job_copy):
        shutil.copy2(args.job, job_copy)
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
    locked_sections = _locked_policy_sections(effective_policy)
    locked_ids = {section["sourceId"] for section in locked_sections}
    brief = {
        "schemaVersion": 3,
        "profileHashes": profile["hashes"],
        "document": profile["config"]["document"],
        "effectivePolicy": effective_policy,
        "eligibleSections": profile["config"]["sections"],
        "tailorableSections": [
            section for section in profile["config"]["sections"]
            if section["sourceId"] not in locked_ids
        ],
        "lockedSections": locked_sections,
        "fit": fit,
        "instructions": {
            "facts": "Use only source IDs and facts from CV.md.",
            "pageTarget": "Use preferred budgets for one page and expand toward maximum budgets for two pages.",
            "payload": "Write schemaVersion 3 tailoring-payload.json with only tailorable sections; omit lockedSections.",
        },
    }
    _write_json(output / "tailoring-brief.json", brief)
    _write_json(output / "payload-skeleton.json", _payload_skeleton(profile, effective_policy, fit, locked_ids))
    _write_json(output / "effective-policy.json", effective_policy)
    _write_json(
        output / "decision-report.json",
        _decision_report(effective_policy, stage="prepared"),
    )
    install_runner(output)
    return {"ok": True, "outputDir": str(output), "brief": str(output / "tailoring-brief.json")}


def command_build(args: argparse.Namespace) -> dict[str, Any]:
    from generate_resume import generate

    renderer = getattr(args, "renderer", "auto")
    if renderer == "docker" or (renderer == "auto" and not _can_render_locally()):
        if renderer == "auto" and not shutil.which("docker"):
            raise ValueError("Local LibreOffice/UNO is unavailable and Docker is missing.")
        return _run_docker_build(args)

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
    notes_path = output / "tailoring-notes.md"
    if not notes_path.exists():
        notes_path.write_text(
            "# Tailoring Notes\n\nGenerated by `jobs-tailor build`; no manual notes were supplied.\n",
            encoding="utf8",
        )
    with OutputLock(output):
        previous_lock = os.environ.get(PIPELINE_LOCK_ENV)
        os.environ[PIPELINE_LOCK_ENV] = "1"
        try:
            report = generate(
                assembled_path,
                output,
                profile["cvPath"],
                policy=policy,
                theme=profile["theme"],
                resume_config=profile["config"],
            )
        finally:
            if previous_lock is None:
                os.environ.pop(PIPELINE_LOCK_ENV, None)
            else:
                os.environ[PIPELINE_LOCK_ENV] = previous_lock
    _write_json(
        output / "decision-report.json",
        _decision_report(policy, stage="built", payload=payload, layout=report),
    )
    return {"ok": report["ok"], "outputDir": str(output), "layout": report}


def command_rerun(args: argparse.Namespace) -> dict[str, Any]:
    output = args.out.resolve()
    payload = output / "tailoring-payload.json"
    if not payload.is_file():
        raise ValueError(f"Missing tailoring-payload.json in {output}.")
    build_args = argparse.Namespace(profile=args.profile, payload=payload, out=output, renderer=getattr(args, "renderer", "auto"))
    result = command_build(build_args)
    if result.get("ok"):
        data = json.loads((output / "tailored-resume.json").read_text(encoding="utf8"))
        result["pdf"] = str(output / final_pdf_filename(data))
    return result


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


def command_migrate_payload(args: argparse.Namespace) -> dict[str, Any]:
    payload = json.loads(args.payload.read_text(encoding="utf8"))
    migrated = from_legacy_payload(payload)
    destination = args.out.resolve()
    if destination.exists() and json.loads(destination.read_text(encoding="utf8")) == migrated:
        return {"ok": True, "changed": False, "output": str(destination)}
    _write_json(destination, migrated)
    return {"ok": True, "changed": True, "output": str(destination)}


def command_migrate_config(args: argparse.Namespace) -> dict[str, Any]:
    profile_dir = args.profile.resolve()
    source = profile_dir / "resume.json"
    destination = profile_dir / RESUME_CONFIG_FILENAME
    if not source.is_file():
        raise ValueError(f"Missing legacy config: {source}")
    config = json.loads(source.read_text(encoding="utf8"))
    toml_text = legacy_json_config_to_toml(config)
    changed = not destination.exists() or destination.read_text(encoding="utf8") != toml_text
    if changed:
        destination.write_text(toml_text, encoding="utf8")
    loaded = normalize_resume_toml(__import__("tomllib").loads(toml_text), destination)
    return {
        "ok": True,
        "changed": changed,
        "input": str(source),
        "output": str(destination),
        "sections": [section["sourceId"] for section in loaded["sections"]],
    }


def command_inspect_run(args: argparse.Namespace) -> dict[str, Any]:
    output = args.out.resolve()
    files = {}
    for name in (
        "tailoring-brief.json",
        "tailoring-payload.json",
        "tailored-resume.json",
        "effective-policy.json",
        "decision-report.json",
        "layout-validation.json",
        "tailored-resume.html",
        "tailored-resume.odt",
    ):
        path = output / name
        files[name] = {"exists": path.exists(), "size": path.stat().st_size if path.exists() else 0}
    policy = None
    if (output / "effective-policy.json").is_file():
        policy = json.loads((output / "effective-policy.json").read_text(encoding="utf8"))
    layout = None
    if (output / "layout-validation.json").is_file():
        layout = json.loads((output / "layout-validation.json").read_text(encoding="utf8"))
    return {
        "ok": True,
        "outputDir": str(output),
        "files": files,
        "effectivePolicy": {
            "targetPages": policy.get("targetPages"),
            "maxPages": policy.get("maxPages"),
            "enabledSections": policy.get("enabledSections"),
        }
        if policy
        else None,
        "layout": {
            "ok": layout.get("ok"),
            "pageCount": layout.get("pageCount"),
            "targetStatus": layout.get("targetStatus"),
            "issues": layout.get("issues", []),
        }
        if layout
        else None,
    }


def command_status(args: argparse.Namespace) -> dict[str, Any]:
    output = args.out.resolve() if args.out else None
    try:
        profile = load_profile(args.profile)
        profile_result = {
            "ok": True,
            "profile": str(profile["root"]),
            "candidate": profile["cv"]["basics"]["name"],
            "rulesFile": str(profile["resumePath"]),
            "hashes": profile["hashes"],
            "effectivePolicy": resolve_effective_policy(profile),
        }
    except (OSError, ValueError, ProfileConfigError) as error:
        profile_result = {"ok": False, "error": str(error)}
    run_result = command_inspect_run(argparse.Namespace(out=output)) if output else None
    next_command = "uv run jobs-tailor validate"
    if profile_result["ok"] and output:
        files = run_result["files"]
        if not files["tailoring-brief.json"]["exists"]:
            next_command = "uv run jobs-tailor prepare --job <job-description.md> --out " + str(output)
        elif not files["tailoring-payload.json"]["exists"]:
            next_command = "Create tailoring-payload.json from tailoring-brief.json"
        elif not files["layout-validation.json"]["exists"]:
            next_command = "uv run jobs-tailor build --payload " + str(output / "tailoring-payload.json") + " --out " + str(output)
        else:
            next_command = "uv run jobs-tailor check --out " + str(output) + " --reinspect"
    return {"ok": bool(profile_result["ok"]), "profile": profile_result, "run": run_result, "next": next_command}


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
        "renderer": args.renderer,
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
    first_run = commands.add_parser("first-run")
    first_run.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    first_run.set_defaults(handler=command_first_run)
    for name, handler in (("validate", command_validate), ("doctor", command_doctor), ("explain-rules", command_explain_rules)):
        item = commands.add_parser(name)
        item.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
        if name == "doctor":
            item.add_argument("--renderer", choices=("auto", "local", "docker"), default="auto")
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
    build.add_argument("--renderer", choices=("auto", "local", "docker"), default="auto")
    build.set_defaults(handler=command_build)
    rerun = commands.add_parser("rerun")
    rerun.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    rerun.add_argument("--out", type=Path, required=True)
    rerun.add_argument("--renderer", choices=("auto", "local", "docker"), default="auto")
    rerun.set_defaults(handler=command_rerun)
    check = commands.add_parser("check")
    check.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    check.add_argument("--out", type=Path, required=True)
    check.add_argument("--reinspect", action="store_true")
    check.set_defaults(handler=command_check)
    migrate = commands.add_parser("migrate-v2")
    migrate.add_argument("--payload", type=Path, required=True)
    migrate.add_argument("--out", type=Path, required=True)
    migrate.set_defaults(handler=command_migrate_payload)
    migrate_config = commands.add_parser("migrate-config")
    migrate_config.add_argument("--profile", type=Path, required=True)
    migrate_config.set_defaults(handler=command_migrate_config)
    inspect_run = commands.add_parser("inspect-run")
    inspect_run.add_argument("--out", type=Path, required=True)
    inspect_run.set_defaults(handler=command_inspect_run)
    status = commands.add_parser("status")
    status.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    status.add_argument("--out", type=Path)
    status.set_defaults(handler=command_status)
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
