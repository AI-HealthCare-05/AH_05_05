# #226 My Page, Visits, and Scheduled Alarms Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let users edit account-level medication times from My Page, manage follow-up visits, and inspect active scheduled alarms without adding models or migrations.

**Architecture:** Extend the existing `/me/settings` aggregate and reuse `MedicationScheduleService._sync_medication_alarms` with a complete four-slot dictionary. Keep snake_case follow-up and alarm DTOs inside entity API adapters, and expose only camelCase screen types to the new pages.

**Tech Stack:** Python 3.13, FastAPI, Pydantic, Tortoise ORM, pytest; React 19, TypeScript, React Router 7, Tailwind CSS, Radix UI, Playwright.

**Spec:** `docs/superpowers/specs/2026-09-02-my-page-visits-design.md`

## Global Constraints

- Work on `feature/226` and use commit messages shaped as `[feature/226][신동훈]내용`.
- Do not add migrations or modify anything under `app/models/`.
- Do not add or modify follow-up visit backend endpoints.
- Keep `PUT /med/medication/schedule/{record_id}` and `/medication-alarm-times` working.
- Reuse `MedicationScheduleService._sync_medication_alarms`; never copy its scheduling logic.
- Pass all four merged MealSlot values whenever synchronization runs.
- Do not connect `is_notify_medication` to alarm-row creation in this issue.
- Keep BottomTabbar at five tabs.
- Keep `USE_MOCK` branching inside each entity's `api.ts`.
- No page may import another page.
- Do not add six-digit hex colors to TSX.

---

### Task 1: Extend `/me/settings` with medication times

**Files:**
- Modify: `app/tests/user_apis/test_notify_settings_api.py`
- Modify: `app/dtos/settings.py`
- Modify: `app/apis/v1/settings_router.py`
- Modify: `app/services/settings.py`
- Regression test: `app/tests/med_apis/test_medication_schedule_api.py`

**Interfaces:**
- Consumes: `MedicationScheduleService._sync_medication_alarms(user_id, meal_times, connection)` where `meal_times` contains MORNING, LUNCH, EVENING, and BEDTIME.
- Produces: `GET/PATCH /api/v1/me/settings` fields `morningMedicationTime`, `lunchMedicationTime`, `eveningMedicationTime`, and `bedtimeMedicationTime`.

- [ ] **Step 1: Add failing response and partial-merge tests**

Update the default response assertion and add focused tests:

```python
assert response.json() == {
    "notifyMedication": False,
    "notifySupplement": False,
    "notifyConsentedAt": None,
    "morningMedicationTime": "08:00:00",
    "lunchMedicationTime": "13:00:00",
    "eveningMedicationTime": "19:00:00",
    "bedtimeMedicationTime": "22:00:00",
}

async def test_patch_updates_one_time_and_keeps_the_other_three(self):
    client, headers = await self.create_authenticated_client("notify-time@example.com")
    try:
        response = await client.patch(
            "/api/v1/me/settings",
            headers=headers,
            json={"morningMedicationTime": "07:30"},
        )
    finally:
        await client.aclose()

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert {
        key: body[key]
        for key in (
            "morningMedicationTime",
            "lunchMedicationTime",
            "eveningMedicationTime",
            "bedtimeMedicationTime",
        )
    } == {
        "morningMedicationTime": "07:30:00",
        "lunchMedicationTime": "13:00:00",
        "eveningMedicationTime": "19:00:00",
        "bedtimeMedicationTime": "22:00:00",
    }

async def test_patch_rejects_invalid_order_after_merging_database_values(self):
    client, headers = await self.create_authenticated_client("notify-order@example.com")
    try:
        response = await client.patch(
            "/api/v1/me/settings",
            headers=headers,
            json={"morningMedicationTime": "21:00"},
        )
    finally:
        await client.aclose()

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    settings = await UserSettings.get(user__email="notify-order@example.com")
    assert settings.morning_medication_time == time(8, 0)
```

- [ ] **Step 2: Run the focused settings tests and confirm RED**

Run:

```bash
uv run pytest app/tests/user_apis/test_notify_settings_api.py -q
```

Expected: the response lacks the four new fields and the time-only PATCH tests fail.

