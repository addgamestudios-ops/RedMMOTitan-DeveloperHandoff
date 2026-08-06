# RED MMO project architecture and world-authoring tools

Status: architecture decision and migration plan. This document does not authorize
bulk package moves, production-map edits, vendor-source edits, or destructive renames.

## Outcome

RED MMO should use Unreal's large-world systems as the foundation and add narrowly
scoped project tools where the spherical planet, three-dimensional traversal, and
hand-painted biome grammar create a real gap.

The current project already has the correct long-term gameplay namespace:

- native runtime module: `RedMMO`;
- content namespace: `/Game/RedMMO`;
- production entry map: `/Game/RedMMO/Maps/RedPlanetGen`.

The remaining `Titan` identity belongs mainly to the project file, build targets,
packaging products, old dormant source, automation paths, and historical evidence.
That identity must be removed transactionally, not with a repository-wide text
replacement.

## Observed repository baseline

The 2026-07-23 read-only audit found:

- 7,142 Unreal packages in project `Content`: 7,085 assets and 57 maps, about
  9.223 GiB;
- 36 top-level project content roots;
- 489 colliding asset basenames involving 1,157 packages;
- four large project plugins are not tracked by Git;
- Git tracks no project `.uasset` or `.umap` package;
- the worktree contains extensive pre-existing modified and untracked work;
- `Source/RedMMO` is one flat, heavily coupled runtime module with editor tools
  mixed into it;
- the existing M07 palette and manual-placement protection types are useful, but
  no curated palette asset or approved content library has been authored yet;
- the six high-value art sources are present:
  `SoStylized`, `StylizedDesertOasis`, `AlienJungle`,
  `TropicalAlienWorld`, `Alien_Grass_Pack`, and `Alien_Plants_Pack`.

These facts make a bulk filesystem cleanup unsafe. Before physical reorganization,
the project needs reproducible dependency storage and an Unreal Asset Registry
dependency audit.

## Engineering rules

1. **Engine first, extension second, custom system last.**
   Prefer World Partition, One File Per Actor, Data Layers, Level Instances, PCG,
   Foliage/ISM/HISM, Asset Manager, Asset User Data, Data Validation, and editor
   scripting. Extend those systems at stable seams.
2. **Hand-authored intent is primary.**
   Procedural generation fills and varies a composition. It does not choose hero
   landmarks, erase protected work, close routes, or rewrite an artist's vista.
3. **Vendor sources are immutable.**
   Do not rename or reorganize marketplace packages in place. Project-owned
   catalogs, material instances, palettes, and collections reference them.
4. **Every generated result is previewable, deterministic, and bakeable.**
   A content creator must see the result in the editor before runtime. The same
   seed and inputs must reproduce the same placement.
5. **Every tool exposes negative space.**
   Roads, paths, hubs, landing zones, silhouettes, water margins, and manual POIs
   are explicit exclusion or falloff inputs, not afterthoughts.
6. **No hidden all-world operation.**
   Whole-world work uses bounded World Partition builder cells, progress,
   cancellation, durable logs, and resumable outputs.
7. **No visual claim without real-GPU evidence.**
   Static analysis can approve architecture and data integrity, not appearance,
   naturalism, overdraw, shadows, streaming, or gameplay feel.

## Lessons adopted from the Subnautica 2 Unreal Fest talk

