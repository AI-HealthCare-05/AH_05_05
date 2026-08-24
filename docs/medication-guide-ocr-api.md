# 조제약 복약안내 OCR API 명세서

## 1. 문서 범위

이 문서는 조제약 복약안내 이미지에서 약품 정보를 추출하고 정규화하는 OCR API만 정의한다.

- 포함: 이미지 업로드, 이미지 검증, CLOVA Template OCR 호출, OCR 결과 정규화, 검토 필요 항목 표시
- 제외: 회원가입·로그인 구현, OCR 결과 DB 저장, 복약 일정 생성, 약품·영양제 가이드 생성, 프론트엔드 화면
- 처리 방식: 클라이언트 관점의 동기 요청/응답 방식
  - 요청 연결을 유지한 상태에서 OCR 완료 결과를 바로 반환한다.
  - 작업 ID 발급, 상태 조회, 폴링 API는 사용하지 않는다.

## 2. API 요약

| 항목 | 값 |
| --- | --- |
| 기능 | 조제약 복약안내 이미지 OCR 및 결과 정규화 |
| Method | `POST` |
| Path | `/api/v1/ocr/medication-guides` |
| Content-Type | `multipart/form-data` |
| 인증 | `Authorization: Bearer <access_token>` |
| 성공 응답 | `200 OK` |
| 응답 형식 | `application/json` |
| Swagger | `/api/docs#/medication-guide-ocr/extract_medication_guide_api_v1_ocr_medication_guides_post` |

## 3. 요청 명세

### 3.1 Header

| Header | 필수 | 값 | 설명 |
| --- | --- | --- | --- |
| `Authorization` | O | `Bearer <access_token>` | 기존 사용자 인증 API에서 발급한 액세스 토큰 |
| `Accept` | 권장 | `application/json` | JSON 응답 요청 |
| `Content-Type` | O | `multipart/form-data` | boundary는 브라우저 또는 HTTP 클라이언트가 자동 생성 |

### 3.2 Form Data

| 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `file` | binary | O | JPG 또는 PNG 형식의 조제약 복약안내 이미지 |

### 3.3 이미지 검증 규칙

| 항목 | 제한 |
| --- | --- |
| 허용 MIME 타입 | `image/jpeg`, `image/png` |
| 허용 실제 포맷 | JPEG signature 또는 PNG signature |
| 이미지 파일 최대 크기 | 50 MiB |
| multipart 요청 전체 최대 크기 | 51 MiB |
| 가로 또는 세로 최대 길이 | 10,000 px |
| 최대 디코딩 픽셀 수 | 40,000,000 pixels |
| 추가 검증 | 파일 확장자가 아니라 실제 signature와 이미지 디코딩 성공 여부를 검사 |

파일의 선언된 MIME 타입과 실제 이미지 signature가 다르면 요청을 거부한다.

### 3.4 cURL 예시

```bash
curl -X POST "http://127.0.0.1:8000/api/v1/ocr/medication-guides" \
  -H "Accept: application/json" \
  -H "Authorization: Bearer <access_token>" \
  -F "file=@template_ocr_exact_02.png;type=image/png"
```

Windows PowerShell에서는 `curl.exe`를 사용한다.

## 4. 성공 응답

### 4.1 응답 Header

| Header | 값 | 설명 |
| --- | --- | --- |
| `Content-Type` | `application/json` | JSON 응답 |
| `Cache-Control` | `no-store` | OCR 결과 캐시 금지 |
| `X-Content-Type-Options` | `nosniff` | MIME 스니핑 방지 |

### 4.2 최상위 응답 객체

| 필드 | 타입 | Nullable | 설명 |
| --- | --- | --- | --- |
| `schemaVersion` | string | X | 고정값 `medication-guide-template/v2` |
| `dispensingDate` | string(date) | O | 조제일, `YYYY-MM-DD` |
| `nextVisitDate` | string(date) | O | 다음 내방일, `YYYY-MM-DD` |
| `medications` | Medication[] | X | 정규화된 약품 목록, 현재 템플릿 기준 최대 4행 |
| `reviewIssues` | ReviewIssue[] | X | 사람이 확인해야 하는 정규화 문제 목록 |
| `ocrFields` | OcrField[] | X | 허용된 CLOVA 필드의 원문과 신뢰도 |

