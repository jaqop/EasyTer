# -*- coding: utf-8 -*-
"""منتقي شكل الموجِّه: معاينةٌ حيّة لكلّ شكل (مُرسَّمة فعلًا عبر oh-my-posh)، فيرى
المستخدم الأشكال المختلفة ويختار المفضّل لديه بنقرة. النقر يطبّقه في $PROFILE."""
import os
import re
import html as _html
import subprocess

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QWidget, QScrollArea, QFrame,
)

from . import posh

# أشكالٌ متمايزة منسّقة (الاسم، وصفٌ قصير) — تُعرَض إن وُجدت على القرص
STYLES = [
    ("kali", "مؤطّر — سطران بإطار أزرق (نمط Kali)"),
    ("paradox", "باورلاين — أسهم ملوّنة + فرع Git"),
    ("agnoster", "باورلاين كلاسيكيّ"),
    ("powerlevel10k_rainbow", "قوس قزح — ألوان غنيّة"),
    ("atomic", "حديث — أيقونات Nerd Font"),
    ("jandedobbeleer", "الرسميّ الغنيّ بالمعلومات"),
    ("robbyrussell", "بسيط — سهمٌ واحد"),
    ("pure", "نقيّ — أدنى تشتيت"),
    ("night-owl", "ليليّ هادئ"),
]

_SGR = re.compile(r"\x1b\[([0-9;]*)m")


def _ansi_to_html(text):
    """يحوّل مخرجات oh-my-posh (ألوان SGR ‏24-bit) إلى HTML ملوّن للعرض في QLabel."""
    out = []
    state = {"fg": None, "bg": None, "bold": False, "open": False}

    def closes():
        if state["open"]:
            out.append("</span>")
            state["open"] = False

    def opens():
        st = []
        if state["fg"]:
            st.append("color:" + state["fg"])
        if state["bg"]:
            st.append("background-color:" + state["bg"])
        if state["bold"]:
            st.append("font-weight:bold")
        out.append('<span style="%s">' % ";".join(st))
        state["open"] = True

    def emit(seg):
        if not seg:
            return
        if not state["open"]:
            opens()
        out.append(_html.escape(seg).replace("\n", "<br>").replace(" ", "&nbsp;"))

    pos = 0
    for m in _SGR.finditer(text):
        emit(text[pos:m.start()])
        pos = m.end()
        codes = [c for c in m.group(1).split(";") if c != ""] or ["0"]
        i = 0
        while i < len(codes):
            c = codes[i]
            if c == "0":
                state["fg"] = state["bg"] = None
                state["bold"] = False
            elif c == "1":
                state["bold"] = True
            elif c == "38" and i + 4 < len(codes) + 1 and codes[i + 1] == "2":
                state["fg"] = "rgb(%s,%s,%s)" % (codes[i + 2], codes[i + 3], codes[i + 4])
                i += 4
            elif c == "48" and i + 4 < len(codes) + 1 and codes[i + 1] == "2":
                state["bg"] = "rgb(%s,%s,%s)" % (codes[i + 2], codes[i + 3], codes[i + 4])
                i += 4
            i += 1
        closes()
    emit(text[pos:])
    closes()
    return "".join(out)


def _strip_noise(s):
    """يزيل تسلسلات غير-اللون (OSC العنوان، CSI غير m، الجرس) فلا تتسرّب للمعاينة."""
    s = re.sub(r"\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)", "", s)   # OSC منتهية
    s = re.sub(r"\x1b\][^\x07\x1b]*", "", s)                  # OSC غير منتهية
    s = re.sub(r"\x1b\[[0-9;?<>=!]*[@-ln-~]", "", s)          # CSI ما عدا SGR (…m)
    s = re.sub(r"\x1b[=>78]", "", s)
    return s.replace("\x07", "")


