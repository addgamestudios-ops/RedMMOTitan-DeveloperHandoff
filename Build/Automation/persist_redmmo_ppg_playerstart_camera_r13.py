"""Persist only the reviewed R13 PlayerStart gravity-relative camera seed."""

from __future__ import annotations

import hashlib
import json
import math
import os
import socket
import traceback

import unreal


PROJECT = r"D:\RedMMOTitanWindowsData\Projects\RedMMO\RedMMO.uproject"
MAP = "/Game/RedMMO/Maps/RedMMO_PPG_HomeWorld"
MAP_FILE = (
    r"D:\RedMMOTitanWindowsData\Projects\RedMMO\Content\RedMMO"
    r"\Maps\RedMMO_PPG_HomeWorld.umap"
)
EXPECTED_MAP = "0A7252E93F6F75FA7FAFAD856C7249E6964C27E34B9DD1386202080E2FD2D6CF"
EXPECTED_FILES = {
    r"D:\RedMMOTitanWindowsData\Projects\RedMMO\Content\RedMMO\Gameplay\Player\BP_RedPlanetCharacter_R11.uasset":
        "65A0413D1921F8ED2F6E4E3893B1C6B5CA3A0D1F7BCFC9AF9BF987940ECDC11E",
    r"D:\RedMMOTitanWindowsData\Projects\RedMMO\Content\RedMMO\Gameplay\Player\GM_RedPlanet_R11.uasset":
        "0696DE6039A5389BF0F872DB84D970E981C69184CD3AEA0279D89001B98BBEBD",
    r"D:\RedMMOTitanWindowsData\Projects\RedMMO\Content\RedMMO\Gameplay\Input\IMC_RedPlanet_R11.uasset":
        "09AC8B9CAB42342C49A22BC6CC1B4A1770B9FB56CE1E251A8E0B0C50581E1DC6",
    r"D:\RedMMOTitanWindowsData\Projects\RedMMO\Content\RedMMO\Gameplay\World\BP_RedParkedStarSparrow_R12.uasset":
        "C9FDCF7D0FE89DACE39D418B79A7951C37C699C1FEA7E485C85670B2AB864BD6",
}
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
ROLLBACK_MANIFEST = (
    r"D:\RedMMOTitanWindowsData\Rollback"
    r"\RedMMO_PPG_PlayerStartCamera_R13_20260802_Candidate3"
    r"\pre_r13_playerstart_manifest.json"
)
ROOT = (
    r"D:\RedMMOTitanWindowsData\Diagnostics"
    r"\RedMMO_PPG_PlayerStartCamera_R13PersistV6_20260802"
)
RESULT = os.path.join(ROOT, "persist_redmmo_ppg_playerstart_camera_r13_result.json")
EXPECTED_BEFORE = {"pitch": 47.790019, "yaw": 158.480630, "roll": 161.955720}
TARGET = {"pitch": 0.0, "yaw": -5.282777, "roll": 0.0}
AUTHORIZED_SCOPE = (
    "Only the unique home-map PlayerStart rotation may change from "
    "(47.790019,158.480630,161.955720) to (0,-5.282777,0)."
)
EXPECTED_CANDIDATE_SHA = (
    "E0A2B3953594778D1CBC93CC8E4681EB9B902AC292E66257D75342B5A864DFCB"
)


def require(value, message: str) -> None:
    if not value:
        raise RuntimeError(message)


def sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def verify(records: dict[str, str], label: str) -> dict[str, str]:
    actual: dict[str, str] = {}
    for path, expected in records.items():
        require(os.path.isfile(path), f"{label} missing: {path}")
        actual[path] = sha256(path)
        require(
            actual[path] == expected,
            f"{label} hash drift: {path} expected={expected} actual={actual[path]}",
        )
    return actual


def dirty_packages() -> dict[str, list[str]]:
    return {
        "content": sorted(
            {
                value.get_path_name()
                for value in unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages()
            }
        ),
        "maps": sorted(
            {
                value.get_path_name()
                for value in unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()
            }
        ),
    }


def provider_gate() -> dict[str, bool]:
    state: dict[str, bool] = {}
    for port in (5353, 8000, 8765):
        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        probe.settimeout(0.15)
        try:
            state[str(port)] = probe.connect_ex(("127.0.0.1", port)) != 0
        finally:
            probe.close()
    require(all(state.values()), f"Provider/MCP listener unexpectedly open: {state}")
    return state


