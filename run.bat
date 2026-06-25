@echo off
cd /d "%~dp0"
rem Launch under Python 3.13: the stable pywinpty 2.x line has no wheel for
rem Python 3.14, so 3.14 pulls pywinpty 3.x (a rewrite) and TUIs like Claude
rem Code freeze. pyw -3.13 keeps us on the tested 2.x stack with no console window.
pyw -3.13 EasyTer.py 2>nul || pythonw EasyTer.py
