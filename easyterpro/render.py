# -*- coding: utf-8 -*-
"""الألوان والثيمات + تحميل خطّ Amiri.

الثيم النشط يحدّد BASE_BG / BASE_FG / PALETTE (متغيّرات وحدة تُعاد كتابتها بـapply_theme).
الوصول للألوان يجب أن يكون عبر هذه الوحدة (render.BASE_BG / render.resolve_color)
حتّى يسري تبديل الثيم فورًا على كلّ الألواح.
"""

import os

from PySide6.QtGui import QColor, QFontDatabase

# ---- مكتبة الثيمات: خلفية/مقدّمة + ١٦ لون ANSI ----
THEMES = {
    "EasyTer Dark": {
        "bg": "#0d1117", "fg": "#e6edf3",
        "ansi": {
            "black": "#0d1117", "red": "#ff6b6b", "green": "#7ee787", "yellow": "#e3b341",
            "blue": "#6ca0f6", "magenta": "#d2a8ff", "cyan": "#56d4dd", "white": "#e6edf3",
            "brightblack": "#6e7681", "brightred": "#ff8a8a", "brightgreen": "#a2f5b0",
            "brightyellow": "#f2cc60", "brightblue": "#8db4f8", "brightmagenta": "#e0c1ff",
            "brightcyan": "#7ee0e6", "brightwhite": "#ffffff",
        },
    },
    "One Dark": {
        "bg": "#282c34", "fg": "#abb2bf",
        "ansi": {
            "black": "#282c34", "red": "#e06c75", "green": "#98c379", "yellow": "#e5c07b",
            "blue": "#61afef", "magenta": "#c678dd", "cyan": "#56b6c2", "white": "#abb2bf",
            "brightblack": "#5c6370", "brightred": "#e06c75", "brightgreen": "#98c379",
            "brightyellow": "#e5c07b", "brightblue": "#61afef", "brightmagenta": "#c678dd",
            "brightcyan": "#56b6c2", "brightwhite": "#ffffff",
        },
    },
    "Dracula": {
        "bg": "#282a36", "fg": "#f8f8f2",
        "ansi": {
            "black": "#21222c", "red": "#ff5555", "green": "#50fa7b", "yellow": "#f1fa8c",
            "blue": "#bd93f9", "magenta": "#ff79c6", "cyan": "#8be9fd", "white": "#f8f8f2",
            "brightblack": "#6272a4", "brightred": "#ff6e6e", "brightgreen": "#69ff94",
            "brightyellow": "#ffffa5", "brightblue": "#d6acff", "brightmagenta": "#ff92df",
            "brightcyan": "#a4ffff", "brightwhite": "#ffffff",
        },
    },
    "Nord": {
        "bg": "#2e3440", "fg": "#d8dee9",
        "ansi": {
            "black": "#3b4252", "red": "#bf616a", "green": "#a3be8c", "yellow": "#ebcb8b",
            "blue": "#81a1c1", "magenta": "#b48ead", "cyan": "#88c0d0", "white": "#e5e9f0",
            "brightblack": "#4c566a", "brightred": "#bf616a", "brightgreen": "#a3be8c",
            "brightyellow": "#ebcb8b", "brightblue": "#81a1c1", "brightmagenta": "#b48ead",
            "brightcyan": "#8fbcbb", "brightwhite": "#eceff4",
        },
    },
    "Solarized Dark": {
        "bg": "#002b36", "fg": "#839496",
        "ansi": {
            "black": "#073642", "red": "#dc322f", "green": "#859900", "yellow": "#b58900",
            "blue": "#268bd2", "magenta": "#d33682", "cyan": "#2aa198", "white": "#eee8d5",
            "brightblack": "#586e75", "brightred": "#cb4b16", "brightgreen": "#586e75",
            "brightyellow": "#657b83", "brightblue": "#839496", "brightmagenta": "#6c71c4",
            "brightcyan": "#93a1a1", "brightwhite": "#fdf6e3",
        },
    },
    "Gruvbox Dark": {
        "bg": "#282828", "fg": "#ebdbb2",
        "ansi": {
            "black": "#282828", "red": "#cc241d", "green": "#98971a", "yellow": "#d79921",
            "blue": "#458588", "magenta": "#b16286", "cyan": "#689d6a", "white": "#a89984",
            "brightblack": "#928374", "brightred": "#fb4934", "brightgreen": "#b8bb26",
            "brightyellow": "#fabd2f", "brightblue": "#83a598", "brightmagenta": "#d3869b",
            "brightcyan": "#8ec07c", "brightwhite": "#ebdbb2",
        },
    },
    # ثيم جوناثان بلو (إعادة إنتاج Naysayer): خلفية فيروزية غامقة + نصّ كريميّ
    "Jonathan Blow": {
        "bg": "#062329", "fg": "#d1b897",
        "ansi": {
            "black": "#0b3335", "red": "#f92672", "green": "#44b340", "yellow": "#e6db74",
            "blue": "#66d9ef", "magenta": "#ae81ff", "cyan": "#2ec09c", "white": "#d1b897",
            "brightblack": "#126367", "brightred": "#ff6e6e", "brightgreen": "#a6e22e",
            "brightyellow": "#fd971f", "brightblue": "#c1d1e3", "brightmagenta": "#fd5ff0",
            "brightcyan": "#a1efe4", "brightwhite": "#ffffff",
        },
    },
    "Tokyo Night": {
        "bg": "#1a1b26", "fg": "#c0caf5",
        "ansi": {
            "black": "#15161e", "red": "#f7768e", "green": "#9ece6a", "yellow": "#e0af68",
            "blue": "#7aa2f7", "magenta": "#bb9af7", "cyan": "#7dcfff", "white": "#a9b1d6",
            "brightblack": "#414868", "brightred": "#f7768e", "brightgreen": "#9ece6a",
            "brightyellow": "#e0af68", "brightblue": "#7aa2f7", "brightmagenta": "#bb9af7",
            "brightcyan": "#7dcfff", "brightwhite": "#c0caf5",
        },
    },
    "Catppuccin Mocha": {
        "bg": "#1e1e2e", "fg": "#cdd6f4",
        "ansi": {
            "black": "#45475a", "red": "#f38ba8", "green": "#a6e3a1", "yellow": "#f9e2af",
            "blue": "#89b4fa", "magenta": "#f5c2e7", "cyan": "#94e2d5", "white": "#bac2de",
            "brightblack": "#585b70", "brightred": "#f38ba8", "brightgreen": "#a6e3a1",
            "brightyellow": "#f9e2af", "brightblue": "#89b4fa", "brightmagenta": "#f5c2e7",
            "brightcyan": "#94e2d5", "brightwhite": "#a6adc8",
        },
    },
    "Monokai": {
        "bg": "#272822", "fg": "#f8f8f2",
        "ansi": {
            "black": "#272822", "red": "#f92672", "green": "#a6e22e", "yellow": "#f4bf75",
            "blue": "#66d9ef", "magenta": "#ae81ff", "cyan": "#a1efe4", "white": "#f8f8f2",
            "brightblack": "#75715e", "brightred": "#f92672", "brightgreen": "#a6e22e",
            "brightyellow": "#f4bf75", "brightblue": "#66d9ef", "brightmagenta": "#ae81ff",
            "brightcyan": "#a1efe4", "brightwhite": "#f9f8f5",
        },
    },
    "Synthwave '84": {
        "bg": "#262335", "fg": "#ff7edb",
        "ansi": {
            "black": "#262335", "red": "#fe4450", "green": "#72f1b8", "yellow": "#fede5d",
            "blue": "#03edf9", "magenta": "#ff7edb", "cyan": "#03edf9", "white": "#ffffff",
            "brightblack": "#495495", "brightred": "#fe4450", "brightgreen": "#72f1b8",
            "brightyellow": "#fede5d", "brightblue": "#03edf9", "brightmagenta": "#ff7edb",
            "brightcyan": "#03edf9", "brightwhite": "#ffffff",
        },
    },
    "Ayu Dark": {
        "bg": "#0a0e14", "fg": "#b3b1ad",
        "ansi": {
            "black": "#01060e", "red": "#ea6c73", "green": "#91b362", "yellow": "#f9af4f",
            "blue": "#53bdfa", "magenta": "#fae994", "cyan": "#90e1c6", "white": "#c7c7c7",
            "brightblack": "#686868", "brightred": "#f07178", "brightgreen": "#c2d94c",
            "brightyellow": "#ffb454", "brightblue": "#59c2ff", "brightmagenta": "#ffee99",
            "brightcyan": "#95e6cb", "brightwhite": "#ffffff",
        },
    },
    "Solarized Light": {
        "bg": "#fdf6e3", "fg": "#657b83",
        "ansi": {
            "black": "#073642", "red": "#dc322f", "green": "#859900", "yellow": "#b58900",
            "blue": "#268bd2", "magenta": "#d33682", "cyan": "#2aa198", "white": "#eee8d5",
            "brightblack": "#002b36", "brightred": "#cb4b16", "brightgreen": "#586e75",
            "brightyellow": "#657b83", "brightblue": "#839496", "brightmagenta": "#6c71c4",
            "brightcyan": "#93a1a1", "brightwhite": "#fdf6e3",
        },
    },
}

