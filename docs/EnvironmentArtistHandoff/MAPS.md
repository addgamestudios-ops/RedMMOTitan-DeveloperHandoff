# Maps — environment artist ownership

**Status:** Aligned with merge-safe hub packages + on-disk env test maps (2026-08-07).

---

## Hub packages (same-repo ownership — use these for delivery)

| Soft path | Owner | Role |
|---|---|---|
| `/Game/RedMMO/Maps/Hubs/L_Hub_Env_Visuals` | **Environment artist** | Hub landscape, lighting, foliage, set dressing — **your save target** |
| `/Game/RedMMO/Maps/Hubs/L_Hub_Persistent` | Lead / rare | Thin shell — streaming refs only |
| `/Game/RedMMO/Maps/Hubs/L_Hub_Gameplay_Logic` | Gameplay developer | HubLogic — **do not edit** |

Disk (handoff / Titan Content): `Content/RedMMO/Maps/Hubs/`

---

## Env / level-design test maps (full Titan Content)

| Soft path | Project | Role |
|---|---|---|
| `/Game/RedMMO/Maps/RedPlanetGen_50km_ArtistCanvas` | Titan | Planetary environment canvas — continents, atmosphere preview |
| `/Game/RedMMO/Maps/Sandbox_DesertDemoSparkle_T01` | Titan | Desert / dressed sandbox for LD, props, lighting |

**Why these two for look-dev**

1. **ArtistCanvas** — planet-artist canvas for environmental / planetary authoring review (PlanetGen).  
2. **Sandbox_DesertDemoSparkle_T01** — desert sandbox for dressed/local env experiments without mutating protected production planets.

Prefer finishing hub delivery in **`L_Hub_Env_Visuals`**, not leaving long-term hub art only on a test map.

---

## Related maps (do not treat as primary ownership)

| Soft path | Note |
|---|---|
| `/Game/RedMMO/Maps/Tests/RedPlanetGen_50km_FusedPrototype_M07_TropicalTile_R15_V3` | Continent / tropical tile lighting scratch |
| `/Game/RedMMO/Maps/RedMMO_PPG_HomeWorld` | Clean RedMMO + PPG only — only if assigned |

---

## Protected — do not save over

- `/Game/RedMMO/Maps/Hubs/L_Hub_Gameplay_Logic` (developer ownership)
- `/Game/RedMMO/Maps/RedPlanetGen`
- `/Game/RedMMO/Maps/RedPlanetGen_50km_Test`
- `/Game/RedMMO/Maps/RedPlanetGen_50km_FusedPrototype`
