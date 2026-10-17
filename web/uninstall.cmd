@echo off
rem Reels A+B=C uninstaller for Windows. Keeps your references/scripts (ReelsExtractor\data).
rem Keep this file ASCII-only (cmd mis-reads Korean lines in batch files).
chcp 65001 >nul
echo.
echo Removing Reels A+B=C...
curl -s -X POST -H "Origin: http://127.0.0.1:8765" http://127.0.0.1:8765/api/shutdown >/dev/null 2>&1
timeout /t 2 /nobreak >nul
taskkill /F /T /IM pythonw.exe >/dev/null 2>&1
reg delete "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v ReelsExtractor /f >/dev/null 2>&1
reg delete "HKCU\Software\Classes\reelsabc" /f >/dev/null 2>&1
for %%D in (.venv helper web media) do if exist "%USERPROFILE%\ReelsExtractor\%%D" rmdir /s /q "%USERPROFILE%\ReelsExtractor\%%D"
if exist "%USERPROFILE%\ReelsExtractor\data\ig_login_profile" rmdir /s /q "%USERPROFILE%\ReelsExtractor\data\ig_login_profile"
for %%F in ("%USERPROFILE%\Desktop" "%APPDATA%\Microsoft\Windows\Start Menu\Programs") do del /q "%%~F\*A+B=C.url" "%%~F\*A+B=C.lnk" >/dev/null 2>&1
for /d %%F in ("%USERPROFILE%\OneDrive*\*") do del /q "%%~F\*A+B=C.url" "%%~F\*A+B=C.lnk" >/dev/null 2>&1
del "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\ReelsExtractor.lnk" >/dev/null 2>&1
echo.
echo Done. Your references and scripts are kept (they come back if you reinstall).
echo You can close this window.
