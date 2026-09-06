# 작업지시 F · ① 마이그레이션 확인

2026-09-05 · feature/252 · d238b6a · 로컬 Docker ai_health

- 27~30은 실행 전 이미 적용됨(aerich id 39~42).
- `docker compose exec -T fastapi uv run aerich upgrade`: exit 0, `No upgrade items found`.
- medication_doses 실행 전/후: 0 / 0. 이번 실행으로 삭제된 행 없음.
- medication_doses: care_episode_id NOT NULL, 4컬럼 UNIQUE, FK CASCADE, 회차/날짜 인덱스 확인. 옛 3컬럼 유니크 없음.
- medication_notes: user/회차 CASCADE, 약 SET NULL, dosed_at/created_at 별도 컬럼 확인.
- supplement_doses: 등록/날짜/슬롯 UNIQUE 및 등록 FK CASCADE 확인.
- care_episodes: alias varchar(50) NULL, title varchar(150) NOT NULL 확인.
- 명시된 중단 지점에 따라 downgrade·후속 테스트·push·PR은 실행하지 않음.
- MySQL 클라이언트에서 world-writable charset.cnf 무시 경고 발생. 확인 쿼리는 UTF-8 연결 옵션을 명시함. 설정 수정은 하지 않음.

## SHOW CREATE TABLE 원문

```text
mysql: [Warning] World-writable config file '/etc/mysql/conf.d/charset.cnf' is ignored.
Table	Create Table
medication_doses	CREATE TABLE `medication_doses` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `dose_date` date NOT NULL,
  `slot` varchar(7) NOT NULL COMMENT 'MORNING: MORNING\nLUNCH: LUNCH\nEVENING: EVENING\nBEDTIME: BEDTIME',
  `taken_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `created_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `user_id` bigint NOT NULL,
  `care_episode_id` bigint NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uid_dose_user_date_slot_ep` (`user_id`,`dose_date`,`slot`,`care_episode_id`),
  KEY `idx_medication__user_date` (`user_id`,`dose_date`),
  KEY `idx_dose_episode_date` (`care_episode_id`,`dose_date`),
  CONSTRAINT `fk_dose_care_episode` FOREIGN KEY (`care_episode_id`) REFERENCES `care_episodes` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_medicati_user_2b519a1e` FOREIGN KEY (`user_id`) REFERENCES `user` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=30 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
Table	Create Table
medication_notes	CREATE TABLE `medication_notes` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '복약 메모 식별자',
  `user_id` bigint NOT NULL COMMENT '작성자',
  `care_episode_id` bigint NOT NULL COMMENT '처방',
  `medication_id` bigint DEFAULT NULL COMMENT '약 (선택)',
  `dosed_at` datetime(6) NOT NULL COMMENT '복용 일시',
  `body` varchar(500) NOT NULL COMMENT '복용 후 느낀 점',
  `created_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `updated_at` datetime(6) DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  KEY `fk_note_med` (`medication_id`),
  KEY `idx_note_user_dosed` (`user_id`,`dosed_at`),
  KEY `idx_note_episode` (`care_episode_id`),
  CONSTRAINT `fk_note_episode` FOREIGN KEY (`care_episode_id`) REFERENCES `care_episodes` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_note_med` FOREIGN KEY (`medication_id`) REFERENCES `medications` (`id`) ON DELETE SET NULL,
  CONSTRAINT `fk_note_user` FOREIGN KEY (`user_id`) REFERENCES `user` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
Table	Create Table
supplement_doses	CREATE TABLE `supplement_doses` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `dose_date` date NOT NULL,
  `slot` varchar(7) NOT NULL,
  `taken_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `registration_id` bigint NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uid_supplement_dose_registration_date_slot` (`registration_id`,`dose_date`,`slot`),
  CONSTRAINT `fk_supplement_dose_registration` FOREIGN KEY (`registration_id`) REFERENCES `user_suppl_nutrient` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=5 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
Table	Create Table
care_episodes	CREATE TABLE `care_episodes` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `title` varchar(150) NOT NULL,
  `status` varchar(9) NOT NULL DEFAULT 'ACTIVE' COMMENT 'ACTIVE: ACTIVE\nCOMPLETED: COMPLETED\nCANCELLED: CANCELLED',
  `started_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `default_end_at` datetime(6) DEFAULT NULL,
  `planned_end_at` datetime(6) DEFAULT NULL,
  `completed_at` datetime(6) DEFAULT NULL,
  `created_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `updated_at` datetime(6) DEFAULT NULL,
  `user_id` bigint NOT NULL,
  `surgery` varchar(500) DEFAULT NULL,
  `medication_days` int DEFAULT NULL,
  `source_ocr_job_id` bigint DEFAULT NULL,
  `medication_start_slot` varchar(7) DEFAULT NULL COMMENT 'MORNING: MORNING\nLUNCH: LUNCH\nEVENING: EVENING\nBEDTIME: BEDTIME',
  `discharge_date` date DEFAULT NULL,
  `diagnosis` varchar(500) DEFAULT NULL,
  `confirmed_at` datetime(6) DEFAULT NULL,
  `confirmation_hash` varchar(64) DEFAULT NULL,
  `medication_start_date` date DEFAULT NULL,
  `alias` varchar(50) DEFAULT NULL COMMENT '복약 별칭',
  PRIMARY KEY (`id`),
  KEY `idx_care_episod_user_id_4f8b7b` (`user_id`,`status`),
  KEY `idx_care_episod_user_id_0c2355` (`user_id`,`planned_end_at`),
  KEY `fk_care_episode_source_ocr` (`source_ocr_job_id`,`id`),
  CONSTRAINT `fk_care_epi_user_04599d52` FOREIGN KEY (`user_id`) REFERENCES `user` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_care_episode_source_ocr` FOREIGN KEY (`source_ocr_job_id`, `id`) REFERENCES `ocr_jobs` (`id`, `care_episode_id`) ON DELETE RESTRICT,
  CONSTRAINT `chk_care_confirmation` CHECK ((((`source_ocr_job_id` is null) and (`confirmed_at` is null) and (`confirmation_hash` is null)) or ((`source_ocr_job_id` is not null) and (`confirmed_at` is not null) and (`confirmation_hash` is not null)))),
  CONSTRAINT `chk_care_episode_completed` CHECK (((`completed_at` is null) or (`completed_at` >= `started_at`))),
  CONSTRAINT `chk_care_episode_default_end` CHECK (((`default_end_at` is null) or (`default_end_at` >= `started_at`))),
  CONSTRAINT `chk_care_episode_planned_end` CHECK (((`planned_end_at` is null) or (`planned_end_at` >= `started_at`))),
  CONSTRAINT `chk_care_medication_days` CHECK (((`medication_days` is null) or (`medication_days` between 1 and 365)))
) ENGINE=InnoDB AUTO_INCREMENT=32 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
```
