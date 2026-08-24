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
