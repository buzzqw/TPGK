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
- **System Stats bar**: CPU, RAM, disk updated every 3s via psutil (View > Show System Stats)
- **SSH detection**: stats label adapts when inside an SSH session
- **Scrollback** with configurable limit (or unlimited, `0`)
- **Scrollbar position**: right, left, or disabled
- **Toolbar**, **menu bar**, **scrollbar**, **stats bar** toggles
- 8 color schemes: Dark, Light, Solarized Dark, Solarized Light,
  Gruvbox Dark, Monokai, Nord, Matrix
- **Custom 16-color palette** editor with presets
- **Clickable URLs** — Ctrl+Click to open in browser
- **Command palette** — press `Ctrl+Shift+P` for an interactive popup with fuzzy search

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
| `/history [terms\|-term\|:sql SQL]` | Search command history (AND logic, exclusion with -, raw SQL) |
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
- `/history ssh 167`: AND logic, `/history ssh -161`: exclusion, `/history :sql SELECT ...`: raw SQL
- **SQL examples**: failed commands (`exit_code != 0`), by directory (`cwd LIKE '%/proj%'`), most used (`GROUP BY command`), last day (`timestamp > datetime('now','-1 day')`)
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
uv pip install requests psutil
```

### Run
```bash
./tpgk.sh
# or
source .venv/bin/activate && python -m tpgk
```

### Command Line
```bash
tpgk /path/to/project                 # Open a terminal in a directory
tpgk --new-window                     # Open another independent window
tpgk --no-restore                     # Start without restoring the last session
tpgk --execute git status             # Run a command in a new terminal window
```

Each command-line invocation starts an independent TPGK process and window.
This also means a new launch is not intercepted by an already running instance.

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
| `Ctrl+Shift+Up` / `Ctrl+Shift+Down` | Jump between prompts (OSC 133) |
| `Ctrl++` / `Ctrl+-` / `Ctrl+0` | Zoom In / Out / Reset |
| `Ctrl+R` | Interactive History Search |
| `Ctrl+U` | Kill Line |
| `Ctrl+W` | Kill Word |
| `Ctrl+L` | Clear Screen |
| `Ctrl+C` | Interrupt / Cancel AI / Exit history search |
| `Ctrl+D` | EOF (closes tab on exit) |
| `F11` | Fullscreen |
| `Ctrl+Click` URL | Open URL in browser |
| `Alt+1..9` | Re-execute history |
| `Ctrl+Shift+P` | Open command palette |
| `Tab` (after `/`) | Autocomplete command / show provider list for `/connect` |

---

## Configuration

Settings in `~/.config/tpgk/settings.json`.

All options via **Edit > Preferences** (7 tabs: General, Appearance, Colors,
Compatibility, AI, Notes, About):

- Font (native chooser), size, bold
- Color scheme (8 presets) with live preview
- Terminal size (cols × rows)
- Scrollback, scrollbar position
- Cursor shape, blink, color
- 16-color palette with presets
- AI provider keys, models, URLs, system prompts
- Shell command, login shell, encoding
- OSC 133 shell integration (bash/zsh)
- Notes directory, file, editor

---

## Shell Integration (OSC 133)

TPGK supports shell integration via OSC 133 sequences to track
prompts, commands, and exit codes.

### Features
- **`Ctrl+Shift+Up/Down`** — jump between prompts in the scrollback buffer
- **Right-click > Copy Command Output** — copy the output of the last command
- **Visual margin markers** — green bar (success) or red bar (failure) at every prompt
- **Exit code tracking** — exit codes shown via margin markers and available for scripting

### Activation

1. Enable in **Preferences > Compatibility > OSC 133**.
2. A setup script `osc-setup.sh` is created in `~/.config/tpgk/`. Run it:
   ```bash
   bash ~/.config/tpgk/osc-setup.sh
   ```
3. Restart TPGK — the integration script `osc133.sh` is auto-generated at startup.

The integration supports both **bash** and **zsh**.

---

## Requirements

- **Python** >= 3.10
- **GTK3** (`gtk3`)
- **VTE 2.91** (`vte3`)
- **PyGObject** (`python-gobject`)
- **requests** (for AI clients)
- **Linux** with X11 or Wayland

---

## Performance

Measured on a typical Linux desktop (average of 3 cold-launch runs, process
start to window mapped):

| Metric | Value |
|---|---|
| Startup time | ~0.7s |
| Idle memory (RSS) | ~84 MB |

The `requests` library — only needed for AI chat — is imported lazily on
first use instead of at startup. This trims ~125ms off startup time and
~20MB off idle memory versus importing it eagerly.

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
├── settings_dialog.py       # GTK preferences dialog (7 tabs)
├── system_stats.py          # CPU/RAM/Disk stats collector
├── tests/
│   ├── test_tpgk.py         # Core unit tests
│   ├── test_tpgk_extra.py   # Edge-case tests
│   └── test_new_features.py # New feature tests
├── setup.sh                 # One-command installer
├── tpgk.sh                  # Launcher script
├── versiona.sh              # Release automation (commit, tag, GitHub release)
├── README.md                # This file
├── manual_en.md             # Full English user manual
└── manual_it.md             # Full Italian user manual
```

---

## Support the Project

TPGK is free and open-source software built in spare time. If it is useful to
you, consider supporting its development with a coffee.

<div align="center">

[![Donate with PayPal](https://img.shields.io/badge/Donate-PayPal-00457C?style=for-the-badge&logo=paypal)](https://www.paypal.com/cgi-bin/webscr?cmd=_donations&business=azanzani@gmail.com&item_name=Support+TPGK+Project)

</div>

---

## License

**EUPL 1.2** (European Union Public License)

**Author:** Andres Zanzani (buzzqw)

---

## Acknowledgements

- [VTE](https://wiki.gnome.org/Apps/Terminal/VTE) — The GNOME terminal widget
- [GTK3](https://gtk.org) — Cross-platform GUI toolkit
- [PyGObject](https://pygobject.gnome.org) — Python bindings for GObject libraries
