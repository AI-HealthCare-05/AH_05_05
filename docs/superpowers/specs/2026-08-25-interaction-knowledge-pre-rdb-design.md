# 상호작용 Knowledge의 RDBMS 직전 단계 설계

## 목표

약-약, 약-영양제, 영양제-영양제 상호작용을 다음 세 계층으로 분리한다.

- Qdrant: 원문 설명과 검색 근거 청크
- RDBMS 후보: 조합, 위험도, 출처 연결처럼 결정론적으로 조회할 규칙
- LLM: 검증된 규칙과 검색 근거를 친절한 한국어로 표현

이번 범위는 RDBMS에 쓰기 전까지다. ORM, Aerich migration, MySQL 연결과 런타임 규칙 조회는 수정하지 않는다.

## 현재 문제

현재 Qdrant Knowledge 스키마에는 약명·성분명·상호작용 유형 필드가 있으나 대표 상호작용 문서의 실제 청크에는 대부분 비어 있다. 또한 `DUR병용금기.csv`는 구조화된 공공 데이터인데도 RDBMS 적재 전에 사용할 정규화 계약과 품질 게이트가 없다.

상호작용을 LLM이 원문에서 자유롭게 추출하면 조합, 위험도, 출처가 달라질 수 있다. 따라서 구조화 출처는 결정론적으로 변환하고, 비정형 문서의 세부 근거는 Qdrant에 보존하되 검수된 주석만 규칙과 연결한다.

## 데이터 흐름

```text
DUR 병용금기 CSV
  -> 필수 컬럼 검사
  -> 약 성분명/코드 정규화
  -> 순서와 무관한 canonical pair_key 생성
  -> 같은 조합의 원인·원본 행 병합
  -> PENDING 후보 JSONL + 품질 보고서
  -> (이번 범위 밖) 사람 승인
  -> (이번 범위 밖) RDBMS 적재

상호작용 PDF
  -> 기존 PDF 정규화/의미 단위 청킹
  -> 검수된 pair_key 주석을 Qdrant metadata에 보존
  -> (이번 범위 밖) RDBMS 규칙의 evidence pair_key와 연결
```

## 계약

### 상호작용 주체

- 종류: `DRUG`, `SUPPLEMENT`, `FOOD`
- 표시 이름과 정규화 이름을 함께 보존한다.
- 출처에 코드가 있으면 `source_code`에 보존한다.

### 조합

- 종류: `DRUG_DRUG`, `DRUG_SUPPLEMENT`, `SUPPLEMENT_SUPPLEMENT`, `DRUG_FOOD`
- `pair_key`는 두 주체의 종류·정규화 이름을 정렬한 뒤 해시하여 생성한다.
- 입력 순서가 바뀌어도 같은 조합은 같은 키가 된다.

### 위험도

- 구조화된 DUR 병용금기는 `CONTRAINDICATED`로 변환한다.
- 근거가 부족한 PDF만으로 위험도를 추측하지 않는다.
- 자동 생성 후보의 검수 상태는 항상 `PENDING`이다.

### 출처 연결

- 구조화 원본의 `source_id`, `document_id`, 원본 행 식별자를 보존한다.
- Qdrant 근거가 검수되어 연결된 경우에만 `evidence_chunk_ids`를 추가한다.
- 출처나 필수 성분이 없는 행은 정상 후보로 만들지 않고 품질 보고서에 기록한다.

## 산출물

- `processed/records/interaction_rule_candidates.jsonl`: 향후 RDBMS 적재 후보
- `processed/reports/interaction-staging-quality.json`: 입력/출력/제외/중복 병합 수
- 두 파일은 재생성 가능하므로 Git에 포함하지 않는다.
- 코드, 테스트, 계약 문서만 Git에 포함한다.

## 안전 원칙

- `PENDING` 후보는 런타임 답변에 사용하지 않는다.
- 근거 없음은 `상호작용 없음`이 아니라 `확인 가능한 근거 없음`이다.
- LLM은 조합과 위험도를 생성하거나 승격하지 않는다.
- 원본의 금기 내용을 요약하지 않고 그대로 보존한다.
- 동일 조합에 여러 사유가 있으면 하나를 버리지 않고 모두 병합한다.

## 이번 범위 밖

- ORM 테이블과 migration
- MySQL import
- 관리자 승인 API/UI
- Chat Core의 RDBMS 규칙 조회
- 비정형 PDF에서 LLM으로 조합을 자동 추출하는 기능

