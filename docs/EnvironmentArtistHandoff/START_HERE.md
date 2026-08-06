# START HERE — **Red MMO** environment artist handoff

**Generated:** 2026-08-07  
**Ukrainian:** [START_HERE_UK.md](./START_HERE_UK.md)  
**PDF (EN):** [RedMMO_Environment_Artist_Handoff.pdf](./RedMMO_Environment_Artist_Handoff.pdf) · **PDF (UK):** [RedMMO_Environment_Artist_Handoff_UK.pdf](./RedMMO_Environment_Artist_Handoff_UK.pdf)

Product name in docs: **Red MMO**. Names like `Titan.uproject` / `RedMMOTitan*` are technical paths only.

Gameplay / netcode role (separate): [../DeveloperHandoff/START_HERE.md](../DeveloperHandoff/START_HERE.md)

---

## Core: same repo, merge-safe world (read this first)

You and the gameplay developer work in the **same GitHub repository**. Your hub environment will **not** overwrite HubLogic, and the developer will **not** overwrite your env package — **if you keep ownership split**:

| Layer | Package | Owner |
|---|---|---|
| Thin persistent | `/Game/RedMMO/Maps/Hubs/L_Hub_Persistent` | Lead / rare edits |
| **Environment (you)** | `/Game/RedMMO/Maps/Hubs/L_Hub_Env_Visuals` | **Environment artist** |
| HubLogic | `/Game/RedMMO/Maps/Hubs/L_Hub_Gameplay_Logic` | Gameplay developer |

- Put landscape, lighting, fog/post look, foliage, static meshes, and set dressing in **`L_Hub_Env_Visuals`**.
- Do **not** edit **`L_Hub_Gameplay_Logic`** (PlayerStarts, combat volumes, replicated actors).
- Do **not** edit pawn / Character BP, running animation, weapons, or netcode packages.
- Details: [MERGE_ENV_AND_GAMEPLAY.md](./MERGE_ENV_AND_GAMEPLAY.md) · developer mirror: [../DeveloperHandoff/MERGE_SAFE_WORLD.md](../DeveloperHandoff/MERGE_SAFE_WORLD.md).

**One-liner:** Clone the same handoff repo as the gameplay developer; own `L_Hub_Env_Visuals` (plus ArtistCanvas / Desert sandbox for tests); leave HubLogic and gameplay code alone.

---

## 60-second path

1. Clone: `https://github.com/addgamestudios-ops/RedMMOTitan-DeveloperHandoff.git`
2. Install **Unreal Engine 5.8**.
3. Open the project that has the env Content you were given:
   - Hub stubs / fundamentals: **`TitanFundamentals.uproject`** in the handoff clone  
   - Full planetary / dressed Titan Content (owner machine or content sync): **`Titan.uproject`**
4. Open **your** maps (see below). Do **not** open HubLogic and save into it.
5. Read [MERGE_ENV_AND_GAMEPLAY.md](./MERGE_ENV_AND_GAMEPLAY.md) before delivering hub art.
6. Run **one Unreal Editor** at a time on a shared machine.

```powershell
git clone https://github.com/addgamestudios-ops/RedMMOTitan-DeveloperHandoff.git
cd RedMMOTitan-DeveloperHandoff
# Hub env ownership: /Game/RedMMO/Maps/Hubs/L_Hub_Env_Visuals
start TitanFundamentals.uproject
```

| Check | Expected |
|---|---|
| Hub stubs present | `L_Hub_Persistent`, `L_Hub_Env_Visuals`, `L_Hub_Gameplay_Logic` |
| Your save target | **`L_Hub_Env_Visuals`** only for hub delivery |
| HubLogic | Present but **not** your edit target |
| Test maps (full Titan Content) | ArtistCanvas and/or Desert sandbox |
| **Running anim / pawn / weapons** | Do not touch |

---

## Maps you open

### Hub delivery (same-repo ownership)

| Soft path | You |
|---|---|
| `/Game/RedMMO/Maps/Hubs/L_Hub_Env_Visuals` | **Own and save here** |
| `/Game/RedMMO/Maps/Hubs/L_Hub_Persistent` | Integration only (streaming refs; rarely edit) |
| `/Game/RedMMO/Maps/Hubs/L_Hub_Gameplay_Logic` | **Do not edit** (developer / HubLogic) |

### Env / level-design test maps (full Titan Content)

| Soft path | Role |
|---|---|
| `/Game/RedMMO/Maps/RedPlanetGen_50km_ArtistCanvas` | Planetary environment canvas (PlanetGen) |
| `/Game/RedMMO/Maps/Sandbox_DesertDemoSparkle_T01` | Desert / dressed sandbox for LD, props, lighting |

Details: [MAPS.md](./MAPS.md) · Fab packs: [ENV_FAB_INVENTORY.md](./ENV_FAB_INVENTORY.md) · Folders: [FOLDER_OWNERSHIP.md](./FOLDER_OWNERSHIP.md)

---

## What you own

- Hub visuals in **`L_Hub_Env_Visuals`**: architecture dressing, set dressing, landscape look, lighting, fog/post that do not change gameplay rules
- Foliage, rocks, props; static meshes / materials under `/Game/RedMMO/World/...` (Quarantine → Approved → Biomes / ManualPOI)
- ArtistCanvas / Desert sandbox experiments when assigned
- Screenshots from player height, jetpack height, and ship approach

---

## What you must NOT edit

| Do not touch | Why |
|---|---|
| **`L_Hub_Gameplay_Logic`** | Developer HubLogic — PlayerStarts, volumes, networked actors |
| Player pawn / Character Blueprints and C++ | Locomotion and replication |
| **Running animation** assets or AnimBP “fixes” | Protected — do not overwrite |
| Weapon Blueprints, projectile C++, aim chain | Gameplay combat |
| Replication / GameMode / GameState / PlayerController networking | Netcode developer owns |
| Protected production maps: `RedPlanetGen`, `RedPlanetGen_50km_Test`, `RedPlanetGen_50km_FusedPrototype` | Rollback baselines |
| Marketplace **master** materials (edit project-owned MI children only) | Pack upgrades break otherwise |

---

## What to read next

| Doc | Why |
|---|---|
| [MERGE_ENV_AND_GAMEPLAY.md](./MERGE_ENV_AND_GAMEPLAY.md) | Same-repo merge without overwrite |
| [ENVIRONMENT_ARTIST_HANDOFF.md](./ENVIRONMENT_ARTIST_HANDOFF.md) | Paths, plugins, first-day checklist |
| [MAPS.md](./MAPS.md) | Map identity + protected list |
| [FOLDER_OWNERSHIP.md](./FOLDER_OWNERSHIP.md) | World folder conventions |
| [ENV_FAB_INVENTORY.md](./ENV_FAB_INVENTORY.md) | Fab / art packs you may need |

---

## Where this package lives

| Copy | Path |
|---|---|
| Repo docs | `docs/EnvironmentArtistHandoff/` (this folder) |
| Public GitHub | https://github.com/addgamestudios-ops/RedMMOTitan-DeveloperHandoff/tree/main/docs/EnvironmentArtistHandoff |
| Desktop PDF pack | `C:\Users\user\Desktop\RedMMO_EnvironmentArtist_Handoff\` |
