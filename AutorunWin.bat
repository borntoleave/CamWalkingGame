@echo off
setlocal EnableExtensions
REM Double-click entry on Windows. PowerShell helper lives under scripts\.
REM Preferred port is 8080; the helper falls back to 8081, 8082, then 8765.
cd /d "%~dp0"
if not exist "%~dp0app\index.html" (
  echo [ERROR] Missing app\index.html.
  pause
  exit /b 1
)
if not exist "%~dp0scripts\AutorunWin.ps1" (
  echo [ERROR] Missing scripts\AutorunWin.ps1.
  pause
  exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\AutorunWin.ps1" -Root "%~dp0app" -Port 8080
set ERR=%ERRORLEVEL%
if not "%ERR%"=="0" (
  echo.
  echo [ERROR] Server exited with code %ERR%.
  pause
)
exit /b %ERR%
