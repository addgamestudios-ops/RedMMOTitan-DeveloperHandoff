# Clean RedMMO Titan Gameplay Migration Plan

## Objective

Move the proven on-foot Titan gameplay presentation and controls into the clean
`D:/RedMMOTitanWindowsData/Projects/RedMMO` project without copying Titan map
geometry, PlanetGen presentation logic, vehicles, mining systems, or any code
that can rewrite the PPG home planet.

The target home map remains:

- `/Game/RedMMO/Maps/RedMMO_PPG_HomeWorld`
- current SHA-256: `1821ED915E924085A2D6B3E1A85984A0F207C116EFF32AC974E8F0B7CD217F87`

## Proven source stack

The legacy default map and GameMode resolve the following stack:

- map: `/Game/RedMMO/Maps/RedPlanetGen`
- GameMode: `/Script/RedMMO.RedGameMode`
- pawn class: `/Game/RedMMO/Characters/BP_RedGameplayCharacter`
- native pawn parent: `/Script/RedMMO.RedPlayerCharacter`
- player controller: `/Game/RedMMO/UI/BP_RedMultiplayerPlayerController`
- HUD: `/Script/RedMMO.RedHUD`
- HUD widget: `/Game/RedMMO/UI/WBP_VibeMMOHUD`
- AnimBP: `/Game/RedMMO/Characters/ABP_RedTrooperFemale`
- Control Rig: `/Game/RedMMO/Characters/CR_RedTrooperFocalAim`
- rifle: `/Game/RedMMO/Weapons/SK_RedTrooper_Rifle_A`
- core movement/gravity: `URedCharacterMovement`,
  `URadialGravityComponent`, and `RedGravityBodies`
- replicated projectile: `ARedBolt`

The source uses the legacy named mappings in `Config/DefaultInput.ini`,
including `MoveForward`, `MoveRight`, `Turn`, `LookUp`, `CameraZoom`, `Jump`,
`Fire`, `ADS`, `Sprint`, `Weapon1`, `Weapon2`, `Holster`, and the four ability
actions. Vehicle and debug mappings are not part of the first migration.

## Exact first-pass content roots

These packages are the reviewed roots, not yet a dependency-closed migration
set:

- `/Game/RedMMO/Characters/BP_RedGameplayCharacter`
- `/Game/RedMMO/Characters/ABP_RedTrooperFemale`
- `/Game/RedMMO/Characters/CR_RedTrooperFocalAim`
- `/Game/RedMMO/Weapons/SK_RedTrooper_Rifle_A`
- `/Game/RedMMO/UI/BP_RedMultiplayerPlayerController`
- `/Game/RedMMO/UI/WBP_VibeMMOHUD`
- `/Game/RedMMO/Materials/M_BoltTracer`
- `/Game/RedMMO/Materials/MI_RedGrapplePlasma`
- the seven reviewed rifle animation packages under
  `/Game/RedMMO/Anims/Rifle`
- the exact Action Trooper body, upper body, and rifle-B packages identified
  in the canonical audit
- `/Game/ProjectilesVol1/Effects/P_Flash_4`
- `/Game/ProjectilesVol1/Effects/P_Hit_3`
- `/Game/BeamsPack/VFX/Beams/NS_BeamOnly_02`
- `/Game/SoStylized/Sounds/Step/SC_Steps_Dirt`

Directories such as `Action_Trooper`, `ProjectilesVol1`, `BeamsPack`,
`Jet_Packs_Sci-Fi`, and `Vefects` must not be bulk-copied. The current UE 5.8
Asset Registry audit now closes the 22 reviewed roots at 728 `/Game` packages,
443,035,130 bytes, 3,389 hard edges, 81 soft edges, and zero unresolved
packages. That full result is an audit boundary, not a migration allowlist:
544 packages belong to `Action_Male_and_Female` customization fan-out.

