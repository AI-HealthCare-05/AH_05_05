# Nutrient Standard Implementation Plan

**Goal:** Add the 2025 Korean nutrient intake standards as a wide `nutrient_standard` table and expose a read-only list API under `/api/v1/med`.

## Design

- One row represents one Excel population/age row.
- `grp` stores the Excel `구분`, and nullable `age` stores `연령`.
- Each of the 15 nutrients has three nullable columns: `_rni` (권장섭취량), `_ai` (충분섭취량), and `_ul` (상한섭취량).
- Nutrient prefixes match `supplement_nutrients` fields, such as `carb_g`, `calcium_mg`, and `vitamin_a_ug_rae`.
- Source blanks remain `NULL`; comma separators are removed before numeric conversion.
- The API is authenticated, list-only, pageable, and filterable by `grp` and `age`.

## Tasks

1. Add failing model metadata and API tests.
2. Add the Tortoise model, DTO, repository, service, and `/api/v1/med/nutr-std` endpoint.
3. Generate an Aerich migration containing the table definition and source rows.
4. Run focused tests, Ruff, migration checks, and the full test suite as practical.
5. Add the table definition to the requested dbdiagram after action-time confirmation.

