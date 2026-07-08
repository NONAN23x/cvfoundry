from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from cv_source import load_cv


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROFILE = ROOT / "profiles" / "local"
DEFAULT_THEME_DIR = ROOT / "themes"
HEX_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")
SECTION_TYPES = {
    "summary",
    "timeline",
    "portfolio",
    "publications",
    "credentials",
    "bullets",
    "education",
    "skills",
}
SELECTION_MODES = {"all", "ranked", "explicit"}
REWRITE_MODES = {"none", "source-bounded"}
PAGE_SIZES = {
    "A4": {"widthMm": 210.0, "heightMm": 297.0},
    "LETTER": {"widthMm": 215.9, "heightMm": 279.4},
}


class ProfileConfigError(ValueError):
    pass


def _read_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ProfileConfigError(f"Unable to read valid JSON from {path}: {error}") from error
    if not isinstance(value, dict):
        raise ProfileConfigError(f"{path} must contain a JSON object.")
    return value


def _hash_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _budget(value: Any, label: str) -> dict[str, int]:
    if not isinstance(value, dict):
        raise ProfileConfigError(f"{label} must be an object.")
    result: dict[str, int] = {}
    for key in ("min", "preferred", "max"):
        item = value.get(key)
        if not isinstance(item, int) or item < 0:
            raise ProfileConfigError(f"{label}.{key} must be a non-negative integer.")
        result[key] = item
    if not result["min"] <= result["preferred"] <= result["max"]:
        raise ProfileConfigError(f"{label} must satisfy min <= preferred <= max.")
    return result


def validate_resume_config(config: dict[str, Any], path: Path) -> dict[str, Any]:
    if config.get("schemaVersion") != 3:
        raise ProfileConfigError(f"{path} must use schemaVersion 3.")
    document = config.get("document")
    if not isinstance(document, dict):
        raise ProfileConfigError(f"{path} requires a document object.")
    page_size = str(document.get("pageSize", "")).upper()
    if page_size not in PAGE_SIZES:
        raise ProfileConfigError("document.pageSize must be A4 or LETTER.")
    target = document.get("targetPages")
    maximum = document.get("maxPages")
    if target not in (1, 2) or maximum not in (1, 2) or target > maximum:
        raise ProfileConfigError(
            "document.targetPages and document.maxPages must be 1 or 2, with targetPages <= maxPages."
        )
    theme = config.get("theme")
    if not isinstance(theme, str) or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", theme):
        raise ProfileConfigError("theme must be a lowercase kebab-case theme ID.")
    contacts = config.get("header", {}).get("contactFields", [])
    if not isinstance(contacts, list) or not all(isinstance(item, str) for item in contacts):
        raise ProfileConfigError("header.contactFields must be a string array.")
    sections = config.get("sections")
    if not isinstance(sections, list) or not sections:
        raise ProfileConfigError("sections must be a non-empty array.")
    seen: set[str] = set()
    normalized_sections: list[dict[str, Any]] = []
    for index, section in enumerate(sections):
        if not isinstance(section, dict):
            raise ProfileConfigError(f"sections[{index}] must be an object.")
        source_id = section.get("sourceId")
        section_type = section.get("type")
        if not isinstance(source_id, str) or not source_id:
            raise ProfileConfigError(f"sections[{index}].sourceId must be non-empty.")
        if source_id in seen:
            raise ProfileConfigError(f"sections repeats sourceId {source_id!r}.")
        seen.add(source_id)
        if section_type not in SECTION_TYPES:
            raise ProfileConfigError(
                f"sections[{index}].type must be one of {', '.join(sorted(SECTION_TYPES))}."
            )
        mode = section.get("selection", {}).get("mode", "all")
        if mode not in SELECTION_MODES:
            raise ProfileConfigError(f"sections[{index}].selection.mode is invalid.")
        rewrite = section.get("rewrite", "none")
        if rewrite not in REWRITE_MODES:
            raise ProfileConfigError(f"sections[{index}].rewrite is invalid.")
        selection = dict(section.get("selection", {}))
        selection["mode"] = mode
        for list_name in ("requiredSourceIds", "excludedSourceIds"):
            values = selection.get(list_name, [])
            if (
                not isinstance(values, list)
                or not all(isinstance(item, str) and item for item in values)
                or len(values) != len(set(values))
            ):
                raise ProfileConfigError(
                    f"sections[{index}].selection.{list_name} must be a unique string array."
                )
            selection[list_name] = list(values)
        overlap = set(selection["requiredSourceIds"]) & set(
            selection["excludedSourceIds"]
        )
        if overlap:
            raise ProfileConfigError(
                f"sections[{index}] cannot require and exclude the same source IDs: "
                + ", ".join(sorted(overlap))
            )
        if "entries" in selection:
            selection["entries"] = _budget(selection["entries"], f"sections[{index}].selection.entries")
        if "bulletsPerEntry" in selection:
            selection["bulletsPerEntry"] = _budget(
                selection["bulletsPerEntry"], f"sections[{index}].selection.bulletsPerEntry"
            )
        if "itemsPerEntry" in selection:
            selection["itemsPerEntry"] = _budget(
                selection["itemsPerEntry"],
                f"sections[{index}].selection.itemsPerEntry",
            )
        normalized_sections.append({**section, "selection": selection})
    return {
        **config,
        "document": {**document, "pageSize": page_size},
        "sections": normalized_sections,
    }


