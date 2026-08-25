# Raw data

다운로드한 원본 파일을 출처와 공개 범위에 따라 보관합니다. 실제 파일은 Git과 Docker 이미지에서 제외됩니다.

```text
raw/
├── public/
│   ├── mfds/
│   │   ├── drug_records/
│   │   ├── drug_food_interactions/
│   │   ├── supplement_products/
│   │   ├── supplement_guides/
│   │   └── supplement_code/
│   └── food_safety_korea/
│       └── supplement_ingredients/
└── demo_restricted/
    ├── kpicia/
    │   ├── drug_encyclopedia/
    │   ├── adverse_case_report/
    │   │   └── ocr/
    │   └── pharm_review/
    ├── research/
    │   └── supplement_interactions/
    └── unknown_source/
        └── supplement_interactions/
```

`ocr/`에는 PDF 텍스트 레이어가 없거나 추출에 실패한 원본이 들어갑니다.
