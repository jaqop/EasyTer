# -*- coding: utf-8 -*-
"""ثيمات موجِّه oh-my-posh: سرد + قراءة الحاليّ + تطبيق.

التطبيق يحدّث **السطر المُدار** فقط داخل ملفّ تعريف PowerShell ($PROFILE):
    oh-my-posh init pwsh --config "<مسار الثيم>" | Invoke-Expression
فلا نلمس أيّ سطرٍ آخر. التبويبات الجديدة تُظهر الموجِّه الجديد.
"""
import os
import re

# العشرة المشهورة (بالترتيب)
FAMOUS = [
    "jandedobbeleer", "paradox", "atomic", "powerlevel10k_rainbow", "clean-detailed",
    "montys", "agnoster", "robbyrussell", "pure", "night-owl",
]

# المنسّقة في مقدّمة القائمة (تشمل ثيم Kali المؤطّر المخصّص)، ثمّ الباقي أبجديًّا
FEATURED = ["kali"] + FAMOUS

THEMES_DIR = os.environ.get("POSH_THEMES_PATH") or os.path.join(
    os.path.expanduser("~"), ".poshthemes")

_INIT_RE = re.compile(r'(oh-my-posh init pwsh --config ")([^"]+)(")')


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


def current():
    """اسم الثيم المضبوط حاليًّا في $PROFILE، أو None."""
    try:
        txt = open(profile_path(), encoding="utf-8-sig").read()
    except OSError:
        return None
    m = _INIT_RE.search(txt)
    if m:
        return os.path.basename(m.group(2)).replace(".omp.json", "")
    return None


def set_theme(name):
    """يحدّث مسار --config في السطر المُدار. يرجع True عند النجاح."""
    path = profile_path()
    try:
        txt = open(path, encoding="utf-8-sig").read()
    except OSError:
        return False
    theme_path = os.path.join(THEMES_DIR, name + ".omp.json")
    if not os.path.exists(theme_path):
        return False
    new, n = _INIT_RE.subn(lambda m: m.group(1) + theme_path + m.group(3), txt, count=1)
    if n == 0:
        return False
    try:
        with open(path, "w", encoding="utf-8-sig") as f:
            f.write(new)
        return True
    except OSError:
        return False
