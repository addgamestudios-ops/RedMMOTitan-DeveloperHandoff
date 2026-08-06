# Same-repo merge: environment + HubLogic (artist view)

**This is the core collaboration rule for Red MMO — environment side.**  
Gameplay and environment work in the **same GitHub repo**, on **separate Unreal map packages**, so hub art can land without forcing a gameplay rewrite and without binary `.umap` overwrite fights.

Developer mirror: [../DeveloperHandoff/MERGE_SAFE_WORLD.md](../DeveloperHandoff/MERGE_SAFE_WORLD.md).

---

## What you are guaranteed

| Need | How it is met |
|---|---|
| Hub visuals that **survive** alongside HubLogic | Your dress lives in **`L_Hub_Env_Visuals`**. Developer actors live in **`L_Hub_Gameplay_Logic`**. |
| Developer does **not** overwrite your env delivery | Developers never check in your env sublevel; you never edit HubLogic. |
| You do **not** rebuild pawn / weapons / netcode when maps compose | Those are separate packages from env `.umap` files. Persistent only streams both. |

---

## Map layout (named packages)

```text
/Game/RedMMO/Maps/Hubs/L_Hub_Persistent          ← thin shell (streaming refs only; rarely edited)
/Game/RedMMO/Maps/Hubs/L_Hub_Env_Visuals         ← you (environment)
/Game/RedMMO/Maps/Hubs/L_Hub_Gameplay_Logic      ← gameplay developer (HubLogic)
```

| Owner | Owns | Do not touch |
|---|---|---|
| **Environment artist** | `L_Hub_Env_Visuals`, landscape/lighting/foliage/dressing, ArtistCanvas / Desert sandbox as assigned | `L_Hub_Gameplay_Logic`, Character/GameMode/weapons/netcode |
| **Gameplay developer** | `L_Hub_Gameplay_Logic`, `Source/`, gameplay Blueprints, netcode | Artist-owned env `.umap` |
| **Lead / either with agreement** | `L_Hub_Persistent` membership (which sublevels load) | Daily art or combat authoring inside Persistent |

```text
L_Hub_Persistent          ← thin shell (streaming only)
├── L_Hub_Env_Visuals     ← you
└── L_Hub_Gameplay_Logic  ← developer / HubLogic (do not edit)
```

---

## Working rules

1. Clone the **same** handoff repo as the gameplay developer:  
   `https://github.com/addgamestudios-ops/RedMMOTitan-DeveloperHandoff.git`
2. Author hub visuals in **`L_Hub_Env_Visuals`**.
3. Use **ArtistCanvas** or **Sandbox_DesertDemoSparkle_T01** for planetary / desert experiments — prefer delivering finished hub look into `L_Hub_Env_Visuals`, not into HubLogic.
4. Do **not** put PlayerStarts, combat volumes, spawn managers, or networked actors in your env package.
5. Do **not** both save the same `.umap` as the developer. Binary packages do not git-merge.

**Binary truth:** two people saving the same `.umap` cannot be safely git-merged. Split packages first.

---

## Safe merge options (ranked)

### (A) Sublevel composition with named hub packages — **best**

1. You deliver dress in `L_Hub_Env_Visuals`.  
2. Developer keeps HubLogic in `L_Hub_Gameplay_Logic`.  
3. Persistent loads both; PIE tests the composition.  
4. You never check in the gameplay sublevel; developers never check in the env sublevel.

**Result:** Parallel work, no binary map conflict, no restart.

### (B) Migrate env-only actors — **good if already diverged**

1. Freeze HubLogic as source of truth for PlayerStarts / volumes.  
2. Migrate **env-only** actors (StaticMesh, lights, foliage, decals) into `L_Hub_Env_Visuals`.  
3. Do **not** migrate Character, GameMode, weapon pickups that own replication, or AnimBP via map copy.  
4. Verify look once in composed Persistent.

### (C) OFPA / World Partition external actors — **good on WP maps**

Reduces whole-map conflicts for externalized actors, but still requires folder ownership. Not a substitute for keeping gameplay out of artist packages.

---

## Explicit guarantees

| Statement | True? |
|---|---|
| Merge hub graphics + HubLogic without starting the hub from zero | **Yes**, via (A) or (B) |
| Keep gameplay C++ / BP while env `.umap` changes | **Yes** |
| Both people save the same `.umap` and “git merge” later | **No** |
| Artist must re-implement PlayerStart / weapons / netcode after merge | **No**, if those stayed in HubLogic |

---

## Checklist before “we’re merging”

- [ ] Env work is in **`L_Hub_Env_Visuals`** (or agreed env-owned package) only  
- [ ] Gameplay actors / PlayerStarts / volumes are in **`L_Hub_Gameplay_Logic`** only  
- [ ] Persistent only adds streaming/WP references (minimal dirtying)  
- [ ] No simultaneous save of the same `.umap`  
- [ ] Running anim, weapons, pawn, replication untouched by art pass  
- [ ] Screenshots of composed PIE from ground + approach  

---

## One sentence for the environment artist

Clone the same handoff repo, own `L_Hub_Env_Visuals` (plus ArtistCanvas / Desert sandbox as needed); the gameplay developer owns HubLogic and will not overwrite your env package if you both keep that split.
