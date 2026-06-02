# WindSite — Architecture Diagrams
# Paste each Mermaid block into Miro → Apps → Mermaid

---

## DIAGRAM 1 · COMPONENT — What are the parts?

```mermaid
flowchart LR
    A["**Frontend**\nwindsite.html\nbrowser"]
    B["**Backend**\nserver.py\nFastAPI · uvicorn"]
    C["**Infrared SDK**\ninfraed.city\nCFD engine"]
    D[("**File Cache**\n./cache/\nJSON files")]

    A -- "HTTP request" --> B
    B -- "API key + polygon" --> C
    C -. "result grid" .-> B
    B -- "read / write" --> D
    B -. "result JSON" .-> A
```

---

## DIAGRAM 2 · SEQUENCE — What happens, in what order?

```mermaid
sequenceDiagram
    actor User
    participant F as Frontend
    participant B as Backend
    participant C as File Cache
    participant I as Infrared SDK

    User->>F: draw polygon · click Run
    F->>B: POST /api/simulate
    B->>C: check cache

    alt cache hit
        C-->>B: cached result
    else cache miss
        B->>I: run CFD (API key · 10 m/s ref)
        I-->>B: result grid
        B->>C: save result JSON
    end

    B-->>F: result JSON
    F-->>User: heatmap · EPW-scaled stats

    User->>F: open 3D Explore
    F->>B: POST /api/geometry
    B->>C: check cache

    alt cache miss
        B->>I: fetch buildings + trees
        I-->>B: DotBim geometry
        B->>C: save geometry JSON
    end

    B-->>F: geometry JSON
    F-->>User: 3D city · wind stick · pins
```

---

## DIAGRAM 3 · ENTITY-RELATIONSHIP — What data, and how is it related?

```mermaid
erDiagram
    POLYGON {
        string hash PK
        json coordinates
        float sw_lon
        float sw_lat
    }

    SIMULATION {
        string id PK
        string polygon_hash FK
        int wind_direction
        int wind_speed_ref
        json grid
        float min_legend
        float max_legend
        json bounds
        int rows
        int cols
    }

    GEOMETRY {
        string polygon_hash FK
        string fetched_at
    }

    BUILDING {
        string id PK
        string polygon_hash FK
        float height
        float cx
        float cy
        json vertices
        json indices
    }

    TREE {
        string id PK
        string polygon_hash FK
        float x
        float y
        float height
        float crown_radius
    }

    POLYGON ||--o{ SIMULATION : "has"
    POLYGON ||--|| GEOMETRY : "has"
    GEOMETRY ||--o{ BUILDING : "contains"
    GEOMETRY ||--o{ TREE : "contains"
```

---

## DIAGRAM 4 · DEPLOYMENT — Where does each part run?

```mermaid
flowchart TB
    subgraph LOCAL["User's Machine"]
        direction TB
        subgraph BROWSER["Browser  —  localhost:8000"]
            F["windsite.html\nFrontend"]
        end
        subgraph PROCESS["Python Process  —  localhost:8000"]
            B["server.py\nFastAPI + uvicorn"]
            ENV["INFRARED_API_KEY\nenv variable"]
        end
        subgraph FS["Local Filesystem"]
            CACHE[("./cache/\nJSON files")]
        end
        F <-- "HTTP" --> B
        ENV --> B
        B <-- "read / write" --> CACHE
    end

    subgraph CLOUD["External  —  infrared.city"]
        I["Infrared API\nCFD engine"]
    end

    B <-- "HTTPS" --> I
```
