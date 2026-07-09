#!/usr/bin/env python3

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import zipfile
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from artifact_names import final_pdf_filename
from cv_source import CVParseError, load_cv
from assemble_resume import assemble_tailored_resume
from pdf_inspection import inspect_pdf
from payload_v3 import to_legacy_payload
from profile_assembly import assemble_profile_resume
from profile_config import canonical_sections
from resume_validation import validate_tailored_resume


ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "config" / "resume-policy.json"
DEFAULT_CV_PATH = ROOT / "profiles" / "john-doe" / "CV.md"
SECTION_ORDER = [
    "summary",
    "experience",
    "certifications",
    "projects",
    "achievements",
    "education",
    "technical-skills",
]
REQUIRED_FILES = [
    "job-description.md",
    "fit-summary.json",
    "fit-summary.md",
    "tailoring-payload.json",
    "tailored-resume.json",
    "tailored-resume.html",
    "tailored-resume.odt",
    "layout-validation.json",
    "rerun.py",
    "tailoring-notes.md",
]
PLACEHOLDER_RE = re.compile(r"TODO|FIXME|\{\{.*?\}\}|lorem ipsum", re.IGNORECASE)
WORD_RE = re.compile(r"\b[\w.+#/-]+\b")


class ResumeHtmlParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.sections: list[str] = []
        self.links: list[tuple[str, str]] = []
        self.bullets: list[str] = []
        self._anchor: list[str] | None = None
        self._href = ""
        self._bullet: list[str] | None = None

    def handle_starttag(self, tag: str, attrs) -> None:
        attributes = dict(attrs)
        if tag == "section" and attributes.get("data-resume-section"):
            self.sections.append(attributes["data-resume-section"])
        elif tag == "a":
            self._anchor = []
            self._href = attributes.get("href", "")
        elif tag == "li":
            self._bullet = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._anchor is not None:
            self.links.append((" ".join(self._anchor).strip(), self._href))
            self._anchor = None
            self._href = ""
        elif tag == "li" and self._bullet is not None:
            self.bullets.append(" ".join(self._bullet).strip())
            self._bullet = None

    def handle_data(self, data: str) -> None:
        if self._anchor is not None:
            self._anchor.append(data)
        if self._bullet is not None:
            self._bullet.append(data)


def _load_json(path: Path, issues: list[str]) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf8"))
    except (OSError, json.JSONDecodeError) as error:
        issues.append(f"Unable to read valid JSON from {path.name}: {error}")
        return None
    if not isinstance(value, dict):
        issues.append(f"{path.name} must contain a JSON object.")
        return None
    return value


def _validate_links(links: list[tuple[str, str]]) -> list[str]:
    issues: list[str] = []
    for label, href in links:
        parsed = urlparse(href)
        if parsed.scheme == "mailto":
            if "@" not in parsed.path:
                issues.append(f"Invalid email link: {href}")
        elif parsed.scheme not in {"http", "https"} or not parsed.netloc:
            issues.append(f"Invalid web link: {label!r} -> {href!r}")
    return issues


def _validate_odt(path: Path) -> list[str]:
    issues: list[str] = []
    try:
        with zipfile.ZipFile(path) as archive:
            names = set(archive.namelist())
            if "content.xml" not in names or "styles.xml" not in names:
                issues.append("tailored-resume.odt is missing required OpenDocument content.")
            if archive.read("mimetype") != b"application/vnd.oasis.opendocument.text":
                issues.append("tailored-resume.odt has an invalid mimetype.")
    except (OSError, KeyError, zipfile.BadZipFile) as error:
        issues.append(f"tailored-resume.odt is invalid: {error}")
    return issues


