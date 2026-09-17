# 단일 사진 OCR 입력 정규화

2026-09-17. 사용자가 지정한 `git/AH_05_05`에 적용했다. 커밋, push, 운영 배포는 하지 않았다.

## 동작과 경계

후속 보완: MPO 대표 프레임 처리와 조건부 표 재시도가 추가됐다. 최신 수용 기준은 [OCR 사진 입력 요구사항](input-requirements.md), 외부 계약은 [API 명세](../medication-guide-ocr-api-spec-v1.md)를 따른다. 아래 검증 기록은 최초 정규화 작업 당시의 범위다.

- 단일 HEIC/HEIF, WebP, BMP, TIFF를 서버에서 JPEG로 변환한다. 알파 채널이 있으면 PNG를 사용한다.
- 정상 JPEG/PNG는 재압축하지 않는다. 회전·해상도·색상 모드 보정이 필요한 경우에만 다시 인코딩하며 PNG는 PNG로 유지한다.
- GIF는 정지/애니메이션 모두 거절한다. 다중 이미지 HEIF, 다중 페이지 TIFF, 애니메이션 WebP/APNG도 첫 장만 사용하지 않고 거절한다. HEIF 썸네일·깊이·보조 데이터는 최상위 사진 목록과 구분한다.
- 확장자/MIME은 참고값이며 실제 디코딩 결과가 기준이다. 저장되는 결과 바이트, MIME, provider format, 파일명은 서로 일치한다. 작업 manifest의 일반화된 파일명(`ocr-input.jpg/png`)은 기존 정책대로 유지한다.
- 변환할 때 EXIF 회전과 ICC 색상 프로필을 반영한다. HEIF 컨테이너 회전은 디코더에서 처리하므로 EXIF 방향을 이중 적용하지 않는다. 변환 결과에는 원본 EXIF/GPS/XMP를 복사하지 않는다. 그대로 통과하는 JPEG/PNG의 메타데이터는 기존 동작대로 보존한다.
- 원본과 결과 각각 50MiB 이하. 원본 상한은 64MP 및 한 변 16,000px이며, 범위 안의 고해상도 사진은 기존 OCR 입력 제한인 40MP 및 한 변 10,000px 이내로 비율을 유지해 축소한다.
- 디코딩은 이벤트 루프 밖에서 프로세스당 최대 2개로 제한한다. 네이티브 코덱을 별도 프로세스에서 강제 종료하는 구조는 추가하지 않았다. 기존 API 처리 제한 시간은 유지한다.

## 최신 Git 코드와 연결

이미지 정규화는 `validate_image` 안에서 끝나므로 Redis 메모리 전용 임시 저장, TTL, 삭제 확인, General OCR 흐름은 유지된다. 새 디스크 사진 저장소를 만들지 않는다.

기존 가이드 카메라와 메모리 전용 미리보기 세션을 보존했다. 브라우저가 지원하지 않는 사진도 선택·등록 가능하며, 검토용 원본은 필요할 때 `/api/v1/ocr/jobs/{id}/image`에서 인증을 거쳐 정규화된 이미지를 받는다. 원본·전처리본 모두 확보한 뒤 서버 삭제 확인을 전송한다. 실패하거나 화면을 떠나면 blob URL을 해제하고, history에는 사진 대신 세션 ID만 둔다. 새로고침·직접 진입 시 사진을 다시 가져오지 않는 정책을 유지한다.

## 주요 파일

- `app/services/ocr_image_input.py`: 입력 정규화와 제한.
- `app/core/exceptions.py`: 지원 형식/다중 이미지/크기/변환 실패 오류.
- `app/apis/v1/medication_guide_ocr_router.py`: 업로드 OpenAPI 설명 갱신.
- `pyproject.toml`, `uv.lock`: app 그룹의 pillow-heif 1.7.0 잠금. 기존 패키지 버전 변경 없이 uv가 중복 플랫폼 마커를 정리했다.
- `frontend/src/pages/document-upload/DocumentUploadPage.tsx`: 선택 형식, GIF 거절, 미리보기 대체 안내.
- `frontend/src/entities/document/api.ts`: 정규화된 원본 미리보기와 URL 정리.
- `tests/ocr/test_image_normalization.py`: 28개 검증. HEIF 회전·48MP·다중 프레임·Redis TTL/삭제·General OCR 전송·실제 메모리 업로드 파서 포함.
- `frontend/tests/e2e/image-normalization.spec.ts`, `frontend/tests/e2e/medication-registration-flow.spec.ts`: 새 형식과 기존 선택 계약 검증.
- `frontend/tests/e2e/camera-guide.spec.ts`: 기본 카메라 선택기의 확장된 accept 기대값만 갱신.

## 서버 검증

- `tests/ocr`: 151 passed.
- `tests/ocr_v3/test_preprocess_safety_v34.py`: 57 passed.
- 이미지 정규화 모듈 mypy, 변경 Python Ruff 검사와 포맷 검사, `uv lock --check` 통과.

## 화면 및 최종 검증

- `VITE_USE_MOCK=false`, 전용 포트 44183에서 새 정규화 테스트·가이드 카메라·관련 OCR 등록/메모리 수명 테스트: 29 passed (19.2s).
- `pnpm build`: TypeScript 및 Vite 빌드 통과. 큰 번들 경고는 남아 있다.
- 375px 모바일 및 1280px 데스크톱의 HEIC 미리보기 대체 화면을 캡처해 육안으로 확인했다. 최종 결과는 `frontend/test-results-image-normalization-git-final/`에 있다.
- 독립 검토에서 차단할 결함은 발견되지 않았다. 정상 JPEG/PNG의 바이트·EXIF 보존은 합의된 기존 동작이며 변환 결과의 메타데이터 제거와 구분했다.
- 첫 브라우저 통합 실행은 재사용한 개발 서버가 종료되며 연결 오류가 발생했다. 별도 포트의 전용 서버로 같은 29개를 재실행해 모두 통과했다. 최신 테스트의 기본 카메라 accept 기대값도 새 계약에 맞췄다.
- 기존 AI 작업 파일 등 범위 밖 변경은 수정하거나 스테이징하지 않았다. 이번 변경 역시 미커밋 상태로 남겼다.

## 운영 확인 범위

프로젝트 Windows 가상환경에 pillow-heif 1.7.0을 설치하고 실제 코덱으로 합성 HEIF를 인코딩/디코딩했다. 다른 실행 환경은 `uv sync --frozen --group app` 등 기존 설치 절차로 새 의존성을 설치하고 API/워커 이미지를 재빌드해야 한다.

실제 실패한 아이폰 원본이 제공되지 않아 해당 사진의 재현 여부와 실제 iOS 파일 선택은 미확인이다. 실제 CLOVA 호출 대신 MockTransport로 전송 계약을 검증했다. Linux 컨테이너 빌드·운영 배포는 실행하지 않았다. 실제 반영 후에는 식별정보 없는 아이폰 사진 한 장으로 업로드부터 OCR 결과까지 확인해야 한다.
