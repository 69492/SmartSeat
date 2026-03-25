"""
qr_generator.py
---------------
QR code generation module for the Dynamic Train Seat Allocation System.

Generates a QR code image containing human-readable ticket details after
a successful payment and saves it to the qr_codes/ directory.
"""

from __future__ import annotations

import logging
import json
import os
from typing import Any

import qrcode

import config

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Directory where QR images are saved
# ---------------------------------------------------------------------------

QR_DIR = config.QR_DIR


def _build_qr_payload(booking: dict[str, Any]) -> str:
    """Build a structured QR payload for scanner-side verification."""
    payload = {
        "ticket_id": booking.get("ticket_id", ""),
        "passenger_name": booking.get("name", ""),
        "train_no": booking.get("train_no", ""),
        "journey": {
            "source": booking.get("source", ""),
            "destination": booking.get("destination", ""),
        },
        "seat": {
            "coach": booking.get("coach", ""),
            "berth_no": booking.get("berth_no", ""),
            "berth_type": booking.get("berth_type", ""),
            "allocation_type": booking.get("allocation_type", ""),
        },
        "valid_from": booking.get("valid_from", ""),
        "valid_until": booking.get("valid_until", ""),
        "status": booking.get("status", "CONFIRMED"),
    }
    return json.dumps(payload, separators=(",", ":"), ensure_ascii=False)


def generate_qr(booking: dict[str, Any], output_dir: str = QR_DIR) -> str:
    """
    Generate a QR code image for the given booking and save it to disk.

    The QR encodes structured JSON so verification clients can parse
    validity times and ticket details reliably.

    Parameters
    ----------
    booking : dict
        Booking/ticket data. The following keys are used (all optional,
        absent keys produce empty strings):
            ticket_id, name, age, train_no, coach, berth_no, berth_type,
            source, destination, allocation_type, price, booking_time,
            validity, status
    output_dir : str
        Directory in which the PNG image is saved.

    Returns
    -------
    str
        Absolute path to the generated QR image.
    """
    os.makedirs(output_dir, exist_ok=True)

    qr_text = _build_qr_payload(booking)

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
