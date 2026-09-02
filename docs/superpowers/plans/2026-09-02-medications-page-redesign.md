# Medications Page Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the prescription detail route with a filterable, multi-expand medication list that uses server-computed completion state and supports sequential multi-delete.

**Architecture:** FastAPI resolves calendar-month query bounds and prescription end dates in shared pure service functions, then exposes `isFinished` through the existing medication overview contract. React keeps filters in URL search params while expansion and selection remain local state; page-specific cards and dialogs isolate the accordion, filtering, and partial-delete behavior.

**Tech Stack:** Python 3.13, FastAPI, Tortoise ORM, Pydantic `CamelModel`, React 19, TypeScript, React Router 7, Tailwind CSS, Radix UI, Playwright.

**Spec:** `docs/superpowers/specs/2026-09-02-medications-page-redesign.md`

## Global Constraints

- Work only on branch `feature/225`, based on the `main` commit that merged #226.
- Commit messages use `[feature/225][신동훈]내용`; do not use Conventional Commits.
- Do not change anything under `app/models/` or create a migration.
- Do not write `completed_at`, add a completion batch, or use `CareEpisodeStatus.COMPLETED` in production code.
- Keep physical deletion and bulk deletion APIs out of scope; use the existing soft-delete endpoint sequentially.
- Do not compute `isFinished` from `endDate` in the frontend.
- Do not change the rendered date strings on Home.
- Do not add frontend dependencies.
- Never run `pnpm install`, `npm i`, `npm install`, `yarn`, `pnpm add`, `pnpm update`, or any command that repairs `node_modules` or a lockfile on Windows.
- The worktree currently has no `frontend/node_modules`. Do not run a frontend command until the developer has prepared dependencies from WSL. Once prepared, invoke checked-in binaries directly (`./node_modules/.bin/tsc`, `./node_modules/.bin/vite`, `./node_modules/.bin/playwright`) so no package manager can auto-install.
- The known #218 `signup-real-api-contract.spec.ts` failure exists on `origin/main`; report it separately from #225 regressions.

---

### Task 1: Server medication range and completion contract

**Files:**
- Create: `app/services/medication_period.py`
- Modify: `app/core/exceptions.py`
- Modify: `app/dtos/medications.py`
- Modify: `app/apis/v1/medication_router.py`
- Modify: `app/services/medications.py`
- Test: `app/tests/med_apis/test_medications_api.py`

**Interfaces:**
- Produces: `resolve_medication_overview_range(from_date: date | None, to_date: date | None, today: date) -> tuple[date, date]`
- Produces: `medication_end_date(episode: CareEpisode, medications: Sequence[Medication]) -> date`
- Produces: `MedicationOverview.is_finished: bool`, serialized as `isFinished`
- Produces: `MedicationService.list_overviews(user, from_date=None, to_date=None)`
- Consumes: `config.TIMEZONE`, `dateutil.relativedelta.relativedelta`, current `ACTIVE` soft-delete contract

- [ ] **Step 1: Write failing range and response tests**

Add API tests with hand-derived dates to `TestMedicationOverviewAPI`:

```python
async def test_overview_defaults_to_three_calendar_months_and_returns_is_finished(self) -> None:
    today = datetime.now(config.TIMEZONE).date()
    inside_start = today - relativedelta(months=3)
    outside_start = inside_start - timedelta(days=1)
    # Create both episodes with OCR IDs and medication rows.
    response = await client.get(OVERVIEW_URL, headers=headers)
    assert response.status_code == status.HTTP_200_OK
    assert [item["recordId"] for item in response.json()] == [inside.id]
    assert response.json()[0]["isFinished"] is True

async def test_overview_filters_by_start_date_and_orders_latest_start_then_id(self) -> None:
    response = await client.get(
        OVERVIEW_URL,
        params={"from": "2026-06-01", "to": "2026-08-31"},
        headers=headers,
    )
    assert [item["recordId"] for item in response.json()] == [newer_id, higher_same_day_id, lower_same_day_id]

async def test_overview_resolves_single_sided_ranges(self) -> None:
    from_only = await client.get(OVERVIEW_URL, params={"from": "2026-01-31"}, headers=headers)
    to_only = await client.get(OVERVIEW_URL, params={"to": today.isoformat()}, headers=headers)
    assert from_only.status_code == status.HTTP_200_OK
    assert to_only.status_code == status.HTTP_200_OK

async def test_overview_rejects_reversed_or_over_five_year_ranges(self) -> None:
    reversed_range = await client.get(
        OVERVIEW_URL,
        params={"from": "2026-09-02", "to": "2026-09-01"},
        headers=headers,
    )
    too_wide = await client.get(
        OVERVIEW_URL,
        params={"from": "2020-09-01", "to": "2026-09-02"},
        headers=headers,
    )
    assert reversed_range.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert too_wide.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
```

