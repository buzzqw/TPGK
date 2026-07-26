#!/bin/bash
set -e

echo "========================================"
echo "  TPGK Terminal - Setup"
echo "========================================"
echo ""

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"

# --- Detect distro ---
OS_ID=""
OS_ID_LIKE=""
if [ -f /etc/os-release ]; then
    . /etc/os-release
    OS_ID="${ID:-}"
    OS_ID_LIKE="${ID_LIKE:-}"
else
    OS_ID="$(uname -s)"
fi
DISTRO_MATCH="$OS_ID $OS_ID_LIKE"

# --- Install uv if missing ---
if ! command -v uv &>/dev/null; then
    echo "[1/4] Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
    if ! command -v uv &>/dev/null; then
        echo "ERROR: Failed to install uv."
        exit 1
    fi
    echo "       uv installed: $(uv --version)"
else
    echo "[1/4] uv already installed: $(uv --version)"
fi

# --- System dependencies ---
echo "[2/4] Checking system dependencies (GTK3 + VTE)..."

case "$DISTRO_MATCH" in
    *debian*|*ubuntu*)
        PKGS="libgtk-3-dev libvte-2.91-dev python3-gi python3-gi-cairo gir1.2-gtk-3.0 gir1.2-vte-2.91"
        INSTALL="sudo apt-get update -qq && sudo apt-get install -y $PKGS"
        ;;
    *rhel*|*centos*|*fedora*)
        PKGS="gtk3-devel vte291-devel python3-gobject"
        INSTALL="sudo dnf install -y $PKGS"
        ;;
    *arch*)
        PKGS="gtk3 vte3 python-gobject"
        INSTALL="sudo pacman -Sy --noconfirm $PKGS"
        ;;
    *suse*)
        PKGS="gtk3-devel vte-devel python3-gobject typelib-1_0-Gtk-3_0 typelib-1_0-Vte-2.91"
        INSTALL="sudo zypper --non-interactive install $PKGS"
        ;;
    *)
        echo "       Unrecognized distro. Skipping system packages."
        echo "       Required: gtk3, vte3, python-gobject (PyGObject)"
        INSTALL=""
        ;;
esac

if [ -n "$INSTALL" ]; then
    echo "       Installing: $PKGS"
    eval "$INSTALL" || echo "       WARNING: install failed, continuing anyway."
fi

# --- Virtual environment ---
echo "[3/4] Creating virtual environment..."
if [ -d "$VENV_DIR" ]; then
    rm -rf "$VENV_DIR"
fi
uv venv "$VENV_DIR" --system-site-packages
source "$VENV_DIR/bin/activate"
uv pip install --python "$VENV_DIR/bin/python" requests psutil

# Pre-compile bytecode
"$VENV_DIR/bin/python" -m compileall -q "$SCRIPT_DIR"

# --- Desktop entry ---
echo "[4/4] Creating application menu entry..."
if [ "$(uname -s)" = "Linux" ]; then
    DESKTOP_DIR="$HOME/.local/share/applications"
    DESKTOP_FILE="$DESKTOP_DIR/tpgk-terminal.desktop"
    mkdir -p "$DESKTOP_DIR"
    cat > "$DESKTOP_FILE" <<EOF
[Desktop Entry]
Type=Application
Name=TPGK Terminal
Comment=Terminal Python GTK with AI chat, history search and notes
Exec=$SCRIPT_DIR/tpgk.sh
Icon=utilities-terminal
Terminal=false
Categories=System;TerminalEmulator;
StartupNotify=false
EOF
    chmod +x "$DESKTOP_FILE"
    command -v update-desktop-database &>/dev/null && update-desktop-database "$DESKTOP_DIR" &>/dev/null
    echo "       Menu entry created: $DESKTOP_FILE"
fi

echo ""
echo "========================================"
echo "  Setup complete!"
echo "========================================"
echo ""
echo "  Run TPGK:  $SCRIPT_DIR/tpgk.sh"
echo "  Activate:  source $VENV_DIR/bin/activate"
echo "  Then:      python -m tpgk"
echo ""
