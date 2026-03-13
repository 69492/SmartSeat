"""Tests for the data generator module."""

import json
import os

import data_generator


def test_generate_train_data_returns_list():
    data = data_generator.generate_train_data(seed=42)
    assert isinstance(data, list)
    assert len(data) == 3  # 3 predefined trains


def test_generate_train_data_reproducible():
    data1 = data_generator.generate_train_data(seed=42)
    data2 = data_generator.generate_train_data(seed=42)
    assert data1 == data2


def test_train_structure():
    data = data_generator.generate_train_data(seed=42)
    for train in data:
        assert "train_no" in train
        assert "train_name" in train
        assert "route" in train
        assert "coaches" in train
        assert len(train["coaches"]) == data_generator.COACHES_PER_TRAIN


def test_coach_has_correct_berth_count():
    data = data_generator.generate_train_data(seed=42)
    for train in data:
        for coach in train["coaches"]:
            assert len(coach["berths"]) == data_generator.BERTHS_PER_COACH


def test_save_and_load(tmp_path):
    path = os.path.join(str(tmp_path), "test_data.json")
    saved = data_generator.save_train_data(path, seed=42)
    loaded = data_generator.load_train_data(path)
    assert saved == loaded


def test_berth_statuses():
    data = data_generator.generate_train_data(seed=42)
    valid_statuses = {"FULL_OCCUPIED", "FULL_VACANT", "PARTIAL"}
    for train in data:
        for coach in train["coaches"]:
            for berth in coach["berths"]:
                assert berth["status"] in valid_statuses


def test_partial_berths_have_segments():
    data = data_generator.generate_train_data(seed=42)
    for train in data:
        for coach in train["coaches"]:
            for berth in coach["berths"]:
                if berth["status"] == "PARTIAL":
                    assert "segments" in berth
                    assert len(berth["segments"]) >= 1
