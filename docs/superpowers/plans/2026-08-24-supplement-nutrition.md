# Supplement Nutrition Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 건강기능식품 표준데이터 5,556건을 검색하고 로그인 사용자가 자신의 복용량·기간·시간대를 등록·관리하는 API를 구축한다.

**Architecture:** 국가 표준 제품은 `SupplementNutrient`, 사용자 복용정보는 `UserSupplementNutrient`, 복용 시간대는 `UserSupplementNutrientSlot`로 정규화한다. `/api/v1/med/nutr`는 제품 검색, `/api/v1/med/user-suppl-nutr`는 사용자 소유 복용정보를 담당하며 Router → Service → Repository → Tortoise Model 경계를 따른다.

**Tech Stack:** Python 3.13, FastAPI, Pydantic v2, Tortoise ORM, Aerich, MySQL 8, pytest, HTTPX, numbers-parser, uv, Ruff

**Spec:** `docs/superpowers/specs/2026-08-24-supplement-nutrition-design.md`

## Global Constraints

- 프로젝트 루트는 `/Users/admin/PycharmProjects/FinalProject`다.
- Git 커밋을 생성하지 않는다.
- 모든 신규 dbdiagram 테이블·컬럼에 용도 note를 작성한다.
- 제품 검색 경로는 `/api/v1/med/nutr`다.
- 사용자 복용정보 경로는 `/api/v1/med/user-suppl-nutr`다.
- 사용자 데이터 endpoint는 `get_request_user` 인증과 소유권 검사를 적용한다.
- 제품명 검색은 `name__icontains`를 사용해 SQL 의미상 `LIKE '%검색어%'`로 동작한다.
- 원본의 빈 영양성분 값은 0이 아니라 `NULL`로 보존한다.
- 알람 생성과 Web Push 연동은 이번 범위에서 제외한다.

---

## File Map

**Create**

- `app/models/supplement_nutrients.py`: 세 Tortoise 모델과 관계·인덱스
- `app/dtos/supplement_nutrients.py`: 제품 검색 요청·응답 DTO
- `app/dtos/user_supplement_nutrients.py`: 사용자 등록·수정·목록 DTO와 검증
- `app/repositories/supplement_nutrient_repository.py`: 제품 검색·상세 쿼리
- `app/repositories/user_supplement_nutrient_repository.py`: 사용자 소유 복용정보 쿼리
- `app/services/supplement_nutrients.py`: 제품 검색 업무 규칙
- `app/services/user_supplement_nutrients.py`: 등록 upsert, slots 교체, 수정, 종료
- `app/apis/v1/med_router.py`: `/med/nutr`, `/med/user-suppl-nutr` endpoint
- `scripts/import_supplement_nutrients.py`: Numbers 파싱·검증·bulk upsert
- `tests/models/test_supplement_nutrition_model.py`: 모델 메타데이터 계약
- `app/tests/med_apis/__init__.py`: 테스트 패키지
- `app/tests/med_apis/helpers.py`: 인증·제품 fixture helper
- `app/tests/med_apis/test_med_nutr_api.py`: 제품 검색·상세·인증 테스트
- `app/tests/med_apis/test_user_suppl_nutr_api.py`: 사용자 복용정보 업무 API 테스트
- `tests/scripts/test_import_supplement_nutrients.py`: 원본 변환·upsert 테스트

**Modify**

- `app/models/enums.py`: `SupplementStatus`
- `app/models/__init__.py`: 신규 모델 export
- `app/core/db/databases.py`: 신규 모델 모듈 등록
- `app/apis/v1/__init__.py`: `med_router` 등록
- `pyproject.toml`, `uv.lock`: `numbers-parser` app 의존성
- `tests/models/test_model_metadata.py`: 공통 모델 로더에 신규 모듈 반영이 필요한 경우만 수정
- `app/core/db/migrations/models/5_*_add_supplement_nutrition.py`: Aerich가 생성하는 다음 revision 마이그레이션 검토
- dbdiagram FinalProject 문서: 두 사용자 연결 테이블·enum·FK·note 추가

---

### Task 1: Tortoise 모델과 enum 계약

**Files:**

