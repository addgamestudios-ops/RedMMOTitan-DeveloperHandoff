# Networking / Replication / Multiplayer / PvP — programmer start

**Audience:** gameplay / netcode programmer (listen-server, replication, PvP).  
**Ukrainian:** [NETWORKING_PVP_UK.md](./NETWORKING_PVP_UK.md)  
**PPG/PlanetGen:** not required for first netcode PIE — use `TitanFundamentals.uproject` + ThirdPersonMap.

---

## Current architecture (honest)

| Layer | What exists | Proven? |
|---|---|---|
| **Topology** | Unreal **listen-server** (host is also a player). Dedicated server not accepted. | PIE 2-client listen-server used historically for aim/jetpack/fire replication |
| **Transport** | **Steam Integration Kit (SIK) v1.9** as sole Steam stack (replacement OnlineSubsystemSteam + SteamSockets). Epic stock OSS Steam plugins **disabled**. Dev App ID **480** (Spacewar) via `steam_appid.txt` | Packaged smokes: Steam auth/relay + single-account host lifecycle. **Real two-account Steam join/PvP not proven** |
| **Session UI** | Escape → Multiplayer/Lobby; **F8** runtime / **F6** in PIE (editor owns F8). Create / Find / Join / Reconnect / Invite / Leave. Sessions advertise ≥8 players. No silent auto-host after empty search | UI + host lifecycle smoke; friend join open |
| **Authority** | Server-authoritative weapons heat/overheat, bolt spawn, ship pilot/weapons, damage; aim direction + jetpack flags replicated | Two-client listen-server PIE verified aim/jetpack/fire/heat (NULL OSS path — **gameplay replication, not Steam transport**) |
| **GameState** | Celestial / PPG frame producers and registry work exist; real 1S/2C late-join transport + radar consumers **open** (M05) | Single-process ordering evidence ≠ multiplayer acceptance |
| **PvP** | `bIsEnemy`, health/shield/armor, downed, grapple-on-player pull, lethal ragdoll / ship death paths in character/ship code | Not a finished PvP mode; no ranked/matchmaking |

---

## Key classes (start here)

| System | Primary files | Net notes |
|---|---|---|
| Player / jetpack / aim / weapons | `Source/RedMMO/RedPlayerCharacter.h/.cpp` | Large `DOREPLIFETIME` block: Health/Shield/Armor/Fuel, aim, weapon heat, jetpack flags, abilities, grapple/slam |
| Movement | `RedCharacterMovement.*` | Radial gravity / planet movement — test carefully under listen-server |
| Projectiles | `RedBolt.*`, `WeaponFirer.*` | Server-spawned bolts; presentation vs authority |
| Ship (StarSparrow) | `RedShip.*`, `RedShipMovementComponent.*` | Replicated Health, WeaponHeat, Pilot, landing flags |
| Shuttle | `RedShuttleBase.*` | Related craft occupancy / audio GC fix history |
| Sessions / Steam | `RedGameInstance.*`, `RedSessionBrowserWidget.*`, `RedHUD.*` (lobby open) | SIK session browser; App 480 |
| Pause / lobby entry | `RedPauseMenuWidget.*` | Escape menu Multiplayer row |
| GameMode | `RedGameMode.*`, clean project `RedPPGGameplayGameMode.cpp` | Default modes differ Titan vs clean RedMMO |
| Celestial / MP consumers | `RedCelestialFrameRegistry.*`, GameState helpers | M05 still open for real 1S/2C |
| Focused MP tests | `Source/RedMMO/Tests/RedDEF0003TwoClientPIETests.cpp` | Listen-server count helpers — extend, don’t treat as full Steam proof |

**Anim / aim presentation (protect run):** `Content/RedMMO/Characters/ABP_RedTrooperFemale` — **do not casually rewrite run/locomotion**. Aim/jetpack pose work should stay additive / parallel. FocalRig marketplace absent → ControlRig substitute in `RedMMOEditorTools`.

---

## Where to start (recommended order)

1. **Day 1 — no Fab planets:** Open `TitanFundamentals.uproject`, build TitanEditor, PIE ThirdPersonMap. Confirm compile with PlanetGen/PPG/FocalRig/WorldGen off.
2. **Day 1–2 — listen-server gameplay replication:** Editor → Play → Number of Players = 2, Net Mode = Play As Listen Server. Validate move/aim/fire/jetpack replication between windows (NULL OSS is fine for this gate).
3. **Day 2–3 — PvP damage loop:** Trace Health/Shield damage, `bIsEnemy`, downed, bolt hit authority in `RedPlayerCharacter` / `RedBolt`. Add a minimal deathmatch spawn/score only after replication is stable.
4. **When ready for Steam:** Enable/copy `Plugins/SteamIntegrationKit`, keep Epic OSS Steam **disabled**, Steam client logged in, App **480**. Host on machine A, join on machine B with **different** Steam accounts. Do not claim success from single-account smoke.
5. **Defer:** PPG home world, PlanetGen maps, fused terrain, final art — not blockers for netcode fundamentals.

---

## Known gaps (net / MP)

- Real **1 server + 2 clients** Steam transport (initial/update/stale/late-join) unaccepted  
- Dedicated server, persistence, matchmaking, Steam App ID beyond 480  
- Radar/minimap multiplayer consumers  
- Warp / interplanetary replication  
- Packaged two-account PvP  
- Clean RedMMO vs Titan session parity  

---

## Protected items

- **Running animation** / locomotion single-node guard on trooper ABP  
- R92 package tree identity; fused 27/6 authoring hashes  
- Do not enable both SIK and Epic OnlineSubsystemSteam together  

---

## Fab / plugins for this track

See [FAB_MARKETPLACE_INVENTORY.md](./FAB_MARKETPLACE_INVENTORY.md).

| Need | Plugin |
|---|---|
| Netcode PIE fundamentals | **None** from Fab |
| Steam friend sessions | **SteamIntegrationKit** (project plugin; ~297 MB — may need copy from owner machine) |
| Planetary maps | PPG / PlanetGen — **optional later** |
