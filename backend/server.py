"""
server.py — WindSite backend (FastAPI)

Local dev:
    cd backend
    uvicorn server:app --reload --port 8000

Render (production):
    render.yaml handles the start command; PORT is set automatically.

Environment variables:
    INFRARED_API_KEY   — required
    DATABASE_URL       — optional; defaults to sqlite:///./windsite.db
                         Set to your Neon Postgres URL on Render.
"""

from __future__ import annotations
import json, hashlib, math, os
from typing import Any

import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import sqlalchemy

from database import SessionLocal, GeometryCache, Simulation, init_db

app = FastAPI(title="WindSite API", version="2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory store for DotBimMesh objects (not JSON-serialisable, not DB-storable)
_bld_cache: dict[str, Any] = {}


@app.on_event("startup")
def on_startup():
    init_db()


# ════════════════════════════════════════════════════════════
# HELPERS
# ════════════════════════════════════════════════════════════

def poly_hash(polygon: dict) -> str:
    return hashlib.md5(json.dumps(polygon, sort_keys=True).encode()).hexdigest()[:12]


def mesh_to_dict(bid: str, mesh) -> dict | None:
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
    h, w   = grid.shape
    step   = max(1, max(h, w) // 128)
    small  = grid[::step, ::step]
    rows, cols = small.shape

    flat = [
        [None if math.isnan(v) else round(float(v), 2) for v in row]
        for row in small.tolist()
    ]

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
    db_ok = False
    try:
        with SessionLocal() as db:
            db.execute(sqlalchemy.text("SELECT 1"))
            db_ok = True
    except Exception:
        pass
    return {
        "status":       "ok",
        "infrared_key": bool(os.getenv("INFRARED_API_KEY")),
        "db":           "connected" if db_ok else "error",
    }


# ════════════════════════════════════════════════════════════
# /api/geometry
# ════════════════════════════════════════════════════════════

class GeoRequest(BaseModel):
    polygon: dict


@app.post("/api/geometry")
def get_geometry(req: GeoRequest):
    polygon = req.polygon
    h       = poly_hash(polygon)

    with SessionLocal() as db:
        cached = db.query(GeometryCache).filter_by(polygon_hash=h).first()
        if cached:
            print(f"📦  geometry DB hit  [{h}]")
            return JSONResponse(cached.data)

    if not os.getenv("INFRARED_API_KEY"):
        raise HTTPException(503, "INFRARED_API_KEY not set")

    print(f"🌐  fetching geometry from Infrared …  [{h}]")
    from infrared_sdk import InfraredClient

    coords  = polygon["coordinates"][0]
    sw_lon  = min(c[0] for c in coords)
    sw_lat  = min(c[1] for c in coords)

    with InfraredClient() as client:
        area     = client.buildings.get_area(polygon)
        area_veg = client.vegetation.get_area(polygon)

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

    with SessionLocal() as db:
        db.add(GeometryCache(polygon_hash=h, data=result))
        db.commit()

    return result


# ════════════════════════════════════════════════════════════
# /api/simulate
# ════════════════════════════════════════════════════════════

class SimRequest(BaseModel):
    polygon:        dict
    wind_speed:     int = 10
    wind_direction: int = 315


@app.post("/api/simulate")
def run_simulation(req: SimRequest):
    polygon = req.polygon
    ph      = poly_hash(polygon)

    with SessionLocal() as db:
        cached = db.query(Simulation).filter_by(
            polygon_hash   = ph,
            wind_direction = req.wind_direction,
            wind_speed_ref = req.wind_speed,
        ).first()
        if cached:
            print(f"📦  simulation DB hit  [{ph} wd={req.wind_direction}]")
            return JSONResponse(cached.payload)

    if not os.getenv("INFRARED_API_KEY"):
        raise HTTPException(503, "INFRARED_API_KEY not set")

    if ph not in _bld_cache:
        print("📐  pre-fetching buildings for simulation …")
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

    with SessionLocal() as db:
        db.add(Simulation(
            polygon_hash   = ph,
            wind_direction = req.wind_direction,
            wind_speed_ref = req.wind_speed,
            payload        = payload,
        ))
        db.commit()

    return payload


if __name__ == "__main__":
    import uvicorn
    print("🌬  WindSite API — http://localhost:8000")
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=False)
