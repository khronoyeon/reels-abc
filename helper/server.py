#!/usr/bin/env python3
"""릴스 A+B=C 로컬 헬퍼.

각자의 컴퓨터에서 실행되며, 배포된 웹사이트가 http://127.0.0.1:8765 로 요청을 보낸다.
- 릴스/쇼츠/틱톡 링크 → yt-dlp로 오디오 추출 → 로컬 whisper로 전사
- (선택) ANTHROPIC_API_KEY가 있으면 후킹/본문/CTA 자동 분리와 C 생성에 Claude 사용
- 같은 주소에서 웹 UI(../web)도 서빙하므로 배포 없이 로컬만으로도 사용 가능
"""
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

# 모델을 받아야 할 때 허깅페이스 Xet 엔진 대신 일반 다운로드 (prepare_model.py 참고)
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
os.environ.setdefault("HF_HUB_DOWNLOAD_TIMEOUT", "180")
os.environ.setdefault("HF_HUB_ETAG_TIMEOUT", "60")

# 백신·회사망이 인터넷 접속을 검사하는 PC(자체 인증서 사용)에서도 되도록: 파이썬 기본 목록 대신 Windows/Mac이 믿는 인증서 사용
try:
    import truststore
    truststore.inject_into_ssl()
except Exception:  # noqa: BLE001
    pass

HERE = Path(__file__).resolve().parent
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)  # Windows: 검은 창 안 띄움
# Windows: 하위 프로그램(yt-dlp)이 한글을 cp949가 아닌 UTF-8로 내보내도록
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
os.environ.setdefault("PYTHONUTF8", "1")

# 창 없이(자동 실행·pythonw) 돌 때는 출력할 곳이 없으므로 로그 파일로
if sys.stdout is None or sys.stderr is None:
    _log = open(Path(__file__).resolve().parent / "helper.log", "a", encoding="utf-8", buffering=1)
    sys.stdout = sys.stdout or _log
    sys.stderr = sys.stderr or _log


def ensure_ffmpeg():
    """ffmpeg가 없으면 pip 패키지(imageio-ffmpeg)에 들어 있는 실행 파일을 PATH에 연결."""
    if shutil.which("ffmpeg"):
        return
    try:
        import imageio_ffmpeg
    except ImportError:
        return
    src = Path(imageio_ffmpeg.get_ffmpeg_exe())
    bindir = HERE / "bin"
    bindir.mkdir(exist_ok=True)
    dst = bindir / ("ffmpeg.exe" if os.name == "nt" else "ffmpeg")
    if not dst.exists():
        try:
            dst.symlink_to(src)
        except OSError:
            shutil.copy2(src, dst)
    os.environ["PATH"] = str(bindir) + os.pathsep + os.environ.get("PATH", "")


ensure_ffmpeg()
WEB_DIR = HERE.parent / "web"
CONFIG_PATH = HERE / "config.json"

DEFAULT_CONFIG = {
    "port": 8765,
    # 배포한 사이트 주소를 여기에 추가 (예: "https://reels-abc.vercel.app")
    "allowed_origins": ["http://127.0.0.1:8765", "http://localhost:8765", "https://reels-abc.vercel.app"],
    # 정확도 우선: large-v3 / 속도 우선: large-v3-turbo
    "model": "auto",
    "language": "ko",
    # 인스타가 로그인을 요구할 때 쿠키를 가져올 브라우저 (chrome, safari, firefox, edge, whale 등). 비우면 사용 안 함
    "cookies_from_browser": "",
}

MLX_MODELS = {
    "large-v3": "mlx-community/whisper-large-v3-mlx",
    "large-v3-turbo": "mlx-community/whisper-large-v3-turbo",
}

CLAUDE_MODEL = "claude-opus-5-5"


def load_env():
    """helper/.env 의 KEY=VALUE 를 환경변수로 (ANTHROPIC_API_KEY 등)."""
    env_path = HERE / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            v = v.strip().strip('"').strip("'")
            if v:
                os.environ.setdefault(k.strip(), v)


load_env()


def load_config():
    cfg = dict(DEFAULT_CONFIG)
    if CONFIG_PATH.exists():
        try:
            cfg.update(json.loads(CONFIG_PATH.read_text(encoding="utf-8")))
        except Exception as e:  # noqa: BLE001
            print(f"[경고] config.json 읽기 실패: {e}")
    env_origins = os.environ.get("ALLOWED_ORIGINS")
    if env_origins:
        cfg["allowed_origins"] += [o.strip() for o in env_origins.split(",") if o.strip()]
    return cfg


CONFIG = load_config()
PROGRESS = {}  # 링크별 현재 단계 (화면에 진행 상황 표시용)


# ---------------------------------------------------------------- 전사 엔진

def detect_engine():
    is_apple_silicon = sys.platform == "darwin" and platform.machine() == "arm64"
    if is_apple_silicon:
        try:
            import mlx_whisper  # noqa: F401
            return "mlx-whisper"
        except ImportError:
            pass
    try:
        import faster_whisper  # noqa: F401
        return "faster-whisper"
    except ImportError:
        pass
    return None


ENGINE = detect_engine()
_model_lock = threading.Lock()
_fw_models = {}

# 한국어 숏폼 전사 품질을 올리기 위한 힌트 (문장부호·구어체 유도)
INITIAL_PROMPT_KO = "안녕하세요. 오늘은 여러분께 꼭 알려드리고 싶은 내용이 있어요. 끝까지 보시고, 저장해 두세요!"


def detect_language_mlx(path, repo):
    import mlx.core as mx
    from mlx_whisper.audio import N_FRAMES, N_SAMPLES, log_mel_spectrogram, pad_or_trim
    from mlx_whisper.transcribe import ModelHolder

    model = ModelHolder.get_model(repo, mx.float16)
    mel = log_mel_spectrogram(str(path), n_mels=model.dims.n_mels, padding=N_SAMPLES)
    _, probs = model.detect_language(pad_or_trim(mel, N_FRAMES, axis=-2).astype(mx.float16))
    return probs


def resolve_language(language, probs):
    """'ko' 설정 = 한국어 우선: 감지 결과가 한국어(또는 한국어 확률이 충분)면 ko 고정,
    아니면 감지된 언어로. 'auto' = 감지 결과 그대로. 그 외 = 강제 지정."""
    detected = max(probs, key=probs.get) if probs else None
    if language in ("", None, "auto"):
        return detected
    if language == "ko":
        if detected == "ko" or probs.get("ko", 0) >= 0.25:
            return "ko"
        return detected
    return language


def resolve_model(model):
    if model in ("", None, "auto"):
        # Windows도 정확도 우선 (가벼운 turbo보다 2~3배 느리지만 Mac 결과와 다른 글자 2.1% → 0.8%)
        # 단, 설치 때 큰 모델이 이 PC에서 안 켜졌으면 설치기가 config.json auto_model 에 가벼운 모델을 적어둠
        return CONFIG.get("auto_model") or "large-v3"
    return model


