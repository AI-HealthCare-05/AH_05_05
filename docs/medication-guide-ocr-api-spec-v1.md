# 조제약 복약안내 OCR API 명세서

- 문서 버전: `v1.0`
- 작성일: `2026-08-25`
- 담당 범위: 조제약 복약안내 이미지 OCR 업로드, 비동기 처리, 검토, 확정 저장
- 기준 구현: `825/AH_05_05`
- Base URL: `/api/v1`
- Swagger: `/api/docs`
- OpenAPI JSON: `/api/openapi.json`

> 이 문서는 OCR 담당 파트의 신규 명세다. 기존 `docs/medication-guide-ocr-api.md` 및 기존 기획 문서는
> 수정하거나 삭제하지 않는다. 현재 실행 코드, Swagger/OpenAPI, 프론트 실 API 연결 결과를 기준으로 작성했다.

---

## 공통 처리 흐름

```text
이미지 선택
  → OCR 작업 생성
  → queued / processing 동안 2초 polling
  → ready_for_review 결과 표시
  → 사용자 수정·추가·삭제
  → 최종 결과 한 번에 확정
  → CareEpisode 1행 + Medication N행 저장
```

- 모든 API는 로그인 사용자의 Bearer 인증이 필요하다.
- 다른 사용자의 OCR 작업은 존재 여부를 노출하지 않고 `404 OCR_JOB_NOT_FOUND`로 처리한다.
- OCR 완료 전에는 `CareEpisode`와 `Medication`을 생성하지 않는다.
- 사용자가 최종 저장할 때만 하나의 DB 트랜잭션으로 RDB에 저장한다.
- 사용자가 약 상세를 열거나 수정하지 않아도 OCR이 추출한 `efficacy`, `administration`,
  `precautions`를 프론트가 그대로 보존하여 확정 요청에 포함한다.
- 공개 API는 `/api/v1/ocr/*`만 사용한다. `/documents/*` 또는 별도 `/confirm` 엔드포인트는 사용하지 않는다.

### 인증 헤더

```http
Authorization: Bearer <access-token>
```

### 공통 오류 응답

```json
{
  "code": "OCR_JOB_NOT_FOUND",
  "message": "OCR 작업을 찾을 수 없습니다."
}
```

검증 위치에 따라 `field`가 추가될 수 있다.

```json
{
  "code": "VALIDATION_ERROR",
  "message": "요청값을 확인해주세요.",
  "field": "medications.0.name"
}
```

---

## 1. API 이름: 조제약 복약안내 OCR 작업 생성

### 기본 정보

| 항목 | 값 |
|---|---|
| Method | `POST` |
| URL | `/api/v1/ocr/medication-guides` |
| Content-Type | `multipart/form-data` |
| 인증 | Bearer 필수 |
| 성공 상태 | `202 Accepted` |
| 설명 | 조제약 복약안내 이미지 한 장을 검증하고 비동기 OCR 대기열에 등록한다. |

### 요청 헤더

| 헤더 | 필수 | 형식 | 설명 |
|---|---:|---|---|
| `Authorization` | O | `Bearer <access-token>` | 로그인 사용자 인증 토큰 |
| `Idempotency-Key` | O | 8~100자 문자열 | 중복 클릭·네트워크 재시도로 같은 작업이 여러 개 생기는 것을 방지 |

프론트 권장 생성 방식:

```ts
const idempotencyKey = `ocr-${crypto.randomUUID()}`;
```

- 같은 `File` 객체를 재시도할 때는 같은 키를 재사용한다.
- 같은 사용자·키·파일이면 기존 OCR 작업을 반환한다.
- 같은 사용자·키로 다른 파일을 보내면 `409 IDEMPOTENCY_CONFLICT`를 반환한다.
- UUID는 백엔드가 발급하는 값이 아니라 프론트가 요청 직전에 생성한다.

### 요청 본문

| 필드 | 타입 | 필수 | 제약 |
|---|---|---:|---|
| `file` | binary | O | JPG 또는 PNG 한 장 |

파일 검증 규칙:

- 허용 MIME: `image/jpeg`, `image/png`
- 확장자, MIME, 실제 파일 시그니처가 일치해야 한다.
- 파일 최대 크기: 50 MiB
- multipart 전체 최대 크기: 51 MiB
- 최대 가로·세로: 각각 10,000px
- 최대 디코딩 픽셀: 40,000,000px
- 빈 파일, 손상된 이미지, 다른 형식은 허용하지 않는다.

### 성공 응답

```json
{
  "batchId": "b_123",
  "documentIds": [123],
  "ocrStatus": "queued"
}
```

| 필드 | 타입 | 설명 |
|---|---|---|
| `batchId` | string | 화면 표시용 식별자. 현재 `b_{ocrJobId}` 형식 |
| `documentIds` | integer[] | 단일 이미지 흐름이므로 한 개의 OCR 작업 ID를 포함 |
| `ocrStatus` | string | 현재 작업 상태 |

후속 조회에는 `batchId`가 아니라 `documentIds[0]`을 사용한다.

```ts
const ocrJobId = response.documentIds[0];
```

예시에서는 후속 조회 URL이 `/api/v1/ocr/jobs/123`이다. `/api/v1/ocr/jobs/b_123`이 아니다.

### 오류 응답

| HTTP | code | 발생 조건 |
|---:|---|---|
| 401 | `AUTHENTICATION_REQUIRED`, `INVALID_TOKEN` | 인증 토큰 없음 또는 잘못된 토큰 |
| 409 | `IDEMPOTENCY_CONFLICT` | 같은 키로 다른 파일을 업로드 |
| 413 | `OCR_UPLOAD_TOO_LARGE` | multipart 요청 전체가 51 MiB 초과 |
| 422 | `VALIDATION_ERROR` | 헤더 또는 multipart 형식 검증 실패 |
| 422 | `INVALID_IMAGE` | 파일 형식, 실제 내용, 크기, 해상도 또는 디코딩 검증 실패 |
| 503 | `OCR_QUEUE_UNAVAILABLE` | 임시 파일 저장 또는 Redis/ARQ 대기열 등록 실패 |

---

## 2. API 이름: 조제약 복약안내 OCR 작업 상태 및 결과 조회

### 기본 정보

| 항목 | 값 |
|---|---|
| Method | `GET` |
| URL | `/api/v1/ocr/jobs/{ocrJobId}` |
| 인증 | Bearer 필수 |
| 성공 상태 | `200 OK` |
| 설명 | 비동기 OCR 작업 상태를 조회하고, 검토 가능한 상태에서 구조화된 결과를 반환한다. |

### Path Parameter

| 이름 | 타입 | 필수 | 설명 |
|---|---|---:|---|
| `ocrJobId` | integer | O | 작업 생성 응답의 `documentIds[0]` |

### 상태값

| 상태 | 의미 | 프론트 처리 |
|---|---|---|
| `queued` | OCR 대기열 등록 완료 | 2초 후 재조회 |
| `processing` | OCR 추출·구조화 진행 중 | 2초 후 재조회 |
| `ready_for_review` | 결과 검토·수정 가능 | 검토 화면 표시 |
| `complete` | 사용자 확정과 RDB 저장 완료 | 저장 완료 화면 표시 |
| `failed` | OCR 처리 실패 | 오류 안내 및 재업로드 제공 |
| `cancelled` | 미확정 작업 만료·취소 상태 | 재업로드 안내 |

### 응답 A: 대기 또는 처리 중

`queued`, `processing`, `cancelled` 상태에서는 아래 키만 반환한다.

```json
{
  "batchId": "b_123",
  "ocrStatus": "processing"
}
```

이 상태에서는 다음 키를 `null`이나 빈 배열로도 보내지 않는다.

```text
documentImageUrl
fields
medications
lowConfidenceCount
```

### 응답 B: 실패

```json
{
  "batchId": "b_123",
  "ocrStatus": "failed",
  "errorCode": "EXTRACTION_FAILED"
}
```

`errorCode`는 화면 메시지 분기와 운영 로그 확인에 사용하는 기계 판독용 코드다.

### 응답 C: 검토 가능 또는 확정 완료

