#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

from cv_source import load_cv
from resume_validation import validate_tailored_resume
from runtime_paths import ROOT


POLICY_PATH = ROOT / "config" / "resume-policy.json"
DEFAULT_CV_PATH = ROOT / "profiles" / "john-doe" / "CV.md"
ALLOWED_PAYLOAD_FIELDS = {
    "jobTitle",
    "headline",
    "summary",
    "summarySourceIds",
    "experience",
    "projects",
    "technicalSkills",
    "skillPriorities",
}
COMPOSITE_TITLE_RE = re.compile(r"\s(?:and)\s|[&/]")
SUMMARY_ROLE_LEAD_RE = re.compile(
    r"^(?P<lead>[A-Za-z][A-Za-z/&+\- ]+?)(?=\s+(with|specializing|focused|experienced|bringing|skilled)\b)",
    re.IGNORECASE,
)


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object.")
    return value


def _require_list(payload: dict[str, Any], field: str) -> list[Any]:
    value = payload.get(field)
    if not isinstance(value, list):
        raise ValueError(f"tailoring-payload.json field {field!r} must be an array.")
    return value


def _require_string_list(payload: dict[str, Any], field: str) -> list[str]:
    value = _require_list(payload, field)
    if not value or not all(isinstance(item, str) for item in value):
        raise ValueError(
            f"tailoring-payload.json field {field!r} must be a non-empty string array."
        )
    return value


def _assemble_bullets(
    entry: dict[str, Any], source: dict[str, Any], section: str
) -> list[dict[str, str]]:
    bullets = entry.get("bullets")
    if not isinstance(bullets, list):
        raise ValueError(f"{section} entry {source['id']!r} requires a bullets array.")
    allowed_ids = {bullet["id"] for bullet in source["bullets"]}
    assembled: list[dict[str, str]] = []
    for bullet in bullets:
        if not isinstance(bullet, dict):
            raise ValueError(f"{section} bullets must be JSON objects.")
        unknown_fields = set(bullet) - {"sourceId", "text"}
        if unknown_fields:
            raise ValueError(
                f"{section} bullet contains unsupported fields: "
                + ", ".join(sorted(unknown_fields))
            )
        source_id = bullet.get("sourceId")
        text = bullet.get("text")
        if source_id not in allowed_ids:
            raise ValueError(
                f"{section} entry {source['id']!r} has unknown bullet sourceId: "
                f"{source_id!r}."
            )
        if not isinstance(text, str) or not text.strip():
            raise ValueError(f"{section} bullet {source_id!r} requires non-empty text.")
        assembled.append({"sourceId": source_id, "text": text.strip()})
    return assembled


