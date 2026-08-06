# RedMMOTitan — Developer Handoff Repo

**Start here:** [Docs/DeveloperHandoff/START_HERE.md](Docs/DeveloperHandoff/START_HERE.md) · [UK](Docs/DeveloperHandoff/START_HERE_UK.md)  
**PDF:** [Docs/DeveloperHandoff/RedMMOTitan_Developer_Handoff.pdf](Docs/DeveloperHandoff/RedMMOTitan_Developer_Handoff.pdf) · [UK PDF](Docs/DeveloperHandoff/RedMMOTitan_Developer_Handoff_UK.pdf)

## First day (no PPG / PlanetGen)

1. Install Unreal Engine **5.8**
2. Open `TitanFundamentals.uproject`
3. Build **TitanEditor** Win64 Development
4. PIE on `/Game/ThirdPerson/Maps/ThirdPersonMap`

Planet / PPG work is optional later — see `Docs/DeveloperHandoff/PPG_PLANETGEN_FREE_START.md` and `FAB_MARKETPLACE_INVENTORY.md`.

Netcode / PvP focus: `Docs/DeveloperHandoff/NETWORKING_PVP.md` (UK: `NETWORKING_PVP_UK.md`).

## Access

This repository is **public**. Clone:

```powershell
git clone https://github.com/addgamestudios-ops/RedMMOTitan-DeveloperHandoff.git
```

The full historical Titan repo (`addgamestudios-ops/RedMMOTitan`) remains **private**. See `Docs/DeveloperHandoff/GITHUB_ACCESS.md`.

## Environment artist handoff

Separate role from netcode/gameplay. Same clone:

- Start: [docs/EnvironmentArtistHandoff/START_HERE.md](docs/EnvironmentArtistHandoff/START_HERE.md)
- PDF: [docs/EnvironmentArtistHandoff/RedMMO_Environment_Artist_Handoff.pdf](docs/EnvironmentArtistHandoff/RedMMO_Environment_Artist_Handoff.pdf)
- Merge env + gameplay maps: [docs/EnvironmentArtistHandoff/MERGE_ENV_AND_GAMEPLAY.md](docs/EnvironmentArtistHandoff/MERGE_ENV_AND_GAMEPLAY.md)

Primary env test maps (Titan Content, not in this thin clone): `RedPlanetGen_50km_ArtistCanvas` and `Sandbox_DesertDemoSparkle_T01`.

## Not included

Full Fab content packs, Binaries/Intermediate/DDC, SteamIntegrationKit (~297MB), R92 packaged builds under `D:\RedMMOTitanWindowsData\`, and secrets.
