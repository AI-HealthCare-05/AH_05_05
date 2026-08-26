---
title: Medication Schedule Endpoint Migration - Plan
type: refactor
date: 2026-08-26
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
product_contract_source: ce-plan-bootstrap
execution: code
---

# Medication Schedule Endpoint Migration

## Goal Capsule

복약 시간 설정 API를 `GET/PUT /api/v1/med/medication/schedule/{record_id}`로 직접 전환한다. 프런트 화면 URL과 DB 저장 구조는 유지하면서, 레코드 식별자를 쿼리·요청 본문이 아닌 API 경로 하나로만 전달한다.

## Product Contract

### Requirements

- **R1** — 복약 시간 조회와 저장은 새 경로에서만 제공한다.
- **R2** — `record_id`는 1 이상의 필수 path parameter이며 해당 사용자의 복약 기록을 식별한다.
- **R3** — GET은 `recordId` 쿼리를 요구하지 않고 PUT 요청 본문은 `recordId`를 노출하지 않는다.
- **R4** — 소유자 검증, 사용자 설정 시간, 복약 시작 정보, 약별 슬롯 저장, 응답 및 오류 의미는 기존 동작을 유지한다.
- **R5** — 기존 `/api/v1/medications/schedule` 경로는 호환 별칭 없이 제거한다.
- **R6** — 프런트 화면 주소의 `?recordId=`는 유지하되 서버 호출에는 새 경로를 사용한다.
- **R7** — Notion API 명세의 GET/PUT 복약 시간 설정 항목을 구현과 동일하게 갱신한다.

### Scope Boundaries

포함 범위는 백엔드 라우터·DTO·서비스 경계, 프런트 API 호출부와 세 저장 화면, 백엔드 계약/회귀 테스트, Playwright 요청 가로채기, Notion GET/PUT 명세다.

DB 스키마·마이그레이션, 회원가입 로직, 영양제 API, 화면 라우트 구조, 기존 복약 저장 트랜잭션의 의미 변경은 범위 밖이다.

## Planning Contract

### Key Technical Decisions

- **KTD1** — 직접 전환한다. *(session-settled: user-directed — chosen over legacy alias: 아직 대기 중인 API이며 중복 계약을 남기지 않기 위해)* Governs R1, R5.
- **KTD2** — 공개 요청의 레코드 식별자는 path parameter 하나로 통일하고 서비스에는 DTO와 별도로 전달한다. *(session-settled: user-directed — chosen over query/body duplication: 조회와 저장의 식별 규칙을 일치시키기 위해)* Governs R2, R3, R4.
- **KTD3** — 복약 스케줄 전용 라우터 모듈은 유지하고 prefix만 `/med/medication`으로 이동한다. 기존 영양 라우터와 구현 책임을 섞지 않는다. Governs R1, R4.
- **KTD4** — 새 OpenAPI/라우팅 계약을 먼저 실패 테스트로 고정한 뒤 구현한다. Governs R1, R2, R3, R5.

## High-Level Technical Design

API 표면과 식별자 흐름은 다음처럼 단일화한다. 이는 방향을 설명하며 세부 구현 서명을 규정하지 않는다.

```text
화면 URL ?recordId=315
        │ 화면이 recordId 해석
        ▼
GET/PUT /api/v1/med/medication/schedule/315
        │ 인증 사용자 + path record_id
        ▼
복약 스케줄 서비스 ── 기존 트랜잭션 ── UserSettings / Episode / Slots
```

## Implementation Units

### U1 — 백엔드 공개 계약 전환

**Covers:** R1, R2, R3, R4, R5; KTD1, KTD2, KTD3, KTD4.

**Files:**

- `app/apis/v1/medication_schedule_router.py`
- `app/dtos/medication_schedule.py`
- `app/services/medication_schedule.py`
- `app/tests/med_apis/test_medication_schedule_api.py`

**Approach:** 전용 라우터를 새 prefix와 `/{record_id}` 경로로 바꾸고 양 메서드에 양의 정수 path 검증을 둔다. 저장 DTO에서 `record_id`를 제거하고 서비스 저장 메서드에 별도 인자로 전달하되 내부 DB 쓰기 순서와 결과는 유지한다.

**Execution note:** OpenAPI에 새 GET/PUT만 존재하고 PUT 스키마에 `recordId`가 없으며 기존 경로가 404가 되는 테스트를 먼저 실패시킨다.

**Test scenarios:**

