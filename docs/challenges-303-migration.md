# #303 챌린지 마이그레이션

## 변경 범위

- 참여 상태에 `EXPIRED`를 추가한다. 만료 자동 전환 로직은 포함하지 않는다.
- `ChallengeVerification`에 `(user_challenge_id, verification_date)` 유니크 제약을 추가한다.
- main의 템플릿 생성 37번·기본값 등록 38번 다음에 `39_20260908151829_challenge_daily_verification.py`를 적용한다.
- 미병합 로컬 작업의 `37_20260908090000_challenge_daily_verification.py`를 39번으로 대체했다. main에 있는 마이그레이션은 수정하지 않는다.
- `MODELS_STATE`는 최신 모델에서 재생성하여 맞춤 템플릿 등 다른 모델 메타데이터를 보존한다.
- 상태 컬럼은 `VARCHAR(9)`이므로 EXPIRED를 위한 컬럼 변경이나 기존 값 변환은 필요 없다.
- API·백오피스·초기 데이터·이메일 기능은 변경하지 않는다.

## 기존 로컬 적용 이력과의 호환

| DB 상태 | 39번 적용 결과 |
| --- | --- |
| main 38번까지 적용, 일일 유니크 없음 | 일반 인덱스를 유니크로 교체 |
| 과거 로컬 37번을 이미 적용 | 올바른 유니크가 있으면 DDL 없이 통과하고 39번 이력만 추가 |
| 같은 참여·날짜의 중복 인증 존재 | 인증을 삭제하지 않고 명시적으로 중단 |
| 같은 이름의 인덱스 정의가 예상과 다름 | 임의 교체하지 않고 중단 |

Aerich는 전체 파일명으로 적용 여부를 확인한다. 과거 로컬 37번 이력 행을 삭제·변경하거나 `--fake`로 덮어쓰지 않는다. 새 39번 적용 후 최신 모델 상태가 기록된다.

## 다운그레이드 주의

- 39번 downgrade는 일일 유니크를 제거하고 일반 인덱스를 복구한다. 인증·참여 데이터와 EXPIRED 값은 삭제하지 않는다.
- 과거 로컬 37번까지 거슬러 내려가는 rollback은 저장소에 해당 파일이 없으므로 별도 복구가 필요하다. 사전 백업과 커밋 `6f0e366`의 원본 파일을 확보하고 순서를 검토한다. 이력 행을 지워 해결하지 않는다.
- EXPIRED를 모르는 이전 애플리케이션으로 되돌릴 때는 기존 상태 처리 방안을 먼저 정한다.
- 사용자 DB에서 downgrade나 재적용을 자동 실행하지 않는다.

## 적용 전 확인

배포할 코드에 39번 파일이 있는지 확인하고 DB를 백업한다. 적용 중 챌린지 인증 쓰기는 잠시 중단하는 것을 권장한다.

```sql
SELECT user_challenge_id, verification_date, COUNT(*) AS duplicate_count
FROM challenge_verifications
GROUP BY user_challenge_id, verification_date
HAVING COUNT(*) > 1;
```

WSL에서 해당 코드가 마운트된 FastAPI 컨테이너를 사용한다.

```bash
docker compose exec -T fastapi /app/.venv/bin/aerich heads
# 대기 파일 전체를 검토하고 백업한 뒤 실행
docker compose exec -T fastapi /app/.venv/bin/aerich upgrade
docker compose exec -T fastapi /app/.venv/bin/aerich heads
```

main 38번까지 적용한 DB에는 39번이 대기한다. 다른 대기 항목이 있으면 함께 적용될 내용을 먼저 검토한다. `init-db`, 볼륨 삭제, 회원 데이터 초기화는 필요 없다.

## 검증 범위

- WSL + 별도 MySQL 8.0 테스트 컨테이너를 사용한다. 사용자 DB는 테스트에 사용하지 않는다.
- 같은 날 중복 차단, 다음 날/다른 참여 허용, 기존 중복 무변경 중단.
- 사전 검사 이후 중복 삽입 시 단일 ALTER 실패와 기존 인덱스 보존.
- 기존 로컬 제약 재적용과 이력 보존, 비정상 인덱스 조합 방어.
- downgrade 데이터 보존, 최신 38번 대비 관계없는 모델 상태 보존.
- 모델·기존 챌린지 API 회귀 검증. 맞춤 챌린지 API와 만료 자동 전환은 별도 범위다.

### 2026-09-08 검증 결과

- WSL의 격리 MySQL 8.0에서 모델·마이그레이션·챌린지 API 테스트 26개 통과.
- 38번 동등 스키마 테스트 fixture에서 실제 Aerich 39번 upgrade 및 재실행 통과. 기존 로컬 37번 이력과 유니크가 있는 별도 fixture에서도 통과하며 이력 행과 테이블별 데이터 수를 보존했다.
- 위 fixture 검증은 전체 과거 마이그레이션 재생 성공을 뜻하지 않는다. 빈 DB에서 전체 이력을 재생하는 별도 점검은 기존 `4_20260821181046_drop_admin_session_salt.py`의 빈 SQL 오류로 중단됐다. 해당 과거 파일은 이 PR에서 수정하지 않는다.
- 사용자 로컬 DB에는 이번 검증으로 39번을 적용하지 않았다. PR 병합 및 배포 코드 반영 후 백업과 대기 이력 확인을 거쳐 적용한다.

일일 유니크는 요청 키가 달라도 DB 중복을 막는다. 중복 요청의 사용자 응답 정책은 API 담당 범위이며, 향후 하루 여러 번 인증을 도입할 때는 제약을 다시 검토해야 한다.
