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

    def _run_with_output(self, stdout="", stderr="", returncode: int = 0, **kwargs):
        fake = types.SimpleNamespace(stdout=stdout, stderr=stderr, returncode=returncode)
        with patch("lmsps.server.subprocess.run", return_value=fake) as _:
            return self.server.tool_ps_run("dummy", **kwargs)

    def test_preserves_whitespace_only_stdout(self):
        result = self._run_with_output(stdout="   ")
        self.assertEqual(result, "   ")

    def test_placeholder_only_when_no_output(self):
        result = self._run_with_output()
        self.assertEqual(result, "(ok)")

    def test_combines_stdout_and_stderr(self):
        result = self._run_with_output(stdout="out", stderr="err")
        self.assertEqual(result, "out\nerr")

    def test_bytes_from_powershell_are_decoded(self):
        result = self._run_with_output(stdout=b"hello\r\n")
        self.assertEqual(result, "hello\r\n")

    def test_stderr_bytes_joined(self):
        result = self._run_with_output(stdout=b"ok", stderr=b"warn")
        self.assertEqual(result, "ok\nwarn")

    def test_stderr_only_has_no_leading_newline(self):
        result = self._run_with_output(stderr="warn")
        self.assertEqual(result, "warn")

    def test_get_childitem_command_wires_through(self):
        command = 'Get-ChildItem -Path "C:/Temp" -Filter "*.txt"'

        def fake_run(args, **kwargs):
            # args[-1] is the PowerShell command string passed via -Command
            self.assertEqual(args[-1], command)
            return types.SimpleNamespace(stdout=b"item1\r\n", stderr=b"", returncode=0)

        with patch("lmsps.server.subprocess.run", side_effect=fake_run):
            result = self.server.tool_ps_run(command)
        self.assertEqual(result, "item1\r\n")

    def test_unicode_utf16le_output(self):
        text = "你好"
        encoded = b"\xff\xfe" + text.encode("utf-16-le")
        result = self._run_with_output(stdout=encoded)
        self.assertEqual(result, text)

    def test_non_zero_exit_without_output(self):
        result = self._run_with_output(returncode=5)
        self.assertEqual(result, "(exit 5)")

    def test_large_output_is_trimmed(self):
        big = "X" * 120
        result = self._run_with_output(stdout=big, trim_chars=50)
        self.assertTrue(result.endswith("...[trimmed 70 chars]"))

