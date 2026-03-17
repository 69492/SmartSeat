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
        assert "qr_code" not in body


def test_search_trains_by_stations():
    response = client.post(
        "/trains/search",
        json={"from": "Howrah", "to": "New Delhi"},
    )
    assert response.status_code == 200
    trains = response.json()
    assert isinstance(trains, list)
    assert any(t["train_no"] == "12301" for t in trains)


def test_recommendations_endpoint():
    response = client.post(
        "/recommendations",
        json={"train_no": "12301", "from": "Howrah", "to": "New Delhi"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["train_no"] == "12301"
    assert "recommendations" in body
    assert "segment_allocation_options" in body
    assert "nearby_station_options" in body
    assert len(body["recommendations"]) <= 3


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


def test_ui_qr_download_button():
    """Test that the QR download button uses fetch+blob (no target=_blank)."""
    response = client.get("/ui")
    assert response.status_code == 200
    html = response.text
    # Button text must be "Download QR Ticket"
    assert "Download QR Ticket" in html
    # Must NOT open a new tab
    assert 'a.target = "_blank"' not in html
    # Must use fetch+blob download approach
    assert "URL.createObjectURL" in html
    # Filename must start with SmartSeat_Ticket_
    assert "SmartSeat_Ticket_" in html


def test_ui_uses_deployed_backend_for_train_search():
    """UI should call deployed backend POST /trains/search with source/destination JSON."""
    response = client.get("/ui")
    assert response.status_code == 200
    html = response.text
    assert 'const API_BASE = "https://smartseat-d91a.onrender.com";' in html
    assert 'fetch(API_BASE + "/trains/search"' in html
    assert 'method: "POST"' in html
    assert 'JSON.stringify({ source: source, destination: dest })' in html


# ---------------------------------------------------------------------------
# CORS tests
# ---------------------------------------------------------------------------

def test_cors_preflight_request():
    """Test that CORS preflight requests return proper headers."""
    response = client.options(
        "/allocate",
        headers={
            "Origin": "https://example.com",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Content-Type",
        },
    )
    assert response.status_code == 200
    assert "access-control-allow-origin" in response.headers
    assert "access-control-allow-methods" in response.headers
    assert "access-control-allow-headers" in response.headers


def test_cors_headers_on_json_request():
    """Test that CORS headers are returned for cross-origin JSON requests."""
    response = client.get(
        "/trains",
        headers={"Origin": "https://example.com"},
    )
    assert response.status_code == 200
    assert "access-control-allow-origin" in response.headers
    assert "access-control-allow-credentials" in response.headers


def test_cors_headers_on_post_request():
    """Test that CORS headers are returned for POST requests with JSON body."""
    response = client.post(
        "/simulation/reset",
        json={"train_no": "12301"},
        headers={"Origin": "https://example.com"},
    )
    assert response.status_code == 200
    assert "access-control-allow-origin" in response.headers


# ---------------------------------------------------------------------------
# Booking tests
# ---------------------------------------------------------------------------

def test_book_ticket():
    """Test the full booking flow via POST /book_ticket."""
    response = client.post(
        "/book_ticket",
        json={
            "train_no": "12301",
            "from": "Howrah",
            "to": "New Delhi",
            "name": "Test User",
            "age": 25,
        },
    )
    # Accept 200 (booked) or 409 (no seats) — both are valid
    assert response.status_code in (200, 409)
    if response.status_code == 200:
        body = response.json()
        assert "ticket_id" in body
        assert body["ticket_id"].startswith("SM-")
        assert "seat_details" in body
        assert body["seat_details"]["train_no"] == "12301"
        assert "price" in body
        assert "booking_time" in body
        assert "validity" in body
        assert "qr_url" in body
        assert body["status"] == "CONFIRMED"
        assert body["name"] == "Test User"
        assert body["age"] == 25


def test_book_ticket_with_email():
    """Test booking with optional email still works."""
    response = client.post(
        "/book_ticket",
        json={
            "train_no": "12301",
            "from": "Howrah",
            "to": "New Delhi",
            "name": "Test User",
            "age": 25,
            "email": "test@example.com",
        },
    )
    assert response.status_code in (200, 409)
    if response.status_code == 200:
        body = response.json()
        assert body["email"] == "test@example.com"


def test_book_ticket_with_preallocated_seat():
    """Test booking with pre-allocated seat details skips re-allocation."""
    response = client.post(
        "/book_ticket",
        json={
            "train_no": "12301",
            "from": "Howrah",
            "to": "New Delhi",
            "name": "Prealloc User",
            "age": 40,
            "coach": "S1",
            "berth_no": 1,
            "berth_type": "LB",
            "allocation_type": "FULL_VACANT",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["seat_details"]["coach"] == "S1"
    assert body["seat_details"]["berth_no"] == 1
    assert body["seat_details"]["berth_type"] == "LB"
    assert body["status"] == "CONFIRMED"
    assert "qr_url" in body


def test_book_ticket_invalid_train():
    """Test booking with an invalid train number."""
    response = client.post(
        "/book_ticket",
        json={
            "train_no": "00000",
            "from": "A",
            "to": "B",
            "name": "Test",
            "age": 30,
        },
    )
    assert response.status_code == 400


def test_book_ticket_missing_fields():
    """Test booking with missing required fields."""
    response = client.post(
        "/book_ticket",
        json={
            "train_no": "12301",
            "from": "Howrah",
            "to": "New Delhi",
        },
    )
    assert response.status_code == 422
