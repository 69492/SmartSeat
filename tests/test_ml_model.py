"""Tests for the ML model module."""

import ml_model


def test_berth_type_map_has_all_types():
    expected = {"LB", "MB", "UB", "SL", "SU"}
    assert set(ml_model.BERTH_TYPE_MAP.keys()) == expected


def test_encode_candidate():
    candidate = {
        "berth_type": "LB",
        "allocation_type": "FULL_VACANT",
        "coach": "S1",
        "berth_no": 1,
        "journey_distance": 5,
    }
    features = ml_model._encode_candidate(candidate)
    assert len(features) == 5
    assert features[0] == 5        # journey_distance
    assert features[1] == 0        # LB encoding
    assert features[2] == 1        # is_full_vacant


def test_get_best_berth_returns_candidate():
    candidates = [
        {
            "train_no": "12301",
            "coach": "S1",
            "berth_no": 1,
            "berth_type": "LB",
            "status": "FULL_VACANT",
            "allocation_type": "FULL_VACANT",
            "segment": None,
            "journey_distance": 9,
            "route": ["A", "B"],
        },
        {
            "train_no": "12301",
            "coach": "S2",
            "berth_no": 50,
            "berth_type": "SU",
            "status": "FULL_VACANT",
            "allocation_type": "FULL_VACANT",
            "segment": None,
            "journey_distance": 2,
            "route": ["A", "B"],
        },
    ]
    best = ml_model.get_best_berth(candidates)
    assert best in candidates


def test_get_best_berth_single_candidate():
    candidates = [
        {
            "train_no": "12301",
            "coach": "S1",
            "berth_no": 1,
            "berth_type": "LB",
            "status": "FULL_VACANT",
            "allocation_type": "FULL_VACANT",
            "segment": None,
            "journey_distance": 5,
            "route": ["A", "B"],
        },
    ]
    best = ml_model.get_best_berth(candidates)
    assert best == candidates[0]
