import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

HUD_H = ROOT / "Source/RedMMO/RedHUD.h"
HUD_CPP = ROOT / "Source/RedMMO/RedHUD.cpp"
PAUSE_H = ROOT / "Source/RedMMO/RedPauseMenuWidget.h"
PAUSE_CPP = ROOT / "Source/RedMMO/RedPauseMenuWidget.cpp"
PLAYER_CPP = ROOT / "Source/RedMMO/RedPlayerCharacter.cpp"
UI_CONTROL_TEST = ROOT / "Source/RedMMO/Tests/RedUIControlBindingTests.cpp"

WIDGET_H = ROOT / "Plugins/RedHUD/Source/RedHUDRuntime/Public/RedHUDWidget.h"
WIDGET_CPP = ROOT / "Plugins/RedHUD/Source/RedHUDRuntime/Private/RedHUDWidget.cpp"
TYPES_H = ROOT / "Plugins/RedHUD/Source/RedHUDRuntime/Public/RedHUDTypes.h"

LAYOUT_TYPES_H = (
    ROOT
    / "Plugins/VibeMMOUIKit/Source/VibeMMOUIKit/Public/Data/VibeMMOHUDLayoutTypes.h"
)
LAYOUT_SUBSYSTEM_H = (
    ROOT
    / "Plugins/VibeMMOUIKit/Source/VibeMMOUIKit/Public/Persistence/VibeMMOHUDLayoutSubsystem.h"
)
LAYOUT_SUBSYSTEM_CPP = (
    ROOT
    / "Plugins/VibeMMOUIKit/Source/VibeMMOUIKit/Private/Persistence/VibeMMOHUDLayoutSubsystem.cpp"
)

DEFECT = ROOT / "ProjectKnowledge/defects/DEF-0004-pixel-exact-hud-static-composite.yaml"
ART_ROOT = ROOT / "Content/UI/RedHUD/Textures"
EXACT_ART_ROOT = ART_ROOT / "ExactLayoutSprites"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="strict")


