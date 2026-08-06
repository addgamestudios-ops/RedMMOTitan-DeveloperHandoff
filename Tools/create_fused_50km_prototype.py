"""Create or verify the rollback-safe fused 50 km PlanetGen prototype map.

The production map and the existing 50 km checkpoint are read-only rollback
points.  This command creates a third map from the checkpoint, assigns the
authenticated fused macro-heightfield asset to its single CLMPlanet actor, and
fails closed if either rollback file changes at any point.
"""

from __future__ import annotations

import hashlib
import os

import unreal


PRODUCTION_MAP = "/Game/RedMMO/Maps/RedPlanetGen"
CHECKPOINT_MAP = "/Game/RedMMO/Maps/RedPlanetGen_50km_Test"
PROTOTYPE_MAP = "/Game/RedMMO/Maps/RedPlanetGen_50km_FusedPrototype"
MACRO_ASSET = "/Game/RedMMO/Environment/DA_RED_Planet50Km_FusedHeightfield"
EXPECTED_RESOLUTION = 257
EXPECTED_RADIUS_CM = 795774.7154594767
EXPECTED_STAMP_COUNT = 27
MANAGED_REGION_TAG = "RedMMO50KmAutoRegionAnchor"
MACRO_BLEND = 1.0
MACRO_DETAIL_NOISE_CM = 1500.0
AUTHORING_SEA_HEIGHT_CM = 0.0
AUTHORING_MIN_HEIGHT_CM = -30000.0
AUTHORING_MAX_HEIGHT_CM = 30000.0
AUTHORING_SEA_LEVEL = (
    (AUTHORING_SEA_HEIGHT_CM - AUTHORING_MIN_HEIGHT_CM)
    / (AUTHORING_MAX_HEIGHT_CM - AUTHORING_MIN_HEIGHT_CM)
)


def file_fingerprint(filename: str) -> tuple[int, int, str]:
    digest = hashlib.sha256()
    with open(filename, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    stat = os.stat(filename)
    return stat.st_size, stat.st_mtime_ns, digest.hexdigest().upper()


def require_unchanged(filename: str, expected: tuple[int, int, str], label: str) -> None:
    actual = file_fingerprint(filename)
    if actual != expected:
        raise RuntimeError(
            f"{label} rollback map changed: before={expected} after={actual}"
        )


content_dir = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_content_dir())
production_filename = os.path.join(content_dir, "RedMMO", "Maps", "RedPlanetGen.umap")
checkpoint_filename = os.path.join(
    content_dir, "RedMMO", "Maps", "RedPlanetGen_50km_Test.umap"
)
prototype_filename = os.path.join(
    content_dir, "RedMMO", "Maps", "RedPlanetGen_50km_FusedPrototype.umap"
)

for filename, label in (
    (production_filename, "Production"),
    (checkpoint_filename, "50 km checkpoint"),
):
    if not os.path.isfile(filename):
        raise RuntimeError(f"{label} rollback map is missing: {filename}")

production_before = file_fingerprint(production_filename)
checkpoint_before = file_fingerprint(checkpoint_filename)
prototype_existed = os.path.isfile(prototype_filename)
prototype_before = file_fingerprint(prototype_filename) if prototype_existed else None

macro_asset = unreal.load_asset(MACRO_ASSET)
if macro_asset is None:
    raise RuntimeError(f"Fused macro-heightfield asset is unavailable: {MACRO_ASSET}")
if macro_asset.get_class().get_name() != "PlanetGenMacroHeightfieldAsset":
    raise RuntimeError(
        "Unexpected fused macro-heightfield asset class: "
        f"{macro_asset.get_class().get_name()}"
    )
if int(macro_asset.get_editor_property("resolution")) != EXPECTED_RESOLUTION:
    raise RuntimeError(
        "Fused macro-heightfield resolution drifted: "
        f"expected {EXPECTED_RESOLUTION}, got "
        f"{macro_asset.get_editor_property('resolution')}"
    )
if abs(float(macro_asset.get_editor_property("min_height_cm")) + 30000.0) > 0.01:
    raise RuntimeError("Fused macro-heightfield minimum decode is not -30000 cm")
if abs(float(macro_asset.get_editor_property("max_height_cm")) - 30000.0) > 0.01:
    raise RuntimeError("Fused macro-heightfield maximum decode is not +30000 cm")
if not bool(macro_asset.get_editor_property("fuse_shared_borders_on_capture")):
    raise RuntimeError("Fused macro-heightfield border capture is not enabled")
expected_face_samples = EXPECTED_RESOLUTION * EXPECTED_RESOLUTION
for face_property in (
    "positive_x",
    "negative_x",
    "positive_y",
    "negative_y",
    "positive_z",
    "negative_z",
):
    actual_samples = len(macro_asset.get_editor_property(face_property))
    if actual_samples != expected_face_samples:
        raise RuntimeError(
            f"Fused macro-heightfield {face_property} has {actual_samples} samples; "
            f"expected {expected_face_samples}"
        )

