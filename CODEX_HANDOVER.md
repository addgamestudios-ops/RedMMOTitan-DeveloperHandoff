# Codex Handover — RedMMO Titan

**Audience:** Coding agents (Codex, Cursor, Claude, etc.) picking up this repo cold.  
**Snapshot:** 2026-07-14 corrected 50 km Development package, both packaged map smokes, and container contents verified · hands-on visual/gameplay approval and real two-account Steam join remain open · GitHub `main` · remote https://github.com/addgamestudios-ops/RedMMOTitan.git
**Entry README:** [`README.md`](README.md)  
**Do not** start a long gameplay fix loop unless the user explicitly asks. Prefer docs + honest status over overclaiming.

---

## 0. Where to go on GitHub

| | |
|---|---|
| **Clone** | `git clone https://github.com/addgamestudios-ops/RedMMOTitan.git` |
| **Repo** | https://github.com/addgamestudios-ops/RedMMOTitan |
| **Branch** | `main` |
| **This file (raw)** | https://github.com/addgamestudios-ops/RedMMOTitan/blob/main/CODEX_HANDOVER.md |
| **README** | https://github.com/addgamestudios-ops/RedMMOTitan/blob/main/README.md |

**After clone:** copy `Content/` + `Plugins/` from the Mac drive into the clone root. They are **gitignored** and required for maps/assets.

### Related docs (cross-links)

| Doc | Role |
|---|---|
| [`README.md`](README.md) | Clone, layout, Mac/Win build, open map |
| [`HANDOVER.md`](HANDOVER.md) | Full Mac→Windows engineering handover |
| [`HANDOVER_SHIP_PLUMES_TERRAIN.md`](HANDOVER_SHIP_PLUMES_TERRAIN.md) | Historical plume / terrain / oasis investigation; defer to this file for current Windows status |
| [`docs/WINDOWS_STEAM.md`](docs/WINDOWS_STEAM.md) | Windows PIE, UAT package, Steam App 480 |
| [`docs/MINI_FIGHTER.md`](docs/MINI_FIGHTER.md) | Rear-bay mini fighter, docking, boarding/camera/collision boundaries |
| [`docs/PLANET_TERRAIN_AUTHORING_PLAN.md`](docs/PLANET_TERRAIN_AUTHORING_PLAN.md) | Held plan for continent, coastline, ocean-coverage, and elevation authoring |
| [`docs/PLANET_50KM_IMPLEMENTATION_SPEC.md`](docs/PLANET_50KM_IMPLEMENTATION_SPEC.md) | Exact 50 km circumference, 27 blended regions, seamless-world architecture, and acceptance gates |
| [`docs/PLANETGEN_PINNED_FORK.md`](docs/PLANETGEN_PINNED_FORK.md) | Project-local PlanetGen 1.4.0 fork, opt-in test profile, rollback, and scalability limits |
| [`docs/ALIEN_WORLD_ART_BIBLE.md`](docs/ALIEN_WORLD_ART_BIBLE.md) | Supplied mood board translated into biome families, shape language, colors, and asset priorities |
| [`docs/WORLD_AUTHORING_WORKFLOW.md`](docs/WORLD_AUTHORING_WORKFLOW.md) | Pack selection, hand placement, and manual-POI protection before future PCG |
| [`docs/MESHY_TRIPO_ALIEN_ASSET_PIPELINE.md`](docs/MESHY_TRIPO_ALIEN_ASSET_PIPELINE.md) | Meshy/Tripo concept-to-Unreal production and validation pipeline |
| [`docs/PLAYER_MENU.md`](docs/PLAYER_MENU.md) | Escape menu and live Inventory/Skills presentation |
| [`WINDOWS_BUILD.md`](WINDOWS_BUILD.md) | Short friend-facing Win64 notes |

---

## 0.5. Windows takeover update (2026-07-11)

- Official UE 5.8 MCP is working with `-ModelContextProtocolStartServer -ModelContextProtocolPort=8000`.
- Default pawn is the creator-native **deep-red Tall Female Trooper** assembled from Action Trooper preset 8. The AMF creator tables now contain Trooper head/upper/lower/hands/feet/shoulders/helmet rows, so gameplay and the creator use one coherent modular character.
- `BP_Character_Master` and `BP_Character_Preview` inherit `ARedPlayerCharacter`; press **I** (or **P** / gamepad face-left) to open the creator.
- Gameplay rifle is `/Game/Action_Trooper/Meshes/Trooper_Accessories/SK_Trooper_Weapon_Rifle_A`, attached to `hand_rSocket`. The creator preview displays either this fallback or a selected creator weapon, never both; gameplay keeps the native rifle authoritative.
- Red helmet copy: `/Game/RedMMO/Characters/SK_TF_Trooper_Helmet_002_DeepRed`; slot `04_Visor` uses the red visor material.
- Imported owned effects: `/Game/ProjectilesVol1` (27 projectile/flash/hit sets) and `/Game/Muzzles`. The live rifle now uses `P_Flash_4` at the accepted muzzle transform, the restored emissive `ARedBolt` tracer (`M_BoltTracer`), and normal-scale `P_Hit_3` impact art.
- Earlier verified Windows archive: `D:\RedMMOTitanWindowsData\PackagedBuilds\Development_20260711_212530\Windows\Titan.exe` (Development, 2.699 GB). Headless launch exited 0 with no error-severity log lines.
- `Content/` remains gitignored. Back up or transfer the modified AMF DataTables, imported Fab folders, and the red helmet asset with the project Content directory.

---

## 0.6. Windows UI, jetpack, weapons, and multiplayer validation (2026-07-12)

- Installed the Mac **VibeMMO player UI** handoff: `/Game/RedMMO/UI/WBP_VibeMMOHUD`, its generated UI assets, `/Game/SciFi_Skills_Icon`, and `Plugins/VibeMMOUIKit`. The HUD is created only for the locally controlled pawn and includes portrait/status, compass, surface/space minimap, abilities, resources, the purchased pack sight, and weapon slots.
- Installed the **Sci-Fi Jet Packs** runtime assets under `/Game/Jet_Packs_Sci-Fi`. Gameplay loads `Sci-Fi_Jetpack_Master_BP`, `Large_Jet_Exhaust_PS` (with `Jet_Exhaust_PS` fallback), and `Jet_Engine_Light_Loop_Cue` while preserving the project character/animation stack.
- Restored barrel-aligned weapon presentation: the muzzle flash is spawned in world space at the accepted barrel tip and rotated with `ShotDirection.Rotation()`, the visible projectile is the emissive `M_BoltTracer` tracer rather than the later Niagara overlay, and impacts use `P_Hit_3` at authored scale `1.0`.
- Hardened multiplayer weapon/jetpack behavior: bolt visual profile replication, server-authoritative collision, reliable impact multicast with delayed destruction, predicted-versus-authoritative muzzle reconciliation, replicated jetpack/enemy state, and spatial remote jetpack audio.
- **Verified:** a two-player listen-server PIE session showed the VibeMMO HUD, both replicated troopers and jetpacks, rifle carry, airborne thrust/fire, barrel-aligned shots, and normal-scale impacts. Steam Integration Kit **v1.9** is now the sole Steam stack, using its replacement OnlineSubsystemSteam and SteamSockets modules with development App ID **480**.
- Restored `/Game/RedMMO/Materials/M_ShipPlume_Cyan` as an HDR cyan unlit emissive material so the packaged ship no longer falls back to the gray engine cone material. Shuttle exhaust activation is now idempotent, and the Cascade backup seats its nozzle from the live mesh bounds instead of a fixed buried offset.
- Hardened the `ARedPlayerCharacter` ↔ `ARedShuttleBase` controller/input handoff. Official-MCP two-client PIE verified remote-client board → shuttle `ROLE_AutonomousProxy`, the correct chase camera, bright plumes outside both nacelles, **V** exit → player `ROLE_AutonomousProxy`, and a clean reboard. Evidence: `Saved/ShuttlePlume_MultiplayerPIE_20260712.png`.
- **Steam-specific baseline package:** `D:\RedMMOTitanWindowsData\PackagedBuilds\Development_SIK_FINAL_20260713_001029\Windows` (Development; launch `Titan.exe`). Its clean smoke initialized the Steam client and Game Server APIs, selected `STEAM`, reached authentication and SDR relay status `OK`, completed four empty compatible-lobby searches, created the advertised eight-slot RED listen lobby, and listened with `SteamSocketsNetDriver` on port 7777 (`Saved/SteamSIKFinalSmokeClean_20260713_001029.log`). A real two-account client join/PvP test remains outstanding.

### FocalRig rifle aim, movement poses, heat, and replication proof

- **FocalRig 1.3.5** is enabled for UE 5.8. `/Game/RedMMO/Characters/CR_RedTrooperFocalAim` uses `spine_01`–`spine_03`, both arms, and `red_virtual_muzzle`, calibrated from the physical grip-to-muzzle line. `/Game/RedMMO/Characters/ABP_RedTrooperFemale` maps `FocalAimTarget` and `FocalAimWeight` into the rig.
- Relaxed carry remains the base stance. The AnimGraph adds looped `/Game/RedMMO/Anims/Rifle/A_Rifle_Jog_Aim_Fwd` and `/Game/RedMMO/Anims/Rifle/A_Rifle_Jetpack_Aim_Air` selectors before `DefaultSlot`, Layered Bone Blend, and FocalRig, preserving the firing montage.
- `ResolveWeaponAim` traces the camera reticle, then calculates the accepted trajectory from the actual barrel tip. `P_Flash_4` and `ARedBolt` use the same `ShotDirection`; `P_Hit_3` remains at authored scale.
- Runtime `WeaponBarrelAimDot` proof: standing `1.000000`, running `1.000000`, jetpack `0.9999939`, and the remote client copy `0.9999929`.
- Weapons have **no reload or magazine**. Replicated authoritative heat is `100` maximum, `+7` per shot, `-28/s`, with firing locked until heat falls to `25` or below. **1 / 2** select the replicated rifle slots; **Q / E** activate Grapple and Slam; **Tab** opens the native loadout and can swap their assignments. The old R/F/X ability mappings are removed.
- Official-MCP two-client listen-server PIE verified replicated aim, jetpack pose, firing, heat state, and remote FocalRig execution. That PIE run used NULL OSS; it proves gameplay replication, not a Steam transport session.
- The final package independently verified SIK's Steam SDK 1.64 transport under App **480**: client/Game Server initialization, the `STEAM` subsystem, authentication, SDR relay status `OK`, four empty searches, eight-slot lobby creation, and port-7777 listening. The session still needs a real two-account host/invite/join/reconnect/PvP test; the first-run Windows Firewall dialog requires manual approval.

### Ultimate Stylized crosshair and weapon-card heat UI