def function_body(source: str, signature: str) -> str:
    start = source.index(signature)
    opening = source.index("{", start)
    depth = 0
    for index in range(opening, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[start : index + 1]
    raise AssertionError(f"unterminated function: {signature}")


class Def0004PixelHUDCurrentContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.hud_h = read(HUD_H)
        cls.hud_cpp = read(HUD_CPP)
        cls.pause_h = read(PAUSE_H)
        cls.pause_cpp = read(PAUSE_CPP)
        cls.player_cpp = read(PLAYER_CPP)
        cls.ui_control_test = read(UI_CONTROL_TEST)
        cls.widget_h = read(WIDGET_H)
        cls.widget_cpp = read(WIDGET_CPP)
        cls.types_h = read(TYPES_H)
        cls.layout_types_h = read(LAYOUT_TYPES_H)
        cls.layout_subsystem_h = read(LAYOUT_SUBSYSTEM_H)
        cls.layout_subsystem_cpp = read(LAYOUT_SUBSYSTEM_CPP)
        cls.defect = read(DEFECT)

    def test_replacement_live_mode_is_now_the_current_default(self):
        begin_play = function_body(self.hud_cpp, "void ARedHUD::BeginPlay")
        initialized = function_body(
            self.widget_cpp, "void URedHUDWidget::NativeOnInitialized"
        )
        self.assertIn("PixelExactHUDWidget->SetLiveDataMode(true);", begin_play)
        self.assertNotIn("SetLiveDataMode(false);", begin_play)
        self.assertIn("SetLiveDataMode(true);", initialized)

    def test_current_gameplay_feeds_vitals_weapon_heat_and_compass(self):
        update_status = function_body(
            self.player_cpp, "void ARedPlayerCharacter::UpdateHUDStatus"
        )
        for token in (
            "ReplacementHUD->UpdateReplacementHUDVitals(",
            "ReplacementHUD->UpdateReplacementHUDWeaponState(",
            "ReplacementHUD->UpdateReplacementHUDCompass(HeadingYaw);",
        ):
            self.assertIn(token, self.player_cpp)
        self.assertIn("GetWeaponHeatForSlot(Slot)", update_status)
        self.assertIn("IsWeaponSlotOverheated(Slot)", update_status)
        self.assertIn("PixelExactHUDWidget->SetPlayerVitals(State);", self.hud_cpp)
        self.assertIn("PixelExactHUDWidget->SetWeaponState(WeaponIndex, State);", self.hud_cpp)
        self.assertIn("PixelExactHUDWidget->SetCompassHeadingDegrees(HeadingDegrees);", self.hud_cpp)

    def test_enemy_ability_and_surface_minimap_feeds_exist_without_unowned_domains(self):
        for token in (
            "void ApplySnapshot(const FRedHUDSnapshot& Snapshot);",
            "void SetEnemyState(const FRedHUDEnemyState& State);",
            "void SetQuestState(const FRedHUDQuestState& State);",
            "void SetConsumableCount(int32 SlotIndex, int32 Count);",
            "void SetAbilityState(int32 AbilityIndex, const FRedHUDAbilityState& State);",
        ):
            self.assertIn(token, self.widget_h)

        current_gameplay_bridge = self.hud_cpp + self.pause_cpp + self.player_cpp
        self.assertIn("PixelExactHUDWidget->SetEnemyState(EnemyState);", self.hud_cpp)
        self.assertIn(
            "PixelExactHUDWidget->SetAbilityState(AbilityIndex, State);",
            self.hud_cpp,
        )
        for missing_call in (
            "->ApplySnapshot(",
            "->SetQuestState(",
            "->SetConsumableCount(",
        ):
            self.assertNotIn(missing_call, current_gameplay_bridge)

        self.assertNotIn("SetParty", self.widget_h)
        self.assertNotIn("FRedHUDParty", self.types_h)
        self.assertIn("SetMinimapPresentation(", self.widget_h)
        self.assertIn("UpdateReplacementHUDMinimap(", current_gameplay_bridge)
        self.assertNotIn("SetMinimapBlips", self.widget_h)
        self.assertNotIn("FRedHUDMinimapContact", self.types_h)

    def test_replacement_exposes_per_element_layout_and_save_apis(self):
        for token in (
            "bool NudgeHUDElement(",
            "bool SetHUDElementScale(",
            "bool SetHUDElementOpacity(",
            "bool SetHUDElementHidden(",
            "bool SetHUDElementLocked(",
            "bool ResetHUDElement(",
            "bool ResetAllHUDElements();",
            "bool SaveHUDLayout();",
        ):
            self.assertIn(token, self.widget_h)

        self.assertIn(
            "LocalPlayer->GetSubsystem<UVibeMMOHUDLayoutSubsystem>()",
            self.widget_cpp,
        )
        self.assertIn("Sanitized.Sanitize();", self.widget_cpp)
        self.assertIn("GetHUDElementLayout(Element).NearlyEquals(Sanitized)", self.widget_cpp)
        self.assertIn(
            "HUDLayoutSubsystem->SetElementLayout(Element, Sanitized)",
            self.widget_cpp,
        )
        self.assertIn("HUDLayoutSubsystem->SaveLayoutNow()", self.widget_cpp)
        self.assertIn("SaveGame", self.layout_types_h)
        self.assertIn("bool SaveLayoutNow();", self.layout_subsystem_h)
        self.assertIn("CurrentSaveGame->SaveGameToSlotForLocalPlayer()", self.layout_subsystem_cpp)

    def test_visible_pause_customizer_routes_to_the_replacement_hud(self):
        self.assertIn("class URedHUDWidget;", self.pause_h)
        self.assertIn("URedHUDWidget* FindActiveReplacementHUD() const;", self.pause_h)
        self.assertIn("GetPixelExactHUDWidget() const", self.hud_h)
        finder = function_body(
            self.pause_cpp,
            "URedHUDWidget* URedPauseMenuWidget::FindActiveReplacementHUD() const",
        )
        self.assertIn("OwnerHUD->GetPixelExactHUDWidget()", finder)
        self.assertNotIn("Character->GetActiveHUDWidget()", finder)
        self.assertNotIn("UVibeMMOHUDWidget", self.pause_h + self.pause_cpp)
        self.assertIn('#include "RedHUDWidget.h"', self.pause_cpp)

    def test_replacement_layout_scope_has_explicit_unmapped_groups(self):
        resolver = function_body(
            self.widget_cpp, "TArray<UWidget*> URedHUDWidget::ResolveHUDElementWidgets"
        )
        self.assertIn("Reticle = 3", self.layout_types_h)
        self.assertNotIn("case EVibeMMOHUDElement::Reticle:", resolver)
        self.assertNotIn("Quest", self.layout_types_h)
        self.assertIn("case EVibeMMOHUDElement::PartyPanel:", resolver)
        self.assertNotIn("PartyLiveWidgets", self.widget_h + self.widget_cpp)
        utility_case = resolver.split("case EVibeMMOHUDElement::UtilityBar:", 1)[1]
        utility_case = utility_case.split("default:", 1)[0]
        self.assertNotIn("ConsumableLiveWidgets", utility_case)

    def test_replacement_painted_surface_has_no_direct_control_handlers(self):
        replacement_surface = self.widget_h + self.widget_cpp
        for interactive_token in (
            "UButton",
            "OnClicked",
            "NativeOnMouseButtonDown",
            "NativeOnKeyDown",
            "FReply",
        ):
            self.assertNotIn(interactive_token, replacement_surface)
        self.assertIn("ESlateVisibility::SelfHitTestInvisible", self.widget_cpp)
        self.assertIn("ESlateVisibility::HitTestInvisible", self.widget_cpp)

    def test_existing_control_test_and_supplied_art_do_not_close_defect(self):
        self.assertIn("UVibeMMOHUDWidget* HUD = NewObject<UVibeMMOHUDWidget>()", self.ui_control_test)
        self.assertNotIn("URedHUDWidget", self.ui_control_test)

        art_assets = sorted(ART_ROOT.rglob("*.uasset"))
        exact_assets = sorted(EXACT_ART_ROOT.glob("*.uasset"))
        self.assertEqual(len(art_assets), 56)
        self.assertEqual(len(exact_assets), 14)
        for required_name in (
            "T_REDHUD_FullComposite_Exact.uasset",
            "T_REDHUD_PlayerStatus_Exact.uasset",
            "T_REDHUD_AbilityCluster_Gamepad_Exact.uasset",
            "T_REDHUD_QuestPanel_Exact.uasset",
            "T_REDHUD_PartyList_Exact.uasset",
            "T_REDHUD_Minimap_Exact.uasset",
        ):
            self.assertTrue((EXACT_ART_ROOT / required_name).is_file(), required_name)

        self.assertIn("status: open", self.defect)
        self.assertNotIn("status: closed", self.defect)


if __name__ == "__main__":
    unittest.main()