Also create ACTIVE episodes ending yesterday, today, and tomorrow and assert literal `isFinished` values `[True, False, False]`. Add a CANCELLED row inside the range and assert it never appears.

- [ ] **Step 2: Run the focused backend tests and verify RED**

Run:

```bash
uv run pytest app/tests/med_apis/test_medications_api.py -q
```

Expected: the new tests fail because query parameters and `isFinished` do not exist and the old list includes all ACTIVE start dates.

- [ ] **Step 3: Add explicit range validation error**

Add to `app/core/exceptions.py`:

```python
class InvalidMedicationOverviewDateRangeError(AppError):
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    code = "INVALID_MEDICATION_OVERVIEW_DATE_RANGE"
    message = "복약 기록 조회 기간이 올바르지 않습니다."
```

- [ ] **Step 4: Implement shared calendar range and end-date functions**

Create `app/services/medication_period.py` with these concrete rules:

```python
from collections.abc import Sequence
from datetime import date, timedelta

from dateutil.relativedelta import relativedelta

from app.core.exceptions import InvalidMedicationOverviewDateRangeError
from app.models.care import CareEpisode
from app.models.medications import Medication

UNKNOWN_DAYS = 1


def resolve_medication_overview_range(
    from_date: date | None,
    to_date: date | None,
    today: date,
) -> tuple[date, date]:
    if from_date is None and to_date is None:
        resolved_from = today - relativedelta(months=3)
        resolved_to = today
    elif from_date is not None and to_date is None:
        resolved_from = from_date
        resolved_to = from_date + relativedelta(months=3)
    elif from_date is None and to_date is not None:
        resolved_from = today
        resolved_to = to_date
    else:
        resolved_from = from_date
        resolved_to = to_date
    if resolved_from is None or resolved_to is None:
        raise InvalidMedicationOverviewDateRangeError()
    if resolved_from > resolved_to:
        raise InvalidMedicationOverviewDateRangeError()
    if resolved_to > resolved_from + relativedelta(years=5):
        raise InvalidMedicationOverviewDateRangeError()
    return resolved_from, resolved_to


def medication_end_date(
    episode: CareEpisode,
    medications: Sequence[Medication],
) -> date:
    start_date = episode.medication_start_date
    if start_date is None:
        raise ValueError("Medication period requires a start date")
    known_days = [item.days for item in medications if item.days is not None]
    fallback_days = episode.medication_days or (max(known_days) if known_days else UNKNOWN_DAYS)
    scheduled_days = [
        item.days or fallback_days
        for item in medications
        if item.times_per_day is not None
    ]
    all_days = [item.days or fallback_days for item in medications]
    longest_days = max(scheduled_days or all_days or [fallback_days])
    return start_date + timedelta(days=longest_days - 1)
```

- [ ] **Step 5: Wire the endpoint and overview DTO**

Add `is_finished: bool` to `MedicationOverview`. Add optional aliased query parameters to `get_medications` and pass them to the service:

```python
from_date: Annotated[date | None, Query(alias="from")] = None,
to_date: Annotated[date | None, Query(alias="to")] = None,
```

In `MedicationService.list_overviews`, resolve bounds from `datetime.now(config.TIMEZONE).date()`, filter `status=CareEpisodeStatus.ACTIVE` and `medication_start_date__gte/__lte`, and order by `-medication_start_date`, `-id`. Keep the existing “only append episodes with medications” rule. In `_overview`, call `medication_end_date` and set:

```python
is_finished=end_date < today,
```

Remove the duplicated `UNKNOWN_DAYS` and end-date selection logic from `medications.py` while preserving per-medication fallback behavior.

- [ ] **Step 6: Run tests and static checks for GREEN**

Run:

```bash
uv run pytest app/tests/med_apis/test_medications_api.py -q
uv run ruff check app/services/medication_period.py app/services/medications.py app/apis/v1/medication_router.py app/dtos/medications.py app/core/exceptions.py app/tests/med_apis/test_medications_api.py
uv run ruff format --check app/services/medication_period.py app/services/medications.py app/apis/v1/medication_router.py app/dtos/medications.py app/core/exceptions.py app/tests/med_apis/test_medications_api.py
```

Expected: all commands exit 0.

- [ ] **Step 7: Commit the server list contract**

```bash
git add app/services/medication_period.py app/services/medications.py app/apis/v1/medication_router.py app/dtos/medications.py app/core/exceptions.py app/tests/med_apis/test_medications_api.py
git commit -m "[feature/225][신동훈]복약 목록 기간과 완료 판정 추가"
```

---

### Task 2: Block schedule changes for finished prescriptions

