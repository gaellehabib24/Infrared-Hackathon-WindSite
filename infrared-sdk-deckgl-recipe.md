# Recipe: Mapbox + deck.gl + Cesium Ion (Google 3D Tiles) + Infrared SDK results

A non-verbose, copy-pasteable starting point for a web app that:

- renders **Google Photorealistic 3D Tiles** (via Cesium Ion, EU-friendly)
- visualises **Infrared Python SDK** simulation results as deck.gl layers
- supports a **study-area cutout** in the photogrammetry
- lifts everything to the photogrammetric ground (**height offset**)
- lets you stack your **own indicators** on top

Stack: React + `react-map-gl` + Mapbox GL + deck.gl `MapboxOverlay` (interleaved).

---

## 0. Deps & env

```bash
npm install mapbox-gl react-map-gl \
  @deck.gl/core @deck.gl/layers @deck.gl/geo-layers @deck.gl/mapbox @deck.gl/extensions \
  @loaders.gl/3d-tiles
```

`.env.local`:

```
VITE_MAPBOX_TOKEN=pk.xxxx
VITE_CESIUM_ION_TOKEN=eyJxxxx
```

You need:

- A **Mapbox** account (free tier is fine) — for the basemap and the terrain DEM.
- A **Cesium Ion** account (free tier: 1,000 sessions/mo, 15 GB) — to proxy Google Photorealistic 3D Tiles. Asset ID **`2275207`**. This works inside the EEA where the direct Google Maps Tiles API is blocked.

---

## 1. Mapbox + deck.gl overlay (interleaved)

```tsx
import 'mapbox-gl/dist/mapbox-gl.css'
import { Map, useControl } from 'react-map-gl'
import { MapboxOverlay } from '@deck.gl/mapbox'
import { useEffect } from 'react'

function DeckOverlay({ layers }: { layers: any[] }) {
  const overlay = useControl(() => new MapboxOverlay({ interleaved: true, layers: [] }))
  useEffect(() => { overlay.setProps({ layers }) }, [overlay, layers])
  return null
}
```

`interleaved: true` is **mandatory** — it lets deck.gl layers share the depth buffer with `Tile3DLayer`. Without it, your buildings either float in front of, or sink behind, the photogrammetry mesh.

**Do not** call `map.setTerrain(...)`. Mapbox's native terrain rendering fights deck.gl's depth buffer in interleaved mode and crashes `Tile3DLayer`'s scenegraph sublayers.

---

## 2. Cesium Ion → Google Photorealistic 3D Tiles

Each `Tile3DLayer` mount = one billable session. Keep the layer mounted across zoom-out cycles; only unmount on an explicit user toggle-off.

### 2.1 Resolve the tileset URL once per session

```ts
async function resolveCesiumTilesetUrl(): Promise<string> {
  const r = await fetch(
    `https://api.cesium.com/v1/assets/2275207/endpoint`,
    { headers: { Authorization: `Bearer ${import.meta.env.VITE_CESIUM_ION_TOKEN}` } },
  )
  if (!r.ok) throw new Error(`Cesium ion endpoint ${r.status}`)
  const data = await r.json() as { options?: { url?: string }, url?: string }
  // External 3D Tiles assets (Google) put the URL at options.url and pre-embed
  // the Google Maps key as a query param. There's no separate accessToken.
  const url = data.options?.url ?? data.url
  if (!url) throw new Error('Cesium ion: missing tileset URL')
  return url
}
```

Cache the resolved URL for the page's lifetime — don't refetch on every mount.

### 2.2 Create the layer

```ts
import { Tile3DLayer } from '@deck.gl/geo-layers'
import { Tiles3DLoader } from '@loaders.gl/3d-tiles'

new Tile3DLayer({
  id: 'g3d',
  data: tilesetUrl,
  loader: Tiles3DLoader,
  opacity,                 // fade in between MIN_ZOOM..FULL_ZOOM
  pickable: false,
  loadOptions: {
    tileset: {
      maximumScreenSpaceError: 12,   // 12 = sharp without overfetch (default is 8)
      maximumMemoryUsage: 512,       // MB resident
      maxRequests: 16,               // concurrent tile fetches
      debounceTime: 80,              // ms — skip mid-flyTo selection
      viewDistanceScale: 0.8,
    },
  },
  onTilesetLoad: (tileset: any) => {
    // tileset.credits.attributions[].html — show this somewhere for legal compliance.
  },
})
```

### 2.3 Zoom gating + mount latch

The mesh has no detail above zoom ~12. Gate by zoom to avoid pulling tiles you can't see:

```ts
const MIN_ZOOM = 13   // start fading in
const FULL_ZOOM = 15  // full opacity

