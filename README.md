# WindSite — Urban Wind Turbine Feasibility Analyzer

A tool for analyzing urban sites for small wind turbine installation feasibility, built for the **Infrared SDK Hackathon** at IAAC Barcelona.

![WindSite](https://img.shields.io/badge/Infrared-SDK-blue) ![Python](https://img.shields.io/badge/Python-3.13-green) ![FastAPI](https://img.shields.io/badge/FastAPI-0.136-teal)

---

## What it does

WindSite takes a drawn polygon on a map, runs a CFD wind simulation via the [Infrared SDK](https://infrared.city), and produces a location-specific feasibility assessment for four turbine installation types — all in a single browser tab.

### Four turbine types assessed

| Type | Hub height | Min viable wind |
|---|---|---|
| Lamppost VAWT | 5 m (street level) | 5.0 m/s |
| Rooftop VAWT | rooftop + 3 m | 3.5 m/s |
| Rooftop HAWT | rooftop + 8 m | 4.5 m/s |
| Community HAWT | rooftop + 30 m | 5.5 m/s |

### Two-zone wind model

Wind behaviour changes fundamentally at rooftop height:

```
┌──────────────────────────────────────────┐
│  Zone 2 — Above rooftop                  │
│  Free-field · EPW weather file · α=0.12  │
├──────────────────────────────────────────┤  ← mean rooftop height
│  Zone 1 — Ground → rooftop               │
│  Urban canyon effects · Infrared SDK     │
│  Power law · α=0.22 suburban / 0.28 dense│
└──────────────────────────────────────────┘
```

Extrapolation: `V(h2) = V(h1) × (h2/h1)^α`

---

## Tabs

### 1 — Infrared Simulation
- Draw a polygon (or use the default Barcelona Eixample area)
- Set wind speed, direction, terrain roughness
- Runs a real CFD simulation via the Infrared SDK
- Shows the wind speed heatmap overlaid on the map with a color legend
- Extracts mean/peak speed and displays the two-zone pipeline

### 2 — 3D Explore
- Real building geometry fetched from the Infrared SDK
- Buildings colored by wind speed at **Ground / Mid / Roof** level (from the actual simulation grid)
- **Wind stick probe**: hover over any building to see the speed at 7 heights simultaneously (1.5 m → rooftop+30 m), with floating color-coded labels
- Season and time-of-day sliders apply seasonal multipliers and diurnal profiles
- Infrared simulation heatmap draped on the 3D ground

### 3 — Feasibility
- Animated turbine cards for each type, spinning at speed proportional to hub wind
- Seasonal breakdown (Winter +30%, Summer −28%, etc.)
- Height profile chart (two-zone model), wind rose, Weibull distribution

### 4 — 3D Map *(requires Mapbox + Cesium Ion tokens)*
- Google Photorealistic 3D Tiles via Cesium Ion (recipe: deck.gl `Tile3DLayer`)
- Infrared heatmap draped at photogrammetric ground level via `BitmapLayer` + height offset
- Study area cutout using `MaskExtension`
- Wind profile panel on hover

---

## Stack

| Component | Technology |
|---|---|
| Wind CFD simulation | [Infrared SDK](https://infrared.city) (`infrared-sdk` 0.4.9) |
| Backend | Python · FastAPI · uvicorn |
| 2D map | Leaflet.js + Leaflet.draw |
| 3D scene | Three.js r128 + OrbitControls |
| 3D photorealistic map | Mapbox GL JS + deck.gl + Cesium Ion |
| Charts | Chart.js 4.4 |

---

## Setup

### Requirements
- Python 3.10+
- An [Infrared API key](https://infrared.city)

### Install

```bash
# Create and activate virtual environment
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS/Linux

# Install dependencies
pip install infrared-sdk fastapi uvicorn numpy pydantic
```

### Run

```bash
# Set your Infrared API key
$env:INFRARED_API_KEY = 'your-key-here'   # PowerShell
# export INFRARED_API_KEY='your-key-here' # bash

# Start the server
.venv\Scripts\python server.py

# Open in browser
# http://localhost:8000
```

The server caches simulation results in `./cache/` so repeated runs on the same polygon are instant.

### Optional: pre-fetch geometry

```bash
.venv\Scripts\python fetch_geometry.py
```

Fetches and caches building geometry for the default Barcelona Eixample polygon before the demo, so the 3D scene loads immediately.

---

## Key files

| File | Purpose |
|---|---|
| `windsite.html` | Single-page frontend (all four tabs) |
| `server.py` | FastAPI backend wrapping the Infrared SDK |
| `fetch_geometry.py` | Standalone geometry pre-fetcher |
| `CONTEXT.md` | Architecture notes — two-zone model, pipeline |
| `infrared-sdk-deckgl-recipe.md` | Recipe used for the 3D Map tab |

---

## Built at

IAAC Barcelona · Programming for AI · Semester 3 · 2025–2026  
Hackathon track: [Infrared SDK](https://infrared.city)
