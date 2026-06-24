# ════════════════════════════════════════════════════════════
#  إضافات EasyTer (Python) — يُحمَّل عند الإقلاع
#  الواجهة:  import easyter as et
# ════════════════════════════════════════════════════════════
import easyter as et


# ── ثيم مخصّص ─────────────────────────────────────────────────
et.add_theme("ليليّ دافئ", "#11161c", "#d8c9a8")


# ── اختصارات مخصّصة ──────────────────────────────────────────
@et.keybind("Ctrl+Alt+G")          # git status في القسم الحاليّ
def _(pane):
    pane.send("git status\r")


@et.keybind("Ctrl+Alt+L")          # مسح الشاشة
def _(pane):
    pane.send("cls\r")


# ── أوامر (لوحة الأوامر: Ctrl+Shift+P) ──────────────────────
@et.command("تبويب جديد على المنزل")
def _(win):
    p = win.new_tab(shell="powershell.exe", name="المنزل")
    p.send("cd ~\r")


@et.command("افتح الرواية (إلينتور)")
def _(win):
    p = win.new_tab(shell="powershell.exe", name="الرواية")
    p.send('cd "D:\\الكتابة\\رواية إلينتور"\r')


@et.command("بدّل ثيم المِحَثّ (Oh My Posh)")
def _(win):
    import os, glob, re
    from PySide6.QtWidgets import QInputDialog
    d = os.path.join(os.path.expanduser("~"), ".poshthemes")
    themes = sorted(os.path.splitext(os.path.basename(p))[0]
                    for p in glob.glob(os.path.join(d, "*.omp.json")))
    if not themes:
        return
    name, ok = QInputDialog.getItem(win, "ثيم المِحَثّ", "اختر ثيماً:", themes, 0, False)
    if not ok or not name:
        return
    cfg = os.path.join(d, name + ".omp.json")
    # تبديل حيّ في القسم الحاليّ
    pane = win.active_pane()
    if pane is not None and hasattr(pane, "send"):
        pane.send(f'oh-my-posh init pwsh --config "{cfg}" | Invoke-Expression\r')
    # حفظ دائم في ملفّ PowerShell
    profile = os.path.join(os.path.expanduser("~"), "Documents",
                           "WindowsPowerShell", "Microsoft.PowerShell_profile.ps1")
    try:
        txt = open(profile, encoding="utf-8-sig").read()
        txt = re.sub(r'(oh-my-posh init pwsh --config ")[^"]*(")',
                     lambda m: m.group(1) + cfg + m.group(2), txt)
        open(profile, "w", encoding="utf-8").write(txt)
    except Exception as ex:
        print("[theme switch]", ex)


# ── الويب (مستوحى من firecrawl-web في h4ni0/pi) ──────────────
@et.command("بحث في الويب")
def _(win):
    import webbrowser
    import urllib.parse
    from PySide6.QtWidgets import QInputDialog
    q, ok = QInputDialog.getText(win, "بحث في الويب", "الاستعلام:")
    if ok and q.strip():
        webbrowser.open("https://duckduckgo.com/?q=" + urllib.parse.quote(q.strip()))


@et.command("اجلب صفحة نصّاً (في محرّر)")
def _(win):
    import urllib.request
    import re
    import html as _html
    from PySide6.QtWidgets import QInputDialog
    url, ok = QInputDialog.getText(win, "اجلب صفحة", "الرابط (URL):")
    if not ok or not url.strip():
        return
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        raw = urllib.request.urlopen(req, timeout=20).read().decode("utf-8", "replace")
        raw = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", raw)
        text = re.sub(r"(?s)<[^>]+>", " ", raw)
        text = _html.unescape(text)
        text = "\n".join(ln.strip() for ln in text.splitlines() if ln.strip())
    except Exception as ex:
        text = f"تعذّر جلب الصفحة:\n{ex}"
    win.open_text_editor(text[:200000], url)


# ── خطّافات أحداث ─────────────────────────────────────────────
@et.on("claude_detected")          # عند دخول كلود، سمِّ التبويب
def _(pane):
    pane.set_title("🤖 كلود")


# ── عنصر في شريط الحالة (الساعة) ────────────────────────────
@et.status_segment()
def _():
    import time
    return "🕐 " + time.strftime("%H:%M")


# ── تخصيص شكل الواجهة (للمحترفين) عبر Qt QSS ────────────────
#   الواجهة كاملةً (تبويبات/حدود/قوائم/أشرطة تمرير) تُشتقّ تلقائيّاً من ثيمك.
#   لتعديل الشكل نفسه، فعّل أحد المثالين:
#
#   (أ) نصّ QSS ثابت يُطبَّق فوق نمط الثيم:
# et.set_ui_style("QTabBar::tab{border-radius:0;padding:8px 22px;}")
#
#   (ب) دالّة تستلم ألوان الثيم المشتقّة وتُرجع QSS (الأقوى):
# @et.ui_style
# def _(c):                       # c فيه: bg fg chrome chrome2 border dim accent hover
#     return (
#         f"QTabBar::tab{{border-radius:0;padding:8px 22px;}}"
#         f"QTabBar::tab:selected{{border-bottom:3px solid {c['accent']};"
#         f"font-weight:bold;}}"
#         f"QSplitter::handle{{background:{c['accent']};}}"
#     )
#
#   بعد تغيير النمط حيّاً نادِ:  et.restyle()
