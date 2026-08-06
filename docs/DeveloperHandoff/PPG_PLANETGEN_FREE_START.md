# PPG / PlanetGen–free start (required for developer onboarding)

**Goal:** The developer must be able to **build and PIE fundamentals without installing PPG or PlanetGen**.

---

## Verdict (2026-08-07)

| Path | Needs PPG? | Needs PlanetGen? | Use for |
|---|---|---|---|
| **`TitanFundamentals.uproject` + ThirdPersonMap** | **No** | **No** | Immediate compile, controls, weapons, HUD, C++ fundamentals |
| `Titan.uproject` + `RedPlanetGen` | No (PPG not in Titan) | **Yes** (enabled; home map is PlanetGen) | Full Titan planetary prototype |
| Clean `RedMMO.uproject` + `RedMMO_PPG_HomeWorld` | **Yes** | Reserved / separate | Accepted R92 planetary baseline |

**Feasible in this handoff:** Yes — use **`TitanFundamentals.uproject`**.  
PlanetGen and PPG are **optional** for the fundamentals baseline. Full planet maps remain plugin-dependent and are documented below.

---

## How to start without PPG / PlanetGen

1. Open **`TitanFundamentals.uproject`** (not `RedMMO.uproject`, not full planetary maps).
2. Confirm plugins:
   - `PlanetGen` → **Enabled: false**
   - `WorldGen` → **Enabled: false**
   - `FocalRig` → **Enabled: false** (stock ControlRig substitute already in source)
   - No `PPG` entry in this uproject
3. Editor / game default map: `/Game/ThirdPerson/Maps/ThirdPersonMap`
4. Build `TitanEditor` Win64 Development → PIE.

### Shims already in project source

| Shim | Path | Behavior when plugin/fork missing |
|---|---|---|
| PlanetGen query compat | `Source/RedMMO/RedPlanetGenCompat.h/.cpp` | Forwards to fork APIs if headers exist; else chunk/radial substitutes so **TitanEditor links** |
| FocalRig optional | `Source/RedMMO/RedMMO.Build.cs` + `RedMMOEditorTools` | `REDMMO_WITH_MARKETPLACE_FOCALRIG=0` → stock ControlRig `AimItem` substitute |
| WorldGen | `Titan.uproject` / Fundamentals | Disabled; no hard module dependency |

### What still needs plugins (optional later)

| Work | Required |
|---|---|
| Clean home world `RedMMO_PPG_HomeWorld`, ProfileV1 biomes, native PPG water/chunks | **PPG** marketplace plugin |
| Titan `RedPlanetGen` / 50 km PlanetGen maps, ACLMPlanet streaming | **PlanetGen** (engine Marketplace 1.7 and/or project pin) |
| Exact fork terrain stamp / MacroHeightfield APIs | `Plugins/PlanetGenPinned_*` (absent on live tree; shims cover link) |

---

## Fallback maps

| Map | Plugin need | Notes |
|---|---|---|
| `/Game/ThirdPerson/Maps/ThirdPersonMap` | None | **Primary PPG/PlanetGen-free starter** (included in handoff Content) |
| `/Game/RedMMO/Maps/Sandbox_DesertDemoSparkle_T01` | Usually none for open | Local Titan sandbox; large; may reference dressed content |
| `/Game/RedMMO/Maps/RedPlanetGen*` | PlanetGen | Do not use for first-day fundamentals |
| `/Game/RedMMO/Maps/RedMMO_PPG_HomeWorld` | PPG | Clean D-drive project only |

If ThirdPerson content is missing after clone, create **File → New Level → Empty Open World / Basic** and set it as Editor Startup Map under Project Settings. That empty level is enough to compile and test C++ pawn/GameMode wiring.

---

## Restoring planetary plugins later

See [FAB_MARKETPLACE_INVENTORY.md](./FAB_MARKETPLACE_INVENTORY.md) and  
`D:\RedMMOTitanWindowsData\Diagnostics\R92_DependencyUnblock_20260807_000731\R92_DEPENDENCY_DISPOSITION.md`.

1. Install official Fab payloads so `*.uplugin` exists (FocalRig/WorldGen currently Intermediate-only on owner machine).
2. Re-enable plugin flags in `Titan.uproject`.
3. Rebuild; FocalRig auto-links when descriptor returns.
4. For clean RedMMO planetary baseline, keep using `D:\RedMMOTitanWindowsData\Projects\RedMMO\RedMMO.uproject` with PPG enabled.
