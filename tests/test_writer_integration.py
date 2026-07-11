from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

from artifact_names import final_pdf_filename  # noqa: E402
from cv_source import load_cv  # noqa: E402
from generate_resume import generate  # noqa: E402
from payload_v3 import from_legacy_payload  # noqa: E402
from profile_assembly import assemble_profile_resume  # noqa: E402
from profile_config import load_profile, resolve_effective_policy  # noqa: E402
from test_assemble_resume import payload_from_cv  # noqa: E402
from test_check_resume_quality import tailored_resume  # noqa: E402


@unittest.skipUnless(
    os.environ.get("RUN_LIBREOFFICE_INTEGRATION") == "1"
    and shutil.which("libreoffice"),
    "set RUN_LIBREOFFICE_INTEGRATION=1 to run LibreOffice integration",
)
class WriterIntegrationTests(unittest.TestCase):
    def test_generates_tagged_pdfua_a4_resume(self):
        cv_path = ROOT / "profiles" / "john-doe" / "CV.md"
        cv = load_cv(cv_path)
        with tempfile.TemporaryDirectory(prefix="resume path with spaces ") as name:
            output = Path(name)
            json_path = output / "tailored-resume.json"
            json_path.write_text(
                json.dumps(tailored_resume(cv), indent=2) + "\n",
                encoding="utf8",
            )
            report = generate(json_path, output, cv_path)
            self.assertTrue(report["ok"], report["issues"])
            self.assertTrue(report["tagged"])
            self.assertTrue(report["pdfUa"])
            self.assertEqual(report["creator"], "Writer")
            self.assertTrue(report["producer"].startswith("LibreOffice "))
            self.assertAlmostEqual(report["pageWidthPt"], 595.3, places=0)
            self.assertAlmostEqual(report["pageHeightPt"], 841.9, places=0)
            self.assertTrue((output / "tailored-resume.odt").exists())
            self.assertTrue(
                (output / final_pdf_filename(tailored_resume(cv))).exists()
            )
            bbox = subprocess.run(
                [
                    "pdftotext",
                    "-bbox-layout",
                    str(output / final_pdf_filename(tailored_resume(cv))),
                    "-",
                ],
                capture_output=True,
                text=True,
                check=True,
            ).stdout
            title_x = min(
                float(value)
                for value in re.findall(
                    r'<word xMin="([0-9.]+)"[^>]*>Rust</word>', bbox
                )
            )
            bullet_x = min(
                float(value)
                for value in re.findall(
                    r'<word xMin="([0-9.]+)"[^>]*>•</word>', bbox
                )
            )
            self.assertGreaterEqual(bullet_x - title_x, 5.0)
            self.assertLessEqual(bullet_x - title_x, 10.0)

    def test_projects_flow_naturally_across_two_pages(self):
        profile = load_profile(ROOT / "profiles" / "john-doe")
        profile["config"]["document"].update({"targetPages": 2, "maxPages": 2})
        policy = resolve_effective_policy(profile)
        payload = from_legacy_payload(payload_from_cv(profile["cv"]))
        projects = next(
            section for section in payload["sections"] if section["sourceId"] == "projects"
        )
        projects["items"] = [
            {
                "sourceId": project["id"],
                "bullets": [
                    {"sourceId": bullet["id"], "text": bullet["text"]}
                    for bullet in project["bullets"]
                ],
            }
            for project in profile["cv"]["projects"]
        ]
        tailored = assemble_profile_resume(
            payload, profile["cv"], policy, profile["sections"]
        )
        tailored.update(
            {
                "sourceResumeConfigSha256": profile["hashes"]["resumeConfig"],
                "sourceThemeSha256": profile["hashes"]["theme"],
                "document": profile["config"]["document"],
            }
        )
        with tempfile.TemporaryDirectory(prefix="two page resume ") as name:
            output = Path(name)
            json_path = output / "tailored-resume.json"
            json_path.write_text(json.dumps(tailored, indent=2) + "\n", encoding="utf8")
            report = generate(
                json_path,
                output,
                profile["cvPath"],
                policy=policy,
                theme=profile["theme"],
                resume_config=profile["config"],
            )
            self.assertTrue(report["ok"], report["issues"])
            self.assertEqual(report["pageCount"], 2)
            self.assertLessEqual(
                report["pageBottomWhitespaceMm"][0],
                policy["maximumIntermediatePageWhitespaceMm"],
            )
            pdf_path = output / final_pdf_filename(tailored)
            page_texts = []
            for page in (1, 2):
                completed = subprocess.run(
                    ["pdftotext", "-f", str(page), "-l", str(page), str(pdf_path), "-"],
                    capture_output=True,
                    text=True,
                    check=True,
                )
                page_texts.append(completed.stdout)
            self.assertIn("PROJECTS", page_texts[0])
            self.assertTrue(page_texts[1].strip(), "expected content on the second page")
            self.assertTrue(any("Key-Value Store" in text for text in page_texts))


if __name__ == "__main__":
    unittest.main()
