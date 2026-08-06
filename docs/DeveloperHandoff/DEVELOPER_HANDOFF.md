# RedMMOTitan — Developer Handoff (2026-08-07)

**Status:** Good enough for developer takeover. Many problems remain. Planetary plugins are optional for first fundamentals work.

| Artifact | Location |
|---|---|
| **START_HERE** | [START_HERE.md](./START_HERE.md) |
| **PDF** | [RedMMOTitan_Developer_Handoff.pdf](./RedMMOTitan_Developer_Handoff.pdf) |
| **Fab inventory** | [FAB_MARKETPLACE_INVENTORY.md](./FAB_MARKETPLACE_INVENTORY.md) |
| **PPG-free start** | [PPG_PLANETGEN_FREE_START.md](./PPG_PLANETGEN_FREE_START.md) |
| **GitHub access** | [GITHUB_ACCESS.md](./GITHUB_ACCESS.md) |
| Diagnostics copy | `D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_DeveloperHandoff_20260807\` |
| Canonical knowledge | `D:\RedMMOTitan\ProjectKnowledge\` (`INDEX.yaml` → `current_state.yaml` → `invariants.yaml`) |

---

## 1. Paths

| Role | Path |
|---|---|
| Primary repo (owner, dirty worktree) | `D:\RedMMOTitan` — `Titan.uproject` |
| Fundamentals handoff project | `TitanFundamentals.uproject` (PlanetGen/PPG not required) |
| Clean planetary RedMMO | `D:\RedMMOTitanWindowsData\Projects\RedMMO\RedMMO.uproject` |
| Engine | `D:\UE_5.8` (UE **5.8** exact) |
| R92 playable package | `D:\RedMMOTitanWindowsData\Builds\RedMMO_R92_Playable_20260806T1740Z\Windows\RedMMO.exe` |
| Tree SHA-256 (R92) | `11F6F6AE332D56EE6BED0ADE800BFD72EC878990F2B262884FD162DD7445B409` |
| Owner origin (private) | `https://github.com/addgamestudios-ops/RedMMOTitan.git` |

Never use `C:\Users\...\Documents\Red MMO Windows`.

---

## 2. What works (honest)

**Build / dependency (evidence: R92_DependencyUnblock pack):**

- `TitanEditor` Win64 Development **succeeds** with FocalRig/WorldGen **disabled** and PlanetGen fork APIs **shimmed** (`RedPlanetGenCompat`).
- FocalRig: stock ControlRig AimItem substitute when Fab payload absent.
- WorldGen: disabled with documented rollback.

**Live RedMMO editor PIE fixes (recent session — treat as working on that build, still need human regression):**

- Mouse wheel → thrust  
- Atmosphere exit  
- Weapons / plumes / jetpack  
- Terrain blend  

**Accepted packaged baseline:**

- R92 Win64 Development package (50 files) — launchable without editor; PlayerStatus cook closure; packaged D3D12 smoke historically clean.

**Still open / many problems remain:**

- Human feel / full physical playtest on R92  
- Authored HUD fuel pixels, audio feel, biome art polish  
- Fused-continent consumer binding on clean RedMMO  
- M04 traversal/perf, M05 real 1S/2C, Steam two-account, warp, final art  
- Running anim must stay **protected** while improving feel  

This handoff is **good enough to take over**, not “feature complete.”

---

## 3. Known bugs / open defects (pointers)

Read `ProjectKnowledge/defects/` and queue `Build/Automation/redmmotitan_module_queue.json`. Snapshot from R92 takeover:

- DEF-0001, DEF-0002 open  
- DEF-0003, DEF-0005, DEF-0007 await runtime acceptance  
- DEF-0004 open (jetpack HUD boundary history)  
- DEF-0006 awaits build/runtime  
- DEF-0008 resolved  
- UAIP / Copilot / Blender MCP: marketplace/human blockers — skip without stalling  

---

## 4. FocalRig / WorldGen / PlanetGen disposition

