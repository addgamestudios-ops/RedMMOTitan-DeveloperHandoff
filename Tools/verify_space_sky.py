"""Non-blocking PIE verify for space sky. Uses slate tick — never sleep on game thread."""
import math
import unreal

LOG = "/tmp/titan_space_sky_verify.log"
DONE = "/tmp/titan_space_sky_verify.done"
STATE = {"step": 0, "frames": 0, "handle": None}


def log(msg):
    print(f"[verify_space_sky] {msg}")
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(str(msg) + "\n")


def finish(ok, msg=""):
    with open(DONE, "w", encoding="utf-8") as f:
        f.write(("ok\n" if ok else f"fail: {msg}\n"))
    log(("DONE ok" if ok else f"FAILED: {msg}"))
    h = STATE.get("handle")
    if h is not None:
        try:
            unreal.unregister_slate_post_tick_callback(h)
        except Exception:
            pass
        STATE["handle"] = None


def tick(_dt):
    try:
        STATE["frames"] += 1
        step = STATE["step"]

        if step == 0:
            ew = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
            sa = unreal.GameplayStatics.get_all_actors_of_class(ew, unreal.SkyAtmosphere)[0]
            sac = sa.get_component_by_class(unreal.SkyAtmosphereComponent)
            log(
                f"editor atm height={sac.get_editor_property('atmosphere_height')} "
                f"bottom={sac.get_editor_property('bottom_radius')} "
                f"rayleigh={sac.get_editor_property('rayleigh_scattering_scale')} "
                f"exp={sac.get_editor_property('rayleigh_exponential_distribution')}"
            )
            sl = unreal.GameplayStatics.get_all_actors_of_class(ew, unreal.SkyLight)[0]
            slc = sl.get_component_by_class(unreal.SkyLightComponent)
            log(
                f"editor skylight src={slc.get_editor_property('source_type')} "
                f"cube={slc.get_editor_property('cubemap')} "
                f"inten={slc.get_editor_property('intensity')}"
            )
            for a in unreal.GameplayStatics.get_all_actors_of_class(ew, unreal.StaticMeshActor):
                if "SpaceStarDome" in [str(t) for t in a.tags]:
                    smc = a.get_component_by_class(unreal.StaticMeshComponent)
                    m = smc.get_material(0) if smc else None
                    log(f"editor dome {a.get_actor_label()} mat={m.get_path_name() if m else None}")
            les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
            les.editor_request_begin_play()
            log("PIE begin requested")
            STATE["step"] = 1
            STATE["wait_frames"] = 0
            return

        if step == 1:
            STATE["wait_frames"] = STATE.get("wait_frames", 0) + 1
            gw = unreal.EditorLevelLibrary.get_game_world()
            if not gw:
                if STATE["wait_frames"] > 600:
                    finish(False, "no game world")
                return
            pawn = unreal.GameplayStatics.get_player_pawn(gw, 0)
            if not pawn:
                if STATE["wait_frames"] > 600:
                    finish(False, "no pawn")
                return
            unreal.SystemLibrary.execute_console_command(gw, "Slate.bAllowThrottling 0")
            log(f"PIE live pawn={pawn.get_name()} class={pawn.get_class().get_name()}")
            STATE["step"] = 2
            STATE["wait_frames"] = 0
            return

        if step == 2:
            # warm ~3s at 60fps ~180 frames; cold shader may be slower — wait 300
            STATE["wait_frames"] = STATE.get("wait_frames", 0) + 1
            if STATE["wait_frames"] < 300:
                return
            gw = unreal.EditorLevelLibrary.get_game_world()
            pawn = unreal.GameplayStatics.get_player_pawn(gw, 0)
            pl = pawn.get_actor_location()
            r = math.sqrt(pl.x * pl.x + pl.y * pl.y + pl.z * pl.z)
            log(f"pre-teleport R={r:.1f} AGL={r - 600000:.1f}")
            if r < 1.0:
                dx, dy, dz = 0.288, 0.957, 0.024
            else:
                dx, dy, dz = pl.x / r, pl.y / r, pl.z / r
            target_r = 1200000.0
            target = unreal.Vector(dx * target_r, dy * target_r, dz * target_r)
            shuttles = [
                a
                for a in unreal.GameplayStatics.get_all_actors_of_class(gw, unreal.Actor)
                if "Shuttle" in a.get_class().get_name()
            ]
            log(f"shuttles={[s.get_name() for s in shuttles]}")
            subject = shuttles[0] if shuttles else pawn
            subject.set_actor_location(target, False, True)
            if subject != pawn:
                pawn.set_actor_location(target, False, True)
            STATE["subject_name"] = subject.get_name()
            STATE["step"] = 3
            STATE["wait_frames"] = 0
            return

        if step == 3:
            STATE["wait_frames"] = STATE.get("wait_frames", 0) + 1
            if STATE["wait_frames"] < 120:
                return
            gw = unreal.EditorLevelLibrary.get_game_world()
            pawn = unreal.GameplayStatics.get_player_pawn(gw, 0)
            subject = pawn
            for a in unreal.GameplayStatics.get_all_actors_of_class(gw, unreal.Actor):
                if a.get_name() == STATE.get("subject_name"):
                    subject = a
                    break
            loc = subject.get_actor_location()
            sr = math.sqrt(loc.x * loc.x + loc.y * loc.y + loc.z * loc.z)
            pc = unreal.GameplayStatics.get_player_controller(gw, 0)
            cam_r = None
            if pc and pc.player_camera_manager:
                cam = pc.player_camera_manager.get_camera_location()
                cam_r = math.sqrt(cam.x * cam.x + cam.y * cam.y + cam.z * cam.z)
                log(f"camera R={cam_r:.1f} AGL={cam_r - 600000:.1f}")
            log(f"subject={subject.get_name()} R={sr:.1f} AGL={sr - 600000:.1f}")

            sa = unreal.GameplayStatics.get_all_actors_of_class(gw, unreal.SkyAtmosphere)[0]
            sac = sa.get_component_by_class(unreal.SkyAtmosphereComponent)
            h = float(sac.get_editor_property("atmosphere_height"))
            b = float(sac.get_editor_property("bottom_radius"))
            top_cm = (b + h) * 100000.0
            check_r = cam_r if cam_r else sr
            outside = check_r > top_cm
            log(f"PIE atm bottom_km={b} height_km={h} top_cm={top_cm:.1f} view_outside={outside}")

            for a in unreal.GameplayStatics.get_all_actors_of_class(gw, unreal.StaticMeshActor):
                if "SpaceStarDome" not in [str(t) for t in a.tags]:
                    continue
                smc = a.get_component_by_class(unreal.StaticMeshComponent)
                mid = smc.get_material(0)
                fade = None
                try:
                    fade = mid.get_scalar_parameter_value("SpaceFade")
                except Exception as e:
                    fade = f"n/a:{e}"
                log(f"dome {a.get_actor_label()} mat={mid.get_name() if mid else None} SpaceFade={fade}")

            if pc:
                try:
                    pc.set_view_target_with_blend(subject, 0.0)
                except Exception:
                    pass
            unreal.SystemLibrary.execute_console_command(gw, "HighResShot 1920x1080")
            log("HighResShot requested")
            STATE["step"] = 4
            STATE["wait_frames"] = 0
            return

        if step == 4:
            STATE["wait_frames"] = STATE.get("wait_frames", 0) + 1
            if STATE["wait_frames"] < 90:
                return
            finish(True)
            return

    except Exception as e:
        finish(False, str(e))


open(LOG, "w", encoding="utf-8").write("start\n")
STATE["handle"] = unreal.register_slate_post_tick_callback(tick)
log("registered tick")
