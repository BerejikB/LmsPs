# LmsPs — LM Studio PowerShell MCP Server

A minimal, environment‑driven MCP server that exposes a persistent PowerShell session to LM Studio. It keeps a single pwsh.exe/powershell.exe process alive and offers tools to run commands, manage cwd, and get/set env vars. Responses to the client are trimmed (default 500 chars) while full I/O is logged.

## Features
- Tools: `ps.run`, `ps.cd`, `ps.cwd`, `ps.reset`, `ps.env_get`, `ps.env_set`
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
- `LMSPS_PWSH` — PowerShell executable (default `pwsh.exe`, fallback `powershell.exe`)
- `LMSPS_PWSH_FALLBACK` — override fallback exe if needed
- `LMSPS_LOGDIR` — log directory (default: `<repo>/logs`)
- `LMSPS_TRIM_CHARS` — max characters returned to client (default: `500`)
- `LMSPS_TIMEOUT_SEC` — per‑call timeout in seconds (default: `30`)

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
- `ps.run` → `Get-Process | Select-Object -First 3`
- `ps.cwd` → should show current location
- `ps.cd` → change to a test directory and re‑run `ps.cwd`
- `ps.env_set`/`ps.env_get` → write/read a temp environment variable
- Re‑run `ps.run` to confirm session persistence

## Logs
- Full request/response JSON lines are appended to `LMSPS_LOGDIR`/`lmsps_server.log`.

## Repo layout
- `src/lmsps/server.py` — MCP server implementation
- `scripts/start_ps_mcp_stdio.sh` — stdio launcher (used by LM Studio)
- `logs/` — default log directory (overridable via `LMSPS_LOGDIR`)

## License
MIT
