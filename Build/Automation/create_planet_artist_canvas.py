"""Create a minimal, non-destructive PlanetGen artist-canvas map.

This script is intended for UnrealEditor ``-ExecutePythonScript`` use.  It
duplicates the protected fused prototype, edits only the duplicate, and saves
only that duplicate.  The source maps are never loaded as the current editing
world and are never saved.

The cleanup policy is deliberately an allow-list.  A blank environmental-art
handoff is safer when an unfamiliar gameplay actor is removed than when a new
ship, UI controller, water shell, cloud rig, or collision helper silently slips
through a name-based deny-list.
"""

from __future__ import annotations

import datetime
import json
import os
import traceback
from typing import Any, Dict, List, Optional, Sequence, Tuple

import unreal


SOURCE_MAP = "/Game/RedMMO/Maps/RedPlanetGen_50km_FusedPrototype"
DESTINATION_MAP = "/Game/RedMMO/Maps/RedPlanetGen_50km_ArtistCanvas"
FUSED_HEIGHTFIELD_PACKAGE = (
    "/Game/RedMMO/Environment/DA_RED_Planet50Km_FusedHeightfield"
)
AUDIT_OUTPUT = os.environ.get(
    "RED_ARTIST_CANVAS_AUDIT",
    r"D:\RedMMOTitanWindowsData\ArtistHandoff\artist_canvas_actor_audit.json",
)

# These packages are rollback/protected inputs.  The script is hard-coded to
# create one new map and refuses to make any of these the current mutation
# target.
PROTECTED_MAPS = {
    "/Game/RedMMO/Maps/RedPlanetGen",
    SOURCE_MAP,
}

POLICY_VERSION = "artist-canvas-v1-strict-allow-list"

# Native engine actors that are useful in an otherwise blank environment map.
# Blueprint subclasses are not retained: a Blueprint may carry arbitrary game
# logic even when its display name resembles a light or camera.
BASIC_NATIVE_CLASSES = {
    "DirectionalLight": "basic_directional_light",
    "SkyLight": "basic_sky_light",
    "SkyAtmosphere": "basic_sky_atmosphere",
    "CameraActor": "editor_preview_camera",
    "PlayerStart": "editor_preview_player_start",
    "TargetPoint": "engine_only_region_authoring_guide",
}

# Actors Unreal owns as part of the level package.  They may not be destroyable
# and do not represent environmental or gameplay content.
LEVEL_INFRASTRUCTURE_CLASSES = {
    "WorldSettings",
    "LevelScriptActor",
    "DefaultPhysicsVolume",
    "WorldDataLayers",
    "WorldPartitionMiniMap",
}


def _utc_now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _package_from_object_path(path: str) -> str:
    """Return /Game/Foo/Asset from /Game/Foo/Asset.Asset[:Subobject]."""

    clean = str(path).split(":", 1)[0]
    return clean.split(".", 1)[0]


def _write_audit(payload: Dict[str, Any]) -> None:
    """Atomically replace the external JSON audit file."""

    output_dir = os.path.dirname(AUDIT_OUTPUT)
    if not output_dir:
        raise RuntimeError("Audit output must include a directory")
    os.makedirs(output_dir, exist_ok=True)
    temporary = AUDIT_OUTPUT + ".tmp"
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
    os.replace(temporary, AUDIT_OUTPUT)


def _current_world_package() -> str:
    world = unreal.EditorLevelLibrary.get_editor_world()
    if not world:
        raise RuntimeError("Unreal Editor has no current editor world")
    return _package_from_object_path(world.get_path_name())


def _assert_destination_is_current() -> None:
    current = _current_world_package()
    if current in PROTECTED_MAPS:
        raise RuntimeError(
            "Mutation guard stopped the script on protected map: " + current
        )
    if current != DESTINATION_MAP:
        raise RuntimeError(
            "Mutation guard expected current map "
            f"{DESTINATION_MAP}, found {current}"
        )


def _class_record(actor: unreal.Actor) -> Tuple[str, str]:
    actor_class = actor.get_class()
    if not actor_class:
        return "", ""
    return actor_class.get_name(), actor_class.get_path_name()


