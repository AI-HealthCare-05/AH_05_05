# Common Code and Chat Feedback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add category-aware common-code management, replace chat star scores with like feedback, update dashboard satisfaction, and apply the schema to Docker MySQL.

**Architecture:** Keep common-code groups and detail codes normalized behind focused repository/service APIs. Chat feedback stores a nullable boolean and optional validated reason code, while the dashboard derives a like percentage from evaluated sessions. The existing A-split admin shell becomes an API-backed ADMIN-write/STAFF-read-only screen.

**Tech Stack:** Python 3.13, FastAPI, Pydantic 2, Tortoise ORM, Aerich, MySQL 8, vanilla JavaScript, HTML, Tailwind/shared CSS, pytest, Node test runner, Ruff

**Spec:** `docs/superpowers/specs/2026-09-03-common-code-and-chat-feedback-design.md`

## Global Constraints

- Project root: `/Users/admin/PycharmProjects/FinalProject`.
- Do not commit; preserve unrelated modified and untracked files.
- Category, group code, and detail code accept only `^[A-Z][A-Z0-9_]*$` after trim and uppercase normalization.
- ADMIN may read and write common codes; STAFF is read-only.
- Common-code records are deactivated, not deleted.
- Existing chat scores are discarded and become unrated feedback.
- Positive reasons use `CHAT/P_REASON`; negative reasons use `CHAT/N_REASON`.
- `reason_code` is optional; when present it must identify an active detail in an active matching group.
- New admin common-code JSON uses snake_case; existing chat JSON keeps camelCase.
- Apply the finished migration to Docker MySQL without resetting or deleting unrelated data.

---

## File Map

- Create `app/models/common_codes.py`: Tortoise models for groups and details.
- Modify `app/models/chat.py`: replace session `score` with `is_like` and `reason_code`.
- Modify `app/models/__init__.py`: register both common-code models.
- Create `app/core/db/migrations/models/23_20260903_add_common_codes_chat_feedback.py`: forward/backward schema migration.
- Create `app/dtos/common_codes.py`: snake_case admin requests, queries, and responses.
- Modify `app/dtos/chat.py`: camelCase feedback request/response.
- Modify `app/dtos/admin_dashboard.py`: replace `average_score` with `like_rate`.
- Create `app/repositories/common_code_repository.py`: all group/detail persistence and active lookup.
- Modify `app/repositories/chat_repository.py`: owned-session feedback update.
- Create `app/services/common_codes.py`: normalization, duplicate handling, permissions-independent business rules.
- Modify `app/services/chat.py`: feedback ownership and reason validation.
- Modify `app/services/admin_dashboard.py`: like-rate aggregation.
- Modify `app/core/exceptions.py`: common-code and feedback validation errors.
- Create `app/apis/v1/common_code_router.py`: public active-code lookup.
- Modify `app/apis/v1/admin_routers.py`: protected common-code CRUD endpoints.
- Modify `app/apis/v1/chat_router.py`: feedback endpoint.
- Modify `app/apis/v1/__init__.py`: register public router.
- Create `app/static/js/common-code-management.js`: A-split screen state, API calls, forms, and pagination.
- Modify `app/static/templates/common-code-management.html`: category-aware controls, overlays, and JS entry.
- Modify `app/static/js/dashboard.js`: percentage formatter/rendering.
- Modify `app/static/templates/dashboard.html`: like-rate copy and visualization markup.
- Modify `app/static/css/dashboard.css`: percent visualization styling.
- Add/update focused Python and Node tests listed below.

---

### Task 1: Persist the new schema in Tortoise and Aerich

**Files:**
- Create: `app/models/common_codes.py`
- Modify: `app/models/chat.py`
- Modify: `app/models/__init__.py`
- Create: `app/core/db/migrations/models/23_20260903_add_common_codes_chat_feedback.py`
- Test: `app/tests/models/test_common_code_models.py`
- Test: `app/tests/models/test_model_metadata.py`

**Interfaces:**
- Produces: `CommonCodeGroup`, `CommonCode`, `ChatSession.is_like`, and `ChatSession.reason_code`.
- Consumes: existing `Admin`, `ChatSession`, and Tortoise model registration through `app.models`.

