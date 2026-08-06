"""Import the tracked Rifle Pro FBXs onto the Action Trooper tall-female skeleton.

Run inside Unreal Editor's Python environment. The import is deliberately
repeatable and writes only project-owned assets under /Game/RedMMO.
"""

from pathlib import Path

import unreal


PROJECT_ROOT = Path(unreal.Paths.project_dir())
SOURCE_ROOT = PROJECT_ROOT / "Source" / "FBX" / "In_Place"
DESTINATION = "/Game/RedMMO/Anims/Rifle"
SKELETON_PATH = (
    "/Game/Action_Trooper/Skeletons_and_Physics_Assets/"
    "SKEL_UE4_Tall_Female_TRPR.SKEL_UE4_Tall_Female_TRPR"
)

ANIMATIONS = {
    "W2_Stand_Relaxed_Idle_v2_IPC.fbx": "A_Rifle_Relaxed_Idle",
    "W2_Stand_Aim_Idle_v2_IPC.fbx": "A_Rifle_Aim_Idle",
    "W2_Stand_Fire_Single_IPC.fbx": "A_Rifle_Fire_Single",
    "W2_Jog_Aim_F_Loop_IPC.fbx": "A_Rifle_Jog_Aim_Fwd",
    "W2_Stand_Aim_Jump_Start_IPC.fbx": "A_Rifle_Aim_Jump_Start",
    "W2_Stand_Aim_Jump_Air_IPC.fbx": "A_Rifle_Jetpack_Aim_Air",
    "W2_Stand_Aim_Jump_End_IPC.fbx": "A_Rifle_Aim_Jump_End",
}


def make_options(skeleton: unreal.Skeleton) -> unreal.FbxImportUI:
    options = unreal.FbxImportUI()
    options.set_editor_property("automated_import_should_detect_type", False)
    options.set_editor_property("mesh_type_to_import", unreal.FBXImportType.FBXIT_ANIMATION)
    options.set_editor_property("import_as_skeletal", True)
    options.set_editor_property("import_mesh", False)
    options.set_editor_property("import_animations", True)
    options.set_editor_property("skeleton", skeleton)

    anim_data = options.get_editor_property("anim_sequence_import_data")
    anim_data.set_editor_property(
        "animation_length",
        unreal.FBXAnimationLengthImportType.FBXALIT_EXPORTED_TIME,
    )
    anim_data.set_editor_property("import_bone_tracks", True)
    anim_data.set_editor_property("remove_redundant_keys", True)
    return options


def main() -> None:
    skeleton = unreal.load_asset(SKELETON_PATH)
    if not skeleton:
        raise RuntimeError(f"Skeleton not found: {SKELETON_PATH}")

    unreal.EditorAssetLibrary.make_directory(DESTINATION)
    tasks = []
    for source_name, asset_name in ANIMATIONS.items():
        source_file = SOURCE_ROOT / source_name
        if not source_file.is_file():
            raise RuntimeError(f"Animation source not found: {source_file}")

        task = unreal.AssetImportTask()
        task.set_editor_property("filename", str(source_file))
        task.set_editor_property("destination_path", DESTINATION)
        task.set_editor_property("destination_name", asset_name)
        task.set_editor_property("automated", True)
        task.set_editor_property("replace_existing", True)
        task.set_editor_property("replace_existing_settings", True)
        task.set_editor_property("save", True)
        task.set_editor_property("options", make_options(skeleton))
        tasks.append(task)

    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks(tasks)

    imported = []
    for task in tasks:
        imported.extend(task.get_editor_property("imported_object_paths"))
    if len(imported) != len(tasks):
        raise RuntimeError(
            f"Expected {len(tasks)} animation assets, imported {len(imported)}: {imported}"
        )

    unreal.EditorAssetLibrary.save_directory(DESTINATION, only_if_is_dirty=False, recursive=True)
    print("RED_RIFLE_IMPORT_OK " + " | ".join(imported))


if __name__ == "__main__":
    main()
