# EasyTer

**A Windows terminal that renders connected (shaped) Arabic correctly** — plus
tabs, split panes, themes, search, an embedded editor, and a Python plugin API.

![Python](https://img.shields.io/badge/Python-3.x-blue)
![PySide6](https://img.shields.io/badge/UI-PySide6-green)
![Platform](https://img.shields.io/badge/OS-Windows-lightgrey)
![License](https://img.shields.io/badge/License-MIT-yellow)

[العربية](README.ar.md)

## Screenshots

Connected, shaped Arabic in a real terminal session — correct letter joining,
diacritics, bidirectional layout, and Arabic-Indic numbers in the right order:

![EasyTer rendering connected Arabic in the terminal](docs/screenshot-arabic.png)

The same correct Arabic in the built-in editor (syntax highlighting + line numbers):

![EasyTer's embedded editor showing connected Arabic](docs/screenshot-editor.png)

## Why

Mainstream Windows terminals (Windows Terminal, and GPU terminals like kitty and
Alacritty) do **not** join Arabic letters or apply the bidirectional algorithm, so
Arabic comes out disconnected and mis-ordered. EasyTer renders every line through
Qt's `QTextLayout`, which embeds HarfBuzz shaping and the Unicode BiDi algorithm
(UAX #9) — the same engine native Linux terminals hand-roll. The result is
properly **connected Arabic**, even inside interactive programs.

It is built on a real pseudo-console (`pywinpty` / ConPTY) running a VT screen
emulator (`pyte`), so it runs real interactive programs (PowerShell, cmd, Git Bash,
WSL, Claude Code, vim, …).

## Features

- **Connected Arabic** via QTextLayout (HarfBuzz shaping + UAX #9 BiDi).
- **Tabs** and **split panes** (side-by-side / top-bottom), draggable dividers, pane
  **zoom**, **broadcast input** to all panes, and **reopen the last closed tab**.
- **New tabs/splits open in the current directory** (OSC 7 / 9;9), and tabs show
  **dynamic titles** that follow the working directory.
- **Command blocks** (OSC 133 shell integration): a green/red gutter bar marks each
  command's success/failure, and `Ctrl+Shift+↑/↓` jumps between commands.
- **Themes** — 15+ built-in (Dracula, Nord, Tokyo Night, Gruvbox, Catppuccin, One
  Dark, Monokai, Solarized, Kali Dark, …) plus full UI theming, free ANSI color
  editing, adjustable opacity, and an optional **background image**.
- **Search** (`Ctrl+F`) over the logical text, so Arabic matches correctly.
- **Embedded editor** pane with syntax highlighting and line numbers (handles large
  files efficiently).
- **Clickable links** (`Ctrl`+click), **multiple cursor styles**, **paste protection**
  + bracketed paste, and **OSC 52 clipboard** (programs can set the clipboard).
- **Desktop notification** when a long command finishes while EasyTer is in the
  background.
- **Quake-style global hotkey** (`Ctrl+Alt+`​`) to summon/hide EasyTer from anywhere.
- **Python plugin API** — keybindings, commands, themes, event hooks, status
  segments (see `examples/init.py`).
- **Shell auto-detect** (PowerShell, cmd, Git Bash, WSL), **session save/restore**,
  configurable scrollback, fast throttled rendering.
- **Claude mode** — automatic BiDi handling for Claude Code's full-screen UI. It
  auto-enables **only when Claude itself is running**, so other alternate-screen
  programs (`git diff` in `less`, `vim`, `man`, `htop`) keep correct native BiDi
  instead of being reshaped — which previously shredded their Arabic. `F2` still
  toggles it manually for any tool that pre-reverses Arabic.
- Bilingual UI: **English (default)** and Arabic. Local-first, **no telemetry**.

## Requirements

Everything you need before you start, in order. New to Windows dev tools?
Read the notes below the table too — they cover the mistakes people usually
hit.

| # | Requirement | Download link | Needed for | You install it? |
|---|---|---|---|---|
| 1 | **Windows 10 (version 1809 / build 17763) or Windows 11** | — | ConPTY, which EasyTer is built on; Windows-only | Already on your PC |
| 2 | **Internet connection** | — | downloading the source and the Python packages below (one-time) | — |
| 3 | **Python 3.10–3.14**, with pip (included by the installer) | [python.org/downloads](https://www.python.org/downloads/) | running `install.bat` and EasyTer itself | **Yes — do this first** |
| 4 | **~200 MB free disk space** | — | Python itself plus PySide6/pywinpty/pyte/wcwidth | Already have it, usually |
| 5 | **Git** — optional | [git-scm.com/downloads](https://git-scm.com/downloads) | only if you `git clone` instead of using Download ZIP | Only if you choose the Git method |
| 6 | **Administrator rights** — optional | — | only needed if you relocate EasyTer to `C:\EasyTer` and get a permissions error | Only if prompted |
| 7 | **Python packages:** `PySide6` (≥ 6.5), `pywinpty` (≥ 3.0.5), `pyte`, `wcwidth` | — | running EasyTer | **No — `install.bat` installs these for you** |

Notes:

- On the Python installer's first screen, **tick "Add python.exe to PATH"**
  before clicking Install — this is the #1 cause of "python is not
  recognized" errors. After installing, **close and reopen your
  terminal/PowerShell** so it picks up the new PATH.
- If typing `python --version` opens the Microsoft Store instead of printing
  a version, that's a Windows shortcut stub, not real Python — install from
  the link above instead (this is normal on a fresh Windows install).
- `pywinpty` 3.0.5 ships prebuilt wheels for Python 3.10–3.14, so no
  compiler / Visual Studio Build Tools are needed.
- You do **not** need to install the packages in row 7 yourself —
  `install.bat` (or `pip install -r requirements.txt`) does it for you.

EasyTer also checks all of this on startup: if Python is too old or a package
is missing, it shows a message box telling you exactly what to install
instead of failing silently.

## Download

Get the source onto your computer first, then follow **Install** below.

> **Important:** both methods below create their own `EasyTer` folder for you.
> Run them from an empty parent folder (e.g. `Desktop`, `Documents`, or
> `C:\DevSoft`) — don't create a folder named `EasyTer` yourself and `cd`
> into it first, or you'll end up with a nested `EasyTer\EasyTer` and
> commands like `pip install` / `pythonw EasyTer.py` will fail with
> "file not found" because you're one level above the actual code.

- **No Git (recommended for most people):** click the green **`<> Code`**
  button at the top of this page → **Download ZIP**, then right-click the
  downloaded ZIP → **Extract All...** (don't run anything from inside the ZIP
  without extracting it first). This creates an `EasyTer` folder — open it
  before continuing.
- **With Git** — install [Git for Windows](https://git-scm.com/downloads) first,
  then from PowerShell or Git Bash:
  ```sh
  git clone https://github.com/jaqop/EasyTer.git
  cd EasyTer
  ```
  (`cd EasyTer` is required — `git clone` creates that folder, it does not
  put the files in your current directory.)

## Install

Double-click **`install.bat`** inside the extracted/cloned `EasyTer` folder —
the one containing `EasyTer.py`, not its parent. It works from any folder: it
shows where EasyTer is, warns you if that's a system/temporary folder, lets
you install here or relocate to `C:\EasyTer` (recommended), then installs the
dependencies. Or do it manually from the project folder:

```sh
cd path\to\EasyTer
pip install -r requirements.txt
```

## Run

```sh
pythonw EasyTer.py
```

Or double-click `EasyTer.vbs` (no console window), or run `run.bat`.

If nothing happens when you run this (`pythonw` shows no console, so errors are
silent), run `python EasyTer.py` instead — plain `python` keeps the window open
and prints the actual error, which is usually either a wrong folder (see
**Download** above) or missing packages (see **Install** above).

## Language

The UI is English by default. To switch to Arabic: **Settings (`Ctrl+,`) → Language →
العربية**, then restart EasyTer.

## Keyboard shortcuts

| Keys | Action |
|------|--------|
| `Ctrl+T` · `+` | New tab |
| `Ctrl+Shift+T` | Reopen the last closed tab |
| `Ctrl+Tab` / `Ctrl+Shift+Tab` | Next / previous tab |
| `Ctrl+Shift+E` / `Ctrl+Shift+O` | Split side-by-side / top-bottom |
| `Ctrl+Shift+N` | Open editor beside terminal |
| `Ctrl+Shift+W` | Close pane (last one closes the tab) |
| `Ctrl+Shift+Z` | Maximize / restore the active pane |
| `Ctrl+Shift+B` | Broadcast typing to all panes |
| `Alt + Arrows` | Move between panes |
| `Ctrl+Shift+↑` / `Ctrl+Shift+↓` | Jump to previous / next command |
| `Ctrl+Shift+Space` | Copy mode (keyboard-select the scrollback) |
| `Ctrl` + click | Open a link |
| `Ctrl+C` / `Ctrl+V` | Copy selection (else interrupt) / paste |
| `Ctrl+Shift+C` / `Ctrl+Shift+V` | Copy / paste (always) |
| `Ctrl+F` | Search |
| `F2` | Claude mode (BiDi) — manual/auto |
| `Ctrl++` / `Ctrl+-` / `Ctrl+0` | Zoom in / out / reset font |
| `Ctrl+,` · ⚙ | Settings |
| `Ctrl+Shift+P` | Command palette (plugin commands) |
| `Ctrl+Shift+M` | Appearance gallery (browse themes) |
| `Ctrl+Shift+G` | Prompt-style gallery (oh-my-posh, live previews) |
| `Ctrl+Alt+`​` | Summon / hide EasyTer (global, works anywhere) |
| `F1` · `?` | All shortcuts |

## Plugins

Drop a `~/.easyter/init.py` to add your own keybindings, commands, themes, event
hooks, and status segments. A documented sample is in
[`examples/init.py`](examples/init.py).

## Fonts & license

The application code is **MIT** licensed (© 2026 jaqop, see [LICENSE](LICENSE)).
The bundled Arabic fonts in `fonts/` (Amiri, Vazirmatn, Noto Naskh Arabic) are under
the **SIL Open Font License 1.1** (see [fonts/OFL.txt](fonts/OFL.txt)). To use a
different Arabic font, drop its `.ttf` in `fonts/` and adjust the font list.

Built with Python + PySide6 + pyte + pywinpty (ConPTY).
