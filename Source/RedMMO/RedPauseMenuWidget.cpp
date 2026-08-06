#include "RedPauseMenuWidget.h"

#include "RedHUD.h"
#include "RedGameInstance.h"
#include "RedPlayerCharacter.h"
#include "Blueprint/WidgetTree.h"
#include "Components/BackgroundBlur.h"
#include "Components/Border.h"
#include "Components/Button.h"
#include "Components/ButtonSlot.h"
#include "Components/CanvasPanel.h"
#include "Components/CanvasPanelSlot.h"
#include "Components/HorizontalBox.h"
#include "Components/HorizontalBoxSlot.h"
#include "Components/Image.h"
#include "Components/Overlay.h"
#include "Components/OverlaySlot.h"
#include "Components/ScaleBox.h"
#include "Components/SizeBox.h"
#include "Components/Spacer.h"
#include "Components/TextBlock.h"
#include "Components/VerticalBox.h"
#include "Components/VerticalBoxSlot.h"
#include "Components/WidgetSwitcher.h"
#include "Engine/Engine.h"
#include "Engine/LocalPlayer.h"
#include "GameFramework/GameUserSettings.h"
#include "Engine/Texture2D.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "GameFramework/PlayerController.h"
#include "InputCoreTypes.h"
#include "Kismet/KismetSystemLibrary.h"
#include "Persistence/VibeMMOHUDLayoutSubsystem.h"
#include "RedHUDWidget.h"
#include "Widgets/VibeMMOScreenWidgets.h"

namespace RedPauseMenu
{
	static const FLinearColor Ink(0.008f, 0.015f, 0.03f, 0.96f);
	static const FLinearColor Panel(0.018f, 0.038f, 0.07f, 0.95f);
	static const FLinearColor PanelSoft(0.025f, 0.065f, 0.11f, 0.92f);
	static const FLinearColor Cyan(0.18f, 0.86f, 1.0f, 1.0f);
	static const FLinearColor CyanSoft(0.08f, 0.38f, 0.52f, 0.9f);
	static const FLinearColor Gold(1.0f, 0.72f, 0.18f, 1.0f);
	static const FLinearColor Purple(0.70f, 0.30f, 1.0f, 1.0f);
	static const FLinearColor Body(0.76f, 0.84f, 0.93f, 1.0f);
	static const FLinearColor Muted(0.48f, 0.60f, 0.70f, 1.0f);

	static FString GetHUDElementLabel(const EVibeMMOHUDElement Element)
	{
		switch (Element)
		{
		case EVibeMMOHUDElement::StatusPanel: return TEXT("PLAYER STATUS");
		case EVibeMMOHUDElement::Compass: return TEXT("COMPASS");
		case EVibeMMOHUDElement::Minimap: return TEXT("MINIMAP / RADAR");
		case EVibeMMOHUDElement::AbilityBar: return TEXT("ABILITY BAR");
		case EVibeMMOHUDElement::WeaponStack: return TEXT("WEAPON STACK");
		case EVibeMMOHUDElement::PartyPanel: return TEXT("PARTY PANEL");
		case EVibeMMOHUDElement::EnemyPanel: return TEXT("ENEMY PANEL");
		case EVibeMMOHUDElement::UtilityBar: return TEXT("UTILITY BAR");
		default: return TEXT("HUD ELEMENT");
		}
	}

	static const TArray<EVibeMMOHUDElement>& GetReplacementHUDElements()
	{
		// Reticle is intentionally excluded until URedHUDWidget maps it to a real
		// replacement widget. Do not present a customization control that is a no-op.
		static const TArray<EVibeMMOHUDElement> Elements = {
			EVibeMMOHUDElement::StatusPanel,
			EVibeMMOHUDElement::Compass,
			EVibeMMOHUDElement::Minimap,
			EVibeMMOHUDElement::AbilityBar,
			EVibeMMOHUDElement::WeaponStack,
			EVibeMMOHUDElement::PartyPanel,
			EVibeMMOHUDElement::EnemyPanel,
			EVibeMMOHUDElement::UtilityBar
		};
		return Elements;
	}

	static void AddCanvasFill(UCanvasPanel* Canvas, UWidget* Widget)
	{
		if (UCanvasPanelSlot* Slot = Canvas ? Canvas->AddChildToCanvas(Widget) : nullptr)
		{
			Slot->SetAnchors(FAnchors(0.0f, 0.0f, 1.0f, 1.0f));
			Slot->SetOffsets(FMargin(0.0f));
		}
	}

	static void AddVertical(UVerticalBox* Box, UWidget* Widget, const FMargin Padding = FMargin(0.0f),
		const ESlateSizeRule::Type SizeRule = ESlateSizeRule::Automatic)
	{
		if (UVerticalBoxSlot* Slot = Box ? Box->AddChildToVerticalBox(Widget) : nullptr)
		{
			Slot->SetPadding(Padding);
			Slot->SetHorizontalAlignment(HAlign_Fill);
			Slot->SetVerticalAlignment(VAlign_Center);
			Slot->SetSize(SizeRule == ESlateSizeRule::Fill ? FSlateChildSize(ESlateSizeRule::Fill) : FSlateChildSize(ESlateSizeRule::Automatic));
		}
	}

	static UBorder* MakeCard(UWidgetTree* Tree, const FLinearColor& Tint, const FMargin Padding = FMargin(24.0f))
	{
		UBorder* Card = Tree->ConstructWidget<UBorder>();
		Card->SetBrushColor(Tint);
		Card->SetPadding(Padding);
		return Card;
	}
}

TSharedRef<SWidget> URedEmbeddedInventoryWidget::RebuildWidget()
{
	// UVibeMMOInventoryWidget normally receives its root from a WBP.  This
	// embedded native variant asks it to build its supplied C++ tree first.
	NativePreConstruct();
	ApplyGridLabelPolish();
	ApplyInventoryLayoutPolish();
	BuildResourceLedger();
	RefreshResourceLedger();
	return Super::RebuildWidget();
}

void URedEmbeddedInventoryWidget::ApplyGridLabelPolish()
{
	if (!WidgetTree)
	{
		return;
	}

	// The kit's compact 58 px slots cannot carry repeated EMPTY text or
	// resource names cleanly at 1280x720. Keep every slot, border, icon,
	// tooltip, category filter, selection, and detail-panel label functional;
	// suppress only the in-slot placeholder text. Render opacity persists when
	// the base widget refreshes placeholder text or visibility after a category
	// change, so this remains a one-time presentation override.
	for (int32 Index = 0; Index < InventoryCapacity; ++Index)
	{
		UTextBlock* GridLabel = Cast<UTextBlock>(WidgetTree->FindWidget(
			*FString::Printf(TEXT("InventorySlotPlaceholder_%d"), Index)));
		if (GridLabel)
		{
			GridLabel->SetRenderOpacity(0.0f);
		}
	}
}

void URedEmbeddedInventoryWidget::ApplyInventoryLayoutPolish()
{
	if (!WidgetTree)
	{
		return;
	}

	// Keep the compact storage state on one line inside the supplied detail
	// panel. The selected resource already has a dedicated quantity ledger, so
	// this label must not grow into a second, oversized inventory readout.
	if (RarityLabelText)
	{
		RarityLabelText->SetAutoWrapText(false);
		FSlateFontInfo RarityFont = RarityLabelText->GetFont();
		RarityFont.Size = 14;
		RarityLabelText->SetFont(RarityFont);
	}

	// The kit's default 26 px gap per category makes the final Consumables tab
	// overrun its 540 px canvas allocation. Give the tabs a little more width
	// and use a compact, even gap while retaining all four supplied buttons.
	UHorizontalBox* Tabs = WidgetTree->FindWidget<UHorizontalBox>(
		FName(TEXT("InventoryTabs")));
	if (Tabs)
	{
		if (UCanvasPanelSlot* TabsSlot = Cast<UCanvasPanelSlot>(Tabs->Slot))
		{
			TabsSlot->SetSize(FVector2D(580.0f, 40.0f));
		}
		for (int32 Index = 0; Index < 4; ++Index)
		{
			UButton* TabButton = WidgetTree->FindWidget<UButton>(
				*FString::Printf(TEXT("InventoryCategoryButton_%d"), Index));
			if (TabButton)
			{
				if (UHorizontalBoxSlot* TabSlot =
						Cast<UHorizontalBoxSlot>(TabButton->Slot))
				{
					TabSlot->SetPadding(FMargin(0.0f, 0.0f, 12.0f, 0.0f));
				}
			}
		}
	}
}

void URedEmbeddedInventoryWidget::SetResourceTotals(
	const int32 Stone, const int32 Iron, const int32 Crystal)
{
	CachedStone = FMath::Max(0, Stone);
	CachedIron = FMath::Max(0, Iron);
	CachedCrystal = FMath::Max(0, Crystal);
	RefreshResourceLedger();
}

bool URedEmbeddedInventoryWidget::GetResourceTotals(
	int32& OutStone, int32& OutIron, int32& OutCrystal,
	FString& OutSummary) const
{
	OutStone = CachedStone;
	OutIron = CachedIron;
	OutCrystal = CachedCrystal;
	OutSummary = FString::Printf(
		TEXT("STONE %d | IRON %d | CRYSTAL %d"),
		CachedStone, CachedIron, CachedCrystal);
	return true;
}

FName URedEmbeddedInventoryWidget::GetControllerCategoryWidgetName(
	const int32 CategoryIndex) const
{
	return CategoryIndex >= 0 && CategoryIndex <= 3
		? FName(*FString::Printf(TEXT("InventoryCategoryButton_%d"), CategoryIndex))
		: NAME_None;
}

FName URedEmbeddedInventoryWidget::GetControllerVisibleSlotWidgetName(
	const int32 VisualSlotIndex) const
{
	return VisualSlotIndex >= 0 && VisualSlotIndex < InventoryCapacity
		? FName(*FString::Printf(TEXT("InventorySlotButton_%d"), VisualSlotIndex))
		: NAME_None;
}

bool URedEmbeddedInventoryWidget::FocusControllerCategory(
	const int32 CategoryIndex, APlayerController* PlayerController)
{
	const FName WidgetName = GetControllerCategoryWidgetName(CategoryIndex);
	UButton* CategoryButton = WidgetTree && !WidgetName.IsNone()
		? WidgetTree->FindWidget<UButton>(WidgetName) : nullptr;
	if (!CategoryButton || !CategoryButton->GetIsEnabled())
	{
		return false;
	}

	if (PlayerController)
	{
		CategoryButton->SetUserFocus(PlayerController);
	}
	else
	{
		CategoryButton->SetKeyboardFocus();
	}
	return true;
}

bool URedEmbeddedInventoryWidget::ActivateControllerCategory(
	const int32 CategoryIndex)
{
	if (CategoryIndex < 0 || CategoryIndex > 3)
	{
		return false;
	}

	SetInventoryCategory(static_cast<EVibeMMOInventoryCategory>(CategoryIndex));
	return GetInventoryCategory()
		== static_cast<EVibeMMOInventoryCategory>(CategoryIndex);
}

