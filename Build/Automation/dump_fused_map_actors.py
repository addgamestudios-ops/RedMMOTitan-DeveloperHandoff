"""Read-only actor inventory for the protected fused prototype map."""

import json
import os

import unreal


MAP = "/Game/RedMMO/Maps/RedPlanetGen_50km_FusedPrototype"
OUTPUT = os.environ.get(
    "RED_FUSED_ACTOR_AUDIT",
    r"D:\RedMMOTitanWindowsData\ArtistHandoff\fused_map_actor_audit.json",
)

if not unreal.EditorAssetLibrary.does_asset_exist(MAP):
    raise RuntimeError(f"Map does not exist: {MAP}")

if not unreal.EditorLevelLibrary.load_level(MAP):
    raise RuntimeError(f"Could not load map: {MAP}")

actors = []
for actor in unreal.EditorLevelLibrary.get_all_level_actors():
    actor_class = actor.get_class()
    actors.append(
        {
            "label": actor.get_actor_label(),
            "name": actor.get_name(),
            "class_name": actor_class.get_name() if actor_class else "",
            "class_path": actor_class.get_path_name() if actor_class else "",
            "folder": str(actor.get_folder_path()),
            "location_cm": [
                round(actor.get_actor_location().x, 3),
                round(actor.get_actor_location().y, 3),
                round(actor.get_actor_location().z, 3),
            ],
        }
    )

actors.sort(key=lambda value: (value["class_path"], value["label"]))
payload = {"map": MAP, "actor_count": len(actors), "actors": actors}
os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)
with open(OUTPUT, "w", encoding="utf-8") as handle:
    json.dump(payload, handle, ensure_ascii=False, indent=2)

unreal.log_warning(f"RED_FUSED_ACTOR_AUDIT_READY count={len(actors)} output={OUTPUT}")
