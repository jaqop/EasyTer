# EasyTer Pro — Handoff / Continuation Brief
_Last updated: 2026-06-24. Paste-able into a fresh Claude session to resume work._

## What this is
A **Windows terminal that renders connected Arabic with correct BiDi** — the one thing every grid
terminal (Windows Terminal, WezTerm, kitty, VS Code, Alacritty) fails. Built on **PySide6/Qt6 +
pyte (VT emulator) + pywinpty (ConPTY)**. The trick that makes Arabic work: each row is rendered
through a single **`QTextLayout`**, so Qt does HarfBuzz shaping + Unicode BiDi reordering in one pass.

## ⚠️ TWO versions live in the SAME folder `C:\Users\Admin\EasyTer` — do not confuse them
| | path | window title | config | who builds it |
|---|---|---|---|---|
| **EasyTer** (old, single file) | `EasyTer.py` (100 KB) | `EasyTer — طرفيّة عربيّة` | `easter_config.json` / `easyter_config.json` | a SEPARATE Claude session — has a "وضع كلود" Claude mode |
| **EasyTer Pro** (THIS track) | `easyterpro\` (package) | `EasyTer Pro — طرفيّة عربيّة` | `~/.easyterpro/config.json` | **us — all new features go here** |

**All feature work in this brief targets `easyterpro\`.** `EasyTer.py` is the user's working fallback; leave it alone.

## How to launch
```powershell
cd C:\Users\Admin\EasyTer
pythonw -m easyterpro      # normal (no console)
python  -m easyterpro      # debug (console shows tracebacks)
```
Python is **3.14 at `C:\Python314`**. To relaunch during dev (kill + start):
```powershell
Get-CimInstance Win32_Process -Filter "Name='pythonw.exe' OR Name='python.exe'" | ? { $_.CommandLine -match 'easyterpro' } | % { Stop-Process -Id $_.ProcessId -Force }
Start-Process pythonw -ArgumentList '-m','easyterpro' -WorkingDirectory 'C:\Users\Admin\EasyTer'
```
Verify a `.py` before launch: `python -m py_compile easyterpro\<file>.py`.

## File map (`easyterpro\`)
| file | role |
|---|---|
| `__main__.py` | entry point. **CRITICAL: redirects sys.stdout/stderr to os.devnull when None** (pythonw has no console → any lib writing to stdout crashes the app SILENTLY at startup). This guard is why the app finally runs from the shortcut. |
| `window.py` | `MainWindow` — tabs (QTabWidget), "+" profile dropdown (top-right), menu, `_open_gallery()` (Ctrl+Shift+M), `_set_theme_global()`. |
| `terminal.py` | `TerminalWidget` — the core: pyte HistoryScreen + paintEvent (per-row QTextLayout), cursor draw (block/beam/underline + blink), `contextMenuEvent` (right-click), `_MENU_QSS` (fixed-dark menu stylesheet). **Has the integer-cw bug — see Pending.** |
| `backend.py` | `PtyBackend` — wraps `winpty.PtyProcess.spawn(command, dimensions=(rows,cols))`. |
| `panes.py` | split panes (nested QSplitter). Ctrl+Shift+D/E split, Ctrl+Shift+W close. |
| `profiles.py` | shell auto-detect → list of `Profile(name, command)`. PowerShell / cmd / Git Bash / pwsh / WSL. |
| `config.py` | `config()` singleton. `.get(*keys, default=)`, `.set(value, *keys)` → saves `~/.easyterpro/config.json` + emits `changed`. |
| `render.py` | themes. `THEMES` dict, `apply_theme(name)` sets `BASE_BG/BASE_FG/PALETTE`, `theme_names()`. Loads `schemes.json` on import. |
| `schemes.json` | 551 bundled color schemes (converted from iTerm2-Color-Schemes). **560 themes total** (13 built-in + 547 unique bundled). |
| `_gen_schemes.py` | build helper: converts Windows-Terminal-format scheme JSON → easyterpro format (renames purple→magenta). |
| `gallery.py` | `AppearanceGallery` (Ctrl+Shift+M) — searchable card grid (≤120 shown), cursor-shape row, oh-my-posh combo. **Chrome is fixed-dark** so light themes stay readable. |
| `palette.py` | command palette (Ctrl+Shift+P) — fuzzy action list. |
| `posh.py` | oh-my-posh: 10 famous themes; reads/writes the managed `oh-my-posh init` line in `$PROFILE`. |
| `pluginhost.py` | **plugin system.** `Registry` singleton + `PluginAPI` facade (`register(api)`) + isolated `load()` + `safe_dispatch()`. Qt-free at import (lazy render/config imports) so it's unit-testable. Widgets PULL from `registry` at call time (no per-widget wiring). |
| `plugins/` | bundled first-party plugins, auto-loaded. Each `.py` defines `register(api)`; 4 samples (timestamp/theme/activity/overlay) + `README.md` (the API contract). Disable via `config plugins.disabled`. |

## Features DONE
- **Plugin system** (2026-07-24) — bundled first-party plugins in `plugins/`, loaded at startup by `pluginhost.load(win)` in `__main__.py`. Capabilities via `register(api)`: `add_palette_action`, `add_theme`, `on_output(text)`, `add_paint_hook(painter,widget)`, plus `write_to_active`/`active_terminal`/`setting`. **Fully error-isolated** (import/register/hook failures logged to `~/.easyterpro/plugins.log`, never crash the app — honors the pythonw guard). Wiring: `backend.output_text` signal → `terminal._dispatch_plugin_output`; paint hooks at end of `terminal.paintEvent` (auto-disable on error); `window._build_actions` appends `registry.palette_actions`. Unit+integration tests in `tests/test_pluginhost.py` (19, all green; run `python -m pytest` from repo root). Design spec: `docs/specs/2026-07-24-plugin-system-design.md`.
- **Connected Arabic + BiDi** (the core, via QTextLayout per row).
- **Full-screen app (alt-screen) rendering** (added 2026-06-24) — TUIs (Claude Code, vim) auto-detected via a `?1049h/l` scan in `backend.py` (`_scan_alt` → `alt_screen_changed` signal) → rendered by `_draw_row_grid` in `terminal.py`: **non-Arabic drawn cell-by-cell pinned to the float-cw grid** (no drift → pixel-art/box-borders crisp), **Arabic runs reversed (visual→logical) + shaped RTL** in their cells. Fixed: right-edge clipping, the distorted Claude crab mascot, and reversed Arabic inside Claude. **Known limitation (NOT a terminal bug):** Claude Code's OWN input box collapses when RTL text is present — its Ink/Yoga layout measures width assuming LTR. Confirmed terminal-side is correct: `wcwidth`=1 per Arabic char, matching Claude's own column count, so no cursor drift originates here. Not fixable from the terminal.
- **Tabs + split panes** (Ctrl+Shift+T new tab, D/E split, W close).
- **Shell profiles + auto-detect** — "+" dropdown top-right. PowerShell (`-NoProfile` default for speed), cmd, **Git Bash (FIXED 2026-06-24)**, pwsh/WSL if present.
- **560 color themes** + **searchable visual gallery** (Ctrl+Shift+M, or right-click → معرض المظاهر…). Right-click → سمة سريعة = 13 built-ins only.
- **Cursor shapes** — block / beam / underline + blink toggle (gallery row; config `cursor.style`/`cursor.blink`).
- **Prompt-style picker with LIVE previews** (`prompt_picker.py`, + menu → «شكل الموجِّه…») — 9 distinct oh-my-posh styles, each rendered live via `oh-my-posh print primary` then ANSI→HTML (`_ansi_to_html` + `_strip_noise` drops OSC/non-SGR). Click a card → applies. Includes a custom **`kali`** framed theme at `~/.poshthemes/kali.omp.json`. **Live-apply:** `window._apply_prompt_live` injects `oh-my-posh init pwsh --config <t> | iex 2>$null` into the active PowerShell pane → the CURRENT tab's prompt updates (not just new tabs). `2>$null` silences benign PSReadLine errors from re-init on PowerShell 5.1. `posh.available()` now lists ALL `.omp.json` in `~/.poshthemes` (FEATURED first). The older gallery combo (`Ctrl+Shift+M` → posh row) still exists too.
- **Default «PowerShell» loads `$PROFILE`** (was `-NoProfile`) so oh-my-posh actually shows; a «PowerShell (سريع · بلا profile)» variant remains in the + menu for fast startup. (profiles.py)
- **Command palette** (Ctrl+Shift+P), **clickable URLs** (Ctrl+click).
- **Config** persisted at `~/.easyterpro/config.json`, live-applied via `changed` signal.

## Pending / next (priority order)
1. **Background images** — user-selected feature, NOT started. Like Windows Terminal: pick an image + opacity, paint under the text in `terminal.py` paintEvent. Add `background.image`/`background.opacity` to config + a row in the gallery.
2. **Intelligent terminal / AI agent** — user-selected (from github.com/microsoft/intelligent-terminal). BIG. **Design + confirm with the user before building.** Idea: a side pane / inline that detects command errors and suggests fixes, NL→command. Defer until backgrounds done.
3. ✅ **integer-cw bug — FIXED 2026-06-24.** Was `cw = QFontMetrics.horizontalAdvance("M")` = **9** (int) while the real advance is **9.344** → `cols = width // 9` overestimated → text overflowed/clipped past the right edge (seen running Claude Code in a Git Bash tab). Fixed in `terminal.py`: `cw` now `QFontMetricsF` (float) + 8 call-sites int-cast (cols/rows compute, cursor rects, selection rects, raw-cell rects). **EasyTer.py still has the same bug — lines 751 (`cw=`) & 796 (`cols=`).**
4. oh-my-posh **live previews** in the gallery (deferred from v1).

