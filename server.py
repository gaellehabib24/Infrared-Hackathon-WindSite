"""
server.py — WindSite backend
Wraps the Infrared SDK and serves the HTML frontend.

Usage (activate venv first):
    python server.py
    # or for auto-reload during dev:
    uvicorn server:app --reload --port 8000

Open: http://localhost:8000
"""

from __future__ import annotations
import json, hashlib, math, os
from pathlib import Path
from typing import Any

import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel

HERE  = Path(__file__).parent
CACHE = HERE / "cache"
CACHE.mkdir(exist_ok=True)

# ── In-memory building cache (DotBimMesh objects can't be JSON-serialised) ────
_bld_cache: dict[str, Any] = {}

app = FastAPI(title="WindSite API", version="1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)


# ════════════════════════════════════════════════════════════
# HELPERS
# ════════════════════════════════════════════════════════════

def poly_hash(polygon: dict) -> str:
    return hashlib.md5(json.dumps(polygon, sort_keys=True).encode()).hexdigest()[:12]


def mesh_to_dict(bid: str, mesh) -> dict | None:
    """Convert a DotBimMesh → plain dict for JSON + Three.js."""
    cs = list(mesh.coordinates)
    if not cs:
        return None
    xs, ys, zs = cs[0::3], cs[1::3], cs[2::3]
    h = round(max(zs) - min(zs), 2)
    if h < 2:
        return None
    return {
        "id":       bid,
        "height":   h,
        "cx":       round((min(xs) + max(xs)) / 2, 2),
        "cy":       round((min(ys) + max(ys)) / 2, 2),
        "minX":     round(min(xs), 2), "maxX": round(max(xs), 2),
        "minY":     round(min(ys), 2), "maxY": round(max(ys), 2),
        "vertices": cs,
        "indices":  list(mesh.indices),
    }


def tree_to_dict(tid: str, feat: dict, sw_lon: float, sw_lat: float) -> dict | None:
    """Convert a vegetation GeoJSON feature → local-coordinate dict."""
    g = feat.get("geometry") or {}
    if g.get("type") != "Point":
        return None
    lon, lat = g["coordinates"]
    p = feat.get("properties") or {}
    lon_m = 111_320 * math.cos(math.radians(sw_lat))
    return {
        "id": tid,
        "x":  round((lon - sw_lon) * lon_m, 2),
        "y":  round((lat - sw_lat) * 111_320, 2),
        "h":  float(p.get("height") or 8),
        "r":  float(p.get("crown_radius") or p.get("crownRadius") or 3),
    }


def grid_to_payload(grid: np.ndarray, min_leg, max_leg, bounds) -> dict:
    """Downsample grid to ≤128×128, NaN→None, and package with map bounds."""
    h, w   = grid.shape
    step   = max(1, max(h, w) // 128)
    small  = grid[::step, ::step]
    rows, cols = small.shape

    flat = [
        [None if math.isnan(v) else round(float(v), 2) for v in row]
        for row in small.tolist()
    ]

    # result.bounds added in SDK 0.4.4 — try attribute, fall back to sequence
    try:
        sw = [float(bounds.south), float(bounds.west)]
        ne = [float(bounds.north), float(bounds.east)]
    except AttributeError:
        sw = [float(bounds[1]), float(bounds[0])]
        ne = [float(bounds[3]), float(bounds[2])]

    actual_min = float(np.nanmin(grid)) if not np.all(np.isnan(grid)) else 0.0
    actual_max = float(np.nanmax(grid)) if not np.all(np.isnan(grid)) else 10.0

    return {
        "grid":      flat,
        "shape":     [rows, cols],
        "bounds":    {"sw": sw, "ne": ne},
        "minLegend": float(min_leg) if min_leg is not None else actual_min,
        "maxLegend": float(max_leg) if max_leg is not None else actual_max,
        "meanSpeed": round(actual_min * 0.3 + actual_max * 0.7, 2),
    }


# ════════════════════════════════════════════════════════════
# /api/health
# ════════════════════════════════════════════════════════════

@app.get("/api/health")
def health():
    return {
        "status":       "ok",
        "infrared_key": bool(os.getenv("INFRARED_API_KEY")),
        "cached_polygons": len(_bld_cache),
    }


# ════════════════════════════════════════════════════════════
# /api/geometry  — fetch buildings + vegetation, cache both
# ════════════════════════════════════════════════════════════

class GeoRequest(BaseModel):
    polygon: dict


@app.post("/api/geometry")
def get_geometry(req: GeoRequest):
    polygon = req.polygon
    h       = poly_hash(polygon)
    file    = CACHE / f"geometry_{h}.json"

    # Return from disk cache if present
    if file.exists():
        print(f"📦  geometry cache hit  [{h}]")
        return JSONResponse(json.loads(file.read_text()))

    if not os.getenv("INFRARED_API_KEY"):
        raise HTTPException(503, "INFRARED_API_KEY not set")

    print(f"🌐  fetching geometry from Infrared …  [{h}]")
    from infrared_sdk import InfraredClient

    coords = polygon["coordinates"][0]
    sw_lon = min(c[0] for c in coords)
    sw_lat = min(c[1] for c in coords)

    with InfraredClient() as client:
        area     = client.buildings.get_area(polygon)
        area_veg = client.vegetation.get_area(polygon)

    # Cache DotBimMesh objects in memory (needed for simulations)
    _bld_cache[h] = area.buildings

    buildings = [b for bid, m in area.buildings.items()
                 if (b := mesh_to_dict(bid, m))]
    trees     = [t for tid, f in area_veg.features.items()
                 if (t := tree_to_dict(tid, f, sw_lon, sw_lat))]

    print(f"   ✓ {len(buildings)} buildings · {len(trees)} trees")

    result = {
        "polygon":   polygon,
        "swLon":     sw_lon,
        "swLat":     sw_lat,
        "buildings": buildings,
        "trees":     trees,
    }

    file.write_text(json.dumps(result))
    return result


# ════════════════════════════════════════════════════════════
# /api/simulate  — run wind-speed analysis
# ════════════════════════════════════════════════════════════

class SimRequest(BaseModel):
    polygon:        dict
    wind_speed:     int = 15    # 1–100 m/s (int only)
    wind_direction: int = 315   # meteorological degrees (315 = from NW)


@app.post("/api/simulate")
def run_simulation(req: SimRequest):
    polygon = req.polygon
    ph      = poly_hash(polygon)
    key     = f"{ph}_ws{req.wind_speed}_wd{req.wind_direction}"
    file    = CACHE / f"sim_{key}.json"

    if file.exists():
        print(f"📦  simulation cache hit  [{key}]")
        return JSONResponse(json.loads(file.read_text()))

    if not os.getenv("INFRARED_API_KEY"):
        raise HTTPException(503, "INFRARED_API_KEY not set")

    # Ensure buildings are cached in memory
    if ph not in _bld_cache:
        print(f"📐  pre-fetching buildings for simulation …")
        from infrared_sdk import InfraredClient
        with InfraredClient() as client:
            area = client.buildings.get_area(polygon)
        _bld_cache[ph] = area.buildings

    print(f"🌀  running wind simulation  ws={req.wind_speed}  wd={req.wind_direction}")
    from infrared_sdk import InfraredClient
    from infrared_sdk.analyses.types import WindModelRequest, AnalysesName

    with InfraredClient() as client:
        result = client.run_area_and_wait(
            WindModelRequest(
                analysis_type  = AnalysesName.wind_speed,
                wind_speed     = req.wind_speed,
                wind_direction = req.wind_direction,
            ),
            polygon,
            buildings = _bld_cache[ph],
        )

    print(f"   ✓ grid shape: {result.grid_shape}")

    payload = grid_to_payload(
        result.merged_grid,
        result.min_legend,
        result.max_legend,
        result.bounds,
    )
    payload["windSpeed"]     = req.wind_speed
    payload["windDirection"] = req.wind_direction

    file.write_text(json.dumps(payload))
    return payload


# ════════════════════════════════════════════════════════════
# Serve static files (HTML + JS + JSON)
# The static mount must be last so API routes take priority
# ════════════════════════════════════════════════════════════

@app.get("/")
def root():
    return RedirectResponse(url="/windsite.html")

app.mount("/", StaticFiles(directory=str(HERE), html=False), name="static")


if __name__ == "__main__":
    import uvicorn
    print("🌬  WindSite server — http://localhost:8000")
    print("   Ctrl+C to stop")
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=False)
