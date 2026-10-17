#!/bin/bash
# 릴스 A+B=C 추출기 설치 (Mac)
#   curl -fsSL https://reels-abc.vercel.app/install.sh | bash
# 다시 실행하면 최신 버전으로 업데이트된다. 컴퓨터를 켜면 자동으로 실행된다.
set -e

BASE="${REELS_BASE:-https://reels-abc.vercel.app}"
DIR="${REELS_DIR:-$HOME/ReelsExtractor}"
LABEL="app.reelsabc.helper"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"

say() { printf "\n\033[1m%s\033[0m\n" "$1"; }
fail() { printf "\n\033[31m❌ %s\033[0m\n" "$1"; exit 1; }

say "🎬 릴스 추출기 설치를 시작할게요 (5~10분, 처음 한 번만)"

# 1) uv: 파이썬을 알아서 받아주는 도구 (관리자 권한 필요 없음)
export PATH="${UV_INSTALL_DIR:-$HOME/.local/bin}:$PATH"
if ! command -v uv >/dev/null 2>&1; then
  say "① 준비 도구 설치 중…"
  curl -LsSf https://astral.sh/uv/install.sh | UV_NO_MODIFY_PATH=1 sh >/dev/null 2>&1 || fail "준비 도구 설치에 실패했어요. 인터넷 연결을 확인해 주세요."
fi

# 2) 추출기 파일 받기
say "② 추출기 받는 중…"
TMP="$(mktemp -d)"
curl -fsSL "$BASE/reels-abc-helper.zip" -o "$TMP/h.zip" || fail "추출기를 받지 못했어요. 인터넷 연결을 확인해 주세요."
unzip -q "$TMP/h.zip" -d "$TMP"
mkdir -p "$DIR"
rsync -a "$TMP/reels-abc-helper/helper/" "$DIR/helper/"
rsync -a --delete "$TMP/reels-abc-helper/web/" "$DIR/web/"
rm -rf "$TMP"
cd "$DIR"
[ -f helper/.env ] || cp helper/.env.example helper/.env

# 3) 파이썬 + 패키지
say "③ 필요한 프로그램 설치 중…"
[ -x .venv/bin/python ] || uv venv -q --python 3.12 .venv || fail "파이썬 설치에 실패했어요."
if [ "$(uname -m)" = "arm64" ]; then REQ=helper/requirements-mac.txt; else REQ=helper/requirements.txt; fi
uv pip install -q --python .venv/bin/python -U -r "$REQ" || fail "프로그램 설치에 실패했어요."

# 4) 받아쓰기 모델 (한 번만, 약 3GB)
say "④ 받아쓰기 모델 내려받는 중 (약 3GB — 인터넷 속도에 따라 몇 분 걸려요)…"
if [ "$(uname -m)" = "arm64" ]; then
  .venv/bin/python -c "from huggingface_hub import snapshot_download as d; d('mlx-community/whisper-large-v3-mlx')"
else
  .venv/bin/python -c "import truststore; truststore.inject_into_ssl(); from faster_whisper import WhisperModel as W; W('large-v3', device='cpu', compute_type='int8')"
fi

# 5) 컴퓨터 켤 때 자동 실행 + 지금 바로 실행
if [ -z "$REELS_NO_AUTOSTART" ]; then
  say "⑤ 자동 실행 설정 중…"
  mkdir -p "$HOME/Library/LaunchAgents"
  cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key><array>
    <string>$DIR/.venv/bin/python</string>
    <string>$DIR/helper/server.py</string>
  </array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>$DIR/helper/helper.log</string>
  <key>StandardErrorPath</key><string>$DIR/helper/helper.log</string>
</dict></plist>
EOF
  launchctl bootout "gui/$(id -u)/$LABEL" >/dev/null 2>&1 || true
  # 이전에 직접 켜 둔 추출기가 있으면 정리
  pkill -f "helper/server.py" >/dev/null 2>&1 || true
  sleep 1
  launchctl bootstrap "gui/$(id -u)" "$PLIST"

  for i in $(seq 1 60); do
    curl -fs http://127.0.0.1:8765/api/health >/dev/null 2>&1 && break
    sleep 1
  done
  curl -fs http://127.0.0.1:8765/api/health >/dev/null 2>&1 || fail "추출기가 켜지지 않았어요. $DIR/helper/helper.log 내용을 알려주세요."
fi

# 6) 프로그램 만들기: 응용 프로그램 폴더의 "릴스 A+B=C.app" + 바탕화면 바로가기
APP="$HOME/Applications/릴스 A+B=C.app"
if [ -z "$REELS_NO_AUTOSTART" ]; then
  say "⑥ 프로그램 만드는 중…"
  rm -rf "$APP"
  mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
  cp "$DIR/helper/assets/icon.icns" "$APP/Contents/Resources/icon.icns"
  cat > "$APP/Contents/Info.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleName</key><string>릴스 A+B=C</string>
  <key>CFBundleDisplayName</key><string>릴스 A+B=C</string>
  <key>CFBundleIdentifier</key><string>app.reelsabc.app</string>
  <key>CFBundleExecutable</key><string>launcher</string>
  <key>CFBundleIconFile</key><string>icon</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>1.0</string>
  <key>LSMinimumSystemVersion</key><string>11.0</string>
  <key>NSHighResolutionCapable</key><true/>
  <key>CFBundleURLTypes</key><array><dict>
    <key>CFBundleURLName</key><string>app.reelsabc.open</string>
    <key>CFBundleURLSchemes</key><array><string>reelsabc</string></array>
  </dict></array>
</dict></plist>
EOF
  cat > "$APP/Contents/MacOS/launcher" <<EOF
#!/bin/bash
exec "$DIR/.venv/bin/python" "$DIR/helper/app_window.py"
EOF
  chmod +x "$APP/Contents/MacOS/launcher"
  /System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister -f "$APP" >/dev/null 2>&1 || true
  # 예전 바로가기(사이트 링크) 정리하고 프로그램 바로가기로
  rm -f "$HOME/Desktop/릴스 A+B=C.webloc"
  [ -d "$HOME/Desktop" ] && ln -sfn "$APP" "$HOME/Desktop/릴스 A+B=C"
fi

say "✅ 설치 끝! '릴스 A+B=C' 프로그램이 열려요."
echo "   다음부터는 응용 프로그램 폴더나 바탕화면의 '릴스 A+B=C'를 실행하세요."
echo "   (Dock에 고정하려면 실행 중인 아이콘을 우클릭 → 옵션 → Dock에 유지)"
echo "   이 창은 닫아도 돼요."
[ -z "$REELS_NO_AUTOSTART" ] && open "$APP" >/dev/null 2>&1 || true
