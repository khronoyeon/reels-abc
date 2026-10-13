#!/usr/bin/env python3
"""릴스 A+B=C 프로그램 창 (Mac).

브라우저 없이 자기 창으로 앱을 띄운다. 추출기(server.py)는 로그인할 때 자동으로 켜져 있지만,
꺼져 있으면 여기서 켠다.
"""
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
URL = "http://127.0.0.1:8765"
APP_NAME = "릴스 A+B=C"


def helper_up():
    try:
        with urllib.request.urlopen(URL + "/api/health", timeout=2) as r:
            return json.load(r).get("ok", False)
    except Exception:  # noqa: BLE001
        return False


def ensure_helper():
    if helper_up():
        return True
    if sys.platform == "darwin":  # 자동 실행 서비스를 깨움
        subprocess.run(["launchctl", "kickstart", f"gui/{__import__('os').getuid()}/app.reelsabc.helper"], capture_output=True)
    for _ in range(40):
        if helper_up():
            return True
        time.sleep(0.5)
    # 서비스가 없으면 직접 켬
    subprocess.Popen([sys.executable, str(HERE / "server.py")], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        if helper_up():
            return True
        time.sleep(0.5)
    return False


def brand_mac_app():
    """메뉴 막대·Dock에 'Python' 대신 앱 이름과 아이콘이 보이도록."""
    try:
        from AppKit import NSApplication, NSImage
        from Foundation import NSBundle
        info = NSBundle.mainBundle().localizedInfoDictionary() or NSBundle.mainBundle().infoDictionary()
        if info is not None:
            info["CFBundleName"] = APP_NAME
        icon = NSImage.alloc().initWithContentsOfFile_(str(HERE / "assets" / "icon.icns"))
        if icon:
            NSApplication.sharedApplication().setApplicationIconImage_(icon)
    except Exception:  # noqa: BLE001
        pass


def main():
    import webview

    brand_mac_app()
    ok = ensure_helper()
    target = URL if ok else "data:text/html;charset=utf-8," + (
        "<body style='font-family:-apple-system;padding:40px;color:#191f28'>"
        "<h2>추출기가 켜지지 않았어요</h2><p>설치 명령을 다시 실행해 주세요.</p></body>")
    webview.create_window(
        APP_NAME, target, width=1480, height=920, min_size=(900, 600), background_color="#F2F4F6",
    )
    data_dir = HERE.parent / "data" / "webview"
    data_dir.mkdir(parents=True, exist_ok=True)
    webview.start(private_mode=False, storage_path=str(data_dir), user_agent=None)


if __name__ == "__main__":
    main()
