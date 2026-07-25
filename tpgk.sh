#!/bin/bash
SCRIPT_DIR="$(dirname "$(readlink -f "$0")")"
VENV_PYTHON="$SCRIPT_DIR/.venv/bin/python3"
if [ -x "$VENV_PYTHON" ]; then
    PYTHON_BIN="$VENV_PYTHON"
else
    PYTHON_BIN="python3"
fi
cd "$HOME"
exec env PYTHONPATH="$(dirname "$SCRIPT_DIR")" "$PYTHON_BIN" -m tpgk "$@"