- 유효한 소유 기록 ID로 조회하면 기존 사용자 설정 시간과 약 4개를 포함한 동일 응답을 반환한다.
- 유효한 ID로 저장하면 사용자 설정, 복약 시작, 약별 슬롯이 기존처럼 반영된다.
- `0` 또는 정수가 아닌 path ID는 422이며 DB 쓰기가 없다.
- 인증 헤더 없는 새 GET/PUT은 401이며 PUT은 DB를 변경하지 않는다.
- 다른 사용자의 ID는 기존 소유자 오류를 유지한다.
- 옛 GET/PUT 경로는 스케줄 API로 처리되지 않고(404/405) OpenAPI에도 노출되지 않는다.

### U2 — 프런트 API 호출자 전환

**Depends on:** U1.

**Covers:** R3, R6; KTD2.

**Files:**

- `frontend/src/entities/medication/api.ts`
- `frontend/src/entities/medication/types.ts`
- `frontend/src/pages/medication-schedule/MedicationSchedulePage.tsx`
- `frontend/src/pages/medication-schedule/MedicationAlarmTimesPage.tsx`
- `frontend/src/pages/medications/MedicationEpisodePage.tsx`

**Approach:** 저장 함수는 `recordId`와 본문을 별도 인자로 받고 조회·저장 모두 새 path URL을 구성한다. 저장 본문 타입과 두 화면의 payload에서 `recordId`를 제거한다. 화면 탐색용 쿼리 파라미터는 유지한다.

**Test scenarios:**

- 설정 화면 진입 시 화면 쿼리의 ID로 새 GET 경로를 요청한다.
- 세 저장 화면 모두 같은 ID의 새 PUT 경로를 요청하고 JSON 본문에는 `recordId`가 없다.
- ID 없는 직접 진입은 임의 서버 기록을 조회하지 않는 기존 방어 동작을 유지한다.
- PUT 실패 뒤 화면 입력을 보존하고 같은 path ID로 다시 저장할 수 있다.

### U3 — 통합 계약과 명세 동기화

**Depends on:** U1, U2.

**Covers:** R1, R3, R5, R6, R7.

**Files and sources:**

- `frontend/tests/e2e/medication-registration-flow.spec.ts`
- [Notion GET 복약 시간 설정 명세](https://app.notion.com/p/8ecafc3f131f830280d401311c76eca2)
- [Notion PUT 복약 시간 설정 명세](https://app.notion.com/p/3f7afc3f131f82dc9f8701cac169c99d)

**Approach:** Playwright route matcher와 요청 단언을 새 path 기반으로 변경하고 GET 쿼리 및 PUT 본문의 `recordId` 부재를 확인한다. Notion 엔드포인트 속성, path parameter, 요청 본문 예시를 같은 계약으로 갱신한다.

**Test scenarios:**

- OCR 검토에서 복약 시간 설정으로 이동한 뒤 약 4개가 표시되고 새 GET 요청이 발생한다.
- 저장 후 새 PUT 경로가 호출되며 DB 회귀 테스트가 기존 저장 결과를 증명한다.
- 첫 PUT이 실패한 뒤 재시도하면 동일한 새 path로 성공하고 사용자의 입력을 잃지 않는다.
- 복약 시간 설정의 뒤로가기는 OCR 검토 화면으로 돌아가는 기존 동작을 유지한다.

## Verification Contract

1. `uv run pytest app/tests/med_apis/test_medication_schedule_api.py -q`
2. `uv run pytest app/tests/med_apis -q`
3. 변경한 Python 파일에 `uv run ruff check` 실행
4. `pnpm --dir frontend typecheck`
5. `pnpm --dir frontend build`
6. `pnpm --dir frontend test:e2e:ocr`
7. 새 OpenAPI 경로, 브라우저 요청, Notion GET/PUT 문서가 모두 동일한 계약인지 최종 검색으로 대조한다.

## Risks and Mitigations

- 작업 폴더에 사용자의 기존 미커밋 변경이 있으므로 관련 파일만 최소 수정하고 unrelated diff를 건드리지 않는다.
- E2E wildcard가 옛 경로까지 허용하지 않도록 pathname과 PUT 본문을 명시적으로 단언한다.
- API 경로만 바뀌므로 DB 마이그레이션은 만들지 않고 기존 저장 회귀 테스트로 데이터 의미 보존을 검증한다.

## Definition of Done

- 새 GET/PUT 경로가 유일한 복약 시간 설정 API다.
- 레코드 ID가 path에만 있고 GET 쿼리와 PUT 본문에는 없다.
- 조회·저장·소유자 검증·사용자별 시간·약 4개·뒤로가기 회귀 테스트가 통과한다.
- 프런트 타입 검사와 빌드 및 관련 E2E가 통과한다.
- Notion GET/PUT 명세가 구현과 일치한다.
- 사용자 작업을 보존하며 커밋이나 푸시는 하지 않는다.
