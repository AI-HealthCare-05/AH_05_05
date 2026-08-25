# Processed data

원본에서 재생성 가능한 중간 산출물입니다. 실제 파일은 Git과 Docker 이미지에서 제외됩니다.

```text
processed/
├── text/       # PDF 추출 또는 OCR 텍스트
├── staging/    # 불변 generation 단위 RDBMS 적재 후보와 품질 보고서
├── chunks/     # Qdrant 임베딩 직전 청크와 메타데이터
├── reports/    # 대표 문서별 자동 품질 지표 JSON
├── review/     # 원본과 사람이 대조할 결정론적 표본 Markdown
└── failed/     # 실패 파일과 오류 기록
```

Qdrant 벡터 자체는 이 디렉터리가 아니라 Qdrant Docker Volume에 저장합니다.

`text/*.jsonl`은 페이지 번호를 포함한 정규화 원문이고, `chunks/*.jsonl`은 Qdrant 임베딩 직전 계약입니다. 청크의 `content`는 출처 표시용 원문이며 `embedding_text`는 문서·약/성분·섹션 접두어를 추가한 검색용 텍스트입니다.

현재 파일럿 산출물은 품질 검토용이며 자동으로 Qdrant에 적재되지 않습니다.

`staging/<version>/<generation>/interaction_rule_candidates.jsonl`은 식약처 DUR
병용금기 CSV에서 결정론적으로 생성한 약-약 규칙 후보입니다. 자동 생성 상태는 모두
`PENDING`이며 MySQL에 자동 적재되지 않습니다. `--allow-pending`을 명시한 importer로
검수 대기 상태 그대로 보관할 수 있지만 런타임 답변에는 사용할 수 없습니다. 같은 generation의
`interaction-staging-quality.json`에서 원본 행 수, 중복 병합 수, 제외 사유와 원본
줄 번호를 확인한 뒤 별도의 승인 단계가 필요합니다. 소비자는 항상
`staging/<version>/current.json`이 가리키는 두 파일을 함께 읽어야 합니다.

`reports/preprocessing-quality.json`에는 페이지·문자·청크 수, 최소·평균·최대
토큰, 의미 섹션 비율, 자동 검사 상태와 수동 검수 상태가 기록됩니다.
`review/<document_id>.md`에는 첫·중간·마지막 및 최단·최장 청크를 중복 없이
선정한 표본과 원본 대조 체크리스트가 기록됩니다.
