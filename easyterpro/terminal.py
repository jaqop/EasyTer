# -*- coding: utf-8 -*-
"""TerminalWidget — لوح طرفيّة واحد (ورقة).

الرسم عبر QTextLayout لكلّ سطر: تشكيل عربيّ متّصل + ترتيب BiDi صحيح + ألوان.
منقول حرفيًّا من EasyTer الأصلي مع إضافتين صغيرتين: إشارة `focused` وإطار اللوح النشط.
"""

from PySide6.QtCore import Qt, QRect, QPointF, Signal, QTimer
from PySide6.QtGui import (
    QFont, QFontMetrics, QFontMetricsF, QPainter, QColor, QPen, QKeyEvent,
    QTextLayout, QTextCharFormat, QTextOption,
)
from PySide6.QtWidgets import QApplication, QWidget, QMenu, QScrollBar

from . import render
from . import pluginhost
from .backend import PtyBackend
from .config import config

import re
import webbrowser

try:
    from wcwidth import wcwidth as _char_width
except Exception:
    def _char_width(_c):
        return 1

ACTIVE_BORDER = QColor("#3b82f6")
URL_RE = re.compile(r"""https?://[^\s<>"'`)\]]+""")

# تنسيق ثابت داكن للقوائم — مقروء مهما كان ثيم الطرفية (حتّى الفاتح)
_MENU_QSS = (
    "QMenu{background:#202024;color:#e6edf3;border:1px solid #3a3a40;"
    "border-radius:8px;padding:5px;}"
    "QMenu::item{padding:6px 26px 6px 16px;border-radius:5px;}"
    "QMenu::item:selected{background:#3b82f6;color:#ffffff;}"
    "QMenu::item:disabled{color:#6e7681;}"
    "QMenu::separator{height:1px;background:#3a3a40;margin:5px 8px;}"
)


def _is_arabic_letter(ch):
    """هل المحرف حرفٌ عربيّ (يشمل أشكال العرض)؟"""
    if not ch:
        return False
    o = ord(ch)
    return (0x0600 <= o <= 0x06FF or 0x0750 <= o <= 0x077F
            or 0x08A0 <= o <= 0x08FF or 0xFB50 <= o <= 0xFDFF
            or 0xFE70 <= o <= 0xFEFF)