서버는 기본값이 있는 필드도 실제 응답에 모두 포함한다.

### 4.3 Medication

| 필드 | 타입 | Nullable | 설명 |
| --- | --- | --- | --- |
| `rowId` | string | X | 약품 행 식별자. `med-1`부터 `med-4`까지 사용 |
| `name` | string | X | 용량 표기를 분리한 약품명 |
| `strength` | string | O | 약품명 끝에서 분리한 `mg`, `g`, `mcg`, `mL`, `%` 용량 |
| `category` | string | O | 효능 필드의 대괄호 안 분류명 |
| `efficacy` | string | O | 대괄호 분류명을 제외한 효능·효과 |
| `doseLine` | string | O | OCR에서 읽은 전체 복용량·횟수·일수 문장 |
| `doseQuantity` | string | O | 1회 복용량. 예: `1정`, `1캡슐`, `5mL`, `1포` |
| `timesPerDay` | integer | O | 1일 복용 횟수, 값이 있으면 1 이상 |
| `days` | integer | O | 복용 일수, 값이 있으면 1 이상 |
| `administration` | string | O | 복용 방법 및 복용 시점 안내 |
| `precautions` | string | O | 보관 라벨을 제거한 주의사항 |
| `confidence` | number | X | 해당 행에 존재하는 OCR 필드 중 최저 신뢰도, 범위 `0.0~1.0` |
| `needsReview` | boolean | X | 해당 약품 행에 검토 문제가 하나 이상 있으면 `true` |
| `sourceFieldNames` | string[] | X | 약품 행에 대응하는 템플릿 필드 이름 목록 |

### 4.4 ReviewIssue

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `code` | string | 검토 문제 코드 |
| `path` | string | 문제가 발생한 응답 필드 경로 |

검토 문제 코드는 오류 응답이 아니다. OCR 요청은 `200 OK`로 성공하지만 사용자가 해당 결과를 확인해야 한다는 뜻이다.

| code | 발생 조건 | path 예시 |
| --- | --- | --- |
| `INVALID_DATE` | 날짜 필드를 `YYYY-MM-DD`로 변환할 수 없음 | `dispensingDate` |
| `MISSING_REQUIRED` | 약품명은 있지만 효능·복약안내·주의사항 중 필수 값이 없음 | `medications.med-1.efficacy` |
| `ORPHAN_ROW` | 약품명 없이 같은 행의 다른 필드만 인식됨 | `medications.med-2` |
| `UNPARSEABLE_DOSE_LINE` | 복용 문장에서 1일 횟수 또는 복용 일수를 추출하지 못함 | `medications.med-1.doseLine` |
| `LOW_CONFIDENCE` | 약품 행의 최저 OCR 신뢰도가 설정 임계치보다 낮음 | `medications.med-1` |

### 4.5 OcrField

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `name` | string | CLOVA 템플릿 필드 이름 |
| `text` | string | CLOVA가 반환한 OCR 원문 |
| `confidence` | number | 필드 신뢰도, 범위 `0.0~1.0` |

### 4.6 성공 응답 예시

아래 예시는 Swagger에서 실제 실행한 결과를 가독성을 위해 약품 1건과 OCR 원문 1건으로 축약한 것이다.

