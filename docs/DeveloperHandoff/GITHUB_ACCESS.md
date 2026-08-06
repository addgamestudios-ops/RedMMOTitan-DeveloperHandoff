# GitHub access — standalone handoff + invite rules

## Intended collaborator

| Field | Value |
|---|---|
| Contact email | **sanyarud@gmail.com** |
| Resolved GitHub username | **sanyarud** (https://github.com/sanyarud, name: Oleksandr) |
| Permission | **write / push** on private Titan (when invite accepted) |
| Standalone handoff | **Public** — clone without invite |

### Invitation status (private Titan)

| Repo | Permissions | Notes |
|---|---|---|
| `addgamestudios-ops/RedMMOTitan-DeveloperHandoff` | n/a (public) | Clone URL below |
| `addgamestudios-ops/RedMMOTitan` | **write** invite for `sanyarud` | Accept while logged in as that username |

---

## Clone URL (standalone handoff — public)

```text
https://github.com/addgamestudios-ops/RedMMOTitan-DeveloperHandoff.git
```

```powershell
git clone https://github.com/addgamestudios-ops/RedMMOTitan-DeveloperHandoff.git
cd RedMMOTitan-DeveloperHandoff
# Read Docs/DeveloperHandoff/START_HERE.md
start TitanFundamentals.uproject
```

Web UI: https://github.com/addgamestudios-ops/RedMMOTitan-DeveloperHandoff

Browser multi-account issues: [GITHUB_AUTH_FIX.md](./GITHUB_AUTH_FIX.md).

---

## What is included vs excluded

### Included in standalone handoff repo

- `Source/` (RedMMO gameplay C++)
- `Config/`
- `docs/` + `Docs/DeveloperHandoff/` (MD + PDF)
- `ProjectKnowledge/`
- `Build/Automation/` (scripts that exist)
- Selected `Tools/` (no `__pycache__`)
- `Titan.uproject`, `TitanFundamentals.uproject`, targets
- `Content/ThirdPerson/` (PPG-free starter map)
- Git-whitelisted `Content/RedMMO/` crumbs (maps/materials/characters listed in `.gitignore` exceptions) when present
- Project plugins that are small enough / essential: prefer `VibeMMOUIKit`, `RedHUD` if size allows; otherwise document copy-from-owner
- `README.md`, `HANDOVER.md`, `WINDOWS_BUILD.md` entry docs

### Excluded (do not expect in clone)

- `Binaries/`, `Intermediate/`, `DerivedDataCache/`, `Saved/`
- Full Fab content packs (TropicalAlienWorld, SpaceColony, Action_Trooper full tree, etc. — tens of GB)
- Git LFS large media beyond tracked exceptions (clone may need separate content drive)
- `Plugins/SteamIntegrationKit` (~297 MB) — optional; copy from owner machine for Steam work
- `.env`, credentials, Steam secrets beyond public App ID **480** for Spacewar tests
- Owner-only diagnostics under `D:\RedMMOTitanWindowsData\` (R92 exe, rollbacks) — documented by path, not uploaded

### Existing private Titan remote

- `https://github.com/addgamestudios-ops/RedMMOTitan.git` — historical Mac/Windows handoff; worktree on owner PC is intentionally dirty and **not** fully mirrored by a blind push of all Content.
