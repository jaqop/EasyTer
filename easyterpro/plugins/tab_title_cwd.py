# -*- coding: utf-8 -*-
"""إضافة: عنوان التبويب يتبع المجلّد الحاليّ تلقائيًّا (يدعم الألواح المقسَّمة).

تعتمد على أنّ الصدفة (PowerShell + oh-my-posh هنا) تبثّ عنوان النافذة باسم
المجلّد عبر ‎OSC 0‎ (‎ESC]0;اسم_المجلّد BEL‎) ويتغيّر مع ‎cd‎. تلتقط هذه الإضافة
ذلك التسلسل وتنسخه إلى عنوان التبويب المالك.

**الألواح المقسَّمة:** تتّصل بكلّ لوح في التبويب (لا الأوّل فقط). عنوان التبويب
يتبع **اللوح النشط** (المركَّز) فلا يتنازع لوحان في مجلّدين مختلفين. الألواح
المستحدَثة بالتقسيم تُوصَل عبر ‎QApplication.focusChanged‎ (اللوح الجديد ينال
التركيز فور إنشائه)، وتبديل التركيز يُحدّث العنوان لمجلّد اللوح المركَّز.

تستعمل ‎api.window‎ (مَخرج الطوارئ) — مقبولٌ لإضافةٍ يكتبها المستخدم لنفسه.
إن لم تبثّ صدفتك ‎OSC 0‎ لا تفعل الإضافة شيئًا (فشل آمن).
"""

import re

# OSC 0 (عنوان+أيقونة) أو OSC 2 (عنوان)، منتهيان بـBEL أو ST. نتجاهل OSC 8 وغيره.
_TITLE_RE = re.compile(r"\x1b\][02];([^\x07\x1b]*)(?:\x07|\x1b\\)")


def extract_title(text):
    """يرجع آخر عنوان OSC 0/2 في الدفقة، أو None إن غاب أو كان فارغًا."""
    last = None
    for m in _TITLE_RE.finditer(text):
        last = m.group(1)
    return last or None


