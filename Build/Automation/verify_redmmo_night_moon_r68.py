"""Fresh D3D12 verification for the project-owned R68 visual moon.

Reuses the lifecycle-stable R67 player-scale PPG harness, keeps the exact
seeded grass/no-palms/surface bindings, aims the no-save PIE camera at the
night presenter's deterministic anti-solar moon, and captures the existing
viewport without resizing it.
"""

from pathlib import Path
import time
import unreal


BASE_PATH = Path(r"D:\RedMMOTitan\Build\Automation\verify_redmmo_profile_v1_painted_leaves_existing_viewport_r67.py")
HEADER = Path(r"D:\RedMMOTitanWindowsData\Projects\RedMMO\Source\RedMMO\Public\RedPlanetNightPresenter.h")
CPP = Path(r"D:\RedMMOTitanWindowsData\Projects\RedMMO\Source\RedMMO\Private\RedPlanetNightPresenter.cpp")
BINARY = Path(r"D:\RedMMOTitanWindowsData\Projects\RedMMO\Binaries\Win64\UnrealEditor-RedMMO.dll")
MOON_FILE = Path(r"D:\RedMMOTitanWindowsData\Projects\RedMMO\Content\RedMMO\Environment\M_RedAnalyticMoon_R68.uasset")
MOON_ASSET = "/Game/RedMMO/Environment/M_RedAnalyticMoon_R68"
DIAG = Path(r"D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_NightMoon_R68_20260805T2213Z\Capture2")
RESULT = DIAG / "result.json"
CAPTURE = DIAG / "R68_surface_night_moon_no_palms.png"


source = BASE_PATH.read_text(encoding="utf-8")
bootstrap = "\ntry:\n    _R67 = R67()"
if bootstrap not in source:
    raise RuntimeError("R67 bootstrap boundary missing")
scope = {"__name__": "redmmo_r67_base_for_r68", "__file__": str(BASE_PATH)}
exec(compile(source.split(bootstrap, 1)[0], str(BASE_PATH), "exec"), scope)

CHECKS = dict(scope["CHECKS"])
CHECKS[HEADER] = "31DF4341B03880EFC858E264538930F644E53878327727BF11F8C6EC6E2CA847"
CHECKS[CPP] = "6647CF79C65220C0A95A62AB6D331163C1C11422DF11E78D06407DF31F4814D0"
CHECKS[BINARY] = "E7D7AAAD61EC348F044787F295658DFABBE177EA782F13F1FCF4FC2B908A8557"
CHECKS[MOON_FILE] = "578D841AB974F9DAE4B6EAB5A474901E2202C601A4350D1BB4E8C7A68893F4C3"
scope["CHECKS"] = CHECKS
scope["DIAG"] = DIAG
scope["RESULT"] = RESULT
scope["CAPTURE"] = CAPTURE
scope["scope"]["CHECKS"] = CHECKS
scope["scope"]["DIAG"] = DIAG
scope["scope"]["RESULT"] = RESULT
scope["scope"]["CAPTURE"] = CAPTURE
scope["scope"]["namespace"]["CHECKS"] = CHECKS
scope["scope"]["namespace"]["DIAG"] = DIAG
scope["scope"]["namespace"]["RESULT"] = RESULT
scope["scope"]["namespace"]["CAPTURE"] = CAPTURE

BaseR67 = scope["R67"]
require = scope["require"]
now = scope["now"]
sha256 = scope["sha256"]
atomic_json = scope["atomic_json"]
asset_path = scope["asset_path"]
dirty_packages = scope["dirty_packages"]
provider_gate = scope["provider_gate"]


