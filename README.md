# TPGK — Terminal Python GTK

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue)](https://python.org)
[![GTK3](https://img.shields.io/badge/GTK-3-green)](https://gtk.org)
[![VTE](https://img.shields.io/badge/VTE-2.91-orange)](https://wiki.gnome.org/Apps/Terminal/VTE)
[![License](https://img.shields.io/badge/License-EUPL%201.2-blue)](LICENSE)

**TPGK** is an advanced terminal emulator for Linux built with Python, GTK3, and VTE.
It combines a full-featured terminal with AI chat capabilities, command history
search, and a built-in notes system.

> TPGK uses **VTE** (the same engine as GNOME Terminal) for perfect scroll,
> selection, and copy-paste behavior.

- **[English manual](manual_en.md)**
- **[Manuale italiano](manual_it.md)**

---

## Features

### Core Terminal
- Full terminal emulation via **VTE** (xterm-256color, true color)
- Tabs with **detach**, **move**, **reorder**, **rename**
- **Split screen** (tmux-like): single, vertical, horizontal panels
- **Scrollback** with configurable limit (or unlimited, `0`)
- **Scrollbar position**: right, left, or disabled
- **Toolbar**, **menu bar**, **scrollbar** toggles
- 8 color schemes: Dark, Light, Solarized Dark, Solarized Light,
  Gruvbox Dark, Monokai, Nord, Matrix
- **Custom 16-color palette** editor with presets
- **Clickable URLs** — Ctrl+Click or direct click to open in browser
- **Command palette** — press `/` for interactive popup with fuzzy search

### AI Chat (built-in)
- `/ai` — Chat with AI directly in the terminal
- `/ai context N <question>` — Include terminal output as AI context
- `Ctrl+C` to cancel AI responses (no orphaned threads)
- `/connect [provider]` — Interactive provider/model selection with auto-detection
- 6 providers: OpenAI, Claude, Gemini, DeepSeek, Ollama (local), Custom
- Streaming responses with busy indicator ("● Thinking")
- **System Prompt** per provider — customize AI persona and behavior

### Smart Commands
| Command | Description |
|---------|-------------|
| `/history [terms]` | Search command history |
| `/ai` | Enter AI chat mode |
| `/ai context N q` | Include last N lines as AI context |
| `/ai off` | Exit AI chat mode |
| `/connect [provider]` | Select AI provider/model |
| `/wnotes [-file.md] text` | Save a timestamped note |
| `/onotes [-file.md]` | Open notes in editor |
| `/help` | Show commands and shortcuts |
| `/clear` or `/cls` | Clear the screen |

### History
- **SQLite-backed** command history (`~/.config/tpgk/history.db`)
- **Ctrl+R**: Interactive reverse-i-search
- `/history ssh 167`: AND logic search, numbered list with digit replay
- **Alt+1..9**: Re-execute a history result

### Notes
- `/wnotes` — Save timestamped notes to markdown
- `/onotes` — Open notes in configured editor
- **Right-click → Add to Note** — Append selected text to notes

### Preferences (live-reload)
- **Font chooser** — native Gtk.FontChooserDialog
- 8 color schemes with instant live preview
- 16-color palette editor
- **Terminal size** (cols × rows) determines window dimensions
- AI API keys, models, URLs, and system prompts
- Shell command, encoding, cursor, transparency, and more
- All changes applied **immediately without restart**

### Signals & Process Control
- **Send Signal** menu (SIGTERM, SIGKILL, SIGHUP, SIGINT, etc.)
- Signals target the **foreground process group** (not just bash)
- 13 encodings (UTF-8 through GBK)
- Shell integration via OSC 133 (bash/zsh)

---

## Installation

### Quick Install
```bash
git clone https://github.com/buzzqw/TPGK.git tpgk
cd tpgk
chmod +x setup.sh
./setup.sh
```

### Manual Install
```bash
# System dependencies (Arch)
sudo pacman -S gtk3 vte3 python-gobject

# Clone and create venv
git clone https://github.com/buzzqw/TPGK.git tpgk
cd tpgk
uv venv .venv --system-site-packages
source .venv/bin/activate
uv pip install requests
```

### Run
```bash
./tpgk.sh
# or
source .venv/bin/activate && python -m tpgk
```

---

## Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| `Ctrl+Shift+T` | New Tab |
| `Ctrl+Shift+N` | New Window |
| `Ctrl+Shift+W` | Close Tab |
| `Ctrl+Shift+Q` | Close Window |
| `Ctrl+Shift+C` | Copy |
| `Ctrl+Shift+V` | Paste |
| `Ctrl+Shift+A` | Select All |
| `Ctrl+Shift+S` | Set Title |
| `Ctrl+Shift+R` | Reset Terminal |
| `Ctrl+Shift+X` | Reset and Clear |
| `Ctrl++` / `Ctrl+-` / `Ctrl+0` | Zoom In / Out / Reset |
| `Ctrl+R` | Interactive History Search |
| `Ctrl+U` | Kill Line |
| `Ctrl+W` | Kill Word |
| `Ctrl+L` | Clear Screen |
| `Ctrl+C` | Interrupt / Cancel AI |
| `Ctrl+D` | EOF (closes tab on exit) |
| `F11` | Fullscreen |
| `Ctrl+Click` URL | Open URL in browser |
| `Alt+1..9` | Re-execute history |
| `/` (start of line) | Open command palette |
| `Tab` (after `/`) | Autocomplete command / show provider list for `/connect` |

---

## Configuration

Settings in `~/.config/tpgk/settings.json`.

All options via **Edit > Preferences** (6 tabs: General, Appearance, Colors,
Compatibility, AI, Notes):

- Font (native chooser), size, bold
- Color scheme (8 presets) with live preview
- Terminal size (cols × rows)
- Scrollback, scrollbar position
- Cursor shape, blink, color
- 16-color palette with presets
- AI provider keys, models, URLs, system prompts
- Shell command, login shell, encoding
- Notes directory, file, editor

---

## Shell Integration (OSC 133)

TPGK can generate a shell integration script at `~/.config/tpgk/osc133.sh` that
tracks prompts, commands, and exit codes for perfect command boundaries.

1. Enable the setting: `"osc133": true` in `~/.config/tpgk/settings.json`
   (or via the Preferences dialog, once the UI toggle is added).
2. Restart TPGK — the script is auto-generated at startup.
3. Add this line to your `~/.bashrc`:
```bash
[ -f ~/.config/tpgk/osc133.sh ] && source ~/.config/tpgk/osc133.sh
```

The script supports both **bash** and **zsh**.

---

## Requirements

- **Python** >= 3.10
- **GTK3** (`gtk3`)
- **VTE 2.91** (`vte3`)
- **PyGObject** (`python-gobject`)
- **requests** (for AI clients)
- **Linux** with X11 or Wayland

---

## Project Structure

```
tpgk/
├── __init__.py              # Package init
├── __main__.py              # Gtk.Application entry point
├── window.py                # MainWindow, menus, tabs, toolbar, detached window
├── terminal.py              # VTE terminal wrapper with AI/history/notes
├── history.py               # SQLite command history with search
├── ai_client.py             # Multi-provider AI API client
├── notes.py                 # Timestamped notes manager
├── settings.py              # JSON config singleton (50+ settings)
├── settings_dialog.py       # GTK preferences dialog (6 tabs)
├── tests/
│   ├── test_tpgk.py         # Core unit tests
│   ├── test_tpgk_extra.py   # Edge-case tests
│   └── test_new_features.py # New feature tests
├── setup.sh                 # One-command installer
├── tpgk.sh                  # Launcher script
├── README.md                # This file
├── manual_en.md             # Full English user manual
└── manual_it.md             # Full Italian user manual
```

---

## License

**EUPL 1.2** (European Union Public License)

**Author:** Andres Zanzani (buzzqw)

---

## Acknowledgements

- [VTE](https://wiki.gnome.org/Apps/Terminal/VTE) — The GNOME terminal widget
- [GTK3](https://gtk.org) — Cross-platform GUI toolkit
- [PyGObject](https://pygobject.gnome.org) — Python bindings for GObject libraries
