import os
import sys
import time
import json
import shlex
import psutil
import threading
import subprocess
from datetime import datetime
from typing import Optional

try:
    from mcp.server import Server
    from mcp.types import Tool, TextContent
except Exception as e:  # graceful message if MCP SDK missing
    Server = None  # type: ignore


DEF_TRIM = int(os.getenv("LMSPS_TRIM_CHARS", "500"))
DEF_TIMEOUT = int(os.getenv("LMSPS_TIMEOUT_SEC", "30"))
LOGDIR = os.getenv("LMSPS_LOGDIR", os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "logs")))
PWSH = os.getenv("LMSPS_PWSH", "pwsh.exe")
PWSH_FALLBACK = "powershell.exe"

os.makedirs(LOGDIR, exist_ok=True)
LOG_PATH = os.path.join(LOGDIR, "lmsps_server.log")


def log(event: str, data: Optional[dict] = None):
    try:
        payload = {
            "ts": datetime.utcnow().isoformat() + "Z",
            "event": event,
        }
        if data is not None:
            payload.update(data)
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception:
        pass


class PersistentPS:
    def __init__(self):
        self.proc: Optional[subprocess.Popen] = None
        self.lock = threading.Lock()
        self.cwd = None  # tracked cwd for info

    def start(self):
        if self.proc and self.proc.poll() is None:
            return
        exe = PWSH
        # Verify executable exists/launchable; if fails, try fallback
        try:
            test = subprocess.run([exe, "-NoLogo", "-NoProfile", "-Command", "$PSVersionTable.PSVersion.ToString()"], capture_output=True, text=True, timeout=5)
            if test.returncode != 0:
                raise RuntimeError(test.stderr or test.stdout)
        except Exception:
            exe = PWSH_FALLBACK
        # Launch interactive session we can feed via -EncodedCommand is not persistent. Use stdio with -NoExit
        self.proc = subprocess.Popen(
            [exe, "-NoLogo", "-NoProfile", "-NoExit", "-Command", "Write-Output 'LmsPs Online'"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            universal_newlines=True,
        )
        # Drain initial banner
        time.sleep(0.2)
        self._drain()

    def _drain(self, timeout: float = 0.05) -> str:
        out = []
        if self.proc and self.proc.stdout:
            start = time.time()
            while time.time() - start < timeout:
                line = self.proc.stdout.readline()
                if not line:
                    break
                out.append(line)
                if not self.proc.stdout.readable():
                    break
        return "".join(out)

    def run(self, command: str, timeout: int = DEF_TIMEOUT) -> str:
        with self.lock:
            self.start()
            assert self.proc and self.proc.stdin and self.proc.stdout
            sentinel = f"__LMSPS_SENTINEL_{int(time.time()*1000)}__"
            script = f"{command}\nWrite-Output '{sentinel}'\n"
            self.proc.stdin.write(script)
            self.proc.stdin.flush()

            # Read until sentinel or timeout
            output_lines = []
            end_time = time.time() + timeout
            while time.time() < end_time:
                line = self.proc.stdout.readline()
                if not line:
                    time.sleep(0.01)
                    continue
                if sentinel in line:
                    break
                output_lines.append(line)
            else:
                output_lines.append(f"\n[Timeout after {timeout}s]\n")
            return "".join(output_lines)

    def cd(self, path: str) -> str:
        return self.run(f"Set-Location -Path {shlex.quote(path)}; Get-Location")

    def cwd_cmd(self) -> str:
        return self.run("Get-Location")

    def reset(self) -> str:
        with self.lock:
            if self.proc and self.proc.poll() is None:
                try:
                    self.proc.terminate()
                    self.proc.wait(timeout=3)
                except Exception:
                    try:
                        self.proc.kill()
                    except Exception:
                        pass
            self.proc = None
        self.start()
        return "Reset OK"


ps_session = PersistentPS()


def trim(s: str, n: int = DEF_TRIM) -> str:
    return s if len(s) <= n else s[:n]


def main():
    if Server is None:
        print("mcp is not installed. pip install mcp", file=sys.stderr)
        sys.exit(1)

    server = Server("lmsps")

    @server.tool()
    def ps_run(command: str, timeout: Optional[int] = None) -> str:
        """Run a PowerShell command in the persistent session."""
        to = timeout or DEF_TIMEOUT
        log("tool_call", {"tool": "ps.run", "command": command, "timeout": to})
        full = ps_session.run(command, timeout=to)
        log("tool_result", {"tool": "ps.run", "len": len(full)})
        return trim(full)

    @server.tool()
    def ps_cd(path: str) -> str:
        """Change directory in the persistent session."""
        log("tool_call", {"tool": "ps.cd", "path": path})
        full = ps_session.cd(path)
        log("tool_result", {"tool": "ps.cd", "len": len(full)})
        return trim(full)

    @server.tool()
    def ps_cwd() -> str:
        """Get current directory of the persistent session."""
        log("tool_call", {"tool": "ps.cwd"})
        full = ps_session.cwd_cmd()
        log("tool_result", {"tool": "ps.cwd", "len": len(full)})
        return trim(full)

    @server.tool()
    def ps_reset() -> str:
        """Restart the PowerShell process and clear state."""
        log("tool_call", {"tool": "ps.reset"})
        full = ps_session.reset()
        log("tool_result", {"tool": "ps.reset", "len": len(full)})
        return trim(full)

    @server.tool()
    def ps_env_get(name: str) -> str:
        """Get environment variable value inside the session."""
        log("tool_call", {"tool": "ps.env_get", "name": name})
        full = ps_session.run(f"$env:{name}")
        log("tool_result", {"tool": "ps.env_get", "len": len(full)})
        return trim(full)

    @server.tool()
    def ps_env_set(name: str, value: str) -> str:
        """Set environment variable inside the session."""
        log("tool_call", {"tool": "ps.env_set", "name": name})
        full = ps_session.run(f"$env:{name} = '{value.replace("'","''")}' ; Write-Output 'OK' ")
        log("tool_result", {"tool": "ps.env_set", "len": len(full)})
        return trim(full)

    # Start serving on stdio
    server.run_stdio()


if __name__ == "__main__":
    main()
