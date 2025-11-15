# LmsPs — LM Studio PowerShell MCP Server

A minimal, environment‑driven MCP server that exposes a persistent PowerShell session to LM Studio. It keeps a single pwsh.exe/powershell.exe process alive and offers tools to run commands, manage cwd, and get/set env vars. Responses to the client are trimmed (default 500 chars) while full I/O is logged.

## Features
- Tools: `ps_run`, `cd`, `cwd`, `env_get`, `env_set`, `ping`
- Persistent PowerShell between calls (stateful session)
- 500‑char response trim to the client; full logs on disk
- All paths/config via environment variables (no hardcoded paths)

## Install (dev)
```bash
cd K:/Repos/LmsPs
python -m venv .venv
. .venv/Scripts/activate  # Windows
pip install -e .
```

## Run (stdio)
- From WSL (recommended by LM Studio):
```bash
bash K:/Repos/LmsPs/scripts/start_ps_mcp_stdio.sh
```
- Or directly (Windows):
```bash
python -m lmsps.server
```

## Environment variables
- `LMSPS_POWERSHELL_PATH` — Preferred path to Windows PowerShell 5.1 (default `C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe`).
- `LMSPS_PWSH` — Legacy override for the PowerShell executable (retained for backward compatibility).
- `LMSPS_LOGDIR` — log directory (default: `<repo>/logs`)
- `LMSPS_TRIM_CHARS` — max characters returned to client (default: `500`)
- `LMSPS_TIMEOUT_SEC` — per‑call timeout in seconds (default: `30`)
- `LMSPS_MAX_COMMAND_CHARS` — maximum PowerShell command length accepted by `ps_run` (default: `8192`)

## `ps_run` tool
- **Arguments**
  - `command` (required): exact PowerShell command text passed to `-Command`.
  - `timeout_sec` (optional): overrides the per-call timeout (defaults to `LMSPS_TIMEOUT_SEC` or 30s).
  - `trim_chars` (optional): overrides the maximum characters returned to the client (defaults to `LMSPS_TRIM_CHARS` or 500).
- **Execution**
  - Uses Windows PowerShell 5.1 (`powershell.exe`) with `-NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass` to avoid side effects. Override the path with `LMSPS_POWERSHELL_PATH` (or legacy `LMSPS_PWSH`).
  - The process runs with the server's current working directory and an environment overlay managed by `env_set`.
  - The working directory persists across calls; use `cd` to reposition before running relative-path commands.
- **Return payload**
  - The tool now returns a JSON object with fields:
    - `status`: `ok`, `powershell-error`, `timeout`, `invalid-command`, or `internal-error`.
    - `exit_code`: integer PowerShell exit code (or `null` for tool-level failures).
    - `stdout` / `stderr`: decoded (UTF‑16/UTF‑8 aware) output trimmed to `trim_chars`.
    - `message`: optional human-readable context (e.g., timeout notice, validation failure).
    - `timeout_seconds`: populated only for timeout responses so callers know the enforced limit.
- **Validation & failure modes**
  - Commands must be non-empty strings and shorter than `LMSPS_MAX_COMMAND_CHARS`; invalid input returns `status: invalid-command` without touching PowerShell.
  - Timeouts return `status: timeout` with any partial decoded output that PowerShell produced.
  - Spawn failures or unexpected exceptions return `status: internal-error` along with the exception type in `message`.

## LM Studio configuration example
Add to your LM Studio settings JSON:
```json
{
  "mcpServers": {
    "lmsps": {
      "command": "bash",
      "args": ["-lc", "K:/Repos/LmsPs/scripts/start_ps_mcp_stdio.sh"],
      "env": {
        "LMSPS_PWSH": "/mnt/c/Program Files/PowerShell/7/pwsh.exe",
        "LMSPS_LOGDIR": "/mnt/k/LMstudio/LmsPs/logs",
        "LMSPS_TRIM_CHARS": "500"
      }
    }
  }
}
```

## Smoke test (from LM Studio)
- `ps_run` → `Get-Process | Select-Object -First 3`
- `cwd` → should show current location
- `cd` → change to a test directory and re‑run `cwd`
- `env_set`/`env_get` → write/read a temp environment variable
- Re‑run `ps_run` to confirm session persistence

## Working directory model
- The MCP server maintains a single-process working directory stored in memory.
- `cwd` reports the current directory, and `cd` updates it (accepting absolute or relative paths).
- Subsequent `ps_run` commands execute within that directory, so `Get-ChildItem -Path .` and `Get-Content` on relative paths resolve as expected.
- FastMCP routes requests sequentially, so there is no concurrent mutation of this state; the model matches LM Studio's expectation of a single PowerShell session.

## Logs
- Full request/response JSON lines are appended to `LMSPS_LOGDIR`/`lmsps_server.log`.

## Repo layout
- `src/lmsps/server.py` — MCP server implementation
- `scripts/start_ps_mcp_stdio.sh` — stdio launcher (used by LM Studio)
- `logs/` — default log directory (overridable via `LMSPS_LOGDIR`)

## License
MIT
