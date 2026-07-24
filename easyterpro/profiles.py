# -*- coding: utf-8 -*-
"""كشف الصدفات المتاحة تلقائيًّا على ويندوز (مستوحى من مولِّدات Windows Terminal).

يكتشف: PowerShell (بلا/مع profile), PowerShell 7 (pwsh), cmd, توزيعات WSL, Git Bash.
"""

import os
import shutil
import subprocess
import ctypes


def _short_path(p):
    """المسار القصير 8.3 (بلا فراغات) — winpty/ConPTY يفشل مع المسارات ذات الفراغ."""
    try:
        buf = ctypes.create_unicode_buffer(260)
        if ctypes.windll.kernel32.GetShortPathNameW(p, buf, 260):
            return buf.value or p
    except Exception:
        pass
    return p


class Profile:
    def __init__(self, name, command, source="builtin"):
        self.name = name
        self.command = command      # سلسلة أمر تُمرَّر إلى ConPTY
        self.source = source

    def __repr__(self):
        return f"Profile({self.name!r})"


def detect_profiles():
    """يرجع قائمة Profile بالصدفات الموجودة فعلًا على هذا الجهاز."""
    profiles = []

    # PowerShell — الافتراضي يحمّل $PROFILE فيظهر موجِّه oh-my-posh المختار (paradox/kali…).
    # ونوفّر نسخةً سريعةً بلا profile لمن يفضّل إقلاعًا أسرع بلا تنميق.
    profiles.append(Profile("PowerShell", "powershell.exe"))
    profiles.append(Profile("PowerShell (سريع · بلا profile)", "powershell.exe -NoProfile"))

    # PowerShell 7+ إن كان مثبّتًا
    if shutil.which("pwsh"):
        profiles.append(Profile("PowerShell 7", "pwsh.exe -NoLogo"))

    # موجّه الأوامر
    profiles.append(Profile("Command Prompt", "cmd.exe"))

    # Git Bash — المسار القصير (8.3) لأنّ winpty لا يتعامل مع الفراغ في المسار.
    # ⚠️ نُفضّل bash الحقيقيّ في usr\bin: أمّا bin\bash.exe فهو غلافٌ (launcher)
    # يُعيد إطلاق الصدفة بطريقةٍ تفصلها عن أنبوب ConPTY، فلا يظهر موجِّه ولا يصل
    # أيّ إدخال («لا أستطيع الكتابة إطلاقًا»). usr\bin\bash.exe يعمل تفاعليًّا مباشرةً.
    for p in (r"C:\Program Files\Git\usr\bin\bash.exe",
              r"C:\Program Files (x86)\Git\usr\bin\bash.exe",
              r"C:\Program Files\Git\bin\bash.exe",           # غلاف — بديلٌ أخير فقط
              r"C:\Program Files (x86)\Git\bin\bash.exe"):
        if os.path.exists(p):
            profiles.append(Profile("Git Bash", f'{_short_path(p)} --login -i'))
            break

    # توزيعات WSL (ناتج wsl يأتي بترميز UTF-16LE)
    try:
        out = subprocess.run(
            ["wsl.exe", "-l", "-q"],
            capture_output=True, timeout=5,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        text = out.stdout.decode("utf-16-le", errors="ignore")
        for line in text.splitlines():
            distro = line.strip().strip("\x00").strip()
            if distro:
                profiles.append(Profile(f"WSL · {distro}", f"wsl.exe -d {distro}", source="wsl"))
    except Exception:
        pass

    return profiles


def merge_user_profiles(detected, user_profiles):
    """يدمج ملفّات المستخدم المخصّصة (من config) مع المكتشَفة."""
    out = list(detected)
    for up in (user_profiles or []):
        try:
            out.append(Profile(up["name"], up["command"], source="user"))
        except (KeyError, TypeError):
            continue
    return out
