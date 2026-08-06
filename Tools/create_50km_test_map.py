"""Create/configure the rollback-safe RedPlanetGen_50km_Test map in Unreal Editor.

Run only after the project-local PlanetGen fork and RedMMO module compile. The production
RedPlanetGen asset is never modified or deleted.
"""

import hashlib
import math
import os

import unreal


SOURCE_MAP = "/Game/RedMMO/Maps/RedPlanetGen"
TEST_MAP = "/Game/RedMMO/Maps/RedPlanetGen_50km_Test"
REGION_COUNT = 27
MANAGED_REGION_TAG = "RedMMO50KmAutoRegionAnchor"


level_subsystem = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)

# EditorAssetLibrary explicitly excludes levels from its asset-existence and duplication
# contract. Use package-to-file checks so Python never holds a UWorld reference across a map
# load; FPyReferenceCollector would otherwise prevent Unreal from garbage-collecting the old
# world and trip the editor's fatal world-leak guard.
content_dir = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_content_dir())
source_filename = os.path.join(content_dir, "RedMMO", "Maps", "RedPlanetGen.umap")
test_filename = os.path.join(content_dir, "RedMMO", "Maps", "RedPlanetGen_50km_Test.umap")


def file_fingerprint(filename):
    digest = hashlib.sha256()
    with open(filename, "rb") as source_file:
        for block in iter(lambda: source_file.read(1024 * 1024), b""):
            digest.update(block)
    stat = os.stat(filename)
    return stat.st_size, stat.st_mtime_ns, digest.hexdigest()

if not os.path.isfile(source_filename):
    raise RuntimeError(f"Source map does not exist: {source_filename}")

source_fingerprint_before = file_fingerprint(source_filename)

if not os.path.isfile(test_filename):
    if not level_subsystem.new_level_from_template(TEST_MAP, SOURCE_MAP):
        raise RuntimeError(f"Failed to create {TEST_MAP} from template {SOURCE_MAP}")
    unreal.log(f"50 km map: created {TEST_MAP} from read-only template {SOURCE_MAP}")
else:
    if not level_subsystem.load_level(TEST_MAP):
        raise RuntimeError(f"Failed to load existing test map: {TEST_MAP}")
    unreal.log(f"50 km map: preserving and updating existing {TEST_MAP}")

actor_subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
planet_class = getattr(unreal, "CLMPlanet", None)
if planet_class is None:
    raise RuntimeError(
        "PlanetGen Python type unreal.CLMPlanet is unavailable; verify the project-local "
        "PlanetGen plugin is enabled and the TitanEditor target was rebuilt"
    )

planet_actors = [
    actor
    for actor in actor_subsystem.get_all_level_actors()
    if isinstance(actor, planet_class)
]

if len(planet_actors) != 1:
    names = [actor.get_name() for actor in planet_actors]
    raise RuntimeError(f"Expected exactly one CLMPlanet actor, found {len(planet_actors)}: {names}")

planet = planet_actors[0]
planet_path = planet.get_path_name()
if not planet_path.startswith(f"{TEST_MAP}."):
    raise RuntimeError(
        "Refusing to configure a PlanetGen actor outside the isolated test map: "
        f"{planet_path}"
    )
# Use the native reflected UFUNCTION name so execution does not depend on how a particular UE
# Python build snake-cases the adjacent "MMO50Km" acronym/digit sequence. Object.call_method is
# an engine-provided escape hatch specifically for reflected functions without generated glue.
planet.call_method("ApplyRedMMO50KmTestProfile")

# Fail closed rather than saving a partially configured map if reflected names or the pinned
# profile drift. The C++ function is the source of truth; these checks are postconditions only.
expected_properties = {
    "planet_radius": (795774.7154594767, 1.0),
    "gravity_radius": (1591549.4309189534, 2.0),
    "tile_size": (200000.0, 0.1),
    "max_chunks_per_face": (8, 0),
    "resolution": (32, 0),
    "view_distance": (3.0, 0.001),
    "terrain_collision_view_distance": (1.5, 0.001),
    "min_height": (-30000.0, 0.1),
    "max_height": (30000.0, 0.1),
    "max_mountain_height": (30000.0, 0.1),
    "sea_level": (0.45, 0.0001),
}
for property_name, (expected, tolerance) in expected_properties.items():
    actual = planet.get_editor_property(property_name)
    if abs(float(actual) - float(expected)) > tolerance:
        raise RuntimeError(
            f"50 km profile verification failed for {property_name}: "
            f"expected {expected}, got {actual}"
        )

for property_name, expected in {
    "enable_foliage": False,
    "enable_grass": False,
    "use_preset": True,
}.items():
    actual = bool(planet.get_editor_property(property_name))
    if actual != expected:
        raise RuntimeError(
            f"50 km profile verification failed for {property_name}: "
            f"expected {expected}, got {actual}"
        )

