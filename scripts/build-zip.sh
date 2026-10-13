#!/bin/zsh
# 배포 전에 실행: 헬퍼 배포용 zip 을 web/ 안에 만든다 (사이트에서 다운로드 가능하게)
cd "$(dirname "$0")/.."
rm -f web/reels-abc-helper.zip
TMP=$(mktemp -d)
mkdir -p $TMP/reels-abc-helper
rsync -a --exclude '.env' --exclude '.env.local' --exclude '.vercel' --exclude '.vercelignore' --exclude '.gitignore' --exclude '__pycache__' --exclude '*.zip' helper web README.md $TMP/reels-abc-helper/
(cd $TMP && zip -qr reels-abc-helper.zip reels-abc-helper)
mv $TMP/reels-abc-helper.zip web/
rm -rf $TMP
echo "✅ web/reels-abc-helper.zip 생성"
