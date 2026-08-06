"""R59 provider-off D3D12 no-save starter-ship parking diagnostic."""

from __future__ import annotations

import hashlib
import json
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

import unreal


PROJECT = Path(r"D:\RedMMOTitanWindowsData\Projects\RedMMO\RedMMO.uproject")
HOME_FILE = Path(r"D:\RedMMOTitanWindowsData\Projects\RedMMO\Content\RedMMO\Maps\RedMMO_PPG_HomeWorld.umap")
BINARY = Path(r"D:\RedMMOTitanWindowsData\Projects\RedMMO\Binaries\Win64\UnrealEditor-RedMMO.dll")
SOURCE = Path(r"D:\RedMMOTitanWindowsData\Projects\RedMMO\Source\RedMMO\Private\RedShip.cpp")
GAMEMODE_SOURCE = Path(r"D:\RedMMOTitanWindowsData\Projects\RedMMO\Source\RedMMO\Private\RedPPGGameplayGameMode.cpp")
GAMEMODE_HEADER = Path(r"D:\RedMMOTitanWindowsData\Projects\RedMMO\Source\RedMMO\Public\RedPPGGameplayGameMode.h")
SURFACE_SOURCE = Path(r"D:\RedMMOTitanWindowsData\Projects\RedMMO\Source\RedMMO\Private\RedPPGSurfaceAuthority.cpp")
DIAG = Path(r"D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_StarterShipParking_R59_20260805T2002Z\CorrectedRunAttempt7")
RESULT = DIAG / "result.json"
SHIP_CLASS = "/Game/RedMMO/Gameplay/Trooper/A01/Ship/BP_RedModularStarSparrow_Trooper_A01.BP_RedModularStarSparrow_Trooper_A01_C"
EXPECTED = {
    PROJECT: "3BF3D8D1D1C7F892A2CD4873F7C0390EC1AF3CA8F77E60549169563D18DBF86F",
    HOME_FILE: "0331E54155DF929C82E56084BEAD569865052A25D20A6082BA9C3E07E88F88F3",
    BINARY: "728992E6FEE98759114E26974337D2AC94B575CD6EC46E39FDECE5F8EE1AC71C",
    SOURCE: "B3257E11A00D81F324F5D123EDD6CAF9B5F64DB2891828360D4C8817230BBED2",
    GAMEMODE_SOURCE: "B0ED7072BEC4731A331C6F45EFB1B682EAD96E91E45D3F48CA6798283AEA4169",
    GAMEMODE_HEADER: "28CDED8E0E486479D622C78324F0E64DED6C7206DD8D8874B6F4C043D73B1C6E",
    SURFACE_SOURCE: "823094E2C229EC289E0905FA18765C7BE6EF253100C159712D44E0787F6A7487",
}


def now():
    return datetime.now(timezone.utc).isoformat()


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


