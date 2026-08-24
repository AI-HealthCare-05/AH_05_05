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

`OCR_REQUIRED`, `STRUCTURED_SOURCE`, `QDRANT_DISABLED_UNTIL_VERIFIED` 문서는 건너뜁니다. 실행 결과는 Git에서 제외된 `processed/text/*.jsonl`과 `processed/chunks/*.jsonl`에 생성됩니다. 같은 문서를 다시 실행하면 동일한 청크 ID를 만들며, 인덱싱 대상에서 제외된 문서의 이전 산출물은 제거합니다.

## 응답 안전 원칙

- 보유한 환자 확정정보와 검색된 근거 범위 안에서만 답한다.
- 진단, 처방, 복용 시작·중단·증량·감량을 결정하지 않는다.
- 답변은 참고정보이며 의료진의 진료를 대체하지 않는다는 안내를 포함한다.
