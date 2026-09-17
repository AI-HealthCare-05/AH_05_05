FROM python:3.13-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    build-essential \
    python3-dev \
    libffi-dev \
    redis-server \
    supervisor \
    && rm -rf /var/lib/apt/lists/*

# 1. uv 설치 (공식 이미지에서 복사해오는 가장 깔끔한 방법)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# 2. 의존성 패키지 관리 파일을 컨테이너 내부에 복사합니다.
COPY pyproject.toml uv.lock ./

# 3. pyproject.toml에 명시된 의존성 패키지 중에서 'app' 그룹만 설치합니다.
RUN uv sync --group app --no-dev --frozen

# 4. 로컬 소스 코드를 컨테이너 내부로 복사합니다.
COPY ./app ./app
COPY ./ai_worker ./ai_worker
COPY ./data/reference_seed ./data/reference_seed
# Report RAG checks provenance against manifests; raw PDFs are not shipped.
COPY ./data/knowledge/manifests/sources.yaml ./data/knowledge/manifests/sources.yaml
COPY ./data/knowledge/manifests/documents.jsonl ./data/knowledge/manifests/documents.jsonl

RUN mkdir -p /run/ocr-images /run/ocr-runtime

# 5. API, OCR worker, private image Redis를 supervisord 아래에서 함께 실행합니다.
# venv Python으로 직접 진입해야 combined 런처의 exec 이후 supervisord가 PID 1이 됩니다.
CMD ["/app/.venv/bin/python", "-m", "app.runtime.combined"]
