# feature/252 PR 검증 기록

2026-09-05 · 작업지시 F · 대상 main · 구현 기준 d238b6a

## 판정

**병합 보류: 마이그레이션 29 downgrade → upgrade 실패.** 검증 및 리뷰를 위한 Draft PR이다. 이번 작업에서 앱 기능과 마이그레이션은 수정하지 않았다.

격리 MySQL 스키마에서 30→27 downgrade와 27→28 upgrade는 성공했다. 29 upgrade는 `uid_medication__user_dose_slot` 인덱스가 없어 MySQL 1091로 실패했다. 29 downgrade가 옛 유니크 인덱스를 복원하지 않는 것이 원인이다. MySQL DDL의 암시적 커밋 때문에 실패 전 `care_episode_id` 추가는 남는다. 30 재적용에는 도달하지 못했다. 실제 개발 DB를 되돌린 결과가 아니다.

- [격리 재현 결과](migration-roundtrip.md)
- [개발 DB 적용 상태와 SHOW CREATE TABLE 4개](database-schema.md)
- [375/390px 스크린샷 20장](screenshots/README.md)

## 실행 환경과 검증 범위

- 의존성 설치 없이 기존 WSL Node 22 / Linux 네이티브 의존성으로 Vite와 타입 검사·빌드 실행.
- WSL에는 Chrome이 없어 기존 Windows Chrome으로 Playwright 실행. 각각 44411(e2e-mock), 44412(e2e-real) 서버 재사용.
- `e2e-real`은 프론트 실 API 어댑터 모드이다. 다수 테스트는 HTTP 응답을 가로채는 계약 테스트이며, 실제 사용자·서버·DB를 끝까지 연결한 수동 인수 테스트 완료를 뜻하지 않는다.
- FastAPI 컨테이너 전체 pytest는 AI 테스트의 pypdf 누락으로 수집 실패했다. 설치하지 않고 기존 WSL 가상환경에서 전체 서버 테스트를 재실행했다.
- 스크린샷은 명시적인 가상 데이터다. 실사용자 기록이나 실제 서버 저장 증거로 사용하지 않는다.

## 검증 결과

- 타입 검사: `node node_modules/typescript/bin/tsc --noEmit` 통과.
- 프로덕션 번들: `node node_modules/vite/bin/vite.js build` 통과. 711.83kB JS 청크 경고는 남아 있다(이번 범위에서 분할하지 않음).
- 목업 전체 E2E: **234 passed / 0 failed / 133 skipped** (367개, 8.8분).
- 실 API 모드 전체 E2E: **142 passed / 11 failed / 214 skipped** (367개, 3.7분). [실패 출력](e2e-real-failures.txt). 모드별 기존 skip이며 이번 검증에서 추가하지 않았다.
- WSL 전체 서버 `pytest app/tests ai_worker/tests tests -q --maxfail=3`: **1568 passed / 3 failed / 5 skipped**, 775.24초 후 중단.
- 중단으로 미실행된 마지막 디렉터리를 빠뜨리지 않도록 WSL `pytest tests -q --tb=short` 전체 재실행: **162 passed / 7 failed**, 98.87초. 위 실행과 중복되므로 두 통과 수를 합산하지 않는다. app/tests와 ai_worker/tests는 첫 실행에서 끝까지 진행됐으며 tests 디렉터리는 두 번째 실행에서 끝까지 진행됐다.
- 375/390px 요구 상태 20장 캡처. 전체 가로 넘침 검사 통과. H-5/H-6 제출 버튼은 844px 뷰포트 안에 유지.
- 개발 DB `aerich upgrade`: No upgrade items found. 기존 27~30 적용 상태 확인. medication_doses 전/후 0행, 이번 실행의 행 삭제 없음.
- 격리 downgrade/re-upgrade: 실패. 위 병합 차단 항목 참조. Aerich 이력 조작이 아닌 실제 migration SQL 검증이다.

## 테스트 보정 이유

F §3에 따라 화면을 바꾸기 전에 원인을 확인했다. 테스트 삭제·skip 추가 없이 다음 오래된 계약만 보정했다.

1. API 오류 화면: 프로필 주소 `/api/v1/me` → `/api/v1/users/me`. 가짜 토큰이 실제 서버로 전송되어 401로 로그아웃되던 테스트 픽스처 수정.
2. OCR 등록: 등록 진행 식별자 `flow=registration`이 포함된 기존 구현의 이동 주소를 검사하도록 수정.
3. 하단 탭바: 가짜 로그인으로 방문하는 화면의 보조 API 응답을 명시적으로 준비. 레이아웃·탭·뒤로/앞으로 이동 검증은 유지.
4. 복약 빈 화면: 영양제 보조 API의 401 방지 및 현재 빈 화면 문구/처방 추가 버튼으로 계약 갱신. 404와 500 구분 및 업로드 이동 검증은 유지.

## 작업지시 F §4.2 확인

