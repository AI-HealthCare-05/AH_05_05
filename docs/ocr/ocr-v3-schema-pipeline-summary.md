# OCR v3 스키마 및 파이프라인 요약

팀 공유를 위한 조제약 OCR v3의 데이터 구조와 처리 흐름 요약이다.

## 공개 결과 스키마

OCR 결과는 조제일과 약별 5개 값만 제공한다.

| 구분 | 필드 | 설명 |
| --- | --- | --- |
| 문서 | `dispensedDate` | 조제일 |
| 약 | `tempId` | 리뷰 화면에서 사용하는 임시 식별자 |
| 약 | `name` | 약품명. OCR 원문을 유지하며 최대 100자 |
| 약 | `strength` | 함량. `mg`, `mL` 등으로 정규화하며 최대 50자 |
| 약 | `doseQuantity` | 1회 투약량. 값과 단위를 합친 문자열이며 최대 50자. 예: `1`, `1정`, `7mL` |
| 약 | `timesPerDay` | 하루 복용 횟수. 1~6 |
| 약 | `days` | 투약 일수. 1~365 |
| 약 | `confidence` | 채택한 OCR 근거 품질: `high`, `medium`, `low` |

`strength`, `doseQuantity`, `timesPerDay`, `days`는 추출하지 못하면 응답에서 생략한다. 불완전한 결과도 리뷰 화면에 표시하며 사용자가 수정·추가·삭제한 뒤 확정할 수 있다.

```json
{
  "fields": {
    "dispensedDate": {
      "value": "2026-08-25",
      "confidence": "high"
    }
  },
  "medications": [
    {
      "tempId": "med-1",
      "name": "에스오메프라졸캡슐",
      "strength": "20mg",
      "doseQuantity": "1캡슐",
      "timesPerDay": 1,
      "days": 14,
      "confidence": "high"
    }
  ],
  "lowConfidenceCount": 0
}
```

## DB 저장 구조

### `ocr_jobs`

OCR 작업 단위와 백오피스 평가 데이터를 저장한다.

- 작업 상태: `QUEUED`, `PROCESSING`, `READY_FOR_REVIEW`, `COMPLETE`, `FAILED`, `CANCELLED`
- `input_manifest`: 원본·전처리 이미지 저장 정보와 무결성 확인값
- `structured_result`: 리뷰용 OCR 결과 JSON
- `ocr_model`, `structuring_model`, `prompt_version`, `schema_version`: 실행 버전 추적
- `stage_results`: 단계별 상태, 소요 시간, 외부 호출 횟수와 오류 코드
- `avg_field_confidence`: 공개된 약품명의 OCR 근거 신뢰도 평균
- `confidence_field_count`: 평균 계산에 포함된 약품명 수
- `user_review_match_rate`: OCR 결과와 사용자가 확정한 값의 필드별 일치율
- `error_code`, `started_at`, `ready_at`, `completed_at`, `expires_at`: 오류 및 처리 시각

`avg_field_confidence`는 정답률이 아니라 공개된 약품명에 사용된 OCR 근거의 품질이다. 조제일, 함량, 1회 투약량, 하루 횟수, 투약 일수의 confidence는 이 평균에 포함하지 않는다. `user_review_match_rate`는 조제일과 약별 `name`, `strength`, `doseQuantity`, `timesPerDay`, `days`를 비교하며, OCR에서 빠진 값을 사용자가 추가한 경우에도 불일치로 계산한다.

### `medications`

사용자가 확정한 최종 약 정보를 약별 한 행으로 저장한다.

- `name`: 약품명
- `strength`: 함량
- `dose_quantity`: 단위를 포함할 수 있는 1회 투약량 문자열
- `times_per_day`: 하루 복용 횟수
- `days`: 투약 일수
- `prescribed_at`: 조제일
- `source_ocr_job_id`: 원본 OCR 작업 추적

확정 시 `care_episodes` 한 건과 `medications` 여러 건이 하나의 트랜잭션으로 생성된다.

## 비동기 처리 파이프라인

```text
POST /api/v1/ocr
  → OcrJob 생성 및 원본 이미지 저장
  → Redis 작업 대기열 등록
  → OCR worker 실행
      preprocess → ocr → candidate → llm → validate
  → READY_FOR_REVIEW
  → 사용자 검토·수정
  → PATCH /api/v1/ocr/jobs/{ocrJobId}
  → CareEpisode 및 Medication 저장
  → COMPLETE
```

| 단계 | 역할 | 외부 호출 |
| --- | --- | --- |
| `preprocess` | 원근·조명 보정, OCR용 이미지 및 전처리 미리보기 생성 | 없음 |
| `ocr` | CLOVA General OCR로 글자와 좌표 추출 | CLOVA 1회 |
| `candidate` | 좌표와 행·열 구조를 이용해 조제일과 약별 필드 후보 구성 | 없음 |
| `llm` | 조제일 또는 함량 후보가 충돌할 때 허용된 OCR block ID만 선택 | 필요할 때 OpenAI 1회 |
| `validate` | 날짜, 범위, 단위 및 행 간 근거를 검증해 공개 결과 생성 | 없음 |

LLM은 약품 정보 문장을 새로 생성하지 않는다. 후보가 없거나 충돌이 없으면 호출하지 않으며, 존재하지 않는 ID나 다른 약 행의 ID는 서버 검증에서 거부한다.

각 단계는 아래 형식으로 `ocr_jobs.stage_results`에 기록한다.

```json
{
  "name": "ocr",
  "status": "succeeded",
  "elapsedMs": 2277,
  "callCount": 1
}
```

실패하거나 실행할 필요가 없는 단계는 각각 `failed`, `skipped`로 기록하고, 필요한 경우 `code`에 오류 코드를 남긴다.

## 관련 API

- `POST /api/v1/ocr`: 이미지 업로드 및 비동기 작업 생성
- `GET /api/v1/ocr/jobs/{ocrJobId}`: 작업 상태와 리뷰 결과 조회
- `GET /api/v1/ocr/jobs/{ocrJobId}/image`: 원본 이미지 조회
- `GET /api/v1/ocr/jobs/{ocrJobId}/processed-image`: 전처리 이미지 조회
- `PATCH /api/v1/ocr/jobs/{ocrJobId}`: 사용자 수정 결과 확정 및 RDB 저장

업로드와 이미지 조회 API는 10초 제한 시간을 사용한다. 실제 OCR·LLM 처리는 worker에서 비동기로 실행되므로 HTTP 요청 제한 시간과 분리된다.
