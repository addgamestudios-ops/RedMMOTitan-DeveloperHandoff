# Windows / Steam playability — RedMMOTitan

Mac development snapshot is saved on GitHub. **A Windows PC (or build farm) is required** to cook/package Win64 and run a Steam-playable build. Mac cannot reliably produce Windows game packages.

| Doc | Role |
|---|---|
| [`../README.md`](../README.md) | Clone, layout, Mac/Win build entry |
| [`../CODEX_HANDOVER.md`](../CODEX_HANDOVER.md) | Codex/agent brief (mission, locked-good, open bugs) |
| [`../HANDOVER.md`](../HANDOVER.md) | Full engineering truth (locked-good, open bugs, MCP, key files) |
| [`../HANDOVER_SHIP_PLUMES_TERRAIN.md`](../HANDOVER_SHIP_PLUMES_TERRAIN.md) | Historical plume / terrain / oasis investigation; defer to CODEX_HANDOVER for current Windows status |
| [`../WINDOWS_BUILD.md`](../WINDOWS_BUILD.md) | Short friend-facing package notes |

**Remote (verify):** `https://github.com/addgamestudios-ops/RedMMOTitan.git` · branch `main`

---

## What transfers from the Mac repo

| Transfer | How | Notes |
|---|---|---|
| `Source/`, `Config/`, `Titan.uproject`, `steam_appid.txt`, docs, `Tools/` | **GitHub** `git clone` / `git pull` | Always |
| `Content/` (~58 GB) | External SSD / cloud **once** | Gitignored |
| `Plugins/` (project plugins) | Same drive copy **once** | Gitignored; Marketplace plugins (PlanetGen, etc.) also install via Epic on Windows |
| `Binaries/Mac`, `Intermediate/`, `Saved/`, `DerivedDataCache/` | **Do not copy** | Windows rebuilds its own |

After clone + Content/Plugins drop-in, Windows builds `Binaries/Win64/` locally (`UnrealEditor-RedMMO.dll`, packaged `Titan.exe`).

The current Windows Content snapshot includes the Sand FX integration, project-owned SoStylized water and colored High Five cloud instances, both project ship Blueprints, and the upgraded UI assets. Raw High Five `.vdb` reimport sources are intentionally **not** runtime Content: they were moved to `Saved/SourceAssets/Cloudz_Hi5/VDB` after UE 5.8 auto-import asserted while trying to replace the imported sparse-volume texture class. Keep the imported `.uasset` files in `Content/Cloudz_Hi5/VDB`; do not copy the raw `.vdb` files back beside them.

---

## One-time Windows machine setup

1. **Unreal Engine 5.8.0** (exact — mismatch breaks Steam net / binary compatibility).
2. **Visual Studio 2022** with:
   - Game development with C++
   - Desktop development with C++
   - Windows 10/11 SDK
3. **Steam** client installed and logged in (use a **different** Steam account than the Mac host for two-player tests).
4. **Steam Integration Kit (SIK) v1.9** installed for UE 5.8. Development uses Spacewar App ID **480**; a real Steam Library release later requires the project's own Steamworks App ID, depot, branch/tester entitlements, and Steamworks access.

---

## Get the project on disk

```bat
git clone https://github.com/addgamestudios-ops/RedMMOTitan.git
cd RedMMOTitan
```

Copy from Mac drive into the clone root:

- `Content\`
- `Plugins\` (project-level)

Confirm present: `Titan.uproject`, `Source\`, `Config\`, `steam_appid.txt` (contents: `480`), `HANDOVER.md`.

### Keep the verified Windows plugin set

Use the checked-in `Titan.uproject` as the source of truth. Keep the official **ModelContextProtocol**, **FocalRig 1.3.5**, and **SteamIntegrationKit** enabled. SIK v1.9 is the sole Steam stack and supplies replacement OnlineSubsystemSteam and SteamSockets modules. Keep the separate Epic stock `OnlineSubsystemSteam` and `SteamSockets` plugin entries disabled; enabling both providers produces duplicate-module build ownership. Disable anything else only after a concrete UE 5.8 Windows load/build error identifies it.

---

## First Windows PIE (editor)

1. Right-click `Titan.uproject` → **Generate Visual Studio project files**.
2. Open the generated `.sln` **or** build from cmd:

```bat
"C:\Program Files\Epic Games\UE_5.8\Engine\Build\BatchFiles\Build.bat" ^
  TitanEditor Win64 Development ^
  -project="C:\Path\To\RedMMOTitan\Titan.uproject" -waitmutex