def _actor_components(actor: unreal.Actor) -> List[str]:
    try:
        components = actor.get_components_by_class(unreal.ActorComponent)
    except Exception:
        return []
    paths = []
    for component in components or []:
        component_class = component.get_class()
        paths.append(
            component_class.get_path_name() if component_class else component.get_name()
        )
    return sorted(set(paths))


def _actor_tags(actor: unreal.Actor) -> List[str]:
    try:
        return sorted(str(tag) for tag in actor.get_editor_property("tags"))
    except Exception:
        return []


def _actor_record(actor: unreal.Actor) -> Dict[str, Any]:
    class_name, class_path = _class_record(actor)
    location = actor.get_actor_location()
    return {
        "label": actor.get_actor_label(),
        "name": actor.get_name(),
        "class_name": class_name,
        "class_path": class_path,
        "folder": str(actor.get_folder_path()),
        "tags": _actor_tags(actor),
        "component_classes": _actor_components(actor),
        "location_cm": [
            round(location.x, 3),
            round(location.y, 3),
            round(location.z, 3),
        ],
    }


def _is_planet_terrain_actor(actor: unreal.Actor) -> bool:
    class_name, class_path = _class_record(actor)
    if class_name in {"CLMPlanet", "CLMPlanetSunSky"}:
        return True

    # This covers Blueprint subclasses without trusting their asset names.
    for python_type_name in ("CLMPlanetSunSky", "CLMPlanet"):
        python_type = getattr(unreal, python_type_name, None)
        if python_type is not None:
            try:
                if isinstance(actor, python_type):
                    return True
            except TypeError:
                pass

    return class_path in {
        "/Script/PlanetGen.CLMPlanet",
        "/Script/PlanetGen.CLMPlanetSunSky",
    }


def _is_level_infrastructure_actor(actor: unreal.Actor) -> bool:
    """Recognize unavoidable level-package actors, including custom subclasses."""

    class_name, _ = _class_record(actor)
    if class_name in LEVEL_INFRASTRUCTURE_CLASSES:
        return True
    for python_type_name in (
        "WorldSettings",
        "LevelScriptActor",
        "DefaultPhysicsVolume",
        "WorldDataLayers",
        "WorldPartitionMiniMap",
    ):
        python_type = getattr(unreal, python_type_name, None)
        if python_type is None:
            continue
        try:
            if isinstance(actor, python_type):
                return True
        except TypeError:
            pass
    return False


def _classify_actor(actor: unreal.Actor) -> Tuple[str, str]:
    """Return (retain|delete, machine-readable reason)."""

    class_name, class_path = _class_record(actor)
    label = actor.get_actor_label()

    if _is_planet_terrain_actor(actor):
        return "retain", "planetgen_fused_terrain"

    if class_name == "CLMPlanetChunk" or class_path.endswith(".CLMPlanetChunk"):
        return "delete", "generated_planet_chunk_rebuilt_by_planet_actor"

    # This is the exact vendor SunSky Blueprint inventoried in the protected
    # source map.  It is retained as a basic editor lighting rig, then its
    # volumetric-cloud component is explicitly disabled below.
    if class_path == "/SunPosition/SunSky.SunSky_C":
        return "retain", "trusted_basic_sun_sky_rig"

    if class_path == "/Script/PlanetGen.PlanetGenGravityDefaults":
        return "retain", "planetgen_editor_preview_gravity_defaults"

    if class_name in BASIC_NATIVE_CLASSES and class_path.startswith("/Script/Engine."):
        return "retain", BASIC_NATIVE_CLASSES[class_name]

    if _is_level_infrastructure_actor(actor):
        return "retain", "required_level_infrastructure"

    if class_name == "Brush" and label.lower() in {"builderbrush", "builder brush"}:
        return "retain", "editor_builder_brush"

    lowered = " ".join((class_name, class_path, label)).lower()
    if "redplanetregionanchor" in lowered:
        return "convert", "convert_redmmo_region_anchor_to_engine_target_point"
    if any(token in lowered for token in ("water", "ocean", "river", "lake")):
        return "delete", "water_or_ocean_presentation"
    if any(token in lowered for token in ("cloud", "hi5", "volumetric")):
        return "delete", "cloud_presentation"
    if any(
        token in lowered
        for token in ("spacescenery", "starfield", "asteroid", "moon", "orbit")
    ):
        return "delete", "space_or_orbit_presentation"
    if any(
        token in lowered
        for token in (
            "ship",
            "fighter",
            "shuttle",
            "carrier",
            "vehicle",
            "pawn",
            "character",
            "controller",
            "hud",
            "widget",
            "ability",
            "weapon",
            "projectile",
        )
    ):
        return "delete", "gameplay_or_ui_actor"

    # Unknown actors are deleted by design.  This is the central safety property
    # of the artist map: only positively identified terrain and simple native
    # preview infrastructure survive.
    return "delete", "not_on_artist_canvas_allow_list"


