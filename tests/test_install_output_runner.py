from __future__ import annotations

import stat
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from install_output_runner import install_runner  # noqa: E402


class InstallOutputRunnerTests(unittest.TestCase):
    def test_installs_executable_wrapper(self):
        with tempfile.TemporaryDirectory() as name:
            output_dir = Path(name) / "output" / "example-role-2026-06-22"
            runner = install_runner(output_dir)
            self.assertEqual(runner, output_dir / "rerun.py")
            self.assertTrue(runner.exists())
            mode = runner.stat().st_mode
            self.assertTrue(mode & stat.S_IXUSR)
            content = runner.read_text(encoding="utf8")
            self.assertIn('"rerun"', content)
            self.assertIn("jobs_tailor_cli.py", content)


if __name__ == "__main__":
    unittest.main()
