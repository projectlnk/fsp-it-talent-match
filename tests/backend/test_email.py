import smtplib
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError
from app.core.config import Settings
from app.core import email


@pytest.mark.parametrize("mode", ["plain", "starttls", "ssl"])
def test_smtp_transport(monkeypatch, mode):
    settings = Settings(_env_file=None, smtp_host="smtp.example.com", smtp_port=465 if mode == "ssl" else 587,
                        smtp_username="login", smtp_password="private-password",
                        smtp_starttls=mode == "starttls", smtp_ssl=mode == "ssl",
                        smtp_from_email="sender@example.com")
    monkeypatch.setattr(email, "get_settings", lambda: settings)
    factory = MagicMock()
    smtp = factory.return_value.__enter__.return_value
    smtp.send_message.return_value = {}
    monkeypatch.setattr(email.smtplib, "SMTP", factory)
    monkeypatch.setattr(email.smtplib, "SMTP_SSL", factory)
    email.send_email(to="recipient@example.com", subject="Подтверждение", body="Текст", html_body="<p>Текст</p>")
    assert factory.call_args.args == (settings.smtp_host, settings.smtp_port)
    assert factory.call_args.kwargs["timeout"] == 10
    assert ("context" in factory.call_args.kwargs) == (mode == "ssl")
    assert smtp.starttls.called == (mode == "starttls")
    if mode == "starttls":
        assert smtp.ehlo.call_count == 2
        assert "context" in smtp.starttls.call_args.kwargs
    smtp.login.assert_called_once_with("login", "private-password")
    msg = smtp.send_message.call_args.args[0]
    assert msg["To"] == "recipient@example.com"
    assert "sender@example.com" in msg["From"]
    assert msg.get_body(preferencelist=("plain",)).get_content().strip() == "Текст"
    assert msg.get_body(preferencelist=("html",)).get_content().strip() == "<p>Текст</p>"


@pytest.mark.parametrize("failure", [OSError("secret"), smtplib.SMTPAuthenticationError(535, b"secret"), "refused"])
def test_failure_is_safe(monkeypatch, caplog, failure):
    monkeypatch.setattr(email, "get_settings", lambda: Settings(_env_file=None))
    factory = MagicMock()
    smtp = factory.return_value.__enter__.return_value
    if failure == "refused":
        smtp.send_message.return_value = {"private@example.com": (550, b"secret")}
    else:
        smtp.send_message.side_effect = failure
    monkeypatch.setattr(email.smtplib, "SMTP", factory)
    with pytest.raises(email.EmailDeliveryError) as exc:
        email.send_email(to="private@example.com", subject="Test", body="token-secret")
    smtp.login.assert_not_called()
    assert "secret" not in str(exc.value) + caplog.text
    assert "private@example.com" not in caplog.text


def test_incompatible_modes_and_credentials():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, smtp_starttls=True, smtp_ssl=True)
    with pytest.raises(ValidationError):
        Settings(_env_file=None, smtp_username="login")
    assert "private-password" not in repr(Settings(_env_file=None, smtp_username="login", smtp_password="private-password"))
