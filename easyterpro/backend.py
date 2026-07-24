# -*- coding: utf-8 -*-
"""PtyBackend — جلسة ConPTY حيّة + محاكي شاشة pyte، واحدة لكلّ لوح."""

import threading

import pyte
from winpty import PtyProcess

from PySide6.QtCore import QObject, Signal


# بعض التطبيقات (vim) ترسل SGR بعلامةٍ خاصّة (مثل CSI > 4 ; 2 m = modifyOtherKeys)،
# فيمرّر pyte الوسيط 'private=True' إلى select_graphic_rendition التي لا تقبله →
# TypeError يَخنق المحلّل ويُسقِط الطرفيّة كلّها. نلفّ الدالّة لتتجاهل العلامة بأمان.
_pyte_orig_sgr = pyte.Screen.select_graphic_rendition
def _pyte_safe_sgr(self, *attrs, private=False, **kwargs):
    _pyte_orig_sgr(self, *attrs)
pyte.Screen.select_graphic_rendition = _pyte_safe_sgr


class PtyBackend(QObject):
    """جلسة ConPTY حيّة + محاكي شاشة pyte."""

    data_ready = Signal()
    exited = Signal()
    alt_screen_changed = Signal(bool)   # دخول/خروج الشاشة البديلة (TUI: Claude/vim)
    output_text = Signal(str)           # نصّ الخرج الخامّ لكلّ قراءة (لمستمعي الإضافات)

    def __init__(self, cols, rows, command="powershell.exe"):
        super().__init__()
        self.lock = threading.Lock()
        self.screen = pyte.HistoryScreen(cols, rows, history=5000, ratio=0.5)
        self.stream = pyte.Stream(self.screen)
        self._alive = True
        self.alt_screen = False     # هل يعمل تطبيق TUI ملء الشاشة الآن؟
        self._scan_tail = ""        # ذيل لالتقاط تسلسلٍ مقسومٍ بين قراءتين
        self.proc = PtyProcess.spawn(command, dimensions=(rows, cols))
        threading.Thread(target=self._reader, daemon=True).start()

    def _reader(self):
        try:
            while self._alive:
                data = self.proc.read(16384)
                if not data:
                    continue
                self._scan_alt(data)
                with self.lock:
                    try:
                        self.stream.feed(data)
                    except Exception:
                        # تسلسلٌ نادرٌ يَخنق pyte → أعِد بناء المحلّل ولا تُسقِط الطرفيّة
                        self.stream = pyte.Stream(self.screen)
                self.data_ready.emit()
                # إشارة منفصلة تحمل النصّ الخامّ لمستمعي الإضافات (تُنقَل إلى الخيط
                # الرئيسيّ عبر آليّة إشارات Qt، فلا تُنادى الإضافات من خيط القارئ).
                self.output_text.emit(data)
        except EOFError:
            pass
        except Exception:
            pass
        finally:
            self.exited.emit()

    def _scan_alt(self, data):
        """يرصد دخول/خروج الشاشة البديلة (?1049h/?1049l) لتفعيل المسار الشبكيّ."""
        try:
            buf = self._scan_tail + data
        except TypeError:
            return
        ih = buf.rfind("\x1b[?1049h")
        il = buf.rfind("\x1b[?1049l")
        new = self.alt_screen
        if ih >= 0 or il >= 0:
            new = ih > il
        self._scan_tail = buf[-8:]
        if new != self.alt_screen:
            self.alt_screen = new
            self.alt_screen_changed.emit(new)

    def write(self, text):
        if not self._alive:
            return
        try:
            self.proc.write(text)
        except Exception:
            pass

    def resize(self, cols, rows):
        with self.lock:
            try:
                self.screen.resize(rows, cols)
            except Exception:
                pass
        try:
            self.proc.setwinsize(rows, cols)
        except Exception:
            pass

    def close(self):
        self._alive = False
        try:
            self.proc.terminate(force=True)
        except Exception:
            pass