- [ ] **Step 1: Write failing model metadata tests**

```python
def test_common_code_group_metadata() -> None:
    assert CommonCodeGroup._meta.db_table == "common_code_groups"
    assert CommonCodeGroup._meta.fields_map["category"].max_length == 50
    assert ("category", "is_active", "group_code") in CommonCodeGroup._meta.indexes


def test_chat_session_uses_like_feedback() -> None:
    assert "score" not in ChatSession._meta.fields_map
    assert ChatSession._meta.fields_map["is_like"].null is True
    assert ChatSession._meta.fields_map["reason_code"].max_length == 20
```

- [ ] **Step 2: Run tests and verify missing models/fields fail**

Run: `uv run pytest app/tests/models/test_common_code_models.py app/tests/models/test_model_metadata.py -q`

Expected: FAIL because common-code models and like-feedback fields do not exist.

- [ ] **Step 3: Implement the two Tortoise models and chat fields**

```python
class CommonCodeGroup(models.Model):
    id = fields.BigIntField(primary_key=True)
    category = fields.CharField(max_length=50, description="공통코드 대분류")
    group_code = fields.CharField(max_length=50, unique=True, description="코드그룹")
    group_name = fields.CharField(max_length=100, description="코드그룹명")
    description = fields.CharField(max_length=500, null=True)
    is_active = fields.BooleanField(default=True)
    created_by_admin = fields.ForeignKeyField("models.Admin", null=True, related_name="created_common_code_groups", on_delete=fields.SET_NULL)
    updated_by_admin = fields.ForeignKeyField("models.Admin", null=True, related_name="updated_common_code_groups", on_delete=fields.SET_NULL)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True, null=True)

    class Meta:
        table = "common_code_groups"
        indexes = (("category", "is_active", "group_code"),)


class CommonCode(models.Model):
    id = fields.BigIntField(primary_key=True)
    group = fields.ForeignKeyField("models.CommonCodeGroup", related_name="codes", on_delete=fields.CASCADE)
    detail_code = fields.CharField(max_length=50)
    detail_name = fields.CharField(max_length=100)
    description = fields.CharField(max_length=500, null=True)
    sort_order = fields.IntField(default=0)
    is_active = fields.BooleanField(default=True)
    created_by_admin = fields.ForeignKeyField("models.Admin", null=True, related_name="created_common_codes", on_delete=fields.SET_NULL)
    updated_by_admin = fields.ForeignKeyField("models.Admin", null=True, related_name="updated_common_codes", on_delete=fields.SET_NULL)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True, null=True)

    class Meta:
        table = "common_codes"
        unique_together = (("group", "detail_code"),)
        indexes = (("group", "is_active", "sort_order"),)
```

Replace the `score` field with nullable `is_like` and nullable length-20 `reason_code`, then export both models from `app/models/__init__.py`.

- [ ] **Step 4: Add the exact forward and backward migration**

Forward SQL must create parent before child, add nullable feedback columns, drop `chk_chat_session_score`, then drop `score`. Backward SQL must drop child before parent and recreate nullable `score` plus the 1–5 check.

```sql
ALTER TABLE `chat_sessions` ADD `is_like` BOOL NULL COMMENT '좋아요 여부';
ALTER TABLE `chat_sessions` ADD `reason_code` VARCHAR(20) NULL COMMENT '평가 사유 코드';
ALTER TABLE `chat_sessions` DROP CHECK `chk_chat_session_score`;
ALTER TABLE `chat_sessions` DROP COLUMN `score`;
```

- [ ] **Step 5: Run metadata and migration import checks**

Run: `uv run pytest app/tests/models/test_common_code_models.py app/tests/models/test_model_metadata.py -q`

Expected: PASS.

Run: `uv run python -m py_compile app/models/common_codes.py app/core/db/migrations/models/23_20260903_add_common_codes_chat_feedback.py`

Expected: exit 0.

---

### Task 2: Build common-code repository, DTOs, service, and errors

**Files:**
- Create: `app/dtos/common_codes.py`
- Create: `app/repositories/common_code_repository.py`
- Create: `app/services/common_codes.py`
- Modify: `app/core/exceptions.py`
- Test: `app/tests/common_codes/test_common_code_service.py`

