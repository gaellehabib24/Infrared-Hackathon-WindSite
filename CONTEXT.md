# WindSite — Context & Architecture

## What this tool does

WindSite identifies which locations in an urban fabric are viable candidates for small wind turbine installation. It takes a drawn site polygon, runs a wind simulation via the Infrared SDK, and produces a location-specific feasibility assessment for four turbine installation types.

---

## Why Infrared is the core engine

EPW (EnergyPlus Weather) files give you the ambient wind speed at a meteorological station — one number for an entire city, measured in open terrain. That number tells you nothing about whether a specific rooftop, street corner, or lamppost in a dense urban area actually receives enough wind.

Urban wind is shaped by the buildings around it. A rooftop on a sheltered interior courtyard and a rooftop on an exposed corner two blocks away can differ by 40% in wind speed even if they're under the same EPW reading. Street canyons accelerate wind through the venturi effect. Tall buildings create wakes that slow wind for hundreds of metres downwind.

**Infrared simulates this.** It runs a wind flow simulation over the actual 3D urban geometry and returns a spatial wind speed grid at near-ground level. This grid is the diagnostic layer that tells you which locations in the site are worth pursuing.

---

## The Two-Zone Wind Model

Wind behaviour changes fundamentally at rooftop height. Below it, buildings dominate. Above it, the flow is effectively free-field again.

```
┌──────────────────────────────────────────────┐
│  ZONE 2 — Above rooftop                      │
│  Free-field conditions. Buildings irrelevant. │
│  Data source: EPW file (hourly, 8760/yr)      │
│  Power law: open-terrain α (0.10–0.14)        │
├──────────────────────────────────────────────┤  ← mean rooftop height
│  ZONE 1 — Ground → rooftop                   │
│  Urban canyon / building wake effects.        │
│  Data source: Infrared SDK wind simulation    │
│  Power law: urban α (0.22–0.28)               │
└──────────────────────────────────────────────┘  ← ground level
```

The boundary (mean rooftop height) is estimated from building height data in the site polygon.

Extrapolation formula (both zones):
```
V(h2) = V(h1) × (h2 / h1)^α
```

In Zone 1, V(h1) is the Infrared ground-level reading.  
In Zone 2, V(h1) is the EPW reading at mean rooftop height.

---

## Turbine Installation Types

### Lamppost VAWT — Hub: ~5 m (street level)
Small vertical-axis turbines mounted on urban lampposts or street furniture. Only viable where Infrared shows sustained wind speed above 5 m/s at street level — typically in exposed corridors, coastal fronts, or strong venturi gaps between buildings. Bird risk is low (urban street environment). Noise and aesthetic regulations apply.

### Rooftop VAWT — Hub: rooftop + 3 m
Vertical-axis turbines on building rooftops. Tolerant of turbulent, variable wind direction — the main advantage over HAWTs in urban settings. Viable from ~3.5 m/s. Best candidates are buildings with exposed roof edges confirmed by Infrared.

### Rooftop HAWT — Hub: rooftop + 8 m
Horizontal-axis turbines on a mast above the roofline. Requires cleaner, more directional flow — needs the turbine hub to be above the turbulent rooftop boundary layer (typically +6–10 m). Infrared identifies buildings where the rooftop flow is consistent enough. Min: ~4.5 m/s.

### Community HAWT — Hub: rooftop + 30 m
Larger turbines elevated well above the urban fabric. At this height they operate almost entirely in Zone 2 (free-field). Infrared contribution is limited to identifying which buildings have the best rooftop base speed before extrapolation. EPW drives the final calculation. Min: ~5.5 m/s.

---

## Pipeline

```
1. User draws polygon on map
       ↓
2. Infrared SDK — wind simulation
   • Runs wind flow over 3D urban geometry
   • Returns: speed grid (m/s), direction vectors, per-cell
       ↓
3. Preprocessing
   • Extract cells inside polygon
   • Compute: mean speed, peak speed, dominant direction
   • Estimate mean rooftop height from building data
       ↓
4. Zone 1 extrapolation (Infrared → rooftop)
   • Power law with urban α per terrain type
   • Applied per turbine hub height
       ↓
5. Zone 2 extrapolation (EPW → above rooftop)
   • Load EPW monthly/hourly profile for city
   • Power law with open-terrain α
   • Apply seasonal and diurnal multipliers
       ↓
6. Feasibility assessment
   • Compare extrapolated speed vs. min threshold per turbine type
   • Output: Not Feasible / Marginal / Feasible / Highly Feasible
       ↓
7. 3D visualisation
   • Turbine placed by user on 3D cityscape
   • Real-time speed at cursor height, zone indicator, season/hour controls
```

---

## Data Sources

| Data | Source | Notes |
|---|---|---|
| Urban wind grid | Infrared SDK | Simulation over site polygon |
| Ambient wind (above roof) | EPW file (climate.onebuilding.org) | Barcelona: free download |
| Building heights | OpenStreetMap `building:height` tags | Used for rooftop boundary |
| Terrain roughness (α) | User-selected terrain type | Suburban 0.22, Dense urban 0.28 |

---

## Key limitation

Infrared simulates wind at near-ground/pedestrian level. The power law extrapolation to rooftop height is an approximation — valid for pre-feasibility screening but not a substitute for an on-site anemometer campaign before any real installation decision.
