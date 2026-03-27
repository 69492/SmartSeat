"""
data_generator.py
-----------------
Generates realistic IRCTC-style train data for the Dynamic Train Seat
Allocation System.  All data is simulated — no external APIs are used.

Distribution of berth status (approximate):
  - FULL_OCCUPIED : ~65 %
  - FULL_VACANT   : ~20 %
  - PARTIAL       : ~15 %

Saved to data/train_data.json.
"""

import json
import logging
import os
import random
from datetime import datetime, timedelta
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

COACHES_PER_TRAIN = 4          # S1 … S4
BERTHS_PER_COACH  = 72         # Standard sleeper coach

# Weight probabilities for berth status
STATUS_WEIGHTS = {
    "FULL_OCCUPIED": 0.65,
    "FULL_VACANT":   0.20,
    "PARTIAL":       0.15,
}

# Pre-defined train routes (station lists are ordered)
TRAIN_ROUTES: list[dict[str, Any]] = [
    {
        "train_no":   "12301",
        "train_name": "Howrah Rajdhani Express",
        "route": [
            "Howrah", "Asansol", "Dhanbad", "Gaya", "Mughalsarai",
            "Allahabad", "Kanpur", "Agra", "Mathura", "New Delhi",
        ],
    },
    {
        "train_no":   "12951",
        "train_name": "Mumbai Rajdhani Express",
        "route": [
            "Mumbai Central", "Surat", "Vadodara", "Ratlam",
            "Kota", "Sawai Madhopur", "Bharatpur", "New Delhi",
        ],
    },
    {
        "train_no":   "12627",
        "train_name": "Karnataka Express",
        "route": [
            "Bangalore City", "Tumkur", "Arsikere", "Davangere",
            "Hubli", "Dharwad", "Belagavi", "Miraj", "Pune",
            "Dadar", "Mumbai CST",
        ],
    },
]

BERTH_TYPES = ["LB", "MB", "UB", "SL", "SU"]   # Lower / Middle / Upper / Side-Lower / Side-Upper


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def _choose_status() -> str:
    """Return a random berth status according to configured weights."""
    population = list(STATUS_WEIGHTS.keys())
    weights    = list(STATUS_WEIGHTS.values())
    return random.choices(population, weights=weights, k=1)[0]


def _generate_partial_segments(route: list[str]) -> list[dict[str, Any]]:
    """
    Build a segment list for a PARTIAL berth.

    The route is divided into 2–4 contiguous segments, each independently
    marked VACANT or OCCUPIED, ensuring at least one of each type exists.
    """
    num_stations = len(route)
    # Need at least 4 stations to make meaningful segments
    if num_stations < 4:
        return [{"from": route[0], "to": route[-1], "status": "OCCUPIED"}]

    # Choose 1–3 internal cut-points (sorted, unique)
    max_cuts   = min(3, num_stations - 2)
    num_cuts   = random.randint(1, max_cuts)
    cut_points = sorted(random.sample(range(1, num_stations - 1), num_cuts))

    # Build segments from cut-points
    boundaries = [0] + cut_points + [num_stations - 1]
    segments: list[dict[str, Any]] = []
    for i in range(len(boundaries) - 1):
        segments.append({
            "from":   route[boundaries[i]],
            "to":     route[boundaries[i + 1]],
            "status": random.choice(["VACANT", "OCCUPIED"]),
        })

    # Guarantee at least one VACANT and one OCCUPIED segment
    if not any(s["status"] == "VACANT" for s in segments):
        segments[0]["status"] = "VACANT"
    if not any(s["status"] == "OCCUPIED" for s in segments):
        segments[-1]["status"] = "OCCUPIED"

    return segments


def _generate_berth(berth_no: int, route: list[str]) -> dict[str, Any]:
    """Create a single berth record."""
    status     = _choose_status()
    berth_type = BERTH_TYPES[(berth_no - 1) % len(BERTH_TYPES)]

    berth: dict[str, Any] = {
        "berth_no":   berth_no,
        "berth_type": berth_type,
        "status":     status,
    }

    if status == "PARTIAL":
        berth["segments"] = _generate_partial_segments(route)

    return berth


def _generate_coach(coach_name: str, route: list[str]) -> dict[str, Any]:
    """Create one sleeper coach with all its berths."""
    return {
        "coach": coach_name,
        "berths": [_generate_berth(n, route) for n in range(1, BERTHS_PER_COACH + 1)],
    }


def _build_station_schedule(route: list[str], start_time: str = "09:00") -> list[dict[str, str]]:
    """
    Build a deterministic station-arrival timetable for a route.

    Each station entry has:
      - code: station identifier used by booking flow (station name here)
      - arrival: HH:MM
    """
    base_time = datetime.strptime(start_time, "%H:%M")
    schedule: list[dict[str, str]] = []
    current = base_time
    for idx, station in enumerate(route):
        if idx > 0:
            # Deterministic interval pattern (realistic 35–50 min gaps)
            current += timedelta(minutes=35 + ((idx - 1) % 4) * 5)
        schedule.append({
            "code": station,
            "arrival": current.strftime("%H:%M"),
        })
    return schedule


def generate_train_data(seed: int | None = None) -> list[dict[str, Any]]:
    """
    Generate data for all configured trains and return it as a Python list.

    Parameters
    ----------
    seed : int, optional
        Random seed for reproducibility.
    """
    if seed is not None:
        random.seed(seed)

    trains: list[dict[str, Any]] = []
    for index, template in enumerate(TRAIN_ROUTES):
        coach_names = [f"S{i}" for i in range(1, COACHES_PER_TRAIN + 1)]
        coaches     = [_generate_coach(name, template["route"]) for name in coach_names]
        start_hour = 6 + (index * 2)
        trains.append({
            "train_no":   template["train_no"],
            "train_name": template["train_name"],
            "route":      template["route"],
            "stations":   _build_station_schedule(template["route"], f"{start_hour:02d}:00"),
            "coaches":    coaches,
        })
    return trains


def save_train_data(path: str = "data/train_data.json", seed: int | None = 42) -> list[dict[str, Any]]:
    """
    Generate train data, save to *path*, and return the data.

    Parameters
    ----------
    path : str
        Output file path (relative to project root or absolute).
    seed : int, optional
        Random seed passed to :func:`generate_train_data`.
    """
    data = generate_train_data(seed=seed)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
    logger.info("Saved %d trains → %s", len(data), path)
    return data


def load_train_data(path: str = "data/train_data.json") -> list[dict[str, Any]]:
    """Load and return train data from a JSON file."""
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    save_train_data()
