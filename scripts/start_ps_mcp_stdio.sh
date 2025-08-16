#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOGDIR="${LMSPS_LOGDIR:-$ROOT_DIR/logs}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

mkdir -p "$LOGDIR"
# Normalize line endings and shebangs self-heal not needed here

exec "$PYTHON_BIN" -m lmsps.server --stdio 2>>"$LOGDIR/start_ps_mcp_stdio.err.log"