```json
{
  "schemaVersion": "medication-guide-template/v2",
  "dispensingDate": "2025-06-11",
  "nextVisitDate": "2025-06-16",
  "medications": [
    {
      "rowId": "med-1",
      "name": "세프디니르건조시럽",
      "strength": null,
      "category": "항생제",
      "efficacy": "세균성감염치료",
      "doseLine": "1회 5mL씩 1일 2회 5일분",
      "doseQuantity": "5mL",
      "timesPerDay": 2,
      "days": 5,
      "administration": "식후에 복용하세요. 복용 전 충분히 흔들어 주세요.",
      "precautions": "의사가정한 기간 동안 끝까지 복용하세요. 실온에 보관하세요.",
      "confidence": 0.98715,
      "needsReview": false,
      "sourceFieldNames": [
        "med_01_name",
        "med_01_efficacy",
        "med_01_dose_line",
        "med_01_administration",
        "med_01_precaution"
      ]
    }
  ],
  "reviewIssues": [],
  "ocrFields": [
    {
      "name": "med_01_name",
      "text": "세프디니르건조시럽",
      "confidence": 0.9984
    }
  ]
}
```

## 5. CLOVA 템플릿 필드 계약

현재 서버가 허용하는 템플릿 필드는 다음과 같다. 목록에 없는 CLOVA 필드는 응답 정규화 대상에서 제외한다.

### 5.1 날짜 필드

| 템플릿 필드 | 응답 필드 |
| --- | --- |
| `dispensing_date` | `dispensingDate` |
| `next_visit_date` | `nextVisitDate` |

### 5.2 약품 행 필드

`NN`은 `01`부터 `04`까지다.

| 템플릿 필드 | 용도 |
| --- | --- |
| `med_NN_name` | 약품명과 함량 |
| `med_NN_efficacy` | `[분류]`와 효능·효과 |
| `med_NN_dose_line` | 1회 복용량, 1일 횟수, 복용 일수 |
| `med_NN_administration` | 복용 방법·시점 |
| `med_NN_precaution` | 주의사항과 보관 라벨 |

## 6. 정규화 규칙

1. 모든 텍스트를 Unicode NFKC로 정규화하고 연속 공백을 하나로 합친다.
2. `med_NN_name` 끝의 함량 단위를 `strength`로 분리한다.
3. `med_NN_efficacy`가 `[분류] 설명` 형식이면 `category`와 `efficacy`로 분리한다.
4. `doseLine`에서 `doseQuantity`, `timesPerDay`, `days`를 추출한다.
5. `precautions` 끝의 `실온보관`, `기밀용기`, `냉장보관`, `차광보관` 라벨을 제거한다.
6. 약품명이 없는 행은 결과 목록에 추가하지 않는다. 같은 행의 다른 값이 있으면 `ORPHAN_ROW`를 기록한다.
7. 약품 행에 존재하는 OCR 필드 중 최저 신뢰도를 `confidence`로 사용한다.
8. 신뢰도가 `OCR_REVIEW_CONFIDENCE_THRESHOLD`보다 낮거나 필수값 누락 등의 문제가 있으면 `needsReview`를 `true`로 설정한다.
9. 정상 약품이 하나도 없으면 `NO_MEDICATIONS_FOUND` 오류를 반환한다.

## 7. 오류 응답

OCR 도메인 오류는 아래 공통 형식을 사용한다.

```json
{
  "code": "INVALID_IMAGE",
  "message": "유효한 JPG 또는 PNG 이미지를 선택해 주세요."
}
```

