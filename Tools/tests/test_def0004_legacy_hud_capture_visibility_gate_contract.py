"""Static contract for the legacy HUD scene-capture visibility gate."""

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PLAYER_CPP = ROOT / "Source/RedMMO/RedPlayerCharacter.cpp"
VIBE_CPP = (
    ROOT
    / "Plugins/VibeMMOUIKit/Source/VibeMMOUIKit/Private/Widgets/VibeMMOHUDWidget.cpp"
)


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="strict")


def braced_body(source: str, signature_pattern: str) -> str:
    match = re.search(signature_pattern, source, re.MULTILINE)
    if not match:
        raise AssertionError(f"signature not found: {signature_pattern}")
    opening = source.index("{", match.end())
    depth = 0
    for index in range(opening, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[match.start() : index + 1]
    raise AssertionError(f"unterminated body: {signature_pattern}")


class Def0004LegacyHUDCaptureVisibilityGateContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.player_cpp = read(PLAYER_CPP)
        cls.vibe_cpp = read(VIBE_CPP)

    def test_recurring_capture_runs_only_for_a_painted_legacy_or_replacement_consumer(self):
        refresh = braced_body(
            self.player_cpp, r"void\s+ARedPlayerCharacter::RefreshHudCaptures\s*\("
        )
        for token in (
            "!IsValid(ActiveHUDWidget)",
            "!ActiveHUDWidget->IsInViewport()",
            "ActiveHUDWidget->GetVisibility()",
            "LegacyHUDVisibility != ESlateVisibility::Collapsed",
            "LegacyHUDVisibility != ESlateVisibility::Hidden",
            "ReplacementHUD->IsReplacementHUDMinimapActive(this)",
            "!bLegacyHUDPainted && !bReplacementSurfaceMinimapPainted",
        ):
            self.assertIn(token, refresh)

        alternation = refresh.index(
            "bHudCapturePortraitTurn = !bHudCapturePortraitTurn;"
        )
        self.assertLess(refresh.index("!IsValid(ActiveHUDWidget)"), alternation)
        self.assertLess(
            refresh.index("!bLegacyHUDPainted && !bReplacementSurfaceMinimapPainted"),
            alternation,
        )
        self.assertLess(
            refresh.index("if (!bLegacyHUDPainted)"),
            alternation,
        )
        self.assertLess(alternation, refresh.index("PortraitCapture->CaptureScene();"))
        self.assertEqual(refresh.count("CaptureScene();"), 3)

    def test_gate_uses_actual_widget_lifecycles_not_gameplay_flags(self):
        refresh = braced_body(
            self.player_cpp, r"void\s+ARedPlayerCharacter::RefreshHudCaptures\s*\("
        )
        for forbidden in (
            "bAbilityLoadoutOpen",
            "HasPixelExactHUD",
            "SetTimer",
            "ClearTimer",
        ):
            self.assertNotIn(forbidden, refresh)

        vibe_constructor = braced_body(
            self.vibe_cpp, r"UVibeMMOHUDWidget::UVibeMMOHUDWidget\s*\("
        )
        overlay = braced_body(
            self.vibe_cpp,
            r"void\s+UVibeMMOHUDWidget::SetAbilityLoadoutOverlayVisible\s*\(",
        )
        self.assertIn("ESlateVisibility::HitTestInvisible", vibe_constructor)
        self.assertIn("ESlateVisibility::SelfHitTestInvisible", overlay)
        self.assertIn("ESlateVisibility::HitTestInvisible", overlay)
        self.assertNotIn("ESlateVisibility::Visible", refresh)

    def test_visible_loadout_resumes_and_replacement_combat_hud_recollapses_legacy(self):
        toggle = braced_body(
            self.player_cpp, r"void\s+ARedPlayerCharacter::ToggleAbilityLoadout\s*\("
        )
        close = braced_body(
            self.player_cpp, r"void\s+ARedPlayerCharacter::CloseAbilityLoadout\s*\("
        )
        self.assertIn(
            "ActiveHUDWidget->SetVisibility(ESlateVisibility::Visible);", toggle
        )
        self.assertIn("PixelHUD->SetPixelExactHUDVisible(false);", toggle)
        self.assertIn("PixelHUD && PixelHUD->HasPixelExactHUD()", close)
        self.assertIn(
            "ActiveHUDWidget->SetVisibility(ESlateVisibility::Collapsed);", close
        )

    def test_render_targets_prewarm_timer_and_teardown_contracts_are_preserved(self):
        create = braced_body(
            self.player_cpp, r"void\s+ARedPlayerCharacter::TryCreateLocalHUD\s*\("
        )
        for token in (
            "PortraitCapture->TextureTarget = PortraitRT;",
            "MinimapCapture->TextureTarget = MinimapRT;",
            "PortraitCapture->CaptureScene();",
            "MinimapCapture->CaptureScene();",
            "Hud->SetPortraitResource(PortraitRT);",
            "Hud->SetMinimapResource(MinimapRT);",
            "&ARedPlayerCharacter::RefreshHudCaptures, 0.15f, true",
        ):
            self.assertIn(token, create)
        self.assertEqual(create.count("CaptureScene();"), 2)

        constructor = braced_body(
            self.player_cpp, r"ARedPlayerCharacter::ARedPlayerCharacter\s*\("
        )
        self.assertGreaterEqual(constructor.count("bCaptureEveryFrame = false;"), 2)
        self.assertGreaterEqual(constructor.count("bCaptureOnMovement = false;"), 2)

        destroy = braced_body(
            self.player_cpp, r"void\s+ARedPlayerCharacter::DestroyLocalHUD\s*\("
        )
        clear_timer = destroy.index("ClearTimer(HudCaptureTimer)")
        portrait_target = destroy.index("PortraitCapture->TextureTarget = nullptr;")
        minimap_target = destroy.index("MinimapCapture->TextureTarget = nullptr;")
        self.assertLess(clear_timer, portrait_target)
        self.assertLess(clear_timer, minimap_target)
        self.assertIn("PortraitRT = nullptr;", destroy)
        self.assertIn("MinimapRT = nullptr;", destroy)


if __name__ == "__main__":
    unittest.main()
