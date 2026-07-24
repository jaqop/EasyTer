# EasyTer Pro — Plugins

Bundled, first-party plugins. Each `.py` module here (not starting with `_`) is
auto-loaded at startup and may define a `register(api)` function.

## Writing a plugin

Create `easyterpro/plugins/my_plugin.py`:

```python
def register(api):
    api.add_palette_action("قل مرحبًا", lambda: api.write_to_active("hello\r"))
```

That's the whole contract: define `register(api)` and call methods on `api`.

## The `api` object (`PluginAPI`)

| Method | What it does |
|---|---|
| `api.add_palette_action(label, callback)` | Adds an entry to the command palette (Ctrl+Shift+P). `callback()` takes no args. |
| `api.add_theme(name, spec)` | Registers a color theme `{bg, fg, ansi{...}}`; appears in the gallery + palette. Raises `ValueError` on a malformed spec. |
| `api.on_output(callback)` | `callback(text: str)` runs for every chunk of terminal output (main thread). |
| `api.add_paint_hook(callback)` | `callback(painter, widget)` runs at the end of every paint frame, on top of everything. A hook that raises is auto-disabled. |
| `api.active_terminal()` | The active `TerminalWidget`, or `None`. |
| `api.write_to_active(text)` | Writes `text` to the active pane's shell; returns `True` if a pane was found. |
| `api.setting(key, default=None)` | Reads `config plugins.settings.<plugin>.<key>`. |
| `api.window` | The `MainWindow` (escape hatch — internal, unstable). |
| `api.name` | This plugin's module name. |

## Guarantees

- **Isolation:** if your `register()` raises, none of its registrations are
  committed and the app keeps running. Import failures and hook errors are
  logged to `~/.easyterpro/plugins.log` and skipped.
- **Never print to stdout** — under `pythonw.exe` there is no console and a write
  crashes the app silently. Log to a file if you must.

## Enabling / disabling

All bundled plugins load by default. To turn one off, add its module name to
`~/.easyterpro/config.json`:

```json
{ "plugins": { "disabled": ["sample_overlay"] } }
```

## Samples in this folder

| File | Capability shown |
|---|---|
| `sample_timestamp.py` | palette action + `write_to_active` |
| `sample_theme.py` | `add_theme` |
| `sample_activity.py` | `on_output` (counts output chunks) |
| `sample_overlay.py` | `add_paint_hook` (draws a badge; reads the counter from `sample_activity`) |
| `tab_title_cwd.py` | real plugin: tab title auto-follows the shell's current directory (split-aware) |

### `tab_title_cwd.py` — how it works

PowerShell + oh-my-posh already broadcast the current folder as the window title
via `OSC 0` (`ESC]0;<folder> BEL`), updated on every `cd`. This plugin connects
per-pane to `backend.output_text`, parses that `OSC 0` title out of the output,
and copies it onto the owning tab (`api.window` escape hatch + `setTabText`).
Per-pane wiring means a background tab never mislabels the active one. If your
shell doesn't emit `OSC 0`, the plugin simply does nothing.

**Split panes:** every pane in a tab is wired, and the tab title follows the
**active (focused)** pane, so two panes in different directories don't fight over
the title. New panes created by splitting are picked up via
`QApplication.focusChanged` (a split focuses its new pane), and switching focus
between panes updates the title to the focused pane's directory.

**Manual rename:** the palette (Ctrl+Shift+P → "إعادة تسمية التبويب…") renames the
current tab and **pins** it — auto-cwd stops touching a pinned tab, so your name
sticks. Rename it to a blank string to un-pin and resume following the directory.