def _asset_package(value: Any) -> str:
    if value is None:
        return ""
    try:
        return _package_from_object_path(value.get_path_name())
    except Exception:
        return ""


def _property_candidates(property_name: str) -> List[str]:
    """Return UE Python and C++ spellings for a reflected property.

    Unreal's generated Python API normally drops the leading ``b`` from C++
    booleans (``bEnableWater`` becomes ``enable_water``), while
    ``get_editor_property`` builds in some engine versions also accept the raw
    reflected name.  Supporting both keeps the handoff script usable across the
    pinned 5.8 build and future 5.8 hotfixes without guessing silently.
    """

    candidates = [property_name]
    if property_name.startswith("enable_"):
        suffix = property_name[len("enable_") :]
        camel = "".join(part.capitalize() for part in suffix.split("_"))
        candidates.extend(
            [
                "b_" + property_name,
                "bEnable" + camel,
            ]
        )
    return list(dict.fromkeys(candidates))


def _read_first_property(actor: unreal.Actor, property_name: str) -> Tuple[str, Any]:
    last_error: Optional[Exception] = None
    for candidate in _property_candidates(property_name):
        try:
            return candidate, actor.get_editor_property(candidate)
        except Exception as exc:
            last_error = exc
    raise RuntimeError(
        f"Actor {actor.get_actor_label()} has no reflected property matching "
        f"{property_name}: {last_error}"
    )


def _require_fused_terrain(actor: unreal.Actor) -> Dict[str, Any]:
    try:
        enabled_property, enabled_value = _read_first_property(
            actor, "enable_macro_heightfield"
        )
        enabled = bool(enabled_value)
        _, macro_asset = _read_first_property(actor, "macro_heightfield_asset")
    except Exception as exc:
        raise RuntimeError(
            f"Planet actor {actor.get_actor_label()} does not expose the pinned "
            "PlanetGen macro-heightfield properties"
        ) from exc

    macro_package = _asset_package(macro_asset)
    if not enabled:
        raise RuntimeError(
            f"Planet actor {actor.get_actor_label()} has macro heightfield disabled"
        )
    if macro_package != FUSED_HEIGHTFIELD_PACKAGE:
        raise RuntimeError(
            f"Planet actor {actor.get_actor_label()} uses {macro_package or '<None>'}; "
            f"expected {FUSED_HEIGHTFIELD_PACKAGE}"
        )

    try:
        radius_cm = float(actor.get_editor_property("planet_radius"))
    except Exception as exc:
        raise RuntimeError("Planet actor has no readable Planet Radius") from exc
    if not 780000.0 <= radius_cm <= 815000.0:
        raise RuntimeError(
            f"Unexpected 50 km planet radius {radius_cm:.3f} cm; refusing cleanup"
        )

    return {
        "label": actor.get_actor_label(),
        "class_path": actor.get_class().get_path_name(),
        "planet_radius_cm": radius_cm,
        "circumference_km": radius_cm * 2.0 * 3.141592653589793 / 100000.0,
        "macro_heightfield_enabled": enabled,
        "macro_heightfield_enabled_property": enabled_property,
        "macro_heightfield_package": macro_package,
    }


def _set_if_present(
    actor: unreal.Actor,
    property_name: str,
    value: Any,
    applied: List[Dict[str, Any]],
    warnings: List[str],
) -> None:
    for candidate in _property_candidates(property_name):
        try:
            actor.get_editor_property(candidate)
        except Exception:
            continue
        try:
            actor.set_editor_property(candidate, value)
            applied.append({"property": candidate, "value": str(value)})
        except Exception as exc:
            warnings.append(
                f"Could not set {actor.get_actor_label()}.{candidate}: {exc}"
            )
        return


