"""Static inventory for the residual legacy HUD scene-capture lifecycle."""

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PLAYER_CPP = ROOT / "Source/RedMMO/RedPlayerCharacter.cpp"
PLAYER_H = ROOT / "Source/RedMMO/RedPlayerCharacter.h"
RED_HUD_CPP = ROOT / "Source/RedMMO/RedHUD.cpp"
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


class Def0004LegacyHUDCaptureResidualInventoryContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.player_cpp = read(PLAYER_CPP)
        cls.player_h = read(PLAYER_H)
        cls.red_hud_cpp = read(RED_HUD_CPP)
        cls.vibe_cpp = read(VIBE_CPP)

    def test_two_persistent_timer_driven_captures_are_the_only_declared_owners(self):
        constructor = braced_body(
            self.player_cpp, r"ARedPlayerCharacter::ARedPlayerCharacter\s*\("
        )
        self.assertEqual(constructor.count("bCaptureEveryFrame = false;"), 2)
        self.assertEqual(constructor.count("bCaptureOnMovement = false;"), 2)
        self.assertEqual(
            constructor.count("bAlwaysPersistRenderingState = true;"), 2
        )
        self.assertIn("FTimerHandle HudCaptureTimer;", self.player_h)
        self.assertIn("bool bHudCapturePortraitTurn = false;", self.player_h)

    def test_render_target_allocation_prewarm_and_minimum_rgba8_footprint_are_pinned(self):
        create = braced_body(
            self.player_cpp, r"void\s+ARedPlayerCharacter::TryCreateLocalHUD\s*\("
        )
        self.assertEqual(
            create.count(
                "RenderTargetFormat = ETextureRenderTargetFormat::RTF_RGBA8;"
            ),
            2,
        )
        for token in (
            "PortraitRT->InitAutoFormat(256, 320);",
            "MinimapRT->InitAutoFormat(512, 512);",
            "PortraitCapture->TextureTarget = PortraitRT;",
            "MinimapCapture->TextureTarget = MinimapRT;",
            "Hud->SetPortraitResource(PortraitRT);",
            "Hud->SetMinimapResource(MinimapRT);",
        ):
            self.assertIn(token, create)
        self.assertEqual(create.count("UpdateResourceImmediate(true);"), 2)
        self.assertEqual(
            create.count("bAlwaysPersistRenderingState = true;"), 2
        )
        self.assertEqual(create.count("CaptureScene();"), 2)

        rgba8_bytes = ((256 * 320) + (512 * 512)) * 4
        self.assertEqual(rgba8_bytes, 1_376_256)
        self.assertEqual(rgba8_bytes / (1024 * 1024), 1.3125)

    def test_timer_has_one_start_one_teardown_and_no_pause_or_resume_contract(self):
        create = braced_body(
            self.player_cpp, r"void\s+ARedPlayerCharacter::TryCreateLocalHUD\s*\("
        )
        destroy = braced_body(
            self.player_cpp, r"void\s+ARedPlayerCharacter::DestroyLocalHUD\s*\("
        )
        self.assertIn(
            "&ARedPlayerCharacter::RefreshHudCaptures, 0.15f, true", create
        )
        self.assertEqual(
            len(re.findall(r"SetTimer\s*\(\s*HudCaptureTimer", self.player_cpp)), 1
        )
        self.assertEqual(self.player_cpp.count("ClearTimer(HudCaptureTimer)"), 1)
        self.assertIn("ClearTimer(HudCaptureTimer)", destroy)
        for forbidden in ("PauseTimer(HudCaptureTimer)", "UnPauseTimer(HudCaptureTimer)"):
            self.assertNotIn(forbidden, self.player_cpp)

    def test_creation_and_destruction_span_multiple_async_lifecycle_entry_points(self):
        for signature in (
            r"void\s+ARedPlayerCharacter::BeginPlay\s*\(",
            r"void\s+ARedPlayerCharacter::PawnClientRestart\s*\(",
            r"void\s+ARedPlayerCharacter::PossessedBy\s*\(",
        ):
            self.assertIn("TryCreateLocalHUD();", braced_body(self.player_cpp, signature))
        end_play = braced_body(
            self.player_cpp, r"void\s+ARedPlayerCharacter::EndPlay\s*\("
        )
        self.assertIn("DestroyLocalHUD();", end_play)

    def test_visibility_is_coowned_by_player_hud_and_legacy_widget_lifecycles(self):
        create = braced_body(
            self.player_cpp, r"void\s+ARedPlayerCharacter::TryCreateLocalHUD\s*\("
        )
        toggle = braced_body(
            self.player_cpp, r"void\s+ARedPlayerCharacter::ToggleAbilityLoadout\s*\("
        )
        close = braced_body(
            self.player_cpp, r"void\s+ARedPlayerCharacter::CloseAbilityLoadout\s*\("
        )
        red_begin = braced_body(self.red_hud_cpp, r"void\s+ARedHUD::BeginPlay\s*\(")
        red_register = braced_body(
            self.red_hud_cpp, r"void\s+ARedHUD::RegisterLegacyCombatHUD\s*\("
        )
        red_draw = braced_body(self.red_hud_cpp, r"void\s+ARedHUD::DrawHUD\s*\(")
        red_reconcile = braced_body(
            self.red_hud_cpp, r"void\s+ARedHUD::ReconcileCombatHUDLayers\s*\("
        )
        vibe_constructor = braced_body(
            self.vibe_cpp, r"UVibeMMOHUDWidget::UVibeMMOHUDWidget\s*\("
        )
        vibe_overlay = braced_body(
            self.vibe_cpp,
            r"void\s+UVibeMMOHUDWidget::SetAbilityLoadoutOverlayVisible\s*\(",
        )

        self.assertIn("Hud->SetVisibility(ESlateVisibility::Collapsed);", create)
        self.assertIn("RegisterLegacyCombatHUD(Character, LegacyHUD);", red_begin)
        self.assertIn(
            "LegacyHUD->SetVisibility(ESlateVisibility::Collapsed);", red_register
        )
        self.assertIn("ReconcileCombatHUDLayers();", red_draw)
        self.assertIn("RegisterLegacyCombatHUD(Character, LegacyHUD);", red_reconcile)
        self.assertIn("ESlateVisibility::HitTestInvisible", vibe_constructor)
        self.assertIn("ESlateVisibility::SelfHitTestInvisible", vibe_overlay)
        self.assertIn("ESlateVisibility::HitTestInvisible", vibe_overlay)
        self.assertIn(
            "ActiveHUDWidget->SetVisibility(ESlateVisibility::Visible);", toggle
        )
        self.assertIn("PixelHUD && PixelHUD->HasPixelExactHUD()", close)
        self.assertIn(
            "ActiveHUDWidget->SetVisibility(ESlateVisibility::Collapsed);", close
        )

    def test_recurring_capture_has_a_replacement_surface_consumer_gate(self):
        refresh = braced_body(
            self.player_cpp, r"void\s+ARedPlayerCharacter::RefreshHudCaptures\s*\("
        )
        destroy = braced_body(
            self.player_cpp, r"void\s+ARedPlayerCharacter::DestroyLocalHUD\s*\("
        )
        for token in (
            "!IsValid(ActiveHUDWidget)",
            "!ActiveHUDWidget->IsInViewport()",
            "ESlateVisibility::Collapsed",
            "ESlateVisibility::Hidden",
            "bHudCapturePortraitTurn = !bHudCapturePortraitTurn;",
            "ReplacementHUD->IsReplacementHUDMinimapActive(this)",
            "!bLegacyHUDPainted && !bReplacementSurfaceMinimapPainted",
        ):
            self.assertIn(token, refresh)
        self.assertEqual(refresh.count("CaptureScene();"), 3)
        for absent_mode_contract in (
            "bHUDSpaceMinimapRequested",
            "bUseSpaceMinimap",
            "EVibeMMOMinimapMode",
        ):
            self.assertNotIn(absent_mode_contract, refresh)
        for absent_lifetime_change in (
            "SetTimer",
            "ClearTimer",
            "PauseTimer",
            "UnPauseTimer",
            "TextureTarget = nullptr",
            "PortraitRT = nullptr",
            "MinimapRT = nullptr",
        ):
            self.assertNotIn(absent_lifetime_change, refresh)

        clear_timer = destroy.index("ClearTimer(HudCaptureTimer)")
        self.assertLess(
            clear_timer, destroy.index("PortraitCapture->TextureTarget = nullptr;")
        )
        self.assertLess(
            clear_timer, destroy.index("MinimapCapture->TextureTarget = nullptr;")
        )
        self.assertIn("PortraitRT = nullptr;", destroy)
        self.assertIn("MinimapRT = nullptr;", destroy)

    def test_surface_render_target_is_shared_with_bounded_replacement_presenter(self):
        self.assertRegex(
            self.player_h,
            r"UPROPERTY\(Transient\)\s+UTextureRenderTarget2D\* PortraitRT;",
        )
        self.assertRegex(
            self.player_h,
            r"UPROPERTY\(Transient\)\s+UTextureRenderTarget2D\* MinimapRT;",
        )
        self.assertEqual(self.player_cpp.count("Hud->SetPortraitResource(PortraitRT);"), 1)
        self.assertEqual(self.player_cpp.count("Hud->SetMinimapResource(MinimapRT);"), 1)
        self.assertNotIn("SetPortraitResource", self.red_hud_cpp)
        self.assertIn("UpdateReplacementHUDMinimap", self.red_hud_cpp)
        self.assertIn("ClearReplacementHUDMinimap", self.red_hud_cpp)
        self.assertIn("SetMinimapPresentation", self.red_hud_cpp)

        portrait_consumer = braced_body(
            self.vibe_cpp, r"void\s+UVibeMMOHUDWidget::SetPortraitResource\s*\("
        )
        minimap_consumer = braced_body(
            self.vibe_cpp, r"void\s+UVibeMMOHUDWidget::SetMinimapResource\s*\("
        )
        self.assertIn("ApplyBrushResource(PortraitImage, PortraitResource", portrait_consumer)
        self.assertIn("ApplyBrushResource(MinimapImage, MinimapResource", minimap_consumer)


if __name__ == "__main__":
    unittest.main()
