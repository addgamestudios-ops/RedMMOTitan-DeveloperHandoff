# Folder ownership conventions (environment)

Aligned with merge-safe hub packages and `docs/WORLD_AUTHORING_WORKFLOW.md`. Artists place and promote content here; gameplay developers do not dump logic Blueprints into these folders.

---

## Hub map packages (first)

```text
/Game/RedMMO/Maps/Hubs/L_Hub_Persistent       ← lead / rare (streaming only)
/Game/RedMMO/Maps/Hubs/L_Hub_Env_Visuals      ← environment artist (you)
/Game/RedMMO/Maps/Hubs/L_Hub_Gameplay_Logic   ← gameplay developer (do not edit)
```

Or World Partition Data Layers: `DL_Env`, `DL_Gameplay` — same ownership idea.

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
| `Maps/Hubs/L_Hub_Env_Visuals` | **Env** | Hub delivery ownership |
| `Maps/Hubs/L_Hub_Gameplay_Logic` | Gameplay | Artists do not edit |
| `Maps/Hubs/L_Hub_Persistent` | Lead / rare | Streaming membership only |
| `World/Quarantine/*` | Env / import pass | Never drag straight into production maps |
| `World/Approved/*` | Env after review | Source for placement |
| `World/Biomes/*/Palettes` | Env | Data Assets (`URedWorldAssetPalette`) |
| `World/ManualPOI/*` | Env | Hand-authored colonies / landmarks |
| `Maps/RedPlanetGen_50km_ArtistCanvas` | Env (canvas) | Look-dev; do not put networked gameplay actors here long-term |
| `Maps/Sandbox_DesertDemoSparkle_T01` | Env / LD experiments | Prefer delivering finished hub look into `L_Hub_Env_Visuals` |
| `Maps/RedPlanetGen` (+ 50km Test / FusedPrototype) | **Protected** | Read-only without explicit gate |
| Character / Weapons / GameMode packages | Gameplay | Artists do not edit |

---

## Marketplace masters

- Do **not** edit Fab/Marketplace master materials or meshes in place.  
- Create project-owned Material Instances under `/Game/RedMMO/World/...` or `/Game/RedMMO/Environment/...`.  
- Keep vendor pack folders intact for updates.

---

## Outliner hygiene

- Group env actors under folders: `Env/Landscape`, `Env/Foliage`, `Env/Lighting`, `Env/Dressing`.  
- Leave gameplay folders (`Gameplay/Spawns`, `Gameplay/Volumes`, `Gameplay/Interactables`) for the developer in HubLogic.  
- Add **Red Manual Placement Protection** on hand-authored POI roots when using the planetary workflow.
