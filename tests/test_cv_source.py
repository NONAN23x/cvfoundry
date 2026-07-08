from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from cv_source import CVParseError, load_cv, parse_cv_text  # noqa: E402


class CVSourceTests(unittest.TestCase):
    def setUp(self):
        self.path = ROOT / "profiles" / "john-doe" / "CV.md"
        self.text = self.path.read_text(encoding="utf8")

    def test_canonical_cv_parses(self):
        cv = load_cv(self.path)
        self.assertEqual(cv["schemaVersion"], 2)
        self.assertEqual(len(cv["experience"]), 3)
        self.assertEqual(len(cv["projects"]), 6)
        self.assertEqual(cv["technicalSkills"][1]["items"][3], "Clap")

    def test_duplicate_id_reports_both_lines(self):
        changed = self.text.replace(
            '"id":"cert-cloud-developer"', '"id":"cert-rust-foundations"', 1
        )
        with self.assertRaises(CVParseError) as raised:
            parse_cv_text(changed)
        self.assertIn("duplicate id 'cert-rust-foundations'", str(raised.exception))
        self.assertIn("first declared on line", str(raised.exception))

    def test_malformed_metadata_reports_line(self):
        changed = self.text.replace(
            '<!-- cv: {"id":"cert-cloud-developer"} -->',
            '<!-- cv: {"id":"cert-cloud-developer",} -->',
        )
        with self.assertRaises(CVParseError) as raised:
            parse_cv_text(changed)
        self.assertIn("invalid cv metadata JSON", str(raised.exception))

    def test_missing_metadata_is_rejected(self):
        changed = self.text.replace('<!-- cv: {"id":"cert-linux"} -->\n', "")
        with self.assertRaises(CVParseError) as raised:
            parse_cv_text(changed)
        self.assertIn("missing preceding", str(raised.exception))

    def test_unsafe_project_url_is_rejected(self):
        changed = self.text.replace(
            "https://example.com/john-doe/async-api",
            "javascript:alert(1)",
        )
        with self.assertRaises(CVParseError) as raised:
            parse_cv_text(changed)
        self.assertIn("absolute HTTP(S) URL", str(raised.exception))

    def test_achievement_urls_are_parsed(self):
        cv = load_cv(self.path)
        self.assertEqual(
            cv["achievements"][0]["url"],
            "https://example.com/john-doe/contributions",
        )

    def test_unsafe_achievement_url_is_rejected(self):
        changed = self.text.replace(
            "https://example.com/john-doe/contributions",
            "javascript:alert(1)",
        )
        with self.assertRaises(CVParseError) as raised:
            parse_cv_text(changed)
        self.assertIn("bullet url must be an absolute HTTP(S) URL", str(raised.exception))

    def test_section_order_is_strict(self):
        changed = self.text.replace("## Summary", "## Wrong Summary", 1)
        with self.assertRaises(CVParseError) as raised:
            parse_cv_text(changed)
        self.assertIn("expected sections in order", str(raised.exception))

    def test_headline_is_optional_in_header(self):
        changed = self.text.replace("Headline: Rust Software Developer\n", "", 1)
        cv = parse_cv_text(changed)
        self.assertEqual(cv["basics"]["headline"], "")


if __name__ == "__main__":
    unittest.main()
