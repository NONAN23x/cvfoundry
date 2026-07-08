#!/usr/bin/env python3

from __future__ import annotations

import re
from typing import Any

from cv_source import all_source_ids


NUMERIC_FACT_RE = re.compile(r"(?<!\w)\d+(?:\.\d+)?(?:%|\+)?(?!\w)")
TOKEN_RE = re.compile(r"\b[A-Za-z][A-Za-z0-9.+#/-]*\b")
COMPOSITE_HEADLINE_RE = re.compile(r"\s(?:and)\s|[&/]")
ALIAS_PATTERNS = (
    (re.compile(r"\bweb apps?\b", re.IGNORECASE), "web application"),
    (re.compile(r"\bui\s*/\s*ux\b", re.IGNORECASE), "uiux"),
    (re.compile(r"\bui\b", re.IGNORECASE), "uiux"),
    (re.compile(r"\bux\b", re.IGNORECASE), "uiux"),
)


def _index(items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        item["id"]: item
        for item in items
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }


def _numeric_facts(text: str) -> set[str]:
    return set(NUMERIC_FACT_RE.findall(text))


def _technology_terms(cv: dict[str, Any]) -> set[str]:
    terms: set[str] = set()
    for group in cv["technicalSkills"]:
        terms.update(item.casefold() for item in group["items"])
        for item in group["items"]:
            terms.update(token.casefold() for token in TOKEN_RE.findall(item))
    for project in cv["projects"]:
        terms.update(token.casefold() for token in TOKEN_RE.findall(project["stack"]))
    return terms


def _claim_tokens(text: str, technology_terms: set[str]) -> set[str]:
    claims: set[str] = set()
    canonical_text = _canonicalize_aliases(text)
    for token in TOKEN_RE.findall(canonical_text):
        folded = token.casefold()
        is_named_term = folded in technology_terms
        is_acronym = len(token) > 1 and token.upper() == token and any(ch.isalpha() for ch in token)
        if is_named_term or is_acronym:
            claims.add(folded)
    return claims