level_subsystem = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
if prototype_existed:
    if not level_subsystem.load_level(PROTOTYPE_MAP):
        raise RuntimeError(f"Failed to load existing fused prototype: {PROTOTYPE_MAP}")
    unreal.log(f"Fused 50 km prototype: loaded existing map {PROTOTYPE_MAP}")
else:
    if not level_subsystem.new_level_from_template(PROTOTYPE_MAP, CHECKPOINT_MAP):
        raise RuntimeError(
            f"Failed to create {PROTOTYPE_MAP} from checkpoint {CHECKPOINT_MAP}"
        )
    unreal.log(
        f"Fused 50 km prototype: created {PROTOTYPE_MAP} from read-only "
        f"checkpoint {CHECKPOINT_MAP}"
    )

# Loading/templating must not mutate either rollback point before we touch the
# isolated prototype actor.
require_unchanged(production_filename, production_before, "Production")
require_unchanged(checkpoint_filename, checkpoint_before, "50 km checkpoint")

actor_subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
planet_class = getattr(unreal, "CLMPlanet", None)
if planet_class is None:
    raise RuntimeError(
        "PlanetGen Python type unreal.CLMPlanet is unavailable; rebuild TitanEditor"
    )

planet_actors = [
    actor
    for actor in actor_subsystem.get_all_level_actors()
    if isinstance(actor, planet_class)
]
if len(planet_actors) != 1:
    raise RuntimeError(
        f"Expected exactly one CLMPlanet in prototype, found {len(planet_actors)}: "
        f"{[actor.get_path_name() for actor in planet_actors]}"
    )

planet = planet_actors[0]
planet_path = planet.get_path_name()
if not planet_path.startswith(f"{PROTOTYPE_MAP}."):
    raise RuntimeError(
        "Refusing to configure a PlanetGen actor outside the fused prototype: "
        f"{planet_path}"
    )

# The checkpoint already owns the complete 50 km profile, 27 authoring anchors,
# and 27 deterministic local-flattening stamps. Reconcile the macro runtime
# fields plus the authored water datum so the physical ocean intersects the
# same zero-centimeter coastline used to bake RED_Land_*.png. The checkpoint
# remains an untouched rollback point.
changed = not prototype_existed


def set_if_different(property_name: str, desired, *, tolerance: float | None = None) -> None:
    global changed
    current = planet.get_editor_property(property_name)
    if tolerance is None:
        differs = current != desired
    else:
        differs = abs(float(current) - float(desired)) > tolerance
    if differs:
        planet.set_editor_property(property_name, desired)
        changed = True


set_if_different("enable_macro_heightfield", True)
current_macro_asset = planet.get_editor_property("macro_heightfield_asset")
if (
    current_macro_asset is None
    or current_macro_asset.get_path_name() != macro_asset.get_path_name()
):
    planet.set_editor_property("macro_heightfield_asset", macro_asset)
    changed = True
set_if_different("macro_heightfield_blend", MACRO_BLEND, tolerance=0.000001)
set_if_different(
    "macro_detail_noise_amplitude_cm", MACRO_DETAIL_NOISE_CM, tolerance=0.01
)
set_if_different("sea_level", AUTHORING_SEA_LEVEL, tolerance=0.0001)
# PlanetGen's stock ocean is a complete sphere.  It is valid only once every
# authored ocean-mask region has a matching water presentation; on the current
# blank-canvas prototype it encloses low terrain and becomes an overhead shell
# during ascent.  Keep the authored sea datum/masks, but leave the global sphere
# disabled until masked ocean bodies are built by the environment pass.
set_if_different("enable_water", False)

# Fail closed on the inherited 50 km profile and authored stamp contract before
# saving.  These checks catch accidental templating from the production map.
expected_profile = {
    "planet_radius": (EXPECTED_RADIUS_CM, 1.0),
    "gravity_radius": (1591549.4309189534, 2.0),
    "tile_size": (200000.0, 0.1),
    "max_chunks_per_face": (8, 0.0),
    "resolution": (32, 0.0),
    "view_distance": (3.0, 0.001),
    "terrain_collision_view_distance": (1.5, 0.001),
    "min_height": (-30000.0, 0.1),
    "max_height": (30000.0, 0.1),
    "max_mountain_height": (30000.0, 0.1),
    "sea_level": (AUTHORING_SEA_LEVEL, 0.0001),
}
for property_name, (expected, tolerance) in expected_profile.items():
    actual = planet.get_editor_property(property_name)
    if abs(float(actual) - expected) > tolerance:
        raise RuntimeError(
            f"Prototype inherited the wrong {property_name}: expected {expected}, got {actual}"
        )
for property_name, expected in {
    "enable_water": False,
    "enable_foliage": False,
    "enable_grass": False,
    "use_preset": True,
}.items():
    actual = bool(planet.get_editor_property(property_name))
    if actual != expected:
        raise RuntimeError(
            f"Prototype inherited the wrong {property_name}: expected {expected}, got {actual}"
        )
if "SMOOTH" not in str(planet.get_editor_property("noise_preset")).upper():
    raise RuntimeError("Prototype did not inherit the Smooth PlanetGen noise preset")