**Files:**
- Modify: `app/core/exceptions.py`
- Modify: `app/services/medication_schedule.py`
- Test: `app/tests/med_apis/test_medication_schedule_api.py`

**Interfaces:**
- Consumes: `medication_end_date` from Task 1
- Produces: 409 `MEDICATION_SCHEDULE_FINISHED` with exact user message

- [ ] **Step 1: Write failing boundary tests**

Add two tests using valid `schedule_payload` values:

```python
async def test_finished_episode_schedule_update_returns_409_without_writes(self) -> None:
    episode.medication_start_date = datetime.now(config.TIMEZONE).date() - timedelta(days=8)
    await episode.save(update_fields=["medication_start_date"])
    before_slots = await MedicationSlot.filter(medication=scheduled).count()
    response = await client.put(schedule_url(episode.id), json=schedule_payload(scheduled.id), headers=headers)
    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json() == {
        "code": "MEDICATION_SCHEDULE_FINISHED",
        "message": "이미 끝난 처방은 수정할 수 없습니다",
    }
    assert await MedicationSlot.filter(medication=scheduled).count() == before_slots

async def test_episode_ending_today_can_update_schedule(self) -> None:
    episode.medication_start_date = datetime.now(config.TIMEZONE).date() - timedelta(days=6)
    await episode.save(update_fields=["medication_start_date"])
    response = await client.put(schedule_url(episode.id), json=schedule_payload(scheduled.id), headers=headers)
    assert response.status_code == status.HTTP_200_OK
```

- [ ] **Step 2: Run the tests and verify RED**

```bash
uv run pytest app/tests/med_apis/test_medication_schedule_api.py -q
```

Expected: the finished prescription currently saves and the first new test fails.

- [ ] **Step 3: Add the conflict and guard before writes**

Add:

```python
class MedicationScheduleFinishedError(AppError):
    status_code = status.HTTP_409_CONFLICT
    code = "MEDICATION_SCHEDULE_FINISHED"
    message = "이미 끝난 처방은 수정할 수 없습니다"
```

In `MedicationScheduleService.save`, after locking and loading the episode and medication rows but before settings, episode, slot, or alarm writes:

```python
today = datetime.now(config.TIMEZONE).date()
if medication_end_date(episode, medications) < today:
    raise MedicationScheduleFinishedError()
```

- [ ] **Step 4: Run schedule and overview regression tests**

```bash
uv run pytest app/tests/med_apis/test_medication_schedule_api.py app/tests/med_apis/test_medications_api.py -q
uv run ruff check app/services/medication_schedule.py app/core/exceptions.py app/tests/med_apis/test_medication_schedule_api.py
uv run ruff format --check app/services/medication_schedule.py app/core/exceptions.py app/tests/med_apis/test_medication_schedule_api.py
```

Expected: all commands exit 0.

- [ ] **Step 5: Commit the finished-prescription guard**

```bash
git add app/core/exceptions.py app/services/medication_schedule.py app/tests/med_apis/test_medication_schedule_api.py
git commit -m "[feature/225][신동훈]완료 처방 시간표 수정 차단"
```

---

### Task 3: Shared date labels with medication-only year display

**Files:**
- Create: `frontend/src/shared/lib/dateLabel.ts`
- Modify: `frontend/src/pages/medications/MedicationsPage.tsx`
- Modify: `frontend/src/pages/home/MedicationRecordGrid.tsx`
- Modify: `frontend/src/pages/home/MedicationTimeline.tsx`
- Test: `frontend/tests/e2e/remaining-pages.spec.ts`
- Test: `frontend/tests/e2e/home-dose-record-grid.spec.ts`

**Interfaces:**
- Produces: `formatDateLabel(value, { includeYear? })`
- Produces: `formatDatePeriod(from, to, { includeYear? })`
- Preserves: Home strings with no year when the option is omitted

- [ ] **Step 1: Change E2E expectations before production code**

In `remaining-pages.spec.ts`, expect the medication card to contain `2026년 8월 22일` and add a route fixture crossing New Year that expects `2026년 12월 28일 ~ 2027년 1월 3일`. Keep the Home assertions expecting `8월 22일` without a year in `home-dose-record-grid.spec.ts`.

- [ ] **Step 2: Verify RED after WSL dependencies are prepared**

From WSL in `frontend/`:

```bash
VITE_USE_MOCK=true ./node_modules/.bin/playwright test tests/e2e/remaining-pages.spec.ts tests/e2e/home-dose-record-grid.spec.ts --reporter=list
```

Expected: the new medication-list year expectations fail while existing Home expectations still pass.

- [ ] **Step 3: Implement the shared formatter**

Create `dateLabel.ts` with a local parse that never invokes UTC conversion:

```ts
interface DateLabelOptions {
  includeYear?: boolean;
}

function dateParts(value: string): [number, number, number] | null {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  return match ? [Number(match[1]), Number(match[2]), Number(match[3])] : null;
}

export function formatDateLabel(value: string, options: DateLabelOptions = {}): string {
  const parts = dateParts(value);
  if (!parts) return value;
  const [year, month, day] = parts;
  return options.includeYear ? `${year}년 ${month}월 ${day}일` : `${month}월 ${day}일`;
}

export function formatDatePeriod(
  from: string,
  to: string,
  options: DateLabelOptions = {},
): string {
  const start = dateParts(from);
  const end = dateParts(to);
  if (!start || !end) return from && to ? `${from} ~ ${to}` : '';
  const [fromYear, fromMonth, fromDay] = start;
  const [toYear, toMonth, toDay] = end;
  if (options.includeYear && fromYear !== toYear) {
    return `${fromYear}년 ${fromMonth}월 ${fromDay}일 ~ ${toYear}년 ${toMonth}월 ${toDay}일`;
  }
  const prefix = options.includeYear ? `${fromYear}년 ` : '';
  return fromMonth === toMonth
    ? `${prefix}${fromMonth}월 ${fromDay}일 ~ ${toDay}일`
    : `${prefix}${fromMonth}월 ${fromDay}일 ~ ${toMonth}월 ${toDay}일`;
}
```

Replace local duplicate formatters in the medication list and both Home components. Pass `{ includeYear: true }` only from the medication list. Append ` 처방` at the caller where needed.

- [ ] **Step 4: Run the focused E2E for GREEN**

```bash
VITE_USE_MOCK=true ./node_modules/.bin/playwright test tests/e2e/remaining-pages.spec.ts tests/e2e/home-dose-record-grid.spec.ts --reporter=list
```

Expected: medication labels include years, cross-year periods include both years, and Home strings remain unchanged.

- [ ] **Step 5: Commit the shared date formatting**

```bash
git add frontend/src/shared/lib/dateLabel.ts frontend/src/pages/medications/MedicationsPage.tsx frontend/src/pages/home/MedicationRecordGrid.tsx frontend/src/pages/home/MedicationTimeline.tsx frontend/tests/e2e/remaining-pages.spec.ts frontend/tests/e2e/home-dose-record-grid.spec.ts
git commit -m "[feature/225][신동훈]복약 목록 날짜에 연도 표시"
```

---

### Task 4: Frontend completion contract

**Files:**
- Modify: `frontend/src/entities/medication/types.ts`
- Modify: `frontend/src/entities/medication/api.mock.ts`
- Modify: `frontend/src/pages/medications/MedicationsPage.tsx`
- Create: `frontend/tests/e2e/medications-management-api.spec.ts`
- Modify: `frontend/tests/e2e/remaining-pages.spec.ts`

**Interfaces:**
- Produces: `MedicationOverview.isFinished: boolean`
- Preserves: existing overview loading while switching status rendering from `daysRemaining` to the server field

- [ ] **Step 1: Write failing completion-field tests**

Create a real-API-only Playwright spec that routes `**/api/v1/medications` with two complete CamelModel fixtures. Give one fixture `daysRemaining: 0, isFinished: false` and the other `daysRemaining: 7, isFinished: true`. Assert the first renders `복용 중` and the second renders `복용 완료`; this proves the frontend does not infer completion from remaining days or a device date.

Add the same explicit `isFinished` literals to mock fixtures and update `remaining-pages.spec.ts` to assert both statuses.

- [ ] **Step 2: Verify RED after WSL dependencies are prepared**

```bash
VITE_USE_MOCK=false ./node_modules/.bin/playwright test tests/e2e/medications-management-api.spec.ts --reporter=list
```

Expected: status still follows `daysRemaining`, so both deliberately contradictory fixtures render the wrong state.

- [ ] **Step 3: Extend the type and mock fixtures**

Add:

```ts
export interface MedicationOverview {
  recordId: number;
  documentImageUrl: string;
  start: MedicationStartPoint;
  endDate: string;
  daysRemaining: number;
  isFinished: boolean;
  mealTimes: MealTimes;
  medications: MedicationOverviewItem[];
}
```

Update every mock fixture with an explicit `isFinished` literal. Do not derive it from mock `endDate` or `daysRemaining`.

- [ ] **Step 4: Render status only from `isFinished`**

Replace the existing local `active = overview.daysRemaining > 0` branch with:

```ts
const active = !overview.isFinished;
```

Keep D-day hidden when `isFinished` is true. This temporary card implementation will move unchanged into `MedicationEpisodeCard` in Task 5.

- [ ] **Step 5: Run focused real and mock contract tests**

```bash
VITE_USE_MOCK=false ./node_modules/.bin/playwright test tests/e2e/medications-management-api.spec.ts --reporter=list
VITE_USE_MOCK=true ./node_modules/.bin/playwright test tests/e2e/remaining-pages.spec.ts --reporter=list
```

