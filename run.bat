@echo off
cd /d "%~dp0"
rem Launch with no console window. pywinpty 3.0.5 works on Python 3.10-3.14.
pythonw EasyTer.py
