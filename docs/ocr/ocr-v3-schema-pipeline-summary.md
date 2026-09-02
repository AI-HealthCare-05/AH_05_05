# OCR v3 스키마 및 처리 흐름

조제약 OCR v3의 추출 범위, DB 저장 구조와 비동기 처리 흐름을 팀 공유용으로 정리한 문서다.

## 1. 추출 범위

OCR은 복약안내 문서에서 다음 정보만 추출한다.

- 조제일
- 약품명
- 함량
- 1회 투약량
- 하루 복용 횟수
- 투약 일수

약품명은 OCR 원문을 최대한 유지한다. 함량과 투약량의 단위는 `mg`, `mL`처럼 정규화하며, 1회 투약량은 값과 단위를 합친 문자열로 처리한다.

예: `1`, `1정`, `0.5정`, `7mL`

추출하지 못한 값은 임의로 생성하지 않고 생략한다. 불완전한 결과도 리뷰 화면에 표시하며, 사용자가 직접 수정·추가·삭제한 뒤 확정할 수 있다.

## 2. 공개 결과 스키마

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

| 필드 | 설명 |
| --- | --- |
| `dispensedDate` | 조제일 |
| `tempId` | 리뷰 화면에서 사용하는 약품 임시 식별자 |
| `name` | 약품명. OCR 원문을 유지하며 최대 100자 |
| `strength` | 함량. 단위를 정규화하며 최대 50자 |
| `doseQuantity` | 단위를 포함할 수 있는 1회 투약량 문자열. 최대 50자 |
| `timesPerDay` | 하루 복용 횟수. 1~6 |
| `days` | 투약 일수. 1~365 |
| `confidence` | 해당 약 행에 채택한 OCR 근거 품질 |
| `lowConfidenceCount` | 검토가 필요한 낮은 신뢰도 항목 수 |

`strength`, `doseQuantity`, `timesPerDay`, `days`는 미추출 시 응답에서 생략한다.

### Confidence 기준

`confidence`는 정답 확률이 아니라 채택한 OCR 근거의 품질이다.

- `high`: 0.90 이상
- `medium`: 0.70 이상 0.90 미만
- `low`: 0.70 미만이거나 필드 누락·검증 오류가 있는 경우

## 3. 비동기 처리 흐름

```text
이미지 업로드
  → OCR 작업 생성 및 원본 이미지 저장
  → Redis 작업 대기열 등록
  → OCR worker 실행
      preprocess → ocr → candidate → llm → validate
  → READY_FOR_REVIEW
  → 사용자 검토·수정
  → 최종 복약 정보 저장
  → COMPLETE
```

| 단계 | 역할 | 외부 호출 |
| --- | --- | --- |
| `preprocess` | 원근·조명 보정, OCR용 이미지와 전처리 미리보기 생성 | 없음 |
| `ocr` | CLOVA General OCR로 글자와 좌표 추출 | CLOVA 1회 |
| `candidate` | 좌표와 행·열 구조를 이용해 조제일과 약별 필드 후보 구성 | 없음 |
| `llm` | 조제일 또는 함량 후보가 충돌할 때 허용된 OCR block ID 선택 | 필요할 때 OpenAI 1회 |
| `validate` | 날짜, 단위, 값 범위와 행 간 근거를 검증해 공개 결과 생성 | 없음 |

LLM은 새로운 약품 정보를 생성하지 않는다. 충돌 후보가 있을 때만 OCR 근거를 선택하며, 충돌이 없거나 유효한 후보가 없으면 호출하지 않는다. 존재하지 않는 ID나 다른 약 행의 ID는 서버에서 거부한다.

각 단계는 상태, 소요 시간, 외부 호출 횟수와 오류 코드를 기록한다.

```json
{
  "name": "ocr",
  "status": "succeeded",
  "elapsedMs": 2277,
  "callCount": 1
}
```

`status`는 `succeeded`, `failed`, `skipped` 중 하나이며, 필요한 경우 `code`에 오류 코드를 저장한다.

## 4. DB 저장 구조

### `ocr_jobs`

OCR 작업 단위와 품질 평가 데이터를 저장한다.

- 작업 상태: `QUEUED`, `PROCESSING`, `READY_FOR_REVIEW`, `COMPLETE`, `FAILED`, `CANCELLED`
- `input_manifest`: 원본·전처리 이미지 저장 정보와 무결성 확인값
- `structured_result`: 사용자 리뷰용 OCR 결과 JSON
- `ocr_model`, `structuring_model`, `prompt_version`, `schema_version`: 실행 버전 추적
- `stage_results`: 단계별 상태, 소요 시간, 호출 횟수와 오류 코드
- `error_code`, `started_at`, `ready_at`, `completed_at`, `expires_at`: 오류 및 처리 시각

품질 평가 컬럼은 다음과 같다.

- `avg_field_confidence`: 공개된 약품명들의 OCR confidence 평균
- `confidence_field_count`: 평균 계산에 포함된 약품명 개수
- `user_review_match_rate`: OCR 결과와 사용자가 확정한 값의 필드별 일치율

`avg_field_confidence`에는 약품명만 포함한다. 조제일, 함량, 1회 투약량, 하루 복용 횟수와 투약 일수의 confidence는 평균 계산에서 제외한다. 약품명 confidence가 없으면 평균은 `NULL`, 개수는 `0`으로 저장한다.

`user_review_match_rate`는 조제일과 약별 `name`, `strength`, `doseQuantity`, `timesPerDay`, `days`를 비교한다. OCR에서 빠진 값을 사용자가 추가하거나 기존 값을 수정하면 불일치로 계산한다.

### `medications`

사용자가 확인한 최종 약 정보를 약별 한 행으로 저장한다.

- `name`: 약품명
- `strength`: 함량
- `dose_quantity`: 단위를 포함할 수 있는 1회 투약량 문자열
- `times_per_day`: 하루 복용 횟수
- `days`: 투약 일수
- `prescribed_at`: 조제일
- `source_ocr_job_id`: 원본 OCR 작업 식별자

사용자가 결과를 확정하면 `care_episodes` 한 건과 약 개수만큼의 `medications` 행을 하나의 트랜잭션으로 저장한다. `source_ocr_job_id`를 통해 최종 약 정보가 생성된 OCR 작업을 추적할 수 있다.

## 5. 관련 API

- `POST /api/v1/ocr`: 이미지 업로드 및 비동기 OCR 작업 생성
- `GET /api/v1/ocr/jobs/{ocrJobId}`: 작업 상태와 리뷰 결과 조회
- `GET /api/v1/ocr/jobs/{ocrJobId}/image`: 원본 이미지 조회
- `GET /api/v1/ocr/jobs/{ocrJobId}/processed-image`: 전처리 이미지 조회
- `PATCH /api/v1/ocr/jobs/{ocrJobId}`: 사용자 수정 결과 확정 및 DB 저장

업로드와 이미지 조회 API는 10초 제한 시간을 사용한다. 실제 전처리·OCR·LLM·검증은 worker에서 비동기로 실행되므로 HTTP 요청 제한 시간과 분리된다.
