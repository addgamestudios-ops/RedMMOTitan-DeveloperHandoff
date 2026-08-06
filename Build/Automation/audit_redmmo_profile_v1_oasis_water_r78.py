"""R78 exact-coast transient absorption sweep over the PPG-compatible Oasis-water candidate."""

from pathlib import Path


SOURCE = Path(r"D:\RedMMOTitan\Build\Automation\audit_redmmo_profile_v1_oasis_water_r76.py")
text = SOURCE.read_text(encoding="utf-8")
text = text.replace("R76", "R78").replace("r76", "r78")
text = text.replace("20260806T0026Z", "20260806T0102Z")
text = text.replace("20260806T0043Z", "20260806T0114Z")
text = text.replace("Verify2", "Verify3")
text = text.replace(
    "F733E34812872D5E0986DB9DAB6B7D61EA06E2FDCBC31DF99AC592BC2ED37F5B",
    "AA3B15F4538145C6B51B589D6B8F3E40899ACC136F573101E86C5790783E22C2",
)
text = text.replace(
    "62A00B4FF41BDB9C88907126C76D54C05595E17841355FFDF804C8B5AB7E4250",
    "B815972272713EDEC40A6CF33591E2FEF05F54D575C6049B29983330D23022F1",
)
text = text.replace(
    "3B0AAFB59A2DD7DD65709958F7ACDE6A27C73A0CBEA1991B8EE04B992A2A3687",
    "2D3DFCC7583CABBCC551DD7D08A2CF5E33CC19465D14EAB5C4308DEC018DAE9A",
)
text = text.replace('ns["now"]', 'base_ns["now"]')
text = text.replace('ns["provider_gate"]', 'base_ns["provider_gate"]')
text = text.replace('ns["write_json_exclusive"]', 'base_ns["write_json_exclusive"]')

assignment = """Audit.start = start_r78
Audit.request_capture = request_capture_r78
Audit.publish = publish_r78
"""