The exact legacy `BP_RedGameplayCharacter` and
`BP_RedMultiplayerPlayerController` roots are therefore excluded from direct
migration. Each expands to 656 packages and all 544 customization packages.
The bounded strict payload instead contains 128 packages (118,284,320 bytes),
zero customization packages, and four already-present exact So Stylized
footstep packages. An optional animated payload contains 137 packages
(121,247,374 bytes), still zero customization packages, but remains gated by
FocalRig and Control Rig loadability. The exact package records and no-clobber
path plan are in `TitanGameplayCleanOverlapAndBoundedPayload_A11.json`.

## Native boundary

The clean RedMMO project is currently content-only: it has no `Source`
directory and no project-local plugins. Copying the Blueprint packages alone
would leave `/Script/RedMMO.RedPlayerCharacter` unresolved.

The clean project has no `Source/RedMMO`, C++ target files, `.uproject`
`Modules` stanza, or project-local plugins. The safe first implementation is a
project-owned runtime module named `RedMMO`, preserving `/Script/RedMMO.*`
class paths while porting only:

- a pruned, API-compatible on-foot `ARedPlayerCharacter`
- `URedCharacterMovement`
- `URadialGravityComponent`
- a pruned, API-compatible `RedGravityBodies`
- a pruned, API-compatible `ARedBolt`
- a clean `ARedPPGGameplayGameMode`
- the smallest controller/HUD adapter needed by the reviewed content

The clean GameMode must own only spawn, controller, pawn, and HUD selection.
It must not run Titan environment setup.

The class name alone is not enough: the port must expose every native property,
function, and component that the retained Blueprint serializes or calls.
`CR_RedTrooperFocalAim` contains hard `/Script/FocalRig.*` references, and
`WBP_VibeMMOHUD` hard-parents
`/Script/VibeMMOUIKit.VibeMMOHUDWidget`. The exact assets cannot load until
those plugins are proven target-compatible, or they are replaced through an
Unreal-aware project-owned Control Rig/HUD adapter path.

## Explicit exclusions

Do not migrate or call the following in the first on-foot slice:

- legacy `ARedGameMode::BeginPlay` environment mutation
- Titan water, shoreline, atmosphere, clouds, stars, foliage, biome, or
  dressing overrides
- `ACLMPlanet` or other PlanetGen-only surface ownership
- shuttle, mini-fighter, fighter possession, vehicle parking, or vehicle input
- mining, cloning, bots, orbital sites, or production-map helpers
- any Titan map, World Partition cell, terrain, PPG seed, or marker mutation
- any manual home-map stand-in

The legacy `ARedGameMode` is not safe to copy unchanged. Its BeginPlay path
alters PlanetGen presentation, removes/repairs dressing, rewrites water and
materials, configures atmosphere/clouds, and manages vehicles.

The raw `RedPlayerCharacter`, `RedGravityBodies`, and `RedBolt` sources are not
safe wholesale either: they retain vehicle, mining, resource, space-scenery,
shoreline, HUD, and PlanetGen-specific coupling.

## Blueprint-compatible native facade

The first clean `ARedPlayerCharacter` pass must preserve the legacy reflected
class facade. `BP_RedGameplayCharacter` serializes inherited native members and
default subobjects, so aggressively deleting or renaming reflected fields can
invalidate its unversioned native property layout before the Blueprint can even
load.

Raw package evidence confirms these inherited names: `SpringArm`, `Camera`,
`RadialGravity`, `FootstepTrail`, `WeaponMesh`, `PortraitCapture`,
`MinimapCapture`, `BoardGlow`, `HoverboardMesh`, `SpeedTrail`, the Jetpack mesh,
tank, exhaust, flame, plume, audio, light and smoke components, and native
callable `Turn`. The excluded systems remain behaviorally disabled, hidden, and
unbound, but their reflected compatibility names stay present in the first
pass. Remove them only after authoritative dependency closure, editor load,
Blueprint compile, reviewed reparent/resave, reload, and MapCheck prove a
specific removal safe.

The active first-pass core is limited to radial movement and grounding, the
spring-arm camera, visible Trooper presentation, on-foot input, movement
animation values, the rifle, aim/fire cosmetics and replication, and a stripped
`ARedBolt`. Vehicle, hoverboard, jetpack, grapple, mining, environment, and
space behavior is not ported merely because its compatibility component name is
retained.

## Package-registry provenance