- [ ] **Step 3: Add a failing alarm-resynchronization test**

Create an active care episode and scheduled medication using the same model setup as `test_medication_schedule_api.py`, save the initial schedule through the existing PUT, then change one time through settings:

```python
patched = await client.patch(
    "/api/v1/me/settings",
    headers=headers,
    json={"morningMedicationTime": "09:00"},
)
alarm = await Alarm.get(user=user, alarm_type=AlarmType.MEDICATION, meal_slot=MealSlot.MORNING)

assert patched.status_code == status.HTTP_200_OK
assert alarm.scheduled_at.strftime("%H:%M") == "09:00"
assert alarm.next_trigger_at == alarm.scheduled_at
```

Use `datetime.now(config.TIMEZONE).date().isoformat()` as the schedule start date so the alarm window is active when the test runs.

- [ ] **Step 4: Run the synchronization test and confirm RED**

Run:

```bash
uv run pytest app/tests/user_apis/test_notify_settings_api.py -q -k "time or alarm"
```

Expected: no medication time field is accepted yet, or the existing alarm remains at its original hour.

- [ ] **Step 5: Implement DTO fields, normalization, merge validation, and synchronization**

Add `time` fields to both DTOs. In `app/services/settings.py` define explicit slot metadata and one driver-safe normalization helper:

```python
_TIME_FIELDS = {
    MealSlot.MORNING: "morning_medication_time",
    MealSlot.LUNCH: "lunch_medication_time",
    MealSlot.EVENING: "evening_medication_time",
    MealSlot.BEDTIME: "bedtime_medication_time",
}

def normalize_medication_time(value: time | timedelta) -> time:
    if isinstance(value, time):
        return value
    seconds = int(value.total_seconds()) % (24 * 60 * 60)
    hour, remainder = divmod(seconds, 60 * 60)
    minute, second = divmod(remainder, 60)
    return time(hour, minute, second)
```

Inside the existing transaction:

```python
meal_times = {
    slot: normalize_medication_time(getattr(settings, field_name))
    for slot, field_name in _TIME_FIELDS.items()
}
for slot, field_name in _TIME_FIELDS.items():
    value = supplied.get(field_name)
    if value is not None:
        meal_times[slot] = value

ordered = [meal_times[slot] for slot in SLOT_ORDER]
if any(first >= second for first, second in zip(ordered, ordered[1:], strict=False)):
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail="Medication times must be ordered morning, lunch, evening, bedtime.",
    )
```

Track actual time changes separately from notification-toggle changes. Save changed settings with the locked connection, then call:

```python
if medication_times_changed:
    await MedicationScheduleService._sync_medication_alarms(
        user.id,
        meal_times,
        connection,
    )
```

Do not pass a partial dictionary. Use `normalize_medication_time` in `settings_router._response` so SQLite `time` and MySQL `timedelta` values serialize consistently.

- [ ] **Step 6: Run backend focused tests and regressions**

Run:

```bash
uv run pytest app/tests/user_apis/test_notify_settings_api.py app/tests/med_apis/test_medication_schedule_api.py -q
uv run ruff check app/apis/v1/settings_router.py app/dtos/settings.py app/services/settings.py app/tests/user_apis/test_notify_settings_api.py
uv run ruff format --check app/apis/v1/settings_router.py app/dtos/settings.py app/services/settings.py app/tests/user_apis/test_notify_settings_api.py
```

Expected: all commands pass; no migration or model file appears in `git status`.

- [ ] **Step 7: Commit the backend settings slice**

```bash
git add app/apis/v1/settings_router.py app/dtos/settings.py app/services/settings.py app/tests/user_apis/test_notify_settings_api.py
git commit -m "[feature/226][신동훈]사용자 복약 알림 시간 설정 추가"
```

---

### Task 2: Share the time picker and make the legacy time page account-scoped