# ---- الحالة النشطة (تُملأ بـapply_theme) ----
BASE_BG = QColor("#0d1117")
BASE_FG = QColor("#e6edf3")
PALETTE = {}
CURRENT_THEME = "EasyTer Dark"


def theme_names():
    return list(THEMES.keys())


def register_custom_themes(custom):
    """يدمج/يستبدل ثيمات المستخدم من config (custom_themes) — تطابق دقيقة وثيمات خاصّة."""
    for name, t in (custom or {}).items():
        if isinstance(t, dict) and t.get("bg") and t.get("fg") and isinstance(t.get("ansi"), dict):
            THEMES[name] = t


def apply_theme(name):
    """يضبط الألوان النشطة من الثيم المسمّى. يرجع الاسم المطبَّق فعليًّا."""
    global BASE_BG, BASE_FG, PALETTE, CURRENT_THEME
    t = THEMES.get(name) or THEMES["EasyTer Dark"]
    name = name if name in THEMES else "EasyTer Dark"
    BASE_BG = QColor(t["bg"])
    BASE_FG = QColor(t["fg"])
    ansi = t["ansi"]
    PALETTE = dict(ansi)
    PALETTE["brown"] = ansi.get("yellow", "#e3b341")   # pyte يسمّي الأصفر "brown"
    CURRENT_THEME = name
    return name


