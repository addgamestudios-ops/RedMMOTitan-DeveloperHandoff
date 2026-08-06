# Building the Windows copy of RedMMOTitan (for your friend)

Full engineering checklist (PIE, packaging, SteamPipe, what to copy): **[`docs/WINDOWS_STEAM.md`](docs/WINDOWS_STEAM.md)**.  
Project entry: **[`README.md`](README.md)** · developer handoff: **[`Docs/DeveloperHandoff/START_HERE.md`](Docs/DeveloperHandoff/START_HERE.md)** · engineering notes: **[`HANDOVER.md`](HANDOVER.md)**.

Your Mac makes the Mac copy; this makes the **Windows `.exe`** your friend runs. Both must be built from
**Unreal Engine 5.8.0** (exact match — a different 5.8.x will cause "connection refused"). Steam then
bridges Mac-host ↔ Windows-client over its relay under App ID **480**.

---

## 1. Install on the Windows PC (one-time)

- **Unreal Engine 5.8.0** — via the Epic Games Launcher → Unreal Engine → Library → install **5.8.0**.
- **Visual Studio 2022** (Community is free) with these workloads ticked in the installer:
  - **Game development with C++**
  - **Desktop development with C++**
  (This project has custom C++, so it must compile — VS is required, not optional.)
- **Steam** installed + logged in (a *different* Steam account than your Mac's — you can't be signed in
  to the same account on both).

## 2. Get the project onto the Windows PC — GitHub for code, drive for the art

The code lives on GitHub; the big art files travel once by drive.

