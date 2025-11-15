import importlib
import subprocess
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
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["stdout"], "   ")

    def test_placeholder_only_when_no_output(self):
        result = self._run_with_output()
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["stdout"], "")
        self.assertEqual(result["stderr"], "")

    def test_combines_stdout_and_stderr(self):
        result = self._run_with_output(stdout="out", stderr="err")
        self.assertEqual(result["stdout"], "out")
        self.assertEqual(result["stderr"], "err")

    def test_bytes_from_powershell_are_decoded(self):
        result = self._run_with_output(stdout=b"hello\r\n")
        self.assertEqual(result["stdout"], "hello\r\n")

    def test_stderr_bytes_joined(self):
        result = self._run_with_output(stdout=b"ok", stderr=b"warn")
        self.assertEqual(result["stdout"], "ok")
        self.assertEqual(result["stderr"], "warn")

    def test_stderr_only_has_no_leading_newline(self):
        result = self._run_with_output(stderr="warn")
        self.assertEqual(result["stdout"], "")
        self.assertEqual(result["stderr"], "warn")

    def test_get_childitem_command_wires_through(self):
        command = 'Get-ChildItem -Path "C:/Temp" -Filter "*.txt"'

        def fake_run(args, **kwargs):
            # args[-1] is the PowerShell command string passed via -Command
            self.assertEqual(args[-1], command)
            self.assertEqual(
                args[0],
                self.server.DEFAULT_POWERSHELL_PATH,
            )
            return types.SimpleNamespace(stdout=b"item1\r\n", stderr=b"", returncode=0)

        with patch("lmsps.server.subprocess.run", side_effect=fake_run):
            result = self.server.tool_ps_run(command)
        self.assertEqual(result["stdout"], "item1\r\n")
        self.assertEqual(result["status"], "ok")

    def test_unicode_utf16le_output(self):
        text = "你好"
        encoded = b"\xff\xfe" + text.encode("utf-16-le")
        result = self._run_with_output(stdout=encoded)
        self.assertEqual(result["stdout"], text)

    def test_non_zero_exit_without_output(self):
        result = self._run_with_output(returncode=5)
        self.assertEqual(result["status"], "powershell-error")
        self.assertEqual(result["exit_code"], 5)
        self.assertEqual(result["stdout"], "")
        self.assertEqual(result["stderr"], "")
        self.assertIn("PowerShell exited", result["message"])

    def test_large_output_is_trimmed(self):
        big = "X" * 120
        result = self._run_with_output(stdout=big, trim_chars=50)
        self.assertTrue(result["stdout"].endswith("...[trimmed 70 chars]"))

    def test_command_must_be_string(self):
        result = self.server.tool_ps_run(123)  # type: ignore[arg-type]
        self.assertEqual(result["status"], "invalid-command")
        self.assertIn("invalid-command", result["message"])

    def test_command_must_not_be_empty(self):
        result = self.server.tool_ps_run("   ")
        self.assertEqual(result["status"], "invalid-command")
        self.assertIn("invalid-command", result["message"])

    def test_command_length_is_limited(self):
        too_long = "x" * 9000
        with patch.dict("os.environ", {"LMSPS_MAX_COMMAND_CHARS": "100"}):
            result = self.server.tool_ps_run(too_long)
        self.assertEqual(result["status"], "invalid-command")
        self.assertEqual(
            result["message"],
            "error: invalid-command: command exceeds 100 characters",
        )

    def test_custom_powershell_path_used(self):
        sentinel = r"D:\\PwSh\\powershell.exe"

        def fake_run(args, **kwargs):
            self.assertEqual(args[0], sentinel)
            return types.SimpleNamespace(stdout=b"ok", stderr=b"", returncode=0)

        with patch.dict("os.environ", {"LMSPS_POWERSHELL_PATH": sentinel}):
            with patch("lmsps.server.subprocess.run", side_effect=fake_run):
                result = self.server.tool_ps_run("Write-Output ok")
        self.assertEqual(result["stdout"], "ok")
        self.assertEqual(result["status"], "ok")

    def test_timeout_reports_partial_output(self):
        exc = subprocess.TimeoutExpired(cmd="powershell", timeout=1)
        exc.stdout = b"partial"
        exc.stderr = b""

        with patch(
            "lmsps.server.subprocess.run",
            side_effect=exc,
        ):
            result = self.server.tool_ps_run("Start-Sleep 5", timeout_sec=1)

        self.assertEqual(result["status"], "timeout")
        self.assertIn("timeout after", result["message"])
        self.assertEqual(result["stdout"], "partial")

    def test_powershell_error_preserves_stderr(self):
        result = self._run_with_output(stdout="", stderr="boom", returncode=1)
        self.assertEqual(result["status"], "powershell-error")
        self.assertEqual(result["stderr"], "boom")

    def test_internal_exception_returns_structured_error(self):
        with patch(
            "lmsps.server.subprocess.run",
            side_effect=RuntimeError("kaput"),
        ):
            result = self.server.tool_ps_run("Write-Output ok")

        self.assertEqual(result["status"], "internal-error")
        self.assertIn("RuntimeError", result["message"])
        self.assertEqual(result["stdout"], "")
        self.assertEqual(result["stderr"], "")

