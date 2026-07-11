from __future__ import annotations

import argparse
import json
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

from cv_source import parse_cv_text  # noqa: E402
from payload_v3 import from_legacy_payload, to_legacy_payload  # noqa: E402
from profile_assembly import assemble_profile_resume  # noqa: E402
from profile_config import (  # noqa: E402
    ProfileConfigError,
    load_profile,
    validate_resume_config,
    validate_theme,
    resolve_effective_policy,
)
from generate_resume import render_html  # noqa: E402
from jobs_tailor_cli import (  # noqa: E402
    OutputLock,
    _docker_user_args,
    command_build,
    command_first_run,
    command_init,
    command_prepare,
)
from resume_validation import validate_source_bounded_text  # noqa: E402
from test_assemble_resume import payload_from_cv  # noqa: E402
from unittest.mock import patch


class ProfileV3Tests(unittest.TestCase):
    def test_default_profile_loads_theme_and_hashes(self):
        profile = load_profile(ROOT / "profiles" / "john-doe")
        self.assertEqual(profile["config"]["schemaVersion"], 3)
        self.assertEqual(profile["theme"]["font"]["family"], "Gelasio")
        self.assertEqual(len(profile["hashes"]["theme"]), 64)

    def test_shared_example_profile_validates_every_optional_section(self):
        profile = load_profile(ROOT / "profiles" / "example-software-engineer")
        self.assertEqual(profile["cv"]["basics"]["name"], "Avery Example")
        self.assertEqual(
            {section["id"] for section in profile["cv"]["extraSections"]},
            {"open-source", "publications"},
        )

    def test_incomplete_private_profile_has_actionable_error(self):
        with tempfile.TemporaryDirectory() as name:
            with self.assertRaisesRegex(ProfileConfigError, "jobs-tailor init"):
                load_profile(Path(name) / "local")

    def test_first_run_rejects_scaffold_profile(self):
        with tempfile.TemporaryDirectory() as name:
            profile_dir = Path(name) / "profile"
            command_init(argparse.Namespace(profile=profile_dir))
            result = command_first_run(argparse.Namespace(profile=profile_dir))
            self.assertFalse(result["ok"])
            self.assertTrue(any("scaffold" in issue for issue in result["issues"]))

    def test_prepare_writes_compact_decision_report(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            job = root / "job.md"
            job.write_text("Software Engineer using Python and PostgreSQL", encoding="utf8")
            output = root / "run"
            command_prepare(
                argparse.Namespace(
                    profile=ROOT / "profiles" / "example-software-engineer",
                    job=job,
                    out=output,
                )
            )
            report = json.loads((output / "decision-report.json").read_text())
            self.assertEqual(report["stage"], "prepared")
            self.assertEqual(report["document"]["targetPages"], 1)
            self.assertIsNone(report["layout"])
            self.assertEqual(report["sections"][1]["resolvedEntryCount"], 1)
            skeleton = json.loads((output / "payload-skeleton.json").read_text())
            self.assertEqual(skeleton["schemaVersion"], 3)
            self.assertTrue(skeleton["sections"])

    def test_prepare_allows_job_description_already_in_output_dir(self):
        with tempfile.TemporaryDirectory() as name:
            output = Path(name)
            job = output / "job-description.md"
            job.write_text("Software Engineer using Python and PostgreSQL", encoding="utf8")
            result = command_prepare(
                argparse.Namespace(
                    profile=ROOT / "profiles" / "example-software-engineer",
                    job=job,
                    out=output,
                )
            )
            self.assertTrue(result["ok"])

    def test_build_writes_default_tailoring_notes(self):
        with tempfile.TemporaryDirectory() as name:
            output = Path(name)
            profile = load_profile(ROOT / "profiles" / "john-doe")
            payload = from_legacy_payload(payload_from_cv(profile["cv"]))
            payload_path = output / "tailoring-payload.json"
            payload_path.write_text(json.dumps(payload), encoding="utf8")
            with patch("generate_resume.generate", return_value={"ok": True}):
                result = command_build(
                    argparse.Namespace(
                        profile=ROOT / "profiles" / "john-doe",
                        payload=payload_path,
                        out=output,
                        renderer="local",
                    )
                )
            self.assertTrue(result["ok"])
            self.assertTrue((output / "tailoring-notes.md").is_file())

    def test_build_does_not_modify_an_active_output(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            output = root / "output"
            output.mkdir()
            payload_path = root / "payload.json"
            profile = load_profile(ROOT / "profiles" / "john-doe")
            payload_path.write_text(
                json.dumps(from_legacy_payload(payload_from_cv(profile["cv"]))),
                encoding="utf8",
            )
            expected = {
                "tailored-resume.json": "existing tailored data",
                "tailoring-payload.json": "existing payload",
                "effective-policy.json": "existing policy",
                "tailoring-notes.md": "existing notes",
            }
            for filename, content in expected.items():
                (output / filename).write_text(content, encoding="utf8")

            with OutputLock(output):
                with self.assertRaisesRegex(RuntimeError, "Another resume generation"):
                    command_build(
                        argparse.Namespace(
                            profile=ROOT / "profiles" / "john-doe",
                            payload=payload_path,
                            out=output,
                            renderer="local",
                        )
                    )

            self.assertEqual(
                {filename: (output / filename).read_text(encoding="utf8") for filename in expected},
                expected,
            )

    def test_failed_build_preserves_existing_output_inputs(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            output = root / "output"
            output.mkdir()
            payload_path = root / "payload.json"
            profile = load_profile(ROOT / "profiles" / "john-doe")
            payload_path.write_text(
                json.dumps(from_legacy_payload(payload_from_cv(profile["cv"]))),
                encoding="utf8",
            )
            expected = {
                "tailored-resume.json": "existing tailored data",
                "tailoring-payload.json": "existing payload",
                "effective-policy.json": "existing policy",
                "tailoring-notes.md": "existing notes",
            }
            for filename, content in expected.items():
                (output / filename).write_text(content, encoding="utf8")

            with patch("generate_resume.generate", side_effect=RuntimeError("render failure")):
                with self.assertRaisesRegex(RuntimeError, "render failure"):
                    command_build(
                        argparse.Namespace(
                            profile=ROOT / "profiles" / "john-doe",
                            payload=payload_path,
                            out=output,
                            renderer="local",
                        )
                    )

            self.assertEqual(
                {filename: (output / filename).read_text(encoding="utf8") for filename in expected},
                expected,
            )

    def test_docker_user_args_are_omitted_when_uid_mapping_is_unavailable(self):
        with patch("jobs_tailor_cli.os.getuid", None), patch("jobs_tailor_cli.os.getgid", None):
            self.assertEqual(_docker_user_args(), [])

    def test_copy_quality_lints_unsourced_soft_claims_but_allows_cve_plural(self):
        cv = load_profile(ROOT / "profiles" / "john-doe")["cv"]
        self.assertFalse(validate_source_bounded_text("triaged CVEs", "triaged CVE", cv, "summary"))
        issues = validate_source_bounded_text(
            "worked with developers",
            "worked calmly with developers",
            cv,
            "summary",
        )
        self.assertTrue(any("unsupported soft claims" in issue for issue in issues))

    def test_scaffold_cv_parses_optional_sections(self):
        cv = parse_cv_text((ROOT / "templates" / "profile" / "CV.md").read_text(encoding="utf8"))
        extras = {section["id"]: section for section in cv["extraSections"]}
        self.assertEqual(extras["open-source"]["type"], "portfolio")
        self.assertEqual(extras["publications"]["items"][0]["id"], "publication-example")

    def test_rejects_invalid_page_target(self):
        config = tomllib.loads((ROOT / "profiles" / "john-doe" / "resume.toml").read_text())
        config["document"]["target_pages"] = 3
        with self.assertRaisesRegex(ProfileConfigError, "must be 1 or 2"):
            validate_resume_config(config, Path("resume.toml"))

    def test_rejects_bullet_rules_on_summary(self):
        config = tomllib.loads((ROOT / "profiles" / "john-doe" / "resume.toml").read_text())
        config["sections"][0]["bullets"] = {"one_page": 1, "two_page": 1}
        with self.assertRaisesRegex(ProfileConfigError, "must not configure bullets"):
            validate_resume_config(config, Path("resume.toml"))

    def test_rejects_remote_fonts(self):
        with tempfile.TemporaryDirectory() as name:
            profile_dir = Path(name).resolve()
            theme_path = profile_dir / "remote-test.json"
            theme = json.loads((ROOT / "themes" / "classic-serif.json").read_text())
            theme["font"]["files"]["regular"] = "https://example.com/font.ttf"
            theme_path.write_text(json.dumps(theme), encoding="utf8")
            with self.assertRaisesRegex(ProfileConfigError, "remote URL"):
                validate_theme(theme, theme_path, profile_dir)

    def test_rejects_negative_bullet_geometry(self):
        theme_path = ROOT / "themes" / "classic-serif.json"
        theme = json.loads(theme_path.read_text())
        theme["bullets"]["leftMarginMm"] = -1
        with self.assertRaisesRegex(ProfileConfigError, "bullets.leftMarginMm"):
            validate_theme(theme, theme_path, ROOT)

    def test_rejects_invalid_skill_item_budget(self):
        config = tomllib.loads((ROOT / "profiles" / "john-doe" / "resume.toml").read_text())
        skills = next(
            item for item in config["sections"] if item["id"] == "technical-skills"
        )
        skills["items_per_category"] = {"one_page": 4, "two_page": 8, "minimum": 5}
        with self.assertRaisesRegex(ProfileConfigError, "minimum <= one_page <= two_page"):
            validate_resume_config(config, Path("resume.toml"))

    def test_rejects_unknown_excluded_source_id(self):
        profile = load_profile(ROOT / "profiles" / "john-doe")
        projects = next(
            item for item in profile["config"]["sections"] if item["sourceId"] == "projects"
        )
        projects["selection"]["excludedSourceIds"] = ["project-does-not-exist"]
        with self.assertRaisesRegex(ProfileConfigError, "excludes unknown source IDs"):
            resolve_effective_policy(profile)

    def test_payload_migration_is_idempotent(self):
        legacy = {
            "jobTitle": "Engineer",
            "summary": "Summary",
            "summarySourceIds": ["summary-primary"],
            "experience": [],
            "projects": [],
            "skillPriorities": [],
        }
        migrated = from_legacy_payload(legacy)
        self.assertEqual(from_legacy_payload(migrated), migrated)
        round_trip = to_legacy_payload(migrated)
        self.assertEqual(round_trip["jobTitle"], "Engineer")

    def test_one_page_uses_preferred_and_two_page_uses_max(self):
        profile = load_profile(ROOT / "profiles" / "john-doe")
        one_page = resolve_effective_policy(profile)
        self.assertEqual(one_page["sectionsById"]["projects"]["effectiveEntryCount"], 2)
        profile["config"]["document"].update({"targetPages": 2, "maxPages": 2})
        two_page = resolve_effective_policy(profile)
        self.assertEqual(two_page["sectionsById"]["projects"]["effectiveEntryCount"], 6)

    def test_bullet_counts_are_clamped_per_source_entry(self):
        profile = load_profile(ROOT / "profiles" / "john-doe")
        profile["cv"]["experience"][0]["bullets"] = profile["cv"]["experience"][0]["bullets"][:2]
        profile["sections"]["experience"]["items"] = profile["cv"]["experience"]
        policy = resolve_effective_policy(profile)
        counts = policy["sectionsById"]["experience"]["effectiveBulletCounts"]
        self.assertEqual(counts[profile["cv"]["experience"][0]["id"]], 2)
        self.assertEqual(counts[profile["cv"]["experience"][1]["id"]], 4)

    def test_disabled_sections_are_absent_from_assembly_and_html(self):
        profile = load_profile(ROOT / "profiles" / "john-doe")
        disabled = {"certifications", "achievements"}
        profile["config"]["sections"] = [
            item for item in profile["config"]["sections"] if item["sourceId"] not in disabled
        ]
        policy = resolve_effective_policy(profile)
        payload = from_legacy_payload(payload_from_cv(profile["cv"]))
        tailored = assemble_profile_resume(
            payload, profile["cv"], policy, profile["sections"]
        )
        self.assertNotIn("certifications", tailored)
        self.assertNotIn("achievements", tailored)
        html = render_html(tailored, profile["theme"], profile["config"])
        self.assertNotIn('data-resume-section="certifications"', html)
        self.assertNotIn('data-resume-section="achievements"', html)

    def test_ordered_certification_budget_is_cv_ordered_and_payload_locked(self):
        profile = load_profile(ROOT / "profiles" / "john-doe")
        certification_config = next(
            item for item in profile["config"]["sections"] if item["sourceId"] == "certifications"
        )
        certification_config["selection"]["entries"] = {"min": 1, "preferred": 2, "max": 3}
        policy = resolve_effective_policy(profile)
        payload = from_legacy_payload(payload_from_cv(profile["cv"]))
        tailored = assemble_profile_resume(
            payload, profile["cv"], policy, profile["sections"]
        )
        self.assertEqual(
            [item["sourceId"] for item in tailored["certifications"]],
            [item["id"] for item in profile["cv"]["certifications"][:2]],
        )
        payload["sections"].append(
            {"sourceId": "certifications", "items": [{"sourceId": profile["cv"]["certifications"][0]["id"]}]}
        )
        with self.assertRaisesRegex(ValueError, "mode 'ordered'"):
            assemble_profile_resume(payload, profile["cv"], policy, profile["sections"])

    def test_html_has_no_forced_project_page_break(self):
        profile = load_profile(ROOT / "profiles" / "john-doe")
        profile["config"]["document"].update({"targetPages": 2, "maxPages": 2})
        payload = from_legacy_payload(payload_from_cv(profile["cv"]))
        projects = next(item for item in payload["sections"] if item["sourceId"] == "projects")
        projects["items"] = [
            {
                "sourceId": item["id"],
                "bullets": [
                    {"sourceId": bullet["id"], "text": bullet["text"]}
                    for bullet in item["bullets"]
                ],
            }
            for item in profile["cv"]["projects"]
        ]
        policy = resolve_effective_policy(profile)
        tailored = assemble_profile_resume(payload, profile["cv"], policy, profile["sections"])
        html = render_html(tailored, profile["theme"], profile["config"])
        self.assertNotIn("break-before", html)
        self.assertNotIn("page-break-before", html)


if __name__ == "__main__":
    unittest.main()
