# RedMMO / Titan — Engineering Handover (Mac → Windows)

**Snapshot date:** 2026-07-11  
**Purpose:** Final Mac development save before continuing on a **Windows** machine. Stop iterating gameplay on Mac unless a trivial doc fix. Read this + [`HANDOVER_SHIP_PLUMES_TERRAIN.md`](HANDOVER_SHIP_PLUMES_TERRAIN.md) + [`docs/WINDOWS_STEAM.md`](docs/WINDOWS_STEAM.md) before changing ship, jetpack, sand, oasis, or atmosphere.

**Codex / agent entry:** Start at [`README.md`](README.md) → full agent brief [`CODEX_HANDOVER.md`](CODEX_HANDOVER.md).  
**GitHub:** https://github.com/addgamestudios-ops/RedMMOTitan · `git clone https://github.com/addgamestudios-ops/RedMMOTitan.git`

**Tone for next AI:** Be honest. Do not claim PIE success without a `HighResShot` (or clear user confirmation). Prior agents overclaimed oasis spawn and sand — treat those as **failed / unverified**.

---

## 1. Project identity

| Item | Value |
|---|---|
| **Active project** | `/Users/alex/Documents/Unreal Projects/RedMMOTitan/` → **`Titan.uproject`** |
| **Engine** | Unreal Engine **5.8.0** (exact). Mac = Apple Silicon Metal/SM6; Windows = DX12 |
| **Gameplay module** | `Source/RedMMO/` (also `Titan`, `TitanEditor`) |
| **Main map** | `/Game/RedMMO/Maps/RedPlanetGen` (EditorStartupMap + GameDefaultMap + ServerDefaultMap) |
| **GitHub** | `https://github.com/addgamestudios-ops/RedMMOTitan.git` (branch `main`) |
| **Legacy (ignore)** | `/Users/alex/Documents/Unreal Projects/RedMMO/RedMMO.uproject` |

Metal consequences: no hardware RT; prefer **Cascade** over GPU Niagara for visible FX on Mac. Lumen largely dialed down for perf.

**Git note:** `Content/` and `Plugins/` are **gitignored** (~58 GB Content). They travel via external drive / cloud. Git tracks `Source/`, `Config/`, `.uproject`, docs, and small helpers (`Tools/`, `steam_appid.txt`).

---

## 2. Locked good (DO NOT TOUCH / regression-check only)

User-confirmed or repeatedly praised — protect these:

| Item | Notes |
|---|---|
| **Ship RMB/LMB steering** | Improved radial nose aim — leave feel alone |
| **Atmosphere → stars** | ~1 km shell; space fade reads beautiful |
| **Sky clarity** | No grain / no star-dome leak onto ground; 2D cloud cards removed |
| **Jetpack plumes + sound** | Cascade exhaust when not broken by later edits — regression-check only |
| **Engines off on land/exit** | `EnsureEnginesOff` on UnPossess / exit |
| **Radial ship flight core** | WASD / Space / Ctrl / Shift boost / QE roll |

**Do not:**
- Re-apply mesh-wide `MF_DesertSand` / world-XY desert MIs on PlanetGen sphere chunks (causes UV stripes).
- Respawn `RedCloudCard` / SM_Cloud / Plane sky cards.
- Freeze `Jump_Loop` for all airborne time (breaks combat aim arms).
- Fight a boarded shuttle from GameMode Tick — `ARedShuttleBase` owns flight.
- Touch ship steering sensitivity “for fun.”

---

## 3. OPEN issues (user playtest 2026-07-11 — not fixed)

Document as **OPEN**. Do not mark fixed until user re-verifies in PIE with eyes / HighResShot.

1. **Ship engine plumes** — Some fire is visible but **hidden inside engines**. Need more offset out of nacelles / more flame like the very beginning of the arc. Code attempts Cascade `Large_Jet_Exhaust_PS` at scale ×10 + pack `NS_Thrusters`; **user still unhappy**. See [`HANDOVER_SHIP_PLUMES_TERRAIN.md`](HANDOVER_SHIP_PLUMES_TERRAIN.md).

2. **Sand** — **Unchanged** vs user expectation. Not SoStylized dunes / demo sand look. Biome-layer path (`MI_PlanetBiome_RED` Sand + SandMult boost) did **not** deliver demo dunes. Still open.

3. **Oasis terraforming pockets** — User **saw none**. Prior agent claimed `EnsureOasisTerraformingPockets` spawned water/palms/dunes near spawn — treat as **unverified / failed**. Do not claim spawn success without HighResShot + user eyes.

4. **Jetpack aim-while-shoot** — Code restored (`bWantFlyPose = bAirJet && !bCombatAim`). Status: **attempted restore; user should re-check** in PIE (double-Space → thrust + fire → aimed weapon, not open hands).

5. **Full planet dune silhouette** — Demo dunes are Landscape-authored; sphere PlanetGen cannot drop-in Landscape MIs. Mesh dunes / height work still needed for Mars look.

6. **Ship / camera under-terrain clamps** — **Unverified**. Do not assume radial clamps prevent clipping under the sphere mesh.

