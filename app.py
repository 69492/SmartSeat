"""
app.py
------
FastAPI application for the Dynamic Train Seat Allocation System.

Endpoints
=========
GET  /                      — health check / welcome message
GET  /trains                — list all available trains
GET  /chart/{train_no}      — full coach + berth chart for a train
POST /allocate              — allocate a seat (CSP + ML)
POST /release               — release / deallocate a seat
GET  /simulation/{train_no} — current station info
POST /simulation/advance    — advance train to next station
POST /simulation/reset      — reset simulation to origin
GET  /ui                    — frontend single-page application
GET  /qr/{filename}         — download QR code image
"""

from __future__ import annotations

import logging
import os
import uuid
import base64
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, AsyncGenerator

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import config
import data_generator
import allocation_engine
import email_sender
import ml_model
import qr_generator
import simulation

logger = logging.getLogger(__name__)

MINUTES_PER_STATION_GAP = 20
MINUTES_PER_STATION_HALT = 3

# ---------------------------------------------------------------------------
# Data path
# ---------------------------------------------------------------------------

DATA_PATH = config.DATA_PATH


def _station_arrival_map(train: dict[str, Any]) -> dict[str, str]:
    """Build a case-insensitive station->arrival(HH:MM) map from train data."""
    stations = train.get("stations")
    if not isinstance(stations, list):
        return {}
    arrival_map: dict[str, str] = {}
    for station in stations:
        if not isinstance(station, dict):
            continue
        code = str(station.get("code", "")).strip()
        arrival = str(station.get("arrival", "")).strip()
        if code and arrival:
            arrival_map[code.lower()] = arrival
    return arrival_map


def _parse_arrival_hhmm(value: str) -> tuple[int, int] | None:
    """Safely parse HH:MM; return None for invalid values."""
    try:
        hh_str, mm_str = value.split(":")
        hh = int(hh_str)
        mm = int(mm_str)
    except (TypeError, ValueError):
        return None
    if not (0 <= hh <= 23 and 0 <= mm <= 59):
        return None
    return hh, mm


def calculate_ticket_validity_window(
    train_no: str,
    source: str,
    destination: str,
    data_path: str = DATA_PATH,
    now_utc: datetime | None = None,
) -> tuple[str, str]:
    """
    Calculate validity window from booking start time and journey duration.

    Returns ISO-8601 UTC timestamps as (valid_from, valid_until).
    """
    data = data_generator.load_train_data(data_path)
    train = next((t for t in data if t.get("train_no") == train_no), None)
    if not train:
        raise ValueError(f"Train not found: {train_no}")

    route = train.get("route", [])
    route_normalized = [str(station).strip().lower() for station in route]
    source_normalized = source.strip().lower()
    destination_normalized = destination.strip().lower()

    if source_normalized not in route_normalized or destination_normalized not in route_normalized:
        raise ValueError("Stations are not available in selected train route.")
    src_idx = route_normalized.index(source_normalized)
    dst_idx = route_normalized.index(destination_normalized)
    if dst_idx <= src_idx:
        raise ValueError("Destination must come after source in route.")

    station_count = (dst_idx - src_idx) + 1
    total_minutes = (
        ((station_count - 1) * MINUTES_PER_STATION_GAP)
        + (station_count * MINUTES_PER_STATION_HALT)
    )
    valid_from = now_utc or datetime.now(timezone.utc)
    valid_until = valid_from + timedelta(minutes=total_minutes)

    return valid_from.isoformat(), valid_until.isoformat()


