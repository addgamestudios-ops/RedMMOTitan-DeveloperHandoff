"""Level the local client's view for a repeatable two-player PIE shot."""

import unreal


worlds = unreal.EditorLevelLibrary.get_pie_worlds(include_dedicated_server=True)
client_world = next(world for world in worlds if "UEDPIE_1_" in world.get_path_name())
characters = unreal.GameplayStatics.get_all_actors_of_class(
    client_world, unreal.RedPlayerCharacter
)
shooter = next(actor for actor in characters if actor.is_locally_controlled())
controller = shooter.get_controller()
rotation = controller.get_control_rotation()
controller.set_control_rotation(
    unreal.Rotator(roll=0.0, pitch=0.0, yaw=rotation.yaw)
)

print(
    "RED_PVP_AIM_LEVEL "
    f"shooter={shooter.get_name()} yaw={rotation.yaw}"
)