terrain_stamps = list(planet.get_editor_property("terrain_stamps"))
if len(terrain_stamps) != EXPECTED_STAMP_COUNT:
    raise RuntimeError(
        f"Prototype inherited {len(terrain_stamps)} terrain stamps; "
        f"expected {EXPECTED_STAMP_COUNT}"
    )
stamp_ids = [int(stamp.get_editor_property("stable_id")) for stamp in terrain_stamps]
if stamp_ids != list(range(EXPECTED_STAMP_COUNT)):
    raise RuntimeError(f"Prototype terrain-stamp IDs drifted: {stamp_ids}")

anchor_class = getattr(unreal, "RedPlanetRegionAnchor", None)
if anchor_class is None:
    raise RuntimeError("Python type unreal.RedPlanetRegionAnchor is unavailable")
region_anchors = [
    actor
    for actor in actor_subsystem.get_all_level_actors()
    if isinstance(actor, anchor_class)
]
if len(region_anchors) != EXPECTED_STAMP_COUNT:
    raise RuntimeError(
        f"Prototype inherited {len(region_anchors)} region anchors; "
        f"expected {EXPECTED_STAMP_COUNT}"
    )
anchor_indices = sorted(
    int(anchor.get_editor_property("region_index")) for anchor in region_anchors
)
if anchor_indices != list(range(EXPECTED_STAMP_COUNT)):
    raise RuntimeError(f"Prototype region-anchor indices drifted: {anchor_indices}")
for anchor in region_anchors:
    if not anchor.get_path_name().startswith(f"{PROTOTYPE_MAP}."):
        raise RuntimeError(
            f"Region anchor exists outside the fused prototype: {anchor.get_path_name()}"
        )
    tags = [str(tag) for tag in anchor.get_editor_property("tags")]
    if MANAGED_REGION_TAG not in tags:
        raise RuntimeError(f"Prototype contains an unmanaged region anchor: {anchor.get_path_name()}")
    if anchor.get_actor_enable_collision():
        raise RuntimeError(f"Prototype region anchor has actor collision: {anchor.get_path_name()}")
    for component in anchor.get_components_by_class(unreal.PrimitiveComponent):
        if component.get_collision_enabled() != unreal.CollisionEnabled.NO_COLLISION:
            raise RuntimeError(
                f"Prototype region anchor component has collision: {component.get_path_name()}"
            )
        if bool(component.get_editor_property("generate_overlap_events")):
            raise RuntimeError(
                f"Prototype region anchor component has overlap events: {component.get_path_name()}"
            )

if not bool(planet.get_editor_property("enable_macro_heightfield")):
    raise RuntimeError("Prototype macro heightfield is not enabled")
assigned_asset = planet.get_editor_property("macro_heightfield_asset")
if assigned_asset is None or assigned_asset.get_path_name() != macro_asset.get_path_name():
    raise RuntimeError(
        f"Prototype macro asset assignment failed: expected {macro_asset.get_path_name()}, "
        f"got {assigned_asset}"
    )
if abs(float(planet.get_editor_property("macro_heightfield_blend")) - MACRO_BLEND) > 0.000001:
    raise RuntimeError("Prototype macro-heightfield blend verification failed")
if (
    abs(
        float(planet.get_editor_property("macro_detail_noise_amplitude_cm"))
        - MACRO_DETAIL_NOISE_CM
    )
    > 0.01
):
    raise RuntimeError("Prototype macro detail-noise verification failed")

if changed:
    if not level_subsystem.save_current_level():
        raise RuntimeError(f"Failed to save fused prototype: {PROTOTYPE_MAP}")
elif not os.path.isfile(prototype_filename):
    raise RuntimeError(f"Existing fused prototype package disappeared: {prototype_filename}")

if not os.path.isfile(prototype_filename):
    raise RuntimeError(f"Fused prototype package was not persisted: {prototype_filename}")

require_unchanged(production_filename, production_before, "Production")
require_unchanged(checkpoint_filename, checkpoint_before, "50 km checkpoint")

prototype_after = file_fingerprint(prototype_filename)
if not changed and prototype_before != prototype_after:
    raise RuntimeError(
        "Idempotent fused-prototype verification rewrote the map unexpectedly: "
        f"before={prototype_before} after={prototype_after}"
    )

unreal.log(
    "RED_FUSED_50KM_PROTOTYPE_READY "
    f"map={PROTOTYPE_MAP} actor={planet_path} asset={macro_asset.get_path_name()} "
    f"resolution={EXPECTED_RESOLUTION} blend={MACRO_BLEND:g} "
    f"detail_noise_cm={MACRO_DETAIL_NOISE_CM:g} "
    f"sea_height_cm={AUTHORING_SEA_HEIGHT_CM:g} "
    f"sea_level={AUTHORING_SEA_LEVEL:g} stamps={len(terrain_stamps)} "
    f"changed={int(changed)} prototype_sha256={prototype_after[2]} "
    f"production_sha256={production_before[2]} "
    f"checkpoint_sha256={checkpoint_before[2]}"
)