def _local_font(profile_root: Path, theme_path: Path, value: Any, label: str) -> Path:
    if not isinstance(value, str) or not value:
        raise ProfileConfigError(f"{label} must be a local font path.")
    if re.match(r"^[a-z]+://", value, re.IGNORECASE):
        raise ProfileConfigError(f"{label} must not use a remote URL.")
    candidate = (theme_path.parent / value).resolve()
    allowed_roots = (ROOT.resolve(), profile_root.resolve())
    if not any(candidate == root or root in candidate.parents for root in allowed_roots):
        raise ProfileConfigError(f"{label} resolves outside the project/profile roots.")
    if not candidate.is_file():
        raise ProfileConfigError(f"{label} does not exist: {candidate}")
    return candidate


def validate_theme(theme: dict[str, Any], path: Path, profile_root: Path) -> dict[str, Any]:
    if theme.get("schemaVersion") != 1:
        raise ProfileConfigError(f"{path} must use schemaVersion 1.")
    font = theme.get("font")
    if not isinstance(font, dict) or not isinstance(font.get("family"), str):
        raise ProfileConfigError("theme.font requires a family and local files.")
    files = font.get("files")
    if not isinstance(files, dict):
        raise ProfileConfigError("theme.font.files must be an object.")
    resolved_files = {
        style: str(_local_font(profile_root, path, files.get(style), f"font.files.{style}"))
        for style in ("regular", "bold", "italic", "boldItalic")
    }
    colors = theme.get("colors")
    if not isinstance(colors, dict):
        raise ProfileConfigError("theme.colors must be an object.")
    for key in ("accent", "ink", "background"):
        if not HEX_COLOR_RE.fullmatch(str(colors.get(key, ""))):
            raise ProfileConfigError(f"theme.colors.{key} must be #RRGGBB.")
    typography = theme.get("typography")
    if not isinstance(typography, dict):
        raise ProfileConfigError("theme.typography must be an object.")
    for key in ("bodyPt", "minimumBodyPt", "namePt", "headlinePt", "sectionPt", "contactPt"):
        value = typography.get(key)
        if not isinstance(value, (int, float)) or value <= 0:
            raise ProfileConfigError(f"theme.typography.{key} must be positive.")
    if typography["minimumBodyPt"] < 8.5 or typography["bodyPt"] < typography["minimumBodyPt"]:
        raise ProfileConfigError("minimumBodyPt must be at least 8.5 and no larger than bodyPt.")
    geometry = theme.get("geometry")
    if not isinstance(geometry, dict):
        raise ProfileConfigError("theme.geometry must be an object.")
    for key in ("topMarginMm", "bottomMarginMm", "leftMarginMm", "rightMarginMm"):
        value = geometry.get(key)
        if not isinstance(value, (int, float)) or not 5 <= value <= 30:
            raise ProfileConfigError(f"theme.geometry.{key} must be between 5 and 30 mm.")
    spacing = theme.get("spacing")
    if not isinstance(spacing, dict):
        raise ProfileConfigError("theme.spacing must be an object.")
    for key in ("comfortable", "compact"):
        level = spacing.get(key)
        if not isinstance(level, dict):
            raise ProfileConfigError(f"theme.spacing.{key} must be an object.")
        for token in ("sectionBeforeMm", "entryBeforeMm"):
            if not isinstance(level.get(token), (int, float)) or level[token] < 0:
                raise ProfileConfigError(f"theme.spacing.{key}.{token} must be non-negative.")
    bullets = theme.get("bullets")
    if not isinstance(bullets, dict):
        raise ProfileConfigError("theme.bullets must be an object.")
    for key in ("leftMarginMm", "gapMm"):
        value = bullets.get(key)
        if not isinstance(value, (int, float)) or value < 0:
            raise ProfileConfigError(f"theme.bullets.{key} must be non-negative.")
    return {**theme, "font": {**font, "files": resolved_files}}


