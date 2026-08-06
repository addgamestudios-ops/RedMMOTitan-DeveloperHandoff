import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

REDHUD_ROOT = ROOT / "Plugins/RedHUD"
REDHUD_SOURCE = REDHUD_ROOT / "Source"
REDHUD_UPLUGIN = REDHUD_ROOT / "RedHUD.uplugin"
TYPES_H = REDHUD_SOURCE / "RedHUDRuntime/Public/RedHUDTypes.h"
WIDGET_H = REDHUD_SOURCE / "RedHUDRuntime/Public/RedHUDWidget.h"
WIDGET_CPP = REDHUD_SOURCE / "RedHUDRuntime/Private/RedHUDWidget.cpp"
BLUEPRINT_LIBRARY_CPP = (
    REDHUD_SOURCE / "RedHUDRuntime/Private/RedHUDBlueprintLibrary.cpp"
)
INTEGRATION_SNIPPET = REDHUD_ROOT / "INTEGRATION_SNIPPET.cpp"

REDMMO_SOURCE = ROOT / "Source/RedMMO"
HUD_CPP = REDMMO_SOURCE / "RedHUD.cpp"
PLAYER_CPP = REDMMO_SOURCE / "RedPlayerCharacter.cpp"
VIBE_SOURCE = ROOT / "Plugins/VibeMMOUIKit/Source"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="strict")


