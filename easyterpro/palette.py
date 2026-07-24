# -*- coding: utf-8 -*-
"""لوحة الأوامر (Command Palette): Ctrl+Shift+P — ابحث وشغّل أيّ إجراء."""

from PySide6.QtCore import Qt, QEvent
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QLineEdit, QListWidget, QListWidgetItem,
)

from . import render


class CommandPalette(QDialog):
    """حوار بحث: حقل تصفية + قائمة نتائج. Enter يشغّل، ↑↓ تنقّل، Esc يُغلق."""

    def __init__(self, parent, actions):
        super().__init__(parent)
        self.actions = actions          # قائمة (نصّ, دالّة)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.resize(560, 400)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(1, 1, 1, 1)
        lay.setSpacing(0)
        self.search = QLineEdit()
        self.search.setPlaceholderText("اكتب لتصفية الأوامر…   (↑↓ تنقّل · Enter تشغيل · Esc إغلاق)")
        self.lst = QListWidget()
        lay.addWidget(self.search)
        lay.addWidget(self.lst)

        bg = render.BASE_BG.name()
        fg = render.BASE_FG.name()
        self.setStyleSheet(
            f"QDialog{{background:{bg};border:1px solid #3b82f6;}}"
            f"QLineEdit{{background:{bg};color:{fg};border:none;border-bottom:1px solid #3b82f6;"
            f"padding:10px;font-size:14px;}}"
            f"QListWidget{{background:{bg};color:{fg};border:none;font-size:13px;outline:none;}}"
            f"QListWidget::item{{padding:7px 12px;}}"
            f"QListWidget::item:selected{{background:#3b82f6;color:#ffffff;}}"
        )

        self.search.textChanged.connect(self._filter)
        self.lst.itemClicked.connect(lambda _it: self._run())
        self.search.installEventFilter(self)
        self._filter("")
        self.search.setFocus()

    def _filter(self, text):
        self.lst.clear()
        t = text.strip().lower()
        for label, cb in self.actions:
            if not t or t in label.lower():
                it = QListWidgetItem(label)
                it.setData(Qt.UserRole, cb)
                self.lst.addItem(it)
        if self.lst.count():
            self.lst.setCurrentRow(0)

    def _run(self):
        it = self.lst.currentItem()
        if it is None:
            return
        cb = it.data(Qt.UserRole)
        self.close()
        try:
            cb()
        except Exception:
            pass

    def eventFilter(self, obj, event):
        if obj is self.search and event.type() == QEvent.KeyPress:
            k = event.key()
            n = self.lst.count()
            if k == Qt.Key_Down and n:
                self.lst.setCurrentRow(min(self.lst.currentRow() + 1, n - 1))
                return True
            if k == Qt.Key_Up and n:
                self.lst.setCurrentRow(max(self.lst.currentRow() - 1, 0))
                return True
            if k in (Qt.Key_Return, Qt.Key_Enter):
                self._run()
                return True
            if k == Qt.Key_Escape:
                self.close()
                return True
        return super().eventFilter(obj, event)

    def event(self, e):
        # يُغلق عند النقر خارجه (فقدان تنشيط النافذة)
        if e.type() == QEvent.WindowDeactivate:
            self.close()
        return super().event(e)