noise_preset = planet.get_editor_property("noise_preset")
if "SMOOTH" not in str(noise_preset).upper():
    raise RuntimeError(f"50 km profile expected Smooth noise, got {noise_preset}")

# Reconcile editor-only region anchors. The script owns only actors carrying its management tag;
# encountering a manually placed anchor fails closed so user-authored work is never overwritten.
anchor_class = getattr(unreal, "RedPlanetRegionAnchor", None)
if anchor_class is None:
    raise RuntimeError(
        "Python type unreal.RedPlanetRegionAnchor is unavailable; rebuild TitanEditor after "
        "adding the reflected RED region authoring bridge"
    )


def tag_strings(actor):
    return [str(tag) for tag in actor.get_editor_property("tags")]


def vector_distance(a, b):
    return math.sqrt(
        ((float(a.x) - float(b.x)) ** 2)
        + ((float(a.y) - float(b.y)) ** 2)
        + ((float(a.z) - float(b.z)) ** 2)
    )


def assert_test_map_actor(actor, purpose):
    actor_path = actor.get_path_name()
    if not actor_path.startswith(f"{TEST_MAP}."):
        raise RuntimeError(
            f"Refusing to {purpose} a RED region anchor outside the isolated test map: "
            f"{actor_path}"
        )


all_region_anchors = [
    actor
    for actor in actor_subsystem.get_all_level_actors()
    if isinstance(actor, anchor_class)
]
for actor in all_region_anchors:
    assert_test_map_actor(actor, "inspect or mutate")

unmanaged_region_anchors = [
    actor for actor in all_region_anchors if MANAGED_REGION_TAG not in tag_strings(actor)
]
if unmanaged_region_anchors:
    paths = [actor.get_path_name() for actor in unmanaged_region_anchors]
    raise RuntimeError(
        "Unmanaged/manual RED region anchors exist; refusing to mutate them: " f"{paths}"
    )

managed_by_index = {}
managed_duplicates = []
for actor in sorted(all_region_anchors, key=lambda value: value.get_path_name()):
    region_index = int(actor.get_editor_property("region_index"))
    if region_index < 0 or region_index >= REGION_COUNT or region_index in managed_by_index:
        managed_duplicates.append(actor)
    else:
        managed_by_index[region_index] = actor

for duplicate in managed_duplicates:
    if MANAGED_REGION_TAG not in tag_strings(duplicate):
        raise RuntimeError(f"Refusing to delete an unmanaged actor: {duplicate.get_path_name()}")
    if not actor_subsystem.destroy_actor(duplicate):
        raise RuntimeError(f"Failed to delete managed duplicate: {duplicate.get_path_name()}")

spawned_count = 0
reused_count = 0
planet_center = planet.get_actor_location()
planet_radius_cm = float(planet.get_editor_property("planet_radius"))
managed_tag_name = unreal.Name(MANAGED_REGION_TAG)

for region_index in range(REGION_COUNT):
    anchor = managed_by_index.get(region_index)
    if anchor is None:
        anchor = actor_subsystem.spawn_actor_from_class(
            anchor_class, unreal.Vector(), unreal.Rotator()
        )
        if anchor is None:
            raise RuntimeError(f"Failed to spawn RED region anchor {region_index}")
        assert_test_map_actor(anchor, "configure")
        managed_by_index[region_index] = anchor
        spawned_count += 1
    else:
        reused_count += 1

    anchor.set_editor_property("region_index", region_index)
    anchor.set_editor_property("planet_center", planet_center)
    anchor.set_editor_property("planet_radius_cm", planet_radius_cm)
    anchor.set_editor_property("position_at_region_site", True)
    anchor.set_editor_property("orient_to_surface", True)
    anchor.set_editor_property("is_spatially_loaded", False)
    if MANAGED_REGION_TAG not in tag_strings(anchor):
        anchor.set_editor_property(
            "tags", list(anchor.get_editor_property("tags")) + [managed_tag_name]
        )
    anchor.call_method("RefreshFromRegionService")
    anchor.set_actor_enable_collision(False)
    anchor.set_actor_label(f"RED_RegionAnchor_{region_index:02d}")

    for component in anchor.get_components_by_class(unreal.PrimitiveComponent):
        component.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
        component.set_editor_property("generate_overlap_events", False)

# Re-query from the loaded level rather than trusting local references. This is both the save gate
# and the contract consumed later by PCG Get Actor Data / Get Actor Property nodes.
verified_anchors = [
    actor
    for actor in actor_subsystem.get_all_level_actors()
    if isinstance(actor, anchor_class) and MANAGED_REGION_TAG in tag_strings(actor)
]
if len(verified_anchors) != REGION_COUNT:
    raise RuntimeError(
        f"Expected {REGION_COUNT} managed RED region anchors, found {len(verified_anchors)}"
    )

