# Alien asset-gap register

This register turns the ten supplied mood-board images into an explicit **audition before generation** decision. It is an inventory and filename audit, not visual approval. No Meshy or Tripo job is authorized until the installed candidates have been viewed in neutral noon and saturated dusk at player, jetpack, and ship distance.

The machine-readable source of truth is [ALIEN_ASSET_GAP_REGISTER.json](ALIEN_ASSET_GAP_REGISTER.json). The protected 50 km checkpoint is read-only throughout this workflow.

## Decision summary

| Family | Decision now | Why |
|---|---|---|
| Alien understory, meadow filler, vines, flowers | Installed review first | `Alien_Grass_Pack`, `Alien_Plants_Pack`, `AlienJungle`, and `TropicalAlienWorld` contain broad named coverage. |
| Crimson droop trees | Partial visual review | `AlienJungle` already has `SM_treeDroop*` and `SM_treeDangl*`; generate only if their silhouettes fail. |
| Needles, cliffs, shelves, hoodoos, obsidian rocks | Installed review first | `TropicalAlienWorld`, `AlienJungle`, `SoStylized`, and `StylizedDesertOasis` have strong support candidates. |
| Portal, bridges, channels, cliff spaceport | Manual kitbash | Collision-critical traversal and modular snapping require controlled authored geometry. |
| Coral umbrella tree | Conditional generation candidate | No explicitly named installed asset matches the buttressed trunk plus five-to-eight horizontal coral plates. |
| Fungal cathedral tree and bracket fungi | Conditional generation candidate | Explicit asset-name scan found no mushroom, fungus, fungi, toadstool, mycelium, or spore mesh family. |
| Floating balloon and spore life | Conditional generation candidate | No explicitly named physical pod family exists; tether and movement should remain Niagara/manual systems. |
| Water, mist, dust, pollen, spray, light shafts | Installed review first | These are VFX/material problems, not image-to-3D mesh problems. |
| Polar/tundra support | Partial visual review | Snow layers and ice flowers exist, but there is no dedicated tundra prop family. Prefer an installed/licensed pack before generation. |

`Conditional generation candidate` still means `generation_allowed=false`. A visible cross-pack audition must first confirm the gap.

## Exact installed candidates

- Understory: `/Game/Alien_Plants_Pack/Meshes/SM_Plant_Alien_Fern_01_A`, `SM_Plant_Alien_Aloe_01_A`, `SM_Plant_Alien_RoundLeaf_01_A`; `/Game/AlienJungle/Meshes/SM_grassGlobA`; `/Game/TropicalAlienWorld/Models/SM_plant1`.
- Droop canopy: `/Game/AlienJungle/Meshes/SM_treeDroopAa`, `SM_treeDroopAb`, `SM_treeDroopBa`, and `SM_treeDanglAa`.
- Geology: `/Game/TropicalAlienWorld/Models/SM_cliff1`, `SM_rockFormation1`; `/Game/AlienJungle/Meshes/SM_obsPillarA`, `SM_obsRockA`; `/Game/SoStylized/Environment/Rocks/Desert/SM_RockDesert_Hoodoo01`.
- Portal/spaceport kitbash: `/Game/AlienJungle/Meshes/SM_ringDevice`, `SM_ringRamp`, `SM_ringWall`; `/Game/AsteroidSpaceport/Meshes/Stations/SM_Mining_Bridge`, `SM_Spaceport_Main`.
- Polar support: `/Game/SoStylized/Environment/Landscape/LL_Snow`, `LL_SnowGrass`, and `/Game/SoStylized/Environment/Foliage/SM_FlowersIce01`.

The audit also found 231 assets under `Alien_Grass_Pack`, 305 under `Alien_Plants_Pack`, 498 under `AlienJungle`, 137 under `TropicalAlienWorld`, 729 under `SoStylized`, and 166 under `StylizedDesertOasis`. Counts include non-mesh supporting assets and therefore do not imply approval.

## Mood-board routing

| Reference suffix | Required visual language | Implementation route |
|---|---|---|
| `23-06-03` | Orange/crimson meadow, magenta canopy, needle and shelf geology | Installed filler first; conditional hero generation only after audition. |
| `23-06-04` | Portal oasis, turquoise water, floating tethered pods | Manual portal; installed water/plants; conditional floating-life generation. |
| `23-06-07` | Pale buttressed coral trees with horizontal plates and tendrils | Conditional hero-family generation. |
| `23-06-23` | Monumental pillars, ceiling shelves, waterfalls, ledge growth | Installed rock/VFX support; generated geometry cannot be final traversal collision. |
| `23-06-24` | Traversable plateaus, bridges, cyan channels | Manual/kitbash only for final gameplay geometry. |
| `23-06-26` | Ordinary forest density and light shafts | Density baseline using installed packs. |
| `23-06-26 (2)` | Buttressed trunks, root arches, bracket fungi | Conditional fungal hero-family generation; manually rebuild critical arches. |
| `23-06-26 (3)` | Cliff-integrated industrial spaceport | Installed modular kitbash and manual construction. |
| `23-06-27` | Crimson droop trees, orange grass, fan understory | Installed review first; generate only if droop family fails. |
| `06-18` | Distinct continents and large oceans | Macro-world reference, not an asset-generation request. |

## Visible audition gate

For each family, make a test-map duplicate and compare candidates without touching the protected checkpoint:

1. Place a mannequin and a scale ruler beside each candidate.
2. Capture neutral noon and saturated dusk.
3. Capture player, jetpack, and ship-approach silhouettes.
4. Record material editability, pivot, real-world scale, radial snap, collision, wind/WPO bounds, Nanite/LOD/HLOD behavior, overdraw, shadow cost, texture memory, and stress-instance cost.
5. Mark the family `pass` if installed assets meet the silhouette and runtime need. Only a failed visual audition may change a conditional family to `generation_allowed=true`.

## Meshy/Tripo intake and promotion

Every generated source begins in quarantine and records tool, model/version, prompt, seed, date, and license evidence. It then needs cleanup for topology, internal shells, UVs, texel density, base pivot, centimetre scale, Z-up, materials without baked lighting, simple collision, radial alignment, wind bounds, Nanite or conventional LOD/HLOD, and instance performance.

Promotion to hand placement and promotion to PCG are separate decisions. Hand placement must pass first. The accepted record is then projected into `URedWorldAssetPalette` with mesh, role, biome tags, scale/slope/elevation constraints, collision policy, reviewed Nanite state, and explicit hand/PCG flags.

## Current honest blocker

Classification and installed-content auditing are complete. No generated mesh has been created or approved. M08 remains in progress until the visible auditions run and any truly missing generated asset passes all technical, visual, and performance gates.
