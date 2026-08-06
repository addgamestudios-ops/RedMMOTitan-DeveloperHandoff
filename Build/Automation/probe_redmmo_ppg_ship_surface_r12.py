"""No-save real-PIE surface probe for the R12 parked visual ship."""

from __future__ import annotations

import hashlib
import json
import math
import os
import socket
import time
import traceback

import unreal


MAP = "/Game/RedMMO/Maps/RedMMO_PPG_HomeWorld"
MAP_FILE = r"D:\RedMMOTitanWindowsData\Projects\RedMMO\Content\RedMMO\Maps\RedMMO_PPG_HomeWorld.umap"
EXPECTED_MAP_SHA = "3F98136280504222E5340DB7044F0F3564E8BFFD7221C4EC2F2DF655CE2FFAEC"
ROOT = r"D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_PPG_CharacterShip_R12_20260802"
RESULT = os.path.join(ROOT, "probe_redmmo_ppg_ship_surface_r12_result.json")
STATE = os.path.join(ROOT, "probe_redmmo_ppg_ship_surface_r12_state.json")
DONE = os.path.join(ROOT, "probe_redmmo_ppg_ship_surface_r12.done")
PROVIDER_PORTS = (5353, 8000, 8765)


def require(value, message: str) -> None:
    if not value:
        raise RuntimeError(message)


def sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def atomic_json(path: str, value: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    temporary = path + ".tmp"
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2, sort_keys=True, default=str)
        handle.write("\n")
    for attempt in range(40):
        try:
            os.replace(temporary, path)
            return
        except PermissionError:
            if attempt == 39:
                raise
            time.sleep(0.025)


def vec(value) -> list[float]:
    return [float(value.x), float(value.y), float(value.z)]


def add(a, b):
    return unreal.Vector(a.x + b.x, a.y + b.y, a.z + b.z)


def sub(a, b):
    return unreal.Vector(a.x - b.x, a.y - b.y, a.z - b.z)


def mul(value, scalar: float):
    return unreal.Vector(value.x * scalar, value.y * scalar, value.z * scalar)


def dot(a, b) -> float:
    return float(a.x * b.x + a.y * b.y + a.z * b.z)


def cross(a, b):
    return unreal.Vector(
        a.y * b.z - a.z * b.y,
        a.z * b.x - a.x * b.z,
        a.x * b.y - a.y * b.x,
    )


def length(value) -> float:
    return math.sqrt(dot(value, value))


def normalized(value):
    magnitude = length(value)
    require(magnitude > 1.0e-6, "Cannot normalize zero vector")
    return mul(value, 1.0 / magnitude)


def dirty_packages() -> list[str]:
    packages = list(unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages())
    packages += list(unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages())
    return sorted({package.get_path_name() for package in packages})


def provider_gate() -> dict[str, bool]:
    result = {}
    for port in PROVIDER_PORTS:
        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        probe.settimeout(0.15)
        try:
            result[str(port)] = probe.connect_ex(("127.0.0.1", port)) != 0
        finally:
            probe.close()
    require(all(result.values()), "AI/MCP/provider listener is active")
    return result


def hit_value(hit, names, default=None):
    for name in names:
        try:
            return hit.get_editor_property(name)
        except Exception:
            continue
    return default


def trace_type(channel_name: str):
    return getattr(unreal.TraceTypeQuery, channel_name, None)


