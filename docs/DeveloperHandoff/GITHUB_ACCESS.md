# GitHub access — clone the handoff repo

## Clone (start here)

```text
https://github.com/addgamestudios-ops/RedMMOTitan-DeveloperHandoff.git
```

```powershell
git clone https://github.com/addgamestudios-ops/RedMMOTitan-DeveloperHandoff.git
cd RedMMOTitan-DeveloperHandoff
# Read docs/DeveloperHandoff/START_HERE.md
start TitanFundamentals.uproject
```

Web UI: https://github.com/addgamestudios-ops/RedMMOTitan-DeveloperHandoff

This handoff repository is the **same-repo** collaboration surface for gameplay and environment: you own HubLogic / gameplay packages; artists own env map packages. See [MERGE_SAFE_WORLD.md](./MERGE_SAFE_WORLD.md).

---

## What is included vs excluded

### Included

- `Source/` (RedMMO gameplay C++)
- `Config/`
- `docs/` DeveloperHandoff + EnvironmentArtistHandoff (MD + PDF)
- `ProjectKnowledge/` (when present)
- `Titan.uproject`, `TitanFundamentals.uproject`, targets
- `Content/ThirdPerson/` starter map
- `Content/RedMMO/Maps/Hubs/` — Persistent / Env / Gameplay_Logic stubs
- Selected `Content/RedMMO/` crumbs when tracked

### Excluded

- `Binaries/`, `Intermediate/`, `DerivedDataCache/`, `Saved/`
- Full Fab content packs
- `Plugins/SteamIntegrationKit` (~297 MB) — optional; copy when doing Steam sessions
- Secrets beyond public Steam App ID **480** for Spacewar tests
- Owner-only workstation diagnostics and packaged build trees

---

## Private full Titan (optional later)

Historical / full private tree: `https://github.com/addgamestudios-ops/RedMMOTitan.git` — use only if you are granted access for content that is not in the public handoff clone. Day-1 HubLogic and netcode do not require it.
