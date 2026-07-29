# TPGK — User Manual (English)

## Table of Contents

1. [Quick Start](#1-quick-start)
2. [Interface](#2-interface)
3. [TPGK Commands](#3-tpgk-commands)
4. [AI Chat](#4-ai-chat)
5. [History](#5-history)
6. [Notes](#6-notes)
7. [Tabs & Windows](#7-tabs--windows)
8. [Preferences](#8-preferences)
9. [Signals & Encoding](#9-signals--encoding)
10. [Shell Integration (OSC 133)](#10-shell-integration-osc-133)
11. [Troubleshooting](#11-troubleshooting)

---

## 1. Quick Start

```bash
cd tpgk
./tpgk.sh
```

Or:

```bash
source .venv/bin/activate
python -m tpgk
```

---

## 2. Interface

### Menu Bar

- **File**: New Tab, New Window, Open File Manager Here, Close Tab/Window, Quit
- **Edit**: Copy, Paste, Paste Selection, Select All, Preferences
- **View**: Split (Single / Vertical / Horizontal), Show/Hide Tabs, Menu Bar, Scrollbar, Toolbar, Fullscreen, Zoom
- **Terminal**: Set Title, Encoding, Send Signal, Reset, Read-Only, Tab & Pane Navigation, Detach Tab
- **Tabs**: List of open tabs (click to switch)
- **Help**: About

### Toolbar

Enable via `View > Always Show Toolbar`. Contains:
- New Tab, New Window, Split V/H, Copy, Paste

### Command Palette (`/`)

**New:** Press `/` at the beginning of a line to open the **command palette**, an interactive popup with:
- List of all TPGK commands with descriptions
- **Fuzzy search**: type to filter
- **Arrow keys** to navigate, **Enter** to execute, **Esc** to dismiss

### Dynamic Title

Configurable: replace, prefix, suffix, or hide the title set by terminal
applications. Uses the VTE engine (same as GNOME Terminal) to detect titles
sent via escape sequences.

### Clickable URLs

**New:** TPGK automatically detects URLs in the terminal. Hover to see a hand cursor, then:
- **Ctrl+Click** a URL to open it in your browser
- **Direct click** a URL (with no active selection) to open it

---

## 3. TPGK Commands

Special commands start with `/` and are processed by TPGK, not the shell.

**New:** Press **Tab** while typing a command to **autocomplete**. For example,
`/hist` + Tab → `/history`.

**Tab into history:** on a regular (non-`/`) command line, **Tab** tries the shell's own
completion first (files, folders, git branches, ssh hosts, anything bash already knows how to
complete) — nothing changes there. Only if the line still looks the same right after (nothing
matched) does TPGK step in, on that same keypress, with the full-screen history panel, already
filtered by whatever you've typed so far — the same view as `/history`. Example: type
`ssh buzzqw` (bash finds nothing to complete there) and press Tab: the panel opens, pick the
matching command from history with the arrow keys, then press Enter to **fill the line** (it
isn't run right away); Esc restores what you had typed.

### /history

```
/history                  # Show recent commands (numbered 1-9)
/history ssh 167          # Search commands with "ssh" AND "167"
/history git push         # Search commands with "git" AND "push"
/history ssh -161         # Commands with "ssh" EXCLUDING those with "161"
/history :sql SELECT * FROM commands WHERE exit_code != 0
```
Prefix a term with `-` to exclude it from results.
Use `:sql` to run a read-only SQLite query directly on the
history database (SELECT, PRAGMA, EXPLAIN only).
![History search screen](img/history.png)

### /ai

```
/ai                       # Enter AI chat mode
/ai context 20 Explain this error  # Send last 20 lines as context
/ai off                    # Exit AI chat mode
```

**New:** `/ai context N <question>` automatically includes the last N visible
terminal lines as context in the AI prompt. Perfect for asking the AI to
analyze command output.

See [Section 4](#4-ai-chat) for details.

### /connect

```
/connect                  # Show all configured providers with live ping
/connect ollama           # Connect to Ollama (auto-detect models)
/connect openai           # Connect to OpenAI
```

The bare `/connect` command performs a **live ping** to providers and
shows which ones are reachable. When selecting a provider (press `1`-`9`),
TPGK auto-detects available models from Ollama (`/api/tags`) and
Custom APIs (`/models`), presenting them in an interactive list.

### /wnotes

```
/wnotes Meeting 7/24: decide tech stack
/wnotes -project.md TODO: refactor auth module
```

Saves a timestamped note to the configured notes file.

**New:** Right-click selected text → **Add to Note** to append the selection
directly to your notes file.

### /onotes

```
/onotes                   # Open default notes file in editor
/onotes -project.md       # Open project.md in editor
```

The editor is configurable in `Preferences > Notes`.

---

## 4. AI Chat

### 4.1 Supported Providers

| Provider | Type | Default Model | API Key |
|----------|------|--------------|---------|
| OpenAI | Cloud | `gpt-4o` | Yes |
| Claude (Anthropic) | Cloud | `claude-sonnet-4-6` | Yes |
| Google Gemini | Cloud | `gemini-2.5-flash` | Yes |
| DeepSeek | Cloud | `deepseek-chat` | Yes |
| Ollama | Local | `llama3` (auto-detected) | No |
| Custom API | Local/Remote | configurable (auto-detected) | Optional |

All providers stream responses. While waiting, TPGK shows the
**● Thinking** indicator.

**New:** AI responses can be cancelled with `Ctrl+C` — no orphaned threads.

### 4.2 Configuration

1. Go to `Edit > Preferences > AI`
2. Enter API keys for cloud providers
3. For Ollama: no API key needed. Ensure `ollama serve` is running
4. For Custom: set your endpoint URL
5. **New:** Set a custom **System Prompt** per provider to define the AI
   assistant's persona and behavior

### 4.3 Chat

```bash
/ai
```

```
=== AI Chat Mode: Ollama (Local) (llama3) ===
Type your message and press Enter. Type /ai off to exit.

● Thinking
Docker is a containerization platform that...
```

Exit with `/ai off` or `Esc`.

### 4.4 /ai context — Output Analysis

```
/ai context 30 why is the build failing?
```

TPGK automatically attaches the last 30 terminal lines as context:

```
Context: last 30 lines of terminal output:

```
npm ERR! code ENOENT
npm ERR! syscall open
...
```

Question: why is the build failing?
```

### 4.5 Auto-Detecting Models

```
/connect ollama
```

TPGK queries `http://localhost:11434/api/tags` and shows:

```
Ollama (Local) — 3 models:
  [1] llama3 (current)
  [2] codellama
  [3] mistral
Press 1..9 to select, any other key for default.
```

### 4.6 Custom API

Any OpenAI-compatible server:
- **llama.cpp**: `http://localhost:8080/v1/chat/completions`
- **vLLM**: `http://localhost:8000/v1/chat/completions`
- **LM Studio**: `http://localhost:1234/v1/chat/completions`

---

## 5. History

### 5.1 Interactive Search (Ctrl+R)

Press `Ctrl+R` to start interactive search:

- **Type** to filter results
- **Arrow keys** to navigate
- **Enter** to execute the selected command
- **Esc** to cancel

A `reverse-i-search` style bar shows the result count.

### 5.2 Search with /history

```
/history ssh            # All commands containing "ssh"
/history git push       # Commands containing BOTH "git" and "push"
/history ssh -161       # Commands with "ssh" EXCLUDING those with "161"
/history -161           # All commands except those with "161"
/history :sql SELECT * FROM commands WHERE exit_code != 0
```

Search uses AND logic: all terms must appear in the command.
Prefix a term with `-` to exclude it (becomes NOT LIKE).
Use `:sql` to run read-only SQLite queries for advanced searches
(table: `commands` with columns `id`, `command`, `cwd`, `exit_code`, `timestamp`).

#### Useful SQL examples
```
/history :sql SELECT * FROM commands WHERE exit_code != 0 ORDER BY id DESC LIMIT 20
/history :sql SELECT * FROM commands WHERE cwd LIKE '%/projects%' ORDER BY id DESC
/history :sql SELECT command, COUNT(*) as cnt FROM commands GROUP BY command ORDER BY cnt DESC LIMIT 10
/history :sql SELECT * FROM commands WHERE timestamp > datetime('now','-1 day') ORDER BY id DESC
/history :sql SELECT * FROM commands WHERE exit_code = 127 ORDER BY id DESC
/history :sql SELECT * FROM commands WHERE cwd = '/home/user/project' ORDER BY id DESC LIMIT 30
```
Results are numbered (1-9). Press the number to re-execute.

### 5.3 Quick Replay

Press `Alt+1`-`Alt+9` at any time to replay recent commands from history.

---

## 6. Notes

### 6.1 Writing a Note

```bash
/wnotes Meeting notes: decisions made...
```

The note is saved with a timestamp in the configured file (default: `~/notes.md`):

```markdown
## 2026-07-24 14:30:00

Meeting notes: decisions made...
```

### 6.2 Adding Selected Text

**New:** Select text in the terminal, right-click, **Add to Note**.
The text is automatically appended with a timestamp.

### 6.3 Opening Notes

```bash
/onotes                   # Opens ~/notes.md with editor
/onotes -project.md       # Opens project.md
```

---

## 7. Tabs & Windows

### 7.1 Tab Management

| Action | Menu | Shortcut |
|--------|------|----------|
| New Tab | File > New Tab | `Ctrl+Shift+T` |
| Close Tab | File > Close Tab | `Ctrl+Shift+W` |
| Previous Tab | Terminal > Previous Tab | `Ctrl+PageUp` |
| Next Tab | Terminal > Next Tab | `Ctrl+PageDown` |
| Move Tab Left | Terminal > Move Tab Left | `Ctrl+Shift+PageUp` |
| Move Tab Right | Terminal > Move Tab Right | `Ctrl+Shift+PageDown` |
| Detach Tab | Terminal > Detach Tab | — |
| Rename Tab | Terminal > Set Title | `Ctrl+Shift+S` |

### 7.2 Split Pane (tmux-like)

`View > Split` offers three modes:
- **Single Panel**: one panel
- **Split Vertical**: two panels stacked vertically
- **Split Horizontal**: two panels side by side

`Ctrl+Alt+PageUp` / `Terminal > Previous Pane` to switch panes.

### 7.3 Detached Tabs

When you detach a tab (`Terminal > Detach Tab`), it opens in a **standalone window**
with a full menu bar (File, Edit, View, Terminal, Help), toolbar, and all
the features of the main window.

### 7.4 New Window

`File > New Window` or `Ctrl+Shift+N` opens a new independent window.

### 7.5 Fullscreen

`View > Full Screen` or `F11`.

### 7.6 Complete Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| `Ctrl+Shift+T` | New Tab |
| `Ctrl+Shift+N` | New Window |
| `Ctrl+Shift+W` | Close Tab |
| `Ctrl+Shift+Q` / `Ctrl+Q` | Close Window |
| `Ctrl+Shift+C` | Copy |
| `Ctrl+Shift+V` | Paste |
| `Ctrl+Shift+A` | Select All |
| `Ctrl+Shift+S` | Set Title |
| `Ctrl+Shift+R` | Reset Terminal |
| `Ctrl+Shift+X` | Reset and Clear |
| `Ctrl++` / `Ctrl+-` / `Ctrl+0` | Zoom In / Out / Reset |
| `Ctrl+R` | Interactive History Search |
| `Ctrl+U` | Kill line |
| `Ctrl+W` | Kill word |
| `Ctrl+L` | Clear screen |
| `Ctrl+C` | Interrupt (SIGINT) / Cancel AI |
| `Ctrl+D` | EOF (on empty line, closes the tab on exit) |
| `F11` | Fullscreen |
| `Ctrl+PageUp` / `Ctrl+PageDown` | Previous / Next Tab |
| `Ctrl+Shift+PageUp` / `Ctrl+Shift+PageDown` | Move Tab Left / Right |
| `Ctrl+Alt+PageUp` | Previous Pane (split mode) |
| `Alt+1..9` | Replay history command |
| `Ctrl+Shift+Up` / `Ctrl+Shift+Down` | Jump to previous / next prompt (OSC 133) |
| `Ctrl+Click` URL | Open URL in browser |
| `Tab` (after `/`) | Autocomplete TPGK command |
| `/` (start of line) | Open command palette |

---

## 8. Preferences

`Edit > Preferences` opens a 6-tab settings window:

**New:** Changes are applied **immediately** without restart (live-reload).
Changing font, colors, scheme, or terminal size takes effect instantly.

### General
- Initial and dynamic title
- Login shell, custom command
- **Terminal size**: columns × rows (default: 80×24). Determines the window
  size at startup. Can be changed live
- **Scrollbar position** (right, left, disabled)
- Scrollback lines (0 = unlimited)
- Scroll on output/keystroke
- Confirm close, auto-copy selection, warn multiline paste
- Custom file manager

### Appearance
- **Native font chooser** (Gtk.FontChooserDialog) instead of free-text entry.
  Pick font family and size with a graphical selector
- Bold text
- Color scheme (8 presets: Dark, Light, Solarized Dark/Light, Gruvbox Dark, Monokai, Nord, Matrix)
- **Individual colors**: foreground, background, cursor, highlight text, highlight background
  (with color picker for each)
- **Tab title colors**: normal and active
- **Cursor shape**: block, underline, ibeam
- Cursor blink
- Transparency (opacity 0.3-1.0)

### Colors
- **16-color palette editor** with per-color pickers:
  Black, Red, Green, Yellow, Blue, Magenta, Cyan, White,
  Bright Black/Red/Green/Yellow/Blue/Magenta/Cyan/White
- Buttons: **Load Preset** (load from Dark, Light, Solarized, Gruvbox, Monokai, Nord, Matrix), **Save As Custom**, **Reset to Default**

### Compatibility
- **Backspace and Delete key behavior**: Auto-detect, ASCII DEL (127), Escape sequence, Control-H (8)
- Default encoding (13 options: UTF-8, ISO-8859-1, ISO-8859-15, UTF-16, UTF-16BE, UTF-16LE, CP1252, CP850, ASCII, KOI8-R, Shift_JIS, EUC-JP, GBK)
- **OSC 133 shell integration** toggle (enables prompt/command/exit-code tracking for bash/zsh)

### AI
- API key and model for OpenAI, Claude, Gemini, DeepSeek
- URL, API key and model for Ollama and Custom
- **New: System Prompt** customizable per provider. Define the AI assistant's
  persona and behavior

### Notes
- Notes directory (default: `~/`)
- Default notes file (default: `notes.md`)
- Editor command (default: `nano`)

---

## 9. Signals & Encoding

### 9.1 Sending a Signal

`Terminal > Send Signal`:

**New:** Signals are sent to the **foreground process group** (e.g., the running
command like `find`, `yes`, `tail -f`), not just the bash shell. This means
`SIGKILL` terminates the foreground process, not your shell.

| Signal | Typical Use |
|--------|-------------|
| **SIGTERM** (15) | Graceful termination |
| **SIGKILL** (9) | Force kill |
| **SIGHUP** (1) | Hangup |
| **SIGINT** (2) | Interrupt (Ctrl+C) |
| **SIGQUIT** (3) | Quit with core dump |
| **SIGSTOP** (19) | Suspend process |
| **SIGCONT** (18) | Resume process |
| **SIGUSR1** (10) | User signal 1 |
| **SIGUSR2** (12) | User signal 2 |

### 9.2 Changing Encoding

`Terminal > Set Encoding` to change the current tab's encoding.

Supported encodings: UTF-8, ISO-8859-1 (Latin-1), ISO-8859-15 (Latin-9),
UTF-16, UTF-16BE, UTF-16LE, CP1252, CP850, ASCII, KOI8-R, Shift_JIS, EUC-JP, GBK.

---

## 10. Shell Integration (OSC 133)

**New:** TPGK supports shell integration via OSC 133 sequences to track
prompts, commands, and exit codes without `/proc` hacking.

### Features

- **Ctrl+Shift+Up/Down**: jump between prompts in the scrollback buffer
- **Right-click > Copy Command Output**: copy the output of the last command
- **Visual margin markers**: a green bar appears next to each prompt after a
  successful command (exit code 0); a red bar appears after a failed command
- **Exit code tracking**: exit codes are visible via margin markers and stored
  internally for future scripting features

### Activation

Enable in `Preferences > Compatibility > OSC 133`.

When enabled, a setup script `~/.config/tpgk/osc-setup.sh` is created. Run it
to add the integration to your shell config:

```bash
bash ~/.config/tpgk/osc-setup.sh
```

**Restart TPGK** — the runtime script `~/.config/tpgk/osc133.sh` is generated
automatically at startup. After running the setup script, restart your shell
or run `source ~/.bashrc`.

### How It Works

- **Prompt start** (`ESC ] 133 ; A`): marks the start of a new prompt
- **Command start** (`ESC ] 133 ; C`): marks the start of command execution
- **Output end** (`ESC ] 133 ; D ; exitcode`): marks the end with exit code

Supports **bash** (via `PROMPT_COMMAND` and `trap DEBUG`) and **zsh** (via
`preexec`/`precmd` hooks).

---

## 11. Troubleshooting

### TPGK won't start

```bash
# Verify GTK3 and VTE are installed
python3 -c "import gi; gi.require_version('Gtk','3.0'); gi.require_version('Vte','2.91'); print('OK')"

# On Arch:
sudo pacman -S gtk3 vte3 python-gobject
```

### / commands don't work

- Make sure `/` is the **first character** of the line
- Use the **command palette**: press `/` for the interactive popup
- Alternatively use **Tab** to autocomplete commands (e.g., `/his` + Tab → `/history`)
- Press `Esc` to cancel

### Strange characters / wrong encoding

- Change encoding: `Terminal > Set Encoding > UTF-8`
- Check `echo $LANG` (should be `en_US.UTF-8`)

### Reset terminal

- `Terminal > Reset` or `Ctrl+Shift+R`
- `Terminal > Reset and Clear` or `Ctrl+Shift+X`

### Corrupt configuration

```bash
rm -rf ~/.config/tpgk/
```

TPGK will create a clean configuration on next startup.

### Configuration files

```
~/.config/tpgk/
├── settings.json    # All settings (50+ keys)
├── history.db       # SQLite command history database
└── osc133.sh        # Shell integration script (if enabled)
```

---

## Quick Reference

```
/history [terms|-term|:sql SQL]   Search command history
/ai                  Enter AI chat mode
/ai context N q      Send last N lines as AI context
/ai off              Exit AI chat mode
/connect [provider]  Connect to AI provider (with model auto-detection)
/wnotes [-f] text    Save a timestamped note
/onotes [-f]         Open notes in editor
/help                Show all commands or press / for palette

Ctrl+R               Interactive history search
Ctrl+U               Kill line
Ctrl+W               Kill word
Ctrl+C               Interrupt process / cancel AI response
Ctrl+L               Clear screen
Ctrl+Click URL       Open URL in browser
Tab (after /)        Autocomplete command
Alt+1..9             Replay history command
/                    Open command palette
```

---

## Author & License

**TPGK Terminal** — Andres Zanzani, 2026

Licensed under the **European Union Public Licence (EUPL) 1.2**.

https://github.com/buzzqw/tpq
