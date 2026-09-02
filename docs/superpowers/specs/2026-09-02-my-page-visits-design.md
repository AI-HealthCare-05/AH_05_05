# #226 마이페이지 개편과 진료일정 화면 설계

## 목표

사용자 단위로 이미 저장되는 네 개의 복약 알림 시간을 마이페이지에서 직접 바꾸게 한다. 처방 유무와 관계없이 시간을 설정할 수 있어야 하며, 변경된 시간은 실제 예약 알람에도 즉시 반영되어야 한다.

동시에 기존 백엔드 계약을 사용해 진료일정 관리 화면과 읽기 전용 알림 목록을 추가한다. 새 모델, 마이그레이션, 진료일정 엔드포인트는 만들지 않는다.

## 확인된 기존 계약

- `UserSettings`에는 `morning_medication_time`, `lunch_medication_time`, `evening_medication_time`, `bedtime_medication_time`이 이미 있다.
- `PUT /med/medication/schedule/{record_id}`는 위 컬럼을 저장하고 `MedicationScheduleService._sync_medication_alarms`로 알람을 재동기화한다.
- `GET/PATCH /me/settings`는 마이페이지 알림 토글이 이미 사용한다.
- `/user/follow-up-visits`에는 등록, 목록, 상세, 부분 수정, 삭제 API가 모두 있다. 날짜는 필수이며 시간과 병원은 선택이다. 삭제 시 FK에 연결된 알람도 삭제된다.
- `GET /alarms`는 발송 이력이 아니라 현재 사용자의 예약 알람 정의를 반환한다. 화면은 `status=ACTIVE`로 활성 예약만 조회하고 가까운 `scheduled_at`부터 보여준다.
- 진료일정과 알람 DTO는 `BaseSerializerModel`을 사용하므로 JSON 필드가 snake_case다. 화면 타입은 API 경계에서 camelCase로 변환한다.

## 선택한 접근

기존 `/me/settings` 계약을 확장하고 기존 알람 동기화 구현을 직접 재사용한다. 별도의 시간 API나 알람 동기화 로직을 만들지 않는다.

알람 동기화를 독립 서비스로 추출하는 방법도 가능하지만 이번 변경에 필요한 범위보다 크다. 기존 schedule PUT을 프론트에서 재사용하는 방법은 복약 배정을 덮어쓰고 처방 없는 사용자에게 동작하지 않으므로 제외한다.

## 백엔드 설계

### 설정 DTO와 응답

기존 `NotifySettingsUpdateRequest`와 `NotifySettingsResponse`에 아래 네 필드를 추가한다.

- `morning_medication_time`
- `lunch_medication_time`
- `evening_medication_time`
- `bedtime_medication_time`

응답 필드는 `time`, PATCH 필드는 `time | None`으로 둔다. `CamelModel`의 기존 정책을 유지하므로 HTTP JSON에서는 `morningMedicationTime` 형태다. `settings_router._response`는 `UserSettings`의 네 값을 함께 반환한다.

### 부분 수정과 순서 검증

`NotifySettingsService.update`는 한 트랜잭션에서 `UserSettings`를 잠근다. 요청에 포함되지 않은 시간은 잠긴 DB 값으로 채우고, 요청된 non-null 시간만 덮어써 완성된 네 값을 만든다. DB 드라이버가 `TIME`을 `timedelta`로 반환하는 경우에도 비교와 동기화 전에 `time`으로 정규화한다.

완성된 값에 대해 다음 순서를 엄격하게 검증한다.

```text
morning < lunch < evening < bedtime
```

순서가 잘못되면 422를 반환하고 설정과 알람을 모두 변경하지 않는다. 알림 on/off 필드의 기존 부분 수정과 `notify_consented_at` 동작은 유지한다.

### 알람 재동기화

시간 필드 중 하나라도 실제 값이 바뀐 경우에만 설정을 저장한 같은 트랜잭션과 DB connection으로 `MedicationScheduleService._sync_medication_alarms`를 호출한다. 변경 트리거가 한 슬롯뿐이어도 전달값은 병합된 네 MealSlot을 모두 포함하는 `dict[MealSlot, time]`이어야 한다. 동기화 구현이 `meal_times[slot]`으로 네 슬롯을 전부 인덱싱하므로 변경된 슬롯만 전달하지 않는다.

이 방식으로 처방이 없는 사용자는 설정만 저장하고, 활성 처방이 있는 사용자는 기존 알람 계산 규칙에 따라 예약 시각이 갱신된다. 기존 schedule PUT은 수정된 동기화 로직을 계속 그대로 사용한다.

