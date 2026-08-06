"""Run a bounded replicated jetpack-and-fire capture in two-player PIE."""

import unreal


worlds = unreal.EditorLevelLibrary.get_pie_worlds(include_dedicated_server=True)
client_world = next(world for world in worlds if "UEDPIE_1_" in world.get_path_name())
characters = unreal.GameplayStatics.get_all_actors_of_class(
    client_world, unreal.RedPlayerCharacter
)
shooter = next(actor for actor in characters if actor.is_locally_controlled())
started_at = unreal.SystemLibrary.get_game_time_in_seconds(client_world)
state = {"handle": None, "reported": False}

shooter.server_set_jetpack_input(True, True, False, False)
shooter.start_firing()
print(f"RED_PVP_JETPACK_FIRE_BEGIN shooter={shooter.get_name()}")


def on_tick(_delta_seconds):
    elapsed = unreal.SystemLibrary.get_game_time_in_seconds(client_world) - started_at
    if not state["reported"] and elapsed >= 0.8:
        for world in worlds:
            for actor in unreal.GameplayStatics.get_all_actors_of_class(
                world, unreal.RedPlayerCharacter
            ):
                if actor.is_locally_controlled() or actor.get_local_role() == unreal.NetRole.ROLE_AUTHORITY:
                    try:
                        jetpack_on = actor.get_editor_property("b_jetpack_on")
                        jump_held = actor.get_editor_property("b_jump_held")
                    except Exception as exc:
                        jetpack_on = f"unreadable:{exc}"
                        jump_held = "unreadable"
                    print(
                        "RED_PVP_JETPACK_STATE "
                        f"world={world.get_path_name()} actor={actor.get_name()} "
                        f"role={actor.get_local_role()} on={jetpack_on} held={jump_held} "
                        f"loc={actor.get_actor_location()}"
                    )
        state["reported"] = True
    if elapsed < 4.0:
        return
    shooter.stop_firing()
    shooter.server_set_jetpack_input(False, False, False, False)
    unreal.unregister_slate_post_tick_callback(state["handle"])
    print(f"RED_PVP_JETPACK_FIRE_END shooter={shooter.get_name()}")


state["handle"] = unreal.register_slate_post_tick_callback(on_tick)
