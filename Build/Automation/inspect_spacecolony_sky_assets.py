"""Read-only audit of installed sky assets for the isolated Night_T03 test."""

import unreal


ASSETS = (
    "/Game/SpaceColony/Materials/Material_Master/M_Master_SimpleSkyDome",
    "/Game/SpaceColony/Textures/T_Stylized_AlienWorldHDRI_13",
    "/Game/SpaceColony/Textures/T_Stylized_AlienWorldHDRI_20",
    "/Game/SpaceColony/Textures/T_milky_way",
    "/Game/SpaceColony/StaticMesh/SM_Skybox",
    "/Engine/EngineSky/SM_SkySphere",
)


def emit(message):
    unreal.log("RED_SKY_ASSET_AUDIT " + str(message))


for asset_path in ASSETS:
    asset = unreal.EditorAssetLibrary.load_asset(asset_path)
    if not asset:
        emit(f"missing path={asset_path}")
        continue
    emit(
        f"asset path={asset_path} object={asset.get_path_name()} "
        f"class={asset.get_class().get_name()}"
    )
    if isinstance(asset, unreal.Texture):
        for property_name in (
            "srgb",
            "compression_settings",
            "lod_group",
            "virtual_texture_streaming",
        ):
            try:
                emit(
                    f"texture path={asset_path} {property_name}="
                    f"{asset.get_editor_property(property_name)}"
                )
            except Exception as exc:
                emit(f"texture path={asset_path} {property_name}=unavailable:{exc}")
        for method_name in ("blueprint_get_size_x", "blueprint_get_size_y"):
            method = getattr(asset, method_name, None)
            if method:
                emit(f"texture path={asset_path} {method_name}={method()}")
    if isinstance(asset, unreal.MaterialInterface):
        editing = unreal.MaterialEditingLibrary
        for label, getter in (
            ("scalar", editing.get_scalar_parameter_names),
            ("vector", editing.get_vector_parameter_names),
            ("texture", editing.get_texture_parameter_names),
            ("static_switch", editing.get_static_switch_parameter_names),
        ):
            try:
                names = sorted(str(name) for name in getter(asset))
                emit(f"material path={asset_path} {label}_parameters={names}")
            except Exception as exc:
                emit(f"material path={asset_path} {label}_parameters=unavailable:{exc}")
    if isinstance(asset, unreal.StaticMesh):
        bounds = asset.get_bounding_box()
        emit(f"mesh path={asset_path} bounds_min={bounds.min} bounds_max={bounds.max}")

emit("complete")