- Create: `app/models/supplement_nutrients.py`
- Create: `tests/models/test_supplement_nutrition_model.py`
- Modify: `app/models/enums.py`
- Modify: `app/models/__init__.py`
- Modify: `app/core/db/databases.py`

**Interfaces:**

- Produces: `SupplementStatus`, `SupplementNutrient`, `UserSupplementNutrient`, `UserSupplementNutrientSlot`
- Produces relations: `User.supplement_nutrients`, `SupplementNutrient.user_registrations`, `UserSupplementNutrient.slots`
- Consumed by: Tasks 2–7

- [ ] **Step 1: Write failing model metadata tests**

Create tests that import the module and assert exact schema contracts:

```python
from decimal import Decimal

from tortoise import Tortoise, fields

from app.models.enums import MealSlot, SupplementStatus


def load_models():
    Tortoise.init_models(
        (
            "app.models.users",
            "app.models.supplement_nutrients",
        ),
        "models",
    )
    from app.models.supplement_nutrients import (
        SupplementNutrient,
        UserSupplementNutrient,
        UserSupplementNutrientSlot,
    )

    return SupplementNutrient, UserSupplementNutrient, UserSupplementNutrientSlot


def test_supplement_nutrient_matches_source_schema():
    supplement, _, _ = load_models()
    assert supplement._meta.db_table == "supplement_nutrients"
    assert supplement._meta.fields_map["food_code"].max_length == 20
    assert supplement._meta.fields_map["food_code"].unique is True
    assert supplement._meta.fields_map["name"].max_length == 100
    assert supplement._meta.fields_map["protein_g"].max_digits == 5
    assert supplement._meta.fields_map["protein_g"].decimal_places == 2
    assert supplement._meta.fields_map["water_g"].null is True
    assert supplement._meta.fields_map["energy_kcal"].null is False


def test_user_supplement_relationships_and_constraints():
    _, registration, slot = load_models()
    assert registration._meta.db_table == "user_suppl_nutrient"
    assert registration._meta.unique_together == (("user", "supplement_nutrient"),)
    assert registration._meta.fields_map["user"].on_delete == fields.CASCADE
    assert registration._meta.fields_map["supplement_nutrient"].on_delete == fields.RESTRICT
    assert registration._meta.fields_map["status"].default is SupplementStatus.ACTIVE
    assert registration._meta.fields_map["dose_amount"].validators[0].min_value == Decimal("0.001")
    assert slot._meta.db_table == "user_suppl_nutrient_slots"
    assert slot._meta.unique_together == (("user_suppl_nutrient", "slot"),)
    assert slot._meta.fields_map["slot"].enum_type is MealSlot
    assert slot._meta.fields_map["user_suppl_nutrient"].on_delete == fields.CASCADE
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
uv run pytest tests/models/test_supplement_nutrition_model.py -q
```

Expected: FAIL because `SupplementStatus` and `app.models.supplement_nutrients` do not exist.

- [ ] **Step 3: Add `SupplementStatus`**

Append to `app/models/enums.py`:

```python
class SupplementStatus(StrEnum):
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
```

- [ ] **Step 4: Implement the three models**

Create `app/models/supplement_nutrients.py` with the exact fields below:

