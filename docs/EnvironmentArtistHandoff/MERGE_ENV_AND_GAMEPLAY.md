# Merging hub / graphics work with the gameplay map

**Question:** Can an environmental artist build a hub / graphics map while a gameplay developer codes on another map, then merge them **without starting over** and **without overwriting** each other?

**Answer: YES — if they never both save the same `.umap` package as the shared ownership file.**  
Gameplay code in C++ and Blueprint *assets* (Character, GameMode, weapons, AnimBP) can stay completely independent of the environment `.umap`. Visual hub work should live in env-owned level packages that the persistent level only **references**.

---

## Recommended Unreal pattern (best)

Use **composition**, not “one person owns the whole world file.”

```text
PersistentLevel (thin shell — rarely edited)
├── Sublevel / WP layer: Env_Landscape_Lighting_Foliage   ← artists
├── Sublevel / WP layer: Env_HubDressing_Meshes           ← artists
└── Sublevel / WP layer: Gameplay_HubLogic                ← gameplay
        (PlayerStarts, volumes, BP gameplay actors,
         triggers, spawn managers, networked actors)
```

| Owner | Owns |
|---|---|
| Environment artist | Landscape, lighting, fog/post look, foliage, static meshes, set dressing, visual-only volumes |
| Gameplay developer | GameMode/GameState refs, PlayerStart authority, combat volumes, replicated actors, interactables logic, spawn rules |
| Tech / lead | Persistent level membership (which sublevels are always loaded), streaming / World Partition rules |

**World Partition / Data Layers / Level Streaming** are all valid implementations of the same idea: **separate packages + clear ownership**. Prefer World Partition + Data Layers when the hub sits on a large planetary map; prefer classic streaming sublevels for a compact hub sandbox.

---

## What breaks if both edit the same `.umap`

| Reality | Consequence |
|---|---|
| `.umap` is a **binary** Unreal package | Git / Git LFS cannot merge conflicting saves; one writer wins or the file is corrupted / needs full replace |
| Perforce (better for UE binaries) still needs **exclusive checkout** | Two people locking/saving the same map = lost work or forced overwrite |
| Actor GUID / external-actor references | Copy-paste between maps without a plan duplicates or orphans gameplay actors |
| Autosave + “Save All” | Easy to dirty the wrong map when both are open |

**Rule:** Never have artist and gameplay developer simultaneously authoring and saving `HubWorld.umap` (or any single shared map). Split first, then compose.

---

## Safe merge options (ranked)

### (A) Sublevel / World Partition composition — **best**

1. Create `L_Env_HubVisuals` (or WP Data Layer `Env`) from the artist’s dressed map / canvas work.  
2. Create `L_Gameplay_HubLogic` from the developer’s gameplay map (or keep logic actors only).  
3. Persistent level loads both; PIE tests the composition.  
4. Artists never check in the gameplay sublevel; developers never check in the env sublevel.

**Result:** Parallel work, no binary map conflict, no restart.

### (B) Migrate / copy actors with ownership rules — **good if already diverged**

1. Freeze one side as “source of truth” for structure (usually gameplay PlayerStarts + volumes).  
2. Migrate **env-only** actors (StaticMesh, lights, foliage, decals) into the env sublevel via Level → Move into Level / Migrate Asset.  
3. Do **not** migrate Character, GameMode overrides, weapon pickups that own replication, or AnimBP assets via map copy.  
4. Verify collision and PlayerStart once in the composed persistent level.

**Result:** Recoverable if both already edited different maps; more manual than (A).

### (C) One File Per Actor (OFPA) / World Partition external actors — **good on WP maps**

When World Partition + OFPA is enabled, many actors become individual files under the map’s external actors folder. That reduces whole-map binary conflicts **for actors that were externalized**, but:

- Persistent map settings, landscape streaming proxies, and non-OFPA actors can still conflict.  
- Still require folder ownership and communication.  
- Not a substitute for keeping gameplay BP/C++ out of artist packages.

---

## Explicit guarantees

| Statement | True? |
|---|---|
| Merge hub graphics + gameplay map without starting the planet/hub from zero | **Yes**, via (A) or (B) |
| Keep gameplay C++ / BP assets while env `.umap` changes | **Yes** — code assets are separate packages |
| Both people save the same `.umap` and “git merge” later | **No** — binary conflict; expect overwrite or restore |
| Artist must re-implement PlayerStart / weapons / netcode after merge | **No**, if those stayed in gameplay-owned assets/sublevel |

---

## Practical workflow for Red MMO

1. **Gameplay developer** works on fundamentals / hub logic (e.g. ThirdPerson / gameplay sublevel / listen-server). Does not dress the ArtistCanvas as the long-term hub visual file.  
2. **Environment artist** works on:
   - `/Game/RedMMO/Maps/RedPlanetGen_50km_ArtistCanvas` for planetary look, **or**
   - `/Game/RedMMO/Maps/Sandbox_DesertDemoSparkle_T01` for desert/LD experiments, **or**
   - a **new** `L_Env_*` sublevel duplicated from either — preferred for hub delivery.  
3. Lead (or either role with agreement) creates a thin persistent hub that **streams both**.  
4. Integration day: load composition, MapCheck, PIE, fix only cross-level references (streaming volumes, soft paths).  
5. Protected maps (`RedPlanetGen`, `RedPlanetGen_50km_Test`, `RedPlanetGen_50km_FusedPrototype`) stay **read-only** unless a dedicated mutation gate says otherwise.

---

## Checklist before “we’re merging”

- [ ] Env work is in env-owned map/sublevel package(s) only  
- [ ] Gameplay actors / PlayerStarts / volumes are in gameplay-owned package(s) only  
- [ ] Persistent level only adds streaming/WP references (minimal dirtying)  
- [ ] No simultaneous save of the same `.umap`  
- [ ] Running anim, weapons, pawn, replication untouched by art pass  
- [ ] Screenshots of composed PIE from ground + approach  

---

## Short answer for stakeholders

**Yes, you can merge.** Use separate env and gameplay levels under one persistent shell. Do not both edit one binary map. Gameplay code does not need to be rebuilt from scratch when the hub art lands.
