"""
qr_generator.py
---------------
QR code generation module for the Dynamic Train Seat Allocation System.

Generates a QR code image containing human-readable ticket details after
a successful payment and saves it to the qr_codes/ directory.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import qrcode

import config

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Directory where QR images are saved
# ---------------------------------------------------------------------------

QR_DIR = config.QR_DIR


def _build_readable_text(booking: dict[str, Any]) -> str:
    """Build a human-readable ticket string for QR encoding."""
    lines = [
        "SmartSeat Ticket",
        "",
        f"Ticket ID: {booking.get('ticket_id', '')}",
        f"Passenger: {booking.get('name', '')}",
        f"Age: {booking.get('age', '')}",
        f"Train: {booking.get('train_no', '')}",
        f"Coach: {booking.get('coach', '')}",
        f"Berth No: {booking.get('berth_no', '')}",
        f"Berth Type: {booking.get('berth_type', '')}",
        f"From: {booking.get('source', '')}",
        f"To: {booking.get('destination', '')}",
        f"Allocation: {booking.get('allocation_type', '')}",
        f"Price: {booking.get('price', '')}",
        f"Booked: {booking.get('booking_time', '')}",
        f"Validity: {booking.get('validity', '')}",
        f"Status: {booking.get('status', 'CONFIRMED')}",
    ]
    return "\n".join(lines)


def generate_qr(booking: dict[str, Any], output_dir: str = QR_DIR) -> str:
    """
    Generate a QR code image for the given booking and save it to disk.

    The QR encodes a human-readable ticket text (not JSON) so that it
    can be scanned and read by any standard QR scanner, phone camera,
    or Google Lens.

    Parameters
    ----------
    booking : dict
        Must contain at minimum:
            ticket_id, name, train_no, coach, berth_no, source, destination
    output_dir : str
        Directory in which the PNG image is saved.

    Returns
    -------
    str
        Absolute path to the generated QR image.
    """
    os.makedirs(output_dir, exist_ok=True)

    qr_text = _build_readable_text(booking)

    # Create QR code with error-correction level M
    qr = qrcode.QRCode(
        version=None,               # auto-determine size
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=4,
    )
    qr.add_data(qr_text)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")

    # File name: <ticket_id>.png (unique per booking)
    ticket_id = booking.get("ticket_id", "TICKET")
    filename = f"{ticket_id}.png"
    filepath = os.path.join(output_dir, filename)
    img.save(filepath)
    return filepath
