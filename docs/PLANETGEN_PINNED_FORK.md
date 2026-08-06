# PlanetGen pinned fork for the 50 km test

The active local fork is `Plugins/PlanetGenPinned_1_4_0_RedMMO`. It was copied from the installed PlanetGen 1.4.0 plugin at `D:\UE_5.8\Engine\Plugins\Marketplace\PlanetGe5e8f23ed72d1V5` without changing the engine installation.

The folder name is unique, but its descriptor and runtime module deliberately remain `PlanetGen`. Unreal therefore resolves the project copy ahead of the Marketplace copy while preserving existing C++ module dependencies, exported Blueprint/UObject paths, and `/PlanetGen/...` content references. Removing the local folder while Unreal and UBT are closed restores the engine copy.

The repository currently ignores `Plugins/*` because these are licensed/local dependencies. The implementation is active in the workspace and package builds, but it will not appear in a normal Git commit unless the repository's licensed-plugin policy is deliberately changed.

## Modified fork files

- `PlanetGen.uplugin`: identifies the pinned RedMMO phase-1 fork; keeps module identity unchanged.
- `Source/PlanetGen/Public/PlanetGen/CLMPlanet.h`
- `Source/PlanetGen/Private/PlanetGen/CLMPlanet.cpp`
- `Source/PlanetGen/Public/PlanetGen/CLMPlanetChunk.h`
- `Source/PlanetGen/Private/PlanetGen/CLMPlanetChunk.cpp`
- `REDMMO_FORK.md`: detailed profile, rollback, limitations, and verification notes inside the local plugin.

Every other copied source/content/config/resource file matched the installed plugin by SHA-256 after the fork was created.

## Implemented foundation

- The planet actor's height range, sea level, snow thresholds, and rock thresholds are copied into the noise generator before its layers are compiled.
- `ViewDistance` is now a real angular cap, including edge coverage and unload hysteresis.
- All replicated-player/player-controlled pawns are streaming sources; additional non-pawn actors can be assigned explicitly.
- Stream/collision tests use the same tangent-corrected chunk centres as mesh generation.
- Terrain collision is cooked only in a smaller configurable near ring. Chunks rebuild when crossing that ring.
- Terrain and grass workers carry a build-generation token and reject stale uploads after a pooled actor is recycled or assigned a new key.
- `LineTraceActiveTerrain` and `SweepActiveTerrain` query only exact active terrain root meshes, walk past unrelated `WorldDynamic` blockers, and resolve equal-distance seam hits by deterministic chunk key.
- The actor exposes **Apply RedMMO 50 km Test Profile**, which configures a 50 km circumference (`795,774.715 cm` radius) smoke profile with a conservative 216-actor pool, 32-vertex resolution, Smooth noise, near-ring collision, and procedural foliage/grass disabled.

No production map binary was edited. Create a duplicated 50 km test map before applying and saving the profile.

## Verification and remaining risk

UnrealBuildTool discovered this project-local source override without a duplicate-plugin error. Unreal Header Tool completed successfully and wrote 32 generated files. Subsequent serial `TitanEditor Win64 Development` builds compiled and linked the fork and its runtime automation.

The active-terrain API compiled in `TitanEditor` and passed real cooked-collision line, sphere, and 37-degree rotated-capsule coverage plus all five fused-runtime regressions on 2026-07-15. It queries currently active collision; the fork still has no generation-aware Chaos cook-completion marker for the brief pooled rebuild window.

The upstream fixed pool still allocates `6 * N^2` actors and the terrain still has one mesh resolution with no LOD rings. The smoke profile bounds the current pool to 216 actors; dynamic pooling/LOD is the next scalability step before increasing chunk density.