7. **Mixamo jetpack hover anim** — User must supply; `Jump_Loop` is stand-in only.

8. **Mac-only editor plugins** — Disable on Windows before compile (see Windows doc).

9. **FPS / volumetrics** — Volumetric clouds intentionally off / crushed; clear sky preferred.

---

## 4. Vision (user): Mars + terraforming

- **Whole planet surface** ≈ SoStylized-style **dune sand** (Mars-like), not gravel/stripes.
- **Oasis pockets** = StylizedDesertOasis water + palms/rocks as terraforming islands.
- Cool Mars + water look.

### What the SoStylized demo actually uses

| Asset | Role |
|---|---|
| `/Game/SoStylized/Maps/Desert/Demonstration_Desert` | Flat **Landscape** demo with sculpted dunes |
| `MI_Landscape_Desert` | Landscape MIC; Desert Sand Scale=1024, wind, sparkle |
| `MF_DesertSand` + `T_DesertSand_BC/N` | Sand look — authored for **Landscape UV0**, not PlanetGen spheres |
| `/Game/StylizedDesertOasis/` | Palms, rocks, `MI_Water`, demo maps |
| `SM_Desert_SandDune1/2` | Real dune **meshes** |

**Why sand keeps failing:** forcing Landscape/world-XY desert materials onto PlanetGen **sphere chunk meshes** → dark/light **UV stripes**. Safe path is sphere-aware `MI_PlanetBiome_RED` / `M_Planet` layers + textures into Sand LayerParameter — but that has **not** yet matched demo dunes visually (user: unchanged).

---

## 5. MCP / editor iteration (Mac)

Editor driven via ModelContextProtocol HTTP on **`:8000`**.

### Build (must kill editor first — Mac cannot relink a loaded dylib)
```bash
UPROJ="/Users/alex/Documents/Unreal Projects/RedMMOTitan/Titan.uproject"
pkill -9 -f "Titan.uproject"; sleep 3
"/Users/Shared/Epic Games/UE_5.8/Engine/Build/BatchFiles/Mac/Build.sh" \
    TitanEditor Mac Development -project="$UPROJ" -waitmutex
```
Built module: `Binaries/Mac/libUnrealEditor-RedMMO.dylib`.

### Relaunch
```bash
rm -f "$UPROJ/../Saved/PackageRestoreData.json"   # recovery modal blocks startup
pkill -9 -f CrashReportClient 2>/dev/null || true
nohup ue58 "$UPROJ" "/Game/RedMMO/Maps/RedPlanetGen" > /tmp/titan_launch.log 2>&1 &
# MCP ready when curl http://127.0.0.1:8000/mcp returns 405
```

### PIE rules
- Always `Slate.bAllowThrottling 0` or focus loss freezes PIE (~0 fps).
- First PIE after relaunch = cold shader compile — warm up before judging.
- Screenshots: `HighResShot` → `Saved/Screenshots/MacEditor/` — **required before claiming visual fixes**.
- Do not fight a running editor rebuild if another agent owns it.

### MCP gotcha
- Occasional **`FAppTime` ensure** when calling editor APIs from the MCP thread. Prefer small Python calls; avoid heavy asset factories from MCP.

---

## 6. Architecture (current)

### Planet
- **CLM PlanetGen** plugin (`BP_CLMPlanet`): ProceduralMesh + async chunks, radius **600000** (6 km), `MaxMountainHeight=50000`.
- Spawn basin attractor ≈ direction `(0.288, 0.957, 0.024)`, walk radius ~608045. Pin sun / ship / props to live settle location.
- `RedGravity::FindMeshPlanet` detects CLM via reflection (no hard plugin link).

### Ship — `ARedShuttleBase`
- C++ parent for pack `BP_Shuttle`.
- Radial frame flight: WASD / Space / Ctrl thrust, **RMB+mouse** free nose aim, **LMB** look, **Shift** boost, Q/E roll, O hangar.
- Auto `EnsureEnginesOn` on possess; `EnsureEnginesOff` on land / UnPossess / exit.
- Engine FX: pack Niagara + Cascade `Large_Jet_Exhaust_PS` backup (Metal). **Plumes still need more out-of-nacelle offset** (OPEN).

### Player — `ARedPlayerCharacter`
- Trooper + alien swap (P), radial gravity via `URedCharacterMovement`.
- Jetpack: `UChildActorComponent` → Sci-Fi Jetpack Master BP on `spine_03`.
- Cascade plumes on Exhaust_L/R; cyan mesh cones are hidden stand-ins.
- Double-Space jetpack; Shift = ground sprint + air boost.
- Hover pose stand-in: `A_ThirdPersonJump_Loop` until real Mixamo hover imported.
- Combat aim: `UpdateJetpackFlightAnim` drops Jump_Loop while `bCombatAim` (**re-check in PIE**).

### GameMode — `ARedGameMode`
- Standing spawn on CLM.
- `EnsureAtmosphereAndClouds`, `EnsureSpaceStarDomes` (space only — destroy on ground).
- `EnsureSoStylizedSandOnPlanetTerrain` — biome-layer path; **user: sand unchanged**.
- `EnsureOasisTerraformingPockets` — code present; **user saw none** → treat failed.
- `EnsureSparseCloudCards` — **destroys** leftover cards only (no respawn).

