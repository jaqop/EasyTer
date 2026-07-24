# -*- coding: utf-8 -*-
"""إضافة عيّنة: تُحصي دفقات الخرج من الطرفيّة.

تُبيّن قدرة ‎on_output‎. تحفظ العدّاد في متغيّر وحدة يقرأه ‎sample_overlay‎ ليرسمه —
مثالٌ على تعاون إضافتين. المستمع يُنادى على الخيط الرئيسيّ لكلّ دفقة خرج."""

# حالة مشتركة يقرأها sample_overlay (يبقى ٠ إن عُطّلت هذه الإضافة).
OUTPUT_CHUNKS = 0


def _on_output(text):
    global OUTPUT_CHUNKS
    OUTPUT_CHUNKS += 1


def register(api):
    api.on_output(_on_output)
