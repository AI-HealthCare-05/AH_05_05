# 추가 연구 PDF Bulk Dry-run 결과

## 목적

대표 문서에서 검증한 전처리 규칙을 같은 출처 유형의 전체 PDF에 적용하되,
검색 메타데이터가 없거나 표·다단·회전 텍스트의 읽기 순서가 불확실한 문서는
임베딩 전에 격리한다. 자동 검사 기준을 낮춰 문서를 통과시키지 않는다.

## 입력과 처리 조건

- 입력 문서: 추가 연구 PDF 12개
- 토크나이저: `o200k_base`
- 원본 범위: `PUBLIC` 및 내부 시연용 `DEMO_RESTRICTED`
- 대표 검수 규칙: 텍스트 복원, 검증 섹션 제목, 승인 청크 해시,
  승인된 레이아웃 경고를 Bulk Manifest에 상속
- 외부 전송: 없음
- Qdrant 변경: 없음

## 1차 Dry-run 문제

| 상태 | 문서 수 | 릴리스 청크 수 |
|---|---:|---:|
| PASS | 5 | 196 |
| REVIEW | 3 | 0 |
| BLOCKED | 4 | 0 |

비대표 문서 7개에서 제목·출처 URL·DOI·검색 대상·근거 수준이 비어 있었다.
따라서 본문 추출 품질과 관계없이 `MISSING_SEARCH_ENTITIES`,
`MISSING_SOURCE_METADATA`, `UNKNOWN_EVIDENCE_LEVEL`이 발생했다.

## 품질 보완

1. PDF 내부 메타데이터와 원문 첫 페이지를 기준으로 제목·저자·발행연도·DOI를
   문서 카탈로그에 기록했다.
2. 문서 전체에 공통인 약 또는 영양성분만 검색 메타데이터에 기록했다.
   개별 청크에만 등장하는 모든 물질을 문서 전체 메타데이터로 올려 다른 대상이
   검색 결과에 섞이는 문제를 피했다.
3. 대표 문서에서 수동 승인한 텍스트 교정·섹션 경계·청크 해시·경고 예외를
   전체 Manifest 작성 시 잃지 않도록 상속 계약을 추가했다.
4. 레이아웃 위험은 메타데이터 보완으로 숨기지 않고 REVIEW/BLOCKED 상태를
   유지했다.

## 2차 Dry-run 결과

| 상태 | 문서 수 | 청크 수 | 처리 |
|---|---:|---:|---|
| PASS | 6 | 248 | 임베딩 후보 |
| REVIEW | 2 | 11 | 원문 대조 전까지 격리 |
| BLOCKED | 4 | 83 | 레이아웃 복원 전까지 격리 |
| 합계 | 12 | 342 | 248개만 릴리스 가능 |

### PASS 문서

- FDA LEVO-T 허가문서: 58청크
- 아스피린·와파린과 영양소 상호작용 문헌고찰: 44청크
- 만성 복용 의약품과 영양소 상호작용 문헌고찰: 52청크
- 레보티록신과 음식·의약품 상호작용 체계적 문헌고찰: 29청크
- 허브·영양제 상호작용 체계적 문헌고찰: 26청크
- 식물성 보충제 이상반응 체계적 문헌고찰: 39청크

### 격리 문서

| 문서 | 상태 | 청크 | 남은 원인 |
|---|---|---:|---|
| Drug-vitamin D interactions | BLOCKED | 19 | 다단·회전 텍스트·표 구조·짧은 조각 |
| Levothyroxine with calcium formulations | REVIEW | 9 | 다단 읽기 순서·짧은 조각 |
| Statins and vitamin D | BLOCKED | 27 | 다단·표 구조 |
| Warfarin and food/herbal/supplement | BLOCKED | 32 | 다단·회전 텍스트·표 구조 |
| Drug–herb interactions in primary care | REVIEW | 2 | 다단 읽기 순서 |
| St John's wort with conventional drugs | BLOCKED | 5 | 다단·읽기 순서·짧은 조각 |

## 재현 명령

```bash
uv run --group ai --group dev \
  python -m scripts.preprocess_knowledge_corpus \
  --documents data/knowledge/manifests/documents.jsonl \
  --sources data/knowledge/manifests/sources.yaml \
  --pilot-quality-report \
    data/knowledge/processed/additional_research_pilot/reports/preprocessing-quality.json \
  --pilot-manifest \
    data/knowledge/manifests/additional_research_pilot_manifest.json \
  --output \
    data/knowledge/processed/additional-research-bulk-o200k-dry-run-v2 \
  --dataset-version additional-research-bulk-dry-run-v2-o200k \
  --tokenizer-encoding o200k_base \
  --interaction-annotations \
    data/knowledge/manifests/interaction_annotations.yaml
```

## 임베딩 전 승인 조건

- 임베딩 대상은 2차 Dry-run의 PASS 6개, 248청크로 제한한다.
- 기존 `knowledge-full-v2-o200k`와 합칠 때 문서 ID와 청크 ID 중복을 검사한다.
- 새 dataset version과 새 불변 Qdrant collection을 사용한다.
- `DEMO_RESTRICTED` 청크 수와 OpenAI 전송 범위를 사용자에게 다시 제시하고
  명시적으로 승인받은 뒤 실행한다.
- REVIEW/BLOCKED 94청크는 자동으로 포함하지 않는다.

