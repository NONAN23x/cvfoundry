#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from cv_source import load_cv


TOKEN_RE = re.compile(r"[a-z0-9+#./-]+")
STOP_WORDS = {
    "a", "about", "across", "after", "all", "also", "an", "and", "any", "are", "as",
    "at", "be", "because", "been", "being", "between", "both", "by", "can", "company",
    "complete", "contribute", "day", "days", "define", "deliverables", "do", "either",
    "environment", "etc", "for", "from", "functional", "genetics", "good", "group",
    "hesitating", "if", "impact", "in", "including", "individual", "individually",
    "inform", "information", "initiatives", "inline", "into", "is", "it", "join", "know",
    "knowledge", "manager", "many", "months", "more", "national", "need", "of", "on",
    "one", "or", "other", "our", "out", "over", "part", "people", "period", "policies",
    "positive", "process", "processes", "proces", "profile", "provide", "regular",
    "responsibilities", "responsibility", "role", "same", "security", "should", "skills",
    "so", "solidarity", "some", "still", "such", "support", "team", "that", "the",
    "their", "them", "there", "these", "they", "this", "through", "to", "together",
    "understanding", "updates", "us", "useful", "using", "various", "we", "well", "why",
    "will", "with", "within", "work", "working", "years", "you", "your",
}
STATIC_PHRASES = {
    "active directory",
    "application security",
    "certificate lifecycle management",
    "cloud security",
    "incident response",
    "infrastructure security",
    "penetration testing",
    "privilege escalation",
    "public key infrastructure",
    "security operations",
    "source code scanning",
    "static analysis",
    "technical documentation",
    "threat detection",
    "vulnerability assessment",
    "web application security",
    "website vulnerability scanning",
}
HEADING_SIGNAL_WEIGHTS = {
    "responsibilities": 3.0,
    "required profile": 3.0,
    "requirements": 3.0,
    "qualifications": 3.0,
    "what you will do": 3.0,
    "must have": 3.0,
    "preferred": 2.0,
}
BOILERPLATE_HEADINGS = {
    "about us",
    "business insight",
    "equal opportunity",
    "why join us",
    "who we are",
    "company overview",
}
DOMAIN_BOOSTS = (
    {
        "jd": (
            "source code scanning",
            "code scanning",
            "secure code review",
            "sast",
            "static analysis",
        ),
        "entry": (
            "source code scanning",
            "secure code review",
            "static analysis",
            "semgrep",
            "application security",
        ),
        "boost": 5.0,
    },
    {
        "jd": (
            "website vulnerability scanning",
            "web vulnerability scanning",
            "web application scanning",
            "owasp",
            "web application attacks",
        ),
        "entry": (
            "website vulnerability scanning",
            "web application security",
            "vulnerability assessment",
            "penetration testing",
            "wordpress",
        ),
        "boost": 4.0,
    },
    {
        "jd": (
            "monitoring",
            "security operations",
            "soc",
            "siem",
            "xdr",
            "incident response",
            "threat detection",
            "wazuh",
        ),
        "entry": (
            "monitoring",
            "security operations",
            "soc",
            "siem",
            "xdr",
            "incident response",
            "threat detection",
            "wazuh",
        ),
        "boost": 6.0,
    },
    {
        "jd": (
            "technical documentation",
            "documentation",
            "documenting",
            "document",
        ),
        "entry": (
            "technical documentation",
            "walkthrough",
            "documentation",
            "documented",
            "training",
        ),
        "boost": 3.0,
    },
)


def normalize_token(token: str) -> str:
    token = token.strip("./-")
    if token.endswith("ies") and len(token) > 4:
        return token[:-3] + "y"
    if token.endswith("s") and len(token) > 4 and not token.endswith("ss"):
        return token[:-1]
    return token


def _normalize_phrase(value: str) -> str:
    return re.sub(r"\s+", " ", value.casefold()).strip()


