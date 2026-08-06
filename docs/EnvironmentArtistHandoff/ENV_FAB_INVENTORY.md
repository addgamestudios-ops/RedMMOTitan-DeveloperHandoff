# Fab / Marketplace inventory — environment focus

Subset of `docs/DeveloperHandoff/FAB_MARKETPLACE_INVENTORY.md` for environmental / level-design work.  
Presence checked on owner machine 2026-08-07.

Legend: **Titan** = `D:\RedMMOTitan\Content` · **Clean** = `D:\RedMMOTitanWindowsData\Projects\RedMMO\Content`

Hub delivery in the shared handoff repo (`L_Hub_Env_Visuals`) does **not** require PlanetGen/PPG. Those plugins matter for planetary test maps and full Titan Content.

---

## Plugins required for env maps

| Name | Needed for | Notes |
|---|---|---|
| *(none)* | Hub stubs `L_Hub_*` in TitanFundamentals | Dress hub visuals without planet plugins |
| **PlanetGen** (UE 5.8 Marketplace) | ArtistCanvas, RedPlanetGen* | Install via Epic Launcher into UE 5.8 |
| **PPG** | Only clean `RedMMO_PPG_HomeWorld` | Not required for Titan ArtistCanvas / desert sandbox |
| Nwiro / UAIP | Optional editor tooling | Not required for art delivery |

---

## Environment content packs

| Pack | On Titan | On Clean RedMMO | Typical use |
|---|---|---|---|
| **SoStylized** | Yes | Yes | Landscape layers, stylized foliage/rocks language |
| **Stylized Desert Oasis** | Yes | Yes | Desert oasis water MI, palms, desert dressing |
| **StylizedRocksPack_01** | — | Yes | Grass chunks / rock meshes used in PPG stylized binding |
| **TropicalAlienWorld** | Yes | — | Cliffs, rock formations, alien tropical silhouettes |
| **AlienJungle** | Yes | Yes | Obsidian pillars/rocks, jungle alien props |
| **Alien_Grass_Pack** | Yes | Yes | Ground cover candidates (review before approve) |
| **Alien_Plants_Pack** | Yes | Yes | Plant props (quarantine → approve) |
| **SpaceColony** | Yes | — | Sci-fi architecture dressing |
| **AsteroidSpaceport** | Yes | — | Port / hard-surface set dressing |
| **Cloudz_Hi5** | Yes | — | Cloud volumes (atmosphere dressing; respect scale rules) |
| **Vefects** | Yes | — | VFX support (use sparingly in env maps) |

Full gameplay/plugin checklist (FocalRig, Steam, etc.) stays in the developer Fab inventory — env artists usually ignore those.

---

## Review before placing on a live map

Score packs (mood-board fit, variation, pivots/LOD/Nanite, editability, cost) per `docs/WORLD_AUTHORING_WORKFLOW.md`.  
Import → `World/Quarantine` → approve → palette entry → place only approved meshes into ManualPOI / biome folders.

---

## Size / transfer note

Full `Content/` is tens of GB and is **not** entirely in git. Artists need a drive sync or shared Content drop for the packs above. The public handoff repo carries docs + fundamentals crumbs, not every marketplace pack.