bool URedEmbeddedInventoryWidget::FocusControllerVisibleSlot(
	const int32 VisualSlotIndex, APlayerController* PlayerController)
{
	const TArray<int32> VisibleIndices = GetVisibleInventoryItemIndices();
	const FName WidgetName = GetControllerVisibleSlotWidgetName(VisualSlotIndex);
	UVibeMMOInventorySlotButton* SlotButton =
		WidgetTree && VisibleIndices.IsValidIndex(VisualSlotIndex)
			&& !WidgetName.IsNone()
		? WidgetTree->FindWidget<UVibeMMOInventorySlotButton>(WidgetName)
		: nullptr;
	if (!SlotButton || !SlotButton->GetIsEnabled()
		|| SlotButton->GetStableItemIndex() != VisibleIndices[VisualSlotIndex])
	{
		return false;
	}

	if (PlayerController)
	{
		SlotButton->SetUserFocus(PlayerController);
	}
	else
	{
		SlotButton->SetKeyboardFocus();
	}
	return true;
}

bool URedEmbeddedInventoryWidget::ActivateControllerVisibleSlot(
	const int32 VisualSlotIndex)
{
	const TArray<int32> VisibleIndices = GetVisibleInventoryItemIndices();
	const FName WidgetName = GetControllerVisibleSlotWidgetName(VisualSlotIndex);
	UVibeMMOInventorySlotButton* SlotButton =
		WidgetTree && VisibleIndices.IsValidIndex(VisualSlotIndex)
			&& !WidgetName.IsNone()
		? WidgetTree->FindWidget<UVibeMMOInventorySlotButton>(WidgetName)
		: nullptr;
	if (!SlotButton || !SlotButton->GetIsEnabled()
		|| SlotButton->GetStableItemIndex() != VisibleIndices[VisualSlotIndex])
	{
		return false;
	}

	SlotButton->OnClicked.Broadcast();
	return GetSelectedInventoryItemIndex() == VisibleIndices[VisualSlotIndex];
}

void URedEmbeddedInventoryWidget::BuildResourceLedger()
{
	if (!WidgetTree
		|| (IsValid(StoneQuantityText)
			&& IsValid(IronQuantityText)
			&& IsValid(CrystalQuantityText)))
	{
		return;
	}

	UCanvasPanel* ContentCanvas = Cast<UCanvasPanel>(
		WidgetTree->FindWidget(FName(TEXT("InventoryContentCanvas"))));
	if (!ContentCanvas)
	{
		return;
	}

	UHorizontalBox* Ledger = WidgetTree->ConstructWidget<UHorizontalBox>(
		UHorizontalBox::StaticClass(), TEXT("RedResourceQuantityLedger"));
	if (UCanvasPanelSlot* LedgerSlot = ContentCanvas->AddChildToCanvas(Ledger))
	{
		// The supplied inventory leaves this upper-right band open above its
		// detail panel. Quantities therefore stay inside Inventory without
		// covering its category tabs, item grid, or always-on gameplay HUD.
		LedgerSlot->SetPosition(FVector2D(630.0f, 0.0f));
		LedgerSlot->SetSize(FVector2D(280.0f, 88.0f));
	}

	auto AddResourceCard = [this, Ledger](
		const TCHAR* WidgetPrefix,
		const TCHAR* LabelText,
		const FLinearColor& AccentColor,
		TObjectPtr<UTextBlock>& OutQuantity)
	{
		UBorder* Card = WidgetTree->ConstructWidget<UBorder>(
			UBorder::StaticClass(),
			*FString::Printf(TEXT("%sCard"), WidgetPrefix));
		Card->SetBrushColor(FLinearColor(
			AccentColor.R * 0.16f,
			AccentColor.G * 0.16f,
			AccentColor.B * 0.16f,
			0.96f));
		Card->SetPadding(FMargin(8.0f, 7.0f));
		Card->SetToolTipText(FText::FromString(
			FString::Printf(TEXT("Authoritative stored %s quantity"), LabelText)));
		if (UHorizontalBoxSlot* CardSlot = Ledger->AddChildToHorizontalBox(Card))
		{
			CardSlot->SetSize(FSlateChildSize(ESlateSizeRule::Fill));
			CardSlot->SetPadding(FMargin(3.0f));
			CardSlot->SetHorizontalAlignment(HAlign_Fill);
			CardSlot->SetVerticalAlignment(VAlign_Fill);
		}

		UVerticalBox* Stack = WidgetTree->ConstructWidget<UVerticalBox>(
			UVerticalBox::StaticClass(),
			*FString::Printf(TEXT("%sStack"), WidgetPrefix));
		Card->SetContent(Stack);

		UTextBlock* Label = WidgetTree->ConstructWidget<UTextBlock>(
			UTextBlock::StaticClass(),
			*FString::Printf(TEXT("%sLabel"), WidgetPrefix));
		Label->SetText(FText::FromString(LabelText));
		Label->SetJustification(ETextJustify::Center);
		Label->SetColorAndOpacity(FSlateColor(AccentColor));
		FSlateFontInfo LabelFont = Label->GetFont();
		LabelFont.Size = 10;
		Label->SetFont(LabelFont);
		RedPauseMenu::AddVertical(Stack, Label);

		UTextBlock* Quantity = WidgetTree->ConstructWidget<UTextBlock>(
			UTextBlock::StaticClass(),
			*FString::Printf(TEXT("%sQuantity"), WidgetPrefix));
		Quantity->SetText(FText::FromString(TEXT("0")));
		Quantity->SetJustification(ETextJustify::Center);
		Quantity->SetColorAndOpacity(FSlateColor(FLinearColor::White));
		FSlateFontInfo QuantityFont = Quantity->GetFont();
		QuantityFont.Size = 22;
		Quantity->SetFont(QuantityFont);
		RedPauseMenu::AddVertical(Stack, Quantity);
		OutQuantity = Quantity;
	};

	AddResourceCard(
		TEXT("RedStone"), TEXT("STONE"),
		FLinearColor(0.56f, 0.70f, 0.82f, 1.0f), StoneQuantityText);
	AddResourceCard(
		TEXT("RedIron"), TEXT("IRON"),
		RedPauseMenu::Gold, IronQuantityText);
	AddResourceCard(
		TEXT("RedCrystal"), TEXT("CRYSTAL"),
		RedPauseMenu::Purple, CrystalQuantityText);
}

void URedEmbeddedInventoryWidget::RefreshResourceLedger()
{
	auto PublishQuantity = [](UTextBlock* QuantityText, const int32 Quantity)
	{
		if (!QuantityText)
		{
			return;
		}

		QuantityText->SetText(FText::AsNumber(Quantity));
		// These cards are appended to the kit's native tree during RebuildWidget.
		// Push the changed property into the already-painted Slate text explicitly
		// so an in-place mining refresh cannot retain the previous glyph run.
		QuantityText->SynchronizeProperties();
		QuantityText->InvalidateLayoutAndVolatility();
	};

	PublishQuantity(StoneQuantityText, CachedStone);
	PublishQuantity(IronQuantityText, CachedIron);
	PublishQuantity(CrystalQuantityText, CachedCrystal);
}

URedPauseMenuWidget::URedPauseMenuWidget(const FObjectInitializer& ObjectInitializer)
	: Super(ObjectInitializer)
{
	SetIsFocusable(true);
}

void URedPauseMenuWidget::InitializeForHUD(ARedHUD* InOwnerHUD)
{
	OwnerHUD = InOwnerHUD;
}

TSharedRef<SWidget> URedPauseMenuWidget::RebuildWidget()
{
	SetIsFocusable(true);
	BuildMenuTree();
	return Super::RebuildWidget();
}

void URedPauseMenuWidget::NativeOnInitialized()
{
	Super::NativeOnInitialized();
	BuildMenuTree();
}

void URedPauseMenuWidget::NativeConstruct()
{
	Super::NativeConstruct();

	// Populate the kit-native inventory with the two real carried weapon cards.
	// The inventory shell stays useful now while remaining ready for the future
	// persistent item backend.
	if (InventoryWidget)
	{
		FVibeMMOInventoryItemPresentation EnergyRifle;
		EnergyRifle.bIsPopulated = true;
		EnergyRifle.Category = EVibeMMOInventoryCategory::Weapons;
		EnergyRifle.DisplayName = FText::FromString(TEXT("ENERGY RIFLE"));
		EnergyRifle.Rarity = FText::FromString(TEXT("EPIC"));
		EnergyRifle.Description = FText::FromString(
			TEXT("Primary energy weapon. Sustained fire builds heat; release the trigger to cool it."));
		EnergyRifle.IconResource = LoadObject<UTexture2D>(
			nullptr, TEXT("/Game/RedMMO/UI/Generated/weapon_slot_epic.weapon_slot_epic"));
		EnergyRifle.RarityColor = RedPauseMenu::Purple;
		InventoryWidget->SetInventoryItemPresentation(0, EnergyRifle);

		FVibeMMOInventoryItemPresentation BallisticRifle;
		BallisticRifle.bIsPopulated = true;
		BallisticRifle.Category = EVibeMMOInventoryCategory::Weapons;
		BallisticRifle.DisplayName = FText::FromString(TEXT("BALLISTIC RIFLE"));
		BallisticRifle.Rarity = FText::FromString(TEXT("LEGENDARY"));
		BallisticRifle.Description = FText::FromString(
			TEXT("High-impact rifle with a distinct projectile profile and its own heat cooldown."));
		BallisticRifle.IconResource = LoadObject<UTexture2D>(
			nullptr, TEXT("/Game/RedMMO/UI/Generated/weapon_slot_legendary.weapon_slot_legendary"));
		BallisticRifle.RarityColor = RedPauseMenu::Gold;
		InventoryWidget->SetInventoryItemPresentation(1, BallisticRifle);

		InventoryWidget->SetInventoryCategory(EVibeMMOInventoryCategory::All);
		InventoryWidget->SelectInventoryItem(0);
		RefreshInventoryResources();
	}
}

FReply URedPauseMenuWidget::NativeOnPreviewKeyDown(
	const FGeometry& InGeometry, const FKeyEvent& InKeyEvent)
{
	if (InKeyEvent.GetKey().IsGamepadKey()
		&& RouteControllerKey(InKeyEvent.GetKey(), InKeyEvent.IsRepeat()))
	{
		return FReply::Handled();
	}
	return Super::NativeOnPreviewKeyDown(InGeometry, InKeyEvent);
}

FReply URedPauseMenuWidget::NativeOnKeyDown(const FGeometry& InGeometry, const FKeyEvent& InKeyEvent)
{
	if (InKeyEvent.GetKey() == EKeys::Escape)
	{
		HandleResume();
		return FReply::Handled();
	}
	return Super::NativeOnKeyDown(InGeometry, InKeyEvent);
}

UTextBlock* URedPauseMenuWidget::MakeText(const FString& Text, const int32 Size,
	const FLinearColor& Color, const bool bWrap)
{
	UTextBlock* Label = WidgetTree->ConstructWidget<UTextBlock>();
	Label->SetText(FText::FromString(Text));
	Label->SetColorAndOpacity(FSlateColor(Color));
	Label->SetAutoWrapText(bWrap);
	FSlateFontInfo Font = Label->GetFont();
	Font.Size = Size;
	Label->SetFont(Font);
	return Label;
}

