"""Create the disposable NightWater_T04 material child without touching vendor assets.

This is intentionally a one-asset, project-only editor automation.  It creates a
child of RED's production water instance, preserves all inherited So Stylized
textures and tiling, and applies only the conservative night-test overrides.
"""

import unreal


SOURCE_PATH = "/Game/RedMMO/Environment/MI_RedClearWater.MI_RedClearWater"
DESTINATION_PATH = "/Game/RedMMO/Environment/Tests"
ASSET_NAME = "MI_RedClearWater_Night_T04"
DESTINATION_OBJECT_PATH = f"{DESTINATION_PATH}/{ASSET_NAME}.{ASSET_NAME}"


def fail(message: str) -> None:
    unreal.log_error(f"NightWater_T04 material setup failed: {message}")
    raise RuntimeError(message)


source = unreal.load_asset(SOURCE_PATH)
if not source:
    fail(f"Missing production source material {SOURCE_PATH}")

existing = unreal.load_asset(DESTINATION_OBJECT_PATH)
if existing:
    if not isinstance(existing, unreal.MaterialInstanceConstant):
        fail(f"Existing target is not a MaterialInstanceConstant: {DESTINATION_OBJECT_PATH}")
    parent = existing.get_editor_property("parent")
    if parent != source:
        fail(
            "Existing target parent is not the production RED water material; "
            "refusing to overwrite it."
        )
    target = existing
else:
    factory = unreal.MaterialInstanceConstantFactoryNew()
    target = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
        ASSET_NAME,
        DESTINATION_PATH,
        unreal.MaterialInstanceConstant,
        factory,
    )
    if not target:
        fail("AssetTools could not create the project-owned material child")
    unreal.MaterialEditingLibrary.set_material_instance_parent(target, source)

# These are test-only presentation values. They preserve all inherited normal
# maps and UV/tiling values while compiling out the two flat-demo branches that
# the real-DX12 radial A/B isolated as the source of the white blinking sheet.
# Use the project helper because Unreal's Python MaterialEditingLibrary setter
# does not reliably rebuild static switch permutations in UE 5.8.
for name, value in {
    "FadeEdge?": False,
    "ShowCaustics?": False,
}.items():
    result = unreal.RedMMOEditorTools.set_mi_static_switch(
        DESTINATION_OBJECT_PATH, name, value
    )
    if not result.startswith("OK:"):
        fail(f"Could not compile static switch {name}={value}: {result}")

unreal.MaterialEditingLibrary.set_material_instance_vector_parameter_value(
    target, "Emissive Color", unreal.LinearColor(0.0, 0.0, 0.0, 1.0)
)
for name, value in {
    "Water Scattering": 0.08,
    "Normal1 Flatness": 0.64,
    "Normal2 Flatness": 0.70,
    "Distant Normal Flatness": 0.82,
    "Foam Multiply": 0.0,
    # The demo's caustic pass is intentionally bright.  On the spherical
    # PlanetGen ocean it has no meaningful receiver depth and becomes a full
    # white sheet during a real dark-side capture, so disable it only on the
    # disposable night-test child.
    "Caustic Strength": 0.0,
    # Keep the So Stylized water physically lit in the night harness.  Its
    # time-of-day emission multipliers are authored for the flat demo's MPC;
    # they must not re-introduce a white animated sheet on this radial ocean.
    "Day Emission Multiplier": 0.0,
    "Night Emission Multiplier": 0.0,
    "Sunrise Emission Multiplier": 0.0,
    "Sunset Emission Multiplier": 0.0,
    "Overcast Emission Multiplier": 0.0,
    # Avoid a full-screen white sky reflection while retaining a readable
    # surface response for the real moon light.
    "Specular": 0.10,
    "Roughness": 0.52,
    # The vendor's separate Edge Waves branch depends on flat-demo distance
    # fields. Fine motion comes from the independent Normal1/Normal2 panners,
    # whose inherited textures, sizes, flatness and nonzero speeds remain intact.
    "Waves": 0.0,
}.items():
    unreal.MaterialEditingLibrary.set_material_instance_scalar_parameter_value(target, name, value)

unreal.MaterialEditingLibrary.update_material_instance(target)
if not unreal.EditorAssetLibrary.save_loaded_asset(target, only_if_is_dirty=False):
    fail(f"Could not save {DESTINATION_OBJECT_PATH}")

unreal.log(
    "NightWater_T04 material setup succeeded: project-owned direct child created/updated at "
    + DESTINATION_OBJECT_PATH
)
