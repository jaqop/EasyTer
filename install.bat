@echo off
setlocal
cd /d "%~dp0"
set "HERE=%~dp0"

echo ============================================================
echo   EasyTer  -  setup
echo ============================================================
echo.
echo   This copy of EasyTer is located at:
echo       %HERE%
echo.

REM Warn if this looks like a system / temporary folder.
echo "%HERE%" | findstr /I /C:"\system32\" /C:"\Windows\" /C:"\Temp\" /C:"\Downloads\" /C:"\Program Files" >nul
if not errorlevel 1 (
  echo   [!] WARNING: this looks like a system or temporary folder.
  echo       Installing or running apps from here is not recommended
  echo       ^(permission problems, files may be cleaned up^).
  echo.
)

echo   Recommended: keep EasyTer in a simple folder, e.g.  C:\EasyTer
echo.
echo   What would you like to do?
echo.
echo     [Y]  Install here          ^(this folder^)
echo     [R]  Move to C:\EasyTer    ^(recommended^) then install there
echo     [N]  Cancel
echo.
set "CHOICE="
set /p CHOICE="Your choice (Y/R/N): "

if /I "%CHOICE%"=="R" goto relocate
if /I "%CHOICE%"=="Y" goto installhere
echo.
echo   Cancelled. Nothing was changed.
echo.
pause
exit /b 0

:relocate
set "DEST=C:\EasyTer"
echo.
echo   Copying EasyTer to %DEST% ...
robocopy "%HERE:~0,-1%" "%DEST%" /E /NFL /NDL /NJH /NJS /NC /NS >nul
if errorlevel 8 (
  echo.
  echo   Could not copy to %DEST% ^(it may need administrator rights^).
  echo   You can move the folder there manually, then run install.bat again.
  echo.
  pause
  exit /b 1
)
cd /d "%DEST%"
echo   Moved. ^(You can delete the old copy at %HERE% later.^)
echo.
goto doinstall

:installhere
echo.

:doinstall
echo   Installing dependencies...
echo.
python -m pip install -r requirements.txt
if errorlevel 1 (
  echo.
  echo   Install failed. Make sure Python 3 is installed and on PATH, then retry.
) else (
  echo.
  echo   Done. Run EasyTer from this folder: double-click EasyTer.vbs or run.bat.
)
echo.
pause
exit /b 0