def analyze_output_dir(
    output_dir: Path,
    max_bullet_words: int = 28,
    max_pages: int = 1,
    cv_path: Path | None = None,
    reinspect_pdf: bool = False,
    policy: dict[str, Any] | None = None,
    theme: dict[str, Any] | None = None,
    resume_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    issues: list[str] = []
    policy = policy or json.loads(POLICY_PATH.read_text(encoding="utf8"))
    required_files = list(REQUIRED_FILES)
    if policy.get("sectionsById"):
        required_files.extend(("effective-policy.json", "decision-report.json"))
    for required_file in required_files:
        if not (output_dir / required_file).exists():
            issues.append(f"Missing required file: {required_file}")
    generator = output_dir / "rerun.py"
    if generator.exists() and not os.access(generator, os.X_OK):
        issues.append("rerun.py is not executable.")

    canonical_cv_path = cv_path or DEFAULT_CV_PATH
    try:
        cv = load_cv(canonical_cv_path)
    except (OSError, CVParseError) as error:
        issues.append(f"Unable to load canonical CV.md: {error}")
        cv = None

    tailored_path = output_dir / "tailored-resume.json"
    tailored = _load_json(tailored_path, issues) if tailored_path.exists() else None
    pdf_filename = ""
    if tailored is not None:
        try:
            pdf_filename = final_pdf_filename(tailored)
        except ValueError as error:
            issues.append(str(error))
    pdf_path = output_dir / pdf_filename if pdf_filename else None
    if pdf_path is not None and not pdf_path.exists():
        issues.append(f"Missing required file: {pdf_filename}")
    payload_path = output_dir / "tailoring-payload.json"
    payload = _load_json(payload_path, issues) if payload_path.exists() else None
    effective_policy_path = output_dir / "effective-policy.json"
    effective_policy = (
        _load_json(effective_policy_path, issues)
        if effective_policy_path.exists()
        else None
    )
    if policy.get("sectionsById") and effective_policy is not None and effective_policy != policy:
        issues.append("effective-policy.json is stale for the active profile configuration.")
    if tailored is not None and cv is not None:
        issues.extend(validate_tailored_resume(tailored, cv, policy))
    if payload is not None and tailored is not None and cv is not None:
        try:
            if payload.get("schemaVersion") == 3 and policy.get("sectionsById"):
                assembled = assemble_profile_resume(
                    payload,
                    cv,
                    policy,
                    {item["id"]: item for item in canonical_sections(cv)},
                )
            else:
                assembled = assemble_tailored_resume(to_legacy_payload(payload), cv, policy)
            comparable_tailored = {key: tailored.get(key) for key in assembled}
            if assembled.get("schemaVersion") == 2 and comparable_tailored.get("schemaVersion") == 3:
                comparable_tailored["schemaVersion"] = 2
            if assembled != comparable_tailored:
                issues.append(
                    "tailored-resume.json does not match the deterministic expansion "
                    "of tailoring-payload.json."
                )
        except ValueError as error:
            issues.append(str(error))

    html_path = output_dir / "tailored-resume.html"
    html_text = ""
    bullet_count = 0
    if html_path.exists():
        html_text = html_path.read_text(encoding="utf8")
        if PLACEHOLDER_RE.search(html_text):
            issues.append("Found placeholder content in tailored-resume.html.")
        if re.search(r"https?://fonts\.(?:googleapis|gstatic)\.com", html_text):
            issues.append("Found a remote font dependency in tailored-resume.html.")
        parser = ResumeHtmlParser()
        parser.feed(html_text)
        expected_section_order = (
            [item["sourceId"] for item in resume_config.get("sections", [])]
            if resume_config
            else SECTION_ORDER
        )
        if parser.sections != expected_section_order:
            issues.append(
                "Section structure mismatch: expected "
                + ", ".join(expected_section_order)
                + "; found "
                + ", ".join(parser.sections)
            )
        issues.extend(_validate_links(parser.links))
        bullet_count = len(parser.bullets)
        for bullet in parser.bullets:
            words = len(WORD_RE.findall(bullet))
            if words > max_bullet_words:
                issues.append(
                    f"Bullet exceeds {max_bullet_words} words ({words}): {bullet}"
                )

    odt_path = output_dir / "tailored-resume.odt"
    if odt_path.exists():
        issues.extend(_validate_odt(odt_path))

    report_path = output_dir / "layout-validation.json"
    report = _load_json(report_path, issues) if report_path.exists() else None
    source_json_sha256 = (
        hashlib.sha256(tailored_path.read_bytes()).hexdigest()
        if tailored_path.exists()
        else ""
    )
    if report is not None:
        expected_report_schema = 4 if report.get("sourceResumeConfigSha256") else 3
        if report.get("schemaVersion") != expected_report_schema:
            issues.append(
                f"layout-validation.json must use schemaVersion {expected_report_schema}."
            )
        if report.get("sourceJsonSha256") != source_json_sha256:
            issues.append("layout-validation.json is stale for tailored-resume.json.")
        if tailored and report.get("sourceCvSha256") != tailored.get("sourceCvSha256"):
            issues.append("layout-validation.json source CV hash is stale.")
        if report.get("pdfFileName") != pdf_filename:
            issues.append("layout-validation.json has a stale PDF filename.")
        if pdf_path is not None and pdf_path.exists():
            pdf_sha256 = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
            if report.get("pdfSha256") != pdf_sha256:
                issues.append(f"layout-validation.json is stale for {pdf_filename}.")
        if html_path.exists() and report.get("htmlSha256") != hashlib.sha256(
            html_path.read_bytes()
        ).hexdigest():
            issues.append("layout-validation.json is stale for tailored-resume.html.")
        if odt_path.exists() and report.get("odtSha256") != hashlib.sha256(
            odt_path.read_bytes()
        ).hexdigest():
            issues.append("layout-validation.json is stale for tailored-resume.odt.")
        if not isinstance(report.get("toolVersions"), dict):
            issues.append("layout-validation.json is missing tool versions.")
        if report.get("ok") is not True:
            issues.append("Final PDF layout validation did not pass.")
        if report.get("pageCount", 0) > max_pages:
            issues.append(
                f"PDF exceeds {max_pages} page(s): {report.get('pageCount')} pages found."
            )
        summary_lines = report.get("summaryLineCount", 0)
        summary_enabled = "summary" in policy.get("enabledSections", ["summary"])
        if summary_enabled and (
            not isinstance(summary_lines, int)
            or not 1 <= summary_lines <= policy["maximumSummaryLines"]
        ):
            issues.append(
                f"Summary occupies {summary_lines} lines; maximum is "
                f"{policy['maximumSummaryLines']}."
            )
        if report.get("tagged") is not True:
            issues.append("Final PDF is not tagged.")
        if report.get("pdfUa") is not True:
            issues.append("Final PDF is not PDF/UA.")
        if report.get("creator") != "Writer":
            issues.append("Final PDF Creator is not Writer.")
        if not str(report.get("producer", "")).startswith("LibreOffice "):
            issues.append("Final PDF Producer is not LibreOffice.")
        if tailored is not None and report.get("title") != f"{tailored['basics']['name']} Resume":
            issues.append("Final PDF Title is not deterministic.")
        if tailored is not None and report.get("subject") != f"{tailored['basics']['headline']} Resume":
            issues.append("Final PDF Subject is not deterministic.")
        if report.get("fontLoaded") is not True:
            expected_font = theme.get("font", {}).get("family", "configured font")
            issues.append(f"Final PDF does not embed {expected_font}.")
        if report.get("hyperlinksValid") is not True:
            issues.append("Final PDF hyperlinks are incomplete.")
        issues.extend(
            f"PDF validation: {issue}"
            for issue in report.get("issues", [])
            if isinstance(issue, str)
        )

    if (
        reinspect_pdf
        and pdf_path is not None
        and pdf_path.exists()
        and tailored is not None
        and tailored.get("schemaVersion") in (2, 3)
        and tailored.get("sourceCvSha256")
        and source_json_sha256
    ):
        try:
            fresh = inspect_pdf(
                pdf_path,
                tailored,
                policy,
                source_json_sha256,
                theme=theme,
                resume_config=resume_config
                or (
                    {"document": tailored.get("document", {})}
                    if tailored.get("schemaVersion") == 3
                    else None
                ),
            )
            issues.extend(f"PDF inspection: {issue}" for issue in fresh["issues"])
            if report is not None:
                for field in (
                    "pdfSha256",
                    "pageCount",
                    "pageWidthPt",
                    "pageHeightPt",
                    "tagged",
                    "pdfUa",
                    "creator",
                    "producer",
                    "title",
                    "subject",
                    "summaryLineCount",
                    "bottomWhitespaceMm",
                    "fontLoaded",
                    "hyperlinksValid",
                ):
                    if report.get(field) != fresh.get(field):
                        issues.append(f"layout-validation.json has stale field {field}.")
        except RuntimeError as error:
            issues.append(str(error))

    return {
        "ok": not issues,
        "outputDir": str(output_dir),
        "maxBulletWords": max_bullet_words,
        "maxPages": max_pages,
        "bulletCount": bullet_count,
        "pageCount": report.get("pageCount") if report else None,
        "issues": issues,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate a complete tailored resume run.")
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--max-bullet-words", type=int, default=28)
    parser.add_argument("--max-pages", type=int, default=1)
    parser.add_argument("--cv", type=Path, default=DEFAULT_CV_PATH)
    parser.add_argument("--reinspect-pdf", action="store_true")
    parser.add_argument("--no-reinspect-pdf", action="store_true", help=argparse.SUPPRESS)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    summary = analyze_output_dir(
        args.output_dir.resolve(),
        max_bullet_words=args.max_bullet_words,
        max_pages=args.max_pages,
        cv_path=args.cv.resolve(),
        reinspect_pdf=args.reinspect_pdf and not args.no_reinspect_pdf,
    )
    print(json.dumps(summary, separators=(",", ":")))
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