def rotation_dict(value) -> dict[str, float]:
    return {
        "pitch": float(value.pitch),
        "yaw": float(value.yaw),
        "roll": float(value.roll),
    }


def rotation_matches(actual: dict[str, float], expected: dict[str, float], tolerance=0.05):
    return all(
        math.isclose(actual[key], expected[key], abs_tol=tolerance)
        for key in ("pitch", "yaw", "roll")
    )


def transform_record(actor) -> dict[str, object]:
    location = actor.get_actor_location()
    rotation = actor.get_actor_rotation()
    scale = actor.get_actor_scale3d()
    parent = actor.get_attach_parent_actor()
    root = actor.get_editor_property("root_component")
    relative_location = (
        root.get_editor_property("relative_location") if root is not None else location
    )
    relative_rotation = (
        root.get_editor_property("relative_rotation") if root is not None else rotation
    )
    relative_scale = (
        root.get_editor_property("relative_scale3d") if root is not None else scale
    )
    return {
        "class": actor.get_class().get_path_name(),
        "label": actor.get_actor_label(),
        "attach_parent": parent.get_path_name() if parent is not None else None,
        "location": [float(location.x), float(location.y), float(location.z)],
        "rotation": rotation_dict(rotation),
        "scale": [float(scale.x), float(scale.y), float(scale.z)],
        "relative_location": [
            float(relative_location.x),
            float(relative_location.y),
            float(relative_location.z),
        ],
        "relative_rotation": rotation_dict(relative_rotation),
        "relative_scale": [
            float(relative_scale.x),
            float(relative_scale.y),
            float(relative_scale.z),
        ],
    }


def non_playerstart_actor_snapshot(actors) -> dict[str, dict[str, object]]:
    records: dict[str, dict[str, object]] = {}
    for actor in actors:
        if actor.get_class().get_name() == "PlayerStart":
            continue
        path = actor.get_path_name()
        require(path not in records, f"Duplicate actor path in snapshot: {path}")
        records[path] = transform_record(actor)
    return dict(sorted(records.items()))


def angle_delta(a: float, b: float) -> float:
    return abs((a - b + 180.0) % 360.0 - 180.0)


def actor_snapshot_differences(
    before: dict[str, dict[str, object]],
    after: dict[str, dict[str, object]],
    tolerance: float = 0.001,
) -> list[dict[str, object]]:
    differences: list[dict[str, object]] = []
    before_keys = set(before)
    after_keys = set(after)
    if before_keys != after_keys:
        differences.append(
            {
                "kind": "actor_identity_set",
                "missing": sorted(before_keys - after_keys),
                "added": sorted(after_keys - before_keys),
            }
        )
        return differences
    for path in sorted(before_keys):
        left = before[path]
        right = after[path]
        record: dict[str, object] = {"path": path, "deltas": {}}
        deltas = record["deltas"]
        if left["class"] != right["class"]:
            deltas["class"] = [left["class"], right["class"]]
        if left["label"] != right["label"]:
            deltas["label"] = [left["label"], right["label"]]
        if left["attach_parent"] != right["attach_parent"]:
            deltas["attach_parent"] = [
                left["attach_parent"],
                right["attach_parent"],
            ]
        attached = left["attach_parent"] is not None
        vector_fields = (
            ("relative_location", "relative_scale")
            if attached
            else ("location", "scale")
        )
        for field in vector_fields:
            values = [abs(float(a) - float(b)) for a, b in zip(left[field], right[field])]
            if max(values, default=0.0) > tolerance:
                deltas[field] = values
        rotation_field = "relative_rotation" if attached else "rotation"
        rotation_deltas = {
            field: angle_delta(
                float(left[rotation_field][field]), float(right[rotation_field][field])
            )
            for field in ("pitch", "yaw", "roll")
        }
        if max(rotation_deltas.values(), default=0.0) > tolerance:
            deltas[rotation_field] = rotation_deltas
        if deltas:
            differences.append(record)
    return differences


def generation_record(spawner) -> dict[str, object]:
    method = getattr(spawner, "get_planet_generation_status", None)
    require(callable(method), "PPG generation status method is unavailable")
    status = method()
    phase = str(status.get_editor_property("phase"))
    progress = float(status.get_editor_property("progress"))
    is_generating = bool(status.get_editor_property("is_generating"))
    require(
        "COMPLETE" in phase.upper() and progress >= 0.999 and not is_generating,
        f"PPG generation is not stable: phase={phase} progress={progress} "
        f"is_generating={is_generating}",
    )
    return {
        "phase": phase,
        "progress": progress,
        "is_generating": is_generating,
    }


