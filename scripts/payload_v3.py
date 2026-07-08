from __future__ import annotations

from typing import Any


class PayloadV3Error(ValueError):
    pass


def to_legacy_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("schemaVersion") != 3:
        return payload
    allowed = {"schemaVersion", "jobTitle", "summary", "sections"}
    unknown = set(payload) - allowed
    if unknown:
        raise PayloadV3Error("v3 payload contains unsupported fields: " + ", ".join(sorted(unknown)))
    summary = payload.get("summary")
    if not isinstance(summary, dict):
        raise PayloadV3Error("v3 payload summary must be an object.")
    sections = payload.get("sections")
    if not isinstance(sections, list):
        raise PayloadV3Error("v3 payload sections must be an array.")
    index: dict[str, dict[str, Any]] = {}
    for section in sections:
        if not isinstance(section, dict) or not isinstance(section.get("sourceId"), str):
            raise PayloadV3Error("Each v3 payload section requires sourceId.")
        if section["sourceId"] in index:
            raise PayloadV3Error(f"v3 payload repeats section {section['sourceId']!r}.")
        index[section["sourceId"]] = section

    def entries(source_id: str) -> list[dict[str, Any]]:
        section = index.get(source_id)
        if section is None or not isinstance(section.get("items"), list):
            raise PayloadV3Error(f"v3 payload requires section {source_id!r} with items.")
        return section["items"]

    skills = entries("technical-skills")
    uses_priorities = all("priorityItems" in group for group in skills)
    return {
        "jobTitle": payload.get("jobTitle"),
        "summary": summary.get("text"),
        "summarySourceIds": summary.get("sourceIds"),
        "experience": entries("experience"),
        "projects": entries("projects"),
        ("skillPriorities" if uses_priorities else "technicalSkills"): skills,
    }


def from_legacy_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("schemaVersion") == 3:
        return payload
    skills = payload.get("skillPriorities", payload.get("technicalSkills", []))
    return {
        "schemaVersion": 3,
        "jobTitle": payload.get("jobTitle", payload.get("headline")),
        "summary": {
            "text": payload.get("summary"),
            "sourceIds": payload.get("summarySourceIds", []),
        },
        "sections": [
            {"sourceId": "experience", "items": payload.get("experience", [])},
            {"sourceId": "projects", "items": payload.get("projects", [])},
            {"sourceId": "technical-skills", "items": skills},
        ],
    }
