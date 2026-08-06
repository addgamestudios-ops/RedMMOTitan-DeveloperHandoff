"""Fire one prediction-local shot from the owning PIE client for net validation."""

import unreal


worlds = unreal.EditorLevelLibrary.get_pie_worlds(include_dedicated_server=True)
client_worlds = [world for world in worlds if "UEDPIE_1_" in world.get_path_name()]
if not client_worlds:
    raise RuntimeError(f"No PIE client world found: {[w.get_path_name() for w in worlds]}")

world = client_worlds[0]
characters = unreal.GameplayStatics.get_all_actors_of_class(world, unreal.RedPlayerCharacter)
shooter = next((actor for actor in characters if actor.is_locally_controlled()), None)
if not shooter:
    raise RuntimeError("No locally controlled RedPlayerCharacter in PIE client world")

weapon = next(
    (
        component
        for component in shooter.get_components_by_class(unreal.SkeletalMeshComponent)
        if component.get_name() == "WeaponMesh"
    ),
    None,
)
muzzle = shooter.get_muzzle_world_location()
socket = weapon.get_socket_location("Muzzle") if weapon else unreal.Vector()
print(
    "RED_PVP_FIRE_BEGIN "
    f"shooter={shooter.get_name()} muzzle={muzzle} socket={socket} "
    f"socket_delta={(muzzle - socket).length()}"
)
shooter.start_firing()
shooter.stop_firing()
print("RED_PVP_FIRE_SENT")