```json
{
  "batchId": "b_123",
  "ocrStatus": "ready_for_review",
  "documentImageUrl": "/api/v1/ocr/jobs/123/image",
  "fields": {
    "dispensedDate": {
      "value": "2025-03-12",
      "confidence": "high"
    }
  },
  "medications": [
    {
      "tempId": "med-1",
      "name": "아세트아미노펜정",
      "dose": "500mg",
      "efficacy": "발열, 두통, 근육통 완화",
      "administration": "식후 30분에 물과 함께 복용하세요.",
      "precautions": "정해진 용법과 용량을 지키고 음주를 피하세요.",
      "timesPerDay": 3,
      "days": 3,
      "confidence": "high"
    }
  ],
  "lowConfidenceCount": 0
}
```

### 결과 필드 규칙

| 필드 | 타입 | 규칙 |
|---|---|---|
| `batchId` | string | `b_{ocrJobId}` 형식 |
| `ocrStatus` | string | `ready_for_review` 또는 `complete` |
| `documentImageUrl` | string | 인증이 필요한 원본 이미지 상대 URL |
| `fields.dispensedDate.value` | string \| null | `YYYY-MM-DD`. 읽지 못했거나 미래 날짜이면 `null` |
| `fields.dispensedDate.confidence` | string | `high`, `medium`, `low` |
| `medications` | array | OCR로 구조화한 약 목록 |
| `lowConfidenceCount` | integer | 조제일 및 약 블록 중 `low`인 항목 수. `medium`은 제외 |

### medications 항목 규칙

| 필드 | 타입 | 규칙 |
|---|---|---|
| `tempId` | string | 검토 화면의 임시 행 ID. RDB PK가 아님 |
| `name` | string | 약품명 |
| `dose` | string | 용량. 추출 실패 시 빈 문자열 |
| `efficacy` | string | 효능. 추출 실패 시 빈 문자열 |
| `administration` | string | 복용 방법. 추출 실패 시 빈 문자열 |
| `precautions` | string | 주의사항. 추출 실패 시 빈 문자열 |
| `timesPerDay` | integer \| null | 1~6. `null`은 필요 시 복용 또는 횟수 미확정 |
| `days` | integer \| null | 1~365. 읽지 못하면 `null` |
| `confidence` | string | `high`, `medium`, `low`. 사용자 추가 약의 완료 응답에서는 생략 가능 |

신뢰도 등급:

```text
high    confidence >= 0.99
medium  0.90 <= confidence < 0.99
low     confidence < 0.90 또는 needsReview=true
```

### 프론트 polling 규칙

```ts
if (ocrStatus === 'queued' || ocrStatus === 'processing') {
  window.setTimeout(poll, 2_000);
}
```

- `ready_for_review`, `complete`, `failed`, `cancelled`에서는 polling을 종료한다.
- OCR 소요 시간 자체에는 API 제한을 두지 않는다.
- 프론트가 장시간 안내를 보여주더라도 백엔드 작업을 임의로 실패 처리하지 않는다.

### 오류 응답

| HTTP | code | 발생 조건 |
|---:|---|---|
| 401 | `AUTHENTICATION_REQUIRED`, `INVALID_TOKEN` | 인증 실패 |
| 404 | `OCR_JOB_NOT_FOUND` | 작업 없음, 다른 사용자의 작업, 만료된 미확정 작업 |
| 422 | `VALIDATION_ERROR` | `ocrJobId` 형식 오류 |

---

## 3. API 이름: 조제약 복약안내 OCR 원본 이미지 조회

### 기본 정보

| 항목 | 값 |
|---|---|
| Method | `GET` |
| URL | `/api/v1/ocr/jobs/{ocrJobId}/image` |
| 인증 | Bearer 필수 |
| 성공 상태 | `200 OK` |
| 응답 형식 | `image/jpeg` 또는 `image/png` binary |
| 설명 | OCR 검토 화면과 저장 완료 기록에서 사용할 원본 이미지를 반환한다. |

### Path Parameter

| 이름 | 타입 | 필수 | 설명 |
|---|---|---:|---|
| `ocrJobId` | integer | O | 작업 생성 응답의 `documentIds[0]` |

### 성공 응답 헤더

```http
Content-Type: image/jpeg
Cache-Control: private, no-store
Content-Disposition: inline; filename="medication-guide"
X-Content-Type-Options: nosniff
```