def render_preview(name):
    """يشغّل oh-my-posh لرسم الموجِّه فعلًا، ويرجع HTML للمعاينة (أو None)."""
    path = os.path.join(posh.THEMES_DIR, name + ".omp.json")
    if not os.path.exists(path):
        return None
    try:
        r = subprocess.run(
            ["oh-my-posh", "print", "primary", "--config", path, "--shell", "pwsh"],
            capture_output=True, text=True, encoding="utf-8", timeout=6,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception:
        return None
    if r.returncode != 0 or not r.stdout.strip():
        return None
    return _ansi_to_html(_strip_noise(r.stdout.rstrip("\n")))


class _StyleCard(QFrame):
    """بطاقة شكلٍ واحد: معاينته الحيّة + اسمه ووصفه. النقر يختاره."""

    chosen = Signal(str)

    def __init__(self, name, desc, preview_html, current, font):
        super().__init__()
        self.name = name
        self._desc = desc
        self.current = current
        self.setCursor(Qt.PointingHandCursor)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.setSpacing(6)
        prev = QLabel(preview_html or "(تعذّرت المعاينة — اختَر بالاسم)")
        prev.setTextFormat(Qt.RichText)
        prev.setFont(font)
        prev.setStyleSheet("color:#e6edf3;background:transparent;border:none;")
        prev.setTextInteractionFlags(Qt.NoTextInteraction)
        lay.addWidget(prev)
        self._meta = QLabel()
        self._meta.setTextInteractionFlags(Qt.NoTextInteraction)
        lay.addWidget(self._meta)
        self._apply_state()

    def _apply_state(self):
        self.setStyleSheet(
            "_StyleCard{background:#0d1117;border:2px solid %s;border-radius:8px;}"
            "_StyleCard:hover{border-color:#3b82f6;}"
            % ("#3b82f6" if self.current else "#2a2a30"))
        self._meta.setText(("●  " if self.current else "") + self.name + "  —  " + self._desc)
        self._meta.setStyleSheet(
            "color:%s;border:none;background:transparent;font-size:12px;"
            % ("#3b82f6" if self.current else "#8b949e"))

    def set_current(self, c):
        self.current = c
        self._apply_state()

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.chosen.emit(self.name)


class PromptPicker(QDialog):
    """نافذة اختيار شكل الموجِّه — بطاقاتٌ بمعاينةٍ حيّة. النقر يطبّق فورًا في $PROFILE."""

    applied = Signal(str)

    def __init__(self, parent=None, font=None):
        super().__init__(parent)
        self.setWindowTitle("اختر شكل الموجِّه — EasyTer Pro")
        self.resize(680, 580)
        self.setStyleSheet("QDialog{background:#1c1c1e;}")
        self._pending = None
        font = font or QFont("Cascadia Code NF", 12)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        title = QLabel("اختر شكل الموجِّه — انقر الشكل المفضّل لديك")
        title.setStyleSheet("color:#e6edf3;font-size:15px;font-weight:bold;padding:14px 16px 4px;")
        root.addWidget(title)
        self._hint = QLabel("انقر شكلًا لتختاره — يُطبَّق على التبويب الحاليّ عند إغلاق النافذة.")
        self._hint.setStyleSheet("color:#8b949e;font-size:12px;padding:0 16px 8px;")
        root.addWidget(self._hint)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea{border:none;}")
        holder = QWidget()
        col = QVBoxLayout(holder)
        col.setContentsMargins(16, 4, 16, 16)
        col.setSpacing(10)

        cur = posh.current()
        avail = set(posh.available())
        self._cards = []
        for name, desc in STYLES:
            if name not in avail:
                continue
            card = _StyleCard(name, desc, render_preview(name), name == cur, font)
            card.chosen.connect(self._on_chosen)
            col.addWidget(card)
            self._cards.append(card)
        col.addStretch(1)
        scroll.setWidget(holder)
        root.addWidget(scroll)

        if not self._cards:
            self._hint.setText("لا توجد ثيمات oh-my-posh على القرص — تأكّد من التثبيت.")

    def _on_chosen(self, name):
        if posh.set_theme(name):
            self._pending = name
            for c in self._cards:
                c.set_current(c.name == name)
            self._hint.setText("✓ مُختار «%s» — يُطبَّق على التبويب الحاليّ عند إغلاق النافذة." % name)
        else:
            self._hint.setText("تعذّر اختيار «%s»." % name)

    def closeEvent(self, e):
        # يُطبَّق على التبويب الحاليّ مرّةً واحدةً عند الإغلاق (لا عند كلّ نقرة)،
        # فلا يتراكم أمر التهيئة في الطرفيّة.
        if self._pending:
            self.applied.emit(self._pending)
        super().closeEvent(e)