def _entry_index(items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {item["id"]: item for item in items}


def normalize_job_title(value: str) -> str:
    title = re.sub(r"\s+", " ", value).strip()
    if not title:
        raise ValueError("tailoring-payload.json requires a non-empty jobTitle.")
    if COMPOSITE_TITLE_RE.search(title.casefold()):
        raise ValueError(
            "tailoring-payload.json jobTitle must contain exactly one prominent role title."
        )
    return title


def align_summary_with_headline(summary: str, headline: str, cv: dict[str, Any]) -> str:
    stripped = summary.strip()
    if not stripped:
        return stripped
    if stripped.casefold().startswith(headline.casefold()):
        return stripped
    prefixes = [cv["basics"]["headline"], *(entry["role"] for entry in cv["experience"])]
    for prefix in sorted({item.strip() for item in prefixes if item.strip()}, key=len, reverse=True):
        if stripped.casefold().startswith(prefix.casefold()):
            return headline + stripped[len(prefix):]
    match = SUMMARY_ROLE_LEAD_RE.match(stripped)
    if match and any(
        term in match.group("lead").casefold()
        for term in ("engineer", "tester", "developer", "analyst", "specialist")
    ):
        return headline + stripped[match.end("lead") :]
    return stripped


def _assemble_skill_group(
    source: dict[str, Any],
    priorities: list[str],
    slots: int,
    maximum_replacements: int,
) -> dict[str, Any]:
    if not priorities or not all(isinstance(item, str) for item in priorities):
        raise ValueError(
            f"Technical skill group {source['id']!r} requires a non-empty string array."
        )
    if len(set(priorities)) != len(priorities):
        raise ValueError(
            f"Technical skill group {source['id']!r} repeats a priority item."
        )
    unsupported = set(priorities) - set(source["items"])
    if unsupported:
        raise ValueError(
            f"Technical skill group {source['id']!r} contains unsupported items: "
            + ", ".join(sorted(unsupported))
        )

    baseline = list(source["items"][:slots])
    selected = list(baseline)
    replacements = 0
    for item in priorities:
        if item in selected:
            continue
        if replacements >= maximum_replacements:
            break
        replace_index = next(
            (
                index
                for index in range(len(selected) - 1, -1, -1)
                if selected[index] not in priorities
            ),
            None,
        )
        if replace_index is None:
            break
        selected[replace_index] = item
        replacements += 1

    ordered = [item for item in priorities if item in selected]
    ordered.extend(item for item in selected if item not in ordered)
    return {
        "sourceId": source["id"],
        "category": source["category"],
        "items": ordered,
    }


def assemble_tailored_resume(
    payload: dict[str, Any],
    cv: dict[str, Any],
    policy: dict[str, Any],
) -> dict[str, Any]:
    unknown_fields = set(payload) - ALLOWED_PAYLOAD_FIELDS
    if unknown_fields:
        raise ValueError(
            "tailoring-payload.json contains locked or unsupported fields: "
            + ", ".join(sorted(unknown_fields))
        )

    job_title = payload.get("jobTitle", payload.get("headline"))
    summary = payload.get("summary")
    if not isinstance(job_title, str):
        raise ValueError("tailoring-payload.json requires a non-empty jobTitle.")
    if not isinstance(summary, str) or not summary.strip():
        raise ValueError("tailoring-payload.json requires a non-empty summary.")

    experience_sources = _entry_index(cv["experience"])
    payload_experience: dict[str, dict[str, Any]] = {}
    for entry in _require_list(payload, "experience"):
        if not isinstance(entry, dict):
            raise ValueError("Experience entries must be JSON objects.")
        unknown_entry_fields = set(entry) - {"sourceId", "bullets"}
        if unknown_entry_fields:
            raise ValueError(
                "Experience entry contains locked or unsupported fields: "
                + ", ".join(sorted(unknown_entry_fields))
            )
        source = experience_sources.get(entry.get("sourceId"))
        if source is None:
            raise ValueError(
                f"Experience entry has unknown sourceId: {entry.get('sourceId')!r}."
            )
        payload_experience[source["id"]] = entry

    experience: list[dict[str, Any]] = []
    for source in cv["experience"]:
        entry = payload_experience.get(source["id"])
        if entry is None:
            raise ValueError(
                f"Experience entry has unknown sourceId: {source['id']!r}."
            )
        experience.append(
            {
                "sourceId": source["id"],
                "role": source["role"],
                "company": source["company"],
                "dates": source["dates"],
                "bullets": _assemble_bullets(entry, source, "Experience"),
            }
        )

    project_sources = _entry_index(cv["projects"])
    projects: list[dict[str, Any]] = []
    for entry in _require_list(payload, "projects"):
        if not isinstance(entry, dict):
            raise ValueError("Project entries must be JSON objects.")
        unknown_entry_fields = set(entry) - {"sourceId", "bullets"}
        if unknown_entry_fields:
            raise ValueError(
                "Project entry contains locked or unsupported fields: "
                + ", ".join(sorted(unknown_entry_fields))
            )
        source = project_sources.get(entry.get("sourceId"))
        if source is None:
            raise ValueError(f"Project entry has unknown sourceId: {entry.get('sourceId')!r}.")
        projects.append(
            {
                "sourceId": source["id"],
                "name": source["name"],
                "stack": source["stack"],
                "bullets": _assemble_bullets(entry, source, "Project"),
            }
        )

    skill_sources = _entry_index(cv["technicalSkills"])
    technical_skills: list[dict[str, Any]] = []
    uses_priorities = "skillPriorities" in payload
    if uses_priorities and "technicalSkills" in payload:
        raise ValueError(
            "tailoring-payload.json cannot contain both skillPriorities and technicalSkills."
        )
    skill_field = "skillPriorities" if uses_priorities else "technicalSkills"
    skill_groups = _require_list(payload, skill_field)
    slots = policy["technicalSkillSlotsPerCategory"]
    maximum_replacements = policy["maximumTechnicalSkillReplacementsPerCategory"]
    for group in skill_groups:
        if not isinstance(group, dict):
            raise ValueError("Technical skill groups must be JSON objects.")
        item_field = "priorityItems" if uses_priorities else "items"
        unknown_group_fields = set(group) - {"sourceId", item_field}
        if unknown_group_fields:
            raise ValueError(
                "Technical skill group contains locked or unsupported fields: "
                + ", ".join(sorted(unknown_group_fields))
            )
        source = skill_sources.get(group.get("sourceId"))
        if source is None:
            raise ValueError(
                f"Technical skill group has unknown sourceId: {group.get('sourceId')!r}."
            )
        items = group.get(item_field)
        if uses_priorities:
            technical_skills.append(
                _assemble_skill_group(
                    source,
                    items,
                    slots,
                    maximum_replacements,
                )
            )
        else:
            if not isinstance(items, list) or not items or not all(
                isinstance(item, str) for item in items
            ):
                raise ValueError(
                    f"Technical skill group {source['id']!r} requires a non-empty string array."
                )
            unsupported = set(items) - set(source["items"])
            if unsupported:
                raise ValueError(
                    f"Technical skill group {source['id']!r} contains unsupported items: "
                    + ", ".join(sorted(unsupported))
                )
            technical_skills.append(
                {
                    "sourceId": source["id"],
                    "category": source["category"],
                    "items": items,
                }
            )

    normalized_job_title = normalize_job_title(job_title)
    aligned_summary = align_summary_with_headline(summary.strip(), normalized_job_title, cv)

    tailored = {
        "schemaVersion": 2,
        "sourceCvSha256": cv["sourceCvSha256"],
        "summarySourceIds": _require_string_list(payload, "summarySourceIds"),
        "basics": {
            **cv["basics"],
            "headline": normalized_job_title,
        },
        "summary": aligned_summary,
        "experience": experience,
        "certifications": [
            {
                "sourceId": item["id"],
                "name": item["name"],
                "issuer": item["issuer"],
                "date": item["date"],
            }
            for item in cv["certifications"]
        ],
        "projects": projects,
        "achievements": [
            {
                "sourceId": item["id"],
                "text": item["text"],
                **({"url": item["url"]} if item.get("url") else {}),
            }
            for item in cv["achievements"]
        ],
        "education": {
            "sourceId": cv["education"]["id"],
            **{
                field: cv["education"][field]
                for field in ("institution", "location", "degree", "dates", "gpa")
            },
        },
        "technicalSkills": technical_skills,
    }
    issues = validate_tailored_resume(tailored, cv, policy)
    if issues:
        raise ValueError("Tailoring payload validation failed:\n" + "\n".join(issues))
    return tailored


def write_assembled_resume(
    payload_path: Path,
    output_path: Path,
    cv_path: Path = DEFAULT_CV_PATH,
) -> dict[str, Any]:
    payload = load_json(payload_path)
    cv = load_cv(cv_path)
    policy = load_json(POLICY_PATH)
    tailored = assemble_tailored_resume(payload, cv, policy)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf8",
        dir=output_path.parent,
        prefix=f".{output_path.name}.",
        delete=False,
    ) as temporary:
        temporary_path = Path(temporary.name)
        json.dump(tailored, temporary, indent=2)
        temporary.write("\n")
    os.replace(temporary_path, output_path)
    return tailored


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Expand a compact tailoring payload with canonical CV fields."
    )
    parser.add_argument("payload_json", type=Path)
    parser.add_argument("output_json", type=Path)
    parser.add_argument("--cv", type=Path, default=DEFAULT_CV_PATH)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    write_assembled_resume(
        args.payload_json.resolve(),
        args.output_json.resolve(),
        args.cv.resolve(),
    )
    print(f"Assembled {args.output_json}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