def canonical_sections(cv: dict[str, Any]) -> list[dict[str, Any]]:
    sections = [
        {"id": "summary", "title": "Summary", "type": "summary", "items": [{"id": cv["summarySourceId"], "text": cv["summary"]}]},
        {"id": "experience", "title": "Experience", "type": "timeline", "items": cv["experience"]},
        {"id": "certifications", "title": "Certifications", "type": "credentials", "items": cv["certifications"]},
        {"id": "projects", "title": "Projects", "type": "portfolio", "items": cv["projects"]},
        {"id": "achievements", "title": "Achievements", "type": "bullets", "items": cv["achievements"]},
        {"id": "education", "title": "Education", "type": "education", "items": [cv["education"]]},
        {"id": "technical-skills", "title": "Technical Skills", "type": "skills", "items": cv["technicalSkills"]},
    ]
    sections.extend(cv.get("extraSections", []))
    return sections


def load_profile(profile_dir: Path = DEFAULT_PROFILE) -> dict[str, Any]:
    profile_dir = profile_dir.resolve()
    cv_path = profile_dir / "CV.md"
    resume_path = profile_dir / "resume.json"
    writing_style_path = profile_dir / "Writing-Style.md"
    missing = [
        path.name
        for path in (cv_path, writing_style_path, resume_path)
        if not path.is_file()
    ]
    if missing:
        raise ProfileConfigError(
            f"Profile {profile_dir} is incomplete; missing {', '.join(missing)}. "
            f"Run './jobs-tailor init {profile_dir}' to create a private profile."
        )
    config = validate_resume_config(_read_object(resume_path), resume_path)
    theme_path = DEFAULT_THEME_DIR / f"{config['theme']}.json"
    theme = validate_theme(_read_object(theme_path), theme_path, profile_dir)
    cv = load_cv(cv_path)
    section_index = {section["id"]: section for section in canonical_sections(cv)}
    for configured in config["sections"]:
        source_id = configured["sourceId"]
        if source_id not in section_index:
            raise ProfileConfigError(f"Configured section {source_id!r} is absent from CV.md.")
        if section_index[source_id]["type"] != configured["type"]:
            raise ProfileConfigError(
                f"Configured section {source_id!r} type does not match CV.md."
            )
    return {
        "root": profile_dir,
        "cvPath": cv_path,
        "writingStylePath": writing_style_path,
        "resumePath": resume_path,
        "themePath": theme_path,
        "cv": cv,
        "sections": section_index,
        "config": config,
        "theme": theme,
        "hashes": {
            "cv": _hash_file(cv_path),
            "resumeConfig": _hash_file(resume_path),
            "theme": _hash_file(theme_path),
        },
    }


