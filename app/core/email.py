"""Отправка писем через SMTP.

В локальной разработке используется Mailpit — он принимает любые письма
без аутентификации и не отправляет их наружу.
"""
from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage

from app.core.config import get_settings

logger = logging.getLogger(__name__)

DEFAULT_FROM = "noreply@fsp-it-talent.local"


def send_email(*, to: str, subject: str, body: str, from_addr: str = DEFAULT_FROM) -> None:
    """Синхронно отправляет текстовое письмо через SMTP.

    Ошибки SMTP логируются и не поднимаются наверх: регистрация не должна
    падать из-за недоступного почтового сервера. Письмо можно переотправить
    отдельной ручкой.
    """
    settings = get_settings()
    msg = EmailMessage()
    msg["From"] = from_addr
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as smtp:
            smtp.send_message(msg)
    except (OSError, smtplib.SMTPException) as exc:
        logger.warning("Не удалось отправить письмо на %s: %s", to, exc)