@echo off
setlocal
cd /d "%~dp0"

echo ============================================================
echo   EasyTer  -  build a standalone EasyTer.exe
echo ============================================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
  echo   [!] Python was not found on PATH. Install it from
  echo       https://www.python.org/downloads/ and tick
  echo       "Add python.exe to PATH", then re-run build.bat.
  pause
  exit /b 1
)

echo   Installing build dependencies...
python -m pip install --upgrade PySide6-Essentials "pywinpty>=3.0.5" pyte wcwidth pyinstaller
if errorlevel 1 (
  echo.
  echo   [!] pip install failed - see the error above.
  pause
  exit /b 1
)

echo.
echo   Building dist\EasyTer.exe ...
python -m PyInstaller EasyTer.spec --noconfirm
if errorlevel 1 (
  echo.
  echo   [!] Build failed - see the error above.
  pause
  exit /b 1
)

echo.
echo   Done: dist\EasyTer.exe
echo.
pause
exit /b 0