- A: `SendChatResult`에 후속 질문 필드가 없다. H-3 ④ 이어서 물어보기는 보류 상태이며, 답변 4단 전체 구현 완료로 표현하면 안 된다.
- B: medication_notes의 user/episode FK는 물리 삭제 시 CASCADE, medication FK는 SET NULL이다. 현재 회원탈퇴는 WITHDRAWN 상태만 저장하므로 탈퇴 즉시 메모가 지워지지 않는다. 물리 삭제 배치 구현/실행은 확인되지 않았다.
- E: 복용 저장은 소유자·날짜를 검증하지만 처방 상태가 ACTIVE인지 차단하는 검증은 없다. 지시대로 변경하지 않았다.
- 알림 기본값: 모델 false와 DB medication/schedule/guide DEFAULT 1 불일치는 별도 과제이며 이번 PR에서 수정하지 않는다.
- 30 supplement_doses 및 `/med` 라우터·영양제 복용 UI는 A~E 밖의 기획 미검수 범위다.

## 남은 서버 테스트 실패

아래는 해결하지 않은 실패이며 통과로 처리하지 않는다.

- `app/tests/admin_apis/test_admin_dashboard_api.py::TestDashboardPeriod::test_new_signups_changes_but_snapshot_counts_do_not`: `(0,2,3)`과 기대 `(1,2,3)` 불일치. 관련 테스트·서비스·DB 설정은 main 대비 동일하지만 정확한 원인은 미확정이다. 시각 경계 가설만으로 통과 처리하지 않았다.
- `tests/models/test_async_ocr_migration.py::test_async_ocr_migration_follows_nutrient_standard_and_captures_merged_models`: 옛 migration 7 스냅샷을 현재 전체 모델과 비교. main에도 이미 있는 birth_date/gender가 스냅샷에 없어 선행 불일치가 확인된다.
- `tests/models/test_model_metadata.py::test_user_settings_are_one_to_one_and_have_default_times`: 기대 True / 모델 False. main에도 존재하는 테스트 불일치이며 F §1.2 범위 밖.
- `tests/models/test_model_metadata.py::test_chat_and_source_retention_v4_metadata`: 제거된 ChatSession.score 필드 조회 KeyError.
- `tests/models/test_ocr_v3_storage_migration.py::test_migration_captures_current_ocr_v3_model_state`: migration 21 스냅샷과 현재 모델 불일치.
- `tests/test_shared_sidebar_templates.py::test_sidebar_partial_contains_every_navigation_target_once`: 공통코드 메뉴가 추가된 목록과 기대 목록 불일치.
- `tests/test_shared_sidebar_templates.py::test_active_sidebar_link_uses_reference_colors_and_bold_weight`: CSS 토큰과 과거 하드코딩 색상 기대값 불일치.
- `tests/test_user_contract.py::test_signup_contract_trims_name`: 공백 포함 이름을 trim하는 기대와 현재 이름 검증 규칙 불일치.

기존 테스트 부채가 섞여 있지만 모든 실패를 기존 문제로 단정하지 않는다. Draft 해제 전 각 계약의 정합성을 정리해야 한다.

## 남은 실 API 모드 E2E 실패 분류

재검증 결과 11건을 그대로 남겼다. 아래 진단은 읽기 전용 비교이며 수정 후 재통과를 뜻하지 않는다.

- OCR 직접 추가 레이아웃 1건: padding 검사에서 DOM 부모를 고정 단계로 찾는 기대가 현재 Input 래퍼와 어긋난다.
- 업로드 2건: 보호된 document-upload를 인증 준비 없이 방문하며 결과 스냅샷은 로그인 화면이다.
- 빈 홈 1건: 영양제 보조 API 인증 픽스처가 빠져 게스트 화면으로 바뀌는 정황.
- 처방 삭제 4건: 첫 버튼의 과거 이름 `삭제하기`를 찾지만 현재는 `선택한 처방 삭제`다.
- 느린 처방 저장 1건: schedule PUT만 준비하고 현재 함께 호출하는 alias PATCH를 준비하지 않아 로그인 화면으로 바뀌는 정황.
- 영양제 랭킹 추가 1건: 프로필 픽스처가 과거 `/api/v1/me`에 남아 있고 실제 경로는 `/api/v1/users/me`다.
- **처방 일부 저장 실패 롤백 1건: 실제 UI 결함 가능성.** 첫 처방 저장 성공·둘째 실패 뒤 첫 처방 완료 배지가 사라진다. HomePage는 실패 ID만 되돌리지만 MedicationTimeline은 false 반환 시 이전 완료 집합 전체를 복원한다. effect 동기화 순서와 함께 추가 재현이 필요하다. 단순 테스트 부채로 분류하지 않았으며 병합 전 확인해야 한다.

## 배포 주의

마이그레이션 29는 기존 medication_doses 행을 전부 삭제한다. 필수 care_episode_id에 기존 행을 귀속시킬 정보가 없어 개발 단계에 한해 기획 승인한 결정이다. downgrade로 삭제 행은 복구되지 않는다. 시범·운영 DB에는 같은 결정을 적용하지 말고 데이터 이전 방안을 다시 검토해야 한다.

`/med` 프리픽스를 med_router와 medication_resource_router가 나눠 사용한다. 현재 경로 충돌은 없지만 새 경로 추가 시 두 파일을 함께 검토해야 한다.

기존 개편 과정에서 제거된 E2E는 home-dose-record-grid 10개와 home-dose-record-animation 5개이며, 대상 MedicationRecordGrid 제거에 따른 것이다. 이번 검증에서는 테스트를 삭제하지 않았다.

ERD v1.1.9 → v1.2.0은 기획이 머지 후 반영한다. 제공된 `docs/ui-reference/ERD_추가분_v1.2.0.md`는 사용자 자료로 유지하며 이번 검증 커밋에 일괄 포함하지 않는다.
