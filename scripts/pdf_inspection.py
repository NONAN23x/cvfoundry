#!/usr/bin/env python3

from __future__ import annotations

import hashlib
import html
import json
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any


SECTION_TITLES = [
    "SUMMARY",
    "EXPERIENCE",
    "CERTIFICATIONS",
    "PROJECTS",
    "ACHIEVEMENTS",
    "EDUCATION",
    "TECHNICAL SKILLS",
]


class PdfToolCache:
    def __init__(self) -> None:
        self._commands: dict[str, str] = {}
        self._output_cache: dict[tuple[str, ...], str] = {}
        self._version_cache: dict[str, str] = {}

    def command(self, name: str) -> str:
        if name not in self._commands:
            resolved = shutil.which(name)
            if not resolved:
                raise RuntimeError(f"Required command is unavailable: {name}")
            self._commands[name] = resolved
        return self._commands[name]

    def run(self, command: list[str]) -> str:
        key = tuple(command)
        if key in self._output_cache:
            return self._output_cache[key]
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            raise RuntimeError(
                f"{Path(command[0]).name} failed with exit code {result.returncode}: "
                f"{result.stderr.strip()}"
            )
        self._output_cache[key] = result.stdout
        return result.stdout


    def version(self, command: str) -> str:
        if command in self._version_cache:
            return self._version_cache[command]
        result = subprocess.run(
            [self.command(command), "-v"],
            capture_output=True,
            text=True,
            check=False,
        )
        output = (result.stdout or result.stderr).strip().splitlines()
        version = output[0] if output else "unknown"
        self._version_cache[command] = version
        return version


def pdfinfo_map(pdf_path: Path, cache: PdfToolCache) -> dict[str, str]:
    output = cache.run([cache.command("pdfinfo"), str(pdf_path)])
    values: dict[str, str] = {}
    for line in output.splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            values[key.strip()] = value.strip()
    return values


def extract_lines(
    pdf_path: Path, cache: PdfToolCache
) -> tuple[list[dict[str, Any]], float, float]:
    xml_text = cache.run([cache.command("pdftotext"), "-bbox-layout", str(pdf_path), "-"])
    root = ET.fromstring(xml_text)
    namespace = {"x": "http://www.w3.org/1999/xhtml"}
    pages = root.findall(".//x:page", namespace)
    if not pages:
        raise RuntimeError("pdftotext returned no page geometry.")
    width = float(pages[0].attrib["width"])
    height = float(pages[0].attrib["height"])
    lines: list[dict[str, Any]] = []
    for page_index, page in enumerate(pages, start=1):
        for line in page.findall(".//x:line", namespace):
            words = [
                html.unescape(word.text or "")
                for word in line.findall("./x:word", namespace)
                if (word.text or "").strip()
            ]
            text = " ".join(words).strip()
            if text:
                lines.append(
                    {
                        "page": page_index,
                        "text": text,
                        "xMin": float(line.attrib["xMin"]),
                        "yMin": float(line.attrib["yMin"]),
                        "xMax": float(line.attrib["xMax"]),
                        "yMax": float(line.attrib["yMax"]),
                    }
                )
    lines.sort(key=lambda item: (item["page"], round(item["yMin"], 1), item["xMin"]))
    return lines, width, height


