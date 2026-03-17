"""Tests for the allocation engine module."""

import json
import os

import data_generator
import allocation_engine


def test_find_valid_berths_returns_list(tmp_data_dir):
    _, data_path = tmp_data_dir
    candidates = allocation_engine.find_valid_berths(
        "12301", "Howrah", "New Delhi", data_path
    )
    assert isinstance(candidates, list)


def test_find_valid_berths_has_expected_keys(tmp_data_dir):
    _, data_path = tmp_data_dir
    candidates = allocation_engine.find_valid_berths(
        "12301", "Howrah", "New Delhi", data_path
    )
    if candidates:
        c = candidates[0]
        assert "train_no" in c
        assert "coach" in c
        assert "berth_no" in c
        assert "berth_type" in c
        assert "allocation_type" in c


def test_find_valid_berths_invalid_train(tmp_data_dir):
    _, data_path = tmp_data_dir
    try:
        allocation_engine.find_valid_berths("00000", "A", "B", data_path)
        assert False, "Should have raised ValueError"
    except ValueError:
        pass


def test_find_valid_berths_invalid_station(tmp_data_dir):
    _, data_path = tmp_data_dir
    try:
        allocation_engine.find_valid_berths("12301", "Nowhere", "New Delhi", data_path)
        assert False, "Should have raised ValueError"
    except ValueError:
        pass


def test_source_before_destination(tmp_data_dir):
    _, data_path = tmp_data_dir
    try:
        allocation_engine.find_valid_berths(
            "12301", "New Delhi", "Howrah", data_path
        )
        assert False, "Should have raised ValueError"
    except ValueError:
        pass


def test_allocate_and_release(tmp_data_dir):
    _, data_path = tmp_data_dir
    candidates = allocation_engine.find_valid_berths(
        "12301", "Howrah", "New Delhi", data_path
    )
    assert len(candidates) > 0

    allocated = allocation_engine.allocate_seat(
        "12301", "Howrah", "New Delhi", data_path, ranked_berth=candidates[0]
    )
    assert allocated["train_no"] == "12301"

    # Release the seat
    released = allocation_engine.release_seat(
        "12301",
        allocated["coach"],
        allocated["berth_no"],
        "Howrah",
        "New Delhi",
        data_path,
    )
    assert isinstance(released, dict)


def test_find_segment_allocation_options(tmp_path):
    data_path = os.path.join(str(tmp_path), "train_data.json")
    custom_data = [
        {
            "train_no": "T100",
            "train_name": "Test Train",
            "route": ["A", "B", "C", "D"],
            "coaches": [
                {
                    "coach": "S1",
                    "berths": [
                        {
                            "berth_no": 1,
                            "berth_type": "LB",
                            "status": "PARTIAL",
                            "segments": [
                                {"from": "A", "to": "B", "status": "VACANT"},
                                {"from": "B", "to": "D", "status": "VACANT"},
                            ],
                        }
                    ],
                }
            ],
        }
    ]
    with open(data_path, "w", encoding="utf-8") as fh:
        json.dump(custom_data, fh)

    options = allocation_engine.find_segment_allocation_options(
        "T100", "A", "D", data_path
    )
    assert options
    assert options[0]["allocation_label"] == "Segment Allocation Option"
    assert options[0]["continuity"] == "SAME_BERTH"
    assert len(options[0]["segments"]) == 2


def test_suggest_nearby_destinations(tmp_path):
    data_path = os.path.join(str(tmp_path), "train_data.json")
    custom_data = [
        {
            "train_no": "T101",
            "train_name": "Nearby Train",
            "route": ["A", "B", "C", "D", "E"],
            "coaches": [
                {
                    "coach": "S1",
                    "berths": [
                        {
                            "berth_no": 2,
                            "berth_type": "UB",
                            "status": "PARTIAL",
                            "segments": [
                                {"from": "A", "to": "C", "status": "VACANT"},
                                {"from": "C", "to": "D", "status": "OCCUPIED"},
                                {"from": "D", "to": "E", "status": "OCCUPIED"},
                            ],
                        }
                    ],
                }
            ],
        }
    ]
    with open(data_path, "w", encoding="utf-8") as fh:
        json.dump(custom_data, fh)

    nearby = allocation_engine.suggest_nearby_destinations(
        "T101", "A", "D", data_path
    )
    assert nearby
    assert nearby[0]["station"] == "C"
