import unreal


ASSETS = [
    "/Game/Cloudz_Hi5/Materials/Instances/MI_Cloudz_Hi5_002",
    "/Game/Cloudz_Hi5/Materials/Instances/MI_Cloudz_Hi5_003",
    "/Game/Cloudz_Hi5/Materials/Instances/MI_Cloudz_Hi5_004",
    "/Game/Cloudz_Hi5/Materials/Instances/MI_Cloudz_Hi5_005",
]


def describe_override(prefix, entry):
    info = entry.get_editor_property("parameter_info")
    name = info.get_editor_property("name")
    value = entry.get_editor_property("parameter_value")
    unreal.log_warning(f"HI5_PARAM {prefix} name={name} value={value}")


for asset_path in ASSETS:
    asset = unreal.EditorAssetLibrary.load_asset(asset_path)
    if asset is None:
        unreal.log_error(f"HI5_ASSET_MISSING {asset_path}")
        continue
    unreal.log_warning(
        f"HI5_ASSET_BEGIN path={asset.get_path_name()} class={asset.get_class().get_name()}"
    )
    for entry in list(asset.get_editor_property("scalar_parameter_values")):
        describe_override("scalar", entry)
    for entry in list(asset.get_editor_property("vector_parameter_values")):
        describe_override("vector", entry)
    for entry in list(asset.get_editor_property("texture_parameter_values")):
        describe_override("texture", entry)
    parent = asset.get_editor_property("parent")
    unreal.log_warning(
        "HI5_ASSET_END parent=" + (parent.get_path_name() if parent else "None")
    )
