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

def _decode_stream(data: bytes) -> str:
    if not data:
        return ""

    candidates = []
    # PowerShell 5.1 defaults to UTF-16LE with embedded NUL bytes; prefer that
    # when we detect a BOM or any NUL characters so we decode without mojibake.
    if data.startswith(b"\xff\xfe") or data.startswith(b"\xfe\xff") or b"\x00" in data:
        candidates.extend(["utf-16-le", "utf-16-be"])

    candidates.extend(["utf-8-sig", "utf-8", "utf-16-le", "utf-16-be"])

    preferred = locale.getpreferredencoding(False)
    if preferred:
        candidates.append(preferred)

    def _roundtrip_matches(text: str, enc: str) -> bool:
        try:
            if enc == "utf-8-sig":
                return text.encode("utf-8-sig") == data
            encoded = text.encode(enc)
        except Exception:
            return False

        if enc == "utf-16-le" and data.startswith(b"\xff\xfe"):
            return b"\xff\xfe" + encoded == data or encoded == data
        if enc == "utf-16-be" and data.startswith(b"\xfe\xff"):
            return b"\xfe\xff" + encoded == data or encoded == data
        return encoded == data

    seen = set()
    for enc in candidates:
        if enc in seen:
            continue
        seen.add(enc)
        try:
            text = data.decode(enc)
        except UnicodeDecodeError:
            continue
        if text.startswith("\ufeff"):
            text = text.lstrip("\ufeff")
        if _roundtrip_matches(text, enc):
            return text

    return data.decode("latin-1", errors="replace")


def _ensure_text(data) -> str:
    """Normalize subprocess output (bytes/str/None) into a text string."""
    if not data:
        return ""
    if isinstance(data, bytes):
        return _decode_stream(data)
    if isinstance(data, str):
        return data
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
        out = stdout + (("\n" + stderr) if stderr else "")
        if not stdout and not stderr:
            out = "(ok)" if cp.returncode == 0 else f"(exit {cp.returncode})"
        result = _trim(out, n)
        stdout_bytes = stdout_raw if isinstance(stdout_raw, (bytes, bytearray)) else stdout.encode("utf-8")
        stderr_bytes = stderr_raw if isinstance(stderr_raw, (bytes, bytearray)) else stderr.encode("utf-8")
        _log(f"ps_run done rc={cp.returncode} bytes={len(stdout_bytes) + len(stderr_bytes)}")
        return result

    except subprocess.TimeoutExpired as e:
        stdout = _decode_stream(e.stdout or b"")
        stderr = _decode_stream(e.stderr or b"")
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