`_sync_medication_alarms`가 `is_notify_medication` 토글을 확인하지 않는 기존 동작은 이번 범위에서 바꾸지 않는다. 토글과 알람 행 생성 정책의 연동은 별도 이슈다.

## 프론트엔드 설계

### settings entity

`NotifySettings`와 업데이트 payload에 네 개의 camelCase 시간 필드를 추가한다. Pydantic의 `time` 직렬화는 초를 포함할 수 있으므로 `api.ts`에서 서버 응답을 화면용 `HH:MM`으로 정규화한다. 목업 상태에도 기본값 `08:00`, `13:00`, `19:00`, `22:00`을 넣고 실제 API와 같은 부분 병합을 수행한다.

### 공용 TimePickerSheet

`pages/medication-schedule/TimePickerSheet.tsx`를 `shared/ui`로 이동하고 barrel export에 추가한다. 현재 이 컴포넌트만 사용하는 시·분 옵션도 공용 컴포넌트와 같은 계층으로 옮겨 `shared`가 `pages`에 의존하지 않게 한다.

동작과 접근성 이름, 00분·30분 선택 규칙은 유지한다. 마이페이지와 `/medication-alarm-times`가 같은 컴포넌트를 사용한다.

### 마이페이지

기존 설정 로딩 한 번으로 알림 토글과 시간 네 개를 모두 채운다. 알림 카드 안에 다음 순서로 배치한다.

1. 복약 알림 토글
2. 영양제 알림 토글
3. 구분선과 알림 시간 네 행
4. 예약된 알림 링크

시간 행을 누르면 해당 슬롯의 `TimePickerSheet`를 연다. 적용 전 `isMealTimeOrderValid`로 즉시 안내하고, 통과하면 변경 슬롯 하나만 PATCH한다. 성공 응답 전체로 로컬 상태를 갱신해 서버가 확정한 값을 표시한다. 실패 시 기존 `ErrorDialog` 패턴으로 재시도를 제공한다.

내 관리 카드에는 `/my/visits`로 이동하는 진료일정 행을 추가한다. 예약된 알림 행은 `/my/alarms`로 이동한다.

### 기존 알림 시간 화면

`MedicationAlarmTimesPage`는 record ID와 복약 overview를 읽지 않는다. `GET /me/settings`로 네 시간을 불러오고, 한 슬롯만 `PATCH /me/settings`로 저장한다. 따라서 처방이 없는 계정과 OCR 온보딩 경로 모두 동작한다.

`/medication-alarm-times` 라우트는 유지한다. `MedicationEpisodePage`의 알림 시간 진입 버튼과 그 버튼에만 필요했던 import만 제거한다.

## 진료일정

### entity 경계

`frontend/src/entities/follow-up-visit/`에 `api.ts`, `api.mock.ts`, `types.ts`, `index.ts`를 추가한다. `USE_MOCK` 분기는 `api.ts`에만 둔다.

`api.ts` 내부의 원시 DTO 타입과 매핑 함수만 snake_case를 안다. 화면에는 다음 camelCase 개념만 노출한다.

- `id`
- `visitDate`
- `visitTime`
- `hospital`
- `createdAt`
- `updatedAt`

등록과 수정 요청도 API 경계에서 `visit_date`, `visit_time`, `hospital`로 변환한다. 빈 시간과 병원은 명시적인 `null`로 보내 기존 값을 지울 수 있게 한다.

목업에는 시간 없는 일정, 병원 없는 일정, 과거 일정이 각각 포함된다. CRUD와 날짜 범위 조회가 실 API와 같은 의미를 갖도록 메모리 상태를 갱신한다.

### `/my/visits` 화면

기본 목록은 오늘을 `start_date`로 보내 미래 일정만 조회한다. 지난 일정 보기를 켜면 시작일 제한 없이 다시 조회하여 과거와 미래를 함께 표시한다. API 페이지 제한은 화면에서 필요한 범위를 담을 수 있게 100으로 요청한다.

목록은 `visitDate`, `visitTime`, `id` 순으로 안정적으로 정렬한다. 시간 없음은 같은 날짜의 정해진 시간 뒤에 놓고 비교 과정에서 null을 직접 파싱하지 않는다. 과거 일정은 muted 스타일로 구분한다.

