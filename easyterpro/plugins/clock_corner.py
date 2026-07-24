# -*- coding: utf-8 -*-
"""إضافة: ساعة رقميّة في زاوية اللوح النشط (أعلى اليمين).

خطّاف رسم يكتب الوقت ‎HH:MM:SS‎، ومؤقّت ‎QTimer‎ كلّ ثانية يُحدّث اللوح النشط فيُعاد
رسمه فتتحرّك الساعة (وإلّا لم يُعَد الرسم إلّا مع الخرج/وميض المؤشّر). تُرسَم على
اللوح النشط فقط كي لا تتكرّر عبر الألواح المقسَّمة، وفي أعلى اليمين كي لا تصطدم بشارة
‎sample_overlay‎ (أسفل اليسار).

استيراد Qt كسول داخل الدوالّ حتّى يبقى ‎format_time‎ قابلًا للاختبار دون واجهة."""

import datetime


def format_time(dt):
    """ينسّق الوقت ‎HH:MM:SS‎ بأربع وعشرين ساعة، بأصفارٍ سابقة. دالّة نقيّة."""
    return dt.strftime("%H:%M:%S")


def _now_text():
    return format_time(datetime.datetime.now())


def _paint_clock(painter, widget):
    # على اللوح النشط فقط (كي لا تتكرّر عبر الألواح المقسَّمة).
    if not getattr(widget, "active", False):
        return
    from PySide6.QtCore import Qt, QRectF
    from PySide6.QtGui import QColor, QFont
    label = _now_text()
    painter.save()
    try:
        painter.setFont(QFont("Consolas", 9))
        w, h = 66, 18
        x = widget.width() - w - 8          # أعلى اليمين
        y = 6
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(0, 0, 0, 120))
        painter.drawRoundedRect(QRectF(x, y, w, h), 5, 5)
        painter.setPen(QColor(210, 214, 224, 210))
        painter.drawText(QRectF(x, y, w, h), Qt.AlignCenter, label)
    finally:
        painter.restore()


def register(api):
    api.add_paint_hook(_paint_clock)
    win = api.window
    if win is None or not hasattr(win, "_active_container"):
        return  # لا نافذة (مثلًا أثناء الاختبار) → الخطّاف مسجَّل بلا مؤقّت

    from PySide6.QtCore import QTimer

    def _tick():
        # يُحدّث اللوح النشط في التبويب الحاليّ ليعاد رسمه فتتقدّم الساعة.
        try:
            c = win._active_container()
            if c is None:
                return
            pane = getattr(c, "active_pane", None)
            if pane is None and hasattr(c, "_first_pane"):
                pane = c._first_pane()
            if pane is not None:
                pane.update()
        except Exception:
            pass

    timer = QTimer(win)
    timer.setInterval(1000)
    timer.timeout.connect(_tick)
    timer.start()
    win._clock_timer = timer            # مرجع حيّ حتّى لا يُجمَع المؤقّت