UButton* URedPauseMenuWidget::MakeMenuButton(const FString& Label, UTextBlock*& OutLabel,
	const FLinearColor& Tint)
{
	UButton* Button = WidgetTree->ConstructWidget<UButton>();
	Button->SetBackgroundColor(Tint);
	Button->SetColorAndOpacity(FLinearColor::White);
	OutLabel = MakeText(Label, 17, FLinearColor::White);
	OutLabel->SetJustification(ETextJustify::Left);
	if (UButtonSlot* ContentSlot = Cast<UButtonSlot>(Button->SetContent(OutLabel)))
	{
		ContentSlot->SetPadding(FMargin(20.0f, 13.0f));
		ContentSlot->SetHorizontalAlignment(HAlign_Fill);
		ContentSlot->SetVerticalAlignment(VAlign_Center);
	}
	return Button;
}

void URedPauseMenuWidget::BuildMenuTree()
{
	if (!WidgetTree || bMenuTreeBuilt)
	{
		return;
	}

	UCanvasPanel* Root = WidgetTree->ConstructWidget<UCanvasPanel>(UCanvasPanel::StaticClass(), TEXT("RedPauseRoot"));
	WidgetTree->RootWidget = Root;

	UBackgroundBlur* Blur = WidgetTree->ConstructWidget<UBackgroundBlur>();
	Blur->SetBlurStrength(20.0f);
	Blur->SetBlurRadius(10);
	Blur->SetOverrideAutoRadiusCalculation(true);
	RedPauseMenu::AddCanvasFill(Root, Blur);

	UBorder* Backdrop = WidgetTree->ConstructWidget<UBorder>();
	Backdrop->SetBrushColor(FLinearColor(0.0f, 0.005f, 0.015f, 0.68f));
	RedPauseMenu::AddCanvasFill(Root, Backdrop);

	UScaleBox* WindowScale = WidgetTree->ConstructWidget<UScaleBox>();
	WindowScale->SetStretch(EStretch::ScaleToFit);
	WindowScale->SetStretchDirection(EStretchDirection::DownOnly);
	if (UCanvasPanelSlot* WindowCanvasSlot = Root->AddChildToCanvas(WindowScale))
	{
		WindowCanvasSlot->SetAnchors(FAnchors(0.0f, 0.0f, 1.0f, 1.0f));
		WindowCanvasSlot->SetOffsets(FMargin(32.0f, 32.0f, -32.0f, -32.0f));
	}

	USizeBox* WindowSize = WidgetTree->ConstructWidget<USizeBox>();
	WindowSize->SetWidthOverride(1420.0f);
	WindowSize->SetHeightOverride(820.0f);
	WindowScale->SetContent(WindowSize);

	UBorder* WindowBorder = RedPauseMenu::MakeCard(WidgetTree, RedPauseMenu::CyanSoft, FMargin(2.0f));
	WindowSize->SetContent(WindowBorder);
	UBorder* WindowFill = RedPauseMenu::MakeCard(WidgetTree, RedPauseMenu::Ink, FMargin(0.0f));
	WindowBorder->SetContent(WindowFill);

	UVerticalBox* WindowStack = WidgetTree->ConstructWidget<UVerticalBox>();
	WindowFill->SetContent(WindowStack);

	UBorder* Header = RedPauseMenu::MakeCard(WidgetTree, RedPauseMenu::PanelSoft, FMargin(30.0f, 17.0f));
	RedPauseMenu::AddVertical(WindowStack, Header);
	UHorizontalBox* HeaderRow = WidgetTree->ConstructWidget<UHorizontalBox>();
	Header->SetContent(HeaderRow);
	UTextBlock* Brand = MakeText(TEXT("RED FRONTIER"), 30, FLinearColor::White);
	if (UHorizontalBoxSlot* BrandSlot = HeaderRow->AddChildToHorizontalBox(Brand))
	{
		BrandSlot->SetSize(FSlateChildSize(ESlateSizeRule::Fill));
		BrandSlot->SetVerticalAlignment(VAlign_Center);
	}
	SessionStateText = MakeText(TEXT("ONLINE SESSION  |  WORLD CONTINUES"), 15, RedPauseMenu::Cyan);
	if (UHorizontalBoxSlot* SessionSlot = HeaderRow->AddChildToHorizontalBox(SessionStateText))
	{
		SessionSlot->SetHorizontalAlignment(HAlign_Right);
		SessionSlot->SetVerticalAlignment(VAlign_Center);
	}

	UHorizontalBox* Body = WidgetTree->ConstructWidget<UHorizontalBox>();
	RedPauseMenu::AddVertical(WindowStack, Body, FMargin(0.0f), ESlateSizeRule::Fill);

	USizeBox* NavSize = WidgetTree->ConstructWidget<USizeBox>();
	NavSize->SetWidthOverride(286.0f);
	if (UHorizontalBoxSlot* NavOuterSlot = Body->AddChildToHorizontalBox(NavSize))
	{
		NavOuterSlot->SetVerticalAlignment(VAlign_Fill);
	}
	UBorder* NavPanel = RedPauseMenu::MakeCard(WidgetTree, RedPauseMenu::Panel, FMargin(20.0f));
	NavSize->SetContent(NavPanel);
	UVerticalBox* Nav = WidgetTree->ConstructWidget<UVerticalBox>();
	NavPanel->SetContent(Nav);

	UTextBlock* MenuLabel = MakeText(TEXT("GAME MENU"), 14, RedPauseMenu::Muted);
	RedPauseMenu::AddVertical(Nav, MenuLabel, FMargin(8.0f, 3.0f, 8.0f, 18.0f));

	PrimaryMenuButtons.Reset();
	UTextBlock* ButtonLabel = nullptr;
	UButton* ResumeButton = MakeMenuButton(TEXT("RESUME"), ButtonLabel, FLinearColor(0.04f, 0.42f, 0.55f, 1.0f));
	ResumeButton->OnClicked.AddDynamic(this, &URedPauseMenuWidget::HandleResume);
	PrimaryMenuButtons.Add(ResumeButton);
	RedPauseMenu::AddVertical(Nav, ResumeButton, FMargin(0.0f, 0.0f, 0.0f, 9.0f));

	UButton* MultiplayerButton = MakeMenuButton(
		TEXT("MULTIPLAYER / LOBBY"), ButtonLabel, FLinearColor(0.04f, 0.48f, 0.34f, 1.0f));
	MultiplayerButton->SetToolTipText(FText::FromString(
		TEXT("Create a Steam game, find a friend's server, join, reconnect, or invite friends")));
	MultiplayerButton->OnClicked.AddDynamic(this, &URedPauseMenuWidget::HandleMultiplayer);
	PrimaryMenuButtons.Add(MultiplayerButton);
	RedPauseMenu::AddVertical(Nav, MultiplayerButton, FMargin(0.0f, 0.0f, 0.0f, 9.0f));

	UButton* OverviewButton = MakeMenuButton(TEXT("OVERVIEW"), ButtonLabel, RedPauseMenu::CyanSoft);
	OverviewButton->OnClicked.AddDynamic(this, &URedPauseMenuWidget::HandleOverview);
	PrimaryMenuButtons.Add(OverviewButton);
	RedPauseMenu::AddVertical(Nav, OverviewButton, FMargin(0.0f, 0.0f, 0.0f, 9.0f));

	UButton* InventoryButton = MakeMenuButton(TEXT("INVENTORY"), ButtonLabel, RedPauseMenu::CyanSoft);
	InventoryButton->OnClicked.AddDynamic(this, &URedPauseMenuWidget::HandleInventory);
	PrimaryMenuButtons.Add(InventoryButton);
	RedPauseMenu::AddVertical(Nav, InventoryButton, FMargin(0.0f, 0.0f, 0.0f, 9.0f));

	CharacterButton = MakeMenuButton(TEXT("CHARACTER"), ButtonLabel,
		FLinearColor(0.16f, 0.28f, 0.46f, 0.95f));
	CharacterButton->SetToolTipText(FText::FromString(
		TEXT("Open the installed modular character creator")));
	CharacterButton->OnClicked.AddDynamic(this, &URedPauseMenuWidget::HandleCharacter);
	PrimaryMenuButtons.Add(CharacterButton);
	RedPauseMenu::AddVertical(Nav, CharacterButton, FMargin(0.0f, 0.0f, 0.0f, 9.0f));

	UButton* SkillsButton = MakeMenuButton(TEXT("SKILLS + LOADOUT"), ButtonLabel, FLinearColor(0.35f, 0.14f, 0.54f, 0.95f));
	SkillsButton->OnClicked.AddDynamic(this, &URedPauseMenuWidget::HandleSkills);
	PrimaryMenuButtons.Add(SkillsButton);
	RedPauseMenu::AddVertical(Nav, SkillsButton, FMargin(0.0f, 0.0f, 0.0f, 9.0f));

	UButton* SettingsButton = MakeMenuButton(TEXT("SETTINGS"), ButtonLabel, RedPauseMenu::CyanSoft);
	SettingsButton->OnClicked.AddDynamic(this, &URedPauseMenuWidget::HandleSettings);
	PrimaryMenuButtons.Add(SettingsButton);
	RedPauseMenu::AddVertical(Nav, SettingsButton, FMargin(0.0f, 0.0f, 0.0f, 9.0f));

	UButton* HUDButton = MakeMenuButton(TEXT("CUSTOMIZE HUD"), ButtonLabel,
		FLinearColor(0.10f, 0.32f, 0.48f, 0.95f));
	HUDButton->SetToolTipText(FText::FromString(
		TEXT("Move, resize, fade, hide, or lock each HUD group independently")));
	HUDButton->OnClicked.AddDynamic(this, &URedPauseMenuWidget::HandleHUDCustomization);
	PrimaryMenuButtons.Add(HUDButton);
	RedPauseMenu::AddVertical(Nav, HUDButton, FMargin(0.0f, 0.0f, 0.0f, 9.0f));

	USpacer* NavSpacer = WidgetTree->ConstructWidget<USpacer>();
	RedPauseMenu::AddVertical(Nav, NavSpacer, FMargin(0.0f), ESlateSizeRule::Fill);

	UTextBlock* ExitLabel = nullptr;
	UButton* ExitButton = MakeMenuButton(TEXT("EXIT TO DESKTOP"), ExitLabel, FLinearColor(0.48f, 0.055f, 0.075f, 1.0f));
	ExitButtonText = ExitLabel;
	ExitButton->OnClicked.AddDynamic(this, &URedPauseMenuWidget::HandleExit);
	PrimaryMenuButtons.Add(ExitButton);
	RedPauseMenu::AddVertical(Nav, ExitButton, FMargin(0.0f, 8.0f));
	UTextBlock* EscapeHint = MakeText(TEXT("ESC / B  Close menu"), 13, RedPauseMenu::Muted);
	RedPauseMenu::AddVertical(Nav, EscapeHint, FMargin(8.0f, 8.0f, 8.0f, 0.0f));

	UBorder* ContentPanel = RedPauseMenu::MakeCard(WidgetTree, RedPauseMenu::PanelSoft, FMargin(28.0f, 20.0f, 28.0f, 28.0f));
	if (UHorizontalBoxSlot* ContentOuterSlot = Body->AddChildToHorizontalBox(ContentPanel))
	{
		ContentOuterSlot->SetSize(FSlateChildSize(ESlateSizeRule::Fill));
		ContentOuterSlot->SetPadding(FMargin(2.0f, 0.0f, 0.0f, 0.0f));
		ContentOuterSlot->SetVerticalAlignment(VAlign_Fill);
	}
	UVerticalBox* ContentStack = WidgetTree->ConstructWidget<UVerticalBox>();
	ContentPanel->SetContent(ContentStack);
	SectionTitleText = MakeText(TEXT("OVERVIEW"), 22, FLinearColor::White);
	RedPauseMenu::AddVertical(ContentStack, SectionTitleText, FMargin(4.0f, 0.0f, 0.0f, 14.0f));
	PageSwitcher = WidgetTree->ConstructWidget<UWidgetSwitcher>();
	RedPauseMenu::AddVertical(ContentStack, PageSwitcher, FMargin(0.0f), ESlateSizeRule::Fill);

	PageSwitcher->AddChild(BuildOverviewPage());
	InventoryWidget = WidgetTree->ConstructWidget<URedEmbeddedInventoryWidget>(URedEmbeddedInventoryWidget::StaticClass(), TEXT("PauseInventoryWidget"));
	PageSwitcher->AddChild(InventoryWidget);
	PageSwitcher->AddChild(BuildSkillsPage());
	PageSwitcher->AddChild(BuildSettingsPage());
	PageSwitcher->AddChild(BuildHUDCustomizationPage());
	PageSwitcher->SetActiveWidgetIndex(0);

	bMenuTreeBuilt = true;
}

