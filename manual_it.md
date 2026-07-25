# TPGK — Manuale d'Uso (Italiano)

## Indice

1. [Avvio Rapido](#1-avvio-rapido)
2. [Interfaccia](#2-interfaccia)
3. [Comandi TPGK](#3-comandi-tpgk)
4. [AI Chat](#4-ai-chat)
5. [History](#5-history)
6. [Notes](#6-notes)
7. [Tabs e Finestre](#7-tabs-e-finestre)
8. [Preferenze](#8-preferenze)
9. [Segnali e Encoding](#9-segnali-e-encoding)
10. [Shell Integration (OSC 133)](#10-shell-integration-osc-133)
11. [Risoluzione Problemi](#11-risoluzione-problemi)

---

## 1. Avvio Rapido

```bash
cd tpgk
./tpgk.sh
```

Oppure:

```bash
source .venv/bin/activate
python -m tpgk
```

---

## 2. Interfaccia

### Menu Bar

- **File**: Nuovo Tab, Nuova Finestra, Apri Gestore File Qui, Chiudi Tab/Finestra, Esci
- **Edit**: Copia, Incolla, Incolla Selezione, Seleziona Tutto, Preferenze
- **View**: Split (Singolo / Verticale / Orizzontale), Mostra/Nascondi Tabs, Menu Bar, Scrollbar, Toolbar, Fullscreen, Zoom
- **Terminal**: Imposta Titolo, Encoding, Invia Segnale, Reset, Read-Only, Navigazione Tab e Pane, Detach Tab
- **Tabs**: Lista dei tab aperti (click per passare)
- **Help**: About

### Toolbar

Attivabile da `View > Always Show Toolbar`. Contiene:
- Nuovo Tab, Nuova Finestra, Split V/H, Copia, Incolla

### Command Palette (`/`)

**Novita':** Premi `/` a inizio riga per aprire la **command palette**, un popup interattivo
con:
- Lista di tutti i comandi TPGK con descrizione
- **Fuzzy search**: digita per filtrare
- **Frecce su/giù** per navigare, **Enter** per eseguire, **Esc** per chiudere

### Titolo Dinamico

Configurabile: sostituisce, precede, segue, o non mostra il titolo impostato
dalle applicazioni terminale. Utilizza il motore VTE (lo stesso di GNOME
Terminal) per rilevare i titoli inviati via escape sequence.

### URL cliccabili

**Novita':** TPGK riconosce automaticamente gli URL nel terminale. Passa il mouse
per vedere il cursore a mano, poi:
- **Ctrl+Click** su un URL per aprirlo nel browser
- **Click diretto** su un URL (senza selezione attiva) per aprirlo

---

## 3. Comandi TPGK

I comandi speciali iniziano con `/` e vengono processati da TPGK, non dalla shell.

**Novita':** Premi **Tab** mentre digiti un comando per **autocompletare**. Ad esempio,
`/hist` + Tab → `/history`.

### /history

```
/history                  # Mostra ultimi comandi (lista numerata 1-9)
/history ssh 167          # Cerca comandi con "ssh" E "167"
/history git push         # Cerca comandi con "git" E "push"
```

Dopo la lista, premi `1`...`9` per rieseguire il comando corrispondente.
In qualsiasi momento, premi `Alt+1`...`Alt+9` per ripetere gli ultimi comandi.

### /ai

```
/ai                       # Entra in modalita' chat AI
/ai context 20 Spiega questo errore  # Invia ultime 20 righe come contesto
/ai off                    # Esci dalla chat AI
```

**Novita':** `/ai context N <domanda>` include automaticamente le ultime N righe
visibili del terminale come contesto nel prompt AI. Perfetto per chiedere all'AI
di analizzare l'output di un comando.

Vedi [Sezione 4](#4-ai-chat) per i dettagli.

### /connect

```
/connect                  # Mostra tutti i provider configurati con ping live
/connect ollama           # Connetti a Ollama (auto-detection modelli)
/connect openai           # Connetti a OpenAI
```

Il comando `/connect` senza argomenti effettua un **ping live** ai provider e
mostra quali sono raggiungibili. Selezionando un provider (premendo `1`-`9`),
TPGK rileva automaticamente i modelli disponibili da Ollama (`/api/tags`) e
Custom API (`/models`) e li presenta in una lista interattiva.

### /wnotes

```
/wnotes Riunione del 24/7: decidere stack tecnologico
/wnotes -progetto.md Da fare: refactor modulo auth
```

Salva una nota con timestamp nel file note predefinito.

**Novita':** Click destro su testo selezionato → **Add to Note** per aggiungere
la selezione direttamente al file note.

### /onotes

```
/onotes                   # Apre il file note predefinito nell'editor
/onotes -progetto.md      # Apre progetto.md nell'editor
```

L'editor e' configurabile in `Preferences > Notes`.

---

## 4. AI Chat

### 4.1 Provider Supportati

| Provider | Tipo | Modello predefinito | API Key |
|----------|------|----------------------|---------|
| OpenAI | Cloud | `gpt-4o` | Si |
| Claude (Anthropic) | Cloud | `claude-sonnet-4-6` | Si |
| Google Gemini | Cloud | `gemini-2.5-flash` | Si |
| DeepSeek | Cloud | `deepseek-chat` | Si |
| Ollama | Locale | `llama3` (auto-detected) | No |
| Custom API | Locale/Remoto | configurabile (auto-detected) | Opzionale |

Tutti i provider rispondono in streaming. Durante l'attesa della risposta,
TPGK mostra l'indicatore **● Thinking**.

**Novita':** La risposta AI puo' essere interrotta con `Ctrl+C` senza lasciare
thread in esecuzione.

### 4.2 Configurazione

1. Vai su `Edit > Preferences > AI`
2. Inserisci la API key per i provider cloud
3. Per Ollama: non serve API key. Assicurati che `ollama serve` sia in esecuzione
4. Per Custom: imposta l'URL del tuo endpoint
5. **Novita':** Puoi impostare un **System Prompt** personalizzato per ogni provider
   per definire il comportamento e la personalita' dell'assistente

### 4.3 Chat

```bash
/ai
```

```
=== AI Chat Mode: Ollama (Local) (llama3) ===
Type your message and press Enter. Type /ai off to exit.

● Thinking
Docker e' una piattaforma di containerizzazione che...
```

Esci con `/ai off` o `Esc`.

### 4.4 /ai context — Analisi dell'output

```
/ai context 30 perche' fallisce la build?
```

TPGK allega automaticamente le ultime 30 righe del terminale come contesto:

```
Context: last 30 lines of terminal output:

```
npm ERR! code ENOENT
npm ERR! syscall open
...
```

Question: perche' fallisce la build?
```

### 4.5 Auto-detection Modelli

```
/connect ollama
```

TPGK interroga `http://localhost:11434/api/tags` e mostra:

```
Ollama (Local) — 3 models:
  [1] llama3 (current)
  [2] codellama
  [3] mistral
Press 1..9 to select, any other key for default.
```

### 4.6 Custom API

Qualsiasi server compatibile con l'API OpenAI:
- **llama.cpp**: `http://localhost:8080/v1/chat/completions`
- **vLLM**: `http://localhost:8000/v1/chat/completions`
- **LM Studio**: `http://localhost:1234/v1/chat/completions`

---

## 5. History

### 5.1 Ricerca Interattiva (Ctrl+R)

Premi `Ctrl+R` per avviare la ricerca interattiva:

- **Digita** per filtrare i risultati
- **Frecce su/giu'** per navigare
- **Enter** per eseguire il comando selezionato
- **Esc** per annullare

Viene mostrata una barra in stile `reverse-i-search` con il conteggio dei risultati.

### 5.2 Ricerca con /history

```
/history ssh            # Tutti i comandi con "ssh"
/history git push       # Comandi con ENTRAMBI "git" e "push"
```

La ricerca usa logica AND: tutti i termini devono apparire nel comando.
I risultati sono numerati (1-9). Premi il numero per rieseguire.

### 5.3 Riesecuzione Rapida

Premi `Alt+1`...`Alt+9` in qualsiasi momento per rieseguire gli ultimi comandi
dalla history.

---

## 6. Notes

### 6.1 Scrivere una Nota

```bash
/wnotes Appunti sulla riunione: decisioni prese...
```

La nota viene salvata con timestamp nel file configurato (default: `~/notes.md`):

```markdown
## 2026-07-24 14:30:00

Appunti sulla riunione: decisioni prese...
```

### 6.2 Aggiungere Testo Selezionato

**Novita':** Seleziona testo nel terminale, click destro, **Add to Note**.
Il testo viene aggiunto automaticamente con timestamp.

### 6.3 Aprire le Note

```bash
/onotes                   # Apre ~/notes.md con l'editor
/onotes -progetto.md      # Apre progetto.md
```

---

## 7. Tabs e Finestre

### 7.1 Gestione Tab

| Azione | Menu | Shortcut |
|--------|------|----------|
| Nuovo Tab | File > New Tab | `Ctrl+Shift+T` |
| Chiudi Tab | File > Close Tab | `Ctrl+Shift+W` |
| Tab Precedente | Terminal > Previous Tab | `Ctrl+PageUp` |
| Tab Successivo | Terminal > Next Tab | `Ctrl+PageDown` |
| Sposta Tab a Sx | Terminal > Move Tab Left | `Ctrl+Shift+PageUp` |
| Sposta Tab a Dx | Terminal > Move Tab Right | `Ctrl+Shift+PageDown` |
| Stacca Tab | Terminal > Detach Tab | — |
| Rinomina Tab | Terminal > Set Title | `Ctrl+Shift+S` |

### 7.2 Split Pane (stile tmux)

`View > Split` offre tre modalita':
- **Single Panel**: un unico pannello
- **Split Vertical**: due pannelli in verticale
- **Split Horizontal**: due pannelli affiancati

`Ctrl+Alt+PageUp` / `Terminal > Previous Pane` per cambiare pannello.

### 7.3 Tab Detached

Quando stacchi un tab (`Terminal > Detach Tab`), si apre una **finestra indipendente**
con menu bar completo (File, Edit, View, Terminal, Help), toolbar, e tutte le
funzionalita' della finestra principale.

### 7.4 Nuova Finestra

`File > New Window` o `Ctrl+Shift+N` apre una nuova finestra indipendente.

### 7.5 Fullscreen

`View > Full Screen` o `F11`.

### 7.6 Scorciatoie Complete

| Scorciatoia | Azione |
|-------------|--------|
| `Ctrl+Shift+T` | Nuovo Tab |
| `Ctrl+Shift+N` | Nuova Finestra |
| `Ctrl+Shift+W` | Chiudi Tab |
| `Ctrl+Shift+Q` / `Ctrl+Q` | Chiudi Finestra |
| `Ctrl+Shift+C` | Copia |
| `Ctrl+Shift+V` | Incolla |
| `Ctrl+Shift+A` | Seleziona Tutto |
| `Ctrl+Shift+S` | Imposta Titolo |
| `Ctrl+Shift+R` | Reset Terminale |
| `Ctrl+Shift+X` | Reset e Pulisci |
| `Ctrl++` / `Ctrl+-` / `Ctrl+0` | Zoom In / Out / Reset |
| `Ctrl+R` | Ricerca history interattiva |
| `Ctrl+U` | Kill line (cancella riga) |
| `Ctrl+W` | Kill word (cancella parola) |
| `Ctrl+L` | Pulisci schermo |
| `Ctrl+C` | Interrompi (SIGINT) |
| `Ctrl+D` | EOF (a riga vuota, chiude il tab all'uscita) |
| `F11` | Fullscreen |
| `Ctrl+PageUp` / `Ctrl+PageDown` | Tab Precedente / Successivo |
| `Ctrl+Shift+PageUp` / `Ctrl+Shift+PageDown` | Sposta Tab a Sx / Dx |
| `Ctrl+Alt+PageUp` | Pannello Precedente (split mode) |
| `Alt+1..9` | Riesegui comando history |
| `Ctrl+Shift+Su` / `Ctrl+Shift+Giu'` | Salta al prompt precedente/successivo (OSC 133) |
| `Ctrl+Click` su URL | Apri URL nel browser |
| `Tab` (dopo `/`) | Autocompleta comando TPGK |
| `/` (a inizio riga) | Apri command palette |

---

## 8. Preferenze

`Edit > Preferences` apre la finestra con 6 tab:

**Novita':** Le modifiche vengono applicate **immediatamente** senza riavvio
(live-reload). Cambiare font, colori, schema, dimensione terminale ha effetto subito.

### General
- Titolo iniziale e dinamico
- Login shell, comando personalizzato
- **Dimensione terminale**: colonne × righe (default: 80×24). Determina la grandezza
  della finestra all'apertura. Modificabile live.
- **Posizione scrollbar** (destra, sinistra, disabilitata)
- Scrollback lines (0=illimitato)
- Scroll on output/keystroke
- Conferma chiusura, auto-copy selezione, warn paste multilinea
- File manager personalizzato

### Appearance
- **Font chooser nativo** (Gtk.FontChooserDialog) al posto del campo testo libero.
  Seleziona font e dimensione con un picker grafico
- Bold text
- Schema colori (8 preset: Dark, Light, Solarized Dark/Light, Gruvbox Dark, Monokai, Nord, Matrix)
- **Colori individuali**: foreground, background, cursore, testo selezione, sfondo selezione
  (con color picker per ciascuno)
- **Colori titoli tab**: normale e attivo
- **Forma cursore**: block, underline, ibeam
- Cursor blink
- Trasparenza (opacity 0.3-1.0)

### Colors
- **Editor palette 16-colori** con color picker per ciascuno:
  Black, Red, Green, Yellow, Blue, Magenta, Cyan, White,
  Bright Black/Red/Green/Yellow/Blue/Magenta/Cyan/White
- Pulsanti: **Load Preset** (carica da Dark, Light, Solarized, Gruvbox, Monokai, Nord, Matrix), **Save As Custom**, **Reset to Default**

### Compatibility
- **Comportamento tasti Backspace e Delete**: Auto-detect, ASCII DEL (127), Escape sequence, Control-H (8)
- Encoding predefinito (13 opzioni: UTF-8, ISO-8859-1, ISO-8859-15, UTF-16, UTF-16BE, UTF-16LE, CP1252, CP850, ASCII, KOI8-R, Shift_JIS, EUC-JP, GBK)
- **OSC 133 shell integration**: attiva/disattiva il tracciamento prompt/comandi/codici di uscita per bash/zsh

### AI
- API key e model per OpenAI, Claude, Gemini, DeepSeek
- URL, API key e model per Ollama e Custom
- **Novita': System Prompt** personalizzabile per ogni provider. Definisci personalita'
  e comportamento dell'assistente AI

### Notes
- Directory note (default: `~/`)
- File note predefinito (default: `notes.md`)
- Comando editor (default: `nano`)

---

## 9. Segnali e Encoding

### 9.1 Inviare un Segnale

`Terminal > Send Signal`:

**Novita':** I segnali vengono inviati al **foreground process group** (es. il
comando in esecuzione come `find`, `yes`, `tail -f`), non solo alla shell bash.
Questo significa che `SIGKILL` termina il processo in foreground, non la shell.

| Segnale | Uso Tipico |
|---------|------------|
| **SIGTERM** (15) | Terminazione gentile |
| **SIGKILL** (9) | Terminazione forzata |
| **SIGHUP** (1) | Hangup |
| **SIGINT** (2) | Interrupt (Ctrl+C) |
| **SIGQUIT** (3) | Quit con core dump |
| **SIGSTOP** (19) | Sospendi processo |
| **SIGCONT** (18) | Riattiva processo |
| **SIGUSR1** (10) | Segnale utente 1 |
| **SIGUSR2** (12) | Segnale utente 2 |

### 9.2 Cambiare Encoding

`Terminal > Set Encoding` per cambiare la codifica del tab corrente.

Encoding supportati: UTF-8, ISO-8859-1 (Latin-1), ISO-8859-15 (Latin-9),
UTF-16, UTF-16BE, UTF-16LE, CP1252, CP850, ASCII, KOI8-R, Shift_JIS, EUC-JP, GBK.

---

## 10. Shell Integration (OSC 133)

**Novita':** TPGK supporta l'integrazione shell via sequenze OSC 133 per tracciare
prompt, comandi e codici di uscita senza bisogno di `/proc` hacking.

### Funzionalita'

- **Ctrl+Shift+Su/Giu'**: salta tra i prompt nel buffer di scrollback
- **Click destro > Copy Command Output**: copia l'output dell'ultimo comando
- **Marker visivi a margine**: una barra verde appare accanto a ogni prompt dopo
  un comando riuscito (exit code 0); una barra rossa appare dopo un comando fallito
- **Tracciamento exit code**: i codici di uscita sono visibili via marker e memorizzati
  internamente per future funzionalita' di scripting

### Attivazione

Attiva l'opzione in `Preferences > Compatibility > OSC 133`.

All'attivazione, viene creato lo script di setup `~/.config/tpgk/osc-setup.sh`.
Eseguilo per aggiungere l'integrazione alla configurazione della shell:

```bash
bash ~/.config/tpgk/osc-setup.sh
```

**Riavvia TPGK** — lo script runtime `~/.config/tpgk/osc133.sh` viene generato
automaticamente all'avvio. Dopo aver eseguito lo script di setup, riavvia la
shell o esegui `source ~/.bashrc`.

### Funzionamento

- **Prompt start** (`ESC ] 133 ; A`): marca l'inizio di un nuovo prompt
- **Command start** (`ESC ] 133 ; C`): marca l'inizio dell'esecuzione comando
- **Output end** (`ESC ] 133 ; D ; exitcode`): marca la fine con codice di uscita

Supporta **bash** (tramite `PROMPT_COMMAND` e `trap DEBUG`) e **zsh** (tramite
`preexec`/`precmd` hooks).

---

## 11. Risoluzione Problemi

### TPGK non si avvia

```bash
# Verifica che GTK3 e VTE siano installati
python3 -c "import gi; gi.require_version('Gtk','3.0'); gi.require_version('Vte','2.91'); print('OK')"

# Su Arch:
sudo pacman -S gtk3 vte3 python-gobject
```

### I comandi / non funzionano

- Assicurati di scrivere `/` come **primo carattere** della riga
- Usa la **command palette**: premi `/` per il popup interattivo
- In alternativa usa **Tab** per autocompletare i comandi (es. `/his` + Tab → `/history`)
- Premi `Esc` per annullare

### Caratteri strani / encoding sbagliato

- Cambia encoding: `Terminal > Set Encoding > UTF-8`
- Verifica `echo $LANG` (dovrebbe essere `en_US.UTF-8`)

### Reset del terminale

- `Terminal > Reset` o `Ctrl+Shift+R`
- `Terminal > Reset and Clear` o `Ctrl+Shift+X`

### Configurazione corrotta

```bash
rm -rf ~/.config/tpgk/
```

Al prossimo avvio TPGK creera' una configurazione pulita.

### File di configurazione

```
~/.config/tpgk/
├── settings.json    # Tutte le impostazioni (50+ chiavi)
├── history.db       # Database SQLite della history
└── osc133.sh        # Script shell integration (se attivato)
```

---

## Comandi Rapidi

```
/history [termini]     Cerca nella history
/ai                    Entra in chat AI
/ai context N q        Invia ultime N righe come contesto AI
/ai off                Esci dalla chat AI
/connect [provider]    Connetti a un provider AI (con auto-detection modelli)
/wnotes [-f] testo     Salva una nota
/onotes [-f]           Apri le note
/help                  Mostra tutti i comandi o apri command palette con /

Ctrl+R                 Ricerca history interattiva
Ctrl+U                 Kill line
Ctrl+W                 Kill word
Ctrl+C                 Interrompi processo / cancella risposta AI
Ctrl+L                 Pulisci schermo
Ctrl+Click URL         Apri URL nel browser
Tab (dopo /)           Autocompleta comando
Alt+1..9               Riesegui comando history
/                      Apri command palette
```

---

## Autore e Licenza

**TPGK Terminal** — Andres Zanzani, 2026

Licensed under the **European Union Public Licence (EUPL) 1.2**.

https://github.com/buzzqw/tpq
