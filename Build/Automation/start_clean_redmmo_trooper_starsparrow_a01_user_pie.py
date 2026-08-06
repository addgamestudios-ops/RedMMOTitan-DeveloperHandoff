"""Open the authenticated clean RedMMO A01 home flow for human hands-on PIE.

This script performs no save or mutation. It authenticates the exact project,
home map, protected content, provider-off state and expected A01 runtime classes,
starts PIE, waits for PPG generation plus the real StarSparrow, publishes a
no-clobber readiness report, then unregisters itself while leaving PIE open.
"""

from __future__ import annotations

import hashlib
import json
import os
import socket
import time
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import unreal


PROJECT_ROOT = Path(r"D:\RedMMOTitanWindowsData\Projects\RedMMO")
PROJECT_FILE = PROJECT_ROOT / "RedMMO.uproject"
PROJECT_SHA256 = "54E664A24FA5E9129C022740EE624F84389F1825AA9A4AE07D5E99DD783F382E"
HOME_MAP = "/Game/RedMMO/Maps/RedMMO_PPG_HomeWorld"
HOME_FILE = PROJECT_ROOT / r"Content\RedMMO\Maps\RedMMO_PPG_HomeWorld.umap"
HOME_SHA256 = "1310D92641AC25DAEA4DF289A8B2C16A46F3F0D4AECB7FB9F4616FE5CEAD5209"
ROOT = "/Game/RedMMO/Gameplay/Trooper/A01"
GAME_MODE_CLASS = ROOT + "/Player/GM_RedTrooperPPG_A01.GM_RedTrooperPPG_A01_C"
PLAYER_CLASS = ROOT + "/Player/BP_RedTrooperPlayer_A01.BP_RedTrooperPlayer_A01_C"
SHIP_CLASS = ROOT + "/Ship/BP_RedModularStarSparrow_Trooper_A01.BP_RedModularStarSparrow_Trooper_A01_C"
REPORT_ENV = "REDMMO_A01_USER_PIE_REPORT"
DIAGNOSTICS_ROOT = Path(r"D:\RedMMOTitanWindowsData\Diagnostics")
PROVIDER_PORTS = (5353, 8000, 8765)
PROTECTED_FILES = {
    Path(r"D:\RedMMOTitan\Content\RedMMO\Maps\RedPlanetGen.umap"):
        "1DF9E6ED913A267875F1EF452F6ED51DAF337DBBAAE4C6EC3379EA6299346724",
    Path(r"D:\RedMMOTitan\Content\RedMMO\Environment\DA_RED_Planet50Km_FusedHeightfield.uasset"):
        "412E26B75DAD95CE0EF4FA63BFF21CCA0EDB755B5D08BA1A4CFA3EEFEC06E562",
    Path(r"D:\RedMMOTitan\Content\RedMMO\Maps\RedPlanetGen_50km_Test.umap"):
        "DA5987012EEB8F550254F5FCF0F47F42B8F5E03428CF4881C83D8687537F6E7D",
    Path(r"D:\RedMMOTitan\Content\RedMMO\Maps\RedPlanetGen_50km_FusedPrototype.umap"):
        "4C84D7752C87854C70987ED9988C64C124C577FBE1DE3DEF3CC826F81B0B6284",
    Path(r"D:\RedMMOTitan\Content\RedMMO\Maps\Tests\RedPlanetGen_50km_FusedPrototype_Night_T03.umap"):
        "211429783F757F3CD8DE4A37B1E37B4A117125BF26EBFCBACF97CCFA9EFBE8D7",
    Path(r"D:\RedMMOTitanWindowsData\Rollback\BeforeCoastDatum_20260714\RedPlanetGen_50km_FusedPrototype.umap"):
        "A9C42C0D1B0429DD1018F00F0D2AB8A18F66C07291611964EFF5F9710F3B0C6A",
}


class ReadinessError(RuntimeError):
    pass


def require(condition: Any, message: str) -> None:
    if not condition:
        raise ReadinessError(message)


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def class_path(value: Any) -> str:
    return value.get_class().get_path_name() if value is not None else ""


def provider_ports() -> dict[str, bool]:
    state: dict[str, bool] = {}
    for port in PROVIDER_PORTS:
        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        probe.settimeout(0.1)
        try:
            state[str(port)] = probe.connect_ex(("127.0.0.1", port)) == 0
        finally:
            probe.close()
    return state


def dirty_packages() -> dict[str, list[str]]:
    return {
        "content": list(unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages()),
        "maps": list(unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()),
    }


def report_path() -> Path:
    raw = os.environ.get(REPORT_ENV, "")
    require(bool(raw), f"{REPORT_ENV} is required")
    root = DIAGNOSTICS_ROOT.resolve(strict=True)
    path = Path(raw).resolve(strict=False)
    require(os.path.commonpath([str(path), str(root)]) == str(root), "Unsafe report path")
    require(path.name == "ready.json", "Report must be named ready.json")
    require(not path.exists() and not path.parent.exists(), "Readiness report no-clobber failed")
    path.parent.mkdir(parents=True, exist_ok=False)
    return path


def write_report(path: Path, value: dict[str, Any]) -> None:
    temporary = path.parent / ("." + path.name + "." + uuid.uuid4().hex + ".tmp")
    with temporary.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, indent=2, sort_keys=True, default=str)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


