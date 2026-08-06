"""R43 fresh-process untouched Lit-first proof for approved grass render-state recreation."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import unreal


BASE_PATH = Path("D:/RedMMOTitan/Build/Automation/verify_redmmo_grass_render_refresh_r41b_lit_first.py")
SPEC = importlib.util.spec_from_file_location("redmmo_r41b_grass_verify_base_for_r43", BASE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("Unable to load proven R41B Lit-first verifier")

base = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(base)

base.DIAG = Path("D:/RedMMOTitanWindowsData/Diagnostics/RedMMO_GrassRenderStateRecreate_R43_20260805T1605Z")
base.RESULT = base.DIAG / "result.json"
base.LIT = base.DIAG / "R43_untouched_lit_first_after_recreate.png"
base.CHECKS[base.HEADER_FILE] = "124F119FAE6172E19C8EB124F703DDAB9DD063573BB6DC74376EA8093C1C0D0D"
base.CHECKS[base.SOURCE_FILE] = "6CEF739924C45D891AD9B90EFD388342530ADEAA0ECDA240052C95CDE605A577"
base.CHECKS[base.BINARY_FILE] = "35F92BE77C67F7CC85835ABDEF2EA9BC6D9BA02774DE27BB976737F0343726E9"

original_capture = base.R41B.capture_lit_first


def capture_r43(self):
    game_mode = unreal.GameplayStatics.get_game_mode(self.world)
    base.require(game_mode is not None, "R43 GameMode missing")
    hook = {
        "game_mode_class": game_mode.get_class().get_name(),
        "recreated": bool(game_mode.get_editor_property("approved_grass_render_state_recreated")),
        "components": int(game_mode.get_editor_property("approved_grass_render_state_component_count")),
        "instances": int(game_mode.get_editor_property("approved_grass_render_state_instance_count")),
    }
    base.require(hook["recreated"], "approved grass render-state recreation did not fire")
    base.require(hook["components"] == 196 and hook["instances"] == 2218356,
                 "approved grass render-state recreation census drift: " + repr(hook))
    self.report["approved_render_state_recreate"] = hook
    self.report["approved_render_state_recreate_called"] = True
    original_capture(self)


def finish_r43(self):
    base.require(not self.level.is_in_play_in_editor(), "PIE did not stop")
    base.require(base.dirty_packages() == {"content": [], "maps": []}, "PIE dirtied packages")
    for path, expected in base.CHECKS.items():
        base.require(base.sha256(path) == expected, "post-PIE drift: " + str(path))
    self.report.update({
        "schema": "redmmo.grass_render_state_recreate.verify.r43.v1",
        "status": "PASS_R43_UNTOUCHED_LIT_FIRST_CAPTURE_PENDING_VISUAL_REVIEW",
        "completed_utc": base.now(),
        "dirty_packages_after": base.dirty_packages(),
        "provider_gate_after": base.provider_gate(),
        "save_called": False,
        "visibility_cycle_called": False,
        "view_mode_command_called_before_capture": False,
        "component_property_mutation_called": False,
        "claim_limit": (
            "Fresh-reload untouched Lit-first D3D12 PIE visual after one approved-only render-state recreation; "
            "no map/content save, package, replication, multiplayer or user-acceptance claim."
        ),
    })
    base.atomic_json(base.RESULT, self.report)
    unreal.log("REDMMO_R43_PASS")
    self.phase = "DONE"
    self.schedule_quit(3.0)


base.R41B.capture_lit_first = capture_r43
base.R41B.finish = finish_r43
base._R41B.report.update({
    "schema": "redmmo.grass_render_state_recreate.verify.r43.v1",
    "slice": "R43 approved-only true render-state recreation",
    "expected_components": 196,
    "expected_instances": 2218356,
})
unreal.log("REDMMO_R43_VERIFY_STARTED")