UWidget* URedPauseMenuWidget::BuildOverviewPage()
{
	UBorder* Page = RedPauseMenu::MakeCard(WidgetTree, RedPauseMenu::Panel, FMargin(36.0f));
	UVerticalBox* Stack = WidgetTree->ConstructWidget<UVerticalBox>();
	Page->SetContent(Stack);
	RedPauseMenu::AddVertical(Stack, MakeText(TEXT("READY FOR DEPLOYMENT"), 36, RedPauseMenu::Cyan), FMargin(0.0f, 12.0f, 0.0f, 10.0f));
	RedPauseMenu::AddVertical(Stack, MakeText(
		TEXT("Resume the live world, create or join a Steam game, inspect your carried weapons, configure the Q/E combat loadout, or change local graphics settings."),
		18, RedPauseMenu::Body, true), FMargin(0.0f, 0.0f, 80.0f, 34.0f));

	UBorder* Controls = RedPauseMenu::MakeCard(WidgetTree, FLinearColor(0.025f, 0.12f, 0.17f, 0.82f), FMargin(26.0f));
	UVerticalBox* ControlsStack = WidgetTree->ConstructWidget<UVerticalBox>();
	Controls->SetContent(ControlsStack);
	RedPauseMenu::AddVertical(ControlsStack, MakeText(TEXT("QUICK CONTROLS"), 16, RedPauseMenu::Gold), FMargin(0.0f, 0.0f, 0.0f, 12.0f));
	RedPauseMenu::AddVertical(ControlsStack, MakeText(TEXT("TAB   Ability loadout     Q / E   Abilities     1 / 2   Weapons"), 17, FLinearColor::White));
	RedPauseMenu::AddVertical(ControlsStack, MakeText(TEXT("B / V  Nearby craft          F       Direct mini fighter          C       Camera"), 17, FLinearColor::White), FMargin(0.0f, 10.0f, 0.0f, 0.0f));
	RedPauseMenu::AddVertical(ControlsStack, MakeText(TEXT("L      Landing assist          F8      Multiplayer lobby     ESC     Game menu"), 17, FLinearColor::White), FMargin(0.0f, 10.0f, 0.0f, 0.0f));
	RedPauseMenu::AddVertical(Stack, Controls);

	UTextBlock* Safety = MakeText(
		TEXT("ONLINE SAFETY  This menu only captures your local controls. Multiplayer simulation, enemies, ships, and other players continue moving."),
		15, RedPauseMenu::Gold, true);
	RedPauseMenu::AddVertical(Stack, Safety, FMargin(4.0f, 28.0f, 40.0f, 0.0f));
	return Page;
}

UWidget* URedPauseMenuWidget::BuildSkillsPage()
{
	UBorder* Page = RedPauseMenu::MakeCard(WidgetTree, RedPauseMenu::Panel, FMargin(34.0f));
	UVerticalBox* Stack = WidgetTree->ConstructWidget<UVerticalBox>();
	Page->SetContent(Stack);
	RedPauseMenu::AddVertical(Stack, MakeText(TEXT("ACTIVE COMBAT LOADOUT"), 30, RedPauseMenu::Purple), FMargin(0.0f, 8.0f, 0.0f, 8.0f));
	RedPauseMenu::AddVertical(Stack, MakeText(
		TEXT("The two equipped abilities are replicated to the server and activate from Q and E while on foot."),
		17, RedPauseMenu::Body, true), FMargin(0.0f, 0.0f, 80.0f, 24.0f));

	UHorizontalBox* Cards = WidgetTree->ConstructWidget<UHorizontalBox>();
	RedPauseMenu::AddVertical(Stack, Cards, FMargin(0.0f, 0.0f, 0.0f, 24.0f));
	for (int32 Index = 0; Index < 2; ++Index)
	{
		UBorder* Card = RedPauseMenu::MakeCard(WidgetTree,
			Index == 0 ? FLinearColor(0.03f, 0.30f, 0.48f, 0.92f) : FLinearColor(0.45f, 0.12f, 0.055f, 0.92f),
			FMargin(24.0f));
		if (UHorizontalBoxSlot* CardSlot = Cards->AddChildToHorizontalBox(Card))
		{
			CardSlot->SetSize(FSlateChildSize(ESlateSizeRule::Fill));
			CardSlot->SetPadding(Index == 0 ? FMargin(0.0f, 0.0f, 10.0f, 0.0f) : FMargin(10.0f, 0.0f, 0.0f, 0.0f));
		}
		UVerticalBox* CardStack = WidgetTree->ConstructWidget<UVerticalBox>();
		Card->SetContent(CardStack);
		UTextBlock* Key = MakeText(Index == 0 ? TEXT("Q") : TEXT("E"), 36, FLinearColor::White);
		RedPauseMenu::AddVertical(CardStack, Key, FMargin(0.0f, 0.0f, 0.0f, 8.0f));
		UTextBlock* Ability = MakeText(Index == 0 ? TEXT("GRAPPLE") : TEXT("KINETIC SLAM"), 22,
			Index == 0 ? RedPauseMenu::Cyan : RedPauseMenu::Gold);
		RedPauseMenu::AddVertical(CardStack, Ability);
		if (Index == 0)
		{
			AbilityQText = Ability;
		}
		else
		{
			AbilityEText = Ability;
		}
	}

	UTextBlock* OpenLabel = nullptr;
	UButton* OpenLoadout = MakeMenuButton(TEXT("OPEN INTERACTIVE LOADOUT"), OpenLabel, FLinearColor(0.42f, 0.18f, 0.64f, 1.0f));
	OpenLabel->SetJustification(ETextJustify::Center);
	OpenLoadout->OnClicked.AddDynamic(this, &URedPauseMenuWidget::HandleOpenAbilityLoadout);
	RedPauseMenu::AddVertical(Stack, OpenLoadout, FMargin(0.0f, 0.0f, 460.0f, 12.0f));
	SkillsHelpText = MakeText(TEXT("You can also press TAB at any time on foot."), 14, RedPauseMenu::Muted, true);
	RedPauseMenu::AddVertical(Stack, SkillsHelpText);
	return Page;
}

UWidget* URedPauseMenuWidget::BuildSettingsPage()
{
	UBorder* Page = RedPauseMenu::MakeCard(WidgetTree, RedPauseMenu::Panel, FMargin(36.0f));
	UVerticalBox* Stack = WidgetTree->ConstructWidget<UVerticalBox>();
	Page->SetContent(Stack);
	RedPauseMenu::AddVertical(Stack, MakeText(TEXT("DISPLAY + QUALITY"), 30, RedPauseMenu::Cyan), FMargin(0.0f, 8.0f, 0.0f, 10.0f));
	RedPauseMenu::AddVertical(Stack, MakeText(
		TEXT("Changes apply locally and are saved by Unreal's game-user settings. They do not alter the server."),
		16, RedPauseMenu::Body, true), FMargin(0.0f, 0.0f, 80.0f, 24.0f));

	GraphicsStatusText = MakeText(TEXT("CURRENT QUALITY"), 16, RedPauseMenu::Gold);
	RedPauseMenu::AddVertical(Stack, GraphicsStatusText, FMargin(0.0f, 0.0f, 0.0f, 18.0f));

	UTextBlock* Label = nullptr;
	UButton* Performance = MakeMenuButton(TEXT("PERFORMANCE"), Label, FLinearColor(0.04f, 0.24f, 0.32f, 1.0f));
	Performance->OnClicked.AddDynamic(this, &URedPauseMenuWidget::HandlePerformanceQuality);
	RedPauseMenu::AddVertical(Stack, Performance, FMargin(0.0f, 0.0f, 520.0f, 10.0f));
	UButton* Balanced = MakeMenuButton(TEXT("BALANCED"), Label, FLinearColor(0.04f, 0.34f, 0.42f, 1.0f));
	Balanced->OnClicked.AddDynamic(this, &URedPauseMenuWidget::HandleBalancedQuality);
	RedPauseMenu::AddVertical(Stack, Balanced, FMargin(0.0f, 0.0f, 520.0f, 10.0f));
	UButton* Cinematic = MakeMenuButton(TEXT("CINEMATIC"), Label, FLinearColor(0.31f, 0.19f, 0.50f, 1.0f));
	Cinematic->OnClicked.AddDynamic(this, &URedPauseMenuWidget::HandleCinematicQuality);
	RedPauseMenu::AddVertical(Stack, Cinematic, FMargin(0.0f, 0.0f, 520.0f, 24.0f));
	UButton* WindowMode = MakeMenuButton(TEXT("TOGGLE FULLSCREEN / WINDOWED"), Label, RedPauseMenu::CyanSoft);
	WindowMode->OnClicked.AddDynamic(this, &URedPauseMenuWidget::HandleToggleWindowMode);
	RedPauseMenu::AddVertical(Stack, WindowMode, FMargin(0.0f, 0.0f, 360.0f, 0.0f));
	return Page;
}

