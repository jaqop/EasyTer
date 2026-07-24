# EasyTer Pro — Plugin System (v1) Design

_Date: 2026-07-24 · Branch: `feat/plugin-system`_

## Goal

A first-party, bundled plugin system for EasyTer Pro. Each module in
`easyterpro/plugins/` extends the app through a stable `register(api)` facade,
fully isolated so **no plugin can crash the app** (honoring the `pythonw`
silent-crash constraint documented in `_HANDOFF.md`).

## Decisions (from brainstorming)

| Question | Decision |
|---|---|
| Capabilities | palette actions · themes · terminal output events · paint/overlay hooks |
| Location | bundled in the package: `easyterpro/plugins/` |
| API style | `register(api)` entry function with a facade object |
| Enable/disable | `config.json` `plugins.disabled` list; all bundled plugins load by default |

## Key architectural decision: widgets *pull* from a registry

One global `Registry` singleton holds all registrations. Widgets read it at call
time rather than connecting per-widget at construction:

- `paintEvent` iterates `registry.paint_hooks` every frame.
- Output dispatch iterates `registry.output_listeners` per output chunk.
- `_build_actions()` reads `registry.palette_actions` each time the palette opens.
- Themes go straight into `render.THEMES`, already read live by gallery/palette.

Consequence: plugin load timing is flexible, disabling works live, and terminals
created before plugins finish loading still work (they reference the registry,
which just starts empty).

## Components

### NEW `easyterpro/pluginhost.py`

- `Registry` — holds `palette_actions`, `output_listeners`, `paint_hooks`.
  Module-level singleton `registry`.
- `PluginAPI` — the facade passed to each plugin's `register`:
  - `add_palette_action(label, callback)`
  - `add_theme(name, spec)` — validates `{bg, fg, ansi{...}}`, inserts into `render.THEMES`
  - `on_output(callback)` — `callback(text: str)` per output chunk
  - `add_paint_hook(callback)` — `callback(painter, widget)` at end of paint
  - `active_terminal()` / `write_to_active(text)` — common app operations
  - `window` — escape hatch, documented as unstable
  - `setting(key, default=None)` — reads `config plugins.settings.<name>.<key>`
- `load(window)` — reads `config plugins.disabled`, iterates modules via
  `pkgutil.iter_modules`, imports + calls `register(api)`. Registrations are
  **buffered per-plugin and committed only if `register()` returns cleanly**
  (clean rollback on error).
- `safe_dispatch(callbacks, *args)` — pure try/except-per-callback helper reused
  by output + paint dispatch; **auto-removes a paint hook that raises** to protect
  frame rate. Errors logged to `~/.easyterpro/plugins.log`.

### Wiring edits (minimal)

- `backend.py` — add `output_text = Signal(str)`, emit in `_reader` alongside
  `data_ready` (existing path untouched).
- `terminal.py` — connect `output_text` → `safe_dispatch(registry.output_listeners, text)`
  in `__init__`; call `safe_dispatch(registry.paint_hooks, p, self)` at end of `paintEvent`.
- `window.py` — `_build_actions()` appends `registry.palette_actions`.
- `__main__.py` — `pluginhost.load(window)` after the window is created.
- `config.py` — add `"plugins": {"disabled": [], "settings": {}}` to DEFAULTS.

### NEW sample plugins (one per capability, as living docs)

- `sample_timestamp.py` — palette action → writes date to active pane.
- `sample_theme.py` — registers one extra theme.
- `sample_activity.py` — `on_output` listener, safe/observable (counts output
  chunks; the count is read by the overlay sample).
- `sample_overlay.py` — paint hook drawing a small unobtrusive corner badge.

### NEW `easyterpro/plugins/README.md`

Documents the `register(api)` contract by example.

## Error isolation (primary safety guarantee)

- Import failure → skip plugin + log.
- `register()` failure → roll back that plugin's registrations + log.
- Hook failure → caught per call; paint hooks auto-disabled after raising.
- Never prints (file log only), honoring the `pythonw` stdout guard.

## Testing

Pure-Python parts get pytest coverage (no Qt needed):

- Registry accumulation + per-plugin rollback on `register()` error.
- Loader skips disabled plugins.
- Loader isolates a plugin that raises at import / at register.
- `add_theme` validation rejects malformed specs.
- `safe_dispatch` continues past a raising callback and auto-disables paint hooks.

Qt-dependent dispatch is thin glue over these tested pure functions.

## File inventory

```
NEW  easyterpro/pluginhost.py
NEW  easyterpro/plugins/__init__.py
NEW  easyterpro/plugins/sample_timestamp.py
NEW  easyterpro/plugins/sample_theme.py
NEW  easyterpro/plugins/sample_activity.py
NEW  easyterpro/plugins/sample_overlay.py
NEW  easyterpro/plugins/README.md
NEW  tests/test_pluginhost.py
EDIT easyterpro/backend.py      (output_text signal)
EDIT easyterpro/terminal.py     (output + paint dispatch)
EDIT easyterpro/window.py       (palette actions)
EDIT easyterpro/__main__.py     (load call)
EDIT easyterpro/config.py       (DEFAULTS keys)
```
