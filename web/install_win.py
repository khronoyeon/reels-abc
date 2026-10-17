# 릴스 A+B=C 설치 (Windows) — install.cmd 가 공식 Python을 준비한 뒤 실행하는 본 설치 단계.
# PowerShell 없이 Python 표준 기능만 사용 (PowerShell이 막힌 PC 대응).
import ctypes
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
import winreg
import zipfile
from pathlib import Path

BASE = os.environ.get("REELS_BASE", "https://reels-abc.vercel.app")
HOME = Path(os.environ["USERPROFILE"])
DIR = HOME / "ReelsExtractor"
APP_URL = "http://127.0.0.1:8765"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def say(msg):
    print("\n" + msg, flush=True)


def ok(msg):
    print("   " + msg, flush=True)


def fail(msg):
    print("\n[설치 실패] " + msg, flush=True)
    print("같은 방법으로 한 번 더 실행해 보시고, 그래도 안 되면 이 창을 캡처해서 보내주세요.", flush=True)
    sys.exit(1)


def download(url, dst):
    req = urllib.request.Request(url, headers={"User-Agent": "reels-abc-installer"})
    with urllib.request.urlopen(req, timeout=120) as r, open(dst, "wb") as f:
        shutil.copyfileobj(r, f)


def known_folder(csidl):
    buf = ctypes.create_unicode_buffer(260)
    ctypes.windll.shell32.SHGetFolderPathW(None, csidl, None, 0, buf)
    return Path(buf.value)


def helper_up():
    try:
        with urllib.request.urlopen(APP_URL + "/api/health", timeout=2) as r:
            return json.load(r).get("ok", False)
    except Exception:  # noqa: BLE001
        return False


def stop_old_helper():
    """예전에 켜 둔 추출기를 끔 (파일을 바꿀 수 있도록)."""
    if not helper_up():
        return
    try:
        req = urllib.request.Request(APP_URL + "/api/shutdown", data=b"{}", method="POST",
                                     headers={"Origin": APP_URL, "Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=3)
    except Exception:  # noqa: BLE001
        pass
    for _ in range(10):
        if not helper_up():
            return
        time.sleep(0.5)
    # 예전 버전(종료 기능 없음): pythonw 로 돌던 추출기 종료
    subprocess.run(["taskkill", "/F", "/T", "/IM", "pythonw.exe"], capture_output=True, creationflags=NO_WINDOW)
    time.sleep(1)


def vc_runtime_ok():
    try:
        k = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64")
        return winreg.QueryValueEx(k, "Installed")[0] == 1
    except OSError:
        return False


def install_vc_runtime():
    say("[1/6] Windows 구성요소 설치 중 (Microsoft 공식 · 확인 창이 뜨면 [예]를 눌러주세요)")
    exe = Path(tempfile.gettempdir()) / "vc_redist.x64.exe"
    try:
        download("https://aka.ms/vs/17/release/vc_redist.x64.exe", exe)
        # 관리자 확인 창(UAC)으로 실행하고 끝날 때까지 기다림
        SEE_MASK_NOCLOSEPROCESS = 0x40

        class SEI(ctypes.Structure):
            _fields_ = [("cbSize", ctypes.c_ulong), ("fMask", ctypes.c_ulong), ("hwnd", ctypes.c_void_p),
                        ("lpVerb", ctypes.c_wchar_p), ("lpFile", ctypes.c_wchar_p), ("lpParameters", ctypes.c_wchar_p),
                        ("lpDirectory", ctypes.c_wchar_p), ("nShow", ctypes.c_int), ("hInstApp", ctypes.c_void_p),
                        ("lpIDList", ctypes.c_void_p), ("lpClass", ctypes.c_wchar_p), ("hkeyClass", ctypes.c_void_p),
                        ("dwHotKey", ctypes.c_ulong), ("hIcon", ctypes.c_void_p), ("hProcess", ctypes.c_void_p)]
        sei = SEI(cbSize=ctypes.sizeof(SEI), fMask=SEE_MASK_NOCLOSEPROCESS, lpVerb="runas", lpFile=str(exe),
                  lpParameters="/install /quiet /norestart", nShow=0)
        if ctypes.windll.shell32.ShellExecuteExW(ctypes.byref(sei)) and sei.hProcess:
            ctypes.windll.kernel32.WaitForSingleObject(ctypes.c_void_p(sei.hProcess), 0xFFFFFFFF)
    except Exception:  # noqa: BLE001
        ok("구성요소 설치를 건너뛰고 계속할게요")
    finally:
        try:
            exe.unlink()
        except OSError:
            pass


def ram_gb():
    class MS(ctypes.Structure):
        _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong), ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong), ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong), ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
    try:
        m = MS(dwLength=ctypes.sizeof(MS))
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
        return m.ullTotalPhys / 2**30
    except Exception:  # noqa: BLE001
        return 0