class HandsOnSession:
    def __init__(self) -> None:
        self.report_path = report_path()
        self.report: dict[str, Any] = {
            "schema": "redmmo.trooper_starsparrow.a01.hands_on_ready.v1",
            "status": "STARTING",
            "started_utc": now(),
            "persistent_writes": False,
        }
        self.editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
        self.level = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
        self.callback = None
        self.started = time.monotonic()
        self.ready_frames = 0

    def stop_callback(self) -> None:
        if self.callback is not None:
            unreal.unregister_slate_post_tick_callback(self.callback)
            self.callback = None

    def prepare(self) -> None:
        require(PROJECT_FILE.is_file() and sha256(PROJECT_FILE) == PROJECT_SHA256, "Project descriptor drift")
        require(HOME_FILE.is_file() and sha256(HOME_FILE) == HOME_SHA256, "Home map drift")
        for path, expected in PROTECTED_FILES.items():
            require(path.is_file() and sha256(path) == expected, "Protected drift: " + str(path))
        ports = provider_ports()
        require(not any(ports.values()), "Provider listener active: " + str(ports))
        require(not dirty_packages()["content"] and not dirty_packages()["maps"], "Editor started dirty")
        require(not self.level.is_in_play_in_editor(), "PIE already active")
        world = self.editor.get_editor_world()
        current = world.get_path_name().split(":", 1)[0].split(".", 1)[0] if world else ""
        if current != HOME_MAP:
            world = unreal.EditorLoadingAndSavingUtils.load_map(HOME_MAP)
        require(world is not None, "Home map load failed")
        require(not dirty_packages()["content"] and not dirty_packages()["maps"], "Home map load dirtied packages")
        world_settings = world.get_world_settings()
        require(world_settings is not None, "WorldSettings unavailable")
        override = world_settings.get_editor_property("default_game_mode")
        require(override is not None and override.get_path_name() == GAME_MODE_CLASS, "A01 GameMode binding drift")
        self.report.update({
            "project": str(PROJECT_FILE),
            "map": HOME_MAP,
            "home_map_sha256": HOME_SHA256,
            "game_mode": GAME_MODE_CLASS,
            "provider_ports_closed_before": ports,
            "preceding_fresh_mapcheck": {
                "result": "D:/RedMMOTitanWindowsData/Diagnostics/RedMMO_TrooperStarSparrow_A01_PIE_20260803T063155Z/result.json",
                "sha256": "5D11C4DB723833D20C0467FA0C96F239AB06F9C7A13B7C94416FB92821E563A3",
                "errors": 0,
                "warnings": 0,
            },
        })
        self.level.editor_request_begin_play()
        self.report["status"] = "WAITING_FOR_PIE_AND_PPG"

    def tick(self, _delta: float) -> None:
        try:
            require(time.monotonic() - self.started <= 240.0, "Hands-on PIE readiness timeout")
            world = self.editor.get_game_world()
            if world is None or not self.level.is_in_play_in_editor():
                return
            controller = unreal.GameplayStatics.get_player_controller(world, 0)
            pawn = unreal.GameplayStatics.get_player_pawn(world, 0)
            if controller is None or pawn is None or class_path(pawn) != PLAYER_CLASS:
                return
            actors = list(unreal.GameplayStatics.get_all_actors_of_class(world, unreal.Actor))
            spawners = [a for a in actors if a.get_class().get_name() == "PlanetSpawnerBP_C"]
            ships = [a for a in actors if class_path(a) == SHIP_CLASS]
            game_mode = unreal.GameplayStatics.get_game_mode(world)
            if len(spawners) != 1 or len(ships) != 1 or class_path(game_mode) != GAME_MODE_CLASS:
                return
            status_method = getattr(spawners[0], "get_planet_generation_status", None)
            if not callable(status_method):
                return
            status = status_method()
            phase = str(status.get_editor_property("phase"))
            progress = float(status.get_editor_property("progress"))
            generating = bool(status.get_editor_property("is_generating"))
            collisions = bool(spawners[0].get_editor_property("generate_collisions"))
            if "COMPLETE" not in phase.upper() or progress < 0.999 or generating or not collisions:
                self.ready_frames = 0
                return
            self.ready_frames += 1
            if self.ready_frames < 60:
                return
            require(not dirty_packages()["content"] and not dirty_packages()["maps"], "PIE dirtied packages")
            ports = provider_ports()
            require(not any(ports.values()), "Provider listener appeared during PIE")
            self.report.update({
                "status": "PASS_VISIBLE_HANDS_ON_PIE_READY_PENDING_USER_REVIEW",
                "completed_utc": now(),
                "pie_left_open_for_user": True,
                "controller": controller.get_path_name(),
                "initial_pawn": pawn.get_path_name(),
                "initial_pawn_class": PLAYER_CLASS,
                "ship": ships[0].get_path_name(),
                "ship_class": SHIP_CLASS,
                "generation": {
                    "phase": phase,
                    "progress": progress,
                    "collisions_enabled": collisions,
                },
                "provider_ports_closed_ready": ports,
                "dirty_packages_ready": dirty_packages(),
                "claim_limit": "Ready for user physical-input and visual review only; no acceptance is inferred by this launcher.",
            })
            write_report(self.report_path, self.report)
            unreal.log("REDMMO_A01_HANDS_ON_PIE_READY")
            self.stop_callback()
        except Exception as error:
            self.report.update({
                "status": "FAIL",
                "completed_utc": now(),
                "error": str(error),
                "traceback": traceback.format_exc(),
            })
            if not self.report_path.exists():
                write_report(self.report_path, self.report)
            unreal.log_error("REDMMO_A01_HANDS_ON_PIE_FAIL " + str(error))
            if self.level.is_in_play_in_editor():
                self.level.editor_request_end_play()
            self.stop_callback()

    def start(self) -> None:
        self.prepare()
        self.callback = unreal.register_slate_post_tick_callback(self.tick)


try:
    _SESSION = HandsOnSession()
    _SESSION.start()
except Exception as bootstrap_error:
    unreal.log_error("REDMMO_A01_HANDS_ON_PIE_BOOTSTRAP_FAIL " + str(bootstrap_error))

