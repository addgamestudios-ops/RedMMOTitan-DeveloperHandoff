"""No-save D3D12 PIE acceptance for the R89 clean jetpack producer.

This adapter reuses the accepted R88 A01 Trooper/StarSparrow path, changes only
its authenticated native source/module identities, and inserts producer-focused
runtime phases between ordinary Jump landing and Fire. It drives the real
Enhanced Input actions, records authority-side replicated getters, then proves
ship possession forces the still-engaged producer off. It saves no package or
configuration and deliberately does not wire or accept HUD/presentation.
"""

from __future__ import annotations

from pathlib import Path


R88 = Path(
    r"D:\RedMMOTitan\Build\Automation"
    r"\validate_clean_redmmo_r88_grounded_footsteps_pie.py"
)

r88_source = R88.read_text(encoding="utf-8")
r88_bootstrap = (
    "\ntry:\n"
    "    b[\"_REDMMO_R88_FOOTSTEP_VALIDATION\"] = A01PIEValidation()"
)
r88_marker = r88_source.rfind(r88_bootstrap)
if r88_marker < 0:
    raise RuntimeError("R88 footstep adapter bootstrap marker drift")

r88_globals = {"__name__": "redmmo_r89_r88_adapter", "__file__": str(R88)}
exec(compile(r88_source[:r88_marker], str(R88), "exec"), r88_globals)

b = r88_globals["b"]
unreal = r88_globals["unreal"]
require = r88_globals["require"]
vec = r88_globals["vec"]
footstep_counts = r88_globals["footstep_counts"]
A01PIEValidation = r88_globals["A01PIEValidation"]

EXPECTED = r88_globals["EXPECTED"]
EXPECTED[r88_globals["EDITOR_DLL"]] = (
    "A38F4D6124E2F5B169E28BF06F2CCD3AAF09C34C48B30413A4D805DA2B344711"
)
EXPECTED[r88_globals["HEADER_FILE"]] = (
    "41CC0642D3E1E70A05381C990C0DF5AC0C9E150F4DCC8FD97003A2ABD24FC425"
)
EXPECTED[r88_globals["SOURCE_FILE"]] = (
    "D871AF7CEAA5329F2AA7DF739CA81108F8DEC4C437F2A54A2C61B1FDA9D645D4"
)


def jetpack_snapshot(self):
    location = self.trooper.get_actor_location()
    radial_up = self.radial_up(location)
    velocity = self.trooper.get_velocity()
    return {
        "fuel": float(self.trooper.get_jetpack_fuel()),
        "fuel_fraction": float(self.trooper.get_jetpack_fuel_fraction()),
        "engaged": bool(self.trooper.is_jetpack_engaged()),
        "thrusting": bool(self.trooper.is_jetpack_thrusting()),
        "boosting": bool(self.trooper.is_jetpack_boosting()),
        "falling": bool(self.movement.is_falling()),
        "location": vec(location),
        "velocity": vec(velocity),
        "radial_speed_cm_s": float(b["dot"](velocity, radial_up)),
    }


old_authenticate_r89 = A01PIEValidation.authenticate_inputs
old_tick_r89 = A01PIEValidation.tick
old_finalize_r89 = A01PIEValidation.finalize_pass


def authenticate_r89(self) -> None:
    old_authenticate_r89(self)
    self.report.update({
        "schema": "redmmo.r89.clean-jetpack-producer.real-d3d12-pie.v1",
        "claim_limit": (
            "One-player no-save D3D12 RenderOffscreen PIE using real A01 Enhanced "
            "Input actions and authority-side jetpack telemetry. It proves the clean "
            "producer's runtime input/state/fuel/movement and possession-shutdown "
            "contract only. It does not accept pixels, sound, physical controls, "
            "packaging, standalone, replication correction quality, or multiplayer."
        ),
    })
    self.report["authenticated_inputs"].update({
        "r89_editor_module_sha256": EXPECTED[r88_globals["EDITOR_DLL"]],
        "r89_player_header_sha256": EXPECTED[r88_globals["HEADER_FILE"]],
        "r89_player_cpp_sha256": EXPECTED[r88_globals["SOURCE_FILE"]],
        "hud_or_presentation_wired": False,
    })


