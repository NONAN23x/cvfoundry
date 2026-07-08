#!/usr/bin/env python3

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


META_RE = re.compile(r"^\s*<!--\s*cv:\s*(\{.*\})\s*-->\s*$")
SECTION_RE = re.compile(r"^## (.+?)\s*$")
ENTRY_RE = re.compile(r"^### (.+?)\s*$")
EXPECTED_SECTIONS = [
    "Header",
    "Summary",
    "Experience",
    "Certifications",
    "Projects",
    "Achievements",
    "Education",
    "Technical Skills",
]
OPTIONAL_SECTIONS = {"Open Source", "Publications"}


class CVParseError(ValueError):
    def __init__(self, path: Path, issues: list[str]) -> None:
        self.path = path
        self.issues = issues
        super().__init__("\n".join(f"{path}:{issue}" for issue in issues))


def _line_issue(line_number: int, message: str) -> str:
    return f"{line_number}: {message}"


def _split_sections(lines: list[str], issues: list[str]) -> dict[str, tuple[int, int]]:
    headings: list[tuple[str, int]] = []
    for index, line in enumerate(lines, start=1):
        match = SECTION_RE.match(line)
        if match:
            headings.append((match.group(1), index))
    names = [name for name, _ in headings]
    required_names = [name for name in names if name not in OPTIONAL_SECTIONS]
    optional_positions_valid = all(
        names.index(name) > names.index("Projects") and names.index(name) < names.index("Achievements")
        for name in OPTIONAL_SECTIONS
        if name in names and "Projects" in names and "Achievements" in names
    )
    if required_names != EXPECTED_SECTIONS or not optional_positions_valid:
        issues.append(
            _line_issue(
                1,
                "expected sections in order "
                + ", ".join(EXPECTED_SECTIONS)
                + "; found "
                + ", ".join(names),
            )
        )
    sections: dict[str, tuple[int, int]] = {}
    for position, (name, start) in enumerate(headings):
        end = headings[position + 1][1] - 1 if position + 1 < len(headings) else len(lines)
        sections[name] = (start + 1, end)
    return sections


def _metadata(line: str, line_number: int, issues: list[str]) -> dict[str, Any] | None:
    match = META_RE.match(line)
    if not match:
        return None
    try:
        value = json.loads(match.group(1))
    except json.JSONDecodeError as error:
        issues.append(_line_issue(line_number, f"invalid cv metadata JSON: {error.msg}"))
        return {}
    if not isinstance(value, dict):
        issues.append(_line_issue(line_number, "cv metadata must be a JSON object"))
        return {}
    return value


def _require_id(
    metadata: dict[str, Any] | None,
    line_number: int,
    seen_ids: dict[str, int],
    issues: list[str],
) -> str:
    if metadata is None:
        issues.append(_line_issue(line_number, "missing preceding <!-- cv: {...} --> metadata"))
        return ""
    source_id = metadata.get("id")
    if not isinstance(source_id, str) or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", source_id):
        issues.append(_line_issue(line_number, "metadata id must be lowercase kebab-case"))
        return ""
    if source_id in seen_ids:
        issues.append(
            _line_issue(
                line_number,
                f"duplicate id {source_id!r}; first declared on line {seen_ids[source_id]}",
            )
        )
    else:
        seen_ids[source_id] = line_number
    return source_id


def _field_map(
    lines: list[str],
    start: int,
    end: int,
    required: list[str],
    allowed: list[str] | None,
    issues: list[str],
) -> dict[str, str]:
    values: dict[str, str] = {}
    for line_number in range(start, end + 1):
        line = lines[line_number - 1].strip()
        if not line or line.startswith("<!--"):
            continue
        if ":" not in line:
            issues.append(_line_issue(line_number, "expected 'Field: value'"))
            continue
        key, value = line.split(":", 1)
        if key in values:
            issues.append(_line_issue(line_number, f"duplicate field {key!r}"))
        values[key] = value.strip()
    for key in required:
        if not values.get(key):
            issues.append(_line_issue(start, f"missing required field {key!r}"))
    permitted = set(allowed if allowed is not None else required)
    unknown = sorted(set(values) - permitted)
    for key in unknown:
        issues.append(_line_issue(start, f"unsupported field {key!r}"))
    return values


