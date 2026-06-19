"""Email rendering/sending and password-reset token helpers."""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import emails  # type: ignore[import-untyped]
import jwt
from jinja2 import Template
from jwt.exceptions import InvalidTokenError

from app.core import security, settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class EmailData:
    """A rendered email's HTML body and subject line."""

    html_content: str
    subject: str


def render_email_template(*, template_name: str, context: dict[str, Any]) -> str:
    """Render a built Jinja2 email template from ``email-templates/build`` with ``context``."""
    logger.info("Rendering email template template_name=%s", template_name)
    template_str = (Path(__file__).parent / "email-templates" / "build" / template_name).read_text()
    html_content = Template(template_str).render(context)
    return html_content


def send_email(*, email_to: str, subject: str = "", html_content: str = "") -> None:
    """Send an HTML email via the configured SMTP server; requires email settings."""
    assert settings.emails_enabled, "no provided configuration for email variables"
    logger.info("Sending email")
    message = emails.Message(subject=subject, html=html_content, mail_from=(settings.EMAILS_FROM_NAME, settings.EMAILS_FROM_EMAIL))
    smtp_options = {"host": settings.SMTP_HOST, "port": settings.SMTP_PORT}
    if settings.SMTP_TLS:
        smtp_options["tls"] = True
    elif settings.SMTP_SSL:
        smtp_options["ssl"] = True
    if settings.SMTP_USER:
        smtp_options["user"] = settings.SMTP_USER
    if settings.SMTP_PASSWORD:
        smtp_options["password"] = settings.SMTP_PASSWORD
    response = message.send(to=email_to, smtp=smtp_options)
    status_code = getattr(response, "status_code", None)
    if isinstance(status_code, int) and status_code >= 400:
        logger.error("Email send failed status_code=%s", status_code)
    else:
        logger.info("Email sent status_code=%s", status_code)


def generate_test_email(email_to: str) -> EmailData:
    """Build the SMTP test email used to verify email delivery."""
    project_name = settings.PROJECT_NAME
    subject = f"{project_name} - Test email"
    html_content = render_email_template(template_name="test_email.html", context={"project_name": settings.PROJECT_NAME, "email": email_to})
    return EmailData(html_content=html_content, subject=subject)


def generate_reset_password_email(email_to: str, email: str, token: str) -> EmailData:
    """Build the password-recovery email embedding a reset link for ``token``."""
    project_name = settings.PROJECT_NAME
    subject = f"{project_name} - Password recovery for user {email}"
    link = f"{settings.FRONTEND_HOST}/reset-password?token={token}"
    html_content = render_email_template(
        template_name="reset_password.html",
        context={
            "project_name": settings.PROJECT_NAME,
            "username": email,
            "email": email_to,
            "valid_hours": settings.EMAIL_RESET_TOKEN_EXPIRE_HOURS,
            "link": link,
        },
    )
    return EmailData(html_content=html_content, subject=subject)


def generate_new_account_email(email_to: str, username: str, password: str) -> EmailData:
    """Build the welcome email delivering a new account's initial credentials."""
    project_name = settings.PROJECT_NAME
    subject = f"{project_name} - New account for user {username}"
    html_content = render_email_template(
        template_name="new_account.html",
        context={"project_name": settings.PROJECT_NAME, "username": username, "password": password, "email": email_to, "link": settings.FRONTEND_HOST},
    )
    return EmailData(html_content=html_content, subject=subject)


def generate_password_reset_token(email: str) -> str:
    """Return a signed JWT scoping a password reset to ``email``, expiring per settings."""
    delta = timedelta(hours=settings.EMAIL_RESET_TOKEN_EXPIRE_HOURS)
    now = datetime.now(timezone.utc)
    expires = now + delta
    exp = expires.timestamp()
    encoded_jwt = jwt.encode({"exp": exp, "nbf": now, "sub": email}, settings.SECRET_KEY, algorithm=security.ALGORITHM)
    return encoded_jwt


def verify_password_reset_token(token: str) -> str | None:
    """Return the email a valid reset token was issued for, or ``None`` if invalid/expired."""
    try:
        decoded_token = jwt.decode(token, settings.SECRET_KEY, algorithms=[security.ALGORITHM])
        return str(decoded_token["sub"])
    except InvalidTokenError:
        logger.warning("Password reset token verification failed")
        return None
