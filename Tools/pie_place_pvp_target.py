"""Place the authoritative remote pawn directly on the client's current camera ray."""

import unreal


worlds = unreal.EditorLevelLibrary.get_pie_worlds(include_dedicated_server=True)
server_world = next(world for world in worlds if "UEDPIE_0_" in world.get_path_name())
client_world = next(world for world in worlds if "UEDPIE_1_" in world.get_path_name())

client_characters = unreal.GameplayStatics.get_all_actors_of_class(
    client_world, unreal.RedPlayerCharacter
)
client_shooter = next(actor for actor in client_characters if actor.is_locally_controlled())
camera = client_shooter.get_component_by_class(unreal.CameraComponent)

server_characters = unreal.GameplayStatics.get_all_actors_of_class(
    server_world, unreal.RedPlayerCharacter
)
server_shooter = min(
    server_characters,
    key=lambda actor: (
        actor.get_actor_location() - client_shooter.get_actor_location()
    ).length(),
)
server_target = next(actor for actor in server_characters if actor != server_shooter)
target_movement = server_target.get_component_by_class(unreal.CharacterMovementComponent)

camera_location = camera.get_world_location()
camera_forward = camera.get_forward_vector()
target_location = camera_location + camera_forward * 650.0
server_target.set_actor_location(target_location, False, True)
target_movement.stop_movement_immediately()
target_movement.disable_movement()

print(
    "RED_PVP_TARGET_PLACED "
    f"shooter={server_shooter.get_name()} target={server_target.get_name()} "
    f"camera={camera_location} forward={camera_forward} target_loc={target_location}"
)