UWidget* URedPauseMenuWidget::BuildHUDCustomizationPage()
{
	UBorder* Page = RedPauseMenu::MakeCard(WidgetTree, RedPauseMenu::Panel, FMargin(32.0f));
	UVerticalBox* Stack = WidgetTree->ConstructWidget<UVerticalBox>();
	Page->SetContent(Stack);
	RedPauseMenu::AddVertical(Stack, MakeText(TEXT("HUD CUSTOMIZATION"), 30, FLinearColor::White),
		FMargin(0.0f, 4.0f, 0.0f, 6.0f));
	RedPauseMenu::AddVertical(Stack, MakeText(
		TEXT("Every HUD group has its own position, size, opacity, visibility, and lock state. Changes preview immediately; APPLY writes this local player's layout."),
		15, RedPauseMenu::Body, true), FMargin(0.0f, 0.0f, 80.0f, 12.0f));

	HUDSelectedElementText = MakeText(TEXT("STATUS PANEL"), 22, RedPauseMenu::Cyan);
	RedPauseMenu::AddVertical(Stack, HUDSelectedElementText, FMargin(0.0f, 0.0f, 0.0f, 8.0f));

	auto AddButtonToRow = [this](UHorizontalBox* Row, UButton* Button)
	{
		if (UHorizontalBoxSlot* Slot = Row->AddChildToHorizontalBox(Button))
		{
			Slot->SetSize(FSlateChildSize(ESlateSizeRule::Fill));
			Slot->SetPadding(FMargin(4.0f));
			Slot->SetVerticalAlignment(VAlign_Center);
		}
	};
	auto AddRow = [this, Stack]()
	{
		UHorizontalBox* Row = WidgetTree->ConstructWidget<UHorizontalBox>();
		RedPauseMenu::AddVertical(Stack, Row, FMargin(0.0f, 0.0f, 0.0f, 4.0f));
		return Row;
	};

	UTextBlock* Label = nullptr;
	UHorizontalBox* SelectionRow = AddRow();
	UButton* Previous = MakeMenuButton(TEXT("< PREVIOUS ELEMENT"), Label, RedPauseMenu::CyanSoft);
	Previous->OnClicked.AddDynamic(this, &URedPauseMenuWidget::HandleHUDPreviousElement);
	AddButtonToRow(SelectionRow, Previous);
	UButton* Next = MakeMenuButton(TEXT("NEXT ELEMENT >"), Label, RedPauseMenu::CyanSoft);
	Next->OnClicked.AddDynamic(this, &URedPauseMenuWidget::HandleHUDNextElement);
	AddButtonToRow(SelectionRow, Next);

	UHorizontalBox* MoveRow = AddRow();
	UButton* MoveLeft = MakeMenuButton(TEXT("MOVE LEFT"), Label, FLinearColor(0.03f, 0.23f, 0.34f, 0.96f));
	MoveLeft->OnClicked.AddDynamic(this, &URedPauseMenuWidget::HandleHUDMoveLeft);
	AddButtonToRow(MoveRow, MoveLeft);
	UButton* MoveRight = MakeMenuButton(TEXT("MOVE RIGHT"), Label, FLinearColor(0.03f, 0.23f, 0.34f, 0.96f));
	MoveRight->OnClicked.AddDynamic(this, &URedPauseMenuWidget::HandleHUDMoveRight);
	AddButtonToRow(MoveRow, MoveRight);
	UButton* MoveUp = MakeMenuButton(TEXT("MOVE UP"), Label, FLinearColor(0.03f, 0.23f, 0.34f, 0.96f));
	MoveUp->OnClicked.AddDynamic(this, &URedPauseMenuWidget::HandleHUDMoveUp);
	AddButtonToRow(MoveRow, MoveUp);
	UButton* MoveDown = MakeMenuButton(TEXT("MOVE DOWN"), Label, FLinearColor(0.03f, 0.23f, 0.34f, 0.96f));
	MoveDown->OnClicked.AddDynamic(this, &URedPauseMenuWidget::HandleHUDMoveDown);
	AddButtonToRow(MoveRow, MoveDown);

	UHorizontalBox* AppearanceRow = AddRow();
	UButton* ScaleDown = MakeMenuButton(TEXT("SIZE -"), Label, FLinearColor(0.12f, 0.24f, 0.42f, 0.96f));
	ScaleDown->OnClicked.AddDynamic(this, &URedPauseMenuWidget::HandleHUDScaleDown);
	AddButtonToRow(AppearanceRow, ScaleDown);
	UButton* ScaleUp = MakeMenuButton(TEXT("SIZE +"), Label, FLinearColor(0.12f, 0.24f, 0.42f, 0.96f));
	ScaleUp->OnClicked.AddDynamic(this, &URedPauseMenuWidget::HandleHUDScaleUp);
	AddButtonToRow(AppearanceRow, ScaleUp);
	UButton* OpacityDown = MakeMenuButton(TEXT("OPACITY -"), Label, FLinearColor(0.12f, 0.24f, 0.42f, 0.96f));
	OpacityDown->OnClicked.AddDynamic(this, &URedPauseMenuWidget::HandleHUDOpacityDown);
	AddButtonToRow(AppearanceRow, OpacityDown);
	UButton* OpacityUp = MakeMenuButton(TEXT("OPACITY +"), Label, FLinearColor(0.12f, 0.24f, 0.42f, 0.96f));
	OpacityUp->OnClicked.AddDynamic(this, &URedPauseMenuWidget::HandleHUDOpacityUp);
	AddButtonToRow(AppearanceRow, OpacityUp);

	UHorizontalBox* StateRow = AddRow();
	UButton* VisibilityButton = MakeMenuButton(TEXT("SHOW / HIDE"), Label, FLinearColor(0.23f, 0.17f, 0.38f, 0.96f));
	VisibilityButton->OnClicked.AddDynamic(this, &URedPauseMenuWidget::HandleHUDToggleVisibility);
	AddButtonToRow(StateRow, VisibilityButton);
	UButton* Lock = MakeMenuButton(TEXT("LOCK / UNLOCK"), Label, FLinearColor(0.23f, 0.17f, 0.38f, 0.96f));
	Lock->OnClicked.AddDynamic(this, &URedPauseMenuWidget::HandleHUDToggleLock);
	AddButtonToRow(StateRow, Lock);
	UButton* Reset = MakeMenuButton(TEXT("RESET ELEMENT"), Label, FLinearColor(0.36f, 0.22f, 0.08f, 0.96f));
	Reset->OnClicked.AddDynamic(this, &URedPauseMenuWidget::HandleHUDResetElement);
	AddButtonToRow(StateRow, Reset);
	UButton* ResetAll = MakeMenuButton(TEXT("RESET ALL"), Label, FLinearColor(0.42f, 0.13f, 0.09f, 0.96f));
	ResetAll->OnClicked.AddDynamic(this, &URedPauseMenuWidget::HandleHUDResetAll);
	AddButtonToRow(StateRow, ResetAll);

	HUDCustomizationStatusText = MakeText(TEXT("Select an element to begin."), 15, RedPauseMenu::Gold, true);
	RedPauseMenu::AddVertical(Stack, HUDCustomizationStatusText, FMargin(4.0f, 10.0f, 4.0f, 10.0f));

	UHorizontalBox* CommitRow = AddRow();
	UButton* Apply = MakeMenuButton(TEXT("APPLY + SAVE"), Label, FLinearColor(0.02f, 0.48f, 0.34f, 1.0f));
	Apply->OnClicked.AddDynamic(this, &URedPauseMenuWidget::HandleHUDApply);
	AddButtonToRow(CommitRow, Apply);
	UButton* Cancel = MakeMenuButton(TEXT("CANCEL CHANGES"), Label, FLinearColor(0.42f, 0.08f, 0.12f, 1.0f));
	Cancel->OnClicked.AddDynamic(this, &URedPauseMenuWidget::HandleHUDCancel);
	AddButtonToRow(CommitRow, Cancel);

	return Page;
}

void URedPauseMenuWidget::PrepareForOpen()
{
	DisarmExit();
	RefreshSessionState();
	RefreshSkillsState();
	RefreshGraphicsState();
	RefreshCharacterControl();
	RefreshInventoryResources();
	ShowPage(0, TEXT("OVERVIEW"));
	ControllerFocusRegion = EControllerFocusRegion::PrimaryMenu;
	ControllerPrimaryIndex = 0;
	ControllerInventoryCategoryIndex = 0;
	ControllerInventoryVisualSlotIndex = 0;
	ControllerFocusedWidget = nullptr;
}

bool URedPauseMenuWidget::SetControllerFocus(
	UWidget* Target, APlayerController* PlayerController)
{
	if (!Target || !Target->GetIsEnabled())
	{
		return false;
	}

	APlayerController* FocusPlayer = PlayerController
		? PlayerController : GetOwningPlayer();
	if (FocusPlayer)
	{
		Target->SetUserFocus(FocusPlayer);
	}
	else
	{
		Target->SetKeyboardFocus();
	}
	ControllerFocusedWidget = Target;
	return true;
}

void URedPauseMenuWidget::FocusInitialControllerTarget(
	APlayerController* PlayerController)
{
	ControllerFocusRegion = EControllerFocusRegion::PrimaryMenu;
	ControllerPrimaryIndex = 0;
	if (PrimaryMenuButtons.IsValidIndex(ControllerPrimaryIndex))
	{
		SetControllerFocus(
			PrimaryMenuButtons[ControllerPrimaryIndex], PlayerController);
	}
}

bool URedPauseMenuWidget::FocusControllerPrimary(const int32 RequestedIndex)
{
	if (!PrimaryMenuButtons.IsValidIndex(RequestedIndex)
		|| !PrimaryMenuButtons[RequestedIndex]
		|| !PrimaryMenuButtons[RequestedIndex]->GetIsEnabled())
	{
		return false;
	}

	ControllerFocusRegion = EControllerFocusRegion::PrimaryMenu;
	ControllerPrimaryIndex = RequestedIndex;
	return SetControllerFocus(PrimaryMenuButtons[RequestedIndex]);
}

bool URedPauseMenuWidget::MoveControllerPrimary(const int32 Direction)
{
	if (Direction == 0 || PrimaryMenuButtons.IsEmpty())
	{
		return false;
	}

	int32 Candidate = ControllerPrimaryIndex;
	for (int32 Attempt = 0; Attempt < PrimaryMenuButtons.Num(); ++Attempt)
	{
		const int32 Next = FMath::Clamp(
			Candidate + FMath::Sign(Direction),
			0,
			PrimaryMenuButtons.Num() - 1);
		if (Next == Candidate)
		{
			break;
		}
		Candidate = Next;
		if (PrimaryMenuButtons[Candidate]
			&& PrimaryMenuButtons[Candidate]->GetIsEnabled())
		{
			return FocusControllerPrimary(Candidate);
		}
	}
	return FocusControllerPrimary(ControllerPrimaryIndex);
}

bool URedPauseMenuWidget::FocusControllerInventoryCategory(
	const int32 RequestedIndex)
{
	if (!InventoryWidget)
	{
		return false;
	}

	const int32 CategoryIndex = FMath::Clamp(RequestedIndex, 0, 3);
	if (!InventoryWidget->FocusControllerCategory(
			CategoryIndex, GetOwningPlayer()))
	{
		return false;
	}

	ControllerFocusRegion = EControllerFocusRegion::InventoryCategory;
	ControllerInventoryCategoryIndex = CategoryIndex;
	ControllerFocusedWidget = InventoryWidget->WidgetTree
		? InventoryWidget->WidgetTree->FindWidget<UButton>(
			InventoryWidget->GetControllerCategoryWidgetName(CategoryIndex))
		: nullptr;
	return ControllerFocusedWidget != nullptr;
}

bool URedPauseMenuWidget::FocusControllerInventorySlot(
	const int32 RequestedVisualSlotIndex)
{
	if (!InventoryWidget)
	{
		return false;
	}

	const TArray<int32> VisibleIndices =
		InventoryWidget->GetVisibleInventoryItemIndices();
	if (VisibleIndices.IsEmpty())
	{
		return false;
	}

	const int32 VisualSlotIndex = FMath::Clamp(
		RequestedVisualSlotIndex, 0, VisibleIndices.Num() - 1);
	if (!InventoryWidget->FocusControllerVisibleSlot(
			VisualSlotIndex, GetOwningPlayer()))
	{
		return false;
	}

	ControllerFocusRegion = EControllerFocusRegion::InventoryGrid;
	ControllerInventoryVisualSlotIndex = VisualSlotIndex;
	ControllerFocusedWidget = InventoryWidget->WidgetTree
		? InventoryWidget->WidgetTree->FindWidget<UVibeMMOInventorySlotButton>(
			InventoryWidget->GetControllerVisibleSlotWidgetName(VisualSlotIndex))
		: nullptr;
	return ControllerFocusedWidget != nullptr;
}