def build_phrase_bank(master: dict[str, Any]) -> tuple[str, ...]:
    phrases = set(STATIC_PHRASES)
    for group in master["technicalSkills"]:
        for item in group["items"]:
            normalized = _normalize_phrase(item)
            if " " in normalized or "/" in normalized or "-" in normalized:
                phrases.add(normalized)
    for project in master["projects"]:
        for tag in project.get("tags", []):
            normalized = _normalize_phrase(tag)
            if " " in normalized or "/" in normalized or "-" in normalized:
                phrases.add(normalized)
    for section in master.get("extraSections", []):
        for item in section.get("items", []):
            for tag in item.get("tags", []):
                normalized = _normalize_phrase(tag)
                if " " in normalized or "/" in normalized or "-" in normalized:
                    phrases.add(normalized)
    return tuple(sorted(phrases, key=len, reverse=True))


def tokenize(text: str, phrase_bank: Iterable[str]) -> list[str]:
    lowered = text.casefold()
    tokens: list[str] = []
    for phrase in phrase_bank:
        if phrase in lowered:
            tokens.append(phrase)
    for raw_token in TOKEN_RE.findall(lowered):
        parts = [raw_token]
        if any(separator in raw_token for separator in "-/."):
            parts.extend(piece for piece in re.split(r"[-/.]+", raw_token) if piece)
        for part in parts:
            token = normalize_token(part)
            if len(token) > 1 and token not in STOP_WORDS:
                tokens.append(token)
    return tokens


def _weighted_jd_lines(job_description: str) -> list[tuple[float, str]]:
    weighted_lines: list[tuple[float, str]] = []
    current_weight = 2.0
    saw_heading = False
    for line in job_description.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        normalized = _normalize_phrase(stripped.rstrip(":"))
        if normalized in BOILERPLATE_HEADINGS:
            current_weight = 0.0
            saw_heading = True
            continue
        if normalized in HEADING_SIGNAL_WEIGHTS:
            current_weight = HEADING_SIGNAL_WEIGHTS[normalized]
            saw_heading = True
            continue
        if stripped.startswith("#"):
            current_weight = 3.5 if not saw_heading else 2.5
            saw_heading = True
            continue
        if current_weight <= 0:
            continue
        line_weight = current_weight + (0.5 if stripped.startswith(("*", "-", "•")) else 0.0)
        weighted_lines.append((line_weight, stripped.lstrip("*-• ").strip()))
    return weighted_lines


def weighted_jd_terms(job_description: str, phrase_bank: Iterable[str]) -> Counter[str]:
    terms: Counter[str] = Counter()
    for weight, line in _weighted_jd_lines(job_description):
        for token in tokenize(line, phrase_bank):
            terms[token] += weight
    return terms


def _entry_text(entry: dict[str, Any]) -> str:
    parts = []
    for field in ("name", "role", "company", "stack"):
        if entry.get(field):
            parts.append(str(entry[field]))
    if entry.get("text"):
        parts.append(str(entry["text"]))
    if entry.get("tags"):
        parts.extend(str(tag) for tag in entry["tags"])
    for bullet in entry.get("bullets", []):
        parts.append(str(bullet.get("text", "")))
    return " ".join(parts)


def _entry_counter(entry: dict[str, Any], phrase_bank: Iterable[str]) -> Counter[str]:
    terms = Counter(tokenize(_entry_text(entry), phrase_bank))
    for term in tokenize(entry.get("name") or entry.get("role") or "", phrase_bank):
        terms[term] += 1.5
    for tag in entry.get("tags", []):
        for term in tokenize(str(tag), phrase_bank):
            terms[term] += 2.0
    return terms


def _domain_boost(job_description: str, entry: dict[str, Any]) -> float:
    jd_text = _normalize_phrase(job_description)
    entry_text = _normalize_phrase(_entry_text(entry))
    score = 0.0
    for rule in DOMAIN_BOOSTS:
        if any(phrase in jd_text for phrase in rule["jd"]) and any(
            phrase in entry_text for phrase in rule["entry"]
        ):
            score += rule["boost"]
    return score