| Plugin | Disposition | Rollback |
|---|---|---|
| FocalRig | **Disabled** + ControlRig substitute | Restore Fab `FocalRig.uplugin` → Enabled true → rebuild |
| WorldGen | **Disabled** | Restore `WorldGen.uplugin` → Enabled true |
| PlanetGen fork pin | **Absent**; shims active | Restore `Plugins/PlanetGenPinned_*` or port APIs; shims auto-forward |
| PlanetGen Marketplace 1.7 | Present on owner engine; **disabled in TitanFundamentals** | Enable only when doing Titan planetary maps |
| PPG | Clean RedMMO only; **not required** for fundamentals | Install Marketplace PPG for home world |

Details: `R92_DEPENDENCY_DISPOSITION.md` and [PPG_PLANETGEN_FREE_START.md](./PPG_PLANETGEN_FREE_START.md).

---

## 5. Build / launch / PIE

### Fundamentals (recommended first day)

```powershell
# Open fundamentals project (no PPG/PlanetGen)
start D:\path\to\RedMMOTitan-DeveloperHandoff\TitanFundamentals.uproject
# Build TitanEditor Win64 Development, PIE on ThirdPersonMap
```

### Full Titan (PlanetGen)

```powershell
start D:\RedMMOTitan\Titan.uproject
# Map: /Game/RedMMO/Maps/RedPlanetGen
```

### Clean planetary RedMMO (PPG)

```powershell
start D:\RedMMOTitanWindowsData\Projects\RedMMO\RedMMO.uproject
# Map: /Game/RedMMO/Maps/RedMMO_PPG_HomeWorld — seed 1337
```

### Packaged smoke (no editor)

```powershell
& 'D:\RedMMOTitanWindowsData\Builds\RedMMO_R92_Playable_20260806T1740Z\Windows\RedMMO.exe'
```

**Single-editor rule:** one UnrealEditor at a time. Prefer guarded MCP start:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File D:\RedMMOTitan\Build\Automation\Start-UnrealAIEditorGuarded.ps1
```

---

## 6. MCP ports

| Server | Port | Notes |
|---|---|---|
| Epic ModelContextProtocol | `http://127.0.0.1:8000/mcp` | Needs editor + `-ModelContextProtocolStartServer` |
| Nwiro | `http://127.0.0.1:5353/mcp` | Needs Nwiro plugins |
| UAIP | `http://127.0.0.1:8765/mcp` | **Blocked** — payload missing |

Cursor catalog IDs: `user-epic_unreal_mcp`, `user-nwiro`, `user-uaip_titan_http`.  
Guide: `...\RedMMO_R92_AgentTakeover_20260806T1805Z\MCP_PLUGIN_ACCESS_GUIDE.md`.

---

## 7. Protected items

1. **Running animation / locomotion graph** on `ABP_RedTrooperFemale` — do not “fix” run by replacing the single-node / R86 locomotion guard without explicit owner authority. Prefer additive or parallel work on aim/jetpack poses.  
2. Fused 27 tangent inputs + six fused faces — never silent bind/regenerate/promote.  
3. Protected hashes (production map, 50 km checkpoint, fused prototype/heightfield, clean home, ProfileV1) — see takeover pack §6.  
4. R92 package directory — immutable; new work gets a new named package.  
5. Owner dirty git worktree — no hard reset / bulk clean.

---

## 8. Next fundamentals work

1. PPG/PlanetGen-free compile + PIE on `TitanFundamentals` / ThirdPersonMap.  
2. Protect run anim; improve on-foot feel, aim, jetpack, fire separately.  
3. Re-verify wheel-thrust, atmosphere exit, weapons/plumes on RedMMO when plugins available.  
4. Only then: PPG home art, shore bands, fused consumer, MP/Steam.

---

## 9. GitHub

See [GITHUB_ACCESS.md](./GITHUB_ACCESS.md).

- Existing org/user repo `addgamestudios-ops/RedMMOTitan` is **private**.  
- Standalone handoff repo is published separately for the developer.  
- **Inviting a collaborator to a private repo requires the developer’s GitHub username (or email for invite).** Agents cannot invent that handle.

---

## 10. Fab / Marketplace

Full checklist: [FAB_MARKETPLACE_INVENTORY.md](./FAB_MARKETPLACE_INVENTORY.md).

**Day-1 rule:** developer must **not** need PPG or PlanetGen installed to start building.
