# START HERE — RedMMOTitan developer handoff

**Generated:** 2026-08-07  
**Ukrainian:** [START_HERE_UK.md](./START_HERE_UK.md) · **PDF UK:** [RedMMOTitan_Developer_Handoff_UK.pdf](./RedMMOTitan_Developer_Handoff_UK.pdf)  
**PDF (EN):** [RedMMOTitan_Developer_Handoff.pdf](./RedMMOTitan_Developer_Handoff.pdf)  
**Full handoff:** [DEVELOPER_HANDOFF.md](./DEVELOPER_HANDOFF.md)  
**Networking / PvP (primary for this developer):** [NETWORKING_PVP.md](./NETWORKING_PVP.md) · [NETWORKING_PVP_UK.md](./NETWORKING_PVP_UK.md)  
**Fab / Marketplace checklist:** [FAB_MARKETPLACE_INVENTORY.md](./FAB_MARKETPLACE_INVENTORY.md)  
**PPG / PlanetGen–free start:** [PPG_PLANETGEN_FREE_START.md](./PPG_PLANETGEN_FREE_START.md)

**Collaborator:** `sanyarud@gmail.com` → GitHub **`sanyarud`** (write/push invites pending accept).

---

## 60-second path

1. Clone the standalone handoff repo (see clone URL in `GITHUB_ACCESS.md`).
2. Install **Unreal Engine 5.8** (exact association in `Titan.uproject` / `TitanFundamentals.uproject`).
3. **Do not wait on PPG or PlanetGen** for first compile / first PIE:
   - Open **`TitanFundamentals.uproject`**
   - Default map: `/Game/ThirdPerson/Maps/ThirdPersonMap`
   - Build **TitanEditor** Win64 Development, then PIE
4. When marketplace planet plugins are available, switch to full `Titan.uproject` or the clean D-drive `RedMMO.uproject` for planetary work.
5. Read `DEVELOPER_HANDOFF.md` before changing locomotion, fused terrain, or production maps.

---

## Clone → open → build → PIE

```powershell
git clone <CLONE_URL_FROM_GITHUB_ACCESS.md>
cd RedMMOTitan-DeveloperHandoff

# Fundamentals (no PPG / PlanetGen required)
start TitanFundamentals.uproject
```

In Visual Studio / Rider / Unreal Build:

```text
Target: TitanEditor
Platform: Win64
Configuration: Development
```

**PIE checklist (fundamentals baseline):**

| Check | Expected |
|---|---|
| Editor opens ThirdPersonMap | No missing PPG/PlanetGen hard fail |
| PIE possess | Character moves with WASD + mouse |
| Compile RedMMO module | Succeeds with FocalRig/WorldGen disabled |
| No second editor | Only one UnrealEditor at a time on this machine |

**PIE checklist (full planetary / clean RedMMO — optional plugins required):**

| Check | Expected |
|---|---|
| Wheel | Thrust (recent RedMMO editor fix) |
| Atmosphere exit | Works (recent fix) |
| Weapons / plumes / jetpack | Present on live RedMMO editor build |
| Terrain blend | Present |
| **Running animation** | **Do not overwrite / “fix” without explicit authority** |

---

## Machine paths (owner workstation)

| Role | Path |
|---|---|
| Repo / knowledge root | `D:\RedMMOTitan` |
| Clean planetary project | `D:\RedMMOTitanWindowsData\Projects\RedMMO\RedMMO.uproject` |
| Accepted packaged R92 baseline | `D:\RedMMOTitanWindowsData\Builds\RedMMO_R92_Playable_20260806T1740Z\Windows\RedMMO.exe` |
| This diagnostics pack | `D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_DeveloperHandoff_20260807\` |
| R92 agent takeover pack | `D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_R92_AgentTakeover_20260806T1805Z\` |
| Dependency disposition | `D:\RedMMOTitanWindowsData\Diagnostics\R92_DependencyUnblock_20260807_000731\R92_DEPENDENCY_DISPOSITION.md` |
| Engine | `D:\UE_5.8` |

Do **not** use `C:\Users\user\Documents\Red MMO Windows`.

---

## Protected items (do not casually touch)

- **Running / locomotion anim graph** on `ABP_RedTrooperFemale` — treat as protected; recent PIE work must not regress run.
- Protected fused 27/6 authoring inputs and hashes (see ProjectKnowledge / handoff).
- Production map hashes and R92 package tree identity.
- Never `git reset --hard` the dirty owner worktree on `D:\RedMMOTitan`.

---

## Next fundamentals work (priority)

1. Stabilize on-foot locomotion feel **without** breaking the protected run anim.
2. Weapon / jetpack / ship entry-exit feel on a map that opens without PPG if planetary plugins are missing.
3. Then (with PPG or PlanetGen restored): home-world art, shore bands, multiplayer, fused-consumer binding.

Continue with [DEVELOPER_HANDOFF.md](./DEVELOPER_HANDOFF.md).
