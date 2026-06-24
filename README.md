# EasyTer

**A Windows terminal that renders connected (shaped) Arabic correctly** — plus
tabs, split panes, themes, search, an embedded editor, and a Python plugin API.

![Python](https://img.shields.io/badge/Python-3.x-blue)
![PySide6](https://img.shields.io/badge/UI-PySide6-green)
![Platform](https://img.shields.io/badge/OS-Windows-lightgrey)
![License](https://img.shields.io/badge/License-MIT-yellow)

[العربية](README.ar.md)

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
- **Tabs** and **split panes** (side-by-side / top-bottom), draggable dividers.
- **Themes** (multiple built-in) with full UI theming, free ANSI color editing, and
  adjustable background opacity.
- **Search** (`Ctrl+F`) over the logical text, so Arabic matches correctly.
- **Embedded editor** pane with syntax highlighting and line numbers.
- **Python plugin API** — keybindings, commands, themes, event hooks, status
  segments (see `examples/init.py`).
- **Shell auto-detect**: PowerShell, cmd, Git Bash, WSL.
- **Claude mode** — automatic BiDi handling for Claude Code's full-screen UI.
- Bilingual UI: **English (default)** and Arabic.

## Requirements

- Windows
- Python 3.x

## Install

Double-click **`install.bat`** — it works from any folder (it switches to its own
directory, so it always finds `requirements.txt`). Or do it manually from the
project folder:

```sh
cd path\to\EasyTer
pip install -r requirements.txt
```

## Run

```sh
pythonw EasyTer.py
```

Or double-click `EasyTer.vbs` (no console window), or run `run.bat`.

## Language

The UI is English by default. To switch to Arabic: **Settings (`Ctrl+,`) → Language →
العربية**, then restart EasyTer.

## Keyboard shortcuts

| Keys | Action |
|------|--------|
| `Ctrl+T` · `+` | New tab |
| `Ctrl+Tab` / `Ctrl+Shift+Tab` | Next / previous tab |
| `Ctrl+Shift+E` / `Ctrl+Shift+O` | Split side-by-side / top-bottom |
| `Ctrl+Shift+N` | Open editor beside terminal |
| `Ctrl+Shift+W` | Close pane (last one closes the tab) |
| `Alt + Arrows` | Move between panes |
| `Ctrl+Shift+C` / `Ctrl+Shift+V` | Copy / paste |
| `Ctrl+F` | Search |
| `F2` | Claude mode (BiDi) — manual/auto |
| `Ctrl++` / `Ctrl+-` / `Ctrl+0` | Zoom in / out / reset font |
| `Ctrl+,` · ⚙ | Settings |
| `Ctrl+Shift+P` | Command palette (plugin commands) |
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
