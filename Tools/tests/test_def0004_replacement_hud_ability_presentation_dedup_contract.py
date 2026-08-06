import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PLAYER_CPP = ROOT / "Source/RedMMO/RedPlayerCharacter.cpp"
WIDGET_H = ROOT / "Plugins/RedHUD/Source/RedHUDRuntime/Public/RedHUDWidget.h"
WIDGET_CPP = ROOT / "Plugins/RedHUD/Source/RedHUDRuntime/Private/RedHUDWidget.cpp"


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


class Def0004AbilityPresentationDedupContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.player_cpp = read(PLAYER_CPP)
        cls.widget_h = read(WIDGET_H)
        cls.widget_cpp = read(WIDGET_CPP)
        cls.tick = function_body(cls.player_cpp, "void ARedPlayerCharacter::Tick")
        cls.update_status = function_body(
            cls.player_cpp, "void ARedPlayerCharacter::UpdateHUDStatus"
        )
        cls.update_ability = function_body(
            cls.player_cpp, "void ARedPlayerCharacter::UpdateAbilityHUD"
        )
        cls.set_ability = function_body(
            cls.widget_cpp, "void URedHUDWidget::SetAbilityState"
        )
        cls.set_live_mode = function_body(
            cls.widget_cpp, "void URedHUDWidget::SetLiveDataMode"
        )
        cls.set_element_tint = function_body(
            cls.widget_cpp, "void URedHUDWidget::SetElementTint"
        )

    def test_inventory_proves_two_replacement_ability_calls_per_local_tick(self):
        self.assertEqual(self.tick.count("UpdateHUDStatus();"), 1)
        self.assertEqual(
            self.update_status.count("UpdateAbilityHUD(ReplacementHUD);"), 1
        )
        self.assertIn("for (int32 Slot = 0; Slot < 2; ++Slot)", self.update_ability)
        self.assertIn(
            "ReplacementHUD->UpdateReplacementHUDAbilityState(", self.update_ability
        )

    def test_cache_is_presentation_only_and_bounded_to_q_and_e(self):
        for token in (
            "struct FAbilityPresentationCache",
            "TArray<FAbilityPresentationCache> AbilityPresentationCache;",
            "const bool bKeyboardQOrE = AbilityIndex >= 1 && AbilityIndex <= 2;",
            "FAbilityPresentationCache* Presentation = bKeyboardQOrE",
        ):
            self.assertIn(token, self.widget_h + self.set_ability)

    def test_exact_authoritative_state_is_retained_before_suppression(self):
        cache = self.set_ability.index("CachedAbilityStates[AbilityIndex] = State;")
        unchanged = self.set_ability.index("if (bPresentationUnchanged)")
        early_return = self.set_ability.index("return;", unchanged)
        first_mutation = self.set_ability.index("SetAbilityArtTint(", unchanged)
        self.assertLess(cache, unchanged)
        self.assertLess(unchanged, early_return)
        self.assertLess(early_return, first_mutation)

    def test_key_covers_every_current_qe_presentation_driver(self):
        for token in (
            "Presentation->InputScheme == InputScheme",
            "Presentation->bLiveMode == bLiveDataMode",
            "Presentation->bAbilityBarHidden == bAbilityBarHidden",
            "Presentation->ArtTintMode == ArtTintMode",
            "Presentation->StatusMode == StatusMode",
            "Presentation->StatusText == StatusText",
        ):
            self.assertIn(token, self.set_ability)

    def test_one_decimal_label_is_the_cooldown_change_boundary(self):
        status_text = self.set_ability.index("StatusText = FString::Printf(")
        precision = self.set_ability.index('TEXT("%.1f")', status_text)
        comparison = self.set_ability.index(
            "Presentation->StatusText == StatusText", precision
        )
        self.assertLess(status_text, precision)
        self.assertLess(precision, comparison)
        self.assertIn(
            "AbilityCooldownText[AbilityIndex]->SetText(FText::FromString(StatusText));",
            self.set_ability,
        )

    def test_live_mode_replay_always_invalidates_before_repainting(self):
        invalidation = self.set_live_mode.index(
            "InvalidateAbilityPresentationCache();"
        )
        replay = self.set_live_mode.index("SetAbilityState(")
        self.assertLess(invalidation, replay)

    def test_cache_is_valid_only_after_all_required_targets_apply(self):
        self.assertIn("Presentation->bInitialized = false;", self.set_ability)
        valid = self.set_ability.index(
            "Presentation->bInitialized = bHasRequiredTargets;"
        )
        for mutation in (
            "SetAbilityArtTint(",
            "StatusSlot->SetPosition(",
            "SetVisibility(",
            "SetText(",
        ):
            self.assertLess(self.set_ability.index(mutation), valid)

    def test_manual_qe_tints_preserve_next_tick_semantic_restoration(self):
        for token in (
            'ElementName == FName(TEXT("AbilityLeft"))',
            "InvalidateAbilityPresentationCache(1);",
            'ElementName == FName(TEXT("AbilityRight"))',
            "InvalidateAbilityPresentationCache(2);",
        ):
            self.assertIn(token, self.set_element_tint)

    def test_optimization_does_not_touch_input_or_gameplay_authority(self):
        presentation_only = self.set_ability + self.set_live_mode
        for forbidden in (
            "ActivateAbilityAuthoritative(",
            "ServerActivateAbility(",
            "SetPredictedAbilityCooldown(",
            "ForceNetUpdate(",
            "HasAuthority(",
            "DOREPLIFETIME(",
        ):
            self.assertNotIn(forbidden, presentation_only)


if __name__ == "__main__":
    unittest.main()
