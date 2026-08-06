"""Static C++ and filename inventory only; Blueprint graphs are not decoded."""

import hashlib
import re
import struct
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

REDHUD_SOURCE = ROOT / "Plugins/RedHUD/Source"
WIDGET_H = REDHUD_SOURCE / "RedHUDRuntime/Public/RedHUDWidget.h"
WIDGET_CPP = REDHUD_SOURCE / "RedHUDRuntime/Private/RedHUDWidget.cpp"
LAYOUT_CPP = REDHUD_SOURCE / "RedHUDRuntime/Private/RedHUDLayout.cpp"
TYPES_H = REDHUD_SOURCE / "RedHUDRuntime/Public/RedHUDTypes.h"

REDMMO_SOURCE = ROOT / "Source/RedMMO"
PLAYER_H = REDMMO_SOURCE / "RedPlayerCharacter.h"
PLAYER_CPP = REDMMO_SOURCE / "RedPlayerCharacter.cpp"
HUD_H = REDMMO_SOURCE / "RedHUD.h"
HUD_CPP = REDMMO_SOURCE / "RedHUD.cpp"

VIBE_SOURCE = ROOT / "Plugins/VibeMMOUIKit/Source/VibeMMOUIKit"
VIBE_H = VIBE_SOURCE / "Public/Widgets/VibeMMOHUDWidget.h"
VIBE_CPP = VIBE_SOURCE / "Private/Widgets/VibeMMOHUDWidget.cpp"

