# Environmental / level-design test maps — identity

**Status:** Identified from on-disk `.umap` inventory + `ProjectKnowledge` artist handoff + developer PPG-free map table (2026-08-07).

---

## Primary pair (use these)

| Soft path | Project | Disk |
|---|---|---|
| `/Game/RedMMO/Maps/RedPlanetGen_50km_ArtistCanvas` | **Titan** `D:\RedMMOTitan\Titan.uproject` | `Content/RedMMO/Maps/RedPlanetGen_50km_ArtistCanvas.umap` |
| `/Game/RedMMO/Maps/Sandbox_DesertDemoSparkle_T01` | **Titan** same | `Content/RedMMO/Maps/Sandbox_DesertDemoSparkle_T01.umap` |

**Why these two**

1. **ArtistCanvas** — documented planet-artist canvas (`ProjectKnowledge` `artist_handoff`, SAFE8 archive, PlanetArtist README). Built for environmental/planetary authoring review.  
2. **Sandbox_DesertDemoSparkle_T01** — Titan desert sandbox called out for dressed/local env experiments (developer handoff map table). Suitable for level-design prop/lighting tests without mutating protected production planets.

---

## Related maps (do not treat as the primary pair)

| Soft path | Project | Note |
|---|---|---|
| `/Game/RedMMO/Maps/Tests/RedPlanetGen_50km_FusedPrototype_M07_TropicalTile_R15_V3` | Titan | Continent / tropical tile lighting scratch (Region-15 PlayerStart) |
| `/Game/RedMMO/Maps/RedPlanetGen_50km_Test` | Titan | Protected 50 km desert/ocean **baseline** — read-only |
| `/Game/RedMMO/Maps/RedPlanetGen` | Titan | Production default planet — protected |
| `/Game/RedMMO/Maps/RedMMO_PPG_HomeWorld` | Clean RedMMO only | PPG home (seed 1337); not in Titan Content |

---

## Protected — do not save over

- `/Game/RedMMO/Maps/RedPlanetGen`
- `/Game/RedMMO/Maps/RedPlanetGen_50km_Test`
- `/Game/RedMMO/Maps/RedPlanetGen_50km_FusedPrototype`
