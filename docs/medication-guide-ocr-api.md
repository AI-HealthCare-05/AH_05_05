# 조제약 복약안내 OCR API 명세 안내

이 문서 경로에서 관리하던 동기 OCR 계약은 `2026-08-27`부로 폐기됐다.
현재 서버는 업로드 요청에서 OCR 결과를 즉시 반환하지 않고, 비동기 작업을 생성한 뒤 상태 조회와 사용자 확정을 거친다.

최신 서버 계약은 [`medication-guide-ocr-api-spec-v1.md`](medication-guide-ocr-api-spec-v1.md)를 기준으로 한다.

## 현재 공개 API

| Method | Path | 성공 응답 | 역할 |
| --- | --- | --- | --- |
| `POST` | `/api/v1/ocr` | `202 Accepted` | 이미지 검증 및 OCR 작업 생성 |
| `GET` | `/api/v1/ocr/jobs/{ocrJobId}` | `200 OK` | 작업 상태와 검토 결과 조회 |
| `GET` | `/api/v1/ocr/jobs/{ocrJobId}/image` | `200 OK` | 인증된 원본 JPEG/PNG binary 조회 |
| `GET` | `/api/v1/ocr/jobs/{ocrJobId}/processed-image` | `200 OK` | 인증된 전처리 JPEG binary 조회 |
| `PATCH` | `/api/v1/ocr/jobs/{ocrJobId}` | `200 OK` | 사용자 검토 결과 확정 및 RDB 저장 |

업로드와 두 이미지 조회는 10초 HTTP 제한 시간(`@api_timeout(10)`: 라우트 데코레이터 아래)을 사용하고, 상태 조회·확정은 공통 3초 제한을 사용한다. 제한 시간 초과는 `504`와 `{"code":"API_TIMEOUT","message":"요청 처리 시간이 초과되었습니다."}`를 반환한다. OCR worker의 전처리·CLOVA·조건부 LLM·검증은 비동기 작업이므로 이 HTTP 제한 시간과 별개다.

`200 OK`로 정규화 결과를 즉시 반환하던 동기 호출 방식, `/documents/*`, 별도 `/confirm` 경로는 현재 서버 계약이 아니다.

Swagger는 `/api/docs`, OpenAPI JSON은 `/api/openapi.json`에서 확인한다.