**Files:**
- Modify: `frontend/src/entities/settings/types.ts`
- Modify: `frontend/src/entities/settings/api.ts`
- Modify: `frontend/src/entities/settings/api.mock.ts`
- Modify: `frontend/src/entities/settings/index.ts`
- Move: `frontend/src/pages/medication-schedule/TimePickerSheet.tsx` → `frontend/src/shared/ui/TimePickerSheet.tsx`
- Move: `frontend/src/pages/medication-schedule/timePresets.ts` → `frontend/src/shared/ui/timePickerOptions.ts`
- Modify: `frontend/src/shared/ui/index.ts`
- Modify: `frontend/src/pages/medication-schedule/MedicationSchedulePage.tsx`
- Modify: `frontend/src/pages/medication-schedule/MedicationAlarmTimesPage.tsx`
- Modify: `frontend/src/pages/medications/MedicationEpisodePage.tsx`
- Modify: `frontend/tests/e2e/remaining-pages.spec.ts`

**Interfaces:**
- Produces: `MedicationTimes` with four `HH:MM` strings and `UpdateNotifySettingsPayload` accepting any subset of them.
- Produces: `TimePickerSheet` from `@/shared/ui`.
- Consumes: `getNotifySettings()` and `updateNotifySettings(payload)` on the account-scoped time page.

- [ ] **Step 1: Replace the obsolete prescription-detail E2E expectation**

Change the test that clicks the detail-page “알림 시간” button into two expectations:

```typescript
test('처방 상세에는 사용자 공통 알림 시간 진입 버튼이 없다', async ({ page }) => {
  await page.goto('/dev/medications');
  await page.getByRole('button', { name: /8월 22일 처방.*약 4개/ }).click();
  await expect(page.getByRole('button', { name: /알림 시간/ })).toHaveCount(0);
});

test('알림 시간 전용 화면은 처방 ID 없이 사용자 설정을 저장한다', async ({ page }) => {
  await page.goto('/dev/medication-alarm-times');
  await expect(page.getByRole('button', { name: /아침약 08:00/ })).toBeVisible();
  await page.getByRole('button', { name: /아침약 08:00/ }).click();
  await chooseAlarmTime(page, '12', '30');
  await page.getByRole('button', { name: '이 시간 적용' }).click();
  await expect(page.getByRole('button', { name: /아침약 12:30/ })).toBeVisible();
});
```

- [ ] **Step 2: Run the affected Playwright spec and confirm RED**

Run:

```bash
cd frontend
npx playwright test tests/e2e/remaining-pages.spec.ts --grep "알림 시간" --reporter=list
```

Expected: the old detail button still exists and the time page still loads a medication overview.

- [ ] **Step 3: Extend the settings entity and normalize server times**

Add:

```typescript
export interface MedicationTimes {
  morningMedicationTime: string;
  lunchMedicationTime: string;
  eveningMedicationTime: string;
  bedtimeMedicationTime: string;
}

export interface NotifySettings extends MedicationTimes {
  notifyMedication: boolean;
  notifySupplement: boolean;
  notifyConsentedAt: string | null;
}
```

Keep a raw API response type in `api.ts` and normalize each time with `value.slice(0, 5)`:

```typescript
function mapNotifySettings(response: NotifySettingsApiResponse): NotifySettings {
  return {
    ...response,
    morningMedicationTime: response.morningMedicationTime.slice(0, 5),
    lunchMedicationTime: response.lunchMedicationTime.slice(0, 5),
    eveningMedicationTime: response.eveningMedicationTime.slice(0, 5),
    bedtimeMedicationTime: response.bedtimeMedicationTime.slice(0, 5),
  };
}
```

Apply the mapper to GET and PATCH real responses. Add the four defaults to `api.mock.ts` and keep mock PATCH as a partial merge.

- [ ] **Step 4: Move the picker and switch all imports**

Move the picker and option constants with `apply_patch`-backed file changes. Export the component and props from `shared/ui/index.ts`. Update `MedicationSchedulePage` and `MedicationAlarmTimesPage` to import it from `@/shared/ui`.

- [ ] **Step 5: Rewrite `MedicationAlarmTimesPage` around settings**

Replace `overview` and `recordId` state with `NotifySettings`. Load `getNotifySettings` on mount. Build the displayed `MealTimes` object from the four settings fields and PATCH only the selected camelCase field:

```typescript
const SETTINGS_FIELD_BY_SLOT: Record<MealSlot, keyof MedicationTimes> = {
  morning: 'morningMedicationTime',
  lunch: 'lunchMedicationTime',
  evening: 'eveningMedicationTime',
  bedtime: 'bedtimeMedicationTime',
};

const saved = await updateNotifySettings({
  [SETTINGS_FIELD_BY_SLOT[editingSlot]]: time,
});
setSettings(saved);
```

Keep client order validation, success toast, retry dialog, and the existing route. Remove the detail-page alarm button and its now-unused `ChevronRight` import.

- [ ] **Step 6: Run frontend checks**

Run:

```bash
cd frontend
pnpm typecheck
npx playwright test tests/e2e/remaining-pages.spec.ts --grep "알림 시간" --reporter=list
```

Expected: typecheck passes, the detail button is absent, and the direct time page saves without a prescription ID.

- [ ] **Step 7: Commit the shared time flow**

```bash
git add frontend/src/entities/settings frontend/src/shared/ui frontend/src/pages/medication-schedule frontend/src/pages/medications/MedicationEpisodePage.tsx frontend/tests/e2e/remaining-pages.spec.ts
git commit -m "[feature/226][신동훈]복약 알림 시간을 사용자 설정으로 이관"
```

---

### Task 3: Put medication times inside My Page

**Files:**
- Modify: `frontend/src/pages/my/MyPage.tsx`
- Create: `frontend/tests/e2e/my-settings.spec.ts`

**Interfaces:**
- Consumes: `NotifySettings`, `updateNotifySettings`, `TimePickerSheet`, `MEAL_SLOTS`, and `isMealTimeOrderValid`.
- Produces: four inline time rows inside the existing notification card.

- [ ] **Step 1: Write mock-mode My Page E2E tests**

Guard the file with:

```typescript
test.beforeEach(() => {
  test.skip(IS_REAL_API, MOCK_ONLY_REASON);
});
```

Test all four labels, one successful edit, invalid order, and 375px overflow:

```typescript
await page.goto('/dev/my-authenticated');
await expect(page.getByRole('button', { name: /아침 08:00/ })).toBeVisible();
await expect(page.getByRole('button', { name: /점심 13:00/ })).toBeVisible();
await expect(page.getByRole('button', { name: /저녁 19:00/ })).toBeVisible();
await expect(page.getByRole('button', { name: /자기전 22:00/ })).toBeVisible();

const overflow = await page.evaluate(
  () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
);
expect(overflow).toBeLessThanOrEqual(0);
```

- [ ] **Step 2: Run the new spec and confirm RED**

Run:

```bash
cd frontend
npx playwright test tests/e2e/my-settings.spec.ts --reporter=list
```

Expected: no inline time rows exist yet.

- [ ] **Step 3: Implement the inline rows**

Add `editingSlot` and time-order error state to `MyPage`. Render a titled “알림 시간” group after the two notification toggles. Use the exact row labels `아침`, `점심`, `저녁`, and `자기전`; do not reuse the medication-page labels `아침약` and `취침약`. Each row is a full-width button with its label, `HH:MM` value, and chevron. Reuse `TimePickerSheet` and PATCH one field using the same slot-to-settings mapping as Task 2.

On invalid ordering, keep the picker open and show:

```text
복약 시간은 아침약 → 점심약 → 저녁약 → 취침약 순서로 설정해주세요.
```

On success, replace the full settings state with the PATCH response and show “알림 시간을 바꿨어요.”

- [ ] **Step 4: Run focused E2E and notification regressions**

Run:

```bash
cd frontend
pnpm typecheck
npx playwright test tests/e2e/my-settings.spec.ts tests/e2e/notification-permission-flow.spec.ts --reporter=list
```

Expected: time interactions pass and the two existing push-permission toggles retain their behavior.

- [ ] **Step 5: Commit the My Page time card**

```bash
git add frontend/src/pages/my/MyPage.tsx frontend/tests/e2e/my-settings.spec.ts
git commit -m "[feature/226][신동훈]마이페이지 복약 알림 시간 추가"
```

---

### Task 4: Build follow-up visit entity and CRUD page

