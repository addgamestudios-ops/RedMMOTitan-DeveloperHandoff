import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WIDGET_HEADER = ROOT / "Plugins/RedHUD/Source/RedHUDRuntime/Public/RedHUDWidget.h"
WIDGET_CPP = ROOT / "Plugins/RedHUD/Source/RedHUDRuntime/Private/RedHUDWidget.cpp"
LAYOUT_CPP = ROOT / "Plugins/RedHUD/Source/RedHUDRuntime/Private/RedHUDLayout.cpp"
HUD_HEADER = ROOT / "Source/RedMMO/RedHUD.h"
HUD_CPP = ROOT / "Source/RedMMO/RedHUD.cpp"
CHARACTER_CPP = ROOT / "Source/RedMMO/RedPlayerCharacter.cpp"


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


def rects_from_array(source: str, name: str):
    match = re.search(
        rf"const\s+FRedHUDRect\s+{re.escape(name)}\[2\]\s*=\s*\{{(.*?)\}};",
        source,
        re.DOTALL,
    )
    if not match:
        raise AssertionError(f"missing rectangle array: {name}")
    rects = [
        tuple(map(int, values))
        for values in re.findall(
            r"FRedHUDRect\(\s*(-?\d+)\s*,\s*(-?\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*(-?\d+)\s*\)",
            match.group(1),
        )
    ]
    if len(rects) != 2:
        raise AssertionError(f"expected two rectangles in {name}, found {len(rects)}")
    return rects


def layout_rects(source: str):
    return {
        name: tuple(map(int, values))
        for name, *values in re.findall(
            r'\{\s*TEXT\("([^"]+)"\)\s*,\s*FRedHUDRect\(\s*(-?\d+)\s*,\s*(-?\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*(-?\d+)\s*\)',
            source,
        )
    }


def contains(outer, inner) -> bool:
    ox, oy, ow, oh, _ = outer
    ix, iy, iw, ih, _ = inner
    return ox <= ix and oy <= iy and ox + ow >= ix + iw and oy + oh >= iy + ih


def overlaps(left, right) -> bool:
    lx, ly, lw, lh, _ = left
    rx, ry, rw, rh, _ = right
    return not (
        lx + lw <= rx
        or rx + rw <= lx
        or ly + lh <= ry
        or ry + rh <= ly
    )