```

3. Launch editor (double-click `Titan.uproject`).
4. Open `/Game/RedMMO/Maps/RedPlanetGen` → Play.
5. Smoke-test:
   - Walk basin spawn (radial upright)
   - Move/sprint over sand: alternating footprint decals, step/scuff puffs, and local camera blowing sand should appear
   - Jetpack plumes + sound; thrust+fire FocalRig pose and barrel alignment
   - **1 / 2** swap rifles; **Q / E** activate Grapple/Slam; **Tab** opens and swaps the ability loadout
   - Confirm the grapple traces land/rocks and live players, accepts anchors at least 1.5 m away, and renders a pulsing plasma ribbon rather than the old blue chain/debug line
   - Use **B/V** to board or exit the main shuttle and **F** to select/board/exit the rear-bay mini fighter; hold RMB to steer, MMB to free-look, LMB to fire; verify health/heat/damage/ejection on a remote client. **I** intentionally remains the character creator.
   - Toggle both functional **C** cameras and verify fitted hull/deck collision, landing, revised ship audio, and faster vacuum travel. The current runtime reached chase view; final framing still needs human review.
   - Confirm the clean desert/ocean baseline: PlanetGen terrain and oceans remain, while procedural foliage, grass, rocks, cliffs, and snow are absent.
   - Inspect all eight evenly distributed atmosphere-bounded High Five VDB clouds, then climb through atmosphere to randomized stars/asteroids, the compact live **210×210** orbit radar, dark-side fill, and the physical moon.
   - Press **F6** in PIE and verify Create Game / Find Games / Join Selected / Reconnect / Invite / Leave / Close; Unreal Editor reserves F8 for Possess/Eject, while packaged builds use Escape -> Multiplayer / Lobby or **F8**. Confirm no vendor `customization window` label remains.
   - Confirm the verified shuttle plumes remain bright and outside both nacelles. The mini fighter is defined as +X forward with one rear plume and compact collision, but visual orientation/plume seating still needs the user's eyes.

Binary: `Binaries\Win64\UnrealEditor-RedMMO.dll` (not Mac `.dylib`).

---

## Packaged Win64 build

### Project Settings
- **Platforms → Windows**: Windows target enabled; Shipping or Development as needed.
- Maps to cook include `RedPlanetGen` (already GameDefaultMap).

### UAT (recommended)

```powershell
$project = (Resolve-Path .\Titan.uproject).Path
$archive = 'D:\RedMMOTitanWindowsData\PackagedBuilds\Development_' + (Get-Date -Format 'yyyyMMdd_HHmmss')
$cookDir = (Resolve-Path .\Content\RedMMO).Path
$packages = '-PACKAGE=/Game/Jet_Packs_Sci-Fi/Blueprints/Sci-Fi_Jetpack_Master_BP+/Game/Jet_Packs_Sci-Fi/Particles/Large_Jet_Exhaust_PS+/Game/Jet_Packs_Sci-Fi/Particles/Jet_Exhaust_PS+/Game/Jet_Packs_Sci-Fi/Audio/Jet_Engine_Light_Loop_Cue'

& 'D:\UE_5.8\Engine\Build\BatchFiles\RunUAT.bat' BuildCookRun `
  "-project=$project" -noP4 -utf8output -platform=Win64 `
  -clientconfig=Development -serverconfig=Development `
  -build -cook -stage -pak -iostore -compressed -prereqs -archive `
  "-archivedirectory=$archive" "-CookDir=$cookDir" `
  "-additionalcookeroptions=$packages"
```

Do not replace the allowlist with `-CookDir=Content\Jet_Packs_Sci-Fi`; unused legacy demo animations in that pack have missing skeleton dependencies and can crash the cook. `/Game/SciFi_Skills_Icon` is already covered by `DirectoriesToAlwaysCook`.

For store-like builds use `-clientconfig=Shipping`.

Output: `$archive\Windows\Titan.exe` plus the real game executable at `$archive\Windows\Titan\Binaries\Win64\Titan.exe`.

Place **`steam_appid.txt`** (single line `480`) beside both executable locations:

```powershell
Copy-Item .\steam_appid.txt "$archive\Windows\steam_appid.txt" -Force
Copy-Item .\steam_appid.txt "$archive\Windows\Titan\Binaries\Win64\steam_appid.txt" -Force
```

Current Development package: `D:\RedMMOTitanWindowsData\PackagedBuilds\Development_DESERT_STABILITY_20260713_181525\Windows` (launch `Titan.exe`). The editor/game builds, full clean cook/package, and packaged runtime smoke succeeded. Evidence: `D:\RedMMOTitanWindowsData\PackagedBuilds\Development_DESERT_STABILITY_20260713_181525\Windows\Titan\Saved\Logs\Titan.log`. Runtime disabled seven procedural foliage/grass/rock/cliff/snow dressing actors while retaining terrain and oceans, evenly distributed eight High Five atmosphere clouds, fitted three shuttle hull plus three deck collision pieces, and restored compact mini-fighter collision. It survived **3m46s** from shuttle board at 16:20:06 to mini-fighter launch at 16:23:52, toggled **C** into chase view, and produced no fatal/critical/assert/unhandled matches or crash folder. The shuttle's raw UObject sound/attenuation caches now use `TStrongObjectPtr`, fixing the garbage-collection crash path. The first normal launch can show a Windows Firewall dialog; approve the intended network profiles manually before testing. A real two-account client join/PvP test and final mini-fighter visual-orientation approval remain open.

Official-MCP two-client PIE previously verified a remote client boarding the shuttle as `ROLE_AutonomousProxy`, receiving the correct chase camera and bright plumes outside both nacelles, exiting with **V** back to a player `ROLE_AutonomousProxy`, and cleanly reboarding. Evidence: `Saved/ShuttlePlume_MultiplayerPIE_20260712.png`. Its earlier oasis-rock observations are historical and superseded by the current desert/ocean cleanup.

### Common cook/build failures

| Symptom | Fix |
|---|---|
| Missing VS / Windows SDK | Install VS 2022 Game + Desktop workloads |
| OpenSSL / libssl link errors | Match UE 5.8 prerequisites; repair Epic launcher prerequisites |
| Plugin compile errors | Use the checked-in `.uproject`; disable only the plugin named by the UE 5.8 Windows error |
| Missing assets | Confirm `Content\` fully copied (not a partial sync) |
| PlanetGen / Marketplace missing | Install matching UE 5.8 Marketplace plugins on Windows |
| UE asserts while auto-importing High Five clouds | Keep raw `.vdb` sources in `Saved/SourceAssets/Cloudz_Hi5/VDB`; only imported `.uasset` sparse-volume textures belong under Content |

---

## Steam multiplayer (SIK v1.9, developer App 480)

Config in `Config/DefaultEngine.ini`:

- `[OnlineSubsystem] DefaultPlatformService=Steam`
- `[OnlineSubsystemSteam] bEnabled=true`, `SteamDevAppId=480`; `[OnlineSubsystem] BuildIdOverride=20260712`
- SIK v1.9 as the sole Steam provider, including its replacement OnlineSubsystemSteam and SteamSockets modules
- `SteamSockets.SteamSocketsNetDriver` as GameNetDriver (NAT traversal + Steam relay), with `IpNetDriver` only as fallback

`steam_appid.txt` = `480` (Spacewar) for local/developer transport testing. It does not turn RedMMOTitan into a downloadable Steam Library title.

`URedGameInstance` advertises at least **8 public connections** and filters discovery/invites by the RED product/build/session type. Startup auto-match is disabled so separate clients do not silently become separate hosts after an empty search. SIK's lobby request uses the worldwide distance filter. It destroys stale sessions before transitions, keeps host/client state through travel, and cleans membership after network/travel failure. `URedSessionBrowserWidget` is the normal player-facing entry point.

### Playtest flow
1. Steam running + logged in on **both** machines (different accounts).
2. Launch matching packaged Development builds. Do not treat a two-client PIE run as Steam transport proof; PIE can use NULL OSS.
3. Open **Escape -> Multiplayer / Lobby** (or press **F8**). On one machine choose **Create Game**, then **Invite Friends** to open Steam's native invite overlay. The button is enabled only for the local host after the session is active.
4. The other player accepts the Steam invite. **Refresh** → select the RED session → **Join Selected** is the browser fallback; **Reconnect** retries the remembered session ID.
5. `HostGame` remains a Development console helper. `JoinHost <SteamID64>` is a strict **Development-only fallback** for a canonical unsigned 64-bit ID and is disabled in Shipping; do not document it as the normal or production join flow.

Current validation boundary: earlier SIK smoke verified Steam client/Game Server initialization, authentication, relay connectivity, compatible lobby search/create, eight-slot listen hosting, and port-7777 listening. The current package independently verifies clean map startup, desert/ocean cleanup, eight-cloud distribution, fitted shuttle collision, the GC-safe shuttle audio-cache path, C camera switching, and shuttle-to-mini-fighter launch. Local two-client PIE separately verified gameplay replication/UI and remote-client shuttle controller handoff. No real two-account invite/join/PvP run, Steam Library SKU, final mini-fighter visual-orientation approval, or full user controls pass is claimed.

### Offline friend-package integrity

Before considering reuse of existing Win64 target binaries, run the standalone
currency audit. It does not build or package anything:

```powershell
python Tools\audit_windows_target_currency.py `
  --project-root D:\RedMMOTitan `
  --output D:\RedMMOTitanWindowsData\Diagnostics\target_currency.json