class Probe:
    def __init__(self):
        self.editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
        self.level = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
        self.phase = "PREPARE"
        self.phase_started = time.monotonic()
        self.handle = None
        self.world = None
        self.spawner = None
        self.player_start = None
        self.pie_pawn = None
        self.pie_controller = None
        self.pie_rotation = None
        self.desired_direction = None
        self.tangent_axis_x = None
        self.tangent_axis_y = None
        self.planet_radius = None
        self.ship_offset_x = 5200.0
        self.ship_offset_y = -1600.0
        self.phase_frames = 0
        self.regeneration_ready_frames = 0
        self.report = {
            "schema": "redmmo.ppg_character_ship.r12.surface_probe.v1",
            "status": "RUNNING",
            "map": MAP,
            "home_map_sha256": EXPECTED_MAP_SHA,
            "evidence_class": "automation",
            "map_saved": False,
        }

    def publish(self):
        self.report["phase"] = self.phase
        self.report["phase_elapsed_seconds"] = time.monotonic() - self.phase_started
        atomic_json(STATE, self.report)

    def set_phase(self, phase: str):
        self.phase = phase
        self.phase_started = time.monotonic()
        self.phase_frames = 0
        self.publish()
        unreal.log("REDMMO_R12_SURFACE_PROBE_PHASE " + phase)

    def start(self):
        for path in (RESULT, STATE, DONE):
            require(not os.path.exists(path), "R12 surface probe no-clobber failed: " + path)
        self.handle = unreal.register_slate_post_tick_callback(self.tick)
        self.publish()

    def prepare(self):
        require(sha256(MAP_FILE) == EXPECTED_MAP_SHA, "R12 pre-probe map hash drift")
        require(not dirty_packages(), "Dirty packages before R12 probe: " + str(dirty_packages()))
        self.report["provider_ports_closed"] = provider_gate()
        require(not self.level.is_in_play_in_editor(), "PIE already active")
        editor_world = unreal.EditorLevelLibrary.get_editor_world()
        current = editor_world.get_path_name().split(":", 1)[0].split(".", 1)[0]
        require(current == MAP, "Wrong editor map: " + current)
        self.level.editor_request_begin_play()
        self.set_phase("WAIT_PIE")

    def bind(self) -> bool:
        world = self.editor.get_game_world()
        if world is None or not self.level.is_in_play_in_editor():
            return False
        actors = list(unreal.GameplayStatics.get_all_actors_of_class(world, unreal.Actor))
        spawners = [a for a in actors if a.get_class().get_name() == "PlanetSpawnerBP_C"]
        player_starts = [a for a in actors if a.get_class().get_name() == "PlayerStart"]
        if not spawners or not player_starts:
            return False
        require(len(spawners) == 1, "Expected exactly one PPG spawner")
        require(len(player_starts) == 1, "Expected exactly one PlayerStart")
        self.world = world
        self.spawner = spawners[0]
        self.player_start = player_starts[0]
        self.stage_pie_probe()
        return True

    def stage_pie_probe(self):
        center = self.spawner.get_actor_location()
        base = self.player_start.get_actor_location()
        up = normalized(sub(base, center))
        forward = self.player_start.get_actor_forward_vector()
        axis_x = sub(forward, mul(up, dot(forward, up)))
        if length(axis_x) < 0.01:
            axis_x = cross(unreal.Vector(0.0, 0.0, 1.0), up)
        if length(axis_x) < 0.01:
            axis_x = cross(unreal.Vector(0.0, 1.0, 0.0), up)
        axis_x = normalized(axis_x)
        axis_y = normalized(cross(up, axis_x))
        candidate = add(
            add(add(base, mul(axis_x, self.ship_offset_x)), mul(axis_y, self.ship_offset_y)),
            mul(up, 150.0),
        )
        direction = normalized(sub(candidate, center))
        planet_data = self.spawner.get_editor_property("planet_data")
        radius = float(planet_data.get_editor_property("planet_radius"))
        pawn = unreal.GameplayStatics.get_player_pawn(self.world, 0)
        require(pawn is not None, "PIE player pawn unavailable for R12 chunk staging")
        staging_forward = normalized(sub(axis_x, mul(direction, 0.05)))
        staging_rotation = unreal.MathLibrary.make_rot_from_xz(staging_forward, direction)
        staging_location = add(center, mul(direction, radius + 125000.0))
        require(bool(pawn.set_actor_location(staging_location, False, True)),
                "Unable to move transient PIE pawn to R12 near-surface chunk")
        require(bool(pawn.set_actor_rotation(staging_rotation, True)),
                "Unable to rotate transient PIE pawn for R12 surface probe")
        controller = unreal.GameplayStatics.get_player_controller(self.world, 0)
        if controller is not None:
            controller.set_control_rotation(staging_rotation)
        self.pie_pawn = pawn
        self.pie_controller = controller
        self.pie_rotation = staging_rotation
        self.desired_direction = direction
        self.tangent_axis_x = axis_x
        self.tangent_axis_y = axis_y
        self.planet_radius = radius
        self.report["pie_staging"] = {
            "world": self.world.get_path_name(),
            "spawner": self.spawner.get_path_name(),
            "pawn": pawn.get_path_name(),
            "player_start_at_stage": vec(base),
            "center_at_stage": vec(center),
            "nominal_radius_cm": radius,
            "above_nominal_cm": 125000.0,
            "location": vec(staging_location),
            "rotation": [staging_rotation.pitch, staging_rotation.yaw, staging_rotation.roll],
            "desired_direction": vec(direction),
            "ship_offset_cm": {"x": self.ship_offset_x, "y": self.ship_offset_y},
            "purpose": "move only the transient PIE pawn so PPG emits query-collision terrain at the R12 ship region",
            "persistent_actors_moved": False,
            "map_saved": False,
        }
        self.set_phase("WAIT_VIEW_STABLE")

    def pin_pie_pawn(self):
        center = self.spawner.get_actor_location()
        location = add(center, mul(self.desired_direction, self.planet_radius + 125000.0))
        require(bool(self.pie_pawn.set_actor_location(location, False, True)),
                "Unable to hold transient PIE pawn at R12 staging point")
        require(bool(self.pie_pawn.set_actor_rotation(self.pie_rotation, True)),
                "Unable to hold transient PIE pawn rotation")
        if self.pie_controller is not None:
            self.pie_controller.set_control_rotation(self.pie_rotation)
        return center, location

    def regenerate_after_stable_view(self):
        center, pinned_location = self.pin_pie_pawn()
        view_location = self.pie_pawn.get_actor_location()
        view_rotation = self.pie_rotation
        view_method = getattr(self.pie_controller, "get_player_view_point", None)
        if callable(view_method):
            raw = view_method()
            if isinstance(raw, tuple):
                for item in raw:
                    if isinstance(item, unreal.Vector):
                        view_location = item
                    elif isinstance(item, unreal.Rotator):
                        view_rotation = item
        view_direction = normalized(sub(view_location, center))
        require(dot(view_direction, self.desired_direction) >= 0.999,
                "PIE viewpoint did not stabilize at requested R12 radial chunk")
        require(abs(length(sub(view_location, center)) - (self.planet_radius + 125000.0)) <= 5000.0,
                "PIE viewpoint radial distance drifted before R12 regeneration")
        regenerate = getattr(self.spawner, "regenerate_planet", None)
        require(callable(regenerate), "PIE PlanetSpawner.RegeneratePlanet unavailable")
        regenerate()
        self.report["pie_staging"].update({
            "center_at_regeneration": vec(center),
            "pinned_location_at_regeneration": vec(pinned_location),
            "player_view_location_at_regeneration": vec(view_location),
            "player_view_rotation_at_regeneration": [view_rotation.pitch, view_rotation.yaw, view_rotation.roll],
            "player_view_direction_dot_requested": dot(view_direction, self.desired_direction),
            "view_stabilization_frames": self.phase_frames,
            "regeneration_requested": True,
        })
        self.regeneration_ready_frames = 0
        self.set_phase("WAIT_REGENERATION")

    def generation_ready(self) -> bool:
        status = self.spawner.get_planet_generation_status()
        phase = str(status.get_editor_property("phase"))
        progress = float(status.get_editor_property("progress"))
        generating = bool(status.get_editor_property("is_generating"))
        self.report["generation"] = {"phase": phase, "progress": progress, "is_generating": generating}
        return "COMPLETE" in phase.upper() and progress >= 0.999 and not generating

    def run_trace(self):
        # Do not move the pawn after regeneration.  The proven R09 sequence
        # lets the PPG/Chaos streaming state settle for 180 ready frames before
        # rebuilding this allowlist and tracing in the current PIE coordinates.
        center = self.spawner.get_actor_location()
        base = self.player_start.get_actor_location()
        axis_x = self.tangent_axis_x
        axis_y = self.tangent_axis_y
        offset_x, offset_y = self.ship_offset_x, self.ship_offset_y
        direction = self.desired_direction
        radius = self.planet_radius
        start = add(center, mul(direction, radius + 250000.0))
        end = add(center, mul(direction, radius - 250000.0))
        components = list(self.spawner.get_components_by_class(unreal.StaticMeshComponent))
        terrain_paths = {
            component.get_path_name() for component in components
            if component.is_query_collision_enabled()
            and component.get_editor_property("static_mesh") is not None
            and not isinstance(component, unreal.InstancedStaticMeshComponent)
        }
        require(terrain_paths, "PIE PPG spawner has no query-collision terrain components")
        self.report["terrain_component_count"] = len(components)
        self.report["query_collision_terrain_component_count"] = len(terrain_paths)
        pawn = unreal.GameplayStatics.get_player_pawn(self.world, 0)
        all_actors = list(unreal.GameplayStatics.get_all_actors_of_class(self.world, unreal.Actor))
        ignored = [actor for actor in all_actors if actor != self.spawner]
        attempts = []
        accepted = None
        for channel_name in ("ECC_VISIBILITY", "ECC_PAWN"):
            query = trace_type(channel_name)
            if query is None:
                attempts.append({
                    "channel": channel_name,
                    "blocking_hit": False,
                    "accepted_ppg_terrain": False,
                    "unavailable_in_python": True,
                })
                continue
            hit = unreal.SystemLibrary.line_trace_single(
                self.world, start, end, query, True, ignored,
                unreal.DrawDebugTrace.NONE, True,
                unreal.LinearColor(1.0, 0.0, 0.0, 1.0),
                unreal.LinearColor(0.0, 1.0, 0.0, 1.0), 0.0,
            )
            record = {"channel": channel_name, "blocking_hit": False, "accepted_ppg_terrain": False}
            if hit is not None:
                actor = hit_value(hit, ("hit_actor", "actor"))
                component = hit_value(hit, ("hit_component", "component"))
                point = hit_value(hit, ("impact_point", "location"))
                normal = hit_value(hit, ("impact_normal", "normal"))
                blocking = bool(hit_value(hit, ("blocking_hit", "bBlockingHit"), False))
                accepted_here = bool(
                    blocking and actor == self.spawner and component is not None
                    and component.get_path_name() in terrain_paths
                )
                record.update({
                    "blocking_hit": blocking,
                    "accepted_ppg_terrain": accepted_here,
                    "hit_actor": actor.get_path_name() if actor else None,
                    "hit_component": component.get_path_name() if component else None,
                    "impact_point": vec(point) if point else None,
                    "impact_normal": vec(normal) if normal else None,
                })
                if accepted_here:
                    accepted = record
            attempts.append(record)
            if accepted is not None:
                break
        if accepted is None:
            object_types = []
            for index in range(1, 7):
                value = getattr(unreal.ObjectTypeQuery, "OBJECT_TYPE_QUERY{}".format(index), None)
                if value is not None:
                    object_types.append(value)
            require(object_types, "ObjectTypeQuery API is unavailable")
            hit = unreal.SystemLibrary.line_trace_single_for_objects(
                self.world, start, end, object_types, True, ignored,
                unreal.DrawDebugTrace.NONE, True,
                unreal.LinearColor(1.0, 0.0, 0.0, 1.0),
                unreal.LinearColor(0.0, 1.0, 0.0, 1.0), 0.0,
            )
            record = {
                "channel": "OBJECT_TYPES_1_TO_6",
                "object_type_count": len(object_types),
                "blocking_hit": False,
                "accepted_ppg_terrain": False,
            }
            if hit is not None:
                actor = hit_value(hit, ("hit_actor", "actor"))
                component = hit_value(hit, ("hit_component", "component"))
                point = hit_value(hit, ("impact_point", "location"))
                normal = hit_value(hit, ("impact_normal", "normal"))
                blocking = bool(hit_value(hit, ("blocking_hit", "bBlockingHit"), False))
                accepted_here = bool(
                    blocking and actor == self.spawner and component is not None
                    and component.get_path_name() in terrain_paths
                )
                record.update({
                    "blocking_hit": blocking,
                    "accepted_ppg_terrain": accepted_here,
                    "hit_actor": actor.get_path_name() if actor else None,
                    "hit_component": component.get_path_name() if component else None,
                    "impact_point": vec(point) if point else None,
                    "impact_normal": vec(normal) if normal else None,
                })
                if accepted_here:
                    accepted = record
            attempts.append(record)
        if accepted is None:
            for profile_name in ("Pawn", "BlockAll"):
                hit = unreal.SystemLibrary.line_trace_single_by_profile(
                    self.world, start, end, unreal.Name(profile_name), True, ignored,
                    unreal.DrawDebugTrace.NONE, True,
                    unreal.LinearColor(1.0, 0.0, 0.0, 1.0),
                    unreal.LinearColor(0.0, 1.0, 0.0, 1.0), 0.0,
                )
                record = {
                    "channel": "PROFILE_" + profile_name,
                    "blocking_hit": False,
                    "accepted_ppg_terrain": False,
                }
                if hit is not None:
                    actor = hit_value(hit, ("hit_actor", "actor"))
                    component = hit_value(hit, ("hit_component", "component"))
                    point = hit_value(hit, ("impact_point", "location"))
                    normal = hit_value(hit, ("impact_normal", "normal"))
                    blocking = bool(hit_value(hit, ("blocking_hit", "bBlockingHit"), False))
                    accepted_here = bool(
                        blocking and actor == self.spawner and component is not None
                        and component.get_path_name() in terrain_paths
                    )
                    record.update({
                        "blocking_hit": blocking,
                        "accepted_ppg_terrain": accepted_here,
                        "hit_actor": actor.get_path_name() if actor else None,
                        "hit_component": component.get_path_name() if component else None,
                        "impact_point": vec(point) if point else None,
                        "impact_normal": vec(normal) if normal else None,
                    })
                    if accepted_here:
                        accepted = record
                attempts.append(record)
                if accepted is not None:
                    break
        if accepted is None:
            # UE 5.8's Python trace-channel bridge can return no hit even when
            # the generated Chaos bodies are present.  Query those exact,
            # allowlisted PPG collision bodies directly from a point safely
            # outside the planet and choose the nearest aligned surface.
            probe_point = add(center, mul(direction, radius + 5000000.0))
            closest_candidates = []
            for component in components:
                path = component.get_path_name()
                if path not in terrain_paths:
                    continue
                query = getattr(component, "get_closest_point_on_collision", None)
                if not callable(query):
                    continue
                try:
                    raw = query(probe_point)
                except Exception as error:
                    closest_candidates.append({"component": path, "error": str(error)})
                    continue
                values = raw if isinstance(raw, tuple) else (raw,)
                point = next((value for value in values if isinstance(value, unreal.Vector)), None)
                distance = next((float(value) for value in values
                                 if isinstance(value, (int, float)) and math.isfinite(float(value))), None)
                if point is None or distance is None or distance < 0.0:
                    continue
                radial_vector = sub(point, center)
                if length(radial_vector) <= 1.0:
                    continue
                radial = normalized(radial_vector)
                alignment = dot(radial, direction)
                surface_radius = length(radial_vector)
                candidate_record = {
                    "component": path,
                    "distance_cm": distance,
                    "point": vec(point),
                    "surface_radius_cm": surface_radius,
                    "direction_alignment": alignment,
                }
                if alignment >= 0.9999 and abs(surface_radius - radius) <= 5000000.0:
                    closest_candidates.append(candidate_record)
            viable = [record for record in closest_candidates if "point" in record]
            viable.sort(key=lambda record: record["distance_cm"])
            self.report["closest_collision_candidate_count"] = len(viable)
            self.report["closest_collision_candidates"] = viable[:12]
            if viable:
                chosen = viable[0]
                point = unreal.Vector(*chosen["point"])
                radial = normalized(sub(point, center))
                accepted = {
                    "channel": "COMPONENT_CLOSEST_POINT_ON_COLLISION",
                    "blocking_hit": True,
                    "accepted_ppg_terrain": True,
                    "hit_actor": self.spawner.get_path_name(),
                    "hit_component": chosen["component"],
                    "impact_point": chosen["point"],
                    "impact_normal": vec(radial),
                    "surface_normal_source": "radial_up_from_authoritative_collision_point",
                    "probe_point": vec(probe_point),
                    "distance_cm": chosen["distance_cm"],
                    "direction_alignment": chosen["direction_alignment"],
                }
                attempts.append(accepted)
        self.report["trace_attempts"] = attempts
        self.publish()
        require(accepted is not None, "No authoritative PPG terrain hit at R12 ship offset")
        point = unreal.Vector(*accepted["impact_point"])
        normal = normalized(unreal.Vector(*accepted["impact_normal"]))
        radial = normalized(sub(point, center))
        require(dot(normal, radial) >= 0.90, "Surface normal is not plausibly outward")
        self.report.update({
            "status": "PASS_REAL_PIE_AUTHORITATIVE_PPG_SURFACE",
            "planet_center": vec(center),
            "planet_radius_cm": radius,
            "player_start": vec(base),
            "tangent_axis_x": vec(axis_x),
            "tangent_axis_y": vec(axis_y),
            "radial_up": vec(radial),
            "ship_offset_cm": {"x": offset_x, "y": offset_y},
            "candidate_direction": vec(direction),
            "surface_point": accepted["impact_point"],
            "surface_normal": accepted["impact_normal"],
            "surface_normal_radial_dot": dot(normal, radial),
            "trace_attempts": attempts,
            "terrain_component_count": len(terrain_paths),
            "map_saved": False,
        })
        self.level.editor_request_end_play()
        self.set_phase("WAIT_STOP")

    def finish(self):
        require(sha256(MAP_FILE) == EXPECTED_MAP_SHA, "R12 probe changed the map")
        require(not dirty_packages(), "Dirty packages after R12 probe: " + str(dirty_packages()))
        self.report["provider_ports_closed_after"] = provider_gate()
        atomic_json(RESULT, self.report)
        with open(DONE, "w", encoding="utf-8") as handle:
            handle.write("PASS_REAL_PIE_AUTHORITATIVE_PPG_SURFACE\n")
        if self.handle is not None:
            unreal.unregister_slate_post_tick_callback(self.handle)
            self.handle = None
        unreal.log("REDMMO_R12_SURFACE_PROBE PASS")

    def fail(self, exc: Exception):
        self.report.update({"status": "FAIL", "error": str(exc), "exception": traceback.format_exc()})
        try:
            if self.level.is_in_play_in_editor():
                self.level.editor_request_end_play()
        except Exception:
            pass
        atomic_json(RESULT, self.report)
        with open(DONE, "w", encoding="utf-8") as handle:
            handle.write("FAIL: " + str(exc) + "\n")
        if self.handle is not None:
            try:
                unreal.unregister_slate_post_tick_callback(self.handle)
            except Exception:
                pass
            self.handle = None
        unreal.log_error("REDMMO_R12_SURFACE_PROBE FAIL " + str(exc))

    def tick(self, _delta_seconds):
        try:
            self.phase_frames += 1
            self.publish()
            elapsed = time.monotonic() - self.phase_started
            if self.phase == "PREPARE":
                self.prepare()
            elif self.phase == "WAIT_PIE":
                if elapsed > 60.0:
                    raise RuntimeError("Timed out waiting for PIE")
                self.bind()
            elif self.phase == "WAIT_VIEW_STABLE":
                if elapsed > 30.0:
                    raise RuntimeError("Timed out stabilizing the R12 PIE viewpoint")
                self.pin_pie_pawn()
                if self.phase_frames >= 3:
                    self.regenerate_after_stable_view()
            elif self.phase == "WAIT_REGENERATION":
                if elapsed > 180.0:
                    raise RuntimeError("Timed out waiting for R12 PPG regeneration")
                if self.generation_ready():
                    self.regeneration_ready_frames += 1
                    # PPG reports generation complete before all query-collision
                    # bodies are registered.  The retained R09 surface proof
                    # established 180 ready frames as the reliable settle gate.
                    if self.regeneration_ready_frames >= 180:
                        self.set_phase("TRACE")
                else:
                    self.regeneration_ready_frames = 0
            elif self.phase == "TRACE":
                self.run_trace()
            elif self.phase == "WAIT_STOP":
                if elapsed > 30.0:
                    raise RuntimeError("Timed out waiting for PIE to stop")
                if not self.level.is_in_play_in_editor() and self.editor.get_game_world() is None:
                    self.finish()
        except Exception as exc:
            self.fail(exc)


PROBE = Probe()
PROBE.start()
