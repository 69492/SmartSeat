"""Tests for the FastAPI application endpoints."""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

# Set up test data paths before importing app
os.environ.setdefault("DATA_DIR", os.path.join(os.path.dirname(__file__), "_test_data"))

from app import app  # noqa: E402

client = TestClient(app)


def test_health_check():
    response = client.get("/")
    assert response.status_code == 200
    body = response.json()
    assert "message" in body
    assert "docs" in body


def test_list_trains():
    response = client.get("/trains")
    assert response.status_code == 200
    trains = response.json()
    assert isinstance(trains, list)
    assert len(trains) > 0
    assert "train_no" in trains[0]


def test_get_chart():
    response = client.get("/chart/12301")
    assert response.status_code == 200
    chart = response.json()
    assert chart["train_no"] == "12301"
    assert "coaches" in chart


def test_get_chart_not_found():
    response = client.get("/chart/00000")
    assert response.status_code == 404


def test_allocate():
    response = client.post(
        "/allocate",
        json={"train_no": "12301", "from": "Howrah", "to": "New Delhi"},
    )
    # Accept 200 (allocated) or 409 (no seats) — both are valid
    assert response.status_code in (200, 409)
    if response.status_code == 200:
        body = response.json()
        assert body["status"] == "ALLOCATED"
        assert body["train_no"] == "12301"


def test_allocate_invalid_train():
    response = client.post(
        "/allocate",
        json={"train_no": "00000", "from": "A", "to": "B"},
    )
    assert response.status_code == 400


def test_simulation_get():
    response = client.get("/simulation/12301")
    assert response.status_code == 200
    body = response.json()
    assert body["train_no"] == "12301"
    assert "current_station" in body


def test_simulation_advance():
    response = client.post(
        "/simulation/advance", json={"train_no": "12301"}
    )
    assert response.status_code == 200


def test_simulation_reset():
    response = client.post(
        "/simulation/reset", json={"train_no": "12301"}
    )
    assert response.status_code == 200


def test_qr_not_found():
    response = client.get("/qr/nonexistent.png")
    assert response.status_code == 404


def test_ui_endpoint():
    response = client.get("/ui")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "SmartSeat" in response.text


def test_static_index_html():
    response = client.get("/static/index.html")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
