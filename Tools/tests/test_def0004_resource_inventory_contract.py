"""Focused static contracts for the default-collapsed resource inventory slice."""

from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PAUSE_HEADER = (ROOT / "Source/RedMMO/RedPauseMenuWidget.h").read_text(
    encoding="utf-8"
)
PAUSE_SOURCE = (ROOT / "Source/RedMMO/RedPauseMenuWidget.cpp").read_text(
    encoding="utf-8"
)
HUD_SOURCE = (ROOT / "Source/RedMMO/RedHUD.cpp").read_text(encoding="utf-8")
PLAYER_HEADER = (ROOT / "Source/RedMMO/RedPlayerCharacter.h").read_text(
    encoding="utf-8"
)
PLAYER_SOURCE = (ROOT / "Source/RedMMO/RedPlayerCharacter.cpp").read_text(
    encoding="utf-8"
)
RED_HUD_WIDGET = (
    ROOT
    / "Plugins/RedHUD/Source/RedHUDRuntime/Private/RedHUDWidget.cpp"
).read_text(encoding="utf-8")
UI_AUTOMATION = (
    ROOT / "Source/RedMMO/Tests/RedUIControlBindingTests.cpp"
).read_text(encoding="utf-8")


def function_body(source: str, signature: str) -> str:
    """Return one balanced C++ function body, including its braces."""

    start = source.find(signature)
    if start < 0:
        raise AssertionError(f"missing function signature: {signature}")
    open_brace = source.find("{", start)
    if open_brace < 0:
        raise AssertionError(f"missing opening brace after: {signature}")
    depth = 0
    for index in range(open_brace, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[open_brace : index + 1]
    raise AssertionError(f"unterminated function body: {signature}")


class ResourceInventoryContractTests(unittest.TestCase):
    def test_resource_totals_keep_the_existing_authoritative_replication_owner(self) -> None:
        for field in ("ResStone", "ResIron", "ResCrystal"):
            self.assertRegex(
                PLAYER_HEADER,
                rf"ReplicatedUsing\s*=\s*OnRep_Resources[\s\S]{{0,120}}int32\s+{field}\s*=",
            )
            self.assertIn(f"DOREPLIFETIME(ARedPlayerCharacter, {field});", PLAYER_SOURCE)

        add_resource = function_body(
            PLAYER_SOURCE, "void ARedPlayerCharacter::AddResource("
        )
        self.assertIn("if (!HasAuthority())", add_resource)
        self.assertIn("ForceNetUpdate();", add_resource)
        self.assertRegex(add_resource, r"ResStone\s*\+=\s*Add")
        self.assertRegex(add_resource, r"ResIron\s*\+=\s*Add")
        self.assertRegex(add_resource, r"ResCrystal\s*\+=\s*Add")

    def test_inventory_uses_the_existing_escape_owned_default_collapsed_route(self) -> None:
        begin_play = function_body(HUD_SOURCE, "void ARedHUD::BeginPlay()")
        self.assertIn("EKeys::Escape", begin_play)
        self.assertIn("EKeys::Gamepad_Special_Right", begin_play)
        self.assertIn("&ARedHUD::TogglePauseMenu", begin_play)

        build_menu = function_body(
            PAUSE_SOURCE, "void URedPauseMenuWidget::BuildMenuTree()"
        )
        self.assertIn("PageSwitcher->AddChild(InventoryWidget);", build_menu)
        self.assertIn("PageSwitcher->SetActiveWidgetIndex(0);", build_menu)

        handle_inventory = function_body(
            PAUSE_SOURCE, "void URedPauseMenuWidget::HandleInventory()"
        )
        self.assertIn('ShowPage(1, TEXT("INVENTORY"));', handle_inventory)
        self.assertIn("bControllerInvoked", handle_inventory)
        self.assertIn(
            "FocusControllerInventoryCategory(",
            handle_inventory,
        )

        close_menu = function_body(HUD_SOURCE, "void ARedHUD::ClosePauseMenu()")
        self.assertIn(
            "PauseMenuWidget->SetVisibility(ESlateVisibility::Collapsed);",
            close_menu,
        )

    def test_controller_route_is_project_owned_and_deterministic(self) -> None:
        toggle = function_body(HUD_SOURCE, "void ARedHUD::TogglePauseMenu()")
        self.assertLess(
            toggle.index("PlayerController->SetInputMode(InputMode);"),
            toggle.index(
                "PauseMenuWidget->FocusInitialControllerTarget(PlayerController);"
            ),
        )

        preview = function_body(
            PAUSE_SOURCE,
            "FReply URedPauseMenuWidget::NativeOnPreviewKeyDown(",
        )
        self.assertIn("InKeyEvent.GetKey().IsGamepadKey()", preview)
        self.assertIn(
            "RouteControllerKey(InKeyEvent.GetKey(), InKeyEvent.IsRepeat())",
            preview,
        )

        route = function_body(
            PAUSE_SOURCE, "bool URedPauseMenuWidget::RouteControllerKey("
        )
        for key in (
            "EKeys::Gamepad_FaceButton_Right",
            "EKeys::Virtual_Gamepad_Back",
            "EKeys::Gamepad_Special_Right",
            "EKeys::Gamepad_FaceButton_Bottom",
            "EKeys::Gamepad_DPad_Left",
            "EKeys::Gamepad_DPad_Right",
            "EKeys::Gamepad_DPad_Up",
            "EKeys::Gamepad_DPad_Down",
        ):
            self.assertIn(key, route)
        self.assertIn("HandleResume();", route)
        self.assertIn("MoveControllerPrimary", route)
        self.assertIn("FocusControllerInventoryCategory", route)
        self.assertIn("FocusControllerInventorySlot", route)
        self.assertNotIn("SetInventoryItemPresentation", route)
        self.assertNotIn("AddResource", route)

    def test_controller_inventory_uses_named_vibe_controls_without_modifying_vibe(self) -> None:
        category_focus = function_body(
            PAUSE_SOURCE,
            "bool URedEmbeddedInventoryWidget::FocusControllerCategory(",
        )
        slot_focus = function_body(
            PAUSE_SOURCE,
            "bool URedEmbeddedInventoryWidget::FocusControllerVisibleSlot(",
        )
        category_activate = function_body(
            PAUSE_SOURCE,
            "bool URedEmbeddedInventoryWidget::ActivateControllerCategory(",
        )
        slot_activate = function_body(
            PAUSE_SOURCE,
            "bool URedEmbeddedInventoryWidget::ActivateControllerVisibleSlot(",
        )
        self.assertIn("InventoryCategoryButton_", PAUSE_SOURCE)
        self.assertIn("InventorySlotButton_", PAUSE_SOURCE)
        self.assertIn("SetUserFocus", category_focus)
        self.assertIn("SetUserFocus", slot_focus)
        self.assertIn("SetInventoryCategory", category_activate)
        self.assertIn("SlotButton->OnClicked.Broadcast();", slot_activate)
        self.assertIn(
            "GetSelectedInventoryItemIndex() == VisibleIndices[VisualSlotIndex]",
            slot_activate,
        )

    def test_project_owned_inventory_ledger_has_three_themed_quantity_cards(self) -> None:
        self.assertIn("void BuildResourceLedger();", PAUSE_HEADER)
        self.assertIn("void RefreshResourceLedger();", PAUSE_HEADER)
        ledger = function_body(
            PAUSE_SOURCE,
            "void URedEmbeddedInventoryWidget::BuildResourceLedger()",
        )
        self.assertIn('TEXT("InventoryContentCanvas")', ledger)
        self.assertIn('TEXT("RedResourceQuantityLedger")', ledger)
        self.assertIn('TEXT("RedStone"), TEXT("STONE")', ledger)
        self.assertIn('TEXT("RedIron"), TEXT("IRON")', ledger)
        self.assertIn('TEXT("RedCrystal"), TEXT("CRYSTAL")', ledger)
        self.assertIn("RedPauseMenu::Gold", ledger)
        self.assertIn("RedPauseMenu::Purple", ledger)
        self.assertNotIn("LoadObject<", ledger)

    def test_resource_inventory_layout_contains_tabs_and_detail_text(self) -> None:
        self.assertIn("void ApplyInventoryLayoutPolish();", PAUSE_HEADER)
        polish = function_body(
            PAUSE_SOURCE,
            "void URedEmbeddedInventoryWidget::ApplyInventoryLayoutPolish()",
        )
        self.assertIn("RarityLabelText->SetAutoWrapText(false);", polish)
        self.assertIn("RarityFont.Size = 14;", polish)
        self.assertIn("RarityLabelText->SetFont(RarityFont);", polish)
        self.assertIn('TEXT("InventoryTabs")', polish)
        self.assertIn("TabsSlot->SetSize(FVector2D(580.0f, 40.0f));", polish)
        self.assertIn("TabSlot->SetPadding(FMargin(0.0f, 0.0f, 12.0f, 0.0f));", polish)
        ledger = function_body(
            PAUSE_SOURCE,
            "void URedEmbeddedInventoryWidget::BuildResourceLedger()",
        )
        self.assertIn("LedgerSlot->SetPosition(FVector2D(630.0f, 0.0f));", ledger)
        self.assertIn("LedgerSlot->SetSize(FVector2D(280.0f, 88.0f));", ledger)
        self.assertIn('TEXT("STORED: %d")', PAUSE_SOURCE)

    def test_grid_polish_suppresses_only_crowded_in_slot_labels(self) -> None:
        self.assertIn("void ApplyGridLabelPolish();", PAUSE_HEADER)
        rebuild = function_body(
            PAUSE_SOURCE,
            "TSharedRef<SWidget> URedEmbeddedInventoryWidget::RebuildWidget()",
        )
        self.assertLess(
            rebuild.index("NativePreConstruct();"),
            rebuild.index("ApplyGridLabelPolish();"),
        )

        polish = function_body(
            PAUSE_SOURCE,
            "void URedEmbeddedInventoryWidget::ApplyGridLabelPolish()",
        )
        self.assertIn(
            "for (int32 Index = 0; Index < InventoryCapacity; ++Index)", polish
        )
        self.assertIn('TEXT("InventorySlotPlaceholder_%d")', polish)
        self.assertIn("GridLabel->SetRenderOpacity(0.0f);", polish)
        self.assertNotIn("SetVisibility", polish)
        self.assertNotIn("SetIsEnabled", polish)
        self.assertNotIn("InventorySlotButton_", polish)
        for preserved_path in (
            "SetInventoryItemPresentation",
            "ClearInventoryItemPresentation",
            "SetInventoryCategory",
            "SelectInventoryItem",
            "InventorySlotBorder_",
            "InventorySlotIcon_",
            "InventoryItemNameText",
            "InventoryItemDescriptionText",
        ):
            self.assertNotIn(preserved_path, polish)

    def test_inventory_cards_publish_exact_replicated_quantities(self) -> None:
        ledger_refresh = function_body(
            PAUSE_SOURCE,
            "void URedEmbeddedInventoryWidget::RefreshResourceLedger()",
        )
        self.assertIn("QuantityText->SetText(FText::AsNumber(Quantity));", ledger_refresh)
        self.assertIn("QuantityText->SynchronizeProperties();", ledger_refresh)
        self.assertIn(
            "QuantityText->InvalidateLayoutAndVolatility();", ledger_refresh
        )
        for card in ("StoneQuantityText", "IronQuantityText", "CrystalQuantityText"):
            self.assertIn(f"PublishQuantity({card}", ledger_refresh)

        refresh = function_body(
            PAUSE_SOURCE, "void URedPauseMenuWidget::RefreshInventoryResources()"
        )
        for field in ("ResStone", "ResIron", "ResCrystal"):
            self.assertIn(f"Character->{field}", refresh)
        self.assertIn("SetResourceInventoryTotals(Stone, Iron, Crystal);", refresh)

        publish = function_body(
            PAUSE_SOURCE,
            "void URedPauseMenuWidget::SetResourceInventoryTotals(",
        )
        self.assertIn("EVibeMMOInventoryCategory::Resources", publish)
        self.assertIn('TEXT("STORED: %d")', publish)
        self.assertIn("Resource.Description = FText::FromString(Description);", publish)
        self.assertRegex(publish, r"PublishResource\(\s*2,\s*TEXT\(\"STONE\"\)")
        self.assertRegex(publish, r"PublishResource\(\s*3,\s*TEXT\(\"IRON\"\)")
        self.assertRegex(publish, r"PublishResource\(\s*4,\s*TEXT\(\"CRYSTAL\"\)")

    def test_inventory_refreshes_at_construct_open_and_inventory_navigation(self) -> None:
        native_construct = function_body(
            PAUSE_SOURCE, "void URedPauseMenuWidget::NativeConstruct()"
        )
        prepare = function_body(
            PAUSE_SOURCE, "void URedPauseMenuWidget::PrepareForOpen()"
        )
        handle_inventory = function_body(
            PAUSE_SOURCE, "void URedPauseMenuWidget::HandleInventory()"
        )
        self.assertIn("RefreshInventoryResources();", native_construct)
        self.assertIn("RefreshInventoryResources();", prepare)
        self.assertIn("RefreshInventoryResources();", handle_inventory)
        self.assertLess(
            prepare.index("RefreshInventoryResources();"),
            prepare.index('ShowPage(0, TEXT("OVERVIEW"));'),
        )
        self.assertLess(
            handle_inventory.index("RefreshInventoryResources();"),
            handle_inventory.index('ShowPage(1, TEXT("INVENTORY"));'),
        )

    def test_resource_totals_remain_absent_from_the_always_on_combat_hud(self) -> None:
        live_overlay = function_body(
            RED_HUD_WIDGET, "void URedHUDWidget::BuildLiveOverlay()"
        )
        self.assertNotIn("ResourceTallyText", live_overlay)
        self.assertNotIn("RedResourceQuantityLedger", live_overlay)
        self.assertNotRegex(
            live_overlay,
            re.compile(r"STONE.*IRON.*CRYSTAL", re.IGNORECASE | re.DOTALL),
        )

        tally_setter = function_body(
            RED_HUD_WIDGET, "void URedHUDWidget::SetResourceTally("
        )
        self.assertIn("CachedResourceStone", tally_setter)
        self.assertNotIn("SetText", tally_setter)
        self.assertNotIn("SetVisibility", tally_setter)

        tally_query = function_body(
            RED_HUD_WIDGET, "bool URedHUDWidget::GetResourceTallyState("
        )
        self.assertIn("OutText.Reset();", tally_query)
        self.assertIn("bOutVisible = false;", tally_query)

    def test_resource_inventory_does_not_reinterpret_consumables_or_steam_items(self) -> None:
        publish = function_body(
            PAUSE_SOURCE,
            "void URedPauseMenuWidget::SetResourceInventoryTotals(",
        )
        self.assertNotIn("Consumable", publish)
        self.assertNotIn("Steam", publish)
        self.assertNotIn("SetConsumableCount", publish)
        self.assertNotIn("IconResource", publish)

    def test_replication_refresh_updates_an_already_created_inventory_page(self) -> None:
        bridge = function_body(
            HUD_SOURCE, "void ARedHUD::UpdateReplacementHUDResources("
        )
        self.assertIn(
            "PauseMenuWidget->SetResourceInventoryTotals(Stone, Iron, Crystal);",
            bridge,
        )

    def test_controller_runtime_harness_uses_slate_events_without_physical_claim(self) -> None:
        self.assertIn("RedDEF0004ControllerInventoryAudit", PLAYER_SOURCE)
        self.assertIn("bLegacyInventoryInteractionAudit && bControllerInventoryAudit", PLAYER_SOURCE)
        self.assertIn("RED_DEF0004_CONTROLLER_ARMED", PLAYER_SOURCE)
        self.assertIn("RED_DEF0004_CONTROLLER_INPUT", PLAYER_SOURCE)
        self.assertIn("RED_DEF0004_CONTROLLER_IRON_SELECT", PLAYER_SOURCE)
        self.assertIn("RED_DEF0004_CONTROLLER_REFRESH", PLAYER_SOURCE)
        self.assertIn("RED_DEF0004_CONTROLLER_CLOSE", PLAYER_SOURCE)
        self.assertIn("RED_DEF0004_CONTROLLER_RESULT", PLAYER_SOURCE)
        self.assertIn("ScheduleControllerInventoryAdvance", PLAYER_SOURCE)
        self.assertIn("adaptive=1", PLAYER_SOURCE)
        self.assertIn("fallbackRoute=%d", PLAYER_SOURCE)
        self.assertIn(
            "PauseMenu->RouteControllerKey(Key, false);",
            PLAYER_SOURCE,
        )
        self.assertIn('Region == TEXT("PrimaryMenu")', PLAYER_SOURCE)
        self.assertIn('Region == TEXT("InventoryCategory")', PLAYER_SOURCE)
        self.assertIn('Region == TEXT("InventoryGrid")', PLAYER_SOURCE)
        self.assertIn(
            "FSlateApplication::Get().ProcessKeyDownEvent(",
            PLAYER_SOURCE,
        )
        self.assertIn(
            "FSlateApplication::Get().ProcessKeyUpEvent(",
            PLAYER_SOURCE,
        )
        self.assertIn("physicalControllerTested=0", PLAYER_SOURCE)
        self.assertIn("synthetic_engine_controller_callback", PLAYER_SOURCE)
        self.assertIn("Controller_Resources_Iron6_Selected", PLAYER_SOURCE)
        self.assertRegex(
            PLAYER_SOURCE,
            r"ControllerInputPassed\s*=\s*\n\s*MakeShared<bool>\(true\);",
        )

    def test_ultrawide_controller_inventory_audit_is_opt_in_and_exact(self) -> None:
        self.assertIn(
            "RedDEF0004ControllerInventoryUltrawideAudit",
            PLAYER_SOURCE,
        )
        self.assertIn(
            "bUltrawideInventoryAudit && !bControllerInventoryAudit",
            PLAYER_SOURCE,
        )
        self.assertIn(
            "bUltrawideInventoryAudit && bUltrawideReceiptAudit",
            PLAYER_SOURCE,
        )
        self.assertRegex(
            PLAYER_SOURCE,
            r"ControllerInventoryViewportWidth\s*=\s*"
            r"\n\s*bUltrawideInventoryAudit \? 3440 : 1280;",
        )
        self.assertRegex(
            PLAYER_SOURCE,
            r"ControllerInventoryViewportHeight\s*=\s*"
            r"\n\s*bUltrawideInventoryAudit \? 1440 : 720;",
        )
        self.assertIn(
            "&& ViewportWidth == ControllerInventoryViewportWidth",
            PLAYER_SOURCE,
        )
        self.assertIn(
            "&& ViewportHeight == ControllerInventoryViewportHeight",
            PLAYER_SOURCE,
        )
        for phase in ("OPEN", "IRON_SELECT", "REFRESH", "CLOSE"):
            self.assertRegex(
                PLAYER_SOURCE,
                rf"RED_DEF0004_CONTROLLER_{phase} pass=%d "
                rf"viewport=%dx%d expectedViewport=%dx%d",
            )
        for capture in (
            "Controller_3440x1440_OverviewOpen",
            "Controller_3440x1440_Resources_Iron0_Selected",
            "Controller_3440x1440_Resources_Iron6_Selected",
            "Controller_3440x1440_Closed",
        ):
            self.assertIn(capture, PLAYER_SOURCE)
        self.assertIn("12.20f,", PLAYER_SOURCE)
        for unrelated_capture in (
            'TEXT("Surface")',
            'TEXT("SpaceBefore")',
            'TEXT("SpaceReward")',
            'TEXT("SpaceTransition")',
            'TEXT("SpaceExplosion")',
            'TEXT("SpaceDebris")',
            'TEXT("SpaceAfter")',
        ):
            capture_index = PLAYER_SOURCE.index(unrelated_capture)
            guard_index = PLAYER_SOURCE.rfind(
                "if (!bControllerInventoryAudit)", 0, capture_index
            )
            self.assertGreater(guard_index, -1)
            self.assertLess(capture_index - guard_index, 300)
        self.assertIn(
            "bUltrawideInventoryAudit ? 15.0f : 14.0f",
            PLAYER_SOURCE,
        )
        self.assertIn(
            "bUltrawideInventoryAudit ? 16.0f : 15.0f",
            PLAYER_SOURCE,
        )
        self.assertIn(
            "RED_DEF0004_ULTRAWIDE_INVENTORY_RESULT",
            PLAYER_SOURCE,
        )
        self.assertIn("physicalControllerTested=0", PLAYER_SOURCE)

    def test_compiled_ui_automation_exercises_quantities_and_resource_cards(self) -> None:
        self.assertIn(
            'PauseMenu->SetResourceInventoryTotals(12, 34, 56);',
            UI_AUTOMATION,
        )
        self.assertIn(
            "ResourceInventory->GetResourceTotals(",
            UI_AUTOMATION,
        )
        for name in ("STONE", "IRON", "CRYSTAL"):
            self.assertIn(f'TEXT("{name}")', UI_AUTOMATION)
        self.assertIn("EVibeMMOInventoryCategory::Resources", UI_AUTOMATION)
        self.assertIn('TEXT("RedStoneQuantity")', UI_AUTOMATION)
        self.assertIn('TEXT("RedIronQuantity")', UI_AUTOMATION)
        self.assertIn('TEXT("RedCrystalQuantity")', UI_AUTOMATION)
        self.assertIn(
            "ResourceInventory->SetInventoryCategory("
            "EVibeMMOInventoryCategory::Resources);",
            UI_AUTOMATION,
        )
        self.assertIn(
            'TEXT("InventorySlotPlaceholder_%d")',
            UI_AUTOMATION,
        )
        self.assertIn(
            "Grid labels stay visually suppressed after a category refresh",
            UI_AUTOMATION,
        )
        self.assertIn("IronSlot->OnClicked.Broadcast();", UI_AUTOMATION)
        self.assertIn(
            'ItemNameText->GetText().ToString(), FString(TEXT("IRON"))',
            UI_AUTOMATION,
        )
        for controller_key in (
            "EKeys::Gamepad_DPad_Down",
            "EKeys::Gamepad_DPad_Right",
            "EKeys::Gamepad_FaceButton_Bottom",
            "EKeys::Gamepad_FaceButton_Right",
        ):
            self.assertIn(controller_key, UI_AUTOMATION)
        self.assertIn(
            "PauseMenu->GetControllerInventoryState(",
            UI_AUTOMATION,
        )
        self.assertIn(
            "Controller-selected Iron detail survives an authoritative live refresh",
            UI_AUTOMATION,
        )


if __name__ == "__main__":
    unittest.main()
