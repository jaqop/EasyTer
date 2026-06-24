# -*- coding: utf-8 -*-
"""
EasyTer — طرفيّة عربيّة حقيقيّة (ConPTY)
========================================
محاكي طرفيّة كامل مبنيّ على:
  - pywinpty  : طرفيّة وهميّة حقيقيّة (ConPTY) تشغّل البرامج التفاعليّة (claude, vim, python...)
  - pyte      : محاكي شاشة VT (مؤشّر، ألوان، تمرير، تسلسلات ANSI)
  - PySide6   : الرسم — كلّ سطرٍ يُرسَم *نصّاً موصولاً* عبر محرّك Qt، لا خليّةً خليّة،
                فتبقى العربيّة موصولة حتّى داخل البرامج التفاعليّة قدر الإمكان.

التشغيل:  pythonw EasyTer.py   (أو EasyTer.vbs / run.bat)
"""

import glob
import json
import os
import re
import shutil
import sys
import threading

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

# تسلسلات بروتوكول لوحة المفاتيح (kitty: CSI <>=? … u) — pyte لا يفهمها فيطبع 'u'
# حرفيّاً. نحذفها (لا أثر لها على العرض، مجرّد تفاوض مع لوحة المفاتيح).
KITTY_KB_RE = re.compile(r"\x1b\[[<>=?][0-9;]*u")
# تسلسل CSI/ESC ناقص في آخر الدفعة (يُحمَل للقراءة التالية تفادياً للانقسام)
INCOMPLETE_TAIL_RE = re.compile(r"\x1b\[?[0-9;?<>=]*$")

DEFAULT_SHELL = "powershell.exe"


def available_shells():
    """قائمة الصدفات المتاحة على الجهاز: (الاسم، الأمر)."""
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
)
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QMenu,
    QSplitter, QDialog, QSpinBox, QPushButton, QLabel, QColorDialog, QFontComboBox,
    QTabWidget, QLineEdit, QPlainTextEdit, QFileDialog, QSlider, QInputDialog,
    QTextEdit, QComboBox,
)

import i18n


# ---- ألوان ANSI القياسيّة ----
BASE_BG = QColor("#0d1117")
BASE_FG = QColor("#e6edf3")

# ---- الإعدادات (تُحفَظ وتُقرأ من ملفّ بجوار البرنامج) ----
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(SCRIPT_DIR, "easyter_config.json")
SESSION_PATH = os.path.join(SCRIPT_DIR, "easyter_session.json")
SETTINGS = {
    "font_family": "JetBrains Mono",
    "font_size": 13,
    "bg": "#0d1117",
    "fg": "#e6edf3",
    "palette": None,    # لوحة ANSI مخصّصة (None = الافتراضيّة)
    "opacity": 1.0,     # شفافيّة الخلفيّة (1.0 معتم، أقلّ = أشفّ)
    "language": "en",   # لغة الواجهة: "en" (افتراضيّة) أو "ar" — تُطبَّق عند الإقلاع التالي
}


def bg_rgba():
    """نصّ rgba للخلفيّة بمستوى الشفافيّة الحاليّ (للأنماط/الـstylesheet)."""
    c = QColor(SETTINGS["bg"])
    return f"rgba({c.red()},{c.green()},{c.blue()},{SETTINGS.get('opacity', 1.0):.3f})"

# لوحة ANSI الكاملة لثيم Jonathan Blow (naysayer): أخضر/تركوازيّ/تان
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
    "Jonathan Blow": ("#062329", "#d1b897", NAYSAYER_ANSI),   # naysayer كامل
    "hypr-waves": ("#141929", "#E0E4EC", {                      # منقول من h4ni0/pi
        "black": "#2A2E3D", "red": "#E8364F", "green": "#6EC8A8",
        "brown": "#F9C846", "yellow": "#F9C846", "blue": "#3A7CA5",
        "magenta": "#A8245E", "cyan": "#5EC4D4", "white": "#E0E4EC",
        "brightblack": "#4A4E5D", "brightred": "#FF4D63",
        "brightgreen": "#7ED4E0", "brightyellow": "#FFD866",
        "brightblue": "#4A9CC5", "brightmagenta": "#C43878",
        "brightcyan": "#7ED4E0", "brightwhite": "#D8DCE4",
    }),
}


THEMES_DIR = os.path.join(os.path.expanduser("~"), ".easyter", "themes")


def load_themes():
    """يحمّل ثيمات إضافيّة من ~/.easyter/themes/*.json (صيغة: name/bg/fg/ansi)."""
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
PALETTE = dict(DEFAULT_PALETTE)   # اللوحة النشطة (تتبدّل مع الثيم)


def apply_palette():
    """يضبط لوحة ANSI النشطة من الإعدادات (لوحة الثيم أو الافتراضيّة)."""
    global PALETTE
    pal = SETTINGS.get("palette")
    PALETTE = {**DEFAULT_PALETTE, **pal} if pal else dict(DEFAULT_PALETTE)


def mix_hex(a, b, t):
    """يمزج لونين سداسيّين: t=0 ⇒ a، t=1 ⇒ b. لاشتقاق ألوان الواجهة من الثيم."""
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
    """يشتقّ ألوان واجهة كاملةً من ثيم المستخدم (bg/fg/اللوحة)."""
    bg, fg = SETTINGS["bg"], SETTINGS["fg"]
    accent = PALETTE.get("blue") or PALETTE.get("cyan") or fg
    return {
        "bg": bg,
        "fg": fg,
        "chrome": mix_hex(bg, fg, 0.06),     # شريط/خلفيّة الواجهة
        "chrome2": mix_hex(bg, fg, 0.13),    # تبويب غير محدَّد
        "border": mix_hex(bg, fg, 0.22),     # حدود
        "dim": mix_hex(bg, fg, 0.55),        # نصّ خافت
        "accent": accent,                    # تمييز التركيز/التحديد
        "hover": mix_hex(bg, fg, 0.18),
    }


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