# ---------------------------------------------------------------------------
# Lifespan (replaces deprecated @app.on_event)
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Generate train data on startup if not already present."""
    if not os.path.exists(DATA_PATH):
        logger.info("Train data not found — generating with seed=%d", config.DATA_SEED)
        data_generator.save_train_data(DATA_PATH, seed=config.DATA_SEED)
    else:
        logger.info("Train data loaded from %s", DATA_PATH)
    yield


# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Dynamic Train Seat Allocation System",
    description=(
        "Segment-wise berth availability with CSP-based allocation "
        "and ML-powered seat ranking — simulated IRCTC Sleeper class."
    ),
    version="1.0.0",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# CORS — allow the frontend to call the API from any origin
# ---------------------------------------------------------------------------
# NOTE: For production use with specific external frontends, set
# CORS_ORIGINS to a comma-separated list of allowed domains instead of "*".
# Example: CORS_ORIGINS="https://myapp.github.io,https://myapp.com"
# The current "*" configuration is suitable for development and demo purposes.

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_credentials=config.CORS_ALLOW_CREDENTIALS,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Static files — serve the frontend UI
# ---------------------------------------------------------------------------

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")

if os.path.isdir(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class AllocateRequest(BaseModel):
    """Request body for POST /allocate.

    Accepts both ``from``/``to`` (spec aliases) and ``source``/``destination``
    field names so that callers can use whichever they prefer.
    """

    train_no: str
    # "from" is a Python keyword, so we accept it via an alias
    source: str = Field(..., alias="from", serialization_alias="from")
    destination: str = Field(..., alias="to", serialization_alias="to")

    model_config = {"populate_by_name": True}


class TrainSearchRequest(BaseModel):
    """Request body for POST /trains/search."""

    source: str = Field(..., alias="from", serialization_alias="from")
    destination: str = Field(..., alias="to", serialization_alias="to")

    model_config = {"populate_by_name": True}


class ReleaseRequest(BaseModel):
    train_no: str
    coach: str
    berth_no: int
    source: str
    destination: str


class AdvanceRequest(BaseModel):
    train_no: str


class BookTicketRequest(BaseModel):
    """Request body for POST /book_ticket."""

    train_no: str
    source: str = Field(..., alias="from", serialization_alias="from")
    destination: str = Field(..., alias="to", serialization_alias="to")
    name: str
    age: int
    email: str = ""
    # Pre-allocated seat details (skip re-allocation when provided)
    coach: str | None = None
    berth_no: int | None = None
    berth_type: str | None = None
    allocation_type: str | None = None

    model_config = {"populate_by_name": True}


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/", tags=["Health"])
def root() -> dict[str, str]:
    return {
        "message": "Dynamic Train Seat Allocation System — API is running.",
        "docs":    "/docs",
    }


# ------------------------------------------------------------------
@app.get("/trains", tags=["Trains"])
def list_trains() -> list[dict[str, Any]]:
    """Return a summary list of all available trains."""
    data = data_generator.load_train_data(DATA_PATH)
    return [
        {
            "train_no":   t["train_no"],
            "train_name": t["train_name"],
            "route":      t["route"],
            "coaches":    [c["coach"] for c in t["coaches"]],
        }
        for t in data
    ]


# ------------------------------------------------------------------
@app.post("/trains/search", tags=["Trains"])
def search_trains(request: TrainSearchRequest) -> list[dict[str, Any]]:
    """Return trains that pass through source and destination in order."""
    source = request.source
    destination = request.destination

    data = data_generator.load_train_data(DATA_PATH)
    matches: list[dict[str, Any]] = []
    for train in data:
        route = train["route"]
        if source not in route or destination not in route:
            continue
        if route.index(source) >= route.index(destination):
            continue
        matches.append({
            "train_no": train["train_no"],
            "train_name": train["train_name"],
            "route": route,
            "coaches": [c["coach"] for c in train["coaches"]],
        })
    return matches


# ------------------------------------------------------------------
@app.get("/chart/{train_no}", tags=["Trains"])
def get_chart(train_no: str) -> dict[str, Any]:
    """Return the full berth chart for a train."""
    data = data_generator.load_train_data(DATA_PATH)
    for train in data:
        if train["train_no"] == train_no:
            return train
    raise HTTPException(status_code=404, detail=f"Train '{train_no}' not found.")


# ------------------------------------------------------------------
@app.post("/allocate", tags=["Booking"])
def allocate(request: AllocateRequest) -> dict[str, Any]:
    """
    Allocate the best available seat for the requested journey.

    Request body:
    ```json
    { "train_no": "12301", "from": "Howrah", "to": "New Delhi" }
    ```
    """
    train_no    = request.train_no
    source      = request.source
    destination = request.destination

    try:
        candidates = allocation_engine.find_valid_berths(
            train_no, source, destination, DATA_PATH
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    if not candidates:
        raise HTTPException(
            status_code=409,
            detail="No valid berths available for the requested journey.",
        )

    # ML ranking
    best = ml_model.get_best_berth(candidates)

    # Persist allocation
    try:
        allocated = allocation_engine.allocate_seat(
            train_no, source, destination, DATA_PATH, ranked_berth=best
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    return {
        "status":          "ALLOCATED",
        "train_no":        allocated["train_no"],
        "coach":           allocated["coach"],
        "berth_no":        allocated["berth_no"],
        "berth_type":      allocated["berth_type"],
        "source":          source,
        "destination":     destination,
        "allocation_type": allocated["allocation_type"],
        "segment":         allocated.get("segment"),
        "candidates_found": len(candidates),
    }


# ------------------------------------------------------------------
@app.post("/recommendations", tags=["Booking"])
def recommendations(request: AllocateRequest) -> dict[str, Any]:
    """Return top seat recommendations and same-train fallback options."""
    train_no = request.train_no
    source = request.source
    destination = request.destination

    try:
        candidates = allocation_engine.find_valid_berths(
            train_no, source, destination, DATA_PATH
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    ranked = ml_model.rank_berths(candidates)
    top_recommendations = []
    for rec in ranked[:3]:
        top_recommendations.append({
            "train_no": rec["train_no"],
            "coach": rec["coach"],
            "berth_no": rec["berth_no"],
            "berth_type": rec["berth_type"],
            "allocation_type": rec["allocation_type"],
            "availability_label": "FULL_VACANT" if rec["allocation_type"] == "FULL_VACANT" else "PARTIAL_VACANT",
            "segment": rec.get("segment"),
            "ranking_score": rec["ranking_score"],
        })

    segment_options = []
    nearby_options = []
    if not top_recommendations:
        segment_options = allocation_engine.find_segment_allocation_options(
            train_no, source, destination, DATA_PATH
        )
        nearby_options = allocation_engine.suggest_nearby_destinations(
            train_no, source, destination, DATA_PATH
        )

    return {
        "train_no": train_no,
        "source": source,
        "destination": destination,
        "recommendations": top_recommendations,
        "segment_allocation_options": segment_options,
        "nearby_station_options": nearby_options,
    }


# ------------------------------------------------------------------
@app.post("/book_ticket", tags=["Booking"])
def book_ticket(request: BookTicketRequest) -> dict[str, Any]:
    """
    Full booking flow: allocate seat (if not pre-allocated), generate ticket,
    create QR, send email.

    When ``coach`` and ``berth_no`` are provided the endpoint skips seat
    allocation and uses the pre-allocated seat directly.  This avoids
    double-allocation when the frontend already called ``/allocate``.

    Request body:
    ```json
    {
      "train_no": "12301",
      "from": "Howrah",
      "to": "New Delhi",
      "name": "John Doe",
      "age": 30,
      "coach": "S1",
      "berth_no": 5,
      "berth_type": "LB",
      "allocation_type": "FULL_VACANT"
    }
    ```
    """
    train_no    = request.train_no
    source      = request.source
    destination = request.destination

    # --- Use pre-allocated seat or allocate a new one ---
    if request.coach is not None and request.berth_no is not None:
        allocated = {
            "train_no":        train_no,
            "coach":           request.coach,
            "berth_no":        request.berth_no,
            "berth_type":      request.berth_type or "",
            "allocation_type": request.allocation_type or "",
        }
    else:
        try:
            candidates = allocation_engine.find_valid_berths(
                train_no, source, destination, DATA_PATH
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

        if not candidates:
            raise HTTPException(
                status_code=409,
                detail="No valid berths available for the requested journey.",
            )

        best = ml_model.get_best_berth(candidates)

        try:
            allocated = allocation_engine.allocate_seat(
                train_no, source, destination, DATA_PATH, ranked_berth=best
            )
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc))

    # --- Build ticket ---
    ticket_id = f"SM-{uuid.uuid4().hex[:8].upper()}"
    booking_now = datetime.now(timezone.utc)
    booking_time = booking_now.strftime("%Y-%m-%d %H:%M:%S UTC")
    price = config.TICKET_PRICE
    try:
        valid_from, valid_until = calculate_ticket_validity_window(
            train_no=allocated["train_no"],
            source=source,
            destination=destination,
            data_path=DATA_PATH,
            now_utc=booking_now,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    ticket = {
        "ticket_id":       ticket_id,
        "name":            request.name,
        "age":             request.age,
        "email":           request.email,
        "train_no":        allocated["train_no"],
        "coach":           allocated["coach"],
        "berth_no":        allocated["berth_no"],
        "berth_type":      allocated["berth_type"],
        "source":          source,
        "destination":     destination,
        "allocation_type": allocated["allocation_type"],
        "price":           price,
        "booking_time":    booking_time,
        "valid_from":      valid_from,
        "valid_until":     valid_until,
        "validity":        f"Valid until arrival at {destination}",
        "status":          "CONFIRMED",
    }

    # --- QR code ---
    try:
        qr_path = qr_generator.generate_qr(ticket)
        qr_filename = os.path.basename(qr_path)
        with open(qr_path, "rb") as qr_file:
            qr_image = "data:image/png;base64," + base64.b64encode(
                qr_file.read()
            ).decode("ascii")
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Unable to generate QR code.") from exc

    # --- Email ---
    email_status = email_sender.send_ticket_email(ticket, qr_path=qr_path)

    return {
        "ticket_id":    ticket_id,
        "seat_details": {
            "train_no":        allocated["train_no"],
            "coach":           allocated["coach"],
            "berth_no":        allocated["berth_no"],
            "berth_type":      allocated["berth_type"],
            "allocation_type": allocated["allocation_type"],
        },
        "name":         request.name,
        "age":          request.age,
        "email":        request.email,
        "source":       source,
        "destination":  destination,
        "price":        price,
        "booking_time": booking_time,
        "valid_from":   valid_from,
        "valid_until":  valid_until,
        "validity":     f"Valid until arrival at {destination}",
        "status":       "CONFIRMED",
        "qr_image":     qr_image,
        "qr_url":       f"/qr/{qr_filename}" if qr_filename else None,
        "email_status": email_status,
    }


# ------------------------------------------------------------------
@app.post("/release", tags=["Booking"])
def release(request: ReleaseRequest) -> dict[str, Any]:
    """
    Release (deallocate) a previously allocated berth segment.

    Request body:
    ```json
    {
        "train_no": "12301",
        "coach": "S1",
        "berth_no": 5,
        "source": "Howrah",
        "destination": "New Delhi"
    }
    ```
    """
    try:
        updated_berth = allocation_engine.release_seat(
            request.train_no,
            request.coach,
            request.berth_no,
            request.source,
            request.destination,
            DATA_PATH,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    return {
        "status":      "RELEASED",
        "train_no":    request.train_no,
        "coach":       request.coach,
        "berth_no":    request.berth_no,
        "berth_state": updated_berth,
    }


# ------------------------------------------------------------------
@app.get("/simulation/{train_no}", tags=["Simulation"])
def get_simulation(train_no: str) -> dict[str, Any]:
    """Return the current station pointer for a train."""
    try:
        return simulation.get_current_station(train_no)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.post("/simulation/advance", tags=["Simulation"])
def advance_simulation(request: AdvanceRequest) -> dict[str, Any]:
    """Advance the train to its next station and auto-release expired segments."""
    try:
        return simulation.advance_station(request.train_no, DATA_PATH)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.post("/simulation/reset", tags=["Simulation"])
def reset_simulation(request: AdvanceRequest) -> dict[str, str]:
    """Reset the simulation pointer to the train's origin station."""
    return simulation.reset_simulation(request.train_no)


# ------------------------------------------------------------------
@app.get("/ui", tags=["UI"], include_in_schema=False)
def serve_ui() -> FileResponse:
    """Serve the frontend single-page application."""
    index = os.path.join(STATIC_DIR, "index.html")
    if not os.path.exists(index):
        raise HTTPException(status_code=404, detail="Frontend not found.")
    return FileResponse(index, media_type="text/html")


# ------------------------------------------------------------------
@app.get("/qr/{filename}", tags=["QR"])
def get_qr(filename: str) -> FileResponse:
    """Download the QR code image for a booking."""
    path = os.path.join(qr_generator.QR_DIR, filename)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="QR code not found.")
    return FileResponse(path, media_type="image/png")


# ---------------------------------------------------------------------------
# Entry-point for local development
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    logging.basicConfig(level=config.LOG_LEVEL.upper())
    uvicorn.run(
        "app:app",
        host=config.HOST,
        port=config.PORT,
        reload=config.RELOAD,
        log_level=config.LOG_LEVEL,
    )
