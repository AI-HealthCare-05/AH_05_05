FROM python:3.13-slim

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

COPY pyproject.toml uv.lock ./

# 공공 PDF 인덱싱 Worker에는 app 그룹이 필요하지 않습니다.
# redis는 기본 dependencies, RAG 관련 패키지는 ai 그룹에 있습니다.
RUN uv sync --group ai --no-dev --frozen

COPY ./ai_worker ./ai_worker
COPY ./data/public_guidelines ./data/public_guidelines

CMD ["uv", "run", "--no-sync", "python", "-m", "ai_worker.main"]
