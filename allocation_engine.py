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
from collections import defaultdict

import config

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------

DATA_PATH = config.DATA_PATH
MAX_SEGMENT_CHAIN_LENGTH = 4
SEGMENT_OPTION_BASE_SCORE = 100
SEGMENT_OPTION_TRANSFER_PENALTY = 15


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


def _extract_vacant_intervals(
    berth: dict[str, Any],
    route: list[str],
) -> list[dict[str, Any]]:
    """Return vacant journey intervals for a berth as route-index ranges."""
    if berth["status"] == "FULL_OCCUPIED":
        return []

    if berth["status"] == "FULL_VACANT":
        return [{
            "from_idx": 0,
            "to_idx": len(route) - 1,
            "from": route[0],
            "to": route[-1],
            "availability": "FULL_VACANT",
        }]

    intervals: list[dict[str, Any]] = []
    for seg in berth.get("segments", []):
        if seg.get("status") != "VACANT":
            continue
        if seg.get("from") not in route or seg.get("to") not in route:
            continue
        from_idx = route.index(seg["from"])
        to_idx = route.index(seg["to"])
        if from_idx < to_idx:
            intervals.append({
                "from_idx": from_idx,
                "to_idx": to_idx,
                "from": seg["from"],
                "to": seg["to"],
                "availability": "PARTIAL_VACANT",
            })
    return intervals


def _build_same_berth_segments(
    intervals: list[dict[str, Any]],
    src_idx: int,
    dst_idx: int,
    route: list[str],
) -> list[dict[str, Any]] | None:
    """Build a same-berth segment chain using greedy farthest extension."""
    journey: list[dict[str, Any]] = []
    current_idx = src_idx
    ordered = sorted(intervals, key=lambda i: (i["from_idx"], i["to_idx"]))

    while current_idx < dst_idx and len(journey) < MAX_SEGMENT_CHAIN_LENGTH:
        covering = [i for i in ordered if i["from_idx"] <= current_idx < i["to_idx"]]
        if not covering:
            return None
        best = max(covering, key=lambda i: i["to_idx"])
        next_idx = min(best["to_idx"], dst_idx)
        journey.append({
            "from": route[current_idx],
            "to": route[next_idx],
            "availability": best["availability"],
        })
        current_idx = next_idx

    if current_idx < dst_idx:
        return None
    return journey


def find_segment_allocation_options(
    train_no: str,
    source: str,
    destination: str,
    data_path: str = DATA_PATH,
    max_options: int = 3,
) -> list[dict[str, Any]]:
    """
    Return fallback segment-wise allocation options within the same train.

    Each option contains one or more contiguous legs from source to destination.
    """
    data = _load_data(data_path)
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
        raise ValueError("Source must come before destination in the route.")

    by_berth: dict[tuple[str, int, str], list[dict[str, Any]]] = defaultdict(list)
    for coach in train["coaches"]:
        for berth in coach["berths"]:
            for interval in _extract_vacant_intervals(berth, route):
                by_berth[(coach["coach"], berth["berth_no"], berth["berth_type"])].append(interval)

    options: list[dict[str, Any]] = []
    for (coach, berth_no, berth_type), intervals in by_berth.items():
        segments = _build_same_berth_segments(intervals, src_idx, dst_idx, route)
        if not segments or len(segments) <= 1:
            continue
        options.append({
            "allocation_label": "Segment Allocation Option",
            "train_no": train_no,
            "continuity": "SAME_BERTH",
            "segments": [
                {
                    "coach": coach,
                    "berth_no": berth_no,
                    "berth_type": berth_type,
                    "from": leg["from"],
                    "to": leg["to"],
                    "availability": leg["availability"],
                }
                for leg in segments
            ],
            "segment_count": len(segments),
            "score": SEGMENT_OPTION_BASE_SCORE - (len(segments) - 1) * SEGMENT_OPTION_TRANSFER_PENALTY,
        })

    options.sort(key=lambda o: (-o["score"], o["segment_count"], o["segments"][0]["coach"], o["segments"][0]["berth_no"]))
    return options[:max_options]


def suggest_nearby_destinations(
    train_no: str,
    source: str,
    destination: str,
    data_path: str = DATA_PATH,
    max_options: int = 3,
) -> list[dict[str, Any]]:
    """Suggest nearest reachable stations in the same train route."""
    data = _load_data(data_path)
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
        raise ValueError("Source must come before destination in the route.")

    nearby: list[dict[str, Any]] = []
    for station_idx in range(src_idx + 1, len(route)):
        station = route[station_idx]
        if station == destination:
            continue
        direct_candidates = find_valid_berths(
            train_no,
            source,
            station,
            data_path=data_path,
        )
        segment_options = find_segment_allocation_options(
            train_no,
            source,
            station,
            data_path=data_path,
            max_options=1,
        )
        if not direct_candidates and not segment_options:
            continue
        nearby.append({
            "station": station,
            "distance_from_requested_stop": abs(station_idx - dst_idx),
            "direction": "BEFORE" if station_idx < dst_idx else "AFTER",
            "sample_option": segment_options[0] if segment_options else {
                "allocation_label": "Direct Seat Available",
                "train_no": train_no,
                "continuity": "SAME_BERTH",
                "segments": [{
                    "coach": direct_candidates[0]["coach"],
                    "berth_no": direct_candidates[0]["berth_no"],
                    "berth_type": direct_candidates[0]["berth_type"],
                    "from": source,
                    "to": station,
                    "availability": "FULL_VACANT" if direct_candidates[0]["allocation_type"] == "FULL_VACANT" else "PARTIAL_VACANT",
                }],
                "segment_count": 1,
                "score": direct_candidates[0].get("journey_distance", 1),
            },
        })

    nearby.sort(key=lambda s: (s["distance_from_requested_stop"], s["direction"] != "BEFORE"))
    return nearby[:max_options]


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
