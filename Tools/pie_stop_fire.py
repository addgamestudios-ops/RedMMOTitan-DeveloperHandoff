"""Release firing on the owning PIE client."""

import unreal


worlds = unreal.EditorLevelLibrary.get_pie_worlds(include_dedicated_server=True)
client_world = next(world for world in worlds if "UEDPIE_1_" in world.get_path_name())
characters = unreal.GameplayStatics.get_all_actors_of_class(
    client_world, unreal.RedPlayerCharacter
)
shooter = next(actor for actor in characters if actor.is_locally_controlled())
shooter.stop_firing()
print(f"RED_PVP_FIRE_RELEASED shooter={shooter.get_name()}")
