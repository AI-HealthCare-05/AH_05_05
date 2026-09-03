from fastapi import status


class AppError(Exception):
    """API 에러 공통 베이스.

    핸들러가 {"code": ..., "message": ...} 형태로 직렬화한다.
    프론트(frontend/src/shared/api/client.ts)가 code로 분기하고 message를 그대로 노출하므로,
    message는 사용자에게 보여도 되는 문구로 작성한다.
    """

    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    code: str = "INTERNAL_ERROR"
    message: str = "서버에서 알 수 없는 오류가 발생했습니다."
    field: str | None = None

    def __init__(self, message: str | None = None) -> None:
        if message is not None:
            self.message = message
        super().__init__(self.message)


class UnauthorizedError(AppError):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = "UNAUTHORIZED"
    message = "인증이 필요합니다."


class ForbiddenError(AppError):
    status_code = status.HTTP_403_FORBIDDEN
    code = "FORBIDDEN"
    message = "접근 권한이 없습니다."


class CommonCodeGroupNotFoundError(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "COMMON_CODE_GROUP_NOT_FOUND"
    message = "공통코드 그룹을 찾을 수 없습니다."


class CommonCodeNotFoundError(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "COMMON_CODE_NOT_FOUND"
    message = "공통코드를 찾을 수 없습니다."


class CommonCodeAlreadyExistsError(AppError):
    status_code = status.HTTP_409_CONFLICT
    code = "COMMON_CODE_ALREADY_EXISTS"
    message = "이미 등록된 공통코드입니다."


class InvalidCommonCodeError(AppError):
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    code = "INVALID_COMMON_CODE"
    message = "공통코드는 영문 대문자, 숫자, 밑줄만 사용할 수 있습니다."


class InvalidChatFeedbackReasonError(AppError):
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    code = "INVALID_CHAT_FEEDBACK_REASON"
    message = "선택한 채팅 평가 사유를 사용할 수 없습니다."


class AdminNotFoundError(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "ADMIN_NOT_FOUND"
    message = "관리자를 찾을 수 없습니다."


class UserNotFoundError(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "USER_NOT_FOUND"
    message = "사용자를 찾을 수 없습니다."


class SupplementRankDisplayNotFoundError(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "SUPPLEMENT_RANK_DISPLAY_NOT_FOUND"
    message = "영양제 랭킹 전시를 찾을 수 없습니다."


class SupplementRankPeriodConflictError(AppError):
    status_code = status.HTTP_409_CONFLICT
    code = "SUPPLEMENT_RANK_PERIOD_CONFLICT"
    message = "활성화된 영양제 랭킹 전시 기간이 겹칩니다."


class SupplementNutrientNotFoundError(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "SUPPLEMENT_NUTRIENT_NOT_FOUND"
    message = "등록할 영양제 정보를 찾을 수 없습니다."


class InvalidCredentialsError(AppError):
    """이메일 열거를 막기 위해 계정 없음과 비밀번호 불일치를 구분하지 않는다."""

    status_code = status.HTTP_401_UNAUTHORIZED
    code = "INVALID_CREDENTIALS"
    message = "이메일 또는 비밀번호가 일치하지 않습니다."


class InvalidPasswordError(AppError):
    status_code = status.HTTP_400_BAD_REQUEST
    code = "INVALID_PASSWORD"
    message = "현재 비밀번호가 일치하지 않습니다."


class SamePasswordError(AppError):
    status_code = status.HTTP_400_BAD_REQUEST
    code = "SAME_AS_CURRENT"
    message = "현재 비밀번호와 다른 비밀번호를 입력해주세요."


class InvalidTokenError(AppError):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = "INVALID_TOKEN"
    message = "유효하지 않거나 만료된 토큰입니다."


class AccountSuspendedError(AppError):
    status_code = status.HTTP_403_FORBIDDEN
    code = "ACCOUNT_SUSPENDED"
    message = "정지된 계정입니다. 관리자에게 문의하세요."


class AccountWithdrawnError(AppError):
    status_code = status.HTTP_403_FORBIDDEN
    code = "ACCOUNT_WITHDRAWN"
    message = "사용할 수 없는 계정입니다."


class EmailAlreadyExistsError(AppError):
    status_code = status.HTTP_409_CONFLICT
    code = "EMAIL_ALREADY_EXISTS"
    message = "이미 등록된 이메일입니다."


class SmtpPasswordRequiredError(AppError):
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    code = "SMTP_PASSWORD_REQUIRED"
    message = "최초 SMTP 설정 저장 시 비밀번호를 입력해 주세요."


class SignupEmailAlreadyExistsError(AppError):
    """계정 열거 방지: 활성 계정인지 탈퇴 계정인지 구분되지 않게 문구를 뭉갠다.

    「이미 사용중인」은 **활성 계정이 있다**는 뜻이라 탈퇴자와 구분됐다.
    「사용할 수 없는」은 이유를 말하지 않는다.

    **로그인과 달리 code·status 는 바꾸지 않는다.** 회원가입은 「이 주소는 쓸 수 없다」를
    반드시 알려야 기능이 성립한다 — 안 알려주면 사용자가 다른 주소를 쓸 수가 없다.
    즉 어떤 코드를 쓰든 열거를 완전히 막을 수 없고, 409 라는 사실만으로 이미 새어나간다.
    문구를 바꿔 얻는 것은 「왜 못 쓰는지」를 감추는 것뿐이다.

    게다가 프론트(AuthPage)가 이 code 로 형식 오류(422)와 분기하고 있어,
    코드를 바꾸면 그 분기까지 고쳐야 한다. 얻는 것에 비해 비싸다.
    """

    status_code = status.HTTP_409_CONFLICT
    code = "EMAIL_ALREADY_EXISTS"
    message = "사용할 수 없는 이메일입니다."
    field = "email"


class CannotResetSuspendedError(AppError):
    """정지를 풀지 않고 비밀번호만 재발급하면 정지가 무의미해진다."""

    status_code = status.HTTP_409_CONFLICT
    code = "CANNOT_RESET_SUSPENDED"
    message = "정지된 계정은 재발송할 수 없습니다."


class CannotResetWithdrawnError(AppError):
    status_code = status.HTTP_409_CONFLICT
    code = "CANNOT_RESET_WITHDRAWN"
    message = "탈퇴한 계정은 재발송할 수 없습니다."


class LastActiveAdminError(AppError):
    """활성 ADMIN 이 0명이 되는 것을 막는다.

    깨지면 아무도 관리자 콘솔에 로그인할 수 없고, DB 를 직접 고치는 것 외에
    복구 수단이 없다.
    """

    status_code = status.HTTP_409_CONFLICT
    code = "LAST_ACTIVE_ADMIN"
    message = "마지막 활성 관리자는 정지할 수 없습니다."


class CannotSuspendSelfError(AppError):
    status_code = status.HTTP_409_CONFLICT
    code = "CANNOT_SUSPEND_SELF"
    message = "본인 계정은 정지할 수 없습니다."


class CannotChangeOwnRoleError(AppError):
    """본인 역할 변경을 막는다.

    권한 검사가 매 요청 DB 를 보므로 스스로를 STAFF 로 낮추면 그 즉시 ADMIN 전용 API 에
    접근할 수 없다. 되돌릴 API 도 그 안에 있어 복구 수단이 없다.
    """

    status_code = status.HTTP_409_CONFLICT
    code = "CANNOT_CHANGE_OWN_ROLE"
    message = "본인 역할은 변경할 수 없습니다."


class SameRoleError(AppError):
    status_code = status.HTTP_409_CONFLICT
    code = "SAME_ROLE"
    message = "이미 해당 역할입니다."


class CannotChangeInactiveAdminError(AppError):
    """정지·탈퇴 계정의 역할 변경을 막는다.

    역할은 로그인해서 쓸 수 있는 권한을 뜻한다. 쓸 수 없는 계정의 권한을 손대면
    나중에 해제될 때 의도하지 않은 권한으로 살아난다.
    """

    status_code = status.HTTP_409_CONFLICT
    code = "CANNOT_CHANGE_INACTIVE_ADMIN"
    message = "정지·탈퇴한 계정은 역할을 변경할 수 없습니다."


class CannotReactivateWithdrawnError(AppError):
    """탈퇴한 계정을 관리자가 되살리는 것을 막는다.

    탈퇴는 본인 의사이고 REQ-ADMIN-007 데이터 삭제의 대상이기도 하다.
    관리자가 임의로 ACTIVE 로 되돌리면 삭제 대기 중인 계정이 다시 살아난다.
    """

    status_code = status.HTTP_409_CONFLICT
    code = "CANNOT_REACTIVATE_WITHDRAWN"
    message = "탈퇴한 계정은 상태를 변경할 수 없습니다."


class InvalidImageError(AppError):
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    code = "INVALID_IMAGE"
    message = "유효한 JPG 또는 PNG 이미지를 선택해 주세요."


class TemplateNotMatchedError(AppError):
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    code = "TEMPLATE_NOT_MATCHED"
    message = "등록된 조제약 복약안내 템플릿과 일치하지 않습니다."


class NoMedicationsFoundError(AppError):
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    code = "NO_MEDICATIONS_FOUND"
    message = "약품 정보를 찾지 못했습니다. 이미지와 템플릿을 확인해 주세요."


class OcrProviderConfigError(AppError):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    code = "PROVIDER_CONFIG_MISSING"
    message = "Template OCR 설정이 필요합니다."


class OcrProviderError(AppError):
    status_code = status.HTTP_502_BAD_GATEWAY
    code = "OCR_PROVIDER_ERROR"
    message = "Template OCR 응답을 처리할 수 없습니다."


class OcrProviderTransientError(OcrProviderError):
    """네트워크 또는 공급자 일시 장애로 한 번 재시도할 수 있는 오류."""


class OcrProviderTimeoutError(AppError):
    status_code = status.HTTP_504_GATEWAY_TIMEOUT
    code = "OCR_PROVIDER_TIMEOUT"
    message = "Template OCR 호출 시간이 초과됐습니다."


class OcrIdempotencyConflictError(AppError):
    status_code = status.HTTP_409_CONFLICT
    code = "IDEMPOTENCY_CONFLICT"
    message = "같은 Idempotency-Key로 다른 파일을 요청할 수 없습니다."


class OcrJobNotFoundError(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "OCR_JOB_NOT_FOUND"
    message = "OCR 작업을 찾을 수 없습니다."


class OcrJobStateConflictError(AppError):
    status_code = status.HTTP_409_CONFLICT
    code = "OCR_JOB_STATE_CONFLICT"
    message = "현재 OCR 작업 상태에서는 요청을 처리할 수 없습니다."


class OcrQueueUnavailableError(AppError):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    code = "OCR_QUEUE_UNAVAILABLE"
    message = "OCR 분석 작업을 시작할 수 없습니다. 잠시 후 다시 시도해 주세요."


class MedicationScheduleNotFoundError(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "MEDICATION_SCHEDULE_NOT_FOUND"
    message = "복약 시간표를 찾을 수 없습니다."


class InvalidMedicationScheduleError(AppError):
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    code = "INVALID_MEDICATION_SCHEDULE"
    message = "복약 시간표 입력값이 올바르지 않습니다."


class MedicationScheduleFinishedError(AppError):
    status_code = status.HTTP_409_CONFLICT
    code = "MEDICATION_SCHEDULE_FINISHED"
    message = "이미 끝난 처방은 수정할 수 없습니다"


class InvalidDoseDateError(AppError):
    status_code = status.HTTP_400_BAD_REQUEST
    code = "INVALID_DOSE_DATE"
    message = "복용 날짜는 오늘 또는 지난 365일 이내여야 합니다."


class InvalidDoseSlotError(AppError):
    status_code = status.HTTP_400_BAD_REQUEST
    code = "INVALID_SLOT"
    message = "복용 시간대가 올바르지 않습니다."


class MedicationRecordForbiddenError(AppError):
    status_code = status.HTTP_403_FORBIDDEN
    code = "MEDICATION_RECORD_FORBIDDEN"
    message = "다른 사용자의 복약 기록에는 접근할 수 없습니다."


class MedicationRecordNotFoundError(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "MEDICATION_RECORD_NOT_FOUND"
    message = "복약 기록을 찾을 수 없습니다."


class InvalidMedicationOverviewDateRangeError(AppError):
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    code = "INVALID_MEDICATION_OVERVIEW_DATE_RANGE"
    message = "복약 목록 조회 기간이 올바르지 않습니다."


class InvalidDoseDateRangeError(AppError):
    status_code = status.HTTP_400_BAD_REQUEST
    code = "INVALID_DOSE_DATE_RANGE"
    message = "복용 기록 조회 기간이 올바르지 않습니다."


class ChatConversationNotFoundError(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "CHAT_SESSION_NOT_FOUND"
    message = "채팅 세션을 찾을 수 없습니다."


class ChatSessionAccessDeniedError(AppError):
    status_code = status.HTTP_403_FORBIDDEN
    code = "CHAT_SESSION_ACCESS_DENIED"
    message = "해당 채팅 세션을 삭제할 권한이 없습니다."


class ChatCareEpisodeNotFoundError(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "CARE_EPISODE_NOT_FOUND"
    message = "확인 완료된 복약 기록을 찾을 수 없습니다."


class ChatContextConflictError(AppError):
    status_code = status.HTTP_409_CONFLICT
    code = "CHAT_CONTEXT_MISMATCH"
    message = "기존 채팅과 다른 복약 기록을 연결할 수 없습니다."


class ChatRequestConflictError(AppError):
    status_code = status.HTTP_409_CONFLICT
    code = "CHAT_REQUEST_IN_PROGRESS"
    message = "같은 채팅 요청을 처리하고 있습니다."


class ChatIdempotencyConflictError(AppError):
    status_code = status.HTTP_409_CONFLICT
    code = "CHAT_IDEMPOTENCY_CONFLICT"
    message = "같은 requestId로 다른 채팅 요청을 보낼 수 없습니다."


class ChatUpstreamUnavailableError(AppError):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    code = "CHAT_UPSTREAM_UNAVAILABLE"
    message = "답변을 생성하지 못했습니다. 잠시 후 다시 시도해 주세요."


class ChatAnswerTimeoutError(AppError):
    status_code = status.HTTP_504_GATEWAY_TIMEOUT
    code = "API_TIMEOUT"
    message = "답변 생성 시간이 초과되었습니다. 잠시 후 다시 시도해 주세요."


class ChatProcessingFailedError(AppError):
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    code = "CHAT_PROCESSING_FAILED"
    message = "채팅 답변 처리 중 오류가 발생했습니다."
