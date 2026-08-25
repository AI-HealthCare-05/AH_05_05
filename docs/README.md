# 실행 방법

## 백엔드

저장소 루트 [`README.md`](../README.md) 참고 (uv · docker compose).

## 프론트엔드

```bash
cd frontend
pnpm install
pnpm dev
```

- **`/dev/gallery`** — 컴포넌트 전체
- **`/dev/document-upload`** — 여기서 시작하면 만들어진 화면을 순서대로 지나갑니다

백엔드를 띄우지 않아도 목업 데이터로 끝까지 돕니다.
실제 서버에 붙이려면 `frontend/.env.local` 에 `VITE_USE_MOCK=false` 를 넣으세요.
`vite` 가 `/api` 요청을 `http://127.0.0.1:8000` 으로 프록시하므로 CORS 설정은 필요 없습니다.

조제약 OCR의 현재 비동기 API·DB 저장·worker 계약은
[`medication-guide-ocr-api-spec-v1.md`](medication-guide-ocr-api-spec-v1.md)를 참고하세요. 실서버 OCR 흐름에는
FastAPI뿐 아니라 `ocr-worker`도 필요합니다.

팀원이 로컬에서 처음 실행할 때는 [조제약 OCR 로컬 실행 가이드](ocr/README.md)를 순서대로 따라가세요.

```bash
docker compose up -d mysql redis fastapi ocr-worker
```

폴더 구조·색·컴포넌트 규칙은 [`frontend/README.md`](../frontend/README.md) 에 있습니다.

## 설치·빌드가 막힐 때

**`Cannot find module 'react'` 가 IDE에서만 뜬다**
WSL에서 `pnpm install` 하고 Windows IDE로 편집하는 조합입니다.
`frontend/pnpm-workspace.yaml` 의 `nodeLinker: hoisted` 로 해결해뒀습니다.
`pnpm config get node-linker` 가 `hoisted` 로 나오는지 확인하세요.
대신 의존성 격리가 약해지므로 **새 패키지는 꼭 `pnpm add`** 로 선언하세요.

**`ERR_PNPM_MINIMUM_RELEASE_AGE_VIOLATION`**
pnpm 11부터 배포된 지 24시간이 안 된 패키지를 거부합니다(공급망 공격 방어).
전이 의존성이 방금 배포됐을 때 걸립니다. `frontend/pnpm-workspace.yaml` 의
`minimumReleaseAgeExclude` 에 해당 패키지 이름만 추가하세요.
**`minimumReleaseAge` 를 0으로 낮추거나 정책을 끄지 마세요.**

**`ERR_PNPM_IGNORED_BUILDS: esbuild`**
`pnpm approve-builds` 로 esbuild를 승인하세요.

**WSL과 PowerShell을 번갈아 쓰면 깨진다**
`node_modules` 의 esbuild 바이너리가 OS별로 다릅니다. 한쪽만 정해서 쓰세요.

## 이 폴더에 있는 것

`sample-docs/` — OCR 테스트용 가상 진료문서 14장
(환자 2명 × 문서 3~4종 × 깔끔한 버전 / 그늘지고 잘린 버전).
확인해야 할 항목은 [`sample-docs/README.md`](sample-docs/README.md) 에 있습니다.

## 기획 · 진행 상황

요구사항정의서, API 명세, ERD, Figma, 진행 상황은 팀 노션에서 관리합니다.