def resolve_effective_policy(profile: dict[str, Any]) -> dict[str, Any]:
    document = profile["config"]["document"]
    layout = profile["config"].get("layout", {})
    target_key = "preferred" if document["targetPages"] == 1 else "max"
    resolved_sections: list[dict[str, Any]] = []
    for configured in profile["config"]["sections"]:
        source_id = configured["sourceId"]
        selection = configured["selection"]
        canonical = profile["sections"][source_id]
        excluded = set(selection.get("excludedSourceIds", []))
        canonical_ids = {item["id"] for item in canonical.get("items", [])}
        unknown_excluded = excluded - canonical_ids
        if unknown_excluded:
            raise ProfileConfigError(
                f"Section {source_id!r} excludes unknown source IDs: "
                + ", ".join(sorted(unknown_excluded))
            )
        available_items = [
            item for item in canonical.get("items", []) if item["id"] not in excluded
        ]
        available_ids = [item["id"] for item in available_items]
        required_ids = list(selection.get("requiredSourceIds", []))
        unknown_required = set(required_ids) - set(available_ids)
        if unknown_required:
            raise ProfileConfigError(
                f"Section {source_id!r} requires unavailable source IDs: "
                + ", ".join(sorted(unknown_required))
            )
        entries = selection.get("entries")
        if entries and len(required_ids) > entries["max"]:
            raise ProfileConfigError(
                f"Section {source_id!r} has more required IDs than its maximum entry budget."
            )
        if selection["mode"] == "all" or entries is None:
            effective_count = len(available_items)
        else:
            requested_count = entries[target_key]
            effective_count = min(len(available_items), requested_count)
            effective_count = max(min(len(available_items), entries["min"]), effective_count)
            effective_count = max(effective_count, len(required_ids))
        bullets = selection.get("bulletsPerEntry")
        desired_bullets = bullets[target_key] if bullets else None
        bullet_counts = {
            item["id"]: min(desired_bullets, len(item.get("bullets", [])))
            for item in available_items
            if desired_bullets is not None
        }
        items_per_entry = selection.get("itemsPerEntry")
        resolved_sections.append(
            {
                "sourceId": source_id,
                "type": configured["type"],
                "priority": configured.get("priority", 0),
                "selectionMode": selection["mode"],
                "rewrite": configured["rewrite"],
                "availableSourceIds": available_ids,
                "requiredSourceIds": required_ids,
                "excludedSourceIds": sorted(excluded),
                "availableEntryCount": len(available_items),
                "effectiveEntryCount": effective_count,
                "effectiveBulletCounts": bullet_counts,
                "effectiveItemsPerEntry": (
                    items_per_entry[target_key] if items_per_entry else None
                ),
                "maximumReplacementsPerCategory": selection.get(
                    "maximumReplacementsPerCategory", 0
                ),
            }
        )
    section_index = {item["sourceId"]: item for item in resolved_sections}

    def count(source_id: str) -> int:
        return section_index.get(source_id, {}).get("effectiveEntryCount", 0)

    def uniform_bullet_count(source_id: str) -> int:
        values = section_index.get(source_id, {}).get("effectiveBulletCounts", {}).values()
        return min(values) if values else 0

    skills = section_index.get("technical-skills", {})
    achievements = section_index.get("achievements", {})
    return {
        "schemaVersion": 1,
        "document": dict(document),
        "sections": resolved_sections,
        "sectionsById": section_index,
        "requiredExperienceCount": count("experience"),
        "requiredProjectCount": count("projects"),
        "experienceBulletsPerEntry": uniform_bullet_count("experience"),
        "projectBulletsPerEntry": uniform_bullet_count("projects"),
        "requiredCertificationCount": count("certifications"),
        "requiredAchievementCount": count("achievements"),
        "requiredTechnicalSkillCategoryCount": count("technical-skills"),
        "technicalSkillSlotsPerCategory": skills.get("effectiveItemsPerEntry") or 0,
        "maximumTechnicalSkillReplacementsPerCategory": skills.get(
            "maximumReplacementsPerCategory", 0
        ),
        "maximumBulletLines": (
            layout.get("maximumBulletLines", 1)
            if document["targetPages"] == 1
            else max(2, layout.get("maximumBulletLines", 2))
        ),
        "requiredContactLines": layout.get("requiredContactLines", 1),
        "maximumSummaryLines": layout.get("maximumSummaryLines", 3),
        "maximumSkillRowLines": layout.get("maximumSkillRowLines", 1),
        "minimumBottomWhitespaceMm": layout.get("minimumBottomWhitespaceMm", 10),
        "maximumBottomWhitespaceMm": layout.get("maximumBottomWhitespaceMm", 18),
        "maximumIntermediatePageWhitespaceMm": layout.get(
            "maximumIntermediatePageWhitespaceMm", 25
        ),
        "requiredAchievementSourceIds": achievements.get("requiredSourceIds", []),
        "targetPages": document["targetPages"],
        "maxPages": document["maxPages"],
        "pageSize": document["pageSize"],
        "enabledSections": [item["sourceId"] for item in resolved_sections],
    }


def legacy_policy(profile: dict[str, Any]) -> dict[str, Any]:
    """Compatibility alias for callers written before the unified resolver."""
    return resolve_effective_policy(profile)
