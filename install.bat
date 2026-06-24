@echo off
REM Install EasyTer's dependencies. Works from any folder: it switches to
REM its own directory first, so double-clicking it always finds requirements.txt.
cd /d "%~dp0"
echo Installing EasyTer dependencies...
echo.
python -m pip install -r requirements.txt
echo.
if errorlevel 1 (
  echo.
  echo Install failed. Make sure Python 3 is installed and on PATH, then retry.
) else (
  echo Done. Run EasyTer with run.bat or by double-clicking EasyTer.vbs.
)
echo.
pause
