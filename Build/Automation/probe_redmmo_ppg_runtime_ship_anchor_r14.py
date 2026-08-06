"""No-save normal-spawn PIE probe for an exact nearby R14 parked-ship anchor."""

from __future__ import annotations

import hashlib
import json
import math
import os
import socket
import time
import traceback

import unreal


PROJECT = r"D:\RedMMOTitanWindowsData\Projects\RedMMO\RedMMO.uproject"
MAP = "/Game/RedMMO/Maps/RedMMO_PPG_HomeWorld"
MAP_FILE = r"D:\RedMMOTitanWindowsData\Projects\RedMMO\Content\RedMMO\Maps\RedMMO_PPG_HomeWorld.umap"
MAP_SHA = "C9BE88085575E75E1790CB9306D564EB100F5ED2E75E012C1FD09EA110FDDFE0"
PAWN = "/Game/RedMMO/Gameplay/Player/BP_RedPlanetCharacter_R11"
SHIP_LABEL = "RedMMO_R12_ParkedStarSparrow_VisualOnly"
SHIP_MESH = "/Game/StarSparrow/Meshes/Examples/SM_StarSparrow01"
PROTECTED = {
    r"D:\RedMMOTitan\Content\RedMMO\Maps\RedPlanetGen_50km_Test.umap":
        "DA5987012EEB8F550254F5FCF0F47F42B8F5E03428CF4881C83D8687537F6E7D",
    r"D:\RedMMOTitan\Content\RedMMO\Maps\RedPlanetGen_50km_FusedPrototype.umap":
        "4C84D7752C87854C70987ED9988C64C124C577FBE1DE3DEF3CC826F81B0B6284",
    r"D:\RedMMOTitan\Content\RedMMO\Maps\Tests\RedPlanetGen_50km_FusedPrototype_Night_T03.umap":
        "211429783F757F3CD8DE4A37B1E37B4A117125BF26EBFCBACF97CCFA9EFBE8D7",
    r"D:\RedMMOTitanWindowsData\Rollback\BeforeCoastDatum_20260714\RedPlanetGen_50km_FusedPrototype.umap":
        "A9C42C0D1B0429DD1018F00F0D2AB8A18F66C07291611964EFF5F9710F3B0C6A",
}
ROOT = r"D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_PPG_RuntimeShipAnchor_R14_20260802"
RESULT = os.path.join(ROOT, "probe_redmmo_ppg_runtime_ship_anchor_r14_result.json")
PROVIDER_PORTS = (5353, 8000, 8765)
FORWARD_CM = 2200.0
RIGHT_CM = 450.0
SETTLE_FRAMES = 60
COLLISION_READY_FRAMES = 180
REVIEWED_TRACE_SOURCES = {
    r"D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_PPG_HomeFoliageRebind_R09_GPU_R02_20260802_031657\capture_r09_surface_resolved_d3d12.py":
        "E154321ACB7716BA375BD0596C396BBF79A38AB393BFA815849F8B995C4AA270",
    r"D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_PPG_HomeFoliageRebind_R09_GPU_R03_20260802_033033\capture_r09_surface_resolved_d3d12_r03.py":
        "FA19873211491F9B1794C82CE168D70C9BFD3C65BDA82AD196D4D2ECCE9DC995",
}


def require(value, message):
    if not value:
        raise RuntimeError(message)


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def vec(value):
    return [float(value.x), float(value.y), float(value.z)]


def rot(value):
    return [float(value.pitch), float(value.yaw), float(value.roll)]


def add(a, b):
    return unreal.Vector(a.x + b.x, a.y + b.y, a.z + b.z)


def sub(a, b):
    return unreal.Vector(a.x - b.x, a.y - b.y, a.z - b.z)


def mul(value, scalar):
    return unreal.Vector(value.x * scalar, value.y * scalar, value.z * scalar)