class Def0006RedHUDRuntimeContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.widget_header = read(WIDGET_HEADER)
        cls.widget_cpp = read(WIDGET_CPP)
        cls.layout_cpp = read(LAYOUT_CPP)
        cls.hud_header = read(HUD_HEADER)
        cls.hud_cpp = read(HUD_CPP)
        cls.character_cpp = read(CHARACTER_CPP)

    def test_compass_is_live_layout_owned_and_uses_gameplay_heading(self):
        self.assertIn("void SetCompassHeadingDegrees(float HeadingDegrees);", self.widget_header)
        self.assertNotIn("NativeTick", self.widget_header)
        self.assertNotIn("GetControlRotation().Yaw", self.widget_cpp)
        self.assertIn("&CompassLiveWidgets", self.widget_cpp)
        self.assertIn("AddArt(TEXT(\"TopProgress\")); AddGroup(CompassLiveWidgets);", self.widget_cpp)
        self.assertIn("SetLiveGroupVisibility(CompassLiveWidgets, true);", self.widget_cpp)

        heading = function_body(
            self.widget_cpp, "void URedHUDWidget::SetCompassHeadingDegrees"
        )
        for token in ("FRotator::ClampAxis", "Directions[]", "CompassText->SetText"):
            self.assertIn(token, heading)

        self.assertIn("FVector TangentNorth", self.character_cpp)
        self.assertIn("FVector TangentEast = FVector::CrossProduct(", self.character_cpp)
        self.assertIn("HUDPlayerController = ActiveHUDWidget->GetOwningPlayer();", self.character_cpp)
        self.assertIn("ReplacementHUD->UpdateReplacementHUDCompass(HeadingYaw);", self.character_cpp)
        self.assertIn("PixelExactHUDWidget->SetCompassHeadingDegrees(HeadingDegrees);", self.hud_cpp)

    def test_live_vitals_and_two_weapon_heat_slots_reach_replacement_hud(self):
        for declaration in (
            "UpdateReplacementHUDVitals(",
            "UpdateReplacementHUDWeaponState(",
            "UpdateReplacementHUDCompass(",
        ):
            self.assertIn(declaration, self.hud_header)

        status = function_body(
            self.character_cpp, "void ARedPlayerCharacter::UpdateHUDStatus()"
        )
        self.assertIn("HUDPlayerController = ActiveHUDWidget->GetOwningPlayer();", status)
        self.assertIn("Shield, MaxShield, Health, MaxHealth, Fuel, MaxFuel", status)
        self.assertIn("for (int32 Slot = 0; Slot < 2; ++Slot)", status)
        self.assertIn("GetWeaponHeatForSlot(Slot)", status)
        self.assertIn("IsWeaponSlotOverheated(Slot)", status)
        self.assertIn("MaxWeaponHeat * WeaponHeatResumeFraction", status)
        self.assertIn("(Heat - ResumeHeat) / WeaponHeatCoolRate", status)
        self.assertIn("Slot == CurrentWeaponSlot", status)
        self.assertIn("ReplacementHUD->UpdateReplacementHUDWeaponState(", status)

        self.assertIn("PixelExactHUDWidget->SetPlayerVitals(State);", self.hud_cpp)
        self.assertIn("PixelExactHUDWidget->SetWeaponState(WeaponIndex, State);", self.hud_cpp)

    def test_opaque_weapon_masks_replace_baked_ammo_with_heat_status(self):
        masks = rects_from_array(self.widget_cpp, "TelemetryMasks")
        fills = rects_from_array(self.widget_cpp, "HeatRects")
        texts = rects_from_array(self.widget_cpp, "HeatTextRects")
        layout = layout_rects(self.layout_cpp)

        for index, card_name in enumerate(("WeaponSlot01", "WeaponSlot02")):
            with self.subTest(card=card_name):
                self.assertTrue(contains(layout[card_name], masks[index]))
                self.assertTrue(contains(masks[index], fills[index]))
                self.assertTrue(contains(masks[index], texts[index]))
                self.assertLess(masks[index][4], fills[index][4])
                self.assertLess(fills[index][4], texts[index][4])

        self.assertIn("OpaqueLiveMaskColor(0.005f, 0.010f, 0.015f, 1.0f)", self.widget_cpp)
        self.assertEqual(self.widget_cpp.count("WeaponAmmoMask%d"), 1)
        self.assertNotIn("State.Magazine", self.widget_cpp)
        self.assertNotIn("State.Reserve", self.widget_cpp)
        for text in ("HEAT %03d%%", "COOL %.1f", "OVERHEAT"):
            self.assertIn(text, self.widget_cpp)
        self.assertIn("CachedWeaponStates.SetNum(2);", self.widget_cpp)
        self.assertIn("CachedWeaponStates[WeaponIndex] = State;", self.widget_cpp)

    def test_player_depletion_masks_preserve_authored_status_art(self):
        layout = layout_rects(self.layout_cpp)
        player_status = layout["PlayerStatus"]
        depletion_matches = re.findall(
            r'AddDepletionMask\(\s*TEXT\("(Player(?:Shield|Health|Energy)DepletionMask)"\),\s*FRedHUDRect\(\s*(-?\d+)\s*,\s*(-?\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*(-?\d+)\s*\)',
            self.widget_cpp,
        )
        text_mask_matches = re.findall(
            r'AddSolidRect\(TEXT\("(PlayerHealthTextMask)"\),\s*FRedHUDRect\(\s*(-?\d+)\s*,\s*(-?\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*(-?\d+)\s*\)',
            self.widget_cpp,
        )
        self.assertEqual(len(depletion_matches), 3)
        self.assertEqual(len(text_mask_matches), 1)
        for name, *values in depletion_matches + text_mask_matches:
            with self.subTest(mask=name):
                self.assertTrue(contains(player_status, tuple(map(int, values))))

        build_artwork = function_body(
            self.widget_cpp, "void URedHUDWidget::BuildArtwork()"
        )
        self.assertIn("T_REDHUD_PlayerStatus.T_REDHUD_PlayerStatus", build_artwork)

        build_live = function_body(
            self.widget_cpp, "void URedHUDWidget::BuildLiveOverlay()"
        )
        for legacy_flat_fill in (
            "PlayerShieldFill = AddFill(",
            "PlayerHealthFill = AddFill(",
            "PlayerEnergyFill = AddFill(",
            "PlayerShieldColor",
            "PlayerHealthColor",
            "PlayerEnergyColor",
        ):
            self.assertNotIn(legacy_flat_fill, self.widget_cpp)

        add_depletion = function_body(
            self.widget_cpp,
            "URedHUDWidget::FMutableDepletionMask URedHUDWidget::AddDepletionMask",
        )
        self.assertIn("SetAlignment(FVector2D(1.0f, 0.0f))", add_depletion)
        self.assertIn(
            "SetPosition(FVector2D(Rect.X + Rect.W, Rect.Y))",
            add_depletion,
        )
        self.assertIn("SetDepletionPercent(Result, 1.0f);", add_depletion)

        set_depletion = function_body(
            self.widget_cpp, "void URedHUDWidget::SetDepletionPercent"
        )
        self.assertIn("FMath::Clamp(Percent, 0.0f, 1.0f)", set_depletion)
        self.assertIn("Fill.MaxWidth * (1.0f - Clamped)", set_depletion)

        set_vitals = function_body(
            self.widget_cpp, "void URedHUDWidget::SetPlayerVitals"
        )
        for mask_name in (
            "PlayerShieldDepletionMask",
            "PlayerHealthDepletionMask",
            "PlayerEnergyDepletionMask",
        ):
            self.assertIn(f"SetDepletionPercent(\n        {mask_name}", set_vitals)

    def test_weapon_utility_and_ability_baselines_do_not_overlap(self):
        layout = layout_rects(self.layout_cpp)
        weapons = [layout[name] for name in ("WeaponSlot01", "WeaponSlot02")]
        utilities = [layout[name] for name in ("UtilityE", "UtilityF", "UtilityG", "UtilityM")]
        abilities = [
            layout[name]
            for name in (
                "AbilityUltimate",
                "AbilityLeft",
                "AbilityRight",
                "AbilityBottom",
                "AbilityKeyboard",
            )
        ]
        for weapon in weapons:
            for other in utilities + abilities:
                self.assertFalse(overlaps(weapon, other))

    def test_legacy_masks_and_canvas_sight_follow_pixel_hud_visibility(self):
        self.assertIn("TWeakObjectPtr<class UUserWidget> CachedLegacyHUDWidget;", self.hud_header)
        self.assertIn("void RegisterLegacyCombatHUD(", self.hud_header)
        self.assertIn("void UnregisterLegacyCombatHUD(", self.hud_header)
        self.assertIn("PixelHUD->RegisterLegacyCombatHUD(this, Hud);", self.character_cpp)
        self.assertIn(
            "PixelHUD->UnregisterLegacyCombatHUD(this, ActiveHUDWidget);",
            self.character_cpp,
        )

        reconcile = function_body(
            self.hud_cpp, "void ARedHUD::ReconcileCombatHUDLayers()"
        )
        self.assertIn("CachedLegacyHUDWidget.Get()", reconcile)
        self.assertIn("LegacyHUD->SetVisibility(ESlateVisibility::Collapsed);", reconcile)

        draw = function_body(self.hud_cpp, "void ARedHUD::DrawHUD()")
        guard = draw.index("PixelExactHUDWidget->GetVisibility() == ESlateVisibility::Collapsed")
        trace = draw.index("Trace only against pawns")
        self.assertLess(guard, trace)
        for token in ("TargetAlpha", "FLinearColor::LerpUsingHSV", "DrawLine(", "DrawRect(SightColor"):
            self.assertIn(token, draw)


if __name__ == "__main__":
    unittest.main()