**Interfaces:**
- Produces: `normalize_common_code(value: str) -> str`, `CommonCodeService.list_groups`, `create_group`, `get_group`, `update_group`, `list_codes`, `create_code`, `get_code`, `update_code`, and `list_active_codes`.
- Consumes: `CommonCodeGroup`, `CommonCode`, actor admin ID, and page/filter DTOs.

- [ ] **Step 1: Write failing normalization, duplicate, and active-lookup tests**

```python
def test_normalize_common_code_trims_and_uppercases() -> None:
    assert normalize_common_code(" chat_reason ") == "CHAT_REASON"


@pytest.mark.asyncio
async def test_active_lookup_excludes_inactive_group_and_code(initialized_db) -> None:
    group = await CommonCodeGroup.create(category="CHAT", group_code="P_REASON", group_name="긍정", is_active=True)
    visible = await CommonCode.create(group=group, detail_code="HELPFUL", detail_name="도움됨", is_active=True)
    await CommonCode.create(group=group, detail_code="OTHER", detail_name="기타", is_active=False)
    result = await CommonCodeService().list_active_codes("CHAT", "P_REASON")
    assert [item.id for item in result] == [visible.id]
```

Also cover invalid code syntax, global duplicate group code, duplicate detail within a group, group status preservation, and `sort_order,id` ordering.

- [ ] **Step 2: Run the service tests and verify failure**

Run: `uv run pytest app/tests/common_codes/test_common_code_service.py -q`

Expected: FAIL because the DTO, repository, and service modules do not exist.

- [ ] **Step 3: Implement snake_case DTOs**

Use `BaseSerializerModel`, not `CamelModel`, for admin common-code payloads. Define distinct create/update types so immutable codes cannot be patched. Use `PageResponse` only if its camelCase output is explicitly overridden; otherwise define `total_count`, `page`, `size`, and `items` on snake_case response classes.

```python
COMMON_CODE_PATTERN = r"^[A-Z][A-Z0-9_]*$"

class CommonCodeGroupCreateRequest(BaseSerializerModel):
    category: str = Field(min_length=1, max_length=50, pattern=COMMON_CODE_PATTERN)
    group_code: str = Field(min_length=1, max_length=50, pattern=COMMON_CODE_PATTERN)
    group_name: str = Field(min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=500)
    is_active: bool = True
```

- [ ] **Step 4: Implement focused persistence methods**

Repository methods must use Tortoise `filter`, `get_or_none`, `count`, and `select_related("group")`; do not expose query construction to routers. Convert `IntegrityError` to `CommonCodeAlreadyExistsError` in the service.

- [ ] **Step 5: Implement normalization and status-aware lookup**

```python
def normalize_common_code(value: str) -> str:
    normalized = value.strip().upper()
    if not re.fullmatch(r"[A-Z][A-Z0-9_]*", normalized):
        raise InvalidCommonCodeError()
    return normalized
```

Group updates change name, description, and active state but never group code. Detail updates change name, description, sort order, and active state but never detail code.

- [ ] **Step 6: Run focused tests**

Run: `uv run pytest app/tests/common_codes/test_common_code_service.py -q`

Expected: PASS.

---

### Task 3: Expose admin and service common-code APIs

**Files:**
- Create: `app/apis/v1/common_code_router.py`
- Modify: `app/apis/v1/admin_routers.py`
- Modify: `app/apis/v1/__init__.py`
- Test: `app/tests/admin_apis/test_admin_common_code_api.py`
- Test: `app/tests/common_code_apis/test_common_code_lookup_api.py`

**Interfaces:**
- Produces: the eight admin endpoints and `GET /api/v1/common-codes/{category}/{group_code}`.
- Consumes: `CommonCodeService`, `AdminOnly`, `AdminOrStaff`, and Task 2 DTOs.

- [ ] **Step 1: Write failing role and response-shape API tests**

```python
created = await request("POST", "/api/v1/admin/common-code-groups", headers=admin_headers, json={
    "category": "chat", "group_code": "p_reason", "group_name": "긍정 사유", "is_active": True,
})
assert created.status_code == 201
assert created.json()["category"] == "CHAT"
assert "group_code" in created.json()

denied = await request("POST", "/api/v1/admin/common-code-groups", headers=staff_headers, json={
    "category": "CHAT", "group_code": "N_REASON", "group_name": "부정 사유", "is_active": True,
})
assert denied.status_code == 403
```

