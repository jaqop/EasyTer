# -*- coding: utf-8 -*-
"""
EasyTer - a real Arabic-capable terminal (ConPTY)
========================================
A full terminal emulator built on:
  - pywinpty  : a real pseudo-console (ConPTY) that runs interactive programs (claude, vim, python...)
  - pyte      : a VT screen emulator (cursor, colors, scrolling, ANSI sequences)
  - PySide6   : rendering - each line is drawn as *connected text* via Qt's engine, not cell by cell,
                so Arabic stays joined even inside interactive programs as much as possible.

Run with:  pythonw EasyTer.py   (or EasyTer.vbs / run.bat)
"""

import ctypes
import ctypes.wintypes
import glob
import json
import os
import re
import shutil
import sys
import threading
import time
import webbrowser

# Under pythonw.exe there is no console, so sys.stdout/sys.stderr are None. A stray
# print() (e.g. from a caught startup error, a hook, or a plugin) would then raise and
# crash the app silently. Redirect the missing streams to the null device up front so
# any print becomes a harmless no-op.
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")

import pyte
from winpty import PtyProcess
from wcwidth import wcwidth as _wcwidth_raw


def _char_width(d):
    """Display width of a terminal cell, robust to multi-codepoint cell data.

    pyte can store more than one codepoint in a single cell (emoji + variation
    selector, ZWJ sequences, a base char + combining mark). wcwidth.wcwidth()
    calls ord() and raises TypeError on such strings, which used to abort the
    whole paintEvent (frozen/garbled screen). Measure the base codepoint only
    (combining marks add no width) and never raise."""
    if not d:
        return 0
    try:
        w = _wcwidth_raw(d[0])
    except TypeError:
        return 1
    return w if (w and w > 0) else 1

# Keyboard protocol sequences (kitty: CSI <>=? ... u) - pyte doesn't understand them and prints 'u'
# literally. We strip them (no effect on display, just keyboard negotiation).
KITTY_KB_RE = re.compile(r"\x1b\[[<>=?][0-9;]*u")
# Incomplete CSI/ESC sequence at the end of a chunk (carried to the next read to avoid splitting)
INCOMPLETE_TAIL_RE = re.compile(r"\x1b\[?[0-9;?<>=]*$")
# Clickable links: match http(s) URLs in the visible text (Ctrl+click to open)
URL_RE = re.compile(r"""https?://[^\s<>"'`)\]}]+""")
# Shell-integration markers (OSC 133, FinalTerm/iTerm2): A=prompt start,
# B=command start, C=output start, D[;exit]=command end. Used for command blocks.
OSC133_RE = re.compile(r"\x1b\]133;([A-D])([^\x07\x1b]*)(?:\x07|\x1b\\)")
# Working-directory reports: OSC 9;9 (Windows path) and OSC 7 (file:// URL).
# Used so a new tab/split opens in the current tab's directory.
OSC99_RE = re.compile(r'\x1b\]9;9;"?([^"\x07\x1b]+)"?(?:\x07|\x1b\\)')
OSC7_RE = re.compile(r"\x1b\]7;file://[^/]*(/[^\x07\x1b]*)(?:\x07|\x1b\\)")
# OSC 52: a program sets the system clipboard (e.g. yank in vim over SSH). Write-only.
OSC52_RE = re.compile(r"\x1b\]52;[cpqs0-7]*;([A-Za-z0-9+/=]+)(?:\x07|\x1b\\)")
# PowerShell shell-integration: wrap the existing prompt (oh-my-posh-safe) to emit
# OSC 133 markers so command blocks work. Runs once, after the profile loads.
PS_SHELL_INTEGRATION = (
    "if(-not $global:__ET_SI){$global:__ET_SI=$true;"
    "$global:__ET_OP=$function:prompt;"
    "function global:prompt{"
    "$c=$global:LASTEXITCODE;if($null -eq $c){if($?){$c=0}else{$c=1}};"
    "\"$([char]27)]133;D;$c$([char]7)$([char]27)]133;A$([char]7)"
    "$([char]27)]9;9;$($PWD.ProviderPath)$([char]7)\""
    "+(& $global:__ET_OP)+"
    "\"$([char]27)]133;B$([char]7)\"}}"
)

DEFAULT_SHELL = "powershell.exe"


def available_shells():
    """List of shells available on this machine: (name, command)."""
    shells = [("PowerShell", "powershell.exe")]
    if shutil.which("pwsh"):
        shells.append(("PowerShell 7", "pwsh.exe"))
    shells.append(("Command Prompt", "cmd.exe"))
    for p in (r"C:\Program Files\Git\bin\bash.exe",
              r"C:\Program Files\Git\usr\bin\bash.exe"):
        if os.path.exists(p):
            shells.append(("Git Bash", p))
            break
    if shutil.which("wsl"):
        shells.append(("WSL (Linux)", "wsl.exe"))
    return shells

from PySide6.QtCore import Qt, QObject, Signal, QRect, QPointF, QTimer
from PySide6.QtGui import (
    QFont, QFontMetrics, QPainter, QColor, QKeyEvent, QPen,
    QTextLayout, QTextCharFormat, QTextOption, QFontDatabase, QSyntaxHighlighter,
    QPixmap, QIcon,
)
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QMenu,
    QSplitter, QDialog, QSpinBox, QPushButton, QLabel, QColorDialog, QFontComboBox,
    QTabWidget, QLineEdit, QPlainTextEdit, QFileDialog, QSlider, QInputDialog,
    QTextEdit, QComboBox, QScrollArea, QFrame, QSystemTrayIcon,
)

import i18n


# ---- Standard ANSI colors ----
BASE_BG = QColor("#0d1117")
BASE_FG = QColor("#e6edf3")

# ---- Settings (saved/loaded from a file next to the program) ----
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(SCRIPT_DIR, "easyter_config.json")
SESSION_PATH = os.path.join(SCRIPT_DIR, "easyter_session.json")
SETTINGS = {
    "font_family": "JetBrains Mono",
    "font_size": 13,
    "bg": "#0d1117",
    "fg": "#e6edf3",
    "palette": None,    # custom ANSI palette (None = default)
    "opacity": 1.0,     # background opacity (1.0 opaque, less = more transparent)
    "language": "en",   # UI language: "en" (default) or "ar" - applied on next launch
    "bg_image": "",            # optional background image path ("" = none); user-chosen
    "bg_image_opacity": 0.35,  # how strongly the background image shows through (0..1)
    "start_dir": "",           # folder new shells open in ("" = home, never system32)
    "cursor_style": "block",   # cursor shape: "block" | "bar" | "underline"
    "shell_integration": True, # inject OSC 133 into PowerShell for command blocks
    "notify_on_finish": True,  # desktop notification when a long command finishes unfocused
    "quake_enabled": True,     # global hotkey (Ctrl+Alt+`) to summon/hide EasyTer from anywhere
    "paste_protection": True,  # confirm before pasting multi-line / large clipboard text
    "scrollback": 10000,       # lines of history kept per terminal
}


def bg_rgba():
    """rgba string for the background at the current opacity (for stylesheets)."""
    c = QColor(SETTINGS["bg"])
    return f"rgba({c.red()},{c.green()},{c.blue()},{SETTINGS.get('opacity', 1.0):.3f})"


# ---- optional background image (user-chosen, drawn behind the text) ----
_BG_PIXMAP = {"path": None, "pm": None}   # original loaded pixmap, cached by path


def _bg_image_scaled(w, h):
    """Return the background image scaled to *cover* a w x h box, or None.
    Loads/caches the source pixmap; returns None if no image is set or it fails."""
    path = SETTINGS.get("bg_image") or ""
    if not path or w <= 0 or h <= 0:
        return None
    if _BG_PIXMAP["path"] != path:
        pm = QPixmap(path)
        _BG_PIXMAP["path"] = path
        _BG_PIXMAP["pm"] = pm if not pm.isNull() else None
    pm = _BG_PIXMAP["pm"]
    if pm is None:
        return None
    return pm.scaled(w, h, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)

# Full ANSI palette for the Jonathan Blow (naysayer) theme: green/teal/tan
NAYSAYER_ANSI = {
    "black": "#06343a", "red": "#e0556f", "green": "#44b340",
    "brown": "#e6db74", "yellow": "#e6db74", "blue": "#66d9ef",
    "magenta": "#ae81ff", "cyan": "#2ec09c", "white": "#d1b897",
    "brightblack": "#4a6b6b", "brightred": "#ff6b81",
    "brightgreen": "#8cde94", "brightyellow": "#f4e07a",
    "brightblue": "#7ad0c6", "brightmagenta": "#c9a0ff",
    "brightcyan": "#a1efe4", "brightwhite": "#ffffff",
}

THEMES = {
    "داكن هادئ": ("#0d1117", "#e6edf3", None),
    "داكن دافئ": ("#1a1612", "#ece0d0", None),
    "أسود مطلق": ("#000000", "#d0d0d0", None),
    "سولاريزد داكن": ("#002b36", "#93a1a1", None),
    "فاتح نهاريّ": ("#fbfbfb", "#1b1b1b", None),
    "Jonathan Blow": ("#062329", "#d1b897", NAYSAYER_ANSI),   # full naysayer
    "hypr-waves": ("#141929", "#E0E4EC", {                      # ported from h4ni0/pi
        "black": "#2A2E3D", "red": "#E8364F", "green": "#6EC8A8",
        "brown": "#F9C846", "yellow": "#F9C846", "blue": "#3A7CA5",
        "magenta": "#A8245E", "cyan": "#5EC4D4", "white": "#E0E4EC",
        "brightblack": "#4A4E5D", "brightred": "#FF4D63",
        "brightgreen": "#7ED4E0", "brightyellow": "#FFD866",
        "brightblue": "#4A9CC5", "brightmagenta": "#C43878",
        "brightcyan": "#7ED4E0", "brightwhite": "#D8DCE4",
    }),
    # ---- popular color schemes (switch freely from Settings > Themes) ----
    "Kali Dark": ("#060a12", "#b6e8e8", {
        "black": "#0d1117", "red": "#ff5370", "green": "#3ad900",
        "brown": "#e7c547", "yellow": "#e7c547", "blue": "#2a9df4",
        "magenta": "#c792ea", "cyan": "#2cf0f0", "white": "#b6e8e8",
        "brightblack": "#37505a", "brightred": "#ff869a", "brightgreen": "#6bff4a",
        "brightyellow": "#ffe066", "brightblue": "#6cc4ff", "brightmagenta": "#e0b6ff",
        "brightcyan": "#84ffff", "brightwhite": "#ffffff",
    }),
    "Dracula": ("#282a36", "#f8f8f2", {
        "black": "#21222c", "red": "#ff5555", "green": "#50fa7b",
        "brown": "#f1fa8c", "yellow": "#f1fa8c", "blue": "#bd93f9",
        "magenta": "#ff79c6", "cyan": "#8be9fd", "white": "#f8f8f2",
        "brightblack": "#6272a4", "brightred": "#ff6e6e", "brightgreen": "#69ff94",
        "brightyellow": "#ffffa5", "brightblue": "#d6acff", "brightmagenta": "#ff92df",
        "brightcyan": "#a4ffff", "brightwhite": "#ffffff",
    }),
    "Nord": ("#2e3440", "#d8dee9", {
        "black": "#3b4252", "red": "#bf616a", "green": "#a3be8c",
        "brown": "#ebcb8b", "yellow": "#ebcb8b", "blue": "#81a1c1",
        "magenta": "#b48ead", "cyan": "#88c0d0", "white": "#e5e9f0",
        "brightblack": "#4c566a", "brightred": "#bf616a", "brightgreen": "#a3be8c",
        "brightyellow": "#ebcb8b", "brightblue": "#81a1c1", "brightmagenta": "#b48ead",
        "brightcyan": "#8fbcbb", "brightwhite": "#eceff4",
    }),
    "Gruvbox Dark": ("#282828", "#ebdbb2", {
        "black": "#282828", "red": "#cc241d", "green": "#98971a",
        "brown": "#d79921", "yellow": "#d79921", "blue": "#458588",
        "magenta": "#b16286", "cyan": "#689d6a", "white": "#a89984",
        "brightblack": "#928374", "brightred": "#fb4934", "brightgreen": "#b8bb26",
        "brightyellow": "#fabd2f", "brightblue": "#83a598", "brightmagenta": "#d3869b",
        "brightcyan": "#8ec07c", "brightwhite": "#ebdbb2",
    }),
    "Tokyo Night": ("#1a1b26", "#c0caf5", {
        "black": "#15161e", "red": "#f7768e", "green": "#9ece6a",
        "brown": "#e0af68", "yellow": "#e0af68", "blue": "#7aa2f7",
        "magenta": "#bb9af7", "cyan": "#7dcfff", "white": "#a9b1d6",
        "brightblack": "#414868", "brightred": "#f7768e", "brightgreen": "#9ece6a",
        "brightyellow": "#e0af68", "brightblue": "#7aa2f7", "brightmagenta": "#bb9af7",
        "brightcyan": "#7dcfff", "brightwhite": "#c0caf5",
    }),
    "Catppuccin Mocha": ("#1e1e2e", "#cdd6f4", {
        "black": "#45475a", "red": "#f38ba8", "green": "#a6e3a1",
        "brown": "#f9e2af", "yellow": "#f9e2af", "blue": "#89b4fa",
        "magenta": "#f5c2e7", "cyan": "#94e2d5", "white": "#bac2de",
        "brightblack": "#585b70", "brightred": "#f38ba8", "brightgreen": "#a6e3a1",
        "brightyellow": "#f9e2af", "brightblue": "#89b4fa", "brightmagenta": "#f5c2e7",
        "brightcyan": "#94e2d5", "brightwhite": "#a6adc8",
    }),
    "One Dark": ("#282c34", "#abb2bf", {
        "black": "#282c34", "red": "#e06c75", "green": "#98c379",
        "brown": "#e5c07b", "yellow": "#e5c07b", "blue": "#61afef",
        "magenta": "#c678dd", "cyan": "#56b6c2", "white": "#abb2bf",
        "brightblack": "#5c6370", "brightred": "#e06c75", "brightgreen": "#98c379",
        "brightyellow": "#e5c07b", "brightblue": "#61afef", "brightmagenta": "#c678dd",
        "brightcyan": "#56b6c2", "brightwhite": "#ffffff",
    }),
    "Monokai": ("#272822", "#f8f8f2", {
        "black": "#272822", "red": "#f92672", "green": "#a6e22e",
        "brown": "#f4bf75", "yellow": "#f4bf75", "blue": "#66d9ef",
        "magenta": "#ae81ff", "cyan": "#a1efe4", "white": "#f8f8f2",
        "brightblack": "#75715e", "brightred": "#f92672", "brightgreen": "#a6e22e",
        "brightyellow": "#f4bf75", "brightblue": "#66d9ef", "brightmagenta": "#ae81ff",
        "brightcyan": "#a1efe4", "brightwhite": "#f9f8f5",
    }),
    "Solarized Dark": ("#002b36", "#839496", {
        "black": "#073642", "red": "#dc322f", "green": "#859900",
        "brown": "#b58900", "yellow": "#b58900", "blue": "#268bd2",
        "magenta": "#d33682", "cyan": "#2aa198", "white": "#eee8d5",
        "brightblack": "#586e75", "brightred": "#cb4b16", "brightgreen": "#586e75",
        "brightyellow": "#657b83", "brightblue": "#839496", "brightmagenta": "#6c71c4",
        "brightcyan": "#93a1a1", "brightwhite": "#fdf6e3",
    }),
    "Tomorrow Night": ("#1d1f21", "#c5c8c6", {
        "black": "#1d1f21", "red": "#cc6666", "green": "#b5bd68",
        "brown": "#f0c674", "yellow": "#f0c674", "blue": "#81a2be",
        "magenta": "#b294bb", "cyan": "#8abeb7", "white": "#c5c8c6",
        "brightblack": "#969896", "brightred": "#cc6666", "brightgreen": "#b5bd68",
        "brightyellow": "#f0c674", "brightblue": "#81a2be", "brightmagenta": "#b294bb",
        "brightcyan": "#8abeb7", "brightwhite": "#ffffff",
    }),
}