const opacity = Math.min(1, Math.max(0, (zoom - MIN_ZOOM) / (FULL_ZOOM - MIN_ZOOM)))
```

**Mount latch:** once the user has crossed `MIN_ZOOM` with tiles enabled in a session, keep the `Tile3DLayer` mounted across subsequent zoom-out → zoom-in cycles. Each fresh mount triggers a new root tileset fetch, which counts against your session quota. Store the latch at **module scope**, not in a `useRef` (so HMR doesn't change the hook count).

---

## 3. Boundary cutout (mask the photogrammetry inside your study area)

Use a hidden mask layer plus `MaskExtension` with `maskInverted: true`. The extension propagates from `Tile3DLayer` to its spawned ScenegraphLayer sublayers automatically.

```ts
import { MaskExtension } from '@deck.gl/extensions'
import { SolidPolygonLayer } from '@deck.gl/layers'

const MASK_ID = 'cutout-mask'

const layers = [
  // Hidden mask layer — never drawn, only feeds the mask texture.
  new SolidPolygonLayer({
    id: MASK_ID,
    operation: 'mask',
    data: [{ polygon: outerRing /* [[lng, lat], ...] */ }],
    getPolygon: (d) => d.polygon,
  }),

  new Tile3DLayer({
    id: 'g3d',
    data: tilesetUrl,
    loader: Tiles3DLoader,
    extensions: [new MaskExtension()],
    maskId: MASK_ID,
    maskInverted: true,    // cut a hole INSIDE the polygon
    // ...rest of props
  }),
]
```

Outside the ring → photogrammetry. Inside the ring → your scenario, heatmap, or a clean basemap floor.

**Don't** try to manually forward extensions via `_subLayerProps: { scenegraph: {...} }` — it breaks ScenegraphLayer's init assertions.

### Optional: clay tint of the photogrammetry

Write a tiny `LayerExtension` that injects a fragment-shader snippet via `DECKGL_FILTER_COLOR` to desaturate / shift the mesh color (e.g. white-clay, dark-clay):

```ts
import { LayerExtension } from '@deck.gl/core'

const tintShaderModule = {
  name: 'tint',
  vs: 'layout(std140) uniform tintUniforms { float mode; } tint;',
  fs: 'layout(std140) uniform tintUniforms { float mode; } tint;',
  inject: {
    'fs:DECKGL_FILTER_COLOR': `
      if (tint.mode > 0.5) {
        float lum = dot(color.rgb, vec3(0.299, 0.587, 0.114));
        vec3 desat = mix(color.rgb, vec3(lum), 0.85);
        // bright clay: lift to warm off-white
        color.rgb = mix(desat, vec3(0.92, 0.91, 0.88), 0.35);
      }
    `,
  },
  uniformTypes: { mode: 'f32' },
  getUniforms: (opts: any) => ({ mode: opts?.mode ?? 0 }),
}

export class TintExtension extends LayerExtension {
  static extensionName = 'TintExtension'
  static defaultProps = { tintMode: 0 }
  getShaders() { return { modules: [tintShaderModule] } }
  draw(this: any) {
    this.setShaderModuleProps({ tint: { mode: this.props.tintMode ?? 0 } })
  }
}
```

Attach it on the `Tile3DLayer` alongside `MaskExtension`.

---

## 4. Height offset (so your scenarios sit on the photogrammetric ground)

Google 3D Tiles are anchored to the **WGS84 ellipsoid**. Mapbox DEM and GeoJSON heights are **orthometric** (above mean sea level). The difference is the geoid undulation — at most coordinates, tens of metres. Without correction, your extruded buildings either hover in the sky or sink into the road.

### 4.1 Simple — uniform Z-translation at scene centroid

Good enough for sites ≤ ~2 km wide.

```ts
const MAPBOX_TOKEN = import.meta.env.VITE_MAPBOX_TOKEN

