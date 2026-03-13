"""
qr_generator.py
---------------
QR code generation module for the Dynamic Train Seat Allocation System.

Generates a QR code image containing booking details after a successful
seat allocation and saves it to the qr_codes/ directory.
"""

from __future__ import annotations

import json
import os
from typing import Any

import qrcode

# ---------------------------------------------------------------------------
# Directory where QR images are saved
# ---------------------------------------------------------------------------

QR_DIR = os.path.join(os.path.dirname(__file__), "qr_codes")


def generate_qr(booking: dict[str, Any], output_dir: str = QR_DIR) -> str:
    """
    Generate a QR code image for the given booking and save it to disk.

    Parameters
    ----------
    booking : dict
        Must contain at minimum:
            train_no, coach, berth_no, source, destination, allocation_type
    output_dir : str
        Directory in which the PNG image is saved.

    Returns
    -------
    str
        Absolute path to the generated QR image.
    """
    os.makedirs(output_dir, exist_ok=True)

    # Build the payload string embedded in the QR code
    payload = {
        "train_no":        booking.get("train_no", ""),
        "coach":           booking.get("coach", ""),
        "berth_no":        booking.get("berth_no", ""),
        "berth_type":      booking.get("berth_type", ""),
        "source":          booking.get("source", ""),
        "destination":     booking.get("destination", ""),
        "allocation_type": booking.get("allocation_type", ""),
    }

    # Include segment details for PARTIAL allocations
    segment = booking.get("segment")
    if segment:
        payload["segment_from"] = segment.get("from", "")
        payload["segment_to"]   = segment.get("to", "")

    qr_text = json.dumps(payload, ensure_ascii=False)

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

    # File name: <train_no>_<coach>_<berth_no>.png
    filename = (
        f"{booking.get('train_no', 'TRAIN')}"
        f"_{booking.get('coach', 'C')}"
        f"_{booking.get('berth_no', 0)}.png"
    )
    filepath = os.path.join(output_dir, filename)
    img.save(filepath)
    return filepath