def _make_planet_artist_safe(
    actor: unreal.Actor, warnings: List[str]
) -> List[Dict[str, Any]]:
    """Remove non-terrain dependencies from the retained PlanetGen actor."""

    applied: List[Dict[str, Any]] = []
    actor.modify()

    # The artist map is land/height/mask authoring.  Water is intentionally
    # absent until a separately verified shoreline implementation is added.
    _set_if_present(actor, "enable_water", False, applied, warnings)
    _set_if_present(actor, "water_material", None, applied, warnings)

    # Keep the low-cost authored macro shell so all 27 authoring sites remain
    # visible from orbit without the full-water-sphere bug.
    _set_if_present(
        actor, "enable_resident_macro_surface", True, applied, warnings
    )

    # Keep the handoff blank and avoid loading vendor foliage packs at startup.
    _set_if_present(actor, "enable_foliage", False, applied, warnings)
    _set_if_present(actor, "foliage_assets", [], applied, warnings)
    _set_if_present(actor, "enable_grass", False, applied, warnings)
    _set_if_present(actor, "grass_assets", [], applied, warnings)
    _set_if_present(actor, "additional_streaming_sources", [], applied, warnings)

    # Keep the trusted SunSky light/atmosphere connection but sever the explicit
    # cloud override.  The SunSky Blueprint's own cloud component is hidden by
    # _disable_cloud_components().
    _set_if_present(actor, "target_clouds", None, applied, warnings)

    # bEnableWater=false normally calls ACLMPlanet::BuildWaterSphere through
    # PostEditChangeProperty.  Clear/hide the serialized procedural component as
    # a second guard so the artist can never encounter the elevated full-ocean
    # shell even if the editor skips that callback during automation.
    for component in actor.get_components_by_class(unreal.ActorComponent) or []:
        component_name = component.get_name().lower()
        component_class = component.get_class()
        component_path = (
            component_class.get_path_name().lower() if component_class else ""
        )
        if "watersphere" not in component_name and "water_sphere" not in component_name:
            continue
        component.modify()
        try:
            component.set_visibility(False, True)
        except Exception as exc:
            warnings.append(f"Could not hide {component.get_name()}: {exc}")
        try:
            component.set_hidden_in_game(True)
        except Exception as exc:
            warnings.append(
                f"Could not mark {component.get_name()} hidden in game: {exc}"
            )
        try:
            component.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
        except Exception as exc:
            warnings.append(
                f"Could not disable {component.get_name()} collision: {exc}"
            )
        if "proceduralmeshcomponent" in component_path:
            try:
                component.clear_all_mesh_sections()
            except Exception as exc:
                warnings.append(
                    f"Could not clear {component.get_name()} mesh sections: {exc}"
                )
        applied.append(
            {
                "component": component.get_name(),
                "action": "hidden_collision_disabled_mesh_sections_cleared",
            }
        )
    return applied


def _disable_cloud_components(
    actor: unreal.Actor, warnings: List[str]
) -> List[Dict[str, Any]]:
    """Disable, but do not modify the vendor class of, bundled cloud components."""

    changes: List[Dict[str, Any]] = []
    for component in actor.get_components_by_class(unreal.ActorComponent) or []:
        component_class = component.get_class()
        component_path = component_class.get_path_name() if component_class else ""
        if "volumetriccloud" not in component_path.lower():
            continue
        component.modify()
        for operation, callback in (
            ("visibility_false", lambda: component.set_visibility(False, True)),
            ("hidden_in_game_true", lambda: component.set_hidden_in_game(True)),
            ("tick_disabled", lambda: component.set_component_tick_enabled(False)),
            ("deactivated", component.deactivate),
        ):
            try:
                callback()
                changes.append(
                    {
                        "component": component.get_name(),
                        "class_path": component_path,
                        "action": operation,
                    }
                )
            except Exception as exc:
                warnings.append(
                    f"Could not apply {operation} to {actor.get_actor_label()}."
                    f"{component.get_name()}: {exc}"
                )
    return changes


