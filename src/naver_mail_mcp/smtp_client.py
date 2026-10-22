"""SMTP client for Naver Mail."""

from __future__ import annotations

import smtplib
import ssl
from email.message import EmailMessage
from email.utils import getaddresses


SMTP_HOST = "smtp.naver.com"
SMTP_PORT = 465
ALLOWED_BODY_TYPES = {"text/plain", "text/html"}


class NaverSMTPError(Exception):
    """SMTP operation failed."""


def _sanitize_header_value(value: str) -> str:
    """Strip CRLF to prevent header injection."""
    if "\r" in value or "\n" in value:
        raise ValueError("Header value contains prohibited CRLF characters.")
    return value


def send_email(
    email_address: str,
    password: str,
    full_name: str,
    to: list[str],
    subject: str,
    body: str,
    body_type: str = "text/plain",
    cc: list[str] | None = None,
    in_reply_to: str | None = None,
    references: list[str] | None = None,
) -> dict:
    """Send an email via Naver SMTP.

    For replies, provide in_reply_to (Message-ID of the email being
    replied to) and references (list of Message-IDs in the thread).
    """
    if body_type not in ALLOWED_BODY_TYPES:
        raise ValueError(f"body_type must be one of {ALLOWED_BODY_TYPES}, got '{body_type}'.")
    if not to:
        raise ValueError("At least one recipient is required.")
    for address in to + (cc or []):
        _sanitize_header_value(address)
    recipients = list(dict.fromkeys(address for _, address in getaddresses(to + (cc or []))))
    if not recipients or any(not address or "@" not in address for address in recipients):
        raise ValueError("Recipients must be valid email addresses.")

    msg = EmailMessage()
    if full_name:
        safe_name = _sanitize_header_value(full_name.strip())
        msg["From"] = f"{safe_name} <{email_address}>"
    else:
        msg["From"] = email_address
    msg["To"] = ", ".join(to)
    msg["Subject"] = _sanitize_header_value(subject)

    if cc:
        msg["Cc"] = ", ".join(cc)
    if in_reply_to:
        msg["In-Reply-To"] = _sanitize_header_value(in_reply_to)
    if references:
        msg["References"] = " ".join(_sanitize_header_value(r) for r in references)

    if body_type == "text/html":
        msg.set_content(body, subtype="html", charset="utf-8")
    else:
        msg.set_content(body, charset="utf-8")

    try:
        with smtplib.SMTP_SSL(
            SMTP_HOST, SMTP_PORT, timeout=30, context=ssl.create_default_context()
        ) as server:
            server.login(email_address, password)
            refused = server.send_message(msg, from_addr=email_address, to_addrs=recipients)
    except smtplib.SMTPAuthenticationError as e:
        raise NaverSMTPError(
            "SMTP authentication failed. "
            "Check your Naver email address and app password."
        ) from e
    except smtplib.SMTPException as e:
        raise NaverSMTPError(
            "Failed to send email. Check recipients and try again."
        ) from e
    except OSError as e:
        raise NaverSMTPError(
            f"Cannot connect to Naver SMTP server ({SMTP_HOST}:{SMTP_PORT}). "
            "Check your network connection."
        ) from e

    accepted = [address for address in recipients if address not in refused]
    return {
        "success": not refused,
        "message": "Email sent." if not refused else "Partial delivery. Do not resend to accepted recipients.",
        "accepted_recipients": accepted,
        "refused_recipients": {
            address: {
                "code": code,
                "message": reason.decode("utf-8", errors="replace") if isinstance(reason, bytes) else str(reason),
            }
            for address, (code, reason) in refused.items()
        },
    }
