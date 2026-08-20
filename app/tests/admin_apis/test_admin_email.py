import logging
from unittest.mock import patch

from starlette import status
from tortoise.contrib.test import TestCase

from app.core.email.backends import ConsoleEmailBackend, EmailMessage, EmailSendError, SmtpEmailBackend
from app.models.admins import Admin
from app.models.enums import AdminRole
from app.services.admin_email import build_temporary_password_mail
from app.tests.admin_apis.conftest import ADMIN_ACCOUNTS_URL, auth_header, create_admin, request

CREATE_PAYLOAD = {"name": "한지수", "email": "jisu@ozcoding.ai", "role": "STAFF", "isActive": True}


class TestTemporaryPasswordMail:
    def test_contains_login_information(self) -> None:
        message = build_temporary_password_mail(
            name="한지수", email="jisu@ozcoding.ai", temporary_password="Temp1234!@#$"
        )

        assert message.to == "jisu@ozcoding.ai"
        assert message.subject == "[Ozcoding AI Health] 관리자 계정이 생성되었습니다"
        assert "한지수" in message.body
        assert "jisu@ozcoding.ai" in message.body
        assert "Temp1234!@#$" in message.body

    def test_tells_user_to_change_password(self) -> None:
        message = build_temporary_password_mail(name="한지수", email="jisu@ozcoding.ai", temporary_password="x")

        assert "비밀번호를 변경" in message.body


class TestConsoleEmailBackend:
    def test_logs_message_body(self, caplog: object) -> None:
        message = EmailMessage(to="jisu@ozcoding.ai", subject="제목", body="본문 Temp1234!")

        with caplog.at_level(logging.INFO, logger="app.core.email.backends"):  # type: ignore[attr-defined]
            ConsoleEmailBackend().send(message)

        text = caplog.text  # type: ignore[attr-defined]
        assert "jisu@ozcoding.ai" in text
        assert "본문 Temp1234!" in text


class TestSmtpEmailBackend:
    backend = SmtpEmailBackend(host="smtp.example.com", port=587, user="u", password="p", sender="from@x.ai")

    def test_raises_email_send_error_on_failure(self) -> None:
        with patch("app.core.email.backends.smtplib.SMTP", side_effect=OSError("connect failed")):
            try:
                self.backend.send(EmailMessage(to="a@x.ai", subject="s", body="b"))
            except EmailSendError:
                return
        raise AssertionError("EmailSendError 가 발생해야 한다")

    def test_never_logs_body(self, caplog: object) -> None:
        """본문에 임시 비밀번호가 있으므로 실패 로그에도 남기지 않는다."""
        message = EmailMessage(to="a@x.ai", subject="제목", body="비밀번호 SuperSecret123!")

        with (
            caplog.at_level(logging.DEBUG, logger="app.core.email.backends"),  # type: ignore[attr-defined]
            patch("app.core.email.backends.smtplib.SMTP", side_effect=OSError("boom")),
        ):
            try:
                self.backend.send(message)
            except EmailSendError:
                pass

        assert "SuperSecret123!" not in caplog.text  # type: ignore[attr-defined]


class TestAdminCreateSendsMail(TestCase):
    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        self.admin = await create_admin(name="김은미", email="eunmi@ozcoding.ai", role=AdminRole.ADMIN)
        self.headers = auth_header(self.admin.id)

    async def test_reports_email_sent(self) -> None:
        response = await request("POST", ADMIN_ACCOUNTS_URL, headers=self.headers, json=CREATE_PAYLOAD)

        assert response.status_code == status.HTTP_201_CREATED
        assert response.json()["emailSent"] is True

    async def test_sends_temporary_password_to_new_admin(self) -> None:
        with patch("app.services.admin_email.email_backend") as backend:
            await request("POST", ADMIN_ACCOUNTS_URL, headers=self.headers, json=CREATE_PAYLOAD)

        backend.send.assert_called_once()
        message = backend.send.call_args.args[0]
        assert message.to == "jisu@ozcoding.ai"
        assert "한지수" in message.body

    async def test_keeps_account_when_sending_fails(self) -> None:
        """메일만 실패한 경우 계정 생성을 되돌리지 않는다. emailSent 로 알린다."""
        with patch("app.services.admin_email.email_backend") as backend:
            backend.send.side_effect = EmailSendError("smtp down")

            response = await request("POST", ADMIN_ACCOUNTS_URL, headers=self.headers, json=CREATE_PAYLOAD)

        assert response.status_code == status.HTTP_201_CREATED
        assert response.json()["emailSent"] is False
        assert await Admin.filter(email="jisu@ozcoding.ai").exists()

    async def test_response_never_contains_plain_password(self) -> None:
        sent: list[EmailMessage] = []

        with patch("app.services.admin_email.email_backend") as backend:
            backend.send.side_effect = sent.append
            response = await request("POST", ADMIN_ACCOUNTS_URL, headers=self.headers, json=CREATE_PAYLOAD)

        # 메일에 실린 평문을 그대로 응답에서 찾아본다.
        temporary_password = next(
            line.split(":", 1)[1].strip() for line in sent[0].body.splitlines() if "임시 비밀번호" in line
        )
        assert temporary_password not in response.text
        assert not any("password" in key.lower() for key in response.json())
