# WindSite — Urban Wind Turbine Feasibility Analyzer

A tool for identifying viable locations for small wind turbines in urban areas, built for the **Infrared SDK Hackathon** at IAAC Barcelona.

![WindSite](https://img.shields.io/badge/Infrared-SDK-blue) ![Python](https://img.shields.io/badge/Python-3.13-green) ![FastAPI](https://img.shields.io/badge/FastAPI-0.136-teal)

---

## The idea

Urban wind is not uniform. A rooftop two blocks away from another can receive 40% more wind simply because of how surrounding buildings channel or block the flow. EPW climate files give you one number for an entire city — they tell you nothing about specific locations.

WindSite combines two data sources:

- **Infrared SDK** — runs a CFD simulation over the actual 3D urban geometry and returns a spatial grid showing how buildings modify wind at every point in the site.
- **EPW climate data** — provides real seasonal wind speeds for Barcelona, grounding the simulation in actual climate conditions.

Together, they produce location-specific, seasonally-calibrated wind feasibility assessments.

---

## Methodology

### Wind speed at each location

Infrared simulates wind flow at a fixed **10 m/s reference speed**. This gives a spatial exposure map — each cell shows what fraction of the incoming wind reaches that point:

```
exposure_factor = infrared_grid_value / 10.0
```

This factor is a property of the urban geometry, not the input speed (CFD scales linearly at these velocities). It is then scaled by real climate data:

```
realistic_local_speed = exposure_factor × EPW_seasonal_mean
```

EPW Barcelona seasonal means used:

| Season | Mean wind speed |
|---|---|
| Annual | 3.5 m/s |
| Winter | 4.2 m/s |
| Spring | 3.7 m/s |
| Summer | 2.8 m/s |
| Autumn | 3.4 m/s |

### Height extrapolation — two-zone model

Wind behaves differently below and above rooftop height:

```
┌──────────────────────────────────────────┐
│  Zone 2 — Above rooftop                  │
│  Free-field conditions · α = 0.12        │
├──────────────────────────────────────────┤  ← mean rooftop height
│  Zone 1 — Ground → rooftop               │
│  Urban canyon effects · Infrared-driven  │
│  Power law · α = 0.22–0.28               │
└──────────────────────────────────────────┘
```

Formula: `V(h2) = V(h1) × (h2 / h1)^α`

### Turbine types assessed

| Type | Hub height | Min viable speed |
|---|---|---|
| Lamppost VAWT | 5 m (street level) | 5.0 m/s |
| Rooftop VAWT | rooftop + 3 m | 3.5 m/s |
| Rooftop HAWT | rooftop + 8 m | 4.5 m/s |
| Community HAWT | rooftop + 30 m | 5.5 m/s |

### Hackathon simplification

Ideally, the analysis would run Infrared for multiple wind directions (e.g. all 8 compass directions), weight each result by its frequency from the EPW wind rose, and sum them into a direction-weighted annual exposure map. This would account for the fact that a sheltered courtyard in NW wind might be fully exposed in SE wind.

For this hackathon, we run a **single user-selected direction** and scale by the omnidirectional EPW seasonal mean. The result is best read as: *"when wind comes from this direction, which locations are viable?"* — rather than a full annual average. NW is the dominant direction for Barcelona (Tramontana/Mestral, ~34% frequency), making it the most representative single scenario.

---

## How to use

### 1 — Infrared Simulation tab

- Draw a polygon on the map, or use the default Barcelona Eixample area
- Select wind direction and terrain roughness (α)
- Click **Run Infrared Simulation**
- The heatmap shows the raw CFD exposure pattern from Infrared
- The stats panel shows EPW-scaled realistic speeds for the selected season

### 2 — 3D Explore tab

- Explore the site in 3D with real building geometry from the Infrared SDK
- Hover over any building or street to see the **wind stick** — speeds at 7 heights from 1.5 m to rooftop+30 m, EPW-scaled and color-coded
- Use **Show Feasible Rooftops** to place mini turbines on buildings that clear the feasibility threshold
- Use **Show Wind Corridors** to highlight street-level zones above 5 m/s, suitable for lamppost VAWTs
- Use **Place Turbine Pin** to click a specific location and get a detailed feasibility card
- The **Top Rooftops** ranked list sorts all buildings by rooftop wind speed

### 3 — Feasibility tab

- Overview of all four turbine types for the simulated site
- Season selector shows how the real EPW seasonal mean shifts feasibility
- Height profile chart shows the two-zone extrapolation
- Animated turbines spin proportionally to hub speed

### 4 — 3D Map tab *(requires Mapbox + Cesium Ion tokens)*

- Google Photorealistic 3D Tiles via Cesium Ion
- Infrared heatmap draped on the photogrammetric ground
- Wind profile panel on hover

---

## Stack

| Component | Technology |
|---|---|
| Wind CFD | [Infrared SDK](https://infrared.city) `infrared-sdk 0.4.9` |
| Climate data | EPW Barcelona (climate.onebuilding.org) |
| Backend | Python · FastAPI · uvicorn |
| Database | SQLAlchemy · Postgres (Neon) in production · SQLite locally |
| 2D map | Leaflet.js + Leaflet.draw |
| 3D scene | Three.js r128 |
| 3D photorealistic | Mapbox GL JS + deck.gl + Cesium Ion |
| Charts | Chart.js 4.4 |

---

## Repository structure

```
├── frontend/          → deployed to Vercel (static site)
│   ├── windsite.html  → single-page app — all four tabs
│   ├── config.js      → set BACKEND_URL here after deploying the backend
│   └── vercel.json    → Vercel routing config
│
├── backend/           → deployed to Render (Python web service)
│   ├── server.py      → FastAPI app — wraps Infrared SDK
│   ├── database.py    → SQLAlchemy models (Simulation + GeometryCache)
│   ├── requirements.txt
│   ├── fetch_geometry.py → local dev helper — pre-fetches building geometry
│   └── Procfile       → Render start command
│
├── render.yaml        → Render service definition
└── README.md
```

---

## Local development

### Requirements

- Python 3.10+
- An [Infrared API key](https://infrared.city)

### Install

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS / Linux

pip install -r backend/requirements.txt
```

### Run

```bash
# Set your Infrared API key
set INFRARED_API_KEY=your-key-here          # Windows CMD
# $env:INFRARED_API_KEY = 'your-key-here'  # PowerShell
# export INFRARED_API_KEY='your-key-here'  # bash

# Start the backend (from repo root)
cd backend
uvicorn server:app --reload --port 8000
```

Then open `frontend/windsite.html` directly in your browser, or serve it with any static server. The frontend reads `config.js` which defaults to `localhost:8000`.

Simulation results are stored in a local SQLite file (`backend/windsite.db`) — re-running the same polygon is instant.

---

## Deployment

### 1 — Backend on Render

1. Connect your GitHub repo to [Render](https://render.com)
2. Create a **Web Service** — Render will detect `render.yaml` automatically
3. Set these environment variables in the Render dashboard:
   - `INFRARED_API_KEY` — your Infrared key
   - `DATABASE_URL` — your Neon Postgres connection string (see below)
4. Deploy. Render will install dependencies and start uvicorn.

### 2 — Database on Neon (free Postgres)

1. Create a free account at [neon.tech](https://neon.tech)
2. Create a new project → copy the **Connection string** (starts with `postgresql://`)
3. Paste it as `DATABASE_URL` in Render. Tables are created automatically on first startup.

### 3 — Frontend on Vercel

1. Connect your GitHub repo to [Vercel](https://vercel.com)
2. Set **Root Directory** to `frontend/`
3. No build command needed — it's a plain HTML file
4. After Render gives you a URL (e.g. `https://windsite-backend.onrender.com`):
   - Edit `frontend/config.js`, set `window.BACKEND_URL = 'https://windsite-backend.onrender.com'`
   - Push → Vercel auto-redeploys

> **Note on Render free tier**: the service sleeps after 15 minutes of inactivity and takes ~30 seconds to wake up on the next request. This is fine for demos. Upgrade to a paid Render plan to avoid cold starts.

---

## Built at

IAAC Barcelona · Programming for AI · Semester 3 · 2025–2026  
Hackathon track: [Infrared SDK](https://infrared.city)