class R68(BaseR67):
    def __init__(self):
        super().__init__()
        self.presenter = None
        self.moon = None
        self.report.update({
            "schema": "redmmo.surface-night-moon.verify.r68.v1",
            "evidence_class": "real_gpu_visual",
            "slice": "R68 project-owned anti-solar visual moon with retained R67/R66 PPG presentation",
            "moon_asset": MOON_ASSET,
        })

    def bind_pie(self):
        if not super().bind_pie():
            return False
        presenters = [
            actor for actor in unreal.GameplayStatics.get_all_actors_of_class(self.world, unreal.Actor)
            if actor.get_class().get_name() == "RedPlanetNightPresenter"
        ]
        require(len(presenters) == 1, "expected one RedPlanetNightPresenter")
        self.presenter = presenters[0]
        moons = [
            component for component in self.presenter.get_components_by_class(unreal.StaticMeshComponent)
            if component.get_name() == "MoonDisc"
        ]
        require(len(moons) == 1, "expected one MoonDisc component")
        self.moon = moons[0]
        require(asset_path(self.presenter.get_editor_property("moon_material")) == MOON_ASSET,
                "R68 moon material binding drift")
        self.report["moon_runtime"] = {
            "material": MOON_ASSET,
            "distance_cm": float(self.presenter.get_editor_property("moon_distance_cm")),
            "angular_radius_degrees": float(self.presenter.get_editor_property("moon_angular_radius_degrees")),
            "emission": float(self.presenter.get_editor_property("moon_emission")),
            "collision": str(self.moon.get_collision_enabled()),
        }
        return True

    def request_capture(self):
        require(self.presenter is not None and self.moon is not None, "moon runtime not bound")
        weight = float(self.presenter.get_editor_property("last_moon_visibility_weight"))
        require(weight >= 0.95, "saved player start is not on the full-night hemisphere")
        camera = unreal.GameplayStatics.get_player_camera_manager(self.world, 0)
        controller = unreal.GameplayStatics.get_player_controller(self.world, 0)
        require(camera is not None and controller is not None, "camera/controller missing")
        camera_location = camera.get_actor_location()
        moon_location = self.moon.get_world_location()
        require((moon_location - camera_location).length() > 1000000.0, "moon location invalid")
        look = unreal.MathLibrary.find_look_at_rotation(camera_location, moon_location)
        controller.set_control_rotation(look)
        self.presenter.set_actor_rotation(look, False)
        controller.set_view_target_with_blend(self.presenter, 0.0)
        self.report["moon_aim"] = {
            "visibility_weight": weight,
            "camera_location": str(camera_location),
            "moon_location": str(moon_location),
            "requested_control_rotation": str(look),
        }
        self.set_phase("SETTLE_MOON_AIM")

    def tick(self, delta):
        if self.phase != "SETTLE_MOON_AIM":
            super().tick(delta)
            return
        try:
            elapsed = time.monotonic() - self.phase_started
            require(elapsed <= 10.0, "moon aim settle timeout")
            self.sample()
            if elapsed >= 2.0:
                camera = unreal.GameplayStatics.get_player_camera_manager(self.world, 0)
                self.report["moon_aim"]["settled_camera_rotation"] = str(camera.get_actor_rotation())
                super().request_capture()
        except Exception as error:
            self.fail(error)

    def finish(self):
        require(not self.level.is_in_play_in_editor(), "PIE did not stop")
        require(dirty_packages() == {"content": [], "maps": []}, "PIE dirtied packages")
        for path, expected in CHECKS.items():
            require(sha256(path) == expected, "post-PIE drift: " + str(path))
        require(CAPTURE.is_file() and CAPTURE.stat().st_size > 0, "capture missing")
        stable = (
            self.report["lifecycle_analysis"]["readiness_stable"]
            and self.report["lifecycle_analysis"]["palm_zero_throughout"]
        )
        self.report.update({
            "status": "PASS_R68_MOON_RUNTIME_PENDING_PIXEL_REVIEW" if stable else "FAIL_R68_RUNTIME_DRIFT",
            "completed_utc": now(),
            "capture": {"path": str(CAPTURE), "bytes": CAPTURE.stat().st_size, "sha256": sha256(CAPTURE)},
            "dirty_packages_after": dirty_packages(),
            "provider_gate_after": provider_gate(),
            "claim_limit": "Fresh D3D12 visual-moon, MapCheck, no-palms and seeded-grass evidence only; no orbit, gravity, gameplay, standalone or final-art claim.",
        })
        atomic_json(RESULT, self.report)
        unreal.log("REDMMO_R68_VERIFY_" + ("PASS" if stable else "FAIL"))
        self.phase = "DONE"
        self.schedule_quit(3.0)


try:
    _R68 = R68()
    _R68.start()
    unreal.log("REDMMO_R68_VERIFY_STARTED")
except Exception as bootstrap_error:
    DIAG.mkdir(parents=True, exist_ok=True)
    atomic_json(RESULT, {
        "schema": "redmmo.surface-night-moon.verify.r68.v1",
        "status": "FAIL",
        "completed_utc": now(),
        "error": str(bootstrap_error),
    })
    unreal.SystemLibrary.quit_editor()
