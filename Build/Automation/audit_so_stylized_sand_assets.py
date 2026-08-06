"""Read-only audit of the So Stylized sand integration assets.

This script intentionally does not save or mutate any package.  It is used by
the modular build queue to determine which project-owned material chain can be
safely promoted to a real-GPU planet-surface test.
"""

import unreal


ASSETS = (
    "/Game/SoStylized/Materials/MF_DesertSand",
    "/Game/SoStylized/Materials/MF_Sparkle",
    "/Game/SoStylized/Environment/Landscape/Materials/MI_Landscape_Desert",
    "/Game/RedMMO/Materials/MI_PlanetBiome_RED",
    "/Game/RedMMO/Materials/MI_PlanetDesert_RED",
    "/Game/RedMMO/Materials/DesertSparkleTest/MF_DesertSand_PlanetLayer_T01",
    "/Game/RedMMO/Materials/DesertSparkleTest/ML_DesertSparkleWrapper_T01",
    "/Game/RedMMO/Materials/DesertSparkleTest/MFI_DesertSparkleWrapper_T01",
    "/Game/RedMMO/Materials/DesertSparkleTest/M_Planet_DesertSparkle_T01",
    "/Game/RedMMO/Materials/DesertSparkleTest/MI_PlanetBiome_DesertSparkle_T01",
    "/Game/RedMMO/Materials/DesertSparkleTest/M_DesertSandSparkle_T01",
    "/Game/RedMMO/Materials/DesertSparkleTest/MI_DesertSandSparkle_Demo_T01",
)


def safe_property(obj, name):
    try:
        value = obj.get_editor_property(name)
        if isinstance(value, unreal.Object):
            return value.get_path_name()
        return str(value)
    except Exception as exc:
        return "<unavailable: {}>".format(exc)


registry = unreal.AssetRegistryHelpers.get_asset_registry()
unreal.log("[RedMMO Sand Audit] BEGIN")
for path in ASSETS:
    exists = unreal.EditorAssetLibrary.does_asset_exist(path)
    unreal.log("[RedMMO Sand Audit] ASSET {} exists={}".format(path, exists))
    if not exists:
        continue
    asset = unreal.load_asset(path)
    if not asset:
        unreal.log_error("[RedMMO Sand Audit] load failed: {}".format(path))
        continue
    unreal.log(
        "[RedMMO Sand Audit] CLASS {} {}".format(
            path, asset.get_class().get_path_name()
        )
    )
    for prop in (
        "parent",
        "material_function_usage",
        "use_material_attributes",
        "blend_mode",
        "shading_model",
    ):
        unreal.log(
            "[RedMMO Sand Audit] PROP {} {}={}".format(
                path, prop, safe_property(asset, prop)
            )
        )
    data = registry.get_asset_by_object_path(unreal.Name(path + "." + path.rsplit("/", 1)[-1]))
    if data and data.is_valid():
        package_name = str(data.package_name)
        dependencies = registry.get_dependencies(
            unreal.Name(package_name),
            unreal.AssetRegistryDependencyOptions(
                include_soft_package_references=True,
                include_hard_package_references=True,
                include_searchable_names=False,
                include_soft_management_references=False,
                include_hard_management_references=False,
            ),
        )
        for dependency in sorted(str(item) for item in dependencies):
            if "Stylized" in dependency or "Desert" in dependency or "Planet" in dependency:
                unreal.log(
                    "[RedMMO Sand Audit] DEP {} -> {}".format(path, dependency)
                )

unreal.log("[RedMMO Sand Audit] END")
