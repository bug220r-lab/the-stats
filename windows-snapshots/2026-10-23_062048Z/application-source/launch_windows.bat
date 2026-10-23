@echo off
setlocal
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
pushd "%~dp0" || goto :directory_error
if not exist "%~dp0.venv\Scripts\python.exe" (
    echo The project Python environment is missing. Run setup_windows.bat first.
    popd
    pause
    exit /b 1
)
"%~dp0.venv\Scripts\python.exe" "%~dp0scripts\launch.py" %*
set "STATS_LAUNCH_EXIT=%ERRORLEVEL%"
popd
if not "%STATS_LAUNCH_EXIT%"=="0" (
    echo.
    echo The dashboard could not start. Read the message above and docs\WINDOWS.md.
    pause
)
exit /b %STATS_LAUNCH_EXIT%
:directory_error
echo Unable to open the project folder.
pause
exit /b 1
