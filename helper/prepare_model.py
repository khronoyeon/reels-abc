# 받아쓰기 모델 준비 (설치 때 실행): 1) 받기 — 끊겨도 이어받기·재시도  2) 메모리에 올려보기
# 실패하면 왜 안 됐는지 쉬운 말로 알려줌. 사용: python prepare_model.py download|load [모델이름]
import os
import shutil
import sys
import time
import warnings

# 모델 파일은 허깅페이스의 새 전송 방식(Xet, 별도 네이티브 엔진)으로 오는데, 일부 Windows PC에서 이 엔진이
# 오류 메시지 없이 꺼짐 → 일반 다운로드로 받음 (속도 비슷, 끊기면 이어받기 됨)
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")  # Windows 바로가기 경고 숨김 (동작엔 지장 없음)
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
os.environ.setdefault("HF_HUB_VERBOSITY", "error")  # "로그인 안 하고 받는 중" 같은 영어 경고 숨김
warnings.filterwarnings("ignore")
try:  # 백신·회사망 인증서가 있는 PC 대응
    import truststore
    truststore.inject_into_ssl()
except Exception:  # noqa: BLE001
    pass

REPOS = {
    "large-v3-turbo": "mobiuslabsgmbh/faster-whisper-large-v3-turbo",
    "large-v3": "Systran/faster-whisper-large-v3",
}
FILES = ["config.json", "preprocessor_config.json", "model.bin", "tokenizer.json", "vocabulary.*"]


def say(msg):
    print("   " + msg, flush=True)


def why(e):
    t = f"{type(e).__name__}: {e}"
    low = t.lower()
    if "certificate" in low or "ssl" in low or "인증서" in t:
        return "보안 프로그램(백신·회사망)이 연결을 막았어요. 잠시 백신의 '웹 보호/HTTPS 검사'를 끄고 다시 실행해 보세요."
    if "no space" in low or "errno 28" in low or "디스크" in t:
        return "C 드라이브 공간이 부족해요. 3GB 이상 비우고 다시 실행해 주세요."
    if "permission" in low or "access is denied" in low or "액세스" in t:
        return "보안 프로그램이 파일 저장을 막았어요. 백신에서 이 설치를 허용하고 다시 실행해 주세요."
    if "timed out" in low or "timeout" in low or "connect" in low or "resolve" in low or "network" in low:
        return "인터넷 연결이 불안정해요. 다른 와이파이로 바꾸거나 잠시 뒤 다시 실행해 주세요."
    if "memory" in low or "bad_alloc" in low:
        return "컴퓨터 메모리(RAM)가 부족해요. 다른 프로그램을 모두 끄고 다시 실행해 주세요."
    return "알 수 없는 오류예요. 이 창을 캡처해서 보내주세요."


def download(model):
    from huggingface_hub import snapshot_download
    home = os.path.expanduser("~")
    free = shutil.disk_usage(home).free / 1e9
    if free < 3:
        say(f"[문제] 저장 공간이 {free:.1f}GB 남았어요. 3GB 이상 필요해요.")
        sys.exit(2)
    last = None
    for attempt in range(1, 6):
        try:
            path = snapshot_download(REPOS[model], allow_patterns=FILES)
            size = sum(os.path.getsize(os.path.join(path, f)) for f in os.listdir(path)) / 1e9
            say(f"받기 완료 ({size:.1f}GB)")
            return
        except Exception as e:  # noqa: BLE001
            last = e
            say(f"받기가 끊겼어요 — 이어서 다시 받을게요 ({attempt}/5)")
            time.sleep(3 * attempt)
    say("[문제] " + why(last))
    say(f"(자세한 내용: {type(last).__name__}: {str(last)[:300]})")
    sys.exit(3)


def load(model):
    try:
        from faster_whisper import WhisperModel
        WhisperModel(model, device="cpu", compute_type="int8", cpu_threads=os.cpu_count() or 4, local_files_only=True)
        say("받아쓰기 기능 확인 완료")
    except Exception as e:  # noqa: BLE001
        say("[문제] " + why(e))
        say(f"(자세한 내용: {type(e).__name__}: {str(e)[:300]})")
        sys.exit(4)


def reset(model):
    """받다 만(깨졌을 수 있는) 모델 파일 지우기 → 새로 받기 전에."""
    from huggingface_hub import constants
    for repo in (REPOS[model], "dropbox-dash/faster-whisper-large-v3-turbo"):
        d = os.path.join(constants.HF_HUB_CACHE, "models--" + repo.replace("/", "--"))
        shutil.rmtree(d, ignore_errors=True)
    say("받았던 파일을 지우고 새로 받을게요")


if __name__ == "__main__":
    mode = sys.argv[1]
    name = sys.argv[2] if len(sys.argv) > 2 else "large-v3-turbo"
    {"download": download, "load": load, "reset": reset}[mode](name)