```python
from decimal import Decimal

from tortoise import fields, models
from tortoise.validators import MinValueValidator

from app.models.enums import MealSlot, SupplementStatus


class SupplementNutrient(models.Model):
    id = fields.BigIntField(primary_key=True)
    food_code = fields.CharField(max_length=20, unique=True)
    name = fields.CharField(max_length=100)
    basis_qty = fields.CharField(max_length=10)
    energy_kcal = fields.IntField()
    water_g = fields.DecimalField(max_digits=10, decimal_places=3, null=True)
    protein_g = fields.DecimalField(max_digits=5, decimal_places=2)
    fat_g = fields.DecimalField(max_digits=5, decimal_places=2, null=True)
    ash_g = fields.DecimalField(max_digits=10, decimal_places=3, null=True)
    carb_g = fields.DecimalField(max_digits=6, decimal_places=2)
    sugar_g = fields.DecimalField(max_digits=5, decimal_places=2, null=True)
    fiber_g = fields.DecimalField(max_digits=7, decimal_places=1, null=True)
    calcium_mg = fields.IntField(null=True)
    iron_mg = fields.DecimalField(max_digits=5, decimal_places=2, null=True)
    phosphorus_mg = fields.IntField(null=True)
    potassium_mg = fields.IntField(null=True)
    sodium_mg = fields.IntField(null=True)
    vitamin_a_ug_rae = fields.IntField(null=True)
    retinol_ug = fields.IntField(null=True)
    beta_carotene_ug = fields.IntField(null=True)
    thiamine_mg = fields.DecimalField(max_digits=6, decimal_places=3, null=True)
    riboflavin_mg = fields.DecimalField(max_digits=6, decimal_places=3, null=True)
    niacin_mg = fields.DecimalField(max_digits=6, decimal_places=3, null=True)
    vitamin_c_mg = fields.DecimalField(max_digits=7, decimal_places=2, null=True)
    vitamin_d_ug = fields.DecimalField(max_digits=7, decimal_places=2, null=True)
    cholesterol_mg = fields.DecimalField(max_digits=6, decimal_places=2, null=True)
    sat_fat_g = fields.DecimalField(max_digits=4, decimal_places=2, null=True)
    trans_fat_g = fields.DecimalField(max_digits=4, decimal_places=2, null=True)
    serving_desc = fields.CharField(max_length=10)
    serving_size = fields.CharField(max_length=10)
    daily_freq = fields.CharField(max_length=5)
    target = fields.CharField(max_length=10, null=True)

    class Meta:
        table = "supplement_nutrients"


class UserSupplementNutrient(models.Model):
    id = fields.BigIntField(primary_key=True)
    user = fields.ForeignKeyField(
        "models.User", related_name="supplement_nutrients", on_delete=fields.CASCADE
    )
    supplement_nutrient = fields.ForeignKeyField(
        "models.SupplementNutrient",
        related_name="user_registrations",
        on_delete=fields.RESTRICT,
    )
    dose_amount = fields.DecimalField(
        max_digits=8,
        decimal_places=3,
        validators=[MinValueValidator(Decimal("0.001"))],
    )
    dose_unit = fields.CharField(max_length=20)
    start_date = fields.DateField()
    end_date = fields.DateField(null=True)
    status = fields.CharEnumField(SupplementStatus, default=SupplementStatus.ACTIVE)
    note = fields.CharField(max_length=500, null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True, null=True)

    class Meta:
        table = "user_suppl_nutrient"
        unique_together = (("user", "supplement_nutrient"),)
        indexes = (("user", "status"),)


class UserSupplementNutrientSlot(models.Model):
    id = fields.BigIntField(primary_key=True)
    user_suppl_nutrient = fields.ForeignKeyField(
        "models.UserSupplementNutrient",
        related_name="slots",
        on_delete=fields.CASCADE,
    )
    slot = fields.CharEnumField(MealSlot)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "user_suppl_nutrient_slots"
        unique_together = (("user_suppl_nutrient", "slot"),)
```

- [ ] **Step 5: Register the model module**

Add the classes to `app/models/__init__.py` and add `"app.models.supplement_nutrients"` to `TORTOISE_APP_MODELS` in `app/core/db/databases.py` after medications.

- [ ] **Step 6: Run model tests and metadata regression**

Run:

```bash
uv run pytest tests/models/test_supplement_nutrition_model.py tests/models/test_model_metadata.py -q
```

Expected: PASS.

---

### Task 2: DTO validation and response contracts

**Files:**

- Create: `app/dtos/supplement_nutrients.py`
- Create: `app/dtos/user_supplement_nutrients.py`
- Create: `app/tests/med_apis/__init__.py`
- Create: `app/tests/med_apis/test_dtos.py`

**Interfaces:**

- Consumes: `SupplementStatus`, `MealSlot`
- Produces: `SupplementNutrientResponse`, `SupplementNutrientListResponse`
- Produces: `UserSupplementNutrientUpsertRequest`, `UserSupplementNutrientUpdateRequest`
- Produces: `UserSupplementNutrientResponse`, `UserSupplementNutrientListResponse`, `SupplementSlotResponse`
- Consumed by: Tasks 3–5

- [ ] **Step 1: Write failing Pydantic validation tests**

Cover these exact behaviors:

