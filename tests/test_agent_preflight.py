from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import agent_preflight  # noqa: E402


class AgentPreflightTests(unittest.TestCase):
    def test_source_fingerprint_is_a_sha256_digest(self):
        fingerprint = agent_preflight.source_fingerprint()
        self.assertRegex(fingerprint, r"^[0-9a-f]{64}$")

    def test_matching_image_is_reused(self):
        with (
            patch("agent_preflight.source_fingerprint", return_value="a" * 64),
            patch("agent_preflight.docker_image_fingerprint", return_value="a" * 64),
            patch("agent_preflight.run") as run,
            patch("agent_preflight.say"),
        ):
            agent_preflight.ensure_docker_image("cvfoundry:test", rebuild=False)
        run.assert_not_called()

    def test_stale_image_is_rebuilt_with_source_fingerprint(self):
        with (
            patch("agent_preflight.source_fingerprint", return_value="b" * 64),
            patch("agent_preflight.docker_image_fingerprint", return_value="a" * 64),
            patch("agent_preflight.run") as run,
            patch("agent_preflight.say"),
        ):
            agent_preflight.ensure_docker_image("cvfoundry:test", rebuild=False)
        run.assert_called_once_with(
            [
                "docker",
                "build",
                "--build-arg",
                f"CVFOUNDRY_SOURCE_SHA256={'b' * 64}",
                "-t",
                "cvfoundry:test",
                ".",
            ]
        )


if __name__ == "__main__":
    unittest.main()
