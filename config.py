"""
config.py
---------
Centralized configuration for the Dynamic Train Seat Allocation System.

All settings are loaded from environment variables with sensible defaults,
making the application configurable across development, staging, and
production environments without code changes.
"""

from __future__ import annotations

import os

# ---------------------------------------------------------------------------
# Server
# ---------------------------------------------------------------------------

HOST: str = os.getenv("API_HOST", "0.0.0.0")
PORT: int = int(os.getenv("API_PORT", "5000"))
RELOAD: bool = os.getenv("API_RELOAD", "false").lower() == "true"
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "info").lower()

# Comma-separated list of allowed CORS origins; "*" permits all origins.
CORS_ORIGINS: list[str] = [
    o.strip()
    for o in os.getenv("CORS_ORIGINS", "*").split(",")
    if o.strip()
]

# Enable CORS credentials (cookies, authorization headers, etc.)
CORS_ALLOW_CREDENTIALS: bool = os.getenv("CORS_ALLOW_CREDENTIALS", "true").lower() == "true"

# ---------------------------------------------------------------------------
# Data paths
# ---------------------------------------------------------------------------

_BASE_DIR: str = os.path.dirname(__file__)

DATA_DIR: str = os.getenv("DATA_DIR", os.path.join(_BASE_DIR, "data"))
DATA_PATH: str = os.path.join(DATA_DIR, "train_data.json")
SIMULATION_STATE_PATH: str = os.path.join(DATA_DIR, "simulation_state.json")
QR_DIR: str = os.getenv("QR_DIR", os.path.join(_BASE_DIR, "qr_codes"))

# ---------------------------------------------------------------------------
# Data generation
# ---------------------------------------------------------------------------

DATA_SEED: int = int(os.getenv("DATA_SEED", "42"))

# ---------------------------------------------------------------------------
# ML model
# ---------------------------------------------------------------------------

ML_MAX_DEPTH: int = int(os.getenv("ML_MAX_DEPTH", "6"))
ML_RANDOM_STATE: int = int(os.getenv("ML_RANDOM_STATE", "42"))
ML_TRAINING_SAMPLES: int = int(os.getenv("ML_TRAINING_SAMPLES", "500"))