def fw_model(model):
    """faster-whisper 모델을 한 번만 메모리에 올림 (_model_lock 안에서 호출)."""
    from faster_whisper import WhisperModel
    if model not in _fw_models:
        t = time.time()
        # 허깅페이스가 막힌 PC는 설치 때 GitHub 사본을 models/ 에 받아둠 (prepare_model.py)
        local = HERE.parent / "models" / model
        src = str(local) if (local / "model.bin").exists() else model
        # 그래픽카드 드라이버 상태와 상관없이 항상 되도록 CPU로 (자동 선택 시 CUDA 라이브러리 없으면 오류)
        _fw_models[model] = WhisperModel(src, device="cpu", compute_type="int8", cpu_threads=os.cpu_count() or 4)
        print(f"[시간] 받아쓰기 모델 올리기 {time.time() - t:.1f}s ({model}, CPU {os.cpu_count()}개)")
    return _fw_models[model]


def transcribe_audio(path, model, language):
    model = resolve_model(model)
    if ENGINE == "mlx-whisper":
        import mlx_whisper

        repo = MLX_MODELS.get(model, MLX_MODELS["large-v3"])
        with _model_lock:
            lang = language
            if language in ("", None, "auto", "ko"):
                try:
                    lang = resolve_language(language, detect_language_mlx(path, repo))
                except Exception as e:  # noqa: BLE001
                    print(f"[경고] 언어 감지 실패, 설정값 사용: {e}")
                    lang = None if language in ("", "auto") else language
            prompt = INITIAL_PROMPT_KO if lang == "ko" else None
            res = mlx_whisper.transcribe(
                str(path),
                path_or_hf_repo=repo,
                language=lang,
                initial_prompt=prompt,
                condition_on_previous_text=False,  # 반복·환각 루프 방지
                hallucination_silence_threshold=2.0,
                word_timestamps=True,
                verbose=None,
            )
        segs = [
            {"start": round(s["start"], 2), "end": round(s["end"], 2), "text": s["text"].strip()}
            for s in res.get("segments", [])
            if s.get("text", "").strip()
        ]
        return segs, res.get("language", lang)

    if ENGINE == "faster-whisper":
        t_wait = time.time()
        with _model_lock:
            fw = fw_model(model)
            print(f"[시간] 모델 대기·준비 {time.time() - t_wait:.1f}s")
            # Mac과 같은 방식: 먼저 언어를 확인하고, 한국어면 한국어로 고정 + 숏폼 말투 힌트
            # (힌트 없이 자동 감지로 받아쓰면 Mac 결과와 다른 글자가 2배 넘게 많았음 — 5.0% → 2.1%)
            from faster_whisper import decode_audio
            audio = decode_audio(str(path))
            lang = language
            if language in ("", None, "auto", "ko"):
                try:
                    _, _, all_probs = fw.detect_language(audio)
                    lang = resolve_language(language, dict(all_probs))
                except Exception as e:  # noqa: BLE001
                    print(f"[경고] 언어 감지 실패, 설정값 사용: {e}")
                    lang = None if language in ("", "auto") else language
            segments, info = fw.transcribe(
                audio,
                language=lang,
                initial_prompt=INITIAL_PROMPT_KO if lang == "ko" else None,
                beam_size=5,
                vad_filter=True,
                condition_on_previous_text=False,
            )
            segs = [
                {"start": round(s.start, 2), "end": round(s.end, 2), "text": s.text.strip()}
                for s in segments
                if s.text.strip()
            ]
        return segs, info.language

    raise RuntimeError("전사 엔진이 없습니다. install 스크립트를 먼저 실행하세요.")


# ---------------------------------------------------------------- 다운로드

def yt_dlp_cmd():
    try:
        import yt_dlp  # noqa: F401
        return [sys.executable, str(HERE / "ytdlp_run.py")]
    except ImportError:
        exe = shutil.which("yt-dlp")
        if exe:
            return [exe]
    raise RuntimeError("yt-dlp가 설치되어 있지 않습니다.")


def video_stats(info):
    """조회수·좋아요·댓글 (플랫폼마다 있는 것만)."""
    return {
        "views": info.get("view_count") or info.get("play_count"),
        "likes": info.get("like_count"),
        "comments": info.get("comment_count"),
        "uploaded": info.get("upload_date") or "",
    }


_IG_ALPH = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
_ig_cookie_cache = {}


def ig_play_count(url, cookies_browser):
    """인스타는 로그인해야 재생수를 알려줌 → 이 컴퓨터 브라우저의 인스타 로그인으로 조회 (인스타에만 전송)."""
    m = re.search(r"instagram\.com/(?:[^/]+/)?(?:reels?|p|tv)/([A-Za-z0-9_-]+)", url)
    if not m:
        return None, ""
    import urllib.error
    import urllib.request
    from yt_dlp.cookies import extract_cookies_from_browser
    pk = 0
    for c in m.group(1)[:11]:
        pk = pk * 64 + _IG_ALPH.index(c)
    tried_login = False  # 인스타 로그인 정보를 하나라도 써봤는지 (없으면 화면에 '로그인 필요' 표시)
    for browser in [b for b in ["__login__" if ig_logged_in() else "", cookies_browser, "chrome"] if b]:
        try:
            if browser not in _ig_cookie_cache:
                if browser == "__login__":
                    import http.cookiejar
                    jar = http.cookiejar.MozillaCookieJar(str(IG_COOKIES))
                    jar.load(ignore_discard=True, ignore_expires=True)
                else:
                    jar = extract_cookies_from_browser(browser)
                _ig_cookie_cache[browser] = {c.name: c.value for c in jar if "instagram.com" in c.domain}
            cookies = _ig_cookie_cache[browser]
            if not cookies.get("sessionid"):
                continue
            tried_login = True
            # 로그인 창은 Windows 엣지라서 그에 맞는 브라우저 정보로 (다른 기기 모양새면 인스타가 거부할 수 있음)
            ua = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/154.0.0.0 Safari/537.36 Edg/154.0.0.0"
                  if os.name == "nt" else "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/154.0.0.0 Safari/537.36")
            req = urllib.request.Request(f"https://i.instagram.com/api/v1/media/{pk}/info/", headers={
                "Cookie": "; ".join(f"{k}={v}" for k, v in cookies.items()),
                "X-IG-App-ID": "936619743392459", "X-CSRFToken": cookies.get("csrftoken", ""),
                "X-Requested-With": "XMLHttpRequest", "Referer": "https://www.instagram.com/",
                "Origin": "https://www.instagram.com", "Accept": "*/*", "User-Agent": ua,
            })
            for attempt in range(2):
                try:
                    item = json.load(urllib.request.urlopen(req, timeout=20))["items"][0]
                    return item.get("play_count") or item.get("ig_play_count") or item.get("view_count"), ""
                except urllib.error.HTTPError as e:
                    body = e.read(300).decode("utf-8", "replace")
                    if e.code in (401, 403) or "login_required" in body or "checkpoint" in body:
                        print(f"[정보] 인스타 조회수: 로그인이 만료됐거나 거부됨({browser}) {e.code} {body[:120]}")
                        if browser == "__login__":
                            IG_LOGIN["expired"] = True
                        raise
                    if attempt:
                        raise
                    time.sleep(1.5)
                except Exception:  # noqa: BLE001
                    if attempt:
                        raise
                    time.sleep(1.5)
        except Exception as e:  # noqa: BLE001
            print(f"[정보] 인스타 조회수 가져오기 실패({browser}): {type(e).__name__}: {str(e)[:160]}")
    return None, ("expired" if IG_LOGIN.get("expired") else "error") if tried_login else "login"


