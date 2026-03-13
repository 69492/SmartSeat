"""
allocation_engine.py
--------------------
CSP-based seat allocation engine for the Dynamic Train Seat Allocation
System.

Constraint Satisfaction Problem (CSP) rules
============================================
1. FULL_OCCUPIED berths are never considered.
2. FULL_VACANT berths are always valid.
3. PARTIAL berths are valid if the requested journey [source → destination]
   fits *entirely inside* a VACANT segment of that berth:
       segment.from_idx <= source_idx  AND  segment.to_idx >= destination_idx
   (indices are derived from the train's ordered route list)

The engine returns *all* valid berths and then delegates ranking to the ML
module (ml_model.py).  If ML is unavailable, the first valid berth is used.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

import config

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------

DATA_PATH = config.DATA_PATH


def _load_data(path: str = DATA_PATH) -> list[dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _save_data(data: list[dict[str, Any]], path: str = DATA_PATH) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)


def _find_train(data: list[dict[str, Any]], train_no: str) -> dict[str, Any] | None:
    for train in data:
        if train["train_no"] == train_no:
            return train
    return None


# ---------------------------------------------------------------------------
# Validity check
# ---------------------------------------------------------------------------

def _is_berth_valid(
    berth: dict[str, Any],
    src_idx: int,
    dst_idx: int,
) -> tuple[bool, str, dict[str, Any] | None]:
    """
    Check whether *berth* is a valid choice for a journey from *src_idx* to
    *dst_idx* (station indices within the route).

    Returns
    -------
    (valid, allocation_type, matched_segment)
        - valid            : True if this berth can be allocated
        - allocation_type  : "FULL_VACANT" | "PARTIAL"
        - matched_segment  : The segment dict (only for PARTIAL), else None
    """
    status = berth["status"]

    if status == "FULL_OCCUPIED":
        return False, "", None

    if status == "FULL_VACANT":
        return True, "FULL_VACANT", None

    # PARTIAL — check segment-level availability
    if status == "PARTIAL":
        for seg in berth.get("segments", []):
            if seg["status"] != "VACANT":
                continue
            # Compare using indices stored in the segment
            seg_from_idx = seg.get("from_idx", -1)
            seg_to_idx   = seg.get("to_idx",   -1)
            if seg_from_idx <= src_idx and seg_to_idx >= dst_idx:
                return True, "PARTIAL", seg
    return False, "", None


# ---------------------------------------------------------------------------
# Core allocation function
# ---------------------------------------------------------------------------

def find_valid_berths(
    train_no: str,
    source: str,
    destination: str,
    data_path: str = DATA_PATH,
) -> list[dict[str, Any]]:
    """
    Return all valid berths (as candidate dicts) for the requested journey.

    Each candidate dict contains:
        train_no, coach, berth_no, berth_type, status, allocation_type,
        segment (or None), journey_distance, route
    """
    data  = _load_data(data_path)
    train = _find_train(data, train_no)
    if train is None:
        raise ValueError(f"Train '{train_no}' not found.")

    route = train["route"]
    if source not in route:
        raise ValueError(f"Station '{source}' not in route {route}.")
    if destination not in route:
        raise ValueError(f"Station '{destination}' not in route {route}.")

    src_idx = route.index(source)
    dst_idx = route.index(destination)
    if src_idx >= dst_idx:
        raise ValueError(f"Source must come before destination in the route.")

    # Pre-compute indices for all segments once for this request
    candidates: list[dict[str, Any]] = []
    for coach in train["coaches"]:
        for berth in coach["berths"]:
            # Inject from_idx / to_idx into PARTIAL segments for comparison
            if berth["status"] == "PARTIAL":
                for seg in berth.get("segments", []):
                    seg["from_idx"] = route.index(seg["from"]) if seg["from"] in route else -1
                    seg["to_idx"]   = route.index(seg["to"])   if seg["to"]   in route else -1

            valid, alloc_type, matched_seg = _is_berth_valid(berth, src_idx, dst_idx)
            if valid:
                candidates.append({
                    "train_no":        train_no,
                    "coach":           coach["coach"],
                    "berth_no":        berth["berth_no"],
                    "berth_type":      berth["berth_type"],
                    "status":          berth["status"],
                    "allocation_type": alloc_type,
                    "segment":         matched_seg,
                    "journey_distance": dst_idx - src_idx,
                    "route":           route,
                })
    return candidates


def allocate_seat(
    train_no: str,
    source: str,
    destination: str,
    data_path: str = DATA_PATH,
    ranked_berth: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Allocate a seat and persist the updated status to disk.

    If *ranked_berth* is provided (from the ML module), that berth is used;
    otherwise the first valid candidate is chosen.

    Returns the allocated berth dict (same structure as :func:`find_valid_berths`
    candidates).
    """
    candidates = find_valid_berths(train_no, source, destination, data_path)
    if not candidates:
        raise RuntimeError("No valid berths available for the requested journey.")

    chosen = ranked_berth if ranked_berth is not None else candidates[0]

    # Persist the allocation
    data  = _load_data(data_path)
    train = _find_train(data, train_no)
    route = train["route"]
    src_idx = route.index(source)
    dst_idx = route.index(destination)

    for coach in train["coaches"]:
        if coach["coach"] != chosen["coach"]:
            continue
        for berth in coach["berths"]:
            if berth["berth_no"] != chosen["berth_no"]:
                continue

            if chosen["allocation_type"] == "FULL_VACANT":
                berth["status"] = "FULL_OCCUPIED"

            elif chosen["allocation_type"] == "PARTIAL":
                # Mark the matched vacant segment as OCCUPIED
                seg_ref = chosen["segment"]
                for seg in berth.get("segments", []):
                    if seg["from"] == seg_ref["from"] and seg["to"] == seg_ref["to"]:
                        seg["status"] = "OCCUPIED"
                        break
                # If all segments are OCCUPIED, promote the berth
                if all(s["status"] == "OCCUPIED" for s in berth.get("segments", [])):
                    berth["status"] = "FULL_OCCUPIED"
            break
        break

    _save_data(data, data_path)
    return chosen


def release_seat(
    train_no: str,
    coach: str,
    berth_no: int,
    source: str,
    destination: str,
    data_path: str = DATA_PATH,
) -> dict[str, Any]:
    """
    Release a previously allocated berth segment and return the updated berth.

    For a FULL_OCCUPIED berth (originally FULL_VACANT), the berth is reset to
    FULL_VACANT.  For a PARTIAL berth, only the matching segment is freed.
    """
    data  = _load_data(data_path)
    train = _find_train(data, train_no)
    if train is None:
        raise ValueError(f"Train '{train_no}' not found.")

    route = train["route"]

    for coach_obj in train["coaches"]:
        if coach_obj["coach"] != coach:
            continue
        for berth in coach_obj["berths"]:
            if berth["berth_no"] != berth_no:
                continue

            if berth["status"] == "FULL_OCCUPIED" and not berth.get("segments"):
                berth["status"] = "FULL_VACANT"
            elif berth.get("segments"):
                for seg in berth["segments"]:
                    if seg["from"] == source and seg["to"] == destination:
                        seg["status"] = "VACANT"
                # Promote back to PARTIAL if not all OCCUPIED
                if any(s["status"] == "VACANT" for s in berth["segments"]):
                    berth["status"] = "PARTIAL"
            _save_data(data, data_path)
            return berth

    raise ValueError(f"Berth {berth_no} in coach {coach} not found for train {train_no}.")
