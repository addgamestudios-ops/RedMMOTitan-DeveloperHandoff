"""Create and bind the project-owned R18 planet-aware night presenter.

This guarded editor transaction creates one deterministic analytic star-sky
material and one ARedPlanetNightPresenter map actor. It preserves PPG, terrain,
the existing atmosphere sun/SkyAtmosphere/SkyLight, water, seed and gameplay.
"""

from __future__ import annotations

import hashlib
import json
import runpy
import socket
from pathlib import Path

import unreal


PROJECT = "D:/RedMMOTitanWindowsData/Projects/RedMMO/RedMMO.uproject"
MAP = "/Game/RedMMO/Maps/RedMMO_PPG_HomeWorld"
MAP_FILE = Path("D:/RedMMOTitanWindowsData/Projects/RedMMO/Content/RedMMO/Maps/RedMMO_PPG_HomeWorld.umap")
EXPECTED_MAP_SHA = "83C78D0ACB599F01E8D3834FB62D58D6B6AA75466F6549F03BFEC4DF908E3336"
MATERIAL_SCRIPT = Path("D:/RedMMOTitan/Build/Automation/create_red_analytic_star_dome_material.py")
MATERIAL = "/Game/RedMMO/Environment/M_RedAnalyticStarDome"
MATERIAL_FILE = Path("D:/RedMMOTitanWindowsData/Projects/RedMMO/Content/RedMMO/Environment/M_RedAnalyticStarDome.uasset")
ACTOR_LABEL = "RED_NightPresenter_R18"
RESULT = Path("D:/RedMMOTitanWindowsData/Diagnostics/RedMMO_NightPresenter_R18_20260805T0940Z/build_result.json")
PROTECTED = {
    Path("D:/RedMMOTitan/Content/RedMMO/Maps/RedPlanetGen_50km_Test.umap"):
        "DA5987012EEB8F550254F5FCF0F47F42B8F5E03428CF4881C83D8687537F6E7D",
    Path("D:/RedMMOTitan/Content/RedMMO/Maps/RedPlanetGen_50km_FusedPrototype.umap"):
        "4C84D7752C87854C70987ED9988C64C124C577FBE1DE3DEF3CC826F81B0B6284",
}
PROVIDER_PORTS = (11111, 5353, 8000, 8765)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def asset_path(value) -> str:
    if value is None:
        return ""
    path = value.get_path_name()
    return path.split(".", 1)[0]


def provider_gate() -> list[dict]:
    records = []
    for port in PROVIDER_PORTS:
        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        probe.settimeout(0.2)
        try:
            code = probe.connect_ex(("127.0.0.1", port))
        finally:
            probe.close()
        records.append({"port": port, "closed": code != 0, "connect_ex": code})
    require(all(record["closed"] for record in records), "Provider listener is active")
    return records


def dirty_packages() -> dict[str, list[str]]:
    content = sorted(asset_path(value) for value in
                     unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages())
    maps = sorted(asset_path(value) for value in
                  unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages())
    return {"content": [value for value in content if value], "maps": [value for value in maps if value]}


def component(actor, component_class):
    values = list(actor.get_components_by_class(component_class))
    require(len(values) == 1, f"{actor.get_actor_label()} has {len(values)} {component_class} components")
    return values[0]


