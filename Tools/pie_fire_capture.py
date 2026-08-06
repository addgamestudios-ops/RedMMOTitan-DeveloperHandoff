"""Fire once and inspect the authoritative/replicated bolt on following PIE frames."""

import unreal


state = {"phase": 0, "handle": None, "server_muzzle": None}


def pie_worlds():
    return unreal.EditorLevelLibrary.get_pie_worlds(include_dedicated_server=True)


def find_shooter():
    client_world = next(w for w in pie_worlds() if "UEDPIE_1_" in w.get_path_name())
    chars = unreal.GameplayStatics.get_all_actors_of_class(
        client_world, unreal.RedPlayerCharacter
    )
    return next(actor for actor in chars if actor.is_locally_controlled())


def capture_server_muzzle(client_shooter):
    server_world = next(w for w in pie_worlds() if "UEDPIE_0_" in w.get_path_name())
    chars = unreal.GameplayStatics.get_all_actors_of_class(
        server_world, unreal.RedPlayerCharacter
    )
    server_shooter = min(
        chars,
        key=lambda actor: (
            actor.get_actor_location() - client_shooter.get_actor_location()
        ).length(),
    )
    return server_shooter.get_muzzle_world_location()


def on_tick(_delta_seconds):
    if state["phase"] == 0:
        shooter = find_shooter()
        state["server_muzzle"] = capture_server_muzzle(shooter)
        shooter.start_firing()
        shooter.stop_firing()
        state["phase"] = 1
        print(f"RED_PVP_FRAME_FIRE server_muzzle={state['server_muzzle']}")
        return

    frame = state["phase"]
    for world in pie_worlds():
        bolts = unreal.GameplayStatics.get_all_actors_of_class(world, unreal.RedBolt)
        for bolt in bolts:
            distance = (bolt.get_actor_location() - state["server_muzzle"]).length()
            print(
                "RED_PVP_FRAME_BOLT "
                f"frame={frame} world={world.get_path_name()} bolt={bolt.get_name()} "
                f"owner={bolt.get_owner().get_name() if bolt.get_owner() else 'None'} "
                f"loc={bolt.get_actor_location()} distance_from_server_muzzle={distance}"
            )
        if not bolts:
            print(
                f"RED_PVP_FRAME_BOLT frame={frame} "
                f"world={world.get_path_name()} bolts=0"
            )

    if frame >= 8:
        unreal.unregister_slate_post_tick_callback(state["handle"])
        print("RED_PVP_FRAME_CAPTURE_DONE")
    else:
        state["phase"] += 1


state["handle"] = unreal.register_slate_post_tick_callback(on_tick)
print("RED_PVP_FRAME_CAPTURE_ARMED")
