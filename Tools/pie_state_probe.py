"""Print authoritative/client weapon and health state for the active two-player PIE session."""

import unreal


def prop(obj, name, default=None):
    try:
        return obj.get_editor_property(name)
    except Exception:
        return default


worlds = unreal.EditorLevelLibrary.get_pie_worlds(include_dedicated_server=True)
for world in worlds:
    characters = unreal.GameplayStatics.get_all_actors_of_class(world, unreal.RedPlayerCharacter)
    bolts = unreal.GameplayStatics.get_all_actors_of_class(world, unreal.RedBolt)
    print(
        f"RED_PVP_WORLD world={world.get_path_name()} chars={len(characters)} bolts={len(bolts)}"
    )
    for actor in characters:
        weapon = next(
            (
                component
                for component in actor.get_components_by_class(unreal.SkeletalMeshComponent)
                if component.get_name() == "WeaponMesh"
            ),
            None,
        )
        muzzle = actor.get_muzzle_world_location()
        socket = weapon.get_socket_location("Muzzle") if weapon else unreal.Vector()
        mesh = actor.get_component_by_class(unreal.SkeletalMeshComponent)
        anim = mesh.get_anim_instance() if mesh else None
        print(
            "RED_PVP_CHAR "
            f"name={actor.get_name()} local={actor.is_locally_controlled()} "
            f"role={actor.get_local_role()} health={prop(actor, 'health')} "
            f"shield={prop(actor, 'shield')} downed={prop(actor, 'b_downed')} "
            f"projectile={prop(actor, 'projectile_class')} fire_rate={prop(actor, 'fire_rate')} "
            f"loc={actor.get_actor_location()} muzzle={muzzle} "
            f"socket_delta={(muzzle - socket).length()} "
            f"weapon={weapon.get_skeletal_mesh_asset().get_name() if weapon and weapon.get_skeletal_mesh_asset() else 'None'} "
            f"anim={anim.get_class().get_name() if anim else 'None'} "
            f"aim={prop(anim, 'b_is_aiming')} weight={prop(anim, 'weapon_drawn_weight')}"
        )
    for bolt in bolts:
        print(
            "RED_PVP_BOLT "
            f"name={bolt.get_name()} owner={bolt.get_owner().get_name() if bolt.get_owner() else 'None'} "
            f"loc={bolt.get_actor_location()}"
        )
