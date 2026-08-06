"""Prepare project-owned copies for PlanetGen/So Stylized sand integration.

This is deliberately a preparation step only.  It duplicates the required
PlanetGen material parent and the current RedMMO biome instance into the
project sandbox, reparents the sandbox instance to the sandbox parent, and
saves just those two copies.  No purchased or production asset is modified.
"""

import traceback
import unreal


TEST_ROOT = "/Game/RedMMO/Materials/DesertSparkleTest"
SOURCE_PARENT = "/PlanetGen/Materials/Landscape/M_Planet"
SOURCE_INSTANCE = "/Game/RedMMO/Materials/MI_PlanetBiome_RED"
TEST_PARENT = TEST_ROOT + "/M_Planet_DesertSparkle_T01"
TEST_INSTANCE = TEST_ROOT + "/MI_PlanetBiome_DesertSparkle_T01"


def fail(message):
    unreal.log_error("[RedMMO Sand Integration Test] " + message)
    raise RuntimeError(message)


try:
    assets = unreal.EditorAssetLibrary

    if not assets.does_asset_exist(TEST_PARENT):
        if not assets.duplicate_asset(SOURCE_PARENT, TEST_PARENT):
            fail("Could not duplicate PlanetGen material into the sandbox")
    if not assets.does_asset_exist(TEST_INSTANCE):
        if not assets.duplicate_asset(SOURCE_INSTANCE, TEST_INSTANCE):
            fail("Could not duplicate RedMMO biome instance into the sandbox")

    parent = unreal.load_asset(TEST_PARENT)
    instance = unreal.load_asset(TEST_INSTANCE)
    if not parent or not instance:
        fail("Sandbox PlanetGen copies did not load")

    unreal.MaterialEditingLibrary.set_material_instance_parent(instance, parent)
    unreal.MaterialEditingLibrary.update_material_instance(instance)
    assets.save_loaded_asset(parent)
    assets.save_loaded_asset(instance)

    unreal.log("[RedMMO Sand Integration Test] Prepared project-only assets:")
    unreal.log("  " + TEST_PARENT)
    unreal.log("  " + TEST_INSTANCE)
except Exception:
    unreal.log_error("[RedMMO Sand Integration Test] Failed:\n" + traceback.format_exc())
    raise
