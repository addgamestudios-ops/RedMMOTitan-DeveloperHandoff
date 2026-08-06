# START HERE — Red MMO environmental artist handoff

**Generated:** 2026-08-07  
**Ukrainian:** [START_HERE_UK.md](./START_HERE_UK.md)  
**PDF (EN):** [RedMMO_Environment_Artist_Handoff.pdf](./RedMMO_Environment_Artist_Handoff.pdf)  
**Merge with gameplay:** [MERGE_ENV_AND_GAMEPLAY.md](./MERGE_ENV_AND_GAMEPLAY.md) · [MERGE_ENV_AND_GAMEPLAY_UK.md](./MERGE_ENV_AND_GAMEPLAY_UK.md)  
**Fab / env packs:** [ENV_FAB_INVENTORY.md](./ENV_FAB_INVENTORY.md)  
**Folder ownership:** [FOLDER_OWNERSHIP.md](./FOLDER_OWNERSHIP.md)

Product name in docs: **Red MMO**. Paths like `Titan.uproject` / `RedMMOTitan*` are technical only.

Gameplay / netcode handoff (separate role): `Docs/DeveloperHandoff/` in the same public repo.

---

## 60-second path

1. Install **Unreal Engine 5.8**.
2. Open the **Titan** project on the machine that has full Content:  
   `D:\RedMMOTitan\Titan.uproject`  
   (PlanetGen marketplace plugin required for planetary maps.)
3. Open **one** of the two env / level-design test maps (see below). Do **not** open both and save blindly.
4. Read [MERGE_ENV_AND_GAMEPLAY.md](./MERGE_ENV_AND_GAMEPLAY.md) before combining hub graphics with a gameplay map.
5. Run **one Unreal Editor** at a time on this machine.

---

## The two maps to open

Both live in the **Titan** monolith (`D:\RedMMOTitan`), not the clean PPG-only RedMMO project.

| # | Soft path | Disk path | Role |
|---|---|---|---|
| **1** | `/Game/RedMMO/Maps/RedPlanetGen_50km_ArtistCanvas` | `Content/RedMMO/Maps/RedPlanetGen_50km_ArtistCanvas.umap` | Planetary environment canvas — continents, atmosphere preview, 50 km planet art |
| **2** | `/Game/RedMMO/Maps/Sandbox_DesertDemoSparkle_T01` | `Content/RedMMO/Maps/Sandbox_DesertDemoSparkle_T01.umap` | Desert / dressed sandbox for level design, props, lighting experiments |

**Related (not the primary pair):**

| Soft path | Project | Note |
|---|---|---|
| `/Game/RedMMO/Maps/Tests/RedPlanetGen_50km_FusedPrototype_M07_TropicalTile_R15_V3` | Titan | Continent / tropical tile lighting scratch (Region-15) |
| `/Game/RedMMO/Maps/RedMMO_PPG_HomeWorld` | Clean RedMMO only: `D:\RedMMOTitanWindowsData\Projects\RedMMO\` | PPG home world (seed 1337) — planetary presentation; needs PPG plugin |

---

## What you own

- Landscape / terrain dressing, foliage, rocks, props, lighting, sky/atmosphere look (within map ownership rules)
- Static meshes and materials under `/Game/RedMMO/World/...` (Quarantine → Approved → Biomes / ManualPOI)
- Hub **visuals**: architecture dressing, set dressing, fog/post volumes that do not change gameplay rules
- Screenshots from player height, jetpack height, and ship approach

---

## What you must NOT edit

| Do not touch | Why |
|---|---|
| Player pawn / Character Blueprints and C++ (`RedPlayerCharacter`, Action Trooper setup) | Locomotion and replication |
| **Running animation** assets or AnimBP “fixes” | Protected — do not overwrite |
| Weapon Blueprints, projectile C++, FocalRig aim chain | Gameplay combat |
| Replication / GameMode / GameState / PlayerController networking | Netcode developer owns |
| Protected production maps: `RedPlanetGen`, `RedPlanetGen_50km_Test`, `RedPlanetGen_50km_FusedPrototype` | Rollback / acceptance baselines |
| Marketplace **master** materials (edit project-owned MI children only) | Pack upgrades break otherwise |
| Clean RedMMO PPG seed / ProfileV1 generation data unless explicitly tasked | Planetary authority |

---

## Engine / plugins for env work

| Need | Requirement |
|---|---|
| UE version | **5.8** (`D:\UE_5.8` on owner machine) |
| ArtistCanvas / RedPlanetGen* | **PlanetGen** (Epic Marketplace for UE 5.8) |
| Sandbox desert map | Usually opens without PPG; may reference dressed Content packs |
| Clean PPG home world | Separate project + **PPG** plugin — only if assigned |

---

## First-day checklist

1. Open `Titan.uproject` → map **ArtistCanvas** OR **Sandbox_DesertDemoSparkle_T01**.
2. Confirm MapCheck is clean enough to work (note any existing warnings; do not “fix” gameplay actors).
3. Place art only under agreed World folders (see `FOLDER_OWNERSHIP.md`).
4. Prefer a **new env sublevel** for hub dressing rather than saving into the gameplay developer’s map package.
5. Export screenshots; list changed folders when you hand work back.

---

## Where this package lives

| Copy | Path |
|---|---|
| Repo docs | `Docs/EnvironmentArtistHandoff/` (this folder) |
| Public GitHub | https://github.com/addgamestudios-ops/RedMMOTitan-DeveloperHandoff → `Docs/EnvironmentArtistHandoff/` |
| Desktop email/PDF pack | `C:\Users\user\Desktop\RedMMO_EnvironmentArtist_Handoff\` |
