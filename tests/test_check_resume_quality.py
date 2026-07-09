from __future__ import annotations

import hashlib
import json
import stat
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from artifact_names import final_pdf_filename  # noqa: E402
from check_resume_quality import analyze_output_dir  # noqa: E402
from cv_source import load_cv  # noqa: E402


def tailored_resume(cv: dict, metric: str = "60%") -> dict:
    headline = cv["basics"].get("headline") or "Rust Software Developer"
    experience = []
    for entry_index, entry in enumerate(cv["experience"]):
        bullets = []
        for bullet_index, bullet in enumerate(entry["bullets"]):
            text = bullet["text"]
            if entry_index == 1 and bullet_index == 3:
                text = text.replace("60%", metric)
            bullets.append({"sourceId": bullet["id"], "text": text})
        experience.append(
            {
                "sourceId": entry["id"],
                "role": entry["role"],
                "company": entry["company"],
                "dates": entry["dates"],
                "bullets": bullets,
            }
        )
    return {
        "schemaVersion": 2,
        "sourceCvSha256": cv["sourceCvSha256"],
        "summarySourceIds": [cv["summarySourceId"]],
        "basics": {**cv["basics"], "headline": headline},
        "summary": cv["summary"],
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
        "projects": [
            {
                "sourceId": item["id"],
                "name": item["name"],
                "stack": item["stack"],
                "bullets": [
                    {"sourceId": bullet["id"], "text": bullet["text"]}
                    for bullet in item["bullets"]
                ],
            }
            for item in cv["projects"][:2]
        ],
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
                key: cv["education"][key]
                for key in ("institution", "location", "degree", "dates", "gpa")
            },
        },
        "technicalSkills": [
            {
                "sourceId": item["id"],
                "category": item["category"],
                "items": list(item["items"]),
            }
            for item in cv["technicalSkills"]
        ],
    }


def html_document(data: dict) -> str:
    sections = "\n".join(
        f'<section data-resume-section="{name}">{name}</section>'
        for name in (
            "summary",
            "experience",
            "certifications",
            "projects",
            "achievements",
            "education",
            "technical-skills",
        )
    )
    bullets = "\n".join(
        f"<li>{bullet['text']}</li>"
        for section in ("experience", "projects")
        for entry in data[section]
        for bullet in entry["bullets"]
    )
    return (
        "<!doctype html><html><body>"
        '<a href="mailto:john.doe@example.com">john.doe@example.com</a>'
        '<a href="https://example.com/john-doe">example.com/john-doe</a>'
        f"{sections}<ul>{bullets}</ul></body></html>"
    )


def tailoring_payload(data: dict) -> dict:
    return {
        "jobTitle": data["basics"]["headline"],
        "summary": data["summary"],
        "summarySourceIds": data["summarySourceIds"],
        "experience": [
            {
                "sourceId": entry["sourceId"],
                "bullets": entry["bullets"],
            }
            for entry in data["experience"]
        ],
        "projects": [
            {
                "sourceId": entry["sourceId"],
                "bullets": entry["bullets"],
            }
            for entry in data["projects"]
        ],
        "technicalSkills": [
            {
                "sourceId": group["sourceId"],
                "items": group["items"],
            }
            for group in data["technicalSkills"]
        ],
    }