def _normalized(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().lstrip("• ")


def _title_key(value: str) -> str:
    return re.sub(r"\s+", "", value).upper()


def _title_index(texts: list[str], title: str) -> int | None:
    key = _title_key(title)
    return next(
        (index for index, text in enumerate(texts) if _title_key(text) == key),
        None,
    )


def _line_count_for_text(lines: list[dict[str, Any]], target: str) -> int:
    lines = [line for line in lines if _normalized(line["text"])]
    target_words = _normalized(target).split()
    if not target_words:
        return 0
    for line in lines:
        if _normalized(target) in _normalized(line["text"]):
            return 1
    for start in range(len(lines)):
        collected: list[str] = []
        for end in range(start, min(len(lines), start + 4)):
            collected.extend(_normalized(lines[end]["text"]).split())
            if collected == target_words:
                return end - start + 1
            if len(collected) >= len(target_words):
                break
    return 0


def inspect_pdf(
    pdf_path: Path,
    tailored: dict[str, Any],
    policy: dict[str, Any],
    source_json_sha256: str,
    theme: dict[str, Any] | None = None,
    resume_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cache = PdfToolCache()
    info = pdfinfo_map(pdf_path, cache)
    lines, width, height = extract_lines(pdf_path, cache)
    texts = [_normalized(line["text"]) for line in lines]
    issues: list[str] = []

    pages = int(info.get("Pages", "0") or 0)
    target_pages = int(policy.get("targetPages", 1))
    max_pages = int(policy.get("maxPages", target_pages))
    if pages < 1 or pages > max_pages:
        issues.append(f"PDF must contain between 1 and {max_pages} pages; found {pages}.")
    if info.get("Tagged", "").lower() != "yes":
        issues.append("PDF is not tagged.")
    if info.get("Metadata Stream", "").lower() != "yes":
        issues.append("PDF has no metadata stream.")
    if info.get("Creator") != "Writer":
        issues.append(f"PDF Creator must be Writer; found {info.get('Creator', '(missing)')}.")
    if not info.get("Producer", "").startswith("LibreOffice "):
        issues.append("PDF Producer must be LibreOffice.")
    if info.get("Author") != tailored["basics"]["name"]:
        issues.append("PDF Author does not match the CV owner.")
    if info.get("Title") != f"{tailored['basics']['name']} Resume":
        issues.append("PDF Title does not match the deterministic resume title.")
    if info.get("Subject") != f"{tailored['basics']['headline']} Resume":
        issues.append("PDF Subject does not match the deterministic resume subject.")
    page_size = str(policy.get("pageSize", "A4")).upper()
    expected = (595.3, 841.9) if page_size == "A4" else (612.0, 792.0)
    if abs(width - expected[0]) > 2 or abs(height - expected[1]) > 2:
        issues.append(
            f"PDF page is not {page_size} portrait: {width:.2f} x {height:.2f} pt."
        )

    configured_titles = {
        "summary": "SUMMARY",
        "experience": "EXPERIENCE",
        "certifications": "CERTIFICATIONS",
        "projects": "PROJECTS",
        "achievements": "ACHIEVEMENTS",
        "education": "EDUCATION",
        "technical-skills": "TECHNICAL SKILLS",
        "open-source": "OPEN SOURCE",
        "publications": "PUBLICATIONS",
    }
    expected_titles = (
        [
            configured_titles.get(section["sourceId"], str(section.get("title", section["sourceId"])).upper())
            for section in resume_config.get("sections", [])
        ]
        if resume_config
        else SECTION_TITLES
    )
    indices: list[int] = []
    for title in expected_titles:
        index = _title_index(texts, title)
        if index is None:
            issues.append(f"PDF reading order is missing section {title}.")
        else:
            indices.append(index)
    if len(indices) == len(expected_titles) and indices != sorted(indices):
        issues.append("PDF section reading order is incorrect.")

    contact_fields = (
        resume_config.get("header", {}).get("contactFields", [])
        if resume_config
        else ["phone", "email", "linkedin", "github", "website"]
    )
    contact_tokens = [
        tailored["basics"].get(field, "")
        for field in contact_fields
        if tailored["basics"].get(field, "")
    ]
    contact_line_count = sum(
        1 for text in texts if all(token in text for token in contact_tokens)
    )
    if contact_line_count != policy["requiredContactLines"]:
        issues.append(
            f"Contact row occupies {contact_line_count or 'multiple/zero'} lines; "
            f"expected {policy['requiredContactLines']}."
        )

    summary_line_count = 0
    summary_index = _title_index(texts, "SUMMARY")
    experience_index = _title_index(texts, "EXPERIENCE")
    if summary_index is not None and experience_index is not None:
        start = summary_index + 1
        end = experience_index
        summary_line_count = end - start
    summary_enabled = "summary" in policy.get("enabledSections", ["summary"])
    if summary_enabled and not 1 <= summary_line_count <= policy["maximumSummaryLines"]:
        issues.append(
            f"Summary occupies {summary_line_count} lines; maximum is {policy['maximumSummaryLines']}."
        )

    bullet_metrics: list[dict[str, Any]] = []
    bullets = [
        bullet
        for section in ("experience", "projects")
        for entry in tailored.get(section, [])
        for bullet in entry["bullets"]
    ]
    for index, bullet in enumerate(bullets, start=1):
        count = _line_count_for_text(lines, bullet["text"])
        bullet_metrics.append(
            {"index": index, "text": bullet["text"], "lineCount": count}
        )
        if count == 0 or count > policy["maximumBulletLines"]:
            issues.append(
                f"Bullet {index} occupies {count or 'unresolved'} lines; "
                f"maximum is {policy['maximumBulletLines']}: {bullet['text']}"
            )

    skill_rows: list[dict[str, Any]] = []
    for index, group in enumerate(tailored.get("technicalSkills", []), start=1):
        text = f"{group['category']}: {', '.join(group['items'])}"
        count = _line_count_for_text(lines, text)
        skill_rows.append({"index": index, "text": text, "lineCount": count})
        if count > policy["maximumSkillRowLines"] or count == 0:
            issues.append(f"Skill row {index} occupies {count or 'unresolved'} lines.")

    page_bottom_whitespace_mm = []
    for page_number in range(1, pages + 1):
        page_lines = [line for line in lines if line["page"] == page_number]
        whitespace = (
            (height - max(line["yMax"] for line in page_lines)) * 25.4 / 72
            if page_lines
            else height * 25.4 / 72
        )
        page_bottom_whitespace_mm.append(round(whitespace, 1))
    bottom_whitespace_mm = page_bottom_whitespace_mm[-1]
    maximum_intermediate_whitespace = policy.get(
        "maximumIntermediatePageWhitespaceMm", 25
    )
    for page_number, whitespace in enumerate(
        page_bottom_whitespace_mm[:-1], start=1
    ):
        if whitespace > maximum_intermediate_whitespace:
            issues.append(
                f"Page {page_number} ends with {whitespace:.1f}mm whitespace; "
                f"intermediate-page maximum is {maximum_intermediate_whitespace}mm."
            )
    if bottom_whitespace_mm < policy["minimumBottomWhitespaceMm"]:
        issues.append(
            f"Bottom whitespace is {bottom_whitespace_mm:.1f}mm; minimum is "
            f"{policy['minimumBottomWhitespaceMm']}mm."
        )
    source_limited = bool(tailored.get("sourceExhausted"))
    if bottom_whitespace_mm > policy["maximumBottomWhitespaceMm"] and not source_limited:
        issues.append(
            f"Bottom whitespace is {bottom_whitespace_mm:.1f}mm; maximum is "
            f"{policy['maximumBottomWhitespaceMm']}mm."
        )

    fonts_output = cache.run([cache.command("pdffonts"), str(pdf_path)])
    expected_font = theme["font"]["family"] if theme else "Gelasio"
    font_loaded = expected_font.replace(" ", "") in fonts_output.replace(" ", "")
    if not font_loaded:
        issues.append(f"Configured font {expected_font!r} is not embedded in the PDF.")

    metadata = cache.run([cache.command("pdfinfo"), "-meta", str(pdf_path)])
    pdf_ua = "pdfuaid:part" in metadata.lower()
    if not pdf_ua:
        issues.append("PDF/UA metadata is missing.")

    structure = cache.run([cache.command("pdfinfo"), "-struct-text", str(pdf_path)])
    if "Document" not in structure or "H1 (block)" not in structure:
        issues.append("PDF structure tree is missing semantic document headings.")

    url_output = cache.run([cache.command("pdfinfo"), "-url", str(pdf_path)])
    expected_urls = {
        *(
            [f"mailto:{tailored['basics']['email']}"]
            if tailored["basics"].get("email") and "email" in contact_fields
            else []
        ),
        *{
            value if "://" in value else f"https://{value}"
            for field in ("linkedin", "github", "website")
            for value in [tailored["basics"].get(field, "")]
            if value and field in contact_fields
        },
        *{
            achievement["url"]
            for achievement in tailored.get("achievements", [])
            if achievement.get("url")
        },
    }
    missing_urls = {url for url in expected_urls if url not in url_output}
    if missing_urls:
        issues.append("PDF is missing hyperlinks: " + ", ".join(sorted(missing_urls)))

    return {
        "schemaVersion": 4 if resume_config else 3,
        "ok": not issues,
        "pdfSha256": hashlib.sha256(pdf_path.read_bytes()).hexdigest(),
        "sourceJsonSha256": source_json_sha256,
        "sourceCvSha256": tailored["sourceCvSha256"],
        "pageCount": pages,
        "targetPages": target_pages,
        "maxPages": max_pages,
        "targetStatus": (
            "source-limited"
            if source_limited and (pages < target_pages or bottom_whitespace_mm > policy["maximumBottomWhitespaceMm"])
            else ("met" if pages == target_pages else "under-target")
        ),
        "pageWidthPt": round(width, 3),
        "pageHeightPt": round(height, 3),
        "tagged": info.get("Tagged", "").lower() == "yes",
        "pdfUa": pdf_ua,
        "creator": info.get("Creator"),
        "producer": info.get("Producer"),
        "author": info.get("Author"),
        "title": info.get("Title"),
        "subject": info.get("Subject"),
        "toolVersions": {
            "python": sys.version.split()[0],
            "poppler": cache.version("pdfinfo"),
            "libreoffice": info.get("Producer"),
        },
        "metadataStream": info.get("Metadata Stream", "").lower() == "yes",
        "contactLineCount": contact_line_count,
        "summaryLineCount": summary_line_count,
        "bottomWhitespaceMm": round(bottom_whitespace_mm, 1),
        "pageBottomWhitespaceMm": page_bottom_whitespace_mm,
        "pageUsedHeightPercent": [
            round(
                100
                * max((line["yMax"] for line in lines if line["page"] == page), default=0)
                / height,
                1,
            )
            for page in range(1, pages + 1)
        ],
        "fontLoaded": font_loaded,
        "hyperlinksValid": not missing_urls,
        "bullets": bullet_metrics,
        "skillRows": skill_rows,
        "issues": issues,
        "suggestions": (
            ["Add more eligible source-backed content to approach the configured page target."]
            if pages < target_pages and not source_limited
            else []
        ),
    }


def write_report(path: Path, report: dict[str, Any]) -> None:
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf8")