def safe_sha256(path: str) -> tuple[str | None, str | None]:
    try:
        return sha256(path), None
    except Exception as error:
        return None, str(error)


payload = {
    "schema": "redmmo.ppg_playerstart_camera.r13.persist.v1",
    "status": "FAIL",
    "rollback_manifest": ROLLBACK_MANIFEST,
}
start = None
before = None
save_attempted = False
save_succeeded = False
disk_mutated = False
rollback_required = False
map_after = None
snapshot_differences: list[dict[str, object]] = []
try:
    require(not os.path.exists(RESULT), "R13 persistence result no-clobber failed")
    require(os.path.isfile(ROLLBACK_MANIFEST), "R13 rollback manifest missing")
    with open(ROLLBACK_MANIFEST, "r", encoding="utf-8") as handle:
        rollback = json.load(handle)
    require(
        rollback.get("schema") == "redmmo.ppg_playerstart_camera.r13.rollback.v1",
        "Wrong R13 rollback schema",
    )
    require(rollback.get("home_map_sha256") == EXPECTED_MAP, "Rollback hash mismatch")
    require(rollback.get("home_map") == MAP_FILE, "Rollback map path mismatch")
    require(
        rollback.get("authorized_scope") == AUTHORIZED_SCOPE,
        "Rollback authorized scope mismatch",
    )
    require(
        rollback.get("candidate3_result_sha256") == EXPECTED_CANDIDATE_SHA,
        "Rollback Candidate3 evidence hash mismatch",
    )
    rollback_copy = rollback.get("rollback_copy", "")
    require(os.path.isfile(rollback_copy), "R13 rollback map copy missing")
    require(sha256(rollback_copy) == EXPECTED_MAP, "R13 rollback copy drift")
    actual_project = unreal.Paths.convert_relative_path_to_full(
        unreal.Paths.get_project_file_path()
    )
    require(unreal.Paths.is_same_path(actual_project, PROJECT), "Wrong project")
    world = unreal.EditorLevelLibrary.get_editor_world()
    world_path = world.get_path_name().split(":", 1)[0].split(".", 1)[0]
    require(world_path == MAP, f"Wrong map: {world_path}")
    require(
        not unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).is_in_play_in_editor(),
        "R13 persistence refused while PIE is active",
    )
    require(sha256(MAP_FILE) == EXPECTED_MAP, "Home-map hash drift")
    verified = verify(EXPECTED_FILES, "R13 invariant")
    protected = verify(PROTECTED, "protected checkpoint")
    providers = provider_gate()
    require(
        dirty_packages() == {"content": [], "maps": []},
        f"R13 persistence requires a clean editor: {dirty_packages()}",
    )
    actors = list(unreal.EditorLevelLibrary.get_all_level_actors())
    starts = [
        actor
        for actor in actors
        if actor.get_class().get_name() == "PlayerStart"
    ]
    require(len(starts) == 1, f"Expected one PlayerStart, found {len(starts)}")
    spawners = [
        actor for actor in actors if actor.get_class().get_name() == "PlanetSpawnerBP_C"
    ]
    require(len(spawners) == 1, f"Expected one PlanetSpawnerBP_C, found {len(spawners)}")
    generation = generation_record(spawners[0])
    non_playerstart_before = non_playerstart_actor_snapshot(actors)
    start = starts[0]
    before = rotation_dict(start.get_actor_rotation())
    require(
        rotation_matches(before, EXPECTED_BEFORE),
        f"PlayerStart pre-rotation drift: {before}",
    )
    target = unreal.Rotator(
        roll=TARGET["roll"], pitch=TARGET["pitch"], yaw=TARGET["yaw"]
    )
    require(start.set_actor_rotation(target, False), "PlayerStart rotation write failed")
    after_transient = rotation_dict(start.get_actor_rotation())
    require(
        rotation_matches(after_transient, TARGET),
        f"PlayerStart transient readback mismatch: {after_transient}",
    )
    non_playerstart_after = non_playerstart_actor_snapshot(
        list(unreal.EditorLevelLibrary.get_all_level_actors())
    )
    snapshot_differences = actor_snapshot_differences(
        non_playerstart_before, non_playerstart_after
    )
    require(
        snapshot_differences == [],
        "A non-PlayerStart actor identity/class/transform changed beyond epsilon "
        f"during R13 write: {snapshot_differences[:5]}",
    )
    generation_after_write = generation_record(spawners[0])
    require(
        generation_after_write == generation,
        f"PPG generation state changed during R13 write: {generation_after_write}",
    )
    require(
        dirty_packages() == {"content": [], "maps": []},
        f"Unexpected dirty package before PlayerStart Modify: {dirty_packages()}",
    )
    modify_result = start.modify()
    after_dirty = dirty_packages()
    require(
        after_dirty["content"] == [] and after_dirty["maps"] == [MAP],
        "PlayerStart Modify dirtied unexpected packages: "
        f"{after_dirty}; return={modify_result}",
    )
    save_attempted = True
    save_succeeded = bool(unreal.EditorLevelLibrary.save_current_level())
    require(save_succeeded, "R13 home-map save failed")
    require(
        dirty_packages() == {"content": [], "maps": []},
        f"Dirty packages remained after R13 save: {dirty_packages()}",
    )
    after_saved = rotation_dict(start.get_actor_rotation())
    require(rotation_matches(after_saved, TARGET), "Saved PlayerStart readback mismatch")
    map_after = sha256(MAP_FILE)
    disk_mutated = map_after != EXPECTED_MAP
    require(map_after != EXPECTED_MAP, "R13 map hash did not change")
    require(verify(EXPECTED_FILES, "R13 invariant after save") == verified,
            "R13 invariant set changed")
    require(verify(PROTECTED, "protected checkpoint after save") == protected,
            "Protected checkpoint set changed")
    payload.update(
        {
            "status": "PASS_SERIALIZED_PENDING_FRESH_RELOAD_MAPCHECK_AND_REAL_PIE",
            "project": PROJECT,
            "map": MAP,
            "map_sha256_before": EXPECTED_MAP,
            "map_sha256_after": map_after,
            "playerstart_before": before,
            "playerstart_after": after_saved,
            "dirty_packages_after_save": dirty_packages(),
            "provider_ports_closed": providers,
            "verified_invariants": verified,
            "protected_hashes": protected,
            "ppg_generation": generation,
            "non_playerstart_actor_count": len(non_playerstart_before),
            "attached_non_playerstart_actor_count": sum(
                1
                for record in non_playerstart_before.values()
                if record["attach_parent"] is not None
            ),
            "playerstart_attached_actor_paths": sorted(
                path
                for path, record in non_playerstart_before.items()
                if record["attach_parent"] == start.get_path_name()
            ),
            "non_playerstart_actor_snapshot_unchanged": True,
            "non_playerstart_transform_epsilon": 0.001,
            "map_reload_in_this_process": False,
            "save_attempted": save_attempted,
            "save_succeeded": save_succeeded,
            "disk_mutated": disk_mutated,
            "rollback_required": False,
        }
    )
