# OCR v3 스키마 및 처리 흐름

조제약 OCR v3의 추출 범위, DB 저장 구조와 비동기 처리 흐름을 팀 공유용으로 정리한 문서다.

## 1. 추출 범위

OCR은 복약안내 문서에서 다음 정보만 추출한다.

- 병원명
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
    "hospitalName": {
      "value": "송도센트럴이비인후과의원",
      "confidence": "high"
    },
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
| `hospitalName` | 병원·의원·진료과 명칭. 최대 255자 |
| `dispensedDate` | 조제일 |
| `tempId` | 리뷰 화면에서 사용하는 약품 임시 식별자 |
| `name` | 약품명. OCR 원문을 유지하며 최대 100자 |
| `strength` | 함량. 단위를 정규화하며 최대 50자 |
| `doseQuantity` | 단위를 포함할 수 있는 1회 투약량 문자열. 최대 50자 |
| `timesPerDay` | 하루 복용 횟수. 1~6 |
| `days` | 투약 일수. 1~365 |
| `confidence` | 해당 약 행에 채택한 OCR 근거 품질 |
| `lowConfidenceCount` | 검토가 필요한 낮은 신뢰도 항목 수 |

`hospitalName`, `strength`, `doseQuantity`, `timesPerDay`, `days`는 미추출 시 응답에서 생략한다.

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
| `candidate` | 좌표와 행·열 구조를 이용해 병원명, 조제일과 약별 필드 후보 구성 | 없음 |
| `llm` | 조제일 또는 함량 후보가 충돌할 때 허용된 OCR block ID 선택 | 필요할 때 OpenAI 1회 |
| `validate` | 날짜, 단위, 값 범위와 행 간 근거를 검증해 공개 결과 생성 | 없음 |

병원명은 문서 상단의 병원명 라벨과 병원·의원·진료과 접미사를 좌표로 판별하고, 가까운 분리 블록만 이어 붙이는 결정론 규칙으로 추출한다. 진료과 뒤에 의사 이름이 붙어 인식되면 진료과까지만 채택한다. 약국명과 효능 문구는 제외하며 후보가 충돌하면 값을 생략한다. 라벨 위치는 맞지만 OCR 오타로 접미사를 확인할 수 없는 값은 버리지 않고 `low`로 화면에 표시해 사용자가 수정할 수 있게 한다. LLM은 병원명을 생성하거나 선택하지 않는다. 조제일·함량 충돌 후보가 있을 때만 OCR 근거를 선택하며, 충돌이 없거나 유효한 후보가 없으면 호출하지 않는다. 존재하지 않는 ID나 다른 약 행의 ID는 서버에서 거부한다.

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

### 단계 결과의 의미

- `succeeded`: 다음 처리나 사용자 검토에 사용할 결과가 있다. 활용 가능한 부분 결과에 문제가 있으면 `code: COMPLETED_WITH_ISSUES`를 함께 기록한다. 빈 선택 필드만으로 작업 전체를 실패시키지 않는다.
- `failed`: 해당 단계에서 필요한 결과를 만들지 못했다. 실패 원인은 그 단계의 `code`에 기록한다.
- `skipped`: 실행하지 않은 단계다. 선행 단계의 치명적 실패가 원인이면 `code: UPSTREAM_FAILED`, 정상적인 결정론 처리로 LLM이 불필요하면 `code: DETERMINISTIC_SUFFICIENT`로 구분한다.

| 상황 | 실패 단계와 코드 | 후속 처리 | 작업 오류 코드 |
| --- | --- | --- | --- |
| 이미지 품질 검사 탈락 | preprocess / RECAPTURE_REQUIRED | 모두 skipped | RECAPTURE_REQUIRED |
| OCR 문자 블록 0개 | ocr / NO_OCR_BLOCKS | 모두 skipped | EXTRACTION_FAILED |
| 약 표 없음·판별 불가 | candidate / TABLE_NOT_FOUND 또는 AMBIGUOUS_MEDICATION_TABLE | resolve·llm·validate skipped | EXTRACTION_FAILED |
| 사용할 근거 없음 | candidate 또는 resolve / NO_EVIDENCE_ROWS | 해당 단계 이후 skipped | EXTRACTION_FAILED |
| 검증 후 약 목록 0개 | validate / NO_VALID_MEDICATION_ROWS | 리뷰 생성 안 함 | EXTRACTION_FAILED |

LLM 호출 실패 시에도 독립적인 결정론 결과가 남아 있으면 검증을 계속해 사용자 검토에 제공할 수 있다. 이 경우 LLM은 `failed`, 검증은 `succeeded`와 `COMPLETED_WITH_ISSUES`를 기록한다. 따라서 단계 실패가 항상 작업 전체 실패를 뜻하지는 않으며, 사용할 약 목록이 없는 경우에만 추출 실패로 종료한다. 결과 스키마 자체가 잘못된 경우는 별도로 `VALIDATION_FAILED`다.

이 규칙은 변경 이후 실행되는 작업에 적용한다. 과거 작업의 상태·코드는 소급 변경하지 않는다.

예외나 워커 중단으로 신뢰할 수 있는 단계 기록이 없으면 `stages: []`로 보존한다. 이때 작업 수준의 `error_code`만 확인된 오류이며, 원인을 알 수 없는데 `preprocess` 실패나 후속 단계 미실행을 추정해 기록하지 않는다.

## 4. DB 저장 구조

### `ocr_jobs`

OCR 작업 단위와 품질 평가 데이터를 저장한다.

- 작업 상태: `QUEUED`, `PROCESSING`, `READY_FOR_REVIEW`, `COMPLETE`, `FAILED`, `CANCELLED`
- `input_manifest`: 원본·전처리 이미지 저장 정보와 무결성 확인값
- `structured_result`: 사용자 리뷰용 OCR 결과 JSON
- `ocr_model`, `structuring_model`, `prompt_version`, `schema_version`: 실행 버전 추적
- `stage_results`: `{"timings": ..., "stages": [...]}`. `timings`는 작업 단위 큐 대기·저장·전체 시간, `stages`는 기존 단계별 상태·`elapsedMs`·호출 횟수·오류 코드다. 애플리케이션 직렬화 순서는 timings → stages이며, MySQL JSON 원문 키 순서는 보장되지 않는다. 기존 배열형 기록과 `input_manifest.timings`는 33번 데이터 마이그레이션(원본 로컬 복사본에서는 32번)으로 이전한다.
- `error_code`, `started_at`, `ready_at`, `completed_at`, `expires_at`: 오류 및 처리 시각

품질 평가 컬럼은 다음과 같다.

- `avg_field_confidence`: 공개된 약품명들의 OCR confidence 평균
- `confidence_field_count`: 평균 계산에 포함된 약품명 개수
- `user_review_match_rate`: OCR 결과와 사용자가 확정한 값의 필드별 일치율

`avg_field_confidence`에는 약품명만 포함한다. 조제일, 함량, 1회 투약량, 하루 복용 횟수와 투약 일수의 confidence는 평균 계산에서 제외한다. 약품명 confidence가 없으면 평균은 `NULL`, 개수는 `0`으로 저장한다.

`user_review_match_rate`는 병원명, 조제일과 약별 `name`, `strength`, `doseQuantity`, `timesPerDay`, `days`를 비교한다. OCR에서 빠진 값을 사용자가 추가하거나 기존 값을 수정하면 불일치로 계산한다.

### `care_episodes`

- `hospital_name`: 사용자가 확인한 병원명. 미추출·미입력 시 `NULL`
- 복용 시작일, 투약 일수와 원본 OCR 작업 연결을 함께 저장한다.

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
