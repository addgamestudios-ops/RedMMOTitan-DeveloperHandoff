import unreal


result = unreal.RedMMOEditorTools.dump_material_expressions(
    "/PlanetGen/Materials/Landscape/M_Planet.M_Planet"
)
unreal.log(f"RED_PLANET_MATERIAL_DUMP {result}")

