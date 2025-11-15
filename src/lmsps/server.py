# src/lmsps/server.py
import locale
import os, sys, subprocess
from typing import Optional, Dict
from mcp.server.fastmcp import FastMCP

# ---- boot log (never prints to stdout) ----
LOGDIR = os.environ.get("LMSPS_LOGDIR") or os.path.join(os.getcwd(), "logs")
os.makedirs(LOGDIR, exist_ok=True)
BOOTLOG = os.path.join(LOGDIR, "lmsps_boot.log")
def _log(msg: str) -> None:
    with open(BOOTLOG, "a", encoding="utf-8") as f:
        f.write(msg.rstrip() + "\n")

# Operational state
_STATE = {
    "cwd": os.path.normpath(os.environ.get("LMSPS_CWD") or os.getcwd()),
    "env": {},  # session-only env overlay
}

def _effective_env() -> Dict[str, str]:
    e = os.environ.copy()
    e.update(_STATE["env"])
    return e

def _trim(s: str, n: int) -> str:
    return s if len(s) <= n else s[:n] + f"\n...[trimmed {len(s)-n} chars]"

# ------------------ Tools (plain functions; not decorated) ------------------

def _decode_stream(raw: bytes) -> str:
    if not raw:
        return ""

    # PowerShell 5.1 defaults to UTF-16LE without advertising it to subprocess.
    # Prefer decoding as UTF-16 when we see either a BOM or embedded NUL bytes
    # (common for UTF-16 output). Fall back to UTF-8 variants and finally the
    # locale's preferred codec before replacing undecodable bytes.
    encodings = []
    if raw.startswith(b"\xff\xfe") or raw.startswith(b"\xfe\xff") or b"\x00" in raw:
        encodings.extend(["utf-16", "utf-16-le", "utf-16-be"])

    encodings.extend(["utf-8-sig", "utf-8"])

    preferred = locale.getpreferredencoding(False)
    if preferred:
        encodings.append(preferred)

    seen = set()
    for enc in encodings:
        if enc in seen:
            continue
        seen.add(enc)
        try:
            text = raw.decode(enc)
        except UnicodeDecodeError:
            continue
        return text.lstrip("\ufeff")

    return raw.decode("utf-8", errors="replace")


def _ensure_text(data) -> str:
    """Normalize subprocess output (bytes/str/None) into a text string."""
    if not data:
        return ""
    if isinstance(data, str):
        return data
    if isinstance(data, (bytes, bytearray)):
        return _decode_stream(bytes(data))
    # Fallback for unexpected objects (e.g., memoryview); mirrors str() but keeps control
    return str(data)


def tool_ps_run(
    command: str,
    timeout_sec: Optional[int] = None,
    trim_chars: Optional[int] = None,
) -> str:
    """Run a PowerShell command and return combined stdout+stderr (trimmed)."""
    exe = os.environ.get(
        "LMSPS_PWSH",
        r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"
    )
    t = int(timeout_sec or os.environ.get("LMSPS_TIMEOUT_SEC", "30"))
    n = int(trim_chars or os.environ.get("LMSPS_TRIM_CHARS", "500"))

    args = [
        exe, "-NoLogo", "-NoProfile", "-NonInteractive",
        "-ExecutionPolicy", "Bypass",
        "-Command", command
    ]

    _log(f"ps_run start t={t}s n={n} cwd={_STATE['cwd']} cmd={command[:120]!r}")

    try:
        cp = subprocess.run(
            args,
            cwd=_STATE["cwd"],
            env=_effective_env(),
            capture_output=True,
            text=False,
            timeout=t,
        )
        stdout_raw = cp.stdout
        stderr_raw = cp.stderr
        # PowerShell 5.1 streams are bytes (typically UTF-16LE). Normalize before
        # joining so we don't hit the "can't concat str to bytes" TypeError that
        # surfaced when stderr/stdout were combined directly.
        stdout = _ensure_text(stdout_raw)
        stderr = _ensure_text(stderr_raw)
        parts = []
        if stdout:
            parts.append(stdout)
        if stderr:
            parts.append(stderr)
        if parts:
            out = "\n".join(parts)
        else:
            out = "(ok)" if cp.returncode == 0 else f"(exit {cp.returncode})"
        result = _trim(out, n)
        if isinstance(stdout_raw, (bytes, bytearray)):
            stdout_bytes = len(stdout_raw)
        else:
            stdout_bytes = len(stdout.encode("utf-8", errors="replace"))
        if isinstance(stderr_raw, (bytes, bytearray)):
            stderr_bytes = len(stderr_raw)
        else:
            stderr_bytes = len(stderr.encode("utf-8", errors="replace"))
        _log(f"ps_run done rc={cp.returncode} bytes={stdout_bytes + stderr_bytes}")
        return result

    except subprocess.TimeoutExpired as e:
        stdout = _ensure_text(e.stdout)
        stderr = _ensure_text(e.stderr)
        parts = []
        if stdout:
            parts.append(stdout)
        if stderr:
            parts.append(stderr)
        decoded = "\n".join(parts)
        msg = f"timeout after {t}s"
        if decoded:
            decoded = decoded.strip()
            if decoded:
                msg += "\npartial output:\n" + _trim(decoded, n)
        _log(f"ps_run timeout t={t}s")
        return msg

    except Exception as e:
        _log(f"ps_run error: {type(e).__name__}: {e}")
        return f"error: {type(e).__name__}: {e}"

def tool_cwd() -> str:
    return _STATE["cwd"]

def tool_cd(path: str) -> str:
    new = path if os.path.isabs(path) else os.path.abspath(os.path.join(_STATE["cwd"], path))
    if not os.path.isdir(new):
        raise FileNotFoundError(new)
    _STATE["cwd"] = os.path.normpath(new)
    return _STATE["cwd"]

def tool_env_get(key: Optional[str] = None):
    e = _effective_env()
    if key is not None:
        return e.get(key, "")
    return dict(_STATE["env"])  # overlay only

def tool_env_set(key: str, value: str) -> str:
    _STATE["env"][key] = value
    return "ok"

def tool_ping() -> str:
    return "pong"

# ------------------ App factory (avoids duplicate registration) ------------------

def build_app() -> FastMCP:
    app = FastMCP("lmsps")

    # Register tools exactly once per FastMCP instance
    app.tool(name="ps_run")(tool_ps_run)
    app.tool(name="cwd")(tool_cwd)
    app.tool(name="cd")(tool_cd)
    app.tool(name="env_get")(tool_env_get)
    app.tool(name="env_set")(tool_env_set)
    app.tool(name="ping")(tool_ping)

    return app

if __name__ == "__main__":
    try:
        import mcp as _mcp
        mcp_ver = getattr(_mcp, "__version__", "unknown")
    except Exception:
        mcp_ver = "unknown"
    _log(f"BOOT exe={sys.executable}")
    _log(f"BOOT module_file={__file__}")
    _log(f"BOOT mcp_version={mcp_ver}")
    _log(f"BOOT LMSPS_CWD={os.environ.get('LMSPS_CWD')}")
    _log(f"BOOT LMSPS_LOGDIR={os.environ.get('LMSPS_LOGDIR')}")

    app = build_app()
    _log("BOOT tools=['ps_run','cwd','cd','env_get','env_set','ping']")
    # STDIO by default; will wait for a client. Ctrl+C here will show KeyboardInterrupt (expected).
    app.run()