등록·수정 시트의 필드는 병원명, 날짜, 시간이다. 날짜만 필수이고 `type="date"`를 사용한다. 병원은 최대 255자이며 과거 날짜를 허용한다. 빈 시간은 목록에서 `시간 미정`, 빈 병원은 `병원 미정`으로 표시한다.

삭제는 별도 확인 Dialog를 거치며 “연결된 알림도 함께 삭제돼요”를 명시한다. 성공 후 목록을 갱신하고, 실패하면 시트를 유지한 채 오류를 표시한다.

## 알림 목록

`frontend/src/entities/alarm/`에 API, 목업, 타입, barrel export를 둔다. 원시 `AlarmListResponse`와 `AlarmResponse`의 snake_case는 `api.ts`의 매핑 함수에서만 처리한다.

`/my/alarms`는 `GET /alarms?status=ACTIVE&offset=0&limit=100`을 호출하고 `scheduledAt` 오름차순, 동률이면 id 오름차순으로 정렬해 가까운 예약을 먼저 보여준다. 제목, 메시지, 예정 시각, 알람 유형과 상태 중 실제 DTO에 있는 값만 표시한다. 생성, 수정, 취소 동작은 제공하지 않는다.

목록이 비어 있으면 예약된 알림이 없다는 빈 상태를 표시한다. 이 화면은 마이페이지 내부 링크로만 진입하며 BottomTabbar의 다섯 탭은 변경하지 않는다. 발송 이벤트를 알람별로 조회하는 `/alarms/{alarm_id}/events`는 N+1 호출이 필요하므로 이번 화면에서 사용하지 않는다.

## 라우팅과 화면 경계

- `/my/visits`: 진료일정 목록과 CRUD
- `/my/alarms`: 읽기 전용 알림 목록
- `/medication-alarm-times`: 유지하되 settings API 사용
- `/medications/:recordId`: 알림 시간 버튼만 제거

필요한 개발용 라우트는 동일 페이지 컴포넌트를 사용해 E2E 상태를 재현한다. `pages` 간 import는 만들지 않는다.

## 오류 처리

- 설정 순서 오류: 클라이언트에서 먼저 안내하고 서버 422도 최종 방어선으로 유지한다.
- 설정, 일정, 알림 조회 실패: 해당 섹션 또는 페이지에 재시도 가능한 오류 상태를 표시한다.
- 일정 저장 실패: 입력 시트를 닫지 않아 사용자가 입력값을 잃지 않게 한다.
- 일정 삭제 실패: 목록에서 항목을 선제 제거하지 않는다.
- 알람 목록은 읽기 전용이므로 조회 실패와 빈 목록을 구분한다.

## 테스트 전략

### 백엔드

- GET 설정 응답에 네 시간이 포함된다.
- 한 시간만 PATCH하면 나머지 값은 유지된다.
- 기존 DB 값과 합쳤을 때 순서가 잘못되는 부분 PATCH는 422다.
- 시간이 변경되면 기존 복약 알람의 예약 시각이 갱신된다.
- 알림 토글만 변경할 때 기존 동작이 유지된다.
- 기존 medication schedule PUT 회귀 테스트가 통과한다.
- 모델과 마이그레이션 변경이 없다.

### 프론트엔드와 E2E

- 마이페이지에서 네 시간과 두 링크가 보이고 시간 수정이 저장된다.
- 처방 상세에서 알림 시간 버튼이 사라진다.
- 기존 알림 시간 페이지가 settings API로 불러오기와 저장을 수행한다.
- 진료일정 등록, 수정, 삭제와 선택 병원·시간, 과거 일정, null-safe 정렬을 검증한다.
- 알림 목록이 `status=ACTIVE`를 요청하고 예정 시각 오름차순과 빈 상태를 올바르게 표시하는지 검증한다.
- 목업 모드와 실 API 모드 모두 실패 0으로 실행한다.
- 375px에서 가로 스크롤이 없고 BottomTabbar가 다섯 개다.
- TSX에 6자리 hex 색상이 추가되지 않는다.

## 범위 제외

- UserSettings와 FollowUpVisit 모델 또는 마이그레이션 변경
- 새 진료일정 또는 알림 시간 백엔드 라우터
- 기존 medication schedule PUT 삭제 또는 요청 축소
- `/medication-alarm-times` 삭제
- 알림 목록에서 생성, 수정, 취소 기능
- 알람별 발송 이벤트를 모은 수신함
- `is_notify_medication` 토글과 예약 알람 행 생성 정책 변경
- 하단 탭 여섯 번째 항목
- #225의 복약 페이지 개편과 연도 표시