The Unreal Fest session
[Lessons Learned from Building a Very Large Open World Game in UE5](https://youtu.be/AalP65lrtpo)
is unusually relevant because underwater movement and flight both turn the
environment into a three-dimensional traversal medium.
The transferable lessons are:

- dense authored worlds need procedural authoring assistance, but runtime
  randomization is not automatically valuable to players;
- a bespoke world-population system can become slower, opaque, and harder to
  maintain than the problem it solves;
- placement results and rule effects must be visible in the editor;
- use data-driven rules, but expose them through an artist-facing interface;
- use World Partition and One File Per Actor from the start for large worlds;
- use builder commandlets to process bounded world regions rather than loading
  everything;
- Data Layers should separate large reworks, gameplay states, and authoring
  concerns;
- Asset User Data can attach gameplay and placement meaning to reusable meshes
  without converting every instance into a ticking Blueprint;
- validators and automated visual/performance patrols catch drift early;
- aggregate repeated updates in managers or subsystems and prefer events over
  hundreds of per-actor ticks;
- a focused plugin is a good experiment when its removal cost is low; a custom
  platform-sized subsystem requires a much higher bar.

The RED MMO interpretation is not "build dozens of bespoke tools." It is "build a
small project tool layer on top of Unreal's systems, only for our recurring pain
points."

## Target repository layout

This is the destination, not a command to move current files immediately:

```text
RedMMO.uproject
Source/
  RedMMOCore/
    Public/
    Private/
  RedMMOGame/
    Public/
    Private/
  RedMMOWorld/
    Public/
    Private/
  RedMMOUI/
    Public/
    Private/
  RedMMOEditor/
    Public/
    Private/
  RedMMO.Target.cs
  RedMMOClient.Target.cs
  RedMMOServer.Target.cs
  RedMMOEditor.Target.cs
Content/
  RedMMO/
    Core/Data/
    ArtLibrary/
      Catalogs/
      MaterialInstances/
      Thumbnails/
    Characters/
    Gameplay/
      Abilities/
      Combat/
      Items/
      Mining/
    World/
      Planets/
      Biomes/
      Hubs/
      POI/
      PCG/
      HLOD/
      Palettes/
    Vehicles/
    UI/
    Audio/
    VFX/
    Maps/
      Persistent/
      Instances/
      Dev/
      Tests/
Plugins/
  Project/
  ThirdParty/
SourceArt/
  Planet/
  Characters/
  UI/
  VendorReferences/
Tools/
  redmmo/
  tests/
docs/
  Architecture/
  Art/
  Operations/
```

The first safe module split is `RedMMOEditor`: move editor-only authoring and
validation code out of the runtime module. Gameplay splits come later, after
include and dependency measurements.

## Content ownership model

### Vendor and supplied content

Keep existing vendor roots at their current package paths during the first
curation pass. Treat them as source libraries:

```text
/Game/SoStylized/
/Game/StylizedDesertOasis/
/Game/AlienJungle/
/Game/TropicalAlienWorld/
/Game/Alien_Grass_Pack/
/Game/Alien_Plants_Pack/
```

Do not infer redistribution rights from their presence. Record pack provenance,
version, license location, and modification policy in the project catalog.

### Project-owned curated layer

Create references and adaptations under:

```text
/Game/RedMMO/ArtLibrary/Catalogs/
/Game/RedMMO/ArtLibrary/MaterialInstances/
/Game/RedMMO/World/Palettes/
/Game/RedMMO/World/Biomes/<BiomeId>/
```

Each approved catalog entry should eventually record:

- stable RED asset ID;
- soft object path;
- source pack, source version, and provenance note;
- candidate and approved roles;
- biome and surface tags;
- hand-painted PBR family and palette;
- collision policy;
- scale, slope, curvature, aspect, elevation, moisture, and water-distance ranges;
- hand-only, PCG-eligible, or hero-only state;
- LOD/Nanite, masked-overdraw, WPO, shadow, and cull review;
- measured CPU/GPU/memory tier;
- thumbnail and neutral-noon/saturated-dusk review captures;
- approval owner, status, and notes.

Use project-owned material instances or material adapters. Never edit a vendor
master material in place.

The initial offline catalog is produced by:

```powershell
python Tools/audit_redmmo_asset_library.py `
  --output D:\RedMMOTitanWindowsData\Diagnostics\<run>\asset_library_inventory.json
```

That report is deliberately an inventory, not approval. Filename and folder
inference cannot prove Unreal class, PBR readiness, collision, Nanite state, or
fitness for a biome.

The follow-up Unreal Asset Registry export is implemented by
`Tools/export_redmmo_asset_registry_catalog.py`. Run it only in one isolated
Unreal process with a new `REDMMO_ASSET_REGISTRY_OUTPUT` path below
`D:\RedMMOTitanWindowsData\Diagnostics`. It waits for registry discovery and
queries the six source roots recursively with `include_only_on_disk_assets`;
it does not call `load_asset`, save, move, rename, duplicate, or edit any
package. Its JSON remains a candidate list until provenance, license, visual,
collision, PBR, LOD/Nanite, and measured runtime review are complete.

The first isolated UE 5.8 NullRHI pass on 2026-07-23 returned 2,066 on-disk
candidates: 729 SoStylized, 166 StylizedDesertOasis, 498 AlienJungle, 137
TropicalAlienWorld, 231 Alien_Grass_Pack, and 305 Alien_Plants_Pack. The largest
classes are 753 static meshes, 482 Texture2D assets, 361 material instances, and
164 foliage types. These exact root counts match the prior filesystem inventory,
and the post-commandlet package-tree signature is unchanged. The raw list still
contains reference maps, map-build data, and one redirector; the curator must
filter those without deleting or moving their source packages.

The deterministic offline curation layer is produced by:

```powershell
python Tools/build_redmmo_asset_curation_manifest.py `
  --input D:\RedMMOTitanWindowsData\Diagnostics\<registry-run>\asset_registry_catalog_candidates.json `
  --output D:\RedMMOTitanWindowsData\Diagnostics\<curation-run>\art_library_curation_manifest.json `
  --project-root D:\RedMMOTitan
```

The first complete pass retained all 2,066 input candidates exactly once:
1,284 primary environment candidates, 721 support dependencies, 29 deferred
specialty candidates, and 32 technical or reference exclusions. It generated
644 deterministic family review batches and proposed logical Content Browser
collection names without creating collections or Unreal packages. No local
license, readme, version, or provenance document was found inside the six pack
roots, so every source pack and every candidate remains unapproved and blocked
on human provenance and license review. An exclusion in this manifest only keeps
an item out of the project-owned curated layer; it never deletes, moves, renames,
or edits the vendor package.

### Content and project-plugin source-input storage manifest

The deterministic storage-readiness manifest is produced by:

```powershell
python Tools/build_redmmo_content_storage_manifest.py `
  --project-root D:\RedMMOTitan `
  --output D:\RedMMOTitanWindowsData\Diagnostics\<run>\content_project_plugin_source_storage_manifest.json
```

The manifest hashes the active project descriptor, every regular file below
`Content`, and every non-generated regular file in each direct project-local
plugin. Plugin `Resources`, scripts, documentation, source art, SDK inputs, and
other top-level files are included rather than silently dropped. Immediate
plugin `.git`, `.vs`, `Binaries`, `DerivedDataCache`, `Intermediate`, and `Saved`
trees are explicitly excluded as repository or generated products.

The 2026-07-24 pass authenticated 8,228 files and 10,490,519,650 bytes:
7,147 Content files, the project descriptor, and 1,080 source-input files across
PlanetGen, RedHUD, SteamIntegrationKit, and VibeMMOUIKit. Two independent
generations are byte-identical at
`FE2927FEAEEF55BF92B01AB52996CE6A1CEFB60D3BCB0438014C8BF46A3BAE00`;
the payload-set signature is
`A9B618EE1B51E381AA02C5350C97D4BE96CF892C18429D094AFEDA715570CD77`.
The tool rejects missing or ambiguous plugin descriptors, links and reparse
points, hard links, unsafe or colliding paths, protected-hash drift, concurrent
input changes, output reuse, and output paths outside D diagnostics.

This is source-input storage readiness, not the storage itself. Empty
directories, named NTFS streams, ACLs, owners, timestamps, and generated plugin
binaries are outside the manifest. External copy, access-control verification,
and an isolated restore test remain required before the Phase 0
access-controlled-storage gate can close.

## RED World Authoring tool suite

The tool suite should become a project plugin with separate runtime data and
editor implementation modules:

```text
Plugins/Project/RedWorldAuthoring/
  Source/
    RedWorldAuthoringRuntime/
    RedWorldAuthoringEditor/
  Content/
    Editor/
    PCG/
    Validators/
```

### 1. Asset Library Curator

Purpose: turn noisy pack roots into a searchable approved library.

- reads Asset Registry data and provisional offline inventory;
- shows thumbnail, source pack, asset class, dependencies, dimensions, material
  slots, collision, LOD/Nanite, texture sizes, and estimated cost;
- assigns role/biome/surface/provenance tags;
- creates project-owned palette entries and shared Content Browser collections;
- creates no package copy until the user explicitly requests an adaptation;
- validates duplicate stable IDs, missing dependencies, forbidden vendor edits,
  unknown licenses, and unreviewed production references.

### 2. Radial Scatter Brush

Purpose: place assets naturally on any curved facet, cliff, cave, overhang, or
floating surface.

- samples through the shared planet surface query rather than world-down traces;
- supports surface, spline, and true 3D volume sampling;
- generates candidates with blue-noise or Poisson-disc spacing, never a visible
  grid;
- supports parent colonies with uneven satellite counts and asymmetric gaps;
- applies deterministic seed, tangent yaw, bounded tilt, scale, hue, and material
  variation;
- rejects by slope, curvature, surface tag, altitude, water distance, path
  distance, visibility reservation, collision, and protected POI;
- previews points, rejection reasons, density fields, and cost before baking;
- writes ISM/HISM/Foliage or PCG outputs, not thousands of ticking actors.

### 3. Path and Negative-Space Director

Purpose: stop foliage and props from forming rows, blocking traversal, or ignoring
level-design intent.

- consumes road, trail, river, shoreline, hub, landing-zone, and vista splines;
- supports attraction bands, exclusion bands, one-sided banks, and graded
  falloffs;
- widens clear space at turns, intersections, combat arenas, entrances, and
  sightline cones;
- biases rocks and plants toward ecologically plausible edges while preserving
  a clean center corridor;
- stores manual pins, erasures, and locked clusters so regeneration preserves
  artist edits.

### 4. Biome Mask Composer

Purpose: provide meaningful inputs instead of uniform density noise.

- combines elevation, slope, curvature, aspect, exposure, moisture, temperature,
  terrain material, water distance, path distance, and reservation fields;
- adds domain-warped macro variation and clustered micro variation;
- supports explicit artist-painted include/exclude/weight masks;
- visualizes each mask independently and the final weighted result;
- version-controls recipes separately from baked placement.

### 5. Hydrology and Shoreline Author

Purpose: create coherent oceans, lakes, rivers, beaches, and waterfalls.

- starts with authored sources, sinks, catchments, and flow splines;
- separates logical water graph, terrain carve/deformation, render surface,
  shoreline material, foam/spray, audio, buoyancy, and gameplay volume;
- derives beach bands from water level, local slope, material, wave exposure,
  and protected geometry;
- places waterfalls only where a flow edge crosses a meaningful vertical drop;
- uses Unreal's spline-based Water system where the surface representation is
  compatible, and a narrow PlanetGen adapter where it is not;
- never assumes a flat-landscape Z datum on the spherical planet.

### 6. World Validation and Patrol

Purpose: keep a growing world healthy.

- data validators enforce naming, provenance, budgets, collision, missing LOD,
  forbidden hard references, and production/test separation;
- World Partition builder jobs process one bounded region at a time;
- an automated patrol captures the same camera stations and Unreal Insights
  counters after material world changes;
- reports compare visual, game-thread, render-thread, GPU, streaming, and memory
  deltas;
- production promotion requires real-GPU review and protected-hash verification.

## Natural placement algorithm

A standard placement pass should be deterministic and layered:

1. Build a facet-local tangent frame from the planet center and authoring anchor.
2. Read a bounded region and all hard reservations.
3. Generate non-grid candidates with blue-noise or Poisson-disc sampling.
4. Warp the density domain at a scale larger than individual assets.
5. Evaluate biome, surface, slope, curvature, aspect, elevation, moisture,
   water, route, vista, collision, and ownership constraints.
6. Select a small number of ecological parent anchors.
7. Spawn unequal satellite colonies around parents with asymmetric gaps.
8. Reserve open corridors and intentional bare terrain.
9. Add small ground-cover islands last.
10. Preview rejection reasons and estimated instance/shadow/overdraw cost.
11. Let the artist pin, erase, or replace individual results.
12. Bake deterministic instances into the correct World Partition/Data Layer
    ownership and validate the cell.

This produces controlled irregularity. Pure random placement is not the goal;
readable composition with ecological logic is.

## Titan-to-RedMMO identity migration

### Preserve

- native module and script namespace `RedMMO`;
- `/Game/RedMMO` package paths;
- protected maps, artist handoffs, rollback archives, and historical evidence;
- canonical historical filenames and recorded commands;
- versioned `redmmotitan.*.v1` authoring schema IDs until an explicit v2
  migration exists;
- old packaged builds needed for rollback.

### Phase 0: dependency and rollback proof

- establish reproducible storage for Content and project plugins;
- hash protected checkpoints and current active build inputs;
- run Unreal Asset Registry reference checks for `/Script/Titan`, dormant Titan
  classes, and `Titan.*` gameplay tags;
- snapshot Steam launch/depot configuration and save/config locations;
- create an exact rollback manifest.

### Phase 1: user-facing branding and network boundary

- change display, product, hosted-session, and server labels to `RED MMO`;
- change active product/build identifiers intentionally so differently branded
  clients cannot enter the same multiplayer session accidentally;
- keep compatibility notes for saves and deployment.

### Phase 2: atomic project and target rename

In one checkpointed change:

- `Titan.uproject` -> `RedMMO.uproject`;
- `Titan.Target.cs` / `TitanTarget` -> `RedMMO.Target.cs` / `RedMMOTarget`;
- editor target equivalent;
- add explicit client and dedicated-server targets;
- `BuildTarget=RedMMO`;
- update live build, package, SteamPipe, verifier, and launch paths.

Regenerate project files, compile editor/game/server targets, run D3D12 runtime
and multiplayer evidence, then package only when the RAM gate is satisfied.

### Phase 3: remove dormant compatibility source

Only after Unreal proves no dependencies:

- archive or remove inactive `Source/Titan` and `Source/TitanEditor`;
- move useful validators into `RedMMOEditor`;
- remove dead `TitanMain`, `TitanLive`, and gameplay-tag entries or add exact
  redirects when a real dependency exists.

Never use a broad substring Core Redirect.

### Phase 4: infrastructure and path cleanup

- retain historical ProjectKnowledge and diagnostics exactly;
- update only live authority pointers and current tooling;
- introduce `D:\RedMMOWindowsData` for future diagnostics while keeping the old
  evidence root immutable;
- rename local repository and remote only after hard-coded absolute paths have
  been eliminated;
- use a temporary compatibility junction during the transition if required.

### Phase 5: Steam and save migration

- keep the existing Steam App ID unless distribution policy changes;
- change the launch executable/depot to `RedMMO.exe`;
- optionally ship a one-release compatibility launcher;
- perform a versioned, non-overwriting save/config copy;
- expect a new Windows Firewall executable prompt.

## Immediate sequence

1. Retain the read-only inventory, Asset Registry candidate catalog, and
   deterministic no-approval curation manifest.
2. Establish checksummed, access-controlled storage for Content and plugins.
3. Resolve provenance and license records, then review one small coherent
   material/static-mesh/foliage family; do not move its source packages.
4. Build one project-owned `RedWorldAssetPalette` and isolated asset-review map
   from that reviewed family.
5. Prototype the Radial Scatter Brush by extending PCG on one duplicate 200 m
   practice biome.
6. Validate player, jetpack, and ship views with real GPU evidence.
7. Begin the identity migration only after Phase 0 dependency and rollback proof.

That order makes the project cleaner immediately while avoiding an asset-reference,
packaging, Steam, or protected-map disaster.

## Primary Unreal references

- [Unreal Engine directory structure](https://dev.epicgames.com/documentation/en-us/unreal-engine/unreal-engine-directory-structure)
- [Recommended asset naming conventions](https://dev.epicgames.com/documentation/en-us/unreal-engine/recommended-asset-naming-conventions-in-unreal-engine-projects)
- [Asset Manager](https://dev.epicgames.com/documentation/en-us/unreal-engine/asset-management-in-unreal-engine)
- [Asset metadata](https://dev.epicgames.com/documentation/en-us/unreal-engine/asset-metadata-in-unreal-engine)
- [Content Browser filters and collections](https://dev.epicgames.com/documentation/en-us/unreal-engine/filters-and-collections-in-unreal-engine)
- [Data Validation](https://dev.epicgames.com/documentation/en-us/unreal-engine/data-validation-in-unreal-engine)
- [World Partition](https://dev.epicgames.com/documentation/en-us/unreal-engine/world-partition-in-unreal-engine)
- [One File Per Actor](https://dev.epicgames.com/documentation/en-us/unreal-engine/one-file-per-actor-in-unreal-engine)
- [World Partition Data Layers](https://dev.epicgames.com/documentation/en-us/unreal-engine/world-partition---data-layers-in-unreal-engine)
- [PCG data types](https://dev.epicgames.com/documentation/en-us/unreal-engine/procedural-content-generation-framework-data-types-reference-in-unreal-engine)
- [PCG generation modes](https://dev.epicgames.com/documentation/en-us/unreal-engine/using-pcg-generation-modes-in-unreal-engine)
- [Foliage Mode](https://dev.epicgames.com/documentation/en-us/unreal-engine/foliage-mode-in-unreal-engine)
- [Instanced Static Meshes](https://dev.epicgames.com/documentation/en-us/unreal-engine/instanced-static-mesh-component-in-unreal-engine)
- [Water System](https://dev.epicgames.com/documentation/en-us/unreal-engine/water-system-in-unreal-engine)
- [Editor scripting and automation](https://dev.epicgames.com/documentation/en-us/unreal-engine/scripting-and-automating-the-unreal-editor)
- [Scriptable Tools System](https://dev.epicgames.com/documentation/en-us/unreal-engine/scriptable-tools-system-in-unreal-engine)
- [Asset Redirectors](https://dev.epicgames.com/documentation/en-us/unreal-engine/asset-redirectors-in-unreal-engine)
- [Core Redirects](https://dev.epicgames.com/documentation/en-us/unreal-engine/core-redirects-in-unreal-engine)