def dot(a, b):
    return float(a.x * b.x + a.y * b.y + a.z * b.z)


def cross(a, b):
    return unreal.Vector(a.y * b.z - a.z * b.y,
                         a.z * b.x - a.x * b.z,
                         a.x * b.y - a.y * b.x)


def length(value):
    return math.sqrt(dot(value, value))


def normalized(value):
    magnitude = length(value)
    require(magnitude > 1.0e-6, "Cannot normalize a zero vector")
    return mul(value, 1.0 / magnitude)


def asset_path(value):
    if value is None:
        return None
    path = value.get_path_name().split(":", 1)[0]
    leaf = path.rsplit("/", 1)[-1]
    return path.rsplit(".", 1)[0] if "." in leaf else path


def dirty_packages():
    packages = list(unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages())
    packages += list(unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages())
    return sorted({package.get_path_name() for package in packages})


def provider_gate():
    state = {}
    for port in PROVIDER_PORTS:
        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        probe.settimeout(0.15)
        try:
            state[str(port)] = probe.connect_ex(("127.0.0.1", port)) != 0
        finally:
            probe.close()
    require(all(state.values()), f"Provider/MCP listener is active: {state}")
    return state


def verify_hashes(records, label):
    actual = {}
    for path, expected in records.items():
        require(os.path.isfile(path), f"{label} missing: {path}")
        actual[path] = sha256(path)
        require(actual[path] == expected, f"{label} hash drift: {path}")
    return actual


def hit_value(hit, names, default=None):
    for name in names:
        try:
            return hit.get_editor_property(name)
        except Exception:
            pass
    return default


def trace_type(name):
    direct = getattr(unreal.TraceTypeQuery, name, None)
    if direct is not None:
        return direct
    engine_types = getattr(unreal, "EngineTypes", None)
    convert = getattr(engine_types, "convert_to_trace_type", None)
    channel = getattr(unreal.CollisionChannel, name, None)
    require(callable(convert) and channel is not None, f"Trace type unavailable: {name}")
    return convert(channel)


def unpack_hit(raw):
    values = raw if isinstance(raw, tuple) else (raw,)
    for value in values:
        if value is None or isinstance(value, bool):
            continue
        point = hit_value(value, ("impact_point", "location"))
        if isinstance(point, unreal.Vector):
            return value
    return None


def player_view(controller, pawn):
    method = getattr(controller, "get_player_view_point", None)
    if callable(method):
        raw = method()
        values = raw if isinstance(raw, tuple) else (raw,)
        location = next((v for v in values if isinstance(v, unreal.Vector)), None)
        rotation = next((v for v in values if isinstance(v, unreal.Rotator)), None)
        if location is not None and rotation is not None:
            return location, rotation
    return pawn.get_actor_eyes_view_point()