### 프론트 사용 규칙

일반 `<img src>` 요청에는 Bearer 헤더를 넣을 수 없으므로 인증 `fetch`로 Blob을 받은 뒤 Blob URL을
화면에 사용한다.

```ts
const blob = await http.getBlob(`/v1/ocr/jobs/${ocrJobId}/image`);
const imageUrl = URL.createObjectURL(blob);
```

검토 화면을 떠나거나 저장을 완료하면 `URL.revokeObjectURL(imageUrl)`로 해제한다.

### 보존 규칙

- 원본 이미지는 공개 `/media` URL로 노출하지 않는다.
- API 서버와 OCR worker가 공유하는 private Docker volume에 저장한다.
- 실패하거나 만료된 미확정 작업의 이미지는 정리한다.
- 확정 완료한 작업의 이미지는 기록 화면에서 재사용할 수 있도록 보존한다.

### 오류 응답

| HTTP | code | 발생 조건 |
|---:|---|---|
| 401 | `AUTHENTICATION_REQUIRED`, `INVALID_TOKEN` | 인증 실패 |
| 404 | `OCR_JOB_NOT_FOUND` | 이미지·작업 없음 또는 다른 사용자의 작업 |
| 422 | `VALIDATION_ERROR` | `ocrJobId` 형식 오류 |

---

## 4. API 이름: 조제약 복약안내 OCR 결과 확정 및 RDB 저장

### 기본 정보

| 항목 | 값 |
|---|---|
| Method | `PATCH` |
| URL | `/api/v1/ocr/jobs/{ocrJobId}` |
| Content-Type | `application/json` |
| 인증 | Bearer 필수 |
| 성공 상태 | `200 OK` |
| 설명 | OCR 결과와 사용자 수정본을 한 번에 확정하고 RDB에 저장한다. |

### Path Parameter

| 이름 | 타입 | 필수 | 설명 |
|---|---|---:|---|
| `ocrJobId` | integer | O | `ready_for_review` 상태인 OCR 작업 ID |

### 요청 본문

약이 네 개면 `medications` 배열에 네 항목을 담아 PATCH를 한 번만 호출한다. 약마다 PATCH를 네 번
호출하지 않는다.

```json
{
  "dispensedDate": "2025-03-12",
  "medications": [
    {
      "tempId": "med-1",
      "name": "아세트아미노펜정",
      "dose": "500mg",
      "efficacy": "발열, 두통, 근육통 완화",
      "administration": "식후 30분에 물과 함께 복용하세요. 복용 간격은 4시간 이상 유지하세요.",
      "precautions": "정해진 용법과 용량을 지키고 음주를 피하세요.",
      "timesPerDay": 3,
      "days": 3
    },
    {
      "tempId": "med-2",
      "name": "세티리진정",
      "dose": "10mg",
      "efficacy": "알레르기성 비염, 재채기, 가려움 완화",
      "administration": "취침 전에 물과 함께 복용하세요.",
      "precautions": "졸음이 나타날 수 있으므로 운전과 음주를 피하세요.",
      "timesPerDay": 1,
      "days": 5
    },
    {
      "tempId": "med-3",
      "name": "암브록솔정",
      "dose": "30mg",
      "efficacy": "가래 배출 도움",
      "administration": "식후에 물과 함께 복용하고 충분한 수분을 섭취하세요.",
      "precautions": "속쓰림이나 메스꺼움이 심하면 상담하세요.",
      "timesPerDay": 3,
      "days": 5
    },
    {
      "tempId": "med-4",
      "name": "파모티딘정",
      "dose": "20mg",
      "efficacy": "속쓰림과 위산 과다 증상 완화",
      "administration": "아침과 저녁 식전에 물과 함께 복용하세요.",
      "precautions": "신장질환이 있으면 의사 또는 약사에게 알리고 임의로 증량하지 마세요.",
      "timesPerDay": 2,
      "days": 5
    }
  ]
}
```

### 요청 필드 규칙

