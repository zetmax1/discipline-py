# Discipline Analytics Microservice

Python analytics service for the **Discipline Tracker** app. Connects to the same PostgreSQL database as the Go backend and provides productivity insights, pattern detection, and data visualizations.

## Architecture

```
Frontend (React)
    │
Go Backend (Gin API) ──── PostgreSQL ──── Python Analytics Service (this)
    port 8080                                    port 8082
```

## Quick Start

```bash
# 1. Install dependencies
cd discipline-py
source venv/bin/activate
pip install -r requirements.txt

# 2. Run the service
python main.py

# 3. Open API docs (only served when ENABLE_DOCS=true)
# http://localhost:8082/docs
```

## API Endpoints

Every endpoint requires `Authorization: Bearer <internal JWT>` signed by the Go backend
(HS256, `INTERNAL_JWT_SECRET`, `aud=discipline-py`, `exp` ≤ 60s). The user is taken only from
the token's `sub` claim; there is no `user_id` parameter. The service is meant to be reached
only over Railway private networking, not from browsers.

| Endpoint | Description |
|---|---|
| `GET /analytics/today` | Today's metrics (dashboard): planned/done minutes and focus-score components |
| `GET /analytics/weekly` | This week up to today: daily metrics, mean focus score, streak, comparison, patterns, charts |
| `GET /analytics/monthly` | Same for this month |
| `GET /analytics/focus-patterns?days=30` | Heatmap (weekday × 00–23), weekday scores, deep-work slots, distraction trend, charts |
| `POST /analytics/smart-schedule` | Weekly schedule from commitments and goals |

Every number comes from `app/metrics.py` (the single metrics definition). Response shapes are
Pydantic models in `app/schemas.py`; `tests/test_contract.py` validates real responses against the
frontend's contract (`../discipline/contracts/analytics.schema.json`), so run the tests with both
repos checked out side by side (or set `ANALYTICS_CONTRACT`).

Charts are returned as `{"image": <base64 PNG>, "data": <the plotted series/matrix>}`; rendered images are cached for 5 minutes.

Configuration: see `.env.example` (names only). `DB_PASSWORD` and `INTERNAL_JWT_SECRET`
are required; the service refuses to start without them.

## CLI Report Generator

```bash
python scripts/generate_report.py --user-id 1 --output ./reports
```

Saves `report.json` + PNG charts to the output directory.

## Project Structure

```
app/
├── api/analytics_api.py   # FastAPI router (response models in schemas.py)
├── smart_schedule/        # Weekly schedule generator + router
├── models/                # SQLAlchemy ORM models (task.py, schedule.py = User)
├── metrics.py             # The single definition of every metric
├── reports.py             # Today / week / month / focus-pattern payloads built on metrics.py
├── charts.py              # Matplotlib (object-oriented API) charts, render limit + cache
├── schemas.py             # Pydantic response models
├── auth.py                # Internal JWT verification
├── timeutil.py            # "Now" in the user's IANA zone
├── config.py
└── database.py
```

## Tech Stack

- **FastAPI** — REST API framework
- **SQLAlchemy** — ORM for PostgreSQL
- **NumPy** — trend fitting
- **Matplotlib** — server-side charts (object-oriented API, no pyplot)