def _preceding_metadata(
    lines: list[str], line_number: int, issues: list[str]
) -> tuple[dict[str, Any] | None, int]:
    cursor = line_number - 1
    while cursor > 0 and not lines[cursor - 1].strip():
        cursor -= 1
    if cursor <= 0:
        return None, line_number
    return _metadata(lines[cursor - 1], cursor, issues), cursor


def _split_list(value: str) -> list[str]:
    items: list[str] = []
    current: list[str] = []
    depth = 0
    for character in value:
        if character == "(":
            depth += 1
        elif character == ")" and depth:
            depth -= 1
        if character == "," and depth == 0:
            item = "".join(current).strip()
            if item:
                items.append(item)
            current = []
        else:
            current.append(character)
    item = "".join(current).strip()
    if item:
        items.append(item)
    return items


def _parse_bullets(
    lines: list[str],
    start: int,
    end: int,
    seen_ids: dict[str, int],
    issues: list[str],
) -> list[dict[str, str]]:
    bullets: list[dict[str, str]] = []
    pending_meta: tuple[dict[str, Any], int] | None = None
    for line_number in range(start, end + 1):
        raw = lines[line_number - 1]
        meta = _metadata(raw, line_number, issues)
        if meta is not None:
            pending_meta = (meta, line_number)
            continue
        stripped = raw.strip()
        if not stripped or stripped == "Highlights:":
            continue
        if not stripped.startswith("- "):
            issues.append(_line_issue(line_number, "expected a metadata-tagged bullet"))
            continue
        metadata, meta_line = pending_meta or (None, line_number)
        source_id = _require_id(metadata, meta_line, seen_ids, issues)
        bullet = {"id": source_id, "text": stripped[2:].strip()}
        url = metadata.get("url") if metadata else None
        if url is not None:
            if not isinstance(url, str):
                issues.append(_line_issue(meta_line, "bullet url must be a string"))
            else:
                parsed = urlparse(url)
                if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                    issues.append(
                        _line_issue(
                            meta_line,
                            "bullet url must be an absolute HTTP(S) URL",
                        )
                    )
                else:
                    bullet["url"] = url
        bullets.append(bullet)
        pending_meta = None
    if pending_meta is not None:
        issues.append(_line_issue(pending_meta[1], "metadata is not followed by a bullet"))
    return bullets


def _parse_experience_or_projects(
    section: str,
    lines: list[str],
    start: int,
    end: int,
    seen_ids: dict[str, int],
    issues: list[str],
) -> list[dict[str, Any]]:
    headings: list[tuple[int, str, dict[str, Any] | None, int]] = []
    for line_number in range(start, end + 1):
        match = ENTRY_RE.match(lines[line_number - 1])
        if not match:
            continue
        metadata, meta_line = _preceding_metadata(lines, line_number, issues)
        headings.append((line_number, match.group(1), metadata, meta_line))
    entries: list[dict[str, Any]] = []
    for position, (line_number, title, metadata, meta_line) in enumerate(headings):
        entry_end = headings[position + 1][3] - 1 if position + 1 < len(headings) else end
        source_id = _require_id(metadata, meta_line, seen_ids, issues)
        if section == "Experience":
            if " | " not in title:
                issues.append(_line_issue(line_number, "experience heading must be 'Role | Company'"))
                role, company = title, ""
            else:
                role, company = title.split(" | ", 1)
            date_lines = [
                candidate
                for candidate in range(line_number + 1, entry_end + 1)
                if lines[candidate - 1].startswith("Dates:")
            ]
            if len(date_lines) != 1:
                issues.append(_line_issue(line_number, "experience requires exactly one Dates field"))
            dates = (
                lines[date_lines[0] - 1].split(":", 1)[1].strip()
                if len(date_lines) == 1
                else ""
            )
            highlight_line = next(
                (
                    candidate
                    for candidate in range(line_number + 1, entry_end + 1)
                    if lines[candidate - 1].strip() == "Highlights:"
                ),
                line_number,
            )
            if highlight_line == line_number:
                issues.append(_line_issue(line_number, "missing Highlights marker"))
            for candidate in range(line_number + 1, highlight_line):
                value = lines[candidate - 1].strip()
                if value and not value.startswith("Dates:"):
                    issues.append(_line_issue(candidate, "unsupported experience field"))
            bullets = _parse_bullets(
                lines, highlight_line + 1, entry_end, seen_ids, issues
            )
            entries.append(
                {
                    "id": source_id,
                    "role": role.strip(),
                    "company": company.strip(),
                    "dates": dates,
                    "bullets": bullets,
                }
            )
        else:
            tags = metadata.get("tags", []) if metadata else []
            url = metadata.get("url") if metadata else None
            if not isinstance(tags, list) or not all(isinstance(tag, str) for tag in tags):
                issues.append(_line_issue(meta_line, "project tags must be an array of strings"))
                tags = []
            if url:
                parsed = urlparse(url)
                if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                    issues.append(_line_issue(meta_line, "project url must be an absolute HTTP(S) URL"))
            stack_line = next(
                (
                    candidate
                    for candidate in range(line_number + 1, entry_end + 1)
                    if lines[candidate - 1].startswith("Stack:")
                ),
                0,
            )
            highlight_line = next(
                (
                    candidate
                    for candidate in range(line_number + 1, entry_end + 1)
                    if lines[candidate - 1].strip() == "Highlights:"
                ),
                0,
            )
            if not stack_line:
                issues.append(_line_issue(line_number, "missing Stack field"))
            if not highlight_line:
                issues.append(_line_issue(line_number, "missing Highlights marker"))
            for candidate in range(line_number + 1, highlight_line or line_number):
                value = lines[candidate - 1].strip()
                if value and not value.startswith("Stack:"):
                    issues.append(_line_issue(candidate, "unsupported project field"))
            bullets = _parse_bullets(
                lines, (highlight_line or line_number) + 1, entry_end, seen_ids, issues
            )
            entry: dict[str, Any] = {
                "id": source_id,
                "name": title.strip(),
                "stack": lines[stack_line - 1].split(":", 1)[1].strip() if stack_line else "",
                "tags": tags,
                "bullets": bullets,
            }
            if url:
                entry["url"] = url
            entries.append(entry)
    return entries