verified_indices = sorted(
    int(actor.get_editor_property("region_index")) for actor in verified_anchors
)
if verified_indices != list(range(REGION_COUNT)):
    raise RuntimeError(f"RED region anchor indices are not unique 0..26: {verified_indices}")

for anchor in verified_anchors:
    region_index = int(anchor.get_editor_property("region_index"))
    actor_path = anchor.get_path_name()
    if not actor_path.startswith(f"{TEST_MAP}."):
        raise RuntimeError(f"RED region anchor exists outside the test map: {actor_path}")
    if anchor.get_actor_label() != f"RED_RegionAnchor_{region_index:02d}":
        raise RuntimeError(
            f"Unexpected RED region anchor label for {region_index}: {anchor.get_actor_label()}"
        )

    tags = tag_strings(anchor)
    archetype_tag = str(anchor.get_editor_property("archetype_tag"))
    expected_tags = {
        MANAGED_REGION_TAG,
        "RedPlanetRegion",
        f"RedRegion_{region_index:02d}",
        f"RedBiome_{archetype_tag}",
    }
    missing_tags = expected_tags.difference(tags)
    if missing_tags:
        raise RuntimeError(
            f"RED region anchor {region_index} is missing tags: {sorted(missing_tags)}"
        )

    unit_site = anchor.get_editor_property("unit_site")
    expected_location = unreal.Vector(
        float(planet_center.x) + (float(unit_site.x) * planet_radius_cm),
        float(planet_center.y) + (float(unit_site.y) * planet_radius_cm),
        float(planet_center.z) + (float(unit_site.z) * planet_radius_cm),
    )
    if vector_distance(anchor.get_actor_location(), expected_location) > 1.0:
        raise RuntimeError(
            f"RED region anchor {region_index} is not on its deterministic site: "
            f"actual={anchor.get_actor_location()} expected={expected_location}"
        )
    if vector_distance(anchor.get_actor_up_vector(), unit_site) > 0.0001:
        raise RuntimeError(
            f"RED region anchor {region_index} is not surface-oriented: "
            f"up={anchor.get_actor_up_vector()} expected={unit_site}"
        )
    if bool(anchor.get_editor_property("is_spatially_loaded")):
        raise RuntimeError(
            f"RED region anchor {region_index} must be always loaded for reconciliation"
        )
    if anchor.get_actor_enable_collision():
        raise RuntimeError(f"RED region anchor {region_index} has actor collision enabled")
    for component in anchor.get_components_by_class(unreal.PrimitiveComponent):
        if component.get_collision_enabled() != unreal.CollisionEnabled.NO_COLLISION:
            raise RuntimeError(
                f"RED region anchor {region_index} component has collision: {component.get_name()}"
            )
        if bool(component.get_editor_property("generate_overlap_events")):
            raise RuntimeError(
                f"RED region anchor {region_index} component overlaps: {component.get_name()}"
            )

# Reconcile the generic PlanetGen terrain stamps from the verified region-service metadata. The
# isolated 50 km test map owns this entire stamp array: StableId 0..26 is the deterministic bridge
# between the editor-only anchors and the runtime terrain worker capture. A field-by-field compare
# avoids dirtying/resaving the map when a fresh second run already matches the desired data.
terrain_stamp_class = getattr(unreal, "PlanetGenTerrainStamp", None)
terrain_stamp_mode_class = getattr(unreal, "PlanetGenTerrainStampMode", None)
if terrain_stamp_class is None or terrain_stamp_mode_class is None:
    raise RuntimeError(
        "PlanetGen terrain-stamp Python types are unavailable; rebuild TitanEditor after adding "
        "the reflected FPlanetGenTerrainStamp API"
    )

sample_base_at_center_mode = getattr(
    terrain_stamp_mode_class, "SAMPLE_BASE_AT_CENTER", None
)
if sample_base_at_center_mode is None:
    raise RuntimeError(
        "PlanetGenTerrainStampMode.SAMPLE_BASE_AT_CENTER is unavailable; reflected enum drifted"
    )


def terrain_stamp_matches_spec(stamp, spec):
    return (
        bool(stamp.get_editor_property("enabled")) is True
        and int(stamp.get_editor_property("stable_id")) == spec["stable_id"]
        and vector_distance(
            stamp.get_editor_property("surface_direction"), spec["surface_direction"]
        )
        <= 0.000001
        and abs(
            float(stamp.get_editor_property("core_radius_cm")) - spec["core_radius_cm"]
        )
        <= 0.01
        and abs(
            float(stamp.get_editor_property("feather_radius_cm"))
            - spec["feather_radius_cm"]
        )
        <= 0.01
        and stamp.get_editor_property("mode") == sample_base_at_center_mode
        and abs(float(stamp.get_editor_property("target_height_cm"))) <= 0.001
    )