```python
from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.dtos.user_supplement_nutrients import UserSupplementNutrientUpsertRequest


def valid_payload():
    return {
        "dose_amount": "1.000",
        "dose_unit": " 정 ",
        "start_date": "2026-08-24",
        "end_date": None,
        "slots": ["MORNING", "EVENING"],
        "note": "식후 복용",
    }


def test_upsert_normalizes_unit_and_rejects_duplicate_slots():
    request = UserSupplementNutrientUpsertRequest.model_validate(valid_payload())
    assert request.dose_amount == Decimal("1.000")
    assert request.dose_unit == "정"

    payload = valid_payload()
    payload["slots"] = ["MORNING", "MORNING"]
    with pytest.raises(ValidationError):
        UserSupplementNutrientUpsertRequest.model_validate(payload)


def test_upsert_rejects_empty_slots_and_invalid_date_range():
    payload = valid_payload()
    payload["slots"] = []
    with pytest.raises(ValidationError):
        UserSupplementNutrientUpsertRequest.model_validate(payload)

    payload = valid_payload()
    payload["end_date"] = date(2026, 8, 23)
    with pytest.raises(ValidationError):
        UserSupplementNutrientUpsertRequest.model_validate(payload)
```

- [ ] **Step 2: Run tests and verify RED**

Run `uv run pytest app/tests/med_apis/test_dtos.py -q`.

Expected: FAIL because the DTO modules do not exist.

- [ ] **Step 3: Implement catalog DTOs**

Define all 32 model fields in `SupplementNutrientResponse(BaseSerializerModel)`. Define list response with `items`, `total`, `offset`, `limit`. Do not collapse the nutrient fields into a JSON blob.

- [ ] **Step 4: Implement user DTOs and validators**

Use these exact public shapes:

```python
class UserSupplementNutrientUpsertRequest(BaseModel):
    dose_amount: Decimal = Field(gt=0, max_digits=8, decimal_places=3)
    dose_unit: str = Field(min_length=1, max_length=20)
    start_date: date
    end_date: date | None = None
    slots: list[MealSlot] = Field(min_length=1, max_length=4)
    note: str | None = Field(default=None, max_length=500)


class UserSupplementNutrientUpdateRequest(BaseModel):
    dose_amount: Decimal | None = Field(default=None, gt=0, max_digits=8, decimal_places=3)
    dose_unit: str | None = Field(default=None, min_length=1, max_length=20)
    start_date: date | None = None
    end_date: date | None = None
    status: SupplementStatus | None = None
    slots: list[MealSlot] | None = Field(default=None, min_length=1, max_length=4)
    note: str | None = Field(default=None, max_length=500)
```

Add field validators that strip `dose_unit`/`note`, reject blank `dose_unit`, reject duplicate slots, and model validators that enforce `end_date >= start_date` when both dates are present. Service-level validation must re-check the merged PATCH state.

Define `SupplementSlotResponse(slot: MealSlot, time: time)`, nested `supplement: SupplementNutrientResponse`, and response/list classes containing registration fields and slots.

- [ ] **Step 5: Run DTO tests**

Run `uv run pytest app/tests/med_apis/test_dtos.py -q`.

Expected: PASS.

---

### Task 3: Product catalog Repository, Service, and API

**Files:**

- Create: `app/repositories/supplement_nutrient_repository.py`
- Create: `app/services/supplement_nutrients.py`
- Create: `app/apis/v1/med_router.py`
- Create: `app/tests/med_apis/helpers.py`
- Create: `app/tests/med_apis/test_med_nutr_api.py`
- Modify: `app/apis/v1/__init__.py`

**Interfaces:**

- Produces: `SupplementNutrientRepository.search(name, offset, limit)`
- Produces: `SupplementNutrientService.search(name, offset, limit)` and `.get(id)`
- Produces authenticated routes `/api/v1/med/nutr` and `/api/v1/med/nutr/{id}`
- Consumed by: Task 5 OpenAPI verification

- [ ] **Step 1: Write failing product API tests**

Create three products containing Korean and mixed-case English names. Assert:

