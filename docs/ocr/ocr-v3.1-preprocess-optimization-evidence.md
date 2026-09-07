# OCR v3.1 전처리 경량화 증빙

## 문서 상태

- 기록 시점: 2026-09-03 11:51 KST
- 단계: v3.1.0~v3.1.8 비교 매트릭스 완료, `v3.1.3` 운영 전환
- 작업 위치: 사용자가 지정한 `903/AH_05_05` 로컬 복사본
- 전처리 본체 상태: `v3.1.3`을 운영 기본값으로 사용하고 v3.1.0~v3.1.8 선택 프로필 유지
- 운영 전환 반영: 2026-09-04 KST
- 기준 코드: `fb7f9b6`

이 문서는 조제약 OCR v3의 전처리 품질을 유지하면서 처리 시간과 메모리 사용을 줄이는 v3.1 실험을 증명하기 위한 기록이다. 코드 변경 전 기준선과 채택한 `v3.1.1` 결과를 같은 측정 조건으로 비교한다. 후속 v3.1.0~v3.1.8 수동 비교용 변형과 결과는 [OCR 전처리 v3.1 변형 매트릭스](./ocr-v3.1-variant-matrix.md)에 분리해 기록했다.

한 장의 기준 사진에서 얻은 결과이므로 전체 문서 유형의 정확도나 일반 성능을 대표한다고 주장하지 않는다. 이번 단계에서는 OCR provider와 LLM을 호출하지 않았으며 전처리 결과만 평가했다.

## 버전 기준

| 구분 | 현재 값 | 비고 |
| --- | --- | --- |
| 최적화 기록 버전 | `ocr-preprocess-benchmark/v3.1` | 측정·증빙 형식 |
| 현재 최적화 리비전 | `preprocess/v3.1.3` | GrabCut 반복 수만 조정 |
| 제품 파이프라인 | `ocr-pipeline/v3` | 공개 계약 버전은 유지 |
| 공개 결과 스키마 | `medication-guide-review/v3` | 이번 전처리 작업에서 변경하지 않음 |
| 전처리 구현 | `opencv-deterministic/v3` | AI·딥러닝 모델 없음 |
| OpenCV runtime | `5.0.0` | `opencv-python-headless 5.0.0.93` |
| NumPy | `2.4.1` | 영상 배열 처리 |
| Pillow | `12.1.0` | decode, EXIF, sRGB, JPEG encode |
| Python | `3.13.14` | Windows 실행 환경 |
| OCR provider | `clova-general-v2` | 이번 기준선에서는 호출하지 않음 |
| 구조화 | `deterministic-v3` | 이번 기준선에서는 실행하지 않음 |
| LLM 프롬프트 | `medication_grounding_v3` | 이번 기준선에서는 실행하지 않음 |
| LLM 선택 스키마 | `medication_block_selection_v3` | 이번 기준선에서는 실행하지 않음 |

전처리에서 말하는 “모델”은 학습 모델이 아니라 OpenCV 규칙 기반 파이프라인이다. 따라서 모델 가중치, GPU와 추론 서버는 사용하지 않는다.

## 현재 전처리 기능

현재 `preprocess_image()`는 다음 순서로 실행된다.

1. JPEG·PNG 형식, 용량, 픽셀 수와 긴 변 제한을 확인한다.
2. EXIF 회전을 반영하고 ICC profile이 있으면 sRGB로 변환한다.
3. 축소 탐지 이미지에서 contour, Hough line과 필요 시 GrabCut으로 문서 사각형을 찾는다.
4. 탐지 사각형을 안전하게 확장하고 원근 보정 가능 여부를 검사한다.
5. 원근 보정 결과가 원본보다 나빠지면 rollback하고 crop·deskew 또는 full-frame 경로를 사용한다.
6. readability 지표를 계산하고 LAB 기반 illumination 보정을 적용한다.
7. 가장자리를 흰색으로 정리하고 quality state와 재촬영 사유를 판정한다.
8. provider용 JPEG와 원본 방향 미리보기 JPEG를 각각 생성한다.