| 필드 | 타입 | 필수 | 제약 및 의미 |
|---|---|---:|---|
| `dispensedDate` | string(date) | O | `YYYY-MM-DD`, 오늘보다 미래일 수 없음 |
| `medications` | array | O | 0~100개. 현재 화면의 최종 약 목록 전체 |
| `medications[].tempId` | string | O | 1~100자. 검토 행 매칭용, RDB PK로 저장하지 않음 |
| `medications[].name` | string | O | 1~255자 |
| `medications[].dose` | string | O | 최대 100자, 값이 없으면 빈 문자열 |
| `medications[].efficacy` | string | O | 최대 500자, 값이 없으면 빈 문자열 |
| `medications[].administration` | string | O | 최대 500자, 값이 없으면 빈 문자열 |
| `medications[].precautions` | string | O | 최대 500자, 값이 없으면 빈 문자열 |
| `medications[].timesPerDay` | integer \| null | X | 1~6 또는 `null`. 생략 시 `null`, 확정된 `null`은 필요 시 복용 |
| `medications[].days` | integer \| null | X | 1~365 또는 `null`. 생략 시 `null` |

### 미수정 OCR 필드 보존 규칙

프론트는 `GET`에서 받은 약 객체 전체를 화면 상태로 유지한다. 사용자가 특정 약을 열어보지 않거나 이름만
수정해도 나머지 OCR 추출 필드를 삭제하지 않는다.

```ts
medications: medications.map((medication) => ({
  tempId: medication.tempId,
  name: medication.name,
  dose: medication.dose,
  efficacy: medication.efficacy,
  administration: medication.administration,
  precautions: medication.precautions,
  timesPerDay: medication.timesPerDay,
  days: medication.days,
}))
```

- 수정한 필드는 사용자 수정값을 전송한다.
- 수정하지 않은 필드는 OCR 추출값을 그대로 전송한다.
- 사용자가 삭제한 약은 최종 배열에서 제외한다.
- 사용자가 추가한 약은 새 `tempId`와 직접 입력한 값을 포함한다.
- OCR confidence는 확정 요청에 보내지 않는다.

### 성공 응답

```json
{
  "recordId": 456,
  "hasMedication": true,
  "statusCode": "active"
}
```

| 필드 | 타입 | 설명 |
|---|---|---|
| `recordId` | integer | 생성된 `care_episodes.id` |
| `hasMedication` | boolean | 확정한 약 목록이 한 개 이상이면 `true` |
| `statusCode` | string | 현재는 `active` 고정 |

### DB 저장 규칙

하나의 트랜잭션에서 다음 순서로 처리한다.

1. `care_episodes`에 조제약 기록 한 행 생성
2. `medications` 배열 항목마다 `medications`에 한 행 생성
3. `ocr_jobs.care_episode_id`와 `care_episodes.source_ocr_job_id` 연결
4. 확정 시각과 본문 hash 저장
5. OCR 작업 상태를 `COMPLETE`로 변경
6. 사용자 확정 결과 스냅샷 보존

테이블별 주요 저장값:

| 테이블 | 저장 내용 |
|---|---|
| `ocr_jobs` | 작업 상태, 사용자, 멱등 키, 구조화 결과, 생성된 CareEpisode 연결 |
| `care_episodes` | `{dispensedDate} 조제약 복약안내`, `ACTIVE`, 복용 시작일, 약 목록의 최대 `days` |
| `medications` | 약품명, 용량, 효능, 복용 방법, 주의사항, 횟수, 일수, 조제일, OCR 작업 연결 |

약 네 개를 확정하면 아래처럼 저장한다.

```text
ocr_jobs       1행
care_episodes  1행
medications    4행
```

각 약의 `efficacy`, `administration`, `precautions`는 `medications`의 동일 이름 컬럼에 저장한다.
`timesPerDay=null`인 필요 시 복용 약은 내부 `note`에 `필요 시 복용`을 기록할 수 있다.

### 확정 멱등성

- 같은 작업에 같은 본문을 다시 PATCH하면 기존 `recordId`를 반환한다.
- 이미 완료된 작업에 다른 본문을 보내면 `409 OCR_JOB_STATE_CONFLICT`를 반환한다.
- 확정 hash는 날짜와 전체 약 목록을 기준으로 계산한다.

### 오류 응답

