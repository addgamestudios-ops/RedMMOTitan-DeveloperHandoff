# RedMMOTitan grass GPU strategy

## Sources reviewed

- Christian Ortiz, `stylized-components`: <https://github.com/cortiz2894/stylized-components>
- Stylized Station, *How grass works in Ghost of Tsushima*: <https://www.youtube.com/watch?v=G8HH_pMKOhk>
- SimonDev, *How do Major Video Games Render Grass?*: <https://www.youtube.com/watch?v=bp7REZBV4P4>

The repository is an MIT-licensed Three.js / React Three Fiber / GLSL web demo, not an
Unreal Engine plugin. No JavaScript package, web runtime, shader source, or repository
asset is installed in RedMMOTitan. The review transfers architecture ideas only.

## Useful ideas

The sources converge on the same scalable structure:

1. scatter stable blade or clump instances from a jittered tile grid;
2. use clustering/noise so density can fall without looking uniformly sparse;
3. reject distant, off-screen, wrong-biome, underwater, and steep-slope samples early;
4. disable dense-grass shadows and other expensive lighting participation;
5. use simpler distant geometry and blend individual grass into a terrain-level far field;
6. keep wind in a cheap shared texture or vertex deformation path;
7. profile alpha overdraw, shadow passes, WPO, instance count, and upload cost separately.

## RedMMOTitan mapping

PlanetGen already provides GPU instancing, deterministic grid jitter, optional clustering,
player-radius/biome/slope/water rejection, asynchronous nearest-first scatter, a bounded
upload budget, disabled distance-field lighting, and shadow casting off by default.

The separate project-owned `ARedFoliageField` uses HISM components and collision-aware
cull distances, but previously forced every grass blade and accent plant to cast shadows.
The first safe optimization makes `Grass`, `AlienAccent`, and `SnowAccent` layers
shadowless and removes their distance-field lighting contribution. `DesertRock` and
`DesertCliff` retain their authored shadows. Existing 600 m visual-only and 900 m
collision-layer cull distances are unchanged.

The 50 km profile and game mode currently suppress procedural surface dressing, all
fallback counts default to zero, and no project-owned `UPlanetGenGrassAsset` package has
been found. The source change therefore prepares a cheaper enabled state; it is not
evidence of a current frame-time improvement.

## Deferred implementation gates

Do not add a compute-blade renderer or copy the web shaders before a representative
grass-enabled duplicate map exists. Evaluate these in order:

1. author one PlanetGen grass data asset with a low-overdraw clump mesh;
2. capture a fixed-camera D3D12 baseline with GPU Visualizer and Shader Complexity;
3. add per-asset render cull start/end and WPO-disable distance;
4. add a cheap distant mesh LOD or terrain tint/mask before shortening the visible radius;
5. compare matched player, jetpack, and ship-approach captures at 16:9 and 3440x1440;
6. accept only after grass remains stable across chunk refreshes and measured GPU time,
   overdraw, shadow cost, and instance count improve.

Static tests and compilation can prove wiring. Only matched real-GPU captures can prove
performance or visual acceptance.
