# Red MMO — Environment Artist Handoff (2026-08-07)

**Status:** Enough to pick up hub visuals and env test maps. Full marketplace Content may need a drive sync.  
**Ukrainian:** [ENVIRONMENT_ARTIST_HANDOFF_UK.md](./ENVIRONMENT_ARTIST_HANDOFF_UK.md) · **START:** [START_HERE.md](./START_HERE.md)

**Audience:** 3D environmental / level-design artist. World ownership first: [MERGE_ENV_AND_GAMEPLAY.md](./MERGE_ENV_AND_GAMEPLAY.md).

| Artifact | Location |
|---|---|
| START_HERE | [START_HERE.md](./START_HERE.md) · [START_HERE_UK.md](./START_HERE_UK.md) |
| Merge-safe world (env view) | [MERGE_ENV_AND_GAMEPLAY.md](./MERGE_ENV_AND_GAMEPLAY.md) · [MERGE_ENV_AND_GAMEPLAY_UK.md](./MERGE_ENV_AND_GAMEPLAY_UK.md) |
| PDF EN / UK | [RedMMO_Environment_Artist_Handoff.pdf](./RedMMO_Environment_Artist_Handoff.pdf) · [RedMMO_Environment_Artist_Handoff_UK.pdf](./RedMMO_Environment_Artist_Handoff_UK.pdf) |
| Maps | [MAPS.md](./MAPS.md) |
| Folders | [FOLDER_OWNERSHIP.md](./FOLDER_OWNERSHIP.md) |
| Fab / art packs | [ENV_FAB_INVENTORY.md](./ENV_FAB_INVENTORY.md) |
| Clone (same as gameplay) | https://github.com/addgamestudios-ops/RedMMOTitan-DeveloperHandoff.git |

---

## 1. Same-repo collaboration (non-negotiable)

Gameplay and environment share one repository. Separable ownership keeps hub art from fighting HubLogic:

```text
L_Hub_Persistent          ← thin shell (streaming only)
├── L_Hub_Env_Visuals     ← you
└── L_Hub_Gameplay_Logic  ← developer / HubLogic (do not edit)
```

| You own | Developer owns |
|---|---|
| `L_Hub_Env_Visuals`, landscape, lighting, foliage, set dressing | `L_Hub_Gameplay_Logic`, `Source/RedMMO`, gameplay BP, netcode |

**Guarantees:** your env delivery file is not the HubLogic package; C++/BP are not rewritten when you save env `.umap`; git will not “merge” two writers on one binary `.umap` — so do not share one.

Aligned with [../DeveloperHandoff/MERGE_SAFE_WORLD.md](../DeveloperHandoff/MERGE_SAFE_WORLD.md).

---

## 2. Paths

| Role | Path |
|---|---|
| Standalone handoff (clone this) | `https://github.com/addgamestudios-ops/RedMMOTitan-DeveloperHandoff.git` → `TitanFundamentals.uproject` |
| Hub map stubs | `/Game/RedMMO/Maps/Hubs/` (`L_Hub_Persistent`, `L_Hub_Env_Visuals`, `L_Hub_Gameplay_Logic`) |
| Your hub save target | `/Game/RedMMO/Maps/Hubs/L_Hub_Env_Visuals` |
| Env test maps (full Titan Content) | ArtistCanvas · Sandbox_DesertDemoSparkle_T01 |
| Engine | Unreal Engine **5.8** |

Optional later (owner / full content): full `Titan.uproject` planetary maps + Fab packs, clean D-drive `RedMMO.uproject` + PPG home world — only if assigned.

---

## 3. What works / what is open (honest)

**Working enough to start:**

- Named hub stubs: Persistent / Env / HubLogic in the shared handoff repo
- Parallel ownership with gameplay (no shared `.umap` save target)
- On full Titan Content: ArtistCanvas and Desert sandbox for env experiments
- World folder conventions: Quarantine → Approved → Biomes / ManualPOI

**Still open / needs content sync:**

- Full Fab pack trees (tens of GB) are not entirely in git
- Composed hub Persistent with finished env + gameplay streaming (stubs exist; dress Env, developer wires HubLogic)
- Planetary look on ArtistCanvas needs **PlanetGen** on UE 5.8

---

## 4. First-day checklist

```powershell
git clone https://github.com/addgamestudios-ops/RedMMOTitan-DeveloperHandoff.git
cd RedMMOTitan-DeveloperHandoff
start TitanFundamentals.uproject
```

1. Confirm hub stubs under `/Game/RedMMO/Maps/Hubs/`.  
2. Open **`L_Hub_Env_Visuals`** — this is your hub ownership file.  
3. Do **not** save into `L_Hub_Gameplay_Logic`.  
4. If you have full Titan Content: open ArtistCanvas **or** Desert sandbox (not both blindly).  
5. Place art under agreed World folders ([FOLDER_OWNERSHIP.md](./FOLDER_OWNERSHIP.md)).  
6. Export screenshots; list changed folders when you hand work back.

One UnrealEditor at a time on a shared machine.

---

## 5. Plugins for env work

| Need | Requirement |
|---|---|
| UE version | **5.8** |
| Hub stubs in fundamentals | No PlanetGen / PPG required |
| ArtistCanvas / RedPlanetGen* | **PlanetGen** (Epic Marketplace for UE 5.8) |
| Sandbox desert map | Usually opens without PPG; may reference dressed Content packs |
| Clean PPG home world | Separate project + **PPG** — only if assigned |

See [ENV_FAB_INVENTORY.md](./ENV_FAB_INVENTORY.md).

---

## 6. Protected items

1. **`L_Hub_Gameplay_Logic`** — not your save target.  
2. **Running animation / locomotion** — do not replace.  
3. Player pawn, weapons, projectile / aim chain, replication / GameMode networking.  
4. Protected production maps: `RedPlanetGen`, `RedPlanetGen_50km_Test`, `RedPlanetGen_50km_FusedPrototype`.  
5. Marketplace master materials — use project-owned Material Instances only.

---

## 7. Next work order

1. Clone same repo; open hub **`L_Hub_Env_Visuals`**.  
2. Block out hub dress (architecture, lighting, foliage) without gameplay actors.  
3. Use ArtistCanvas / Desert sandbox for look-dev when Content is available.  
4. Hand back env package + screenshots; integration day loads Persistent with HubLogic.  
5. Do not “fix” gameplay actors or rewrite AnimBP during art pass.

---

## 8. Clone contents (expectations)

**Expect:** `docs/` EnvironmentArtistHandoff + DeveloperHandoff (MD + PDF), `TitanFundamentals.uproject`, Hub stubs under `Content/RedMMO/Maps/Hubs/`, selected RedMMO crumbs.

**Do not expect:** full Fab packs, Binaries/Intermediate/DDC, owner machine diagnostics, or gameplay netcode deep-dives (those stay in the developer pack).