- Purchased source: [Ultimate Stylized UI Crosshair Pack - Unreal Engine 5](https://www.fab.com/listings/707a878d-0d11-431a-813c-a7aaad10109f). The Fab download supplied a UE 5.6 `/Game/Crosshair` asset package; it was imported, opened, upgraded, and resaved through UE 5.8.
- The live sight is `/Game/RedMMO/UI/Crosshair/MI_RedMMO_ArcSight`, a project-local material instance based on the pack's design 38 (`/Game/Crosshair/UI_Material/MI_Crosshair38`). Target-lock alpha smoothly scales the sight and transitions its authored red, green, and blue channel parameters toward the lock colors.
- `ARedHUD` retains the center-screen target trace and enemy world-space shield/health bars, but draws **no** Canvas square reticle and **no** center heat arc. It forwards target-lock state to the retained VibeMMO HUD widget instead.
- Weapon heat is now a smooth rounded progress rail on the active bottom-right weapon card. Cooling adds a cyan card frame/wash; overheat adds a pulsing red frame/wash. The card border and background use semantic rarity colors, currently Epic for slot 1 and Legendary for slot 2.
- **Verified:** the C++ target built successfully, and an official-MCP two-client listen-server PIE run showed the pack sight plus active-card heat/rarity presentation on both local player HUDs.

### Critical Jet_Packs cook rule

Do **not** always-cook the entire `/Game/Jet_Packs_Sci-Fi` directory. Unused legacy demo animation sequences in that pack reference missing skeleton dependencies and can trigger an `AnimSequence.cpp` zero-hash assertion during cook. Cook only these runtime packages in addition to the normal project content:

- `/Game/Jet_Packs_Sci-Fi/Blueprints/Sci-Fi_Jetpack_Master_BP`
- `/Game/Jet_Packs_Sci-Fi/Particles/Large_Jet_Exhaust_PS`
- `/Game/Jet_Packs_Sci-Fi/Particles/Jet_Exhaust_PS`
- `/Game/Jet_Packs_Sci-Fi/Audio/Jet_Engine_Light_Loop_Cue`

Pass those exact packages through UAT `-additionalcookeroptions=-PACKAGE=...` (joined with `+`) or an equivalent explicit package list. Keep `/Game/SciFi_Skills_Icon` in `DirectoriesToAlwaysCook`; the VibeMMO ability icons are loaded dynamically and must be present in packaged builds.

### Windows environment, ships, abilities, and session browser (2026-07-12)

- **Sand FX:** `ARedPlayerCharacter` configures `UFootstepTrailComponent` with `/Game/Vefects/Sand_VFX/VFX/DynamicSandSurface/Materials/M_VFX_Footstep_Decal` and `/Game/Vefects/Sand_VFX/VFX/LitSandPuff/NS_SandPuff_Small`. The locally controlled camera also runs `/Game/Vefects/Sand_VFX/VFX/AmbientSand/NS_Flying_Sand_Around_Camera`. Dedicated servers skip these visuals. Do not add the separate NOOD pack; the attached Sand FX pack supplies the requested footprints.
- **Desert/ocean baseline:** the PlanetGen terrain and oceans are retained. The previous procedural foliage, grass, rocks, cliffs, and snow pass is intentionally suppressed; the latest packaged runtime disabled seven dressing actors. Three saved `RedOasisWater_*` assets remain available, but no procedural oasis rocks or plant dressing should be treated as current surface composition.
- **Clouds/space:** eight reusable `AHeterogeneousVolume` actors use project-owned violet, cyan, gold, and rose material instances and are now evenly distributed around the atmosphere instead of clustering at spawn. SkyAtmosphere remains active in far orbit, the old opaque rim/painted cloud-band shells are retired, and runtime space scenery uses randomized stars/asteroids, a compact live **210×210** orbit radar, dark-side fill, and the reachable physical moon (~0.9 km at ~60 km). The raw `.vdb` files remain under `Saved/SourceAssets`; do not return them beside the imported assets.
- **Ships:** `/Game/RedMMO/Ships/BP_RedPilotableShuttle` (`ARedShuttleBase`) and `/Game/RedMMO/Ships/BP_RedModularStarSparrow` (`ARedShip`) are saved in `RedPlanetGen`. Both have replicated health, pilot/occupant state, movement, weapon heat/overheat, server-computed muzzle/aim, server-authoritative bolt spawning, and replicated death/ejection behavior. **B/V** selects the main shuttle, **F** selects the mini fighter, and **C** switches functional cockpit/chase cameras. The shuttle's raw UObject audio caches now use `TStrongObjectPtr` to survive garbage collection.
- **Player combat/UI:** two replicated rifle slots, independent heat state, 100 replicated armor with post-shield mitigation, ragdoll, Q/E Grapple/Slam, and a Tab loadout are implemented. The weapon textures are exact transparent cutouts over solid Epic/Legendary rarity fills. Escape puts **Multiplayer / Lobby** directly below Resume, followed by Overview, Inventory, Skills/Loadout, Settings, and two-click Exit without pausing live network sessions. The July 12 grapple visual used crossed animated plasma ribbons; the July 14 source update supersedes that as the normal path with the Beams-pack Niagara cable while retaining the splines as fallback only. The vendor controller's stray `I` / `customization window` HUD text was removed; **I/P** still deliberately opens the character creator.
- **Steam UI:** Escape -> **Multiplayer / Lobby** or **F8** opens `URedSessionBrowserWidget` in packaged builds; **F6** is the PIE fallback because Unreal Editor consumes F8 for Possess/Eject. The browser provides Create Game, Find Games, Join Selected, Reconnect, **Invite Friends**, Leave Game, and Close. Active hosts reopen as Connected and do not auto-search. Session creation uses at least eight public connections, includes RED product/build/type filtering, and cleans up stale membership around travel/network failures. `JoinHost <SteamID64>` is a strict **Development-only** fallback and is disabled in Shipping.
- **Build/PIE status:** `TitanEditor Win64 Development` built successfully after these changes. Two-client PIE verified the remote shuttle handoff/plumes as well as gameplay replication/UI, but uses NULL OSS; it is not proof of Steam transport or a two-account join. Day/night now promotes the SunSky attachment chain to Movable before rotation, eliminating the prior `SunSky_C_0` mobility spam.

## 0.7. Historical alien-biome and lobby package (superseded, 2026-07-13)

- **Historical package:** `D:\RedMMOTitanWindowsData\PackagedBuilds\Development_ALIEN_LOBBY_20260713_034618\Windows`. It is retained only as evidence for the earlier lobby pass; it is **not** the current handoff build.
- **Superseded input:** this package used shared B/V selection. The current mapping reserves **B/V** for the main shuttle and **F** for the mini fighter. **I** still deliberately opens the character creator.
- **Grapple:** acquisition traces world geometry and live players, so land/rocks are valid anchors instead of requiring a shuttle hit. Only hits closer than **1.5 m** are rejected; the player-vs-player damage/pull path is retained.
- **Ships:** shuttle/fighter collision, cockpit/chase cameras, landing/surface handling, engine audio, and faster vacuum travel were stabilized. Runtime modular collision fits the live hull/deck. Weapon impacts are distinct; ragdoll remains active; destroying an occupied craft applies the occupant-death path.
- **Historical environment:** this package used the earlier fixed-count space population and temporary alien-colour scatter. Both are superseded: the latest package randomizes stars/asteroids and suppresses procedural foliage/grass/rocks/cliffs/snow.
- **UI:** inventory/skills mock data is disabled; pages show live state or explicit empty slots. Escape now exposes the multiplayer lobby directly.
- **Steam host fix:** `ARedGameMode::BeginPlay` explicitly finalizes same-map listen travel, so `StartSession` is no longer missed. Final packaged smoke created the eight-slot lobby, listened with SteamSockets on port 7777, reached Multiplayer Online, and reopened the lobby as Connected without launching another search.
- **Honest boundary:** successful builds/package/visual smoke prove compilation, cooking, startup, the logged runtime counts, and the single-account host lifecycle. Steam still lacks a real RedMMOTitan App ID/depot/package and a real two-account join/PvP test.

## 0.8. Desert-stability, shuttle-GC, mini-fighter, and space-UI repair (historical predecessor package, 2026-07-13)

- **Historical predecessor package:** `D:\RedMMOTitanWindowsData\PackagedBuilds\Development_DESERT_STABILITY_20260713_181525\Windows` (launch `Titan.exe`). `TitanEditor` and `Titan` Win64 Development, a full clean cook/package, and packaged runtime smoke succeeded. Evidence: `D:\RedMMOTitanWindowsData\PackagedBuilds\Development_DESERT_STABILITY_20260713_181525\Windows\Titan\Saved\Logs\Titan.log`. The July 14 50 km foundation archive in section 0.9 supersedes this as the current packaged handoff.
- **Runtime evidence:** the process ran **3m46s** from shuttle boarding at 16:20:06 to mini-fighter launch at 16:23:52, toggled **C** into chase view, and produced no fatal/critical/assert/unhandled matches or crash folder.
- **Boarding:** **B/V** targets the main shuttle; **F** is dedicated to the rear-bay mini fighter. The mini fighter's registered dock bounds remain selectable while bay collision is disabled.
- **Shuttle collision/crash fix:** the shuttle creates three fitted blocking hull boxes plus three walkable deck boxes. Its static raw UObject sound and attenuation caches were converted to `TStrongObjectPtr`, fixing the garbage-collection invalidation that caused the longer-flight crash.
- **Mini fighter:** the runtime contract is **+X forward**, one rear engine plume, and compact fitted collision. The packaged runtime restored compact collision and launched the fighter; exact visual orientation/plume quality still requires the user's eyes.
- **Surface FX:** every center/foot/scuff emitter uses a physical-material trace and a 220 cm contact limit. Explicit sand is accepted; ships, spacecraft, vehicles, water, foliage, rocks, and structures are rejected, preventing desert dust while walking on a craft or above the ground.
- **Environment cleanup:** procedural foliage, grass, rocks, cliffs, and snow are suppressed; runtime disabled **seven** dressing actors while retaining the PlanetGen terrain and oceans. Eight High Five clouds are evenly distributed around the atmosphere. Future landmass/heightmap work is held in [`docs/PLANET_TERRAIN_AUTHORING_PLAN.md`](docs/PLANET_TERRAIN_AUTHORING_PLAN.md).
- **Space UI/lighting:** stars and asteroids are randomized, the orbit radar is a compact live **210×210** display, and dark-side fill prevents the planet surface from becoming unreadable black.
- **Steam discovery:** startup auto-match is disabled so two players do not silently create separate lobbies after an empty search. The host explicitly chooses Create Game and the client chooses Find Games/Join Selected. SIK lobby search is compiled with Steam's worldwide distance filter. Current smoke verifies Steam authentication and SDR readiness; the actual two-account join remains unproved.
- **Cook schema gotcha fixed:** after adding native default subobjects, rebuild `TitanEditor` before cooking. The stale editor DLL cooked old reflected field indices and produced `Bad export index` in `BP_RedPilotableShuttle`; rebuilding the editor target and doing a clean recook eliminated the failure.

## 0.9. Beams, night-water, and 50 km authoring foundation (current packaged handoff, 2026-07-14)

- **Build/package truth:** the consolidated `TitanEditor Win64 Development` target succeeded after these source/plugin changes. The corrected current archive is `D:\RedMMOTitanWindowsData\PackagedBuilds\Development_50KM_FOUNDATION_20260714_035718` (normal launch: `Windows\Titan.exe`; isolated-map launch: `Windows\Launch_50km_Test.bat`). `D:\RedMMOTitanWindowsData\BuildLogs\Package50km_20260714_035718.log` ends `BUILD SUCCESSFUL` and `ExitCode=0` after cook, stage, package, and archive.
- **Grapple cable:** `ARedPlayerCharacter` now loads `/Game/BeamsPack/VFX/Beams/NS_BeamOnly_02.NS_BeamOnly_02` into a Niagara component attached at `hand_r`. Gameplay rotates the system's local +Z axis toward the replicated anchor and updates `User.BeamLength` in centimetres, keeping the continuous beam aligned to the real hand-to-anchor span. The two crossed `/Game/RedMMO/Materials/MI_RedGrapplePlasma` spline ribbons remain an automatic fallback only when the Beams asset cannot load. `/Game/BeamsPack/VFX/Beams` is included in `DirectoriesToAlwaysCook`; `D:\RedMMOTitanWindowsData\BuildLogs\Package50km_20260714_035718.log.iostore.list.txt` proves `NS_BeamOnly_02.uasset` is in the packaged IoStore container. Hands-on beam rendering and gameplay feel still require visual approval.
- **Night/space/water baseline:** `ARedSpaceScenery` builds a scrambled procedural **2,800-star** field, randomized asteroids, a reachable physical moon, and an additive moon-glow shell. Stars are available in space and become surface-visible on the night side. `ARedDayNight` retains the 7,200-second/two-hour cycle and dark-side fill. `URedShorelineWaveComponent` repairs the spherical water tangent basis and generates traced SoStylized shoreline crests. The isolated-map runtime smoke confirmed the shared `795,775 cm` surface radius, SoStylized ocean, star tiers `2240/464/96`, 72 decorative asteroids, moon fill, and water tangent repair; packaged bootstrap now passes, while hands-on visual approval remains pending.
- **Pinned PlanetGen fork:** `Plugins/PlanetGenPinned_1_4_0_RedMMO` is a project-local copy of PlanetGen 1.4.0 that shadows the engine Marketplace copy without modifying `D:\UE_5.8`. It fixes settings propagation, streaming-source selection, angular view limits/hysteresis, tangent-correct chunk centres, near-ring collision, and stale async terrain/grass uploads. Its opt-in **Apply RedMMO 50 km Test Profile** uses an exact `795,774.715 cm` radius, a conservative 216-actor pool, 32-vertex chunks, Smooth noise, near-ring collision, and no procedural foliage/grass. The fork is local/licensed and currently ignored by git; transfer it deliberately with project plugins.
- **27-region foundation:** `RedPlanetRegionService` defines one continuous **50.000 km-circumference** spherical world with 27 deterministic spherical-Fibonacci authoring sites. Great-circle lookup and four-way blending provide art/biome metadata without collision, teleport, streaming, or visible region boundaries. It is metadata and test infrastructure, not 27 separate levels and not a finished terrain implementation.
- **M03 authoring-region checkpoint (in progress):** `URedPlanetRegionBlueprintLibrary` now exposes the compiled region metadata, lookup/blending, tangent frames, and tangent Exp/Log placement helpers to Blueprint. `ARedPlanetRegionAnchor` supplies editor-only authoring markers with actor/component collision, overlap generation, and navigation influence disabled. `D:\RedMMOTitanWindowsData\BuildLogs\TitanEditor_M03Regions_20260714.log` records a successful `TitanEditor Win64 Development` build, and `D:\RedMMOTitanWindowsData\BuildLogs\RegionServiceAutomation_20260714.log` records `RedMMO.Planet.RegionService.DeterministicGeometry` as `Success`.
- **M03 isolated-map proof:** `D:\RedMMOTitanWindowsData\BuildLogs\Create50kmRegions_FirstRetry_20260714.log` records exactly 27 managed, collision-disabled anchors in `/Game/RedMMO/Maps/RedPlanetGen_50km_Test`. A new editor process then produced `spawned=0 reused=27 removed=0` (`removed_managed_duplicates=0` in the log) in `D:\RedMMOTitanWindowsData\BuildLogs\Create50kmRegions_Idempotent_20260714.log`. The production `RedPlanetGen.umap` SHA256 remained `1DF9E6ED913A267875F1EF452F6ED51DAF337DBBAAE4C6EC3379EA6299346724`, and `D:\RedMMOTitanWindowsData\BuildLogs\AuditProductionRegionAnchors_20260714.log` reports `count=0 result=clean read_only=true`. `D:\RedMMOTitanWindowsData\BuildLogs\Smoke50kmRegions_20260714.log` loaded the updated isolated map and exited cleanly.
- **M03 geodesic hub-stamp checkpoint (in progress):** `D:\RedMMOTitanWindowsData\BuildLogs\TitanEditor_M03HubStamps_20260714.log` ends `Result: Succeeded`, and `D:\RedMMOTitanWindowsData\BuildLogs\TerrainStampAutomation_20260714.log` records `RedMMO.Planet.TerrainStamp.DeterministicGeodesicMath` as `Success` with test exit code `0`. The first isolated-map authoring run wrote exactly 27 `sample_base_at_center` stamps (`count=27 changed=1`) in `D:\RedMMOTitanWindowsData\BuildLogs\Create50kmHubStamps_First_20260714.log`; a fresh second run reused all 27 anchors and made no stamp change (`count=27 changed=0`) in `D:\RedMMOTitanWindowsData\BuildLogs\Create50kmHubStamps_Idempotent_20260714.log`. `D:\RedMMOTitanWindowsData\BuildLogs\Smoke50kmHubStamps_20260714.log` resolved all 27 enabled terrain stamps and exited cleanly. The read-only production audit at `D:\RedMMOTitanWindowsData\BuildLogs\AuditProductionHubStamps_20260714.log` reports `count=0 terrain_stamps=0 result=clean read_only=true`, and the production map SHA256 remains `1DF9E6ED913A267875F1EF452F6ED51DAF337DBBAAE4C6EC3379EA6299346724`.
- **M02 ship/shuttle exact-terrain checkpoint (source/runtime, not re-packaged):** `RedPlanetTerrainQuery` routes ship landing/parking/exit/void/governor logic and shuttle landing/terrain/camera clamps to exact active terrain owned by the matching PlanetGen actor. The filtered physical checkpoint also integrates the production ship's swept `260 cm` root sphere into `URedShipMovementComponent`: local controlled flight and server-authoritative remote flight share the same safe-move, impact/slide, crater-aware recovery, and velocity path. Focused real-Chaos PIE crossed the cooked `+X/+Y` fixture, ignored a closer generic `WorldDynamic` blocker, preserved an earlier native `WorldStatic` component at exactly `3400.000 cm`, and then stopped the actual root on the exact owned terrain contact after the control wall was removed. The expanded all-boundary fixture then used that native root and shared mover for 12 high-speed edge crossings plus 24 signed X/Y/Z corner-loop legs; all 8 loops closed, maximum endpoint error was `0.000000 cm`, and minimum route speed was `25993.982 cm/s`. `D:\RedMMOTitanWindowsData\AutomationReports\ShipAllBoundaries_Acceptance_20260715_0815\index.json` records the focused test as `Success`, and `D:\RedMMOTitanWindowsData\AutomationReports\ShipAllBoundaries_FusedRegressions_20260715_0815\index.json` records all five fused runtime tests as `Success`, failed `0`. The constrained initial-overlap retry then compiled successfully and focused real-Chaos PIE placed the production root `50.007141 cm` inside the active seam, repeated a stable MTD four times, corrected `50.132141 cm` outward, completed the full `100.000549 cm` tangential `SafeMove` with zero endpoint error, and ended on a clear exact probe (`D:\RedMMOTitanWindowsData\AutomationReports\ShipInitialOverlap_Acceptance_20260715_0911\index.json`: `Success`, errors `0`). Its post-change fused regression passed all five tests with failed `0` and errors `0`; this verifies the existing movement-triggered depenetration path.
- **M02 passive zero-input root checkpoint (source/runtime, not re-packaged):** `URedShipMovementComponent` now performs a throttled authority-only zero-length exact-terrain sweep before its controller early return, skips attached craft, and applies one bounded MTD to a stationary penetrating sphere/capsule root. Focused real-Chaos PIE enabled only the real movement tick on an unpossessed production `260 cm` root embedded `50.007141 cm` at the active seam. `RED_SHIP_PASSIVE_ZERO_INPUT_PASS` reported 16 ticks, expected/observed outward correction `50.132141/50.132141 cm`, `0.000546 cm` tangent displacement, zero expected error and settle drift, and final `NoHit`. `D:\RedMMOTitanWindowsData\AutomationReports\ShipPassiveOverlap_AcceptanceRetry_20260715_1249\index.json` is `Success`, failed `0`, errors `0`; the subsequent fused prefix passed all five tests with failed `0`, errors `0`, exit `0`, and no fatal/assert/ensure. All four protected hashes remain unchanged. This is still root-sphere-only: attached body/deck/wing boxes, packaged-client recovery, landing/exit, hands-on rendered traversal, and two-client authority/replication remain open.
- **M02 oriented fitted-hull box-query checkpoint (source/runtime, not re-packaged):** the pinned PlanetGen exact query now accepts validated oriented boxes, rejects non-finite rotation magnitude/normalization before Chaos, and uses rotation-aware AABB candidate culling. Focused real-Chaos PIE rejected a finite-component overflow quaternion, then swept a `1100 x 900 x 300 cm` box rotated `37 degrees` through the cooked `+X/+Y` seam. The raw control hit the nearer transient `WorldDynamic` blocker; PlanetGen and `RedPlanetTerrainQuery` ignored it, selected the same owned key `(0,5,2)`, returned identical `79751.382812 cm` distance, and stayed stable across eight direct repeats (`RED_FUSED_ACTIVE_TERRAIN_BOX_PASS`). `D:\RedMMOTitanWindowsData\AutomationReports\ActiveTerrainBox_AcceptanceRetry_20260715_134509\index.json` is `Success`, errors `0`, exit `0`; all five fused regressions then passed with failed `0`, errors `0`, exit `0`. A second query-only target-candidacy control temporarily used raw bounds on that already-cooked component, placed the box centre outside its raw and naïve-expanded bounds but inside only its rotation-aware expansion, confirmed a real zero-length Chaos overlap, and selected the same key eight times (`RED_FUSED_ACTIVE_TERRAIN_BOX_BROADPHASE_PASS axis=2 side=1 margin_cm=5.0`). `D:\RedMMOTitanWindowsData\AutomationReports\ActiveTerrainBoxBroadphase_Acceptance_20260715_141718\index.json` is `Success`, errors `0`, exit `0`; its five-test fused regression also has failed `0`, errors `0`, exit `0`, and no fatal/assert/ensure. Protected hashes remain unchanged. This closes only the oriented-box query and target-candidacy prerequisite: production movement still sweeps its root sphere, not attached per-piece compound hull/wing boxes, and production box-overlap recovery remains open.
- **M02 rotated fitted-box MTD checkpoint (source/runtime, not re-packaged):** a real-Chaos query-only fixture embeds the same `1100 x 900 x 300 cm` rotated box `50.000 cm` into the cooked `+X/+Y` seam. Raw Chaos, direct PlanetGen, and `RedPlanetTerrainQuery` agree on one finite MTD/component/key; eight repeats preserve `50.006725 cm` depth and normal, and one bounded `52.006725 cm` correction clears the identical zero-length exact query. `RED_FUSED_ACTIVE_TERRAIN_BOX_MTD_PASS` reports `normal_dot_radial=0.999993`, key `(0,5,2)`, repeats `8`; `D:\RedMMOTitanWindowsData\AutomationReports\ActiveTerrainBoxMTD_QueryAcceptance_20260715_152542\index.json` is `Success`, errors `0`, exit `0`, and its five-test fused regression is also all `Success` with no fatal/assert/ensure. Compound egress remains `incomplete_retry`: a deterministic `100 cm` owner-interior MTD-plane sweep from the clear pose contacted adjacent +Y-face key `(2,0,3)` after `3.936044 cm`, `start_penetrating=0`, `depth=0` (`D:\RedMMOTitanWindowsData\AutomationReports\ActiveTerrainBoxMTD_OwnerwardAcceptance_20260715_151847\index.json`). That is a new multi-surface contact, not residual overlap; production movement remains root-sphere-only until per-piece contact arbitration/manifold handling and box recovery pass.
- **M02 adjacent-contact handoff checkpoint (source/runtime, not re-packaged):** the previously deferred contact is now deterministic query history. From the exact-clear MTD-corrected pose, raw Chaos, direct PlanetGen, and `RedPlanetTerrainQuery` all preserve primary key `(0,5,2)` and identify adjacent key `(2,0,3)` after `3.936044 cm` at `time=0.039360434`, non-penetrating with depth `0`; eight repeats preserve component, key, `FaceIndex`, time/distance, location/impact, and normal. `RED_FUSED_ACTIVE_TERRAIN_BOX_ADJACENT_CONTACT_PASS` reports `planes=2 retained_fraction=1.000000 repeats=8`; `D:\RedMMOTitanWindowsData\AutomationReports\ActiveTerrainBoxAdjacentContact_Acceptance_20260715_163349\index.json` is `Success`, and `D:\RedMMOTitanWindowsData\AutomationReports\ActiveTerrainBoxAdjacentContact_Regressions_20260715_163349\index.json` records all five fused tests as `Success` with no fatal/assert/ensure. The protected hashes are unchanged. This does not yet move a live fighter hull: next derive the actual Blueprint modular fighter `RuntimeHullCollision` fit (observed centre offset about `203.80,0,88.02 cm`, half-extents about `746.67,668.38,220.54 cm`) and verify one bounded live-piece translation/contact response before per-piece compound traversal is claimed.
- **M02 production-derived live fighter hull query checkpoint (source/runtime, not re-packaged):** the focused fixture loads and transiently spawns `/Game/RedMMO/Ships/BP_RedModularStarSparrow`, lets production `BeginPlay` fit `RuntimeHullCollision`, and independently reconstructs the same 29-mesh visible union. The live centre is `(203.80,0.00,88.02) cm` and half-extents are `(746.67,668.38,220.54) cm`, rather than the old hardcoded `(550,450,150) cm` query box. Raw Chaos, direct PlanetGen, and `RedPlanetTerrainQuery` preserve the full owned key `(0,5,2)` contact across eight repeats. In a valid nose-radial attitude, support math predicts `282.872101 cm` lead over the `260 cm` root sphere and runtime observes `284.000000 cm` (`79359.312500` versus `79643.312500 cm`). `D:\RedMMOTitanWindowsData\AutomationReports\ActiveTerrainLiveFighterHullQuery_RetryAcceptance_20260715_172926\index.json` is `Success`; `D:\RedMMOTitanWindowsData\AutomationReports\ActiveTerrainLiveFighterHullQuery_RetryRegressions_20260715_172926\index.json` records all five fused tests as `Success`, with no fatal/assert/ensure. The actor remains unmoved/transient, the Blueprint package stays clean, and all protected hashes are unchanged. This is query-only: the next gate is one bounded whole-actor translation/contact response driven by the live box; rotation, multi-piece compound response, box-overlap recovery, packaged-client, rendered traversal, and replication remain open.
- **M02 production-derived live fighter hull translation checkpoint (source/runtime, not re-packaged):** the automation-only response fixture now native-sweeps the actual registered `RuntimeHullCollision`, so its production `Vehicle` response mask participates. A closer generic `WorldDynamic` control contacts at `24.999882 cm` but is ignored; the transient `WorldStatic` control contacts at `49.999882 cm` and wins the probe-only native branch; after it is disabled, exact owned terrain wins at `99.985832 cm` on key `(0,5,2)`. One committed translation with `2 cm` pullback moves the actor root, fitted hull, and a visible modular mesh together by `97.985832 cm`, preserves actor/hull rotation and relative fit, and finishes exact-clear (`RED_FUSED_ACTIVE_TERRAIN_LIVE_FIGHTER_HULL_TRANSLATION_PASS`). `D:\RedMMOTitanWindowsData\AutomationReports\ActiveTerrainLiveFighterHullTranslation_First_20260715_144115\index.json` is `Success`; `D:\RedMMOTitanWindowsData\AutomationReports\ActiveTerrainLiveFighterHullTranslation_Regressions_20260715_144115\index.json` records all five fused tests as `Success`, with no fatal/assert/ensure. The Blueprint package and all protected hashes remain unchanged. This does not yet change playable movement: `URedShipMovementComponent` still sweeps only the root sphere/capsule. Next add a typed fit-ready translation-envelope pointer, fixed-rotation live-box native/exact preflight, and root movement; rotation, box-overlap recovery, multi-piece compound response, packaged client, rendered traversal, and replication remain open.
- **M02 production fitted-envelope movement checkpoint (source/runtime, not re-packaged):** playable source movement now receives the fitted `RuntimeHullCollision` only after the complete virtual fit succeeds; a non-virtual wrapper fixes the same binding for `ARedMiniFighter` while leaving the sphere root as `UpdatedComponent`. Supported fixed-rotation translation preflights the live box against its native `Vehicle` responses and exact owned PlanetGen terrain, applies a `2 cm` pullback, and moves only the root. Focused real-Chaos production `SafeMoveUpdatedComponent` calls ignored a closer `WorldDynamic` contact at `24.999882 cm`, moved `47.999882 cm` to the `WorldStatic` control, reset, then moved `97.985832 cm` to exact terrain key `(0,5,2)`; root exact/native counterfactuals were clear and all attached components remained synchronized (`RED_FUSED_ACTIVE_TERRAIN_PRODUCTION_FIGHTER_HULL_TRANSLATION_PASS`). `D:\RedMMOTitanWindowsData\AutomationReports\ProductionFittedHullTranslation_Focused_20260715_185444\index.json` is `Success`, and `D:\RedMMOTitanWindowsData\AutomationReports\ProductionFittedHullTranslation_Regressions_20260715_185621\index.json` contains all five fused tests as `Success`; fatal/assert/ensure scans are empty and all protected hashes plus the Sparrow Blueprint remain unchanged. Rotation-changing movement, fitted-box initial-overlap recovery, multi-piece body/wing arbitration, child hit-event dispatch, packaged-client behavior, rendered traversal, and replication remain open.
- **M02 production fitted-envelope initial-overlap checkpoint (source/runtime, not re-packaged):** fixed-rotation fitted-box movement now intercepts exact owned-terrain start overlap before the root-only resolver. A one-shot token revalidates the live box, bounds `Depth + 2 cm`, preflights root-native, box-native, and box-exact clearance, moves only the actor root once without sweep at unchanged rotation, post-validates synchronization, and lets `SafeMoveUpdatedComponent` retry the original request; native box overlap remains fail-closed/deferred. Focused real-Chaos PIE embedded the live Sparrow hull `50.000 cm`, applied one `52.013332 cm` correction, completed `25.000 cm` outward plus `100.000 cm` tangent movement with zero endpoint error, preserved the actor/root/hull/visible-mesh fit, repeated eight times, and ended clear (`RED_FUSED_ACTIVE_TERRAIN_PRODUCTION_FIGHTER_HULL_INITIAL_OVERLAP_PASS`). `D:\RedMMOTitanWindowsData\AutomationReports\ProductionFittedHullInitialOverlap_Focused_20260715_202645\index.json` is `Success`; `D:\RedMMOTitanWindowsData\AutomationReports\ProductionFittedHullInitialOverlap_Regressions_20260715_202645\index.json` contains all five fused tests as `Success`; exits are `0`, fatal/assert/ensure scans are empty, and the four protected world assets plus Sparrow Blueprint retain their hashes. Rotation-changing fitted motion/overlap, native box depenetration, multi-piece manifold response, passive fitted recovery, child event dispatch, packaged-client behavior, rendered traversal, and replication remain open.
- **M02 bounded production fitted-envelope angular-corridor checkpoint (source/runtime, not re-packaged):** playable Sparrow movement now preflights nonzero translation plus at most `6 degrees` of shortest-path rotation through at most three conservative `2 degree` fitted-box segments. The live off-centre child arc and root route are both covered; native queries preserve the `Vehicle` response mask, exact PlanetGen terrain is probed separately, and exact proxies honor both blocking and start-penetrating results. All contacts veto the complete transform without slide, while clear requests commit inside a revertible scoped move. Focused real-Chaos PIE requested `30 cm` plus `6 degrees`: a mid-arc-only `WorldStatic` control blocked eight deterministic repeats without moving actor/root/hull/farthest visible mesh, an earlier geometric `WorldDynamic` control remained ignored, `MoveWithPlanetCollision` did not slide, and eight clear repeats reached the exact full transforms. The hardened terrain-only control then disabled both native controls: actual start/end fitted boxes were exact-clear, the midpoint overlapped active owned chunk `(0,5,2)` by `0.152307 cm` inside a measured `1.521254 cm` support window, all native fitted-box poses and the complete native/exact root route remained clear, and eight production calls vetoed without moving. Changing only the query centre produced `NoMatchingPlanet` and committed the identical full transform, proving route-specific exact-terrain attribution (`exact=midarc_blocked exact_translation_cm=30.000 exact_counterfactual=commit`). The hardened build is `D:\RedMMOTitanWindowsData\BuildLogs\TitanEditor_ProductionAngularExactMidArc_Counterfactual_20260715.log`; `D:\RedMMOTitanWindowsData\AutomationReports\ProductionFittedHullAngularCorridor_Focused_20260715\index.json` is `Success`; `D:\RedMMOTitanWindowsData\AutomationReports\ProductionFittedHullAngularCorridor_Regressions_20260715\index.json` contains all five fused tests as `Success`; exits are `0`, fatal/assert/ensure/unhandled scans are empty, and all five protected hashes remain unchanged. Pure rotation, larger/hitch-substepped angular requests, rotating initial penetration, partial angular TOI/slide, native box depenetration, multi-piece body/wing arbitration and manifold response, passive fitted recovery, child hit/overlap events, a fresh packaged Windows client, rendered traversal, landing/exit, two-client authority/replication, rendered shoreline and visible-seam approval, actual foliage/PCG placement, and multiplayer validation remain open.
- **Author-controlled world building:** `URedWorldAssetPalette` records approved asset roles, biome tags, scale/slope/elevation ranges, PCG eligibility, and collision policy. `URedManualPlacementProtectionComponent` tags hand-authored POIs and supplies geodesic protection weights so future PCG can avoid them. The supplied ten-image mood board is translated in [`docs/ALIEN_WORLD_ART_BIBLE.md`](docs/ALIEN_WORLD_ART_BIBLE.md); pack review/hand placement is in [`docs/WORLD_AUTHORING_WORKFLOW.md`](docs/WORLD_AUTHORING_WORKFLOW.md); missing signature assets follow [`docs/MESHY_TRIPO_ALIEN_ASSET_PIPELINE.md`](docs/MESHY_TRIPO_ALIEN_ASSET_PIPELINE.md).
- **Isolated-map verification:** `Tools/create_50km_test_map.py` created `Content/RedMMO/Maps/RedPlanetGen_50km_Test.umap` idempotently without changing the production `RedPlanetGen.umap`. Strict verification log `D:\RedMMOTitanWindowsData\BuildLogs\Verify50kmTestMap_20260714_031230.log` contains `RED_50KM_TEST_MAP_READY` with `circumference_cm=5000000`, `radius_cm=795774.715`, and `gravity_radius_cm=1591549.431`.
- **Headless runtime smokes:** `D:\RedMMOTitanWindowsData\BuildLogs\Smoke50kmTestMap_20260714_031509.log` loaded the isolated map in the editor commandlet path, initialized the 50 km radius consistently across gameplay systems, configured eight atmosphere clouds, applied the SoStylized ocean, built 2,800 stars and 72 asteroids, bound moon fill, snapped the player to the surface, fitted shuttle/Sparrow collision, restored mini-fighter compact collision, and completed a clean shutdown. The corrected archive was then exercised through `D:\RedMMOTitanWindowsData\BuildLogs\PackagedSmoke50km_20260714.log` and `D:\RedMMOTitanWindowsData\BuildLogs\PackagedSmokeProduction_20260714.log`; both packaged processes exited `0`, loaded their requested map, shut down cleanly, and contain no fatal/assert/ensure matches.
- **Container proof:** `D:\RedMMOTitanWindowsData\BuildLogs\Package50km_20260714_035718.log.iostore.list.txt` contains `/Game/RedMMO/Maps/RedPlanetGen`, `/Game/RedMMO/Maps/RedPlanetGen_50km_Test`, and `/Game/BeamsPack/VFX/Beams/NS_BeamOnly_02`.
- **Honest boundary:** compilation, cook/stage/archive, container presence, automated packaged map-load smokes, M03 metadata/anchors, and deterministic geodesic hub-stamp authoring/runtime bootstrap now pass. M03 itself remains **in progress** until hands-on visual flatness plus traced player/vehicle seam traversal and no-invisible-wall acceptance pass; PCG biomes are also still open. Do not claim a playable/finished biome world, generated Meshy/Tripo assets, or user-approved traversal/streaming/visuals yet. Use `Windows\Launch_50km_Test.bat` for the isolated map while leaving the normal production-map launch untouched. The executable plan and remaining acceptance criteria are in [`docs/PLANET_50KM_IMPLEMENTATION_SPEC.md`](docs/PLANET_50KM_IMPLEMENTATION_SPEC.md), and fork details are in [`docs/PLANETGEN_PINNED_FORK.md`](docs/PLANETGEN_PINNED_FORK.md).

---

## 1. Mission / current product state

**What it is:** RedMMO Titan — UE **5.8.0** spherical **PlanetGen** MMO prototype. Player spawns on a ~6 km radius procedural planet (CLM `BP_CLMPlanet`), walks under **radial gravity**, uses a **Sci-Fi jetpack**, boards either project ship (`ARedShuttleBase` shuttle or `ARedShip` Sparrow), climbs through a ~1 km atmosphere shell into **space stars**, and (on Windows) can package for **Steam** multiplayer (App ID **480**).

**What “done” looks like:**

- Mars-like PlanetGen terrain has readable movement feedback from Sand FX while a later terrain pass can add the SoStylized demo's larger sculpted dune silhouette without sphere UV stripes.
- The current surface stays intentionally simple: PlanetGen desert terrain plus oceans, with procedural foliage/grass/rocks/cliffs/snow suppressed until deliberate hand placement or a later approved PCG pass.
- Colored High Five volumetric clouds, atmosphere→stars, replicated character/ship combat, and usable host/join UI coexist without breaking frame clarity.
- Ship engine fire is clearly outside nacelles; jetpack aim-while-shoot remains solid.

**Honest current state (2026-07-14 source and packaged validation):**

- Steering, atmosphere→stars, colored VDB clouds, and sky composition: **implemented / protect**.
- Ship plumes: **implemented / verified** — bright exhaust is visible outside both nacelles, activation no longer restarts every Tick, and the remote-client chase-camera pass is captured in `Saved/ShuttlePlume_MultiplayerPIE_20260712.png`.
- Sand movement FX: **implemented** — alternating decals, speed/scuff dust puffs, and local blowing sand from the attached Sand FX pack. This does not claim the whole planet now matches the SoStylized demo's sculpted dunes.
- Desert/ocean surface: **clean baseline implemented** — PlanetGen terrain and oceans remain; seven procedural foliage/grass/rock/cliff/snow dressing actors are disabled.
- Ships: **two saved, compiled project Blueprints plus the rear-bay mini fighter**, with replicated health, piloting, weapons, heat, movement, fitted runtime collision, two camera modes, landing handling, vacuum speed, and death/ejection. **B/V** controls the main shuttle, **F** controls the mini fighter, and **C** camera switching works in the packaged runtime.
- Player/loadout: **two rifles, Q/E Grapple/Slam, Tab swap UI, armor/ragdoll, Beams-pack Niagara tether, and Escape/F8 multiplayer lobby implemented in current source**. Grapple accepts world/player hits at least 1.5 m away; mock Inventory/Skills data is off. Crossed plasma splines are fallback-only, and the Beams Niagara asset is verified inside the corrected package container; the tether's hands-on visual/gameplay pass remains open.
- Rifle aim-while-shoot: **verified** standing, running, jetpack-airborne, and on the remote replicated client copy; physical barrel-to-shot dot remained `0.9999929` or better.
- Space/environment: the July 13 package proved the physical 0.9 km moon, randomized stars/asteroids, compact live 210×210 orbit radar, dark-side fill, eight evenly distributed atmosphere clouds, and clean desert/ocean baseline. The July 14 isolated-map smoke further proved the 2,800-star tiers, 72 asteroids, moon fill, eight clouds, SoStylized ocean/tangent repair, and shared 50 km surface radius; the corrected July 14 package now passes both isolated-test and production-map load/shutdown smokes. Hands-on visual approval remains pending.
- Planet authoring: **map/profile/cook/container/packaged-bootstrap verified** — the project-local PlanetGen fork, exact 50 km-circumference profile, deterministic 27-region blended metadata, asset-palette data, and manual-POI protection exist. `RedPlanetGen_50km_Test.umap` was created idempotently, reports `RED_50KM_TEST_MAP_READY`, is present in the package container, and cleanly loads/shuts down from the packaged executable. Biome content and hands-on traversal/streaming validation remain incomplete.
- Steam: local two-client replication is verified, and the final SIK package verified Steam initialization/authentication/relay plus lobby search/create/listen hosting. The invite/join/PvP flow is **not yet verified between two Steam accounts**.

---

## 2. Locked-good (DO NOT BREAK)

User-confirmed or repeatedly praised. Regression-check only — do **not** “improve” feel while fixing something else.

| System | Notes |
|---|---|
| **Ship control core** | RMB steers, MMB free-looks, LMB fires; the new cameras/audio/landing/vacuum tuning require user validation before they become locked-good |
| **Atmosphere → stars** | ~1 km shell; space fade reads beautiful |
| **Sky composition** | Eight evenly distributed atmosphere-bounded High Five VDB volumes; no spawn-point pileup, no star-dome leak onto ground, and 2D cloud cards removed |
| **Jetpack plumes + sound** | Cascade exhaust when not broken by later edits |
| **Shuttle plume presentation** | Bright plumes outside both nacelles; idempotent activation and mesh-bounds nozzle seating verified in remote-client PIE |
| **FocalRig rifle aim** | Relaxed carry + jog + jetpack selectors; actual barrel, flash, and projectile trajectory aligned |
| **Engines off on land/exit** | `EnsureEnginesOff` on UnPossess / exit |
| **Radial ship flight core** | WASD / Space / Ctrl / Shift boost / QE roll |
| **Sand movement FX** | Sand FX footprints, puffs/scuffs, and camera-local ambient blowing sand |
| **Clean desert/ocean baseline** | Terrain and oceans retained; procedural foliage, grass, rocks, cliffs, and snow intentionally suppressed |
| **Loadout/session UI** | 1/2 weapons, Q/E abilities, Tab loadout, F8 session browser; no vendor debug label |

### Hard “do not”

- Re-apply mesh-wide `MF_DesertSand` / world-XY desert MIs on PlanetGen **sphere chunks** → UV stripes.
- Respawn `RedCloudCard` / SM_Cloud / Plane sky cards.
- Put raw High Five `.vdb` files back in `Content/Cloudz_Hi5/VDB` beside the imported `.uasset` textures; UE 5.8 auto-import can assert on the class replacement.
- Freeze `Jump_Loop` for all airborne time (breaks combat aim arms).
- Add reload or magazine mechanics — weapon pacing is heat/cooldown/overheat only.
- Fight a boarded shuttle from GameMode Tick — **`ARedShuttleBase` owns flight**.
- Touch ship steering “for fun.”
- Claim oasis/sand fixed from log lines alone.

---

## 3. Open work (honest — not fixed)

Document as **OPEN**. Do not mark fixed until user re-verifies in PIE with eyes / `HighResShot`.

1. **Terrain authoring (held)** — No runtime biome scatter is active. When the user is ready, reshape continents, coastlines, ocean coverage, and elevation through [`docs/PLANET_TERRAIN_AUTHORING_PLAN.md`](docs/PLANET_TERRAIN_AUTHORING_PLAN.md). Do not force flat-Landscape UV materials onto spherical chunks.

2. **Client stabilization play pass** — **Unverified by the user.** Test B/V main-shuttle selection, F mini-fighter selection, both C camera framings, mini-fighter +X visual orientation and single-plume seating, collision/deck walking, landing and moon surface snap, engine audio comfort, vacuum speed, grapple, mining, distinct impacts, ragdoll, and occupied-ship destruction. Do not infer feel from smoke logs.

3. **Real Steam join** — Current eight-player session discovery/join/reconnect code requires a packaged test on two machines with two logged-in Steam accounts. NULL-OSS PIE is replication proof only.

4. **Mixamo jetpack hover anim** — User must supply; `Jump_Loop` is stand-in only for non-combat hover.

5. **Plugin compatibility** — use `Titan.uproject` as source of truth; disable a plugin only after a concrete UE 5.8 load/build failure identifies it.

---

## 4. Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  RedPlanetGen map + ARedGameMode                             │
│  CLM spawn · saved VDB clouds/water/ships · stars (space)    │
│  sphere-safe sand · rock/dune ensures · destroy cloud cards  │
└───────────────────────────┬─────────────────────────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        ▼                   ▼                   ▼
 ARedPlayerCharacter   Red ship classes    Planet (CLM)
 Trooper + jetpack     Shuttle + Sparrow   BP_CLMPlanet
 Sand FX + armor       health + heat       radius 600000
 2 rifles + Q/E/Tab    server weapons      basin attractor
 Plasma grapple        replicated pilots
        │
        ▼
 URedCharacterMovement + RedGravityBodies
 Radial gravity / surface snap / FindMeshPlanet
```

### Planet

- **CLM PlanetGen** plugin (`BP_CLMPlanet`): ProceduralMesh + async chunks, radius **600000** (6 km), `MaxMountainHeight=50000`.
- Spawn basin attractor ≈ direction `(0.288, 0.957, 0.024)`, walk radius ~608045. Pin sun / ship / props to live settle location.
- `RedGravity::FindMeshPlanet` detects CLM via reflection (no hard plugin link).

### Ships — `ARedShuttleBase` and `ARedShip`

- Project Blueprints: **`/Game/RedMMO/Ships/BP_RedPilotableShuttle`** and **`/Game/RedMMO/Ships/BP_RedModularStarSparrow`**; both are saved in `RedPlanetGen`.
- **B/V** enters or exits the main shuttle; **F** selects, boards, or exits the rear-bay mini fighter. Movement, pilot/occupant, health, heat/overheat, and death/ejection replicate. Destroying an occupied craft applies lethal occupant damage. Remote input is server-authoritative and stale/bounded; the player/shuttle controller handoff preserves the autonomous proxy and input context through board, exit, and reboard.
- Shuttle radial flight retains WASD / Space / Ctrl / Shift; hold **RMB+mouse** to steer, **MMB+mouse** to free-look, and **LMB** to fire. Muzzles are explicit native components with authored-marker fallback; the server computes muzzle position and forward aim.
- Auto `EnsureEnginesOn` on possess; `EnsureEnginesOff` on land / UnPossess / exit. Both ship classes now have stabilized collision/cameras/landing, revised engine audio, and a faster vacuum speed profile. Shuttle sound/attenuation caches use `TStrongObjectPtr` so garbage collection cannot invalidate them in flight; human validation of feel remains required.
- Engine FX: pack Niagara + Cascade backup (Metal). `SetEngineFXActive` is idempotent so the emitter age is not reset each Tick; backup nozzle seating derives from the mesh's forward bound plus 80 cm (clamped 320–900 cm). Official-MCP remote-client PIE verified bright plumes outside both nacelles.

### Player — `ARedPlayerCharacter`

- Creator-native Tall Female Trooper; **I** / **P** opens the character creator. Radial gravity uses `URedCharacterMovement`.
- Jetpack: `UChildActorComponent` → Sci-Fi Jetpack Master BP on `spine_03`.
- Cascade plumes on Exhaust_L/R; cyan mesh cones are hidden stand-ins.
- Double-Space jetpack; Shift = ground sprint + air boost.
- Hover pose stand-in: `A_ThirdPersonJump_Loop` until Mixamo hover is imported for non-combat flight.
- Combat aim: FocalRig is the final AnimGraph pass. Relaxed carry feeds looped rifle-jog and jetpack-air selectors, then `DefaultSlot`, upper-body blend, and FocalRig; firing montages remain intact.
- `ResolveWeaponAim` traces the reticle and resolves the exact accepted shot from the real muzzle. The same direction drives barrel pose, flash, replicated bolt, and remote aim.
- **1 / 2** select Rifle A and Rifle B. Each slot has independent authoritative heat, cooling, and overheat recovery; there is no reload.
- **Q / E** activate the replicated Grapple/Slam slots (defaults: Q Grapple, E Slam); **Tab** opens the native loadout and swaps the assignments. Cooldowns are authoritative and replicated to the UI.
- Grapple traces world geometry and live players and rejects only anchors closer than 1.5 m. Its primary visual is the Beams VFX Pack Niagara system `/Game/BeamsPack/VFX/Beams/NS_BeamOnly_02`, attached at `hand_r`, rotated from local +Z to the replicated anchor, and stretched through `User.BeamLength`. Two crossed spline ribbons using `/Game/RedMMO/Materials/MI_RedGrapplePlasma` are retained as fallback only; the old debug line/blue chain is gone.
- `UFootstepTrailComponent` spawns Sand FX footprint decals and step/scuff puffs. A local-only Niagara system attached to the camera supplies ambient blowing sand; dedicated servers do not render either effect.
- Replicated defense includes shield/health plus 100 armor with 35% post-shield mitigation. Ragdoll remains enabled.
- Vehicle entry/exit hardening coordinates controller possession, input state, and camera handoff with `ARedShuttleBase`; the remote client returns to its player autonomous proxy on exit and can immediately reboard.
- The sample `Source/Titan` pawn still contains GAS, but the live RedMMO trooper weapon/jetpack/heat pipeline is **not GAS-driven**; it is `ARedPlayerCharacter` + AnimBP + FocalRig.

### GameMode — `ARedGameMode`

- Standing spawn on CLM.
- `EnsureAtmosphereAndClouds`, `EnsureSpaceStarDomes` (space only — destroy on ground). Eight High Five heterogeneous volumes are evenly distributed around the atmosphere. `ARedSpaceScenery` now generates a scrambled 2,800-star field, randomized asteroids, the compact live 210×210 orbit radar, dark-side fill, the reachable physical moon (~0.9 km at ~60 km), and its additive glow; surface star visibility follows night state.
- `EnsureSoStylizedSandOnPlanetTerrain` keeps the sphere-safe desert base; visible movement feedback comes from Sand FX on the pawn. `ARedFoliageField` and the other procedural grass/rock/cliff/snow dressing actors remain in code/history but are disabled in the current runtime (seven actors suppressed).
- `EnsureOasisTerraformingPockets` no longer contributes procedural rocks or plant dressing to the current clean desert/ocean baseline. The saved water assets remain available; terrain and oceans are retained.
- `EnsureSparseCloudCards` — **destroys** leftover cards only (no respawn).

### Atmosphere / day-night — `ARedDayNight`

- Before rotating the SunSky directional light, the day/night path promotes the full attached parent chain—including a static `Scene` root—to Movable. The packaged smoke logged zero Sun-mobility warnings while retaining the atmosphere/day-night behavior.

### HUD

- `/Game/RedMMO/UI/WBP_VibeMMOHUD` — shield/health, abilities, jetpack stamina, the pack-authored sight, and bottom-right weapon cards.
- `Plugins/VibeMMOUIKit/.../VibeMMOHUDWidget.{h,cpp}` owns the retained sight, target-lock color response, rarity surfaces, active-weapon heat rail, cooling frame, and overheat pulse.
- `Source/RedMMO/RedHUD.{h,cpp}` owns the center target trace and projected enemy bars, then forwards target-lock alpha to the locally possessed `ARedPlayerCharacter`; it no longer draws a reticle or heat indicator.
- Weapon heat presentation reads the locally possessed `ARedPlayerCharacter`; it does not search for legacy `AWeaponFirer` actors.
- `URedSessionBrowserWidget`, opened from Escape -> Multiplayer / Lobby or **F8**, supplies Create / Find / Join Selected / Reconnect / Invite / Leave / Close without persistent HUD debug text. Active hosts do not auto-search.
- Escape Inventory/Skills pages expose live carried/loadout state or explicit empty slots only; mock/sample rows are disabled. **I** remains the intentional character-creator key.

### Networking / Steam

- `RedGameInstance` + **Steam Integration Kit v1.9**, App **480**. SIK is the sole Steam provider and owns the replacement OnlineSubsystemSteam and SteamSockets modules; `SteamSockets.SteamSocketsNetDriver` supplies NAT traversal and the Steam relay. The separate Epic stock plugins must remain disabled.
- Config: `Config/DefaultEngine.ini`; root `steam_appid.txt` = `480`.
- Sessions advertise at least **8 public connections** with RED product/build/type filtering. Travel and network failures clean up stale session membership; invites are accepted only when compatible.
- **F8** is the normal host/discover/join/reconnect path and exposes the host-only **Invite Friends** Steam-overlay action. `JoinHost <SteamID64>` is Development-only and disabled in Shipping.
- Server-authoritative firing/heat and `ReplicatedAimDirection` drive remote shots. Replicated combat-aim/jetpack state plus local AnimBP evaluation runs the FocalRig pose on every client.
- Two-client listen-server PIE proves gameplay replication. A packaged Steam host/join still requires two logged-in Steam clients; PIE used NULL OSS.
- Full Windows path: [`docs/WINDOWS_STEAM.md`](docs/WINDOWS_STEAM.md).

---

## 5. Key file paths (what each does)

### C++ — primary gameplay (`Source/RedMMO/`)

| Path | Role |
|---|---|
| `RedShuttleBase.{h,cpp}` | Pilotable shuttle, radial/vacuum flight, fitted collision, cockpit/chase cameras, landing/audio, `TStrongObjectPtr` GC-safe audio caches, replicated health/weapon heat, server muzzle fire, controller/input handoff, idempotent engines/plumes |
| `RedShip.{h,cpp}` | Modular Sparrow movement, fitted hull/deck collision, two cameras, landing/vacuum speed/audio, replicated health/pilot/input, server-authoritative weapon fire |
| `RedMiniFighter*.{h,cpp}` | Rear-bay modular mini fighter plus authoritative spawn/dock subsystem; dedicated F selection, +X forward contract, one rear plume, and compact collision after launch |
| `RedSpaceScenery.{h,cpp}` | Physical moon/glow, procedural 2,800-star field, randomized asteroids, compact live orbit radar, and dark-side fill |
| `RedMineableAsteroid.{h,cpp}` | Damageable/mineable randomized space asteroids |
| `RedFoliageField.{h,cpp}` | Historical procedural dressing implementation; suppressed in the current desert/ocean baseline |
| `RedSpaceDust.{h,cpp}` | Runtime-created space-dust HISM; avoids Blueprint default-subobject template mismatches |
| `RedPlayerCharacter.{h,cpp}` | Trooper, two rifles, Q/E+Tab loadout, Beams Niagara grapple with spline fallback, armor/ragdoll, Sand FX, jetpack, exact muzzle aim, authoritative heat, hardened vehicle boarding handoff |
| `RedShorelineWaveComponent.{h,cpp}` | Spherical-water tangent repair and traced SoStylized shoreline crest ribbon |
| `Planet/RedPlanetRegionService.{h,cpp}` | Exact 50 km profile constants, 27 seeded spherical-Fibonacci regions, great-circle lookup/blending, and tangent-map helpers |
| `WorldAuthoring/RedWorldAssetPalette.{h,cpp}` | Data-driven approved-asset roles, biome/range constraints, PCG eligibility, and collision policy |
| `WorldAuthoring/RedManualPlacementProtectionComponent.{h,cpp}` | Manual-POI tags plus geodesic protection radius/weights for later PCG exclusion |
| `FootstepTrailComponent.{h,cpp}` | Alternating gravity-aware footprint decals plus Sand FX puffs/scuffs |
| `RedGameMode.{h,cpp}` | Spawn, sphere-safe desert/ocean/atmosphere/space ensures; disables seven procedural dressing actors and evenly distributes eight clouds |
| `RedDayNight.{h,cpp}` | Day/night sun rotation; promotes the SunSky attachment chain to Movable before rotation |
| `RedCharacterMovement.{h,cpp}` | Radial gravity, surface snap |
| `RedGravityBodies.{h,cpp}` | CLM planet detection |
| `RedGameInstance.{h,cpp}` | Eight-player Steam host/search/join/reconnect/invite state machine; Development-only direct-ID fallback |
| `RedBolt.{h,cpp}` | Replicated per-weapon emissive tracer, collision, and distinct impact multicast |
| `RedHUD.{h,cpp}` | Center target trace, enemy projected bars, pack-sight forwarding, and F8 session-browser toggle |
| `RedSessionBrowserWidget.{h,cpp}` | Native Create / Find / Join / Reconnect / Invite / Leave lobby and session-state UI |
| `RedMMOEditorTools.{h,cpp}` | Editor/MCP helpers; generates/installs FocalRig and rifle movement selectors |
| `WeaponFirer.{h,cpp}` | Legacy/standalone weapon helper; not the live player HUD heat source |
| `RedMMO.Build.cs` | Runtime deps plus editor-only ControlRig, RigVM, and FocalRig tooling deps |

### Config / project

| Path | Role |
|---|---|
| `Titan.uproject` | UE 5.8 modules + plugins |
| `Config/DefaultEngine.ini` | Maps, Steam OSS (App 480), rendering |
| `Config/DefaultInput.ini` | 1/2 weapons, Q/E abilities, Tab loadout, V vehicle, I/P creator, ship inputs; legacy R/F/X ability mappings removed |
| `Config/DefaultGame.ini` | Game settings; always-cooks `/Game/BeamsPack/VFX/Beams` for the primary grapple cable |
| `steam_appid.txt` | `480` |

### Project-local plugin override (gitignored)

| Path | Role |
|---|---|
| `Plugins/PlanetGenPinned_1_4_0_RedMMO/` | Pinned PlanetGen 1.4.0 source fork; preserves `PlanetGen` module/content identity, leaves the engine install untouched, and exposes the opt-in 50 km test profile |

### Content (gitignored — paths inside editor)

| Path | Role |
|---|---|
| `/Game/RedMMO/Maps/RedPlanetGen` | **Play map** |
| `/Game/RedMMO/Maps/RedPlanetGen_50km_Test` | Isolated exact-50 km test map; strict profile, headless bootstrap, cook/container presence, and packaged runtime smoke verified |
| `/Game/RedMMO/Ships/BP_RedPilotableShuttle` | Project pilotable shuttle (`ARedShuttleBase`) |
| `/Game/RedMMO/Ships/BP_RedModularStarSparrow` | Project modular ship (`ARedShip`) |
| `/Game/Jet_Packs_Sci-Fi/...` | Jetpack + Cascade exhaust |
| `/Game/RedMMO/UI/WBP_VibeMMOHUD` | HUD widget |
| `/Game/RedMMO/Materials/MI_RedGrapplePlasma` | Cyan/violet animated plasma grapple material |
| `/Game/BeamsPack/VFX/Beams/NS_BeamOnly_02` | Primary continuous Niagara grapple cable; `/Game/RedMMO/Materials/MI_RedGrapplePlasma` splines are fallback-only |
| `/Game/Vefects/Sand_VFX/VFX/DynamicSandSurface/Materials/M_VFX_Footstep_Decal` | Sand footprint decal |
| `/Game/Vefects/Sand_VFX/VFX/LitSandPuff/NS_SandPuff_Small` | Footstep/scuff puff |
| `/Game/Vefects/Sand_VFX/VFX/AmbientSand/NS_Flying_Sand_Around_Camera` | Local camera blowing-sand system |
| `/Game/RedMMO/Environment/SM_RedOasisWaterPlane` | Project-owned SoStylized oasis-water mesh |
| `/Game/RedMMO/Materials/MI_RedOasisWater` | Clear-blue SoStylized oasis-water material instance |
| `/Game/RedMMO/Materials/Clouds/MI_RedCloud_{Violet,Cyan,Gold,Rose}` | Colored High Five heterogeneous-volume material instances |
| `/Game/Crosshair/UI_Material/MI_Crosshair38` | Imported UE 5.6 source material from the purchased Ultimate Stylized UI Crosshair Pack |
| `/Game/RedMMO/UI/Crosshair/MI_RedMMO_ArcSight` | UE 5.8-resaved project-local live sight based on pack design 38 |
| `/Game/RedMMO/Characters/CR_RedTrooperFocalAim` | Generated FocalRig Control Rig with explicit spine, arms, and virtual muzzle |
| `/Game/RedMMO/Characters/ABP_RedTrooperFemale` | Live female trooper AnimBP; stance, jog, jetpack, montage, upper-body, FocalRig |
| `/Game/RedMMO/Anims/Rifle/A_Rifle_Jog_Aim_Fwd` | Looped running-with-rifle aim pose |
| `/Game/RedMMO/Anims/Rifle/A_Rifle_Jetpack_Aim_Air` | Looped airborne/jetpack rifle aim pose |
| `/Game/SoStylized/Maps/Desert/Demonstration_Desert` | Reference Landscape dunes |
| `/Game/StylizedDesertOasis/` | Source assets retained for future hand placement; current procedural rock/plant dressing is suppressed |
| `MI_PlanetBiome_RED` / `M_Planet` | Sphere-safe biome materials |
| `SM_Desert_SandDune1/2` | Dune meshes |

### Tools

| Path | Role |
|---|---|
| `Tools/tiny_mcp.py` | Small MCP client helper |
| `Tools/fix_*.py` | Atmosphere / stars / sand MCP scripts |
| `Tools/verify_space_sky.py` | Space sky checks |
| `Tools/FabWatch/` | Fab free-asset watcher (optional) |

---

## 6. Mars environment implementation and boundaries

### Delivered on Windows

- The PlanetGen sphere keeps its sphere-safe desert material and oceans. Player movement adds alternating Sand FX footprint decals, small footstep puffs, larger speed/scuff dust, and local camera blowing sand.
- Runtime suppresses seven procedural foliage/grass/rock/cliff/snow dressing actors. Source meshes and saved water assets remain available for later deliberate hand placement, but they are not evidence of active current dressing.
- Eight reusable High Five `AHeterogeneousVolume` actors are evenly distributed around the atmosphere rather than concentrated at spawn.
- Runtime space presentation uses randomized stars/asteroids, a compact live 210×210 orbit radar, and dark-side fill. The saved map contains the pilotable shuttle and modular Sparrow alongside the retained terrain/ocean/cloud composition.
- Current source extends that baseline with a scrambled 2,800-star field, moon glow, surface stars gated by night, and a two-hour day/night cycle. `URedShorelineWaveComponent` repairs the spherical ocean tangent basis and creates traced SoStylized shoreline crests. The July 14 isolated-map editor smoke and corrected packaged smoke exercised this environment bootstrap and shut down cleanly; user-visible approval remains pending.
- The 50 km/27-region work is deliberately separate from the production map. `RedPlanetGen_50km_Test.umap` now exists and passes its strict profile plus headless bootstrap gates, while `RedPlanetGen.umap` remains unchanged. Its architecture, remaining acceptance gates, and rollback rules are documented in [`docs/PLANET_50KM_IMPLEMENTATION_SPEC.md`](docs/PLANET_50KM_IMPLEMENTATION_SPEC.md) and [`docs/PLANETGEN_PINNED_FORK.md`](docs/PLANETGEN_PINNED_FORK.md). Hand-authored asset control and mood-board direction are documented in [`docs/WORLD_AUTHORING_WORKFLOW.md`](docs/WORLD_AUTHORING_WORKFLOW.md), [`docs/ALIEN_WORLD_ART_BIBLE.md`](docs/ALIEN_WORLD_ART_BIBLE.md), and [`docs/MESHY_TRIPO_ALIEN_ASSET_PIPELINE.md`](docs/MESHY_TRIPO_ALIEN_ASSET_PIPELINE.md).

### Asset-source safety

The imported High Five sparse-volume `.uasset` files remain under `Content/Cloudz_Hi5/VDB`. Five same-named raw `.vdb` source files were moved to `Saved/SourceAssets/Cloudz_Hi5/VDB`; UE 5.8's auto-importer otherwise tried to replace `StaticSparseVolumeTexture` assets with `AnimatedSparseVolumeTexture` and asserted. The raw files are reimport sources only and are not runtime cook content.

### Remaining terrain boundary

The Sand FX pass solves movement feedback, not the large-scale terrain silhouette. `/Game/SoStylized/Maps/Desert/Demonstration_Desert` is a flat Landscape using Landscape UVs. Forcing its `MI_Landscape_Desert` / `MF_DesertSand` path onto PlanetGen sphere chunks caused dark/light UV stripes. Any later full-dune pass should use sphere-safe height noise, denser mesh silhouettes, or a purpose-built triplanar/spherical material—not a drop-in Landscape MI.

`ARedGameMode::EnsureOasisTerraformingPockets` remains a legacy-named helper, but its procedural output is suppressed in the current desert/ocean package. Do not re-enable it as part of unrelated work. The earlier continent/coastline/elevation workflow is documented in [`docs/PLANET_TERRAIN_AUTHORING_PLAN.md`](docs/PLANET_TERRAIN_AUTHORING_PLAN.md); the active isolated 50 km test architecture and its no-boundary 27-region model are in [`docs/PLANET_50KM_IMPLEMENTATION_SPEC.md`](docs/PLANET_50KM_IMPLEMENTATION_SPEC.md).

---

## 7. Verification protocol (mandatory)

Before claiming any visual or gameplay fix:

1. Rebuild if C++ changed; relaunch editor; compile the Control Rig and AnimBP through the official UE 5.8 MCP; warm shaders in PIE.
2. Console: `Slate.bAllowThrottling 0` (or focus loss freezes PIE ~0 fps).
3. For rifle changes, inspect live state through MCP in standing, moving, and jetpack-airborne aim:
   - `WeaponBarrelAimDot >= 0.9999`
   - `FocalAimWeight=1`; the appropriate `bRifleAimMoving` / `bRifleJetpackAim` selector is true
   - remote client copy receives aim/pose state and evaluates FocalRig locally
   - overheat prevents firing until authoritative heat cools to `25` or below; no reload input exists
   - each local player HUD shows the pack design 38 sight; target lock changes its channel colors, and heat stays on the active bottom-right rarity card
4. Capture **`HighResShot`** from the relevant camera for visual work:
   - Ship plumes → chase cam on nacelles with engines on
   - Sand FX → move/sprint across the basin and inspect alternating prints, puffs/scuffs, and local blowing sand
   - Surface → confirm only the intended desert terrain and oceans remain; no procedural foliage/grass/rock/cliff/snow dressing
   - Clouds → inspect all eight evenly distributed High Five atmosphere volumes and confirm no raw-VDB auto-import assertion
   - Ships → board both Blueprints, fire from authored muzzles, damage/eject, and inspect a remote client
   - Jetpack → double-Space → thrust + fire → aimed pose
5. Leave a concise, self-contained result and what remains for the user to judge visually; do not repeatedly ask for prompts or permission.
6. If user says they saw nothing → mark **failed**, not “spawned.”
7. **Do not fix unbroken systems** (locked-good table). Touch only the ticket you were asked to fix.

---

## 8. Mac MCP / build gotchas

```bash
UPROJ="/Users/alex/Documents/Unreal Projects/RedMMOTitan/Titan.uproject"
pkill -9 -f "Titan.uproject"; sleep 3
"/Users/Shared/Epic Games/UE_5.8/Engine/Build/BatchFiles/Mac/Build.sh" \
    TitanEditor Mac Development -project="$UPROJ" -waitmutex
```

- Clear `Saved/PackageRestoreData.json` if recovery modal blocks startup.
- Kill `CrashReportClient` squatters if editor won’t start cleanly.
- MCP on `:8000` — prefer small Python; avoid heavy factories (`FAppTime` ensure).
- Metal: prefer **Cascade** over GPU Niagara for visible FX on Mac.
- Work only in **RedMMOTitan / Titan.uproject**.

More Mac detail: [`HANDOVER.md`](HANDOVER.md) §5–10.

---

## 9. Windows / Steam pointer

Mac cannot reliably cook Win64 for distribution.

1. Clone https://github.com/addgamestudios-ops/RedMMOTitan.git  
2. Copy `Content/` + `Plugins/` from Mac drive  
3. UE **5.8.0** + VS 2022; use the checked-in `Titan.uproject` plugin set, keep MCP/FocalRig/SteamIntegrationKit enabled, and keep the separate Epic stock OnlineSubsystemSteam/SteamSockets entries disabled
4. Build `TitanEditor` Win64 → PIE on `RedPlanetGen`  
5. Package via UAT; place `steam_appid.txt` (`480`) beside exe  
6. SIK v1.9 Steam developer multiplayer is wired for App 480; this is not yet a RedMMOTitan Steam Library download

**Full steps:** [`docs/WINDOWS_STEAM.md`](docs/WINDOWS_STEAM.md) · short [`WINDOWS_BUILD.md`](WINDOWS_BUILD.md).

---

## 10. Content / Plugins reminder

| Transfer | How |
|---|---|
| `Source/`, `Config/`, docs, `Tools/`, `Titan.uproject`, `steam_appid.txt` | **GitHub** |
| `Content/` (~58 GB) | **Drive / cloud once** — not in git |
| `Plugins/` | **Drive / cloud once** + Marketplace install on Windows; FocalRig **1.3.5** is required for the generated aim rig |
| `Binaries/`, `Intermediate/`, `Saved/`, `DDC/` | Rebuild locally — do not copy Mac binaries to Windows |

---

## 11. Recommended next work (only when user asks)

1. **Two-account Steam host/invite/join/PvP test** (App 480) through the F8 browser. The final SIK package verifies Steam initialization/authentication/relay/lobby create/listen on one account, and local PIE verifies gameplay replication, but the cross-machine eight-player path remains open.
2. **True Steam Library deployment** once the owner provides the real Steamworks App ID, Win64 depot ID, test package/private branch entitlements, and Steamworks access. App 480 cannot produce a RedMMOTitan Library entry, and SIK cannot bypass Valve's publishing credentials.
3. **Hands-on stabilized-client pass** — use the current package to validate B/V main-shuttle selection, F mini-fighter selection, fighter +X visual orientation/single plume, fighter/shuttle collision, both C camera framings, landing/moon snap, replacement engine audio, vacuum acceleration, grapple targets, asteroid mining, weapon impacts, ragdoll, and occupant death.
4. **Finish the 50 km hands-on play gate** — strict isolated-map creation/profile, clean cook/archive, IoStore content checks, and both packaged map-load smokes pass; `Launch_50km_Test.bat` is included. Perform hands-on traversal/streaming/collision/visual tests next. Follow [`docs/PLANET_50KM_IMPLEMENTATION_SPEC.md`](docs/PLANET_50KM_IMPLEMENTATION_SPEC.md); do not edit the production map or treat the 27 metadata regions as separate levels/walls.
5. **Author-controlled biome sample** — after the test map passes, approve packs and hand-place one small hero biome using [`docs/WORLD_AUTHORING_WORKFLOW.md`](docs/WORLD_AUTHORING_WORKFLOW.md) and [`docs/ALIEN_WORLD_ART_BIBLE.md`](docs/ALIEN_WORLD_ART_BIBLE.md). Generate only missing signature silhouettes through [`docs/MESHY_TRIPO_ALIEN_ASSET_PIPELINE.md`](docs/MESHY_TRIPO_ALIEN_ASSET_PIPELINE.md); keep broad PCG dressing off until that sample is approved.
6. Import Mixamo jetpack hover when provided for non-combat flight.
7. Push `Source`/`Config` often and transfer updated `Content/` when map/art changes; transfer the gitignored pinned PlanetGen fork with project plugins, and keep raw High Five VDB sources in `Saved/SourceAssets`, not `Content`.

---

## 12. Hard-won gotchas (quick list)

1. Pawn settles at basin `(0.288, 0.957, 0.024)` — pin lighting/props there.
2. `Slate.bAllowThrottling 0` always in PIE.
3. Never override shared `Texture` on all `M_Planet` layers.
4. Clear `PackageRestoreData.json`; kill CrashReportClient squatters.
5. Don't GameMode-Tick-fight a boarded shuttle.
6. `PreviewPlanet()` + save = huge map; destroy preview chunks before save.
7. Additive `SpaceStarDome` on ground = grey grain sky — destroy on ground, spawn only in space.
8. Sand FX, terrain/oceans, eight evenly distributed VDB clouds, orbit radar, and dark-side fill are implemented; continent/heightmap redesign remains a held future pass.
9. `JoinHost` is a Development-only diagnostic fallback. Use F8 or Steam invites for normal play and never document it as a Shipping flow.
10. The July 14 isolated 50 km `.umap` exists and passes strict profile, headless runtime bootstrap, package-container presence, and packaged runtime smoke. Hands-on gameplay approval, finished biomes, and generated Meshy/Tripo assets do not yet exist.

---

*Bottom line for Codex: `D:\RedMMOTitanWindowsData\PackagedBuilds\Development_50KM_FOUNDATION_20260714_035718` is the current completed Development handoff. `D:\RedMMOTitanWindowsData\BuildLogs\Package50km_20260714_035718.log` ends `BUILD SUCCESSFUL` / `ExitCode=0`, and its IoStore listing proves the production map, isolated `RedPlanetGen_50km_Test` map, and Beams `NS_BeamOnly_02` asset are shipped. `D:\RedMMOTitanWindowsData\BuildLogs\PackagedSmoke50km_20260714.log` and `D:\RedMMOTitanWindowsData\BuildLogs\PackagedSmokeProduction_20260714.log` both exit `0`, load the requested maps, and contain no fatal/assert/ensure matches. The July 14 package includes the Beams-pack Niagara grapple as primary (crossed plasma splines fallback-only), procedural 2,800-star/moon-glow/night shoreline additions, the project-local PlanetGen fork, exact 50 km profile, deterministic 27-region metadata, and authoring/POI-protection types; the production map remains the normal launch and `Windows\Launch_50km_Test.bat` launches the isolated test. Hands-on visual/gameplay approval, finished biomes, and Meshy/Tripo-generated assets remain open. Escape exposes the Steam lobby, but no real two-account join/PvP or Steam Library SKU is claimed. Weapons use heat/overheat, never reload. Content and project plugins are not in git; transfer the pinned PlanetGen fork deliberately and keep raw High Five `.vdb` sources outside Content.*
