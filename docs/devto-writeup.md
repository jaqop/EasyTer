---
title: "Why no Windows terminal renders Arabic correctly — and how I fixed it"
published: false
description: "Every Windows terminal breaks Arabic: disconnected letters, reversed order. Here's why it happens at the terminal layer, and how I built one that gets it right."
tags: terminal, arabic, windows, python
cover_image: https://jaqop.github.io/EasyTer/screenshot-arabic.png
canonical_url: https://github.com/jaqop/EasyTer
---

Open Windows Terminal, kitty, Alacritty, or WezTerm and type a line of Arabic. This is roughly what you get:

```
ﻡ ﻼ ﺱ ﻝ ﺍ
```

The letters are **disconnected**, each frozen in its isolated form, and the **order is reversed**. To an Arabic reader that's not "slightly off" — it's unreadable, like this English:

```
d e t c e n n o c s i d
```

I got tired of this, so I built **[EasyTer](https://github.com/jaqop/EasyTer)** — a Windows terminal that renders Arabic the way it's supposed to look:

```
السلام عليكم
```

Connected, shaped, right-to-left. Here's what's actually going wrong in every other terminal, and what it takes to fix it.

## Two problems, not one

Rendering Arabic correctly means solving two independent hard problems. Terminals skip both.

### Problem 1: shaping (letter joining)

Arabic is cursive. A letter changes shape depending on its neighbors — it has up to four forms: **isolated**, **initial**, **medial**, and **final**. Take the letter *ha* (ه):

| Position | Form |
|---|---|
| isolated | ه |
| initial | هـ |
| medial | ـهـ |
| final | ـه |

Picking the right glyph for each letter based on context is called **shaping**. The Unicode code points you store are always the same abstract letters; turning them into the correct connected glyphs is a separate step done by a shaping engine like **HarfBuzz**.

Terminals render text as a **grid of fixed cells**, one code point per cell, each drawn independently. That model has no concept of "this glyph depends on its neighbor." So every Arabic letter comes out in its isolated form, and the cursive joining never happens.

### Problem 2: the bidirectional algorithm (BiDi)

Arabic reads **right to left**, but numbers, Latin words, and punctuation inside it read left to right. Ordering a mixed run correctly is the job of the **Unicode Bidirectional Algorithm** (UAX #9) — a genuinely intricate spec with embedding levels and reordering rules.

Terminals store and render text in **logical order, left to right**, cell by cell. No BiDi pass runs. So Arabic marches out in the wrong direction, and any embedded numbers land in the wrong place.

Native Linux terminals that handle Arabic (like some VTE-based ones) implement this machinery by hand. On Windows, nobody did.

## The fix: stop treating a line as independent cells

The insight behind EasyTer is that a terminal line isn't really a bag of independent cells — it's a **string that needs shaping and BiDi as a unit**. So instead of drawing cell-by-cell, EasyTer hands each line to a real text engine.

Concretely, it renders every line through Qt's **`QTextLayout`**, which internally runs:

1. **HarfBuzz shaping** — resolves each letter to its correct contextual glyph and joins them.
2. **Unicode BiDi (UAX #9)** — reorders mixed LTR/RTL runs into correct visual order.

That's the same combination Linux terminals hand-roll — except QTextLayout gives it to you as a battle-tested library instead of thousands of lines of custom code.

## But it still has to be a *terminal*

Correct text rendering is useless if `vim`, `git`, and your shell don't run. So under the hood EasyTer is a genuine terminal:

- **[pywinpty](https://pypi.org/project/pywinpty/) / ConPTY** — a real Windows pseudo-console. Programs think they're talking to a normal terminal.
- **[pyte](https://pypi.org/project/pyte/)** — a VT screen emulator that interprets escape sequences and maintains the screen grid, scrollback, colors, and cursor.

pyte gives you the logical screen state; QTextLayout turns each logical line into correctly shaped, correctly ordered pixels. Interactive programs — PowerShell, cmd, Git Bash, WSL, vim, and Claude Code — all just work, now with readable Arabic.

## The hard part: reconciling a cell grid with proportional shaping

Here's the tension that makes this genuinely tricky, and it's worth being honest about.

A terminal is a **monospace grid**: the emulator, the cursor, and the running program all agree that column N is column N, and every cell is one fixed width. But shaped Arabic is **proportional and reordered** — a run of five code points might render as three connected glyphs of varying width, laid out right to left.

So you're constantly translating between two coordinate systems:

- **Logical/grid coordinates** — what pyte and the program running inside believe (cursor at row 3, column 12).
- **Visual coordinates** — where the shaped, BiDi-reordered glyph actually lands on screen.

Selection, the cursor, click-to-position, and search (`Ctrl+F`) all have to operate in **logical order** so they match what the user typed and what the program expects — even though the pixels are in visual order. Search that matched the *visual* order would fail to find text the user actually typed. Getting this mapping right, in both directions, is most of the work.

## The nastiest edge case: full-screen apps that pre-reverse their own text

Some TUI programs are "BiDi-aware" in their own way — they run the reversal *themselves* and then hand the terminal text that's already in visual order, assuming the terminal will draw it verbatim. If EasyTer then applies BiDi *again*, you get a double-reversal: Arabic that's broken in a new and exciting way.

This shows up with full-screen (alternate-screen) programs. `git diff` piped through `less`, `vim`, `man`, `htop` — many expect the terminal to leave their layout alone.

EasyTer's answer is context-sensitive. It only auto-enables its full-screen BiDi handling for specific tools that need it (Claude Code's UI, in the current build), and leaves everything else on native behavior so their Arabic isn't re-mangled. There's also a manual toggle (`F2`) for any tool that pre-reverses text. This "when to reshape and when to keep hands off" decision turned out to be one of the fiddlier parts of the whole project.

## It's not just Arabic

The same shaping-plus-BiDi pipeline handles every connected right-to-left script. EasyTer also renders:

- **Persian** (فارسی)
- **Urdu** (اردو)
- **Pashto** (پښتو)

Together that's a few hundred million people whose scripts no Windows terminal renders correctly. The terminal was always the missing piece.

## Try it

EasyTer is free, open source (MIT), Windows-only, and has no telemetry. There's a single standalone `.exe` — no Python needed:

👉 **[Download EasyTer.exe / source on GitHub](https://github.com/jaqop/EasyTer)**

If you write code in Arabic, Persian, Urdu, or Pashto — or you just find text rendering internals interesting — I'd love your feedback and issues. And if this saved you from copy-pasting Arabic into a text editor to read your own terminal output, a ⭐ on the repo genuinely helps.

*Built with PySide6 (QTextLayout / HarfBuzz), pywinpty (ConPTY), and pyte.*
