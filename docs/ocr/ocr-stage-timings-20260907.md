# OCR 단계 계측과 6단계 저장 호환성

작업 위치: `906/AH_05_05` 로컬 복사본. 커밋·push·별도 Git 폴더 반영 없음.

## 인식 실패 원인과 수정

`resolve` 추가 도중 파이프라인은 6단계를 반환하지만 작업 저장 검증은 기존 5단계만 허용하는 불일치가 있었다. 실제 `test.jpg`에서 약품 7개가 추출된 뒤 `OCR stages must contain the five ordered v3 stages` 오류로 저장 검증에 실패하는 것을 재현했다. 최근 실제 작업에도 `VALIDATION_FAILED`가 확인됐다.

저장 검증은 새 6단계와 기존 5단계의 정확한 순서를 모두 허용한다. 기존 기록에 측정하지 않은 resolve 값을 만들어 넣지 않으며, 중복·알 수 없는 단계나 잘못된 자료형은 계속 거부한다. 새 실패 fallback도 6단계다.

실제 같은 이미지의 CLOVA OCR → LLM → 결과 저장 검증을 다시 실행해 7개 약품 및 저장 검증 성공을 확인했다. 처리 대기/진행 작업이 모두 0건인 것을 확인하고 로컬 OCR 워커를 재시작했으며, 실행 컨테이너에서 6단계 허용을 확인했다. 기존 실패 작업을 변경하거나 자동 재실행하지 않았다.

## 계측 계약

순서: `preprocess → ocr → candidate → resolve → llm → validate`.

- `preprocess`: 기존 전처리와 OCR 전송 이미지 준비를 모두 포함한다.
- `candidate`: 레이아웃·병원명·약품 행·근거 후보 구성.
- `resolve`: 규칙 기반 확정 계획과 LLM 호출 필요 여부 판단.
- `llm`: 외부 LLM 호출. 규칙으로 충분하면 `code: DETERMINISTIC_SUFFICIENT`와 함께 생략한다.
- `validate`: 값 검증뿐 아니라 최종 review·진단 정보 구성까지 포함한다.
- `elapsedMs`는 기존 정수 ms 규약을 유지한다. `succeeded`의 0ms는 반올림 결과일 수 있다.

작업 단위 수치는 JSON `stage_results.timings`에 저장하고 상태 API의 `timings`로 노출한다. `stage_results`는 `{"timings": ..., "stages": [...]}` 구조이며 기존 단계별 기록과 `elapsedMs`는 `stages`에 그대로 보존한다. 처음에는 `input_manifest.timings`에 저장했으나, 후속 33번 데이터 마이그레이션(원본 로컬 복사본에서는 32번)에서 기존 값을 이전하도록 변경했다. DB 열과 JSON 타입은 유지한다. 상세: [저장 구조 이전](ocr-stage-results-envelope-20260907.md).

- `queueWaitMs`: 작업 생성부터 최초 워커 시작까지. 업로드 자체의 시간은 포함하지 않는다.
- `persistMs`: 마지막 시도의 처리 이미지 저장과 결과 DB 저장에 걸린 시간. 실패 시 실패 상태 저장·파일 정리도 포함한다.
- `totalMs`: 작업 생성부터 마지막 시도의 결과 저장/실패 처리가 돌아올 때까지 직접 측정한다. 큐 대기와 재시도 대기도 포함하며 단계 합계로 만들지 않는다. 과거 생성 시각과 현재 시도 시작의 차이에, 현재 시도의 단조 시계 경과 시간을 더한다.

계측 메타데이터 자체의 읽기/쓰기 시간은 제외한다. 메타데이터는 결과 저장 뒤 별도 갱신되므로 아주 짧게 결과만 먼저 보일 수 있다. 메타데이터 저장 실패는 OCR 성공을 실패로 바꾸지 않고 경고를 남긴다. 이전 기록이나 아직 처리 중인 작업에는 측정값을 추정해 채우지 않는다. 단계·persist 시간은 마지막 시도 기준이며 total에는 이전 시도와 재시도 대기가 포함된다.

## 검증

- OCR 전체·작업 서비스·worker·compose·기존 OCR API 통합 실행: **432 passed in 20.03s**.
- `ruff check app tests` 통과, 수정 파일 `git diff --check` 통과.
- 작업 서비스/DTO의 mypy는 변경 전 스냅샷과 변경 후 모두 기존 오류 27개가 남아 있다. 전체 타입 검사 통과로 표현하지 않는다.
- 지연을 통제한 실제 DB 테스트에서 처리 이미지 저장 200ms + DB 저장 300ms가 `persistMs: 500`으로 기록됨을 확인했다. 새 6단계 저장, 기존 5단계 호환, 재시도·재호출 보호도 검증했다.

주요 파일: `app/services/medication_ocr_v3/{pipeline/analyze.py,service.py}`, `app/services/medication_guide_ocr_jobs.py`, `app/dtos/medication_guide_ocr.py`와 관련 OCR 서비스 테스트.

독립 검토에서 실제 HTTP DTO 변환이 timings를 누락하는 문제와 즉시 확정 시 COMPLETE 전환으로 계측 저장이 빠질 수 있는 문제를 확인했다. 각각 HTTP 3개 상태 테스트와 두 시점의 상태 변경 테스트에서 실패를 재현한 후 수정했다. 결과/실패 공개 DTO가 숫자 3개를 전달하고, 계측 저장은 COMPLETE도 허용한다. 재처리 요청 자체는 이미 완료된 작업의 기존 계측값을 덮어쓰지 않는다.

품질 범위: 기존 미커밋 변경이 겹쳐 전체 파일 단순화는 하지 않았다. Code review: targeted manual due to unrelated branch work. 별도 독립 읽기 전용 검토의 발견 사항을 재현·수정하고 통합 검증했다. ORM/DTO의 기존 mypy 오류는 이번 범위 밖으로 남겼다.
