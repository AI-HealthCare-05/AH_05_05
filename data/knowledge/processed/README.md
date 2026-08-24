# Processed data

원본에서 재생성 가능한 중간 산출물입니다. 실제 파일은 Git과 Docker 이미지에서 제외됩니다.

```text
processed/
├── text/       # PDF 추출 또는 OCR 텍스트
├── records/    # MySQL 적재용 정규화 레코드
├── chunks/     # Qdrant 임베딩 직전 청크와 메타데이터
└── failed/     # 실패 파일과 오류 기록
```

Qdrant 벡터 자체는 이 디렉터리가 아니라 Qdrant Docker Volume에 저장합니다.

`text/*.jsonl`은 페이지 번호를 포함한 정규화 원문이고, `chunks/*.jsonl`은 Qdrant 임베딩 직전 계약입니다. 청크의 `content`는 출처 표시용 원문이며 `embedding_text`는 문서·약/성분·섹션 접두어를 추가한 검색용 텍스트입니다.

현재 파일럿 산출물은 품질 검토용이며 자동으로 Qdrant에 적재되지 않습니다.
