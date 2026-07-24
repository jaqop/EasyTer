# -*- coding: utf-8 -*-
"""إضافة عيّنة: تُرسم شارة صغيرة غير مزعجة في زاوية اللوح النشط.

تُبيّن قدرة ‎add_paint_hook‎. الخطّاف يتلقّى ‎(painter, widget)‎ حيث ‎painter‎ فرشاة
Qt نشطة (لا تستدعِ ‎end()‎) و‎widget‎ هو TerminalWidget. تقرأ العدّاد من
‎sample_activity‎. خطّاف الرسم يُعطَّل تلقائيًّا إن رمى استثناءً (حمايةً للإطارات)."""

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor, QFont

from . import sample_activity


def _paint_badge(painter, widget):
    # على اللوح النشط فقط، حتّى لا تتكرّر الشارة عبر الألواح المقسَّمة.
    if not getattr(widget, "active", False):
        return
    label = f"◈ {sample_activity.OUTPUT_CHUNKS}"
    painter.save()
    try:
        painter.setFont(QFont("Consolas", 8))
        w, h = 66, 18
        x = 6
        y = widget.height() - h - 6
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(0, 0, 0, 120))
        painter.drawRoundedRect(QRectF(x, y, w, h), 5, 5)
        painter.setPen(QColor(200, 220, 255, 200))
        painter.drawText(QRectF(x, y, w, h), Qt.AlignCenter, label)
    finally:
        painter.restore()


def register(api):
    api.add_paint_hook(_paint_badge)
