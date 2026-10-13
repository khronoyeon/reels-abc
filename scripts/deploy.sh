#!/bin/zsh
# 사이트(설치 안내 + 설치 파일) 배포.
# 저장소 안에서 바로 배포하면 Vercel이 커밋 작성자 권한 문제로 막기 때문에, 사이트 파일만 임시 폴더에 복사해서 배포한다.
set -e
cd "$(dirname "$0")/.."
./scripts/build-zip.sh
TMP=$(mktemp -d)
rsync -a --exclude '.env*' --exclude '.gitignore' web/ "$TMP/"
(cd "$TMP" && npx -y vercel@latest deploy --prod --yes)
rm -rf "$TMP"
