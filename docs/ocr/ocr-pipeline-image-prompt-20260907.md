# OCR 파이프라인 이미지 제작 기록

- 사용자 요청: 파이프라인을 이미지로 정리하고 각 단계를 숫자로 표기.
- 생성 방식: 내장 이미지 생성 도구.
- 기준 소스: `service.py`, `pipeline/analyze.py`, `pipeline/preprocess.py` 및 직전 최적화 결과.
- 확인 기준: 01~09 순서, 품질 부족 시 재촬영, 조건부 LLM 및 건너뛰기, 05 최적화 표시, 한글 가독성과 화살표 연결.
- 저장본: `assets/ocr-pipeline-numbered-20260907.png` — 실제 출력 1024×1536 PNG, 1,307,881바이트.
- 검증: 번호 9개, 주요 한글, 재촬영/LLM 분기와 연결을 시각적으로 확인. PNG 디코딩·무결성 검사 통과. 07은 조건부 처리를 명확히 보이기 위해 옆 분기로 배치되었다.

## 생성 프롬프트

Use case: infographic-diagram.
Asset type: one finished Korean infographic explaining an existing medication-guide OCR software pipeline.
Create a polished, highly legible, portrait 3:4 infographic, ideally 1536 x 2048, with a white background, crisp modern Korean sans-serif typography, dark charcoal text, subtle mint and blue accents, thin connectors and simple small line icons. This is a technical flowchart, not a photograph or marketing poster. No decorative illustrations, logos, watermark, people, actual prescriptions, patient information, or performance statistics.

Title, verbatim: "복약안내문 OCR 파이프라인"
Subtitle, verbatim: "입력부터 사용자 확인까지 · 현재 구현 기준"

Composition: nine vertically stacked horizontal cards in one single top-to-bottom sequence with clear downward arrows. Every card has a prominent circular step number on the left, numbered 01 through 09 exactly once in ascending order. Use generous whitespace and large readable Korean text. Give the center/main cards about 75% of the width, reserving a narrow side margin for the two important branch annotations. Do not use a snaking grid. Each card contains only its supplied title and compact description. Numbers are the primary navigational device.

Exact card content:
01 — "이미지 접수"
description: "사진 업로드 · 파일 검증 · 작업 큐"

02 — "이미지 전처리"
description on two lines: "방향·문서 영역 보정" / "조건부 색상·선명도 보정"

03 — "품질 확인"
description: "흐림·잘림·문서 경계 검사"

04 — "CLOVA General OCR"
description: "텍스트 · 위치 좌표 · 신뢰도 추출"

05 — "레이아웃·약품행 분석"
description: "헤더·행 묶기 · 기울어진 행 복구"

06 — "근거 기반 후보 구성"
description: "약품명·함량·1회량·횟수·일수"

07 — "조건부 LLM"
description: "모호한 후보만 근거에서 선택"

08 — "검증·결과 저장"
description: "원문 근거·값 검증 · OCR 결과 저장"

09 — "사용자 검토·확정"
description: "인식 결과 확인·수정 후 최종 등록"

Semantically essential branches:
- Beside card03, a small coral outlined callout reading exactly "품질 부족" and "재촬영 요청". A clear arrow from03 to that callout and a return connector toward01. The main successful route proceeds03 to04. Do not connect recapture to OCR.
- Card07 is optional and tinted pale amber. Label the connector06 to07 exactly "모호한 경우". Also draw a clean dashed bypass arrow from06 around07 directly into08, labeled exactly "확실하면 건너뜀". Card07 still connects to08. This conveys conditional LLM use, not LLM on every request.
- Highlight card05 with a pale mint background and a small badge exactly "이번 최적화". Do not highlight other cards as optimized.

Small footer, verbatim: "원문 근거가 없는 값은 만들지 않고, 최종 확인은 사용자가 합니다."

Accuracy constraints: preserve all nine numbers and all exact Korean headings; no missing or duplicated steps; no invented stage; text must not overlap connectors; all arrows must have unambiguous endpoints; do not imply automatic patient-data masking; do not imply automatic medication approval. Make it elegant, practical and immediately understandable.

