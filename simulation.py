"""
simulation.py
-------------
Real-time train position simulation for the Dynamic Train Seat Allocation
System.

Each train maintains a "current station pointer" that can be advanced by the
API.  When the pointer moves past a station, all berths whose passengers had
that station as their destination are automatically released.
"""

from __future__ import annotations

import json
import os
from typing import Any

from allocation_engine import _load_data, _save_data, _find_train

# ---------------------------------------------------------------------------
# State file — tracks current station index per train
# ---------------------------------------------------------------------------

_STATE_PATH = os.path.join(os.path.dirname(__file__), "data", "simulation_state.json")


def _load_state() -> dict[str, int]:
    """Return {train_no: current_station_index} mapping."""
    if os.path.exists(_STATE_PATH):
        with open(_STATE_PATH, "r", encoding="utf-8") as fh:
            return json.load(fh)
    return {}


def _save_state(state: dict[str, int]) -> None:
    os.makedirs(os.path.dirname(_STATE_PATH), exist_ok=True)
    with open(_STATE_PATH, "w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=2)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_current_station(train_no: str) -> dict[str, Any]:
    """Return the current station name and index for a train."""
    state = _load_state()
    data  = _load_data()
    train = _find_train(data, train_no)
    if train is None:
        raise ValueError(f"Train '{train_no}' not found.")

    idx  = state.get(train_no, 0)
    route = train["route"]
    return {
        "train_no":       train_no,
        "current_index":  idx,
        "current_station": route[idx] if idx < len(route) else route[-1],
        "route":          route,
    }


def advance_station(train_no: str, data_path: str | None = None) -> dict[str, Any]:
    """
    Advance the current station pointer by one stop and release any berths
    whose passengers have reached their destination.

    Returns the updated station info dict.
    """
    from allocation_engine import DATA_PATH as _DATA_PATH

    dp    = data_path or _DATA_PATH
    state = _load_state()
    data  = _load_data(dp)
    train = _find_train(data, train_no)
    if train is None:
        raise ValueError(f"Train '{train_no}' not found.")

    route = train["route"]
    idx   = state.get(train_no, 0)

    if idx >= len(route) - 1:
        return {
            "train_no":        train_no,
            "current_index":   idx,
            "current_station": route[-1],
            "message":         "Train has reached its final destination.",
        }

    # Advance
    idx += 1
    state[train_no] = idx
    _save_state(state)

    current_station = route[idx]

    # Release PARTIAL segments for passengers who arrived at current_station
    released: list[dict[str, Any]] = []
    for coach in train["coaches"]:
        for berth in coach["berths"]:
            if berth["status"] not in ("PARTIAL", "FULL_OCCUPIED"):
                continue
            if berth.get("segments"):
                for seg in berth["segments"]:
                    if seg["status"] == "OCCUPIED" and seg["to"] == current_station:
                        seg["status"] = "VACANT"
                        released.append({
                            "coach":    coach["coach"],
                            "berth_no": berth["berth_no"],
                            "seg_from": seg["from"],
                            "seg_to":   seg["to"],
                        })
                # Recalculate berth-level status
                if any(s["status"] == "VACANT" for s in berth["segments"]):
                    berth["status"] = "PARTIAL"

    _save_data(data, dp)

    return {
        "train_no":        train_no,
        "current_index":   idx,
        "current_station": current_station,
        "released_segments": released,
    }


def reset_simulation(train_no: str) -> dict[str, str]:
    """Reset the station pointer for a train to the first station."""
    state = _load_state()
    state[train_no] = 0
    _save_state(state)
    return {"train_no": train_no, "message": "Simulation reset to origin."}