_ARABIC_FONT_LOADED = False


def _ensure_arabic_font():
    """تحميل خطّ Amiri إلى قاعدة خطوط Qt حتّى تُرسَم العربيّة به (دون تثبيت في ويندوز)."""
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
#  وضع كلود: عكس UAX#9 (قاعدة L2) — تحويل سطر كلود البصريّ ← منطقيّ
#  كلود (Ink) يطبّق BiDi بنفسه ويُخرج ترتيباً بصريّاً معكوساً. لإصلاحه:
#  نعكس البصريّ ← منطقيّ، ثمّ يعيد Qt تطبيق BiDi والتشكيل صحيحاً.
#  (PowerShell يُخرج منطقيّاً أصلاً، لذلك هذا وضعٌ يُفعَّل لكلود فقط.)
# ════════════════════════════════════════════════════════════════════════

def _is_ltr_char(ch):
    if not ch:
        return False
    o = ord(ch[0])   # base codepoint only; a cell may hold emoji+selector/ZWJ
    return (0x41 <= o <= 0x5A) or (0x61 <= o <= 0x7A) or \
           (0x30 <= o <= 0x39) or (0xC0 <= o <= 0x2AF)


def _is_inner_ltr(ch):
    # محارف تبقى ضمن جزيرة LTR (مسارات، أسماء ملفّات، أرقام إصدار…)
    return ch in "._-/:\\@~+=#&%" or _is_ltr_char(ch)


def _is_arabic_letter(ch):
    if not ch:
        return False
    o = ord(ch[0])   # base codepoint only; a cell may hold emoji+selector/ZWJ
    return (0x0600 <= o <= 0x06FF) or (0x0750 <= o <= 0x077F) or \
           (0xFB50 <= o <= 0xFDFF) or (0xFE70 <= o <= 0xFEFF)


def line_is_rtl_visual(text):
    """هل يغلب على السطر طابعٌ عربيّ (فقد عكسه كلود)؟"""
    ar = lt = 0
    for ch in text:
        if _is_arabic_letter(ch):
            ar += 1
        elif _is_ltr_char(ch) and ch.isalpha():
            lt += 1
    return ar > 0 and ar >= lt


_LTR_PUNCT = "._-/:\\@~+=#&%"


def unbidi_rtl_line(line):
    """عكس L2 لسطرٍ قاعدته RTL: اعكس كامل السطر ثمّ أعد عكس جُزُر LTR. الترقيم
    يُضمّ للجزيرة فقط إن تلاه حرفٌ لاتينيّ (فيبقى داخل config.txt لكن يخرج من
    نهاية رقمٍ مثل «01.» فلا ينقلب إلى «.01»)."""
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
    """يعكس كلّ مقطع عربيّ في مكانه — لأسطر قاعدتها LTR فيها جُزُر عربيّة
    (مثل: 'What are you working on ؟كتدعاسم...' ← الجزء العربيّ معكوس)."""
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
    """يحوّل سطر كلود البصريّ ← منطقيّ حسب اتّجاه قاعدته. None = لا تغيير.
    - قاعدة RTL (عربيّ غالب): اعكس السطر كاملاً (مع جُزُر LTR).
    - قاعدة LTR فيها عربيّ: اعكس المقاطع العربيّة في مكانها فقط.
    - إنجليزيّ خالص: لا تغيير."""
    if line_is_rtl_visual(text):
        return unbidi_rtl_line(text)
    if _has_arabic(text):
        return reverse_arabic_runs(text)
    return None


