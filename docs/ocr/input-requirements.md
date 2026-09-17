# OCR 사진 입력 요구사항

현재 구현 기준. 기존 요구사항정의서에 반영할 OCR 입력·인식 보완 항목이며 아래 ID는 이 문서 내 식별자다.

| ID | 요구사항 | 수용 기준 |
|---|---|---|
| OCR-IN-01 | 사용자는 지원되는 단일 사진을 등록할 수 있다. | JPEG, PNG, HEIC/HEIF, WebP, BMP, 단일 TIFF를 처리한다. 확장자/MIME만으로 판정하지 않는다. |
| OCR-IN-02 | MPO 카메라 사진은 대표 사진만 인식한다. | 첫 프레임만 재인코딩하고 보조 프레임·MPF 메타데이터는 OCR 입력에서 제외한다. 다른 다중 이미지와 GIF는 거절한다. |
| OCR-IN-03 | 지원 사진을 자동 정규화한다. | 필요한 경우 방향·색상 모드를 보정하고 JPEG/PNG로 변환한다. 정상 JPEG/PNG는 불필요하게 재압축하지 않는다. 변환 시 메타데이터를 복사하지 않지만 그대로 통과하는 JPEG/PNG의 메타데이터 제거까지 보장하지 않는다. |
| OCR-IN-04 | 과도한 용량·해상도는 제한한다. | 파일 50 MiB, multipart 51 MiB, 원본 64MP·한 변 16,000px 이하. 결과는 40MP·10,000px 및 50 MiB 이하이며 필요 시 비율 유지 축소한다. |
| OCR-IN-05 | 검토 화면에서 전처리 전·후 사진을 확인할 수 있다. | 전처리 전 사진도 정규화된 JPEG/PNG일 수 있다. 서버는 기존 Redis 메모리 임시 보관·TTL·삭제 확인 정책을 유지하며 영구 디스크 사진 저장소를 추가하지 않는다. |
| OCR-IN-06 | 선명화로 인한 표 인식 실패에 제한적으로 재시도한다. | v3.4.1에서 선명화가 적용됐고 TABLE_NOT_FOUND 또는 AMBIGUOUS_MEDICATION_TABLE로 실패한 경우 v3.4.2로 최대 1회 재시도한다. 안전하지 않은 대체 영상은 사용하지 않으며 이름·용량 충돌 검증을 우회하지 않는다. |
| OCR-IN-07 | 약명에 혼입된 명시적 보관 문구를 정리한다. | 실온/냉장/차광 보관 문구 뒤에 별표와 한글 약명이 있는 경우에 한정한다. 특정 제품명이나 정답 목록을 하드코딩하지 않는다. |
| OCR-IN-08 | 실패 원인을 구분해 안내한다. | 지원 형식, 다중 이미지, 크기, 변환 실패, 손상 이미지 오류를 API 코드로 구분한다. 모든 사진의 인식 성공이나 고정 처리 시간을 보장하지 않는다. |

## 계약 및 검증 근거

- [API 명세](../medication-guide-ocr-api-spec-v1.md): 기존 POST/GET/PATCH와 응답 구조를 유지한다. 재시도는 worker 내부 처리로 새 API를 추가하지 않는다.
- 입력 정규화: `app/services/ocr_image_input.py`, `tests/ocr/test_image_normalization.py`
- 재시도와 약명 정리: `app/services/medication_ocr_v3/service.py`, `app/services/medication_ocr_v3/pipeline/medication_rows.py`, `tests/ocr_v3/test_service.py`, `tests/ocr_v3/test_internal_pipeline.py`
- 진단 사진과 스크립트는 배포 기능이 아니며 `.context`는 Git에서 제외한다. 과거 이력 삭제는 별도 작업이다.