class _TabTitleTracker:
    """يربط كلّ لوح بمستمعٍ يحدّث عنوان تبويبه من عنوان OSC 0/2 للّوح النشط."""

    def __init__(self, window):
        self.win = window
        self._connected = set()     # id(pane) الموصولة (تفادي التكرار)
        self._pane_title = {}       # id(pane) -> آخر عنوان معروف للّوح
        self._pinned = set()        # id(container) لتبويبات أُعيدت تسميتها يدويًّا

    # ---- الوصل ----
    def attach_all(self):
        tabs = self.win.tabs
        for i in range(tabs.count()):
            self._attach_container(tabs.widget(i))

    def attach_current(self):
        self._attach_container(self.win.tabs.currentWidget())

    def _attach_container(self, container):
        """يوصل كلّ ألواح الحاوية (يدعم التقسيم)."""
        if container is None or not hasattr(container, "_all_panes"):
            return
        try:
            panes = container._all_panes()
        except Exception:
            return
        for pane in panes:
            self._connect_pane(pane)

    def _connect_pane(self, pane):
        if pane is None or id(pane) in self._connected:
            return
        backend = getattr(pane, "backend", None)
        if backend is None or not hasattr(backend, "output_text"):
            return
        self._connected.add(id(pane))
        backend.output_text.connect(lambda text, p=pane: self._on_output(p, text))

    # ---- الأحداث ----
    def _on_output(self, pane, text):
        title = extract_title(text)
        if not title:
            return
        self._pane_title[id(pane)] = title
        container = self._container_of(pane)
        if container is None:
            return
        if id(container) in self._pinned:
            return                          # تبويبٌ مُعاد تسميته يدويًّا → لا تلمسه
        # عنوان التبويب يتبع اللوح النشط فقط (إن وُجد لوحٌ نشطٌ مختلف تجاهل).
        active = getattr(container, "active_pane", None)
        if active is not None and active is not pane:
            return
        self._set_tab_title(container, title)

    def on_focus_changed(self, old, new):
        """يُنادى من QApplication.focusChanged: يوصل ألواح التقسيم المستحدَثة،
        ويُحوّل عنوان التبويب لمجلّد اللوح المركَّز حديثًا."""
        pane = self._pane_of(new)
        if pane is None:
            return
        container = self._container_of(pane)
        if container is None:
            return
        self._attach_container(container)   # التقط أيّ لوحٍ جديدٍ من تقسيم
        if id(container) in self._pinned:
            return                          # اسمٌ يدويّ مثبَّت → لا تبدّله بالتركيز
        title = self._pane_title.get(id(pane))
        if title:
            self._set_tab_title(container, title)

    # ---- إعادة التسمية اليدويّة ----
    def _apply_rename(self, container, text):
        """يضبط عنوان التبويب ويثبّته (pin). نصٌّ فارغ → يزيل التثبيت فيعود التتبّع."""
        text = (text or "").strip()
        idx = self.win.tabs.indexOf(container)
        if idx < 0:
            return
        if text:
            self.win.tabs.setTabText(idx, text)
            self._pinned.add(id(container))
        else:
            self._pinned.discard(id(container))

    def rename_current(self):
        """إجراء لوحة الأوامر: يسأل عن اسمٍ للتبويب الحاليّ ويثبّته."""
        tabs = self.win.tabs
        idx = tabs.currentIndex()
        if idx < 0:
            return
        container = tabs.currentWidget()
        from PySide6.QtWidgets import QInputDialog
        dlg = QInputDialog(self.win)
        dlg.setWindowTitle("إعادة تسمية التبويب")
        dlg.setLabelText("اسم التبويب (فارغ = عودة للتتبّع التلقائيّ):")
        dlg.setTextValue(tabs.tabText(idx))
        # QSS صريح: توريث ستايل النافذة الداكنة يجعل نصّ الحوار غير مقروء (gotcha موثَّق).
        try:
            from .. import render
            bg, fg = render.BASE_BG.name(), render.BASE_FG.name()
        except Exception:
            bg, fg = "#0d1117", "#e6edf3"
        dlg.setStyleSheet(
            f"QInputDialog,QLabel{{color:{fg};background:{bg};}}"
            f"QLineEdit{{color:{fg};background:{bg};border:1px solid #3b82f6;padding:5px;}}"
            f"QPushButton{{color:{fg};background:#21262d;border:1px solid #30363d;padding:5px 12px;}}"
        )
        if dlg.exec():
            self._apply_rename(container, dlg.textValue())

    # ---- مساعدات ----
    def _set_tab_title(self, container, title):
        idx = self.win.tabs.indexOf(container)
        if idx >= 0:
            self.win.tabs.setTabText(idx, title)

    def _pane_of(self, widget):
        """يصعد سلسلة الآباء حتّى يجد لوح طرفيّة (له backend.output_text)."""
        while widget is not None:
            b = getattr(widget, "backend", None)
            if b is not None and hasattr(b, "output_text"):
                return widget
            widget = widget.parentWidget() if hasattr(widget, "parentWidget") else None
        return None

    def _container_of(self, widget):
        """يصعد سلسلة الآباء حتّى يجد حاوية التقسيم (لها _all_panes)."""
        while widget is not None:
            if hasattr(widget, "_all_panes") and hasattr(widget, "active_pane"):
                return widget
            widget = widget.parentWidget() if hasattr(widget, "parentWidget") else None
        return None


def register(api):
    win = api.window
    if win is None or not hasattr(win, "tabs"):
        return  # لا نافذة (مثلًا أثناء الاختبار) → لا شيء
    tracker = _TabTitleTracker(win)
    tracker.attach_all()
    # إعادة تسمية يدويّة عبر لوحة الأوامر (Ctrl+Shift+P) — تثبّت التبويب.
    api.add_palette_action("إعادة تسمية التبويب…", tracker.rename_current)
    # التبويبات الجديدة تصير الحاليّة عند إنشائها → currentChanged يلتقطها.
    win.tabs.currentChanged.connect(lambda _i: tracker.attach_current())
    # تبديل التركيز + ألواح التقسيم المستحدَثة (اللوح الجديد ينال التركيز).
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance()
    if app is not None:
        app.focusChanged.connect(tracker.on_focus_changed)
    # مرجع حيّ حتّى لا يُجمَع المتتبِّع.
    api.window._tab_title_tracker = tracker
