# Medication and Supplement Knowledge Data

약·영양제 기본정보와 상호작용 답변에 사용하는 원본 및 전처리 데이터의 로컬 작업 구조입니다.

## 디렉터리

- `manifests/`: Git에 포함하는 출처, 문서 해시, 중복 제거, 파일 유형별 pilot 목록
- `raw/`: 내려받은 원본의 로컬 복사본. Git과 Docker 이미지에서 제외
- `processed/`: 추출 텍스트, MySQL 적재용 records, Qdrant 적재용 chunks. Git과 Docker 이미지에서 제외

## 처리 원칙

1. `raw/` 파일은 직접 수정하지 않는다.
2. 파일명과 컬럼명 정규화는 `processed/` 생성 단계에서 수행한다.
3. SHA-256이 같은 파일만 정확한 중복으로 판단한다.
4. 텍스트를 추출할 수 없는 PDF는 해당 출처의 `ocr/` 디렉터리에 둔다.
5. 모든 PDF를 즉시 청킹하지 않고 `manifests/pilot_manifest.json`의 유형별 대표 파일부터 검증한다.
6. MySQL에는 제품·성분·DUR 등 구조화 가능한 레코드를 적재한다.
7. Qdrant에는 출처가 확인된 설명·주의·상호작용 근거 청크만 적재한다.
8. `DEMO_RESTRICTED` 자료는 내부 발표·포트폴리오 데모에서만 사용하며 원문 다운로드 API를 제공하지 않는다.

## VectorDB 파일럿 전처리

청킹 경계와 선택 이유는 `CHUNKING_STRATEGY.md`에 기록합니다. 대표 PDF만 다시 전처리하려면 저장소 루트에서 실행합니다.

```bash
uv run --group ai python -m scripts.preprocess_knowledge_pilots \
  --dataset-version knowledge-pilot-v1
```

이 명령은 다음 문서만 처리합니다.

- `pilot_manifest.json`에서 `TEXT_EXTRACTABLE` 상태인 문서
- `sources.yaml`에서 `target: QDRANT`로 허용된 출처

`OCR_REQUIRED`, `STRUCTURED_SOURCE`, `QDRANT_DISABLED_UNTIL_VERIFIED` 문서는 건너뜁니다. 실행 결과는 Git에서 제외된 `processed/text/*.jsonl`과 `processed/chunks/*.jsonl`에 생성됩니다. 같은 문서를 다시 실행하면 동일한 청크 ID를 만들며, 인덱싱 대상에서 제외되거나 매니페스트에서 제거된 문서의 이전 텍스트·청크·검수 표본은 제거합니다.

### 대표 문서 품질 검사와 승인

전처리 명령은 다음 로컬 검수 산출물도 생성합니다.

- `processed/reports/preprocessing-quality.json`: 문서별 자동 품질 지표와 전체 처리 준비 출처 목록
- `processed/review/<document_id>.md`: 원본 PDF와 대조할 결정론적 표본 청크 및 체크리스트

자동 검사는 다음 조건을 확인합니다.

- 기존 텍스트 품질 검사: 최소 추출량, 대체문자, 비정상적인 장문 무공백 문자열
- 유형별 최대 토큰 초과 여부
- 제목 사전에 따른 의미 섹션이 하나 이상 탐지되었는지
- `SUPPLEMENT_CODE` 청크의 성분·계층 문맥 누락 여부
- 건강기능식품 일일섭취량의 의심 단위와 미해결 번호 참조 여부
- 원료·기능성·일일섭취량·주의사항 간 경계 혼입 및 제외 대상 제조기준·규격·시험법 혼입 여부
- 건강기능식품공전의 필수 절(`원료`, `기능성 내용`, `일일섭취량`) 누락 여부
- 빈 괄호·뒤집힌 괄호·비정상 구두점과 성분 기호 위치가 깨진 알려진 문장 패턴

`SUPPLEMENT_CODE` 검수 표본에는 길이 기준 표본뿐 아니라 문서에 존재하는 각 절의
첫 청크도 포함합니다. 복원 규칙은 번호·고정 필드명·현재 성분·원문 수치가 모두
확인되는 경우에만 적용하며, 의미가 불확실한 문장은 추측하지 않고 자동 차단합니다.
검색 청크의 원료 절에는 `(가) 한글 원료명 (English Ingredient Name)` 형식으로
식별되는 항목만 포함합니다. 설명문·일반 식품원료 문장·제조기준 `(2)·(3)`·규격·
시험법은 원본 추출문에는 보존하지만 Qdrant 후보에서는 제외합니다. 기능성 내용,
일일섭취량, 원문에 존재하는 주의사항은 각각 독립 검색 청크로 유지합니다.

건강기능식품공전 대표 문서의 문제, 전용 파서 보완 내용과 재처리 전후 결과는
`SUPPLEMENT_CODE_PREPROCESSING_RESULTS.md`에 기록합니다. 자동 `PASS`는
구조적 오류를 찾지 못했다는 뜻이며, 수동 검수 상태를 자동으로 승인하지 않습니다.

자동 상태가 `PASS`여도 전체 원본으로 바로 확대하지 않습니다. 검수자는
`review/<document_id>.md`의 표본을 원본 PDF와 대조한 뒤 해당
`pilot_manifest.json` 항목에 아래 상태를 기록합니다.

