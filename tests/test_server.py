import importlib
import sys
import types
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


class PsRunOutputTests(TestCase):
    def setUp(self):
        # Ensure we reload the module so patches don't leak between tests.
        self.server = importlib.import_module("lmsps.server")

    def _run_with_output(self, stdout: str = "", stderr: str = "", returncode: int = 0):
        fake = types.SimpleNamespace(stdout=stdout, stderr=stderr, returncode=returncode)
        with patch("lmsps.server.subprocess.run", return_value=fake) as _:
            return self.server.tool_ps_run("dummy")

    def test_preserves_whitespace_only_stdout(self):
        result = self._run_with_output(stdout="   ")
        self.assertEqual(result, "   ")

    def test_placeholder_only_when_no_output(self):
        result = self._run_with_output()
        self.assertEqual(result, "(ok)")

    def test_combines_stdout_and_stderr(self):
        result = self._run_with_output(stdout="out", stderr="err")
        self.assertEqual(result, "out\nerr")