```

The default gate returns exit code 10 unless **both** Titan and TitanEditor have
separate exact build-time proofs matching the current input manifest, receipt,
required project products, and preserved successful build log. Timestamp
cleanliness is diagnostic only. The package launcher intentionally still uses
`-build` and has no `-skipbuild` path; use `--allow-unverified-report` only to
write a diagnostic refusal report, never to authorize packaging.

Packages built with the 50 km checkpoints must use `-FreshCook`; iterative cooking cannot establish
current fused input provenance. `REDMMO_PACKAGE_READY.txt` records the matching workspace-source
hash observed at the pre-UAT and post-package endpoints as
`fused_prototype_source_sha256=4C84D7752C87854C70987ED9988C64C124C577FBE1DE3DEF3CC826F81B0B6284`.
The packaged fused verifier rejects older archives that contain only the map path: IoStore path
presence does not prove which source bytes were cooked. Endpoint equality does not prove continuous
file stability or decode the cooked payload. The ready marker is atomically published only after a
zero UAT exit record, and remains package-input provenance rather than runtime, visual, gameplay, or
multiplayer acceptance.

Create a friend ZIP only from an explicit successful UAT archive. Never point this command at an
old extracted friend folder or an inferred "latest" directory:

```powershell
python Tools\create_windows_friend_artifact.py `
  --packaged-root D:\path\Development_BUILD\Windows `
  --ready-marker D:\path\Development_BUILD\REDMMO_PACKAGE_READY.txt `
  --uat-log D:\RedMMOTitanWindowsData\BuildLogs\Package50km_TIMESTAMP.log `
  --quickstart-pdf D:\path\RedMMOTitan_Friend_Multiplayer_Quickstart.pdf `
  --output-dir D:\RedMMOTitanWindowsData\FriendBuilds `
  --label RedMMOTitan_Friend_PvP_TIMESTAMP `
  --configuration Development `
  --build-timestamp-utc 2026-07-19T00:00:00Z `
  --source-revision FULL_PACKAGING_TIME_GIT_REVISION
```

The builder omits Saved data, crash/log folders, debug symbols, and staging manifests; normalizes
both App ID locations from the canonical project file; generates truthful `BUILD_INFO.txt` and an
all-payload `BUILD_MANIFEST.json`; refuses to overwrite an existing label; and publishes only after
strict static verification passes.

Before sharing, verify the immutable ZIP rather than an extracted folder that may have accumulated
runtime changes:

```powershell
python Tools\verify_windows_multiplayer_artifact.py `
  --zip D:\path\RedMMOTitan_Friend.zip `
  --sha256-sidecar D:\path\RedMMOTitan_Friend.zip.sha256 `
  --report D:\RedMMOTitanWindowsData\Diagnostics\friend_artifact_report.json