Expected: both commands exit 0.

- [ ] **Step 6: Commit the frontend completion contract**

```bash
git add frontend/src/entities/medication/types.ts frontend/src/entities/medication/api.mock.ts frontend/src/pages/medications/MedicationsPage.tsx frontend/tests/e2e/medications-management-api.spec.ts frontend/tests/e2e/remaining-pages.spec.ts
git commit -m "[feature/225][신동훈]복약 완료 상태 계약 연결"
```

---

### Task 5: Multi-expand prescription cards and remove the detail route

**Files:**
- Modify: `frontend/src/entities/medication/api.ts`
- Modify: `frontend/src/entities/medication/index.ts`
- Create: `frontend/src/pages/medications/MedicationEpisodeCard.tsx`
- Modify: `frontend/src/pages/medications/MedicationsPage.tsx`
- Modify: `frontend/src/pages/medications/index.ts`
- Modify: `frontend/src/app/router.tsx`
- Delete: `frontend/src/pages/medications/MedicationEpisodePage.tsx`
- Test: `frontend/tests/e2e/medications-management-api.spec.ts`
- Test: `frontend/tests/e2e/remaining-pages.spec.ts`
- Test: `frontend/tests/e2e/medication-registration-flow.spec.ts`

**Interfaces:**
- Produces: page-local `expandedRecordIds: Set<number>`
- Produces: `MedicationEpisodeCard` with separate expand, select, and medication-edit actions
- Preserves: active regular-medication slot editing through `saveMedicationSchedule`

- [ ] **Step 1: Rewrite detail-route tests as accordion behavior tests**

Change the old “navigate to detail” test to click two prescription expand controls and assert both panels are visible while the URL remains `/dev/medications`. Add assertions that:

- the active card exposes a regular medication edit action;
- the finished card contains no medication edit action;
- neither card exposes `약봉투 사진 보기` or requests the source image;
- `/medications/12` no longer renders `처방 상세`;
- the existing delete-flow test starts from `/medications`, enters selection mode, and uses the new confirmation path rather than the removed route.

- [ ] **Step 2: Verify RED**

```bash
VITE_USE_MOCK=true ./node_modules/.bin/playwright test tests/e2e/remaining-pages.spec.ts tests/e2e/medication-registration-flow.spec.ts --reporter=list
```

Expected: cards navigate away, cannot remain expanded together, and the detail route still exists.

- [ ] **Step 3: Build `MedicationEpisodeCard` without nested buttons**

Use a non-interactive card root. The summary expand control has `aria-expanded` and `aria-controls`; selection mode renders a sibling `Checkbox`. The expanded panel maps all medication rows. Its edit callback is defined only when `!overview.isFinished && !medication.asNeeded`.

The summary status must be selected only by:

```ts
const statusLabel = overview.isFinished ? '복용 완료' : '복용 중';
const dDay = overview.daysRemaining <= 1
  ? 'D-Day'
  : `D-${overview.daysRemaining - 1}`;
```

Do not compare `endDate` with `new Date()`.

- [ ] **Step 4: Move detail behavior into `MedicationsPage`**

Add independent `Set<number>` expansion toggling, active-medication schedule save, and existing error handling. Multiple IDs remain in the set at once. Do not expose or request the source envelope image.

- [ ] **Step 5: Remove the detail page and route**

Delete `MedicationEpisodePage.tsx`, remove its export/import, remove the now-unused `getMedicationOverview` entity function, and remove only `/medications/:recordId`. Keep `/medications`, `/dev/medications`, medication schedule routes, and Home routes.

- [ ] **Step 6: Run accordion and route regression tests**

```bash
VITE_USE_MOCK=true ./node_modules/.bin/playwright test tests/e2e/remaining-pages.spec.ts tests/e2e/medication-registration-flow.spec.ts --reporter=list
VITE_USE_MOCK=false ./node_modules/.bin/playwright test tests/e2e/medications-management-api.spec.ts --reporter=list
./node_modules/.bin/tsc --noEmit
```

Expected: tests pass, TypeScript reports no imports of the deleted page, and two cards stay expanded.

- [ ] **Step 7: Commit the single-page accordion**

```bash
git add frontend/src/entities/medication/api.ts frontend/src/entities/medication/index.ts frontend/src/pages/medications/MedicationEpisodeCard.tsx frontend/src/pages/medications/MedicationsPage.tsx frontend/src/pages/medications/MedicationEpisodePage.tsx frontend/src/pages/medications/index.ts frontend/src/app/router.tsx frontend/tests/e2e/medications-management-api.spec.ts frontend/tests/e2e/remaining-pages.spec.ts frontend/tests/e2e/medication-registration-flow.spec.ts
git commit -m "[feature/225][신동훈]복약 상세를 목록 아코디언으로 통합"
```

