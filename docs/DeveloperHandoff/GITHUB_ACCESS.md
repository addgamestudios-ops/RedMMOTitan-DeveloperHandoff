# GitHub access — standalone handoff + invite rules

## Answer (invite vs open)

| Repo | Visibility | Must owner invite developer by GitHub username? |
|---|---|---|
| `addgamestudios-ops/RedMMOTitan` (existing) | **Private** | **YES** — invite by GitHub username (or email invite). Agents cannot grant access without the developer’s handle. |
| `addgamestudios-ops/RedMMOTitan-DeveloperHandoff` (standalone) | **Private** (created for handoff) | **YES** — same rule. After invite, developer clones the URL below. |

Making the handoff repo **public** would allow clone without invite, but game source + licensed plugin trees should stay **private**. Prefer invite.

### Invite commands (owner runs once they have the developer’s username)

```powershell
$env:Path = [System.Environment]::GetEnvironmentVariable('Path','Machine') + ';' + [System.Environment]::GetEnvironmentVariable('Path','User')
# Replace DEVELOPER_GITHUB_USERNAME
gh api -X PUT repos/addgamestudios-ops/RedMMOTitan-DeveloperHandoff/collaborators/DEVELOPER_GITHUB_USERNAME -f permission=push
# Optional: also grant the full private Titan repo
gh api -X PUT repos/addgamestudios-ops/RedMMOTitan/collaborators/DEVELOPER_GITHUB_USERNAME -f permission=push
```

Or GitHub UI: Repo → Settings → Collaborators → Add people → enter **username**.

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