The July 17 staged Titan package contains an authenticated
`Titan/AssetRegistry.bin`, extracted read-only to the D: diagnostics tree. Its
SHA-256 is
`C5CC2EA71F8D61F5BD54DEDECFEBEC4EB371A2E54CB246DDB8FF925E496401F8`.
It is useful only as a package-era cooked dependency cross-check. It cannot
replace the required current editor/source Asset Registry query, current plugin
validation, or Blueprint compile/load evidence.

## Dependency and implementation gates

1. The authenticated historical registry cross-check and current UE 5.8 hard
   and soft package closure are complete. Retain the historical detailed dump
   for searchable-name/management review because UE Python cannot reliably
   distinguish those non-package categories in this audit path.
2. Use the exact bounded strict payload and size manifest; never use directory
   roots or the 728-package full legacy graph as a copy instruction.
3. Create a rollback checkpoint of the clean project descriptor, Config,
   target home map, and any target package paths before writes.
4. Add `Source/RedMMO`, `RedMMO.Target.cs`, `RedMMOEditor.Target.cs`, a
   `.uproject` runtime module declaration, and the minimal `RedMMO` module;
   compile the clean
   editor and game targets before copying assets.
5. Validate the hard runtime plugin needs. The exact rig requires FocalRig and
   the exact HUD widget requires VibeMMOUIKit; both must be proven compatible or
   replaced with project-owned adapters. RedHUDRuntime also needs validation.
6. Prefer bridging the proven clean R11 Enhanced Input mapping to the native
   on-foot APIs. If legacy mappings are needed, merge only the reviewed named
   on-foot subset after collision audit; do not copy DefaultInput.ini wholesale
   or import vehicle/debug actions.
7. Migrate the exact dependency closure without overwriting packages. Retain
   path-referenced legacy/vendor packages at their exact `/Game` paths with
   no-clobber hashes, or use Unreal-aware duplication/remap plus fresh closure;
   ordinary filesystem relocation is forbidden.
8. Fresh-load every migrated package, compile Blueprints, run MapCheck, and
   require zero unresolved `/Script/RedMMO` parents.
9. Bind `ARedPPGGameplayGameMode` to a disposable or rollback-backed clean-home
   variant only after steps 1-8 pass.
10. Require real PIE evidence for third-person visibility, radial walking,
    running, jump/landing, grounded-only footsteps, aim, fire, muzzle/impact
    VFX, projectile authority, and home-map terrain preservation.
11. Require a separate listen-server/two-client regression before claiming
    multiplayer parity.

The reviewed source proves the fire hook, replicated bolt path, and muzzle/hit
VFX, but `WeaponFireSound` has no verified assignment. Audible gunfire parity
is not part of the current source proof.

## Current decision

The current hard/soft dependency closure, clean native runtime-module
bootstrap, radial kernel, and behavior-pruned on-foot combat tranche are
complete. `RedPlayerCharacter` now retains the reviewed radial movement,
camera, six FocalRig-free animation slots, rifle attachment, ADS/fire hooks,
server-authoritative `RedBolt` spawn, and replicated projectile cosmetics.
Serialized UE 5.8.1 Editor and Game builds pass. Direct migration of the
legacy character/controller Blueprints remains rejected because their
544-package customization fan-out is outside the clean on-foot goal.

The exact accepted content boundary is now present in clean RedMMO: the
135-package Trooper/rifle/projectile/FocalRig-free animation union fresh-loads
135 of 135 with zero dirty content or maps, and the separately reviewed
25-package StarSparrow closure is byte-identical to Titan after ten
no-clobber copies. FocalRig, customization, Vibe HUD, and legacy RedGameMode
remain excluded.

The next gate is not another broad copy. It is the project-owned PPG
surface-authority plus possessable StarSparrow native adapter, followed by
creation and compile of only the project-owned Trooper pawn, bolt, input, and
neutral PPG GameMode assets. The exact ship Blueprint must then package-load,
all new Blueprints must compile, and a fresh reload plus MapCheck must pass
before one checkpointed home-map bind. Neither copied content nor successful
native builds constitute character, ship, multiplayer, or visual runtime
acceptance.
