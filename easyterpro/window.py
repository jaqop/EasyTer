# -*- coding: utf-8 -*-
"""MainWindow — تبويبات (QTabWidget) فوق SplitContainer، مع اختصارات النافذة."""

import os

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QMainWindow, QTabWidget, QToolButton, QMenu, QWidget, QHBoxLayout

from . import render
from . import pluginhost
from .panes import SplitContainer
from .palette import CommandPalette
from .gallery import AppearanceGallery
from .config import config
from .profiles import detect_profiles, merge_user_profiles


class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("EasyTer Pro — طرفيّة عربيّة")
        self._apply_window_theme()

        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.setMovable(True)
        self.tabs.setDocumentMode(True)
        self.tabs.tabCloseRequested.connect(self._close_tab)
        self.setCentralWidget(self.tabs)

        self.config = config()
        self.config.changed.connect(self._apply_window_theme)
        self.profiles = merge_user_profiles(detect_profiles(),
                                            self.config.get("profiles", default=[]))
        self._install_new_tab_button()

        self._tab_seq = 0
        self._new_tab()
        self._install_shortcuts()
        self.resize(1100, 680)

    # ---------- زرّ «+» مع قائمة الصدفات ----------
    def _install_new_tab_button(self):
        btn = QToolButton()
        btn.setText("+")
        btn.setPopupMode(QToolButton.MenuButtonPopup)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setToolTip("تبويب جديد  ·  ▾ لاختيار الصدفة")
        btn.setStyleSheet(
            "QToolButton{color:#e6edf3;background:rgba(255,255,255,0.06);"
            "border:none;border-radius:5px;font-size:18px;font-weight:bold;"
            "padding:3px 8px;}"
            "QToolButton:hover{background:rgba(255,255,255,0.16);}"
            "QToolButton::menu-button{width:16px;border:none;}"
        )
        menu = QMenu(btn)
        menu.setStyleSheet("QMenu{font-size:13px;padding:4px;}")
        for i, prof in enumerate(self.profiles):
            sc_txt = f"\tCtrl+Shift+{i + 1}" if i < 9 else ""
            act = menu.addAction(f"{prof.name}{sc_txt}")
            act.triggered.connect(
                lambda checked=False, p=prof: self._new_tab(p.command, p.name))
        menu.addSeparator()
        a_pal = menu.addAction("لوحة الأوامر\tCtrl+Shift+P")
        a_pal.triggered.connect(lambda checked=False: self._open_palette())
        a_gal = menu.addAction("معرض المظاهر\tCtrl+Shift+M")
        a_gal.triggered.connect(lambda checked=False: self._open_gallery())
        a_prompt = menu.addAction("شكل الموجِّه…")
        a_prompt.triggered.connect(lambda checked=False: self._open_prompt_picker())
        a_set = menu.addAction("الإعدادات\tCtrl+,")
        a_set.triggered.connect(lambda checked=False: self._open_config())
        a_about = menu.addAction("حول EasyTer Pro")
        a_about.triggered.connect(lambda checked=False: self._about())
        btn.setMenu(menu)
        btn.clicked.connect(lambda: self._new_tab())

        # غلاف بهامش يمين حتّى لا يلتصق الزرّ بحافّة النافذة (كان يُقصّ)
        holder = QWidget()
        hl = QHBoxLayout(holder)
        hl.setContentsMargins(0, 2, 10, 2)
        hl.addWidget(btn)
        self.tabs.setCornerWidget(holder, Qt.TopRightCorner)

    def _open_prompt_picker(self):
        from PySide6.QtGui import QFont
        from .prompt_picker import PromptPicker
        fam = self.config.get("font", "family", default="Cascadia Code NF")
        dlg = PromptPicker(self, font=QFont(fam, 12))
        dlg.applied.connect(self._apply_prompt_live)
        dlg.exec()

    def _apply_prompt_live(self, name):
        """يطبّق الموجِّه على صدفة PowerShell النشطة فورًا (بلا فتح تبويب جديد)."""
        import os
        from . import posh
        label = self.tabs.tabText(self.tabs.currentIndex()).lower()
        if "powershell" not in label and "pwsh" not in label:
            return  # غير PowerShell → لا نحقن أمر pwsh في صدفةٍ أخرى
        cont = self.tabs.currentWidget()
        pane = cont._first_pane() if hasattr(cont, "_first_pane") else None
        if pane is None or not hasattr(pane, "backend"):
            return
        theme_path = os.path.join(posh.THEMES_DIR, name + ".omp.json")
        # 2>$null: إعادة تهيئة oh-my-posh حيًّا تُطلق أخطاء PSReadLine حميدة على
        # PowerShell 5.1 (Get-PSReadLineKeyHandler نَسَقيّ غير مدعوم) — نكتمها.
        pane.backend.write(
            'oh-my-posh init pwsh --config "%s" | Invoke-Expression 2>$null\r' % theme_path)

    def _default_command(self):
        name = self.config.get("default_profile", default="PowerShell")
        for p in self.profiles:
            if p.name == name:
                return p.command, p.name
        if self.profiles:
            return self.profiles[0].command, self.profiles[0].name
        return "powershell.exe -NoProfile", "PowerShell"

    # ---------- تبويبات ----------
    def _new_tab(self, command=None, label=None):
        self._tab_seq += 1
        if command is None:
            command, label = self._default_command()
        container = SplitContainer(command=command)
        container.last_pane_closed.connect(self._on_container_emptied)
        title = label or f"طرفيّة {self._tab_seq}"
        idx = self.tabs.addTab(container, title)
        self.tabs.setCurrentIndex(idx)
        fp = container._first_pane()
        if fp is not None:
            fp.setFocus()

    def _close_tab(self, index):
        w = self.tabs.widget(index)
        if isinstance(w, SplitContainer):
            w.close_all()
        self.tabs.removeTab(index)
        if self.tabs.count() == 0:
            self.close()

    def _on_container_emptied(self, container):
        idx = self.tabs.indexOf(container)
        if idx >= 0:
            self.tabs.removeTab(idx)
        if self.tabs.count() == 0:
            self.close()

    def _cycle_tab(self, d):
        n = self.tabs.count()
        if n:
            self.tabs.setCurrentIndex((self.tabs.currentIndex() + d) % n)

    # ---------- اللوح/التبويب الحاليّ ----------
    def _active_container(self):
        w = self.tabs.currentWidget()
        return w if isinstance(w, SplitContainer) else None

    def _split(self, orientation):
        c = self._active_container()
        if c:
            c.split(orientation)

    def _close_active_pane(self):
        c = self._active_container()
        if c:
            c.close_active_pane()

    def _focus_next(self, step):
        c = self._active_container()
        if c:
            c.focus_next(step)

    def _zoom(self, delta):
        c = self._active_container()
        if c and c.active_pane:
            c.active_pane.change_font(delta)

    # ---------- لوحة الأوامر ----------
    def _build_actions(self):
        acts = [("تبويب جديد", self._new_tab)]
        for p in self.profiles:
            acts.append((f"تبويب: {p.name}",
                         lambda checked=False, pr=p: self._new_tab(pr.command, pr.name)))
        acts += [
            ("تقسيم يمين", lambda: self._split(Qt.Horizontal)),
            ("تقسيم أسفل", lambda: self._split(Qt.Vertical)),
            ("إغلاق اللوح", self._close_active_pane),
            ("التبويب التالي", lambda: self._cycle_tab(1)),
            ("التبويب السابق", lambda: self._cycle_tab(-1)),
            ("تكبير الخطّ", lambda: self._zoom(1)),
            ("تصغير الخطّ", lambda: self._zoom(-1)),
        ]
        for tn in render.theme_names():
            acts.append((f"السمة: {tn}",
                         lambda checked=False, t=tn: self._set_theme_global(t)))
        acts += [
            ("معرض المظاهر", self._open_gallery),
            ("تبديل الاتّجاه (BiDi)", self._toggle_bidi_global),
            ("فتح ملفّ الإعدادات", self._open_config),
        ]
        # إجراءات الإضافات (تُقرأ وقت الفتح، فتظهر الإضافات المحمَّلة حيًّا)
        acts += list(pluginhost.registry.palette_actions)
        return acts

    def _open_palette(self):
        dlg = CommandPalette(self, self._build_actions())
        self._palette = dlg          # مرجع حتّى لا يُجمَع (غير حصريّ)
        geo = self.geometry()
        dlg.move(geo.x() + (geo.width() - dlg.width()) // 2, geo.y() + 90)
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()
        dlg.search.setFocus()

    def _open_gallery(self):
        dlg = AppearanceGallery(self, render.CURRENT_THEME)
        self._gallery = dlg          # مرجع حتّى لا يُجمَع (غير حصريّ)
        dlg.theme_chosen.connect(self._set_theme_global)
        geo = self.geometry()
        dlg.move(geo.x() + (geo.width() - dlg.width()) // 2, geo.y() + 60)
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()

    def _set_theme_global(self, name):
        render.apply_theme(name)
        self.config.set(name, "theme")

    def _toggle_bidi_global(self):
        self.config.set(not self.config.get("bidi", default=True), "bidi")

    def _open_config(self):
        try:
            os.startfile(self.config.path)
        except Exception:
            pass

    def _about(self):
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.about(
            self, "حول EasyTer Pro",
            "EasyTer Pro — طرفيّة عربيّة\n\n"
            "طرفية تعرض العربية موصولةً ومرتّبة عبر Qt/QTextLayout.\n"
            "تبويبات · ألواح · ٧ ثيمات · لوحة أوامر · روابط · صدفات تلقائية.\n\n"
            "Python + PySide6 + pyte + ConPTY")

    # ---------- اختصارات (مستوى النافذة، لا تُرسَل للصدفة) ----------
    def _install_shortcuts(self):
        def sc(seq, fn):
            s = QShortcut(QKeySequence(seq), self)
            s.setContext(Qt.WidgetWithChildrenShortcut)
            s.activated.connect(fn)
            return s

        sc("Ctrl+Shift+T", self._new_tab)
        sc("Ctrl+Shift+P", self._open_palette)
        sc("Ctrl+Shift+M", self._open_gallery)
        sc("Ctrl+,", self._open_config)
        for i, prof in enumerate(self.profiles[:9]):
            sc(f"Ctrl+Shift+{i + 1}", lambda p=prof: self._new_tab(p.command, p.name))
        sc("Ctrl+Shift+W", self._close_active_pane)
        sc("Ctrl+Tab", lambda: self._cycle_tab(1))
        sc("Ctrl+Shift+Tab", lambda: self._cycle_tab(-1))
        sc("Ctrl+Shift+D", lambda: self._split(Qt.Horizontal))
        sc("Ctrl+Shift+E", lambda: self._split(Qt.Vertical))
        sc("Ctrl+Shift+Right", lambda: self._focus_next(1))
        sc("Ctrl+Shift+Down", lambda: self._focus_next(1))
        sc("Ctrl+Shift+Left", lambda: self._focus_next(-1))
        sc("Ctrl+Shift+Up", lambda: self._focus_next(-1))
        sc("Ctrl+=", lambda: self._zoom(+1))
        sc("Ctrl++", lambda: self._zoom(+1))
        sc("Ctrl+-", lambda: self._zoom(-1))

    def _apply_window_theme(self):
        self.setStyleSheet(f"background:{render.BASE_BG.name()};")

    def closeEvent(self, event):
        for i in range(self.tabs.count()):
            w = self.tabs.widget(i)
            if isinstance(w, SplitContainer):
                w.close_all()
        super().closeEvent(event)
