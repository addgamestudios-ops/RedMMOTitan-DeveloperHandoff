# Same-repo, merge-safe world ownership

**This is the core collaboration rule for Red MMO.**  
Gameplay and environment work in the **same GitHub repo**, on **separate Unreal map packages**, so hub art can land without forcing a gameplay rewrite and without binary `.umap` overwrite fights.

Full artist-side detail: [../EnvironmentArtistHandoff/MERGE_ENV_AND_GAMEPLAY.md](../EnvironmentArtistHandoff/MERGE_ENV_AND_GAMEPLAY.md).

---

## What you are guaranteed

| Need | How it is met |
|---|---|
| A world/map setup that is **not lost** when the player hub environment is built | Your gameplay actors live in **`L_Hub_Gameplay_Logic`** (HubLogic). Env dress lives in **`L_Hub_Env_Visuals`**. |
| You **do not reprogram everything** after env artists finish the hub | C++ / Blueprint assets (Character, GameMode, weapons, AnimBP) are separate packages from env `.umap` files. Art swaps the env sublevel; your logic stays. |
| **Same-repo** collaboration that does **not overwrite** the other discipline | Artists never check in the gameplay sublevel; you never edit the env sublevel. Thin persistent level only references both. |

---

## Map layout (fundamentals starter)

```text
/Game/RedMMO/Maps/Hubs/L_Hub_Persistent          ← thin shell (streaming refs only; rarely edited)
/Game/RedMMO/Maps/Hubs/L_Hub_Env_Visuals         ← environment artists
/Game/RedMMO/Maps/Hubs/L_Hub_Gameplay_Logic      ← you (HubLogic): PlayerStarts, volumes, replicated actors
```

| Owner | Owns | Do not touch |
|---|---|---|
| **Gameplay developer** | `L_Hub_Gameplay_Logic`, `Source/`, gameplay Blueprints, netcode | Artist-owned env `.umap` |
| **Environment artist** | `L_Hub_Env_Visuals`, landscape/lighting/foliage/dressing | Gameplay sublevel, Character/GameMode packages |
| **Lead / either with agreement** | `L_Hub_Persistent` membership (which sublevels load) | Daily art or combat authoring inside Persistent |

Day-1 compile / listen-server PIE can still use `/Game/ThirdPerson/Maps/ThirdPersonMap`. Put **hub** gameplay that must survive env delivery into **`L_Hub_Gameplay_Logic`**.

---

## Working rules

1. Clone the handoff repo; open **`TitanFundamentals.uproject`**.
2. Put hub PlayerStarts, combat volumes, spawn managers, networked actors in **`L_Hub_Gameplay_Logic`**.
3. Do **not** dress the long-term hub look inside the gameplay sublevel or inside a single shared `HubWorld.umap`.
4. Do **not** edit `L_Hub_Env_Visuals` (or ArtistCanvas / sandbox env delivery maps) as your ownership file.
5. When env art is ready, Persistent loads both sublevels — you fix only cross-level references (streaming, soft paths), not a full rewrite.

**Binary truth:** two people saving the same `.umap` cannot be safely git-merged. Split packages first.

---

## One sentence for the developer

Clone the handoff repo, work in the HubLogic / gameplay layer (`L_Hub_Gameplay_Logic` + C++/BP); artists own the env sublevel and will not overwrite your code or gameplay map.