def stats_with_views(info, url, cookies_browser):
    st = video_stats(info)
    if st["views"] is None and "instagram.com" in url:
        st["views"], reason = ig_play_count(url, cookies_browser)
        if st["views"] is None and reason:
            st["views_reason"] = reason  # login: 인스타 로그인 안 함 / expired: 다시 로그인 필요 / error: 일시 오류
    return st


def fetch_meta(url, cookies_browser):
    cmd = yt_dlp_cmd() + ["--no-playlist", "--no-warnings", "--skip-download", "-j"]
    p, err = run_with_login(cmd, url, lambda _p: bool(_p.stdout.strip()), cookies_browser)
    if p is None:
        raise RuntimeError("영상 정보를 가져오지 못했어요." + login_hint(err) + "\n" + err[-400:])
    info = json.loads(p.stdout.strip().splitlines()[-1])
    return {"stats": stats_with_views(info, url, cookies_browser), "duration": info.get("duration")}


# 레퍼런스·대본 데이터: 브라우저가 아니라 이 컴퓨터 파일에 저장 (프로그램/브라우저 어디서 열어도 같은 데이터)
DATA_DIR = HERE.parent / "data"
STATE_FILE = DATA_DIR / "state.json"
_state_lock = threading.Lock()


def read_state():
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def write_state(data):
    DATA_DIR.mkdir(exist_ok=True)
    with _state_lock:
        tmp = STATE_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        if STATE_FILE.exists():  # 바로 전 버전 하나는 백업으로 남김
            shutil.copy2(STATE_FILE, DATA_DIR / "state.backup.json")
        os.replace(tmp, STATE_FILE)


def export_state():
    import datetime
    downloads = Path.home() / "Downloads"
    downloads.mkdir(exist_ok=True)
    dst = downloads / f"reels-abc-{datetime.date.today().isoformat()}.json"
    dst.write_text(json.dumps(read_state(), ensure_ascii=False, indent=2), encoding="utf-8")
    return str(dst)


# 원본 영상(구간 재생용): 처음 재생할 때 한 번만 받아서 보관
MEDIA_DIR = HERE.parent / "media"
_video_lock = threading.Lock()


