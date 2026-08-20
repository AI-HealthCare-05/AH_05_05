from app.core.email.backends import EmailBackend, build_backend

# jwt/state.py 와 같은 방식으로 모듈 로드 시 한 번만 만든다.
email_backend: EmailBackend = build_backend()