def parse_cv_text(text: str, path: Path = Path("CV.md")) -> dict[str, Any]:
    lines = text.splitlines()
    issues: list[str] = []
    sections = _split_sections(lines, issues)
    seen_ids: dict[str, int] = {}
    if not lines or lines[0].strip() != "# CV":
        issues.append(_line_issue(1, "document must start with '# CV'"))

    def bounds(name: str) -> tuple[int, int]:
        return sections.get(name, (1, 0))

    start, end = bounds("Header")
    header = _field_map(
        lines,
        start,
        end,
        ["Name", "Email"],
        ["Name", "Headline", "Phone", "Email", "LinkedIn", "GitHub", "Website"],
        issues,
    )
    basics = {
        "name": header.get("Name", ""),
        "headline": header.get("Headline", ""),
        "phone": header.get("Phone", ""),
        "email": header.get("Email", ""),
        "linkedin": header.get("LinkedIn", ""),
        "github": header.get("GitHub", ""),
        "website": header.get("Website", ""),
    }
    if basics["email"] and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", basics["email"]):
        issues.append(_line_issue(start, "Email is invalid"))
    for field in ("linkedin", "github", "website"):
        value = basics[field]
        parsed = urlparse(value if "://" in value else f"https://{value}")
        if value and not parsed.netloc:
            issues.append(_line_issue(start, f"{field} is invalid"))

    start, end = bounds("Summary")
    summary_lines: list[str] = []
    summary_meta: dict[str, Any] | None = None
    summary_meta_line = start
    for line_number in range(start, end + 1):
        meta = _metadata(lines[line_number - 1], line_number, issues)
        if meta is not None:
            summary_meta, summary_meta_line = meta, line_number
        elif lines[line_number - 1].strip():
            summary_lines.append(lines[line_number - 1].strip())
    summary_id = _require_id(summary_meta, summary_meta_line, seen_ids, issues)
    summary = " ".join(summary_lines)
    if not summary:
        issues.append(_line_issue(start, "summary text is required"))

    start, end = bounds("Experience")
    experience = _parse_experience_or_projects(
        "Experience", lines, start, end, seen_ids, issues
    )

    start, end = bounds("Certifications")
    certifications: list[dict[str, str]] = []
    pending_meta: tuple[dict[str, Any], int] | None = None
    for line_number in range(start, end + 1):
        meta = _metadata(lines[line_number - 1], line_number, issues)
        if meta is not None:
            pending_meta = (meta, line_number)
            continue
        line = lines[line_number - 1].strip()
        if not line:
            continue
        if not line.startswith("- ") or len(line[2:].split(" | ")) != 3:
            issues.append(_line_issue(line_number, "certification must be '- Name | Issuer | Date'"))
            continue
        metadata, meta_line = pending_meta or (None, line_number)
        source_id = _require_id(metadata, meta_line, seen_ids, issues)
        name, issuer, date = (part.strip() for part in line[2:].split(" | "))
        certifications.append(
            {"id": source_id, "name": name, "issuer": issuer, "date": date}
        )
        pending_meta = None
    if pending_meta is not None:
        issues.append(_line_issue(pending_meta[1], "metadata is not followed by a certification"))

    start, end = bounds("Projects")
    projects = _parse_experience_or_projects(
        "Projects", lines, start, end, seen_ids, issues
    )

    start, end = bounds("Achievements")
    achievements = _parse_bullets(lines, start, end, seen_ids, issues)

    start, end = bounds("Education")
    education_meta: dict[str, Any] | None = None
    education_meta_line = start
    for line_number in range(start, end + 1):
        meta = _metadata(lines[line_number - 1], line_number, issues)
        if meta is not None:
            education_meta, education_meta_line = meta, line_number
    education_fields = _field_map(
        lines,
        start,
        end,
        ["Institution", "Location", "Degree", "Dates", "GPA"],
        None,
        issues,
    )
    education = {
        "id": _require_id(education_meta, education_meta_line, seen_ids, issues),
        "institution": education_fields.get("Institution", ""),
        "location": education_fields.get("Location", ""),
        "degree": education_fields.get("Degree", ""),
        "dates": education_fields.get("Dates", ""),
        "gpa": education_fields.get("GPA", ""),
    }

    start, end = bounds("Technical Skills")
    technical_skills: list[dict[str, Any]] = []
    pending_meta = None
    for line_number in range(start, end + 1):
        meta = _metadata(lines[line_number - 1], line_number, issues)
        if meta is not None:
            pending_meta = (meta, line_number)
            continue
        line = lines[line_number - 1].strip()
        if not line:
            continue
        if ":" not in line:
            issues.append(_line_issue(line_number, "skill row must be 'Category: item, item'"))
            continue
        metadata, meta_line = pending_meta or (None, line_number)
        source_id = _require_id(metadata, meta_line, seen_ids, issues)
        category, items = line.split(":", 1)
        parsed_items = _split_list(items)
        if not parsed_items:
            issues.append(_line_issue(line_number, "skill row requires at least one item"))
        technical_skills.append(
            {"id": source_id, "category": category.strip(), "items": parsed_items}
        )
        pending_meta = None
    if pending_meta is not None:
        issues.append(_line_issue(pending_meta[1], "metadata is not followed by a skill row"))

    extra_sections: list[dict[str, Any]] = []
    if "Open Source" in sections:
        extra_start, extra_end = bounds("Open Source")
        extra_sections.append(
            {
                "id": "open-source",
                "title": "Open Source",
                "type": "portfolio",
                "items": _parse_experience_or_projects(
                    "Projects", lines, extra_start, extra_end, seen_ids, issues
                ),
            }
        )
    if "Publications" in sections:
        extra_start, extra_end = bounds("Publications")
        extra_sections.append(
            {
                "id": "publications",
                "title": "Publications",
                "type": "publications",
                "items": _parse_bullets(
                    lines, extra_start, extra_end, seen_ids, issues
                ),
            }
        )

    if issues:
        raise CVParseError(path, issues)
    return {
        "schemaVersion": 2,
        "sourceCvSha256": hashlib.sha256(text.encode("utf8")).hexdigest(),
        "summarySourceId": summary_id,
        "basics": basics,
        "summary": summary,
        "experience": experience,
        "certifications": certifications,
        "projects": projects,
        "achievements": achievements,
        "education": education,
        "technicalSkills": technical_skills,
        "extraSections": extra_sections,
    }


def load_cv(path: Path) -> dict[str, Any]:
    return parse_cv_text(path.read_text(encoding="utf8"), path)


def all_source_ids(cv: dict[str, Any]) -> set[str]:
    ids = {cv["summarySourceId"], cv["education"]["id"]}
    for section in ("experience", "projects"):
        for entry in cv[section]:
            ids.add(entry["id"])
            ids.update(bullet["id"] for bullet in entry["bullets"])
    for section in ("certifications", "achievements", "technicalSkills"):
        ids.update(item["id"] for item in cv[section])
    for section in cv.get("extraSections", []):
        ids.update(item["id"] for item in section.get("items", []))
        for item in section.get("items", []):
            ids.update(bullet["id"] for bullet in item.get("bullets", []))
    return ids