기본 correction preset은 `illumination`, grayscale 비율은 `0`이다. JPEG는 quality 95, 4:4:4, optimize 옵션으로 인코딩한다.

## 기준 입력과 측정 조건

민감 문서의 파일명과 내용은 측정 JSON과 이 문서에 기록하지 않고 `REF-001`로만 식별한다. 원본은 저장소나 실험 산출물 폴더에 복사하지 않았다.

| 항목 | 값 |
| --- | ---: |
| 입력 형식 | JPEG |
| 입력 크기 | 2461 × 1846 px |
| 입력 파일 크기 | 1,377,479 bytes |
| 워밍업 | 2회 |
| 실측 | 8회 |
| 실행 방식 | 단일 프로세스, 직렬 |
| 외부 호출 | 0회 |
| 운영체제 | Windows 11 Education 10.0.26200 |
| CPU | AMD Ryzen 7 7800X3D, 16 logical processors |
| 시스템 메모리 | 33,453,109,248 bytes |

네트워크, CLOVA와 LLM 시간이 섞이지 않은 순수 `preprocess_image()` wall-clock만 측정했다. peak working set은 같은 Python 프로세스의 Windows peak working set이다.

## 기준선 결과

### 성능

| 지표 | 기준선 |
| --- | ---: |
| 전처리 p50 | 1,904.668 ms |
| 전처리 p95 | 1,983.629 ms |
| 전처리 최댓값 | 2,004.244 ms |
| peak working set | 280,174,592 bytes (약 267.20 MiB) |
| provider JPEG | 736,731 bytes |
| 원본 방향 미리보기 JPEG | 603,488 bytes |
| 출력 픽셀 | 1,998,048 px |

실측 원본값은 다음과 같다.

```text
1880.155, 1922.931, 1879.346, 1928.850,
2004.244, 1945.343, 1886.404, 1860.689 ms
```

### 처리 결과

| 항목 | 결과 |
| --- | --- |
| quality state | `PROCESSED` |
| 처리 mode | `PERSPECTIVE` |
| correction preset | `illumination` |
| 출력 크기 | 1601 × 1248 px |
| 원근 보정 | 적용 |
| rollback | 없음 |
| 판정 사유 | `perspective_rectified` |
| 탐지 문서 수 | 1 |
| 문서 coverage | 0.420133 |
| corner confidence | 0.817521 |
| 원래 기울기 | 13.655449° |
| blur variance | 960.602238 |
| edge density | 0.092870 |

적용 작업은 `EXIF 정규화 → 문서 사각형 안전 확장 → 원근 보정 → illumination 보정 → sRGB 유지 → 흰색 안전 테두리` 순서다.

### 육안 품질 판정

- 촬영 배경이 제거되고 약봉투의 좌우 영역이 한 화면에 정렬됐다.
- 상단 제목, 좌측 약품 행, 우측 영수증과 하단 약품 목록이 잘리지 않았다.
- 7개 약품 행과 투약량·횟수·일수 열이 육안으로 구분 가능하다.
- 조명 편차가 완화됐으며 큰 글자와 약품명은 선명하게 유지됐다.
- 우측 하단의 매우 작은 글자는 원본 해상도 한계가 남아 있지만 전처리 때문에 새로 뭉개지거나 사라진 흔적은 확인되지 않았다.

이 판정은 전처리 이미지의 가독성과 crop 손실 여부에 대한 육안 확인이다. 약품명과 각 필드의 OCR 정확도 평가는 전처리 최적화 후보가 확정된 뒤 baseline·candidate의 제한된 live 비교에서 별도로 수행한다.

## v3.1.1 — GrabCut 반복 축소

### 선택 근거

표준 `cProfile` 1회에서 `preprocess_image()` 약 1.89초 중 문서 검출이 약 1.49초였고, 그 안의 `cv2.grabCut`이 약 1.25초로 전체의 약 66%를 차지했다. Hough와 경계 점수 계산은 합쳐도 이보다 훨씬 작아 첫 후보는 가장 큰 병목 하나로 제한했다.

