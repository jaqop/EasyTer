# -*- coding: utf-8 -*-
"""معرض المظاهر — اختر ثيمًا بصريًّا من بطاقات معاينة، فيُطبَّق فورًا على كلّ الألواح."""

from PySide6.QtCore import Qt, Signal, QRectF
from PySide6.QtGui import QColor, QPainter, QFont, QPen, QBrush
from PySide6.QtWidgets import (
    QDialog, QWidget, QGridLayout, QVBoxLayout, QHBoxLayout, QScrollArea,
    QLabel, QPushButton, QCheckBox, QLineEdit, QComboBox,
)

from . import render
from . import posh
from .config import config

# الألوان الثمانية المعروضة كمربّعات معاينة أسفل كلّ بطاقة
SWATCHES = ["red", "green", "yellow", "blue", "magenta", "cyan", "brightblue", "brightmagenta"]


class ThemeCard(QWidget):
    """بطاقة معاينة لثيمٍ واحد: خلفيّته، اسمه، سطر موجِّه ملوّن، سطر عربيّ، وصفّ ألوان."""

    chosen = Signal(str)

    def __init__(self, name, theme, current=False):
        super().__init__()
        self.name = name
        self.theme = theme
        self.current = current
        self.setFixedSize(216, 134)
        self.setCursor(Qt.PointingHandCursor)

    def set_current(self, c):
        self.current = c
        self.update()

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.chosen.emit(self.name)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        bg = QColor(self.theme["bg"])
        fg = QColor(self.theme["fg"])
        ansi = self.theme["ansi"]

        rect = QRectF(2, 2, self.width() - 4, self.height() - 4)
        p.setBrush(QBrush(bg))
        if self.current:
            p.setPen(QPen(QColor("#3b82f6"), 3))
        else:
            p.setPen(QPen(QColor(255, 255, 255, 45), 1))
        p.drawRoundedRect(rect, 10, 10)

        # اسم الثيم
        p.setPen(fg)
        p.setFont(QFont("Segoe UI", 10, QFont.Bold))
        p.drawText(QRectF(14, 9, self.width() - 28, 20), Qt.AlignLeft | Qt.AlignVCenter, self.name)
        if self.current:
            p.setPen(QColor("#3b82f6"))
            p.setFont(QFont("Segoe UI", 8, QFont.Bold))
            p.drawText(QRectF(0, 11, self.width() - 14, 16), Qt.AlignRight | Qt.AlignVCenter, "● الحاليّ")

        # سطر شبيه بالموجِّه بألوان ANSI
        p.setFont(QFont("Consolas", 9))
        x = 14
        y = 50
        for txt, col in (("admin", "green"), ("@", "brightblack"),
                         ("easyter ", "blue"), ("$ ", fg.name())):
            p.setPen(QColor(ansi.get(col, col)))
            p.drawText(x, y, txt)
            x += p.fontMetrics().horizontalAdvance(txt)
        p.setPen(QColor(ansi.get("yellow", fg.name())))
        p.drawText(x, y, "echo")

        # سطر عربيّ موصول (يُظهر دعم العربيّة + لون النصّ)
        p.setPen(fg)
        p.setFont(QFont("Consolas", 9))
        p.drawText(14, 72, "مرحبا بالعالم — Hello 123")

        # صفّ الألوان (٨ مربّعات)
        n = len(SWATCHES)
        sw = (self.width() - 28) / n
        sy = self.height() - 30
        p.setPen(Qt.NoPen)
        for i, key in enumerate(SWATCHES):
            p.setBrush(QBrush(QColor(ansi.get(key, "#888888"))))
            p.drawRoundedRect(QRectF(14 + i * sw, sy, sw - 4, 14), 3, 3)
        p.end()


