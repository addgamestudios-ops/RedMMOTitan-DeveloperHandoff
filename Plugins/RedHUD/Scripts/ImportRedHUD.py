"""
RED HUD texture importer for Unreal Engine 5.8.

Run from the Unreal Editor:
    Tools -> Execute Python Script -> Plugins/RedHUD/Scripts/ImportRedHUD.py

Or command line:
    UnrealEditor <Project>.uproject -ExecutePythonScript="<Project>/Plugins/RedHUD/Scripts/ImportRedHUD.py"
"""

from __future__ import annotations

import os
from pathlib import Path

import unreal


DESTINATION_ROOT = "/Game/UI/RedHUD/Textures"


def enum_member(enum_type, *candidate_names):
    for candidate in candidate_names:
        if hasattr(enum_type, candidate):
            return getattr(enum_type, candidate)
    raise RuntimeError(
        f"Could not resolve any of {candidate_names!r} on Unreal enum {enum_type!r}"
    )


def configure_ui_texture(texture: unreal.Texture2D) -> None:
    texture.set_editor_property(
        "compression_settings",
        enum_member(
            unreal.TextureCompressionSettings,
            "TC_EDITOR_ICON",       # Display name: UserInterface2D (RGBA)
        ),
    )
    texture.set_editor_property(
        "lod_group",
        enum_member(unreal.TextureGroup, "TEXTUREGROUP_UI"),
    )
    texture.set_editor_property(
        "mip_gen_settings",
        enum_member(
            unreal.TextureMipGenSettings,
            "TMGS_NO_MIPMAPS",
            "TMGS_NO_MIPMAP",
        ),
    )
    texture.set_editor_property("never_stream", True)
    texture.set_editor_property("srgb", True)
    texture.set_editor_property("virtual_texture_streaming", False)
    texture.set_editor_property("compression_no_alpha", False)
    texture.set_editor_property(
        "address_x",
        enum_member(unreal.TextureAddress, "TA_CLAMP"),
    )
    texture.set_editor_property(
        "address_y",
        enum_member(unreal.TextureAddress, "TA_CLAMP"),
    )
    texture.set_editor_property(
        "filter",
        enum_member(unreal.TextureFilter, "TF_BILINEAR", "TF_DEFAULT"),
    )
    texture.modify()
    # UE 5.8's Python Texture2D wrapper no longer exposes post_edit_change().
    # Setting editor properties already notifies the asset; save it explicitly.
    unreal.EditorAssetLibrary.save_loaded_asset(texture, only_if_is_dirty=False)


def import_png(source_file: Path, destination_path: str) -> list[str]:
    task = unreal.AssetImportTask()
    task.set_editor_property("filename", str(source_file))
    task.set_editor_property("destination_path", destination_path)
    task.set_editor_property("destination_name", source_file.stem)
    task.set_editor_property("automated", True)
    # These assets live in a dedicated project namespace. Refuse silent
    # replacement so an import can never overwrite accepted project content.
    task.set_editor_property("replace_existing", False)
    task.set_editor_property("replace_existing_settings", False)
    task.set_editor_property("save", False)

    factory = unreal.TextureFactory()
    factory.set_editor_property("create_material", False)
    factory.set_editor_property("no_alpha", False)
    task.set_editor_property("factory", factory)

    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
    return list(task.get_editor_property("imported_object_paths"))


def main() -> None:
    script_dir = Path(__file__).resolve().parent
    plugin_dir = script_dir.parent
    art_root = plugin_dir / "Resources" / "Art"

    if not art_root.is_dir():
        raise RuntimeError(f"RED HUD art folder does not exist: {art_root}")

    imported_count = 0
    failed = []

    for png_file in sorted(art_root.rglob("*.png")):
        relative_parent = png_file.parent.relative_to(art_root)
        destination = DESTINATION_ROOT
        if str(relative_parent) != ".":
            destination += "/" + relative_parent.as_posix()

        unreal.log(f"[RED HUD] Importing {png_file.name} -> {destination}")
        object_paths = import_png(png_file, destination)

        if not object_paths:
            failed.append(str(png_file))
            unreal.log_error(f"[RED HUD] Import returned no assets for {png_file}")
            continue

        for object_path in object_paths:
            asset = unreal.load_asset(object_path)
            if isinstance(asset, unreal.Texture2D):
                configure_ui_texture(asset)
                imported_count += 1
            else:
                unreal.log_warning(
                    f"[RED HUD] Imported object is not Texture2D: {object_path}"
                )

    if failed:
        raise RuntimeError(
            "[RED HUD] Some files failed to import:\n" + "\n".join(failed)
        )

    unreal.log(
        f"[RED HUD] Complete. Configured {imported_count} PNG textures under "
        f"{DESTINATION_ROOT}."
    )


if __name__ == "__main__":
    main()
