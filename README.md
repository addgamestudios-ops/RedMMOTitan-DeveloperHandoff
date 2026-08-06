# Red MMO — Developer Handoff Repo

**Start here:** [docs/DeveloperHandoff/START_HERE.md](docs/DeveloperHandoff/START_HERE.md) · [UK](docs/DeveloperHandoff/START_HERE_UK.md)  
**PDF:** [docs/DeveloperHandoff/RedMMOTitan_Developer_Handoff.pdf](docs/DeveloperHandoff/RedMMOTitan_Developer_Handoff.pdf) · [UK PDF](docs/DeveloperHandoff/RedMMOTitan_Developer_Handoff_UK.pdf)

## Core collaboration rule

Same GitHub repo for gameplay and environment. Merge-safe ownership:

| Layer | Map | Owner |
|---|---|---|
| Persistent | `/Game/RedMMO/Maps/Hubs/L_Hub_Persistent` | Thin shell |
| Env | `/Game/RedMMO/Maps/Hubs/L_Hub_Env_Visuals` | Environment artists |
| **HubLogic** | `/Game/RedMMO/Maps/Hubs/L_Hub_Gameplay_Logic` | **Gameplay developer** |

Details: [docs/DeveloperHandoff/MERGE_SAFE_WORLD.md](docs/DeveloperHandoff/MERGE_SAFE_WORLD.md) · [docs/EnvironmentArtistHandoff/MERGE_ENV_AND_GAMEPLAY.md](docs/EnvironmentArtistHandoff/MERGE_ENV_AND_GAMEPLAY.md)

**One-liner:** Clone this repo, work in the HubLogic / gameplay layer; artists will not overwrite your code or gameplay map.

## First day

1. Install Unreal Engine **5.8**
2. Open `TitanFundamentals.uproject`
3. Build **TitanEditor** Win64 Development
4. PIE on `/Game/ThirdPerson/Maps/ThirdPersonMap` for controls / listen-server
5. Put hub gameplay that must survive env delivery in `L_Hub_Gameplay_Logic`

Netcode / PvP: [docs/DeveloperHandoff/NETWORKING_PVP.md](docs/DeveloperHandoff/NETWORKING_PVP.md)

## Access

```powershell
git clone https://github.com/addgamestudios-ops/RedMMOTitan-DeveloperHandoff.git
```

## Environment artist role

- [docs/EnvironmentArtistHandoff/START_HERE.md](docs/EnvironmentArtistHandoff/START_HERE.md)

## Not included

Full Fab packs, Binaries/Intermediate/DDC, SteamIntegrationKit (~297MB) unless copied separately, owner workstation diagnostics / packaged trees.