---

### Task 6: URL-backed medication period filter

**Files:**
- Modify: `frontend/src/entities/medication/types.ts`
- Modify: `frontend/src/entities/medication/api.ts`
- Modify: `frontend/src/entities/medication/api.mock.ts`
- Modify: `frontend/src/entities/medication/index.ts`
- Create: `frontend/src/pages/medications/MedicationPeriodFilterSheet.tsx`
- Create: `frontend/src/pages/medications/medicationPeriod.ts`
- Modify: `frontend/src/pages/medications/MedicationsPage.tsx`
- Test: `frontend/tests/e2e/medications-management.spec.ts`
- Test: `frontend/tests/e2e/medications-management-api.spec.ts`

**Interfaces:**
- Produces: `MedicationOverviewRange { from?: string; to?: string }`
- Produces: `getMedicationOverviews(range?: MedicationOverviewRange)`
- Produces: `MedicationPeriodPreset = 'one-month' | 'three-months' | 'six-months' | 'custom'`
- Produces: pure local-date helpers that return `{ from?: string; to?: string }`
- Consumes: `useSearchParams` and `getMedicationOverviews(range)`

- [ ] **Step 1: Write failing mock and real filter tests**

Cover these observable behaviors:

```ts
test('기본 최근 3개월은 URL 쿼리 없이 조회한다', async ({ page }) => {
  await page.goto('/dev/medications');
  await expect(page).toHaveURL(/\/dev\/medications$/);
  await expect(page.getByRole('button', { name: '최근 3개월' })).toBeVisible();
});

test('최근 6개월과 직접 지정은 URL에 남고 뒤로가기로 복원된다', async ({ page }) => {
  await page.goto('/dev/medications');
  await page.getByRole('button', { name: '최근 3개월' }).click();
  await page.getByRole('radio', { name: '최근 6개월' }).click();
  await page.getByRole('button', { name: '적용' }).click();
  await expect(page).toHaveURL(/from=\d{4}-\d{2}-\d{2}&to=\d{4}-\d{2}-\d{2}/);
  await page.goBack();
  await expect(page).toHaveURL(/\/dev\/medications$/);
});
```

Add a custom reversed-date test that keeps the sheet open with an inline message, and an empty-result test that shows `기간 넓히기` without `약봉투 등록하기` inside the empty state. In the real API spec, assert query parameters match the URL exactly.

- [ ] **Step 2: Verify RED**

```bash
VITE_USE_MOCK=true ./node_modules/.bin/playwright test tests/e2e/medications-management.spec.ts --reporter=list
VITE_USE_MOCK=false ./node_modules/.bin/playwright test tests/e2e/medications-management-api.spec.ts --reporter=list
```

Expected: no filter control or URL synchronization exists.

- [ ] **Step 3: Implement pure period helpers**

Add `MedicationOverviewRange` to the entity types. Change `getMedicationOverviews` to append only defined query values and change `mockMedicationOverviews` to filter by `start.date` for the same values. Keep the default URL exactly `/v1/medications` and keep mock `isFinished` as a literal.

In `medicationPeriod.ts`, parse local dates without UTC, subtract calendar months with end-of-month clamping, and expose:

```ts
function localIsoDate(date: Date): string {
  return [
    date.getFullYear(),
    String(date.getMonth() + 1).padStart(2, '0'),
    String(date.getDate()).padStart(2, '0'),
  ].join('-');
}

function subtractCalendarMonths(today: Date, months: number): string {
  const target = new Date(today.getFullYear(), today.getMonth() - months, 1);
  const lastDay = new Date(target.getFullYear(), target.getMonth() + 1, 0).getDate();
  target.setDate(Math.min(today.getDate(), lastDay));
  return localIsoDate(target);
}

export function medicationRangeFromSearchParams(params: URLSearchParams): MedicationOverviewRange {
  return {
    ...(params.get('from') ? { from: params.get('from')! } : {}),
    ...(params.get('to') ? { to: params.get('to')! } : {}),
  };
}

export function presetRange(
  preset: Exclude<MedicationPeriodPreset, 'three-months' | 'custom'>,
  today: Date,
): Required<MedicationOverviewRange> {
  const months = preset === 'one-month' ? 1 : 6;
  return { from: subtractCalendarMonths(today, months), to: localIsoDate(today) };
}
```

Keep recent three months represented by `{}` so the server owns its default date.

- [ ] **Step 4: Build the filter sheet and URL data flow**

Use Radix `DialogContent variant="sheet"`, radio semantics, and native `type="date"` inputs. `MedicationsPage` reads `useSearchParams`, passes exact values to the loader, and updates search params only on Apply. The empty-state `기간 넓히기` opens the same sheet.