def braced_body(source: str, signature_pattern: str) -> str:
    match = re.search(signature_pattern, source, re.MULTILINE)
    if not match:
        raise AssertionError(f"signature not found: {signature_pattern}")
    start = match.start()
    opening = source.index("{", match.end())
    depth = 0
    for index in range(opening, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[start : index + 1]
    raise AssertionError(f"unterminated body: {signature_pattern}")


def compiled_source_paths(root: Path) -> list[Path]:
    return sorted(
        path
        for path in root.rglob("*")
        if path.is_file() and path.suffix.lower() in {".h", ".cpp"}
    )


def compiled_source_text(root: Path) -> str:
    return "\n".join(read(path) for path in compiled_source_paths(root))


def call_sites(root: Path, symbol: str) -> dict[str, int]:
    pattern = re.compile(rf"\b{re.escape(symbol)}\s*\(")
    sites = {}
    for path in compiled_source_paths(root):
        count = len(pattern.findall(read(path)))
        if count:
            sites[path.relative_to(root).as_posix()] = count
    return sites


def literal_sites(root: Path, literal: str) -> dict[str, int]:
    sites = {}
    for path in compiled_source_paths(root):
        count = read(path).count(literal)
        if count:
            sites[path.relative_to(root).as_posix()] = count
    return sites


class Def0004ReplacementHUDSnapshotInventoryContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.types_h = read(TYPES_H)
        cls.widget_h = read(WIDGET_H)
        cls.widget_cpp = read(WIDGET_CPP)
        cls.library_cpp = read(BLUEPRINT_LIBRARY_CPP)
        cls.snippet = read(INTEGRATION_SNIPPET)
        cls.hud_cpp = read(HUD_CPP)
        cls.player_cpp = read(PLAYER_CPP)
        cls.redmmo_source = compiled_source_text(REDMMO_SOURCE)
        cls.vibe_source = compiled_source_text(VIBE_SOURCE)

    def test_snapshot_is_a_presentation_value_not_a_replicated_or_saved_owner(self):
        snapshot = braced_body(self.types_h, r"struct\s+FRedHUDSnapshot\b")
        for current_field in (
            "FRedHUDPlayerVitals Player;",
            "FRedHUDWeaponState Weapon1;",
            "FRedHUDWeaponState Weapon2;",
            "FRedHUDEnemyState Enemy;",
            "FRedHUDQuestState Quest;",
            "TArray<int32> ConsumableCounts",
            "TArray<FRedHUDAbilityState> Abilities;",
        ):
            self.assertIn(current_field, snapshot)
        self.assertNotIn("ReplicatedUsing", snapshot)
        self.assertNotIn("SaveGame", snapshot)

    def test_apply_snapshot_has_a_multi_domain_mutation_surface(self):
        apply_snapshot = braced_body(
            self.widget_cpp, r"void\s+URedHUDWidget::ApplySnapshot\s*\("
        )
        for direct_fanout in (
            "SetPlayerVitals(Snapshot.Player);",
            "SetWeaponState(0, Snapshot.Weapon1);",
            "SetWeaponState(1, Snapshot.Weapon2);",
            "SetEnemyState(Snapshot.Enemy);",
            "SetQuestState(Snapshot.Quest);",
        ):
            self.assertIn(direct_fanout, apply_snapshot)
        self.assertEqual(apply_snapshot.count("SetConsumableCount("), 1)
        self.assertEqual(apply_snapshot.count("SetAbilityState("), 1)
        self.assertRegex(
            self.widget_h,
            r"UFUNCTION\s*\(\s*BlueprintCallable[^)]*\)\s*\r?\n\s*void\s+ApplySnapshot",
        )

    def test_no_compiled_gameplay_or_vibe_snapshot_producer_exists(self):
        self.assertEqual(
            call_sites(REDHUD_SOURCE, "ApplySnapshot"),
            {
                "RedHUDRuntime/Private/RedHUDWidget.cpp": 1,
                "RedHUDRuntime/Public/RedHUDWidget.h": 1,
            },
        )
        self.assertEqual(call_sites(REDMMO_SOURCE, "ApplySnapshot"), {})
        self.assertEqual(call_sites(VIBE_SOURCE, "ApplySnapshot"), {})
        self.assertEqual(
            literal_sites(REDHUD_SOURCE, "FRedHUDSnapshot"),
            {
                "RedHUDRuntime/Private/RedHUDWidget.cpp": 1,
                "RedHUDRuntime/Public/RedHUDTypes.h": 1,
                "RedHUDRuntime/Public/RedHUDWidget.h": 1,
            },
        )
        self.assertEqual(literal_sites(REDMMO_SOURCE, "FRedHUDSnapshot"), {})
        self.assertEqual(literal_sites(VIBE_SOURCE, "FRedHUDSnapshot"), {})

    def test_widget_creation_and_initialization_do_not_publish_a_snapshot(self):
        initialized = braced_body(
            self.widget_cpp, r"void\s+URedHUDWidget::NativeOnInitialized\s*\("
        )
        begin_play = braced_body(self.hud_cpp, r"void\s+ARedHUD::BeginPlay\s*\(")
        create_widget = braced_body(
            self.library_cpp,
            r"URedHUDWidget\s*\*\s*URedHUDBlueprintLibrary::CreateAndAddRedHUD\s*\(",
        )
        for lifecycle_body in (initialized, begin_play, create_widget):
            self.assertNotIn("ApplySnapshot(", lifecycle_body)
            self.assertNotIn("FRedHUDSnapshot", lifecycle_body)
        self.assertIn("SetLiveDataMode(true);", initialized)
        self.assertIn("PixelExactHUDWidget->SetLiveDataMode(true);", begin_play)

    def test_current_trustworthy_presentation_paths_remain_granular(self):
        for bridge in (
            "UpdateReplacementHUDVitals(",
            "UpdateReplacementHUDWeaponState(",
            "UpdateReplacementHUDAbilityState(",
            "UpdateReplacementHUDCompass(",
        ):
            self.assertIn(bridge, self.player_cpp)
            self.assertIn(bridge, self.hud_cpp)
        for setter in (
            "SetPlayerVitals(State);",
            "SetWeaponState(WeaponIndex, State);",
            "SetAbilityState(AbilityIndex, State);",
            "SetCompassHeadingDegrees(HeadingDegrees);",
        ):
            self.assertIn(setter, self.hud_cpp)

        draw_hud = braced_body(self.hud_cpp, r"void\s+ARedHUD::DrawHUD\s*\(")
        for fail_closed_enemy_token in (
            "FRedHUDEnemyState EnemyState;",
            "EnemyState.bVisible = false;",
            "IsValid(TargetCharacter)",
            "TargetCharacter->bIsEnemy",
            "!TargetCharacter->IsDowned()",
            "PixelExactHUDWidget->SetEnemyState(EnemyState);",
        ):
            self.assertIn(fail_closed_enemy_token, draw_hud)
        self.assertNotIn("ApplySnapshot(", self.hud_cpp + self.player_cpp)

    def test_noncompiled_integration_example_is_placeholder_not_a_producer(self):
        self.assertNotIn(REDHUD_SOURCE, INTEGRATION_SNIPPET.parents)
        plugin_descriptor = json.loads(read(REDHUD_UPLUGIN))
        self.assertEqual(
            [(module["Name"], module["Type"]) for module in plugin_descriptor["Modules"]],
            [("RedHUDRuntime", "Runtime")],
        )
        for example_token in (
            "Example: add to your existing PlayerController class.",
            "AYourPlayerController::RefreshHUD()",
            "FRedHUDSnapshot Snapshot;",
            "CurrentHealth",
            "PrimaryMagazine",
            "PrimaryReserve",
            "LockedTarget",
            "ActiveQuestTitle",
            "Consumable1",
            "SetLiveDataMode(false);",
        ):
            self.assertIn(example_token, self.snippet)
        for placeholder in (
            "AYourPlayerController",
            "CurrentHealth",
            "PrimaryMagazine",
            "LockedTarget",
            "ActiveQuestTitle",
            "Consumable1",
        ):
            self.assertNotIn(placeholder, self.redmmo_source)
        for sample_literal in (
            "BROODHUNTER",
            "Locate the Ancient Waygate",
            "Enter the Sunken Archive",
        ):
            self.assertNotIn(sample_literal, self.redmmo_source)

    def test_bounded_content_names_expose_no_snapshot_state_aggregator(self):
        filename_pattern = re.compile(
            r"(?:hud[_ -]?snapshot|ui[_ -]?snapshot|hud[_ -]?state|"
            r"ui[_ -]?state|player[_ -]?state|snapshot[_ -]?producer)",
            re.IGNORECASE,
        )
        matching_paths = {
            path.relative_to(ROOT).as_posix()
            for content_root in (ROOT / "Content/RedMMO", ROOT / "Content/UI")
            if content_root.is_dir()
            for path in content_root.rglob("*")
            if path.is_file() and filename_pattern.search(path.as_posix())
        }
        self.assertEqual(matching_paths, set())


if __name__ == "__main__":
    unittest.main()