MINIMAP_PNG = (
    ROOT
    / "Plugins/RedHUD/Resources/Art/HighResSprites/T_REDHUD_Minimap.png"
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


def compiled_source_paths(root: Path) -> list[Path]:
    return sorted(
        path
        for path in root.rglob("*")
        if path.is_file() and path.suffix.lower() in {".h", ".cpp"}
    )


def compiled_source_text(root: Path) -> str:
    return "\n".join(read(path) for path in compiled_source_paths(root))


class Def0004ReplacementHUDMinimapInventoryContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.widget_h = read(WIDGET_H)
        cls.widget_cpp = read(WIDGET_CPP)
        cls.layout_cpp = read(LAYOUT_CPP)
        cls.types_h = read(TYPES_H)
        cls.player_h = read(PLAYER_H)
        cls.player_cpp = read(PLAYER_CPP)
        cls.hud_h = read(HUD_H)
        cls.hud_cpp = read(HUD_CPP)
        cls.redhud_source = compiled_source_text(REDHUD_SOURCE)
        cls.vibe_h = read(VIBE_H)
        cls.vibe_cpp = read(VIBE_CPP)

    def test_supplied_baked_minimap_is_preserved_but_live_group_owns_presentation(self):
        artwork = braced_body(
            self.widget_cpp, r"void\s+URedHUDWidget::BuildArtwork\s*\("
        )
        resolution = braced_body(
            self.widget_cpp,
            r"TArray\s*<\s*UWidget\s*\*\s*>\s+URedHUDWidget::ResolveHUDElementWidgets\s*\(",
        )
        self.assertRegex(
            artwork,
            r'AddImage\s*\(\s*TEXT\("Minimap"\)\s*,\s*'
            r'TEXT\("/Game/UI/RedHUD/Textures/HighResSprites/'
            r'T_REDHUD_Minimap\.T_REDHUD_Minimap"\)',
        )
        minimap_case = resolution[
            resolution.index("case EVibeMMOHUDElement::Minimap") :
            resolution.index("case EVibeMMOHUDElement::AbilityBar")
        ]
        self.assertIn('AddArt(TEXT("Minimap"));', minimap_case)
        self.assertIn("AddGroup(MinimapLiveWidgets);", minimap_case)
        self.assertRegex(
            self.layout_cpp,
            r'\{\s*TEXT\("Minimap"\)\s*,\s*FRedHUDRect\s*\(',
        )

        png = MINIMAP_PNG.read_bytes()
        self.assertEqual(png[:8], b"\x89PNG\r\n\x1a\n")
        self.assertEqual(struct.unpack(">II", png[16:24]), (1157, 1199))
        self.assertEqual(
            hashlib.sha256(png).hexdigest().upper(),
            "1FA5A1EA4CBE02E0579216DD60FF28699186342A4D0AD26EAA83AC15F7A35A2D",
        )

    def test_baked_minimap_and_party_art_fail_closed_in_known_visibility_paths(self):
        dormant = braced_body(
            self.widget_cpp, r"bool\s+IsDormantLiveDataArtName\s*\("
        )
        for name in ("Minimap", "PartyRow01", "PartyRow02", "PartyRow03"):
            self.assertIn(name, dormant)

        live_mode = braced_body(
            self.widget_cpp, r"void\s+URedHUDWidget::SetLiveDataMode\s*\("
        )
        self.assertIn("!IsDormantLiveDataArtName(Pair.Key)", live_mode)
        self.assertIn("ESlateVisibility::Collapsed", live_mode)

        generic_visibility = braced_body(
            self.widget_cpp, r"void\s+URedHUDWidget::SetElementVisible\s*\("
        )
        self.assertIn(
            "bLiveDataMode && bVisible && !IsDormantLiveDataArtName(ElementName)",
            generic_visibility,
        )
        self.assertEqual(self.widget_cpp.count("IsDormantLiveDataArtName("), 3)

        apply_layout = braced_body(
            self.widget_cpp, r"void\s+URedHUDWidget::ApplyHUDLayout\s*\("
        )
        self.assertLess(
            apply_layout.index("SetLiveDataMode(bLiveDataMode)"),
            apply_layout.index("ApplyHUDElementLayout(Element)"),
        )

    def test_replacement_has_bounded_surface_contract_without_fabricated_contacts(self):
        replacement = self.redhud_source + self.hud_h + self.hud_cpp
        for required_identifier in (
            "ERedHUDMinimapMode",
            "SetMinimapPresentation",
            "ClearMinimapPresentation",
            "GetMinimapPresentationState",
            "MinimapLiveWidgets",
            "CachedMinimapSourceOwner",
            "CachedMinimapCelestialFrameId",
            "CachedMinimapPresentationEpoch",
            "UpdateReplacementHUDMinimap",
            "ClearReplacementHUDMinimap",
        ):
            self.assertIn(required_identifier, replacement)

        set_presentation = braced_body(
            self.widget_cpp,
            r"bool\s+URedHUDWidget::SetMinimapPresentation\s*\(",
        )
        for required_guard in (
            "PresentationEpoch <= 0",
            "PresentationEpoch < CachedMinimapPresentationEpoch",
            "CachedMinimapSourceOwner.Get() != SourceOwner",
            "CelestialFrameId.IsNone()",
            "Mode == ERedHUDMinimapMode::Surface",
        ):
            self.assertIn(required_guard, set_presentation)
        for fabricated_contact in (
            "FRedHUDMinimapContact",
            "SetMinimapBlips",
            "ContactId",
            "ObjectiveId",
            "HostileId",
        ):
            self.assertNotIn(fabricated_contact, self.redhud_source + self.hud_h + self.hud_cpp)

        snapshot = braced_body(self.types_h, r"struct\s+FRedHUDSnapshot\b")
        self.assertNotRegex(snapshot, r"(?i)\bminimap\b|\bmapcontact\b|\bradar\b")

    def test_legacy_surface_backend_is_local_and_clears_its_lifecycle(self):
        constructor = braced_body(
            self.player_cpp, r"ARedPlayerCharacter::ARedPlayerCharacter\s*\("
        )
        for token in (
            'CreateDefaultSubobject<USceneCaptureComponent2D>(TEXT("MinimapCapture"))',
            "ProjectionType = ECameraProjectionMode::Orthographic;",
            "OrthoWidth = 6000.f;",
            "bCaptureEveryFrame = false;",
        ):
            self.assertIn(token, constructor)

        create = braced_body(
            self.player_cpp, r"void\s+ARedPlayerCharacter::TryCreateLocalHUD\s*\("
        )
        for token in (
            "GetNetMode() == NM_DedicatedServer",
            "!IsLocallyControlled()",
            "!PC->IsLocalController()",
            "MinimapRT = NewObject<UTextureRenderTarget2D>",
            "MinimapRT->InitAutoFormat(512, 512);",
            "Hud->SetMinimapResource(MinimapRT);",
            "&ARedPlayerCharacter::RefreshHudCaptures, 0.15f, true",
        ):
            self.assertIn(token, create)

        destroy = braced_body(
            self.player_cpp, r"void\s+ARedPlayerCharacter::DestroyLocalHUD\s*\("
        )
        for token in (
            "ClearTimer(HudCaptureTimer)",
            "ActiveHUDWidget->RemoveFromParent();",
            "MinimapCapture->TextureTarget = nullptr;",
            "MinimapRT = nullptr;",
        ):
            self.assertIn(token, destroy)
        restart = braced_body(
            self.player_cpp, r"void\s+ARedPlayerCharacter::PawnClientRestart\s*\("
        )
        self.assertIn("TryCreateLocalHUD();", restart)
        self.assertNotRegex(self.player_h, r"Replicated[^\n]*Minimap(?:RT|Capture)")

    def test_surface_contacts_use_replication_but_are_legacy_presentation_only(self):
        tick = braced_body(
            self.player_cpp, r"void\s+ARedPlayerCharacter::Tick\s*\("
        )
        for token in (
            "!Other->bIsEnemy",
            "Other->IsDowned()",
            "FVector::DotProduct(Delta, Right)",
            "FVector::DotProduct(Delta, Forward)",
            "if (Blips.Num() >= 8)",
            "ActiveHUDWidget->SetMinimapBlips(Blips);",
        ):
            self.assertIn(token, tick)
        self.assertIn("DOREPLIFETIME(ARedPlayerCharacter, bDowned);", self.player_cpp)
        self.assertIn("DOREPLIFETIME(ARedPlayerCharacter, bIsEnemy);", self.player_cpp)

        set_blips = braced_body(
            self.vibe_cpp, r"void\s+UVibeMMOHUDWidget::SetMinimapBlips\s*\("
        )
        self.assertIn("!OffsetsPx.IsValidIndex(Index)", set_blips)
        self.assertIn("Blip->SetVisibility(ESlateVisibility::Collapsed);", set_blips)
        self.assertIn("Offset *= MapRadius / Len;", set_blips)

    def test_legacy_space_scan_is_not_an_accepted_replacement_producer(self):
        native_tick = braced_body(
            self.vibe_cpp, r"void\s+UVibeMMOHUDWidget::NativeTick\s*\("
        )
        self.assertIn("SpaceMinimapRefreshAccumulator >= 0.20f", native_tick)

        refresh = braced_body(
            self.vibe_cpp,
            r"void\s+UVibeMMOHUDWidget::RefreshSpaceMinimapNavigation\s*\(",
        )
        for token in (
            'GetAllActorsWithTag(World, TEXT("RedMineableSpaceAsteroid")',
            'GetAllActorsWithTag(World, TEXT("VibeOrbitalMining")',
            'Identity.Contains(TEXT("Ship")',
            'Identity.Contains(TEXT("Shuttle")',
            'Identity.Contains(TEXT("Fighter")',
            "ReferenceActor->GetActorForwardVector()",
            "ReferenceActor->GetActorRightVector()",
            "ReferenceActor->GetActorRotation().Yaw",
            "A.DistanceCm < B.DistanceCm",
        ):
            self.assertIn(token, refresh)

        invalid_guard_end = refresh.index("const float HeadingDegrees")
        invalid_guard = refresh[:invalid_guard_end]
        self.assertIn("if (!World || !IsValid(ReferenceActor))", invalid_guard)
        self.assertIn("return;", invalid_guard)
        self.assertNotIn("SetVisibility", invalid_guard)
        self.assertNotIn("NO CONTACTS", invalid_guard)
        for absent_contract in (
            "ContactId",
            "ContactID",
            "SensorRevision",
            "OwnershipEpoch",
            "FogOfWar",
        ):
            self.assertNotIn(absent_contract, refresh + self.vibe_h)

    def test_nonruntime_minimap_assets_remain_unreferenced_by_live_presenter(self):
        matching = sorted(
            path.relative_to(ROOT).as_posix()
            for relative_root in (Path("Content/RedMMO"), Path("Content/UI"))
            for path in (ROOT / relative_root).rglob("*")
            if path.is_file() and "minimap" in path.name.lower()
        )
        self.assertEqual(
            matching,
            [
                "Content/RedMMO/UI/Generated/minimap_stylized_planet.uasset",
                "Content/UI/RedHUD/Textures/ExactLayoutSprites/T_REDHUD_Minimap_Exact.uasset",
                "Content/UI/RedHUD/Textures/HighResSprites/T_REDHUD_Minimap.uasset",
                "Content/UI/RedHUD/Textures/Masks/T_REDHUD_MinimapCircleMask.uasset",
            ],
        )
        self.assertIn("T_REDHUD_Minimap.T_REDHUD_Minimap", self.widget_cpp)
        self.assertNotIn("T_REDHUD_Minimap_Exact", self.redhud_source)
        self.assertNotIn("T_REDHUD_MinimapCircleMask", self.redhud_source)
        self.assertNotIn("minimap_stylized_planet", self.redhud_source)

    def test_space_mode_is_explicit_and_fails_closed_in_the_live_presenter(self):
        mode_enum = re.search(
            r"enum\s+class\s+ERedHUDMinimapMode\b[\s\S]*?\};",
            self.types_h,
        )
        self.assertIsNotNone(mode_enum)
        for mode in ("Absent", "Surface", "Space"):
            self.assertRegex(mode_enum.group(0), rf"\b{mode}\b")

        refresh = braced_body(
            self.widget_cpp,
            r"void\s+URedHUDWidget::RefreshMinimapPresentationVisibility\s*\(",
        )
        self.assertIn(
            "CachedMinimapMode == ERedHUDMinimapMode::Surface", refresh
        )
        self.assertNotIn("ERedHUDMinimapMode::Space", refresh)
        self.assertIn("CachedMinimapCelestialFrameId.IsNone()", refresh)

    def test_surface_frame_resolution_and_hud_mode_mapping_are_explicit(self):
        resolve_frame = braced_body(
            self.player_cpp,
            r"FName\s+ARedPlayerCharacter::ResolveReplacementHUDMinimapFrameId\s*\(",
        )
        for token in (
            "GetCurrentGravityBodyId()",
            "RedGravity::QueryDominantBodyDetailed(",
            "Body.StableId",
        ):
            self.assertIn(token, resolve_frame)

        publish = braced_body(
            self.hud_cpp,
            r"void\s+ARedHUD::UpdateReplacementHUDMinimap\s*\(",
        )
        self.assertIn(
            "CachedLegacyHUDWidget.Get() != SourceOwner->GetActiveHUDWidget()",
            publish,
        )
        self.assertIn(
            "bSpaceMode\n\t\t? ERedHUDMinimapMode::Space", publish
        )
        self.assertIn("ERedHUDMinimapMode::Absent", publish)

    def test_guarded_publisher_requires_fresh_matching_capture_before_surface(self):
        publisher = braced_body(
            self.player_cpp,
            r"void\s+ARedPlayerCharacter::PublishReplacementHUDMinimap\s*\(",
        )
        for token in (
            "bSpaceMode || CelestialFrameId.IsNone()",
            "bReplacementMinimapSurfaceCaptureFresh = false;",
            "LastReplacementMinimapCaptureFrameId != CelestialFrameId",
            "MinimapCapture->TextureTarget != MinimapRT",
            "MinimapCapture->CaptureScene();",
            "const bool bSurfaceReady",
            "LastReplacementMinimapCaptureFrameId == CelestialFrameId",
            "MinimapCapture->TextureTarget == MinimapRT",
            "bSurfaceReady ? MinimapRT : nullptr",
            "bSurfaceReady ? CelestialFrameId : NAME_None",
        ):
            self.assertIn(token, publisher)
        self.assertLess(
            publisher.index("MinimapCapture->CaptureScene();"),
            publisher.index("const bool bSurfaceReady"),
        )
        self.assertLess(
            publisher.index("const bool bSurfaceReady"),
            publisher.index("UpdateReplacementHUDMinimap("),
        )
        self.assertEqual(
            self.player_cpp.count("UpdateReplacementHUDMinimap("), 1
        )
        tick = braced_body(
            self.player_cpp, r"void\s+ARedPlayerCharacter::Tick\s*\("
        )
        self.assertIn("PublishReplacementHUDMinimap(bUseSpaceMinimap);", tick)
        self.assertNotIn("UpdateReplacementHUDMinimap(", tick)
        self.assertIn(
            "bUseSpaceMinimap = bUseSpaceMinimap", tick
        )

    def test_composed_minimap_scales_from_one_authored_origin_without_stretching_rt(self):
        layout = braced_body(
            self.widget_cpp,
            r"void\s+URedHUDWidget::ApplyHUDElementLayout\s*\(",
        )
        for token in (
            'RedHUDLayout::Get(TEXT("Minimap")).Position()',
            "MinimapLiveWidgets.Contains(Widget)",
            "Widget->SetRenderTransformPivot(FVector2D::ZeroVector)",
            "(CanvasSlot->GetPosition() - MinimapOrigin)",
            "* (Layout.Scale - 1.0f)",
        ):
            self.assertIn(token, layout)

        live_overlay = braced_body(
            self.widget_cpp,
            r"void\s+URedHUDWidget::BuildLiveOverlay\s*\(",
        )
        self.assertIn(
            "MinimapImageSlot->SetSize(FVector2D(512.0f, 512.0f));",
            live_overlay,
        )
        self.assertNotIn("517.0f, 512.0f", live_overlay)

    def test_source_handoff_and_equal_epoch_updates_fail_closed(self):
        register = braced_body(
            self.hud_cpp,
            r"void\s+ARedHUD::RegisterLegacyCombatHUD\s*\(",
        )
        self.assertIn("CachedLegacyHUDWidget.Get() != LegacyHUD", register)
        self.assertIn("ResetReplacementHUDMinimap();", register)
        unregister = braced_body(
            self.hud_cpp,
            r"void\s+ARedHUD::UnregisterLegacyCombatHUD\s*\(",
        )
        self.assertIn(
            "CachedLegacyHUDWidget.Get() != ExpectedLegacyHUD", unregister
        )
        self.assertIn("ClearReplacementHUDMinimap(SourceOwner);", unregister)

        setter = braced_body(
            self.widget_cpp,
            r"bool\s+URedHUDWidget::SetMinimapPresentation\s*\(",
        )
        equal_epoch = setter[
            setter.index("PresentationEpoch == CachedMinimapPresentationEpoch") :
        ]
        for token in (
            "!CachedMinimapSourceOwner.IsValid()",
            "CachedMinimapSourceOwner.Get() != SourceOwner",
            "CachedMinimapMode != Mode",
            "CachedMinimapSurfaceTexture.Get() != ExpectedTexture",
            "CachedMinimapCelestialFrameId != ExpectedFrame",
            "return true;",
        ):
            self.assertIn(token, equal_epoch)


if __name__ == "__main__":
    unittest.main()
