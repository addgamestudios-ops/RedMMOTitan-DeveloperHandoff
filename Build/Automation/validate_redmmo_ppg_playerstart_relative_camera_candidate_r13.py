"""Run a no-save R13 PlayerStart probe using a direct gravity-relative seed.

PPG's controller preserves the initial PlayerStart Euler pitch/yaw as its
gravity-relative view while radial gravity initializes.  This probe therefore
stores the already-derived tangent-relative yaw directly on PlayerStart instead
of converting it back to a gravity-world rotator.  The map is never saved.
"""

from __future__ import annotations

import hashlib


SOURCE = r"D:\RedMMOTitan\Build\Automation\validate_redmmo_ppg_playerstart_camera_candidate_r13.py"
EXPECTED_SOURCE_SHA = "F9E18FD2D88A79FE508B53F58277772C48347A79C2EA80CBF44E9D3B288AE6AC"


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def replace_exact(source, old, new, count=1):
    actual = source.count(old)
    if actual != count:
        raise RuntimeError(f"Reviewed relative-seed candidate marker drift: {old!r} count={actual}")
    return source.replace(old, new)


if sha256(SOURCE) != EXPECTED_SOURCE_SHA:
    raise RuntimeError("Reviewed R13 candidate source hash drift")
with open(SOURCE, "r", encoding="utf-8") as handle:
    code = handle.read()

code = replace_exact(
    code,
    r'ROOT = r"D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_PPG_PlayerStartCamera_R13Candidate_20260802"',
    r'ROOT = r"D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_PPG_PlayerStartCamera_R13Candidate3_20260802"',
)
code = replace_exact(
    code,
    '''        target = unreal.MathLibrary.make_rot_from_xz(tangent, radial_up)
        require(start.set_actor_rotation(target, False), "Transient PlayerStart rotation failed")''',
    '''        tangent_world = unreal.MathLibrary.make_rot_from_xz(tangent, radial_up)
        gravity_direction = mul(radial_up, -1.0)
        tangent_relative = unreal.GravityController.get_gravity_relative_rotation(
            tangent_world, gravity_direction
        )
        target = unreal.Rotator(roll=0.0, pitch=0.0, yaw=float(tangent_relative.yaw))
        require(start.set_actor_rotation(target, False), "Transient PlayerStart relative seed failed")''',
)
code = replace_exact(
    code,
    '''            elif self.phase == "WAIT_PIE_END":
                require(elapsed <= 90.0, "PIE shutdown timeout")
                if not self.level.is_in_play_in_editor() and self.editor.get_game_world() is None and elapsed >= 1.0:
                    require(unreal.EditorLoadingAndSavingUtils.load_map(MAP), "Unable to reload home map")
                    self.set_phase("WAIT_RELOAD")
            elif self.phase == "WAIT_RELOAD":
                require(elapsed <= 90.0, "Map reload timeout")
                world = self.editor.get_editor_world()
                if world is not None and world.get_path_name().split(":", 1)[0].split(".", 1)[0] == MAP and elapsed >= 1.0:
                    self.finish_after_reload()''',
    '''            elif self.phase == "WAIT_PIE_END":
                require(elapsed <= 90.0, "PIE shutdown timeout")
                if not self.level.is_in_play_in_editor() and elapsed >= 1.0:
                    require(sha256(MAP_FILE) == EXPECTED_MAP_SHA, "Candidate changed home-map file")
                    for path, expected in PROTECTED.items():
                        require(sha256(path) == expected, "Protected checkpoint drift: " + path)
                    require(os.path.isfile(SCREENSHOT) and os.path.getsize(SCREENSHOT) > 10000, "Screenshot missing")
                    view = self.report["default_view"]
                    self.report["candidate_structural_gate"] = {
                        "ship_in_front": view["camera_forward_dot_ship"] > 0.10,
                        "not_skyward": view["camera_forward_dot_radial_up"] < 0.35,
                    }
                    self.report["status"] = "PASS_REAL_D3D12_NO_SAVE_PLAYERSTART_RELATIVE_SEED_PENDING_HUMAN_VISUAL_REVIEW"
                    self.report["screenshot"] = {
                        "path": SCREENSHOT, "sha256": sha256(SCREENSHOT), "bytes": os.path.getsize(SCREENSHOT)
                    }
                    self.report["cleanup"] = {
                        "map_file_unchanged": True,
                        "transient_editor_transform_unsaved": True,
                        "required_outer_action": "close exact launched editor PID without saving",
                    }
                    atomic_json(RESULT, self.report)
                    self.publish()
                    if self.handle is not None:
                        unreal.unregister_slate_post_tick_callback(self.handle)
                        self.handle = None
                    unreal.log("REDMMO_R13_PLAYERSTART_RELATIVE_CAMERA_CANDIDATE PASS")''',
)
code = replace_exact(
    code,
    "redmmo.ppg_playerstart_camera.r13_candidate.real_pie.v1",
    "redmmo.ppg_playerstart_camera.r13_candidate3.relative_seed.real_pie.v1",
    count=2,
)

exec(compile(code, SOURCE, "exec"), globals(), globals())
