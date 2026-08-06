import unreal


result = unreal.RedMMOEditorTools.create_so_stylized_desert_sparkle_layer_test()
unreal.log(f"RED_SAND_T02_ASSET_RESULT {result}")
if not result.startswith("OK:"):
    raise RuntimeError(result)