def _assert_planet_artist_safe(actor: unreal.Actor) -> Dict[str, Any]:
    values: Dict[str, Any] = {}
    for property_name, expected in (
        ("enable_water", False),
        ("enable_foliage", False),
        ("enable_grass", False),
        ("enable_resident_macro_surface", True),
    ):
        reflected_name, value = _read_first_property(actor, property_name)
        values[reflected_name] = bool(value)
        if bool(value) is not expected:
            raise RuntimeError(
                f"Artist-safe terrain invariant failed: {reflected_name}="
                f"{bool(value)}, expected {expected}"
            )

    _, water_material = _read_first_property(actor, "water_material")
    values["water_material"] = _asset_package(water_material)
    if water_material is not None:
        raise RuntimeError("Artist-safe terrain still references a water material")

    water_components = []
    for component in actor.get_components_by_class(unreal.ActorComponent) or []:
        name = component.get_name()
        if "watersphere" not in name.lower() and "water_sphere" not in name.lower():
            continue
        visible: Optional[bool]
        try:
            visible = bool(component.is_visible())
        except Exception:
            visible = None
        water_components.append({"name": name, "visible": visible})
        if visible is True:
            raise RuntimeError(f"Artist-safe WaterSphere remains visible: {name}")
    values["water_components"] = water_components
    return values


def _destroy_actor(actor: unreal.Actor) -> bool:
    _assert_destination_is_current()
    subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    if subsystem:
        return bool(subsystem.destroy_actor(actor))
    return bool(unreal.EditorLevelLibrary.destroy_actor(actor))


def _spawn_native_actor(
    python_class_name: str,
    label: str,
    folder: str,
) -> unreal.Actor:
    _assert_destination_is_current()
    actor_class = getattr(unreal, python_class_name, None)
    if actor_class is None:
        raise RuntimeError(f"Unreal Python class is unavailable: {python_class_name}")
    subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    if not subsystem:
        raise RuntimeError("EditorActorSubsystem is unavailable")
    actor = subsystem.spawn_actor_from_class(
        actor_class,
        unreal.Vector(0.0, 0.0, 0.0),
        unreal.Rotator(0.0, 0.0, 0.0),
    )
    if not actor:
        raise RuntimeError(f"Failed to spawn {python_class_name}")
    actor.set_actor_label(label, mark_dirty=True)
    try:
        actor.set_folder_path(folder)
    except Exception:
        pass
    return actor


def _convert_region_anchor_to_target_point(
    source_actor: unreal.Actor,
) -> Tuple[unreal.Actor, Dict[str, Any]]:
    """Replace a RedMMO marker with an engine-only authoring guide."""

    _assert_destination_is_current()
    source_record = _actor_record(source_actor)
    subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    if not subsystem:
        raise RuntimeError("EditorActorSubsystem is unavailable")
    target_type = getattr(unreal, "TargetPoint", None)
    if target_type is None:
        raise RuntimeError("Unreal Python TargetPoint class is unavailable")

    target = subsystem.spawn_actor_from_class(
        target_type,
        source_actor.get_actor_location(),
        source_actor.get_actor_rotation(),
    )
    if not target:
        raise RuntimeError(
            "Could not create engine TargetPoint for " + source_record["label"]
        )
    target.set_actor_label(source_record["label"], mark_dirty=True)
    try:
        target.set_folder_path("ArtistCanvas/27_RegionGuides")
    except Exception:
        pass

    label = source_record["label"]
    suffix = label.rsplit("_", 1)[-1] if "_" in label else "Unknown"
    tag_strings = set(source_record["tags"])
    tag_strings.update(
        {
            "ArtistCanvasRegion",
            "FusedAuthoringSite",
            "RegionIndex=" + suffix,
        }
    )
    try:
        target.set_editor_property(
            "tags", [unreal.Name(value) for value in sorted(tag_strings)]
        )
    except Exception as exc:
        raise RuntimeError(
            f"Could not copy authoring tags to {source_record['label']}: {exc}"
        ) from exc

    target_record = _actor_record(target)
    return target, {
        "reason": "redmmo_region_anchor_replaced_with_engine_target_point",
        "source": source_record,
        "target": target_record,
    }


