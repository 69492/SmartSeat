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
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import config
import data_generator
import allocation_engine
import ml_model
import qr_generator
import simulation

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data path
# ---------------------------------------------------------------------------

DATA_PATH = config.DATA_PATH


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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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


class ReleaseRequest(BaseModel):
    train_no: str
    coach: str
    berth_no: int
    source: str
    destination: str


class AdvanceRequest(BaseModel):
    train_no: str


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

    # Generate QR code
    booking_info = {**allocated, "source": source, "destination": destination}
    try:
        qr_path = qr_generator.generate_qr(booking_info)
        qr_filename = os.path.basename(qr_path)
    except Exception:
        qr_filename = None

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
        "qr_code":         f"/qr/{qr_filename}" if qr_filename else None,
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