// Sample Mapbox's raster DEM at one point.
// Encoding: height(m) = -10000 + (R*65536 + G*256 + B) * 0.1
export async function fetchDemElevation(lon: number, lat: number): Promise<number | null> {
  const zoom = 14
  const tileSize = 512
  const n = 2 ** zoom
  const worldX = ((lon + 180) / 360) * n * tileSize
  const latRad = (lat * Math.PI) / 180
  const worldY = ((1 - Math.log(Math.tan(latRad) + 1 / Math.cos(latRad)) / Math.PI) / 2) * n * tileSize
  const tx = Math.floor(worldX / tileSize)
  const ty = Math.floor(worldY / tileSize)
  const px = Math.floor(worldX - tx * tileSize)
  const py = Math.floor(worldY - ty * tileSize)
  const url = `https://api.mapbox.com/v4/mapbox.mapbox-terrain-dem-v1/${zoom}/${tx}/${ty}@2x.pngraw?access_token=${MAPBOX_TOKEN}`
  const resp = await fetch(url)
  if (!resp.ok) return null
  const blob = await resp.blob()
  const bmp = await createImageBitmap(blob)
  const canvas = new OffscreenCanvas(bmp.width, bmp.height)
  const ctx = canvas.getContext('2d')!
  ctx.drawImage(bmp, 0, 0)
  const sx = Math.min(bmp.width - 1, Math.floor((px * bmp.width) / tileSize))
  const sy = Math.min(bmp.height - 1, Math.floor((py * bmp.height) / tileSize))
  const d = ctx.getImageData(sx, sy, 1, 1).data
  return -10000 + (d[0] * 65536 + d[1] * 256 + d[2]) * 0.1
}
```

For coarse use you can approximate the geoid as a constant (it varies slowly across a city). For accuracy, interpolate from EGM2008 — there are small JS libraries for this, or sample a small lookup table.

Then build a column-major 4×4 translate-Z matrix and pass it as `modelMatrix` on every overlay layer:

```ts
const liftMeters = orthometric + geoidUndulation - 2  // -2m to sit just under the mesh
const modelMatrix = [1,0,0,0, 0,1,0,0, 0,0,1,0, 0,0, liftMeters, 1]

new PolygonLayer({ /* ...props */, modelMatrix })
new BitmapLayer({  /* ...props */, modelMatrix })
```

### 4.2 Full — per-vertex terrain follow

Drape every overlay onto a terrain surface so buildings on a slope tilt correctly:

1. Add an invisible `TerrainLayer` (`@deck.gl/geo-layers`) sourced from the Mapbox DEM. It exists only to provide a depth texture.
2. Attach `_TerrainExtension` from `@deck.gl/extensions` to every consumer layer, with `terrainDrawMode: 'drape'` (flat polygons, heatmaps) or `'offset'` (extruded buildings, columns).

### 4.3 Centralise the choice

Build one switchboard and one applier so every layer gets the same elevation treatment:

```ts
type ElevationModifier =
  | { type: 'modelMatrix', matrix: number[] }
  | { type: 'extensions', extensions: any[], terrainDrawMode: 'drape' | 'offset' }

export function applyElevationProps(mod: ElevationModifier | null) {
  if (!mod) return {}
  if (mod.type === 'modelMatrix') return { modelMatrix: mod.matrix }
  return { extensions: mod.extensions, terrainDrawMode: mod.terrainDrawMode }
}

// Usage on every overlay:
new PolygonLayer({ ...props, ...applyElevationProps(mod) })
new BitmapLayer({  ...props, ...applyElevationProps(mod) })
```

---

## 5. Infrared SDK simulation results → deck.gl

The Infrared async SDK (OGC API Processes, GPU models) returns one of two shapes:

- **Raster** — a 2D matrix (e.g. 512×512) of floats, with a geographic bounds box. Wind, solar, thermal comfort, daylight, etc.
- **Vector** — features (points / polygons) with properties.

### 5.1 Raster results → `BitmapLayer`

Colorise the matrix once on the client, then drape as a `BitmapLayer`.

```ts
import { BitmapLayer } from '@deck.gl/layers'

function colorizeMatrix(values: Float32Array, w: number, h: number, scale: (v: number) => [number, number, number, number]): ImageData {
  const data = new Uint8ClampedArray(w * h * 4)
  for (let i = 0; i < values.length; i++) {
    const [r, g, b, a] = scale(values[i])
    data[i * 4 + 0] = r
    data[i * 4 + 1] = g
    data[i * 4 + 2] = b
    data[i * 4 + 3] = a
  }
  return new ImageData(data, w, h)
}

// SDK returns bounds in [[southLat, westLon], [northLat, eastLon]].
// BitmapLayer needs [west, south, east, north]:
function toDeckBounds([[s, w], [n, e]]: [[number, number], [number, number]]): [number, number, number, number] {
  return [w, s, e, n]
}

