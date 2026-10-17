@echo off
rem Reels A+B=C uninstaller for Windows. Keeps your references/scripts (ReelsExtractor\data).
rem Keep this file ASCII-only (cmd mis-reads Korean lines in batch files). Use ">nul", never "/dev/null".
chcp 65001 >nul
setlocal EnableExtensions
set "RX=%USERPROFILE%\ReelsExtractor"
echo.
echo Removing Reels A+B=C...
curl -s -X POST -H "Origin: http://127.0.0.1:8765" http://127.0.0.1:8765/api/shutdown >nul 2>&1
reg delete "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v ReelsExtractor /f >nul 2>&1
reg delete "HKCU\Software\Classes\reelsabc" /f >nul 2>&1
set "TRIES=0"
:stop
set "HPID="
if exist "%RX%\helper.pid" set /p HPID=<"%RX%\helper.pid"
if defined HPID taskkill /F /T /PID %HPID% >nul 2>&1
taskkill /F /T /IM pythonw.exe >nul 2>&1
timeout /t 2 /nobreak >nul
if exist "%RX%\.venv" rmdir /s /q "%RX%\.venv" >nul 2>&1
set /a TRIES+=1
if exist "%RX%\.venv" if %TRIES% LSS 8 goto stop
for %%D in (helper web media) do if exist "%RX%\%%D" rmdir /s /q "%RX%\%%D" >nul 2>&1
if exist "%RX%\data\ig_login_profile" rmdir /s /q "%RX%\data\ig_login_profile" >nul 2>&1
del "%RX%\helper.pid" >nul 2>&1
for %%F in ("%USERPROFILE%\Desktop" "%APPDATA%\Microsoft\Windows\Start Menu\Programs") do del /q "%%~F\*A+B=C.url" "%%~F\*A+B=C.lnk" >nul 2>&1
for /d %%F in ("%USERPROFILE%\OneDrive*\*") do del /q "%%~F\*A+B=C.url" "%%~F\*A+B=C.lnk" >nul 2>&1
del "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\ReelsExtractor.lnk" >nul 2>&1
echo.
if exist "%RX%\.venv" (
  echo Some files are still in use. Restart the computer and run the same command again.
  exit /b 1
)
echo Done. Your references and scripts are kept (they come back if you reinstall).
echo You can close this window.
