# -*- coding: utf-8 -*-
"""إضافة عيّنة: إجراء لوحة أوامر يكتب الطابع الزمنيّ في اللوح النشط.

تُبيّن قدرة ‎add_palette_action‎ + ‎write_to_active‎."""

import datetime


def _insert_timestamp(api):
    stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    api.write_to_active(stamp)


def register(api):
    # نمرّر api إلى ردّ النداء عبر إغلاق (closure) ليصل إلى اللوح النشط وقت التشغيل.
    api.add_palette_action("إدراج الطابع الزمنيّ", lambda: _insert_timestamp(api))
