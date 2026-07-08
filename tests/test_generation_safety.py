from __future__ import annotations

import fcntl
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

from artifact_names import final_pdf_filename  # noqa: E402
from cv_source import load_cv  # noqa: E402
from generate_resume import (  # noqa: E402
    ContentValidationError,
    LibreOfficeRuntimeError,
    WriterSession,
    generate,
    render_html,
)
from test_check_resume_quality import tailored_resume  # noqa: E402


class GenerationSafetyTests(unittest.TestCase):
    def setUp(self):
        self.cv_path = ROOT / "profiles" / "john-doe" / "CV.md"
        self.cv = load_cv(self.cv_path)

    def input_json(self, output: Path) -> Path:
        path = output / "tailored-resume.json"
        path.write_text(
            json.dumps(tailored_resume(self.cv), indent=2) + "\n",
            encoding="utf8",
        )
        return path

    def test_missing_libreoffice_fails_clearly(self):
        with tempfile.TemporaryDirectory() as name:
            with patch("generate_resume.shutil.which", return_value=None):
                with self.assertRaisesRegex(LibreOfficeRuntimeError, "LibreOffice Writer is unavailable"):
                    with WriterSession(Path(name)):
                        pass

    def test_concurrent_generation_is_rejected(self):
        with tempfile.TemporaryDirectory() as name:
            output = Path(name)
            input_json = self.input_json(output)
            lock_path = output / ".generate.lock"
            with lock_path.open("w") as lock:
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                with self.assertRaisesRegex(LibreOfficeRuntimeError, "Another resume generation is active"):
                    generate(input_json, output, self.cv_path)

    def test_failed_generation_preserves_existing_artifact(self):
        with tempfile.TemporaryDirectory() as name:
            output = Path(name)
            input_json = self.input_json(output)
            html_path = output / "tailored-resume.html"
            html_path.write_text("existing", encoding="utf8")
            with patch.object(
                WriterSession,
                "__enter__",
                side_effect=RuntimeError("simulated Writer failure"),
            ):
                with self.assertRaisesRegex(LibreOfficeRuntimeError, "simulated Writer failure"):
                    generate(input_json, output, self.cv_path)
            self.assertEqual(html_path.read_text(encoding="utf8"), "existing")
            self.assertFalse(
                (output / final_pdf_filename(tailored_resume(self.cv))).exists()
            )

    def test_pipeline_lock_env_allows_generate_under_external_lock(self):
        with tempfile.TemporaryDirectory() as name:
            output = Path(name)
            input_json = self.input_json(output)
            lock_path = output / ".generate.lock"
            with lock_path.open("w") as lock:
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                with patch.dict(os.environ, {"JOBS_TAILORING_PIPELINE_LOCK": "1"}, clear=False):
                    with patch.object(
                        WriterSession,
                        "__enter__",
                        side_effect=RuntimeError("simulated Writer failure"),
                    ):
                        with self.assertRaisesRegex(LibreOfficeRuntimeError, "simulated Writer failure"):
                            generate(input_json, output, self.cv_path)

    def test_invalid_resume_payload_fails_before_writer_starts(self):
        with tempfile.TemporaryDirectory() as name:
            output = Path(name)
            input_json = self.input_json(output)
            data = json.loads(input_json.read_text(encoding="utf8"))
            data["basics"]["name"] = "Someone Else"
            input_json.write_text(json.dumps(data), encoding="utf8")
            with patch.object(WriterSession, "__enter__", side_effect=AssertionError("writer should not start")):
                with self.assertRaises(ContentValidationError):
                    generate(input_json, output, self.cv_path)

    def test_achievement_links_are_inline(self):
        html = render_html(tailored_resume(self.cv))
        self.assertIn('href="https://example.com/john-doe/contributions"', html)
        self.assertIn('href="https://example.com/rust-talk"', html)
        self.assertNotIn("(Link)", html)


if __name__ == "__main__":
    unittest.main()