```json
"manual_review_status": "APPROVED"
```

가능한 값은 `PENDING`, `APPROVED`, `REJECTED`이며 기본값은 `PENDING`입니다.
같은 출처의 대표 문서가 모두 `자동 PASS + 수동 APPROVED`인 경우에만 실행
결과의 `ready_for_bulk_source_ids`에 포함됩니다. `REVIEW`는 제목·섹션 규칙을
보완하고 다시 실험하며, `BLOCKED`는 청크를 전체 처리 후보로 사용하지 않습니다.
현재 명령은 대표 문서만 처리하고 전체 원본 확대는 수행하지 않습니다.

## 불변 Qdrant release 생성

전처리된 청크를 새 컬렉션에 적재하려면 다음 명령을 실행합니다.

```bash
uv run --group ai python -m scripts.index_knowledge_release \
  --dataset-version knowledge-pilot-v1 \
  --collection medication_knowledge_pilot_v1
```

인덱싱 명령은 같은 dataset version의
`processed/reports/preprocessing-quality.json`을 읽습니다. 청크에 포함된 모든
출처가 `ready_for_bulk_source_ids`에 없으면 OpenAI 임베딩 호출과 Qdrant 적재를
시작하기 전에 실패합니다. 따라서 자동 `PASS`만으로는 적재할 수 없고, 대표
문서 표본의 수동 `APPROVED`까지 완료해야 합니다.

현재 파일럿처럼 `DEMO_RESTRICTED` 청크가 포함된 release는 기본적으로 외부 임베딩 전송을 차단합니다. 자료 이용 범위와 외부 API 전송을 확인하고 명시적으로 승인한 경우에만 다음 플래그를 추가합니다.

```bash
  --allow-demo-restricted
```

- `content`는 답변의 근거·출처 표시에 보존하고, 검색 임베딩에는 약명·성분명·섹션명이 포함된 `embedding_text`를 사용합니다.
- 컬렉션은 release 단위의 불변 산출물입니다. 같은 이름이 이미 있으면 덮어쓰거나 먼저 삭제하지 않고 실패합니다.
- 새 release는 반드시 새 컬렉션 이름으로 생성합니다. 검증 전까지 기존 `public_guidelines_small_v1`과 Chat Core의 현재 컬렉션 설정은 변경하지 않습니다.
- 적재가 끝난 뒤 Qdrant point 수와 JSONL 청크 수가 정확히 같은지 검사합니다.

## 검색 품질 평가

파일럿 질문 세트로 새 컬렉션을 평가하려면 다음 명령을 실행합니다.

```bash
uv run --group ai python -m scripts.evaluate_knowledge_retrieval \
  --evaluation-file data/knowledge/evaluation/pilot_queries.yaml \
  --dataset-version knowledge-pilot-v1 \
  --collection medication_knowledge_pilot_v1 \
  --output data/knowledge/reports/knowledge-pilot-v1.json
```

평가는 질문 임베딩 시간을 제외한 Qdrant 검색 시간과 함께 Hit@5, MRR, 출처 정확도, 잘못된 약·성분 혼합, 중복 검색 결과를 기록합니다. 종료 코드 `0`은 모든 품질 기준 통과, `2`는 실행은 정상적으로 끝났지만 하나 이상의 품질 기준을 통과하지 못했다는 의미입니다. 생성된 JSON 보고서는 로컬 실험 산출물이므로 Git에서 제외합니다.

평가를 통과한 뒤에만 FastAPI/Chat Core가 참조하는 컬렉션 별칭 또는 설정을 새 release로 전환합니다. 전환에 실패하면 기존 컬렉션으로 되돌릴 수 있으므로 Qdrant 볼륨이나 기존 컬렉션을 먼저 삭제하지 않습니다.

현재 파일럿의 실제 평가 결과는 `EVALUATION_RESULTS.md`에 기록되어 있습니다.

## Chat Core 연결

검색 평가를 통과한 `knowledge-pilot-v1`은 Chat Core의 기본 Knowledge 검색 대상으로 연결되어 있습니다.

```dotenv
KNOWLEDGE_QDRANT_COLLECTION=medication_knowledge_pilot_v1
KNOWLEDGE_DATASET_VERSION=knowledge-pilot-v1
```

Chat Core는 새 `QdrantKnowledgeStore`를 직접 기존 가이드라인 스키마로 읽지 않습니다. `KnowledgeGuidelineRetriever`가 dataset version과 질문 유형별 메타데이터 필터를 적용한 뒤, 검색 결과를 기존 답변·출처 계약으로 변환합니다.

기존 `QDRANT_COLLECTION` 설정은 아직 레거시 공공 PDF 인덱싱 Worker와 회복 가이드 데모가 사용합니다. 새 Chat 검색 대상과는 별도 설정입니다. 레거시 Worker에 새 작업을 등록하면 삭제한 과거 컬렉션이 다시 만들어질 수 있으므로, 프로젝트 방향 전환 후에는 해당 작업을 등록하지 않습니다.

## 응답 안전 원칙

- 보유한 환자 확정정보와 검색된 근거 범위 안에서만 답한다.
- 진단, 처방, 복용 시작·중단·증량·감량을 결정하지 않는다.
- 답변은 참고정보이며 의료진의 진료를 대체하지 않는다는 안내를 포함한다.
