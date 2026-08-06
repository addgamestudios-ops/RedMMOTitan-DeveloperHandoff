# Hub map ownership (do not delete)

| Asset | Owner | Purpose |
|---|---|---|
| `L_Hub_Persistent` | Lead / rare edits | Thin shell — streams Env + Gameplay |
| `L_Hub_Env_Visuals` | Environment artists | Landscape, lighting, foliage, dressing |
| `L_Hub_Gameplay_Logic` | Gameplay developer (HubLogic) | PlayerStarts, volumes, networked actors |

Gameplay developers: edit **Gameplay_Logic** only. Do not save hub logic into Env.  
Docs: `docs/DeveloperHandoff/MERGE_SAFE_WORLD.md`

**Stub status:** Empty composition stubs. Persistent already references Env + Gameplay as streaming levels. Day-1 netcode PIE can stay on `ThirdPersonMap`; put hub work that must survive env delivery into `L_Hub_Gameplay_Logic`.
