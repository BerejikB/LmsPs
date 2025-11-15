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
- `LMSPS_PWSH` — PowerShell executable (default `C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe`)
- `LMSPS_LOGDIR` — log directory (default: `<repo>/logs`)
- `LMSPS_TRIM_CHARS` — max characters returned to client (default: `500`)
- `LMSPS_TIMEOUT_SEC` — per‑call timeout in seconds (default: `30`)

## `ps_run` tool
- **Arguments**
  - `command` (required): exact PowerShell command text passed to `-Command`.
  - `timeout_sec` (optional): overrides the per-call timeout (defaults to `LMSPS_TIMEOUT_SEC` or 30s).
  - `trim_chars` (optional): overrides the maximum characters returned to the client (defaults to `LMSPS_TRIM_CHARS` or 500).
- **Execution**
  - Uses Windows PowerShell 5.1 (`powershell.exe`) by default to maximize LM Studio compatibility. Override `LMSPS_PWSH` if you need `pwsh.exe` or a custom path.
  - The process runs with the server's current working directory and an environment overlay managed by `env_set`.
- **Output handling**
  - PowerShell 5.1 emits UTF‑16LE bytes; output is decoded with BOM/unicode aware fallbacks and concatenated as `stdout` followed by `stderr` separated by a newline.
  - If there is no output, the tool returns `(ok)` for exit code 0, or `(exit <code>)` otherwise.
  - Results longer than `trim_chars` are truncated with a summary suffix (the full data is logged on disk).
- **Failure modes**
  - Timeouts return `timeout after <n>s` along with any partial decoded output that PowerShell produced.
  - Spawn failures or unexpected exceptions return `error: <Type>: <message>`.

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

## Logs
- Full request/response JSON lines are appended to `LMSPS_LOGDIR`/`lmsps_server.log`.

## Repo layout
- `src/lmsps/server.py` — MCP server implementation
- `scripts/start_ps_mcp_stdio.sh` — stdio launcher (used by LM Studio)
- `logs/` — default log directory (overridable via `LMSPS_LOGDIR`)

## License
MIT