**Files:**
- Create: `frontend/src/entities/follow-up-visit/types.ts`
- Create: `frontend/src/entities/follow-up-visit/api.mock.ts`
- Create: `frontend/src/entities/follow-up-visit/api.ts`
- Create: `frontend/src/entities/follow-up-visit/index.ts`
- Create: `frontend/src/pages/my/FollowUpVisitsPage.tsx`
- Create: `frontend/src/pages/my/FollowUpVisitSheet.tsx`
- Create: `frontend/src/pages/my/DeleteFollowUpVisitDialog.tsx`
- Modify: `frontend/src/pages/my/index.ts`
- Modify: `frontend/src/pages/my/MyPage.tsx`
- Modify: `frontend/src/app/router.tsx`
- Create: `frontend/tests/e2e/follow-up-visits.spec.ts`

**Interfaces:**
- Produces: `FollowUpVisit`, `FollowUpVisitInput`, `listFollowUpVisits`, `createFollowUpVisit`, `updateFollowUpVisit`, and `deleteFollowUpVisit`.
- Consumes: existing backend `/v1/user/follow-up-visits` snake_case contract.

- [ ] **Step 1: Write mock CRUD and edge-case E2E tests**

Guard the spec as mock-only. Verify:

```typescript
await page.goto('/dev/my-visits');
await expect(page.getByText('시간 미정')).toBeVisible();
await expect(page.getByText('병원 미정')).toBeVisible();
await page.getByRole('button', { name: '지난 일정 보기' }).click();
await expect(page.getByText(/지난 진료/)).toBeVisible();
```

Add a create case with blank hospital and time, an edit case that clears both optional values, and a delete case that asserts the dialog contains “연결된 알림도 함께 삭제돼요.”

- [ ] **Step 2: Run the new visit spec and confirm RED**

Run:

```bash
cd frontend
npx playwright test tests/e2e/follow-up-visits.spec.ts --reporter=list
```

Expected: `/dev/my-visits` has no route.

- [ ] **Step 3: Implement types, DTO mapping, and mock behavior**

Define screen types:

```typescript
export interface FollowUpVisit {
  id: number;
  visitDate: string;
  visitTime: string | null;
  hospital: string | null;
  createdAt: string;
  updatedAt: string | null;
}

export interface FollowUpVisitInput {
  visitDate: string;
  visitTime: string | null;
  hospital: string | null;
}

export interface FollowUpVisitListParams {
  startDate?: string;
  endDate?: string;
}

export function listFollowUpVisits(
  params?: FollowUpVisitListParams,
): Promise<FollowUpVisit[]>;
export function createFollowUpVisit(input: FollowUpVisitInput): Promise<FollowUpVisit>;
export function updateFollowUpVisit(
  visitId: number,
  input: FollowUpVisitInput,
): Promise<FollowUpVisit>;
export function deleteFollowUpVisit(visitId: number): Promise<void>;
```

Keep raw `visit_date`, `visit_time`, `created_at`, and `updated_at` types inside `api.ts`. Implement one `mapFollowUpVisit` and request serializers there. Build list URLs with `URLSearchParams` using `start_date`, `end_date`, `offset=0`, and `limit=100`.

The mock begins with three distinct cases: one missing time, one missing hospital, and one past visit. Apply the same start/end filtering and CRUD mutation semantics as the server.

- [ ] **Step 4: Implement the page and dialogs**

`FollowUpVisitsPage` owns loading, show-past state, selection, save/delete pending state, and errors. Sort with:

```typescript
function compareVisits(left: FollowUpVisit, right: FollowUpVisit): number {
  const dateOrder = left.visitDate.localeCompare(right.visitDate);
  if (dateOrder !== 0) return dateOrder;
  const leftTime = left.visitTime ?? '24:00';
  const rightTime = right.visitTime ?? '24:00';
  return leftTime.localeCompare(rightTime) || left.id - right.id;
}
```

The sheet uses a 255-character hospital input, required date input, and optional time input. Empty optional fields serialize to `null`; past dates have no `min` restriction. The delete dialog states the alarm cascade explicitly.

Register `/my/visits` and `/dev/my-visits`. Add the My Page management row labeled “진료일정”.

- [ ] **Step 5: Run visit tests and frontend checks**

Run:

```bash
cd frontend
pnpm typecheck
npx playwright test tests/e2e/follow-up-visits.spec.ts --reporter=list
```