def score_entry(entry: dict[str, Any], jd_terms: Counter[str], job_description: str, phrase_bank: Iterable[str]) -> dict[str, Any]:
    entry_terms = _entry_counter(entry, phrase_bank)
    matched = sorted(set(jd_terms) & set(entry_terms))
    score = sum(
        min(jd_terms[term], 4.0) * min(entry_terms[term], 3.0)
        for term in matched
    )
    score += _domain_boost(job_description, entry)
    return {
        "id": entry["id"],
        "name": entry.get("name") or entry.get("role") or entry.get("text") or entry["id"],
        "score": round(score, 2),
        "matchedTerms": matched,
    }


def rank_entries(
    entries: list[dict[str, Any]],
    jd_terms: Counter[str],
    job_description: str,
    phrase_bank: Iterable[str],
) -> list[dict[str, Any]]:
    ranked = [score_entry(entry, jd_terms, job_description, phrase_bank) for entry in entries]
    return sorted(ranked, key=lambda item: (-item["score"], item["name"].lower()))


def build_summary(job_description: str, master: dict[str, Any]) -> dict[str, Any]:
    phrase_bank = build_phrase_bank(master)
    jd_terms = weighted_jd_terms(job_description, phrase_bank)
    project_ranking = rank_entries(master["projects"], jd_terms, job_description, phrase_bank)
    experience_ranking = rank_entries(master["experience"], jd_terms, job_description, phrase_bank)
    section_rankings = {
        section["id"]: rank_entries(
            section.get("items", []), jd_terms, job_description, phrase_bank
        )
        for section in master.get("extraSections", [])
    }
    skill_terms = set(tokenize(" ".join(
        item
        for group in master["technicalSkills"]
        for item in group["items"]
    ), phrase_bank))
    matched_skills = [
        term for term, count in jd_terms.most_common()
        if term in skill_terms and count > 0
    ]
    top_terms = [
        term
        for term, score in sorted(jd_terms.items(), key=lambda item: (-item[1], item[0]))
        if term not in STOP_WORDS
    ]
    return {
        "schemaVersion": 2,
        "topJobTerms": top_terms[:30],
        "matchedSkills": matched_skills[:20],
        "experienceRanking": experience_ranking,
        "projectRanking": project_ranking,
        "recommendedProjectIds": [item["id"] for item in project_ranking[:2]],
        "sectionRankings": section_rankings,
    }


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# Pre-Tailoring Fit Summary",
        "",
        "## Recommended Projects",
        "",
    ]
    recommendations = set(summary["recommendedProjectIds"])
    for item in summary["projectRanking"]:
        marker = "recommended" if item["id"] in recommendations else "candidate"
        terms = ", ".join(item["matchedTerms"]) or "no direct keyword overlap"
        lines.append(f"- {item['name']} ({marker}, score {item['score']}): {terms}")
    lines.extend(["", "## Experience Ranking", ""])
    for item in summary["experienceRanking"]:
        terms = ", ".join(item["matchedTerms"]) or "no direct keyword overlap"
        lines.append(f"- {item['name']} (score {item['score']}): {terms}")
    for section_id, ranking in summary.get("sectionRankings", {}).items():
        lines.extend(["", f"## {section_id.replace('-', ' ').title()} Ranking", ""])
        for item in ranking:
            terms = ", ".join(item["matchedTerms"]) or "no direct keyword overlap"
            lines.append(f"- {item['name']} (score {item['score']}): {terms}")
    lines.extend(["", "## Matched Skills", ""])
    lines.append(", ".join(summary["matchedSkills"]) or "No direct skill matches found.")
    lines.extend(["", "## Highest-Signal Job Terms", ""])
    lines.append(", ".join(summary["topJobTerms"]))
    lines.append("")
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a deterministic pre-tailoring fit report."
    )
    parser.add_argument("job_description")
    parser.add_argument("cv_markdown")
    parser.add_argument("output_dir")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    job_description = Path(args.job_description).read_text(encoding="utf8")
    master = load_cv(Path(args.cv_markdown))
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    summary = build_summary(job_description, master)
    (output_dir / "fit-summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf8"
    )
    (output_dir / "fit-summary.md").write_text(
        render_markdown(summary), encoding="utf8"
    )
    print(json.dumps(summary, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