Cover all GETs for STAFF, all writes for ADMIN, patch immutability, 409 duplicates, pagination, and active-only public lookup.

- [ ] **Step 2: Run tests and verify route failures**

Run: `uv run pytest app/tests/admin_apis/test_admin_common_code_api.py app/tests/common_code_apis/test_common_code_lookup_api.py -q`

Expected: FAIL with 404 or missing imports.

- [ ] **Step 3: Add admin routes with explicit dependencies**

Use `AdminOrStaff` for GET and `AdminOnly` for POST/PATCH. Pass `actor.admin_id` to write service methods. Document the Korean usage of each route in `summary` and docstrings.

- [ ] **Step 4: Add and register the public lookup router**

```python
common_code_router = APIRouter(prefix="/common-codes", tags=["common-codes"])

@common_code_router.get("/{category}/{group_code}", response_model=CommonCodeLookupResponse)
async def list_active_common_codes(category: str, group_code: str, service: Annotated[CommonCodeService, Depends(CommonCodeService)]):
    return CommonCodeLookupResponse(items=await service.list_active_codes(category, group_code))
```

- [ ] **Step 5: Run API and OpenAPI documentation tests**

Run: `uv run pytest app/tests/admin_apis/test_admin_common_code_api.py app/tests/common_code_apis/test_common_code_lookup_api.py -q`

Expected: PASS.

Run: `uv run pytest app/tests -q -k 'openapi or documentation'`

Expected: PASS after updating any exact operation-count assertion to include the new documented endpoints.

---

### Task 4: Add owned chat feedback with common-code validation

**Files:**
- Modify: `app/dtos/chat.py`
- Modify: `app/repositories/chat_repository.py`
- Modify: `app/services/chat.py`
- Modify: `app/apis/v1/chat_router.py`
- Modify: `app/core/exceptions.py`
- Test: `app/tests/chat_apis/test_chat_feedback_api.py`

**Interfaces:**
- Produces: `ChatFeedbackRequest`, `ChatFeedbackResponse`, `ChatSessionService.update_feedback(user, session_id, is_like, reason_code)`.
- Consumes: `CommonCodeService.is_active_code(category, group_code, detail_code) -> bool` from Task 2.

- [ ] **Step 1: Write failing feedback tests**

```python
response = await request(
    "PUT",
    f"/api/v1/chat/sessions/{session.id}/feedback",
    headers=user_headers,
    json={"isLike": False, "reasonCode": "NOT_HELPFUL"},
)
assert response.status_code == 200
assert response.json()["data"] == {
    "sessionId": session.id,
    "isLike": False,
    "reasonCode": "NOT_HELPFUL",
}
```

Cover positive `P_REASON`, negative `N_REASON`, optional reason, wrong group 422, inactive group/code 422, clear with both null, reason-with-null 422, overwrite, other-user 403, and missing session 404.

- [ ] **Step 2: Run tests and verify endpoint absence**

Run: `uv run pytest app/tests/chat_apis/test_chat_feedback_api.py -q`

Expected: FAIL with 404.

- [ ] **Step 3: Add camelCase request and response DTOs**

```python
class ChatFeedbackRequest(CamelModel):
    is_like: bool | None
    reason_code: str | None = Field(default=None, max_length=20)

class ChatFeedbackDataResponse(CamelModel):
    session_id: int
    is_like: bool | None
    reason_code: str | None
```

- [ ] **Step 4: Implement service validation and atomic owned update**

Normalize a non-empty reason to uppercase. Select `P_REASON` for true and `N_REASON` for false. Reject a reason when `is_like` is null. Validate the active code, then update only an owned non-deleted session. Distinguish missing session from another user's session using the repository's existing access pattern.

- [ ] **Step 5: Add the PUT route and Korean OpenAPI documentation**

The route must use `get_request_user` and the lightweight `ChatSessionService`; it must not initialize Qdrant or the AI chat service.

- [ ] **Step 6: Run feedback tests**

Run: `uv run pytest app/tests/chat_apis/test_chat_feedback_api.py -q`

Expected: PASS.

