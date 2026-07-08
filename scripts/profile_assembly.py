from __future__ import annotations

from typing import Any

from assemble_resume import (
    _assemble_bullets,
    _assemble_skill_group,
    align_summary_with_headline,
    normalize_job_title,
)
from resume_validation import validate_source_bounded_text, validate_tailored_resume


STANDARD_SECTION_KEYS = {
    "summary",
    "experience",
    "certifications",
    "projects",
    "achievements",
    "education",
    "technical-skills",
}


def _payload_sections(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    sections = payload.get("sections")
    if not isinstance(sections, list):
        raise ValueError("v3 payload sections must be an array.")
    index: dict[str, dict[str, Any]] = {}
    for section in sections:
        if not isinstance(section, dict) or not isinstance(section.get("sourceId"), str):
            raise ValueError("Each v3 payload section requires sourceId.")
        source_id = section["sourceId"]
        if source_id in index:
            raise ValueError(f"v3 payload repeats section {source_id!r}.")
        unknown = set(section) - {"sourceId", "items"}
        if unknown:
            raise ValueError(
                f"v3 payload section {source_id!r} contains unsupported fields: "
                + ", ".join(sorted(unknown))
            )
        items = section.get("items")
        if not isinstance(items, list):
            raise ValueError(f"v3 payload section {source_id!r} items must be an array.")
        index[source_id] = section
    return index


def _selected_requests(
    section_policy: dict[str, Any],
    canonical_items: list[dict[str, Any]],
    payload_section: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    source_id = section_policy["sourceId"]
    canonical_index = {item["id"]: item for item in canonical_items}
    available_ids = section_policy["availableSourceIds"]
    requested = payload_section["items"] if payload_section else []
    request_index: dict[str, dict[str, Any]] = {}
    request_order: list[str] = []
    for item in requested:
        if not isinstance(item, dict) or not isinstance(item.get("sourceId"), str):
            raise ValueError(f"Section {source_id!r} items require sourceId.")
        item_id = item["sourceId"]
        if item_id in request_index:
            raise ValueError(f"Section {source_id!r} repeats sourceId {item_id!r}.")
        if item_id not in canonical_index or item_id not in available_ids:
            raise ValueError(f"Section {source_id!r} contains unavailable sourceId {item_id!r}.")
        request_index[item_id] = item
        request_order.append(item_id)

    mode = section_policy["selectionMode"]
    count = section_policy["effectiveEntryCount"]
    required = section_policy["requiredSourceIds"]
    if mode == "all":
        selected_ids = list(available_ids)
        if requested and set(request_order) != set(selected_ids):
            raise ValueError(f"Section {source_id!r} uses mode 'all' and must include every available item.")
    elif mode == "explicit":
        selected_ids = list(required)
        selected_ids.extend(item_id for item_id in request_order if item_id not in selected_ids)
        if len(selected_ids) != count:
            raise ValueError(f"Section {source_id!r} requires exactly {count} selected item(s).")
    else:
        if not requested and count == len(available_ids):
            selected_ids = list(available_ids)
        else:
            selected_ids = request_order
        if len(selected_ids) != count:
            raise ValueError(f"Section {source_id!r} requires exactly {count} selected item(s).")
    missing_required = set(required) - set(selected_ids)
    if missing_required:
        raise ValueError(
            f"Section {source_id!r} is missing required source IDs: "
            + ", ".join(sorted(missing_required))
        )
    if source_id == "experience":
        selected_ids = [item_id for item_id in available_ids if item_id in selected_ids]
    return [
        request_index.get(item_id, {"sourceId": item_id}) for item_id in selected_ids
    ]


def _assemble_entry_section(
    section_policy: dict[str, Any],
    canonical_items: list[dict[str, Any]],
    requests: list[dict[str, Any]],
    cv: dict[str, Any],
) -> list[dict[str, Any]]:
    source_id = section_policy["sourceId"]
    canonical_index = {item["id"]: item for item in canonical_items}
    assembled: list[dict[str, Any]] = []
    for request in requests:
        source = canonical_index[request["sourceId"]]
        unknown = set(request) - {"sourceId", "bullets", "priorityItems", "items"}
        if unknown:
            raise ValueError(
                f"Section {source_id!r} item contains unsupported fields: "
                + ", ".join(sorted(unknown))
            )
        if source.get("bullets") is not None:
            bullets = _assemble_bullets(request, source, source_id)
            expected = section_policy["effectiveBulletCounts"].get(source["id"], 0)
            if len(bullets) != expected:
                raise ValueError(
                    f"Section {source_id!r} item {source['id']!r} requires exactly {expected} bullet(s)."
                )
            source_bullets = {item["id"]: item for item in source["bullets"]}
            for bullet in bullets:
                issues = validate_source_bounded_text(
                    source_bullets[bullet["sourceId"]]["text"],
                    bullet["text"],
                    cv,
                    f"{source_id} bullet {bullet['sourceId']}",
                )
                if issues:
                    raise ValueError("\n".join(issues))
        else:
            bullets = None
        item = {
            "sourceId": source["id"],
            **{key: value for key, value in source.items() if key not in {"id", "bullets"}},
        }
        if bullets is not None:
            item["bullets"] = bullets
        assembled.append(item)
    return assembled


def assemble_profile_resume(
    payload: dict[str, Any],
    cv: dict[str, Any],
    policy: dict[str, Any],
    canonical_sections: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    if payload.get("schemaVersion") != 3:
        raise ValueError("Profile assembly requires a schemaVersion 3 payload.")
    job_title = payload.get("jobTitle")
    summary = payload.get("summary")
    if not isinstance(job_title, str):
        raise ValueError("v3 payload requires jobTitle.")
    if not isinstance(summary, dict):
        raise ValueError("v3 payload summary must be an object.")
    summary_text = summary.get("text")
    summary_source_ids = summary.get("sourceIds")
    if not isinstance(summary_text, str) or not summary_text.strip():
        raise ValueError("v3 payload summary.text must be non-empty.")
    if not isinstance(summary_source_ids, list) or not summary_source_ids:
        raise ValueError("v3 payload summary.sourceIds must be non-empty.")

    section_payloads = _payload_sections(payload)
    enabled = policy["enabledSections"]
    unknown_payload_sections = set(section_payloads) - set(enabled)
    if unknown_payload_sections:
        raise ValueError(
            "v3 payload contains disabled sections: "
            + ", ".join(sorted(unknown_payload_sections))
        )
    headline = normalize_job_title(job_title)
    tailored: dict[str, Any] = {
        "schemaVersion": 3,
        "sourceCvSha256": cv["sourceCvSha256"],
        "basics": {**cv["basics"], "headline": headline},
    }
    if "summary" in enabled:
        tailored["summarySourceIds"] = summary_source_ids
        tailored["summary"] = align_summary_with_headline(
            summary_text.strip(), headline, cv
        )

    extra_sections: list[dict[str, Any]] = []
    all_effective_content_selected = True
    for section_policy in policy["sections"]:
        source_id = section_policy["sourceId"]
        if source_id == "summary":
            continue
        canonical = canonical_sections[source_id]
        requests = _selected_requests(
            section_policy, canonical.get("items", []), section_payloads.get(source_id)
        )
        if len(requests) != section_policy["effectiveEntryCount"]:
            all_effective_content_selected = False
        if source_id == "technical-skills":
            canonical_index = {item["id"]: item for item in canonical["items"]}
            groups: list[dict[str, Any]] = []
            for request in requests:
                source = canonical_index[request["sourceId"]]
                if "priorityItems" in request:
                    groups.append(
                        _assemble_skill_group(
                            source,
                            request["priorityItems"],
                            section_policy["effectiveItemsPerEntry"],
                            section_policy["maximumReplacementsPerCategory"],
                        )
                    )
                elif "items" in request:
                    items = request["items"]
                    if not isinstance(items, list) or not items:
                        raise ValueError(f"Skill group {source['id']!r} requires items.")
                    unsupported = set(items) - set(source["items"])
                    if unsupported:
                        raise ValueError(
                            f"Skill group {source['id']!r} contains unsupported items: "
                            + ", ".join(sorted(unsupported))
                        )
                    groups.append(
                        {
                            "sourceId": source["id"],
                            "category": source["category"],
                            "items": items[: section_policy["effectiveItemsPerEntry"]],
                        }
                    )
                else:
                    groups.append(
                        {
                            "sourceId": source["id"],
                            "category": source["category"],
                            "items": source["items"][: section_policy["effectiveItemsPerEntry"]],
                        }
                    )
            tailored["technicalSkills"] = groups
            continue
        assembled = _assemble_entry_section(
            section_policy, canonical.get("items", []), requests, cv
        )
        if source_id == "education":
            tailored["education"] = assembled[0] if assembled else None
        elif source_id in STANDARD_SECTION_KEYS:
            tailored[source_id] = assembled
        else:
            extra_sections.append(
                {
                    "sourceId": source_id,
                    "title": canonical["title"],
                    "type": canonical["type"],
                    "items": assembled,
                }
            )
    if extra_sections:
        tailored["extraSections"] = extra_sections
    tailored["sourceExhausted"] = all_effective_content_selected
    issues = validate_tailored_resume(tailored, cv, policy)
    if issues:
        raise ValueError("Tailoring payload validation failed:\n" + "\n".join(issues))
    return tailored
