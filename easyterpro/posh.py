# -*- coding: utf-8 -*-
"""ثيمات موجِّه oh-my-posh: سرد + قراءة الحاليّ + تطبيق.

التطبيق يحدّث **السطر المُدار** فقط داخل ملفّ تعريف PowerShell ($PROFILE):
    oh-my-posh init pwsh --config '<مسار الثيم>' | Invoke-Expression
فلا نلمس أيّ سطرٍ آخر. التبويبات الجديدة تُظهر الموجِّه الجديد.
"""
import os
import re

from .shellquote import quote_shell_path

# العشرة المشهورة (بالترتيب)
FAMOUS = [
    "jandedobbeleer", "paradox", "atomic", "powerlevel10k_rainbow", "clean-detailed",
    "montys", "agnoster", "robbyrussell", "pure", "night-owl",
]

# المنسّقة في مقدّمة القائمة (تشمل ثيم Kali المؤطّر المخصّص)، ثمّ الباقي أبجديًّا
FEATURED = ["kali"] + FAMOUS

THEMES_DIR = os.environ.get("POSH_THEMES_PATH") or os.path.join(
    os.path.expanduser("~"), ".poshthemes")

# The managed line is single-quoted PowerShell. A legacy double-quoted line is
# still recognized so it can be rewritten. Group 1 is the single-quoted body
# (ASCII quotes doubled). Group 2 is the legacy double-quoted body.
_INIT_RE = re.compile(
    r"""oh-my-posh init pwsh --config (?:'((?:[^']|'')*)'|"([^"]*)")"""
)
_THEME_NAME = re.compile(r"[A-Za-z0-9._-]+\Z")


def profile_path():
    return os.path.join(os.path.expanduser("~"), "Documents",
                        "WindowsPowerShell", "Microsoft.PowerShell_profile.ps1")


def available():
    """كلّ ثيمات oh-my-posh الموجودة في THEMES_DIR: المنسّقة أوّلًا ثمّ الباقي أبجديًّا."""
    try:
        names = sorted(f[:-9] for f in os.listdir(THEMES_DIR)
                       if f.endswith(".omp.json"))
    except OSError:
        return []
    nameset = set(names)
    front = [t for t in FEATURED if t in nameset]
    rest = [t for t in names if t not in FEATURED]
    return front + rest


def _theme_name(raw, single_quoted):
    if single_quoted:
        raw = _PS_SINGLE_QUOTES.sub(lambda m: m.group(0)[0], raw)
    base = os.path.basename(raw)
    if base.lower().endswith(".omp.json"):
        return base[:-len(".omp.json")]
    return None


# Same five characters quote_shell_path doubles inside a PowerShell single quote.
_PS_SINGLE_QUOTES = re.compile("['\u2018\u2019\u201a\u201b]{2}")


def current():
    """اسم الثيم المضبوط حاليًّا في $PROFILE، أو None."""
    try:
        txt = open(profile_path(), encoding="utf-8-sig").read()
    except OSError:
        return None
    m = _INIT_RE.search(txt)
    if not m:
        return None
    if m.group(1) is not None:
        return _theme_name(m.group(1), True)
    return _theme_name(m.group(2), False)


def set_theme(name):
    """يحدّث مسار --config في السطر المُدار. يرجع True عند النجاح.

    The theme name has to be a plain filename. The path is then PowerShell
    single-quoted, so a quote or ``$(...)`` in the themes directory cannot
    run when PowerShell starts.
    """
    if not isinstance(name, str) or not _THEME_NAME.fullmatch(name):
        return False
    path = profile_path()
    try:
        txt = open(path, encoding="utf-8-sig").read()
    except OSError:
        return False
    theme_path = os.path.join(THEMES_DIR, name + ".omp.json")
    if not os.path.exists(theme_path):
        return False
    quoted = quote_shell_path(theme_path, "powershell")
    if not quoted:
        return False
    replacement = "oh-my-posh init pwsh --config " + quoted
    new, n = _INIT_RE.subn(lambda _m: replacement, txt, count=1)
    if n == 0:
        return False
    try:
        with open(path, "w", encoding="utf-8-sig") as f:
            f.write(new)
        return True
    except OSError:
        return False
