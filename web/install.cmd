@echo off
rem 릴스 A+B=C 설치 (Windows, PowerShell 없이)
rem   Windows 키 + R 에 붙여넣기:
rem   cmd /k curl -fsSL https://reels-abc.vercel.app/install.cmd -o "%TEMP%\reels-install.cmd" && "%TEMP%\reels-install.cmd"
rem PowerShell이 막힌 PC(회사·학교 보안 정책, 일부 백신)에서도 되도록
rem Windows 기본 도구(cmd, curl)와 공식 Python만 씀. 나머지는 install_win.py 가 처리.
chcp 65001 >nul
setlocal EnableExtensions
if "%REELS_BASE%"=="" set "REELS_BASE=https://reels-abc.vercel.app"
set "PYVER=3.12.10"

echo.
echo ==============================================
echo    릴스 A+B=C 설치를 시작할게요
echo    (5~15분 걸려요. 다 될 때까지 이 창을 닫지 마세요)
echo ==============================================

call :findpy
if defined PY goto havepy

echo.
echo [1/6] 기본 프로그램 준비 중 (자동으로 설치돼요)
curl -fsSL "https://www.python.org/ftp/python/%PYVER%/python-%PYVER%-amd64.exe" -o "%TEMP%\reels-python.exe"
if errorlevel 1 goto fail_net
"%TEMP%\reels-python.exe" /quiet InstallAllUsers=0 PrependPath=0 Include_launcher=0 Include_test=0 Include_doc=0 Shortcuts=0
del "%TEMP%\reels-python.exe" >nul 2>&1
call :findpy
if not defined PY goto fail_py

:havepy
curl -fsSL "%REELS_BASE%/install_win.py" -o "%TEMP%\reels-install.py"
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
echo [설치 실패] 파일을 받지 못했어요. 인터넷 연결을 확인하고 같은 방법으로 다시 실행해 주세요.
exit /b 1

:fail_py
echo.
echo [설치 실패] 기본 프로그램을 설치하지 못했어요. 같은 방법으로 한 번 더 실행해 주세요.
exit /b 1

:fail_any
echo.
echo 같은 방법으로 한 번 더 실행해 보시고, 그래도 안 되면 이 창을 캡처해서 보내주세요.
exit /b 1
