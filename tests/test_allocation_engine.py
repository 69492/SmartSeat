"""Tests for the allocation engine module."""

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