class AppearanceGallery(QDialog):
    """نافذة غير حصريّة: شبكة بطاقات. النقر يطبّق الثيم فورًا ويبقيها مفتوحة للتجربة."""

    theme_chosen = Signal(str)

    def __init__(self, parent, current_name):
        super().__init__(parent)
        self.setWindowTitle("معرض المظاهر — EasyTer Pro")
        self.resize(820, 600)
        self._current = current_name
        # واجهة المعرض داكنة ثابتة (مقروءة مع كلّ الثيمات حتّى الفاتحة)؛
        # البطاقات وحدها تحتفظ بألوان ثيماتها.
        bg = "#1c1c1e"
        fg = "#e6edf3"
        self.setStyleSheet(f"QDialog{{background:{bg};}}")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        top = QHBoxLayout()
        top.setContentsMargins(16, 12, 16, 6)
        title = QLabel("اختر مظهرًا — يُطبَّق فورًا")
        title.setStyleSheet(f"color:{fg};font-size:15px;font-weight:bold;")
        top.addWidget(title)
        self._count_lbl = QLabel("")
        self._count_lbl.setStyleSheet(f"color:{fg};font-size:12px;")
        top.addWidget(self._count_lbl)
        top.addStretch(1)
        self.search = QLineEdit()
        self.search.setPlaceholderText("ابحث في +550 مظهرًا…")
        self.search.setFixedWidth(240)
        self.search.setStyleSheet(
            f"QLineEdit{{background:rgba(255,255,255,0.06);color:{fg};"
            "border:1px solid rgba(255,255,255,0.16);border-radius:7px;"
            "padding:6px 10px;font-size:13px;}")
        self.search.textChanged.connect(self._render_grid)
        top.addWidget(self.search)
        root.addLayout(top)

        root.addWidget(self._build_cursor_row(fg))
        root.addWidget(self._build_posh_row(fg))

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setStyleSheet("QScrollArea{border:none;}")
        self._holder = QWidget()
        self._grid = QGridLayout(self._holder)
        self._grid.setSpacing(16)
        self._grid.setContentsMargins(16, 4, 16, 16)
        self._grid.setAlignment(Qt.AlignTop)
        self._scroll.setWidget(self._holder)
        root.addWidget(self._scroll)

        self.cards = []
        self._render_grid("")

    def _render_grid(self, text=""):
        for c in self.cards:
            c.setParent(None)
            c.deleteLater()
        self.cards = []
        t = (text or "").strip().lower()
        names = [n for n in render.theme_names() if (not t or t in n.lower())]
        shown = names[:120]
        more = len(names) - len(shown)
        self._count_lbl.setText(
            f"{len(names)} مظهرًا" + (f"  ·  يُعرَض {len(shown)}، اكتب للتصفية" if more > 0 else ""))
        for i, name in enumerate(shown):
            card = ThemeCard(name, render.THEMES[name], current=(name == self._current))
            card.chosen.connect(self._on_chosen)
            self._grid.addWidget(card, i // 3, i % 3)
            self.cards.append(card)
        self._scroll.verticalScrollBar().setValue(0)

    def _on_chosen(self, name):
        self._current = name
        for c in self.cards:
            c.set_current(c.name == name)
        self.theme_chosen.emit(name)

    # ---------- شكل المؤشّر ----------
    def _build_cursor_row(self, fg):
        row = QWidget()
        lay = QHBoxLayout(row)
        lay.setContentsMargins(16, 0, 16, 8)
        lay.setSpacing(8)
        lbl = QLabel("المؤشّر:")
        lbl.setStyleSheet(f"color:{fg};font-size:13px;")
        lay.addWidget(lbl)
        css = ("QPushButton{background:rgba(255,255,255,0.06);color:%s;"
               "border:1px solid rgba(255,255,255,0.14);border-radius:6px;"
               "padding:5px 12px;font-size:13px;}"
               "QPushButton:hover{background:rgba(255,255,255,0.16);}"
               "QPushButton:checked{background:#3b82f6;color:#ffffff;border-color:#3b82f6;}") % fg
        self._cursor_btns = {}
        cur = config().get("cursor", "style", default="block")
        for key, txt in (("block", "▌ مربّع"), ("beam", "▎ عمود"), ("underline", "▁ تحته")):
            b = QPushButton(txt)
            b.setCheckable(True)
            b.setChecked(key == cur)
            b.setCursor(Qt.PointingHandCursor)
            b.setStyleSheet(css)
            b.clicked.connect(lambda _c=False, k=key: self._set_cursor_style(k))
            lay.addWidget(b)
            self._cursor_btns[key] = b
        blink = QCheckBox("وميض")
        blink.setChecked(bool(config().get("cursor", "blink", default=True)))
        blink.setStyleSheet(f"color:{fg};font-size:13px;")
        blink.toggled.connect(lambda v: config().set(bool(v), "cursor", "blink"))
        lay.addWidget(blink)
        lay.addStretch(1)
        return row

    def _set_cursor_style(self, key):
        for k, b in self._cursor_btns.items():
            b.setChecked(k == key)
        config().set(key, "cursor", "style")

    # ---------- موجِّه الصدفة (oh-my-posh) ----------
    def _build_posh_row(self, fg):
        row = QWidget()
        lay = QHBoxLayout(row)
        lay.setContentsMargins(16, 0, 16, 10)
        lay.setSpacing(8)
        lbl = QLabel("موجِّه الصدفة:")
        lbl.setStyleSheet(f"color:{fg};font-size:13px;")
        lay.addWidget(lbl)
        self._posh_combo = QComboBox()
        self._posh_combo.setStyleSheet(
            f"QComboBox{{background:rgba(255,255,255,0.06);color:{fg};"
            "border:1px solid rgba(255,255,255,0.16);border-radius:6px;"
            "padding:5px 10px;font-size:13px;min-width:170px;}"
            f"QComboBox QAbstractItemView{{background:#202020;color:{fg};"
            "selection-background-color:#3b82f6;outline:none;}")
        themes = posh.available()
        self._posh_combo.addItems(themes)
        cur = posh.current()
        if cur in themes:
            self._posh_combo.setCurrentText(cur)
        self._posh_combo.currentTextChanged.connect(self._set_posh_theme)
        lay.addWidget(self._posh_combo)
        self._posh_hint = QLabel("")
        self._posh_hint.setStyleSheet(f"color:{fg};font-size:12px;")
        lay.addWidget(self._posh_hint)
        lay.addStretch(1)
        return row

    def _set_posh_theme(self, name):
        if posh.set_theme(name):
            self._posh_hint.setText("✓ طبّق — افتح تبويبًا جديدًا لتراه")
        else:
            self._posh_hint.setText("تعذّر التحديث")
