"""Tests for the configuration module."""

import os

import config


def test_default_host():
    assert config.HOST == os.getenv("API_HOST", "0.0.0.0")


def test_default_port():
    assert isinstance(config.PORT, int)
    assert config.PORT > 0


def test_default_log_level():
    assert config.LOG_LEVEL in ("debug", "info", "warning", "error", "critical")


def test_data_path_exists_as_string():
    assert isinstance(config.DATA_PATH, str)
    assert config.DATA_PATH.endswith("train_data.json")
