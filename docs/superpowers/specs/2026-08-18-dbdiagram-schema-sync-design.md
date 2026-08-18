# DBDiagram 스키마 동기화 설계

## 목적

온라인 DBDiagram `FinalProject-6a79bddbe093539a9e8459eb`을 스키마의 기준으로 삼아 Tortoise ORM 모델, 사용자 API 계약, Aerich 마이그레이션, 로컬 `ai_health` 데이터베이스를 일치시킨다.

현재 업무 테이블은 모두 비어 있으므로 기존 업무 데이터의 변환이나 보존 로직은 필요하지 않다. 이미 적용된 초기 Aerich 이력은 유지하고 후속 마이그레이션을 추가한다.

## 스키마 변경

### 사용자 알림 설정

- `user.is_alarm`을 제거한다.
- 기본값이 `true`인 `notify_medication`, `notify_schedule`, `notify_guide`를 추가한다.
- 사용자 응답 DTO와 갱신 허용 필드를 새 알림 설정으로 변경한다.

### 복약 슬롯

- `meal_slot` enum을 `MORNING`, `LUNCH`, `EVENING`, `BEDTIME`으로 추가한다.
- 기존 `medication_times` 테이블과 `MedicationTime` 모델을 제거한다.
- 사용자별 실제 시간을 저장하는 `user_meal_times`를 추가한다.
  - `(user_id, slot)`은 유일하다.
  - `time_of_day` 인덱스를 둔다.
- 약별 복용 슬롯을 저장하는 `medication_slots`를 추가한다.
  - `(medication_id, slot)`은 유일하다.
  - `slot` 인덱스를 둔다.

### 케어 및 알람

- `care_episodes`에 nullable `medication_start_date`, `medication_start_slot`을 추가한다.
- `alarm_type`에 `GUIDE_CHECK`를 추가한다.
- `alarms`에 nullable `meal_slot`을 추가한다.
- `(user_id, alarm_type, meal_slot)` 유일 인덱스를 추가한다.
- MEDICATION 알람만 `meal_slot`을 가져야 한다는 체크 제약을 추가한다.

### 백그라운드 작업

- `background_jobs.idempotency_key`를 `varchar(150)`, not null, unique로 추가한다.

## 구현 구조

- enum은 `app/models/enums.py`에서 관리한다.
- 도메인 모델은 기존 파일 경계를 유지한다.
  - 사용자 알림: `app/models/users.py`
  - 케어 시작 정보: `app/models/care.py`
  - 알람 슬롯: `app/models/alarms.py`
  - 멱등성 키: `app/models/background_jobs.py`
  - 복약 슬롯 모델: `app/models/medications.py`
- Aerich가 새 모델을 인식하도록 기존 명시적 모델 모듈 등록 방식을 유지한다.
- 사용자가 수정한 `app/models/__init__.py`와 관련 없는 작업 트리 변경은 보존한다.

## 마이그레이션 전략

1. 현재 적용된 초기 마이그레이션은 변경하지 않는다.
2. 모델을 온라인 ERD와 일치시킨 후 이름이 명확한 후속 Aerich 마이그레이션을 생성한다.
3. 생성 SQL을 검토하고 Aerich가 표현하지 못하는 체크 제약은 마이그레이션 SQL에 명시한다.
4. `medication_times`를 삭제하고 두 신규 슬롯 테이블을 생성한다.
5. 로컬 DB가 비어 있음을 전제로 새 not-null 필드와 제약을 적용한다.
6. `aerich upgrade` 후 `information_schema`를 조회해 컬럼, 인덱스, 외래키, 체크 제약을 검증한다.

## 오류 및 호환성 처리

- 구형 `is_alarm`과 `MedicationTime` API/모델 호환 계층은 유지하지 않는다. 온라인 ERD를 새 계약으로 사용한다.
- 사용자 갱신 요청은 정의된 알림 필드만 허용한다.
- 알람의 유형/슬롯 조합은 DB 체크 제약과 모델 검증 범위에서 일관되게 다룬다.
- 마이그레이션 생성 결과가 온라인 ERD와 다르면 자동 생성 SQL을 그대로 적용하지 않고 보완한다.

## 테스트 및 완료 조건

- 모델 메타데이터 테스트를 먼저 새 계약으로 변경해 실패를 확인한다.
- enum, 필드, 테이블명, unique/index 관계를 테스트한다.
- 사용자 응답 DTO와 저장소 갱신 허용 필드를 테스트한다.
- 전체 테스트를 실행한다.
- Aerich 마이그레이션 생성과 업그레이드가 성공해야 한다.
- 로컬 DB에 20개 업무 테이블이 존재하고 `medication_times`는 없어야 한다.
- 실제 DB 구조가 온라인 DBDiagram의 변경된 컬럼과 제약을 포함해야 한다.