def explain_exit(rc):
    """오류 메시지 없이 프로그램이 멈췄을 때 (Windows 종료 코드) 이유 설명."""
    code = rc & 0xFFFFFFFF
    if code in (2, 3, 4):
        return  # prepare_model.py 가 이미 이유를 말함
    known = {
        0xC000001D: "이 컴퓨터 CPU가 받아쓰기 기능에 필요한 명령을 지원하지 않아요 (아주 오래된 CPU).",
        0xC0000005: "받아쓰기 기능이 갑자기 멈췄어요. 보안 프로그램이 막았을 수 있어요 — 백신에서 이 설치를 허용하고 다시 실행해 주세요.",
        0xC0000409: "받아쓰기 기능이 갑자기 멈췄어요. 보안 프로그램이 막았을 수 있어요 — 백신에서 이 설치를 허용하고 다시 실행해 주세요.",
        0xC0000017: "컴퓨터 메모리(RAM)가 부족해요. 다른 프로그램을 모두 끄고 다시 실행해 주세요.",
        1: "보안 프로그램이 설치 중인 프로그램을 강제로 껐을 수 있어요. 백신에서 이 설치를 허용하고 다시 실행해 주세요.",
    }
    ok("[문제] " + known.get(code, "설치 중인 프로그램이 갑자기 꺼졌어요. 보안 프로그램이 막았을 수 있어요."))
    ok(f"(오류 코드: 0x{code:08X})")


