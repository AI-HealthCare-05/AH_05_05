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


class AdminNotFoundError(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "ADMIN_NOT_FOUND"
    message = "관리자를 찾을 수 없습니다."


class UserNotFoundError(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "USER_NOT_FOUND"
    message = "사용자를 찾을 수 없습니다."


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
