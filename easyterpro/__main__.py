# -*- coding: utf-8 -*-
"""نقطة تشغيل EasyTer Pro:  python -m easyterpro"""

import sys
import os

# pythonw.exe لا كونسول لها → sys.stdout/stderr = None. أيّ مكتبة تكتب إليها عند
# الإقلاع (تحذيرات/سجلّات) تُسقط التطبيق صامتًا. نوجّهها إلى العدم لتفادي ذلك.
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")

from PySide6.QtWidgets import QApplication

from . import render
from . import pluginhost
from .config import config
from .window import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("EasyTer Pro")
    cfg = config()
    render.register_custom_themes(cfg.get("custom_themes", default={}))
    render.apply_theme(cfg.get("theme", default="EasyTer Dark"))
    win = MainWindow()
    # تحميل الإضافات المرفقة بعد بناء النافذة (فتصل الواجهة إلى الطرفيّة النشطة).
    # معزول تمامًا: أيّ إضافة معطوبة تُسجَّل وتُتخطّى دون إسقاط التطبيق.
    pluginhost.load(win, disabled=cfg.get("plugins", "disabled", default=[]))
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