```python
listed = await client.get(
    "/api/v1/med/nutr",
    params={"name": "철분", "offset": 0, "limit": 1},
    headers=headers,
)
assert listed.status_code == 200
assert listed.json()["total"] == 2
assert len(listed.json()["items"]) == 1

english = await client.get(
    "/api/v1/med/nutr",
    params={"name": "vitamin"},
    headers=headers,
)
assert english.json()["items"][0]["name"] == "VITAMIN D 1000"

anonymous = await client.get("/api/v1/med/nutr", params={"name": "철분"})
assert anonymous.status_code == 401
```

Also assert detail returns all nutrient fields and an unknown ID returns 404.

- [ ] **Step 2: Run tests and verify RED**

Run `uv run pytest app/tests/med_apis/test_med_nutr_api.py -q`.

Expected: FAIL with 404 because `med_router` is not registered.

- [ ] **Step 3: Implement Repository and Service**

Repository:

```python
class SupplementNutrientRepository:
    async def search(self, name: str, *, offset: int, limit: int) -> tuple[list[SupplementNutrient], int]:
        query = SupplementNutrient.filter(name__icontains=name)
        total = await query.count()
        items = await query.order_by("name", "id").offset(offset).limit(limit)
        return items, total

    async def get(self, supplement_nutrient_id: int) -> SupplementNutrient | None:
        return await SupplementNutrient.get_or_none(id=supplement_nutrient_id)
```

Service strips the search string, rejects blank input with HTTP 422, delegates search, and raises `HTTPException(404, "Supplement nutrient not found.")` for missing detail.

- [ ] **Step 4: Implement authenticated Router**

Create `med_router = APIRouter(prefix="/med", tags=["med-nutrition"])`. Add:

```python
@med_router.get("/nutr", response_model=SupplementNutrientListResponse)
async def search_supplement_nutrients(
    _user: Annotated[User, Depends(get_request_user)],
    service: Annotated[SupplementNutrientService, Depends(get_supplement_nutrient_service)],
    name: Annotated[str, Query(min_length=1, max_length=100)],
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> SupplementNutrientListResponse:
    """제품명 앞뒤 부분 검색으로 건강기능식품 기준정보를 조회한다."""
```

Add detail route after the fixed `/nutr` route and include `med_router` in `app/apis/v1/__init__.py`.

- [ ] **Step 5: Run product API tests**

Run `uv run pytest app/tests/med_apis/test_med_nutr_api.py -q`.

Expected: PASS.

---

### Task 4: User registration Repository and Service transaction

**Files:**

- Create: `app/repositories/user_supplement_nutrient_repository.py`
- Create: `app/services/user_supplement_nutrients.py`
- Create: `app/tests/med_apis/test_user_suppl_nutr_service.py`

**Interfaces:**

- Produces: `UserSupplementNutrientRepository` ownership and locking queries
- Produces: `UserSupplementNutrientService.upsert`, `.list`, `.get`, `.update`, `.complete`
- Consumed by: Task 5 Router

- [ ] **Step 1: Write failing Service tests**

Test with real Tortoise models:

- first upsert creates one registration and two slots
- second upsert for the same user/product keeps registration count at one, sets status ACTIVE, and replaces slots
- `UserSettings` is created with 08:00/13:00/19:00/22:00 defaults
- a different user cannot read/update/complete the registration
- invalid merged PATCH date range raises 422 without modifying data
- complete sets status COMPLETED and Seoul current date; repeating complete is unchanged

Use a fake or injected Repository only for an explicit rollback test if a real DB constraint cannot deterministically trigger the failure.

- [ ] **Step 2: Run tests and verify RED**

Run `uv run pytest app/tests/med_apis/test_user_suppl_nutr_service.py -q`.

Expected: FAIL because the Repository and Service modules do not exist.

- [ ] **Step 3: Implement ownership queries**

Repository methods:

```python
async def get_product(self, product_id: int) -> SupplementNutrient | None
async def get_owned(self, registration_id: int, user_id: int) -> UserSupplementNutrient | None
async def get_by_user_product_for_update(
    self, user_id: int, product_id: int, connection: BaseDBAsyncClient
) -> UserSupplementNutrient | None
async def list_owned(
    self, user_id: int, status: SupplementStatus | None, offset: int, limit: int
) -> tuple[list[UserSupplementNutrient], int]
async def replace_slots(
    self, registration_id: int, slots: list[MealSlot], connection: BaseDBAsyncClient
) -> None
```