`app/services/medication_ocr_v3/pipeline/preprocess.py`에서 GrabCut refinement 반복을 `4 → 3`으로 변경했다. 해상도, 마스크 생성, 난수 seed, morphology, 후보 선택, 원근 보정, illumination과 JPEG 설정은 바꾸지 않았다.

### 동일 조건 재측정

| 지표 | 기준선 | v3.1.1 | 변화 |
| --- | ---: | ---: | ---: |
| 전처리 p50 | 1,904.668 ms | 1,744.462 ms | -160.206 ms (-8.41%) |
| 전처리 p95 | 1,983.629 ms | 1,772.354 ms | -211.275 ms (-10.65%) |
| 전처리 최댓값 | 2,004.244 ms | 1,777.944 ms | -226.300 ms (-11.29%) |
| peak working set | 280,174,592 bytes | 276,905,984 bytes | -3,268,608 bytes (-1.17%) |
| provider JPEG | 736,731 bytes | 736,731 bytes | 동일 |
| 미리보기 JPEG | 603,488 bytes | 603,488 bytes | 동일 |

v3.1.1 실측 원본값은 다음과 같다.

```text
1720.517, 1727.194, 1761.971, 1741.765,
1777.944, 1754.615, 1747.160, 1735.656 ms
```

측정 도구의 로컬 산출물 경로 필수화와 현재 코드 hash 기록 뒤 동일 프로토콜로 확인 측정을 한 번 더 수행했다. 확인 측정은 p50 `1,661.618 ms`, p95 `1,676.503 ms`, 최댓값 `1,677.605 ms`였고 고정 출력 계약은 다시 exact match였다. 최초 측정의 더 보수적인 p95 `1,772.354 ms`를 공식 비교값으로 유지한다.

### 품질 및 계약 비교

- provider JPEG와 미리보기 JPEG의 SHA-256이 기준선과 동일하다. 즉 공개되는 전처리 픽셀 결과는 바뀌지 않았다.
- `PROCESSED`, `PERSPECTIVE`, 1601×1248 px, 변환행렬, reasons, operations, perspective 적용과 rollback 상태가 모두 exact match다.
- 선택 문서 polygon, coverage, skew, blur, clipping, illumination과 edge density도 동일하다.
- 진단용 corner confidence만 `0.8175213088 → 0.8174722225`로 `0.0000490863` 감소했다. 분기 임계값, 선택 polygon, 품질 판정과 출력에는 영향을 주지 않았다.
- 별도 로컬 예시 14장을 익명으로 비교한 결과 14/14에서 provider·미리보기 JPEG, mode, quality state, 크기, 변환행렬, reasons, operations, perspective와 rollback 계약이 동일했고 오류는 0건이었다.
- 자동 판정 결과는 `keep`이며 p95 10% 감소 기준을 충족했고 provider payload와 메모리 상한을 위반하지 않았다.
- `tests/ocr_v3`와 `app/tests/ocr_apis`의 관련 테스트 60개가 통과했고 Ruff lint·format 검사와 `git diff --check`도 통과했다.

속도 수치는 `REF-001` 한 장의 측정 결과이며, 14장 보조 비교는 출력 계약 회귀 여부만 확인했다. OCR과 LLM을 호출하지 않았으므로 필드 정확도나 전체 사진군의 성능 개선으로 일반화하지 않는다.

## 고정된 품질 계약

동일 출력 최적화 후보는 아래 항목이 기준선과 정확히 같아야 한다.

- provider 및 공개 미리보기 JPEG bytes
- quality state와 preprocessing mode
- 출력 크기
- 원본→방향 보정 및 원본→전처리 변환행렬
- reasons와 operations
- 원근 보정 적용 여부와 rollback 사유

처음에는 출력 이미지를 바꾸지 않는 계산 공유·중복 제거만 허용한다. 출력 계약이 달라지는 후보는 이 실험에 포함하지 않고 별도 승인과 OCR 품질 검증을 거친다.

## 채택 기준

