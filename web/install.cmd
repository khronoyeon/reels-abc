@echo off
rem Reels A+B=C installer for Windows (no PowerShell needed)
rem   Paste into Win+R, Command Prompt or PowerShell:
rem   cmd /k "cd /d %TEMP% && curl --ssl-revoke-best-effort -fsSL https://reels-abc.vercel.app/install.cmd -o reels-install.cmd && reels-install.cmd"
rem Uses only built-in cmd + curl and the official Python; install_win.py does the rest (Korean messages there).
rem Keep this file ASCII-only: cmd mis-reads multibyte (Korean) lines in batch files and can run broken fragments.
chcp 65001 >nul
setlocal EnableExtensions
if "%REELS_BASE%"=="" set "REELS_BASE=https://reels-abc.vercel.app"
set "PYVER=3.12.10"

echo.
echo ==============================================
echo    Reels A+B=C - installing (5-15 min)
echo    Please keep this window open until it finishes.
echo ==============================================

call :findpy
if defined PY goto havepy

echo.
echo [1/6] Installing Python (automatic)...
curl --ssl-revoke-best-effort -fsSL "https://www.python.org/ftp/python/%PYVER%/python-%PYVER%-amd64.exe" -o "%TEMP%\reels-python.exe"
if errorlevel 1 goto fail_net
"%TEMP%\reels-python.exe" /quiet InstallAllUsers=0 PrependPath=0 Include_launcher=0 Include_test=0 Include_doc=0 Shortcuts=0
del "%TEMP%\reels-python.exe" >nul 2>&1
call :findpy
if not defined PY goto fail_py

:havepy
curl --ssl-revoke-best-effort -fsSL "%REELS_BASE%/install_win.py" -o "%TEMP%\reels-install.py"
if errorlevel 1 goto fail_net
"%PY%" -X utf8 "%TEMP%\reels-install.py"
if errorlevel 1 goto fail_any
exit /b 0

:findpy
set "PY="
for %%V in (Python312 Python313 Python311 Python310) do (
  if not defined PY if exist "%LOCALAPPDATA%\Programs\Python\%%V\python.exe" set "PY=%LOCALAPPDATA%\Programs\Python\%%V\python.exe"
  if not defined PY if exist "%ProgramFiles%\%%V\python.exe" set "PY=%ProgramFiles%\%%V\python.exe"
)
exit /b 0

:fail_net
echo.
echo [FAILED] Download failed. Check the internet connection and run the same command again.
exit /b 1

:fail_py
echo.
echo [FAILED] Python could not be installed. Please run the same command again.
exit /b 1

:fail_any
echo.
rem (install_win.py already printed the reason in Korean)
exit /b 1
