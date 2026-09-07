# 현재 OCR 파이프라인 엄격 검증 — 2026-09-07

> 후속 수정: 사용자 요청에 따라 아래 **2번 저장 실패**와 마이그레이션 검증 오류를 수정했다. [수정·검증 결과](ocr-publication-recovery-20260907.md)를 참고한다. 1번·3번은 미수정이며, 아래 내용은 수정 전 감사 기록이다.

## 판정

**엄격 통과 보류. 현재 활성 legacy 경로에서 수정이 필요한 결함 3건을 재현했다.**

대상은 `906/AH_05_05` 로컬 복사본의 현재 파일 전체이며, Git HEAD와의 변경분만 검토한 결과가 아니다. 입력·전처리·OCR·후처리·LLM·검증·작업 저장·공개 API를 대상으로 테스트 및 읽기 전용 독립 검토를 수행했다. 구현 파일·설정·운영 DB는 수정하지 않았고 서비스도 재시작하지 않았다. 이 보고서만 추가했다.

## 확정 결함

### 1. P1 — 잘린 약명을 높은 신뢰도로 인정한다

- 위치: `app/services/medication_ocr_v3/pipeline/medication_rows.py:1581-1591`, `pipeline/review_projection.py:137-152,215-245`.
- 원인: 원문의 명시적 절단 표시를 `...`로 보존하지만, 약명 완전성 검사와 신뢰도 계산은 이를 불완전한 근거로 처리하지 않는다.
- 합성 표를 실제 `analyze_processed_image()`에 넣어 확인했다. 외부 OCR 호출 대신 개인정보 없는 OCR 블록만 제공했으며 이후 단계는 실제 코드다.
- 입력 약명 `감마정100밀리그램...`에 명확한 용량·횟수·일수가 있으면, 출력은 해당 잘린 이름과 `100mg / 1 / 2 / 5`, `confidence: high`, `lowConfidenceCount: 0`, `issues: []`다. LLM도 `DETERMINISTIC_SUFFICIENT`로 생략된다.
- 공개 확정 요청 DTO도 이 약명을 그대로 수용한다. 실제 DB 저장은 실행하지 않았다. 프론트는 high 신뢰도 경고를 생략한다(`frontend/src/pages/ocr-review/OcrReviewPage.tsx:84`).
- 영향: 약물 식별자가 불완전한데도 사용자에게 별도 확인 필요 표시가 사라진다. 원문 그대로 표시하는 것과 완전한 약명으로 인정하는 것은 구분해야 한다.
- 권장 수정: 절단 상태를 검증 이슈로 유지하고 최소한 낮은 신뢰도로 표시한다. 다른 근거가 없으면 완전한 이름을 추측하지 않는다.

### 2. P1 — 마지막 DB 저장 실패가 작업을 PROCESSING에 남긴다

- 위치: `app/services/medication_guide_ocr_jobs.py:465-506`.
- 원인: 분석 중 오류는 처리하지만, 최종 `job.save()`는 해당 `try/except` 밖에 있다. 이 저장에 실패하면 작업 상태 갱신과 실패 처리가 모두 누락된다.
- 실제 `process()`에 메모리 ORM·storage 대역을 연결하고 최종 저장에서 `OperationalError`를 주입했다. 결과: `escaped OperationalError`, `persisted_status PROCESSING`, `processed_files_saved 1`.
- 설치된 ARQ 0.28.0의 `worker.py:610-635`도 확인했다. 일반 DB 예외는 실패 종료이며 자동 재시도하지 않는다. `max_tries=2`만으로 이 오류가 재시도된다고 해석하면 안 된다.
- 영향: 분석은 끝났어도 공개 상태가 계속 처리 중으로 보이며, 기본 60분 stale 기준 이후 정리 주기에 삭제될 수 있다. 저장되지 않은 처리 이미지 참조는 orphan 정리 대상이 된다.
- 권장 수정: 최종 결과 게시에 한정한 재시도·복구 경로와 상태 조정을 마련한다. 분석 공급자를 다시 호출하는 것과 DB 결과 저장을 재시도하는 것은 구분한다.

### 3. P2 — 4자리 미래 조제일의 검증 규칙이 저장 API와 다르다

- 위치: `app/services/medication_ocr_v3/pipeline/grounding.py:208-226`, `app/dtos/medication_guide_ocr.py:304-307`.
- 원인: OCR의 오늘+31일 상한은 2자리 연도에만 적용된다. 공개 확정 DTO는 모든 날짜에 같은 상한을 적용한다.
- 실제 분석 경로에 `조제일 / 2099.01.01`을 넣으면 `2099-01-01`, `confidence: high`, `issues: []`, `lowConfidenceCount: 0`으로 나온다. 반면 같은 날짜의 확정 DTO는 `value_error`로 거부한다.
- 영향: 높은 신뢰도로 제시한 값을 사용자가 그대로 저장하면 실패한다. 잘못된 미래 날짜가 DB에 저장된다는 뜻은 아니다.
- 권장 수정: 출력 검증과 확정 검증의 날짜 허용 정책을 일치시킨다.

