from app.core.utils.security import generate_session_salt
from app.models.admins import Admin


def rotate_session_salt(admin: Admin) -> None:
    """관리자의 세션 난수를 새로 발급한다. 저장은 호출한 쪽에서 한다.

    이 함수를 부르면 해당 관리자에게 이전에 발급된 리프레시 토큰이 기기와 무관하게
    모두 무효가 된다(갱신 시 sid 클레임과 session_salt 를 대조하므로).

    **세션을 끊어야 하는 모든 지점에서 이 함수를 부른다.** 호출부가 흩어지면
    한 곳을 빠뜨렸을 때 조용히 세션이 살아남는다. 현재 호출 지점은 다음과 같다.

    - 비밀번호 변경 (REQ-ADMIN-009) — 계정 노출 의심이 사유일 수 있어 다른 기기도 끊는다
    - 관리자 정지 (REQ-ADMIN-011) — 정지 즉시 접근이 끊겨야 한다
    - 역할 변경 (ADMIN <-> STAFF) — 새 권한으로 다시 로그인하게 한다.
      역할 변경 API 는 아직 없다. 추가할 때 이 함수를 함께 불러야 한다.
    """
    admin.session_salt = generate_session_salt()