def tick_r89(self, delta_seconds: float) -> None:
    try:
        elapsed = b["time"].monotonic() - self.phase_started

        if self.phase == "R89_TAP1_PRESS":
            require(elapsed <= 1.0, "R89 first jetpack tap press timeout")
            if not hasattr(self, "r89_first_tap_pressed_at"):
                self.r89_first_tap_pressed_at = b["time"].monotonic()
            self.inject("jump", x=1.0)
            require(not self.trooper.is_jetpack_engaged(), "First isolated tap engaged jetpack")
            if elapsed >= 0.08:
                self.set_phase("R89_TAP1_RELEASE", reset_motion=False)
            self.publish_state()
            return

        if self.phase == "R89_TAP1_RELEASE":
            require(elapsed <= 1.0, "R89 first jetpack tap release timeout")
            self.inject("jump")
            require(not self.trooper.is_jetpack_engaged(), "First tap release engaged jetpack")
            if elapsed >= 0.08:
                self.set_phase("R89_TAP2_PRESS", reset_motion=False)
            self.publish_state()
            return

        if self.phase == "R89_TAP2_PRESS":
            require(elapsed <= 1.0, "R89 double-tap engagement timeout")
            self.inject("jump", x=1.0)
            snapshot = jetpack_snapshot(self)
            if snapshot["engaged"] and snapshot["thrusting"]:
                gap = b["time"].monotonic() - self.r89_first_tap_pressed_at
                self.r89_normal_start = snapshot
                self.r89_jetpack_start_location = self.trooper.get_actor_location()
                self.report["tests"]["jetpack_double_tap_engagement"] = {
                    "python_callback_wall_seconds": gap,
                    "python_callback_timing_is_authoritative": False,
                    "compiled_server_window_seconds": 0.30,
                    "snapshot": snapshot,
                    "serialized_physical_key": "SpaceBar",
                    "runtime_action": b["ACTIONS"]["jump"],
                    "server_owned_state_observed_on_authority_pawn": True,
                }
                self.set_phase("R89_NORMAL_THRUST", reset_motion=False)
            self.publish_state()
            return

        if self.phase == "R89_NORMAL_THRUST":
            require(elapsed <= 2.5, "R89 normal-thrust timeout")
            self.inject("jump", x=1.0)
            self.inject("sprint")
            snapshot = jetpack_snapshot(self)
            self.r89_normal_max_radial_speed = max(
                getattr(self, "r89_normal_max_radial_speed", -1.0e9),
                snapshot["radial_speed_cm_s"],
            )
            if elapsed >= 0.80:
                radial_delta = b["length"](
                    b["sub"](self.trooper.get_actor_location(), self.center)
                ) - b["length"](b["sub"](self.r89_jetpack_start_location, self.center))
                require(snapshot["engaged"] and snapshot["thrusting"], "Normal thrust state dropped")
                require(not snapshot["boosting"], "Normal thrust incorrectly boosted")
                require(snapshot["fuel"] <= self.r89_normal_start["fuel"] - 8.0, "Normal thrust did not drain fuel")
                require(radial_delta >= 100.0, f"Normal thrust produced too little radial lift: {radial_delta}")
                require(self.r89_normal_max_radial_speed >= 250.0, "Normal thrust radial speed too small")
                self.report["tests"]["jetpack_normal_thrust_fuel_and_radial_lift"] = {
                    "start": self.r89_normal_start,
                    "end": snapshot,
                    "radial_delta_cm": radial_delta,
                    "max_radial_speed_cm_s": self.r89_normal_max_radial_speed,
                }
                self.r89_boost_start = snapshot
                self.set_phase("R89_BOOST_THRUST", reset_motion=False)
            self.publish_state()
            return

        if self.phase == "R89_BOOST_THRUST":
            require(elapsed <= 2.5, "R89 boost-thrust timeout")
            self.inject("jump", x=1.0)
            self.inject("sprint", x=1.0)
            snapshot = jetpack_snapshot(self)
            self.r89_boost_max_radial_speed = max(
                getattr(self, "r89_boost_max_radial_speed", -1.0e9),
                snapshot["radial_speed_cm_s"],
            )
            if elapsed >= 0.80:
                require(snapshot["engaged"] and snapshot["thrusting"] and snapshot["boosting"], "Boost state did not engage")
                require(snapshot["fuel"] <= self.r89_boost_start["fuel"] - 14.0, "Boost did not apply extra fuel drain")
                require(
                    self.r89_boost_max_radial_speed >= self.r89_normal_max_radial_speed + 100.0,
                    "Boost did not increase radial speed above normal thrust",
                )
                self.report["tests"]["jetpack_sprint_boost"] = {
                    "start": self.r89_boost_start,
                    "end": snapshot,
                    "normal_max_radial_speed_cm_s": self.r89_normal_max_radial_speed,
                    "boost_max_radial_speed_cm_s": self.r89_boost_max_radial_speed,
                    "serialized_physical_key": "LeftShift",
                    "runtime_action": b["ACTIONS"]["sprint"],
                }
                self.set_phase("R89_EXHAUST_FUEL", reset_motion=False)
            self.publish_state()
            return

        if self.phase == "R89_EXHAUST_FUEL":
            require(elapsed <= 7.0, "R89 fuel-exhaustion timeout")
            self.inject("jump", x=1.0)
            self.inject("sprint", x=1.0)
            snapshot = jetpack_snapshot(self)
            if snapshot["fuel"] <= 0.01:
                require(snapshot["engaged"], "Fuel exhaustion incorrectly disengaged jetpack")
                require(not snapshot["thrusting"] and not snapshot["boosting"], "Exhausted jetpack still thrusts")
                self.r89_exhausted = snapshot
                self.report["tests"]["jetpack_authoritative_fuel_exhaustion"] = snapshot
                self.set_phase("R89_EXHAUSTION_LOCK", reset_motion=False)
            self.publish_state()
            return

        if self.phase == "R89_EXHAUSTION_LOCK":
            require(elapsed <= 2.0, "R89 exhaustion-lock timeout")
            self.inject("jump", x=1.0)
            self.inject("sprint", x=1.0)
            snapshot = jetpack_snapshot(self)
            require(footstep_counts(self) == self.r88_jump_baseline, "Footsteps fired during jetpack flight")
            if elapsed >= 0.75:
                require(snapshot["fuel"] <= 0.01, "Fuel regenerated while Jump remained held")
                require(snapshot["engaged"] and not snapshot["thrusting"] and not snapshot["boosting"], "Exhaustion lock state drift")
                self.report["tests"]["jetpack_exhaustion_locked_until_release"] = {
                    "start": self.r89_exhausted,
                    "held_after_seconds": elapsed,
                    "end": snapshot,
                }
                self.set_phase("R89_RELEASE_REGEN", reset_motion=False)
            self.publish_state()
            return

        if self.phase == "R89_RELEASE_REGEN":
            require(elapsed <= 3.0, "R89 release-regeneration timeout")
            self.inject("jump")
            self.inject("sprint")
            snapshot = jetpack_snapshot(self)
            require(not snapshot["thrusting"] and not snapshot["boosting"], "Released jetpack retained thrust")
            if elapsed >= 1.0:
                require(snapshot["fuel"] >= 15.0, f"Released jetpack did not regenerate fuel: {snapshot}")
                require(snapshot["engaged"], "Release unexpectedly disengaged jetpack")
                self.report["tests"]["jetpack_release_regeneration"] = {
                    "exhausted": self.r89_exhausted,
                    "after_release": snapshot,
                    "release_elapsed_seconds": elapsed,
                }
                self.r89_post_jetpack_grounded_frames = 0
                self.set_phase("R89_WAIT_LAND_AFTER_JETPACK", reset_motion=False)
            self.publish_state()
            return

        if self.phase == "R89_WAIT_LAND_AFTER_JETPACK":
            require(elapsed <= 45.0, "R89 Trooper did not land after jetpack flight")
            self.inject("jump")
            self.inject("sprint")
            require(footstep_counts(self) == self.r88_jump_baseline, "Footsteps fired before post-jetpack landing")
            if not self.movement.is_falling():
                self.r89_post_jetpack_grounded_frames += 1
            else:
                self.r89_post_jetpack_grounded_frames = 0
            if self.r89_post_jetpack_grounded_frames >= 20:
                snapshot = jetpack_snapshot(self)
                require(snapshot["engaged"] and not snapshot["thrusting"] and not snapshot["boosting"], "Post-jetpack landed state drift")
                self.report["tests"]["jetpack_post_flight_landing"] = snapshot
                self.r89_jetpack_runtime_verified = True
                self.set_phase("FIRE_PULSE")
            self.publish_state()
            return

        before = self.phase
        old_tick_r89(self, delta_seconds)
        after = self.phase

        if before == "WAIT_LAND" and after == "FIRE_PULSE" and not getattr(self, "r89_jetpack_runtime_verified", False):
            snapshot = jetpack_snapshot(self)
            require(not snapshot["engaged"] and not snapshot["thrusting"] and not snapshot["boosting"], "Ordinary single Jump engaged jetpack")
            require(snapshot["fuel"] >= 99.0, f"Ordinary Jump changed jetpack fuel: {snapshot}")
            self.report["tests"]["ordinary_single_jump_does_not_engage_jetpack"] = snapshot
            self.set_phase("R89_TAP1_PRESS", reset_motion=False)
        elif before == "ENTER_SETTLE" and after == "ENTER_PULSE":
            snapshot = jetpack_snapshot(self)
            require(snapshot["engaged"] and not snapshot["thrusting"] and not snapshot["boosting"], "Pre-ship jetpack state unavailable for shutdown proof")
            self.r89_pre_ship_jetpack = snapshot
        elif before == "WAIT_SHIP_POSSESSION" and after == "SHIP_ASCEND":
            snapshot = jetpack_snapshot(self)
            require(not snapshot["engaged"] and not snapshot["thrusting"] and not snapshot["boosting"], "Ship possession did not force jetpack state off")
            movement_mode = str(
                self.trooper.get_editor_property("character_movement").get_editor_property("movement_mode")
            )
            require("NONE" in movement_mode.upper(), f"Ship possession did not disable Trooper movement: {movement_mode}")
            self.report["tests"]["jetpack_forced_shutdown_on_ship_possession"] = {
                "before_entry": self.r89_pre_ship_jetpack,
                "after_possession": snapshot,
                "trooper_hidden": True,
                "trooper_collision_disabled": True,
                "movement_mode": movement_mode,
            }
    except Exception as error:
        self.begin_failure(error)


