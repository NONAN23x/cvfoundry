from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from generate_fit_summary import build_summary  # noqa: E402
from cv_source import load_cv  # noqa: E402


class FitSummaryRegressionTests(unittest.TestCase):
    def test_role_family_project_rankings(self):
        fixtures = ROOT / "tests" / "fixtures"
        master = load_cv(ROOT / "profiles" / "john-doe" / "CV.md")
        import json
        expectations = json.loads(
            (fixtures / "project-ranking-expectations.json").read_text(encoding="utf8")
        )

        for fixture_name, expected_ids in expectations.items():
            with self.subTest(fixture=fixture_name):
                job_description = (fixtures / fixture_name).read_text(encoding="utf8")
                summary = build_summary(job_description, master)
                self.assertEqual(summary["recommendedProjectIds"], expected_ids)

    def test_recommends_two_projects_even_for_low_overlap_roles(self):
        master = load_cv(ROOT / "profiles" / "john-doe" / "CV.md")
        summary = build_summary("Seeking a governance specialist for policy workshops.", master)
        self.assertEqual(len(summary["recommendedProjectIds"]), 2)

    def test_filters_noisy_boilerplate_terms_from_top_job_terms(self):
        master = load_cv(ROOT / "profiles" / "john-doe" / "CV.md")
        job_description = """
        Responsibilities
        * Perform source code scanning and website vulnerability scanning.
        * Produce technical documentation and monitoring updates.

        Why join us
        We provide day to day group updates and information for all employees.
        """
        summary = build_summary(job_description, master)
        self.assertIn("source code scanning", summary["topJobTerms"])
        self.assertIn("website vulnerability scanning", summary["topJobTerms"])
        for noisy in ("day", "group", "information", "all"):
            self.assertNotIn(noisy, summary["topJobTerms"])

    def test_monitoring_roles_prefer_log_analyzer(self):
        master = load_cv(ROOT / "profiles" / "john-doe" / "CV.md")
        job_description = """
        Responsibilities
        * Build structured logging and tracing workflows for service observability.
        * Improve production monitoring and incident investigation.
        """
        summary = build_summary(job_description, master)
        self.assertEqual(summary["recommendedProjectIds"][0], "project-log-analyzer")


if __name__ == "__main__":
    unittest.main()
