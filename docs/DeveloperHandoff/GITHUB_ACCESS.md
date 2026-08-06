# GitHub access — standalone handoff + invite rules

## Intended collaborator

| Field | Value |
|---|---|
| Contact email | **sanyarud@gmail.com** |
| Resolved GitHub username | **sanyarud** (https://github.com/sanyarud, name: Oleksandr) |
| Permission | **write / push** (not read-only) |
| API note | Collaborator PUT requires username; email local-part matched `sanyarud` |

### Invitation status (sent 2026-08-06 UTC)

| Repo | Invite ID | Permissions | Status | Accept URL |
|---|---|---|---|---|
| `addgamestudios-ops/RedMMOTitan-DeveloperHandoff` | 328309879 | **write** | **pending accept** (`expired: false`) | https://github.com/addgamestudios-ops/RedMMOTitan-DeveloperHandoff/invitations |
| `addgamestudios-ops/RedMMOTitan` | 328309881 | **write** | **pending accept** (`expired: false`) | https://github.com/addgamestudios-ops/RedMMOTitan/invitations |

Developer must accept while logged into GitHub as **sanyarud** (GitHub notifies that account’s email).

## Answer (invite vs open)

| Repo | Visibility | Must invite by username? |
|---|---|---|
| `addgamestudios-ops/RedMMOTitan` | **Private** | **YES** — done for `sanyarud` (from sanyarud@gmail.com) |
| `addgamestudios-ops/RedMMOTitan-DeveloperHandoff` | **Private** | **YES** — done for `sanyarud` |

Re-invite if needed:

```powershell
gh api -X PUT repos/addgamestudios-ops/RedMMOTitan-DeveloperHandoff/collaborators/sanyarud -f permission=push
gh api -X PUT repos/addgamestudios-ops/RedMMOTitan/collaborators/sanyarud -f permission=push
```

---

## Clone URL (standalone handoff)

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
- README / CODEX_HANDOVER / WINDOWS_BUILD entry docs

### Excluded (do not expect in clone)

- `Binaries/`, `Intermediate/`, `DerivedDataCache/`, `Saved/`
- Full Fab content packs (TropicalAlienWorld, SpaceColony, Action_Trooper full tree, etc. — tens of GB)
- Git LFS large media beyond tracked exceptions (clone may need separate content drive)
- `Plugins/SteamIntegrationKit` (~297 MB) — optional; copy from owner machine for Steam work
- `.env`, credentials, Steam secrets beyond public App ID **480** for Spacewar tests
- Owner-only diagnostics under `D:\RedMMOTitanWindowsData\` (R92 exe, rollbacks) — documented by path, not uploaded

### Existing private Titan remote

- `https://github.com/addgamestudios-ops/RedMMOTitan.git` — historical Mac/Windows handoff; worktree on owner PC is intentionally dirty and **not** fully mirrored by a blind push of all Content.

---

## If `gh` create/push failed on a machine

```powershell
gh auth login
gh repo create addgamestudios-ops/RedMMOTitan-DeveloperHandoff --private --source=. --remote=origin --push
# then invite:
gh api -X PUT repos/addgamestudios-ops/RedMMOTitan-DeveloperHandoff/collaborators/DEVELOPER_GITHUB_USERNAME -f permission=push
```