THEMES_DIR = os.path.join(os.path.expanduser("~"), ".easyter", "themes")


def load_themes():
    """Loads extra themes from ~/.easyter/themes/*.json (format: name/bg/fg/ansi)."""
    for fpath in sorted(glob.glob(os.path.join(THEMES_DIR, "*.json"))):
        try:
            with open(fpath, encoding="utf-8") as f:
                d = json.load(f)
            name = d.get("name") or os.path.splitext(os.path.basename(fpath))[0]
            THEMES[name] = (d["bg"], d["fg"], d.get("ansi"))
        except Exception:
            pass


def load_settings():
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            SETTINGS.update(json.load(f))
    except Exception:
        pass


def save_settings():
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(SETTINGS, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def apply_base_colors():
    global BASE_BG, BASE_FG
    BASE_BG = QColor(SETTINGS["bg"])
    BASE_FG = QColor(SETTINGS["fg"])
    apply_palette()


DEFAULT_PALETTE = {
    "black": "#0d1117", "red": "#ff6b6b", "green": "#7ee787",
    "brown": "#e3b341", "yellow": "#e3b341", "blue": "#6ca0f6",
    "magenta": "#d2a8ff", "cyan": "#56d4dd", "white": "#e6edf3",
    "brightblack": "#6e7681", "brightred": "#ff8a8a",
    "brightgreen": "#a2f5b0", "brightyellow": "#f2cc60",
    "brightblue": "#8db4f8", "brightmagenta": "#e0c1ff",
    "brightcyan": "#7ee0e6", "brightwhite": "#ffffff",
}
PALETTE = dict(DEFAULT_PALETTE)   # active palette (changes with the theme)


def apply_palette():
    """Sets the active ANSI palette from settings (theme palette or default)."""
    global PALETTE
    pal = SETTINGS.get("palette")
    PALETTE = {**DEFAULT_PALETTE, **pal} if pal else dict(DEFAULT_PALETTE)


def mix_hex(a, b, t):
    """Mixes two hex colors: t=0 => a, t=1 => b. For deriving UI colors from the theme."""
    a = (a or "#000000").lstrip("#")
    b = (b or "#ffffff").lstrip("#")
    if len(a) == 3:
        a = "".join(c * 2 for c in a)
    if len(b) == 3:
        b = "".join(c * 2 for c in b)
    try:
        ar, ag, ab = int(a[0:2], 16), int(a[2:4], 16), int(a[4:6], 16)
        br, bg_, bb = int(b[0:2], 16), int(b[2:4], 16), int(b[4:6], 16)
    except Exception:
        return "#" + a
    r = round(ar + (br - ar) * t)
    g = round(ag + (bg_ - ag) * t)
    bl = round(ab + (bb - ab) * t)
    return f"#{max(0,min(255,r)):02x}{max(0,min(255,g)):02x}{max(0,min(255,bl)):02x}"


def ui_theme_colors():
    """Derives a full set of UI colors from the user's theme (bg/fg/palette)."""
    bg, fg = SETTINGS["bg"], SETTINGS["fg"]
    accent = PALETTE.get("blue") or PALETTE.get("cyan") or fg
    return {
        "bg": bg,
        "fg": fg,
        "chrome": mix_hex(bg, fg, 0.06),     # UI bar/background
        "chrome2": mix_hex(bg, fg, 0.13),    # unselected tab
        "border": mix_hex(bg, fg, 0.22),     # borders
        "dim": mix_hex(bg, fg, 0.55),        # dim text
        "accent": accent,                    # focus/selection accent
        "hover": mix_hex(bg, fg, 0.18),
    }


def resolve_color(name, is_bg):
    if name == "default" or name is None:
        return BASE_BG if is_bg else BASE_FG
    if name in PALETTE:
        return QColor(PALETTE[name])
    # truecolor / 256 arrives as a six-digit hex
    if isinstance(name, str) and len(name) == 6:
        try:
            return QColor("#" + name)
        except Exception:
            pass
    return BASE_BG if is_bg else BASE_FG


_ARABIC_FONT_LOADED = False


def _ensure_arabic_font():
    """Load the Amiri font into Qt's font database so Arabic renders with it (without installing it on Windows)."""
    global _ARABIC_FONT_LOADED
    if _ARABIC_FONT_LOADED:
        return
    # Load from the bundled fonts/ folder first (ships with the repo so connected
    # Arabic works from a fresh clone), then fall back to the user's ~/.wezterm-fonts.
    for fn in ("Amiri-Regular.ttf", "Amiri-Bold.ttf",
               "Vazirmatn.ttf", "NotoNaskhArabic.ttf"):
        for base in (os.path.join(SCRIPT_DIR, "fonts"),
                     os.path.join(os.path.expanduser("~"), ".wezterm-fonts")):
            path = os.path.join(base, fn)
            if os.path.exists(path):
                try:
                    QFontDatabase.addApplicationFont(path)
                except Exception:
                    pass
                break
    _ARABIC_FONT_LOADED = True


# ════════════════════════════════════════════════════════════════════════
#  Claude mode: reverse UAX#9 (rule L2) - convert Claude's visual line to logical
#  Claude (Ink) applies BiDi itself and emits a reversed visual order. To fix it:
#  we reverse visual -> logical, then Qt re-applies BiDi and shaping correctly.
#  (PowerShell already emits logical order, so this mode is enabled for Claude only.)
# ════════════════════════════════════════════════════════════════════════

def _is_ltr_char(ch):
    if not ch:
        return False
    o = ord(ch[0])   # base codepoint only; a cell may hold emoji+selector/ZWJ
    return (0x41 <= o <= 0x5A) or (0x61 <= o <= 0x7A) or \
           (0x30 <= o <= 0x39) or (0xC0 <= o <= 0x2AF)


def _is_inner_ltr(ch):
    # characters that stay inside an LTR island (paths, file names, version numbers...)
    return ch in "._-/:\\@~+=#&%" or _is_ltr_char(ch)


def _is_arabic_letter(ch):
    if not ch:
        return False
    o = ord(ch[0])   # base codepoint only; a cell may hold emoji+selector/ZWJ
    return (0x0600 <= o <= 0x06FF) or (0x0750 <= o <= 0x077F) or \
           (0xFB50 <= o <= 0xFDFF) or (0xFE70 <= o <= 0xFEFF)


def line_is_rtl_visual(text):
    """Is the line predominantly Arabic (so Claude reversed it)?"""
    ar = lt = 0
    for ch in text:
        if _is_arabic_letter(ch):
            ar += 1
        elif _is_ltr_char(ch) and ch.isalpha():
            lt += 1
    return ar > 0 and ar >= lt


_LTR_PUNCT = "._-/:\\@~+=#&%"


def unbidi_rtl_line(line):
    """Reverse L2 for an RTL-base line: reverse the whole line then re-reverse LTR islands. Punctuation
    is joined to the island only if a Latin letter follows it (so it stays inside config.txt but leaves
    the end of a number like "01." so it does not flip to ".01")."""
    rev = line[::-1]
    out = []
    i, n = 0, len(rev)
    while i < n:
        if _is_ltr_char(rev[i]):
            j = i
            while j < n:
                cj = rev[j]
                if _is_ltr_char(cj):
                    j += 1
                elif cj in _LTR_PUNCT and j + 1 < n and _is_ltr_char(rev[j + 1]):
                    j += 1
                elif cj == " " and j + 1 < n and _is_ltr_char(rev[j + 1]):
                    j += 1
                else:
                    break
            out.append(rev[i:j][::-1])
            i = j
        else:
            out.append(rev[i])
            i += 1
    return "".join(out)


def _has_arabic(text):
    return any(_is_arabic_letter(c) for c in text)


def reverse_arabic_runs(line):
    """Reverse each Arabic run in place - for LTR-base lines that contain Arabic islands
    (e.g. 'What are you working on ؟كتدعاسم...' - the Arabic part is reversed)."""
    out = []
    i, n = 0, len(line)
    while i < n:
        if _is_arabic_letter(line[i]):
            j = i
            while j < n and (_is_arabic_letter(line[j]) or
                             (line[j] == ' ' and j + 1 < n and _is_arabic_letter(line[j + 1]))):
                j += 1
            out.append(line[i:j][::-1])
            i = j
        else:
            out.append(line[i])
            i += 1
    return "".join(out)


def restore_bidi_line(text):
    """Convert Claude's visual line to logical based on its base direction. None = no change.
    - RTL base (Arabic-dominant): reverse the whole line (with LTR islands).
    - LTR base with Arabic: reverse only the Arabic runs in place.
    - pure English: no change."""
    if line_is_rtl_visual(text):
        return unbidi_rtl_line(text)
    if _has_arabic(text):
        return reverse_arabic_runs(text)
    return None


# ════════════════════════════════════════════════════════════════════════
#  Plugin system (Python): ~/.easyter/init.py is loaded at startup and gives
#  the power user an API: keybindings, commands, themes, event hooks, status segments.
# ════════════════════════════════════════════════════════════════════════
PLUGIN_DIR = os.path.join(os.path.expanduser("~"), ".easyter")
PLUGIN_INIT = os.path.join(PLUGIN_DIR, "init.py")


def _key_from_token(tok):
    tok = tok.strip()
    if len(tok) == 1 and tok.isalpha():
        return Qt.Key_A + (ord(tok.upper()) - ord("A"))
    if len(tok) == 1 and tok.isdigit():
        return Qt.Key_0 + int(tok)
    try:
        return getattr(Qt, "Key_" + tok.capitalize())
    except Exception:
        return None


def _parse_combo(combo):
    parts = [p.strip().lower() for p in combo.split("+")]
    return (("ctrl" in parts), ("alt" in parts), ("shift" in parts),
            _key_from_token(parts[-1]))


class _PluginAPI:
    """The API that init.py uses via: import easyter as et"""

    def __init__(self):
        self.keybinds = []          # (ctrl, alt, shift, key, cb)
        self.commands = []          # (name, cb)
        self.hooks = {}             # event -> [cb]
        self.status_segments = []   # [cb]
        self.ui_style = None        # extra QSS: a string or a function(colors)->string

    def keybind(self, combo):
        spec = _parse_combo(combo)

        def deco(fn):
            self.keybinds.append((*spec, fn, combo))
            return fn
        return deco

    def command(self, name):
        def deco(fn):
            self.commands.append((name, fn))
            return fn
        return deco

    def add_theme(self, name, bg, fg, ansi=None):
        THEMES[name] = (bg, fg, ansi)

    def set_ui_style(self, qss):
        """Customize the UI look (tabs/borders/menus/dialogs) via Qt QSS.
        Pass a QSS string, or a function that takes the theme color dict and returns a string:
            @et.ui_style
            def _(c): return f'QTabBar::tab{{border-radius:0;}}'
        It is applied on top of the auto-derived theme style, so it tweaks/overrides as you wish."""
        self.ui_style = qss

    def ui_style(self, fn):
        """Decorator equivalent to set_ui_style with a function: @et.ui_style then def _(colors):"""
        self.ui_style = fn
        return fn

    def restyle(self):
        """Re-applies the UI style (call it after changing ui_style dynamically)."""
        try:
            for w in QApplication.topLevelWidgets():
                if isinstance(w, MainWindow):
                    w._style_window()
        except Exception as ex:
            print(f"[easyter restyle] {ex}")

    def on(self, event):
        def deco(fn):
            self.hooks.setdefault(event, []).append(fn)
            return fn
        return deco

    def status_segment(self):
        def deco(fn):
            self.status_segments.append(fn)
            return fn
        return deco

    def emit(self, event, *args):
        for cb in self.hooks.get(event, []):
            try:
                cb(*args)
            except Exception as ex:
                print(f"[easyter hook {event}] {ex}")


PLUGINS = _PluginAPI()


def run_plugin_keybind(pane, ctrl, alt, shift, key):
    """Runs a matching plugin keybinding if found; returns True then."""
    for kb in PLUGINS.keybinds:
        kc, ka, ks, kk, cb = kb[0], kb[1], kb[2], kb[3], kb[4]
        if kk == key and kc == ctrl and ka == alt and ks == shift:
            try:
                cb(pane)
            except Exception as ex:
                print(f"[easyter keybind] {ex}")
            return True
    return False


def load_plugins():
    """Loads ~/.easyter/init.py with the easyter module available for import."""
    import types
    mod = types.ModuleType("easyter")
    for n in dir(PLUGINS):
        if not n.startswith("_"):
            setattr(mod, n, getattr(PLUGINS, n))
    sys.modules["easyter"] = mod
    if not os.path.exists(PLUGIN_INIT):
        return
    try:
        with open(PLUGIN_INIT, encoding="utf-8") as f:
            code = compile(f.read(), PLUGIN_INIT, "exec")
        exec(code, {"__name__": "__easyter_init__", "__file__": PLUGIN_INIT})
    except Exception:
        import traceback
        print("[easyter init.py error]")
        traceback.print_exc()


_SGR_NAMES = {
    "black": 30, "red": 31, "green": 32, "brown": 33, "yellow": 33,
    "blue": 34, "magenta": 35, "cyan": 36, "white": 37,
    "brightblack": 90, "brightred": 91, "brightgreen": 92, "brightyellow": 93,
    "brightblue": 94, "brightmagenta": 95, "brightcyan": 96, "brightwhite": 97,
}


def _color_codes(val, base):
    """Converts a pyte color (name/hex) into SGR codes (base=30 for text, 40 for background)."""
    if not val or val == "default":
        return None
    if val in _SGR_NAMES:
        n = _SGR_NAMES[val]
        return str(n + (base - 30))
    if isinstance(val, str) and len(val) == 6:
        try:
            r, g, b = int(val[0:2], 16), int(val[2:4], 16), int(val[4:6], 16)
            return f"{38 if base == 30 else 48};2;{r};{g};{b}"
        except ValueError:
            return None
    return None


def line_to_ansi(row, ncols):
    """Serializes a pyte line into text that preserves its colors (for re-streaming on resize)."""
    out = []
    cur = None
    for c in range(ncols):
        ch = row[c]
        st = (ch.fg, ch.bg, ch.bold, ch.reverse)
        if st != cur:
            codes = ["0"]
            if ch.bold:
                codes.append("1")
            if ch.reverse:
                codes.append("7")
            fg = _color_codes(ch.fg, 30)
            bg = _color_codes(ch.bg, 40)
            if fg:
                codes.append(fg)
            if bg:
                codes.append(bg)
            out.append("\x1b[" + ";".join(codes) + "m")
            cur = st
        out.append(ch.data or " ")
    return "".join(out).rstrip() + "\x1b[0m"


class PtyBackend(QObject):
    """A live ConPTY session + a pyte screen emulator."""

    data_ready = Signal()
    exited = Signal()
    alt_screen_changed = Signal(bool)  # entering/leaving the alternate screen (a TUI like Claude)
    command_ended = Signal(object)     # a command finished (OSC 133 D); arg = exit code or None
    clipboard_set = Signal(str)        # a program set the clipboard via OSC 52

    def __init__(self, cols, rows, command="powershell.exe", start_cwd=None):
        super().__init__()
        self.lock = threading.Lock()
        hist = max(1000, int(SETTINGS.get("scrollback", 10000)))
        self.screen = pyte.HistoryScreen(cols, rows, history=hist, ratio=0.5)
        self.stream = pyte.Stream(self.screen)
        self._alive = True
        self.alt_screen = False     # is a full-screen TUI program active now?
        self.bracketed_paste = False  # does the program want bracketed paste (?2004h)?
        self.cwd = None             # current working directory (from OSC 9;9 / OSC 7)
        self._scan_tail = ""        # tail to catch a sequence split across two reads
        self._carry = ""            # incomplete sequence carried to the next read
        # command blocks: each entry = [prompt_abs_line, exit_code_or_None],
        # populated from OSC 133 shell-integration markers (empty if the shell
        # doesn't emit them — the feature is then simply inactive)
        self.command_marks = []
        # remove a short fake API key (it breaks `claude` inside the terminal; the subscription is enough)
        env = dict(os.environ)
        key = env.get("ANTHROPIC_API_KEY", "")
        if key and len(key) < 40:
            env.pop("ANTHROPIC_API_KEY", None)
        # a list not a string: keeps paths with spaces (like Git Bash) intact
        spec = command if isinstance(command, list) else [command]
        # auto-enable command blocks for PowerShell by appending an OSC 133 prompt
        # wrapper that runs after the profile (coexists with oh-my-posh)
        if SETTINGS.get("shell_integration", True):
            exe = spec[0].lower()
            has_cmd = any(a.lower() in ("-command", "-c", "-file", "-encodedcommand") for a in spec)
            if ("powershell" in exe or "pwsh" in exe) and not has_cmd:
                spec = spec + ["-NoExit", "-Command", PS_SHELL_INTEGRATION]
        # start the shell in: the requested dir (new tab/split inherits the
        # current tab's directory), else the configured start folder, else home —
        # never inheriting whatever launched EasyTer (often C:\Windows\system32)
        start_dir = start_cwd or SETTINGS.get("start_dir") or os.path.expanduser("~")
        if not (isinstance(start_dir, str) and os.path.isdir(start_dir)):
            start_dir = os.path.expanduser("~")
        self.proc = PtyProcess.spawn(spec, dimensions=(rows, cols), env=env, cwd=start_dir)
        threading.Thread(target=self._reader, daemon=True).start()

    def _reader(self):
        try:
            while self._alive:
                data = self.proc.read(65536)   # bigger reads = fewer feed cycles on huge output
                if not data:
                    continue
                self._scan_alt(data)                 # detect the alternate screen (on the raw data)
                self._scan_cwd(data)                 # track the working directory
                self._scan_osc52(data)               # programs setting the clipboard
                data = self._carry + data
                data = KITTY_KB_RE.sub("", data)      # strip the stray 'u'
                # carry any incomplete sequence at the end of the chunk to the next read (avoid splitting)
                m = INCOMPLETE_TAIL_RE.search(data)
                if m and m.group():
                    self._carry = data[m.start():]
                    data = data[:m.start()]
                else:
                    self._carry = ""
                if data:
                    self._feed_with_marks(data)
                    self.data_ready.emit()
        except EOFError:
            pass
        except Exception:
            pass
        finally:
            try:
                self.exited.emit()
            except Exception:
                pass

    def _feed_with_marks(self, data):
        """Feed data to pyte, recording OSC 133 command-block marks as we go.

        We split the stream at each marker so we can read the cursor position
        exactly where the marker sits (= the prompt/command line). If the shell
        emits no OSC 133, this is just a normal feed."""
        if "\x1b]133;" not in data:
            with self.lock:
                self.stream.feed(data)
            return
        pos = 0
        ended = []
        with self.lock:
            for m in OSC133_RE.finditer(data):
                seg = data[pos:m.start()]
                if seg:
                    self.stream.feed(seg)
                kind = m.group(1)
                params = (m.group(2) or "").lstrip(";")
                abs_line = len(self.screen.history.top) + self.screen.cursor.y
                if kind == "A":                     # a new prompt starts here
                    self.command_marks.append([abs_line, None])
                    if len(self.command_marks) > 2000:
                        del self.command_marks[:1000]
                elif kind == "D":                           # the command just finished
                    code = None
                    if params:
                        try:
                            code = int(params.split(";")[0])
                        except ValueError:
                            code = None
                    if self.command_marks:
                        self.command_marks[-1][1] = code
                    ended.append(code)
                pos = m.end()
            tail = data[pos:]
            if tail:
                self.stream.feed(tail)
        for code in ended:                 # notify outside the lock
            self.command_ended.emit(code)

    def _scan_alt(self, data):
        """Detects entering/leaving the alternate screen (?1049h/?1049l) to enable Claude mode automatically."""
        buf = self._scan_tail + data
        ih = buf.rfind("\x1b[?1049h")
        il = buf.rfind("\x1b[?1049l")
        new = self.alt_screen
        if ih >= 0 or il >= 0:
            new = ih > il        # active if the last toggle was an enter
        # bracketed paste mode (?2004h/l): track so paste can be wrapped safely
        bh = buf.rfind("\x1b[?2004h")
        bl = buf.rfind("\x1b[?2004l")
        if bh >= 0 or bl >= 0:
            self.bracketed_paste = bh > bl
        self._scan_tail = buf[-8:]
        if new != self.alt_screen:
            self.alt_screen = new
            self.alt_screen_changed.emit(new)

    def _scan_cwd(self, data):
        """Track the working directory from OSC 9;9 (Windows path) or OSC 7 (URL)."""
        if "\x1b]9;9;" not in data and "\x1b]7;" not in data:
            return
        cwd = None
        for m in OSC99_RE.finditer(data):
            cwd = m.group(1)
        if cwd is None:
            for m in OSC7_RE.finditer(data):
                cwd = self._osc7_to_path(m.group(1))
        if cwd:
            cwd = cwd.strip().rstrip("\\/") or cwd.strip()
            try:
                if os.path.isdir(cwd):
                    self.cwd = cwd
            except Exception:
                pass

    def _scan_osc52(self, data):
        """A program set the clipboard via OSC 52 (write-only; queries ignored)."""
        if "\x1b]52;" not in data:
            return
        import base64
        for m in OSC52_RE.finditer(data):
            try:
                txt = base64.b64decode(m.group(1)).decode("utf-8", "replace")
            except Exception:
                continue
            if txt:
                self.clipboard_set.emit(txt)

    @staticmethod
    def _osc7_to_path(p):
        try:
            import urllib.parse
            p = urllib.parse.unquote(p)
        except Exception:
            pass
        m = re.match(r"^/([A-Za-z]):?(/.*)?$", p)   # /C:/Users or /c/Users -> C:\Users
        if m:
            return m.group(1) + ":" + (m.group(2) or "/").replace("/", "\\")
        return p

    def write(self, text):
        if not self._alive:
            return
        try:
            self.proc.write(text)
        except Exception:
            pass

    def resize(self, cols, rows):
        # ConPTY (conhost) reflows its content and repaints automatically on resize
        # (confirmed by experiment + ResizePseudoConsole docs). Keeping a manual re-stream
        # accumulated line fragmentation and duplication across successive zooms. So we just resize pyte
        # in place (preserving history and cursor) and let ConPTY repaint - as terminal
        # makers do. This is the same behavior in the alternate screen (Claude) and the normal one.
        with self.lock:
            try:
                self.screen.resize(rows, cols)
            except Exception:
                pass
        try:
            self.proc.setwinsize(rows, cols)
        except Exception:
            pass

    def close(self):
        self._alive = False
        try:
            self.proc.terminate(force=True)
        except Exception:
            pass


class TerminalWidget(QWidget):
    def __init__(self, command=None, start_cwd=None):
        super().__init__()
        self.command = command or DEFAULT_SHELL
        self._start_cwd = start_cwd      # open this shell in this dir (new tab/split)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setAutoFillBackground(True)

        self.font_size = SETTINGS["font_size"]
        self._init_font()

        self.cols = 110
        self.rows = 32
        self.scroll_offset = 0

        # mouse text-selection state (absolute coordinates across the whole history)
        self.sel_anchor = None   # (abs_line, col)
        self.sel_point = None
        self._paint_start = 0    # first absolute line shown in the last paint

        # Claude mode: reverses Claude's visual BiDi to logical. Enabled **automatically** when
        # Claude enters the alternate screen, and stops when returning to PowerShell.
        # F2 toggles between auto and manual only when needed.
        self.claude_mode = False
        self.auto_follow = True

        # search state (Ctrl+F): matching lines + the current index
        self.search_bar = None
        self.search_term = ""
        self.search_matches = []   # absolute line numbers that match
        self.search_idx = -1

        # caches for lines (PowerShell path) and for runs (Claude grid engine)
        self._layout_cache = {}
        self._run_cache = {}

        # throttle the paint rate: coalesce Claude's fast bursts into one paint every ~16ms
        self._repaint_timer = QTimer(self)
        self._repaint_timer.setSingleShot(True)
        self._repaint_timer.timeout.connect(self.update)

        # cursor blink
        self._blink = True
        self._blink_timer = QTimer(self)
        self._blink_timer.timeout.connect(self._toggle_blink)
        self._blink_timer.start(530)

        # debounce resize: only resize after the corner drag stops (~140ms)
        self._resize_timer = QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.timeout.connect(self._recompute_size)

        self.setMouseTracking(True)   # needed for Ctrl+hover link hinting
        self._exited = False
        self._start_backend(self.command)

        self.resize(self.cols * self.cw, self.rows * self.ch)

    def _start_backend(self, command):
        self.command = command
        self.backend = PtyBackend(self.cols, self.rows, command=command, start_cwd=self._start_cwd)
        self.backend.data_ready.connect(self._on_data)
        self.backend.exited.connect(self._on_exit)
        self.backend.alt_screen_changed.connect(self._on_alt_screen)
        self.backend.command_ended.connect(self._on_command_ended)
        self.backend.clipboard_set.connect(
            lambda txt: QApplication.clipboard().setText(txt))
        self._cmd_started = None      # time the user submitted a command (for finish notify)
        self._exited = False

    def restart_with(self, command):
        """Closes the current shell and restarts the pane with a new shell (resetting state)."""
        try:
            self.backend.data_ready.disconnect(self._on_data)
            self.backend.exited.disconnect(self._on_exit)
            self.backend.alt_screen_changed.disconnect(self._on_alt_screen)
        except Exception:
            pass
        self.backend.close()
        self.scroll_offset = 0
        self.sel_anchor = self.sel_point = None
        self.claude_mode = False
        self.auto_follow = True
        self._layout_cache.clear()
        self._run_cache.clear()
        self._start_backend(command)
        self._set_title()
        self.update()
        self.setFocus()

    def _session(self):
        """Walks up to the session (tab) that contains this pane."""
        w = self.parentWidget()
        while w is not None and not isinstance(w, SessionWidget):
            w = w.parentWidget()
        return w

    # ---- plugin API ----
    def send(self, text):
        self.backend.write(text)

    def set_title(self, title):
        sess = self._session()
        w = self.window()
        if sess and hasattr(w, "set_tab_title"):
            w.set_tab_title(sess, title)

    def _init_font(self):
        _ensure_arabic_font()
        self.font = QFont()
        # the font chosen in settings first, then a fallback chain (ensures Arabic coverage)
        self.font.setFamilies([
            SETTINGS["font_family"], "JetBrains Mono", "Cascadia Mono",
            "Consolas", "Vazirmatn", "Amiri",
        ])
        self.font.setStyleHint(QFont.Monospace)
        self.font.setPointSize(self.font_size)
        self.font.setHintingPreference(QFont.PreferFullHinting)
        fm = QFontMetrics(self.font)
        self.cw = max(1, fm.horizontalAdvance("M"))
        self.line_pad = 4                        # vertical padding for readability
        self.ch = max(1, fm.height() + self.line_pad)
        self._text_dy = self.line_pad // 2       # vertically center the text
        if hasattr(self, "_layout_cache"):
            self._layout_cache.clear()
            self._run_cache.clear()

    def change_font(self, delta):
        self.font_size = max(8, min(36, self.font_size + delta))
        self._init_font()
        self._recompute_size()
        self.update()

    def reset_font(self):
        self.font_size = SETTINGS.get("font_size", 13)
        self._init_font()
        self._recompute_size()
        self.update()

    def _toggle_blink(self):
        if self.hasFocus():
            self._blink = not self._blink
            self.update()

    # ---------- backend signals ----------
    def _on_data(self):
        self.scroll_offset = 0  # jump to the bottom when new output arrives
        # throttle: one paint every ~16ms no matter how fast bursts arrive (prevents slowdown)
        if not self._repaint_timer.isActive():
            self._repaint_timer.start(16)

    def _on_exit(self):
        self._exited = True
        self.update()

    def _on_command_ended(self, code):
        """Notify on the desktop when a long command finishes while EasyTer is
        not the active window (needs OSC 133 shell integration)."""
        started, self._cmd_started = self._cmd_started, None
        if started is None or not SETTINGS.get("notify_on_finish", True):
            return
        dur = time.time() - started
        win = self.window()
        if dur < 6 or (win is not None and win.isActiveWindow()):
            return
        if win is not None and hasattr(win, "notify"):
            ok = (code == 0 or code is None)
            status = i18n.t("notify.ok") if ok else i18n.t("notify.fail", code=code)
            win.notify(i18n.t("notify.title"),
                       i18n.t("notify.body", sec=int(dur), status=status))

    # ---------- sizing ----------
    def resizeEvent(self, event):
        # don't resize on every drag event - debounce until the drag stops
        self._resize_timer.start(140)
        if self.search_bar and self.search_bar.isVisible():
            self._place_search_bar()
        super().resizeEvent(event)

    def _recompute_size(self):
        cols = max(20, self.width() // self.cw)
        rows = max(5, self.height() // self.ch)
        if cols != self.cols or rows != self.rows:
            self.cols, self.rows = cols, rows
            self._layout_cache.clear()   # line width changed
            self._run_cache.clear()
            self.backend.resize(cols, rows)
            self._notify_status()

    # ---------- painting ----------
    def paintEvent(self, event):
        # A QPainter must always be ended, even if drawing raises — otherwise Qt
        # floods "QBackingStore::endPaint() called with active painter" every
        # frame and the widget freezes. Wrap the body so end() is guaranteed and
        # any paint exception is logged (PySide6 can otherwise swallow it).
        p = QPainter(self)
        try:
            self._paint(p)
        except Exception:
            import traceback
            try:
                with open(os.path.join(SCRIPT_DIR, "_easyter_paint_error.log"),
                          "a", encoding="utf-8") as _f:
                    _f.write(traceback.format_exc() + "\n")
            except Exception:
                pass
        finally:
            p.end()

    def _paint(self, p):
        p.fillRect(self.rect(), BASE_BG)
        # optional background image: drawn over the base fill at the chosen
        # opacity, so text (and ANSI cell backgrounds) stay on top and readable
        bgpm = _bg_image_scaled(self.width(), self.height())
        if bgpm is not None:
            p.setOpacity(max(0.0, min(1.0, float(SETTINGS.get("bg_image_opacity", 0.35)))))
            x = (self.width() - bgpm.width()) // 2
            y = (self.height() - bgpm.height()) // 2
            p.drawPixmap(x, y, bgpm)
            p.setOpacity(1.0)
        p.setFont(self.font)
        p.setPen(BASE_FG)  # default color for Claude-mode lines (no formats)
        self._row_layouts = {}

        with self.backend.lock:
            screen = self.backend.screen
            history = list(screen.history.top)
            live = [screen.buffer[y] for y in range(screen.lines)]
            all_lines = history + live
            total = len(all_lines)
            start = max(0, total - self.rows - self.scroll_offset)
            self._paint_start = start
            visible = all_lines[start:start + self.rows]
            cur_x, cur_y = screen.cursor.x, screen.cursor.y
            cur_hidden = screen.cursor.hidden
            ncols = screen.columns

            for yi, row in enumerate(visible):
                if self.claude_mode:
                    self._draw_row_grid(p, yi, row, ncols)   # grid engine
                else:
                    self._draw_row(p, yi, row, ncols)         # PowerShell path

            # cursor (only at the bottom, where visible = the live screen)
            if self.scroll_offset == 0 and not cur_hidden:
                cy = cur_y * self.ch
                cx = cur_x * self.cw
                if not self.claude_mode:   # the grid engine is already cell-aligned
                    lay = self._row_layouts.get(cur_y)
                    if lay is not None:
                        try:
                            rx = lay[1].cursorToX(min(cur_x, ncols))
                            cx = rx[0] if isinstance(rx, (tuple, list)) else rx
                        except Exception:
                            pass
                crect = QRect(int(cx), cy, self.cw, self.ch)
                if self.hasFocus():
                    if self._blink:                       # solid cursor when focused
                        cc = QColor(BASE_FG)
                        cc.setAlpha(200)
                        style = SETTINGS.get("cursor_style", "block")
                        if style == "bar":
                            p.fillRect(QRect(int(cx), cy, 2, self.ch), cc)
                        elif style == "underline":
                            p.fillRect(QRect(int(cx), cy + self.ch - 2, self.cw, 2), cc)
                        else:
                            p.fillRect(crect, cc)
                else:                                     # outline when not focused
                    pen = QPen(BASE_FG)
                    pen.setWidth(1)
                    p.setPen(pen)
                    p.setBrush(Qt.NoBrush)
                    p.drawRect(crect.adjusted(0, 0, -1, -1))

            # command-block markers: a thin bar in the left gutter at each prompt
            # line (green = success, red = failure, grey = unknown/running)
            if self.backend.command_marks:
                ec_by_line = {pl: ec for pl, ec in self.backend.command_marks}
                for yi in range(len(visible)):
                    ec = ec_by_line.get(start + yi, "none")
                    if ec == "none":
                        continue
                    bar = (QColor("#2ea043") if ec == 0
                           else QColor("#cf222e") if ec is not None
                           else QColor("#6e7681"))
                    p.fillRect(QRect(0, yi * self.ch, 3, self.ch), bar)

            # selection highlight (over the text, translucent)
            sel = self._norm_sel()
            if sel:
                (lo_l, lo_c), (hi_l, hi_c) = sel
                sel_color = QColor(80, 140, 255, 90)
                for L in range(lo_l, hi_l + 1):
                    yi = L - start
                    if yi < 0 or yi >= self.rows:
                        continue
                    c0 = lo_c if L == lo_l else 0
                    c1 = hi_c if L == hi_l else ncols
                    if c1 > c0:
                        p.fillRect(QRect(c0 * self.cw, yi * self.ch,
                                         (c1 - c0) * self.cw, self.ch), sel_color)

            # search-result highlight (the whole matching line; the current one stronger)
            if self.search_matches:
                cur_L = (self.search_matches[self.search_idx]
                         if 0 <= self.search_idx < len(self.search_matches) else -1)
                for L in self.search_matches:
                    yi = L - start
                    if 0 <= yi < self.rows:
                        c = (QColor(240, 180, 40, 140) if L == cur_L
                             else QColor(240, 200, 80, 60))
                        p.fillRect(QRect(0, yi * self.ch, self.width(), self.ch), c)

        # visible Claude-mode badge (top right)
        if self.claude_mode:
            label = i18n.t("badge.claude_auto") if self.auto_follow else i18n.t("badge.claude_manual")
            fm = QFontMetrics(self.font)
            tw = fm.horizontalAdvance(label) + 10
            bh = self.ch + 6
            bx = self.width() - tw - 6
            p.fillRect(QRect(bx, 4, tw, bh), QColor(46, 160, 67))
            p.setPen(QColor("#ffffff"))
            p.drawText(QRect(bx, 4, tw, bh), Qt.AlignCenter, label)

        # border marking the focused pane (only when split)
        if isinstance(self.parentWidget(), QSplitter):
            pen = QPen(QColor("#2ea043") if self.hasFocus() else QColor("#30363d"))
            pen.setWidth(2)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            p.drawRect(1, 1, self.width() - 2, self.height() - 2)

    def _draw_row(self, p, yi, row, ncols):
        """Draws the line as a unit via QTextLayout (shaping + correct BiDi), with caching:
        a line whose content/style has not changed is not rebuilt (performance)."""
        y = yi * self.ch
        # the line signature (content + style) is cheap with no Qt objects - the cache key
        chars = []
        runs = []
        cur = None
        rstart = 0          # in text positions (not columns) because continuation cells are skipped
        col = 0
        while col < ncols:
            ch = row[col]
            d = ch.data if ch.data else " "
            st = (ch.fg, ch.bg, ch.bold, ch.reverse)
            if st != cur:
                if cur is not None:
                    runs.append((rstart, len(chars) - rstart, cur))
                cur = st
                rstart = len(chars)
            chars.append(d)
            # wide cell (emoji/CJK): skip the empty continuation cell after it
            # so the char is drawn at its natural width (two cells) and columns don't shift.
            if _char_width(d) == 2 and col + 1 < ncols and not row[col + 1].data:
                col += 2
            else:
                col += 1
        if cur is not None:
            runs.append((rstart, len(chars) - rstart, cur))
        text = "".join(chars)
        if not text.strip():
            self._row_layouts[yi] = None
            return

        # Claude mode: convert the reversed visual line to logical (includes English lines
        # with Arabic islands) so Qt re-orders it correctly
        rtl_fixed = False
        if self.claude_mode:
            fixed = restore_bidi_line(text)
            if fixed is not None:
                text = fixed
                rtl_fixed = True

        key = (text, "RTL") if rtl_fixed else (text, tuple(runs))
        cached = self._layout_cache.get(key)
        if cached is None:
            cached = self._build_layout(text, () if rtl_fixed else runs)
            if len(self._layout_cache) > 800:
                self._layout_cache.clear()
            self._layout_cache[key] = cached
        cached[0].draw(p, QPointF(0, y + self._text_dy))
        self._row_layouts[yi] = cached

    def _build_layout(self, text, runs):
        """Builds a QTextLayout with color formats (once per unique content)."""
        layout = QTextLayout(text, self.font)
        opt = QTextOption()
        opt.setWrapMode(QTextOption.NoWrap)
        layout.setTextOption(opt)
        formats = []
        for start, length, style in runs:
            fg = resolve_color(style[0], False)
            bg = resolve_color(style[1], True)
            if style[3]:
                fg, bg = bg, fg
            fmt = QTextCharFormat()
            fmt.setForeground(fg)
            if bg.rgb() != BASE_BG.rgb():
                fmt.setBackground(bg)
            if style[2]:
                fmt.setFontWeight(QFont.Bold)
            fr = QTextLayout.FormatRange()
            fr.start = start
            fr.length = length
            fr.format = fmt
            formats.append(fr)
        if formats:
            layout.setFormats(formats)
        layout.beginLayout()
        line = layout.createLine()
        line.setLineWidth(self.cols * self.cw)
        line.setPosition(QPointF(0, 0))
        layout.endLayout()
        return (layout, line)

    # ===== grid engine (Claude mode) =====
    def _draw_row_grid(self, p, yi, row, ncols):
        """Draws the line run by run, pinned to the cell grid: each item stays in
        its visual cell (as Claude placed it) so alignment does not shift; Arabic runs are reversed
        to logical and shaped within their cells so letters join. Combines both benefits."""
        y = yi * self.ch
        # collect cells in visual order with their columns (skipping wide continuation cells)
        cells = []
        c = 0
        while c < ncols:
            ch = row[c]
            d = ch.data if ch.data else " "
            wide = (_char_width(d) == 2 and c + 1 < ncols and not row[c + 1].data)
            cells.append((c, d, (ch.fg, ch.bg, ch.bold, ch.reverse), 2 if wide else 1))
            c += 2 if wide else 1
        if not any(d.strip() for (_, d, _, _) in cells):
            return
        # group consecutive cells into runs by (is-Arabic?, style)
        n = len(cells)
        i = 0
        while i < n:
            st0 = cells[i][2]
            is_ar = _is_arabic_letter(cells[i][1])
            chars = []
            j = i
            while j < n and _is_arabic_letter(cells[j][1]) == is_ar and cells[j][2] == st0:
                chars.append(cells[j][1])
                j += 1
            col_start = cells[i][0]
            col_end = cells[j - 1][0] + cells[j - 1][3]
            text = "".join(chars)
            if is_ar:
                text = text[::-1]   # Claude visual -> logical for shaping
            self._draw_run(p, col_start * self.cw, y,
                           (col_end - col_start) * self.cw, text, st0, is_ar)
            i = j

    def _draw_run(self, p, x0, y, boxw, text, style, is_ar):
        fg = resolve_color(style[0], False)
        bg = resolve_color(style[1], True)
        if style[3]:
            fg, bg = bg, fg
        if bg.rgb() != BASE_BG.rgb():
            p.fillRect(QRect(int(x0), y, int(boxw), self.ch), bg)
        if not text.strip():
            return
        key = (text, style, is_ar)
        cached = self._run_cache.get(key)
        if cached is None:
            layout = QTextLayout(text, self.font)
            opt = QTextOption()
            opt.setWrapMode(QTextOption.NoWrap)
            opt.setTextDirection(Qt.RightToLeft if is_ar else Qt.LeftToRight)
            layout.setTextOption(opt)
            fmt = QTextCharFormat()
            fmt.setForeground(fg)
            if style[2]:
                fmt.setFontWeight(QFont.Bold)
            fr = QTextLayout.FormatRange()
            fr.start = 0
            fr.length = len(text)
            fr.format = fmt
            layout.setFormats([fr])
            layout.beginLayout()
            line = layout.createLine()
            line.setLineWidth(100000)
            line.setPosition(QPointF(0, 0))
            layout.endLayout()
            if len(self._run_cache) > 2000:
                self._run_cache.clear()
            cached = (layout, line)
            self._run_cache[key] = cached
        layout, line = cached
        natw = line.naturalTextWidth()
        # Arabic (RTL) is right-aligned in its box; others left
        dx = (x0 + boxw - natw) if is_ar else x0
        p.setPen(fg)
        layout.draw(p, QPointF(dx, y + self._text_dy))

    # ---------- input ----------
    def keyPressEvent(self, event: QKeyEvent):
        if self._exited:
            return
        key = event.key()
        mod = event.modifiers()
        ctrl = bool(mod & Qt.ControlModifier)
        shift = bool(mod & Qt.ShiftModifier)
        alt = bool(mod & Qt.AltModifier)
        win = self.window()
        sess = self._session()

        # plugin keybindings (take priority)
        if run_plugin_keybind(self, ctrl, alt, shift, key):
            return
        # command palette: Ctrl+Shift+P
        if ctrl and shift and key == Qt.Key_P:
            if hasattr(win, "command_palette"):
                win.command_palette()
            return
        # all shortcuts: F1
        if key == Qt.Key_F1:
            if hasattr(win, "show_shortcuts"):
                win.show_shortcuts()
            return

        # ----- tabs -----
        if ctrl and key == Qt.Key_T:                  # new tab / reopen closed (with Shift)
            if shift:
                if hasattr(win, "reopen_tab"):
                    win.reopen_tab()
            elif hasattr(win, "new_tab"):
                win.new_tab()
            return
        if ctrl and key == Qt.Key_Tab:                # next tab
            if hasattr(win, "next_tab"):
                win.next_tab()
            return
        if ctrl and key == Qt.Key_Backtab:            # Ctrl+Shift+Tab: previous
            if hasattr(win, "prev_tab"):
                win.prev_tab()
            return

        # ----- split & navigation (within the session) -----
        if ctrl and shift and key == Qt.Key_E:        # two panes side by side
            if sess:
                sess.split_pane(self, Qt.Horizontal)
            return
        if ctrl and shift and key == Qt.Key_O:        # two panes top/bottom
            if sess:
                sess.split_pane(self, Qt.Vertical)
            return
        if ctrl and shift and key == Qt.Key_N:        # editor beside the terminal
            if sess:
                sess.split_pane(self, Qt.Horizontal, factory=EditorWidget)
            return
        if ctrl and shift and key == Qt.Key_W:        # close pane
            if sess:
                sess.close_pane(self)
            return
        if alt and key in (Qt.Key_Left, Qt.Key_Right, Qt.Key_Up, Qt.Key_Down):
            if sess:
                sess.focus_dir(self, key)
            return
        if ctrl and shift and key == Qt.Key_Z:        # maximize / restore this pane
            if sess:
                sess.toggle_zoom(self)
            return
        if ctrl and shift and key == Qt.Key_B:        # broadcast typing to all panes
            if hasattr(win, "toggle_broadcast"):
                win.toggle_broadcast()
            return
        if ctrl and shift and key == Qt.Key_Up:       # jump to previous command (OSC 133)
            self._jump_command(-1)
            return
        if ctrl and shift and key == Qt.Key_Down:     # jump to next command
            self._jump_command(+1)
            return

        # zoom in/out/reset font (for the focused pane)
        if ctrl and key in (Qt.Key_Plus, Qt.Key_Equal):
            self.change_font(+1)
            return
        if ctrl and key == Qt.Key_Minus:
            self.change_font(-1)
            return
        if ctrl and key == Qt.Key_0:            # reset to default size
            self.reset_font()
            return

        # settings: Ctrl+,
        if ctrl and key == Qt.Key_Comma:
            if hasattr(win, "open_settings"):
                win.open_settings()
            return

        # search the output: Ctrl+F
        if ctrl and key == Qt.Key_F:
            self._open_search()
            return

        # F2: toggle Claude mode (BiDi reverse)
        if key == Qt.Key_F2:
            self.toggle_claude_mode()
            return

        # copy: Ctrl+Shift+C
        if ctrl and shift and key == Qt.Key_C:
            self._copy_selection()
            return

        # paste: Ctrl+Shift+V
        if ctrl and shift and key == Qt.Key_V:
            self._do_paste()
            return

        self.scroll_offset = 0

        seq = None
        if key in (Qt.Key_Return, Qt.Key_Enter):
            seq = "\r"
            if not self.backend.alt_screen:
                self._cmd_started = time.time()   # for long-command finish notifications
        elif key == Qt.Key_Backspace:
            seq = "\x7f"
        elif key == Qt.Key_Tab:
            seq = "\t"
        elif key == Qt.Key_Escape:
            seq = "\x1b"
        elif key == Qt.Key_Up:
            seq = "\x1b[A"
        elif key == Qt.Key_Down:
            seq = "\x1b[B"
        elif key == Qt.Key_Right:
            seq = "\x1b[C"
        elif key == Qt.Key_Left:
            seq = "\x1b[D"
        elif key == Qt.Key_Home:
            seq = "\x1b[H"
        elif key == Qt.Key_End:
            seq = "\x1b[F"
        elif key == Qt.Key_PageUp:
            seq = "\x1b[5~"
        elif key == Qt.Key_PageDown:
            seq = "\x1b[6~"
        elif key == Qt.Key_Delete:
            seq = "\x1b[3~"
        elif ctrl and Qt.Key_A <= key <= Qt.Key_Z:
            seq = chr(key - Qt.Key_A + 1)  # Ctrl+C=\x03 ...
        else:
            t = event.text()
            if t:
                seq = t

        if self.sel_anchor is not None:   # clear any stuck selection when typing
            self.sel_anchor = self.sel_point = None
        if seq:
            win = self.window()
            if getattr(win, "broadcast", False):   # type once -> all terminals
                for t in win.findChildren(TerminalWidget):
                    try:
                        t.backend.write(seq)
                    except Exception:
                        pass
            else:
                self.backend.write(seq)
            self._blink = True            # cursor solid right when typing

    # ---------- mouse text selection ----------
    def _pos_to_cell(self, pos):
        yi = max(0, min(self.rows - 1, int(pos.y() // self.ch)))
        col = None
        lay = getattr(self, "_row_layouts", {}).get(yi)
        if lay is not None:
            try:
                col = lay[1].xToCursor(float(pos.x()))  # exact logical column despite BiDi
            except Exception:
                col = None
        if col is None:
            col = round(pos.x() / self.cw)
        col = max(0, min(self.cols, col))
        abs_line = self._paint_start + yi
        return abs_line, col

    def _url_at(self, pos):
        """Return the http(s) URL under the mouse position, or None."""
        if not hasattr(self, "_row_layouts"):
            return None
        abs_line, col = self._pos_to_cell(pos)
        with self.backend.lock:
            screen = self.backend.screen
            all_lines = list(screen.history.top) + [screen.buffer[y] for y in range(screen.lines)]
            if abs_line < 0 or abs_line >= len(all_lines):
                return None
            row = all_lines[abs_line]
            ncols = screen.columns
            text = "".join((row[c].data if row[c].data else " ") for c in range(ncols))
        for m in URL_RE.finditer(text):
            if m.start() <= col < m.end():
                return m.group(0)
        return None

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            if event.modifiers() & Qt.ControlModifier:   # Ctrl+click opens a link
                url = self._url_at(event.position())
                if url:
                    try:
                        webbrowser.open(url)
                    except Exception:
                        pass
                    return
            self.setFocus()
            self.sel_anchor = self._pos_to_cell(event.position())
            self.sel_point = self.sel_anchor
            self.update()

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton and self.sel_anchor is not None:
            self.sel_point = self._pos_to_cell(event.position())
            self.update()
        elif (event.modifiers() & Qt.ControlModifier) and self._url_at(event.position()):
            self.setCursor(Qt.PointingHandCursor)   # hint a clickable link
        else:
            self.unsetCursor()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self._norm_sel():
            self._copy_selection()  # auto-copy on mouse release

    def _norm_sel(self):
        """Returns ((lo_line,lo_col),(hi_line,hi_col)) ordered, or None if no selection."""
        if self.sel_anchor is None or self.sel_point is None:
            return None
        a, b = self.sel_anchor, self.sel_point
        if a == b:
            return None
        return (a, b) if a <= b else (b, a)

    def _selection_text(self):
        sel = self._norm_sel()
        if not sel:
            return ""
        (lo_l, lo_c), (hi_l, hi_c) = sel
        with self.backend.lock:
            screen = self.backend.screen
            history = list(screen.history.top)
            live = [screen.buffer[y] for y in range(screen.lines)]
            all_lines = history + live
            ncols = screen.columns
            out = []
            for L in range(lo_l, hi_l + 1):
                if L < 0 or L >= len(all_lines):
                    continue
                row = all_lines[L]
                if self.claude_mode:
                    # in Claude mode we copy the whole line logically (reversal can't be split by columns)
                    full = self._full_row_text(row, ncols)
                    fixed = restore_bidi_line(full)
                    out.append((fixed if fixed is not None else full).rstrip())
                    continue
                c0 = lo_c if L == lo_l else 0
                c1 = hi_c if L == hi_l else ncols
                chars = []
                for col in range(c0, min(c1, ncols)):
                    ch = row[col]
                    chars.append(ch.data if ch.data else " ")
                out.append("".join(chars).rstrip())
        return "\n".join(out)

    def _full_row_text(self, row, ncols):
        """The whole line's text, skipping continuation cells of wide chars (emoji)."""
        chars = []
        col = 0
        while col < ncols:
            d = row[col].data if row[col].data else " "
            chars.append(d)
            if _char_width(d) == 2 and col + 1 < ncols and not row[col + 1].data:
                col += 2
            else:
                col += 1
        return "".join(chars)

    def _copy_selection(self):
        txt = self._selection_text()
        if txt:
            QApplication.clipboard().setText(txt)

    # ---------- search the output (Ctrl+F) ----------
    def _line_logical_text(self, row, ncols):
        full = self._full_row_text(row, ncols)
        if self.claude_mode:
            fixed = restore_bidi_line(full)
            if fixed is not None:
                full = fixed
        return full

    def _open_search(self):
        if self.search_bar is None:
            self.search_bar = SearchBar(self)
        self._place_search_bar()
        self.search_bar.show()
        self.search_bar.edit.setText(self.search_term)
        self.search_bar.edit.setFocus()
        self.search_bar.edit.selectAll()

    def _place_search_bar(self):
        if self.search_bar:
            w = min(360, max(220, self.width() - 20))
            self.search_bar.setFixedWidth(w)
            self.search_bar.move(self.width() - w - 10, 8)

    def _do_search(self, text):
        self.search_term = text
        self.search_matches = []
        if text:
            tl = text.lower()
            with self.backend.lock:
                s = self.backend.screen
                all_lines = list(s.history.top) + [s.buffer[y] for y in range(s.lines)]
                ncols = s.columns
            for L, row in enumerate(all_lines):
                if tl in self._line_logical_text(row, ncols).lower():
                    self.search_matches.append(L)
        # start from the last match (closest to the bottom)
        self.search_idx = len(self.search_matches) - 1
        if self.search_matches:
            self._scroll_to_match()
        self._update_search_count()
        self.update()

    def _search_next(self):
        if not self.search_matches:
            return
        self.search_idx = (self.search_idx + 1) % len(self.search_matches)
        self._scroll_to_match()
        self._update_search_count()
        self.update()

    def _search_prev(self):
        if not self.search_matches:
            return
        self.search_idx = (self.search_idx - 1) % len(self.search_matches)
        self._scroll_to_match()
        self._update_search_count()
        self.update()

    def _scroll_to_match(self):
        if not self.search_matches:
            return
        L = self.search_matches[self.search_idx]
        with self.backend.lock:
            total = len(self.backend.screen.history.top) + self.backend.screen.lines
            maxoff = len(self.backend.screen.history.top)
        off = total - self.rows // 2 - L
        self.scroll_offset = max(0, min(maxoff, off))

    def _jump_command(self, direction):
        """Scroll to the previous (-1) or next (+1) command prompt (OSC 133 marks)."""
        marks = self.backend.command_marks
        if not marks:
            return
        with self.backend.lock:
            total = len(self.backend.screen.history.top) + self.backend.screen.lines
            maxoff = len(self.backend.screen.history.top)
        cur_top = max(0, total - self.rows - self.scroll_offset)
        plines = sorted({pl for pl, _ in marks if 0 <= pl < total})
        target = None
        if direction < 0:
            for pl in plines:
                if pl < cur_top:
                    target = pl            # last prompt strictly above the view
        else:
            for pl in plines:
                if pl > cur_top:
                    target = pl            # first prompt below the view
                    break
        if target is None:
            return
        self.scroll_offset = max(0, min(maxoff, total - self.rows - max(0, target - 1)))
        self.update()

    def _update_search_count(self):
        if self.search_bar:
            n = len(self.search_matches)
            cur = (self.search_idx + 1) if n else 0
            self.search_bar.count.setText(f"{cur}/{n}" if n else i18n.t("search.no_results"))

    def _clear_search(self):
        self.search_term = ""
        self.search_matches = []
        self.search_idx = -1
        self.update()

    def _paste_clipboard(self):
        self._do_paste()

    def _do_paste(self):
        """Paste the clipboard, with optional protection (confirm multi-line/large
        pastes) and bracketed-paste wrapping so the shell won't auto-run lines."""
        txt = QApplication.clipboard().text()
        if not txt:
            return
        if SETTINGS.get("paste_protection", True) and ("\n" in txt.strip() or len(txt) > 2000):
            from PySide6.QtWidgets import QMessageBox
            lines = txt.count("\n") + (0 if txt.endswith("\n") else 1)
            box = QMessageBox(self)
            box.setWindowTitle(i18n.t("paste.title"))
            box.setText(i18n.t("paste.warn", lines=lines, chars=len(txt)))
            box.setStandardButtons(QMessageBox.Ok | QMessageBox.Cancel)
            box.setDefaultButton(QMessageBox.Cancel)
            if box.exec() != QMessageBox.Ok:
                return
        body = txt.replace("\r\n", "\r").replace("\n", "\r")
        if self.backend.bracketed_paste:
            self.backend.write("\x1b[200~" + body + "\x1b[201~")
        else:
            self.backend.write(body)

    def _select_all(self):
        with self.backend.lock:
            screen = self.backend.screen
            total = len(screen.history.top) + screen.lines
            ncols = screen.columns
        if total > 0:
            self.sel_anchor = (0, 0)
            self.sel_point = (total - 1, ncols)
            self.update()

    def _set_title(self):
        w = self.window()
        if w is None:
            return
        base = i18n.t("win.title")
        if self.claude_mode:
            tag = i18n.t("claude.tag_auto") if self.auto_follow else i18n.t("claude.tag_manual")
        else:
            tag = "" if self.auto_follow else i18n.t("win.title_manual")
        w.setWindowTitle(base + tag)

    def _on_alt_screen(self, active):
        """Enable/disable Claude mode automatically as a full-screen TUI program enters/leaves."""
        if self.auto_follow:
            self.claude_mode = active
            self._set_title()
            self.update()
            self._notify_status()
        if active:
            PLUGINS.emit("claude_detected", self)

    def toggle_claude_mode(self):
        # F2: if auto, switch to manual and flip the state; otherwise go back to auto
        if self.auto_follow:
            self.auto_follow = False
            self.claude_mode = not self.claude_mode
        else:
            self.auto_follow = True
            self.claude_mode = self.backend.alt_screen
        self._set_title()
        self.update()
        self._notify_status()
        return self.claude_mode

    def contextMenuEvent(self, event):
        win = self.window()
        sess = self._session()
        menu = QMenu(self)
        act_copy = menu.addAction(i18n.t("menu.copy"))
        act_copy.setEnabled(self._norm_sel() is not None)
        act_paste = menu.addAction(i18n.t("menu.paste"))
        act_all = menu.addAction(i18n.t("menu.select_all"))
        menu.addSeparator()
        act_claude = menu.addAction(
            i18n.t("claude.toggle_off") if self.claude_mode else i18n.t("claude.toggle_on"))
        menu.addSeparator()
        # switch shell (restarts this pane)
        shell_menu = menu.addMenu(i18n.t("menu.shell"))
        shell_acts = {}
        for name, cmd in available_shells():
            a = shell_menu.addAction(("● " if cmd == self.command else "    ") + name)
            shell_acts[a] = cmd
        menu.addSeparator()
        # split
        act_split_h = menu.addAction(i18n.t("menu.split_h"))
        act_split_v = menu.addAction(i18n.t("menu.split_v"))
        act_editor = menu.addAction(i18n.t("menu.editor"))
        act_close = menu.addAction(i18n.t("menu.close_pane"))
        menu.addSeparator()
        act_settings = menu.addAction(i18n.t("menu.settings"))

        chosen = menu.exec(event.globalPos())
        if chosen is None:
            return
        if chosen == act_copy:
            self._copy_selection()
        elif chosen == act_paste:
            self._paste_clipboard()
        elif chosen == act_all:
            self._select_all()
        elif chosen == act_claude:
            self.toggle_claude_mode()
        elif chosen in shell_acts:
            self.restart_with(shell_acts[chosen])
        elif chosen == act_split_h and sess:
            sess.split_pane(self, Qt.Horizontal)
        elif chosen == act_split_v and sess:
            sess.split_pane(self, Qt.Vertical)
        elif chosen == act_editor and sess:
            sess.split_pane(self, Qt.Horizontal, factory=EditorWidget)
        elif chosen == act_close and sess:
            sess.close_pane(self)
        elif chosen == act_settings and hasattr(win, "open_settings"):
            win.open_settings()

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        if delta == 0:
            return
        # in the alternate screen (Claude/TUI): pass the wheel to the program so it scrolls itself
        if self.backend.alt_screen:
            btn = 64 if delta > 0 else 65   # 64=up, 65=down (SGR mouse)
            pos = event.position()
            col = max(1, int(pos.x() // self.cw) + 1)
            rowy = max(1, int(pos.y() // self.ch) + 1)
            seq = f"\x1b[<{btn};{col};{rowy}M"
            for _ in range(3):
                self.backend.write(seq)
            return
        # normal (PowerShell): scroll within pyte's history
        with self.backend.lock:
            max_off = len(self.backend.screen.history.top)
        steps = int(delta / 120) * 3
        self.scroll_offset = max(0, min(max_off, self.scroll_offset + steps))
        self.update()

    def focusInEvent(self, event):
        self._blink = True
        self.update()
        w = self.window()
        if hasattr(w, "update_status"):
            w.update_status(self)
        PLUGINS.emit("pane_focused", self)

    def focusOutEvent(self, event):
        self.update()

    def _notify_status(self):
        if self.hasFocus():
            w = self.window()
            if hasattr(w, "update_status"):
                w.update_status(self)

    def closeEvent(self, event):
        self.backend.close()
        super().closeEvent(event)


class SettingsDialog(QDialog):
    """Customization panel: font and size, background and text color, and ready themes."""

    def __init__(self, win):
        super().__init__(win)
        self.win = win
        self.bg = SETTINGS["bg"]
        self.fg = SETTINGS["fg"]
        self.palette = dict(PALETTE)               # freely editable ANSI palette
        self.opacity = SETTINGS.get("opacity", 1.0)
        self._orig_opacity = self.opacity
        self._orig_bg = SETTINGS["bg"]
        self._orig_fg = SETTINGS["fg"]
        self._orig_palette = SETTINGS.get("palette")
        self.bg_image = SETTINGS.get("bg_image", "")
        self.bg_image_opacity = SETTINGS.get("bg_image_opacity", 0.35)
        self.start_dir = SETTINGS.get("start_dir", "")
        self._ansi_btns = {}
        self.setWindowTitle(i18n.t("settings.title"))
        self.setMinimumWidth(500)
        self.setStyleSheet(
            "QDialog{background:#161b22;color:#e6edf3;}"
            "QLabel{color:#e6edf3;} QPushButton{background:#21262d;color:#e6edf3;"
            "border:1px solid #30363d;border-radius:6px;padding:6px 10px;}"
            "QPushButton:hover{background:#30363d;}"
            "QSpinBox,QFontComboBox{background:#0d1117;color:#e6edf3;"
            "border:1px solid #30363d;border-radius:4px;padding:3px;}"
        )
        # scrollable form so a tall settings list never clips the buttons
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea{border:0;background:#161b22;}")
        outer.addWidget(scroll, 1)
        content = QWidget()
        content.setStyleSheet("background:#161b22;")
        scroll.setWidget(content)
        self.setMaximumHeight(680)
        self.resize(560, 620)
        g = QGridLayout(content)
        g.setContentsMargins(16, 16, 16, 16)
        g.setVerticalSpacing(12)

        g.addWidget(QLabel(i18n.t("settings.font")), 0, 0)
        self.font_combo = QFontComboBox()
        self.font_combo.setCurrentText(SETTINGS["font_family"])
        g.addWidget(self.font_combo, 0, 1)

        g.addWidget(QLabel(i18n.t("settings.font_size")), 1, 0)
        self.size_spin = QSpinBox()
        self.size_spin.setRange(8, 40)
        self.size_spin.setValue(SETTINGS["font_size"])
        g.addWidget(self.size_spin, 1, 1)

        g.addWidget(QLabel(i18n.t("settings.bg")), 2, 0)
        self.bg_btn = QPushButton()
        self.bg_btn.clicked.connect(self._pick_bg)
        g.addWidget(self.bg_btn, 2, 1)

        g.addWidget(QLabel(i18n.t("settings.fg")), 3, 0)
        self.fg_btn = QPushButton()
        self.fg_btn.clicked.connect(self._pick_fg)
        g.addWidget(self.fg_btn, 3, 1)

        # opacity (live preview while dragging)
        g.addWidget(QLabel(i18n.t("settings.opacity")), 4, 0)
        op_row = QHBoxLayout()
        self.op_slider = QSlider(Qt.Horizontal)
        self.op_slider.setRange(30, 100)
        self.op_slider.setValue(int(self.opacity * 100))
        self.op_slider.valueChanged.connect(self._on_opacity)
        self.op_label = QLabel(f"{int(self.opacity * 100)}%")
        op_row.addWidget(self.op_slider, 1)
        op_row.addWidget(self.op_label)
        opw = QWidget()
        opw.setLayout(op_row)
        g.addWidget(opw, 4, 1)

        # ANSI colors (free editing)
        g.addWidget(QLabel(i18n.t("settings.ansi")), 5, 0)
        ansi_row = QHBoxLayout()
        ansi_row.setSpacing(4)
        for key in ("red", "green", "yellow", "blue", "magenta", "cyan", "white"):
            b = QPushButton()
            b.setFixedSize(26, 26)
            b.setToolTip(key)
            b.clicked.connect(lambda _=False, k=key: self._pick_ansi(k))
            self._ansi_btns[key] = b
            ansi_row.addWidget(b)
        ansi_row.addStretch(1)
        aw = QWidget()
        aw.setLayout(ansi_row)
        g.addWidget(aw, 5, 1)

        g.addWidget(QLabel(i18n.t("settings.themes", n=len(THEMES))), 6, 0)
        self.theme_combo = QComboBox()
        self.theme_combo.addItem(i18n.t("theme.choose"))
        self.theme_combo.addItems(list(THEMES.keys()))
        self.theme_combo.setMaxVisibleItems(20)
        self.theme_combo.currentTextChanged.connect(self._on_theme_combo)
        g.addWidget(self.theme_combo, 6, 1)

        # background image (user-chosen; applied on save)
        g.addWidget(QLabel(i18n.t("settings.bg_image")), 7, 0)
        img_row = QHBoxLayout()
        self.img_label = QLabel(os.path.basename(self.bg_image) if self.bg_image else "—")
        choose = QPushButton(i18n.t("settings.bg_image_choose"))
        choose.clicked.connect(self._pick_bg_image)
        clear = QPushButton(i18n.t("settings.bg_image_clear"))
        clear.clicked.connect(self._clear_bg_image)
        img_row.addWidget(self.img_label, 1)
        img_row.addWidget(choose)
        img_row.addWidget(clear)
        iw = QWidget()
        iw.setLayout(img_row)
        g.addWidget(iw, 7, 1)

        g.addWidget(QLabel(i18n.t("settings.bg_image_opacity")), 8, 0)
        imgop_row = QHBoxLayout()
        self.img_op_slider = QSlider(Qt.Horizontal)
        self.img_op_slider.setRange(0, 100)
        self.img_op_slider.setValue(int(self.bg_image_opacity * 100))
        self.img_op_slider.valueChanged.connect(self._on_img_opacity)
        self.img_op_label = QLabel(f"{int(self.bg_image_opacity * 100)}%")
        imgop_row.addWidget(self.img_op_slider, 1)
        imgop_row.addWidget(self.img_op_label)
        iow = QWidget()
        iow.setLayout(imgop_row)
        g.addWidget(iow, 8, 1)

        # start folder for new shells (default = home, never system32)
        g.addWidget(QLabel(i18n.t("settings.start_dir")), 9, 0)
        sd_row = QHBoxLayout()
        self.sd_label = QLabel(self.start_dir or "~")
        sd_choose = QPushButton(i18n.t("settings.bg_image_choose"))
        sd_choose.clicked.connect(self._pick_start_dir)
        sd_home = QPushButton(i18n.t("settings.start_dir_home"))
        sd_home.clicked.connect(self._reset_start_dir)
        sd_row.addWidget(self.sd_label, 1)
        sd_row.addWidget(sd_choose)
        sd_row.addWidget(sd_home)
        sdw = QWidget()
        sdw.setLayout(sd_row)
        g.addWidget(sdw, 9, 1)

        # cursor shape
        g.addWidget(QLabel(i18n.t("settings.cursor")), 10, 0)
        self.cursor_combo = QComboBox()
        self.cursor_combo.addItem(i18n.t("cursor.block"), "block")
        self.cursor_combo.addItem(i18n.t("cursor.bar"), "bar")
        self.cursor_combo.addItem(i18n.t("cursor.underline"), "underline")
        ci = self.cursor_combo.findData(SETTINGS.get("cursor_style", "block"))
        self.cursor_combo.setCurrentIndex(ci if ci >= 0 else 0)
        g.addWidget(self.cursor_combo, 10, 1)

        # language (applies immediately)
        g.addWidget(QLabel(i18n.t("settings.language")), 11, 0)
        lang_row = QHBoxLayout()
        self.lang_combo = QComboBox()
        self.lang_combo.addItem("English", "en")
        self.lang_combo.addItem("العربية", "ar")
        li = self.lang_combo.findData(SETTINGS.get("language", "en"))
        self.lang_combo.setCurrentIndex(li if li >= 0 else 0)
        lang_row.addWidget(self.lang_combo, 1)
        lang_row.addWidget(QLabel(i18n.t("settings.language_note")))
        lw = QWidget()
        lw.setLayout(lang_row)
        g.addWidget(lw, 11, 1)

        # fixed button bar below the scroll area (always visible)
        btns = QHBoxLayout()
        btns.setContentsMargins(16, 8, 16, 12)
        ok = QPushButton(i18n.t("settings.apply"))
        ok.clicked.connect(self._apply)
        cancel = QPushButton(i18n.t("settings.cancel"))
        cancel.clicked.connect(self.reject)
        btns.addStretch(1)
        btns.addWidget(cancel)
        btns.addWidget(ok)
        bw = QWidget()
        bw.setLayout(btns)
        outer.addWidget(bw)

        self._refresh_swatches()
        self._refresh_ansi()

    def _refresh_swatches(self):
        self.bg_btn.setText(self.bg)
        self.bg_btn.setStyleSheet(f"background:{self.bg};color:{self.fg};"
                                  "border:1px solid #30363d;border-radius:6px;padding:6px;")
        self.fg_btn.setText(self.fg)
        self.fg_btn.setStyleSheet(f"background:{self.bg};color:{self.fg};"
                                  "border:1px solid #30363d;border-radius:6px;padding:6px;")

    def _pick_bg(self):
        c = QColorDialog.getColor(QColor(self.bg), self, i18n.t("dialog.pick_bg"))
        if c.isValid():
            self.bg = c.name()
            self._refresh_swatches()

    def _pick_fg(self):
        c = QColorDialog.getColor(QColor(self.fg), self, i18n.t("dialog.pick_fg"))
        if c.isValid():
            self.fg = c.name()
            self._refresh_swatches()

    def _on_theme_combo(self, name):
        vals = THEMES.get(name)
        if not vals:
            return
        bg, fg = vals[0], vals[1]
        pal = vals[2] if len(vals) > 2 else None
        self.bg, self.fg = bg, fg
        self.palette = {**DEFAULT_PALETTE, **pal} if pal else dict(DEFAULT_PALETTE)
        self._refresh_swatches()
        self._refresh_ansi()
        # live theme preview
        SETTINGS["bg"], SETTINGS["fg"], SETTINGS["palette"] = self.bg, self.fg, self.palette
        apply_base_colors()
        self.win.apply_settings()

    def _on_opacity(self, v):
        self.opacity = v / 100.0
        self.op_label.setText(f"{v}%")
        self.win.setWindowOpacity(self.opacity)   # instant live preview

    def _pick_bg_image(self):
        path, _ = QFileDialog.getOpenFileName(
            self, i18n.t("dialog.pick_image"), "",
            "Images (*.png *.jpg *.jpeg *.bmp *.gif *.webp)")
        if path:
            self.bg_image = path
            self.img_label.setText(os.path.basename(path))

    def _clear_bg_image(self):
        self.bg_image = ""
        self.img_label.setText("—")

    def _on_img_opacity(self, v):
        self.bg_image_opacity = v / 100.0
        self.img_op_label.setText(f"{v}%")

    def _pick_start_dir(self):
        d = QFileDialog.getExistingDirectory(
            self, i18n.t("dialog.pick_folder"),
            self.start_dir or os.path.expanduser("~"))
        if d:
            self.start_dir = d
            self.sd_label.setText(d)

    def _reset_start_dir(self):
        self.start_dir = ""
        self.sd_label.setText("~")

    def _pick_ansi(self, key):
        c = QColorDialog.getColor(QColor(self.palette.get(key, "#ffffff")), self, i18n.t("dialog.pick_ansi", name=key))
        if c.isValid():
            self.palette[key] = c.name()
            self._refresh_ansi()

    def _refresh_ansi(self):
        for key, b in self._ansi_btns.items():
            b.setStyleSheet(f"background:{self.palette.get(key, '#ffffff')};"
                            "border:1px solid #30363d;border-radius:4px;")

    def reject(self):
        # revert all live previews (theme/colors/opacity)
        SETTINGS["bg"] = self._orig_bg
        SETTINGS["fg"] = self._orig_fg
        SETTINGS["palette"] = self._orig_palette
        SETTINGS["opacity"] = self._orig_opacity
        apply_base_colors()
        self.win.apply_settings()
        super().reject()

    def _apply(self):
        SETTINGS["font_family"] = self.font_combo.currentText()
        SETTINGS["font_size"] = self.size_spin.value()
        SETTINGS["bg"] = self.bg
        SETTINGS["fg"] = self.fg
        SETTINGS["palette"] = self.palette
        SETTINGS["opacity"] = self.opacity
        SETTINGS["language"] = self.lang_combo.currentData()
        SETTINGS["bg_image"] = self.bg_image
        SETTINGS["bg_image_opacity"] = self.bg_image_opacity
        SETTINGS["start_dir"] = self.start_dir
        SETTINGS["cursor_style"] = self.cursor_combo.currentData()
        save_settings()
        i18n.set_language(SETTINGS["language"])   # live: menus/dialogs/shortcuts switch on next open
        apply_base_colors()
        self.win.apply_settings()
        self.accept()


class SearchBar(QWidget):
    """A search bar floating at the pane's top-right: field + counter + prev/next/close."""

    def __init__(self, term):
        super().__init__(term)
        self.term = term
        self.setStyleSheet(
            "QWidget{background:#1c2128;border:1px solid #30363d;border-radius:8px;}"
            "QLineEdit{background:#0d1117;color:#e6edf3;border:1px solid #30363d;"
            "border-radius:5px;padding:4px;}"
            "QLabel{color:#9da7b3;border:0;background:transparent;}"
            "QPushButton{background:#21262d;color:#e6edf3;border:1px solid #30363d;"
            "border-radius:5px;padding:2px 8px;}"
            "QPushButton:hover{background:#30363d;}"
        )
        h = QHBoxLayout(self)
        h.setContentsMargins(6, 6, 6, 6)
        h.setSpacing(4)
        self.edit = QLineEdit()
        self.edit.setPlaceholderText(i18n.t("search.placeholder"))
        self.edit.textChanged.connect(self.term._do_search)
        self.edit.installEventFilter(self)
        self.count = QLabel("")
        prev = QPushButton("▲")
        prev.setToolTip(i18n.t("search.prev"))
        prev.clicked.connect(self.term._search_prev)
        nxt = QPushButton("▼")
        nxt.setToolTip(i18n.t("search.next"))
        nxt.clicked.connect(self.term._search_next)
        close = QPushButton("✕")
        close.clicked.connect(self.close_bar)
        h.addWidget(self.edit, 1)
        h.addWidget(self.count)
        h.addWidget(prev)
        h.addWidget(nxt)
        h.addWidget(close)

    def eventFilter(self, obj, ev):
        if obj is self.edit and ev.type() == ev.Type.KeyPress:
            k = ev.key()
            if k in (Qt.Key_Return, Qt.Key_Enter):
                if ev.modifiers() & Qt.ShiftModifier:
                    self.term._search_prev()
                else:
                    self.term._search_next()
                return True
            if k == Qt.Key_Escape:
                self.close_bar()
                return True
        return super().eventFilter(obj, ev)

    def close_bar(self):
        self.term._clear_search()
        self.hide()
        self.term.setFocus()


class CodeHighlighter(QSyntaxHighlighter):
    """Generic syntax highlighting (C/C++/Python/JS...): keywords, strings, comments, numbers."""

    KEYWORDS = (
        "int float double char void bool long short unsigned signed const static "
        "struct class public private protected return if else for while do switch "
        "case default break continue goto new delete namespace using template typename "
        "true false null nullptr sizeof typedef enum union virtual override final auto "
        "def import from as lambda pass elif try except finally with in is not and or "
        "function var let async await yield this self None True False raise while global"
    ).split()
    PREPROC = {"include", "define", "ifndef", "ifdef", "endif", "pragma", "if",
               "else", "elif", "undef", "error", "import", "line"}

    def __init__(self, doc):
        super().__init__(doc)

        def fmt(color, bold=False, italic=False):
            f = QTextCharFormat()
            f.setForeground(QColor(color))
            if bold:
                f.setFontWeight(QFont.Bold)
            if italic:
                f.setFontItalic(True)
            return f

        self.comment_fmt = fmt("#44b340", italic=True)
        self.preproc_fmt = fmt("#ff9d5c")
        self.rules = [
            (re.compile(r"\b(?:" + "|".join(self.KEYWORDS) + r")\b"), fmt("#66d9ef", bold=True)),
            (re.compile(r"\b\d+\.?\d*\b"), fmt("#ae81ff")),
            (re.compile(r'"[^"\\]*(?:\\.[^"\\]*)*"'), fmt("#e6db74")),
            (re.compile(r"'[^'\\]*(?:\\.[^'\\]*)*'"), fmt("#e6db74")),
            (re.compile(r"//[^\n]*"), self.comment_fmt),
        ]

    def highlightBlock(self, text):
        # Stay fast on large input: skip a very long single line, and turn
        # highlighting off entirely once the document gets big (regex per block
        # over a huge file is the usual cause of editor lag).
        if len(text) > 5000 or self.document().characterCount() > 600000:
            return
        for rx, f in self.rules:
            for m in rx.finditer(text):
                self.setFormat(m.start(), m.end() - m.start(), f)
        # a line starting with # : a preprocessor directive (orange) or a Python comment (green)
        stripped = text.lstrip()
        if stripped.startswith("#"):
            indent = len(text) - len(stripped)
            w = re.match(r"#\s*(\w+)", stripped)
            f = self.preproc_fmt if (w and w.group(1) in self.PREPROC) else self.comment_fmt
            self.setFormat(indent, len(stripped), f)
        # block comments /* */ (across lines)
        self.setCurrentBlockState(0)
        start = 0 if self.previousBlockState() == 1 else text.find("/*")
        while start >= 0:
            end = text.find("*/", start)
            if end == -1:
                self.setCurrentBlockState(1)
                length = len(text) - start
            else:
                length = end - start + 2
            self.setFormat(start, length, self.comment_fmt)
            start = text.find("/*", start + length)


class LineNumberArea(QWidget):
    """The line-number strip on the left of the editor."""

    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor

    def paintEvent(self, e):
        self.editor._paint_line_numbers(e)


class CodeEdit(QPlainTextEdit):
    """The inner text editor; forwards special shortcuts to EditorWidget."""

    def __init__(self, owner):
        super().__init__()
        self.owner = owner
        self.setLineWrapMode(QPlainTextEdit.NoWrap)   # no wrap = much faster on big files
        self.setCenterOnScroll(True)                  # cheaper scrolling for large docs
        self._lna = LineNumberArea(self)
        self.blockCountChanged.connect(self._update_lna_width)
        self.updateRequest.connect(self._update_lna)
        self._update_lna_width()

    def _lna_width(self):
        digits = max(2, len(str(max(1, self.blockCount()))))
        return 16 + self.fontMetrics().horizontalAdvance("9") * digits

    def _update_lna_width(self, *_):
        self.setViewportMargins(self._lna_width(), 0, 0, 0)

    def _update_lna(self, rect, dy):
        if dy:
            self._lna.scroll(0, dy)
        else:
            self._lna.update(0, rect.y(), self._lna.width(), rect.height())
        if rect.contains(self.viewport().rect()):
            self._update_lna_width()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        cr = self.contentsRect()
        self._lna.setGeometry(cr.left(), cr.top(), self._lna_width(), cr.height())

    def _paint_line_numbers(self, event):
        p = QPainter(self._lna)
        p.fillRect(event.rect(), QColor("#0a2a30"))
        p.setFont(self.font())
        p.setPen(QColor("#5f8787"))
        block = self.firstVisibleBlock()
        num = block.blockNumber()
        top = self.blockBoundingGeometry(block).translated(self.contentOffset()).top()
        bottom = top + self.blockBoundingRect(block).height()
        h = self.fontMetrics().height()
        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                p.drawText(0, int(top), self._lna.width() - 8, h,
                           Qt.AlignRight, str(num + 1))
            block = block.next()
            top = bottom
            bottom = top + self.blockBoundingRect(block).height()
            num += 1

    def keyPressEvent(self, e):
        if self.owner._handle_shortcut(e):
            return
        super().keyPressEvent(e)

    def focusInEvent(self, e):
        super().focusInEvent(e)
        self.owner._on_focus(True)

    def focusOutEvent(self, e):
        super().focusOutEvent(e)
        self.owner._on_focus(False)


class EditorWidget(QWidget):
    """A file editor embedded as a pane in the split tree (open/save, Arabic, same theme)."""

    def __init__(self, path=None, title=None):
        super().__init__()
        self.path = None
        self.custom_title = title       # manual title (double-click the header)
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        self.header = QLabel("")
        self.header.setToolTip(i18n.t("editor.rename_tip"))
        self.header.installEventFilter(self)
        close_btn = QPushButton("×")
        close_btn.setFixedSize(22, 20)
        close_btn.setToolTip(i18n.t("menu.close_pane").split("\t")[0])
        close_btn.setStyleSheet(
            "QPushButton{border:none;background:transparent;color:#9aa4b2;font-size:16px;}"
            "QPushButton:hover{color:#ff6b6b;}")
        close_btn.clicked.connect(self._close_self)
        hbar = QWidget()
        hb = QHBoxLayout(hbar)
        hb.setContentsMargins(0, 0, 4, 0)
        hb.setSpacing(0)
        hb.addWidget(self.header, 1)
        hb.addWidget(close_btn)
        self.edit = CodeEdit(self)
        self.highlighter = CodeHighlighter(self.edit.document())
        v.addWidget(hbar)
        v.addWidget(self.edit, 1)
        self.setFocusProxy(self.edit)
        self.edit.modificationChanged.connect(lambda *_: self._update_header())
        self.apply_theme()
        if path:
            self.open_path(path)
        else:
            self._update_header()

    def _close_self(self):
        w = self.parentWidget()
        while w is not None and not isinstance(w, SessionWidget):
            w = w.parentWidget()
        if isinstance(w, SessionWidget):
            w.close_pane(self)

    def eventFilter(self, obj, ev):
        if obj is self.header and ev.type() == ev.Type.MouseButtonDblClick:
            self._rename_header()
            return True
        return super().eventFilter(obj, ev)

    def _rename_header(self):
        start = self.custom_title or (os.path.basename(self.path) if self.path else "")
        edit = QLineEdit(start, self.header)
        edit.setGeometry(self.header.rect())
        edit.setStyleSheet("background:#0d1117;color:#e6edf3;border:1px solid #2ea043;"
                           "border-radius:4px;padding:2px;")
        edit.selectAll()
        edit.setFocus()
        done = {"v": False}

        def finish():
            if done["v"]:
                return
            done["v"] = True
            self.custom_title = edit.text().strip() or None
            edit.deleteLater()
            self._update_header()

        edit.returnPressed.connect(edit.clearFocus)
        edit.editingFinished.connect(finish)
        edit.show()

    def apply_theme(self):
        f = QFont()
        f.setFamilies([SETTINGS["font_family"], "JetBrains Mono", "Consolas",
                       "Vazirmatn", "Amiri"])
        f.setPointSize(SETTINGS["font_size"])
        self.edit.setFont(f)
        self.edit.setStyleSheet(
            f"QPlainTextEdit{{background:{SETTINGS['bg']};color:{SETTINGS['fg']};"
            "border:0;padding:6px;selection-background-color:#2a4a5a;}")
        self.edit._update_lna_width()
        self.edit._lna.update()
        self._on_focus(self.edit.hasFocus())

    def _on_focus(self, focused):
        c = "#2ea043" if focused else "#2a4a4a"
        self.header.setStyleSheet(
            f"background:#0a2a30;color:#cdd9d9;padding:3px 10px;border-bottom:2px solid {c};")
        if focused:
            w = self.window()
            if hasattr(w, "update_status"):
                w.update_status(self)

    def _update_header(self):
        if self.custom_title:
            name = self.custom_title
        elif self.path:
            name = os.path.basename(self.path)
        else:
            name = i18n.t("editor.untitled")
        dot = "● " if self.edit.document().isModified() else ""
        self.header.setText(f"  ✎ {dot}{name}")

    def open_dialog(self):
        path, _ = QFileDialog.getOpenFileName(self, i18n.t("dialog.open_file"))
        if path:
            self.open_path(path)

    def open_path(self, path):
        try:
            with open(path, encoding="utf-8", errors="replace") as fh:
                data = fh.read()
            # disable repaints during the bulk insert: much faster for big files
            self.edit.setUpdatesEnabled(False)
            try:
                self.edit.setPlainText(data)
            finally:
                self.edit.setUpdatesEnabled(True)
            self.path = path
            self.edit.document().setModified(False)
        except Exception as ex:
            self.edit.setPlainText(i18n.t("editor.open_failed", ex=ex))
        self._update_header()

    def save(self):
        if not self.path:
            return self.save_as()
        try:
            with open(self.path, "w", encoding="utf-8") as fh:
                fh.write(self.edit.toPlainText())
            self.edit.document().setModified(False)
            self._update_header()
        except Exception as ex:
            self.header.setText(i18n.t("editor.save_failed", ex=ex))

    def save_as(self):
        path, _ = QFileDialog.getSaveFileName(self, i18n.t("dialog.save_as"))
        if path:
            self.path = path
            self.save()

    def _session(self):
        w = self.parentWidget()
        while w is not None and not isinstance(w, SessionWidget):
            w = w.parentWidget()
        return w

    def _handle_shortcut(self, e):
        k = e.key()
        m = e.modifiers()
        ctrl = bool(m & Qt.ControlModifier)
        shift = bool(m & Qt.ShiftModifier)
        alt = bool(m & Qt.AltModifier)
        sess = self._session()
        win = self.window()
        if run_plugin_keybind(self, ctrl, alt, shift, k):
            return True
        if ctrl and shift and k == Qt.Key_P and hasattr(win, "command_palette"):
            win.command_palette()
            return True
        if k == Qt.Key_F1 and hasattr(win, "show_shortcuts"):
            win.show_shortcuts()
            return True
        if ctrl and shift and k == Qt.Key_S:
            self.save_as()
            return True
        if ctrl and k == Qt.Key_S:
            self.save()
            return True
        if ctrl and k == Qt.Key_O:
            self.open_dialog()
            return True
        if ctrl and shift and k == Qt.Key_W:
            if sess:
                sess.close_pane(self)
            return True
        if alt and k in (Qt.Key_Left, Qt.Key_Right, Qt.Key_Up, Qt.Key_Down):
            if sess:
                sess.focus_dir(self, k)
            return True
        if ctrl and k == Qt.Key_T:
            if shift:
                if hasattr(win, "reopen_tab"):
                    win.reopen_tab()
            elif hasattr(win, "new_tab"):
                win.new_tab()
            return True
        return False


def serialize_node(widget):
    """Converts the pane tree (QSplitter/TerminalWidget) into a savable structure."""
    if isinstance(widget, QSplitter):
        return {
            "type": "split",
            "orient": "h" if widget.orientation() == Qt.Horizontal else "v",
            "sizes": widget.sizes(),
            "children": [serialize_node(widget.widget(i)) for i in range(widget.count())],
        }
    if isinstance(widget, TerminalWidget):
        return {"type": "term", "command": widget.command}
    if isinstance(widget, EditorWidget):
        return {"type": "editor", "path": widget.path, "title": widget.custom_title}
    return None


def build_node(node):
    """Builds the pane tree from a saved structure."""
    if not node:
        return TerminalWidget()
    if node.get("type") == "term":
        return TerminalWidget(command=node.get("command"))
    if node.get("type") == "editor":
        return EditorWidget(path=node.get("path"), title=node.get("title"))
    orient = Qt.Horizontal if node.get("orient") == "h" else Qt.Vertical
    split = QSplitter(orient)
    split.setHandleWidth(6)
    split.setChildrenCollapsible(False)
    for ch in node.get("children", []):
        split.addWidget(build_node(ch))
    sizes = node.get("sizes")
    if sizes:
        split._saved_sizes = sizes
    return split


class SessionWidget(QWidget):
    """A session = one tab's content: a splittable tree of terminals (vertical/horizontal)."""

    def __init__(self, tree=None, start_cwd=None):
        super().__init__()
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(8, 8, 8, 8)
        self.lay.addWidget(build_node(tree) if tree else TerminalWidget(start_cwd=start_cwd))

    def root_widget(self):
        item = self.lay.itemAt(0)
        return item.widget() if item else None

    def _all_terms(self):
        return self.findChildren(TerminalWidget)

    def _all_panes(self):
        """All panes: terminals and editors."""
        return self.findChildren(TerminalWidget) + self.findChildren(EditorWidget)

    def toggle_zoom(self, pane):
        """Maximize this pane, or restore the split layout.

        Hiding siblings leaves empty slots in a QSplitter, so instead we collapse
        every sibling along the path from the pane to the root to size 0 (and
        restore the saved sizes on the second press)."""
        if getattr(self, "_zoom_state", None):
            for sp, sizes, collap in self._zoom_state:
                if sp is not None:
                    sp.setChildrenCollapsible(collap)
                    sp.setSizes(sizes)
            self._zoom_state = None
        else:
            state = []
            w = pane
            parent = w.parentWidget()
            while isinstance(parent, QSplitter):
                state.append((parent, parent.sizes(), parent.childrenCollapsible()))
                idx = parent.indexOf(w)
                parent.setChildrenCollapsible(True)
                full = max(parent.width(), parent.height())
                parent.setSizes([full if i == idx else 0 for i in range(parent.count())])
                w = parent
                parent = w.parentWidget()
            self._zoom_state = state or None
        pane.setFocus()

    def close_all(self):
        for t in self.findChildren(TerminalWidget):
            t.backend.close()

    def split_pane(self, pane, orientation, factory=None):
        cwd = pane.backend.cwd if isinstance(pane, TerminalWidget) else None
        new_w = factory() if factory else TerminalWidget(start_cwd=cwd)
        parent = pane.parentWidget()
        split = QSplitter(orientation)
        split.setHandleWidth(6)
        split.setChildrenCollapsible(False)
        if isinstance(parent, QSplitter):
            idx = parent.indexOf(pane)
            sizes = parent.sizes()
            split.addWidget(pane)
            split.addWidget(new_w)
            parent.insertWidget(idx, split)
            parent.setSizes(sizes)
        else:
            self.lay.removeWidget(pane)
            split.addWidget(pane)
            split.addWidget(new_w)
            self.lay.addWidget(split)
        half = max(split.width(), split.height()) // 2 or 100
        split.setSizes([half, half])
        new_w.setFocus()

    def close_pane(self, pane):
        if len(self._all_panes()) <= 1:
            # last pane in the session -> close the whole tab
            mw = self.window()
            if hasattr(mw, "close_tab_for"):
                mw.close_tab_for(self)
            return
        parent = pane.parentWidget()
        if hasattr(pane, "backend"):
            pane.backend.close()
        pane.setParent(None)
        pane.deleteLater()
        if isinstance(parent, QSplitter) and parent.count() == 1:
            child = parent.widget(0)
            grand = parent.parentWidget()
            if isinstance(grand, QSplitter):
                idx = grand.indexOf(parent)
                sizes = grand.sizes()
                grand.insertWidget(idx, child)
                parent.setParent(None)
                parent.deleteLater()
                grand.setSizes(sizes)
            else:
                self.lay.removeWidget(parent)
                self.lay.addWidget(child)
                parent.setParent(None)
                parent.deleteLater()
        rem = self._all_panes()
        if rem:
            rem[0].setFocus()

    def focus_dir(self, pane, key):
        panes = self._all_panes()
        if len(panes) < 2:
            return
        cr = pane.mapToGlobal(pane.rect().center())
        best, bestd = None, None
        for t in panes:
            if t is pane:
                continue
            tc = t.mapToGlobal(t.rect().center())
            dx, dy = tc.x() - cr.x(), tc.y() - cr.y()
            ok = ((key == Qt.Key_Left and dx < 0 and abs(dx) >= abs(dy)) or
                  (key == Qt.Key_Right and dx > 0 and abs(dx) >= abs(dy)) or
                  (key == Qt.Key_Up and dy < 0 and abs(dy) >= abs(dx)) or
                  (key == Qt.Key_Down and dy > 0 and abs(dy) >= abs(dx)))
            if ok:
                d = dx * dx + dy * dy
                if bestd is None or d < bestd:
                    bestd, best = d, t
        if best:
            best.setFocus()


SHORTCUTS = [
    ("sc.cat.tabs", [
        ("sck.tabs.new", "sc.tabs.new"),
        ("sck.tabs.cycle", "sc.tabs.cycle"),
        ("sck.tabs.rename", "sc.tabs.rename"),
        ("sck.tabs.close", "sc.tabs.close"),
        ("sck.tabs.reopen", "sc.tabs.reopen"),
    ]),
    ("sc.cat.split", [
        ("sck.split.h", "sc.split.h"),
        ("sck.split.v", "sc.split.v"),
        ("sck.split.editor", "sc.split.editor"),
        ("sck.split.close", "sc.split.close"),
        ("sck.split.nav", "sc.split.nav"),
        ("sck.split.resize", "sc.split.resize"),
        ("sck.split.zoom", "sc.split.zoom"),
        ("sck.split.broadcast", "sc.split.broadcast"),
    ]),
    ("sc.cat.clip", [
        ("sck.clip.copypaste", "sc.clip.copypaste"),
        ("sck.clip.select", "sc.clip.select"),
        ("sck.clip.rightclick", "sc.clip.rightclick"),
        ("sck.clip.search", "sc.clip.search"),
        ("sck.clip.wheel", "sc.clip.wheel"),
        ("sck.clip.link", "sc.clip.link"),
        ("sck.clip.cmdjump", "sc.clip.cmdjump"),
    ]),
    ("sc.cat.arabic", [
        ("sck.arabic.f2", "sc.arabic.f2"),
        ("sck.arabic.zoom", "sc.arabic.zoom"),
        ("sck.arabic.settings", "sc.arabic.settings"),
    ]),
    ("sc.cat.editor", [
        ("sck.editor.open", "sc.editor.open"),
        ("sck.editor.save", "sc.editor.save"),
        ("sck.editor.rename", "sc.editor.rename"),
    ]),
    ("sc.cat.plugins", [
        ("sck.plugins.palette", "sc.plugins.palette"),
        ("sck.plugins.help", "sc.plugins.help"),
        ("sck.plugins.init", "sc.plugins.init"),
        ("sck.app.quake", "sc.app.quake"),
    ]),
]


class HelpDialog(QDialog):
    """A list of all shortcuts (F1 or the ? button)."""

    def __init__(self, win):
        super().__init__(win)
        self.setWindowTitle(i18n.t("shortcuts.title"))
        self.setMinimumSize(560, 620)
        self.setStyleSheet("QDialog{background:#0d1117;}")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        view = QTextEdit()
        view.setReadOnly(True)
        view.setStyleSheet("QTextEdit{background:#0d1117;color:#e6edf3;border:0;padding:8px;}")
        h = ['<div style="font-family:Segoe UI;font-size:13px;">',
             f'<h2 style="color:#e6edf3;">{i18n.t("shortcuts.heading")}</h2>']
        for cat_key, items in SHORTCUTS:
            h.append(f'<h3 style="color:#7ee787;margin:14px 0 2px;">{i18n.t(cat_key)}</h3>'
                     '<table width="100%" cellpadding="3">')
            for keys_key, desc_key in items:
                h.append(f'<tr><td style="color:#f2cc60;white-space:nowrap;">'
                         f'<b>{i18n.t(keys_key)}</b></td>'
                         f'<td style="color:#c9d1d9;">{i18n.t(desc_key)}</td></tr>')
            h.append('</table>')
        if PLUGINS.keybinds:
            h.append(f'<h3 style="color:#7ee787;margin:14px 0 2px;">{i18n.t("shortcuts.plugin_heading")}</h3>'
                     '<table width="100%" cellpadding="3">')
            for kb in PLUGINS.keybinds:
                combo = kb[5] if len(kb) > 5 else "?"
                h.append(f'<tr><td style="color:#f2cc60;white-space:nowrap;"><b>{combo}</b>'
                         f'</td><td style="color:#c9d1d9;">{i18n.t("shortcuts.custom_cmd")}</td></tr>')
            h.append('</table>')
        h.append('</div>')
        view.setHtml("".join(h))
        lay.addWidget(view)


class MainWindow(QWidget):
    """A tabbed window; each tab is a splittable session.

    Shortcuts: Ctrl+T new tab - Ctrl+Tab/Ctrl+Shift+Tab cycle tabs -
    Ctrl+Shift+E/O split - Ctrl+Shift+W close pane - Alt+Arrows move between panes -
    Ctrl+, settings.
    """

    def __init__(self):
        super().__init__()
        self.broadcast = False           # when True, typing goes to every terminal pane
        self._closed_tabs = []           # stack of recently closed tabs for reopen
        self.setWindowTitle(i18n.t("win.title"))
        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.setMovable(True)
        self.tabs.setDocumentMode(True)
        self.tabs.tabCloseRequested.connect(self.close_tab)
        self.tabs.tabBarDoubleClicked.connect(self._rename_tab)
        # corner buttons: + new tab - settings
        corner = QWidget()
        ch = QHBoxLayout(corner)
        ch.setContentsMargins(0, 0, 4, 0)
        ch.setSpacing(2)
        plus = self._plus_btn = QPushButton("+")
        plus.setFixedSize(30, 26)
        plus.setToolTip(i18n.t("win.new_tab_tip"))
        plus.clicked.connect(lambda: self.new_tab())
        gear = self._gear_btn = QPushButton("⚙")
        gear.setFixedSize(30, 26)
        gear.setToolTip(i18n.t("win.settings_tip"))
        gear.clicked.connect(self.open_settings)
        helpb = self._help_btn = QPushButton("?")
        helpb.setFixedSize(30, 26)
        helpb.setToolTip(i18n.t("win.help_tip"))
        helpb.clicked.connect(self.show_shortcuts)
        for b in (plus, gear, helpb):
            b.setStyleSheet("QPushButton{background:#21262d;color:#e6edf3;"
                            "border:1px solid #30363d;border-radius:5px;font-size:15px;}"
                            "QPushButton:hover{background:#30363d;}")
        ch.addWidget(plus)
        ch.addWidget(gear)
        ch.addWidget(helpb)
        self.tabs.setCornerWidget(corner, Qt.TopRightCorner)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 0)
        lay.setSpacing(0)
        lay.addWidget(self.tabs)
        self.status = QLabel("")
        self.status.setStyleSheet(
            "color:#9da7b3;padding:3px 10px;background:#161b22;"
            "border-top:1px solid #30363d;")
        lay.addWidget(self.status)
        self._current_pane = None
        if PLUGINS.status_segments:           # periodic refresh of dynamic status segments
            self._status_timer = QTimer(self)
            self._status_timer.timeout.connect(
                lambda: self.update_status(self._current_pane))
            self._status_timer.start(2000)
        self.resize(1180, 720)
        self.setMinimumSize(520, 320)
        self._style_window()
        if not self.restore_session():
            self.new_tab()

    def _style_window(self):
        c = ui_theme_colors()                 # all UI colors derived from the theme
        bg, fg = c["bg"], c["fg"]
        pal = self.palette()
        pal.setColor(self.backgroundRole(), QColor(bg))
        self.setPalette(pal)
        self.setAutoFillBackground(True)
        qss = (
            # tab bar
            f"QTabWidget::pane{{border:0;background:{bg};}}"
            f"QTabBar{{background:{c['chrome']};}}"
            f"QTabBar::tab{{background:{c['chrome2']};color:{c['dim']};"
            f"padding:6px 16px;border:1px solid {c['border']};border-bottom:0;"
            f"margin-right:2px;border-top-left-radius:6px;border-top-right-radius:6px;}}"
            f"QTabBar::tab:selected{{background:{bg};color:{fg};"
            f"border-bottom:2px solid {c['accent']};}}"
            f"QTabBar::tab:hover{{background:{c['hover']};}}"
            # pane split handles
            f"QSplitter::handle{{background:{c['border']};}}"
            f"QSplitter::handle:horizontal{{width:1px;}}"
            f"QSplitter::handle:vertical{{height:1px;}}"
            # scroll bars (editor and dialogs)
            f"QScrollBar:vertical{{background:{c['chrome']};width:12px;margin:0;}}"
            f"QScrollBar::handle:vertical{{background:{c['border']};"
            f"border-radius:6px;min-height:24px;}}"
            f"QScrollBar::handle:vertical:hover{{background:{c['dim']};}}"
            f"QScrollBar:horizontal{{background:{c['chrome']};height:12px;margin:0;}}"
            f"QScrollBar::handle:horizontal{{background:{c['border']};"
            f"border-radius:6px;min-width:24px;}}"
            f"QScrollBar::add-line,QScrollBar::sub-line{{height:0;width:0;}}"
            # right-click menus
            f"QMenu{{background:{c['chrome']};color:{fg};border:1px solid {c['border']};}}"
            f"QMenu::item:selected{{background:{c['accent']};color:{bg};}}"
            f"QMenu::separator{{height:1px;background:{c['border']};margin:4px 8px;}}"
            # tooltips
            f"QToolTip{{background:{c['chrome2']};color:{fg};border:1px solid {c['border']};}}"
        )
        # power-user style (Python): @et.ui_style or et.set_ui_style - applied on top of the derived one
        extra = PLUGINS.ui_style
        if extra is not None:
            try:
                extra = extra(c) if callable(extra) else extra
                if extra:
                    qss += "\n" + str(extra)
            except Exception as ex:
                print(f"[easyter ui_style] {ex}")
        self.setStyleSheet(qss)
        self.status.setStyleSheet(
            f"color:{c['dim']};padding:3px 10px;background:{c['chrome']};"
            f"border-top:1px solid {c['border']};")
        # reliable opacity on Windows: whole-window opacity (the desktop shows through)
        self.setWindowOpacity(SETTINGS.get("opacity", 1.0))

    # ---------- tab management ----------
    def _active_cwd(self):
        """The working directory of the focused terminal (for new tabs/splits)."""
        foc = QApplication.focusWidget()
        if isinstance(foc, TerminalWidget) and foc.backend.cwd:
            return foc.backend.cwd
        cur = self.tabs.currentWidget()
        if isinstance(cur, SessionWidget):
            for t in cur._all_terms():
                if t.backend.cwd:
                    return t.backend.cwd
        return None

    def new_tab(self, tree=None, name=None, shell=None):
        cwd = self._active_cwd()
        if tree is None and shell:
            tree = {"type": "term", "command": shell}
        s = SessionWidget(tree, start_cwd=cwd)
        title = name or i18n.t("tab.default", n=self.tabs.count() + 1)
        idx = self.tabs.addTab(s, title)
        self.tabs.setCurrentIndex(idx)
        terms = s._all_terms()
        if terms:
            # Defer focus: setFocus() right after addTab()/setCurrentIndex()
            # doesn't stick before the tab is actually shown, leaving the new
            # terminal unfocused so its solid block cursor never draws.
            QTimer.singleShot(0, terms[0].setFocus)
        return terms[0] if terms else s

    def save_session(self):
        tabs_data = []
        for i in range(self.tabs.count()):
            s = self.tabs.widget(i)
            if isinstance(s, SessionWidget):
                tabs_data.append({
                    "name": self.tabs.tabText(i),
                    "tree": serialize_node(s.root_widget()),
                })
        try:
            with open(SESSION_PATH, "w", encoding="utf-8") as f:
                json.dump({"tabs": tabs_data}, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def restore_session(self):
        try:
            with open(SESSION_PATH, encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return False
        tabs = data.get("tabs", [])
        if not tabs:
            return False
        for t in tabs:
            self.new_tab(tree=t.get("tree"), name=t.get("name"))
        self.tabs.setCurrentIndex(0)
        QTimer.singleShot(0, self._restore_sizes)
        return True

    def _restore_sizes(self):
        for split in self.findChildren(QSplitter):
            sz = getattr(split, "_saved_sizes", None)
            if sz:
                split.setSizes(sz)

    def close_tab(self, index):
        s = self.tabs.widget(index)
        if isinstance(s, SessionWidget):
            try:                                  # remember it for reopen (Ctrl+Shift+T)
                root = s.root_widget()
                tree = serialize_node(root) if root is not None else None
                if tree is not None:
                    self._closed_tabs.append((tree, self.tabs.tabText(index)))
                    del self._closed_tabs[:-10]
            except Exception:
                pass
            s.close_all()
        self.tabs.removeTab(index)
        if s is not None:
            s.deleteLater()
        if self.tabs.count() == 0:
            self.close()

    def reopen_tab(self):
        """Reopen the most recently closed tab (Ctrl+Shift+T)."""
        if not self._closed_tabs:
            return
        tree, name = self._closed_tabs.pop()
        self.new_tab(tree=tree, name=name)

    def close_tab_for(self, session):
        idx = self.tabs.indexOf(session)
        if idx >= 0:
            self.close_tab(idx)

    def next_tab(self):
        n = self.tabs.count()
        if n:
            self.tabs.setCurrentIndex((self.tabs.currentIndex() + 1) % n)
            self._focus_current()

    def prev_tab(self):
        n = self.tabs.count()
        if n:
            self.tabs.setCurrentIndex((self.tabs.currentIndex() - 1) % n)
            self._focus_current()

    def _focus_current(self):
        s = self.tabs.currentWidget()
        if isinstance(s, SessionWidget):
            terms = s._all_terms()
            if terms:
                terms[0].setFocus()

    def update_status(self, pane):
        self._current_pane = pane
        if pane is None:
            base = ""
        elif isinstance(pane, EditorWidget):
            name = os.path.basename(pane.path) if pane.path else i18n.t("editor.untitled")
            base = i18n.t("editor.header", name=name)
        else:
            shell = os.path.basename(str(pane.command))
            mode = i18n.t("status.claude") if pane.claude_mode else ""
            base = f"  {shell}    {pane.cols}×{pane.rows}{mode}"
        segs = []
        for seg in PLUGINS.status_segments:
            try:
                segs.append(str(seg()))
            except Exception:
                pass
        if segs:
            base += "       " + " · ".join(segs)
        self.status.setText(base)

    def _rename_tab(self, index):
        if index < 0:
            return
        bar = self.tabs.tabBar()
        rect = bar.tabRect(index)
        edit = QLineEdit(self.tabs.tabText(index), bar)
        edit.setGeometry(rect)
        edit.setStyleSheet("background:#0d1117;color:#e6edf3;border:1px solid #2ea043;"
                           "border-radius:4px;padding:2px;")
        edit.selectAll()
        edit.setFocus()
        done = {"v": False}

        def finish():
            if done["v"]:
                return
            done["v"] = True
            txt = edit.text().strip()
            if txt:
                self.tabs.setTabText(index, txt)
            edit.deleteLater()

        edit.returnPressed.connect(edit.clearFocus)
        edit.editingFinished.connect(finish)
        edit.show()

    # ---- plugin API ----
    def command_palette(self):
        if not PLUGINS.commands:
            self.status.setText(i18n.t("palette.no_commands"))
            return
        names = [c[0] for c in PLUGINS.commands]
        name, ok = QInputDialog.getItem(self, i18n.t("palette.title"), i18n.t("palette.choose"),
                                        names, 0, False)
        if ok and name:
            for n, cb in PLUGINS.commands:
                if n == name:
                    try:
                        cb(self)
                    except Exception as ex:
                        print(f"[easyter command] {ex}")
                    break

    def set_tab_title(self, session, title):
        idx = self.tabs.indexOf(session)
        if idx >= 0:
            self.tabs.setTabText(idx, title)

    def active_pane(self):
        w = QApplication.focusWidget()
        while w is not None and not isinstance(w, (TerminalWidget, EditorWidget)):
            w = w.parentWidget()
        return w

    def open_text_editor(self, text, title="Text"):
        """Opens an editor tab containing text (for plugins: showing web results, e.g.)."""
        s = SessionWidget({"type": "editor"})
        idx = self.tabs.addTab(s, title)
        self.tabs.setCurrentIndex(idx)
        eds = s.findChildren(EditorWidget)
        if eds:
            eds[0].edit.setPlainText(text)
            eds[0].custom_title = title
            eds[0]._update_header()
            QTimer.singleShot(0, eds[0].setFocus)   # defer; see new_tab()
            return eds[0]
        return None

    def show_shortcuts(self):
        HelpDialog(self).exec()

    def open_settings(self):
        SettingsDialog(self).exec()

    def retranslate(self):
        """Re-apply UI text after a live language change (title + tooltips).
        Menus, dialogs and the shortcuts window pick up the new language the
        next time they open, since they read i18n.t() at build time."""
        self.setWindowTitle(i18n.t("win.title"))
        self._plus_btn.setToolTip(i18n.t("win.new_tab_tip"))
        self._gear_btn.setToolTip(i18n.t("win.settings_tip"))
        self._help_btn.setToolTip(i18n.t("win.help_tip"))

    def toggle_broadcast(self):
        """Toggle broadcasting keystrokes to every terminal pane in the window."""
        self.broadcast = not self.broadcast
        base = i18n.t("win.title")
        self.setWindowTitle(base + i18n.t("win.broadcast_tag") if self.broadcast else base)

    def notify(self, title, body):
        """Show a desktop notification via a (lazily created) tray icon."""
        try:
            if getattr(self, "_tray", None) is None:
                icon_path = os.path.join(SCRIPT_DIR, "icon.ico")
                ic = QIcon(icon_path) if os.path.exists(icon_path) else self.windowIcon()
                self._tray = QSystemTrayIcon(ic, self)
                self._tray.setToolTip("EasyTer")
                self._tray.show()
            self._tray.showMessage(title, body, QSystemTrayIcon.Information, 5000)
        except Exception:
            pass

    # ---------- Quake-style global summon hotkey (Windows: Ctrl+Alt+`) ----------
    def _register_quake(self):
        if sys.platform != "win32" or not SETTINGS.get("quake_enabled", True):
            return
        if getattr(self, "_quake_registered", False):
            return
        try:
            MOD_CONTROL, MOD_ALT, MOD_NOREPEAT = 0x0002, 0x0001, 0x4000
            VK_OEM_3 = 0xC0   # the ` / ~ key
            self._quake_id = 0xE751
            ok = ctypes.windll.user32.RegisterHotKey(
                int(self.winId()), self._quake_id,
                MOD_CONTROL | MOD_ALT | MOD_NOREPEAT, VK_OEM_3)
            self._quake_registered = bool(ok)
        except Exception:
            self._quake_registered = False

    def nativeEvent(self, eventType, message):
        try:
            if bytes(eventType) == b"windows_generic_MSG":
                msg = ctypes.wintypes.MSG.from_address(int(message))
                if msg.message == 0x0312 and msg.wParam == getattr(self, "_quake_id", -1):
                    self._toggle_quake()
                    return True, 0
        except Exception:
            pass
        return super().nativeEvent(eventType, message)

    def _toggle_quake(self):
        if self.isVisible() and self.isActiveWindow() and not self.isMinimized():
            self.hide()
        else:
            self.showNormal()
            self.raise_()
            self.activateWindow()
            ap = self.findChild(TerminalWidget)
            if ap is not None:
                ap.setFocus()

    def showEvent(self, event):
        super().showEvent(event)
        self._register_quake()

    def apply_settings(self):
        self._style_window()
        self.retranslate()
        for t in self.findChildren(TerminalWidget):
            t.font_size = SETTINGS["font_size"]
            t._init_font()
            t._layout_cache.clear()
            t._run_cache.clear()
            t._recompute_size()
            t.update()
        for e in self.findChildren(EditorWidget):
            e.apply_theme()
        self.update()

    def closeEvent(self, event):
        self.save_session()
        for t in self.findChildren(TerminalWidget):
            t.backend.close()
        super().closeEvent(event)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("EasyTer")
    load_settings()
    i18n.set_language(SETTINGS.get("language", "en"))   # UI language (en default)
    load_themes()                       # extra themes from ~/.easyter/themes/
    apply_base_colors()
    load_plugins()                      # registers plugin keybindings/commands/themes/hooks
    win = MainWindow()
    win.show()
    PLUGINS.emit("startup", win)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
