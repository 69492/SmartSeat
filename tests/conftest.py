"""
Shared test fixtures for the SmartSeat test suite.
"""

from __future__ import annotations

import json
import os
import tempfile

import pytest

import data_generator


@pytest.fixture()
def tmp_data_dir(tmp_path):
    """Provide a temporary directory pre-populated with generated train data."""
    data_path = os.path.join(str(tmp_path), "train_data.json")
    data_generator.save_train_data(data_path, seed=42)
    return str(tmp_path), data_path


@pytest.fixture()
def train_data(tmp_data_dir):
    """Return the generated train data as a Python list."""
    _, data_path = tmp_data_dir
    return data_generator.load_train_data(data_path)