class ResumeQualityTests(unittest.TestCase):
    def setUp(self):
        self.cv_path = ROOT / "profiles" / "john-doe" / "CV.md"
        self.cv = load_cv(self.cv_path)

    def create_output(self, *, metric: str = "60%") -> Path:
        output = Path(tempfile.mkdtemp())
        data = tailored_resume(self.cv, metric)
        json_path = output / "tailored-resume.json"
        json_path.write_text(json.dumps(data), encoding="utf8")
        (output / "tailoring-payload.json").write_text(
            json.dumps(tailoring_payload(data)), encoding="utf8"
        )
        html = html_document(data)
        (output / "tailored-resume.html").write_text(html, encoding="utf8")
        for name, text in (
            ("job-description.md", "Role"),
            ("fit-summary.json", "{}"),
            ("fit-summary.md", "Fit"),
            ("tailoring-notes.md", "Notes"),
            ("rerun.py", "#!/usr/bin/env python3\n"),
        ):
            (output / name).write_text(text, encoding="utf8")
        (output / "rerun.py").chmod(
            (output / "rerun.py").stat().st_mode | stat.S_IXUSR
        )
        odt_path = output / "tailored-resume.odt"
        with zipfile.ZipFile(odt_path, "w") as archive:
            archive.writestr("mimetype", "application/vnd.oasis.opendocument.text")
            archive.writestr("content.xml", "<office/>")
            archive.writestr("styles.xml", "<office/>")
        pdf_bytes = b"%PDF-1.7 fake test artifact"
        pdf_filename = final_pdf_filename(data)
        (output / pdf_filename).write_bytes(pdf_bytes)
        report = {
            "schemaVersion": 3,
            "ok": True,
            "pdfSha256": hashlib.sha256(pdf_bytes).hexdigest(),
            "pdfFileName": pdf_filename,
            "htmlSha256": hashlib.sha256(html.encode("utf8")).hexdigest(),
            "odtSha256": hashlib.sha256(odt_path.read_bytes()).hexdigest(),
            "sourceJsonSha256": hashlib.sha256(json_path.read_bytes()).hexdigest(),
            "sourceCvSha256": self.cv["sourceCvSha256"],
            "pageCount": 1,
            "pageWidthPt": 595.304,
            "pageHeightPt": 841.89,
            "tagged": True,
            "pdfUa": True,
            "creator": "Writer",
            "producer": "LibreOffice test",
            "title": f"{data['basics']['name']} Resume",
            "subject": f"{data['basics']['headline']} Resume",
            "summaryLineCount": 3,
            "bottomWhitespaceMm": 14.0,
            "fontLoaded": True,
            "hyperlinksValid": True,
            "toolVersions": {
                "python": "test",
                "poppler": "test",
                "libreoffice": "LibreOffice test",
            },
            "issues": [],
        }
        (output / "layout-validation.json").write_text(
            json.dumps(report), encoding="utf8"
        )
        return output

    def analyze(self, output: Path) -> dict:
        return analyze_output_dir(
            output, cv_path=self.cv_path, reinspect_pdf=False
        )

    def test_valid_output_passes(self):
        result = self.analyze(self.create_output())
        self.assertTrue(result["ok"], result["issues"])

    def test_surfaces_layout_warnings_without_failing(self):
        output = self.create_output()
        report_path = output / "layout-validation.json"
        report = json.loads(report_path.read_text())
        report["warnings"] = ["Bottom whitespace is 22.2mm, accepted because the resume is source-limited."]
        report_path.write_text(json.dumps(report))
        result = self.analyze(output)
        self.assertTrue(result["ok"], result["issues"])
        self.assertTrue(result["warnings"])

    def test_pdf_filename_uses_first_name_and_headline(self):
        data = tailored_resume(self.cv)
        data["basics"]["headline"] = "Network & Infrastructure Engineer"
        self.assertEqual(
            final_pdf_filename(data),
            "John-Network-Infrastructure-Engineer.pdf",
        )

    def test_rejects_stale_cv_hash(self):
        output = self.create_output()
        data_path = output / "tailored-resume.json"
        data = json.loads(data_path.read_text())
        data["sourceCvSha256"] = "0" * 64
        data_path.write_text(json.dumps(data))
        result = self.analyze(output)
        self.assertTrue(any("sourceCvSha256" in issue for issue in result["issues"]))

    def test_rejects_stale_pdf_report(self):
        output = self.create_output()
        data = json.loads((output / "tailored-resume.json").read_text())
        pdf_filename = final_pdf_filename(data)
        (output / pdf_filename).write_bytes(b"changed")
        result = self.analyze(output)
        self.assertTrue(any(f"stale for {pdf_filename}" in issue for issue in result["issues"]))

    def test_rejects_unsupported_numeric_fact(self):
        result = self.analyze(self.create_output(metric="99%"))
        self.assertTrue(any("unsupported numeric facts" in issue for issue in result["issues"]))

    def test_rejects_unsupported_factual_token(self):
        output = self.create_output()
        path = output / "tailored-resume.json"
        data = json.loads(path.read_text())
        data["experience"][0]["bullets"][0]["text"] += " Used AWS."
        path.write_text(json.dumps(data))
        result = self.analyze(output)
        self.assertTrue(any("unsupported factual tokens" in issue for issue in result["issues"]))

    def test_allows_safe_ui_alias_contraction(self):
        output = self.create_output()
        path = output / "tailored-resume.json"
        data = json.loads(path.read_text())
        data["experience"][0]["bullets"][3]["text"] = (
            "Owned full development lifecycle from research to UI through security validation."
        )
        path.write_text(json.dumps(data))
        result = self.analyze(output)
        self.assertFalse(any("unsupported factual tokens" in issue for issue in result["issues"]))

    def test_malformed_tailored_resume_reports_issues_without_crashing(self):
        output = self.create_output()
        path = output / "tailored-resume.json"
        data = json.loads(path.read_text())
        data["summary"] = {"text": "invalid"}
        data["experience"][0]["bullets"][0]["text"] = None
        data["technicalSkills"][0]["items"] = "python"
        path.write_text(json.dumps(data))
        result = self.analyze(output)
        self.assertFalse(result["ok"])
        self.assertTrue(any("Tailored summary must be non-empty." in issue for issue in result["issues"]))
        self.assertTrue(any("requires non-empty text" in issue for issue in result["issues"]))
        self.assertTrue(any("must provide a string array" in issue for issue in result["issues"]))

    def test_requires_summary_provenance(self):
        output = self.create_output()
        path = output / "tailored-resume.json"
        data = json.loads(path.read_text())
        data["summarySourceIds"] = []
        path.write_text(json.dumps(data))
        result = self.analyze(output)
        self.assertTrue(any("summarySourceIds" in issue for issue in result["issues"]))

    def test_requires_odt(self):
        output = self.create_output()
        (output / "tailored-resume.odt").unlink()
        result = self.analyze(output)
        self.assertIn("Missing required file: tailored-resume.odt", result["issues"])

    def test_rerun_helper_requires_tailoring_payload(self):
        output = self.create_output()
        (output / "tailoring-payload.json").unlink()
        result = self.analyze(output)
        self.assertIn("Missing required file: tailoring-payload.json", result["issues"])

    def test_rejects_invalid_odt(self):
        output = self.create_output()
        (output / "tailored-resume.odt").write_text("not a zip")
        result = self.analyze(output)
        self.assertTrue(any("odt is invalid" in issue for issue in result["issues"]))

    def test_rejects_failed_pdf_report(self):
        output = self.create_output()
        path = output / "layout-validation.json"
        report = json.loads(path.read_text())
        report["ok"] = False
        report["summaryLineCount"] = 4
        report["issues"] = ["Summary occupies 4 lines; maximum is 3."]
        path.write_text(json.dumps(report))
        result = self.analyze(output)
        self.assertTrue(any("Final PDF layout validation did not pass" in issue for issue in result["issues"]))
        self.assertTrue(any("Summary occupies 4 lines" in issue for issue in result["issues"]))

    def test_accepts_one_or_three_summary_lines(self):
        for line_count in (1, 3):
            with self.subTest(line_count=line_count):
                output = self.create_output()
                path = output / "layout-validation.json"
                report = json.loads(path.read_text())
                report["summaryLineCount"] = line_count
                path.write_text(json.dumps(report))
                result = self.analyze(output)
                self.assertTrue(result["ok"], result["issues"])

    def test_rejects_four_summary_lines_even_if_report_claims_success(self):
        output = self.create_output()
        path = output / "layout-validation.json"
        report = json.loads(path.read_text())
        report["summaryLineCount"] = 4
        path.write_text(json.dumps(report))
        result = self.analyze(output)
        self.assertTrue(any("Summary occupies 4 lines" in issue for issue in result["issues"]))

    def test_rejects_changed_employer(self):
        output = self.create_output()
        path = output / "tailored-resume.json"
        data = json.loads(path.read_text())
        data["experience"][0]["company"] = "Invented Company"
        path.write_text(json.dumps(data))
        result = self.analyze(output)
        self.assertTrue(any("changed canonical field 'company'" in issue for issue in result["issues"]))

    def test_rejects_remote_font(self):
        output = self.create_output()
        path = output / "tailored-resume.html"
        path.write_text(path.read_text() + '<link href="https://fonts.googleapis.com/x">')
        result = self.analyze(output)
        self.assertTrue(any("remote font dependency" in issue for issue in result["issues"]))

    def test_rejects_nondeterministic_pdf_metadata(self):
        output = self.create_output()
        path = output / "layout-validation.json"
        report = json.loads(path.read_text())
        report["title"] = "Someone Else Resume"
        report["subject"] = "Wrong Headline Resume"
        path.write_text(json.dumps(report))
        result = self.analyze(output)
        self.assertTrue(any("Final PDF Title is not deterministic." in issue for issue in result["issues"]))
        self.assertTrue(any("Final PDF Subject is not deterministic." in issue for issue in result["issues"]))

    def test_rejects_composite_headline(self):
        output = self.create_output()
        path = output / "tailored-resume.json"
        data = json.loads(path.read_text())
        data["basics"]["headline"] = "Rust Developer & Backend Engineer"
        path.write_text(json.dumps(data))
        result = self.analyze(output)
        self.assertTrue(any("exactly one prominent role title" in issue for issue in result["issues"]))

    def test_rejects_noncanonical_experience_order(self):
        output = self.create_output()
        path = output / "tailored-resume.json"
        data = json.loads(path.read_text())
        data["experience"] = list(reversed(data["experience"]))
        path.write_text(json.dumps(data))
        result = self.analyze(output)
        self.assertTrue(any("experience order must follow canonical CV chronology" in issue for issue in result["issues"]))


if __name__ == "__main__":
    unittest.main()