def find_edge():
    for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        try:
            k = winreg.OpenKey(root, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\msedge.exe")
            p = winreg.QueryValueEx(k, "")[0]
            if p and Path(p).exists():
                return p
        except OSError:
            pass
    for c in (os.environ.get("ProgramFiles(x86)", ""), os.environ.get("ProgramFiles", "")):
        p = Path(c) / "Microsoft" / "Edge" / "Application" / "msedge.exe"
        if c and p.exists():
            return str(p)
    return None


def set_reg(root, path, name, value):
    k = winreg.CreateKey(root, path)
    winreg.SetValueEx(k, name, 0, winreg.REG_SZ, value)
    winreg.CloseKey(k)


def write_url_shortcut(path, url, icon):
    """바탕화면·시작 메뉴 바로가기 (.url — 만드는 데 PowerShell이 필요 없음)."""
    path.write_text(f"[InternetShortcut]\r\nURL={url}\r\nIconFile={icon}\r\nIconIndex=0\r\n", encoding="utf-8")


def main():
    print("", flush=True)
    if not vc_runtime_ok():
        install_vc_runtime()

    say("[2/6] 릴스 A+B=C 받는 중")
    stop_old_helper()
    tmp = Path(tempfile.mkdtemp(prefix="reels-abc-"))
    try:
        download(f"{BASE}/reels-abc-helper.zip", tmp / "h.zip")
    except Exception as e:  # noqa: BLE001
        fail(f"프로그램 파일을 받지 못했어요. 인터넷 연결을 확인해 주세요. ({e})")
    with zipfile.ZipFile(tmp / "h.zip") as z:
        z.extractall(tmp)
    src = tmp / "reels-abc-helper"
    DIR.mkdir(exist_ok=True)
    shutil.copytree(src / "helper", DIR / "helper", dirs_exist_ok=True)
    shutil.rmtree(DIR / "web", ignore_errors=True)
    shutil.copytree(src / "web", DIR / "web")
    shutil.rmtree(tmp, ignore_errors=True)
    if not (DIR / "helper" / ".env").exists():
        shutil.copy(DIR / "helper" / ".env.example", DIR / "helper" / ".env")

    say("[3/6] 필요한 부품 설치 중 (몇 분 걸려요)")
    venv = DIR / ".venv"
    cfg = venv / "pyvenv.cfg"
    if cfg.exists() and "uv" in cfg.read_text(encoding="utf-8", errors="ignore").lower().split("\n")[0]:
        shutil.rmtree(venv, ignore_errors=True)  # 예전 방식(uv)으로 만든 환경은 새로
    if not (venv / "Scripts" / "python.exe").exists():
        if subprocess.run([sys.executable, "-m", "venv", str(venv)]).returncode:
            fail("설치 폴더를 준비하지 못했어요.")
    vpy = str(venv / "Scripts" / "python.exe")
    vpyw = str(venv / "Scripts" / "pythonw.exe")
    pip = [vpy, "-m", "pip", "install", "-q", "--disable-pip-version-check", "--no-warn-script-location", "-U"]
    subprocess.run(pip + ["pip"])
    if subprocess.run(pip + ["-r", str(DIR / "helper" / "requirements.txt")]).returncode:
        fail("필요한 부품을 설치하지 못했어요.")
    if subprocess.run([vpy, "-c", "import faster_whisper, yt_dlp, imageio_ffmpeg, truststore"]).returncode:
        fail("설치한 부품을 불러오지 못했어요. (보안 프로그램이 막았을 수 있어요)")

    say("[4/6] 받아쓰기 기능 받는 중 (약 1.6GB · 인터넷 속도에 따라 몇 분)")
    prep = str(DIR / "helper" / "prepare_model.py")
    ram = ram_gb()
    if ram and ram < 5:
        ok(f"참고: 이 컴퓨터 메모리가 {ram:.0f}GB라 받아쓰기가 느리거나 안 될 수 있어요")
    rc = subprocess.run([vpy, prep, "download"]).returncode
    if rc:
        explain_exit(rc)
        fail("받아쓰기 기능을 받지 못했어요.")
    rc = subprocess.run([vpy, prep, "load"]).returncode
    if rc:
        explain_exit(rc)
        fail("받아쓰기 기능을 켜지 못했어요.")
    ok("타이틀 자막 읽기 기능 받는 중")
    r = subprocess.run([vpy, "-c", f"import sys; sys.path.insert(0, r'{DIR / 'helper'}'); import server; server.rapid_engine()"],
                       capture_output=True)
    if r.returncode:
        ok("타이틀 읽기는 Windows 기본 기능으로 대신할게요")

    say("[5/6] 컴퓨터 켤 때 자동으로 켜지게 설정")
    server_cmd = f'"{vpyw}" "{DIR / "helper" / "server.py"}"'
    set_reg(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", "ReelsExtractor", server_cmd)
    startup = known_folder(7)  # 시작프로그램 폴더 — 예전 방식 정리
    for old in ("ReelsExtractor.lnk", "ReelsExtractor.vbs"):
        try:
            (startup / old).unlink()
        except OSError:
            pass
    subprocess.Popen([vpyw, str(DIR / "helper" / "server.py")], cwd=str(DIR / "helper"),
                     creationflags=getattr(subprocess, "DETACHED_PROCESS", 0) | NO_WINDOW, close_fds=True)
    for _ in range(90):
        if helper_up():
            break
        time.sleep(1)
    else:
        log = DIR / "helper" / "helper.log"
        if log.exists():
            print("\n".join(log.read_text(encoding="utf-8", errors="ignore").splitlines()[-15:]))
        fail("추출기가 켜지지 않았어요.")

    say("[6/6] 바탕화면 아이콘 만들기")
    edge = find_edge()
    app_args = f"--app={APP_URL} --window-size=1480,920"
    open_cmd = f'"{edge}" {app_args}' if edge else f"explorer.exe {APP_URL}"
    cls = r"Software\Classes\reelsabc"
    set_reg(winreg.HKEY_CURRENT_USER, cls, "", "URL:Reels A+B=C")
    set_reg(winreg.HKEY_CURRENT_USER, cls, "URL Protocol", "")
    set_reg(winreg.HKEY_CURRENT_USER, cls + r"\DefaultIcon", "", str(DIR / "helper" / "assets" / "icon.ico"))
    set_reg(winreg.HKEY_CURRENT_USER, cls + r"\shell\open\command", "", open_cmd)
    icon = str(DIR / "helper" / "assets" / "icon.ico")
    desk = known_folder(0x10)        # 바탕화면 (OneDrive 바탕화면 포함)
    progs = known_folder(2)          # 시작 메뉴 > 프로그램
    for folder in (desk, progs):
        for old in ("릴스 A+B=C.lnk",):  # 예전 방식 바로가기는 새 것으로 교체
            try:
                (folder / old).unlink()
            except OSError:
                pass
        write_url_shortcut(folder / "릴스 A+B=C.url", "reelsabc://open", icon)

    print("\n==============================================")
    print("   설치 끝! 릴스 A+B=C 프로그램이 열려요.")
    print("==============================================")
    print("   다음부터는 바탕화면이나 시작 메뉴의 [릴스 A+B=C]를 실행하세요.")
    print("   컴퓨터를 다시 켜도 추출기는 자동으로 실행돼요. 이 창은 닫아도 돼요.", flush=True)
    if not os.environ.get("REELS_NO_OPEN"):
        if edge:
            subprocess.Popen([edge, f"--app={APP_URL}", "--window-size=1480,920"])
        else:
            os.startfile(APP_URL)


if __name__ == "__main__":
    main()