All detail/list queries prefetch `supplement_nutrient` and `slots`. `get_owned` always filters both registration ID and user ID.

- [ ] **Step 4: Implement Service transactions**

`upsert` algorithm:

```text
validate product exists
open in_transaction()
get_or_create UserSettings for user using the transaction
select existing (user, product) FOR UPDATE
if missing: create ACTIVE registration
if present: overwrite dose/date/note and set ACTIVE
delete existing slots and bulk-create requested unique slots
commit
reload registration with supplement and slots
```

Catch concurrent unique `IntegrityError`, reopen a transaction, lock the winning row, and apply the same update. Never create a duplicate row and do not convert the idempotent race to 409.

`update` merges the stored state with fields from `model_dump(exclude_unset=True)`, validates the merged date range, optionally replaces slots, and applies `end_date = datetime.now(config.TIMEZONE).date()` when status changes to COMPLETED without an explicit end date.

`complete` is idempotent and uses `datetime.now(config.TIMEZONE).date()`.

- [ ] **Step 5: Map MealSlot to UserSettings time**

Use one constant mapping:

```python
SLOT_TIME_FIELDS = {
    MealSlot.MORNING: "morning_medication_time",
    MealSlot.LUNCH: "lunch_medication_time",
    MealSlot.EVENING: "evening_medication_time",
    MealSlot.BEDTIME: "bedtime_medication_time",
}
```

Sort slots in enum/business order rather than database insertion order.

- [ ] **Step 6: Run Service tests**

Run `uv run pytest app/tests/med_apis/test_user_suppl_nutr_service.py -q`.

Expected: PASS.

---

### Task 5: User registration API and OpenAPI documentation

**Files:**

- Modify: `app/apis/v1/med_router.py`
- Create: `app/tests/med_apis/test_user_suppl_nutr_api.py`
- Create: `app/tests/med_apis/test_med_openapi_docs.py`

**Interfaces:**

- Consumes: `UserSupplementNutrientService` and DTOs
- Produces: five authenticated `/api/v1/med/user-suppl-nutr` operations

- [ ] **Step 1: Write failing end-to-end API tests**

Assert the exact routes and behaviors:

```text
PUT    /api/v1/med/user-suppl-nutr/{supplement_nutrient_id} -> 200
GET    /api/v1/med/user-suppl-nutr                          -> 200
GET    /api/v1/med/user-suppl-nutr/{registration_id}        -> 200
PATCH  /api/v1/med/user-suppl-nutr/{registration_id}        -> 200
DELETE /api/v1/med/user-suppl-nutr/{registration_id}        -> 204
```

