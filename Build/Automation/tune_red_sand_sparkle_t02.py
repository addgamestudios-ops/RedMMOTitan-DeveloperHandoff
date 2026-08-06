"""Retune the project-owned T02 sparkle function instance only."""

import unreal


result = unreal.RedMMOEditorTools.tune_so_stylized_desert_sparkle_layer_test(120.0, 0.75)
unreal.log("RED_SAND_T02_TUNE_RESULT " + result)
if not result.startswith("OK:"):
    raise RuntimeError(result)
