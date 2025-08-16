#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOGDIR="${LMSPS_LOGDIR:-$ROOT_DIR/logs}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
export PYTHONPATH="$ROOT_DIR/src${PYTHONPATH:+:$PYTHONPATH}"
mkdir -p "$LOGDIR"
exec "$PYTHON_BIN" -m lmsps.server 2>>"$LOGDIR/start_ps_mcp_stdio.err.log"