```

For newly generated artifacts, add `--strict` and include `BUILD_MANIFEST.json` with build
provenance and a SHA-256 for every packaged payload. A static pass proves ZIP identity, safe paths,
required executables/guides, App ID files, content containers, and the declared game-executable
hash. It deliberately reports runtime acceptance as `UNVERIFIED`; it does not prove launch, Steam
transport, host/find/join, replication, respawn, combat, or craft possession.

### True RedMMOTitan Steam Library build (not yet available)

App ID 480 supports this developer transport test, but it cannot provide a RedMMOTitan entry that friends install and launch from their Steam Libraries. That distribution flow requires Valve-side project credentials and publishing state that no Unreal plugin can create or bypass:

1. Register/obtain the real RedMMOTitan **Steamworks App ID** and a Win64 **depot ID**.
2. Grant the test accounts access through the correct Steamworks package/private branch.
3. Replace `480` in `steam_appid.txt`, `SteamAppId`, `SteamDevAppId`, and shipping configuration.
4. Upload the packaged Win64 depot with SteamPipe and set its launch option to `Titan.exe`.
5. Publish the build to the authorized private test branch, then install it from each tester's Steam Library.

SIK's [One Click Package and Deploy](https://sik.betide.studio/gettingstarted/OneClickPackageAndDeploy) requires the project's own App/depot configuration and explicitly cannot deploy App ID 480. Do not put Steam credentials in project files or logs; use the repository's interactive `Build/SteamPipe` workflow once the real IDs and account access are available.

---

## Cross-machine workflow

- **Do not expect** Mac to cook Win64 Shipping for distribution.
- Push `Source`/`Config`/docs to GitHub from Mac; Windows `git pull` + rebuild.
- Re-copy `Content/` only when art/maps change materially.
- Before claiming visual fixes on either machine: **HighResShot** + user eyes (see HANDOVER verification protocol).

---

## Checklist — first Windows PIE

- [ ] UE 5.8.0 + VS 2022 installed
- [ ] Repo cloned from `https://github.com/addgamestudios-ops/RedMMOTitan.git`
- [ ] `Content\` + `Plugins\` present
- [ ] Checked-in UE 5.8 plugin set retained; disable only a plugin named by a concrete load/build error
- [ ] `TitanEditor` Win64 Development builds
- [ ] PIE on `RedPlanetGen`: walk / Sand FX / jetpack / main shuttle / mini fighter / eight distributed colored clouds / desert-ocean baseline / randomized space / moon / live orbit radar
- [ ] 1/2 weapons, Q/E abilities, Tab loadout, F8 browser, armor/ragdoll, and plasma grapple smoke-tested
- [ ] No palm actors and no vendor `customization window` label
- [ ] Verify B/V main-shuttle board/exit, F mini-fighter board/exit, both C camera framings, mini-fighter +X orientation/one plume, collision/landing/audio/vacuum speed, grapple, mining, distinct impacts, ragdoll, and occupant death with human eyes/input
- [ ] Note open boundaries: continent/heightmap redesign is held, real packaged two-machine/two-account Steam join is unproved, and real Steamworks App/depot/package IDs remain unavailable

## Checklist — first packaged + Steam

- [ ] `BuildCookRun` Win64 succeeds → `Titan.exe`
- [ ] `steam_appid.txt` (`480`) beside exe
- [ ] Steam client running; launch exe
- [ ] F8 Host → Refresh → Join Selected with a second Steam account (Mac or Win)
- [ ] At least 8 public connections advertised; compatible session metadata shown; Reconnect works
- [ ] Send last ~40 log lines on any failure back to Mac engineer

---

## Open issues for the next AI on Windows

Do **not** start a long visual rewrite unless the user asks. Current boundaries:

1. Procedural foliage/grass/rocks/cliffs/snow are intentionally suppressed. Future continents, coastlines, ocean coverage, and elevation work follows [`PLANET_TERRAIN_AUTHORING_PLAN.md`](PLANET_TERRAIN_AUTHORING_PLAN.md); it is not implemented in this package.
2. The new ship/fighter collision, camera framing, landing, audio, vacuum acceleration, moon snap, randomized asteroids, and grapple changes need a user visual/controls pass. The mini fighter's +X/one-plume contract and successful launch log do not prove that its art looks correctly oriented.
3. The eight-player F8 session path needs a real packaged two-machine/two-account Steam test. A true Steam Library SKU additionally waits for real Steamworks App/depot/package IDs and onboarding.
4. Protect the verified shuttle plumes/controller handoff, GC-safe audio cache, clean desert/ocean baseline, eight evenly distributed High Five clouds, compact 210×210 orbit radar, dark-side fill, both replicated ships, jetpack/FocalRig aim, heat-only weapons, and Q/E+Tab/F8 UI.

---

*Mac keeps the source of truth on GitHub. Windows is the package/Steam machine + optional next visual pass.*
