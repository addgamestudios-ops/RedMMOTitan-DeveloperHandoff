import unreal


MAP_PATH = "/Game/Cloudz_Hi5/Overview"


def describe_object(obj):
    if obj is None:
        return "None"
    return f"{obj.get_class().get_name()} {obj.get_path_name()}"


def safe_property(obj, name):
    if obj is None:
        return "None"
    try:
        return obj.get_editor_property(name)
    except Exception as exc:
        return f"UNAVAILABLE({name}: {exc})"


if not unreal.EditorLoadingAndSavingUtils.load_map(MAP_PATH):
    raise RuntimeError(f"Unable to load {MAP_PATH}")

actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors()
volumes = [actor for actor in actors if actor.get_class().get_name() == "HeterogeneousVolume"]
unreal.log_warning(f"HI5_OVERVIEW_VOLUME_COUNT {len(volumes)}")

for actor in sorted(volumes, key=lambda item: item.get_name()):
    components = actor.get_components_by_class(unreal.ActorComponent)
    component = next(
        (item for item in components if item.get_class().get_name() == "HeterogeneousVolumeComponent"),
        None,
    )
    material = component.get_material(0) if component else None
    bounds = safe_property(component, "bounds")
    resolution = safe_property(component, "volume_resolution")
    frame_transform = safe_property(component, "frame_transform")
    pivot_at_centroid = safe_property(component, "pivot_at_centroid")
    unreal.log_warning(
        "HI5_OVERVIEW_VOLUME "
        f"actor={actor.get_name()} "
        f"location={actor.get_actor_location()} "
        f"rotation={actor.get_actor_rotation()} "
        f"scale={actor.get_actor_scale3d()} "
        f"component={describe_object(component)} "
        f"material={describe_object(material)} "
        f"resolution={resolution} "
        f"frame={frame_transform} "
        f"pivot_centroid={pivot_at_centroid} "
        f"local_bounds={bounds}"
    )

unreal.log_warning("HI5_OVERVIEW_INSPECTION_COMPLETE")
