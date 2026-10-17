@echo off
rem 릴스 A+B=C 지우기 (Windows). 만든 레퍼런스·대본(data 폴더)은 남겨둠.
chcp 65001 >nul
echo.
echo 릴스 A+B=C 프로그램을 지우는 중이에요...
curl -s -X POST -H "Origin: http://127.0.0.1:8765" http://127.0.0.1:8765/api/shutdown >nul 2>&1
timeout /t 2 /nobreak >nul
taskkill /F /T /IM pythonw.exe >nul 2>&1
reg delete "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v ReelsExtractor /f >nul 2>&1
reg delete "HKCU\Software\Classes\reelsabc" /f >nul 2>&1
for %%D in (.venv helper web media) do if exist "%USERPROFILE%\ReelsExtractor\%%D" rmdir /s /q "%USERPROFILE%\ReelsExtractor\%%D"
if exist "%USERPROFILE%\ReelsExtractor\data\ig_login_profile" rmdir /s /q "%USERPROFILE%\ReelsExtractor\data\ig_login_profile"
for %%F in ("%USERPROFILE%\Desktop" "%USERPROFILE%\OneDrive\Desktop" "%USERPROFILE%\OneDrive\바탕 화면" "%APPDATA%\Microsoft\Windows\Start Menu\Programs") do (
  del "%%~F\릴스 A+B=C.url" >nul 2>&1
  del "%%~F\릴스 A+B=C.lnk" >nul 2>&1
)
del "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\ReelsExtractor.lnk" >nul 2>&1
echo.
echo 다 지웠어요. 만든 레퍼런스·대본은 남겨뒀어요. (다시 설치하면 그대로 나와요)
echo 이 창은 닫아도 돼요.
