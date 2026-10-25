# EasyTer — continuation brief

_Last verified: 2026-10-25, against commit `39b510a` (working tree clean)._
_Paste-able into a fresh session. Every claim below names the command that produced it._

## What this is

A **Windows terminal that renders connected Arabic with correct BiDi** — the one thing
every grid terminal (Windows Terminal, WezTerm, kitty, VS Code, Alacritty) fails. Built on
**PySide6/Qt6 + pyte (VT emulator) + pywinpty (ConPTY)**. The trick that makes Arabic work:
each row is rendered through a single **`QTextLayout`**, so Qt does HarfBuzz shaping +
Unicode BiDi reordering (UAX #9) in one pass.

## Where things stand

Nothing is unmerged. `main` is at `39b510a` (merge of PR #14), the working tree is clean,
and the last three PRs (#11 CI, #13 the NTLM path gate, #14 input-side hardening) are all in.
There is no branch carrying unlanded work.

The open thread is the chunk PR #14 deliberately dropped — see **Pending**, item 1.

## ⚠️ The two apps, and which one is the product

This repo holds two applications. **Their roles are the reverse of what earlier notes said**,
so do not trust any description of this that predates 2026-10-25.

| | `EasyTer.py` | `easyterpro/` |
|---|---|---|
| role | **the product** | second app **+ shared library** |
| size | 5,718 lines, one file | 20 modules |
| ships? | **yes** — `EasyTer.spec` builds it into `dist/EasyTer/EasyTer.exe`, `release.yml` attaches the zip to each `v*` tag | no — source only |
| documented? | yes, the README is about this | not mentioned in the README |
| run | `pythonw EasyTer.py`, `run.bat`, `EasyTer.vbs` | `python -m easyterpro` |
| window title | `i18n.t("win.title")` | `EasyTer Pro — طرفيّة عربيّة` |
| config | `easyter_config.json` (next to the script; `~/.easyter/` when frozen) | `~/.easyterpro/config.json` |
| plugins | `~/.easyter/init.py`, decorator API (`_PluginAPI`, EasyTer.py:1075) | `easyterpro/plugins/*.py`, `register(api)` API |

**`EasyTer.py` imports three modules out of `easyterpro/`** — that is the whole coupling:

```
EasyTer.py:33-41  →  easyterpro.localpath, easyterpro.pasteguard, easyterpro.shellquote
```

Those three are the **shared security layer for both apps**. A change to them lands in the
shipped product and in EasyTer Pro at once. Everything else in `easyterpro/` (`window.py`,
`terminal.py`, `backend.py`, `render.py`, …) belongs to EasyTer Pro alone and is not in the exe.

Re-derive this any time:

```sh
grep -rn 'easyterpro' --include='*.py' --include='*.spec' . | grep -v '^./easyterpro/'
```

Note the two plugin systems are **unrelated implementations**, not one system shared. Likewise
the two theme tables are separate (see **Verified**).

## File map — `easyterpro/`

| file | role |
|---|---|
| `localpath.py` | **the NTLM gate.** `accept_local_path` is purely lexical — it never calls the filesystem, because on Windows those calls *are* the leak. Plus `local_drive_ok` (GetDriveTypeW), `cached_drive_ok`, `hover_file_reference`, `require_wide_path`. Used by both apps. See `docs/SECURITY.md`. |
| `shellquote.py` | quoting for a *known* shell (PowerShell / cmd / POSIX): dropped files, oh-my-posh theme paths. `accept_local_path` is **not** a quoter — it accepts `'`, `;`, `&`, `$(` and backticks. Used by both apps. |
| `pasteguard.py` | paste confirmation + bracketed-paste wrapping; strips an embedded paste-end marker. Used by both apps. |
| `__main__.py` | EasyTer Pro entry point. **Redirects sys.stdout/stderr to devnull when None** — see Landmines. |
| `window.py` | `MainWindow` — tabs, profile dropdown, menu, gallery, theme application. |
| `terminal.py` | `TerminalWidget` — pyte HistoryScreen + per-row `QTextLayout` paint, cursor, context menu. |
| `backend.py` | `PtyBackend` — wraps `winpty.PtyProcess.spawn`. |
| `render.py` | themes. `THEMES` dict + `_load_bundled_schemes()` reading `schemes.json` at import. |
| `schemes.json` | bundled color schemes, converted from iTerm2-Color-Schemes. |
| `_gen_schemes.py` | build helper: Windows-Terminal scheme JSON → easyterpro format (renames purple→magenta). |
| `gallery.py` / `palette.py` / `prompt_picker.py` / `posh.py` | appearance gallery, command palette, oh-my-posh picker with live previews. |
| `panes.py` / `profiles.py` / `config.py` | split panes, shell auto-detect, config singleton. |
| `pluginhost.py` | EasyTer Pro's plugin system. `Registry` + `PluginAPI` + isolated `load()` + `safe_dispatch()`. Qt-free at import, so it is unit-testable. |
| `plugins/` | bundled first-party plugins, auto-loaded; each defines `register(api)`. Disable via `config plugins.disabled`. |

## Pending

- [ ] **Re-land the drive-cache and hover-cursor fixes PR #14 dropped.**
      Commit `b5c9da7` built both; commit `5fda654` removed them again to keep the PR small
      ("Leave drive-cache and hover-cursor fixes for a later PR"). Neither is in the tree now.
      Two separate behaviours:
      **(a) drive-type freshness** — `local_drive_ok` caches the `GetDriveTypeW` answer per
      drive letter forever, so a letter remapped to a share *after* its first classification
      keeps the stale "local" verdict. The dropped version read the type fresh before each
      filesystem call and kept the cache for hover hints only.
      **(b) hover existence** — `_hover_file` is now purely lexical, so Ctrl+hover shows the
      hand cursor for a path that does not exist. The dropped version added a 50 ms debounced
      existence check off the mouse-move path, cached at 64 entries.
      Found by: `git show 5fda654 -- EasyTer.py easyterpro/localpath.py`
      Last run: 2026-10-25

- [ ] **Decide whether `_hover_file`'s current laxness is acceptable or a gap.**
      (judgement — not verified; re-read `EasyTer.py:2983` `_hover_file` and
      `easyterpro/localpath.py:152` `hover_file_reference` before acting.)

- [ ] **`easyterpro/` has no stated future.** It is simultaneously a live dependency of the
      shipped product and an undocumented second app that the README never mentions and the
      exe never contains. Whether EasyTer Pro is still a product direction, or whether the
      three shared modules should move somewhere neutral, is an open question for the author.
      (judgement — not verified; nothing in the repo records a decision either way.)

## Verified this session

These were measured on 2026-10-25. They may be leaned on without re-running, but each
names its measurement so you can.

- **The integer-`cw` bug is fixed in both apps.** Earlier notes claimed `EasyTer.py` still
  had it at lines 751/796 — that is **wrong**; those line numbers now point at unrelated code.
  Both use the float `QFontMetricsF`:
  `EasyTer.py:1972` and `easyterpro/terminal.py:131`.
  Measured by: `grep -n 'QFontMetricsF' EasyTer.py easyterpro/terminal.py`

- **Theme counts differ between the apps, because only EasyTer Pro loads `schemes.json`.**
  `EasyTer.py` THEMES: 17 literal entries, plus `~/.easyter/themes/*.json` at runtime — it
  never reads `schemes.json`. `easyterpro/render.py` THEMES: 13 literal entries, plus 551
  loaded from `schemes.json` by `_load_bundled_schemes()` at import.
  Measured by: `grep -n 'schemes' EasyTer.py` (comment only), `python -c "import json;print(len(json.load(open('easyterpro/schemes.json',encoding='utf-8'))))"`,
  and counting the 4-space-indented keys inside each `THEMES = {` literal.
  (Counting `^    "` across the whole of `render.py` gives 17 — it catches quotes outside
  the literal. Match the block, not the file.)

- **Test suite state on this machine: 1 failed, 351 passed, 16 errors.** CI's `TEST_FLOOR`
  is 368 and CI is green, so this is a local-environment gap, not a regression — see Landmines.
  Measured by: `C:\Python314\python.exe -m pytest -q`

- **Both `C:\Python314` and `C:\Python315` can run the app; only 3.14 can run the tests.**
  3.15 is first on PATH and, since 2026-10-25, has PySide6 / pyte / pywinpty / wcwidth —
  `EasyTer.py` imports and its dependency check passes there. It has no pytest.
  Measured by: `where pythonw`,
  `C:\Python315\python.exe -c "import PySide6, pyte, winpty, wcwidth"`, and
  `QT_QPA_PLATFORM=offscreen C:\Python315\python.exe -c "import EasyTer"`

## Landmines

- **Two interpreters are in play, and `python` is not the one CI uses.** Python 3.15.1 is
  installed and sits **ahead of 3.14 on PATH**, so `run.bat`, `EasyTer.vbs`, and
  `pythonw EasyTer.py` all launch **3.15**. CI and `release.yml` pin **3.14**, so the app
  you run by double-clicking is not the build the test suite covers. Keep that in mind when
  a bug reproduces for the author but not in CI.
  On 2026-10-25 the four runtime packages were installed into 3.15 (`pip install -r
  requirements.txt`), which is why the launchers work. Before that they raised EasyTer's own
  "missing required Python packages" dialog — if that dialog returns, a third interpreter has
  jumped ahead on PATH; check with `where pythonw`.
  **Tests still require 3.14** — 3.15 has no pytest. See Testing.

- **`pytest-qt` is missing from `C:\Python314`**, which is the entire cause of the 16 errors
  above — every one is `fixture 'qapp' not found`, and `pytest.ini`'s `qt_api` option is
  reported unknown. `pip install -r requirements-dev.txt` fixes it.
  Check with: `C:\Python314\python.exe -c "import pytestqt"`

- **The one failing test is probably an artefact of the guard, not a leak.**
  `tests/test_local_path.py::test_osc7_bad_host_never_stats` fails because `install_guard`
  patches `os.path.exists` *globally* and then records calls made by Python's own import
  machinery — the recorded paths are stdlib files such as
  `C:\Python314\Lib\urllib\__init__.py`, not the UNC path under test, and `backend.cwd` is
  correctly left untouched. On CI those modules are already imported by the time the test
  runs, so no calls are recorded.
  (judgement — **not confirmed**; the run that would have proved it produced no output.
  Re-derive before trusting it, and do not "fix" the gate on the strength of this entry.)
  Reproduce with: `C:\Python314\python.exe -m pytest -q tests/test_local_path.py::test_osc7_bad_host_never_stats`

- **`pythonw` silent crash.** Under `pythonw.exe`, `sys.stdout`/`sys.stderr` are `None`; any
  library that writes to them at import kills the app with **no error at all**. Both entry
  points guard against this (`easyterpro/__main__.py:9`, `EasyTer.py:80`). If a new dependency
  prints at import time, this is why a launch "does nothing".

- **winpty cannot spawn paths containing spaces.** Quoted → the quotes are included in the
  lookup; unquoted → it splits on the space. The fix is the 8.3 short path via
  `GetShortPathNameW` — see `profiles.py` `_short_path()`. Apply it to any spaced-path profile.

- **Qt stylesheet inheritance breaks light themes.** A window-level
  `setStyleSheet("background:white")` cascades into child `QMenu`/`QDialog`, giving
  light-on-light. The fix in place: app chrome gets an explicit fixed-dark QSS
  (`_MENU_QSS` in `terminal.py`; gallery chrome hardcoded). Only the terminal body follows
  the theme.

- **pyte names yellow "brown".** In `render.py`, `PALETTE["brown"]` is the theme's yellow.

- **CI fails on *skipped* tests, not only failures.** `ci.yml` throws when `skipped > 0`, so
  an import-failure `skipIf` cannot hide a test. It also enforces `TEST_FLOOR` (368) —
  **raise it in the same PR that adds tests**.

## Testing

```sh
C:\Python314\python.exe -m pip install -r requirements-dev.txt
C:\Python314\python.exe -m pytest
```

`conftest.py` at the repo root forces `QT_QPA_PLATFORM=offscreen` before PySide6 picks a
platform plugin. `pytest.ini` collects both `tests/` and `dev/`.

## Author & working style

Arabic novelist (GitHub `jaqop`, jaqopx1@outlook.com), writing the "Elintor" novel; this
terminal serves that Arabic writing. Action-oriented, dislikes verbosity, hedging, and
blind debugging. Verifies by screenshot. Wants to choose appearances himself. When stuck,
read the actual code and test it — do not guess. The Tabby fork was abandoned and deleted;
do not resurrect it.

## Related memory

See `[[arabic-terminal-project]]` (auto-loaded) and `[[sillytavern-writing-setup]]`.