def _ensure_basic_lighting(
    actors: Sequence[unreal.Actor], warnings: List[str]
) -> List[Dict[str, Any]]:
    """Guarantee simple native lights/atmosphere after strict cleanup."""

    present = {_class_record(actor)[0] for actor in actors}
    spawned: List[Dict[str, Any]] = []
    if any(_class_record(actor)[1] == "/SunPosition/SunSky.SunSky_C" for actor in actors):
        return spawned
    requirements = (
        ("DirectionalLight", "ArtistCanvas_Sun"),
        ("SkyLight", "ArtistCanvas_SkyLight"),
        ("SkyAtmosphere", "ArtistCanvas_SkyAtmosphere"),
    )
    for class_name, label in requirements:
        if class_name in present:
            continue
        try:
            actor = _spawn_native_actor(class_name, label, "ArtistCanvas/Lighting")
            record = _actor_record(actor)
            record["reason"] = "spawned_missing_basic_lighting"
            spawned.append(record)
        except Exception as exc:
            warnings.append(f"Could not spawn {class_name}: {exc}")
    return spawned


def _source_package_is_dirty() -> bool:
    source_asset = unreal.EditorAssetLibrary.load_asset(SOURCE_MAP)
    if source_asset is None:
        raise RuntimeError(f"Could not load source-map asset metadata: {SOURCE_MAP}")

    # UE 5.8 does not expose ``UPackage::IsDirty`` as ``Package.is_dirty`` in
    # Python.  Query the editor's supported dirty-package lists instead.  This
    # also works in the Python commandlet used by the handoff build, where the
    # lists should be empty in a fresh process.
    try:
        dirty_packages = []
        dirty_packages.extend(
            unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()
        )
        dirty_packages.extend(
            unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages()
        )
        for package in dirty_packages:
            if _package_from_object_path(package.get_path_name()) == SOURCE_MAP:
                return True
        return False
    except Exception as exc:
        # Failing closed prevents accidentally cloning unsaved source changes.
        raise RuntimeError("Could not verify protected source package dirty state") from exc


