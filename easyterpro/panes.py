# -*- coding: utf-8 -*-
"""SplitContainer — شجرة QSplitter من الألواح داخل تبويب واحد.

الجذر دائمًا QSplitter (حتّى للوح واحد) ليكون والد كلّ لوح من نوعٍ موحَّد،
فيبسط منطق التقسيم والإغلاق. التقسيم يلفّ اللوح النشط داخل splitter جديد.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QWidget, QVBoxLayout, QSplitter

from .terminal import TerminalWidget


class SplitContainer(QWidget):

    last_pane_closed = Signal(object)   # يُطلَق حين يُغلَق آخر لوح (لإغلاق التبويب)

    def __init__(self, command="powershell.exe"):
        super().__init__()
        self._command = command
        self.active_pane = None

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.root = QSplitter(Qt.Horizontal)
        self.root.setHandleWidth(3)
        lay.addWidget(self.root)

        pane = self._new_pane()
        self.root.addWidget(pane)
        pane.setFocus()

    # ---------- إنشاء لوح ----------
    def _new_pane(self):
        pane = TerminalWidget(command=self._command)
        pane.focused.connect(self._on_pane_focused)
        pane.backend.exited.connect(lambda p=pane: self._remove_pane(p))
        return pane

    def _on_pane_focused(self, pane):
        if self.active_pane is pane:
            return
        if self.active_pane is not None:
            self.active_pane.active = False
            self.active_pane.update()
        self.active_pane = pane
        pane.active = True
        pane.update()

    # ---------- تقسيم ----------
    def split(self, orientation):
        pane = self.active_pane or self._first_pane()
        if pane is None:
            return
        parent = pane.parentWidget()
        if not isinstance(parent, QSplitter):
            return
        idx = parent.indexOf(pane)
        sizes = parent.sizes()

        new_split = QSplitter(orientation)
        new_split.setHandleWidth(3)
        parent.insertWidget(idx, new_split)   # ضع splitter جديد في مكان اللوح
        new_split.addWidget(pane)             # ينقل اللوح إلى الـsplitter الجديد
        new_pane = self._new_pane()
        new_split.addWidget(new_pane)
        new_split.setSizes([10000, 10000])
        if sizes:
            parent.setSizes(sizes)
        new_pane.setFocus()

    def split_right(self):
        self.split(Qt.Horizontal)

    def split_down(self):
        self.split(Qt.Vertical)

    # ---------- إغلاق ----------
    def close_active_pane(self):
        if self.active_pane is not None:
            self._remove_pane(self.active_pane)

    def _remove_pane(self, pane):
        if pane is None:
            return
        try:
            pane.backend.close()
        except Exception:
            pass
        if pane is self.active_pane:
            self.active_pane = None
        pane.setParent(None)
        pane.deleteLater()

        remaining = self._all_panes()
        if not remaining:
            self.last_pane_closed.emit(self)
        else:
            remaining[0].setFocus()

    # ---------- استعلام ----------
    def _all_panes(self):
        out = []

        def walk(node):
            if isinstance(node, TerminalWidget):
                out.append(node)
            elif isinstance(node, QSplitter):
                for i in range(node.count()):
                    walk(node.widget(i))

        walk(self.root)
        return out

    def _first_pane(self):
        ps = self._all_panes()
        return ps[0] if ps else None

    def focus_next(self, step=1):
        panes = self._all_panes()
        if not panes:
            return
        cur = self.active_pane or panes[0]
        try:
            i = panes.index(cur)
        except ValueError:
            i = 0
        panes[(i + step) % len(panes)].setFocus()

    def close_all(self):
        for p in self._all_panes():
            try:
                p.backend.close()
            except Exception:
                pass