def resolve_color(name, is_bg):
    if name == "default" or name is None:
        return BASE_BG if is_bg else BASE_FG
    if name in PALETTE:
        return QColor(PALETTE[name])
    # truecolor / 256 يأتي كستّ خانات سداسيّة
    if isinstance(name, str) and len(name) == 6:
        try:
            return QColor("#" + name)
        except Exception:
            pass
    return BASE_BG if is_bg else BASE_FG


def _load_bundled_schemes():
    """يحمّل مجموعة الثيمات المرفقة (schemes.json، مولّدة من iTerm2-Color-Schemes،
    +550 ثيمًا). الثيمات المدمجة تبقى لها الأولويّة عند تطابق الاسم."""
    import json
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "schemes.json")
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return
    for nm, t in data.items():
        if nm not in THEMES and isinstance(t, dict) and t.get("bg") and t.get("ansi"):
            THEMES[nm] = t


_load_bundled_schemes()


# طبّق الثيم الافتراضي عند الاستيراد (main يعيد تطبيق ثيم config لاحقًا)
apply_theme("EasyTer Dark")


# ---- تحميل خطّ Amiri ----
_ARABIC_FONT_LOADED = False


def ensure_arabic_font():
    """تحميل خطّ Amiri إلى قاعدة خطوط Qt حتّى تُرسَم العربيّة به (دون تثبيت في ويندوز)."""
    global _ARABIC_FONT_LOADED
    if _ARABIC_FONT_LOADED:
        return
    base = os.path.join(os.path.expanduser("~"), ".wezterm-fonts")
    for fn in ("Amiri-Regular.ttf", "Amiri-Bold.ttf"):
        path = os.path.join(base, fn)
        if os.path.exists(path):
            try:
                QFontDatabase.addApplicationFont(path)
            except Exception:
                pass
    _ARABIC_FONT_LOADED = True