class RuntimeShipAnchorProbe:
    def __init__(self):
        self.editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
        self.level = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
        self.handle = None
        self.phase = "PREPARE"
        self.phase_started = time.monotonic()
        self.world = self.spawner = self.pawn = self.controller = None
        self.movement = self.ship = None
        self.last_location = None
        self.settle_frames = 0
        self.ready_frames = 0
        self.failure = None
        self.published = False
        self.report = {
            "schema": "redmmo.ppg_runtime_ship_anchor.r14.no_save_probe.v1",
            "status": "RUNNING",
            "project": PROJECT,
            "map": MAP,
            "map_sha256": MAP_SHA,
            "evidence_class": "automation_real_pie_runtime_collision_readback",
            "script_write_contract": {
                "pawn_transform_writes": False,
                "ship_transform_writes": False,
                "controller_rotation_writes": False,
                "input_injection": False,
                "planet_regeneration_requested": False,
                "map_or_asset_save": False,
            },
        }

    def set_phase(self, phase):
        self.phase = phase
        self.phase_started = time.monotonic()
        unreal.log("REDMMO_R14_SHIP_ANCHOR_PHASE " + phase)

    def start(self):
        require(not os.path.exists(RESULT), "R14 result no-clobber failed")
        self.handle = unreal.register_slate_post_tick_callback(self.tick)

    def prepare(self):
        require(sha256(MAP_FILE) == MAP_SHA, "R14 home-map hash drift")
        self.report["protected_hashes"] = verify_hashes(PROTECTED, "protected checkpoint")
        self.report["reviewed_trace_source_hashes"] = verify_hashes(
            REVIEWED_TRACE_SOURCES, "reviewed R09 trace source"
        )
        require(not dirty_packages(), f"Dirty packages before R14 probe: {dirty_packages()}")
        self.report["provider_ports_closed"] = provider_gate()
        project = unreal.Paths.convert_relative_path_to_full(unreal.Paths.get_project_file_path())
        require(unreal.Paths.is_same_path(project, PROJECT), f"Wrong project: {project}")
        require(not self.level.is_in_play_in_editor(), "PIE is already active")
        editor_world = self.editor.get_editor_world()
        current = editor_world.get_path_name().split(":", 1)[0].split(".", 1)[0]
        require(current == MAP, f"Wrong map: {current}")
        self.level.editor_request_begin_play()
        self.set_phase("WAIT_PIE")

    def bind(self):
        world = self.editor.get_game_world()
        if world is None or not self.level.is_in_play_in_editor():
            return False
        actors = list(unreal.GameplayStatics.get_all_actors_of_class(world, unreal.Actor))
        spawners = [a for a in actors if a.get_class().get_name() == "PlanetSpawnerBP_C"]
        ships = [a for a in actors if a.get_actor_label() == SHIP_LABEL]
        pawn = unreal.GameplayStatics.get_player_pawn(world, 0)
        controller = unreal.GameplayStatics.get_player_controller(world, 0)
        if pawn is None or controller is None or not spawners:
            return False
        require(len(spawners) == 1, f"Expected one PlanetSpawnerBP_C, found {len(spawners)}")
        require(len(ships) == 1, f"Expected one visual ship, found {len(ships)}")
        require(asset_path(pawn.get_class()) == PAWN, f"Unexpected normal-spawn pawn: {pawn.get_class()}")
        movements = list(pawn.get_components_by_class(unreal.CharacterMovementComponent))
        require(len(movements) == 1, f"Expected one CharacterMovementComponent, found {len(movements)}")
        require(callable(getattr(movements[0], "is_moving_on_ground", None)),
                "Grounded-state API is unavailable")
        self.world, self.spawner, self.pawn, self.controller = world, spawners[0], pawn, controller
        self.movement, self.ship = movements[0], ships[0]
        require(not self.ship.get_actor_enable_collision(), "Visual ship collision is enabled")
        scale = self.ship.get_actor_scale3d()
        require(all(abs(v - 1.0) <= 0.001 for v in (scale.x, scale.y, scale.z)),
                f"Visual ship is not at native scale: {vec(scale)}")
        self.report["normal_spawn"] = {
            "pawn": pawn.get_path_name(),
            "initial_location": vec(pawn.get_actor_location()),
            "spawner": self.spawner.get_path_name(),
            "existing_ship": self.ship.get_path_name(),
            "existing_ship_location": vec(self.ship.get_actor_location()),
            "existing_ship_rotation": rot(self.ship.get_actor_rotation()),
            "existing_ship_scale": vec(scale),
        }
        self.set_phase("WAIT_GENERATION")
        return True

    def generation_ready(self):
        status = self.spawner.get_planet_generation_status()
        phase = str(status.get_editor_property("phase"))
        progress = float(status.get_editor_property("progress"))
        generating = bool(status.get_editor_property("is_generating"))
        self.report["generation"] = {
            "phase": phase, "progress": progress, "is_generating": generating,
        }
        return "COMPLETE" in phase.upper() and progress >= 0.999 and not generating

    def sample_settle(self):
        location = self.pawn.get_actor_location()
        velocity = self.pawn.get_velocity()
        delta = length(sub(location, self.last_location)) if self.last_location is not None else float("inf")
        speed = length(velocity)
        grounded = bool(self.movement.is_moving_on_ground())
        generation_ready = self.generation_ready()
        stable = grounded and speed <= 5.0 and delta <= 2.0 and generation_ready
        self.settle_frames = self.settle_frames + 1 if stable else 0
        self.ready_frames = self.ready_frames + 1 if generation_ready else 0
        self.last_location = location
        self.report["settle"] = {
            "location": vec(location), "velocity_cm_s": vec(velocity), "speed_cm_s": speed,
            "frame_delta_cm": delta, "grounded": grounded,
            "settled_consecutive_frames": self.settle_frames,
            "complete_consecutive_frames": self.ready_frames,
        }
        return self.settle_frames >= SETTLE_FRAMES and self.ready_frames >= COLLISION_READY_FRAMES

    def trace_methods(self, start, end, ignored):
        attempts = []
        accepted = None
        terrain_paths = {
            component.get_path_name()
            for component in self.spawner.get_components_by_class(unreal.StaticMeshComponent)
            if component.is_query_collision_enabled()
            and component.get_editor_property("static_mesh") is not None
        }
        require(terrain_paths, "Unique PPG spawner has no allowlisted query-collision terrain")
        for name in ("ECC_VISIBILITY", "ECC_PAWN"):
            record = {"method": "LINE_TRACE_" + name, "accepted_ppg_terrain": False}
            try:
                raw = unreal.SystemLibrary.line_trace_single(
                    self.world, start, end, trace_type(name), True, ignored,
                    unreal.DrawDebugTrace.NONE, True,
                    unreal.LinearColor(1.0, 0.0, 0.0, 1.0),
                    unreal.LinearColor(0.0, 1.0, 0.0, 1.0), 0.0,
                )
                hit = unpack_hit(raw)
                if hit is not None:
                    actor = hit_value(hit, ("hit_actor", "actor"))
                    component = hit_value(hit, ("hit_component", "component"))
                    point = hit_value(hit, ("impact_point", "location"))
                    normal = hit_value(hit, ("impact_normal", "normal"))
                    blocking = bool(hit_value(hit, ("blocking_hit", "bBlockingHit"), False))
                    accepted_here = bool(
                        blocking and actor == self.spawner and component is not None
                        and component.get_path_name() in terrain_paths
                        and isinstance(point, unreal.Vector) and isinstance(normal, unreal.Vector)
                    )
                    record.update({
                        "blocking_hit": blocking,
                        "hit_actor": actor.get_path_name() if actor else None,
                        "hit_component": component.get_path_name() if component else None,
                        "impact_point": vec(point) if isinstance(point, unreal.Vector) else None,
                        "impact_normal": vec(normal) if isinstance(normal, unreal.Vector) else None,
                        "accepted_ppg_terrain": accepted_here,
                    })
                    if accepted_here:
                        accepted = (record, point, normal)
            except Exception as error:
                record["call_error"] = str(error)
            attempts.append(record)
            if accepted is not None:
                break
        self.report["trace_attempts"] = attempts
        self.report["allowlisted_query_collision_terrain_components"] = len(terrain_paths)
        require(accepted is not None, "No authoritative collision hit owned by the unique PPG spawner")
        return accepted

    def probe(self):
        require(self.generation_ready(), "PPG lost COMPLETE state before R14 trace")
        pawn_location = self.pawn.get_actor_location()
        require(length(sub(pawn_location, self.last_location)) <= 2.0,
                "Normal-spawn pawn moved after settle gate")
        center = self.spawner.get_actor_location()
        radial_up = normalized(sub(pawn_location, center))
        camera_location, camera_rotation = player_view(self.controller, self.pawn)
        camera_forward = unreal.MathLibrary.get_forward_vector(camera_rotation)
        tangent_forward = sub(camera_forward, mul(radial_up, dot(camera_forward, radial_up)))
        if length(tangent_forward) < 0.5:
            pawn_forward = self.pawn.get_actor_forward_vector()
            tangent_forward = sub(pawn_forward, mul(radial_up, dot(pawn_forward, radial_up)))
        tangent_forward = normalized(tangent_forward)
        tangent_right = normalized(cross(radial_up, tangent_forward))
        candidate_vector = add(add(sub(pawn_location, center), mul(tangent_forward, FORWARD_CM)),
                               mul(tangent_right, RIGHT_CM))
        candidate_direction = normalized(candidate_vector)
        planet_data = self.spawner.get_editor_property("planet_data")
        radius = float(planet_data.get_editor_property("planet_radius"))
        start = add(center, mul(candidate_direction, radius + 250000.0))
        end = add(center, mul(candidate_direction, radius - 250000.0))
        actors = list(unreal.GameplayStatics.get_all_actors_of_class(self.world, unreal.Actor))
        ignored = [actor for actor in actors if actor != self.spawner]
        accepted, point, raw_normal = self.trace_methods(start, end, ignored)
        normal = normalized(raw_normal)
        outward = normalized(sub(point, center))
        if dot(normal, outward) < 0.0:
            normal = mul(normal, -1.0)
        require(dot(normal, outward) >= 0.90, "Actual impact normal is not plausibly outward")
        distance = length(sub(point, pawn_location))
        require(1500.0 <= distance <= 3500.0, f"Proposed ship anchor is not nearby: {distance} cm")

        mesh = unreal.EditorAssetLibrary.load_asset(SHIP_MESH)
        require(isinstance(mesh, unreal.StaticMesh), "StarSparrow mesh is unavailable")
        bounds = mesh.get_bounding_box()
        clearance = max(0.0, -float(bounds.min.z)) + 5.0
        root_location = add(point, mul(normal, clearance))
        heading = sub(tangent_forward, mul(normal, dot(tangent_forward, normal)))
        require(length(heading) >= 0.25, "Camera tangent is degenerate on the hit plane")
        heading = normalized(heading)
        root_rotation = unreal.MathLibrary.make_rot_from_xz(heading, normal)
        camera_dot = dot(normalized(sub(root_location, camera_location)), normalized(camera_forward))
        require(camera_dot >= 0.97, f"Proposed ship anchor is outside intended camera cone: {camera_dot}")
        self.report.update({
            "status": "PASS_NO_SAVE_RUNTIME_ANCHOR_PENDING_SEPARATE_SERIALIZED_RELOCATION",
            "normal_spawn_final": {
                "pawn_location": vec(pawn_location),
                "camera_location": vec(camera_location),
                "camera_rotation": rot(camera_rotation),
                "radial_up": vec(radial_up),
            },
            "candidate": {
                "tangent_offset_cm": {"forward": FORWARD_CM, "right": RIGHT_CM},
                "candidate_direction": vec(candidate_direction),
                "trace_start": vec(start), "trace_end": vec(end),
                "surface_point": vec(point), "actual_impact_normal": vec(normal),
                "surface_normal_source": "authoritative_collision_hit_impact_normal",
                "surface_normal_radial_dot": dot(normal, outward),
                "pawn_to_surface_cm": distance,
                "accepted_trace": accepted,
            },
            "proposed_native_scale_ship_transform": {
                "location": vec(root_location), "rotation": rot(root_rotation),
                "scale": [1.0, 1.0, 1.0],
                "mesh_bounds_min_z_cm": float(bounds.min.z),
                "surface_clearance_cm": 5.0,
                "root_contact_offset_cm": clearance,
                "camera_forward_dot_root": camera_dot,
                "applied_to_runtime_ship": False,
            },
        })
        self.set_phase("REQUEST_CLEAN_END")

    def publish_result(self):
        require(not self.published, "R14 result publication attempted twice")
        require(not self.level.is_in_play_in_editor() and self.editor.get_game_world() is None,
                "R14 result cannot publish before clean PIE end")
        map_after = sha256(MAP_FILE) if os.path.isfile(MAP_FILE) else None
        dirty_after = dirty_packages()
        protected_after = {
            path: sha256(path) if os.path.isfile(path) else None for path in PROTECTED
        }
        try:
            providers_after = provider_gate()
        except Exception as error:
            providers_after = {"gate_error": str(error)}
        providers_ok = all(providers_after.get(str(port)) is True for port in PROVIDER_PORTS)
        preservation_ok = (
            map_after == MAP_SHA and not dirty_after
            and protected_after == self.report.get("protected_hashes")
            and providers_ok
        )
        self.report.update({
            "map_sha256_after": map_after,
            "dirty_packages_after": dirty_after,
            "protected_hashes_after": protected_after,
            "provider_ports_closed_after": providers_after,
            "preservation_gates_passed": preservation_ok,
        })
        if self.report["status"].startswith("PASS"):
            require(preservation_ok, "R14 post-probe preservation gate failed")
        self.report["clean_pie_end"] = True
        self.report["map_saved"] = False
        os.makedirs(ROOT, exist_ok=True)
        with open(RESULT, "xb") as handle:
            handle.write((json.dumps(self.report, indent=2, sort_keys=True) + "\n").encode("utf-8"))
            handle.flush()
            os.fsync(handle.fileno())
        self.published = True
        if self.handle is not None:
            unreal.unregister_slate_post_tick_callback(self.handle)
            self.handle = None
        if self.report["status"].startswith("PASS"):
            unreal.log("REDMMO_R14_RUNTIME_SHIP_ANCHOR_PROBE PASS")
        else:
            unreal.log_error("REDMMO_R14_RUNTIME_SHIP_ANCHOR_PROBE FAIL " + self.report.get("error", ""))

    def fail(self, error):
        if self.failure is not None:
            return
        self.failure = error
        self.report.update({"status": "FAIL", "error": str(error), "traceback": traceback.format_exc()})
        if self.level.is_in_play_in_editor():
            self.level.editor_request_end_play()
            self.set_phase("FAIL_WAIT_CLEAN_END")
        else:
            self.publish_result()

    def tick(self, _delta):
        try:
            elapsed = time.monotonic() - self.phase_started
            if self.phase == "PREPARE":
                self.prepare()
            elif self.phase == "WAIT_PIE":
                require(elapsed <= 60.0, "Timed out waiting for normal-spawn PIE")
                self.bind()
            elif self.phase == "WAIT_GENERATION":
                require(elapsed <= 180.0, "Timed out waiting for PPG COMPLETE")
                if self.generation_ready():
                    self.set_phase("WAIT_NORMAL_PAWN_SETTLE")
            elif self.phase == "WAIT_NORMAL_PAWN_SETTLE":
                require(elapsed <= 120.0, "Timed out waiting for grounded normal pawn and collision settle")
                if self.sample_settle():
                    self.set_phase("TRACE")
            elif self.phase == "TRACE":
                self.probe()
            elif self.phase == "REQUEST_CLEAN_END":
                self.level.editor_request_end_play()
                self.set_phase("WAIT_CLEAN_END")
            elif self.phase in ("WAIT_CLEAN_END", "FAIL_WAIT_CLEAN_END"):
                require(elapsed <= 90.0, "Timed out waiting for clean PIE end")
                if not self.level.is_in_play_in_editor() and self.editor.get_game_world() is None:
                    self.publish_result()
        except Exception as error:
            self.fail(error)


PROBE = RuntimeShipAnchorProbe()
PROBE.start()