bool URedPauseMenuWidget::ActivateControllerTarget()
{
	switch (ControllerFocusRegion)
	{
	case EControllerFocusRegion::PrimaryMenu:
		if (!PrimaryMenuButtons.IsValidIndex(ControllerPrimaryIndex)
			|| !PrimaryMenuButtons[ControllerPrimaryIndex]
			|| !PrimaryMenuButtons[ControllerPrimaryIndex]->GetIsEnabled())
		{
			return false;
		}
		PrimaryMenuButtons[ControllerPrimaryIndex]->OnClicked.Broadcast();
		if (ControllerPrimaryIndex == 3)
		{
			ControllerInventoryCategoryIndex = 0;
			ControllerInventoryVisualSlotIndex = 0;
			return FocusControllerInventoryCategory(
				ControllerInventoryCategoryIndex);
		}
		return true;

	case EControllerFocusRegion::InventoryCategory:
		if (!InventoryWidget
			|| !InventoryWidget->ActivateControllerCategory(
				ControllerInventoryCategoryIndex))
		{
			return false;
		}
		ControllerInventoryVisualSlotIndex = 0;
		return FocusControllerInventoryCategory(
			ControllerInventoryCategoryIndex);

	case EControllerFocusRegion::InventoryGrid:
		if (!InventoryWidget
			|| !InventoryWidget->ActivateControllerVisibleSlot(
				ControllerInventoryVisualSlotIndex))
		{
			return false;
		}
		return FocusControllerInventorySlot(
			ControllerInventoryVisualSlotIndex);
	}
	return false;
}

bool URedPauseMenuWidget::RouteControllerKey(
	const FKey& Key, const bool bIsRepeat)
{
	if (bIsRepeat
		&& (Key == EKeys::Gamepad_FaceButton_Bottom
			|| Key == EKeys::Gamepad_FaceButton_Right
			|| Key == EKeys::Virtual_Gamepad_Back
			|| Key == EKeys::Gamepad_Special_Right))
	{
		return true;
	}

	if (Key == EKeys::Gamepad_FaceButton_Right
		|| Key == EKeys::Virtual_Gamepad_Back
		|| Key == EKeys::Gamepad_Special_Right)
	{
		HandleResume();
		return true;
	}
	if (Key == EKeys::Gamepad_FaceButton_Bottom)
	{
		return ActivateControllerTarget();
	}

	const bool bLeft = Key == EKeys::Gamepad_DPad_Left;
	const bool bRight = Key == EKeys::Gamepad_DPad_Right;
	const bool bUp = Key == EKeys::Gamepad_DPad_Up;
	const bool bDown = Key == EKeys::Gamepad_DPad_Down;
	if (!bLeft && !bRight && !bUp && !bDown)
	{
		return false;
	}

	switch (ControllerFocusRegion)
	{
	case EControllerFocusRegion::PrimaryMenu:
		if (bUp || bDown)
		{
			return MoveControllerPrimary(bDown ? 1 : -1);
		}
		return true;

	case EControllerFocusRegion::InventoryCategory:
		if (bLeft || bRight)
		{
			return FocusControllerInventoryCategory(
				ControllerInventoryCategoryIndex + (bRight ? 1 : -1));
		}
		if (bDown)
		{
			return FocusControllerInventorySlot(0);
		}
		if (bUp)
		{
			return FocusControllerPrimary(3);
		}
		return true;

	case EControllerFocusRegion::InventoryGrid:
		if (!InventoryWidget)
		{
			return false;
		}
		if (bLeft || bRight)
		{
			return FocusControllerInventorySlot(
				ControllerInventoryVisualSlotIndex + (bRight ? 1 : -1));
		}
		if (bUp)
		{
			if (ControllerInventoryVisualSlotIndex < 8)
			{
				return FocusControllerInventoryCategory(
					ControllerInventoryCategoryIndex);
			}
			return FocusControllerInventorySlot(
				ControllerInventoryVisualSlotIndex - 8);
		}
		if (bDown)
		{
			const int32 RequestedSlot =
				ControllerInventoryVisualSlotIndex + 8;
			return RequestedSlot
					< InventoryWidget->GetVisibleInventoryItemIndices().Num()
				? FocusControllerInventorySlot(RequestedSlot)
				: FocusControllerInventorySlot(
					ControllerInventoryVisualSlotIndex);
		}
		return true;
	}
	return false;
}

bool URedPauseMenuWidget::GetControllerInventoryState(
	FString& OutRegion,
	int32& OutPrimaryIndex,
	int32& OutCategoryIndex,
	int32& OutVisualSlotIndex,
	int32& OutStableItemIndex,
	FString& OutFocusedWidget,
	bool& bOutHasUserFocus) const
{
	switch (ControllerFocusRegion)
	{
	case EControllerFocusRegion::PrimaryMenu:
		OutRegion = TEXT("PrimaryMenu");
		break;
	case EControllerFocusRegion::InventoryCategory:
		OutRegion = TEXT("InventoryCategory");
		break;
	case EControllerFocusRegion::InventoryGrid:
		OutRegion = TEXT("InventoryGrid");
		break;
	default:
		OutRegion = TEXT("Unknown");
		break;
	}

	OutPrimaryIndex = ControllerPrimaryIndex;
	OutCategoryIndex = ControllerInventoryCategoryIndex;
	OutVisualSlotIndex = ControllerInventoryVisualSlotIndex;
	OutStableItemIndex = InventoryWidget
		? InventoryWidget->GetSelectedInventoryItemIndex() : INDEX_NONE;
	OutFocusedWidget = ControllerFocusedWidget
		? ControllerFocusedWidget->GetName() : TEXT("None");
	APlayerController* PlayerController = GetOwningPlayer();
	bOutHasUserFocus = ControllerFocusedWidget
		&& (PlayerController
			? ControllerFocusedWidget->HasUserFocus(PlayerController)
			: ControllerFocusedWidget->HasKeyboardFocus());
	return InventoryWidget != nullptr;
}

void URedPauseMenuWidget::RefreshInventoryResources()
{
	const ARedPlayerCharacter* Character = FindLocalPlayerCharacter();
	const int32 Stone = Character ? FMath::Max(0, Character->ResStone) : 0;
	const int32 Iron = Character ? FMath::Max(0, Character->ResIron) : 0;
	const int32 Crystal = Character ? FMath::Max(0, Character->ResCrystal) : 0;
	SetResourceInventoryTotals(Stone, Iron, Crystal);
}

void URedPauseMenuWidget::SetResourceInventoryTotals(
	const int32 Stone, const int32 Iron, const int32 Crystal)
{
	if (!InventoryWidget)
	{
		return;
	}

	InventoryWidget->SetResourceTotals(Stone, Iron, Crystal);

	auto PublishResource = [this](
		const int32 StableIndex,
		const TCHAR* DisplayName,
		const int32 Quantity,
		const FLinearColor& AccentColor,
		const TCHAR* Description)
	{
		FVibeMMOInventoryItemPresentation Resource;
		Resource.bIsPopulated = true;
		Resource.Category = EVibeMMOInventoryCategory::Resources;
		Resource.DisplayName = FText::FromString(DisplayName);
		Resource.Rarity = FText::FromString(FString::Printf(
			TEXT("STORED: %d"), Quantity));
		Resource.Description = FText::FromString(Description);
		Resource.RarityColor = AccentColor;
		InventoryWidget->SetInventoryItemPresentation(StableIndex, Resource);
	};

	PublishResource(
		2, TEXT("STONE"), Stone,
		FLinearColor(0.56f, 0.70f, 0.82f, 1.0f),
		TEXT("Construction aggregate recovered from mineable bodies."));
	PublishResource(
		3, TEXT("IRON"), Iron,
		RedPauseMenu::Gold,
		TEXT("Metallic ore reserved for fabrication and structural work."));
	PublishResource(
		4, TEXT("CRYSTAL"), Crystal,
		RedPauseMenu::Purple,
		TEXT("High-energy crystalline material reserved for advanced systems."));
}

void URedPauseMenuWidget::RefreshCharacterControl()
{
	if (!CharacterButton)
	{
		return;
	}

	const ARedPlayerCharacter* Character = FindLocalPlayerCharacter();
	const bool bCreatorAvailable = Character && Character->CanOpenCharacterCreator();
	CharacterButton->SetIsEnabled(bCreatorAvailable);
	CharacterButton->SetToolTipText(FText::FromString(
		bCreatorAvailable
			? TEXT("Open the installed modular character creator")
			: Character
				? TEXT("Character creator unavailable: the active player controller does not expose ToggleCharacterWindow.")
				: TEXT("Character creator unavailable while the local player is still loading.")));
}

void URedPauseMenuWidget::ShowPage(const int32 PageIndex, const FString& PageTitle)
{
	if (bHUDCustomizationPreviewActive && PageIndex != 4)
	{
		CancelHUDCustomizationPreview();
	}
	DisarmExit();
	if (PageSwitcher)
	{
		PageSwitcher->SetActiveWidgetIndex(PageIndex);
	}
	if (SectionTitleText)
	{
		SectionTitleText->SetText(FText::FromString(PageTitle));
	}
}

void URedPauseMenuWidget::RefreshSessionState()
{
	if (!SessionStateText)
	{
		return;
	}
	if (const URedGameInstance* GameInstance = Cast<URedGameInstance>(GetGameInstance()))
	{
		FString Label;
		switch (GameInstance->SessionState)
		{
		case ERedSessionState::Destroying: Label = TEXT("CLOSING MULTIPLAYER SESSION..."); break;
		case ERedSessionState::Creating: Label = TEXT("CREATING MULTIPLAYER GAME..."); break;
		case ERedSessionState::Searching: Label = TEXT("SEARCHING STEAM LOBBIES..."); break;
		case ERedSessionState::Joining: Label = TEXT("JOINING MULTIPLAYER GAME..."); break;
		case ERedSessionState::Traveling: Label = TEXT("CONNECTING TO MULTIPLAYER..."); break;
		case ERedSessionState::InSession: Label = TEXT("MULTIPLAYER ONLINE  |  WORLD CONTINUES"); break;
		case ERedSessionState::Error: Label = TEXT("MULTIPLAYER ERROR  |  OPEN LOBBY"); break;
		default: Label = TEXT("SOLO  |  OPEN MULTIPLAYER / LOBBY TO HOST OR JOIN"); break;
		}
		SessionStateText->SetText(FText::FromString(Label));
		return;
	}

	SessionStateText->SetText(FText::FromString(TEXT("SOLO  |  MULTIPLAYER UNAVAILABLE")));
}

void URedPauseMenuWidget::RefreshSkillsState()
{
	const APlayerController* PC = GetOwningPlayer();
	const ARedPlayerCharacter* Character = FindLocalPlayerCharacter();
	const bool bOnFoot = PC && Cast<ARedPlayerCharacter>(PC->GetPawn());
	if (AbilityQText)
	{
		AbilityQText->SetText(Character ? Character->GetAbilityDisplayNameForSlot(0) : FText::FromString(TEXT("GRAPPLE")));
	}
	if (AbilityEText)
	{
		AbilityEText->SetText(Character ? Character->GetAbilityDisplayNameForSlot(1) : FText::FromString(TEXT("KINETIC SLAM")));
	}
	if (SkillsHelpText)
	{
		SkillsHelpText->SetText(FText::FromString(bOnFoot
			? TEXT("Open the editor here, or press TAB at any time on foot.")
			: TEXT("Skills remain equipped while piloting. Exit the vehicle to edit the on-foot Q/E loadout.")));
	}
}

