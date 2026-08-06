# START HERE — **Red MMO** developer handoff

**Generated:** 2026-08-07  
**Ukrainian:** [START_HERE_UK.md](./START_HERE_UK.md)  
**PDF (EN):** [RedMMOTitan_Developer_Handoff.pdf](./RedMMOTitan_Developer_Handoff.pdf) · **PDF (UK):** [RedMMOTitan_Developer_Handoff_UK.pdf](./RedMMOTitan_Developer_Handoff_UK.pdf)

Product name in docs: **Red MMO**. Names like `TitanFundamentals.uproject` / `RedMMOTitan*` are technical paths only.

---

## Core: same repo, merge-safe world (read this first)

You and the environment artists work in the **same GitHub repository**. You will **not** lose your hub gameplay when the player-hub environment is built, and you will **not** have to reprogram everything after art lands — **if you keep ownership split**:

| Layer | Package | Owner |
|---|---|---|
| Thin persistent | `/Game/RedMMO/Maps/Hubs/L_Hub_Persistent` | Lead / rare edits |
| Environment | `/Game/RedMMO/Maps/Hubs/L_Hub_Env_Visuals` | Environment artists |
| **HubLogic (you)** | `/Game/RedMMO/Maps/Hubs/L_Hub_Gameplay_Logic` | **Gameplay developer** |

- Put PlayerStarts, volumes, spawn managers, replicated / networked actors in **`L_Hub_Gameplay_Logic`**.
- Do **not** edit the artist-owned env `.umap`.
- Keep C++ / gameplay Blueprints in your packages — they are independent of env map saves.
- Details: [MERGE_SAFE_WORLD.md](./MERGE_SAFE_WORLD.md) · artist merge doc: [../EnvironmentArtistHandoff/MERGE_ENV_AND_GAMEPLAY.md](../EnvironmentArtistHandoff/MERGE_ENV_AND_GAMEPLAY.md).

**One-liner:** Clone this handoff repo, work in the HubLogic / gameplay layer; artists will not overwrite your code or gameplay map.

---

## 60-second path

1. Clone: `https://github.com/addgamestudios-ops/RedMMOTitan-DeveloperHandoff.git`
2. Install **Unreal Engine 5.8**.
3. Open **`TitanFundamentals.uproject`** (PlanetGen / PPG not required).
4. Build **TitanEditor** Win64 Development.
5. Day-1 PIE: `/Game/ThirdPerson/Maps/ThirdPersonMap` (controls / listen-server).  
   Hub work that must survive env delivery: **`L_Hub_Gameplay_Logic`** under `/Game/RedMMO/Maps/Hubs/`.
6. Netcode track: [NETWORKING_PVP.md](./NETWORKING_PVP.md). Full pack: [DEVELOPER_HANDOFF.md](./DEVELOPER_HANDOFF.md).

```powershell
git clone https://github.com/addgamestudios-ops/RedMMOTitan-DeveloperHandoff.git
cd RedMMOTitan-DeveloperHandoff
start TitanFundamentals.uproject
```

| Check | Expected |
|---|---|
| Editor opens without planet plugins | No hard fail for missing PPG / PlanetGen |
| PIE on ThirdPersonMap | Character moves; listen-server 2P for replication tests |
| Hub stubs present | `L_Hub_Persistent`, `L_Hub_Env_Visuals`, `L_Hub_Gameplay_Logic` |
| Env sublevel | You do not save artist ownership into that package |
| **Running anim** | Do not overwrite trooper locomotion without authority |

---

## What to read next

| Doc | Why |
|---|---|
| [MERGE_SAFE_WORLD.md](./MERGE_SAFE_WORLD.md) | Same-repo ownership + no-overwrite merge path |
| [NETWORKING_PVP.md](./NETWORKING_PVP.md) | Listen-server, replication, PvP order of work |
| [DEVELOPER_HANDOFF.md](./DEVELOPER_HANDOFF.md) | Paths, protected items, plugin disposition |
| [PPG_PLANETGEN_FREE_START.md](./PPG_PLANETGEN_FREE_START.md) | Fundamentals without planet plugins |
| [FAB_MARKETPLACE_INVENTORY.md](./FAB_MARKETPLACE_INVENTORY.md) | Optional marketplace plugins later |

**Environment artist role (separate):** [../EnvironmentArtistHandoff/START_HERE.md](../EnvironmentArtistHandoff/START_HERE.md)

---

## Protected (short list)

- Running / locomotion on `ABP_RedTrooperFemale`
- Artist-owned env map packages (do not treat as your hub file)
- Do not enable Steam Integration Kit and Epic OnlineSubsystemSteam together
