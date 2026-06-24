# Harvest: Best Ideas from 6 Terminals → EasyTer Pro (Qt/Python)

Date: 2026-06-24. Method: 6 parallel research agents, one per terminal. Goal: steal the best *ideas* (not code — they're in 5 incompatible languages) and adapt them to our Qt/PySide6 + pyte + ConPTY foundation.

## The meta-insight (confirmed by every agent)
Qt's **`QTextLayout` already embeds HarfBuzz** → shaping + BiDi + ligatures + font fallback **for free**. This is exactly what native terminals (WezTerm, kitty, Windows Terminal, Ghostty) hand-roll with FreeType+HarfBuzz+FriBidi. So:
- Our connected-Arabic killer feature is the *same engine* that gives ligatures/complex shaping.
- We do NOT chase GPU-latency parity (Python/Qt/ConPTY can't hit Zig's 2–5ms). We **cache aggressively** instead.
- The valuable harvest is **UX + architecture + protocols** — mostly tagged [easy] in Python.

## Harvest table
| Terminal (lang) | Signature strength | Adapt to Qt |
|---|---|---|
| **kitty** (C+Py) | Terminal **graphics protocol** (inline images, the de-facto standard) | [medium] QImage + temp-file/shm + z-ordered paint layer |
| | Remote control + **Python "kittens"** (plugins) | [easy] QLocalSocket/JSON-RPC + Python modules |
| **Warp** (Rust) | **App-side input editor** (terminal owns the line, sends on Enter) | [easy] QPlainTextEdit; *fixes Arabic input*; QTextLayout plugs in |
| | **Command Blocks** (group cmd+output via shell hooks → OSC/DCS markers) | [medium] emit markers in shell prompt, parse in read loop; fights pyte single-screen |
| | AI generate/correct (`#` → command; explain errors) | [easy] we already drive Claude |
| **Tabby** (TS) | **ConfigProxy** YAML core (default-stripping, migrations, reactive) | [easy] — highest ROI, the foundation |
| | **Provider registry** (ABC + registry for menu/settings/hotkey/profile) | [easy] — backbone; makes Arabic "just another provider" |
| | Themes from 16-color schemes (auto-contrast) | [medium] JSON scheme → QPalette+QSS; reuse .itermcolors corpus |
| **Windows Terminal** (C++) | **Profiles** (defaults+list inherit) + **dynamic shell generators** (auto-detect pwsh/WSL/cmd/Git-Bash) + stable-GUID reconcile | [easy] — biggest steal, most Windows-relevant |
| | Command palette over JSON `actions` registry (feeds keybinds too) | [easy] QLineEdit+QListView fuzzy |
| | Acrylic/Mica transparency | [medium] DwmEnableBlurBehind via ctypes |
| **WezTerm** (Rust) | Per-font `harfbuzz_features` overrides (toggle ligatures per family) | [easy] QFont.setFeatures (Qt 6.7+) |
| | Local panes/tabs (binary tree) | [easy/done] QSplitter — we have this |
| | Lua config + hot reload | [easy] TOML + QFileSystemWatcher |
| **Ghostty** (Zig) | **Dirty-region-only repaint + coalesced/throttled PTY-read timer** | [easy idea] biggest realistic latency/CPU win |
| | **Shaped-run glyph cache** (QTextLayout run → pixmap, keyed by text+attrs) | [easy] protects Arabic perf (no re-shape per frame) |
| | Per-codepoint-range font mapping | [easy] route Arabic ranges to Amiri via QFont |

## Evidence-based roadmap (value × feasibility)
- **Tier 1 — Backbone (do first, everything hangs off it):** ConfigProxy YAML config (Tabby) + Provider registry (Tabby) + Profiles & shell auto-detect (Windows Terminal). Directly fixes customization + shell choice + startup speed.
- **Tier 2 — Signature UX:** App-side **input editor** (Warp — fixes Arabic input) + Command palette + Command blocks.
- **Tier 3 — Differentiators:** Inline images (kitty graphics protocol) + AI assist.
- **Tier 4 — Perf discipline:** dirty-region repaint + shaped-run glyph cache + throttled reads.
- **Free polish:** per-font ligature toggles, themes from .itermcolors, Python plugins.

## What we deliberately DON'T do
Custom GPU/D3D/OpenGL renderer, persistent remote-mux RPC server, matching Zig single-ms latency. Cache instead; lean on Qt.
