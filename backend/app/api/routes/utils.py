"""Utility endpoints: superuser email test and an unauthenticated health check."""

import logging

from fastapi import APIRouter, Depends
from pydantic.networks import EmailStr

from app.dependencies import get_current_active_superuser
from app.schemas.authentication import Message
from app.utils import generate_test_email, send_email

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/utils", tags=["utils"])


@router.post("/test-email/", dependencies=[Depends(get_current_active_superuser)], status_code=201)
def test_email(email_to: EmailStr) -> Message:
    """Send a test email to verify SMTP configuration (superuser only)."""
    email_data = generate_test_email(email_to=email_to)
    send_email(email_to=email_to, subject=email_data.subject, html_content=email_data.html_content)
    logger.info("Test email sent")
    return Message(message="Test email sent")


@router.get("/health-check/")
async def health_check() -> bool:
    """Return ``True`` to signal the service is up."""
    return True