new BitmapLayer({
  id: `sdk-${runId}`,
  image: colorizeMatrix(values, w, h, myColorScale),
  bounds: toDeckBounds(sdkBounds),
  opacity: 0.65,
  ...applyElevationProps(mod),       // ride the photogrammetry mesh
  parameters: { depthTest: true },
})
```

Keep the color scale + KPI logic **pure** (no deck.gl import) so you can unit-test it headless.

### 5.2 Stitching tiled results

If you call the SDK once per tile, fetch in parallel and **merge into one matrix before colorisation**. Render one merged `BitmapLayer`, not one per tile. Per-tile bitmaps create visible seams at the edges and multiply your draw calls.

### 5.3 Indicator overlays on top

Compute KPI values from the matrix (mean, percentiles, threshold counts) and emit standard deck.gl layers:

| Indicator | Layer | Notes |
|---|---|---|
| Building extrusions from GeoJSON | `PolygonLayer` | `extruded: true`, `getElevation: f => f.properties.height_m` |
| Point pins | `ScatterplotLayer` | `radiusUnits: 'meters'`. For "always on top" set `parameters: { depthTest: false }` |
| Icon markers | `IconLayer` | sprite-based |
| Per-cell bars | `ColumnLayer` | **`radius` is a uniform, not an accessor** — group by size class and emit one layer per group |
| Probe / hover indicator | `ScatterplotLayer` over the map (NOT a CSS div) | CSS overlays don't work with pitch/bearing and break when the user enables 3D |
| Custom GLTF (street furniture, trees) | `ScenegraphLayer` | needs glTF binary |
| Generic vector | `GeoJsonLayer` | |

Custom indicators with the **same** `applyElevationProps(mod)` so they share the lift.

---

## 6. Composition order (matters)

deck.gl renders the array in order. Later layers win for non-depth-tested fragments.

```ts
overlay.setProps({ layers: [
  ...google3DTilesLayers,    // photogrammetry first (bottom)
  ...boundaryOutlineLayers,  // ring stroke
  ...scenarioLayers,         // your extruded buildings
  ...sdkRasterLayers,        // SDK heatmap drape
  ...indicatorLayers,        // pins / KPI cards on top
]})
```

---

## 7. Gotchas (each one will cost you hours otherwise)

- **`interleaved: true`** on `MapboxOverlay` is required for depth-correct compositing with `Tile3DLayer`.
- **Never call `map.setTerrain(...)`** while `Tile3DLayer` is active. Use the direct DEM fetch (§4.1) or `_TerrainExtension` (§4.2) instead.
- The **Cesium Ion endpoint** must be resolved once per session; cache the URL. Don't refetch on every render.
- Latch the "ever crossed `MIN_ZOOM`" flag at **module scope**, not in a `useRef` — HMR can change hook counts otherwise.
- Mapbox style: set `show3dObjects: false` whenever Google 3D Tiles are visible, otherwise you get z-fighting between Mapbox's 3D building extrusions and the photogrammetry mesh.
- `BitmapLayer` bounds are **`[W, S, E, N]`**, not `[[lat, lon], [lat, lon]]`. The SDK gives you the latter — convert.
- Import `COORDINATE_SYSTEM` from `@deck.gl/core`, **not** from the `deck.gl` barrel — module mismatch causes `BitmapLayer` init assertions on every frame.
- `Tile3DLayer` sublayers receive parent extensions automatically. Do **not** manually forward via `_subLayerProps`.
- `ColumnLayer.radius` is a uniform, not an accessor. There is no `getRadius`. Group rows by size and emit one layer per group.
- Refs do not trigger re-renders. For 60fps overlays driven by an external source, use a `requestAnimationFrame` loop + `setNeedsRedraw()`, not a ref inside `useMemo`.
- Test with the **outcome**, not the implementation detail. Asserting on `spy.callCount` breaks the moment you switch sync → async, even when the behaviour is right.

---

## 8. Minimum end-to-end scaffold

One file, all the moving parts:

```tsx
import 'mapbox-gl/dist/mapbox-gl.css'
import { useEffect, useMemo, useState } from 'react'
import { Map, useControl } from 'react-map-gl'
import { MapboxOverlay } from '@deck.gl/mapbox'
import { Tile3DLayer } from '@deck.gl/geo-layers'
import { BitmapLayer, SolidPolygonLayer, PolygonLayer } from '@deck.gl/layers'
import { MaskExtension } from '@deck.gl/extensions'
import { Tiles3DLoader } from '@loaders.gl/3d-tiles'

