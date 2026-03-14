"""
email_sender.py
---------------
SMTP-based email delivery module for the Dynamic Train Seat Allocation System.

Sends booking confirmation emails with ticket details and an attached QR code
image.  Credentials are read from environment variables via ``config.py``.
If SMTP is not configured the module logs a warning and returns gracefully.
"""

from __future__ import annotations

import logging
import os
import smtplib
from email.message import EmailMessage
from typing import Any

import config

logger = logging.getLogger(__name__)


def _smtp_configured() -> bool:
    """Return True when the minimum SMTP settings are present."""
    return bool(config.SMTP_HOST and config.SMTP_USER and config.SMTP_PASS)


def send_ticket_email(
    ticket: dict[str, Any],
    qr_path: str | None = None,
) -> str:
    """
    Send a booking confirmation email for *ticket*.

    Parameters
    ----------
    ticket : dict
        Must contain at minimum: ticket_id, name, email, train_no, coach,
        berth_no, berth_type, source, destination, allocation_type, price,
        booking_time, validity.
    qr_path : str | None
        Absolute path to the QR code PNG to attach.  Skipped when ``None``.

    Returns
    -------
    str
        ``"sent"`` on success, ``"skipped"`` when SMTP is not configured, or
        ``"failed"`` on error.
    """
    if not _smtp_configured():
        logger.warning("SMTP not configured — skipping email delivery.")
        return "skipped"

    recipient = ticket.get("email", "")
    if not recipient:
        logger.warning("No recipient email — skipping email delivery.")
        return "skipped"

    msg = EmailMessage()
    msg["Subject"] = f"SmartSeat Booking Confirmation — {ticket.get('ticket_id', '')}"
    msg["From"] = config.SMTP_FROM
    msg["To"] = recipient

    body = (
        f"Dear {ticket.get('name', 'Passenger')},\n\n"
        f"Your booking has been confirmed!  Here are your ticket details:\n\n"
        f"  Ticket ID       : {ticket.get('ticket_id', '')}\n"
        f"  Train           : {ticket.get('train_no', '')}\n"
        f"  Coach           : {ticket.get('coach', '')}\n"
        f"  Berth No.       : {ticket.get('berth_no', '')}\n"
        f"  Berth Type      : {ticket.get('berth_type', '')}\n"
        f"  From            : {ticket.get('source', '')}\n"
        f"  To              : {ticket.get('destination', '')}\n"
        f"  Allocation Type : {ticket.get('allocation_type', '')}\n"
        f"  Price           : ₹{ticket.get('price', '')}\n"
        f"  Booking Time    : {ticket.get('booking_time', '')}\n"
        f"  Validity        : {ticket.get('validity', '')}\n\n"
        f"Thank you for choosing SmartSeat!\n"
    )
    msg.set_content(body)

    # Attach QR code image if available
    if qr_path and os.path.isfile(qr_path):
        with open(qr_path, "rb") as f:
            img_data = f.read()
        msg.add_attachment(
            img_data,
            maintype="image",
            subtype="png",
            filename=os.path.basename(qr_path),
        )

    try:
        with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=15) as server:
            server.ehlo()
            server.starttls()
            server.login(config.SMTP_USER, config.SMTP_PASS)
            server.send_message(msg)
        logger.info("Ticket email sent to %s", recipient)
        return "sent"
    except Exception:
        logger.exception("Failed to send ticket email to %s", recipient)
        return "failed"