| 기준 | 통과 조건 |
| --- | --- |
| 속도 | 전처리 p95가 기준선보다 10% 이상 감소: `≤ 1,785.266 ms` |
| 출력 | 고정된 품질 계약 전체 exact match |
| provider payload | `≤ 736,731 bytes` |
| 메모리 | `≤ 296,951,808 bytes` |
| 재촬영 판정 | `PROCESSED` 유지 |
| 개인정보 | 측정값에 원본 파일명, OCR 원문과 환자 식별정보 없음 |

메모리 상한은 기준선의 5%와 16 MiB 중 큰 값인 16 MiB를 적용해 계산했다.

## 재현 방법

저장소 루트에서 PowerShell로 실행한다.

```powershell
$env:OCR_V31_REFERENCE_IMAGE = Read-Host "기준 이미지 절대 경로"
$env:OCR_V31_ARTIFACT_DIR = (Resolve-Path "..\ocr-v3.1-local\baseline").Path
uv run --project . --frozen python -m scripts.benchmark_ocr_preprocess_v31
```

후보 비교 시 baseline contract를 추가한다.

```powershell
$env:OCR_V31_ARTIFACT_DIR = (Resolve-Path "..\ocr-v3.1-local\v3.1.1").Path
$env:OCR_V31_BASELINE_CONTRACT = (Resolve-Path "..\ocr-v3.1-local\baseline\contract.json").Path
uv run --project . --frozen python -m scripts.benchmark_ocr_preprocess_v31
```

## 증빙 산출물

민감 문서가 포함된 이미지는 저장소 밖의 로컬 폴더에만 둔다.

| 산출물 | 역할 |
| --- | --- |
| `../../../ocr-v3.1-local/baseline/preprocessed.jpg` | 육안 비교용 전처리 결과 |
| `../../../ocr-v3.1-local/baseline/metrics.json` | 익명 원본 측정값 |
| `../../../ocr-v3.1-local/baseline/contract.json` | 이후 후보와 비교할 출력 계약 |
| `../../../ocr-v3.1-local/baseline/run-metadata.json` | 실행 환경과 코드 identity |
| `../../../ocr-v3.1-local/v3.1.1/preprocessed.jpg` | v3.1.1 육안 확인용 전처리 결과 |
| `../../../ocr-v3.1-local/v3.1.1/metrics.json` | v3.1.1 익명 원본 측정값 |
| `../../../ocr-v3.1-local/v3.1.1-confirmation/metrics.json` | 현재 코드 hash로 재실행한 확인 측정값 |
| `../../../ocr-v3.1-local/v3.1.1-confirmation/run-metadata.json` | 코드·harness·test·산출물 hash |
| `.context/compound-engineering/ce-optimize/ocr-v31-preprocess/v3.1.1/result.yaml` | v3.1.1 결과 및 코드 hash |
| `.context/compound-engineering/ce-optimize/ocr-v31-preprocess/experiment-log.yaml` | 기준선과 실험 이력의 단일 원본 |

전처리 결과 이미지 자체에는 문서 내용이 남아 있으므로 외부 공유·커밋·push 대상이 아니다.

## 변경 범위

기준선 단계에서는 제품 전처리 본체를 수정하지 않았다. `v3.1.1`에서는 전처리 본체의 GrabCut 반복 인자 한 줄만 변경했고 OCR, 후보 추출, LLM, 검증, API, DB, 프론트와 AI worker는 수정하지 않았다. 측정 도구는 전처리 이미지가 저장소 내부 기본 경로로 기록되지 않도록 `OCR_V31_ARTIFACT_DIR`를 필수화했다.

후속 실험에서는 `v3.1.2`~`v3.1.8` 번호를 GrabCut 반복 수·작업 해상도·실행 임계값 비교에 사용했다. Hough edge-support lookup 최적화는 이번 매트릭스에 포함하지 않았으며 별도 후보로 보류한다. 운영 기본값은 출력 계약과 익명 보조 56장 비교를 모두 통과한 `v3.1.1`로 유지한다.