def ensure_video(url, cookies_browser):
    """원본 영상을 받아 media/ 에 보관. (경로, 영상 정보) 반환. 이미 있으면 다시 받지 않음."""
    import hashlib
    MEDIA_DIR.mkdir(exist_ok=True)
    url = url.split("?")[0] if "instagram.com" in url else url
    name = hashlib.sha1(url.encode()).hexdigest()[:16] + ".mp4"
    dst = MEDIA_DIR / name
    info_path = MEDIA_DIR / (name[:-4] + ".info.json")
    with _video_lock:
        if not dst.exists():
            cmd = yt_dlp_cmd() + [
                "--no-playlist", "--no-warnings", "--write-info-json",
                "-f", "b[ext=mp4][height<=1080]/bv*[height<=720][ext=mp4]+ba[ext=m4a]/b[ext=mp4]/bv*[height<=720]+ba/b",
                "--merge-output-format", "mp4", "-o", str(MEDIA_DIR / (name[:-4] + ".%(ext)s")),
            ]
            p, err = run_with_login(cmd, url, lambda _p: dst.exists(), cookies_browser)
            if p is None:
                raise RuntimeError("영상을 받지 못했어요." + login_hint(err) + "\n" + err[-400:])
    info = {}
    if info_path.exists():
        try:
            info = json.loads(info_path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            pass
    return dst, info


def login_hint(err):
    e = err.lower()
    if "certain audiences" in e or "isn't available" in e or "private" in e:
        return " (나이·지역 제한이나 비공개 릴스라서 인스타에 로그인해야 볼 수 있어요. 크롬 등 브라우저에서 인스타에 로그인한 뒤 다시 가져와 주세요.)"
    if "login" in e or "cookie" in e or "rate" in e:
        return " (인스타 로그인이 필요해요. 브라우저에서 인스타에 로그인한 뒤 다시 가져와 주세요.)"
    return ""


# 로그인해야 보이는 릴스(나이·지역 제한, 비공개 계정 등): 컴퓨터에 깔린 브라우저의 인스타 로그인으로 자동 재시도
AUTO_BROWSERS = (["firefox", "edge", "whale", "chrome", "brave"] if os.name == "nt"
                 else ["chrome", "whale", "edge", "brave", "firefox"])
_good_browser = {"name": ""}


# ---- 프로그램 전용 인스타 로그인 창
# Windows 크롬·엣지는 저장된 로그인을 다른 프로그램이 못 읽게 잠가둠(앱 바운드 암호화) → 브라우저 로그인을 빌릴 수 없음.
# 대신 이 프로그램 전용 브라우저 창(별도 프로필)을 띄워 거기서 인스타에 로그인하게 하고,
# 창 안의 로그인 정보를 브라우저 개발자 연결(CDP)로 직접 받아 data/ig_cookies.txt 에 저장. 로그인 정보는 인스타 외에는 보내지 않음.
IG_COOKIES = Path(__file__).resolve().parent.parent / "data" / "ig_cookies.txt"
IG_PROFILE = Path(__file__).resolve().parent.parent / "data" / "ig_login_profile"
IG_CDP_PORT = 9223
IG_LOGIN = {"state": "idle", "proc": None, "expired": False}  # idle | waiting | done | error


def ig_logged_in():
    try:
        return "\tsessionid\t" in IG_COOKIES.read_text(encoding="utf-8")
    except OSError:
        return False


def login_browser():
    """로그인 창으로 쓸 브라우저 실행 파일 (Windows는 엣지가 항상 있음)."""
    if os.name == "nt":
        cands = [Path(os.environ.get(v, "")) / "Microsoft" / "Edge" / "Application" / "msedge.exe" for v in ("ProgramFiles(x86)", "ProgramFiles", "LOCALAPPDATA")]
        cands += [Path(os.environ.get(v, "")) / "Google" / "Chrome" / "Application" / "chrome.exe" for v in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA")]
        cands += [Path(os.environ.get(v, "")) / "Naver" / "Naver Whale" / "Application" / "whale.exe" for v in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA")]
    else:
        cands = [Path(p) for p in ("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                                   "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
                                   "/Applications/Whale.app/Contents/MacOS/Whale",
                                   "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser")]
    for c in cands:
        if str(c) not in ("", ".") and c.is_file():
            return str(c)
    return None


def _ws_call(ws_url, method, params=None):
    """아주 작은 웹소켓 클라이언트: CDP 명령 하나 보내고 결과 받기 (표준 기능만 사용)."""
    import base64
    import socket
    import struct
    from urllib.parse import urlparse as _up
    u = _up(ws_url)
    sock = socket.create_connection((u.hostname, u.port), timeout=10)
    try:
        key = base64.b64encode(os.urandom(16)).decode()
        sock.sendall((f"GET {u.path} HTTP/1.1\r\nHost: {u.hostname}:{u.port}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                      f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n").encode())
        buf = b""
        while b"\r\n\r\n" not in buf:
            chunk = sock.recv(4096)
            if not chunk:
                raise RuntimeError("연결 끊김")
            buf += chunk
        head, rest = buf.split(b"\r\n\r\n", 1)
        if b" 101 " not in head.split(b"\r\n")[0]:
            raise RuntimeError("웹소켓 연결 실패")
        payload = json.dumps({"id": 1, "method": method, "params": params or {}}).encode()
        mask = os.urandom(4)
        n = len(payload)
        hdr = bytes([0x81]) + (bytes([0x80 | n]) if n < 126 else bytes([0x80 | 126]) + struct.pack(">H", n) if n < 65536 else bytes([0x80 | 127]) + struct.pack(">Q", n))
        sock.sendall(hdr + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(payload)))

        def read(k):
            nonlocal rest
            while len(rest) < k:
                chunk = sock.recv(65536)
                if not chunk:
                    raise RuntimeError("연결 끊김")
                rest += chunk
            out, rest = rest[:k], rest[k:]
            return out

        msg = b""
        while True:
            b1, b2 = read(2)
            ln = b2 & 0x7F
            if ln == 126:
                ln = struct.unpack(">H", read(2))[0]
            elif ln == 127:
                ln = struct.unpack(">Q", read(8))[0]
            data = read(ln)
            op = b1 & 0x0F
            if op in (0x1, 0x0):
                msg += data
                if b1 & 0x80:
                    obj = json.loads(msg)
                    if obj.get("id") == 1:
                        return obj.get("result", {})
                    msg = b""
            elif op == 0x8:
                raise RuntimeError("연결 닫힘")
    finally:
        sock.close()


def _cdp_browser_ws():
    import urllib.request
    with urllib.request.urlopen(f"http://127.0.0.1:{IG_CDP_PORT}/json/version", timeout=3) as r:
        return json.load(r)["webSocketDebuggerUrl"]


def save_ig_cookies(cookies):
    """CDP 쿠키 목록 → yt-dlp가 읽는 cookies.txt (Netscape 형식)."""
    lines = ["# Netscape HTTP Cookie File"]
    for c in cookies:
        dom = c.get("domain", "")
        if "instagram.com" not in dom:
            continue
        exp = int(c.get("expires") or 0)
        lines.append("\t".join([dom, "TRUE" if dom.startswith(".") else "FALSE", c.get("path", "/"),
                                 "TRUE" if c.get("secure") else "FALSE", str(max(exp, 0)), c["name"], c["value"]]))
    IG_COOKIES.parent.mkdir(exist_ok=True)
    IG_COOKIES.write_text("\n".join(lines) + "\n", encoding="utf-8")
    _ig_cookie_cache.pop("__login__", None)


def ig_login_watch():
    """로그인 창이 열려 있는 동안 2초마다 확인 → 로그인되면 저장하고 창 닫기."""
    import time as _t
    deadline = _t.time() + 15 * 60
    while _t.time() < deadline:
        _t.sleep(2)
        proc = IG_LOGIN["proc"]
        try:
            ws = _cdp_browser_ws()
            cookies = _ws_call(ws, "Storage.getCookies").get("cookies", [])
        except Exception:  # noqa: BLE001
            if proc is not None and proc.poll() is not None:
                break  # 사용자가 로그인 안 하고 창을 닫음
            continue
        if any(c.get("name") == "sessionid" and "instagram.com" in c.get("domain", "") and c.get("value") for c in cookies):
            save_ig_cookies(cookies)
            IG_LOGIN["state"] = "done"
            IG_LOGIN["expired"] = False
            print("[정보] 인스타 로그인 저장 완료")
            _t.sleep(1.5)
            try:
                _ws_call(_cdp_browser_ws(), "Browser.close")
            except Exception:  # noqa: BLE001
                pass
            return
    IG_LOGIN["state"] = "done" if ig_logged_in() else "idle"
    if proc is not None and proc.poll() is None:
        proc.terminate()


def start_ig_login():
    exe = login_browser()
    if not exe:
        raise RuntimeError("로그인 창을 띄울 브라우저(엣지·크롬·웨일)를 찾지 못했어요.")
    if IG_LOGIN["state"] == "waiting" and IG_LOGIN["proc"] is not None and IG_LOGIN["proc"].poll() is None:
        return  # 이미 열려 있음
    IG_PROFILE.mkdir(parents=True, exist_ok=True)
    IG_LOGIN["proc"] = subprocess.Popen([
        exe, f"--user-data-dir={IG_PROFILE}", f"--remote-debugging-port={IG_CDP_PORT}", "--remote-allow-origins=*",
        "--no-first-run", "--no-default-browser-check", "--disable-sync", "--window-size=480,760",
        "--app=https://www.instagram.com/accounts/login/",
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    IG_LOGIN["state"] = "waiting"
    threading.Thread(target=ig_login_watch, daemon=True).start()


def cookie_attempts(cookies_browser):
    """yt-dlp에 붙일 로그인 옵션 후보들. 설정한 브라우저(없으면 로그인 없이) → 지난번 성공한 브라우저 → 나머지."""
    order = [cookies_browser or ""]
    for b in [_good_browser["name"]] + AUTO_BROWSERS:
        if b and b not in order:
            order.append(b)
    tries = [(b, ["--cookies-from-browser", b] if b else []) for b in order]
    if ig_logged_in():  # 프로그램 전용 로그인 창으로 로그인해 뒀으면 그걸 가장 먼저
        tries.insert(1 if not cookies_browser else 0, ("__login__", ["--cookies", str(IG_COOKIES)]))
    return tries


def run_with_login(cmd_head, url, ok, cookies_browser):
    """cmd_head + 로그인옵션 + url 실행. ok(p)가 참이면 성공. 실패하면 브라우저 로그인으로 차례로 재시도."""
    first_err = ""
    for b, extra in cookie_attempts(cookies_browser):
        p = subprocess.run(cmd_head + extra + [url], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300, creationflags=NO_WINDOW)
        if p.returncode == 0 and ok(p):
            if b and b != "__login__":
                _good_browser["name"] = b
            return p, ""
        err = p.stderr or p.stdout or ""
        if not first_err:
            first_err = err
            if "instagram.com" not in url and "facebook.com" not in url:
                break  # 유튜브·틱톡 등은 로그인 재시도 안 함
        if b == "" and "unsupported url" in err.lower():
            break
    return None, first_err


# 3) 화면 맨 위 타이틀 자막 읽기
#    Mac: Apple Vision / Windows: 한국어 전용 모델(RapidOCR PP-OCRv5) → 안 되면 Windows 내장 OCR
#    + 받아쓴 대본과 대조해서 잘못 읽은 글자 보정
TOP_CROP = 0.45  # 화면 위쪽 45%만 읽음


def frame_texts(png):
    """Mac Vision: [(글자, 위쪽 끝(0~1, 아래가 0), 높이, 왼쪽, 확신도)]"""
    import Quartz
    import Vision
    from Foundation import NSURL
    src = Quartz.CGImageSourceCreateWithURL(NSURL.fileURLWithPath_(str(png)), None)
    img = Quartz.CGImageSourceCreateImageAtIndex(src, 0, None)
    req = Vision.VNRecognizeTextRequest.alloc().init()
    req.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
    req.setRecognitionLanguages_(["ko-KR", "en-US"])
    req.setUsesLanguageCorrection_(True)
    Vision.VNImageRequestHandler.alloc().initWithCGImage_options_(img, None).performRequests_error_([req], None)
    out = []
    for o in req.results() or []:
        b = o.boundingBox()
        c = o.topCandidates_(1)[0]
        out.append((c.string().strip(), b.origin.y + b.size.height, b.size.height, b.origin.x, float(c.confidence())))
    return out


_rapid = None


def rapid_engine():
    global _rapid
    if _rapid is None:
        from rapidocr import LangRec, ModelType, OCRVersion, RapidOCR
        _rapid = RapidOCR(params={
            "Rec.lang_type": LangRec.KOREAN, "Rec.ocr_version": OCRVersion.PPOCRV5, "Rec.model_type": ModelType.MOBILE,
        })
    return _rapid


def rapid_texts(crop_png):
    """한국어 전용 모델로 (위쪽만 잘라낸) 이미지 읽기 → 전체 화면 좌표로 변환."""
    r = rapid_engine()(str(crop_png))
    if r.boxes is None or r.txts is None:
        return []
    import cv2
    hc, wc = cv2.imread(str(crop_png)).shape[:2]
    out = []
    for box, text, score in zip(r.boxes, r.txts, r.scores):
        ys = [float(pt[1]) for pt in box]
        xs = [float(pt[0]) for pt in box]
        top = 1 - TOP_CROP * (min(ys) / hc)
        h = TOP_CROP * (max(ys) - min(ys)) / hc
        out.append((str(text).strip(), top, h, min(xs) / wc, float(score)))
    return out


def crop_top(ffmpeg, png, scale=1):
    c = png.with_name(png.stem + f"_top{scale}.png")
    vf = f"crop=iw:ih*{TOP_CROP}:0:0" + (f",scale=iw*{scale}:-1:flags=lanczos" if scale != 1 else "")
    subprocess.run([ffmpeg, "-loglevel", "error", "-y", "-i", str(png), "-vf", vf, str(c)],
                   capture_output=True, timeout=60, creationflags=NO_WINDOW)
    return c if c.exists() else None


def win_builtin_texts(pngs, ffmpeg):
    """Windows 내장 OCR (한국어 모델을 못 쓸 때). 위쪽만 잘라 2배로 키워서 읽음."""
    crops = {p: crop_top(ffmpeg, p, 2) for p in pngs} if ffmpeg else {}
    targets = [crops.get(p) or p for p in pngs]
    ps = shutil.which("powershell") or "powershell"
    r = subprocess.run([ps, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(HERE / "ocr_win.ps1"), *map(str, targets)],
                       capture_output=True, timeout=120, creationflags=NO_WINDOW)
    out = {p: [] for p in pngs}
    by_name = {str(crops.get(p) or p): p for p in pngs}
    for line in r.stdout.decode("utf-8", "ignore").splitlines():
        line = line.strip().lstrip("﻿")
        if not line.startswith("{"):
            continue
        try:
            d = json.loads(line)
            orig = by_name[d["file"]]
            top, h = float(d["top"]), float(d["h"])
            if crops.get(orig):
                top, h = 1 - TOP_CROP * (1 - top), TOP_CROP * h
            # 내장 OCR은 확신도를 주지 않음 → 보정 대상이 되도록 낮게
            out[orig].append((d["text"].strip(), top, h, float(d.get("left", 0)), 0.6))
        except Exception:  # noqa: BLE001
            pass
    return out


def frames_texts(pngs):
    """여러 장의 글자 인식 결과: {png: [(글자, 위쪽 끝, 높이, 왼쪽, 확신도)]}"""
    if sys.platform == "darwin":
        try:
            import Vision  # noqa: F401
            return {p: frame_texts(p) for p in pngs}
        except ImportError:
            pass
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:
        try:  # 한국어 전용 모델
            out = {}
            for p in pngs:
                c = crop_top(ffmpeg, p)
                out[p] = rapid_texts(c) if c else []
            return out
        except Exception as e:  # noqa: BLE001
            print(f"[정보] 한국어 글자 인식 모델 사용 실패 → Windows 기본 기능으로: {e}")
    if os.name == "nt":
        return win_builtin_texts(pngs, ffmpeg)
    return {}


# --- 받아쓴 대본과 대조해서 보정 ---
def _jamo(s):
    """한글을 자모로 풀어서 비교 (네프리 ↔ 넷플릭스 처럼 비슷한 글자를 가깝게 봄)."""
    out = []
    for ch in s:
        code = ord(ch) - 0xAC00
        if 0 <= code < 11172:
            out += [chr(0x1100 + code // 588), chr(0x1161 + (code % 588) // 28)]
            if code % 28:
                out.append(chr(0x11A7 + code % 28))
        elif ch.strip():
            out.append(ch.lower())
    return out


_HANGUL = re.compile(r"[가-힣]")


def _plain(t):
    return re.sub(r"[^0-9A-Za-z가-힣]", "", t)


def _ratio(a, b):
    import difflib
    return difflib.SequenceMatcher(None, _jamo(a), _jamo(b)).ratio()


def refine_lines(ordered, transcript):
    """타이틀 줄들을 대본과 대조해서 다듬음.
    - 대본과 글자가 똑같으면 대본의 띄어쓰기로
    - 비슷하면(확신도 낮은 줄) 대본 구절로 교체
    - 그래도 이상한 줄은 옆 줄을 기준으로 대본 앞뒤 구절에서 찾고, 못 찾으면 버림"""
    words = [w for w in (transcript or "").split()][:150]
    wplain = [_plain(w) for w in words]

    def spans(maxlen=8):
        for i in range(len(words)):
            for j in range(i, min(i + maxlen, len(words))):
                yield i, j + 1

    def text_of(i, j):
        return re.sub(r"[.,!?]+$", "", " ".join(words[i:j]))

    out = []
    for e in ordered:
        e = dict(e, match=None)
        tp = _plain(e["text"])
        if words and tp:
            # 1) 글자가 똑같은 구절 → 띄어쓰기만 대본대로
            for i, j in spans():
                if "".join(wplain[i:j]) == tp:
                    e["text"], e["match"], e["conf"] = text_of(i, j), (i, j), 1.0
                    break
            # 2) 확신도가 낮으면 가장 비슷한 구절로
            if e["match"] is None and e["conf"] < 0.9:
                best, br = None, 0.0
                for i, j in spans():
                    cand = "".join(wplain[i:j])
                    if not (len(tp) - 3 <= len(cand) <= len(tp) + 4):
                        continue
                    r = _ratio(tp, cand)
                    if r > br:
                        best, br = (i, j), r
                if best and br >= 0.62:
                    e["text"], e["match"], e["conf"] = text_of(*best), best, 0.95
        out.append(e)
    # 3) 이상한 줄: 바로 아래/위 줄이 대본에서 찾아졌으면 그 앞/뒤 구절에서 찾음
    for k, e in enumerate(out):
        if e["match"] is not None or e["conf"] >= 0.8 or not words:
            continue
        tp = _plain(e["text"])
        cands = []
        if k + 1 < len(out) and out[k + 1]["match"]:
            s0 = out[k + 1]["match"][0]
            cands += [(i, s0) for i in range(max(0, s0 - 4), s0)]
        if k > 0 and out[k - 1]["match"]:
            e0 = out[k - 1]["match"][1]
            cands += [(e0, j) for j in range(e0 + 1, min(len(words), e0 + 4) + 1)]
        best, br = None, 0.0
        for i, j in cands:
            r = _ratio(tp, "".join(wplain[i:j]))
            # 타이틀 윗줄은 보통 말의 첫머리 → 문장 시작에서 시작하는 구절에 가산점
            if i == 0 or re.search(r"[.?!]$", words[i - 1]):
                r += 0.1
            if r > br:
                best, br = (i, j), r
        if best and br >= 0.35:
            e["text"], e["match"], e["conf"] = text_of(*best), best, 0.9
    # 4) 끝까지 확신이 없는 줄은 버림
    return [e for e in out if e["conf"] >= 0.75]


def screen_title(video_path, transcript=""):
    """영상 앞부분 프레임에서 화면 위쪽의 큰 글자 중 계속 떠 있는 줄 = 타이틀 자막."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return ""
    seen = {}
    frames = 0
    with tempfile.TemporaryDirectory(prefix="reels-title-") as tmp:
        pngs = []
        for t in (0.3, 1.0, 2.0, 3.0):
            png = Path(tmp) / f"f{t}.png"
            subprocess.run([ffmpeg, "-loglevel", "error", "-y", "-ss", str(t), "-i", str(video_path), "-frames:v", "1", str(png)],
                           capture_output=True, timeout=60, creationflags=NO_WINDOW)
            if png.exists():
                pngs.append(png)
        results = frames_texts(pngs)
    for png in pngs:
        if png not in results:
            continue
        frames += 1
        for text, top, h, left, conf in results[png]:
            if top < 1 - TOP_CROP or len(text) < 2:
                continue
            # 프레임마다 "실패확률...." / "실패 확률:" 처럼 다르게 읽혀도 같은 줄로 보도록 글자만 남겨 비교
            key = re.sub(r"[^0-9A-Za-z가-힣]", "", text)
            if len(key) < 2:
                continue
            clean = re.sub(r"[^0-9A-Za-z가-힣\s?!%·,&+<>\-]", "", text)
            clean = re.sub(r"\s+", " ", clean).strip(" .,:·-")
            e = seen.setdefault(key, {"text": clean, "top": top, "h": h, "left": left, "conf": conf, "n": 0})
            e["n"] += 1
            e["h"] = max(e["h"], h)
            if conf > e["conf"]:
                e["text"], e["conf"] = clean, conf
    if not seen:
        return ""
    # 1) 여러 프레임에 계속 떠 있는 줄만 (화면 속 소품·스쳐가는 글자 제외)
    need = 2 if frames >= 2 else 1
    steady = [e for e in seen.values() if e["n"] >= need] or list(seen.values())
    # 2) 한국어 타이틀이면 배경의 영문 간판·책 제목 같은 글자는 제외
    if any(_HANGUL.search(e["text"]) for e in steady):
        steady = [e for e in steady if _HANGUL.search(e["text"])]
    # 3) 그중 가장 큰 글자의 70% 이상 크기만 = 타이틀
    max_h = max(e["h"] for e in steady)
    lines = [e for e in steady if e["h"] >= max(0.03, max_h * 0.7)]
    # 4) 위 → 아래, 같은 줄(높이가 비슷)은 왼쪽 → 오른쪽 순서로
    lines.sort(key=lambda e: -e["top"])
    rows = []
    for e in lines:
        if rows and abs(rows[-1][0]["top"] - e["top"]) < 0.6 * max(e["h"], rows[-1][0]["h"]):
            rows[-1].append(e)
        else:
            rows.append([e])
    ordered = [e for row in rows for e in sorted(row, key=lambda e: e["left"])]
    # 5) 받아쓴 대본과 대조해서 잘못 읽은 글자 보정
    ordered = refine_lines(ordered, transcript)
    return " ".join(e["text"] for e in ordered)[:80]

def download_audio(url, workdir, cookies_browser):
    out = str(Path(workdir) / "audio.%(ext)s")
    base = yt_dlp_cmd() + [
        "--no-playlist", "--no-warnings", "-f", "bestaudio/best",
        "-x", "--audio-format", "wav", "--postprocessor-args", "ffmpeg:-ar 16000 -ac 1",
        "--print-json", "-o", out,
    ]
    p, err = run_with_login(base, url, lambda _p: bool(list(Path(workdir).glob("audio*.wav"))), cookies_browser)
    if p is None:
        raise RuntimeError("영상을 받지 못했어요." + login_hint(err) + "\n" + err[-800:])
    info = {}
    for line in p.stdout.splitlines():
        line = line.strip()
        if line.startswith("{"):
            try:
                info = json.loads(line)
            except json.JSONDecodeError:
                pass
    return list(Path(workdir).glob("audio*.wav"))[0], info


# ---------------------------------------------------------------- Claude (선택)

def claude_client():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return None
    try:
        import anthropic
    except ImportError:
        return None
    return anthropic.Anthropic()


def claude_json(prompt, schema):
    client = claude_client()
    if client is None:
        raise RuntimeError("AI 기능을 쓰려면 ANTHROPIC_API_KEY 와 anthropic 패키지가 필요합니다.")
    params = dict(
        model=CLAUDE_MODEL,
        max_tokens=16000,
        output_config={"effort": "medium", "format": {"type": "json_schema", "schema": schema}},
        messages=[{"role": "user", "content": prompt}],
    )
    try:
        # 안전 분류기가 거절하면 서버가 다른 모델로 자동 재시도
        resp = client.beta.messages.create(
            betas=["server-side-fallback-2026-07-01"], fallbacks="default", **params
        )
    except TypeError:
        # 구버전 SDK(fallbacks 미지원)
        resp = client.beta.messages.create(**params)
    if resp.stop_reason == "refusal":
        raise RuntimeError("AI가 이 요청을 처리하지 않았습니다.")
    text = next(b.text for b in resp.content if b.type == "text")
    return json.loads(text)


SPLIT_SCHEMA = {
    "type": "object",
    "properties": {
        "units": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "label": {"type": "string", "enum": ["hook", "body", "cta"]},
                    "section_start": {"type": "boolean"},
                    "section_title": {"type": "string"},
                },
                "required": ["label", "section_start", "section_title"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["units"],
    "additionalProperties": False,
}


def ai_split(segments):
    numbered = "\n".join(f"{i}. {s['text']}" for i, s in enumerate(segments))
    prompt = f"""아래는 인스타그램 릴스 대본을 문장(또는 호흡) 단위로 나눈 것이다. 각 줄을 hook / body / cta 로 분류하고, body는 내용 단위 섹션으로 나눠라.

정의:
- hook: 스크롤을 멈추게 하는 도입부 (질문, 충격적 사실, 결과 먼저, 공감 유발). 보통 맨 앞 1~3줄.
- body: 실제 정보·스토리·근거·방법.
- cta: 행동 유도와, 그 행동을 하게 만드는 '예고/미끼' 문장까지 전부 포함한다.
  예) 아래 세 줄은 모두 cta 다:
    이 외에도 S&P500보다 수익 많이 내는 ETF들
    특징 주의사항 다 정리했으니까
    댓글에 5 적어줘.
  즉 "이 외에도 / 나머지는 / 더 자세한 건 / 다 정리했으니까 / 보내줄게" 같은 연결·예고 문장이 마지막 행동 요청(댓글, 팔로우, 저장, 공유, 프로필 링크, DM 등) 앞에 붙어 있으면 그것도 cta 다.
- 순서는 반드시 hook → body → cta 연속 구간. CTA가 없으면 cta 없이 끝나도 된다.

body 섹션:
- body 안에서 다루는 항목/단계/포인트가 바뀌는 첫 줄에 section_start=true, section_title에 그 섹션을 3~10자로 요약 (예: "1번 ETF QQQM", "주의사항", "실제 수익 비교").
- body의 첫 줄은 항상 section_start=true.
- hook/cta 줄은 section_start=false, section_title="".
- units 배열 길이는 정확히 {len(segments)}개, 입력 순서 그대로.

대본:
{numbered}"""
    data = claude_json(prompt, SPLIT_SCHEMA)
    units = data["units"][: len(segments)]
    units += [{"label": "body", "section_start": False, "section_title": ""}] * (len(segments) - len(units))
    return {"units": units}


COMPOSE_SCHEMA = {
    "type": "object",
    "properties": {
        "hook": {"type": "string"},
        "body": {"type": "string"},
        "cta": {"type": "string"},
        "notes": {"type": "string"},
    },
    "required": ["hook", "body", "cta", "notes"],
    "additionalProperties": False,
}


def ai_compose(parts, topic, tone):
    blocks = []
    for p in parts:
        sub = f" ({p['sectionTitle']})" if p.get("sectionTitle") else ""
        blocks.append(f"[{p['group']} 레퍼런스 · {p['section'].upper()}{sub} · 출처: {p.get('title') or '제목없음'}]\n{p['text']}")
    prompt = f"""나는 릴스를 A+B=C 구조로 기획한다. 여러 레퍼런스(A, B, C …)에서 골라낸 후킹/본문/CTA 조각을 재료로, 새로운 릴스 대본 C를 써라.

규칙:
- 레퍼런스 문장을 그대로 베끼지 말고, 구조·리듬·심리 장치(후킹 방식, 전개 방식, CTA 방식)를 가져와 내 주제에 맞게 새로 쓴다.
- 재료는 사용자가 문장 단위로 직접 고른 것이다. 고른 순서와 본문 섹션 구성을 최대한 살린다.
- CTA는 '예고/미끼 문장 + 행동 요청'(예: 이 외에도 ~ 다 정리했으니까 댓글에 5 적어줘) 구조를 유지한다.
- 선택된 섹션이 없는 부분은 다른 재료의 흐름에 맞춰 자연스럽게 채운다.
- 말로 읽는 대본이므로 짧은 구어체 문장, 한 줄에 한 호흡.
- notes에는 어떤 레퍼런스의 어떤 장치를 가져왔는지 2~4줄로 설명.

내 주제: {topic or '(주제 미지정 — 레퍼런스 주제를 조합해 자연스럽게)'}
톤: {tone or '레퍼런스와 비슷하게'}

재료:
""" + "\n\n".join(blocks)
    return claude_json(prompt, COMPOSE_SCHEMA)


# ---------------------------------------------------------------- HTTP

class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(WEB_DIR), **kw)

    def end_headers(self):
        self.send_header("Cache-Control", "no-cache")  # 업데이트한 UI가 바로 반영되도록
        super().end_headers()

    def log_message(self, fmt, *args):
        origin = self.headers.get("Origin") if hasattr(self, "headers") and self.headers else None
        ua = (self.headers.get("User-Agent") or "")[-40:] if hasattr(self, "headers") and self.headers else ""
        extra = f" origin={origin} ua=…{ua}" if origin else ""
        sys.stderr.write("[helper] " + (fmt % args) + extra + "\n")

    def _origin_ok(self):
        origin = self.headers.get("Origin")
        return origin is None or origin in CONFIG["allowed_origins"]

    def _cors(self):
        origin = self.headers.get("Origin")
        if origin and origin in CONFIG["allowed_origins"]:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.send_header("Access-Control-Allow-Private-Network", "true")

    def _json(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204 if self._origin_ok() else 403)
        self._cors()
        self.end_headers()

    def do_GET(self):
        if self.path.startswith("/api/health"):
            if not self._origin_ok():
                return self._json(403, {"error": "허용되지 않은 사이트입니다. helper/config.json 의 allowed_origins 에 추가하세요."})
            return self._json(200, {
                "ok": True,
                "engine": ENGINE,
                "model": CONFIG["model"],
                "language": CONFIG["language"],
                "ai": claude_client() is not None,
                "cookies_from_browser": CONFIG["cookies_from_browser"],
            })
        if self.path.startswith("/api/webversion"):
            files = [WEB_DIR / n for n in ("index.html", "app.js", "style.css")]
            return self._json(200, {"version": str(int(max(f.stat().st_mtime for f in files if f.exists())))})
        if self.path.startswith("/api/iglogin"):
            return self._json(200, {"state": IG_LOGIN["state"], "loggedIn": ig_logged_in()})
        if self.path.startswith("/api/progress"):
            from urllib.parse import parse_qs
            q = parse_qs(urlparse(self.path).query)
            return self._json(200, {"stage": PROGRESS.get((q.get("url") or [""])[0], "")})
        if self.path.startswith("/api/state"):
            if not self._origin_ok():
                return self._json(403, {"error": "forbidden"})
            return self._json(200, read_state())
        if self.path.startswith("/media/"):
            return self.serve_media()
        return super().do_GET()

    def serve_media(self):
        """영상 파일 전송 — 원하는 구간으로 건너뛸 수 있게 Range 요청 지원."""
        name = urlparse(self.path).path.rsplit("/", 1)[-1]
        f = MEDIA_DIR / name
        if not re.fullmatch(r"[0-9a-f]{16}\.mp4", name) or not f.exists():
            self.send_error(404)
            return
        size = f.stat().st_size
        start, end = 0, size - 1
        m = re.match(r"bytes=(\d*)-(\d*)", self.headers.get("Range") or "")
        if m:
            if m.group(1):
                start = int(m.group(1))
                if m.group(2):
                    end = min(int(m.group(2)), size - 1)
            elif m.group(2):
                start = max(0, size - int(m.group(2)))
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        else:
            self.send_response(200)
        self.send_header("Content-Type", "video/mp4")
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(end - start + 1))
        self.end_headers()
        with open(f, "rb") as fh:
            fh.seek(start)
            left = end - start + 1
            try:
                while left > 0:
                    chunk = fh.read(min(256 * 1024, left))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    left -= len(chunk)
            except (BrokenPipeError, ConnectionResetError):
                pass

    def do_POST(self):
        if not self._origin_ok():
            return self._json(403, {"error": "허용되지 않은 사이트입니다. helper/config.json 의 allowed_origins 에 추가하세요."})
        try:
            length = int(self.headers.get("Content-Length") or 0)
            data = json.loads(self.rfile.read(length) or b"{}")
            route = urlparse(self.path).path
            if route == "/api/state":
                write_state(data)
                return self._json(200, {"ok": True})
            if route == "/api/shutdown":  # 업데이트 설치 때 파일을 바꿀 수 있도록 스스로 종료
                self._json(200, {"ok": True})
                threading.Thread(target=lambda: (__import__("time").sleep(0.3), os._exit(0)), daemon=True).start()
                return
            if route == "/api/iglogin":  # 프로그램 전용 인스타 로그인 창 열기
                start_ig_login()
                return self._json(200, {"state": IG_LOGIN["state"]})
            if route == "/api/iglogout":
                IG_COOKIES.unlink(missing_ok=True)
                shutil.rmtree(IG_PROFILE, ignore_errors=True)
                _ig_cookie_cache.clear()
                IG_LOGIN["state"] = "idle"
                return self._json(200, {"ok": True})
            if route == "/api/export":
                return self._json(200, {"path": export_state()})
            if route == "/api/open":
                import webbrowser
                if re.match(r"^https?://", data.get("url", "")):
                    webbrowser.open(data["url"])
                return self._json(200, {"ok": True})
            if route == "/api/transcribe":
                return self._json(200, self.transcribe(data))
            cookies = data.get("cookies_from_browser", CONFIG["cookies_from_browser"])
            if route == "/api/meta":
                return self._json(200, fetch_meta(data["url"], cookies))
            if route == "/api/video":
                return self._json(200, {"src": "/media/" + ensure_video(data["url"], cookies)[0].name})
            if route == "/api/title":
                video, _ = ensure_video(data["url"], cookies)
                return self._json(200, {"screen_title": screen_title(video, data.get("transcript", "")), "video": "/media/" + video.name})
            if route == "/api/split":
                return self._json(200, ai_split(data["segments"]))
            if route == "/api/compose":
                return self._json(200, ai_compose(data["parts"], data.get("topic", ""), data.get("tone", "")))
            return self._json(404, {"error": "not found"})
        except Exception as e:  # noqa: BLE001
            import traceback
            traceback.print_exc()
            return self._json(500, {"error": str(e)})

    def transcribe(self, data):
        url = (data.get("url") or "").strip()
        if not re.match(r"^https?://", url):
            raise RuntimeError("올바른 링크가 아닙니다.")
        model = data.get("model") or CONFIG["model"]
        language = data.get("language") or CONFIG["language"]
        cookies = data.get("cookies_from_browser", CONFIG["cookies_from_browser"])
        import time
        t0 = time.time()
        PROGRESS[url] = "download"
        video, info = ensure_video(url, cookies)
        t1 = time.time()
        PROGRESS[url] = "transcribe"
        with tempfile.TemporaryDirectory(prefix="reels-abc-") as tmp:
            wav = Path(tmp) / "audio.wav"
            subprocess.run([shutil.which("ffmpeg") or "ffmpeg", "-loglevel", "error", "-y", "-i", str(video),
                            "-vn", "-ar", "16000", "-ac", "1", str(wav)], capture_output=True, timeout=120, creationflags=NO_WINDOW)
            if not wav.exists():
                if ENGINE == "faster-whisper":
                    wav = video  # ffmpeg가 막혀도 영상에서 소리를 바로 읽을 수 있음 (Windows)
                else:
                    wav, info = download_audio(url, tmp, cookies)
            segments, lang = transcribe_audio(wav, model, language)
        t2 = time.time()
        PROGRESS[url] = "title"
        try:
            title_text = screen_title(video, " ".join(seg["text"] for seg in segments))
        except Exception as e:  # noqa: BLE001
            print(f"[정보] 타이틀 자막 읽기 실패: {e}")
            title_text = ""
        print(f"[시간] 영상 {t1 - t0:.1f}s / 받아쓰기 {t2 - t1:.1f}s / 타이틀 {time.time() - t2:.1f}s")
        return {
            "url": url,
            "title": info.get("title") or info.get("description", "")[:60],
            "uploader": info.get("uploader") or info.get("channel") or "",
            "duration": info.get("duration"),
            "thumbnail": info.get("thumbnail"),
            "caption": info.get("description") or "",
            "stats": stats_with_views(info, url, cookies),
            "screen_title": title_text,
            "video": "/media/" + video.name,
            "language": lang,
            "model": model,
            "segments": segments,
        }


def warm_up():
    """1초짜리 무음으로 한 번 돌려서 모델을 메모리에 올려둠."""
    try:
        import wave
        tmp = Path(tempfile.gettempdir()) / "reels-abc-warmup.wav"
        with wave.open(str(tmp), "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000); w.writeframes(b"\x00\x00" * 16000)
        t = time.time()
        if ENGINE == "faster-whisper":
            # Windows: 모델만 올림 (무음을 받아쓰면 CPU에서 몇 분씩 걸려 첫 추출이 그만큼 기다리게 됨)
            with _model_lock:
                fw_model(resolve_model(CONFIG["model"]))
        else:
            transcribe_audio(tmp, CONFIG["model"], "ko")
        print(f"[정보] 받아쓰기 모델 준비 완료 ({time.time() - t:.1f}s)")
    except Exception as e:  # noqa: BLE001
        print(f"[정보] 모델 미리 올리기 실패(첫 추출 때 올림): {e}")


def main():
    try:
        sys.stdout.reconfigure(line_buffering=True)
        sys.stderr.reconfigure(line_buffering=True)
    except Exception:  # noqa: BLE001
        pass
    if ENGINE is None:
        print("[오류] whisper 엔진이 설치되지 않았습니다. 설치 명령을 다시 실행하세요.")
    port = int(os.environ.get("PORT", CONFIG["port"]))
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    try:  # 지우기·업데이트 때 이 프로세스만 정확히 끄도록 번호 기록
        (HERE.parent / "helper.pid").write_text(str(os.getpid()))
    except OSError:
        pass
    threading.Thread(target=warm_up, daemon=True).start()
    print(f"✅ 릴스 A+B=C 헬퍼 실행 중: http://127.0.0.1:{port}")
    print(f"   전사 엔진: {ENGINE} / 모델: {CONFIG['model']} / AI: {'켜짐' if claude_client() else '꺼짐'}")
    print(f"   허용된 사이트: {', '.join(CONFIG['allowed_origins'])}")
    print("   종료하려면 Ctrl+C")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
