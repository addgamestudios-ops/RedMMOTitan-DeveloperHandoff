from pathlib import Path

import unreal


ROOT = Path(__file__).resolve().parents[1]
DESTINATION = "/Game/RedMMO/UI/Generated"
NAMES = ("weapon_slot_epic", "weapon_slot_legendary")


tasks = []
for name in NAMES:
    task = unreal.AssetImportTask()
    task.set_editor_property(
        "filename", str(ROOT / "Saved" / "VibeEngine" / "Generated" / f"{name}.png")
    )
    task.set_editor_property("destination_path", DESTINATION)
    task.set_editor_property("destination_name", name)
    task.set_editor_property("automated", True)
    task.set_editor_property("replace_existing", True)
    task.set_editor_property("replace_existing_settings", True)
    task.set_editor_property("save", True)
    tasks.append(task)

unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks(tasks)

for name, task in zip(NAMES, tasks):
    asset_path = f"{DESTINATION}/{name}"
    if not task.get_editor_property("imported_object_paths"):
        raise RuntimeError(f"Import produced no object for {asset_path}")
    asset = unreal.EditorAssetLibrary.load_asset(asset_path)
    if not asset:
        raise RuntimeError(f"Missing weapon texture after import: {asset_path}")
    asset.set_editor_property("lod_group", unreal.TextureGroup.TEXTUREGROUP_UI)
    asset.set_editor_property("never_stream", True)
    unreal.EditorAssetLibrary.save_asset(asset_path)
    unreal.log_warning(f"REDWEAPONCARD imported transparent silhouette: {asset_path}")

unreal.log_warning("REDWEAPONCARD complete")