# ════════════════════════════════════════════════════════════════════════
#  نظام الإضافات (Python): يُحمَّل ~/.easyter/init.py عند الإقلاع ويعطي
#  المستخدم المحترف API: اختصارات، أوامر، ثيمات، خطّافات أحداث، عناصر حالة.
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
    """الواجهة التي يستعملها init.py عبر: import easyter as et"""

    def __init__(self):
        self.keybinds = []          # (ctrl, alt, shift, key, cb)
        self.commands = []          # (name, cb)
        self.hooks = {}             # event -> [cb]
        self.status_segments = []   # [cb]
        self.ui_style = None        # QSS إضافيّ: نصّ أو دالّة(colors)->نصّ

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
        """يخصّص شكل الواجهة (تبويبات/حدود/قوائم/حوارات) عبر Qt QSS.
        مرِّر نصّ QSS، أو دالّةً تستلم قاموس ألوان الثيم وتُرجع نصّاً:
            @et.ui_style
            def _(c): return f'QTabBar::tab{{border-radius:0;}}'
        تُطبَّق فوق نمط الثيم المشتقّ تلقائيّاً، فتُعدّل/تتجاوز ما تشاء."""
        self.ui_style = qss

    def ui_style(self, fn):
        """مزخرِف مكافئ لـset_ui_style بدالّة: @et.ui_style ثمّ def _(colors):"""
        self.ui_style = fn
        return fn

    def restyle(self):
        """يُعيد تطبيق نمط الواجهة (نادِها بعد تغيير ui_style ديناميّاً)."""
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
    """يُنفّذ اختصار إضافةٍ مطابِقاً إن وُجد؛ يرجع True عندها."""
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
    """يُحمّل ~/.easyter/init.py مع إتاحة وحدة easyter للاستيراد."""
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
    """يحوّل لون pyte (اسم/سداسيّ) إلى رموز SGR (base=30 للنصّ، 40 للخلفيّة)."""
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
    """يُسلسِل سطر pyte إلى نصٍّ يحفظ ألوانه (لإعادة البثّ عند التحجيم)."""
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
    """جلسة ConPTY حيّة + محاكي شاشة pyte."""

    data_ready = Signal()
    exited = Signal()
    alt_screen_changed = Signal(bool)  # دخول/خروج الشاشة البديلة (TUI مثل كلود)

    def __init__(self, cols, rows, command="powershell.exe"):
        super().__init__()
        self.lock = threading.Lock()
        self.screen = pyte.HistoryScreen(cols, rows, history=5000, ratio=0.5)
        self.stream = pyte.Stream(self.screen)
        self._alive = True
        self.alt_screen = False     # هل برنامج TUI ملء الشاشة نشط الآن؟
        self._scan_tail = ""        # ذيل لالتقاط تسلسلٍ مقسوم بين قراءتين
        self._carry = ""            # تسلسل ناقص محمول للقراءة التالية
        # أزِل مفتاح API وهميّاً قصيراً (يكسر `claude` داخل الطرفيّة؛ الاشتراك يكفي)
        env = dict(os.environ)
        key = env.get("ANTHROPIC_API_KEY", "")
        if key and len(key) < 40:
            env.pop("ANTHROPIC_API_KEY", None)
        # قائمة لا سلسلة: يحفظ المسارات ذات المسافات (مثل Git Bash) كاملةً
        spec = command if isinstance(command, list) else [command]
        self.proc = PtyProcess.spawn(spec, dimensions=(rows, cols), env=env)
        threading.Thread(target=self._reader, daemon=True).start()

    def _reader(self):
        try:
            while self._alive:
                data = self.proc.read(16384)
                if not data:
                    continue
                self._scan_alt(data)                 # كشف الشاشة البديلة (على الخام)
                data = self._carry + data
                data = KITTY_KB_RE.sub("", data)      # احذف 'u' المزعجة
                # احمل أيّ تسلسل ناقص في آخر الدفعة للقراءة التالية (تفادي الانقسام)
                m = INCOMPLETE_TAIL_RE.search(data)
                if m and m.group():
                    self._carry = data[m.start():]
                    data = data[:m.start()]
                else:
                    self._carry = ""
                if data:
                    with self.lock:
                        self.stream.feed(data)
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

    def _scan_alt(self, data):
        """يكشف دخول/خروج الشاشة البديلة (?1049h/?1049l) لتفعيل وضع كلود تلقائيّاً."""
        buf = self._scan_tail + data
        ih = buf.rfind("\x1b[?1049h")
        il = buf.rfind("\x1b[?1049l")
        new = self.alt_screen
        if ih >= 0 or il >= 0:
            new = ih > il        # نشط إن كان آخر تبديلٍ هو الدخول
        self._scan_tail = buf[-8:]
        if new != self.alt_screen:
            self.alt_screen = new
            self.alt_screen_changed.emit(new)

    def write(self, text):
        if not self._alive:
            return
        try:
            self.proc.write(text)
        except Exception:
            pass

    def resize(self, cols, rows):
        # ConPTY (conhost) يُعيد تدفّق محتواه ويرسم العرض تلقائيّاً عند تغيير الحجم
        # (مؤكَّد بالتجربة + توثيق ResizePseudoConsole). الإبقاء على إعادة بثٍّ يدويّةٍ
        # كان يُراكم تفتيت الأسطر وتكرارها عبر التكبيرات المتتالية. فنكتفي بتحجيم pyte
        # في مكانه (يحفظ السجلّ والمؤشّر) ونترك ConPTY يُعيد الرسم — كما يفعل صانعو
        # الطرفيّات. هذا هو السلوك نفسه في الشاشة البديلة (كلود) وفي العاديّة.
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
    def __init__(self, command=None):
        super().__init__()
        self.command = command or DEFAULT_SHELL
        self.setFocusPolicy(Qt.StrongFocus)
        self.setAutoFillBackground(True)

        self.font_size = SETTINGS["font_size"]
        self._init_font()

        self.cols = 110
        self.rows = 32
        self.scroll_offset = 0

        # حالة تحديد النصّ بالفأرة (إحداثيّات مطلقة في كامل السجلّ)
        self.sel_anchor = None   # (abs_line, col)
        self.sel_point = None
        self._paint_start = 0    # أوّل سطر مطلق ظاهر في آخر رسمة

        # وضع كلود: يعكس BiDi البصريّ لكلود ← منطقيّ. يتفعّل **تلقائيّاً** عند
        # دخول كلود الشاشة البديلة، ويتوقّف عند العودة لـPowerShell.
        # F2 يبدّل بين التلقائيّ واليدويّ عند الحاجة فقط.
        self.claude_mode = False
        self.auto_follow = True

        # حالة البحث (Ctrl+F): أسطر مطابِقة + المؤشّر الحاليّ
        self.search_bar = None
        self.search_term = ""
        self.search_matches = []   # أرقام الأسطر المطلقة المطابِقة
        self.search_idx = -1

        # ذاكرة تخبئة للأسطر (مسار PowerShell) وللمقاطع (محرّك كلود الشبكيّ)
        self._layout_cache = {}
        self._run_cache = {}

        # تقييد معدّل الرسم: نجمع دفقات كلود السريعة في رسمةٍ واحدة كلّ ~16ms
        self._repaint_timer = QTimer(self)
        self._repaint_timer.setSingleShot(True)
        self._repaint_timer.timeout.connect(self.update)

        # وميض المؤشّر
        self._blink = True
        self._blink_timer = QTimer(self)
        self._blink_timer.timeout.connect(self._toggle_blink)
        self._blink_timer.start(530)

        # تأجيل التحجيم: لا نُحجّم إلّا بعد توقّف سحب الزاوية (~140ms)
        self._resize_timer = QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.timeout.connect(self._recompute_size)

        self.setMouseTracking(False)
        self._exited = False
        self._start_backend(self.command)

        self.resize(self.cols * self.cw, self.rows * self.ch)

    def _start_backend(self, command):
        self.command = command
        self.backend = PtyBackend(self.cols, self.rows, command=command)
        self.backend.data_ready.connect(self._on_data)
        self.backend.exited.connect(self._on_exit)
        self.backend.alt_screen_changed.connect(self._on_alt_screen)
        self._exited = False

    def restart_with(self, command):
        """يُغلق الصدفة الحاليّة ويُشغّل القسم بصدفةٍ جديدة (مع تصفير الحالة)."""
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
        """يصعد إلى الجلسة (التبويب) الحاوية لهذا القسم."""
        w = self.parentWidget()
        while w is not None and not isinstance(w, SessionWidget):
            w = w.parentWidget()
        return w

    # ---- واجهة الإضافات ----
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
        # الخطّ المختار من الإعدادات أوّلاً، ثمّ سلسلة احتياط (تضمن تغطية العربيّة)
        self.font.setFamilies([
            SETTINGS["font_family"], "JetBrains Mono", "Cascadia Mono",
            "Consolas", "Vazirmatn", "Amiri",
        ])
        self.font.setStyleHint(QFont.Monospace)
        self.font.setPointSize(self.font_size)
        self.font.setHintingPreference(QFont.PreferFullHinting)
        fm = QFontMetrics(self.font)
        self.cw = max(1, fm.horizontalAdvance("M"))
        self.line_pad = 4                        # تباعد رأسيّ للقراءة
        self.ch = max(1, fm.height() + self.line_pad)
        self._text_dy = self.line_pad // 2       # توسيط النصّ رأسيّاً
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

    # ---------- إشارات المحرّك ----------
    def _on_data(self):
        self.scroll_offset = 0  # القفز إلى الأسفل عند وصول ناتج جديد
        # تقييد: رسمةٌ واحدة كلّ ~16ms مهما تدفّقت الدفعات (يمنع البطء)
        if not self._repaint_timer.isActive():
            self._repaint_timer.start(16)

    def _on_exit(self):
        self._exited = True
        self.update()

    # ---------- القياس ----------
    def resizeEvent(self, event):
        # لا نُحجّم فوراً مع كلّ حدث سحب — نؤجّل حتّى يتوقّف السحب
        self._resize_timer.start(140)
        if self.search_bar and self.search_bar.isVisible():
            self._place_search_bar()
        super().resizeEvent(event)

    def _recompute_size(self):
        cols = max(20, self.width() // self.cw)
        rows = max(5, self.height() // self.ch)
        if cols != self.cols or rows != self.rows:
            self.cols, self.rows = cols, rows
            self._layout_cache.clear()   # عرض السطر تغيّر
            self._run_cache.clear()
            self.backend.resize(cols, rows)
            self._notify_status()

    # ---------- الرسم ----------
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
        p.setFont(self.font)
        p.setPen(BASE_FG)  # لون افتراضيّ لأسطر وضع كلود (بلا formats)
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
                    self._draw_row_grid(p, yi, row, ncols)   # محرّك شبكيّ
                else:
                    self._draw_row(p, yi, row, ncols)         # مسار PowerShell

            # المؤشّر (فقط في القاع، حيث visible = الشاشة الحيّة)
            if self.scroll_offset == 0 and not cur_hidden:
                cy = cur_y * self.ch
                cx = cur_x * self.cw
                if not self.claude_mode:   # المحرّك الشبكيّ مرصوصٌ على الخلايا أصلاً
                    lay = self._row_layouts.get(cur_y)
                    if lay is not None:
                        try:
                            rx = lay[1].cursorToX(min(cur_x, ncols))
                            cx = rx[0] if isinstance(rx, (tuple, list)) else rx
                        except Exception:
                            pass
                crect = QRect(int(cx), cy, self.cw, self.ch)
                if self.hasFocus():
                    if self._blink:                       # كتلة وامضة عند التركيز
                        cc = QColor(BASE_FG)
                        cc.setAlpha(200)
                        p.fillRect(crect, cc)
                else:                                     # إطارٌ عند عدم التركيز
                    pen = QPen(BASE_FG)
                    pen.setWidth(1)
                    p.setPen(pen)
                    p.setBrush(Qt.NoBrush)
                    p.drawRect(crect.adjusted(0, 0, -1, -1))

            # تظليل التحديد (فوق النصّ، شفّاف)
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

            # تظليل نتائج البحث (السطر المطابِق كاملاً؛ الحاليّ أقوى)
            if self.search_matches:
                cur_L = (self.search_matches[self.search_idx]
                         if 0 <= self.search_idx < len(self.search_matches) else -1)
                for L in self.search_matches:
                    yi = L - start
                    if 0 <= yi < self.rows:
                        c = (QColor(240, 180, 40, 140) if L == cur_L
                             else QColor(240, 200, 80, 60))
                        p.fillRect(QRect(0, yi * self.ch, self.width(), self.ch), c)

        # شارة مرئيّة لوضع كلود (أعلى يمين)
        if self.claude_mode:
            label = i18n.t("badge.claude_auto") if self.auto_follow else i18n.t("badge.claude_manual")
            fm = QFontMetrics(self.font)
            tw = fm.horizontalAdvance(label) + 10
            bh = self.ch + 6
            bx = self.width() - tw - 6
            p.fillRect(QRect(bx, 4, tw, bh), QColor(46, 160, 67))
            p.setPen(QColor("#ffffff"))
            p.drawText(QRect(bx, 4, tw, bh), Qt.AlignCenter, label)

        # حدّ يميّز القسم المركَّز (عند التقسيم فقط)
        if isinstance(self.parentWidget(), QSplitter):
            pen = QPen(QColor("#2ea043") if self.hasFocus() else QColor("#30363d"))
            pen.setWidth(2)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            p.drawRect(1, 1, self.width() - 2, self.height() - 2)

    def _draw_row(self, p, yi, row, ncols):
        """يرسم السطر كوحدةٍ عبر QTextLayout (تشكيل + BiDi صحيح)، مع تخبئة:
        لا يُعاد بناء أيّ سطرٍ لم يتغيّر محتواه/نمطه (أداء)."""
        y = yi * self.ch
        # توقيع السطر (محتوى + نمط) رخيصٌ بلا كائنات Qt — مفتاح التخبئة
        chars = []
        runs = []
        cur = None
        rstart = 0          # بمواضع النصّ (لا الأعمدة) بسبب تخطّي خلايا الاستمرار
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
            # خليّة عريضة (إيموجي/CJK): تخطّ خليّة الاستمرار الفارغة بعدها
            # فيُرسَم المحرف بعرضه الطبيعيّ (خليّتين) ولا تنزاح الأعمدة.
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

        # وضع كلود: حوّل السطر البصريّ المعكوس ← منطقيّ (يشمل الأسطر الإنجليزيّة
        # ذات الجُزُر العربيّة) ليعيد Qt ترتيبه صحيحاً
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
        """يبني QTextLayout مع تنسيقات الألوان (مرّةً واحدة لكلّ محتوى فريد)."""
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

    # ===== المحرّك الشبكيّ (وضع كلود) =====
    def _draw_row_grid(self, p, yi, row, ncols):
        """يرسم السطر مقطعاً مقطعاً مثبّتاً على شبكة الخلايا: كلّ عنصرٍ يبقى في
        خليّته البصريّة (كما وضعه كلود) فلا تنزاح المحاذاة؛ ومقاطع العربيّة تُعكَس
        إلى المنطقيّ وتُشكَّل داخل خلاياها فتتّصل الحروف. يجمع الفائدتين."""
        y = yi * self.ch
        # اجمع الخلايا بترتيبها البصريّ مع أعمدتها (وتخطّ خلايا الاستمرار العريضة)
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
        # جمّع الخلايا المتتالية في مقاطع حسب (عربيّ؟ ، النمط)
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
                text = text[::-1]   # بصريّ كلود ← منطقيّ للتشكيل
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
        # العربيّة (RTL) تُحاذى يمين صندوقها؛ غيرها يسار
        dx = (x0 + boxw - natw) if is_ar else x0
        p.setPen(fg)
        layout.draw(p, QPointF(dx, y + self._text_dy))

    # ---------- الإدخال ----------
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

        # اختصارات الإضافات (لها الأولويّة)
        if run_plugin_keybind(self, ctrl, alt, shift, key):
            return
        # لوحة الأوامر: Ctrl+Shift+P
        if ctrl and shift and key == Qt.Key_P:
            if hasattr(win, "command_palette"):
                win.command_palette()
            return
        # كلّ الاختصارات: F1
        if key == Qt.Key_F1:
            if hasattr(win, "show_shortcuts"):
                win.show_shortcuts()
            return

        # ----- التبويبات -----
        if ctrl and key == Qt.Key_T:                  # تبويب جديد
            if hasattr(win, "new_tab"):
                win.new_tab()
            return
        if ctrl and key == Qt.Key_Tab:                # التبويب التالي
            if hasattr(win, "next_tab"):
                win.next_tab()
            return
        if ctrl and key == Qt.Key_Backtab:            # Ctrl+Shift+Tab: السابق
            if hasattr(win, "prev_tab"):
                win.prev_tab()
            return

        # ----- التقسيم والتنقّل (داخل الجلسة) -----
        if ctrl and shift and key == Qt.Key_E:        # قسمان جنباً إلى جنب
            if sess:
                sess.split_pane(self, Qt.Horizontal)
            return
        if ctrl and shift and key == Qt.Key_O:        # قسمان فوق/تحت
            if sess:
                sess.split_pane(self, Qt.Vertical)
            return
        if ctrl and shift and key == Qt.Key_N:        # محرّر جنب الطرفيّة
            if sess:
                sess.split_pane(self, Qt.Horizontal, factory=EditorWidget)
            return
        if ctrl and shift and key == Qt.Key_W:        # إغلاق القسم
            if sess:
                sess.close_pane(self)
            return
        if alt and key in (Qt.Key_Left, Qt.Key_Right, Qt.Key_Up, Qt.Key_Down):
            if sess:
                sess.focus_dir(self, key)
            return

        # تكبير/تصغير/إعادة ضبط الخطّ (للقسم المركَّز)
        if ctrl and key in (Qt.Key_Plus, Qt.Key_Equal):
            self.change_font(+1)
            return
        if ctrl and key == Qt.Key_Minus:
            self.change_font(-1)
            return
        if ctrl and key == Qt.Key_0:            # إعادة الحجم الافتراضيّ
            self.reset_font()
            return

        # الإعدادات: Ctrl+,
        if ctrl and key == Qt.Key_Comma:
            if hasattr(win, "open_settings"):
                win.open_settings()
            return

        # البحث في المخرجات: Ctrl+F
        if ctrl and key == Qt.Key_F:
            self._open_search()
            return

        # F2: تبديل وضع كلود (عكس BiDi)
        if key == Qt.Key_F2:
            self.toggle_claude_mode()
            return

        # نسخ: Ctrl+Shift+C
        if ctrl and shift and key == Qt.Key_C:
            self._copy_selection()
            return

        # لصق: Ctrl+Shift+V
        if ctrl and shift and key == Qt.Key_V:
            txt = QApplication.clipboard().text()
            if txt:
                self.backend.write(txt.replace("\r\n", "\r").replace("\n", "\r"))
            return

        self.scroll_offset = 0

        seq = None
        if key in (Qt.Key_Return, Qt.Key_Enter):
            seq = "\r"
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

        if self.sel_anchor is not None:   # امسح أيّ تحديد عالق عند الكتابة
            self.sel_anchor = self.sel_point = None
        if seq:
            self.backend.write(seq)
            self._blink = True            # المؤشّر صلبٌ فور الكتابة

    # ---------- تحديد النصّ بالفأرة ----------
    def _pos_to_cell(self, pos):
        yi = max(0, min(self.rows - 1, int(pos.y() // self.ch)))
        col = None
        lay = getattr(self, "_row_layouts", {}).get(yi)
        if lay is not None:
            try:
                col = lay[1].xToCursor(float(pos.x()))  # عمود منطقيّ دقيق رغم BiDi
            except Exception:
                col = None
        if col is None:
            col = round(pos.x() / self.cw)
        col = max(0, min(self.cols, col))
        abs_line = self._paint_start + yi
        return abs_line, col

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.setFocus()
            self.sel_anchor = self._pos_to_cell(event.position())
            self.sel_point = self.sel_anchor
            self.update()

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton and self.sel_anchor is not None:
            self.sel_point = self._pos_to_cell(event.position())
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self._norm_sel():
            self._copy_selection()  # نسخ تلقائيّ عند رفع الفأرة

    def _norm_sel(self):
        """يرجع ((lo_line,lo_col),(hi_line,hi_col)) مرتّباً، أو None إن لا تحديد."""
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
                    # في وضع كلود ننسخ السطر كاملاً منطقيّاً (العكس لا يقبل تجزئة الأعمدة)
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
        """نصّ السطر كاملاً مع تخطّي خلايا استمرار المحارف العريضة (إيموجي)."""
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

    # ---------- البحث في المخرجات (Ctrl+F) ----------
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
        # ابدأ من آخر مطابَقة (الأقرب للأسفل)
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
        txt = QApplication.clipboard().text()
        if txt:
            self.backend.write(txt.replace("\r\n", "\r").replace("\n", "\r"))

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
        base = "EasyTer — طرفيّة عربيّة"
        if self.claude_mode:
            tag = i18n.t("claude.tag_auto") if self.auto_follow else i18n.t("claude.tag_manual")
        else:
            tag = "" if self.auto_follow else "  (يدويّ)"
        w.setWindowTitle(base + tag)

    def _on_alt_screen(self, active):
        """تفعيل/إيقاف وضع كلود تلقائيّاً مع دخول/خروج برنامج TUI ملء الشاشة."""
        if self.auto_follow:
            self.claude_mode = active
            self._set_title()
            self.update()
            self._notify_status()
        if active:
            PLUGINS.emit("claude_detected", self)

    def toggle_claude_mode(self):
        # F2: إن كنّا تلقائيّين انتقل ليدويّ واقلب الحالة؛ وإلّا ارجع للتلقائيّ
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
        # تبديل الصدفة (يُعيد تشغيل هذا القسم)
        shell_menu = menu.addMenu(i18n.t("menu.shell"))
        shell_acts = {}
        for name, cmd in available_shells():
            a = shell_menu.addAction(("● " if cmd == self.command else "    ") + name)
            shell_acts[a] = cmd
        menu.addSeparator()
        # التقسيم
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
        # في الشاشة البديلة (كلود/TUI): مرّر العجلة إلى البرنامج ليمرّر محتواه بنفسه
        if self.backend.alt_screen:
            btn = 64 if delta > 0 else 65   # 64=أعلى، 65=أسفل (SGR mouse)
            pos = event.position()
            col = max(1, int(pos.x() // self.cw) + 1)
            rowy = max(1, int(pos.y() // self.ch) + 1)
            seq = f"\x1b[<{btn};{col};{rowy}M"
            for _ in range(3):
                self.backend.write(seq)
            return
        # عاديّ (PowerShell): مرّر في سجلّ pyte
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
    """لوحة تخصيص: الخطّ وحجمه، الخلفيّة ولون النصّ، وثيمات جاهزة."""

    def __init__(self, win):
        super().__init__(win)
        self.win = win
        self.bg = SETTINGS["bg"]
        self.fg = SETTINGS["fg"]
        self.palette = dict(PALETTE)               # لوحة ANSI قابلة للتعديل الحرّ
        self.opacity = SETTINGS.get("opacity", 1.0)
        self._orig_opacity = self.opacity
        self._orig_bg = SETTINGS["bg"]
        self._orig_fg = SETTINGS["fg"]
        self._orig_palette = SETTINGS.get("palette")
        self._ansi_btns = {}
        self.setWindowTitle(i18n.t("settings.title"))
        self.setMinimumWidth(380)
        self.setStyleSheet(
            "QDialog{background:#161b22;color:#e6edf3;}"
            "QLabel{color:#e6edf3;} QPushButton{background:#21262d;color:#e6edf3;"
            "border:1px solid #30363d;border-radius:6px;padding:6px 10px;}"
            "QPushButton:hover{background:#30363d;}"
            "QSpinBox,QFontComboBox{background:#0d1117;color:#e6edf3;"
            "border:1px solid #30363d;border-radius:4px;padding:3px;}"
        )
        g = QGridLayout(self)
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

        # الشفافيّة (معاينة حيّة أثناء السحب)
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

        # ألوان ANSI (تعديل حرّ)
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

        # اللغة (تُطبَّق عند الإقلاع التالي)
        g.addWidget(QLabel(i18n.t("settings.language")), 7, 0)
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
        g.addWidget(lw, 7, 1)

        btns = QHBoxLayout()
        ok = QPushButton(i18n.t("settings.apply"))
        ok.clicked.connect(self._apply)
        cancel = QPushButton(i18n.t("settings.cancel"))
        cancel.clicked.connect(self.reject)
        btns.addStretch(1)
        btns.addWidget(cancel)
        btns.addWidget(ok)
        bw = QWidget()
        bw.setLayout(btns)
        g.addWidget(bw, 8, 0, 1, 2)

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
        # معاينة حيّة للثيم
        SETTINGS["bg"], SETTINGS["fg"], SETTINGS["palette"] = self.bg, self.fg, self.palette
        apply_base_colors()
        self.win.apply_settings()

    def _on_opacity(self, v):
        self.opacity = v / 100.0
        self.op_label.setText(f"{v}%")
        self.win.setWindowOpacity(self.opacity)   # معاينة حيّة فوريّة

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
        # تراجع عن كلّ المعاينات الحيّة (ثيم/ألوان/شفافيّة)
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
        SETTINGS["language"] = self.lang_combo.currentData()   # تُطبَّق عند الإقلاع التالي
        save_settings()
        apply_base_colors()
        self.win.apply_settings()
        self.accept()


class SearchBar(QWidget):
    """شريط بحثٍ يطفو أعلى يمين القسم: حقل + عدّاد + سابق/تالي/إغلاق."""

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
    """تلوين صياغةٍ عامّ (C/C++/Python/JS…): كلمات مفتاحيّة، نصوص، تعليقات، أرقام."""

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
        for rx, f in self.rules:
            for m in rx.finditer(text):
                self.setFormat(m.start(), m.end() - m.start(), f)
        # سطر يبدأ بـ# : موجّه معالج (برتقاليّ) أو تعليق بايثون (أخضر)
        stripped = text.lstrip()
        if stripped.startswith("#"):
            indent = len(text) - len(stripped)
            w = re.match(r"#\s*(\w+)", stripped)
            f = self.preproc_fmt if (w and w.group(1) in self.PREPROC) else self.comment_fmt
            self.setFormat(indent, len(stripped), f)
        # تعليقات الكتلة /* */ (عبر الأسطر)
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
    """شريط أرقام الأسطر على يسار المحرّر."""

    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor

    def paintEvent(self, e):
        self.editor._paint_line_numbers(e)


class CodeEdit(QPlainTextEdit):
    """محرّر النصّ الداخليّ؛ يمرّر الاختصارات الخاصّة إلى EditorWidget."""

    def __init__(self, owner):
        super().__init__()
        self.owner = owner
        self.setLineWrapMode(QPlainTextEdit.NoWrap)
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
    """محرّر ملفّاتٍ مدمج كقسمٍ في شجرة التقسيم (فتح/حفظ، عربيّ، بنفس الثيم)."""

    def __init__(self, path=None, title=None):
        super().__init__()
        self.path = None
        self.custom_title = title       # عنوانٌ يدويّ (نقر مزدوج على الترويسة)
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        self.header = QLabel("")
        self.header.setToolTip(i18n.t("editor.rename_tip"))
        self.header.installEventFilter(self)
        self.edit = CodeEdit(self)
        self.highlighter = CodeHighlighter(self.edit.document())
        v.addWidget(self.header)
        v.addWidget(self.edit, 1)
        self.setFocusProxy(self.edit)
        self.edit.modificationChanged.connect(lambda *_: self._update_header())
        self.apply_theme()
        if path:
            self.open_path(path)
        else:
            self._update_header()

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
            name = "بلا عنوان"
        dot = "● " if self.edit.document().isModified() else ""
        self.header.setText(f"  ✎ {dot}{name}")

    def open_dialog(self):
        path, _ = QFileDialog.getOpenFileName(self, i18n.t("dialog.open_file"))
        if path:
            self.open_path(path)

    def open_path(self, path):
        try:
            with open(path, encoding="utf-8", errors="replace") as fh:
                self.edit.setPlainText(fh.read())
            self.path = path
            self.edit.document().setModified(False)
        except Exception as ex:
            self.edit.setPlainText(f"# تعذّر فتح الملفّ: {ex}")
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
        if ctrl and k == Qt.Key_T and hasattr(win, "new_tab"):
            win.new_tab()
            return True
        return False


def serialize_node(widget):
    """يحوّل شجرة القسم (QSplitter/TerminalWidget) إلى بنية قابلة للحفظ."""
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
    """يبني شجرة القسم من بنيةٍ محفوظة."""
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
    """جلسة = محتوى تبويبٍ واحد: شجرة طرفيّاتٍ قابلة للتقسيم (طوليّ/عرضيّ)."""

    def __init__(self, tree=None):
        super().__init__()
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(8, 8, 8, 8)
        self.lay.addWidget(build_node(tree) if tree else TerminalWidget())

    def root_widget(self):
        item = self.lay.itemAt(0)
        return item.widget() if item else None

    def _all_terms(self):
        return self.findChildren(TerminalWidget)

    def _all_panes(self):
        """كلّ الأقسام: طرفيّات ومحرّرات."""
        return self.findChildren(TerminalWidget) + self.findChildren(EditorWidget)

    def close_all(self):
        for t in self.findChildren(TerminalWidget):
            t.backend.close()

    def split_pane(self, pane, orientation, factory=None):
        new_w = factory() if factory else TerminalWidget()
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
            # آخر قسمٍ في الجلسة → أغلق التبويب كاملاً
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
    ]),
    ("sc.cat.split", [
        ("sck.split.h", "sc.split.h"),
        ("sck.split.v", "sc.split.v"),
        ("sck.split.editor", "sc.split.editor"),
        ("sck.split.close", "sc.split.close"),
        ("sck.split.nav", "sc.split.nav"),
        ("sck.split.resize", "sc.split.resize"),
    ]),
    ("sc.cat.clip", [
        ("sck.clip.copypaste", "sc.clip.copypaste"),
        ("sck.clip.select", "sc.clip.select"),
        ("sck.clip.rightclick", "sc.clip.rightclick"),
        ("sck.clip.search", "sc.clip.search"),
        ("sck.clip.wheel", "sc.clip.wheel"),
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
    ]),
]


class HelpDialog(QDialog):
    """قائمة كلّ الاختصارات (F1 أو زرّ ؟)."""

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
    """نافذة بتبويبات؛ كلّ تبويب جلسةٌ قابلة للتقسيم.

    اختصارات: Ctrl+T تبويب جديد · Ctrl+Tab/Ctrl+Shift+Tab تنقّل التبويبات ·
    Ctrl+Shift+E/O تقسيم · Ctrl+Shift+W إغلاق قسم · Alt+أسهم تنقّل الأقسام ·
    Ctrl+, الإعدادات.
    """

    def __init__(self):
        super().__init__()
        self.setWindowTitle(i18n.t("win.title"))
        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.setMovable(True)
        self.tabs.setDocumentMode(True)
        self.tabs.tabCloseRequested.connect(self.close_tab)
        self.tabs.tabBarDoubleClicked.connect(self._rename_tab)
        # أزرار الزاوية: + تبويب جديد · ⚙ الإعدادات
        corner = QWidget()
        ch = QHBoxLayout(corner)
        ch.setContentsMargins(0, 0, 4, 0)
        ch.setSpacing(2)
        plus = QPushButton("+")
        plus.setFixedSize(30, 26)
        plus.setToolTip(i18n.t("win.new_tab_tip"))
        plus.clicked.connect(lambda: self.new_tab())
        gear = QPushButton("⚙")
        gear.setFixedSize(30, 26)
        gear.setToolTip(i18n.t("win.settings_tip"))
        gear.clicked.connect(self.open_settings)
        helpb = QPushButton("?")
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
        if PLUGINS.status_segments:           # تحديث دوريّ لعناصر الحالة الديناميّة
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
        c = ui_theme_colors()                 # كلّ ألوان الواجهة مشتقّة من الثيم
        bg, fg = c["bg"], c["fg"]
        pal = self.palette()
        pal.setColor(self.backgroundRole(), QColor(bg))
        self.setPalette(pal)
        self.setAutoFillBackground(True)
        qss = (
            # شريط التبويبات
            f"QTabWidget::pane{{border:0;background:{bg};}}"
            f"QTabBar{{background:{c['chrome']};}}"
            f"QTabBar::tab{{background:{c['chrome2']};color:{c['dim']};"
            f"padding:6px 16px;border:1px solid {c['border']};border-bottom:0;"
            f"margin-right:2px;border-top-left-radius:6px;border-top-right-radius:6px;}}"
            f"QTabBar::tab:selected{{background:{bg};color:{fg};"
            f"border-bottom:2px solid {c['accent']};}}"
            f"QTabBar::tab:hover{{background:{c['hover']};}}"
            # مقابض تقسيم الأقسام
            f"QSplitter::handle{{background:{c['border']};}}"
            f"QSplitter::handle:horizontal{{width:1px;}}"
            f"QSplitter::handle:vertical{{height:1px;}}"
            # أشرطة التمرير (المحرّر والحوارات)
            f"QScrollBar:vertical{{background:{c['chrome']};width:12px;margin:0;}}"
            f"QScrollBar::handle:vertical{{background:{c['border']};"
            f"border-radius:6px;min-height:24px;}}"
            f"QScrollBar::handle:vertical:hover{{background:{c['dim']};}}"
            f"QScrollBar:horizontal{{background:{c['chrome']};height:12px;margin:0;}}"
            f"QScrollBar::handle:horizontal{{background:{c['border']};"
            f"border-radius:6px;min-width:24px;}}"
            f"QScrollBar::add-line,QScrollBar::sub-line{{height:0;width:0;}}"
            # قوائم نقر اليمين
            f"QMenu{{background:{c['chrome']};color:{fg};border:1px solid {c['border']};}}"
            f"QMenu::item:selected{{background:{c['accent']};color:{bg};}}"
            f"QMenu::separator{{height:1px;background:{c['border']};margin:4px 8px;}}"
            # تلميحات
            f"QToolTip{{background:{c['chrome2']};color:{fg};border:1px solid {c['border']};}}"
        )
        # نمط المحترفين (Python): @et.ui_style أو et.set_ui_style — يُطبَّق فوق المشتقّ
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
        # الشفافيّة الموثوقة على ويندوز: شفافيّة النافذة كاملةً (يظهر سطح المكتب)
        self.setWindowOpacity(SETTINGS.get("opacity", 1.0))

    # ---------- إدارة التبويبات ----------
    def new_tab(self, tree=None, name=None, shell=None):
        if tree is None and shell:
            tree = {"type": "term", "command": shell}
        s = SessionWidget(tree)
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
            s.close_all()
        self.tabs.removeTab(index)
        if s is not None:
            s.deleteLater()
        if self.tabs.count() == 0:
            self.close()

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
            name = os.path.basename(pane.path) if pane.path else "بلا عنوان"
            base = f"  ✎ محرّر · {name}"
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

    # ---- واجهة الإضافات ----
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

    def open_text_editor(self, text, title="نصّ"):
        """يفتح تبويب محرّرٍ يحوي نصّاً (للإضافات: عرض نتائج الويب مثلاً)."""
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

    def apply_settings(self):
        self._style_window()
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
    i18n.set_language(SETTINGS.get("language", "en"))   # لغة الواجهة (en افتراضيّة)
    load_themes()                       # ثيمات إضافيّة من ~/.easyter/themes/
    apply_base_colors()
    load_plugins()                      # يسجّل اختصارات/أوامر/ثيمات/خطّافات الإضافات
    win = MainWindow()
    win.show()
    PLUGINS.emit("startup", win)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