Do not store the filter in localStorage. Do not reset `expandedRecordIds` unless the loaded response no longer contains an expanded ID.

- [ ] **Step 5: Run filter tests and typecheck**

```bash
VITE_USE_MOCK=true ./node_modules/.bin/playwright test tests/e2e/medications-management.spec.ts --reporter=list
VITE_USE_MOCK=false ./node_modules/.bin/playwright test tests/e2e/medications-management-api.spec.ts --reporter=list
./node_modules/.bin/tsc --noEmit
```

Expected: both modes pass and default URL has no query.

- [ ] **Step 6: Commit URL filtering**

```bash
git add frontend/src/entities/medication/types.ts frontend/src/entities/medication/api.ts frontend/src/entities/medication/api.mock.ts frontend/src/entities/medication/index.ts frontend/src/pages/medications/MedicationPeriodFilterSheet.tsx frontend/src/pages/medications/medicationPeriod.ts frontend/src/pages/medications/MedicationsPage.tsx frontend/tests/e2e/medications-management.spec.ts frontend/tests/e2e/medications-management-api.spec.ts
git commit -m "[feature/225][신동훈]복약 목록 기간 필터 추가"
```

---

### Task 7: Sequential multi-delete with partial-failure recovery

**Files:**
- Create: `frontend/src/pages/medications/MedicationBulkDeleteDialog.tsx`
- Modify: `frontend/src/pages/medications/MedicationEpisodeCard.tsx`
- Modify: `frontend/src/pages/medications/MedicationsPage.tsx`
- Test: `frontend/tests/e2e/medications-management.spec.ts`
- Test: `frontend/tests/e2e/medications-management-api.spec.ts`
- Modify: `frontend/tests/e2e/medication-registration-flow.spec.ts`

**Interfaces:**
- Produces: selection mode with `selectedRecordIds: Set<number>`
- Produces: sequential `deleteSelectedMedications(recordIds)` behavior owned by the page
- Consumes: existing `cancelMedication(recordId)` one item at a time

- [ ] **Step 1: Write failing selection and deletion tests**

Add tests for:

- entering selection mode shows one checkbox per card and no whole-list checkbox;
- zero selected hides `삭제하기`;
- clicking a card in selection mode selects it without changing `aria-expanded`;
- selecting two cards changes the title to `2개 선택`;
- DELETE requests occur in selected card order, never concurrently;
- all success removes both cards and shows `2개를 삭제했어요`;
- one success and one failure removes only the success, keeps the failed checkbox selected, and shows `1개를 삭제했어요. 1개는 실패했어요`;
- all failure opens the error state, preserves both selections, and Retry attempts those same two IDs again.

For sequencing, hold the first route promise and assert the second DELETE has not arrived before the first is fulfilled.

- [ ] **Step 2: Verify RED**

```bash
VITE_USE_MOCK=true ./node_modules/.bin/playwright test tests/e2e/medications-management.spec.ts --reporter=list
VITE_USE_MOCK=false ./node_modules/.bin/playwright test tests/e2e/medications-management-api.spec.ts --reporter=list
```

Expected: selection controls and plural confirmation do not exist.

- [ ] **Step 3: Implement selection mode and header states**

Normal header actions contain `+` and `삭제`. Selection mode changes the title to `${selectedRecordIds.size}개 선택`, always shows `취소`, and conditionally renders `삭제하기` only when the set is non-empty. Entering selection mode keeps existing expansion state but disables expansion interactions; leaving selection mode clears selections.

- [ ] **Step 4: Implement sequential deletion result handling**

Use an ordered input array and explicit loop:

```ts
const succeeded: number[] = [];
const failed: number[] = [];
for (const recordId of recordIds) {
  try {
    await medicationCanceller(recordId);
    succeeded.push(recordId);
  } catch {
    failed.push(recordId);
  }
}
```

Remove only succeeded IDs from `overviews`, `expandedRecordIds`, and `selectedRecordIds`. On partial failure, replace selection with `new Set(failed)`. On total failure, keep the dialog error visible and make Retry call the same function with `failed`. Do not call `Promise.all`, `Promise.allSettled`, or a new backend endpoint.

- [ ] **Step 5: Run deletion tests and regressions**

```bash
VITE_USE_MOCK=true ./node_modules/.bin/playwright test tests/e2e/medications-management.spec.ts tests/e2e/remaining-pages.spec.ts tests/e2e/medication-registration-flow.spec.ts --reporter=list
VITE_USE_MOCK=false ./node_modules/.bin/playwright test tests/e2e/medications-management-api.spec.ts --reporter=list
./node_modules/.bin/tsc --noEmit
```

Expected: all #225 tests pass in both modes.

- [ ] **Step 6: Commit multi-delete**

