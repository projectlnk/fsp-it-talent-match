"""SMTP sender: внешний провайдер или локальный Mailpit."""
from __future__ import annotations

import logging
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class EmailDeliveryError(Exception):
    """SMTP-сервер не подтвердил приём письма."""


def send_email(*, to: str, subject: str, body: str,
               from_addr: str | None = None, html_body: str | None = None) -> None:
    settings = get_settings()
    msg = EmailMessage()
    msg["From"] = formataddr((settings.smtp_from_name, from_addr or settings.smtp_from_email))
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    if html_body is not None:
        msg.add_alternative(html_body, subtype="html")
    try:
        connection = (smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port,
                                      timeout=10, context=ssl.create_default_context())
                      if settings.smtp_ssl else
                      smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10))
        with connection as smtp:
            if settings.smtp_starttls:
                smtp.ehlo()
                smtp.starttls(context=ssl.create_default_context())
                smtp.ehlo()
            if settings.smtp_username:
                smtp.login(settings.smtp_username, settings.smtp_password.get_secret_value())
            if smtp.send_message(msg):
                raise EmailDeliveryError("Письмо не принято почтовым сервером")
    except (OSError, smtplib.SMTPException, EmailDeliveryError) as exc:
        # Не записываем ответ сервера: он может содержать credentials или адреса.
        logger.warning("Ошибка отправки email: %s", type(exc).__name__)
        raise EmailDeliveryError("Не удалось отправить письмо подтверждения") from None
