# DBDiagram 스키마 동기화 설계

## 목적

온라인 DBDiagram `FinalProject-6a79bddbe093539a9e8459eb`의 최신 18개 테이블을 스키마의 기준으로 삼아 Tortoise ORM 모델, 사용자 API 계약, Aerich 마이그레이션, 로컬 `ai_health` 데이터베이스를 일치시킨다.

현재 업무 테이블은 모두 비어 있으므로 기존 업무 데이터의 변환이나 보존 로직은 필요하지 않다. 이미 적용된 초기 Aerich 이력은 유지하고 후속 마이그레이션을 추가한다.

## 스키마 변경

### 사용자 설정

- `user.is_alarm`을 제거하고 설정 필드를 별도 `user_settings` 테이블로 분리한다.
- `user_settings`에는 알림 설정 3종, 약관 동의 여부, 아침·점심·저녁·취침 복약 시간을 저장한다.
- `user_settings.user_id`에 unique index를 두어 사용자당 설정 한 행만 허용한다.
- 사용자 응답 DTO와 갱신 허용 필드를 새 설정 구조와 일치시킨다.

### 복약 슬롯

- `meal_slot` enum을 `MORNING`, `LUNCH`, `EVENING`, `BEDTIME`으로 추가한다.
- 기존 `medication_times` 테이블과 `MedicationTime` 모델을 제거한다.
- 사용자별 실제 복약 시간은 `user_settings`의 네 시간 필드로 저장한다.
- 약별 복용 슬롯을 저장하는 `medication_slots`를 추가한다.
  - `(medication_id, slot)`은 유일하다.
  - `slot` 인덱스를 둔다.

### 케어 및 알람

- `care_episodes`에 사용자 확정 진단명, 수술명, 퇴원일, 전체 복약일수, source OCR job, 확정 hash·시각을 추가한다.
- `care_episodes`에 nullable `medication_start_date`, `medication_start_slot`을 추가한다.
- `alarm_type`에 `GUIDE_CHECK`를 추가한다.
- `alarm_type.CUSTOM`을 제거하고 기본값을 `MEDICATION`으로 변경한다.
- `alarms`에 nullable `meal_slot`을 추가한다.
- `(user_id, alarm_type, meal_slot)` 유일 인덱스를 추가한다.
- MEDICATION 알람만 `meal_slot`을 가져야 한다는 체크 제약을 추가한다.

### 백그라운드 작업

- `background_jobs.idempotency_key`를 `varchar(150)`, not null, unique로 추가한다.

### OCR 확정 데이터

- `ocr_extracted_fields`를 제거한다.
- `ocr_jobs`는 입력 manifest, 검토용 `structured_result`, OCR·구조화 모델 버전, 검토 준비·만료 시각을 저장하도록 재설계한다.
- `(care_episode_id, idempotency_key)`를 유일하게 유지한다.
- 검토 후보는 `structured_result`에만 임시 저장하고 확정 결과는 `care_episodes`, `medications`, `care_advices`에 저장한다.
- `medications`, `care_advices`, `follow_up_visits`의 `source_extracted_field_id`를 제거한다.

### 가이드 및 채팅 출처

- `patient_source_kind`와 `care_episode_source_field` enum을 추가한다.
- 환자 출처는 케어 필드, medication, care advice, follow-up visit 중 정확히 하나를 참조한다.
- 공공 RAG 출처와 환자 저장 데이터 출처의 필드 조합은 DB 체크 제약으로 강제한다.
- 최종 회복 가이드의 콘텐츠, 모델명, 프롬프트·스키마 버전, 안전 사유 코드 배열, 완료 시각은 필수로 저장한다.
- 안전성 검사가 끝난 가이드만 저장하므로 `safety_status=PENDING`을 허용하지 않는다.
- 가이드·채팅 공공 출처에 nullable 원문 페이지 번호와 라이선스를 저장하며 페이지 번호는 1 이상이어야 한다.

### 제거되는 구조

- `ocr_extracted_fields`, `medication_times`, `user_meal_times`, `user_consents`를 제거한다.
- `ocr_document_type`, `ocr_masking_status`, `ocr_review_status`, `consent_type` enum을 제거한다.

## 구현 구조

- enum은 `app/models/enums.py`에서 관리한다.
- 도메인 모델은 기존 파일 경계를 유지한다.
  - 사용자 알림: `app/models/users.py`
  - 사용자 설정: `app/models/users.py`
  - 케어 시작 정보: `app/models/care.py`
  - OCR 작업: `app/models/ocr.py`
  - 가이드·채팅 출처: `app/models/recovery.py`, `app/models/chat.py`
  - 알람 슬롯: `app/models/alarms.py`
  - 멱등성 키: `app/models/background_jobs.py`
  - 복약 슬롯 모델: `app/models/medications.py`
- Aerich가 새 모델을 인식하도록 기존 명시적 모델 모듈 등록 방식을 유지한다.
- 사용자가 수정한 `app/models/__init__.py`와 관련 없는 작업 트리 변경은 보존한다.

## 마이그레이션 전략

1. 현재 적용된 초기 마이그레이션은 변경하지 않는다.
2. 모델을 온라인 ERD와 일치시킨 후 이름이 명확한 후속 Aerich 마이그레이션을 생성한다.
3. 생성 SQL을 검토하고 Aerich가 표현하지 못하는 체크 제약은 마이그레이션 SQL에 명시한다.
4. 구형 OCR·복약 시간·사용자 동의 테이블과 관련 외래키를 의존 순서대로 제거한다.
5. `user_settings`, `medication_slots`와 새 출처 관계를 생성한다.
6. Tortoise가 표현하지 못하는 OCR 복합 외래키와 출처·상태 체크 제약은 마이그레이션 SQL로 보완한다.
7. 로컬 DB가 비어 있음을 전제로 새 not-null 필드와 제약을 적용한다.
8. `aerich upgrade` 후 `information_schema`를 조회해 컬럼, 인덱스, 외래키, 체크 제약을 검증한다.

## 오류 및 호환성 처리

- 구형 `is_alarm`, `MedicationTime`, `OcrExtractedField`, `UserConsent` API/모델 호환 계층은 유지하지 않는다. 온라인 ERD를 새 계약으로 사용한다.
- 사용자 갱신 요청은 정의된 알림 필드만 허용한다.
- 사용자 설정은 사용자당 한 행만 허용하며 기본 복약 시간은 08:00, 13:00, 19:00, 22:00이다.
- 알람의 유형/슬롯 조합과 OCR 상태 조합, 출처 종류별 필드 조합을 DB 체크 제약으로 검증한다.
- 마이그레이션 생성 결과가 온라인 ERD와 다르면 자동 생성 SQL을 그대로 적용하지 않고 보완한다.

## 테스트 및 완료 조건

- 모델 메타데이터 테스트를 먼저 새 계약으로 변경해 실패를 확인한다.
- enum, 필드, 테이블명, unique/index, FK 관계를 테스트한다.
- 사용자 응답 DTO와 저장소 갱신 허용 필드를 테스트한다.
- 전체 테스트를 실행한다.
- Aerich 마이그레이션 생성과 업그레이드가 성공해야 한다.
- 로컬 DB에 18개 업무 테이블이 존재해야 한다.
- `ocr_extracted_fields`, `medication_times`, `user_meal_times`, `user_consents`는 없어야 한다.
- `user_settings.user_id`에는 unique index가 있어야 한다.
- 실제 DB 구조가 온라인 DBDiagram의 변경된 컬럼과 제약을 포함해야 한다.
