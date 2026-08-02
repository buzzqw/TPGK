#!/bin/bash
SCRIPT_DIR="$(dirname "$(readlink -f "$0")")"
VENV_PYTHON="$SCRIPT_DIR/.venv/bin/python3"
if [ -x "$VENV_PYTHON" ]; then
    PYTHON_BIN="$VENV_PYTHON"
else
    PYTHON_BIN="python3"
fi
if [ -d "$1" ]; then
    cd "$1" || cd "$HOME"
    shift
fi
exec env PYTHONPATH="$SCRIPT_DIR" "$PYTHON_BIN" -m tpgk "$@"

#env PYTHONPATH=$HOME/tpgk $HOME/tpgk/.venv/bin/python3 -m tpgk