def finalize_r89(self) -> None:
    old_finalize_r89(self)
    required_tests = (
        "ordinary_single_jump_does_not_engage_jetpack",
        "jetpack_double_tap_engagement",
        "jetpack_normal_thrust_fuel_and_radial_lift",
        "jetpack_sprint_boost",
        "jetpack_authoritative_fuel_exhaustion",
        "jetpack_exhaustion_locked_until_release",
        "jetpack_release_regeneration",
        "jetpack_post_flight_landing",
        "jetpack_forced_shutdown_on_ship_possession",
    )
    for key in required_tests:
        require(key in self.report["tests"], f"Missing R89 runtime gate: {key}")
    self.report.update({
        "status": "PASS_R89_CLEAN_JETPACK_PRODUCER_A01_STARSPARROW_REAL_D3D12_PIE",
        "evidence_class": "automation",
        "r89_runtime_gate": {
            "ordinary_single_jump_preserved": True,
            "double_tap_engagement": True,
            "radial_move_falling_lift": True,
            "server_fuel_drain_and_regeneration": True,
            "sprint_boost": True,
            "exhaustion_locked_until_release": True,
            "ship_possession_forced_shutdown": True,
            "hud_or_presentation_accepted": False,
        },
    })
    b["atomic_replace_json"](self.result_path, self.report)


A01PIEValidation.authenticate_inputs = authenticate_r89
A01PIEValidation.tick = tick_r89
A01PIEValidation.finalize_pass = finalize_r89

try:
    b["_REDMMO_R89_JETPACK_VALIDATION"] = A01PIEValidation()
    b["_REDMMO_R89_JETPACK_VALIDATION"].start()
except Exception as bootstrap_error:
    unreal.log_error("REDMMO_R89_JETPACK_BOOTSTRAP_FAIL " + str(bootstrap_error))
    try:
        unreal.SystemLibrary.quit_editor()
    except Exception:
        pass
