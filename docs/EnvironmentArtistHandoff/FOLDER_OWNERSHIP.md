# Folder ownership conventions (environment)

Aligned with `docs/WORLD_AUTHORING_WORKFLOW.md`. Artists place and promote content here; gameplay developers do not dump logic Blueprints into these folders.

---

## Content layout

```text
/Game/RedMMO/World/Quarantine/<PackName>/     ← new marketplace imports (review only)
/Game/RedMMO/World/Approved/<PackName>/       ← passed pivot/scale/collision/perf
/Game/RedMMO/World/Biomes/<BiomeName>/Palettes/
/Game/RedMMO/World/ManualPOI/<RegionId>/<POIName>/
```

| Folder | Who writes | Rule |
|---|---|---|
| `World/Quarantine/*` | Env artist / import pass | Never drag straight into production maps |
| `World/Approved/*` | Env after review | Source for placement |
| `World/Biomes/*/Palettes` | Env | Data Assets (`URedWorldAssetPalette`) |
| `World/ManualPOI/*` | Env | Hand-authored colonies / landmarks |
| `Maps/RedPlanetGen_50km_ArtistCanvas` | Env (canvas) | Do not put networked gameplay actors here long-term |
| `Maps/Sandbox_DesertDemoSparkle_T01` | Env / LD experiments | Prefer spawning a new `L_Env_*` delivery sublevel from it |
| `Maps/RedPlanetGen` (+ 50km Test / FusedPrototype) | **Protected** | Read-only without explicit gate |
| Character / Weapons / GameMode packages | Gameplay | Artists do not edit |

---

## Map package naming (delivery)

Prefer names that make ownership obvious:

```text
/Game/RedMMO/Maps/Hubs/L_Hub_Persistent
/Game/RedMMO/Maps/Hubs/L_Hub_Env_Visuals
/Game/RedMMO/Maps/Hubs/L_Hub_Gameplay_Logic
```

Or World Partition Data Layers: `DL_Env`, `DL_Gameplay`.

---

## Marketplace masters

- Do **not** edit Fab/Marketplace master materials or meshes in place.  
- Create project-owned Material Instances under `/Game/RedMMO/World/...` or `/Game/RedMMO/Environment/...`.  
- Keep vendor pack folders intact for updates.

---

## Outliner hygiene

- Group env actors under folders: `Env/Landscape`, `Env/Foliage`, `Env/Lighting`, `Env/Dressing`.  
- Group gameplay under `Gameplay/Spawns`, `Gameplay/Volumes`, `Gameplay/Interactables`.  
- Add **Red Manual Placement Protection** on hand-authored POI roots when using the planetary workflow (see world authoring guide).