## Critical gotchas (hard-won — don't relearn these)
- **pythonw silent crash:** under `pythonw.exe` `sys.stdout`/`sys.stderr` are `None`; any library writing to them at import crashes the app with NO error. Fixed by the guard in `__main__.py`. If a new dep prints at import, this is why a launch "does nothing."
- **winpty can't spawn paths with spaces:** `PtyProcess.spawn('"C:\Program Files\...\bash.exe" ...')` → FileNotFoundError (quotes included in lookup); unquoted → splits on the space. **Fix: 8.3 short path** (`C:\PROGRA~1\Git\bin\bash.exe`) via `GetShortPathNameW` (ctypes) — see `profiles.py _short_path()`. Apply the same to ANY spaced-path profile.
- **Qt stylesheet inheritance breaks light themes:** a window `setStyleSheet("background:white")` cascades into child `QMenu`/`QDialog` → light-on-light unreadable. **Fix: give menus/dialogs an explicit fixed-dark QSS** (`_MENU_QSS` in terminal.py; gallery chrome hardcoded `#1c1c1e`/`#e6edf3`). The terminal body still takes the theme color; only the app chrome is fixed-dark.
- **Environment deletion hook:** `Remove-Item -Recurse` / `rmdir /s` are BLOCKED even with `dangerouslyDisableSandbox:true` ("path is protected from removal"). `Stop-Process` is allowed. To delete a folder, hand the user a paste-able command.
- **pyte names yellow "brown":** in `render.py`, `PALETTE["brown"]` = the theme's yellow.

## User & working style
Arabic novelist (GitHub `jaqop`, jaqopx1@outlook.com), building the "Elintor" novel; this terminal serves his Arabic writing. **Action-oriented, dislikes verbosity/hedging/blind-debugging.** Verifies by screenshot. Wants to choose appearances himself. When stuck, read the actual code + test, don't guess. Tabby fork was abandoned & deleted — do not resurrect it.

## Related memory
See `[[arabic-terminal-project]]` (auto-loaded) and `[[sillytavern-writing-setup]]`.
