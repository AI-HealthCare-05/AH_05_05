# Public Guideline Data

퇴원 환자 회복 가이드 RAG 검색에 사용하는 공공 가이드라인 자료입니다.

## 데이터 사용 목적

- 퇴원 후 복약 및 생활관리 추가 설명 검색
- 환자 확정 정보보다 낮은 우선순위로 사용
- 원문 Chunk와 출처 메타데이터를 Qdrant에 저장

## 문서 목록

| 문서 ID | 자료명 | 발행기관 | 연도 | 질환 | 주제 |
| --- | --- | --- | --- | --- | --- |
| canadian-stroke-2020 | Canadian Stroke Best Practice Recommendations | Heart and Stroke Foundation of Canada | 2020 | STROKE | LIFESTYLE |

## 인덱싱 설정

- 임베딩 모델: text-embedding-3-small
- 임베딩 차원: 1536
- Chunk 크기: 1000
- Chunk 중첩: 200
- 거리 방식: COSINE
- Collection: public_guidelines_small_v1

## 주의사항

- 환자 확정 정보와 충돌하면 환자 정보를 우선합니다.
- PDF의 원본 URL과 라이선스는 manifest.json에서 관리합니다.
- Qdrant 인덱스 자체는 Git에 저장하지 않고 원본 PDF에서 재생성합니다.
