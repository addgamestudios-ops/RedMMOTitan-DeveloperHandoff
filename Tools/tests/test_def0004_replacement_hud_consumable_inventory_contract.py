import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

REDHUD_ROOT = ROOT / "Plugins/RedHUD"
REDHUD_SOURCE = REDHUD_ROOT / "Source"
WIDGET_H = REDHUD_SOURCE / "RedHUDRuntime/Public/RedHUDWidget.h"
WIDGET_CPP = REDHUD_SOURCE / "RedHUDRuntime/Private/RedHUDWidget.cpp"
LAYOUT_CPP = REDHUD_SOURCE / "RedHUDRuntime/Private/RedHUDLayout.cpp"
TYPES_H = REDHUD_SOURCE / "RedHUDRuntime/Public/RedHUDTypes.h"
INTEGRATION_SNIPPET = REDHUD_ROOT / "INTEGRATION_SNIPPET.cpp"

REDMMO_SOURCE = ROOT / "Source/RedMMO"
HUD_H = REDMMO_SOURCE / "RedHUD.h"
HUD_CPP = REDMMO_SOURCE / "RedHUD.cpp"
PLAYER_H = REDMMO_SOURCE / "RedPlayerCharacter.h"
PLAYER_CPP = REDMMO_SOURCE / "RedPlayerCharacter.cpp"
PAUSE_CPP = REDMMO_SOURCE / "RedPauseMenuWidget.cpp"
RESOURCE_H = REDMMO_SOURCE / "RedResourcePickup.h"
RESOURCE_CPP = REDMMO_SOURCE / "RedResourcePickup.cpp"
ORBITAL_H = REDMMO_SOURCE / "RedOrbitalMiningSite.h"
ORBITAL_CPP = REDMMO_SOURCE / "RedOrbitalMiningSite.cpp"
ASTEROID_H = REDMMO_SOURCE / "RedMineableAsteroid.h"
ASTEROID_CPP = REDMMO_SOURCE / "RedMineableAsteroid.cpp"

VIBE_SOURCE = ROOT / "Plugins/VibeMMOUIKit/Source/VibeMMOUIKit"
VIBE_SCREEN_H = VIBE_SOURCE / "Public/Widgets/VibeMMOScreenWidgets.h"
VIBE_SCREEN_CPP = VIBE_SOURCE / "Private/Widgets/VibeMMOScreenWidgets.cpp"
VIBE_LAYOUT_H = VIBE_SOURCE / "Public/Data/VibeMMOHUDLayoutTypes.h"
VIBE_INVENTORY_TEST = (
    VIBE_SOURCE / "Private/Tests/VibeMMOInventoryInteractionTests.cpp"
)


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


def symbol_sites(root: Path, symbol: str) -> dict[str, int]:
    pattern = re.compile(rf"\b{re.escape(symbol)}\s*\(")
    sites = {}
    for path in compiled_source_paths(root):
        count = len(pattern.findall(read(path)))
        if count:
            sites[path.relative_to(root).as_posix()] = count
    return sites


def literal_sites(root: Path, literal: str) -> list[str]:
    return [
        path.relative_to(root).as_posix()
        for path in compiled_source_paths(root)
        if literal in read(path)
    ]


class Def0004ReplacementHUDConsumableInventoryContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.widget_h = read(WIDGET_H)
        cls.widget_cpp = read(WIDGET_CPP)
        cls.layout_cpp = read(LAYOUT_CPP)
        cls.types_h = read(TYPES_H)
        cls.snippet = read(INTEGRATION_SNIPPET)
        cls.hud_source = read(HUD_H) + read(HUD_CPP)
        cls.player_h = read(PLAYER_H)
        cls.player_cpp = read(PLAYER_CPP)
        cls.pause_cpp = read(PAUSE_CPP)
        cls.resource_h = read(RESOURCE_H)
        cls.resource_cpp = read(RESOURCE_CPP)
        cls.orbital_source = read(ORBITAL_H) + read(ORBITAL_CPP)
        cls.asteroid_source = read(ASTEROID_H) + read(ASTEROID_CPP)
        cls.redmmo_source = compiled_source_text(REDMMO_SOURCE)
        cls.redmmo_backend_source = "\n".join(
            read(path)
            for path in compiled_source_paths(REDMMO_SOURCE)
            if path.name not in {"RedPauseMenuWidget.h", "RedPauseMenuWidget.cpp"}
        )
        cls.vibe_screen_h = read(VIBE_SCREEN_H)
        cls.vibe_screen_cpp = read(VIBE_SCREEN_CPP)
        cls.vibe_layout_h = read(VIBE_LAYOUT_H)
        cls.vibe_test = read(VIBE_INVENTORY_TEST)

    def test_replacement_consumer_is_three_counts_but_dormant(self):
        self.assertIn("TArray<int32> ConsumableCounts", self.types_h)
        self.assertIn(
            "void SetConsumableCount(int32 SlotIndex, int32 Count);",
            self.widget_h,
        )

        overlay = braced_body(
            self.widget_cpp, r"void\s+URedHUDWidget::BuildLiveOverlay\s*\("
        )
        self.assertIn("ConsumableCountText.SetNum(3);", overlay)
        self.assertRegex(
            overlay,
            r"AddSolidRect\s*\([^;]+&ConsumableLiveWidgets\s*\)",
        )
        self.assertRegex(
            overlay,
            r"ConsumableCountText\s*\[\s*Index\s*\]\s*=\s*AddText\s*\([^;]+&ConsumableLiveWidgets\s*\)",
        )

        setter = braced_body(
            self.widget_cpp, r"void\s+URedHUDWidget::SetConsumableCount\s*\("
        )
        self.assertIn("ConsumableCountText.IsValidIndex(SlotIndex)", setter)
        self.assertIn("FMath::Max(0, Count)", setter)
        self.assertNotIn("SetLiveGroupVisibility", setter)

        visibility_calls = re.findall(
            r"SetLiveGroupVisibility\s*\(\s*ConsumableLiveWidgets\s*,\s*(true|false)\s*\)",
            self.widget_cpp,
        )
        self.assertEqual(visibility_calls, ["false"])
        self.assertEqual(self.widget_cpp.count("ConsumableLiveWidgets"), 3)

    def test_consumer_has_no_consumable_art_identity_cache_or_layout_owner(self):
        artwork = braced_body(
            self.widget_cpp, r"void\s+URedHUDWidget::BuildArtwork\s*\("
        )
        for absent_art in (
            "Consumable01",
            "Consumable02",
            "Consumable03",
            "T_REDHUD_Consumable",
        ):
            self.assertNotIn(absent_art, artwork)
        for layout_only_name in ("Consumable01", "Consumable02", "Consumable03"):
            self.assertIn(layout_only_name, self.layout_cpp)

        layout_resolution = braced_body(
            self.widget_cpp,
            r"TArray\s*<\s*UWidget\s*\*\s*>\s+URedHUDWidget::ResolveHUDElementWidgets\s*\(",
        )
        for unowned_element in (
            "ConsumableLiveWidgets",
            "Consumable01",
            "Consumable02",
            "Consumable03",
        ):
            self.assertNotIn(unowned_element, layout_resolution)
        layout_enum = braced_body(
            self.vibe_layout_h, r"enum\s+class\s+EVibeMMOHUDElement\b"
        )
        self.assertNotRegex(layout_enum, r"(?i)consumable")

        consumer = self.widget_h + self.widget_cpp
        for missing_contract in (
            "CachedConsumable",
            "ConsumableItemId",
            "ConsumableItemID",
            "ConsumableSlotId",
            "ConsumableSlotID",
            "EquippedConsumable",
            "SetConsumableVisible",
        ):
            self.assertNotIn(missing_contract, consumer)

    def test_snapshot_is_the_only_compiled_redhud_count_caller(self):
        apply_snapshot = braced_body(
            self.widget_cpp, r"void\s+URedHUDWidget::ApplySnapshot\s*\("
        )
        self.assertRegex(
            apply_snapshot,
            r"Index\s*<\s*Snapshot\.ConsumableCounts\.Num\s*\(\s*\)\s*&&\s*Index\s*<\s*3",
        )
        self.assertRegex(
            apply_snapshot,
            r"SetConsumableCount\s*\(\s*Index\s*,\s*Snapshot\.ConsumableCounts\s*\[\s*Index\s*\]\s*\)",
        )
        self.assertEqual(
            symbol_sites(REDHUD_SOURCE, "SetConsumableCount"),
            {
                "RedHUDRuntime/Private/RedHUDWidget.cpp": 2,
                "RedHUDRuntime/Public/RedHUDWidget.h": 1,
            },
        )
        self.assertEqual(symbol_sites(REDMMO_SOURCE, "SetConsumableCount"), {})
        self.assertEqual(symbol_sites(REDMMO_SOURCE, "ApplySnapshot"), {})
        self.assertEqual(
            symbol_sites(REDHUD_SOURCE, "ApplySnapshot"),
            {
                "RedHUDRuntime/Private/RedHUDWidget.cpp": 1,
                "RedHUDRuntime/Public/RedHUDWidget.h": 1,
            },
        )

    def test_redmmo_has_no_consumable_stack_quickslot_or_steam_inventory_bridge(self):
        suspicious_backend_identifier = re.compile(
            r"\b(?:F|U|A|E)?(?:Red)?(?:"
            r"Consumable(?:Inventory|Stack|Slot|Item)?|"
            r"(?:Player|Replicated)Inventory|"
            r"Inventory(?:Component|Subsystem|Manager|Items?|Entr(?:y|ies)|Slots?|State)|"
            r"Item(?:Stacks?|Quantity|Count|Entr(?:y|ies))|StackCounts?|"
            r"QuickSlots?|Hotbar(?:Slots?)?|"
            r"Server(?:Use|Consume)(?:Item|Consumable)|"
            r"Use(?:Item|Consumable)|Consume(?:Item|Consumable)|"
            r"OnRep_(?:Consumable|Inventory|Item)\w*"
            r")\b",
            re.IGNORECASE,
        )
        self.assertEqual(
            suspicious_backend_identifier.findall(self.redmmo_backend_source), []
        )
        for steam_bridge_identifier in ("ISteamInventory", "SteamInventory"):
            self.assertNotIn(steam_bridge_identifier, self.redmmo_source)

        native_construct = braced_body(
            self.pause_cpp, r"void\s+URedPauseMenuWidget::NativeConstruct\s*\("
        )
        populated_variables = set(
            re.findall(r"\b(\w+)\.bIsPopulated\s*=\s*true", native_construct)
        )
        categorized_variables = {
            variable: category
            for variable, category in re.findall(
                r"\b(\w+)\.Category\s*=\s*EVibeMMOInventoryCategory::(\w+)",
                native_construct,
            )
        }
        self.assertTrue(populated_variables)
        self.assertEqual(populated_variables, set(categorized_variables))
        self.assertEqual(set(categorized_variables.values()), {"Weapons"})
        self.assertNotIn("EVibeMMOInventoryCategory::Consumables", native_construct)
        for absent_backend_field in ("Quantity", "StackCount", "UseItem", "ConsumeItem"):
            self.assertNotIn(absent_backend_field, native_construct)

    def test_vibe_inventory_is_transient_quantity_free_presentation(self):
        presentation = braced_body(
            self.vibe_screen_h,
            r"struct\s+VIBEMMOUIKIT_API\s+FVibeMMOInventoryItemPresentation\b",
        )
        for visual_field in (
            "bIsPopulated",
            "Category",
            "DisplayName",
            "Rarity",
            "Description",
            "IconResource",
            "RarityColor",
        ):
            self.assertIn(visual_field, presentation)
        for missing_backend_field in (
            "Quantity",
            "StackCount",
            "MaxStack",
            "ConsumableId",
            "ItemId",
            "ItemID",
            "EquippedSlot",
            "QuickSlot",
            "bEquipped",
            "UseItem",
            "ConsumeItem",
            "ReplicatedUsing",
        ):
            self.assertNotIn(missing_backend_field, presentation)

        inventory_widget = braced_body(
            self.vibe_screen_h,
            r"class\s+VIBEMMOUIKIT_API\s+UVibeMMOInventoryWidget\b",
        )
        self.assertRegex(
            inventory_widget,
            r"UPROPERTY\s*\(\s*Transient\s*\)\s*TArray\s*<\s*FVibeMMOInventoryItemPresentation\s*>\s*InventoryItems",
        )
        self.assertNotIn("ReplicatedUsing", inventory_widget)
        self.assertNotIn("SaveGame", inventory_widget)
        self.assertNotIn("GetLifetimeReplicatedProps", inventory_widget)
        self.assertIsNone(
            re.search(
                r"UFUNCTION\s*\([^)]*\b(?:Server|Client|NetMulticast)\b",
                inventory_widget,
            )
        )
        self.assertNotIn("Coolant Cell", self.vibe_screen_h + self.vibe_screen_cpp)
        self.assertIn('TEXT("Coolant Cell")', self.vibe_test)
        self.assertIn("#if WITH_DEV_AUTOMATION_TESTS", self.vibe_test)
        self.assertEqual(
            literal_sites(VIBE_SOURCE, "Coolant Cell"),
            ["Private/Tests/VibeMMOInventoryInteractionTests.cpp"],
        )

    def test_resources_fuel_heat_and_ore_are_not_consumable_producers(self):
        resource_enum = braced_body(
            self.resource_h, r"enum\s+class\s+ERedResourceType\b"
        )
        enum_values = re.findall(
            r"^\s*(Stone|Iron|Crystal)\s+UMETA\s*\(",
            resource_enum,
            re.MULTILINE,
        )
        self.assertEqual(enum_values, ["Stone", "Iron", "Crystal"])

        update_resources = braced_body(
            self.player_cpp,
            r"void\s+ARedPlayerCharacter::UpdateHUDResources\s*\("
        )
        self.assertRegex(
            update_resources,
            r"UpdateReplacementHUDResources\s*\(\s*ResStone\s*,\s*ResIron\s*,\s*ResCrystal\s*\)",
        )
        self.assertNotIn("ActiveHUDWidget->SetResourceTally", update_resources)
        for absent_route in ("SetConsumableCount", "ApplySnapshot", "ConsumableCounts"):
            self.assertNotIn(absent_route, update_resources)

        update_status = braced_body(
            self.player_cpp, r"void\s+ARedPlayerCharacter::UpdateHUDStatus\s*\("
        )
        self.assertIn("Fuel", update_status)
        self.assertIn("UpdateReplacementHUDVitals(", update_status)
        self.assertIn("UpdateReplacementHUDWeaponState(", update_status)
        for absent_route in ("SetConsumableCount", "ApplySnapshot", "ConsumableCounts"):
            self.assertNotIn(absent_route, update_status)

        for world_ore_source in (self.orbital_source, self.asteroid_source):
            self.assertIn("OreRemaining", world_ore_source)
            self.assertNotIn("SetConsumableCount", world_ore_source)
            self.assertNotIn("ApplySnapshot", world_ore_source)
        self.assertIn("ReplicatedUsing = OnRep_OreRemaining", self.asteroid_source)
        self.assertIn("RewardPlayer->AddResource(", self.asteroid_source)

        pickup_receipt = braced_body(
            self.resource_cpp, r"void\s+ARedResourcePickup::OnCollectOverlap\s*\("
        )
        self.assertIn("Player->AddResource(ResourceType, Amount)", pickup_receipt)
        self.assertNotIn("SetConsumableCount", pickup_receipt)

        add_resource = braced_body(
            self.player_cpp, r"void\s+ARedPlayerCharacter::AddResource\s*\("
        )
        for resource_name in ("Stone", "Iron", "Crystal"):
            self.assertIn(f"ERedResourceType::{resource_name}", add_resource)
        self.assertIn("UpdateHUDResources()", add_resource)
        self.assertNotIn("SetConsumableCount", add_resource)
        self.assertNotIn("UpdateReplacementHUDConsumable", self.hud_source)

    def test_noncompiled_example_and_bounded_content_names_are_not_producers(self):
        self.assertNotIn(REDHUD_SOURCE, INTEGRATION_SNIPPET.parents)
        for token in (
            "Example: add to your existing PlayerController class.",
        ):
            self.assertIn(token, self.snippet)
        self.assertRegex(
            self.snippet,
            r"Snapshot\.ConsumableCounts\s*=\s*\{\s*Consumable1\s*,\s*Consumable2\s*,\s*Consumable3\s*\}",
        )
        compiled_gameplay = compiled_source_text(REDHUD_SOURCE) + self.redmmo_source
        for placeholder in ("Consumable1", "Consumable2", "Consumable3"):
            self.assertNotIn(placeholder, compiled_gameplay)

        filename_pattern = re.compile(
            r"(?:consumable|inventory|stack|medkit|stim|potion|grenade|"
            r"usable|heal|medpack|healthpack|booster|coolant)",
            re.IGNORECASE,
        )
        matching_paths = {
            path.relative_to(ROOT).as_posix()
            for content_root in (ROOT / "Content/RedMMO", ROOT / "Content/UI")
            for path in content_root.rglob("*")
            if path.is_file()
            and filename_pattern.search(path.relative_to(ROOT).as_posix())
        }
        self.assertEqual(
            matching_paths,
            {
                "Content/UI/RedHUD/Textures/ExactLayoutSprites/T_REDHUD_Consumables_Exact.uasset",
                "Content/UI/RedHUD/Textures/HighResSprites/T_REDHUD_Consumables.uasset",
                "Content/UI/RedHUD/Textures/IndividualSprites/T_REDHUD_Consumable_01.uasset",
                "Content/UI/RedHUD/Textures/IndividualSprites/T_REDHUD_Consumable_02.uasset",
                "Content/UI/RedHUD/Textures/IndividualSprites/T_REDHUD_Consumable_03.uasset",
            },
        )
        self.assertTrue(all(path.suffix.lower() == ".uasset" for path in (
            ROOT / relative_path for relative_path in matching_paths
        )))
        self.assertTrue(
            all(
                relative_path.startswith("Content/UI/RedHUD/Textures/")
                for relative_path in matching_paths
            )
        )


if __name__ == "__main__":
    unittest.main()