def main() -> None:
    require(not RESULT.exists(), "R18 result already exists")
    actual_project = unreal.Paths.convert_relative_path_to_full(unreal.Paths.get_project_file_path())
    require(unreal.Paths.is_same_path(actual_project, PROJECT), "Wrong project: " + actual_project)
    level = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    require(not level.is_in_play_in_editor(), "PIE is active")
    require(not dirty_packages()["content"] and not dirty_packages()["maps"], "Dirty packages before R18")
    require(sha256(MAP_FILE) == EXPECTED_MAP_SHA, "Home map preimage drift")
    providers = provider_gate()
    for path, expected in PROTECTED.items():
        require(sha256(path) == expected, "Protected hash drift: " + str(path))

    require(unreal.EditorLevelLibrary.load_level(MAP), "Unable to load home map")
    world = unreal.EditorLevelLibrary.get_editor_world()
    current = world.get_path_name().split(":", 1)[0].split(".", 1)[0]
    require(current == MAP, "Wrong map after load: " + current)
    actors_before = list(unreal.EditorLevelLibrary.get_all_level_actors())
    require(not [actor for actor in actors_before if actor.get_actor_label() == ACTOR_LABEL],
            "R18 presenter label already exists")

    suns = []
    for actor in actors_before:
        if isinstance(actor, unreal.DirectionalLight):
            light = component(actor, unreal.DirectionalLightComponent)
            if bool(light.get_editor_property("atmosphere_sun_light")) and int(
                    light.get_editor_property("atmosphere_sun_light_index")) == 0:
                suns.append(actor)
    require(len(suns) == 1, f"Expected one primary atmosphere sun, found {len(suns)}")
    require(len([actor for actor in actors_before if isinstance(actor, unreal.SkyAtmosphere)]) == 1,
            "Expected one existing SkyAtmosphere")
    require(len([actor for actor in actors_before if isinstance(actor, unreal.SkyLight)]) == 1,
            "Expected one existing SkyLight")

    require(MATERIAL_SCRIPT.is_file(), "Reviewed analytic material builder is missing")
    runpy.run_path(str(MATERIAL_SCRIPT), run_name="__main__")
    material = unreal.EditorAssetLibrary.load_asset(MATERIAL)
    require(isinstance(material, unreal.Material), "Analytic star material did not load")
    require(bool(material.get_editor_property("is_sky")), "Analytic material is not a sky material")
    require(bool(material.get_editor_property("two_sided")), "Analytic material is not two-sided")
    require(material.get_editor_property("shading_model") == unreal.MaterialShadingModel.MSM_UNLIT,
            "Analytic material is not unlit")

    actor_subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    presenter = actor_subsystem.spawn_actor_from_class(
        unreal.RedPlanetNightPresenter, unreal.Vector(0.0, 0.0, 0.0), unreal.Rotator())
    require(presenter is not None, "Unable to spawn R18 presenter")
    presenter.set_actor_label(ACTOR_LABEL)
    presenter.set_editor_property("star_material", material)
    presenter.set_editor_property("star_emission", 64.0)
    presenter.set_editor_property("night_fill_lux_per_weight", 8.0)

    expected_dirty = dirty_packages()
    require(expected_dirty["maps"] == [MAP], "Unexpected dirty maps before save: " + str(expected_dirty))
    require(set(expected_dirty["content"]).issubset({MATERIAL}),
            "Unexpected dirty content before save: " + str(expected_dirty))
    require(level.save_current_level(), "Unable to save R18 home map")
    if MATERIAL in dirty_packages()["content"]:
        require(unreal.EditorAssetLibrary.save_loaded_asset(material, False), "Unable to save analytic material")
    require(not dirty_packages()["content"] and not dirty_packages()["maps"], "Dirty packages after R18 save")
    require(MATERIAL_FILE.is_file(), "Analytic material package missing after save")

    actors_after = list(unreal.EditorLevelLibrary.get_all_level_actors())
    presenters = [actor for actor in actors_after if actor.get_actor_label() == ACTOR_LABEL]
    require(len(presenters) == 1 and isinstance(presenters[0], unreal.RedPlanetNightPresenter),
            "R18 presenter readback failed")
    presenter = presenters[0]
    require(asset_path(presenter.get_editor_property("star_material")) == MATERIAL,
            "R18 star material readback mismatch")

    output = {
        "status": "PASS_R18_SERIALIZED_PENDING_FRESH_RELOAD_MAPCHECK_REAL_D3D12",
        "project": PROJECT,
        "map": MAP,
        "map_sha256_before": EXPECTED_MAP_SHA,
        "map_sha256_after": sha256(MAP_FILE),
        "material": MATERIAL,
        "material_file": MATERIAL_FILE.as_posix(),
        "material_sha256": sha256(MATERIAL_FILE),
        "presenter_class": presenter.get_class().get_path_name(),
        "presenter_label": presenter.get_actor_label(),
        "actor_count_before": len(actors_before),
        "actor_count_after": len(actors_after),
        "primary_atmosphere_sun_label": suns[0].get_actor_label(),
        "providers": providers,
        "dirty_after": dirty_packages(),
        "protected_hashes": {str(path): sha256(path) for path in PROTECTED},
        "claim_limit": "Serialized project-owned presenter only; fresh reload, MapCheck, runtime weights and D3D12 pixels remain pending.",
    }
    RESULT.parent.mkdir(parents=True, exist_ok=True)
    with RESULT.open("x", encoding="utf-8") as stream:
        json.dump(output, stream, indent=2)
        stream.write("\n")
    unreal.log_warning("REDMMO_NIGHT_PRESENTER_R18_BUILD_PASS " + json.dumps(output, sort_keys=True))


try:
    main()
except Exception as error:
    unreal.log_error("REDMMO_NIGHT_PRESENTER_R18_BUILD_FAIL " + repr(error))
    raise
