# src/lmsps/server.py
import os, sys, subprocess
from typing import Optional, Dict
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("lmsps")

# ---- boot log (never prints to stdout) ----
LOGDIR = os.environ.get("LMSPS_LOGDIR") or os.path.join(os.getcwd(), "logs")
os.makedirs(LOGDIR, exist_ok=True)
BOOTLOG = os.path.join(LOGDIR, "lmsps_boot.log")
def _log(msg: str) -> None:
    with open(BOOTLOG, "a", encoding="utf-8") as f:
        f.write(msg.rstrip() + "\n")

# Operational root / default cwd
_STATE = {
    "cwd": os.path.normpath(os.environ.get("LMSPS_CWD") or os.getcwd()),
    "env": {},  # session-only overlay
}

def _effective_env() -> Dict[str, str]:
    e = os.environ.copy()
    e.update(_STATE["env"])
    return e

def _trim(s: str) -> str:
    n = int(os.environ.get("LMSPS_TRIM_CHARS", "500"))
    return s if len(s) <= n else s[:n] + f"\n...[trimmed {len(s)-n} chars]"

@mcp.tool()
def ps_run(command: str) -> str:
    """Run a PowerShell command and return combined stdout+stderr (trimmed)."""
    exe = os.environ.get(
        "LMSPS_PWSH",
        r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"
    )
    timeout = int(os.environ.get("LMSPS_TIMEOUT_SEC", "30"))
    cp = subprocess.run(
        [exe, "-NoLogo", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
        cwd=_STATE["cwd"],
        env=_effective_env(),
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    out = (cp.stdout or "") + (("\n" + cp.stderr) if cp.stderr else "")
    return _trim(out)

@mcp.tool()
def cwd() -> str:
    """Return current working directory."""
    return _STATE["cwd"]

@mcp.tool()
def cd(path: str) -> str:
    """Change working directory; returns new path."""
    new = path if os.path.isabs(path) else os.path.abspath(os.path.join(_STATE["cwd"], path))
    if not os.path.isdir(new):
        raise FileNotFoundError(new)
    _STATE["cwd"] = os.path.normpath(new)
    return _STATE["cwd"]

@mcp.tool()
def env_get(key: Optional[str] = None):
    """Get a specific env value or (by default) the session overlay dict."""
    e = _effective_env()
    if key is not None:
        return e.get(key, "")
    return dict(_STATE["env"])  # overlay only

@mcp.tool()
def env_set(key: str, value: str) -> str:
    """Set a session env var override."""
    _STATE["env"][key] = value
    return "ok"

@mcp.tool()
def ping() -> str:
    """Simple health-check."""
    return "pong"

if __name__ == "__main__":
    # Log exactly what LM Studio is running
    try:
        import mcp as _mcp
        mcp_ver = getattr(_mcp, "__version__", "unknown")
    except Exception:
        mcp_ver = "unknown"
    _log(f"BOOT: exe={sys.executable}")
    _log(f"BOOT: sys.path[0]={sys.path[0]}")
    _log(f"BOOT: module_file={__file__}")
    _log(f"BOOT: mcp_version={mcp_ver}")
    _log(f"BOOT: env.LMSPS_CWD={os.environ.get('LMSPS_CWD')}")
    _log(f"BOOT: env.LMSPS_LOGDIR={os.environ.get('LMSPS_LOGDIR')}")
    _log(f"BOOT: registering tools: {sorted([t.name for t in mcp._tools])}")

    # FastMCP defaults to STDIO; no manual streams.
    mcp.run()
