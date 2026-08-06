"""Read-only water material compatibility audit for the T04 shoreline test."""

import unreal


ASSET_PATHS = (
    "/WorldGen/Materials/Water/M_Water.M_Water",
    "/WorldGen/Materials/Water/MI_Water.MI_Water",
    "/Game/RedMMO/Environment/MI_RedClearWater.MI_RedClearWater",
    "/Game/RedMMO/Environment/Tests/MI_RedClearWater_Night_T04.MI_RedClearWater_Night_T04",
)


def describe(asset_path: str) -> None:
    asset = unreal.EditorAssetLibrary.load_asset(asset_path)
    if not asset:
        unreal.log_warning(f"RED_WATER_COMPAT missing={asset_path}")
        return

    parent_path = "<none>"
    base = asset
    if isinstance(asset, unreal.MaterialInstance):
        parent = asset.get_editor_property("parent")
        parent_path = parent.get_path_name() if parent else "<none>"
        while isinstance(base, unreal.MaterialInstance):
            base = base.get_editor_property("parent")
            if not base:
                break
    material_info = "<not-material>"
    if isinstance(base, unreal.Material):
        # UE's Python property name for the shading model differs between minor
        # releases; the material identity and blend mode are enough for this
        # compatibility audit.
        material_info = f"blend={base.get_editor_property('blend_mode')}"
    unreal.log_warning(
        f"RED_WATER_COMPAT asset={asset.get_path_name()} class={asset.get_class().get_name()} "
        f"parent={parent_path} {material_info}"
    )


for path in ASSET_PATHS:
    describe(path)

# The pinned plugin's folder name differs from its logical mount point in some
# editor sessions. Discover the actual registered path instead of guessing it.
registry = unreal.AssetRegistryHelpers.get_asset_registry()
for asset_data in registry.get_all_assets():
    asset_name = str(asset_data.asset_name)
    package_name = str(asset_data.package_name)
    if asset_name in {"M_PlanetWater", "M_Water", "M_WaterSimple", "MI_Water"} \
            and "Materials/Water" in package_name:
        unreal.log_warning(
            f"RED_WATER_COMPAT_DISCOVERED package={package_name} "
            f"asset={asset_name} raw={asset_data}"
        )

unreal.log_warning("RED_WATER_COMPAT_COMPLETE")
