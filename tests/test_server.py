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

    def _run_with_output(self, stdout: bytes = b"", stderr: bytes = b"", returncode: int = 0):
        fake = types.SimpleNamespace(stdout=stdout, stderr=stderr, returncode=returncode)
        with patch("lmsps.server.subprocess.run", return_value=fake) as _:
            return self.server.tool_ps_run("dummy")

    def test_preserves_whitespace_only_stdout(self):
        result = self._run_with_output(stdout=b"   ")
        self.assertEqual(result, "   ")

    def test_placeholder_only_when_no_output(self):
        result = self._run_with_output()
        self.assertEqual(result, "(ok)")

    def test_exit_code_placeholder_when_no_output(self):
        result = self._run_with_output(returncode=5)
        self.assertEqual(result, "(exit 5)")

    def test_combines_stdout_and_stderr(self):
        result = self._run_with_output(stdout=b"out", stderr=b"err")
        self.assertEqual(result, "out\nerr")

    def test_decodes_utf16_output(self):
        utf16 = "Hello".encode("utf-16-le")
        result = self._run_with_output(stdout=utf16)
        self.assertEqual(result, "Hello")

    def test_decodes_utf16_stderr(self):
        utf16 = "Oops".encode("utf-16-le")
        result = self._run_with_output(stderr=utf16, returncode=1)
        self.assertEqual(result, "Oops")

