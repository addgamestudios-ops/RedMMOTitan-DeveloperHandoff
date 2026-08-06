import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
HUD_H = ROOT / "Source/RedMMO/RedHUD.h"
HUD_CPP = ROOT / "Source/RedMMO/RedHUD.cpp"
PLAYER_H = ROOT / "Source/RedMMO/RedPlayerCharacter.h"
PLAYER_CPP = ROOT / "Source/RedMMO/RedPlayerCharacter.cpp"
TYPES_H = ROOT / "Plugins/RedHUD/Source/RedHUDRuntime/Public/RedHUDTypes.h"
WIDGET_CPP = (
    ROOT / "Plugins/RedHUD/Source/RedHUDRuntime/Private/RedHUDWidget.cpp"
)


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


class Def0004ReplacementHUDAbilityFeedContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.hud_h = read(HUD_H)
        cls.hud_cpp = read(HUD_CPP)
        cls.player_h = read(PLAYER_H)
        cls.player_cpp = read(PLAYER_CPP)
        cls.types_h = read(TYPES_H)
        cls.widget_cpp = read(WIDGET_CPP)
        cls.bridge = function_body(
            cls.hud_cpp, "void ARedHUD::UpdateReplacementHUDAbilityState"
        )
        cls.update_ability = function_body(
            cls.player_cpp, "void ARedPlayerCharacter::UpdateAbilityHUD"
        )
        cls.update_status = function_body(
            cls.player_cpp, "void ARedPlayerCharacter::UpdateHUDStatus"
        )
        cls.close_loadout = function_body(
            cls.player_cpp, "void ARedPlayerCharacter::CloseAbilityLoadout"
        )
        cls.set_ability = function_body(
            cls.widget_cpp, "void URedHUDWidget::SetAbilityState"
        )
        cls.set_input_scheme = function_body(
            cls.widget_cpp, "void URedHUDWidget::SetInputScheme"
        )
        cls.apply_input_scheme = function_body(
            cls.widget_cpp, "void URedHUDWidget::ApplyInputSchemeVisibility"
        )
        cls.set_ability_tint = function_body(
            cls.widget_cpp, "void URedHUDWidget::SetAbilityArtTint"
        )

    def test_primitive_bridge_builds_a_bounded_replacement_state(self):
        self.assertIn("void UpdateReplacementHUDAbilityState(", self.hud_h)
        for token in (
            "FRedHUDAbilityState State;",
            "State.CooldownDuration = FMath::Max(0.f, CooldownDuration);",
            "CooldownRemaining, 0.f, State.CooldownDuration);",
            "State.ChargePercent = 1.f;",
            "State.bSelected = false;",
            "State.bDisabled = bDisabled;",
            "PixelExactHUDWidget->SetAbilityState(AbilityIndex, State);",
        ):
            self.assertIn(token, self.bridge)

    def test_ready_requires_zero_cooldown_and_an_enabled_ability(self):
        self.assertIn(
            "State.bReady = !bDisabled && State.CooldownRemaining <= KINDA_SMALL_NUMBER;",
            self.bridge,
        )

    def test_q_and_e_map_to_replacement_left_and_right_indices(self):
        self.assertIn(
            "// 0 = Ultimate, 1 = Left/Q, 2 = Right/E, 3 = Bottom/R.",
            self.types_h,
        )
        self.assertIn("for (int32 Slot = 0; Slot < 2; ++Slot)", self.update_ability)
        self.assertIn("Slot + 1, Remaining, Duration, bAbilityDisabled", self.update_ability)

    def test_existing_server_clock_and_replicated_cooldowns_remain_the_producer(self):
        for token in (
            "const float Now = GetAbilityClockSeconds();",
            "GetAbilityCooldownEnd(Ability) - Now",
            "GetAbilityCooldownDuration(Ability)",
            "GameState->GetServerWorldTimeSeconds()",
            "DOREPLIFETIME(ARedPlayerCharacter, AbilitySlotQ);",
            "DOREPLIFETIME(ARedPlayerCharacter, AbilitySlotE);",
            "DOREPLIFETIME(ARedPlayerCharacter, GrappleCooldownEndServerTime);",
            "DOREPLIFETIME(ARedPlayerCharacter, SlamCooldownEndServerTime);",
        ):
            self.assertIn(token, self.player_cpp)

    def test_legacy_feed_is_preserved_and_no_longer_required(self):
        self.assertIn("if (ActiveHUDWidget)", self.update_ability)
        self.assertIn(
            "ActiveHUDWidget->SetAbilityCooldownState(Slot, Remaining, Duration);",
            self.update_ability,
        )
        self.assertIn("if (!ActiveHUDWidget && !ReplacementHUD)", self.update_ability)
        self.assertNotIn("if (!ActiveHUDWidget)\n\t{\n\t\treturn;", self.update_ability)

    def test_tick_forwards_abilities_even_without_the_legacy_widget(self):
        self.assertIn("UpdateAbilityHUD(ReplacementHUD);", self.update_status)
        call = self.update_status.index("UpdateAbilityHUD(ReplacementHUD);")
        self.assertNotIn("if (ActiveHUDWidget)", self.update_status[call - 40 : call])

    def test_closing_loadout_refreshes_enabled_state_before_re_show(self):
        clear_open = self.close_loadout.index("bAbilityLoadoutOpen = false;")
        refresh = self.close_loadout.index("UpdateAbilityHUD(PixelHUD);")
        show = self.close_loadout.index("PixelHUD->SetPixelExactHUDVisible(true);")
        self.assertLess(clear_open, refresh)
        self.assertLess(refresh, show)

    def test_downed_and_loadout_states_disable_but_do_not_invent_selection(self):
        self.assertIn(
            "const bool bAbilityDisabled = bDowned || bAbilityLoadoutOpen;",
            self.update_ability,
        )
        self.assertNotIn("bSelected = true", self.bridge + self.update_ability)

    def test_feed_does_not_mutate_ability_gameplay_or_authority(self):
        presentation_only = self.bridge + self.update_ability
        for forbidden in (
            "ActivateAbilityAuthoritative(",
            "ServerActivateAbility(",
            "SetPredictedAbilityCooldown(",
            "ForceNetUpdate(",
            "HasAuthority(",
            "DOREPLIFETIME(",
        ):
            self.assertNotIn(forbidden, presentation_only)

    def test_default_keyboard_has_a_bounded_q_and_e_status_consumer(self):
        begin_play = function_body(self.hud_cpp, "void ARedHUD::BeginPlay")
        self.assertIn(
            "PixelExactHUDWidget->SetInputScheme(ERedHUDInputScheme::KeyboardMouse);",
            begin_play,
        )
        for token in (
            "const bool bKeyboard = InputScheme == ERedHUDInputScheme::KeyboardMouse;",
            "const bool bKeyboardQOrE = AbilityIndex >= 1 && AbilityIndex <= 2;",
            "KeyboardAbilityStatusRects[AbilityIndex - 1]",
            "bKeyboard &&",
            "bKeyboardQOrE &&",
        ):
            self.assertIn(token, self.set_ability)

    def test_keyboard_status_reflows_to_the_supplied_q_and_e_cards(self):
        for token in (
            "FRedHUDRect(3418, 1643, 170, 147, 90)",
            "FRedHUDRect(3613, 1640, 185, 150, 90)",
            "StatusSlot->SetPosition(StatusRect.Position());",
            "StatusSlot->SetSize(StatusRect.Size());",
            "StatusSlot->SetZOrder(StatusRect.Z);",
        ):
            self.assertIn(token, self.widget_cpp)

    def test_keyboard_feedback_distinguishes_disabled_cooldown_and_unknown(self):
        for token in (
            "State.bDisabled ||",
            "State.CooldownRemaining > KINDA_SMALL_NUMBER ||",
            "!State.bReady",
            'FText::FromString(TEXT("X"))',
            'TEXT("%.1f")',
            'FText::FromString(TEXT("..."))',
        ):
            self.assertIn(token, self.set_ability)
        self.assertIn(
            "bShowStatus ? ESlateVisibility::HitTestInvisible : ESlateVisibility::Collapsed",
            self.set_ability,
        )

    def test_status_ticks_cannot_resurrect_a_hidden_ability_bar(self):
        self.assertIn(
            "GetHUDElementLayout(EVibeMMOHUDElement::AbilityBar).bHidden",
            self.set_ability,
        )
        self.assertGreaterEqual(self.set_ability.count("!bAbilityBarHidden"), 2)

    def test_scheme_switch_cannot_resurrect_hidden_ability_art(self):
        for token in (
            "GetHUDElementLayout(EVibeMMOHUDElement::AbilityBar).bHidden",
            "const bool bShowGamepad = bGamepad && !bAbilityBarHidden;",
            "const bool bShowKeyboard = !bGamepad && !bAbilityBarHidden;",
            "bShowGamepad ? ESlateVisibility::HitTestInvisible",
            "bShowKeyboard ? ESlateVisibility::HitTestInvisible",
        ):
            self.assertIn(token, self.apply_input_scheme)

    def test_gamepad_feedback_and_cached_scheme_replay_are_preserved(self):
        self.assertIn("!bKeyboard &&", self.set_ability)
        self.assertIn(
            "GamepadAbilityArt[AbilityIndex]->SetColorAndOpacity(Tint);",
            self.set_ability_tint,
        )
        self.assertIn("ApplyInputSchemeVisibility();", self.set_input_scheme)
        self.assertIn(
            "SetAbilityState(Index, CachedAbilityStates[Index]);",
            self.set_input_scheme,
        )


if __name__ == "__main__":
    unittest.main()