def _text(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _canonicalize_aliases(text: str) -> str:
    canonical = text
    for pattern, replacement in ALIAS_PATTERNS:
        canonical = pattern.sub(replacement, canonical)
    return canonical


def validate_source_bounded_text(
    source_text: str, rewritten_text: str, cv: dict[str, Any], label: str
) -> list[str]:
    issues: list[str] = []
    unsupported_numbers = _numeric_facts(rewritten_text) - _numeric_facts(source_text)
    unsupported_tokens = _claim_tokens(
        rewritten_text, _technology_terms(cv)
    ) - _claim_tokens(source_text, _technology_terms(cv))
    if unsupported_numbers:
        issues.append(
            f"{label} adds unsupported numeric facts: "
            + ", ".join(sorted(unsupported_numbers))
        )
    if unsupported_tokens:
        issues.append(
            f"{label} adds unsupported factual tokens: "
            + ", ".join(sorted(unsupported_tokens))
        )
    return issues


def _dict_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _source_text_index(cv: dict[str, Any]) -> dict[str, str]:
    values = {cv["summarySourceId"]: cv["summary"], cv["education"]["id"]: " ".join(
        str(cv["education"][key]) for key in ("institution", "location", "degree", "dates", "gpa")
    )}
    for section in ("experience", "projects"):
        for entry in cv[section]:
            values[entry["id"]] = " ".join(
                str(entry.get(key, ""))
                for key in ("role", "company", "dates", "name", "stack")
            )
            values.update({bullet["id"]: bullet["text"] for bullet in entry["bullets"]})
    for section in ("certifications", "achievements", "technicalSkills"):
        for item in cv[section]:
            values[item["id"]] = " ".join(
                str(value) if not isinstance(value, list) else " ".join(value)
                for key, value in item.items()
                if key != "id"
            )
    return values


def validate_tailored_resume(
    tailored: dict[str, Any], cv: dict[str, Any], policy: dict[str, Any]
) -> list[str]:
    issues: list[str] = []
    dynamic_policy = bool(policy.get("sectionsById"))
    enabled = set(
        policy.get(
            "enabledSections",
            [
                "summary", "experience", "certifications", "projects",
                "achievements", "education", "technical-skills",
            ],
        )
    )
    section_policies = policy.get("sectionsById", {})
    technology_terms = _technology_terms(cv)
    source_texts = _source_text_index(cv)
    if tailored.get("schemaVersion") not in (2, 3):
        issues.append("tailored-resume.json must use schemaVersion 2 or 3.")
    if tailored.get("sourceCvSha256") != cv.get("sourceCvSha256"):
        issues.append("tailored-resume.json sourceCvSha256 does not match CV.md.")
    summary_source_ids = tailored.get("summarySourceIds")
    if "summary" not in enabled:
        if "summary" in tailored or "summarySourceIds" in tailored:
            issues.append("Tailored resume contains disabled section 'summary'.")
    elif not isinstance(summary_source_ids, list) or not summary_source_ids:
        issues.append("summarySourceIds must be a non-empty array.")
    else:
        unknown = set(summary_source_ids) - all_source_ids(cv)
        if unknown:
            issues.append("Summary has unknown source IDs: " + ", ".join(sorted(unknown)))
        else:
            supported_summary_text = " ".join(source_texts[source_id] for source_id in summary_source_ids)
            summary_text = _text(tailored.get("summary"))
            unsupported_numbers = _numeric_facts(summary_text) - _numeric_facts(
                supported_summary_text
            )
            unsupported_tokens = _claim_tokens(
                summary_text, technology_terms
            ) - _claim_tokens(supported_summary_text, technology_terms)
            if unsupported_numbers:
                issues.append(
                    "Summary adds unsupported numeric facts: "
                    + ", ".join(sorted(unsupported_numbers))
                )
            if unsupported_tokens:
                issues.append(
                    "Summary adds unsupported factual tokens: "
                    + ", ".join(sorted(unsupported_tokens))
                )

    basics = tailored.get("basics", {})
    if not isinstance(basics, dict):
        issues.append("Tailored basics must be a JSON object.")
        basics = {}
    for field in ("name", "phone", "email", "linkedin", "github", "website"):
        if basics.get(field) != cv["basics"].get(field):
            issues.append(f"Tailored basics changed canonical field {field!r}.")
    if not basics.get("headline"):
        issues.append("Tailored basics requires a headline.")
    elif COMPOSITE_HEADLINE_RE.search(str(basics.get("headline"))):
        issues.append("Tailored headline must contain exactly one prominent role title.")
    if "summary" in enabled and (
        not isinstance(tailored.get("summary"), str) or not tailored["summary"].strip()
    ):
        issues.append("Tailored summary must be non-empty.")

    experience = _dict_list(tailored.get("experience"))
    projects = _dict_list(tailored.get("projects"))
    if "experience" in enabled and not isinstance(tailored.get("experience"), list):
        issues.append("Tailored experience must be an array.")
    if "projects" in enabled and not isinstance(tailored.get("projects"), list):
        issues.append("Tailored projects must be an array.")
    if len(experience) != policy["requiredExperienceCount"]:
        issues.append(
            f"Tailored resume must include exactly {policy['requiredExperienceCount']} experience entries."
        )
    experience_ids = [entry.get("sourceId") for entry in experience]
    canonical_experience_order = [entry["id"] for entry in cv["experience"]]
    experience_policy = section_policies.get("experience", {})
    if dynamic_policy and not set(experience_ids) <= set(
        experience_policy.get("availableSourceIds", [])
    ):
        issues.append("Tailored resume contains unavailable experience entries.")
    elif not dynamic_policy and set(experience_ids) != set(canonical_experience_order):
        issues.append("Tailored resume must include every canonical experience entry.")
    if experience_ids != [
        item_id for item_id in canonical_experience_order if item_id in experience_ids
    ]:
        issues.append("Tailored resume experience order must follow canonical CV chronology.")
    if len(projects) != policy["requiredProjectCount"]:
        issues.append(
            f"Tailored resume must include exactly {policy['requiredProjectCount']} projects."
        )
    project_ids = [entry.get("sourceId") for entry in projects]
    if len(set(project_ids)) != len(project_ids):
        issues.append("Tailored resume repeats a project sourceId.")

    for section_name, section_id, tailored_items, source_items, bullet_count in (
        (
            "Experience",
            "experience",
            experience,
            cv["experience"],
            policy["experienceBulletsPerEntry"],
        ),
        ("Project", "projects", projects, cv["projects"], policy["projectBulletsPerEntry"]),
    ):
        source_index = _index(source_items)
        for entry in tailored_items:
            source_id = entry.get("sourceId")
            source = source_index.get(source_id)
            if source is None:
                issues.append(f"{section_name} entry has unknown sourceId: {source_id!r}")
                continue
            for field in ("role", "company", "dates", "name", "stack"):
                if field in entry and entry.get(field) != source.get(field):
                    issues.append(
                        f"{section_name} entry {source_id} changed canonical field {field!r}."
                    )
            expected_bullet_count = section_policies.get(section_id, {}).get(
                "effectiveBulletCounts", {}
            ).get(source_id, bullet_count)
            bullets = entry.get("bullets", [])
            if not isinstance(bullets, list) or len(bullets) != expected_bullet_count:
                issues.append(
                    f"{section_name} entry {source_id!r} has "
                    f"{len(bullets) if isinstance(bullets, list) else 0} bullets; "
                    f"expected exactly {expected_bullet_count}."
                )
                continue
            bullet_ids = [bullet.get("sourceId") for bullet in bullets]
            if len(set(bullet_ids)) != len(bullet_ids):
                issues.append(f"{section_name} entry {source_id!r} repeats a bullet sourceId.")
            source_bullets = _index(source["bullets"])
            for bullet in bullets:
                if not isinstance(bullet, dict):
                    issues.append(f"{section_name} entry {source_id!r} contains a non-object bullet.")
                    continue
                source_bullet = source_bullets.get(bullet.get("sourceId"))
                if source_bullet is None:
                    issues.append(
                        f"{section_name} bullet has unknown sourceId: {bullet.get('sourceId')!r}"
                    )
                    continue
                bullet_text = _text(bullet.get("text"))
                if not bullet_text.strip():
                    issues.append(
                        f"{section_name} bullet {bullet.get('sourceId')!r} requires non-empty text."
                    )
                    continue
                unsupported_numbers = _numeric_facts(bullet_text) - _numeric_facts(
                    source_bullet["text"]
                )
                if unsupported_numbers:
                    issues.append(
                        f"{section_name} bullet {bullet.get('sourceId')} adds unsupported numeric facts: "
                        + ", ".join(sorted(unsupported_numbers))
                    )
                unsupported_tokens = _claim_tokens(
                    bullet_text, technology_terms
                ) - _claim_tokens(source_bullet["text"], technology_terms)
                if unsupported_tokens:
                    issues.append(
                        f"{section_name} bullet {bullet.get('sourceId')} adds unsupported factual tokens: "
                        + ", ".join(sorted(unsupported_tokens))
                    )

    certifications = _dict_list(tailored.get("certifications"))
    if "certifications" in enabled and not isinstance(tailored.get("certifications"), list):
        issues.append("Tailored certifications must be an array.")
    if len(certifications) != policy["requiredCertificationCount"]:
        issues.append(
            f"Tailored resume must include exactly {policy['requiredCertificationCount']} certifications."
        )
    source_certs = _index(cv["certifications"])
    for item in certifications:
        source = source_certs.get(item.get("sourceId"))
        if source is None:
            issues.append(f"Certification has unknown sourceId: {item.get('sourceId')!r}")
            continue
        for field in ("name", "issuer", "date"):
            if item.get(field) != source[field]:
                issues.append(
                    f"Certification {item.get('sourceId')} changed canonical field {field!r}."
                )

    achievements = _dict_list(tailored.get("achievements"))
    if "achievements" in enabled and not isinstance(tailored.get("achievements"), list):
        issues.append("Tailored achievements must be an array.")
    if len(achievements) != policy["requiredAchievementCount"]:
        issues.append(
            f"Tailored resume must include exactly {policy['requiredAchievementCount']} achievements."
        )
    source_achievements = _index(cv["achievements"])
    required_achievement_ids = set(policy["requiredAchievementSourceIds"])
    actual_achievement_ids = {item.get("sourceId") for item in achievements}
    missing = required_achievement_ids - actual_achievement_ids
    if missing:
        issues.append("Tailored resume is missing required achievements: " + ", ".join(sorted(missing)))
    for item in achievements:
        source = source_achievements.get(item.get("sourceId"))
        if source is None:
            issues.append(f"Achievement has unknown sourceId: {item.get('sourceId')!r}")
            continue
        if item.get("text") != source["text"]:
            issues.append(f"Achievement {item.get('sourceId')} changed canonical text.")
        if item.get("url") != source.get("url"):
            issues.append(f"Achievement {item.get('sourceId')} changed canonical URL.")

    education = tailored.get("education", {})
    if "education" in enabled:
        if not isinstance(education, dict):
            issues.append("Tailored education must be a JSON object.")
            education = {}
        if education.get("sourceId") != cv["education"]["id"]:
            issues.append("Education has an unknown or missing sourceId.")
        for field in ("institution", "location", "degree", "dates", "gpa"):
            if education.get(field) != cv["education"].get(field):
                issues.append(f"Education changed canonical field {field!r}.")
    elif "education" in tailored:
        issues.append("Tailored resume contains disabled section 'education'.")

    skill_groups = _dict_list(tailored.get("technicalSkills"))
    if "technical-skills" in enabled and not isinstance(tailored.get("technicalSkills"), list):
        issues.append("Tailored technicalSkills must be an array.")
    if len(skill_groups) != policy["requiredTechnicalSkillCategoryCount"]:
        issues.append(
            f"Tailored resume must include exactly {policy['requiredTechnicalSkillCategoryCount']} technical skill categories."
        )
    source_skills = _index(cv["technicalSkills"])
    skill_source_ids = [group.get("sourceId") for group in skill_groups]
    if len(set(skill_source_ids)) != len(skill_source_ids):
        issues.append("Tailored resume repeats a technical skill category sourceId.")
    expected_skill_ids = set(
        section_policies.get("technical-skills", {}).get(
            "availableSourceIds", source_skills
        )
    )
    if dynamic_policy:
        if not set(skill_source_ids) <= expected_skill_ids:
            issues.append("Tailored resume contains unavailable technical skill categories.")
    elif set(skill_source_ids) != set(source_skills):
        issues.append("Tailored resume must include every canonical technical skill category.")
    for group in skill_groups:
        source = source_skills.get(group.get("sourceId"))
        if source is None:
            issues.append(f"Technical skill category has unknown sourceId: {group.get('sourceId')!r}")
            continue
        if group.get("category") != source["category"]:
            issues.append(
                f"Technical skill category {group.get('sourceId')} changed canonical category."
            )
        items = group.get("items", [])
        if not isinstance(items, list) or not all(isinstance(item, str) for item in items):
            issues.append(
                f"Technical skill category {group.get('sourceId')} must provide a string array."
            )
            continue
        unsupported = set(items) - set(source.get("items", []))
        if unsupported:
            issues.append(
                f"Technical skill category {group.get('sourceId')} contains unsupported items: "
                + ", ".join(sorted(unsupported))
            )
    return issues
