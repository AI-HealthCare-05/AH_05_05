from typing import Literal, overload

from fastapi import HTTPException

from app.core import config
from app.core.jwt.exceptions import ExpiredTokenError, TokenError
from app.core.jwt.tokens import AccessToken, JwtScope, RefreshToken
from app.models.users import User


class JwtService:
    access_token_class = AccessToken
    refresh_token_class = RefreshToken

    def create_access_token(self, user: User) -> AccessToken:
        return self.access_token_class.for_user(user)

    def create_refresh_token(self, user: User) -> RefreshToken:
        return self.refresh_token_class.for_user(user)

    @overload
    def verify_jwt(
        self,
        token: str,
        token_type: Literal["access"],
        *,
        allow_expired: bool = False,
    ) -> AccessToken: ...

    @overload
    def verify_jwt(
        self,
        token: str,
        token_type: Literal["refresh"],
        *,
        allow_expired: bool = False,
    ) -> RefreshToken: ...

    @overload
    def verify_jwt(
        self,
        token: str,
        token_type: Literal["access", "refresh"],
        *,
        allow_expired: bool = False,
    ) -> AccessToken | RefreshToken: ...

    def verify_jwt(
        self,
        token: str,
        token_type: Literal["access", "refresh"],
        *,
        allow_expired: bool = False,
    ) -> AccessToken | RefreshToken:
        token_class: type[AccessToken | RefreshToken]
        if token_type == "access":
            token_class = self.access_token_class
        else:
            token_class = self.refresh_token_class

        try:
            verified = token_class(token=token)
            return verified
        except ExpiredTokenError as err:
            if allow_expired:
                # 정상 검증에서 ExpiredTokenError 가 났다는 것은 같은 토큰의 서명과 알고리즘은
                # 이미 통과했다는 뜻이다. 그 경우에만 exp 검사를 끄고 identity claim 을 읽는다.
                # 처음부터 verify=False 로 열면 위변조 토큰도 신뢰하게 되므로 금지한다.
                try:
                    return token_class(token=token, verify=False)
                except TokenError as invalid_err:
                    raise HTTPException(status_code=400, detail="Provided invalid token.") from invalid_err
            raise HTTPException(status_code=401, detail=f"{token_type} token has expired.") from err
        except TokenError as err:
            raise HTTPException(status_code=400, detail="Provided invalid token.") from err

    def get_user_subject(
        self,
        token: str,
        token_type: Literal["access", "refresh"],
        *,
        allow_expired: bool = False,
    ) -> int:
        verified = self._verify_user_token(token, token_type, allow_expired=allow_expired)
        return self._read_user_subject(verified)

    def get_user_session_identity(
        self,
        token: str,
        token_type: Literal["access", "refresh"],
        *,
        allow_expired: bool = False,
    ) -> tuple[int, str]:
        verified = self._verify_user_token(token, token_type, allow_expired=allow_expired)
        user_id = self._read_user_subject(verified)
        session_claim = "session_id" if token_type == "access" else "jti"
        session_id = verified.payload.get(session_claim)
        if not isinstance(session_id, str) or not session_id:
            raise HTTPException(status_code=401, detail="User token session is invalid.")
        return user_id, session_id

    def _verify_user_token(
        self,
        token: str,
        token_type: Literal["access", "refresh"],
        *,
        allow_expired: bool,
    ) -> AccessToken | RefreshToken:
        try:
            verified = self.verify_jwt(token=token, token_type=token_type, allow_expired=allow_expired)
        except HTTPException as err:
            if err.status_code == 400:
                raise HTTPException(status_code=401, detail="Provided invalid token.") from err
            raise
        if verified.payload.get("scope") != JwtScope.USER:
            raise HTTPException(status_code=403, detail="Token is not a user token.")
        return verified

    @staticmethod
    def _read_user_subject(verified: AccessToken | RefreshToken) -> int:
        subject = verified.payload.get("sub")
        legacy_user_id = verified.payload.get("user_id")
        if (
            isinstance(subject, bool)
            or isinstance(legacy_user_id, bool)
            or not isinstance(subject, (str, int))
            or not isinstance(legacy_user_id, (str, int))
        ):
            raise HTTPException(status_code=401, detail="User token subject is invalid.")
        try:
            subject_id = int(subject)
            user_id = int(legacy_user_id)
        except (TypeError, ValueError) as err:
            raise HTTPException(status_code=401, detail="User token subject is invalid.") from err
        if subject_id != user_id:
            raise HTTPException(status_code=401, detail="User token subject is invalid.")
        return subject_id

    def refresh_user_jwt(self, refresh_token: str, access_token: str | None = None) -> tuple[AccessToken, int]:
        user_id, refresh_session_id = self.get_user_session_identity(refresh_token, "refresh")
        if access_token is not None:
            bearer_identity = self.get_user_session_identity(access_token, "access", allow_expired=True)
            if bearer_identity != (user_id, refresh_session_id):
                raise HTTPException(status_code=403, detail="Access and refresh token sessions do not match.")

        verified_rt = self.verify_jwt(token=refresh_token, token_type="refresh")
        return verified_rt.access_token, user_id

    def should_clear_user_refresh_cookie(self, refresh_token: str | None, access_token: str | None) -> bool:
        if refresh_token is None:
            return False

        try:
            refresh_identity = self.get_user_session_identity(refresh_token, "refresh")
        except HTTPException:
            # 쓸 수 없는 쿠키는 남겨 둘 이유가 없다.
            return True

        if access_token is None:
            return True
        try:
            access_identity = self.get_user_session_identity(access_token, "access", allow_expired=True)
        except HTTPException:
            # 유효한 다른 탭의 쿠키를 출처 불명의 stale 요청이 지우지 않게 한다.
            return False
        return access_identity == refresh_identity

    def refresh_jwt(self, refresh_token: str) -> AccessToken:
        verified_rt = self.verify_jwt(token=refresh_token, token_type="refresh")
        return verified_rt.access_token

    def issue_jwt_pair(self, user: User) -> dict[str, AccessToken | RefreshToken]:
        rt = self.create_refresh_token(user)
        at = rt.access_token
        return {"access_token": at, "refresh_token": rt}

    def issue_or_reuse_user_jwt_pair(
        self, user: User, existing_refresh_token: str | None
    ) -> tuple[dict[str, AccessToken | RefreshToken], int]:
        if existing_refresh_token is not None:
            try:
                existing_user_id, _session_id = self.get_user_session_identity(existing_refresh_token, "refresh")
                verified = self.verify_jwt(existing_refresh_token, "refresh")
                expires_at = verified.payload.get("exp")
                if isinstance(expires_at, bool) or not isinstance(expires_at, (str, int)):
                    raise ValueError("Refresh token expiry is invalid")
                remaining = int(expires_at) - int(verified.current_time.timestamp())
                if existing_user_id == user.id and remaining > 0:
                    return {"access_token": verified.access_token, "refresh_token": verified}, remaining
            except (HTTPException, TypeError, ValueError):
                pass

        return self.issue_jwt_pair(user), config.REFRESH_TOKEN_EXPIRE_MINUTES * 60
