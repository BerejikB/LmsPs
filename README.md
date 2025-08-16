# LmsPs — LM Studio PowerShell MCP Server

A minimal MCP server that exposes a persistent PowerShell session to LM Studio.

- Tools:
  - `ps.run` — run a command in the persistent session
  - `ps.cwd` — print the current working directory
  - `ps.cd` — change directory in the persistent session
  - `ps.reset` — restart the PowerShell process
  - `ps.env_get` / `ps.env_set` — read or set environment variables within the session

## Install

```bash
pip install -e .
```

## Run (stdio)

```bash
python -m lmsps.server --stdio
```

Or via script wrapper from WSL:

```bash
bash scripts/start_ps_mcp_stdio.sh
```

## Environment variables

- `LMSPS_PWSH` — path to PowerShell executable (default: `pwsh.exe`, fallback `powershell.exe`)
- `LMSPS_LOGDIR` — log directory (default: `./logs`)
- `LMSPS_TRIM_CHARS` — max characters returned to client (default: `500`)
- `LMSPS_TIMEOUT_SEC` — per-call timeout (default: `30`)

## LM Studio config example

```json
{
  "mcpServers": {
    "lmsps": {
      "command": "bash",
      "args": ["-lc", "K:/Repos/LmsPs/scripts/start_ps_mcp_stdio.sh"],
      "env": {
        "LMSPS_PWSH": "/mnt/c/Program Files/PowerShell/7/pwsh.exe",
        "LMSPS_LOGDIR": "/mnt/k/LMstudio/LmsPs/logs"
      }
    }
  }
}
```