### HUD
- `/Game/RedMMO/UI/WBP_VibeMMOHUD` — shield/health, abilities, jetpack stamina.

---

## 7. Key files

| Path | Role |
|---|---|
| `Source/RedMMO/RedShuttleBase.{h,cpp}` | Radial ship flight, engines on/off, plume FX |
| `Source/RedMMO/RedPlayerCharacter.{h,cpp}` | Trooper, jetpack, board/exit, sky fade, aim |
| `Source/RedMMO/RedGameMode.{h,cpp}` | Spawn, sand/oasis/atm/stars ensures |
| `Source/RedMMO/RedCharacterMovement.{h,cpp}` | Radial gravity, surface snap |
| `Source/RedMMO/RedGravityBodies.{h,cpp}` | CLM planet detection |
| `Source/RedMMO/RedBolt.{h,cpp}` | Projectiles + Cascade impacts |
| `Source/RedMMO/RedMMOEditorTools.{h,cpp}` | Editor/MCP helpers |
| `Config/DefaultEngine.ini` | Maps, Steam OSS (App ID **480**) |
| `Config/DefaultInput.ini` | Sprint/Shift, flying axis |
| `steam_appid.txt` | `480` (Spacewar dev) |
| `/Game/RedMMO/Maps/RedPlanetGen` | Play map |
| `/Game/SpaceShip/Blueprints/BP_Shuttle` | Pack ship BP |
| `/Game/Jet_Packs_Sci-Fi/...` | Jetpack + Cascade exhaust |
| `README.md` | Codex entry — clone, layout, build |
| `CODEX_HANDOVER.md` | Full agent brief (mission, bugs, architecture) |
| `docs/WINDOWS_STEAM.md` | Full Windows PIE + package + Steam |
| `WINDOWS_BUILD.md` | Short friend-facing package notes |
| `HANDOVER_SHIP_PLUMES_TERRAIN.md` | Open plume/sand/oasis track |
| `Tools/fix_*.py`, `Tools/tiny_mcp.py` | Atmosphere/stars/sand MCP scripts |

---

## 8. Verification protocol (mandatory)

Before claiming any visual fix:

1. Rebuild if C++ changed; relaunch editor; warm shaders in PIE.
2. `Slate.bAllowThrottling 0`.
3. Capture **`HighResShot`** from the relevant camera (chase cam for ship plumes; ground for sand/oasis).
4. Ask user to load PIE and confirm — do not go idle without saying what to check.
5. If user says they saw nothing → mark **failed**, not “spawned.”

---

## 9. Windows / Steam (summary)

Mac snapshot is frozen for handoff. **Win64 cook/package needs a Windows PC.**

1. Clone `https://github.com/addgamestudios-ops/RedMMOTitan.git`
2. Copy `Content/` + `Plugins/` from Mac drive into clone root
3. UE **5.8.0** + VS 2022; disable Mac-only plugins in `Titan.uproject`
4. Build `TitanEditor` Win64 → PIE on `RedPlanetGen`
5. Package Win64 via UAT; place `steam_appid.txt` (`480`) beside exe
6. Steam multiplayer already wired (OnlineSubsystemSteam, App 480)

**Full steps:** [`docs/WINDOWS_STEAM.md`](docs/WINDOWS_STEAM.md) · short [`WINDOWS_BUILD.md`](WINDOWS_BUILD.md).

---

## 10. Hard-won gotchas

1. Pawn settles at basin `(0.288,0.957,0.024)` — pin lighting/props there.
2. `Slate.bAllowThrottling 0` always in PIE.
3. Never override shared `Texture` on all `M_Planet` layers.
4. Clear `PackageRestoreData.json`; kill `CrashReportClient` squatters.
5. Don't GameMode-Tick-fight a boarded shuttle.
6. `PreviewPlanet()` + save = huge map; destroy preview chunks before save.
7. Work only in **RedMMOTitan / Titan.uproject**.
8. Additive `SpaceStarDome` on ground = grey grain sky — destroy on ground, spawn only in space.

---

## 11. Recommended next (Windows machine / next AI)

1. **Windows first PIE** + first packaged `Titan.exe` + Steam invite test (App 480).
2. **Ship plumes** — push Cascade further out of nacelles / larger flame (user: still inside engines).
3. **Sand** — new approach toward SoStylized dune read without sphere UV stripes (OPEN).
4. **Oasis** — diagnose why pockets never appeared for user; fix + HighResShot prove.
5. **Jetpack aim** — user re-check after restore.
6. Import Mixamo jetpack hover when provided.
7. Push `Source`/`Config` often — friend `git pull`s without re-copying Content.

---

*Bottom line: radial ship steering, atmosphere→stars, and sky clarity are in good shape. Ship plumes need more visible flame outside engines. Sand and oasis terraforming are **not** delivered to user eyes. Jetpack aim restore needs re-check. Windows/Steam is the parallel track using this repo + drive-copied Content.*
