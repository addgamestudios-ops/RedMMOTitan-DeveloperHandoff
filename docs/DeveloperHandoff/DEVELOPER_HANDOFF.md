# Red MMO — Developer Handoff (2026-08-07)

**Status:** Good enough to pick up. Many problems remain. Fundamentals do not require planet plugins.  
**Ukrainian:** [DEVELOPER_HANDOFF_UK.md](./DEVELOPER_HANDOFF_UK.md) · **START:** [START_HERE.md](./START_HERE.md)

**Audience:** gameplay / netcode programmer. World ownership first: [MERGE_SAFE_WORLD.md](./MERGE_SAFE_WORLD.md). Netcode order: [NETWORKING_PVP.md](./NETWORKING_PVP.md).

| Artifact | Location |
|---|---|
| START_HERE | [START_HERE.md](./START_HERE.md) · [START_HERE_UK.md](./START_HERE_UK.md) |
| Merge-safe world | [MERGE_SAFE_WORLD.md](./MERGE_SAFE_WORLD.md) · [MERGE_SAFE_WORLD_UK.md](./MERGE_SAFE_WORLD_UK.md) |
| PDF EN / UK | [RedMMOTitan_Developer_Handoff.pdf](./RedMMOTitan_Developer_Handoff.pdf) · [RedMMOTitan_Developer_Handoff_UK.pdf](./RedMMOTitan_Developer_Handoff_UK.pdf) |
| Networking / PvP | [NETWORKING_PVP.md](./NETWORKING_PVP.md) · [NETWORKING_PVP_UK.md](./NETWORKING_PVP_UK.md) |
| PPG-free start | [PPG_PLANETGEN_FREE_START.md](./PPG_PLANETGEN_FREE_START.md) |
| Fab inventory | [FAB_MARKETPLACE_INVENTORY.md](./FAB_MARKETPLACE_INVENTORY.md) |
| Clone | https://github.com/addgamestudios-ops/RedMMOTitan-DeveloperHandoff.git |

---

## 1. Same-repo collaboration (non-negotiable)

Gameplay and environment share one repository. Separable ownership keeps hub art from forcing a gameplay rewrite:

```text
L_Hub_Persistent          ← thin shell (streaming only)
├── L_Hub_Env_Visuals     ← artists (do not edit)
└── L_Hub_Gameplay_Logic  ← you / HubLogic
```

| You own | Artists own |
|---|---|
| `L_Hub_Gameplay_Logic`, `Source/RedMMO`, gameplay BP, netcode | `L_Hub_Env_Visuals`, landscape, lighting, foliage, set dressing |

**Guarantees:** hub gameplay map package is not the env delivery file; C++/BP are not rewritten when env `.umap` changes; git will not “merge” two writers on one binary `.umap` — so do not share one.

Aligned with [../EnvironmentArtistHandoff/MERGE_ENV_AND_GAMEPLAY.md](../EnvironmentArtistHandoff/MERGE_ENV_AND_GAMEPLAY.md).

---

## 2. Paths

| Role | Path |
|---|---|
| Standalone handoff (clone this) | `https://github.com/addgamestudios-ops/RedMMOTitan-DeveloperHandoff.git` → `TitanFundamentals.uproject` |
| Hub map stubs | `/Game/RedMMO/Maps/Hubs/` (`L_Hub_Persistent`, `L_Hub_Env_Visuals`, `L_Hub_Gameplay_Logic`) |
| Day-1 PIE (no hub art required) | `/Game/ThirdPerson/Maps/ThirdPersonMap` |
| Engine | Unreal Engine **5.8** |

Optional later (owner / full content): full `Titan.uproject` planetary maps, clean D-drive `RedMMO.uproject` + PPG home world, packaged R92 baseline — not required for HubLogic / netcode start.

---

## 3. What works / what is open (honest)

**Working enough to start:**

- `TitanEditor` Win64 Development with FocalRig/WorldGen disabled and PlanetGen APIs shimmed (`RedPlanetGenCompat`)
- Fundamentals PIE without PPG / PlanetGen
- Listen-server aim / fire / jetpack replication (gameplay path; not a finished Steam two-account proof)
- Live RedMMO editor fixes historically: wheel→thrust, atmosphere exit, weapons/plumes/jetpack, terrain blend (re-verify on your build)

**Still open:**

- Physical feel polish; HUD fuel pixels; biome art; fused consumer; M04/M05; Steam two-account PvP; dedicated server
- Composed hub Persistent with real env + gameplay streaming (stubs exist; dress and wire on integration days)

---

## 4. Build / PIE

```powershell
git clone https://github.com/addgamestudios-ops/RedMMOTitan-DeveloperHandoff.git
cd RedMMOTitan-DeveloperHandoff
start TitanFundamentals.uproject
# Target: TitanEditor | Win64 | Development
```

1. Confirm compile with PlanetGen / PPG / FocalRig / WorldGen off.  
2. PIE ThirdPersonMap for controls and 2-player listen-server.  
3. Author hub gameplay in **`L_Hub_Gameplay_Logic`**; leave **`L_Hub_Env_Visuals`** to artists.  
4. Wire both under **`L_Hub_Persistent`** when integrating.

One UnrealEditor at a time on a shared machine.

---

## 5. Plugin disposition (fundamentals)

| Plugin | Fundamentals |
|---|---|
| FocalRig | Disabled (+ ControlRig substitute in source) |
| WorldGen | Disabled |
| PlanetGen | Disabled (`RedPlanetGenCompat` shims link) |
| PPG | Not in TitanFundamentals; optional later on clean RedMMO |

See [PPG_PLANETGEN_FREE_START.md](./PPG_PLANETGEN_FREE_START.md).

---

## 6. Protected items

1. **Running animation / locomotion** on `ABP_RedTrooperFemale` — do not replace without explicit authority.  
2. **Env-owned map packages** — not your save target for hub logic.  
3. Fused 27/6 authoring hashes and production planetary maps — read-only without a dedicated gate.  
4. Do not enable SIK and Epic OnlineSubsystemSteam together.

---

## 7. Next work order

1. Fundamentals compile + PIE (ThirdPersonMap).  
2. Listen-server replication → PvP damage loop ([NETWORKING_PVP.md](./NETWORKING_PVP.md)).  
3. HubLogic actors in `L_Hub_Gameplay_Logic` so env can land without rewrite.  
4. Steam SIK two-account only after gameplay replication is stable.  
5. Planetary / PPG maps only when those plugins are intentionally in scope.

---

## 8. Clone contents (expectations)

**Expect:** `Source/`, `Config/`, `docs/` (Developer + Environment handoffs), `TitanFundamentals.uproject`, ThirdPerson starter map, Hub stubs under `Content/RedMMO/Maps/Hubs/`, selected RedMMO crumbs.

**Do not expect:** full Fab packs, Binaries/Intermediate/DDC, large SteamIntegrationKit tree unless copied separately, owner machine diagnostics / packaged R92 trees.
