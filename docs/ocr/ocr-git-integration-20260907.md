# OCR 변경의 Git 폴더 통합 — 2026-09-07

## 범위와 보존

원본 `906/AH_05_05`의 OCR 관련 119개 파일을 `git/AH_05_05`에 파일 변경으로 반영했다. OCR API·모델·서비스·worker·설정 예시, 업로드·검토 UI·복약 표시, 회귀 테스트·벤치마크·문서·이미지를 포함한다. 채팅 관련 별도 작업, `.env` 비밀 값, 실행 산출물은 복사하지 않았다.

대상은 시작 시 미커밋 변경이 없었으며 HEAD는 `caea38276f5ad6a20a9324b98779e5a695110c3a`였다. 팀의 이메일 인증 설정과 홈 `MedicationTimeline`의 `referenceTime` 처리를 유지했다. 기존 31번 이메일 인증 마이그레이션과 나머지 팀 파일을 덮어쓰지 않았다.

## 마이그레이션 번호

| 내용 | 원본 로컬 복사본 | Git 폴더 |
| --- | --- | --- |
| 팀 이메일 인증 | 없음 | 기존 `31_20260907131651_add_email_verifications.py` 보존 |
| 병원명 | `31_20260906000000_add_care_episode_hospital_name.py` | `32_20260907223000_add_care_episode_hospital_name.py` |
| stage_results envelope | `32_20260907220000_stage_results_envelope.py` | `33_20260907223001_stage_results_envelope.py` |

새 32번 MODELS_STATE는 팀 31번의 47개 모델에 nullable `CareEpisode.hospital_name`만 추가했다. 데이터 전용 33번은 32번과 같은 상태를 사용한다. 관련 테스트의 동적 import도 33번으로 맞췄으며, 모델 집합과 이메일 인증 모델 보존을 검사하는 `tests/models/test_ocr_git_migration_chain.py`를 추가했다.

**이번 작업에서는 애플리케이션 DB에 마이그레이션을 적용하지 않았다.** 원본 31·32번이 적용된 로컬 DB는 Git 폴더의 팀 31→32→33 이력과 다르다. 그 DB에 이 체인을 그대로 실행하면 병원명 컬럼 중복 등 충돌이 생길 수 있으므로, 별도 이력·스키마 대조 및 정합 절차가 선행되어야 한다. 이 문서는 배포 또는 DB 전환 완료 보고가 아니다.

## 검증

- 대상 OCR·worker·설정·마이그레이션·팀 이메일 인증 모델/API 회귀: **526 passed, 1 skipped**. 스킵은 frozen local OCR-16 증거 번들 미존재 조건이다.
- 마이그레이션 상태·저장 계약·OCR 서비스 집중 검사: **58 passed**.
- 프런트 `npm run build`: TypeScript와 Vite 빌드 성공. 기존 번들 크기 경고는 남아 있다.
- OCR 함량 표시·홈 복약 압축 브라우저 회귀: **13 passed**. API fixture를 사용한 UI 검사이며 실제 외부 OCR 호출 검증은 아니다.
- 별도 화면 캡처 실행 **6 passed**(위 OCR 검사 재실행). 375px·1280px 검토/수정 화면을 직접 확인했다.
- 독립 읽기 전용 QA: 파일 전송 누락과 코드·마이그레이션 차단 사항 없음. 의도된 차이는 팀 설정·referenceTime 보존, 마이그레이션 import 번호 변경이다. 이후 문서 번호 설명을 보완했다.
- 임시 DB에서 real Aerich 31→32→33 체인을 실행하는 추가 검사는 **DB 생성 권한 부족으로 미실행**. 기존 테스트에서 신규 33번 SQL과 상태 보존은 검증했지만, 전체 체인 실DB 실행 성공으로 표현하지 않는다. 임시 DB는 생성되지 않았다.

## Git 상태

커밋·스테이징·브랜치 변경·merge·cherry-pick·push는 하지 않았다. 변경 파일과 신규 파일은 모두 미커밋 상태로 남겼다. 통합에 무관한 원본 로컬 작업은 그대로 유지했다.