**a) Clone the code** (Command Prompt):
```
git clone https://github.com/addgamestudios-ops/RedMMOTitan.git
```
**b) Drop in the two heavy folders** (they're too big for git, so copy them once from the Mac via an
external SSD or a cloud link) into the cloned `RedMMOTitan\` folder:
- **`Content\`** (~57 GB)
- **`Plugins\`**

After that the folder has `Source\ Config\ Content\ Plugins\ Titan.uproject steam_appid.txt` — ready to build.

**When I fix a build error:** just `git pull` in that folder to get the new code, then re-run the build
(step 4) — no re-copying. `Content` / `Plugins` only need to be copied the one time.

## 3. Keep the verified Windows plugin set

Use the checked-in `Titan.uproject` as the source of truth. Keep the official **ModelContextProtocol**, **FocalRig 1.3.5**, and **SteamIntegrationKit** enabled. SIK v1.9 is the sole Steam stack and supplies its own replacement OnlineSubsystemSteam and SteamSockets modules; keep the separate Epic stock `OnlineSubsystemSteam` and `SteamSockets` plugin entries disabled to avoid duplicate-module ownership. Disable anything else only when the Windows editor/build log identifies a concrete incompatibility.

Keep the imported High Five cloud `.uasset` files under `Content\Cloudz_Hi5\VDB`, but keep their five raw `.vdb` reimport sources under `Saved\SourceAssets\Cloudz_Hi5\VDB`. Putting the raw files back beside the imported assets can make UE 5.8 auto-import attempt an incompatible sparse-volume texture class replacement and assert.

## 4. Generate project files + build

- Right-click `Titan.uproject` → **Generate Visual Studio project files**.
- Then package from **PowerShell**. The explicit four-package jetpack allowlist is required because cooking the whole legacy jetpack directory can crash on orphaned demo animations:

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

First run compiles ~10 C++ modules + cooks 57 GB of content — **expect 30–90 minutes**. That first
compile is the one risky step; if it stops with an error, that's normal for a first cross-platform build —
**copy the last ~40 lines of the output and send them to me** and I'll fix the source, you re-pull `Source/`
and re-run (much faster the second time).

## 5. Output + Steam file

Result: `$archive\Windows\` containing `Titan.exe` and its files. Copy the checked-in `steam_appid.txt` (single line `480`) beside both launch paths:

```powershell
Copy-Item .\steam_appid.txt "$archive\Windows\steam_appid.txt" -Force
Copy-Item .\steam_appid.txt "$archive\Windows\Titan\Binaries\Win64\steam_appid.txt" -Force
```

Current Development package on the Windows build machine: `D:\RedMMOTitanWindowsData\PackagedBuilds\Development_DESERT_STABILITY_20260713_181525\Windows` (launch `Titan.exe`). The editor/game builds, full clean cook/package, and packaged runtime smoke succeeded. Evidence: `D:\RedMMOTitanWindowsData\PackagedBuilds\Development_DESERT_STABILITY_20260713_181525\Windows\Titan\Saved\Logs\Titan.log`. Runtime disabled seven procedural foliage/grass/rock/cliff/snow dressing actors while retaining terrain and oceans, evenly distributed eight High Five atmosphere clouds, fitted the shuttle's three hull plus three deck collision pieces, and launched the compact-collision mini fighter. The process survived **3m46s** from shuttle boarding to mini-fighter launch, toggled **C** into chase view, and produced no fatal/critical/assert/unhandled matches or crash folder. The shuttle's raw UObject audio/attenuation caches now use `TStrongObjectPtr` so garbage collection cannot invalidate them during flight. The first normal launch can show a Windows Firewall permission dialog; approve the intended network profiles manually. This smoke does not prove the mini fighter's final visual orientation or a real two-account Steam client join/PvP run.

That folder is the whole game — zip it and it's your friend's copy.

## Current controls and content to smoke-test

- **1 / 2:** swap the two replicated rifles. Weapons use independent heat/overheat; there is no reload.
- **Q / E:** Grapple and Slam by default. **Tab:** open the loadout and swap those assignments. Grapple traces world geometry and players and accepts anchors at least 1.5 m away.
- **B / V:** enter or exit the main shuttle. **F:** select, board, or exit the rear-bay mini fighter. **I** intentionally remains the character creator.
- **C:** switch the functional cockpit/chase cameras; the current packaged runtime reached chase view. In the shuttle, **RMB** steers, **MMB** free-looks, and **LMB** fires. Confirm framing with human eyes, revised ship audio, fitted hull/deck collision, and faster vacuum travel.
- **L (while piloting):** toggle optional low-altitude landing assist on either craft. It aligns to traced terrain and eases into a settled touchdown; press lift/Space to disengage for takeoff, or leave it off for manual combat landings.
- **Escape → Multiplayer / Lobby** or **F8:** open the native lobby in a packaged build: Create Game, Find Games, Join Selected, Reconnect, **Invite Friends**, Leave Game, Close. Startup no longer silently auto-hosts after an empty search; the host explicitly chooses Create Game and the client chooses Find Games. Discovery uses Steam's worldwide lobby-distance filter. Use **F6** in PIE because Unreal Editor reserves F8 for Possess/Eject. Sessions advertise at least **8 public connections**.
- Walk/sprint to check Sand FX footprints, puffs/scuffs, and local blowing sand. Confirm the clean desert/ocean baseline has no procedural foliage, grass, rocks, cliffs, or snow, and inspect all eight evenly distributed High Five atmosphere clouds.
- In space, confirm randomized stars/asteroids, the compact live **210×210** orbit radar, dark-side fill, and physical surface snapping on the roughly 0.9 km moon at about 60 km.
- Damage-test both distinct weapon impact profiles, player ragdoll, and occupant death when a piloted ship is destroyed. Player menus must show live/empty state only; mock inventory/skills rows are disabled.
- Smoke both **C** camera modes and confirm the first-person view is inside the cockpit. The mini fighter's runtime contract is **+X forward**, one rear plume, and compact collision; verify its final visual orientation and plume seating through steering, lift-vector rotation, and boost.
- A two-client PIE run checks replication/UI, not Steam transport. A real join requires two machines and two logged-in Steam accounts.

Future continent, coastline, ocean-coverage, and elevation changes are held in [`docs/PLANET_TERRAIN_AUTHORING_PLAN.md`](docs/PLANET_TERRAIN_AUTHORING_PLAN.md); they are not part of this package.

---

## What to send back to me
- If the build **fails**: the last ~40 lines of the error output (I fix the code, you re-run).
- If it **succeeds**: just tell me — the `.exe` folder goes to your friend, not me. I'll have your Mac copy
  ready, and we do the host → invite → join test.

## Reminder on how the test actually works

This App ID 480 package uses Steam transport for developer testing, but it is **not** a RedMMOTitan entry downloadable from each friend's Steam Library. A real Library **Play** button requires a RedMMOTitan Steamworks App ID, Win64 depot ID, uploaded build, private branch/tester entitlements, and Steamworks account access. SIK cannot create or bypass those Valve-owned publishing credentials, and its One Click Deploy flow does not support App ID 480.

Both people launch matching packaged builds with **Steam running** under different accounts. Press **F8**: one player chooses **Host**; the other chooses **Refresh**, selects the RED session, and chooses **Join Selected**. Compatible Steam-overlay invites also work. `HostGame` is only a Development console helper, and `JoinHost <SteamID64>` is a strict Development-only fallback that is disabled in Shipping—not the normal player flow.