injection = r'''R78_VARIANTS = [
    {"label": "008", "scale": 0.08, "coefficient": [0.02248, 0.00575544, 0.00433208]},
    {"label": "018", "scale": 0.18, "coefficient": [0.05058, 0.01294974, 0.00974718]},
    {"label": "035", "scale": 0.35, "coefficient": [0.09835, 0.02518005, 0.01895285]},
]
R78_PARAMETER = "R78_AbsorptionCoefficient"
R78_VARIANT_SETTLE_FRAMES = 75


def apply_variant_r78(self, index):
    require(0 <= index < len(R78_VARIANTS), "R78 variant index invalid")
    variant = R78_VARIANTS[index]
    coefficient = variant["coefficient"]
    value = unreal.LinearColor(coefficient[0], coefficient[1], coefficient[2], 1.0)
    matched = 0
    updated = 0
    created_dynamic = 0
    material_classes = {}
    material_paths = set()
    for component in self.spawner.get_components_by_class(unreal.StaticMeshComponent):
        material = component.get_material(0)
        if material is None:
            continue
        ancestry = ns["material_ancestry"](material)
        if TARGET_MI not in ancestry:
            continue
        matched += 1
        class_name = material.get_class().get_name()
        material_classes[class_name] = material_classes.get(class_name, 0) + 1
        setter = getattr(material, "set_vector_parameter_value", None)
        if not callable(setter):
            material = component.create_dynamic_material_instance(0, material)
            require(material is not None, "R78 dynamic material creation failed")
            setter = getattr(material, "set_vector_parameter_value", None)
            require(callable(setter), "R78 runtime material has no vector setter")
            created_dynamic += 1
        setter(R78_PARAMETER, value)
        material_paths.add(material.get_path_name())
        updated += 1
    require(matched > 0 and updated == matched, "R78 did not update every native water component")
    self.r78_variant_index = index
    self.r78_variant_runtime = {
        "label": variant["label"],
        "scale": variant["scale"],
        "coefficient": coefficient,
        "matched_water_components": matched,
        "updated_water_components": updated,
        "created_dynamic_materials": created_dynamic,
        "material_classes": material_classes,
        "unique_runtime_material_count": len(material_paths),
    }
    self.ready_frames = 0
    self.set_phase("settle_variant")


def request_capture_sweep_r78(self):
    self.selected["absorption_sweep"] = []
    self.selected["sweep_camera_contract"] = "same PIE, seeded coast, pawn transform and exposure; runtime material parameter only"
    apply_variant_r78(self, 0)


def request_variant_capture_r78(self):
    variant = R78_VARIANTS[self.r78_variant_index]
    path = ns["CAPTURE_DIR"] / ("R78_absorption_{}_seeded_desert_coast_lit.png".format(variant["label"]))
    require(not path.exists(), "R78 capture no-clobber failed: " + str(path))
    camera = unreal.GameplayStatics.get_player_camera_manager(self.world, 0)
    record = dict(self.r78_variant_runtime)
    record.update({
        "capture_player_location": vec(self.pawn.get_actor_location()),
        "capture_camera_location": vec(camera.get_actor_location()) if camera else None,
        "capture_camera_rotation": str(camera.get_actor_rotation()) if camera else None,
        "capture_path": str(path),
    })
    self.r78_pending_capture = record
    self.selected["capture_path"] = str(path)
    require(unreal.RedPPGFoliageDiagnostics.request_viewport_screenshot(str(path)), "R78 viewport screenshot rejected")
    self.capture_requested = base_ns["time"].monotonic()
    self.set_phase("wait_capture")


def complete_capture_sweep_r78(self):
    record = self.r78_pending_capture
    path = Path(record["capture_path"])
    require(path.is_file() and path.stat().st_size > 0, "R78 capture missing")
    record["capture_bytes"] = path.stat().st_size
    record["capture_sha256"] = sha256(path)
    self.selected["absorption_sweep"].append(record)
    next_index = self.r78_variant_index + 1
    if next_index < len(R78_VARIANTS):
        apply_variant_r78(self, next_index)
        return
    self.records.append(self.selected)
    self.begin_next_target()


old_tick_r78 = Audit.tick


def tick_sweep_r78(self, delta):
    if self.phase != "settle_variant":
        old_tick_r78(self, delta)
        return
    try:
        self.frames += 1
        require(base_ns["time"].monotonic() - self.started < 1200.0, "R78 overall timeout")
        require(base_ns["time"].monotonic() - self.phase_started < 300.0, "R78 variant timeout")
        self.pin_orientation()
        if self.generation_ready():
            self.ready_frames += 1
            if self.ready_frames >= R78_VARIANT_SETTLE_FRAMES:
                request_variant_capture_r78(self)
        else:
            self.ready_frames = 0
    except Exception as error:
        self.fail(error)


def publish_sweep_r78(self):
    require(not self.level.is_in_play_in_editor() and self.editor.get_game_world() is None, "PIE still active")
    require(dirty_packages() == {"content": [], "maps": []}, "R78 audit dirtied packages")
    for path, expected_hash in expected.items():
        require(sha256(path) == expected_hash, "R78 post-run drift: " + str(path))
    require(len(self.records) == 1, "R78 coast record missing")
    record = self.records[0]
    sweep = record.get("absorption_sweep", [])
    require(len(sweep) == len(R78_VARIANTS), "R78 absorption sweep incomplete")
    require(len({item["capture_sha256"] for item in sweep}) == len(sweep), "R78 captures are byte-identical")
    require(record["native_water_component_count"] > 0, "R78 native water components missing")
    require(record["native_water_visible_main_pass_count"] > 0, "R78 native water not in main pass")
    ancestry = [
        path
        for item in record["native_water_component_preview"]
        for path in item["material_ancestry"]
    ]
    require(TARGET_MI in ancestry and TARGET_PARENT in ancestry, "R78 runtime material ancestry drift")
    self.report.update({
        "status": "PASS_R78_TRANSIENT_ABSORPTION_SWEEP_FRESH_RELOAD_LIT",
        "completed_utc": base_ns["now"](),
        "records": self.records,
        "map_sha256_after": sha256(HOME_FILE),
        "profile_sha256_after": sha256(PROFILE_FILE),
        "target_parent_sha256_after": sha256(TARGET_PARENT_FILE),
        "target_mi_sha256_after": sha256(TARGET_MI_FILE),
        "dirty_packages_after": dirty_packages(),
        "provider_gate_after": base_ns["provider_gate"](),
        "claim_limit": "Three matched Lit D3D12 transient absorption samples at one exact seeded PPG Desert coast. This does not prove final water acceptance, water gameplay, packaging, replication, multiplayer or player acceptance.",
    })
    base_ns["write_json_exclusive"](base_ns["RESULT"], self.report)
    unreal.log_warning("REDMMO_R78_ABSORPTION_SWEEP_PASS " + str([item["capture_path"] for item in sweep]))
    if self.handle is not None:
        unreal.unregister_slate_post_tick_callback(self.handle)
        self.handle = None
    unreal.SystemLibrary.execute_console_command(self.editor.get_editor_world(), "QUIT_EDITOR")


Audit.start = start_r78
Audit.request_capture = request_capture_sweep_r78
Audit.complete_capture = complete_capture_sweep_r78
Audit.publish = publish_sweep_r78
Audit.tick = tick_sweep_r78
'''

if text.count(assignment) != 1:
    raise RuntimeError("R78 verifier assignment contract drift")
text = text.replace(assignment, injection)

exec(compile(text, str(SOURCE), "exec"), {"__name__": "__main__", "__file__": str(SOURCE)})