function useCesiumTilesetUrl() {
  const [url, setUrl] = useState<string | null>(null)
  useEffect(() => {
    fetch(`https://api.cesium.com/v1/assets/2275207/endpoint`, {
      headers: { Authorization: `Bearer ${import.meta.env.VITE_CESIUM_ION_TOKEN}` },
    })
      .then(r => r.json())
      .then(d => setUrl(d.options?.url ?? d.url ?? null))
      .catch(console.error)
  }, [])
  return url
}

function Overlay({ tilesetUrl, boundary, sdkRaster }: {
  tilesetUrl: string | null
  boundary: number[][] | null                                       // [[lng, lat], ...]
  sdkRaster: { image: ImageData | string, bounds: [number, number, number, number] } | null
}) {
  const overlay = useControl(() => new MapboxOverlay({ interleaved: true, layers: [] }))

  const layers = useMemo(() => {
    const out: any[] = []

    const hasMask = boundary && boundary.length >= 3
    if (hasMask) {
      out.push(new SolidPolygonLayer({
        id: 'cutout-mask',
        operation: 'mask',
        data: [{ polygon: boundary }],
        getPolygon: (d: any) => d.polygon,
      }))
    }

    if (tilesetUrl) {
      out.push(new Tile3DLayer({
        id: 'g3d',
        data: tilesetUrl,
        loader: Tiles3DLoader,
        opacity: 1,
        pickable: false,
        loadOptions: {
          tileset: { maximumScreenSpaceError: 12, maximumMemoryUsage: 512, maxRequests: 16 },
        },
        extensions: hasMask ? [new MaskExtension()] : [],
        ...(hasMask ? { maskId: 'cutout-mask', maskInverted: true } : {}),
      }))
    }

    if (hasMask) {
      out.push(new PolygonLayer({
        id: 'boundary-outline',
        data: [{ polygon: boundary }],
        getPolygon: (d: any) => d.polygon,
        stroked: true, filled: false,
        getLineColor: [43, 124, 133, 240],
        getLineWidth: 3, lineWidthMinPixels: 2,
      }))
    }

    if (sdkRaster) {
      out.push(new BitmapLayer({
        id: 'sdk-raster',
        image: sdkRaster.image,
        bounds: sdkRaster.bounds,
        opacity: 0.65,
      }))
    }

    return out
  }, [tilesetUrl, boundary, sdkRaster])

  useEffect(() => { overlay.setProps({ layers }) }, [overlay, layers])
  return null
}

export function App({ boundary, sdkRaster }: any) {
  const tilesetUrl = useCesiumTilesetUrl()
  return (
    <Map
      mapboxAccessToken={import.meta.env.VITE_MAPBOX_TOKEN}
      initialViewState={{ longitude: 9.99, latitude: 53.54, zoom: 15, pitch: 60, bearing: 0 }}
      mapStyle="mapbox://styles/mapbox/standard"
      style={{ width: '100vw', height: '100vh' }}
    >
      <Overlay tilesetUrl={tilesetUrl} boundary={boundary} sdkRaster={sdkRaster} />
    </Map>
  )
}
```

That gets you basemap + photogrammetry + cutout + SDK raster. Add the elevation lift (§4) and your indicator layers (§6) on top.

---

## 9. Where to extend next

- **Camera flyTo on study-area pick:** imperative `map.flyTo({ center, zoom, pitch, bearing })` driven by a small store with a monotonic nonce — bypass React reactive cycles.
- **Drawing the boundary:** `react-map-gl-draw` or Mapbox GL Draw, then feed the polygon into the mask layer and the SDK request.
- **Multiple SDK runs side-by-side:** keep a `Map<runId, BitmapLayer>` keyed by run, and swap `image`/`bounds` on update. Don't recreate the layer when only the matrix changed — pass a new `image` and let deck.gl diff.
- **Animation across hours / scenarios:** keep the colorized `ImageData` in a module-level cache keyed by `(runId, scenarioKey, hour)`; swap by setting `image` on the existing `BitmapLayer`.
- **Pricing / quotas:** Cesium Ion free tier is 1,000 sessions/mo. One mount = one session. Mount-latch (§2.3) is what keeps you inside the quota.

That's the whole recipe.