ARedPlayerCharacter* URedPauseMenuWidget::FindLocalPlayerCharacter() const
{
	const APlayerController* PC = GetOwningPlayer();
	APawn* ControlledPawn = PC ? PC->GetPawn() : nullptr;
	if (ARedPlayerCharacter* OnFootCharacter = Cast<ARedPlayerCharacter>(ControlledPawn))
	{
		return OnFootCharacter;
	}

	// While piloting, RED keeps the original character attached to the possessed
	// craft so terrain streaming and HUD ownership remain continuous.
	if (UWorld* World = GetWorld(); World && ControlledPawn)
	{
		for (TActorIterator<ARedPlayerCharacter> It(World); It; ++It)
		{
			if (It->GetAttachParentActor() == ControlledPawn)
			{
				return *It;
			}
		}
	}
	return nullptr;
}

URedHUDWidget* URedPauseMenuWidget::FindActiveReplacementHUD() const
{
	return OwnerHUD ? OwnerHUD->GetPixelExactHUDWidget() : nullptr;
}

UVibeMMOHUDLayoutSubsystem* URedPauseMenuWidget::FindHUDLayoutSubsystem() const
{
	if (ULocalPlayer* LocalPlayer = GetOwningLocalPlayer())
	{
		return LocalPlayer->GetSubsystem<UVibeMMOHUDLayoutSubsystem>();
	}
	return nullptr;
}

bool URedPauseMenuWidget::BeginHUDCustomizationPreview()
{
	URedHUDWidget* HUD = FindActiveReplacementHUD();
	UVibeMMOHUDLayoutSubsystem* LayoutSubsystem = FindHUDLayoutSubsystem();
	if (!HUD || !LayoutSubsystem || !LayoutSubsystem->IsLayoutLoaded())
	{
		RefreshHUDCustomizationState(TEXT("HUD is unavailable while the local player is still loading."));
		return false;
	}

	if (!bHUDCustomizationPreviewActive)
	{
		HUDCustomizationOriginalProfile = LayoutSubsystem->GetLayoutProfile();
		bHUDCustomizationPreviewActive = true;
	}
	RefreshHUDCustomizationState();
	return true;
}

void URedPauseMenuWidget::RefreshHUDCustomizationState(const FString& Feedback)
{
	if (HUDSelectedElementText)
	{
		HUDSelectedElementText->SetText(FText::FromString(
			RedPauseMenu::GetHUDElementLabel(SelectedHUDElement)));
	}

	if (!HUDCustomizationStatusText)
	{
		return;
	}
	const URedHUDWidget* HUD = FindActiveReplacementHUD();
	if (!HUD)
	{
		HUDCustomizationStatusText->SetText(FText::FromString(
			Feedback.IsEmpty() ? TEXT("HUD unavailable.") : Feedback));
		HUDCustomizationStatusText->SetColorAndOpacity(FSlateColor(RedPauseMenu::Gold));
		return;
	}

	const FVibeMMOHUDElementLayout Layout = HUD->GetHUDElementLayout(SelectedHUDElement);
	const FString State = FString::Printf(
		TEXT("SIZE %d%%   |   OPACITY %d%%   |   %s   |   %s"),
		FMath::RoundToInt(Layout.Scale * 100.0f),
		FMath::RoundToInt(Layout.Opacity * 100.0f),
		Layout.bHidden ? TEXT("HIDDEN") : TEXT("VISIBLE"),
		Layout.bLocked ? TEXT("LOCKED") : TEXT("UNLOCKED"));
	HUDCustomizationStatusText->SetText(FText::FromString(
		Feedback.IsEmpty() ? State : FString::Printf(TEXT("%s\n%s"), *Feedback, *State)));
	HUDCustomizationStatusText->SetColorAndOpacity(FSlateColor(
		Feedback.IsEmpty() ? RedPauseMenu::Body : RedPauseMenu::Gold));
}

bool URedPauseMenuWidget::CancelHUDCustomizationPreview()
{
	if (!bHUDCustomizationPreviewActive)
	{
		return true;
	}
	UVibeMMOHUDLayoutSubsystem* LayoutSubsystem = FindHUDLayoutSubsystem();
	if (!LayoutSubsystem
		|| !LayoutSubsystem->SetLayoutProfile(HUDCustomizationOriginalProfile)
		|| !LayoutSubsystem->SaveLayoutNow())
	{
		bHUDResetAllArmed = false;
		return false;
	}
	bHUDCustomizationPreviewActive = false;
	bHUDResetAllArmed = false;
	return true;
}

void URedPauseMenuWidget::RefreshGraphicsState()
{
	if (!GraphicsStatusText)
	{
		return;
	}
	if (UGameUserSettings* Settings = GEngine ? GEngine->GetGameUserSettings() : nullptr)
	{
		const TCHAR* Mode = Settings->GetFullscreenMode() == EWindowMode::Windowed ? TEXT("WINDOWED") : TEXT("FULLSCREEN");
		GraphicsStatusText->SetText(FText::FromString(FString::Printf(TEXT("QUALITY LEVEL %d   |   %s"),
			Settings->GetOverallScalabilityLevel(), Mode)));
	}
}

void URedPauseMenuWidget::DisarmExit()
{
	bExitArmed = false;
	if (ExitButtonText)
	{
		ExitButtonText->SetText(FText::FromString(TEXT("EXIT TO DESKTOP")));
	}
}

void URedPauseMenuWidget::HandleResume()
{
	CancelHUDCustomizationPreview();
	if (OwnerHUD)
	{
		OwnerHUD->ClosePauseMenu();
	}
}

void URedPauseMenuWidget::HandleOverview()
{
	ShowPage(0, TEXT("OVERVIEW"));
}

void URedPauseMenuWidget::HandleMultiplayer()
{
	if (!OwnerHUD || !OwnerHUD->OpenSessionBrowserFromPauseMenu())
	{
		if (SessionStateText)
		{
			SessionStateText->SetText(FText::FromString(TEXT("COULD NOT OPEN MULTIPLAYER LOBBY")));
			SessionStateText->SetColorAndOpacity(FSlateColor(RedPauseMenu::Gold));
		}
	}
}

void URedPauseMenuWidget::HandleInventory()
{
	APlayerController* PlayerController = GetOwningPlayer();
	const bool bControllerInvoked =
		ControllerFocusRegion == EControllerFocusRegion::PrimaryMenu
		&& ControllerPrimaryIndex == 3
		&& PrimaryMenuButtons.IsValidIndex(3)
		&& ControllerFocusedWidget == PrimaryMenuButtons[3]
		&& PlayerController
		&& PrimaryMenuButtons[3]->HasUserFocus(PlayerController);
	RefreshInventoryResources();
	ShowPage(1, TEXT("INVENTORY"));
	if (bControllerInvoked)
	{
		ControllerInventoryCategoryIndex = 0;
		ControllerInventoryVisualSlotIndex = 0;
		FocusControllerInventoryCategory(
			ControllerInventoryCategoryIndex);
	}
}

void URedPauseMenuWidget::HandleCharacter()
{
	if (ARedPlayerCharacter* Character = FindLocalPlayerCharacter())
	{
		if (Character->OpenCharacterCreatorFromMenu())
		{
			HandleResume();
			return;
		}
	}

	if (SectionTitleText)
	{
		SectionTitleText->SetText(FText::FromString(
			TEXT("CHARACTER CREATOR UNAVAILABLE - THE ACTIVE CONTROLLER HAS NO CREATOR COMMAND")));
	}
	RefreshCharacterControl();
}

void URedPauseMenuWidget::HandleSkills()
{
	RefreshSkillsState();
	ShowPage(2, TEXT("SKILLS + ABILITY LOADOUT"));
}

void URedPauseMenuWidget::HandleSettings()
{
	RefreshGraphicsState();
	ShowPage(3, TEXT("SETTINGS"));
}

void URedPauseMenuWidget::HandleHUDCustomization()
{
	ShowPage(4, TEXT("CUSTOMIZE HUD"));
	bHUDResetAllArmed = false;
	BeginHUDCustomizationPreview();
}

void URedPauseMenuWidget::HandleHUDPreviousElement()
{
	const TArray<EVibeMMOHUDElement>& Elements = RedPauseMenu::GetReplacementHUDElements();
	const int32 Current = Elements.IndexOfByKey(SelectedHUDElement);
	SelectedHUDElement = Elements[(Current <= 0 ? Elements.Num() : Current) - 1];
	bHUDResetAllArmed = false;
	RefreshHUDCustomizationState();
}

void URedPauseMenuWidget::HandleHUDNextElement()
{
	const TArray<EVibeMMOHUDElement>& Elements = RedPauseMenu::GetReplacementHUDElements();
	const int32 Current = FMath::Max(0, Elements.IndexOfByKey(SelectedHUDElement));
	SelectedHUDElement = Elements[(Current + 1) % Elements.Num()];
	bHUDResetAllArmed = false;
	RefreshHUDCustomizationState();
}

void URedPauseMenuWidget::HandleHUDMoveLeft()
{
	bHUDResetAllArmed = false;
	if (!BeginHUDCustomizationPreview())
	{
		return;
	}
	URedHUDWidget* HUD = FindActiveReplacementHUD();
	const FVibeMMOHUDElementLayout Layout = HUD
		? HUD->GetHUDElementLayout(SelectedHUDElement) : FVibeMMOHUDElementLayout();
	const bool bChanged = HUD
		&& HUD->NudgeHUDElement(SelectedHUDElement, FVector2D(-0.01f, 0.0f));
	RefreshHUDCustomizationState(bChanged
		? TEXT("Moved left.")
		: (!HUD
			? TEXT("HUD unavailable.")
			: (Layout.bLocked
				? TEXT("Unlock this element before moving it.")
				: TEXT("Element is already at its movement limit or the profile is read-only."))));
}

void URedPauseMenuWidget::HandleHUDMoveRight()
{
	bHUDResetAllArmed = false;
	if (!BeginHUDCustomizationPreview())
	{
		return;
	}
	URedHUDWidget* HUD = FindActiveReplacementHUD();
	const FVibeMMOHUDElementLayout Layout = HUD
		? HUD->GetHUDElementLayout(SelectedHUDElement) : FVibeMMOHUDElementLayout();
	const bool bChanged = HUD
		&& HUD->NudgeHUDElement(SelectedHUDElement, FVector2D(0.01f, 0.0f));
	RefreshHUDCustomizationState(bChanged
		? TEXT("Moved right.")
		: (!HUD
			? TEXT("HUD unavailable.")
			: (Layout.bLocked
				? TEXT("Unlock this element before moving it.")
				: TEXT("Element is already at its movement limit or the profile is read-only."))));
}

