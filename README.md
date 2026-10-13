# 릴스 A+B=C 기획기

A 레퍼런스 + B 레퍼런스 → 후킹/본문/CTA로 쪼개고 → 골라서 C 대본을 만드는 도구.

## 구조

```
[배포된 웹사이트 (Vercel)]  ──fetch──▶  [각자 컴퓨터의 로컬 헬퍼 127.0.0.1:8765]
  화면·조합·저장(브라우저)               yt-dlp 다운로드 → whisper large-v3 전사
                                          (선택) Claude로 자동 분리·C 생성
```

- 영상/음성은 **각자 컴퓨터 밖으로 나가지 않음** (전사도 로컬)
- 레퍼런스·C 데이터는 **각자 브라우저에 저장** (설정 탭에서 내보내기/가져오기)
- 헬퍼가 웹 UI도 같이 띄우므로 배포 없이 `http://127.0.0.1:8765` 로만 써도 됨

## 사용자 (팀원) 설치 — 복사·붙여넣기 한 번 → 프로그램 설치

사이트 → 설정 탭에 나오는 명령을 복사해서 붙여넣고 Enter.

- Mac (터미널): `curl -fsSL https://reels-abc.vercel.app/install.sh | bash`
- Windows (PowerShell): `irm https://reels-abc.vercel.app/install.ps1 | iex`

Python·Homebrew·ffmpeg 미리 설치 필요 없음 (uv가 파이썬을, imageio-ffmpeg가 ffmpeg를 가져옴).
`~/ReelsExtractor`에 설치되고 로그인할 때 자동 실행(Mac: LaunchAgent `app.reelsabc.helper`, Windows: 시작프로그램 `ReelsExtractor.vbs`).
프로그램: Mac은 `~/Applications/릴스 A+B=C.app`(pywebview 창, 바탕화면 바로가기), Windows는 시작 메뉴·바탕화면 바로가기(Edge `--app` 창). 데이터는 `~/ReelsExtractor/data/state.json`(직전 버전은 state.backup.json).
같은 명령을 다시 실행하면 최신 버전으로 업데이트. AI 기능은 `~/ReelsExtractor/helper/.env`에 `ANTHROPIC_API_KEY` 입력.

## 배포 (관리자)

```bash
./scripts/build-zip.sh          # web/reels-abc-helper.zip 생성
cd web && npx vercel deploy --prod --yes     # web 폴더만 정적 배포 (https://reels-abc.vercel.app)
```

배포 전 `web/.env.local`이 생겨 있으면 지울 것 (vercel link가 만드는 토큰 파일, .vercelignore로도 막아둠).

## 정확도 관련

- 기본 모델 `large-v3` (whisper 최고 정확도). 설정에서 `large-v3-turbo`(빠름)로 바꿀 수 있음
- "한국어 우선": 언어 자동 감지 후 한국어면 한국어 고정 + 숏폼 구어체 힌트로 전사, 외국어 영상이면 그 언어로 전사
- 반복 환각 방지(`condition_on_previous_text=False`, 무음 구간 환각 억제) 적용
- 오탈자는 레퍼런스 카드에서 문장을 클릭해 바로 수정