sorted_verified_anchors = sorted(
    verified_anchors, key=lambda value: int(value.get_editor_property("region_index"))
)
desired_terrain_stamp_specs = []
desired_terrain_stamps = []
for anchor in sorted_verified_anchors:
    region_index = int(anchor.get_editor_property("region_index"))
    spec = {
        "stable_id": region_index,
        "surface_direction": anchor.get_editor_property("unit_site"),
        "core_radius_cm": float(
            anchor.get_editor_property("suggested_flatten_core_radius_cm")
        ),
        "feather_radius_cm": float(
            anchor.get_editor_property("suggested_flatten_blend_radius_cm")
        ),
    }
    if spec["core_radius_cm"] <= 0.0 or spec["feather_radius_cm"] < 0.0:
        raise RuntimeError(
            f"RED region anchor {region_index} supplied invalid terrain-stamp radii: "
            f"core={spec['core_radius_cm']} feather={spec['feather_radius_cm']}"
        )

    stamp = terrain_stamp_class()
    stamp.set_editor_property("enabled", True)
    stamp.set_editor_property("stable_id", spec["stable_id"])
    stamp.set_editor_property("surface_direction", spec["surface_direction"])
    stamp.set_editor_property("core_radius_cm", spec["core_radius_cm"])
    stamp.set_editor_property("feather_radius_cm", spec["feather_radius_cm"])
    stamp.set_editor_property("mode", sample_base_at_center_mode)
    stamp.set_editor_property("target_height_cm", 0.0)
    desired_terrain_stamp_specs.append(spec)
    desired_terrain_stamps.append(stamp)

current_terrain_stamps = list(planet.get_editor_property("terrain_stamps"))
terrain_stamps_changed = len(current_terrain_stamps) != REGION_COUNT or any(
    not terrain_stamp_matches_spec(current, desired)
    for current, desired in zip(current_terrain_stamps, desired_terrain_stamp_specs)
)
if terrain_stamps_changed:
    planet.set_editor_property("terrain_stamps", desired_terrain_stamps)

# Re-read reflected values after reconciliation. This is the save gate for count, deterministic
# order, unique IDs, direction, radii, enabled state, target mode, and target height.
verified_terrain_stamps = list(planet.get_editor_property("terrain_stamps"))
if len(verified_terrain_stamps) != REGION_COUNT:
    raise RuntimeError(
        f"Expected {REGION_COUNT} PlanetGen terrain stamps, found "
        f"{len(verified_terrain_stamps)}"
    )

verified_stamp_ids = [
    int(stamp.get_editor_property("stable_id")) for stamp in verified_terrain_stamps
]
if verified_stamp_ids != list(range(REGION_COUNT)):
    raise RuntimeError(
        "PlanetGen terrain stamps are not deterministically sorted with unique IDs 0..26: "
        f"{verified_stamp_ids}"
    )

for stamp, spec in zip(verified_terrain_stamps, desired_terrain_stamp_specs):
    if not terrain_stamp_matches_spec(stamp, spec):
        raise RuntimeError(
            f"PlanetGen terrain stamp {spec['stable_id']} failed reflected postconditions"
        )

if file_fingerprint(source_filename) != source_fingerprint_before:
    raise RuntimeError("Production map changed before the isolated test map save gate")

if not level_subsystem.save_current_level():
    raise RuntimeError(f"Failed to save configured test map: {TEST_MAP}")

source_fingerprint_after = file_fingerprint(source_filename)
if source_fingerprint_after != source_fingerprint_before:
    raise RuntimeError(
        "Production map changed while configuring the isolated test map: "
        f"before={source_fingerprint_before} after={source_fingerprint_after}"
    )

unreal.log(
    "RED_50KM_REGION_ANCHORS_READY "
    f"count={len(verified_anchors)} spawned={spawned_count} reused={reused_count} "
    f"removed_managed_duplicates={len(managed_duplicates)} collision=disabled"
)
unreal.log(
    "RED_50KM_TERRAIN_STAMPS_READY "
    f"count={len(verified_terrain_stamps)} changed={int(terrain_stamps_changed)} "
    "mode=sample_base_at_center"
)
unreal.log(
    "RED_50KM_TEST_MAP_READY "
    f"map={TEST_MAP} actor={planet.get_path_name()} "
    "circumference_cm=5000000 radius_cm=795774.715 gravity_radius_cm=1591549.431"
)
