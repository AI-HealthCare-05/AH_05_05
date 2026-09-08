# Typed Query Entity Design

## Goal

질문에서 실제 RDBMS, Qdrant 또는 활성 복용정보 카탈로그에 존재하는 약·영양제·음식·제품만 검색 엔터티로 승인하고, 임의 일반 단어가 약 이름으로 해석되는 일을 차단한다.

## Current problem

`MedicationKnowledgeQueryBuilder`는 제외어가 아닌 토큰을 기본적으로 `DRUG` 엔터티로 만든다. 따라서 `현재`, `가장`, `정리`, `먼저` 같은 일반 단어가 상호작용 조합과 제품 조회 후보가 될 수 있다. `DbMedicationExpressionCatalog`도 표현 문자열만 반환하므로 엔터티의 타입과 출처가 유실된다.

## Design

### Typed catalog entry

새 `MedicationCatalogEntry` 계약은 다음 정보를 보존한다.

- `canonical_name`: 검색과 출처 표시에 사용할 표준 이름
- `aliases`: 사용자 표현과 비교할 별칭
- `entity_type`: `PRODUCT_NAME`, `BRAND_ALIAS`, `INGREDIENT_NAME`, `FOOD_CATEGORY`, `INGREDIENT_FAMILY`
- `kind`: `DRUG`, `SUPPLEMENT`, `FOOD` 또는 제품 정보만 있는 경우 `None`
- `source`: `RDBMS`, `QDRANT`, `PATIENT_CONTEXT`, `CATALOG`

카탈로그는 동일 표현이 여러 유형으로 존재할 수 있으므로, 이름이 아닌 `(canonical_name, entity_type, source)`로 보존한다. 제품명이나 별칭은 약물 가이드 조회에 사용할 수 있지만 상호작용 쌍에는 `kind`가 있는 엔터티만 참여한다.

### Catalog sources

- RDBMS: `MedicationProductGuide`, `InteractionEntity`, `InteractionEntityAlias`, `SupplementNutrient`
- Qdrant: 활성 데이터셋 payload의 `drug_names`, `ingredient_names`, `food_names` 메타데이터. 필드가 없는 릴리스는 빈 목록으로 안전하게 처리한다.
- Patient context: 사용자의 현재 활성 약과 영양제. 이전 두 공급원에 없더라도 현 사용자 정보는 엔터티로 인식한다.

각 공급원은 5분 TTL 캐시를 사용하고, 복합 카탈로그는 부분 장애가 나도 사용 가능한 공급원의 결과만 합친다.

### Question flow

1. Resolver가 원본 질문을 정규화하고 카탈로그를 사용해 오타·띄어쓰기를 보정한다.
2. 보정된 질문에서 typed catalog entry와 정확히 일치하는 표현만 `MedicationQueryEntity`로 반환한다.
3. Query Plan chain은 Resolver가 반환한 엔터티를 우선 사용한다. 카탈로그 엔터티가 없는 단어는 `DRUG`로 추론하지 않는다.
4. 상호작용 쌍은 `DRUG`, `SUPPLEMENT`, `FOOD` 타입이 확정된 두 엔터티 사이에서만 만든다.
5. 유효 엔터티가 없는 일반 추천 질문은 제품 가이드 조회와 광범위한 임의 제품 fallback을 하지 않는다. 근거 없는 범위 내 질문은 "대상을 특정해 달라"는 제한 응답으로 끝낸다.

### Legacy compatibility boundary

기존 단위 테스트나 독립 실행 도구가 `MedicationKnowledgeQueryBuilder`만 직접 호출하는 경우에만 과거의 정규식 기반 추론을 호환 모드로 남긴다. 실제 `MedicationChatCoreService` 경로는 항상 Resolver와 typed catalog를 주입하므로, 운영 요청에서는 이 호환 모드가 사용되지 않는다.

## Safety constraints

- 제품·성분명 예외 목록을 코드에 추가하지 않는다.
- RAG 점수 기준을 낮추지 않는다.
- 카탈로그 부재를 특정 약 이름 추정으로 보완하지 않는다.
- 일반 질문에는 현재 복용 목록을 답변 근거로 자동 노출하지 않는다.

## Verification

- "피곤할 때 가장 좋은 영양제 하나 추천해줘"는 엔터티와 제품 가이드 조회가 모두 0건이다.
- "현재 복용 중인 약과 영양제를 정리하고 가장 먼저 확인할 상호작용을 알려줘"는 일반 단어가 엔터티나 쌍이 되지 않는다.
- 실제 카탈로그의 제품·성분·음식은 타입과 출처를 보존한다.
- 기존 타이레놀 오타 교정과 마그네슘 기능성 검색 회귀 테스트가 통과한다.
