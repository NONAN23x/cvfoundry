from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from assemble_resume import assemble_tailored_resume  # noqa: E402
from cv_source import load_cv  # noqa: E402


def payload_from_cv(cv: dict) -> dict:
    return {
        "jobTitle": "Rust Software Developer",
        "summary": cv["summary"],
        "summarySourceIds": [cv["summarySourceId"]],
        "experience": [
            {
                "sourceId": entry["id"],
                "bullets": [
                    {"sourceId": bullet["id"], "text": bullet["text"]}
                    for bullet in entry["bullets"]
                ],
            }
            for entry in cv["experience"]
        ],
        "projects": [
            {
                "sourceId": entry["id"],
                "bullets": [
                    {"sourceId": bullet["id"], "text": bullet["text"]}
                    for bullet in entry["bullets"]
                ],
            }
            for entry in cv["projects"][:2]
        ],
        "skillPriorities": [
            {"sourceId": group["id"], "priorityItems": [group["items"][0]]}
            for group in cv["technicalSkills"]
        ],
    }


class AssembleResumeTests(unittest.TestCase):
    def setUp(self):
        self.cv = load_cv(ROOT / "profiles" / "john-doe" / "CV.md")
        self.policy = json.loads(
            (ROOT / "config" / "resume-policy.json").read_text(encoding="utf8")
        )
        self.payload = payload_from_cv(self.cv)

    def test_injects_locked_sections_from_cv(self):
        tailored = assemble_tailored_resume(self.payload, self.cv, self.policy)
        self.assertEqual(tailored["basics"]["name"], self.cv["basics"]["name"])
        self.assertEqual(tailored["certifications"][0]["name"], self.cv["certifications"][0]["name"])
        self.assertEqual(tailored["achievements"][0]["text"], self.cv["achievements"][0]["text"])
        self.assertEqual(tailored["achievements"][0]["url"], self.cv["achievements"][0]["url"])
        self.assertEqual(tailored["education"]["degree"], self.cv["education"]["degree"])
        self.assertEqual(tailored["experience"][0]["company"], self.cv["experience"][0]["company"])
        self.assertEqual(tailored["projects"][0]["stack"], self.cv["projects"][0]["stack"])

    def test_rejects_locked_top_level_fields(self):
        self.payload["basics"] = {"name": "Someone Else"}
        with self.assertRaisesRegex(ValueError, "locked or unsupported fields: basics"):
            assemble_tailored_resume(self.payload, self.cv, self.policy)

    def test_rejects_cross_category_skill_items(self):
        self.payload["skillPriorities"][0]["priorityItems"] = ["Kubernetes"]
        with self.assertRaisesRegex(ValueError, "contains unsupported items: Kubernetes"):
            assemble_tailored_resume(self.payload, self.cv, self.policy)

    def test_requires_each_skill_category_once(self):
        self.payload["skillPriorities"][-1] = self.payload["skillPriorities"][0]
        with self.assertRaisesRegex(ValueError, "repeats a technical skill category"):
            assemble_tailored_resume(self.payload, self.cv, self.policy)

    def test_skill_priorities_preserve_baseline(self):
        programming = self.payload["skillPriorities"][0]
        programming["priorityItems"] = ["TypeScript", "C"]
        tailored = assemble_tailored_resume(self.payload, self.cv, self.policy)
        items = tailored["technicalSkills"][0]["items"]
        self.assertEqual(items, ["TypeScript", "C", "Rust", "Python"])

    def test_skill_priorities_limit_replacements(self):
        programming = self.payload["skillPriorities"][0]
        programming["priorityItems"] = ["TypeScript", "C", "Bash"]
        tailored = assemble_tailored_resume(self.payload, self.cv, self.policy)
        items = tailored["technicalSkills"][0]["items"]
        self.assertEqual(items, ["TypeScript", "C", "Bash", "Rust"])

    def test_normalizes_composite_headline_to_single_jd_aligned_role(self):
        self.payload["jobTitle"] = "Rust Developer & Backend Engineer"
        with self.assertRaisesRegex(ValueError, "exactly one prominent role title"):
            assemble_tailored_resume(self.payload, self.cv, self.policy)

    def test_uses_explicit_job_title_directly(self):
        self.payload["jobTitle"] = "Backend Rust Developer"
        tailored = assemble_tailored_resume(self.payload, self.cv, self.policy)
        self.assertEqual(tailored["basics"]["headline"], "Backend Rust Developer")

    def test_supports_legacy_headline_field(self):
        self.payload.pop("jobTitle")
        self.payload["headline"] = "Rust Software Developer"
        tailored = assemble_tailored_resume(self.payload, self.cv, self.policy)
        self.assertEqual(tailored["basics"]["headline"], "Rust Software Developer")

    def test_aligns_summary_opening_with_explicit_job_title(self):
        self.payload["jobTitle"] = "Systems Developer"
        self.payload["summary"] = (
            "Rust Software Developer focused on backend services and systems programming."
        )
        tailored = assemble_tailored_resume(self.payload, self.cv, self.policy)
        self.assertTrue(tailored["summary"].startswith("Systems Developer focused"))

    def test_experience_is_assembled_in_canonical_cv_order(self):
        self.payload["experience"] = list(reversed(self.payload["experience"]))
        tailored = assemble_tailored_resume(self.payload, self.cv, self.policy)
        self.assertEqual(
            [entry["sourceId"] for entry in tailored["experience"]],
            [entry["id"] for entry in self.cv["experience"]],
        )


if __name__ == "__main__":
    unittest.main()
