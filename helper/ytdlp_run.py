# yt-dlp 실행기: 컴퓨터가 믿는 인증서를 쓰도록 한 뒤 yt-dlp 실행 (백신·회사망 인증서 대응)
try:
    import truststore
    truststore.inject_into_ssl()
except Exception:  # noqa: BLE001
    pass
import yt_dlp

yt_dlp.main()
