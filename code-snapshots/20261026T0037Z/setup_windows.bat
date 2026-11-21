@echo off
setlocal
pushd "%~dp0" || goto :directory_error
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\setup_windows.ps1" -ProjectRoot "%~dp0."
set "STATS_SETUP_EXIT=%ERRORLEVEL%"
popd
if not "%STATS_SETUP_EXIT%"=="0" (
    echo.
    echo Setup did not complete. Read the message above and docs\WINDOWS.md.
    pause
    exit /b %STATS_SETUP_EXIT%
)
echo.
echo Setup complete. Double-click launch_windows.bat to open The Stats.
pause
exit /b 0
:directory_error
echo Unable to open the project folder.
pause
exit /b 1
