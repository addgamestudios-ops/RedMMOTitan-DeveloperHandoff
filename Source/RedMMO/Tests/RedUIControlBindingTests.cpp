#if WITH_DEV_AUTOMATION_TESTS

#include "../RedPauseMenuWidget.h"
#include "../RedSessionBrowserWidget.h"
#include "Widgets/VibeMMOHUDWidget.h"

#include "Blueprint/WidgetTree.h"
#include "Components/Button.h"
#include "Components/TextBlock.h"
#include "InputCoreTypes.h"
#include "Misc/AutomationTest.h"
#include "UObject/Class.h"

namespace RedUIControlBindingTests
{
	struct FExpectedBinding
	{
		const TCHAR* Label;
		const TCHAR* Handler;
	};

	static FString GetButtonLabel(UButton* Button)
	{
		if (const UTextBlock* Label = Button ? Cast<UTextBlock>(Button->GetContent()) : nullptr)
		{
			return Label->GetText().ToString();
		}
		return FString();
	}

	static bool ValidateButtonSurface(
		FAutomationTestBase& Test,
		UUserWidget* Owner,
		const TCHAR* SurfaceName,
		const TArray<FExpectedBinding>& ExpectedBindings)
	{
		if (!Test.TestNotNull(*FString::Printf(TEXT("%s widget exists"), SurfaceName), Owner)
			|| !Test.TestNotNull(*FString::Printf(TEXT("%s has a widget tree"), SurfaceName), Owner->WidgetTree.Get()))
		{
			return false;
		}

		TArray<UWidget*> Widgets;
		Owner->WidgetTree->GetAllWidgets(Widgets);
		TArray<UButton*> Buttons;
		for (UWidget* Widget : Widgets)
		{
			if (UButton* Button = Cast<UButton>(Widget))
			{
				Buttons.Add(Button);
			}
		}

		bool bPassed = Test.TestEqual(
			*FString::Printf(TEXT("%s exposes only the audited button set"), SurfaceName),
			Buttons.Num(), ExpectedBindings.Num());

		TSet<FString> SeenLabels;
		for (UButton* Button : Buttons)
		{
			const FString Label = GetButtonLabel(Button);
			bPassed &= Test.TestFalse(
				*FString::Printf(TEXT("%s has no unlabeled interactive button"), SurfaceName),
				Label.IsEmpty());
			bPassed &= Test.TestFalse(
				*FString::Printf(TEXT("%s button label is unique: %s"), SurfaceName, *Label),
				SeenLabels.Contains(Label));
			SeenLabels.Add(Label);

			const FExpectedBinding* Expected = ExpectedBindings.FindByPredicate(
				[&Label](const FExpectedBinding& Candidate)
				{
					return Label == Candidate.Label;
				});
			bPassed &= Test.TestNotNull(
				*FString::Printf(TEXT("%s button is part of the audited contract: %s"), SurfaceName, *Label),
				Expected);
			if (!Expected)
			{
				continue;
			}

			const FName HandlerName(Expected->Handler);
			const UFunction* HandlerFunction = Owner->FindFunction(HandlerName);
			bPassed &= Test.TestNotNull(
				*FString::Printf(TEXT("%s handler exists: %s -> %s"), SurfaceName, *Label, Expected->Handler),
				HandlerFunction);
			if (HandlerFunction)
			{
				bPassed &= Test.TestTrue(
					*FString::Printf(TEXT("%s handler is native code: %s"), SurfaceName, Expected->Handler),
					HandlerFunction->HasAnyFunctionFlags(FUNC_Native)
						&& HandlerFunction->GetNativeFunc() != nullptr);
			}

			bPassed &= Test.TestTrue(
				*FString::Printf(TEXT("%s click delegate is bound: %s"), SurfaceName, *Label),
				Button->OnClicked.IsBound());
			bPassed &= Test.TestTrue(
				*FString::Printf(TEXT("%s click routes to its audited handler: %s -> %s"),
					SurfaceName, *Label, Expected->Handler),
				Button->OnClicked.Contains(Owner, HandlerName));

			if (!Button->GetIsEnabled())
			{
				bPassed &= Test.TestFalse(
					*FString::Printf(TEXT("%s disabled control explains why: %s"), SurfaceName, *Label),
					Button->GetToolTipText().IsEmpty());
			}
		}

		for (const FExpectedBinding& Expected : ExpectedBindings)
		{
			bPassed &= Test.TestTrue(
				*FString::Printf(TEXT("%s required control is present: %s"), SurfaceName, Expected.Label),
				SeenLabels.Contains(Expected.Label));
		}
		return bPassed;
	}
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(
	FRedUIControlBindingTest,
	"RedMMO.UI.Controls.NoDeadEnds",
	EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::ProductFilter)

bool FRedUIControlBindingTest::RunTest(const FString& Parameters)
{
	using namespace RedUIControlBindingTests;
	bool bPassed = true;

	URedPauseMenuWidget* PauseMenu = NewObject<URedPauseMenuWidget>();
	bPassed &= TestTrue(TEXT("Pause menu initializes without PIE"), PauseMenu->Initialize());
	PauseMenu->TakeWidget();
	const TArray<FExpectedBinding> PauseBindings = {
		{ TEXT("RESUME"), TEXT("HandleResume") },
		{ TEXT("MULTIPLAYER / LOBBY"), TEXT("HandleMultiplayer") },
		{ TEXT("OVERVIEW"), TEXT("HandleOverview") },
		{ TEXT("INVENTORY"), TEXT("HandleInventory") },
		{ TEXT("CHARACTER"), TEXT("HandleCharacter") },
		{ TEXT("SKILLS + LOADOUT"), TEXT("HandleSkills") },
		{ TEXT("SETTINGS"), TEXT("HandleSettings") },
		{ TEXT("CUSTOMIZE HUD"), TEXT("HandleHUDCustomization") },
		{ TEXT("EXIT TO DESKTOP"), TEXT("HandleExit") },
		{ TEXT("OPEN INTERACTIVE LOADOUT"), TEXT("HandleOpenAbilityLoadout") },
		{ TEXT("PERFORMANCE"), TEXT("HandlePerformanceQuality") },
		{ TEXT("BALANCED"), TEXT("HandleBalancedQuality") },
		{ TEXT("CINEMATIC"), TEXT("HandleCinematicQuality") },
		{ TEXT("TOGGLE FULLSCREEN / WINDOWED"), TEXT("HandleToggleWindowMode") },
		{ TEXT("< PREVIOUS ELEMENT"), TEXT("HandleHUDPreviousElement") },
		{ TEXT("NEXT ELEMENT >"), TEXT("HandleHUDNextElement") },
		{ TEXT("MOVE LEFT"), TEXT("HandleHUDMoveLeft") },
		{ TEXT("MOVE RIGHT"), TEXT("HandleHUDMoveRight") },
		{ TEXT("MOVE UP"), TEXT("HandleHUDMoveUp") },
		{ TEXT("MOVE DOWN"), TEXT("HandleHUDMoveDown") },
		{ TEXT("SIZE -"), TEXT("HandleHUDScaleDown") },
		{ TEXT("SIZE +"), TEXT("HandleHUDScaleUp") },
		{ TEXT("OPACITY -"), TEXT("HandleHUDOpacityDown") },
		{ TEXT("OPACITY +"), TEXT("HandleHUDOpacityUp") },
		{ TEXT("SHOW / HIDE"), TEXT("HandleHUDToggleVisibility") },
		{ TEXT("LOCK / UNLOCK"), TEXT("HandleHUDToggleLock") },
		{ TEXT("RESET ELEMENT"), TEXT("HandleHUDResetElement") },
		{ TEXT("RESET ALL"), TEXT("HandleHUDResetAll") },
		{ TEXT("APPLY + SAVE"), TEXT("HandleHUDApply") },
		{ TEXT("CANCEL CHANGES"), TEXT("HandleHUDCancel") },
	};
	bPassed &= ValidateButtonSurface(*this, PauseMenu, TEXT("Pause menu"), PauseBindings);

	URedEmbeddedInventoryWidget* ResourceInventory = Cast<URedEmbeddedInventoryWidget>(
		PauseMenu->WidgetTree->FindWidget(TEXT("PauseInventoryWidget")));
	bPassed &= TestNotNull(
		TEXT("Pause menu owns the default-collapsed resource inventory page"),
		ResourceInventory);
	if (ResourceInventory)
	{
		PauseMenu->SetResourceInventoryTotals(12, 34, 56);

		int32 Stone = 0;
		int32 Iron = 0;
		int32 Crystal = 0;
		FString ResourceSummary;
		bPassed &= TestTrue(
			TEXT("Resource inventory exposes its sanitized session totals"),
			ResourceInventory->GetResourceTotals(
				Stone, Iron, Crystal, ResourceSummary));
		bPassed &= TestEqual(TEXT("Stone quantity reaches Inventory"), Stone, 12);
		bPassed &= TestEqual(TEXT("Iron quantity reaches Inventory"), Iron, 34);
		bPassed &= TestEqual(TEXT("Crystal quantity reaches Inventory"), Crystal, 56);
		bPassed &= TestEqual(
			TEXT("Resource inventory summary carries all three exact quantities"),
			ResourceSummary,
			FString(TEXT("STONE 12 | IRON 34 | CRYSTAL 56")));

		const TArray<TPair<int32, FString>> ExpectedResources = {
			{ 2, TEXT("STONE") },
			{ 3, TEXT("IRON") },
			{ 4, TEXT("CRYSTAL") },
		};
		for (const TPair<int32, FString>& Expected : ExpectedResources)
		{
			FVibeMMOInventoryItemPresentation Presentation;
			bPassed &= TestTrue(
				*FString::Printf(TEXT("%s resource card is populated"), *Expected.Value),
				ResourceInventory->GetInventoryItemPresentation(
					Expected.Key, Presentation));
			bPassed &= TestEqual(
				*FString::Printf(TEXT("%s card has resource category"), *Expected.Value),
				Presentation.Category,
				EVibeMMOInventoryCategory::Resources);
			bPassed &= TestEqual(
				*FString::Printf(TEXT("%s card keeps its stable name"), *Expected.Value),
				Presentation.DisplayName.ToString(),
				Expected.Value);
			bPassed &= TestTrue(
				*FString::Printf(TEXT("%s card carries a quantity detail"), *Expected.Value),
				Presentation.Rarity.ToString().Contains(TEXT("QUANTITY")));
		}

		const UTextBlock* StoneText = Cast<UTextBlock>(
			ResourceInventory->WidgetTree->FindWidget(TEXT("RedStoneQuantity")));
		const UTextBlock* IronText = Cast<UTextBlock>(
			ResourceInventory->WidgetTree->FindWidget(TEXT("RedIronQuantity")));
		const UTextBlock* CrystalText = Cast<UTextBlock>(
			ResourceInventory->WidgetTree->FindWidget(TEXT("RedCrystalQuantity")));
		bPassed &= TestNotNull(TEXT("Stone quantity card exists"), StoneText);
		bPassed &= TestNotNull(TEXT("Iron quantity card exists"), IronText);
		bPassed &= TestNotNull(TEXT("Crystal quantity card exists"), CrystalText);
		if (StoneText && IronText && CrystalText)
		{
			bPassed &= TestEqual(
				TEXT("Stone quantity card is current"),
				StoneText->GetText().ToString(), FString(TEXT("12")));
			bPassed &= TestEqual(
				TEXT("Iron quantity card is current"),
				IronText->GetText().ToString(), FString(TEXT("34")));
			bPassed &= TestEqual(
				TEXT("Crystal quantity card is current"),
				CrystalText->GetText().ToString(), FString(TEXT("56")));
		}

		ResourceInventory->SetInventoryCategory(EVibeMMOInventoryCategory::Resources);
		UVibeMMOInventorySlotButton* IronSlot = Cast<UVibeMMOInventorySlotButton>(
			ResourceInventory->WidgetTree->FindWidget(TEXT("InventorySlotButton_1")));
		bPassed &= TestNotNull(TEXT("Filtered Iron resource slot exists"), IronSlot);
		if (IronSlot)
		{
			bPassed &= TestEqual(
				TEXT("Filtered Iron slot keeps stable resource index"),
				IronSlot->GetStableItemIndex(), 3);
			bPassed &= TestTrue(
				TEXT("Filtered Iron slot remains interactive"),
				IronSlot->GetIsEnabled());
			IronSlot->OnClicked.Broadcast();
			bPassed &= TestEqual(
				TEXT("Clicking the caption-free Iron slot selects Iron"),
				ResourceInventory->GetSelectedInventoryItemIndex(), 3);
			bPassed &= TestNotNull(
				TEXT("Inventory detail name remains available"),
				ResourceInventory->ItemNameText.Get());
			bPassed &= TestNotNull(
				TEXT("Inventory rarity detail remains available"),
				ResourceInventory->RarityLabelText.Get());
			bPassed &= TestNotNull(
				TEXT("Inventory description detail remains available"),
				ResourceInventory->ItemDescriptionText.Get());
			if (ResourceInventory->ItemNameText
				&& ResourceInventory->RarityLabelText
				&& ResourceInventory->ItemDescriptionText)
			{
				bPassed &= TestEqual(
					TEXT("Caption-free Iron slot still publishes its detail name"),
					ResourceInventory->ItemNameText->GetText().ToString(), FString(TEXT("IRON")));
				bPassed &= TestTrue(
					TEXT("Caption-free Iron slot still publishes its quantity detail"),
					ResourceInventory->RarityLabelText->GetText().ToString().Contains(
						TEXT("QUANTITY 34")));
				bPassed &= TestTrue(
					TEXT("Caption-free Iron slot still publishes its description quantity"),
					ResourceInventory->ItemDescriptionText->GetText().ToString().Contains(
						TEXT("Stored quantity: 34")));
			}
		}

		for (int32 Index = 0; Index < UVibeMMOInventoryWidget::InventoryCapacity; ++Index)
		{
			const UTextBlock* GridLabel = Cast<UTextBlock>(
				ResourceInventory->WidgetTree->FindWidget(
					*FString::Printf(TEXT("InventorySlotPlaceholder_%d"), Index)));
			bPassed &= TestNotNull(
				*FString::Printf(TEXT("Inventory grid label %d exists"), Index),
				GridLabel);
			if (GridLabel)
			{
				bPassed &= TestTrue(
					*FString::Printf(
						TEXT("Grid labels stay visually suppressed after a category refresh (%d)"),
						Index),
					FMath::IsNearlyZero(GridLabel->GetRenderOpacity()));
			}
		}
		ResourceInventory->SetInventoryCategory(EVibeMMOInventoryCategory::All);
		ResourceInventory->SelectInventoryItem(0);

		PauseMenu->PrepareForOpen();
		PauseMenu->FocusInitialControllerTarget(nullptr);
		bPassed &= TestTrue(
			TEXT("Controller D-pad moves from Resume toward Inventory (1/3)"),
			PauseMenu->RouteControllerKey(EKeys::Gamepad_DPad_Down));
		bPassed &= TestTrue(
			TEXT("Controller D-pad moves from Resume toward Inventory (2/3)"),
			PauseMenu->RouteControllerKey(EKeys::Gamepad_DPad_Down));
		bPassed &= TestTrue(
			TEXT("Controller D-pad focuses Inventory"),
			PauseMenu->RouteControllerKey(EKeys::Gamepad_DPad_Down));
		bPassed &= TestTrue(
			TEXT("Controller accept opens Inventory and transfers focus to its tabs"),
			PauseMenu->RouteControllerKey(EKeys::Gamepad_FaceButton_Bottom));
		PauseMenu->SetResourceInventoryTotals(12, 34, 56);
		bPassed &= TestTrue(
			TEXT("Controller moves from All to Weapons"),
			PauseMenu->RouteControllerKey(EKeys::Gamepad_DPad_Right));
		bPassed &= TestTrue(
			TEXT("Controller moves from Weapons to Resources"),
			PauseMenu->RouteControllerKey(EKeys::Gamepad_DPad_Right));
		bPassed &= TestTrue(
			TEXT("Controller accepts the Resources category"),
			PauseMenu->RouteControllerKey(EKeys::Gamepad_FaceButton_Bottom));
		bPassed &= TestTrue(
			TEXT("Controller enters the filtered resource grid"),
			PauseMenu->RouteControllerKey(EKeys::Gamepad_DPad_Down));
		bPassed &= TestTrue(
			TEXT("Controller moves from Stone to Iron"),
			PauseMenu->RouteControllerKey(EKeys::Gamepad_DPad_Right));
		bPassed &= TestTrue(
			TEXT("Controller accepts Iron"),
			PauseMenu->RouteControllerKey(EKeys::Gamepad_FaceButton_Bottom));

		FString ControllerRegion;
		int32 ControllerPrimaryIndex = INDEX_NONE;
		int32 ControllerCategoryIndex = INDEX_NONE;
		int32 ControllerVisualSlotIndex = INDEX_NONE;
		int32 ControllerStableItemIndex = INDEX_NONE;
		FString ControllerFocusedWidget;
		bool bHasUserFocus = false;
		bPassed &= TestTrue(
			TEXT("Controller inventory state is queryable"),
			PauseMenu->GetControllerInventoryState(
				ControllerRegion,
				ControllerPrimaryIndex,
				ControllerCategoryIndex,
				ControllerVisualSlotIndex,
				ControllerStableItemIndex,
				ControllerFocusedWidget,
				bHasUserFocus));
		bPassed &= TestEqual(
			TEXT("Controller finishes in the Inventory grid"),
			ControllerRegion, FString(TEXT("InventoryGrid")));
		bPassed &= TestEqual(
			TEXT("Controller Inventory route keeps the left-nav Inventory index"),
			ControllerPrimaryIndex, 3);
		bPassed &= TestEqual(
			TEXT("Controller Inventory route selects Resources"),
			ControllerCategoryIndex,
			static_cast<int32>(EVibeMMOInventoryCategory::Resources));
		bPassed &= TestEqual(
			TEXT("Controller Inventory route focuses filtered visual slot one"),
			ControllerVisualSlotIndex, 1);
		bPassed &= TestEqual(
			TEXT("Controller Inventory route selects stable Iron item three"),
			ControllerStableItemIndex, 3);
		bPassed &= TestEqual(
			TEXT("Controller Inventory route focuses the Iron slot widget"),
			ControllerFocusedWidget,
			FString(TEXT("InventorySlotButton_1")));
		bPassed &= TestEqual(
			TEXT("Controller-selected Iron publishes its quantity detail"),
			ResourceInventory->RarityLabelText->GetText().ToString(),
			FString(TEXT("STORED MATERIAL  |  QUANTITY 34")));

		PauseMenu->SetResourceInventoryTotals(12, 40, 56);
		bPassed &= TestEqual(
			TEXT("Controller-selected Iron detail survives an authoritative live refresh"),
			ResourceInventory->GetSelectedInventoryItemIndex(), 3);
		bPassed &= TestEqual(
			TEXT("Controller-selected Iron detail repaints its live quantity"),
			ResourceInventory->RarityLabelText->GetText().ToString(),
			FString(TEXT("STORED MATERIAL  |  QUANTITY 40")));
		bPassed &= TestTrue(
			TEXT("Controller B is an owned close command"),
			PauseMenu->RouteControllerKey(EKeys::Gamepad_FaceButton_Right));
	}

	URedSessionBrowserWidget* SessionBrowser = NewObject<URedSessionBrowserWidget>();
	bPassed &= TestTrue(TEXT("Session browser initializes without PIE"), SessionBrowser->Initialize());
	SessionBrowser->TakeWidget();
	const TArray<FExpectedBinding> SessionBindings = {
		{ TEXT("CLOSE"), TEXT("HandleCloseClicked") },
		{ TEXT("CREATE GAME"), TEXT("HandleHostClicked") },
		{ TEXT("FIND GAMES"), TEXT("HandleRefreshClicked") },
		{ TEXT("JOIN SELECTED"), TEXT("HandleJoinClicked") },
		{ TEXT("RECONNECT"), TEXT("HandleReconnectClicked") },
		{ TEXT("INVITE FRIENDS"), TEXT("HandleInviteClicked") },
		{ TEXT("LEAVE GAME"), TEXT("HandleLeaveClicked") },
	};
	bPassed &= ValidateButtonSurface(*this, SessionBrowser, TEXT("Multiplayer browser"), SessionBindings);

	URedSessionResultButton* ResultButton = NewObject<URedSessionResultButton>();
	ResultButton->InitializeResultButton(7);
	bPassed &= TestEqual(TEXT("Dynamic session row retains its search index"), ResultButton->SearchIndex, 7);
	bPassed &= TestTrue(TEXT("Dynamic session row click has an internal forwarding route"),
		ResultButton->OnClicked.Contains(ResultButton, TEXT("HandleInternalClick")));
	bPassed &= TestNotNull(TEXT("Multiplayer browser exposes the result-selection receiver"),
		SessionBrowser->FindFunction(TEXT("HandleResultSelected")));

	UVibeMMOHUDWidget* HUD = NewObject<UVibeMMOHUDWidget>();
	bPassed &= TestTrue(TEXT("Gameplay HUD initializes without PIE"), HUD->Initialize());
	HUD->RebuildDefaultHUDLayout();
	const TArray<FExpectedBinding> HUDBindings = {
		{ TEXT("SWAP Q / E"), TEXT("HandleAbilityLoadoutSwapClicked") },
	};
	bPassed &= ValidateButtonSurface(*this, HUD, TEXT("Gameplay HUD"), HUDBindings);

	HUD->SetAbilityLoadoutOverlayVisible(true, true);
	bPassed &= TestEqual(TEXT("Opening the loadout keeps child buttons hit-testable"),
		HUD->GetVisibility(), ESlateVisibility::SelfHitTestInvisible);
	HUD->SetAbilityLoadoutOverlayVisible(false, true);
	bPassed &= TestEqual(TEXT("Closing the loadout restores the passive combat HUD"),
		HUD->GetVisibility(), ESlateVisibility::HitTestInvisible);

	bPassed &= TestTrue(TEXT("HUD opacity command mutates the selected element"),
		HUD->SetHUDElementOpacity(EVibeMMOHUDElement::StatusPanel, 0.55f));
	bPassed &= TestTrue(TEXT("HUD opacity command stores the requested value"),
		FMath::IsNearlyEqual(
			HUD->GetHUDElementLayout(EVibeMMOHUDElement::StatusPanel).Opacity, 0.55f));
	bPassed &= TestFalse(TEXT("Repeating an identical HUD mutation reports a no-op"),
		HUD->SetHUDElementOpacity(EVibeMMOHUDElement::StatusPanel, 0.55f));
	bPassed &= TestTrue(TEXT("HUD lock command changes state"),
		HUD->SetHUDElementLocked(EVibeMMOHUDElement::StatusPanel, true));
	bPassed &= TestFalse(TEXT("Locked HUD element rejects movement"),
		HUD->NudgeHUDElement(EVibeMMOHUDElement::StatusPanel, FVector2D(0.01f, 0.0f)));
	bPassed &= TestTrue(TEXT("HUD unlock command changes state"),
		HUD->SetHUDElementLocked(EVibeMMOHUDElement::StatusPanel, false));
	bPassed &= TestTrue(TEXT("Reset element command restores a modified element"),
		HUD->ResetHUDElement(EVibeMMOHUDElement::StatusPanel));
	bPassed &= TestTrue(TEXT("Reset element command restores defaults"),
		HUD->GetHUDElementLayout(EVibeMMOHUDElement::StatusPanel).IsDefault());
	bPassed &= TestFalse(TEXT("Resetting an already-default element reports a no-op"),
		HUD->ResetHUDElement(EVibeMMOHUDElement::StatusPanel));
	bPassed &= TestFalse(TEXT("Reset-all reports a no-op when every element is already default"),
		HUD->ResetAllHUDElements());

	return bPassed;
}

#endif // WITH_DEV_AUTOMATION_TESTS