## 직접 실행한 검증

| 검사 | 이번 결과 |
|---|---|
| OCR·OCR v3·job/API·worker·compose 테스트 | 496 passed, 22.78초 |
| 추가 OCR 설정·마이그레이션 테스트 | 8 passed, 2 failed, 4.93초 |
| 합계 — 서로 겹치지 않는 위 두 실행 | **504 passed, 2 failed** |
| `ruff check app tests` | 통과 |
| OCR 관련 31개 파일 scoped mypy | **10개 파일에서 67개 오류** |
| 잘린 약명·미래 날짜 합성 end-to-end 재현 | 위 1·3번 결함 확인 |
| 메모리 대역 기반 최종 DB 저장 실패 | 위 2번 결함 확인 |

실행 명령:

```powershell
.venv/Scripts/python.exe -m pytest tests/ocr tests/ocr_v3 app/tests/ocr_apis app/tests/workers/test_medication_guide_ocr_worker.py app/tests/test_medication_guide_ocr_worker_compose.py -q --tb=short
.venv/Scripts/python.exe -m pytest app/tests/test_ocr_config.py tests/models/test_ocr_v3_storage_migration.py tests/models/test_async_ocr_migration.py -q --tb=short
.venv/Scripts/ruff.exe check app tests
.venv/Scripts/python.exe -m mypy --follow-imports=silent app/services/medication_ocr_v3 app/services/medication_guide_ocr_jobs.py app/services/ocr_image_input.py app/dtos/medication_guide_ocr.py app/apis/v1/medication_guide_ocr_router.py app/workers/medication_guide_ocr_worker.py
```

실패한 테스트는 `tests/models/test_ocr_v3_storage_migration.py:35`와 `tests/models/test_async_ocr_migration.py:32`다. 각각 과거 21번·7번 마이그레이션의 전체 모델 스냅샷을 현재 전체 모델과 비교한다. 21번의 `OcrJob` 모델 자체는 현재와 일치하지만 `CareEpisode.alias/hospital_name`, 새 모델·관계 등은 다르다. 이를 현재 OCR 추출 오류 또는 이번 변경의 회귀라고 단정하지 않는다. 테스트의 비교 대상을 정리할 필요는 있다.

Mypy 오류에는 Pydantic MISSING sentinel·ORM 타입, NumPy/OpenCV 배열 타입, 서로 다른 종류의 루프 변수 재사용, legacy/semantic 선택 union 등이 섞여 있다. **67개 실행 결함을 발견했다는 뜻이 아니며**, 정적 검사 전체 통과도 아니다.

## 운영 상태와 범위 제한

- 읽기 전용 확인 당시 fastapi·ocr-worker 컨테이너 실행 중, 활성 OCR DB 작업 0건, ARQ health 명령 성공. health 레코드 시각은 20:24:33이므로 20:50의 새 작업 처리 증거로 오해하지 않는다.
- 주요 4개 파일(job service, analyze, layout, OpenAI provider)의 로컬/컨테이너 SHA256 일치. 컨테이너 새 Python 프로세스에서 LLM 제한 10초 확인. 이는 컨테이너 파일 및 새 import 확인이며 기존 worker 객체 메모리 직접 검사와는 다르다.
- 현재 worker의 기본 모드는 legacy다. 보존된 semantic 경로를 현재 활성 동작으로 보고하지 않았다.
- 소유권 검사·이미지 no-store·LLM 증거 ID/행 소속 검증 등은 검토·테스트 범위에서 통과했다. 확정 이미지 보존은 API 사양에 명시되어 있어 결함으로 분류하지 않았다.
- CLOVA에는 OCR용 이미지가, LLM에는 필터링된 텍스트 증거가 전달되는 서로 다른 경계가 있다. 이미지 전송 자체를 무단 개인정보 유출로 단정하지 않았다.
- LLM 실패가 내부 stage에는 남고 공개 응답에는 직접 노출되지 않는 관찰성 한계, CLOVA URL 환경설정의 HTTPS/호스트 검증은 별도 개선 검토 항목이다. 이번 확정 결함 3건에 포함하지 않았다.
- 새로운 실제 문서 정답셋, 외부 CLOVA/OpenAI 실호출, 브라우저 전체 흐름, 고부하·프로세스 강제 종료·실DB 장애 주입은 이번에 실행하지 않았다. 기존 개발 표본의 정확도를 현재 신규 문서의 정확도 보장으로 재사용하지 않는다.

## 변경 및 후속 순서

보고서 외 코드 변경 없음. 기존 미커밋 변경을 보존했다. 커밋·push·Git 폴더 반영 없음.

수정 요청 시 우선순위는 약명 절단 경고 → 최종 저장 실패 복구 → 날짜 정책 일치다. 각각 이번 재현을 회귀 테스트로 고정한 뒤 실제 문서 검증과 장애 경로 검증을 수행하는 것이 다음 단계다.