---

### Task 5: Replace dashboard star-score aggregation and UI

**Files:**
- Modify: `app/dtos/admin_dashboard.py`
- Modify: `app/services/admin_dashboard.py`
- Modify: `app/static/js/dashboard.js`
- Modify: `app/static/templates/dashboard.html`
- Modify: `app/static/css/dashboard.css`
- Modify: `app/tests/admin_apis/test_admin_dashboard_api.py`
- Modify: `app/tests/static_ui/dashboard.test.mjs`

**Interfaces:**
- Produces: `chatResponses.likeRate: float | null` and `formatChatSatisfaction(value) -> {text, ariaLabel, percent}`.
- Consumes: `ChatSession.is_like` and the existing dashboard period boundaries.

- [ ] **Step 1: Replace backend assertions with like-rate cases**

```python
await self.create_session(is_like=True, created_at=at(0))
await self.create_session(is_like=True, created_at=at(1))
await self.create_session(is_like=False, created_at=at(2))
await self.create_session(is_like=None, created_at=at(0))
assert response.json()["chatResponses"]["likeRate"] == 66.7
```

Add a no-evaluations case asserting null and retain period-boundary coverage.

- [ ] **Step 2: Run dashboard API tests and verify score references fail**

Run: `uv run pytest app/tests/admin_apis/test_admin_dashboard_api.py -q`

Expected: FAIL until the DTO and service use `like_rate`.

- [ ] **Step 3: Implement boolean aggregation**

Filter sessions by selected-period `created_at` and `is_like__not_isnull=True`. Count evaluated and liked rows, return `round(liked / evaluated * 100, 1)`, or null when evaluated is zero. Remove `AVG(score)` and its `RawSQL` use if no other method needs it.

- [ ] **Step 4: Update static UI tests for percentage semantics**

Assert `formatChatSatisfaction(66.7)` renders `66.7%`, null renders `데이터 없음`, the explanation says `챗봇 사용자의 긍정 평가 비율을 나타냅니다.`, and star-specific markup/classes are absent.

- [ ] **Step 5: Implement the percentage visualization**

Bind the progress visualization to a clamped 0–100 value and set an accessible label such as `챗봇 긍정 평가 비율 66.7%`. Remove star fill calculations and stale score copy.

- [ ] **Step 6: Run backend and Node dashboard tests**

Run: `uv run pytest app/tests/admin_apis/test_admin_dashboard_api.py -q`

Expected: PASS.

Run: `node --test app/tests/static_ui/dashboard.test.mjs`

Expected: PASS.

---

### Task 6: Connect the A-split common-code admin screen

**Files:**
- Create: `app/static/js/common-code-management.js`
- Modify: `app/static/templates/common-code-management.html`
- Modify: `app/static/css/management.css`
- Modify: `app/static/js/sidebar.js`
- Test: `app/tests/static_ui/common-code-management.test.mjs`
- Test: `app/tests/static_ui/sidebar.test.mjs`

**Interfaces:**
- Produces: browser-backed group/detail listing, filtering, pagination, registration, editing, status toggles, and role-based controls.
- Consumes: Task 3 admin APIs and `session.isAdminRole()`, `get`, `post`, `patch`, `ApiError` from `app/static/js/api.js`.

- [ ] **Step 1: Write failing pure-function and markup tests**

```javascript
assert.deepEqual(buildGroupQuery({ category: " chat ", groupCode: " p_reason ", page: 2, size: 20 }), {
  category: "CHAT", group_code: "P_REASON", page: 2, size: 20,
});
assert.equal(normalizeCodeInput(" p_reason "), "P_REASON");
assert.equal(isValidCodeInput("NOT-HELPFUL"), false);
assert.equal(canEditCommonCodes({ role: "ADMIN" }), true);
assert.equal(canEditCommonCodes({ role: "STAFF" }), false);
```

Markup assertions must cover category filter/column/form field, left and right pagination roots, empty/error states, and module import.

- [ ] **Step 2: Run Node tests and verify missing module failure**

Run: `node --test app/tests/static_ui/common-code-management.test.mjs app/tests/static_ui/sidebar.test.mjs`

Expected: FAIL because the screen module does not exist.

- [ ] **Step 3: Implement testable state helpers**