Expected: CRUD, optional fields, past-list toggle, null-safe sorting, delete copy, and 375px layout pass.

- [ ] **Step 6: Confirm backend visit files are untouched**

Run:

```bash
git diff origin/main -- app/models/care.py app/apis/v1/follow_up_visit_router.py app/dtos/follow_up_visits.py app/services/follow_up_visits.py
```

Expected: no output.

- [ ] **Step 7: Commit the visit frontend**

```bash
git add frontend/src/entities/follow-up-visit frontend/src/pages/my frontend/src/app/router.tsx frontend/tests/e2e/follow-up-visits.spec.ts
git commit -m "[feature/226][신동훈]진료일정 관리 화면 추가"
```

---

### Task 5: Build the active scheduled-alarm page

**Files:**
- Create: `frontend/src/entities/alarm/types.ts`
- Create: `frontend/src/entities/alarm/api.mock.ts`
- Create: `frontend/src/entities/alarm/api.ts`
- Create: `frontend/src/entities/alarm/index.ts`
- Create: `frontend/src/pages/my/ScheduledAlarmsPage.tsx`
- Modify: `frontend/src/pages/my/index.ts`
- Modify: `frontend/src/pages/my/MyPage.tsx`
- Modify: `frontend/src/app/router.tsx`
- Create: `frontend/tests/e2e/scheduled-alarms.spec.ts`

**Interfaces:**
- Produces: `ScheduledAlarm` and `getActiveScheduledAlarms()`.
- Consumes: `GET /v1/alarms?status=ACTIVE&offset=0&limit=100`.

- [ ] **Step 1: Write mock-mode list, sorting, and empty-state tests**

Guard the spec as mock-only. Verify the My Page row is labeled “예약된 알림”, the route is `/my/alarms`, the earliest scheduled time is first, and an injected empty list displays “예약된 알림이 없어요.”

Give `ScheduledAlarmsPage` an optional `alarmLoader?: () => Promise<ScheduledAlarm[]>` prop whose default is `getActiveScheduledAlarms`. Register `/dev/my-alarms-empty` with `alarmLoader={async () => []}` instead of adding mode logic to the page.

- [ ] **Step 2: Run the scheduled-alarm spec and confirm RED**

Run:

```bash
cd frontend
npx playwright test tests/e2e/scheduled-alarms.spec.ts --reporter=list
```

Expected: no scheduled-alarm route or My Page row exists.

- [ ] **Step 3: Implement the entity adapter**

Define only fields exposed by `AlarmResponse`:

```typescript
export interface ScheduledAlarm {
  id: number;
  alarmType: string;
  mealSlot: string | null;
  title: string;
  message: string | null;
  scheduledAt: string;
  recurrenceRule: string | null;
  status: string;
}

export function getActiveScheduledAlarms(): Promise<ScheduledAlarm[]>;
```

Keep snake_case in a private raw response type and map it once. Request exactly:

```typescript
const response = await http.get<AlarmListApiResponse>(
  '/v1/alarms?status=ACTIVE&offset=0&limit=100',
);
return response.items.map(mapScheduledAlarm).sort(compareScheduledAlarms);
```

Sort `scheduledAt` ascending and id ascending for ties. The mock should contain out-of-order active alarms so the sort is observable.

- [ ] **Step 4: Implement the read-only page**

Render a back header titled “예약된 알림”. Cards show title, optional message, formatted scheduled date/time, and a human-readable alarm type or meal slot. Do not render edit, cancel, or create controls. Add a loader override for the empty-state dev route.

Register `/my/alarms`, `/dev/my-alarms`, and `/dev/my-alarms-empty`. Add the My Page notification-card row labeled “예약된 알림”. Do not modify `BottomTabbar.tsx`.

- [ ] **Step 5: Run scheduled-alarm checks**

Run:

```bash
cd frontend
pnpm typecheck
npx playwright test tests/e2e/scheduled-alarms.spec.ts --reporter=list
```

Expected: active query semantics, ascending display order, read-only UI, and empty state pass.

- [ ] **Step 6: Commit the scheduled-alarm frontend**

```bash
git add frontend/src/entities/alarm frontend/src/pages/my frontend/src/app/router.tsx frontend/tests/e2e/scheduled-alarms.spec.ts
git commit -m "[feature/226][신동훈]예약된 알림 목록 추가"
```