class R59:
    def __init__(self):
        self.editor = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
        self.level = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
        self.handle = None
        self.phase = "PREPARE"
        self.phase_started = time.monotonic()
        self.world = None
        self.spawner = None
        self.report = {
            "schema": "redmmo.starter-ship-parking.r59.diagnostic.v1",
            "status": "RUNNING",
            "started_utc": now(),
            "evidence_class": "d3d12_runtime_diagnostic",
            "persistent_save": False,
            "mutation_scope": "none; diagnostic instrumentation only",
        }

    def set_phase(self, value):
        self.phase = value
        self.phase_started = time.monotonic()
        unreal.log("REDMMO_R59_PHASE " + value)

    def prepare(self):
        DIAG.mkdir(parents=True, exist_ok=True)
        require(not RESULT.exists(), "R59 result no-clobber failed")
        active = Path(unreal.Paths.convert_relative_path_to_full(unreal.Paths.get_project_file_path())).resolve(strict=True)
        require(active == PROJECT.resolve(strict=True), "wrong project")
        for path, expected in EXPECTED.items():
            require(path.is_file() and sha256(path) == expected, "input drift: " + str(path))
        require(not self.level.is_in_play_in_editor(), "PIE already active")
        command = str(unreal.SystemLibrary.get_command_line()).lower()
        require("-d3d12" in command and "-renderoffscreen" in command and "-nullrhi" not in command,
                "renderer gate failed")
        self.level.editor_request_begin_play()
        self.set_phase("WAIT_PIE")

    def bind_pie(self):
        world = self.editor.get_game_world()
        if world is None or not self.level.is_in_play_in_editor():
            return False
        actors = list(unreal.GameplayStatics.get_all_actors_of_class(world, unreal.Actor))
        spawners = [actor for actor in actors if actor.get_class().get_name() == "PlanetSpawnerBP_C"]
        if len(spawners) != 1:
            return False
        self.world = world
        self.spawner = spawners[0]
        self.set_phase("WAIT_GENERATION")
        return True

    def generation_ready(self):
        status = self.spawner.get_planet_generation_status()
        record = {
            "phase": str(status.get_editor_property("phase")),
            "progress": float(status.get_editor_property("progress")),
            "is_generating": bool(status.get_editor_property("is_generating")),
        }
        self.report["generation"] = record
        return "COMPLETE" in record["phase"].upper() and record["progress"] >= 0.999 and not record["is_generating"]

    def inspect_ship(self):
        actors = list(unreal.GameplayStatics.get_all_actors_of_class(self.world, unreal.Actor))
        foliage = []
        for actor in actors:
            if actor.get_class().get_name() != "FoliageSpawner":
                continue
            for component in actor.get_components_by_class(unreal.StaticMeshComponent):
                if component.get_name() != "InstancedStaticMeshComponent_162":
                    continue
                mesh = component.get_editor_property("static_mesh")
                foliage.append({
                    "actor": actor.get_path_name(),
                    "component": component.get_path_name(),
                    "mesh": mesh.get_path_name() if mesh else None,
                })
        self.report["foreign_foliage_component_162"] = foliage
        ships = [actor for actor in actors if actor.get_class().get_path_name() == SHIP_CLASS]
        records = []
        for ship in ships:
            records.append({
                "path": ship.get_path_name(),
                "validated_owned_surface": bool(ship.has_validated_owned_surface_placement()),
                "validated_gap_cm": float(ship.get_validated_owned_surface_gap_cm()),
                "location_cm": [ship.get_actor_location().x, ship.get_actor_location().y, ship.get_actor_location().z],
            })
        self.report["ships"] = records
        self.report["ship_count"] = len(records)
        require(len(records) == 1, "expected exactly one starter ship after deterministic parking search")
        require(records[0]["validated_owned_surface"], "starter ship lacks validated owned-surface placement")
        require(abs(records[0]["validated_gap_cm"] - 15.0) <= 0.01, "starter ship surface gap drift")
        self.level.editor_request_end_play()
        self.set_phase("WAIT_STOP")

    def finish(self):
        for path, expected in EXPECTED.items():
            require(sha256(path) == expected, "post-runtime drift: " + str(path))
        self.report.update({
            "status": "PASS_R59_STARTER_SHIP_PARKED_ON_AUTHENTIC_PPG_SURFACE",
            "completed_utc": now(),
            "home_map_sha256_after": sha256(HOME_FILE),
            "save_called": False,
            "claim_limit": "Starter-ship parking only; no ship entry, flight, replication, standalone, package, or visual-acceptance claim.",
        })
        RESULT.write_text(json.dumps(self.report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        unreal.log("REDMMO_R59_DIAGNOSTIC_COMPLETE")
        self.schedule_quit(2.0)

    def fail(self, error):
        failed_phase = self.phase
        self.phase = "FAILED"
        self.report.update({
            "status": "FAIL",
            "failed_phase": failed_phase,
            "completed_utc": now(),
            "error": str(error),
            "traceback": traceback.format_exc(),
        })
        if self.level.is_in_play_in_editor():
            self.level.editor_request_end_play()
        DIAG.mkdir(parents=True, exist_ok=True)
        if not RESULT.exists():
            RESULT.write_text(json.dumps(self.report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        unreal.log_error("REDMMO_R59_FAIL " + str(error))
        self.schedule_quit(2.0)

    def schedule_quit(self, delay):
        started = time.monotonic()
        old = self.handle
        if old is not None:
            try:
                unreal.unregister_slate_post_tick_callback(old)
            except Exception:
                pass

        def tick(_delta):
            if time.monotonic() - started < delay:
                return
            try:
                unreal.unregister_slate_post_tick_callback(self.handle)
            except Exception:
                pass
            unreal.SystemLibrary.quit_editor()

        self.handle = unreal.register_slate_post_tick_callback(tick)

    def tick(self, _delta):
        try:
            elapsed = time.monotonic() - self.phase_started
            if self.phase == "PREPARE":
                self.prepare()
            elif self.phase == "WAIT_PIE":
                require(elapsed <= 30.0, "PIE startup timeout")
                self.bind_pie()
            elif self.phase == "WAIT_GENERATION":
                require(elapsed <= 300.0, "generation timeout")
                if self.generation_ready():
                    self.set_phase("SETTLE_PARKING")
            elif self.phase == "SETTLE_PARKING":
                require(elapsed <= 30.0, "starter-ship settle timeout")
                if elapsed >= 12.0:
                    self.inspect_ship()
            elif self.phase == "WAIT_STOP":
                require(elapsed <= 25.0, "PIE stop timeout")
                if not self.level.is_in_play_in_editor():
                    self.finish()
        except Exception as error:
            self.fail(error)

    def start(self):
        self.handle = unreal.register_slate_post_tick_callback(self.tick)


try:
    _R59 = R59()
    _R59.start()
except Exception as bootstrap_error:
    DIAG.mkdir(parents=True, exist_ok=True)
    RESULT.write_text(json.dumps({
        "schema": "redmmo.starter-ship-parking.r59.diagnostic.v1",
        "status": "FAIL",
        "completed_utc": now(),
        "error": str(bootstrap_error),
        "traceback": traceback.format_exc(),
    }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    unreal.SystemLibrary.quit_editor()
