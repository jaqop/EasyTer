# -*- coding: utf-8 -*-
"""إضافة عيّنة: تسجّل ثيمًا إضافيًّا يظهر في معرض المظاهر ولوحة الأوامر.

تُبيّن قدرة ‎add_theme‎. المواصفة: ‎{bg, fg, ansi{...}}‎ (١٦ لون ANSI اختياريّة)."""

_THEME = {
    "bg": "#12141c", "fg": "#c8d0e0",
    "ansi": {
        "black": "#12141c", "red": "#ff6188", "green": "#a9dc76", "yellow": "#ffd866",
        "blue": "#78dce8", "magenta": "#ab9df2", "cyan": "#78dce8", "white": "#c8d0e0",
        "brightblack": "#5b6268", "brightred": "#ff6188", "brightgreen": "#a9dc76",
        "brightyellow": "#ffd866", "brightblue": "#78dce8", "brightmagenta": "#ab9df2",
        "brightcyan": "#78dce8", "brightwhite": "#ffffff",
    },
}


def register(api):
    api.add_theme("عيّنة الإضافة — Plugin Demo", _THEME)