Export normalization, query-building, pagination calculation, permission, and table-rendering helpers. Keep DOM initialization guarded by `typeof document !== "undefined"` so Node can import the module.

- [ ] **Step 4: Implement API-backed group selection and independent pagination**

On entry require login, load group page, select the first available group, then load that group's detail page. A group filter submission resets both pages to 1. Selecting another group resets only the detail page to 1.

- [ ] **Step 5: Add group/detail overlays and submit locking**

Group create includes category, group code, name, description, and active state. Group edit excludes group code. Detail create includes detail code, name, description, sort order, and active state. Detail edit excludes detail code. Disable the save button while each request is pending and refresh the affected list after success.

- [ ] **Step 6: Enforce STAFF read-only behavior in the UI**

Hide all create/edit/status controls when `session.isAdminRole()` is false. Keep row selection and both lists available.

- [ ] **Step 7: Run focused static tests and syntax checks**

Run: `node --test app/tests/static_ui/common-code-management.test.mjs app/tests/static_ui/sidebar.test.mjs`

Expected: PASS.

Run: `node --check app/static/js/common-code-management.js`

Expected: exit 0.

---

### Task 7: Apply migration to Docker MySQL and perform integrated verification

**Files:**
- Modify only if generated-state corrections are required: `app/core/db/migrations/models/23_20260903_add_common_codes_chat_feedback.py`
- Verify: all files changed by Tasks 1–6

**Interfaces:**
- Consumes: completed code and migration.
- Produces: upgraded Docker MySQL schema and verification evidence.

- [ ] **Step 1: Format and lint changed Python files**

Run: `uv run ruff format app/models/common_codes.py app/models/chat.py app/dtos/common_codes.py app/dtos/chat.py app/repositories/common_code_repository.py app/repositories/chat_repository.py app/services/common_codes.py app/services/chat.py app/services/admin_dashboard.py app/apis/v1/common_code_router.py app/apis/v1/admin_routers.py app/apis/v1/chat_router.py app/core/exceptions.py app/core/db/migrations/models/23_20260903_add_common_codes_chat_feedback.py`

Expected: exit 0.

Run the same paths with `uv run ruff check`; expected exit 0.

- [ ] **Step 2: Run focused backend and UI suites**

Run: `uv run pytest app/tests/models/test_common_code_models.py app/tests/common_codes app/tests/common_code_apis app/tests/admin_apis/test_admin_common_code_api.py app/tests/chat_apis/test_chat_feedback_api.py app/tests/admin_apis/test_admin_dashboard_api.py -q`

Expected: PASS.

Run: `node --test app/tests/static_ui/common-code-management.test.mjs app/tests/static_ui/dashboard.test.mjs app/tests/static_ui/sidebar.test.mjs`

Expected: PASS.

- [ ] **Step 3: Confirm Docker services and migration state**

Run: `docker compose ps`

Expected: MySQL service is running and healthy.

Run: `uv run aerich heads`

Expected: the new migration is the single unapplied head before upgrade.

- [ ] **Step 4: Apply the migration**

Run: `uv run aerich upgrade`

Expected: `23_20260903_add_common_codes_chat_feedback.py` is applied successfully without resetting the database.

- [ ] **Step 5: Verify actual MySQL structures**

Run through `docker compose exec -T mysql` using the container's configured credentials:

```sql
SHOW CREATE TABLE common_code_groups;
SHOW CREATE TABLE common_codes;
SHOW COLUMNS FROM chat_sessions WHERE Field IN ('score', 'is_like', 'reason_code');
SELECT version, app FROM aerich ORDER BY id DESC LIMIT 1;
```

Expected: both tables, required indexes/FKs, no `score`, nullable `is_like`, length-20 nullable `reason_code`, and the new Aerich version.

- [ ] **Step 6: Run broader regression and check the diff**

Run: `uv run pytest app/tests -q`

Expected: PASS or only clearly identified pre-existing unrelated failures.

Run: `node --test app/tests/static_ui/*.test.mjs`

Expected: PASS or only the already-known unrelated assertions; document every non-passing test.

Run: `git diff --check && git status --short`

Expected: no whitespace errors; only intended files plus preserved pre-existing changes are present.

No commit is created.
