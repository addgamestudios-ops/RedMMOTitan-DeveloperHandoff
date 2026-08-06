import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

HUD_H = ROOT / "Source/RedMMO/RedHUD.h"
HUD_CPP = ROOT / "Source/RedMMO/RedHUD.cpp"
PAUSE_H = ROOT / "Source/RedMMO/RedPauseMenuWidget.h"
PAUSE_CPP = ROOT / "Source/RedMMO/RedPauseMenuWidget.cpp"
PLAYER_H = ROOT / "Source/RedMMO/RedPlayerCharacter.h"
PLAYER_CPP = ROOT / "Source/RedMMO/RedPlayerCharacter.cpp"


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


class Def0004ReplacementHUDCustomizerRouteContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.hud_h = read(HUD_H)
        cls.hud_cpp = read(HUD_CPP)
        cls.pause_h = read(PAUSE_H)
        cls.pause_cpp = read(PAUSE_CPP)
        cls.player_h = read(PLAYER_H)
        cls.player_cpp = read(PLAYER_CPP)

    def test_red_hud_exposes_the_active_replacement_widget(self):
        self.assertIn(
            "URedHUDWidget* GetPixelExactHUDWidget() const",
            self.hud_h,
        )
        accessor = function_body(
            self.hud_cpp, "URedHUDWidget* ARedHUD::GetPixelExactHUDWidget() const"
        )
        self.assertIn("IsValid(PixelExactHUDWidget)", accessor)
        self.assertIn("PixelExactHUDWidget.Get()", accessor)
        finder = function_body(
            self.pause_cpp,
            "URedHUDWidget* URedPauseMenuWidget::FindActiveReplacementHUD() const",
        )
        self.assertIn("OwnerHUD->GetPixelExactHUDWidget()", finder)
        self.assertNotIn("GetActiveHUDWidget", finder)
        self.assertNotIn("UVibeMMOHUDWidget", self.pause_h + self.pause_cpp)

    def test_customizer_offers_only_mapped_replacement_groups(self):
        selection = function_body(
            self.pause_cpp,
            "static const TArray<EVibeMMOHUDElement>& GetReplacementHUDElements()",
        )
        expected = (
            "StatusPanel",
            "Compass",
            "Minimap",
            "AbilityBar",
            "WeaponStack",
            "PartyPanel",
            "EnemyPanel",
            "UtilityBar",
        )
        for element in expected:
            self.assertIn(f"EVibeMMOHUDElement::{element}", selection)
        self.assertEqual(selection.count("EVibeMMOHUDElement::"), len(expected))
        self.assertNotIn("EVibeMMOHUDElement::Reticle", selection)
        previous = function_body(
            self.pause_cpp, "void URedPauseMenuWidget::HandleHUDPreviousElement"
        )
        following = function_body(
            self.pause_cpp, "void URedPauseMenuWidget::HandleHUDNextElement"
        )
        self.assertIn("GetReplacementHUDElements()", previous)
        self.assertIn("GetReplacementHUDElements()", following)

    def test_preview_snapshots_the_shared_local_player_profile(self):
        finder = function_body(
            self.pause_cpp,
            "UVibeMMOHUDLayoutSubsystem* URedPauseMenuWidget::FindHUDLayoutSubsystem() const",
        )
        begin = function_body(
            self.pause_cpp, "bool URedPauseMenuWidget::BeginHUDCustomizationPreview"
        )
        self.assertIn("GetOwningLocalPlayer()", finder)
        self.assertIn("GetSubsystem<UVibeMMOHUDLayoutSubsystem>()", finder)
        self.assertIn("FindActiveReplacementHUD()", begin)
        self.assertIn("LayoutSubsystem->IsLayoutLoaded()", begin)
        self.assertIn("return false;", begin)
        self.assertIn("return true;", begin)
        self.assertIn(
            "HUDCustomizationOriginalProfile = LayoutSubsystem->GetLayoutProfile();",
            begin,
        )

    def test_every_visible_mutation_targets_the_replacement_widget(self):
        expected_calls = {
            "HandleHUDMoveLeft": "HUD->NudgeHUDElement(",
            "HandleHUDMoveRight": "HUD->NudgeHUDElement(",
            "HandleHUDMoveUp": "HUD->NudgeHUDElement(",
            "HandleHUDMoveDown": "HUD->NudgeHUDElement(",
            "HandleHUDScaleDown": "HUD->SetHUDElementScale(",
            "HandleHUDScaleUp": "HUD->SetHUDElementScale(",
            "HandleHUDOpacityDown": "HUD->SetHUDElementOpacity(",
            "HandleHUDOpacityUp": "HUD->SetHUDElementOpacity(",
            "HandleHUDToggleVisibility": "HUD->SetHUDElementHidden(",
            "HandleHUDToggleLock": "HUD->SetHUDElementLocked(",
            "HandleHUDResetElement": "HUD->ResetHUDElement(",
            "HandleHUDResetAll": "HUD->ResetAllHUDElements(",
        }
        for function_name, call in expected_calls.items():
            body = function_body(
                self.pause_cpp, f"void URedPauseMenuWidget::{function_name}"
            )
            self.assertIn("FindActiveReplacementHUD()", body, function_name)
            self.assertIn(call, body, function_name)
            self.assertNotIn("UVibeMMOHUDWidget", body, function_name)

    def test_cancel_restores_and_apply_saves_the_profile(self):
        cancel = function_body(
            self.pause_cpp, "bool URedPauseMenuWidget::CancelHUDCustomizationPreview"
        )
        apply = function_body(
            self.pause_cpp, "void URedPauseMenuWidget::HandleHUDApply"
        )
        self.assertNotIn("FindActiveReplacementHUD()", cancel)
        self.assertIn(
            "LayoutSubsystem->SetLayoutProfile(HUDCustomizationOriginalProfile)",
            cancel,
        )
        self.assertIn("LayoutSubsystem->SaveLayoutNow()", cancel)
        self.assertIn("return false;", cancel)
        self.assertNotIn("FindActiveReplacementHUD()", apply)
        self.assertIn("bHUDCustomizationPreviewActive", apply)
        self.assertIn("LayoutSubsystem->SaveLayoutNow()", apply)
        self.assertIn("LayoutSubsystem->GetLayoutProfile()", apply)

    def test_legacy_hud_remains_for_data_and_loadout_only(self):
        self.assertIn('#include "Widgets/VibeMMOHUDWidget.h"', self.hud_cpp)
        self.assertIn("CachedLegacyHUDWidget", self.hud_h + self.hud_cpp)
        self.assertIn("UVibeMMOHUDWidget", self.player_h + self.player_cpp)
        self.assertIn("GetActiveHUDWidget", self.player_h + self.player_cpp)
        self.assertNotIn('#include "Widgets/VibeMMOHUDWidget.h"', self.pause_cpp)


if __name__ == "__main__":
    unittest.main()