Test response nesting, effective slot times, status filtering, owner isolation, 404 for unknown product, 422 for duplicate/empty slots, and unauthenticated 401 for both catalog and user routes.

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
uv run pytest app/tests/med_apis/test_user_suppl_nutr_api.py app/tests/med_apis/test_med_openapi_docs.py -q
```

Expected: FAIL because the user routes are absent.

- [ ] **Step 3: Add the five Router operations**

Use these paths exactly:

```python
@med_router.put(
    "/user-suppl-nutr/{supplement_nutrient_id}",
    response_model=UserSupplementNutrientResponse,
    summary="사용자 복용 영양제 등록 또는 재등록",
)
@med_router.get(
    "/user-suppl-nutr",
    response_model=UserSupplementNutrientListResponse,
    summary="사용자 복용 영양제 목록 조회",
)
@med_router.get(
    "/user-suppl-nutr/{user_suppl_nutrient_id}",
    response_model=UserSupplementNutrientResponse,
    summary="사용자 복용 영양제 상세 조회",
)
@med_router.patch(
    "/user-suppl-nutr/{user_suppl_nutrient_id}",
    response_model=UserSupplementNutrientResponse,
    summary="사용자 복용 영양제 수정",
)
@med_router.delete(
    "/user-suppl-nutr/{user_suppl_nutrient_id}",
    status_code=204,
    summary="사용자 복용 영양제 종료",
)
```

Place the fixed collection route before the dynamic detail route. Every endpoint receives `user: Annotated[User, Depends(get_request_user)]`, delegates to Service, and contains a Korean purpose docstring plus concise Swagger `summary`.

- [ ] **Step 4: Add explicit response builder**

Create one Service or Router helper that converts a prefetched registration plus `UserSettings` into `UserSupplementNutrientResponse`. It must include all product fields and sorted slots with actual `time`; do not duplicate this mapping across endpoint functions.

- [ ] **Step 5: Verify OpenAPI contract**

Test that `/api/openapi.json` contains all seven catalog/user operations across the four collection/detail paths, bearer auth requirements, query bounds, request schemas, summaries, and no old `/api/v1/supplement-nutrients` or `/api/v1/user-suppl-nutrients` path.

- [ ] **Step 6: Run all med API tests**

Run `uv run pytest app/tests/med_apis -q`.

Expected: PASS.

---

### Task 6: Re-runnable Numbers importer

**Files:**

- Modify: `pyproject.toml`
- Modify: `uv.lock`
- Create: `scripts/import_supplement_nutrients.py`
- Create: `tests/scripts/test_import_supplement_nutrients.py`

**Interfaces:**

- Produces: `EXPECTED_HEADERS`, `parse_numbers(path)`, `validate_rows(rows)`, `upsert_records(records)`
- Consumes: `SupplementNutrient`, `TORTOISE_ORM`

- [ ] **Step 1: Add dependency**

Run:

```bash
uv add --group app numbers-parser
```

Expected: `pyproject.toml` app group and `uv.lock` contain `numbers-parser`.

- [ ] **Step 2: Write failing pure parsing tests**

Use literal header and row fixtures. Assert:

- all 31 Korean headers and order must match
- empty string/None becomes None for nullable nutrients
- `0` remains numeric zero, not None
- integers and Decimal scales convert correctly
- duplicate food code raises an error naming both row numbers
- a too-long string or numeric overflow names the row and column

- [ ] **Step 3: Write failing database upsert test**

Call `upsert_records` twice with the same two food codes, changing one name before the second call. Assert first result `(created=2, updated=0)`, second `(created=0, updated=2)`, final count 2, and changed name persisted.

- [ ] **Step 4: Run importer tests and verify RED**

Run `uv run pytest tests/scripts/test_import_supplement_nutrients.py -q`.

Expected: FAIL because the script module does not exist.

- [ ] **Step 5: Implement parser and full-file validation**

Set `EXPECTED_HEADERS` to the exact source header list:

```python
EXPECTED_HEADERS = [
    "식품코드", "식품명", "영양성분제공단위량", "에너지(kcal)", "수분(g)",
    "단백질(g)", "지방(g)", "회분(g)", "탄수화물(g)", "당류(g)",
    "식이섬유(g)", "칼슘(mg)", "철(mg)", "인(mg)", "칼륨(mg)",
    "나트륨(mg)", "비타민 A(μg RAE)", "레티놀(μg)", "베타카로틴(μg)",
    "티아민(mg)", "리보플라빈(mg)", "니아신(mg)", "비타민 C(mg)",
    "비타민 D(μg)", "콜레스테롤(mg)", "포화지방산(g)", "트랜스지방산(g)",
    "1회분량", "1회분량중량/부피", "1일섭취횟수", "섭취대상",
]
```

Parse the first sheet/table using `numbers_parser.Document`, find the first non-empty row as header, and validate every row before opening a DB transaction.

- [ ] **Step 6: Implement transactional bulk upsert**

Fetch existing products by `food_code__in`, split records into model instances for `bulk_create` and existing objects for `bulk_update`, process with `batch_size=500`, and update every source-backed field. Do not delete rows missing from the current source.

- [ ] **Step 7: Implement CLI**

Required invocation:

```bash
uv run python scripts/import_supplement_nutrients.py \
  '/Users/admin/Downloads/전국건강기능식품영양성분정보표준데이터-20260824.numbers'
```

Initialize Tortoise with `TORTOISE_ORM`, close connections in `finally`, return nonzero on validation/database failure, and print exactly these counters: `total`, `created`, `updated`, `failed`.

- [ ] **Step 8: Run importer tests**

Run `uv run pytest tests/scripts/test_import_supplement_nutrients.py -q`.

Expected: PASS.

---

### Task 7: Aerich migration, dbdiagram notes, Docker MySQL, and source import

**Files:**

- Create: `app/core/db/migrations/models/5_*_add_supplement_nutrition.py` (exact timestamp is assigned by Aerich)
- Modify external artifact: `https://dbdiagram.io/d/FinalProject-6a79bddbe093539a9e8459eb`