except Exception as error:
    current_map_sha, current_map_sha_error = safe_sha256(MAP_FILE)
    disk_mutated = current_map_sha != EXPECTED_MAP
    rollback_required = disk_mutated or current_map_sha is None
    if start is not None and before is not None and not rollback_required:
        try:
            start.set_actor_rotation(
                unreal.Rotator(
                    roll=before["roll"], pitch=before["pitch"], yaw=before["yaw"]
                ),
                False,
            )
        except Exception:
            pass
    payload.update(
        {
            "error": str(error),
            "traceback": traceback.format_exc(),
            "save_attempted": save_attempted,
            "save_succeeded": save_succeeded,
            "current_map_sha256": current_map_sha,
            "current_map_sha256_error": current_map_sha_error,
            "disk_mutated": disk_mutated,
            "rollback_required": rollback_required,
            "non_playerstart_snapshot_differences": snapshot_differences,
            "required_outer_action": (
                "Close the exact editor without saving; restore rollback_copy over "
                "MAP_FILE offline; re-hash before continuing."
                if rollback_required
                else "Close the exact editor without saving; no disk rollback required."
            ),
        }
    )

os.makedirs(ROOT, exist_ok=True)
with open(RESULT + ".tmp", "w", encoding="utf-8", newline="\n") as handle:
    json.dump(payload, handle, indent=2, sort_keys=True)
    handle.write("\n")
os.replace(RESULT + ".tmp", RESULT)
if payload["status"].startswith("PASS"):
    unreal.log("REDMMO_R13_PLAYERSTART_PERSIST PASS")
else:
    unreal.log_error("REDMMO_R13_PLAYERSTART_PERSIST FAIL " + payload.get("error", ""))