class TerminalWidget(QWidget):

    focused = Signal(object)   # يُطلَق عند تركيز هذا اللوح (لتتبّع اللوح النشط)

    def __init__(self, command="powershell.exe"):
        super().__init__()
        self.setFocusPolicy(Qt.StrongFocus)
        # نرسم كامل الخلفية بأنفسنا → نُخبر Qt بذلك لمنع آثار اللطخ عند تحريك النافذة
        self.setAttribute(Qt.WA_OpaquePaintEvent, True)
        # قبول إسقاط الملفّات (سحبٌ وإفلات): يُدرِج مسار الملفّ المُفلَت عند الموجِّه
        self.setAcceptDrops(True)

        self.active = False
        self.bidi = bool(config().get("bidi", default=True))
        self.cursor_style = config().get("cursor", "style", default="block")
        self.cursor_blink = bool(config().get("cursor", "blink", default=True))
        self._cursor_on = True
        self._blink_timer = QTimer(self)
        self._blink_timer.setInterval(530)
        self._blink_timer.timeout.connect(self._toggle_cursor_blink)
        self.font_size = int(config().get("font", "size", default=13))
        self._init_font()

        self.cols = 110
        self.rows = 32
        self.scroll_offset = 0

        # حالة تحديد النصّ بالفأرة (إحداثيّات مطلقة في كامل السجلّ)
        self.sel_anchor = None
        self.sel_point = None
        self._paint_start = 0

        self.setMouseTracking(True)

        # شريط تمرير عموديّ للتاريخ (scrollback)
        self._max_off = 0
        self.sbar = QScrollBar(Qt.Vertical, self)
        self.sbar.setCursor(Qt.ArrowCursor)
        self.sbar.valueChanged.connect(self._on_scrollbar)
        self.sbar.setStyleSheet(
            "QScrollBar:vertical{background:transparent;width:12px;margin:0;}"
            "QScrollBar::handle:vertical{background:rgba(255,255,255,0.25);"
            "border-radius:5px;min-height:24px;}"
            "QScrollBar::handle:vertical:hover{background:rgba(255,255,255,0.45);}"
            "QScrollBar::add-line,QScrollBar::sub-line{height:0;}"
            "QScrollBar::add-page,QScrollBar::sub-page{background:transparent;}"
        )

        self._alt_screen = False    # تطبيق TUI ملء الشاشة نشط → المسار الشبكيّ
        self._run_cache = {}        # ذاكرة تخطيطات المقاطع (المسار الشبكيّ)
        self.backend = PtyBackend(self.cols, self.rows, command=command)
        self.backend.data_ready.connect(self._on_data)
        self.backend.exited.connect(self._on_exit)
        self.backend.alt_screen_changed.connect(self._on_alt_screen)
        self.backend.output_text.connect(self._dispatch_plugin_output)
        self._exited = False

        config().changed.connect(self._on_config_changed)
        self.resize(int(self.cols * self.cw), self.rows * self.ch)
        self._apply_blink_timer()

    def _init_font(self):
        render.ensure_arabic_font()
        cfg = config()
        fam = cfg.get("font", "family", default="Consolas")
        afam = cfg.get("font", "arabic_family", default="Amiri")
        self.font = QFont()
        # اللاتيني/الكود ثابت العرض، والعربيّة تنتقل تلقائيًّا إلى الخطّ العربي
        self.font.setFamilies([fam, afam])
        self.font.setStyleHint(QFont.Monospace)
        self.font.setPointSize(self.font_size)
        # QFontMetricsF كسريّ: تقدّم المحرف الحقيقيّ قد يكون 9.6px لا 9. اقتطاعه
        # عددًا صحيحًا يجعل cols أكبر ممّا يتّسع فيفيض النصّ خارج يمين النافذة ويُقتطع.
        fm = QFontMetricsF(self.font)
        self.cw = max(1.0, fm.horizontalAdvance("M"))
        self.ch = max(1, int(round(fm.height())))

    def change_font(self, delta):
        self.font_size = max(8, min(36, self.font_size + delta))
        self._init_font()
        self._recompute_size()
        self.update()

    # ---------- إشارات المحرّك ----------
    def _on_data(self):
        # لا نُجبر القفز للأسفل: إن مرّر المستخدم للأعلى يبقى مكانه
        self._sync_scrollbar()
        self.update()

    def _dispatch_plugin_output(self, text):
        # يُنادى على الخيط الرئيسيّ (إشارة Qt). يوزّع خرج الطرفيّة على مستمعي
        # الإضافات بأمان — خطأ مستمعٍ لا يؤثّر في العرض ولا في البقيّة.
        if pluginhost.registry.output_listeners:
            pluginhost.safe_dispatch(pluginhost.registry.output_listeners, text)

    def _on_exit(self):
        self._exited = True
        self.update()

    def _on_alt_screen(self, on):
        # تطبيقات ملء الشاشة (Claude/vim) → المسار الشبكيّ: كلّ خليّة مثبّتة على
        # عمودها فلا تنجرف ولا تُقتطع، والعربيّة تُشكَّل متّصلةً داخل خلاياها.
        self._alt_screen = bool(on)
        self._run_cache.clear()
        self.update()

    def _on_config_changed(self):
        # تبديل الثيم/الإعدادات/BiDi/المؤشّر: أعِد القراءة وأعِد الرسم
        self.bidi = bool(config().get("bidi", default=True))
        self._run_cache.clear()   # الثيم/الخطّ تغيّر → أبطِل ذاكرة المقاطع
        self.cursor_style = config().get("cursor", "style", default="block")
        self.cursor_blink = bool(config().get("cursor", "blink", default=True))
        self._cursor_on = True
        self._apply_blink_timer()
        self.update()

    def _apply_blink_timer(self):
        if self.cursor_blink:
            self._blink_timer.start()
        else:
            self._blink_timer.stop()
            self._cursor_on = True

    def _toggle_cursor_blink(self):
        if self.hasFocus():
            self._cursor_on = not self._cursor_on
            self.update()
        elif not self._cursor_on:
            self._cursor_on = True
            self.update()

    # ---------- القياس ----------
    def resizeEvent(self, event):
        sbw = self.sbar.sizeHint().width() or 12
        self.sbar.setGeometry(self.width() - sbw, 0, sbw, self.height())
        self._recompute_size()
        super().resizeEvent(event)

    def _recompute_size(self):
        sbw = self.sbar.width() or 12
        cols = max(20, int((self.width() - sbw) / self.cw))
        rows = max(5, int(self.height() / self.ch))
        if cols != self.cols or rows != self.rows:
            self.cols, self.rows = cols, rows
            self.backend.resize(cols, rows)
            # بعد التحجيم: الْتصق بالقاع وأعِد مزامنة التمرير. لولاها يبقى
            # scroll_offset قديمًا فيقفز start فوق المحتوى الحيّ ⟸ «اختفاء النصّ».
            self.scroll_offset = 0
            self._sync_scrollbar()
            self.update()

    # ---------- الرسم ----------
    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(self.rect(), render.BASE_BG)
        p.setFont(self.font)
        self._row_layouts = {}
        self._url_spans = {}

        with self.backend.lock:
            screen = self.backend.screen
            history = list(screen.history.top)
            live = [screen.buffer[y] for y in range(screen.lines)]
            all_lines = history + live
            total = len(all_lines)
            start = max(0, total - self.rows - self.scroll_offset)
            self._paint_start = start
            visible = all_lines[start:start + self.rows]
            cur_x, cur_y = screen.cursor.x, screen.cursor.y
            cur_hidden = screen.cursor.hidden
            ncols = screen.columns

            sel = self._norm_sel()
            for yi, row in enumerate(visible):
                abs_line = start + yi
                sel_range = None
                if sel:
                    (lo_l, lo_c), (hi_l, hi_c) = sel
                    if lo_l <= abs_line <= hi_l:
                        c0 = lo_c if abs_line == lo_l else 0
                        c1 = hi_c if abs_line == hi_l else ncols
                        if c1 > c0:
                            sel_range = (c0, c1)
                if self._alt_screen:
                    self._draw_row_grid(p, yi, row, ncols, sel_range)
                else:
                    self._draw_row(p, yi, row, ncols, sel_range)

            # المؤشّر (في القاع فقط) — يحترم الشكل (مربّع/عمود/تحته) والوميض
            if (self.scroll_offset == 0 and not cur_hidden and self.hasFocus()
                    and (self._cursor_on or not self.cursor_blink)):
                cy = cur_y * self.ch
                cx = cur_x * self.cw
                lay = self._row_layouts.get(cur_y)
                if lay is not None:
                    try:
                        rx = lay[1].cursorToX(min(cur_x, ncols))
                        cx = rx[0] if isinstance(rx, (tuple, list)) else rx
                    except Exception:
                        pass
                cx = int(cx)
                ccol = QColor(230, 237, 243, 150)
                cwi = int(round(self.cw))
                if self.cursor_style == "beam":
                    p.fillRect(QRect(cx, cy, max(2, cwi // 6), self.ch), ccol)
                elif self.cursor_style == "underline":
                    uh = max(2, self.ch // 8)
                    p.fillRect(QRect(cx, cy + self.ch - uh, cwi, uh), ccol)
                else:
                    p.fillRect(QRect(cx, cy, cwi, self.ch), ccol)

        # إطار اللوح النشط (يساعد عند وجود عدّة ألواح)
        if self.active:
            pen = QPen(ACTIVE_BORDER)
            pen.setWidth(2)
            p.setPen(pen)
            p.drawRect(self.rect().adjusted(1, 1, -1, -1))

        # خطاطيف رسم الإضافات: تُنادى آخر كلّ إطار فوق كلّ ما رُسم، وتُعطَّل
        # تلقائيًّا عند الفشل حمايةً لمعدّل الإطارات.
        if pluginhost.registry.paint_hooks:
            pluginhost.safe_dispatch(pluginhost.registry.paint_hooks, p, self,
                                     auto_disable=True)
        p.end()

    def _draw_row(self, p, yi, row, ncols, sel_range=None):
        """يرسم السطر كلَّه كوحدة واحدة عبر QTextLayout: تشكيل عربيّ متّصل +
        ترتيب ثنائيّ الاتجاه (BiDi) صحيح + ألوان لكلّ مقطع + تظليل تحديد واعٍ بالـBiDi."""
        y = yi * self.ch
        if not self.bidi:
            self._draw_row_raw(p, yi, row, ncols, sel_range)
            return
        chars = []
        for col in range(ncols):
            ch = row[col]
            chars.append(ch.data if ch.data else " ")
        text = "".join(chars)
        if not text.strip():
            self._row_layouts[yi] = None
            if sel_range is not None:
                c0, c1 = sel_range
                p.fillRect(QRect(int(c0 * self.cw), y, int((c1 - c0) * self.cw), self.ch),
                           QColor(80, 140, 255, 90))
            return

        layout = QTextLayout(text, self.font)
        opt = QTextOption()
        opt.setWrapMode(QTextOption.NoWrap)
        layout.setTextOption(opt)

        # نمط كلّ خليّة → نطاقات تنسيق (لون/خلفيّة/عريض) يحفظها المحرّك عبر إعادة الترتيب
        formats = []
        col = 0
        while col < ncols:
            ch = row[col]
            style = (ch.fg, ch.bg, ch.bold, ch.reverse)
            start = col
            col += 1
            while col < ncols:
                c2 = row[col]
                if (c2.fg, c2.bg, c2.bold, c2.reverse) != style:
                    break
                col += 1
            fg = render.resolve_color(style[0], False)
            bg = render.resolve_color(style[1], True)
            if style[3]:
                fg, bg = bg, fg
            fmt = QTextCharFormat()
            fmt.setForeground(fg)
            if bg.rgb() != render.BASE_BG.rgb():
                fmt.setBackground(bg)
            if style[2]:
                fmt.setFontWeight(QFont.Bold)
            fr = QTextLayout.FormatRange()
            fr.start = start
            fr.length = col - start
            fr.format = fmt
            formats.append(fr)
        # روابط: تسطيرها وتخزين مواضعها (للنقر بـCtrl)
        spans = []
        for m in URL_RE.finditer(text):
            s, e = m.start(), m.end()
            spans.append((s, e, m.group(0)))
            ufmt = QTextCharFormat()
            ufmt.setFontUnderline(True)
            ur = QTextLayout.FormatRange()
            ur.start = s
            ur.length = e - s
            ur.format = ufmt
            formats.append(ur)
        self._url_spans[yi] = spans
        layout.setFormats(formats)

        layout.beginLayout()
        line = layout.createLine()
        line.setLineWidth(self.cols * self.cw)
        line.setPosition(QPointF(0, 0))
        layout.endLayout()
        selections = []
        if sel_range is not None:
            c0, c1 = sel_range
            sfr = QTextLayout.FormatRange()
            sfr.start = c0
            sfr.length = c1 - c0
            sfmt = QTextCharFormat()
            sfmt.setBackground(QColor(80, 140, 255, 120))
            sfr.format = sfmt
            selections = [sfr]
        layout.draw(p, QPointF(0, y), selections)
        self._row_layouts[yi] = (layout, line)

    def _draw_row_raw(self, p, yi, row, ncols, sel_range=None):
        """وضع توافق (BiDi مُطفأ): كلّ خليّة في موضعها بلا تشكيل ولا إعادة ترتيب،
        لتطبيقات ملء الشاشة التي تتولّى تخطيطها بنفسها (Claude Code / vim)."""
        y = yi * self.ch
        self._row_layouts[yi] = None
        self._url_spans[yi] = []
        for col in range(ncols):
            ch = row[col]
            data = ch.data if ch.data else " "
            fg = render.resolve_color(ch.fg, False)
            bg = render.resolve_color(ch.bg, True)
            if ch.reverse:
                fg, bg = bg, fg
            x0 = int(col * self.cw)
            rx = QRect(x0, y, int((col + 1) * self.cw) - x0, self.ch)
            if bg.rgb() != render.BASE_BG.rgb():
                p.fillRect(rx, bg)
            if data != " ":
                if ch.bold:
                    self.font.setBold(True)
                    p.setFont(self.font)
                p.setPen(fg)
                p.drawText(rx, Qt.AlignLeft | Qt.AlignVCenter, data)
                if ch.bold:
                    self.font.setBold(False)
                    p.setFont(self.font)
        if sel_range is not None:
            c0, c1 = sel_range
            p.fillRect(QRect(int(c0 * self.cw), y, int((c1 - c0) * self.cw), self.ch),
                       QColor(80, 140, 255, 90))

    # ===== المسار الشبكيّ (تطبيقات ملء الشاشة: Claude/vim) =====
    def _draw_row_grid(self, p, yi, row, ncols, sel_range=None):
        """تطبيقات ملء الشاشة (Claude/vim): غير-العربيّ يُرسَم خليّةً-بخليّة مثبّتًا على
        الشبكة (فنّ البكسل والإطارات لا ينجرف ولا يتشوّه)، ومقاطع العربيّة تُشكَّل
        متّصلةً RTL داخل خلاياها (بعد عكس البصريّ→منطقيّ)."""
        y = yi * self.ch
        self._row_layouts[yi] = None
        self._url_spans[yi] = []
        if sel_range is not None:
            c0, c1 = sel_range
            p.fillRect(QRect(int(c0 * self.cw), y, int((c1 - c0) * self.cw), self.ch),
                       QColor(80, 140, 255, 90))
        c = 0
        while c < ncols:
            cell = row[c]
            d = cell.data if cell.data else " "
            if _is_arabic_letter(d):
                # مقطع عربيّ متّصل بنفس النمط → عكسٌ وتشكيلٌ RTL داخل خلاياه
                style = (cell.fg, cell.bg, cell.bold, cell.reverse)
                chars = []
                start = c
                while (c < ncols and _is_arabic_letter(row[c].data or "")
                       and (row[c].fg, row[c].bg, row[c].bold, row[c].reverse) == style):
                    chars.append(row[c].data or " ")
                    c += 1
                text = "".join(chars)[::-1]   # بصريّ (كلود) → منطقيّ للتشكيل
                self._draw_run(p, start * self.cw, y,
                               (c - start) * self.cw, text, style, True)
            else:
                # خليّة غير عربيّة → مثبّتة على عمودها بالضبط (لا انجراف)
                wide = (_char_width(d) == 2 and c + 1 < ncols and not row[c + 1].data)
                span = 2 if wide else 1
                x0 = int(c * self.cw)
                x1 = int((c + span) * self.cw)
                fg = render.resolve_color(cell.fg, False)
                bg = render.resolve_color(cell.bg, True)
                if cell.reverse:
                    fg, bg = bg, fg
                if bg.rgb() != render.BASE_BG.rgb():
                    p.fillRect(QRect(x0, y, x1 - x0, self.ch), bg)
                if d != " ":
                    if cell.bold:
                        self.font.setBold(True)
                        p.setFont(self.font)
                    p.setPen(fg)
                    p.drawText(QRect(x0, y, x1 - x0, self.ch),
                               Qt.AlignLeft | Qt.AlignVCenter, d)
                    if cell.bold:
                        self.font.setBold(False)
                        p.setFont(self.font)
                c += span

    def _draw_run(self, p, x0, y, boxw, text, style, is_ar):
        """مقطعٌ واحد داخل صندوق خلاياه: عربيّ RTL محاذًى يمينًا (متّصل)، وغيره
        LTR يسارًا. التخطيطات مخزّنة في _run_cache."""
        fg = render.resolve_color(style[0], False)
        bg = render.resolve_color(style[1], True)
        if style[3]:
            fg, bg = bg, fg
        if bg.rgb() != render.BASE_BG.rgb():
            p.fillRect(QRect(int(x0), y, int(boxw), self.ch), bg)
        if not text.strip():
            return
        key = (text, style, is_ar)
        cached = self._run_cache.get(key)
        if cached is None:
            layout = QTextLayout(text, self.font)
            opt = QTextOption()
            opt.setWrapMode(QTextOption.NoWrap)
            opt.setTextDirection(Qt.RightToLeft if is_ar else Qt.LeftToRight)
            layout.setTextOption(opt)
            fmt = QTextCharFormat()
            fmt.setForeground(fg)
            if style[2]:
                fmt.setFontWeight(QFont.Bold)
            fr = QTextLayout.FormatRange()
            fr.start = 0
            fr.length = len(text)
            fr.format = fmt
            layout.setFormats([fr])
            layout.beginLayout()
            line = layout.createLine()
            line.setLineWidth(100000)
            line.setPosition(QPointF(0, 0))
            layout.endLayout()
            if len(self._run_cache) > 2000:
                self._run_cache.clear()
            cached = (layout, line)
            self._run_cache[key] = cached
        layout, line = cached
        natw = line.naturalTextWidth()
        dx = (x0 + boxw - natw) if is_ar else x0
        p.setPen(fg)
        layout.draw(p, QPointF(dx, y))

    # ---------- الإدخال ----------
    def keyPressEvent(self, event: QKeyEvent):
        if self._exited:
            return
        key = event.key()
        mod = event.modifiers()
        ctrl = bool(mod & Qt.ControlModifier)
        shift = bool(mod & Qt.ShiftModifier)

        # نسخ: Ctrl+Shift+C
        if ctrl and shift and key == Qt.Key_C:
            self._copy_selection()
            return

        # لصق: Ctrl+Shift+V
        if ctrl and shift and key == Qt.Key_V:
            self._paste_clipboard()
            return

        # تمرير العرض بالكيبورد: Shift+PageUp/PageDown
        if shift and key == Qt.Key_PageUp:
            self._scroll_view(self.rows - 1)
            return
        if shift and key == Qt.Key_PageDown:
            self._scroll_view(-(self.rows - 1))
            return

        self.scroll_offset = 0

        seq = None
        if key in (Qt.Key_Return, Qt.Key_Enter):
            seq = "\r"
        elif key == Qt.Key_Backspace:
            seq = "\x7f"
        elif key == Qt.Key_Tab:
            seq = "\t"
        elif key == Qt.Key_Escape:
            seq = "\x1b"
        elif key == Qt.Key_Up:
            seq = "\x1b[A"
        elif key == Qt.Key_Down:
            seq = "\x1b[B"
        elif key == Qt.Key_Right:
            seq = "\x1b[C"
        elif key == Qt.Key_Left:
            seq = "\x1b[D"
        elif key == Qt.Key_Home:
            seq = "\x1b[H"
        elif key == Qt.Key_End:
            seq = "\x1b[F"
        elif key == Qt.Key_PageUp:
            seq = "\x1b[5~"
        elif key == Qt.Key_PageDown:
            seq = "\x1b[6~"
        elif key == Qt.Key_Delete:
            seq = "\x1b[3~"
        elif ctrl and Qt.Key_A <= key <= Qt.Key_Z:
            seq = chr(key - Qt.Key_A + 1)  # Ctrl+C=\x03 ...
        else:
            t = event.text()
            if t:
                seq = t

        if seq:
            self.backend.write(seq)

    # ---------- تحديد النصّ بالفأرة ----------
    def _pos_to_cell(self, pos):
        yi = max(0, min(self.rows - 1, int(pos.y() // self.ch)))
        col = None
        lay = getattr(self, "_row_layouts", {}).get(yi)
        if lay is not None:
            try:
                col = lay[1].xToCursor(float(pos.x()))  # عمود منطقيّ دقيق رغم BiDi
            except Exception:
                col = None
        if col is None:
            col = round(pos.x() / self.cw)
        col = max(0, min(self.cols, col))
        abs_line = self._paint_start + yi
        return abs_line, col

    def _url_at(self, pos):
        yi = max(0, min(self.rows - 1, int(pos.y() // self.ch)))
        spans = getattr(self, "_url_spans", {}).get(yi)
        if not spans:
            return None
        lay = getattr(self, "_row_layouts", {}).get(yi)
        if lay is not None:
            try:
                col = int(lay[1].xToCursor(float(pos.x())))
            except Exception:
                col = round(pos.x() / self.cw)
        else:
            col = round(pos.x() / self.cw)
        for s, e, url in spans:
            if s <= col < e:
                return url
        return None

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            if event.modifiers() & Qt.ControlModifier:
                url = self._url_at(event.position())
                if url:
                    try:
                        webbrowser.open(url)
                    except Exception:
                        pass
                    return
            self.setFocus()
            self.sel_anchor = self._pos_to_cell(event.position())
            self.sel_point = self.sel_anchor
            self.update()

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton and self.sel_anchor is not None:
            self.sel_point = self._pos_to_cell(event.position())
            self.update()
        elif (event.modifiers() & Qt.ControlModifier) and self._url_at(event.position()):
            self.setCursor(Qt.PointingHandCursor)
        else:
            self.unsetCursor()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self._norm_sel():
            self._copy_selection()  # نسخ تلقائيّ عند رفع الفأرة

    def _norm_sel(self):
        if self.sel_anchor is None or self.sel_point is None:
            return None
        a, b = self.sel_anchor, self.sel_point
        if a == b:
            return None
        return (a, b) if a <= b else (b, a)

    def _selection_text(self):
        sel = self._norm_sel()
        if not sel:
            return ""
        (lo_l, lo_c), (hi_l, hi_c) = sel
        with self.backend.lock:
            screen = self.backend.screen
            history = list(screen.history.top)
            live = [screen.buffer[y] for y in range(screen.lines)]
            all_lines = history + live
            ncols = screen.columns
            out = []
            for L in range(lo_l, hi_l + 1):
                if L < 0 or L >= len(all_lines):
                    continue
                row = all_lines[L]
                c0 = lo_c if L == lo_l else 0
                c1 = hi_c if L == hi_l else ncols
                chars = []
                for col in range(c0, min(c1, ncols)):
                    ch = row[col]
                    chars.append(ch.data if ch.data else " ")
                out.append("".join(chars).rstrip())
        return "\n".join(out)

    def _copy_selection(self):
        txt = self._selection_text()
        if txt:
            QApplication.clipboard().setText(txt)

    def _paste_clipboard(self):
        txt = QApplication.clipboard().text()
        if txt:
            self.backend.write(txt.replace("\r\n", "\r").replace("\n", "\r"))

    # ---------- السحب والإفلات (إسقاط الملفّات) ----------
    def dragEnterEvent(self, event):
        # نقبل إسقاط الملفّات (URLs) أو نصًّا عاديًّا
        md = event.mimeData()
        if md.hasUrls() or md.hasText():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        md = event.mimeData()
        if md.hasUrls() or md.hasText():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        if self._exited:
            event.ignore()
            return
        md = event.mimeData()
        parts = []
        if md.hasUrls():
            for url in md.urls():
                if url.isLocalFile():
                    # على ويندوز نُعطي مسارًا بشرطات عكسيّة يفهمه الصدف
                    parts.append(url.toLocalFile().replace("/", "\\"))
                else:
                    parts.append(url.toString())
        elif md.hasText():
            parts.append(md.text())
        if not parts:
            event.ignore()
            return
        # اقتبس أيّ مسار فيه فراغ أو محرف خاصّ كي يصل سليمًا للصدف
        chunks = []
        for pth in parts:
            if any(ws in pth for ws in (" ", "\t")):
                pth = '"' + pth.replace('"', '\\"') + '"'
            chunks.append(pth)
        self.setFocus()
        self.scroll_offset = 0
        self.backend.write(" ".join(chunks))
        event.acceptProposedAction()

    def _select_all(self):
        with self.backend.lock:
            screen = self.backend.screen
            total = len(screen.history.top) + screen.lines
            ncols = screen.columns
        if total > 0:
            self.sel_anchor = (0, 0)
            self.sel_point = (total - 1, ncols)
            self.update()

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        menu.setStyleSheet(_MENU_QSS)
        act_copy = menu.addAction("نسخ\tCtrl+Shift+C")
        act_copy.setEnabled(self._norm_sel() is not None)
        act_paste = menu.addAction("لصق\tCtrl+Shift+V")
        menu.addSeparator()
        act_all = menu.addAction("تحديد الكل")
        menu.addSeparator()
        act_gallery = menu.addAction("معرض المظاهر…\tCtrl+Shift+M")
        theme_menu = menu.addMenu("سمة سريعة")
        theme_menu.setStyleSheet(_MENU_QSS)
        theme_acts = {}
        for tn in render.theme_names()[:13]:   # المدمجة فقط؛ الباقي (+500) في المعرض
            a = theme_menu.addAction(tn)
            a.setCheckable(True)
            a.setChecked(tn == render.CURRENT_THEME)
            theme_acts[a] = tn
        menu.addSeparator()
        act_bidi = menu.addAction("اتّجاه ثنائي (BiDi)")
        act_bidi.setCheckable(True)
        act_bidi.setChecked(self.bidi)
        chosen = menu.exec(event.globalPos())
        if chosen == act_copy:
            self._copy_selection()
        elif chosen == act_paste:
            self._paste_clipboard()
        elif chosen == act_all:
            self._select_all()
        elif chosen == act_gallery:
            w = self.window()
            if hasattr(w, "_open_gallery"):
                w._open_gallery()
        elif chosen in theme_acts:
            self._set_theme(theme_acts[chosen])
        elif chosen == act_bidi:
            config().set(not self.bidi, "bidi")   # يحفظ + يُطلق changed → كلّ الألواح

    def _set_theme(self, name):
        render.apply_theme(name)
        config().set(name, "theme")   # يحفظ + يُطلق changed → كلّ الألواح تُعاد رسمها

    def _sync_scrollbar(self):
        with self.backend.lock:
            self._max_off = len(self.backend.screen.history.top)
        self.scroll_offset = max(0, min(self.scroll_offset, self._max_off))
        self.sbar.blockSignals(True)
        self.sbar.setRange(0, self._max_off)
        self.sbar.setPageStep(max(1, self.rows))
        self.sbar.setValue(self._max_off - self.scroll_offset)
        self.sbar.blockSignals(False)

    def _on_scrollbar(self, value):
        self.scroll_offset = max(0, self._max_off - value)
        self.update()

    def _scroll_view(self, lines):
        self.scroll_offset = max(0, self.scroll_offset + lines)
        self._sync_scrollbar()
        self.update()

    def wheelEvent(self, event):
        steps = int(event.angleDelta().y() / 120) * 3
        self.scroll_offset = max(0, self.scroll_offset + steps)
        self._sync_scrollbar()
        self.update()

    def focusInEvent(self, event):
        self.focused.emit(self)
        self._cursor_on = True
        self.update()

    def focusOutEvent(self, event):
        self.update()

    def closeEvent(self, event):
        self.backend.close()
        super().closeEvent(event)