**Interfaces:**

- Consumes: final models from Task 1 and importer from Task 6
- Produces: synchronized ERD, migration, Docker schema, and 5,556 product rows

- [ ] **Step 1: Generate migration**

Run:

```bash
uv run aerich migrate --name add_supplement_nutrition
```

Expected: one new migration creating `supplement_nutrients`, `user_suppl_nutrient`, and `user_suppl_nutrient_slots` with enum comments, unique constraints, indexes, and FK delete policies.

- [ ] **Step 2: Review migration before applying**

Confirm no unrelated table or column is altered. Confirm decimal precision, max lengths, `RESTRICT`/`CASCADE`, and indexes match the spec. If Aerich omits the check constraints, add safe MySQL checks for `dose_amount > 0` and `end_date IS NULL OR end_date >= start_date` to the migration.

- [ ] **Step 3: Update dbdiagram**

Add DBML `Enum supplement_status`, the two user tables, indexes, checks, and three FK refs. Confirm every column has `note`, table Notes exist, index notes exist, relation comments explain deletion policy, and dbdiagram displays the saved state without parser alerts.

- [ ] **Step 4: Apply migration to Docker MySQL**

Run:

```bash
uv run aerich upgrade
```

Then inspect `SHOW CREATE TABLE` for all three tables and compare with the Tortoise metadata and dbdiagram.

- [ ] **Step 5: Import source twice**

Run the CLI from Task 6 twice. Expected first run: `total=5556`, `created=5556`, `updated=0`, `failed=0` when the table is empty. Expected second run: `total=5556`, `created=0`, `updated=5556`, `failed=0`.

- [ ] **Step 6: Verify database invariants**

Run SQL:

```sql
SELECT COUNT(*) AS total,
       COUNT(DISTINCT food_code) AS unique_codes
FROM supplement_nutrients;

SELECT name, food_code
FROM supplement_nutrients
WHERE name LIKE '%철분%'
ORDER BY name, id
LIMIT 20;
```

Expected: `total=5556`, `unique_codes=5556`, and at least one matching product.

---

### Task 8: Final integration and regression verification

**Files:**

- Modify only files required to fix failures attributable to Tasks 1–7

**Interfaces:**

- Consumes all previous tasks
- Produces final verified feature with no commit

- [ ] **Step 1: Run focused tests**

```bash
uv run pytest \
  tests/models/test_supplement_nutrition_model.py \
  tests/scripts/test_import_supplement_nutrients.py \
  app/tests/med_apis -q
```

Expected: all focused tests PASS.

- [ ] **Step 2: Run Ruff**

```bash
uv run ruff check \
  app/models/supplement_nutrients.py \
  app/dtos/supplement_nutrients.py \
  app/dtos/user_supplement_nutrients.py \
  app/repositories/supplement_nutrient_repository.py \
  app/repositories/user_supplement_nutrient_repository.py \
  app/services/supplement_nutrients.py \
  app/services/user_supplement_nutrients.py \
  app/apis/v1/med_router.py \
  scripts/import_supplement_nutrients.py \
  tests/models/test_supplement_nutrition_model.py \
  tests/scripts/test_import_supplement_nutrients.py \
  app/tests/med_apis
```

Expected: no lint errors.

- [ ] **Step 3: Run full Python test suite**

```bash
uv run pytest -q
```

Expected: all existing and new tests PASS.

- [ ] **Step 4: Smoke-test running FastAPI**

Recreate FastAPI only if dependency or container image changes require it. Authenticate, call `/api/v1/med/nutr?name=철분`, PUT one product to `/api/v1/med/user-suppl-nutr/{id}`, GET the user list, and confirm nested product plus effective slot times.

- [ ] **Step 5: Review final diff and database state**

Run:

```bash
git diff --check
git status --short
git diff --stat
```

Confirm no unrelated user changes were overwritten, the design and plan remain uncommitted, no secrets or source health dataset rows were accidentally committed, and Docker MySQL contains exactly 5,556 unique product codes.
