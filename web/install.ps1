# 릴스 A+B=C 설치 (Windows 10/11)
#   Windows 키 + R → 아래 한 줄 붙여넣기 → Enter
#   powershell -NoExit -ExecutionPolicy Bypass -c "irm https://reels-abc.vercel.app/install.ps1 | iex"
# 다시 실행하면 최신 버전으로 업데이트된다.
#
# Windows 스마트 앱 컨트롤에 막히지 않도록 서명된 프로그램만 쓴다:
#   - Python: python.org 공식 설치 파일 (Python Software Foundation 서명)
#   - 프로그램 창: Windows에 들어 있는 Microsoft Edge (--app 모드)
#   - 자동 실행: 시작프로그램 폴더의 바로가기 (VBS 사용 안 함)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}
[Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12

$Base = if ($env:REELS_BASE) { $env:REELS_BASE } else { 'https://reels-abc.vercel.app' }
$Dir = Join-Path $env:USERPROFILE 'ReelsExtractor'
$AppUrl = 'http://127.0.0.1:8765'
$PyVersion = '3.12.10'

function Say($m) { Write-Host ''; Write-Host $m -ForegroundColor Cyan }
function Ok($m) { Write-Host "   $m" -ForegroundColor DarkGray }
function Fail($m) {
  Write-Host ''
  Write-Host "[설치 실패] $m" -ForegroundColor Red
  Write-Host '같은 방법으로 한 번 더 실행해 보시고, 그래도 안 되면 이 창을 캡처해서 보내주세요.' -ForegroundColor Yellow
  throw $m
}

Write-Host ''
Write-Host '==============================================' -ForegroundColor Cyan
Write-Host '   릴스 A+B=C 설치를 시작할게요' -ForegroundColor Cyan
Write-Host '   (5~15분 걸려요. 다 될 때까지 이 창을 닫지 마세요)' -ForegroundColor Cyan
Write-Host '==============================================' -ForegroundColor Cyan

if (-not [Environment]::Is64BitOperatingSystem) { Fail '64비트 Windows에서만 설치할 수 있어요.' }

# ---------------------------------------------------------------- 1) 공식 Python
function Find-Python {
  $roots = @("$env:LOCALAPPDATA\Programs\Python", "$env:ProgramFiles")
  foreach ($v in @('Python312', 'Python313', 'Python311', 'Python310')) {
    foreach ($r in $roots) {
      $exe = Join-Path (Join-Path $r $v) 'python.exe'
      if (Test-Path $exe) { return $exe }
    }
  }
  return $null
}

$Py = Find-Python
if (-not $Py) {
  Say '[1/6] 기본 프로그램 준비 중 (자동으로 설치돼요)'
  $inst = Join-Path $env:TEMP "python-$PyVersion-amd64.exe"
  try {
    Invoke-WebRequest "https://www.python.org/ftp/python/$PyVersion/python-$PyVersion-amd64.exe" -OutFile $inst -UseBasicParsing
    Start-Process $inst -ArgumentList '/quiet', 'InstallAllUsers=0', 'PrependPath=0', 'Include_launcher=0', 'Include_test=0', 'Include_doc=0', 'Shortcuts=0' -Wait | Out-Null
    Remove-Item $inst -ErrorAction SilentlyContinue
  } catch { Ok '다른 방법으로 다시 시도할게요' }
  $Py = Find-Python
  if (-not $Py -and (Get-Command winget -ErrorAction SilentlyContinue)) {
    winget install -e --id Python.Python.3.12 --scope user --silent --accept-package-agreements --accept-source-agreements | Out-Null
    $Py = Find-Python
  }
  if (-not $Py) { Fail '기본 프로그램을 설치하지 못했어요. 인터넷 연결을 확인하고 같은 방법으로 다시 실행해 주세요.' }
} else {
  Say '[1/6] 기본 프로그램 확인'
}

# Visual C++ 런타임: 받아쓰기 엔진과 한국어 글자 인식 모델이 필요로 함 (Microsoft 공식, 대부분 PC엔 이미 있음)
$vc = Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64' -ErrorAction SilentlyContinue
if (-not $vc -or $vc.Installed -ne 1) {
  Say '[1/6] Windows 구성요소 설치 중 (Microsoft 공식 · 확인 창이 뜨면 [예]를 눌러주세요)'
  $vcExe = Join-Path $env:TEMP 'vc_redist.x64.exe'
  try {
    Invoke-WebRequest 'https://aka.ms/vs/17/release/vc_redist.x64.exe' -OutFile $vcExe -UseBasicParsing
    Start-Process $vcExe -ArgumentList '/install', '/quiet', '/norestart' -Verb RunAs -Wait
  } catch { Ok '구성요소 설치를 건너뛰고 계속할게요' }
  Remove-Item $vcExe -ErrorAction SilentlyContinue
}

# ---------------------------------------------------------------- 2) 프로그램 파일 받기
Say '[2/6] 릴스 A+B=C 받는 중'
# 실행 중인 추출기 정리 (파일 덮어쓰기 위해)
Get-CimInstance Win32_Process -Filter "Name like 'python%'" -ErrorAction SilentlyContinue |
  Where-Object { $_.CommandLine -like '*ReelsExtractor*server.py*' } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
$tmp = Join-Path $env:TEMP ('reels-abc-' + [guid]::NewGuid())
New-Item -ItemType Directory -Force $tmp | Out-Null
try {
  Invoke-WebRequest "$Base/reels-abc-helper.zip" -OutFile "$tmp\h.zip" -UseBasicParsing
} catch { Fail "프로그램 파일을 받지 못했어요. 인터넷 연결을 확인해 주세요. ($($_.Exception.Message))" }
Expand-Archive "$tmp\h.zip" -DestinationPath $tmp -Force
New-Item -ItemType Directory -Force $Dir | Out-Null
Copy-Item "$tmp\reels-abc-helper\helper" $Dir -Recurse -Force
if (Test-Path "$Dir\web") { Remove-Item "$Dir\web" -Recurse -Force }
Copy-Item "$tmp\reels-abc-helper\web" $Dir -Recurse -Force
Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue
Set-Location $Dir
if (-not (Test-Path 'helper\.env')) { Copy-Item 'helper\.env.example' 'helper\.env' }

# ---------------------------------------------------------------- 3) 필요한 프로그램
Say '[3/6] 필요한 부품 설치 중 (몇 분 걸려요)'
# 예전에 다른 방식(uv)으로 만든 환경이 있으면 새로 만듦
if ((Test-Path '.venv\pyvenv.cfg') -and (Select-String -Path '.venv\pyvenv.cfg' -Pattern '^uv' -Quiet)) { Remove-Item '.venv' -Recurse -Force }
if (-not (Test-Path '.venv\Scripts\python.exe')) {
  & $Py -m venv .venv
  if ($LASTEXITCODE -ne 0) { Fail '설치 폴더를 준비하지 못했어요.' }
}
$VPy = Join-Path $Dir '.venv\Scripts\python.exe'
$VPyw = Join-Path $Dir '.venv\Scripts\pythonw.exe'
& $VPy -m pip install -q --disable-pip-version-check --no-warn-script-location -U pip | Out-Null
& $VPy -m pip install -q --disable-pip-version-check --no-warn-script-location -U -r helper\requirements.txt
if ($LASTEXITCODE -ne 0) { Fail '필요한 프로그램을 설치하지 못했어요.' }
& $VPy -c "import faster_whisper, yt_dlp, imageio_ffmpeg; print('ok')" | Out-Null
if ($LASTEXITCODE -ne 0) { Fail '설치한 프로그램을 불러오지 못했어요. (보안 프로그램이 막았을 수 있어요)' }

# ---------------------------------------------------------------- 4) 받아쓰기 모델
Say '[4/6] 받아쓰기 기능 받는 중 (약 1.6GB · 인터넷 속도에 따라 몇 분)'
& $VPy -c "from faster_whisper import WhisperModel as W; W('large-v3-turbo', device='cpu', compute_type='int8')"
if ($LASTEXITCODE -ne 0) { Fail '받아쓰기 모델을 받지 못했어요. 인터넷 연결을 확인하고 다시 실행해 주세요.' }

Ok '타이틀 자막 읽기 기능 받는 중'
& $VPy -c "import sys; sys.path.insert(0, r'$Dir\helper'); import server; server.rapid_engine(); print('ok')" | Out-Null
if ($LASTEXITCODE -ne 0) { Ok '타이틀 읽기는 Windows 기본 기능으로 대신할게요' }

# ---------------------------------------------------------------- 5) 자동 실행 + 지금 실행
Say '[5/6] 컴퓨터 켤 때 자동으로 켜지게 설정'
$sh = New-Object -ComObject WScript.Shell
$startup = [Environment]::GetFolderPath('Startup')
Remove-Item (Join-Path $startup 'ReelsExtractor.vbs') -ErrorAction SilentlyContinue
$lnk = $sh.CreateShortcut((Join-Path $startup 'ReelsExtractor.lnk'))
$lnk.TargetPath = $VPyw
$lnk.Arguments = "`"$Dir\helper\server.py`""
$lnk.WorkingDirectory = "$Dir\helper"
$lnk.WindowStyle = 7
$lnk.Description = 'Reels A+B=C extractor'
$lnk.Save()
Start-Process -FilePath $VPyw -ArgumentList "`"$Dir\helper\server.py`"" -WorkingDirectory "$Dir\helper"

$ok = $false
for ($i = 0; $i -lt 90; $i++) {
  try { Invoke-WebRequest "$AppUrl/api/health" -UseBasicParsing -TimeoutSec 2 | Out-Null; $ok = $true; break } catch { Start-Sleep 1 }
}
if (-not $ok) {
  $log = Join-Path $Dir 'helper\helper.log'
  if (Test-Path $log) { Get-Content $log -Tail 15 }
  Fail '추출기가 켜지지 않았어요.'
}

# ---------------------------------------------------------------- 6) 프로그램 바로가기
Say '[6/6] 바탕화면 아이콘 만들기'
$edge = $null
try { $edge = (Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\msedge.exe' -ErrorAction Stop).'(default)' } catch {}
foreach ($c in @("${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe", "$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe")) {
  if (-not $edge -and (Test-Path $c)) { $edge = $c }
}
$desk = [Environment]::GetFolderPath('Desktop')
$progs = [Environment]::GetFolderPath('Programs')
Remove-Item (Join-Path $desk '릴스 A+B=C.url') -ErrorAction SilentlyContinue
$appArgs = "--app=$AppUrl --window-size=1480,920"
foreach ($folder in @($desk, $progs)) {
  # 바로가기 도구는 한글 파일 이름을 못 쓰는 Windows가 있어서 영문으로 만든 뒤 한글 이름으로 바꿈
  $tmpName = Join-Path $folder 'ReelsABC-tmp.lnk'
  $final = Join-Path $folder '릴스 A+B=C.lnk'
  $l = $sh.CreateShortcut($tmpName)
  if ($edge) { $l.TargetPath = $edge; $l.Arguments = $appArgs } else { $l.TargetPath = $AppUrl }
  $l.IconLocation = "$Dir\helper\assets\icon.ico"
  $l.Description = 'Reels A+B=C'
  $l.Save()
  Remove-Item -LiteralPath $final -ErrorAction SilentlyContinue
  Rename-Item -LiteralPath $tmpName -NewName '릴스 A+B=C.lnk'
}

Write-Host ''
Write-Host '==============================================' -ForegroundColor Green
Write-Host '   설치 끝! 릴스 A+B=C 프로그램이 열려요.' -ForegroundColor Green
Write-Host '==============================================' -ForegroundColor Green
Write-Host '   다음부터는 바탕화면이나 시작 메뉴의 [릴스 A+B=C]를 실행하세요.'
Write-Host '   컴퓨터를 다시 켜도 추출기는 자동으로 실행돼요. 이 창은 닫아도 돼요.'
if ($env:REELS_NO_OPEN) { return }
if ($edge) { Start-Process $edge $appArgs } else { Start-Process $AppUrl }
