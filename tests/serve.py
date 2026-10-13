# 테스트용: 설치 파일을 Vercel과 똑같이 UTF-8 텍스트로 내보내는 간단한 서버
import http.server, sys, functools
H = http.server.SimpleHTTPRequestHandler
H.extensions_map.update({".ps1": "text/plain; charset=utf-8", ".sh": "text/plain; charset=utf-8"})
http.server.ThreadingHTTPServer(("127.0.0.1", 8000), functools.partial(H, directory=sys.argv[1])).serve_forever()
