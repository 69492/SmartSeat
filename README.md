# SmartSeat — Dynamic Train Seat Allocation System

> **Segment-Wise Berth Availability for Indian Railways (Sleeper Class)**

A production-style B.Tech academic project that simulates IRCTC-style seat allocation using CSP (Constraint Satisfaction Problem) logic and ML-based ranking. All data is **fully simulated** — no real IRCTC API is used.

---

## Table of Contents

- [Project Description](#project-description)
- [Features](#features)
- [Technology Stack](#technology-stack)
- [Project Structure](#project-structure)
- [How to Run Locally](#how-to-run-locally)
- [API Usage Examples](#api-usage-examples)
- [Cloud Deployment](#cloud-deployment)

---

## Project Description

Traditional railway seat-booking systems treat a berth as either *fully vacant* or *fully occupied*.  
**SmartSeat** introduces a **segment-wise berth model** where each berth tracks independent VACANT/OCCUPIED segments along a route.

Example: A berth from Howrah→New Delhi might be occupied for Howrah→Gaya but vacant for Gaya→New Delhi. SmartSeat can allocate that berth to a passenger travelling Gaya→Kanpur.

### Core Concepts

| Concept | Description |
|---|---|
| **FULL_VACANT** | Berth is empty for the entire route |
| **FULL_OCCUPIED** | Berth is fully booked (never allocated) |
| **PARTIAL** | Berth has a mix of vacant/occupied segments |
| **CSP Rules** | Feasibility is determined by constraint checking |
| **ML Ranking** | Decision Tree ranks multiple valid berths |

---

## Features

1. **Data Generator** — Generates 3 realistic trains with Sleeper coaches (S1–S4), 72 berths each, distributed ~65% occupied / ~20% vacant / ~15% partial.
2. **CSP Allocation Engine** — Checks PARTIAL segments with `seg.from ≤ source AND seg.to ≥ destination`.
3. **ML Recommendation** — Decision Tree ranks multiple valid berths on journey distance, berth type, and coach preference.
4. **QR Code Generator** — Produces a QR image with booking details after allocation.
5. **FastAPI REST Backend** — Clean RESTful API with Swagger UI at `/docs`.
6. **Web Frontend** — Responsive single-page UI at `/ui` built with pure HTML, CSS, and vanilla JavaScript.
7. **Real-Time Simulation** — Advance train position station by station; expired segments auto-release.

---

## Technology Stack

| Layer | Technology |
|---|---|
| Frontend | HTML / CSS / vanilla JavaScript |
| Backend Framework | FastAPI (Python 3.10+) |
| ML Library | scikit-learn (Decision Tree) |
| Data Storage | JSON files |
| QR Generation | qrcode + Pillow |
| Server | Uvicorn (ASGI) |
| Data Validation | Pydantic v2 |
| Testing | pytest + httpx |
| Containerisation | Docker |

---

## Project Structure

```
SmartSeat/
├── app.py                  # FastAPI application & all endpoints
├── config.py               # Centralised configuration (env vars)
├── data_generator.py       # Synthetic train data generator
├── allocation_engine.py    # CSP-based seat allocation
├── ml_model.py             # ML ranking (Decision Tree)
├── qr_generator.py         # QR code image generation
├── simulation.py           # Real-time station pointer simulation
├── static/
│   └── index.html          # Frontend UI (HTML + CSS + JS)
├── data/
│   ├── train_data.json     # Generated train/berth data (auto-created)
│   └── simulation_state.json  # Current station per train (auto-created)
├── qr_codes/               # Generated QR PNG images (auto-created)
├── tests/                  # pytest test suite
├── Dockerfile              # Production container image
├── docker-compose.yml      # Local/cloud orchestration
├── .env.example            # Environment variable template
├── requirements.txt
└── README.md
```

---

## How to Run Locally

### Prerequisites
- Python 3.10 or higher
- pip

### 1. Clone and install dependencies

```bash
git clone https://github.com/69492/SmartSeat.git
cd SmartSeat
pip install -r requirements.txt
```

### 2. (Optional) Configure environment

```bash
cp .env.example .env
# Edit .env to override defaults (port, log level, etc.)
```

### 3. (Optional) Pre-generate train data

```bash
python data_generator.py
```

Train data is also auto-generated on first API request if the file does not exist.

### 4. Start the API server

```bash
python app.py
```

Or using uvicorn directly:

```bash
uvicorn app:app --host 0.0.0.0 --port 5000 --reload
```

### 5. Open the Web UI

Navigate to **http://localhost:5000/ui** for the seat allocation frontend.

### 6. Open Swagger UI

Navigate to **http://localhost:5000/docs** for interactive API documentation.

### 7. Run tests

```bash
python -m pytest tests/ -v
```

---

## API Usage Examples

### List trains

```bash
curl http://localhost:5000/trains
```

**Response:**
```json
[
  {
    "train_no": "12301",
    "train_name": "Howrah Rajdhani Express",
    "route": ["Howrah", "Asansol", "Dhanbad", "Gaya", ...],
    "coaches": ["S1", "S2", "S3", "S4"]
  }
]
```

---

### Get berth chart for a train

```bash
curl http://localhost:5000/chart/12301
```

---

### Allocate a seat

```bash
curl -X POST http://localhost:5000/allocate \
  -H "Content-Type: application/json" \
  -d '{"train_no": "12301", "from": "Howrah", "to": "New Delhi"}'
```

**Response:**
```json
{
  "status": "ALLOCATED",
  "train_no": "12301",
  "coach": "S1",
  "berth_no": 3,
  "berth_type": "UB",
  "source": "Howrah",
  "destination": "New Delhi",
  "allocation_type": "FULL_VACANT",
  "segment": null,
  "candidates_found": 14,
  "qr_code": "/qr/12301_S1_3.png"
}
```

---

### Release a seat

```bash
curl -X POST http://localhost:5000/release \
  -H "Content-Type: application/json" \
  -d '{
    "train_no": "12301",
    "coach": "S1",
    "berth_no": 3,
    "source": "Howrah",
    "destination": "New Delhi"
  }'
```

---

### Simulation — advance train

```bash
# Check current station
curl http://localhost:5000/simulation/12301

# Advance to next station
curl -X POST http://localhost:5000/simulation/advance \
  -H "Content-Type: application/json" \
  -d '{"train_no": "12301"}'

# Reset simulation
curl -X POST http://localhost:5000/simulation/reset \
  -H "Content-Type: application/json" \
  -d '{"train_no": "12301"}'
```

---

### Download QR code

```bash
curl http://localhost:5000/qr/12301_S1_3.png --output booking_qr.png
```

---

## Cloud Deployment

### Docker

```bash
# Build and run with Docker
docker build -t smartseat .
docker run -p 5000:5000 smartseat

# Or use Docker Compose
docker compose up --build
```

The container exposes port **5000** by default. Override behaviour with environment
variables — see `.env.example` for the full list.

### Render / Railway

1. Push the repository to GitHub.
2. Create a new **Web Service** on [Render](https://render.com) or [Railway](https://railway.app).
3. Set:
   - **Build command:** `pip install -r requirements.txt`
   - **Start command:** `uvicorn app:app --host 0.0.0.0 --port 5000`
4. Deploy — the API will be live at the assigned URL.

> **Note:** The `data/` and `qr_codes/` directories are created automatically at runtime if they don't exist.

---

## Configuration

All settings are loaded from environment variables (see `.env.example`):

| Variable | Default | Description |
|---|---|---|
| `API_HOST` | `0.0.0.0` | Bind address |
| `API_PORT` | `5000` | Listen port |
| `API_RELOAD` | `false` | Auto-reload on code changes (dev only) |
| `LOG_LEVEL` | `info` | Logging verbosity |
| `DATA_DIR` | `./data` | Train data directory |
| `QR_DIR` | `./qr_codes` | QR code output directory |
| `DATA_SEED` | `42` | Random seed for data generation |
| `ML_MAX_DEPTH` | `6` | Decision tree max depth |
| `ML_RANDOM_STATE` | `42` | ML model random seed |
| `ML_TRAINING_SAMPLES` | `500` | Synthetic training samples |