| HTTP status | code | 발생 조건 | message |
| --- | --- | --- | --- |
| `413` | `OCR_UPLOAD_TOO_LARGE` | multipart 요청 전체가 51 MiB 초과 | `OCR 요청 크기는 51MB를 초과할 수 없습니다.` |
| `422` | `VALIDATION_ERROR` | `file` 필드 누락 등 요청 형식 오류 | `입력값이 올바르지 않습니다.` 또는 첫 번째 검증 오류 메시지 |
| `422` | `INVALID_IMAGE` | 지원하지 않는 MIME, 손상된 이미지, 크기·해상도 초과, MIME/signature 불일치 | `유효한 JPG 또는 PNG 이미지를 선택해 주세요.` |
| `422` | `TEMPLATE_NOT_MATCHED` | CLOVA가 매칭한 템플릿 ID가 서버 설정과 다름 | `등록된 조제약 복약안내 템플릿과 일치하지 않습니다.` |
| `422` | `NO_MEDICATIONS_FOUND` | 정규화 가능한 약품 행이 없음 | `약품 정보를 찾지 못했습니다. 이미지와 템플릿을 확인해 주세요.` |
| `502` | `OCR_PROVIDER_ERROR` | CLOVA HTTP 오류, JSON 오류 또는 응답 구조 오류 | `Template OCR 응답을 처리할 수 없습니다.` |
| `503` | `PROVIDER_CONFIG_MISSING` | CLOVA URL, Secret 또는 Template ID 설정 누락 | `Template OCR 설정이 필요합니다.` |
| `504` | `OCR_PROVIDER_TIMEOUT` | CLOVA 호출 제한 시간 초과 | `Template OCR 호출 시간이 초과됐습니다.` |

`401 Unauthorized`는 기존 팀 공통 사용자 인증 계층에서 처리하며 이 OCR 명세의 구현 범위에는 포함하지 않는다.

## 8. 서버 설정

값은 서버 환경변수로만 관리하며 클라이언트에 노출하지 않는다.

| 환경변수 | 기본값/현재값 | 설명 |
| --- | --- | --- |
| `CLOVA_TEMPLATE_OCR_INVOKE_URL` | 필수 | CLOVA Template OCR Invoke URL |
| `CLOVA_TEMPLATE_OCR_SECRET` | 필수 | CLOVA OCR Secret, 서버 전용 |
| `CLOVA_TEMPLATE_ID` | `43199` | 매칭을 허용할 템플릿 ID |
| `CLOVA_CONNECT_TIMEOUT_SECONDS` | `5` | CLOVA 연결 제한 시간 |
| `CLOVA_READ_TIMEOUT_SECONDS` | `60` | CLOVA 응답 읽기 제한 시간 |
| `OCR_REVIEW_CONFIDENCE_THRESHOLD` | `0.90` | 이 값 미만이면 `LOW_CONFIDENCE` |

Nginx `/api/` 경로에는 `client_max_body_size 51m`과 `proxy_read_timeout 60s`를 적용한다.

## 9. Swagger 수동 테스트

1. FastAPI 서버 실행 후 `http://127.0.0.1:8000/api/docs`에 접속한다.
2. 기존 인증 API로 로그인하고 액세스 토큰을 발급받는다.
3. Swagger 상단 `Authorize`에서 토큰을 등록한다.
4. `medication-guide-ocr`의 `POST /api/v1/ocr/medication-guides`를 펼친다.
5. `Try it out`을 누르고 JPG 또는 PNG 파일을 선택한다.
6. `Execute`를 누른다.
7. `200` 응답과 `schemaVersion`, `medications`, `reviewIssues`, `ocrFields`를 확인한다.

현재 Swagger 실제 실행에서 Bearer 인증, JPG multipart 업로드, 실제 CLOVA 호출, 정규화된 약품 4건 반환, `Cache-Control: no-store`, `X-Content-Type-Options: nosniff`를 확인했다.

## 10. 구현 파일

| 역할 | 경로 |
| --- | --- |
| API 라우터 | `app/apis/v1/medication_guide_ocr_router.py` |
| 의존성 조립 | `app/dependencies/medication_guide_ocr.py` |
| 응답 DTO | `app/dtos/medication_guide_ocr.py` |
| OCR 처리 흐름 | `app/services/medication_guide_ocr.py` |
| CLOVA 호출 | `app/services/clova_template_ocr.py` |
| 이미지 검증 | `app/services/ocr_image_input.py` |
| 결과 정규화 | `app/services/medication_guide_normalizer.py` |
| 업로드 크기 제한 | `app/core/ocr_upload_middleware.py` |
| 오류 정의 | `app/core/exceptions.py` |
| OCR 테스트 | `tests/ocr/` |
