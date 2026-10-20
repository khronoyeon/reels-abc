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
os.environ["PYTHONUTF8"] = "1"  # 이 설치가 실행하는 파이썬들도 한글 출력 때문에 멈추지 않게


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


def pc_info():
    """실패 원인 파악용: CPU 이름 · 메모리 · AVX2 지원 여부 (받아쓰기 엔진이 CPU 명령어를 가림)."""
    cpu = ""
    try:
        k = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0")
        cpu = winreg.QueryValueEx(k, "ProcessorNameString")[0].strip()
    except OSError:
        pass
    try:
        avx2 = bool(ctypes.windll.kernel32.IsProcessorFeaturePresent(40))  # PF_AVX2_INSTRUCTIONS_AVAILABLE
    except Exception:  # noqa: BLE001
        avx2 = None
    return f"CPU: {cpu or '?'} / 메모리 {ram_gb():.0f}GB / AVX2 {'지원' if avx2 else '미지원·확인불가' if avx2 is None else '미지원'} / Windows {platform_ver()}"


def platform_ver():
    try:
        import platform
        return platform.version()
    except Exception:  # noqa: BLE001
        return "?"


def explain_exit(rc):
    """오류 메시지 없이 프로그램이 멈췄을 때 (Windows 종료 코드) 이유 설명."""
    code = rc & 0xFFFFFFFF
    if code in (2, 3, 4):
        return  # prepare_model.py 가 이미 이유를 말함
    known = {
        0xC000001D: "이 컴퓨터 CPU가 받아쓰기 기능에 필요한 명령을 지원하지 않아요 (아주 오래된 CPU).",
        0xC0000005: "받아쓰기 모델을 켜다가 멈췄어요. 이 컴퓨터 메모리(RAM)에 비해 모델이 크거나, 백신이 막았을 수 있어요.",
        0xC0000409: "받아쓰기 기능이 갑자기 멈췄어요. 보안 프로그램이 막았을 수 있어요 — 백신에서 이 설치를 허용하고 다시 실행해 주세요.",
        0xC0000017: "컴퓨터 메모리(RAM)가 부족해요. 다른 프로그램을 모두 끄고 다시 실행해 주세요.",
    }
    if code == 1:
        return  # 파이썬 오류: 위에 오류 내용이 이미 찍혀 있음
    ok("[문제] " + known.get(code, "설치 중인 프로그램이 갑자기 꺼졌어요. 보안 프로그램이 막았을 수 있어요."))
    ok(f"(오류 코드: 0x{code:08X})")


MODEL_CHAIN = ["large-v3", "large-v3-turbo"]  # 정확도 순. 큰 모델이 이 PC에서 안 돌면 다음 것으로
CHOICE_FILE = DIR / "data" / "model_choice.json"  # 어떤 모델이 이 PC에서 됐는지 기억 (업데이트 때 3GB 다시 안 받게)


def prepare_model(vpy, prep):
    """모델을 받고 켜본다. 큰 모델이 이 PC에서 못 켜지면(메모리 부족·오래된 CPU) 가벼운 모델로 자동 전환."""
    chain = list(MODEL_CHAIN)
    try:
        prev = json.loads(CHOICE_FILE.read_text(encoding="utf-8"))
        if prev.get("model") in chain:  # 지난번에 이 PC에서 된 모델부터 (그 위 모델은 이미 안 되는 걸 확인함)
            chain = chain[chain.index(prev["model"]):]
            if prev.get("skipped"):
                ok(f"지난번에 이 컴퓨터에서 더 정확한 모델이 안 돼서 {prev['model']} 모델을 써요")
    except Exception:  # noqa: BLE001
        pass
    ram = ram_gb()
    if ram and ram < 8 and chain[0] == "large-v3":
        ok(f"이 컴퓨터 메모리가 {ram:.0f}GB라 가벼운 모델을 써요 (정확도는 조금 낮아요)")
        chain = chain[1:]
    skipped = []
    for model in chain:
        rc = subprocess.run([vpy, prep, "download", model]).returncode
        if rc:
            explain_exit(rc)
            fail("받아쓰기 기능을 받지 못했어요.")
        rc = subprocess.run([vpy, prep, "load", model]).returncode
        if rc:  # 받다 만 파일이 깨져 있을 수 있음 → 지우고 한 번 더
            explain_exit(rc)
            subprocess.run([vpy, prep, "reset", model])
            if subprocess.run([vpy, prep, "download", model]).returncode:
                fail("받아쓰기 기능을 받지 못했어요.")
            rc = subprocess.run([vpy, prep, "load", model]).returncode
        if rc == 0:
            for other in MODEL_CHAIN:  # 안 쓰는 모델은 지워서 공간 확보
                if other != model:
                    subprocess.run([vpy, prep, "reset", other], capture_output=True)
            CHOICE_FILE.parent.mkdir(exist_ok=True)
            CHOICE_FILE.write_text(json.dumps({"model": model, "skipped": skipped, "pc": pc_info()}, ensure_ascii=False), encoding="utf-8")
            cfg_path = DIR / "helper" / "config.json"
            cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
            cfg["auto_model"] = model  # 추출기의 '자동' 모델 = 이 PC에서 되는 모델
            cfg_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
            if skipped:
                ok(f"이 컴퓨터에서는 {model} 모델로 받아써요 (가장 정확한 모델은 켜지지 않았어요)")
            return model
        explain_exit(rc)
        skipped.append(model)
        subprocess.run([vpy, prep, "reset", model], capture_output=True)
        if model != chain[-1]:
            ok("더 가벼운 받아쓰기 모델로 다시 해볼게요")
    ok("이 컴퓨터 정보: " + pc_info())
    fail("이 컴퓨터에서는 받아쓰기 기능이 켜지지 않아요. (메모리 부족이거나 아주 오래된 CPU일 수 있어요. 이 창을 캡처해서 보내주세요)")


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

    say("[4/6] 받아쓰기 기능 받는 중 (약 3GB · 인터넷 속도에 따라 5~20분)")
    prepare_model(str(venv / "Scripts" / "python.exe"), str(DIR / "helper" / "prepare_model.py"))
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