| HTTP | code | 발생 조건 |
|---:|---|---|
| 401 | `AUTHENTICATION_REQUIRED`, `INVALID_TOKEN` | 인증 실패 |
| 404 | `OCR_JOB_NOT_FOUND` | 작업 없음, 다른 사용자의 작업, 검토 시간 만료 |
| 409 | `OCR_JOB_STATE_CONFLICT` | 확정할 수 없는 상태 또는 다른 본문으로 재확정 |
| 422 | `VALIDATION_ERROR` | 날짜, 약 목록, 필드 길이 또는 값 범위 검증 실패 |

---

## 상태 전이 및 보존 정책

```text
QUEUED
  → PROCESSING
    → READY_FOR_REVIEW
      → COMPLETE

QUEUED / PROCESSING
  → FAILED

미확정 작업 만료
  → CANCELLED 또는 정리
```

- 공개 API에서는 상태를 소문자로 반환한다.
- OCR worker는 timeout, 일시 네트워크 오류, HTTP `408`, `425`, `429`, `5xx`만 한 번 재시도한다.
- 기본 검토 TTL은 `READY_FOR_REVIEW` 이후 60분이다.
- 만료된 미확정 결과와 원본 이미지는 정리한다.
- `COMPLETE` 결과와 원본 이미지는 저장 기록에서 다시 사용할 수 있도록 보존한다.

---

## Swagger 테스트 순서

1. `/api/v1/auth/login`으로 로그인하여 access token을 받는다.
2. Swagger 우측 상단 `Authorize`에 access token을 입력한다.
3. **1번 API** `POST /api/v1/ocr/medication-guides`를 실행한다.
4. `Idempotency-Key`에 `ocr-`로 시작하는 UUID를 입력하고 JPG/PNG 한 장을 선택한다.
5. 응답의 `documentIds[0]`을 복사한다.
6. **2번 API** `GET /api/v1/ocr/jobs/{ocrJobId}`를 `queued` 또는 `processing` 동안 반복 실행한다.
7. `ready_for_review`가 되면 `medications` 전체를 확인한다.
8. 필요하면 **3번 API**로 원본 이미지를 확인한다.
9. `GET` 결과의 약 전체를 **4번 API** PATCH 예시에 옮기고 수정할 값만 변경한다.
10. PATCH를 한 번 실행하고 응답의 `recordId`를 확인한다.
11. DB에서 `care_episodes.id=recordId`와 연결된 `medications` 행을 조회한다.

Swagger는 GET 응답을 PATCH 요청란으로 자동 복사하지 않는다. PATCH 예시는 입력 형식을 보여주기 위한
것이며, 실제 사용자는 프론트가 GET 결과를 상태로 보존해 자동으로 전송한다.

DB 확인 예시:

```sql
SELECT
    id,
    care_episode_id,
    name,
    dose,
    efficacy,
    administration,
    precautions,
    times_per_day,
    days,
    source_ocr_job_id
FROM medications
WHERE care_episode_id = <recordId>
ORDER BY id;
```

---

## 현재 범위에서 제외하는 항목

- 퇴원요약지 OCR
- 진단명, 수술명, 퇴원일 구조화
- 다음 외래 일정 저장
- 복약 알림 시간 설정 API
- RAG/LLM 질의 API
- OCR bounding box 공개
- 여러 장 동시 업로드
- 객체 스토리지 전환
- 별도 취소 API

이 문서는 조제약 복약안내 OCR의 업로드부터 사용자 확정 및 RDB 저장까지로 범위를 제한한다.

---

## 구현 및 검증 위치

| 영역 | 위치 |
|---|---|
| API route | `app/apis/v1/medication_guide_ocr_router.py` |
| DTO/OpenAPI | `app/dtos/medication_guide_ocr.py` |
| OCR 작업·확정 서비스 | `app/services/medication_guide_ocr_jobs.py` |
| OCR worker | `app/workers/medication_guide_ocr_worker.py` |
| 프론트 API·타입 | `frontend/src/entities/document/` |
| 프론트 검토·확정 화면 | `frontend/src/pages/ocr-review/` |
| API 계약 테스트 | `tests/ocr/` |
| 서비스·worker 테스트 | `app/tests/ocr_apis/`, `app/tests/workers/` |
