# 서비스에서 반복해서 사용하는 상태와 유형을 문자열 Enum으로

from enum import StrEnum


class InstructionType(StrEnum):
    DISCHARGE_INSTRUCTION = "DISCHARGE_INSTRUCTION"  # 퇴원지침
    PRECAUTION = "PRECAUTION"  # 주의사항
    WARNING_SIGN = "WARNING_SIGN"  # 경고증상/위험신호
    FOLLOW_UP = "FOLLOW_UP"  # 추적관찰/추적 진료


class SourceType(StrEnum):
    PATIENT_SAVED_FIELD = "PATIENT_SAVED_FIELD"  # 환자의 개인 저장 데이터
    PUBLIC_RAG_CHUNK = "PUBLIC_RAG_CHUNK"  # 공공/일반 RAG데이터 조각


class PatientSourceKind(StrEnum):
    CARE_EPISODE_FIELD = "CARE_EPISODE_FIELD"
    MEDICATION = "MEDICATION"
    CARE_ADVICE = "CARE_ADVICE"
    FOLLOW_UP_VISIT = "FOLLOW_UP_VISIT"


class CareEpisodeSourceField(StrEnum):
    DIAGNOSIS = "DIAGNOSIS"
    SURGERY = "SURGERY"
    DISCHARGE_DATE = "DISCHARGE_DATE"
    MEDICATION_DAYS = "MEDICATION_DAYS"


class SafetyStatus(StrEnum):
    PENDING = "PENDING"  # 검사 대기중
    SAFE = "SAFE"  # 안전함(사용자에게 출력 가능)
    RESTRICTED = "RESTRICTED"  # 제한됨
    BLOCKED = "BLOCKED"  # 차단됨
    VALIDATION_FAILED = "VALIDATION_FAILED"  # 검증/유효성 검사 실패


class ConflictStatus(StrEnum):  # 데이터 충돌 상태
    NOT_APPLICABLE = "NOT_APPLICABLE"  # 해당 없음(충돌을 검사할 필요가 없는 상황)
    NO_CONFLICT = "NO_CONFLICT"  # 충돌 없음(두 정보가 서로 모순되지 않음)
    PATIENT_DATA_PRIORITY = (
        "PATIENT_DATA_PRIORITY"  # 환자 개인 데이터 우선 적용(충돌 시 환자의 특정 정보가 더 중요하므로 이를 채택)
    )
    PUBLIC_SOURCE_EXCLUDED = "PUBLIC_SOURCE_EXCLUDED"  # 공공 출처 제외됨(충돌로 인해 일반 RAG 정보는 배제됨)
    REVIEW_REQUIRED = "REVIEW_REQUIRED"  # 검토 필요(사람/의료진의 직접적인 확인이 필요한 상태)
