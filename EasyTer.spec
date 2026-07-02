# -*- mode: python ; coding: utf-8 -*-
# PyInstaller build spec for EasyTer.
#
# Build:   python -m PyInstaller EasyTer.spec --noconfirm
# Output:  dist/EasyTer.exe   (single file, no console window)
#
# Notes:
# - fonts/ and icon.ico are bundled; EasyTer.py finds them via RESOURCE_DIR
#   (sys._MEIPASS when frozen).
# - Config/session/logs go to ~/.easyter when frozen (see EasyTer.py), so the
#   exe can live anywhere, including read-only locations.
# - collect_all('winpty') pulls in pywinpty's native bits (ConPTY backend).

from PyInstaller.utils.hooks import collect_all

winpty_datas, winpty_binaries, winpty_hidden = collect_all('winpty')

a = Analysis(
    ['EasyTer.py'],
    pathex=[],
    binaries=winpty_binaries,
    datas=[
        ('fonts', 'fonts'),
        ('icon.ico', '.'),
        ('examples', 'examples'),
    ] + winpty_datas,
    hiddenimports=winpty_hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        # PySide6 modules EasyTer never imports (QtCore/QtGui/QtWidgets only) —
        # excluding them keeps the exe smaller if the full PySide6 is installed.
        'PySide6.QtNetwork', 'PySide6.QtQml', 'PySide6.QtQuick',
        'PySide6.QtWebEngineCore', 'PySide6.QtWebEngineWidgets',
        'PySide6.QtMultimedia', 'PySide6.QtSql', 'PySide6.QtTest',
        'PySide6.QtPdf', 'PySide6.Qt3DCore',
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='EasyTer',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,           # GUI app: no console window
    icon='icon.ico',
)
