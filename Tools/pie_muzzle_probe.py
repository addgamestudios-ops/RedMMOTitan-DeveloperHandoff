"""Compare the authored muzzle socket with the weapon component-space barrel tip."""

import unreal


world = next(
    w
    for w in unreal.EditorLevelLibrary.get_pie_worlds(include_dedicated_server=True)
    if "UEDPIE_1_" in w.get_path_name()
)
characters = unreal.GameplayStatics.get_all_actors_of_class(world, unreal.RedPlayerCharacter)
shooter = next(actor for actor in characters if actor.is_locally_controlled())
weapon = next(
    component
    for component in shooter.get_components_by_class(unreal.SkeletalMeshComponent)
    if component.get_name() == "WeaponMesh"
)
component_tip = weapon.get_world_transform().transform_location(
    unreal.Vector(0.0, 55.0, 7.0)
)
muzzle_world = weapon.get_socket_location("Muzzle")
muzzle_local = weapon.get_world_transform().inverse_transform_location(muzzle_world)
print(
    "RED_MUZZLE_PROBE "
    f"actor={shooter.get_actor_location()} component={weapon.get_world_location()} "
    f"root_bone={weapon.get_socket_location('root_weapon')} "
    f"weapon_bone={weapon.get_socket_location('weapon')} "
    f"component_tip={component_tip} muzzle={muzzle_world} muzzle_local={muzzle_local} "
    f"socket_vs_component={(muzzle_world - component_tip).length()}"
)