---

### Task 6: Verify real API adapters and the complete feature

**Files:**
- Create: `frontend/tests/e2e/my-management-api.spec.ts`
- Verify or correct: `frontend/src/entities/settings/api.ts`
- Verify or correct: `frontend/src/entities/follow-up-visit/api.ts`
- Verify or correct: `frontend/src/entities/alarm/api.ts`

**Interfaces:**
- Consumes: all public APIs and routes created in Tasks 1–5.
- Produces: evidence that mock and real API modes both finish with zero failures.

- [ ] **Step 1: Write real-API-only contract tests**

Guard the file with:

```typescript
test.beforeEach(() => {
  test.skip(!IS_REAL_API, REAL_API_ONLY_REASON);
});
```

Intercept `/api/v1/me/settings` and assert a one-field time PATCH body stays camelCase while `08:00:00` is returned to screens as `08:00`. Intercept follow-up visits and assert query names `start_date`, `offset=0`, `limit=100` plus snake_case-to-camelCase mapping. Intercept alarms and assert:

```typescript
expect(url.searchParams.get('status')).toBe('ACTIVE');
expect(url.searchParams.get('offset')).toBe('0');
expect(url.searchParams.get('limit')).toBe('100');
expect(result.map((alarm) => alarm.id)).toEqual([2, 1]);
```

Use scheduled times where id 2 is earlier than id 1 so ascending behavior is explicit.

- [ ] **Step 2: Run real API contract tests and confirm behavior**

Run:

```bash
cd frontend
VITE_USE_MOCK=false npx playwright test tests/e2e/my-management-api.spec.ts --reporter=list
```

Expected: all contract tests pass after Tasks 1–5. If one fails, adjust only the corresponding entity adapter and rerun this command.

- [ ] **Step 3: Run backend verification**

Run:

```bash
uv run pytest app/tests/user_apis/test_notify_settings_api.py app/tests/med_apis/test_medication_schedule_api.py app/tests/follow_up_visit_apis/test_follow_up_visit_crud_api.py app/tests/alarm_apis/test_alarm_crud_api.py -q
uv run ruff check app/apis/v1/settings_router.py app/dtos/settings.py app/services/settings.py app/tests/user_apis/test_notify_settings_api.py
uv run ruff format --check app/apis/v1/settings_router.py app/dtos/settings.py app/services/settings.py app/tests/user_apis/test_notify_settings_api.py
```

Expected: all tests and static checks pass.

- [ ] **Step 4: Run frontend static verification**

Run:

```bash
cd frontend
pnpm typecheck
pnpm build
```

Expected: both commands exit 0.

- [ ] **Step 5: Run both complete Playwright modes**

Run:

```bash
cd frontend
npx playwright test --reporter=list
VITE_USE_MOCK=false npx playwright test --reporter=list
```

Expected: both commands report zero failed tests. Record passed, skipped, and failed counts for each mode, and confirm the sum of skip counts does not hide a test in both modes.

- [ ] **Step 6: Run scope and UI invariant checks**

Run:

```bash
git diff --name-only origin/main
git diff origin/main -- app/models app/core/db/migrations app/apis/v1/follow_up_visit_router.py
rg -n "#[0-9a-fA-F]{6}" frontend/src -g "*.tsx"
rg -n "@/pages/" frontend/src/pages frontend/src/shared frontend/src/entities
```

Expected:

- No model, migration, or follow-up router diff.
- No new six-digit hex color in TSX.
- No page-to-page import.
- `frontend/src/shared/ui/BottomTabbar.tsx` is unchanged.

- [ ] **Step 7: Commit the real API contract tests and verified adjustments**

```bash
git add frontend/tests/e2e/my-management-api.spec.ts
git add app/apis/v1/settings_router.py app/dtos/settings.py app/services/settings.py app/tests/user_apis/test_notify_settings_api.py frontend/src frontend/tests/e2e
git commit -m "[feature/226][신동훈]마이페이지 개편 통합 검증 추가"
```

If the second `git add` has no additional changes, commit only the new contract spec. Before push or PR creation, rerun `git status --short` and ensure it is empty.