def main() -> None:
    started = _utc_now()
    destination_created = False
    destination_saved = False
    initial_records: List[Dict[str, Any]] = []
    retained_records: List[Dict[str, Any]] = []
    deleted_records: List[Dict[str, Any]] = []
    spawned_records: List[Dict[str, Any]] = []
    converted_region_anchors: List[Dict[str, Any]] = []
    planet_adjustments: List[Dict[str, Any]] = []
    cloud_component_adjustments: List[Dict[str, Any]] = []
    artist_safe_terrain_validation: Dict[str, Any] = {}
    warnings: List[str] = []
    terrain_validation: List[Dict[str, Any]] = []

    base_audit: Dict[str, Any] = {
        "policy_version": POLICY_VERSION,
        "started_utc": started,
        "source_map": SOURCE_MAP,
        "destination_map": DESTINATION_MAP,
        "protected_maps": sorted(PROTECTED_MAPS),
        "fused_heightfield_package": FUSED_HEIGHTFIELD_PACKAGE,
        "audit_output": AUDIT_OUTPUT,
    }

    try:
        if SOURCE_MAP == DESTINATION_MAP or DESTINATION_MAP in PROTECTED_MAPS:
            raise RuntimeError("Destination map violates the protected-map policy")
        if not unreal.EditorAssetLibrary.does_asset_exist(SOURCE_MAP):
            raise RuntimeError(f"Protected source map does not exist: {SOURCE_MAP}")
        if unreal.EditorAssetLibrary.does_asset_exist(DESTINATION_MAP):
            raise RuntimeError(
                "Destination already exists; refusing to overwrite it: "
                + DESTINATION_MAP
            )
        if _source_package_is_dirty():
            raise RuntimeError(
                "Protected source map has unsaved changes; save or discard them "
                "manually before creating an artist canvas"
            )

        duplicate = unreal.EditorAssetLibrary.duplicate_asset(
            SOURCE_MAP, DESTINATION_MAP
        )
        if duplicate is None:
            raise RuntimeError(
                f"EditorAssetLibrary could not duplicate {SOURCE_MAP} to "
                f"{DESTINATION_MAP}"
            )
        destination_created = True

        if not unreal.EditorLevelLibrary.load_level(DESTINATION_MAP):
            raise RuntimeError(f"Could not open duplicate map: {DESTINATION_MAP}")
        _assert_destination_is_current()

        actors = list(unreal.EditorLevelLibrary.get_all_level_actors())
        initial_records = [_actor_record(actor) for actor in actors]
        initial_records.sort(key=lambda item: (item["class_path"], item["label"]))

        terrain_actors = [actor for actor in actors if _is_planet_terrain_actor(actor)]
        if len(terrain_actors) != 1:
            raise RuntimeError(
                "Expected exactly one PlanetGen fused-terrain actor, found "
                + str(len(terrain_actors))
            )
        terrain_validation = [_require_fused_terrain(terrain_actors[0])]

        classifications: List[Tuple[unreal.Actor, str, str]] = []
        for actor in actors:
            action, reason = _classify_actor(actor)
            classifications.append((actor, action, reason))

        # Configure terrain before removing referenced presentation actors.  All
        # mutations are guarded by a current-map assertion.
        _assert_destination_is_current()
        planet_adjustments = _make_planet_artist_safe(terrain_actors[0], warnings)
        artist_safe_terrain_validation = _assert_planet_artist_safe(
            terrain_actors[0]
        )

        trusted_sun_sky_actors = [
            actor
            for actor in actors
            if _class_record(actor)[1] == "/SunPosition/SunSky.SunSky_C"
        ]
        if len(trusted_sun_sky_actors) != 1:
            raise RuntimeError(
                "Expected exactly one trusted SunSky rig, found "
                + str(len(trusted_sun_sky_actors))
            )
        cloud_component_adjustments = _disable_cloud_components(
            trusted_sun_sky_actors[0], warnings
        )

        for actor, action, reason in classifications:
            record = _actor_record(actor)
            record["reason"] = reason
            if action == "retain":
                retained_records.append(record)
                continue
            if action == "convert":
                _, conversion = _convert_region_anchor_to_target_point(actor)
                if not _destroy_actor(actor):
                    raise RuntimeError(
                        "Failed to delete converted source region anchor "
                        f"{record['label']} ({record['class_path']})"
                    )
                converted_region_anchors.append(conversion)
                deleted_records.append(record)
                continue
            if not _destroy_actor(actor):
                # Construction-script child actors (the ship engine actors in
                # the protected source map) cannot always be destroyed
                # directly.  Their owning parent is deleted later in this
                # pass, which removes the child.  Do not weaken the result:
                # the strict post-delete allow-list below still fails if any
                # such actor actually survives.
                warnings.append(
                    "Direct actor deletion returned false; requiring parent "
                    f"cleanup/post-delete invariant: {record['label']} "
                    f"({record['class_path']})"
                )
            deleted_records.append(record)

        if len(converted_region_anchors) != 27:
            raise RuntimeError(
                "Expected to convert all 27 region anchors to engine TargetPoints, "
                f"converted {len(converted_region_anchors)}"
            )

        remaining = list(unreal.EditorLevelLibrary.get_all_level_actors())
        spawned_records = _ensure_basic_lighting(remaining, warnings)

        # Remove production game-mode dependency if this engine version exposes
        # the standard AWorldSettings property.  Failure is audited but is not a
        # reason to risk deleting the successfully cleaned terrain duplicate.
        world = unreal.EditorLevelLibrary.get_editor_world()
        world_settings_change = "not_attempted"
        try:
            world_settings = world.get_world_settings()
            world_settings.modify()
            world_settings.set_editor_property("default_game_mode", unreal.GameModeBase)
            world_settings_change = "/Script/Engine.GameModeBase"
        except Exception as exc:
            world_settings_change = "unchanged"
            warnings.append(f"Could not clear map game-mode override: {exc}")

        _assert_destination_is_current()
        if not unreal.EditorAssetLibrary.save_asset(
            DESTINATION_MAP, only_if_is_dirty=False
        ):
            raise RuntimeError(f"Could not save duplicate map: {DESTINATION_MAP}")
        destination_saved = True

        final_actors = list(unreal.EditorLevelLibrary.get_all_level_actors())
        final_records = [_actor_record(actor) for actor in final_actors]
        final_records.sort(key=lambda item: (item["class_path"], item["label"]))

        # Post-save invariant: the only content actors must still satisfy the
        # same strict allow-list, and the fused terrain must still be present.
        unexpected = []
        final_terrain = []
        for actor in final_actors:
            if _is_planet_terrain_actor(actor):
                final_terrain.append(actor)
                continue
            action, reason = _classify_actor(actor)
            if action != "retain":
                unexpected.append(
                    {
                        "actor": _actor_record(actor),
                        "classification_reason": reason,
                    }
                )
        if len(final_terrain) != 1 or unexpected:
            raise RuntimeError(
                "Post-save artist-canvas invariant failed: "
                f"terrain_count={len(final_terrain)}, unexpected={len(unexpected)}"
            )
        _require_fused_terrain(final_terrain[0])
        artist_safe_terrain_validation = _assert_planet_artist_safe(
            final_terrain[0]
        )

        payload = dict(base_audit)
        payload.update(
            {
                "status": "success",
                "completed_utc": _utc_now(),
                "destination_saved": destination_saved,
                "initial_actor_count": len(initial_records),
                "retained_actor_count_before_spawn": len(retained_records),
                "deleted_actor_count": len(deleted_records),
                "spawned_actor_count": len(spawned_records),
                "final_actor_count": len(final_records),
                "terrain_validation": terrain_validation,
                "planet_adjustments": planet_adjustments,
                "artist_safe_terrain_validation": artist_safe_terrain_validation,
                "cloud_component_adjustments": cloud_component_adjustments,
                "converted_region_anchor_count": len(converted_region_anchors),
                "converted_region_anchors": converted_region_anchors,
                "world_settings_default_game_mode": world_settings_change,
                "retained_actors": sorted(
                    retained_records,
                    key=lambda item: (item["class_path"], item["label"]),
                ),
                "deleted_actors": sorted(
                    deleted_records,
                    key=lambda item: (item["class_path"], item["label"]),
                ),
                "spawned_actors": sorted(
                    spawned_records,
                    key=lambda item: (item["class_path"], item["label"]),
                ),
                "final_actors": final_records,
                "warnings": warnings,
            }
        )
        _write_audit(payload)
        unreal.log_warning(
            "RED_ARTIST_CANVAS_READY "
            f"map={DESTINATION_MAP} retained={len(retained_records)} "
            f"deleted={len(deleted_records)} spawned={len(spawned_records)} "
            f"audit={AUDIT_OUTPUT}"
        )

    except Exception as exc:
        cleanup_error: Optional[str] = None
        if destination_created and not destination_saved:
            try:
                # Never delete an asset outside the one destination this run
                # just created.
                if unreal.EditorAssetLibrary.does_asset_exist(DESTINATION_MAP):
                    if not unreal.EditorAssetLibrary.delete_asset(DESTINATION_MAP):
                        cleanup_error = "EditorAssetLibrary.delete_asset returned false"
            except Exception as cleanup_exc:
                cleanup_error = str(cleanup_exc)

        failure = dict(base_audit)
        failure.update(
            {
                "status": "failed",
                "completed_utc": _utc_now(),
                "error": str(exc),
                "traceback": traceback.format_exc(),
                "destination_created": destination_created,
                "destination_saved": destination_saved,
                "failed_destination_cleanup_error": cleanup_error,
                "initial_actors": initial_records,
                "retained_actors": retained_records,
                "deleted_actors": deleted_records,
                "spawned_actors": spawned_records,
                "terrain_validation": terrain_validation,
                "planet_adjustments": planet_adjustments,
                "artist_safe_terrain_validation": artist_safe_terrain_validation,
                "cloud_component_adjustments": cloud_component_adjustments,
                "converted_region_anchors": converted_region_anchors,
                "warnings": warnings,
            }
        )
        try:
            _write_audit(failure)
        except Exception as audit_exc:
            unreal.log_error(f"Could not write artist-canvas failure audit: {audit_exc}")
        unreal.log_error(f"RED_ARTIST_CANVAS_FAILED: {exc}")
        raise


if __name__ == "__main__":
    main()