void URedPauseMenuWidget::HandleHUDMoveUp()
{
	bHUDResetAllArmed = false;
	if (!BeginHUDCustomizationPreview())
	{
		return;
	}
	URedHUDWidget* HUD = FindActiveReplacementHUD();
	const FVibeMMOHUDElementLayout Layout = HUD
		? HUD->GetHUDElementLayout(SelectedHUDElement) : FVibeMMOHUDElementLayout();
	const bool bChanged = HUD
		&& HUD->NudgeHUDElement(SelectedHUDElement, FVector2D(0.0f, -0.01f));
	RefreshHUDCustomizationState(bChanged
		? TEXT("Moved up.")
		: (!HUD
			? TEXT("HUD unavailable.")
			: (Layout.bLocked
				? TEXT("Unlock this element before moving it.")
				: TEXT("Element is already at its movement limit or the profile is read-only."))));
}

void URedPauseMenuWidget::HandleHUDMoveDown()
{
	bHUDResetAllArmed = false;
	if (!BeginHUDCustomizationPreview())
	{
		return;
	}
	URedHUDWidget* HUD = FindActiveReplacementHUD();
	const FVibeMMOHUDElementLayout Layout = HUD
		? HUD->GetHUDElementLayout(SelectedHUDElement) : FVibeMMOHUDElementLayout();
	const bool bChanged = HUD
		&& HUD->NudgeHUDElement(SelectedHUDElement, FVector2D(0.0f, 0.01f));
	RefreshHUDCustomizationState(bChanged
		? TEXT("Moved down.")
		: (!HUD
			? TEXT("HUD unavailable.")
			: (Layout.bLocked
				? TEXT("Unlock this element before moving it.")
				: TEXT("Element is already at its movement limit or the profile is read-only."))));
}

void URedPauseMenuWidget::HandleHUDScaleDown()
{
	bHUDResetAllArmed = false;
	if (!BeginHUDCustomizationPreview())
	{
		return;
	}
	URedHUDWidget* HUD = FindActiveReplacementHUD();
	const FVibeMMOHUDElementLayout Layout = HUD
		? HUD->GetHUDElementLayout(SelectedHUDElement) : FVibeMMOHUDElementLayout();
	const bool bChanged = HUD && HUD->SetHUDElementScale(SelectedHUDElement, Layout.Scale - 0.05f);
	RefreshHUDCustomizationState(bChanged
		? TEXT("Element made smaller.")
		: (!HUD
			? TEXT("HUD unavailable.")
			: (Layout.bLocked
				? TEXT("Unlock this element before resizing it.")
				: TEXT("Element is already at its size limit or the profile is read-only."))));
}

void URedPauseMenuWidget::HandleHUDScaleUp()
{
	bHUDResetAllArmed = false;
	if (!BeginHUDCustomizationPreview())
	{
		return;
	}
	URedHUDWidget* HUD = FindActiveReplacementHUD();
	const FVibeMMOHUDElementLayout Layout = HUD
		? HUD->GetHUDElementLayout(SelectedHUDElement) : FVibeMMOHUDElementLayout();
	const bool bChanged = HUD && HUD->SetHUDElementScale(SelectedHUDElement, Layout.Scale + 0.05f);
	RefreshHUDCustomizationState(bChanged
		? TEXT("Element made larger.")
		: (!HUD
			? TEXT("HUD unavailable.")
			: (Layout.bLocked
				? TEXT("Unlock this element before resizing it.")
				: TEXT("Element is already at its size limit or the profile is read-only."))));
}

void URedPauseMenuWidget::HandleHUDOpacityDown()
{
	bHUDResetAllArmed = false;
	if (!BeginHUDCustomizationPreview())
	{
		return;
	}
	URedHUDWidget* HUD = FindActiveReplacementHUD();
	const FVibeMMOHUDElementLayout Layout = HUD
		? HUD->GetHUDElementLayout(SelectedHUDElement) : FVibeMMOHUDElementLayout();
	const bool bChanged = HUD
		&& HUD->SetHUDElementOpacity(SelectedHUDElement, Layout.Opacity - 0.10f);
	RefreshHUDCustomizationState(bChanged
		? TEXT("Opacity lowered.")
		: (HUD ? TEXT("Opacity is already at its limit or the profile is read-only.") : TEXT("HUD unavailable.")));
}

void URedPauseMenuWidget::HandleHUDOpacityUp()
{
	bHUDResetAllArmed = false;
	if (!BeginHUDCustomizationPreview())
	{
		return;
	}
	URedHUDWidget* HUD = FindActiveReplacementHUD();
	const FVibeMMOHUDElementLayout Layout = HUD
		? HUD->GetHUDElementLayout(SelectedHUDElement) : FVibeMMOHUDElementLayout();
	const bool bChanged = HUD
		&& HUD->SetHUDElementOpacity(SelectedHUDElement, Layout.Opacity + 0.10f);
	RefreshHUDCustomizationState(bChanged
		? TEXT("Opacity raised.")
		: (HUD ? TEXT("Opacity is already at its limit or the profile is read-only.") : TEXT("HUD unavailable.")));
}

void URedPauseMenuWidget::HandleHUDToggleVisibility()
{
	bHUDResetAllArmed = false;
	if (!BeginHUDCustomizationPreview())
	{
		return;
	}
	URedHUDWidget* HUD = FindActiveReplacementHUD();
	const FVibeMMOHUDElementLayout Layout = HUD
		? HUD->GetHUDElementLayout(SelectedHUDElement) : FVibeMMOHUDElementLayout();
	const bool bChanged = HUD
		&& HUD->SetHUDElementHidden(SelectedHUDElement, !Layout.bHidden);
	RefreshHUDCustomizationState(bChanged
		? (Layout.bHidden ? TEXT("Element shown.") : TEXT("Element hidden."))
		: (HUD ? TEXT("Visibility could not be changed because the profile is read-only.") : TEXT("HUD unavailable.")));
}

void URedPauseMenuWidget::HandleHUDToggleLock()
{
	bHUDResetAllArmed = false;
	if (!BeginHUDCustomizationPreview())
	{
		return;
	}
	URedHUDWidget* HUD = FindActiveReplacementHUD();
	const FVibeMMOHUDElementLayout Layout = HUD
		? HUD->GetHUDElementLayout(SelectedHUDElement) : FVibeMMOHUDElementLayout();
	const bool bChanged = HUD
		&& HUD->SetHUDElementLocked(SelectedHUDElement, !Layout.bLocked);
	RefreshHUDCustomizationState(bChanged
		? (Layout.bLocked ? TEXT("Element unlocked.") : TEXT("Element locked."))
		: (HUD ? TEXT("Lock state could not be changed because the profile is read-only.") : TEXT("HUD unavailable.")));
}

void URedPauseMenuWidget::HandleHUDResetElement()
{
	bHUDResetAllArmed = false;
	if (!BeginHUDCustomizationPreview())
	{
		return;
	}
	if (URedHUDWidget* HUD = FindActiveReplacementHUD())
	{
		const bool bChanged = HUD->ResetHUDElement(SelectedHUDElement);
		RefreshHUDCustomizationState(bChanged
			? TEXT("Selected element reset.")
			: TEXT("Element is already at its default or the profile is read-only."));
		return;
	}
	RefreshHUDCustomizationState(TEXT("HUD unavailable."));
}

void URedPauseMenuWidget::HandleHUDResetAll()
{
	if (!BeginHUDCustomizationPreview())
	{
		return;
	}
	if (!bHUDResetAllArmed)
	{
		bHUDResetAllArmed = true;
		RefreshHUDCustomizationState(TEXT("Press RESET ALL again to confirm."));
		return;
	}
	bHUDResetAllArmed = false;
	if (URedHUDWidget* HUD = FindActiveReplacementHUD())
	{
		const bool bChanged = HUD->ResetAllHUDElements();
		RefreshHUDCustomizationState(bChanged
			? TEXT("All HUD elements reset. Press APPLY + SAVE to keep it.")
			: TEXT("All HUD elements are already at default or the profile is read-only."));
		return;
	}
	RefreshHUDCustomizationState(TEXT("HUD unavailable."));
}

void URedPauseMenuWidget::HandleHUDApply()
{
	bHUDResetAllArmed = false;
	if (bHUDCustomizationPreviewActive)
	{
		if (UVibeMMOHUDLayoutSubsystem* LayoutSubsystem = FindHUDLayoutSubsystem())
		{
			const bool bSaveStarted = LayoutSubsystem->SaveLayoutNow();
			if (bSaveStarted)
			{
				HUDCustomizationOriginalProfile = LayoutSubsystem->GetLayoutProfile();
			}
			RefreshHUDCustomizationState(bSaveStarted
				? TEXT("HUD layout saved for this local player.")
				: TEXT("HUD layout could not be saved; no changes were discarded."));
			return;
		}
	}
	RefreshHUDCustomizationState(TEXT("HUD unavailable."));
}

void URedPauseMenuWidget::HandleHUDCancel()
{
	const bool bRestored = CancelHUDCustomizationPreview();
	RefreshHUDCustomizationState(bRestored
		? TEXT("Preview changes canceled and the saved layout restored.")
		: TEXT("The saved layout could not be restored; preview changes remain pending."));
}

void URedPauseMenuWidget::HandleOpenAbilityLoadout()
{
	if (!OwnerHUD || !OwnerHUD->OpenAbilityLoadoutFromPauseMenu())
	{
		if (SkillsHelpText)
		{
			SkillsHelpText->SetText(FText::FromString(TEXT("Exit the vehicle first; ability editing is available while on foot.")));
			SkillsHelpText->SetColorAndOpacity(FSlateColor(RedPauseMenu::Gold));
		}
	}
}

static void ApplyQualityPreset(const int32 Quality)
{
	if (UGameUserSettings* Settings = GEngine ? GEngine->GetGameUserSettings() : nullptr)
	{
		const int32 SafeQuality = FMath::Clamp(Quality, 1, 3);
		const float SafeResolutionScale = SafeQuality == 1 ? 67.f : SafeQuality == 2 ? 75.f : 85.f;
		Settings->SetOverallScalabilityLevel(SafeQuality);
		Settings->SetResolutionScaleValueEx(SafeResolutionScale);
		Settings->ApplySettings(false);
		Settings->SaveSettings();
	}
}

void URedPauseMenuWidget::HandlePerformanceQuality()
{
	ApplyQualityPreset(1);
	RefreshGraphicsState();
}

void URedPauseMenuWidget::HandleBalancedQuality()
{
	ApplyQualityPreset(2);
	RefreshGraphicsState();
}

void URedPauseMenuWidget::HandleCinematicQuality()
{
	ApplyQualityPreset(4);
	RefreshGraphicsState();
}

void URedPauseMenuWidget::HandleToggleWindowMode()
{
	if (UGameUserSettings* Settings = GEngine ? GEngine->GetGameUserSettings() : nullptr)
	{
		Settings->SetFullscreenMode(Settings->GetFullscreenMode() == EWindowMode::Windowed
			? EWindowMode::WindowedFullscreen : EWindowMode::Windowed);
		Settings->ApplyResolutionSettings(false);
		Settings->SaveSettings();
	}
	RefreshGraphicsState();
}

void URedPauseMenuWidget::HandleExit()
{
	if (!bExitArmed)
	{
		bExitArmed = true;
		if (ExitButtonText)
		{
			ExitButtonText->SetText(FText::FromString(TEXT("CONFIRM EXIT")));
		}
		return;
	}

	if (APlayerController* PC = GetOwningPlayer())
	{
		UKismetSystemLibrary::QuitGame(this, PC, EQuitPreference::Quit, false);
	}
}