```bash
git add frontend/src/pages/medications/MedicationBulkDeleteDialog.tsx frontend/src/pages/medications/MedicationEpisodeCard.tsx frontend/src/pages/medications/MedicationsPage.tsx frontend/tests/e2e/medications-management.spec.ts frontend/tests/e2e/medications-management-api.spec.ts frontend/tests/e2e/medication-registration-flow.spec.ts
git commit -m "[feature/225][신동훈]복약 기록 선택 삭제 추가"
```

---

### Task 8: Full verification and scope audit

**Files:**
- Modify only if a verification failure proves a #225 regression in an already-listed file.

**Interfaces:**
- Verifies all server, frontend, accessibility, mode-guard, and scope constraints.

- [ ] **Step 1: Run the full relevant backend suite**

```bash
uv run pytest app/tests/med_apis/test_medications_api.py app/tests/med_apis/test_medication_schedule_api.py app/tests/alarm_apis -q
uv run ruff check app app/tests
uv run ruff format . --check
```

Expected: all #225-related tests pass. If an unrelated baseline failure appears, reproduce it on `origin/main` before classifying it.

- [ ] **Step 2: Run frontend typecheck and production build after WSL dependencies are prepared**

From WSL in `frontend/`:

```bash
./node_modules/.bin/tsc --noEmit
./node_modules/.bin/tsc -b
./node_modules/.bin/vite build
```

Expected: all commands exit 0. Do not install or repair dependencies if a binary is absent.

- [ ] **Step 3: Run full E2E in both modes**

```bash
VITE_USE_MOCK=true ./node_modules/.bin/playwright test --reporter=list
VITE_USE_MOCK=false ./node_modules/.bin/playwright test --reporter=list
```

Record executed, skipped, and failed counts for both modes. The #225 tests must have zero failures. Reproduce the known #218 signup test on `origin/main` and report it separately if it remains the only failure.

- [ ] **Step 4: Run source and scope invariants**

```bash
git diff --name-only main...HEAD
git diff main...HEAD -- app/models app/core/db/migrations
rg -n "CareEpisodeStatus\.COMPLETED" app -g "*.py" -g "!tests/**"
rg -n "MedicationEpisodePage|/medications/:recordId" frontend/src frontend/tests/e2e
rg -n "#[0-9a-fA-F]{6}" frontend/src -g "*.tsx"
git diff --check
```

Expected:

- no output for models or migrations;
- no production use of `CareEpisodeStatus.COMPLETED`;
- no source or E2E reference to the deleted detail page/route;
- no hard-coded six-digit colors in TSX;
- no whitespace errors.

- [ ] **Step 5: Verify the 375px layout**

Use the Playwright viewport `{ width: 375, height: 812 }` and assert `document.documentElement.scrollWidth === 375` while:

- two cards are expanded;
- selection mode shows header actions;
- the custom date fields are visible;
- a partial-delete toast is visible.

- [ ] **Step 6: Commit only necessary final test adjustments**

If verification required an in-scope adjustment, inspect `git status --short`, stage only the changed paths from the following complete in-scope list, and commit:

```bash
git add app/core/exceptions.py app/dtos/medications.py app/apis/v1/medication_router.py app/services/medication_period.py app/services/medications.py app/services/medication_schedule.py app/tests/med_apis/test_medications_api.py app/tests/med_apis/test_medication_schedule_api.py frontend/src/app/router.tsx frontend/src/entities/medication/types.ts frontend/src/entities/medication/api.ts frontend/src/entities/medication/api.mock.ts frontend/src/entities/medication/index.ts frontend/src/shared/lib/dateLabel.ts frontend/src/pages/home/MedicationRecordGrid.tsx frontend/src/pages/home/MedicationTimeline.tsx frontend/src/pages/medications/MedicationEpisodeCard.tsx frontend/src/pages/medications/MedicationPeriodFilterSheet.tsx frontend/src/pages/medications/MedicationBulkDeleteDialog.tsx frontend/src/pages/medications/medicationPeriod.ts frontend/src/pages/medications/MedicationsPage.tsx frontend/src/pages/medications/index.ts frontend/tests/e2e/home-dose-record-grid.spec.ts frontend/tests/e2e/remaining-pages.spec.ts frontend/tests/e2e/medication-registration-flow.spec.ts frontend/tests/e2e/medications-management.spec.ts frontend/tests/e2e/medications-management-api.spec.ts
git commit -m "[feature/225][신동훈]복약 페이지 통합 검증 보완"
```

If no files changed, do not create an empty commit.

- [ ] **Step 7: Prepare branch completion**

Confirm `git status --short` is empty, list `git log --oneline main..HEAD`, then invoke `superpowers:verification-before-completion` and `superpowers:finishing-a-development-branch`. Push and create a PR only after the user selects that finish option.
