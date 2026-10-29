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

# 3. Open API docs
# http://localhost:8082/docs
```

## API Endpoints

| Endpoint | Description |
|---|---|
| `GET /analytics/weekly?user_id=1` | Weekly report — metrics, daily breakdown, charts |
| `GET /analytics/monthly?user_id=1` | Monthly report — weekly trends, category distribution |
| `GET /analytics/productivity-trend?user_id=1&days=30` | Productivity trend line over N days |
| `GET /analytics/focus-patterns?user_id=1&days=30` | Focus heatmap, peak hours, distraction trends |

All responses return **structured JSON** with metrics + **base64-encoded chart images**.

## CLI Report Generator

```bash
python scripts/generate_report.py --user-id 1 --output ./reports
```

Saves `report.json` + PNG charts to the output directory.

## Project Structure

```
app/
├── api/               # FastAPI router
│   └── analytics_api.py
├── analytics/         # Analysis modules
│   ├── weekly_analysis.py
│   ├── monthly_analysis.py
│   └── pattern_detection.py
├── models/            # SQLAlchemy ORM models
│   ├── task.py
│   └── schedule.py    # User model
├── services/          # Core business logic
│   ├── metrics_service.py
│   ├── productivity_service.py
│   └── focus_service.py
├── visualization/     # Chart generators
│   ├── charts.py
│   ├── focus_heatmap.py
│   └── productivity_plot.py
├── config.py
└── database.py
```

## Tech Stack

- **FastAPI** — REST API framework
- **SQLAlchemy** — ORM for PostgreSQL
- **Pandas / NumPy** — data processing
- **Matplotlib / Seaborn** — data visualization
