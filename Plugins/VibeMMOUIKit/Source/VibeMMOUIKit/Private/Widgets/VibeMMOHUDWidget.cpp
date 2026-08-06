#include "Widgets/VibeMMOHUDWidget.h"

#include "Blueprint/WidgetLayoutLibrary.h"
#include "Blueprint/WidgetTree.h"
#include "Components/Border.h"
#include "Components/Button.h"
#include "Components/CanvasPanel.h"
#include "Components/CanvasPanelSlot.h"
#include "Components/HorizontalBox.h"
#include "Components/HorizontalBoxSlot.h"
#include "Components/Image.h"
#include "Components/Overlay.h"
#include "Components/OverlaySlot.h"
#include "Components/ProgressBar.h"
#include "Components/SafeZone.h"
#include "Components/SceneComponent.h"
#include "Components/SizeBox.h"
#include "Components/TextBlock.h"
#include "Components/VerticalBox.h"
#include "Components/VerticalBoxSlot.h"
#include "Brushes/SlateDynamicImageBrush.h"
#include "Brushes/SlateRoundedBoxBrush.h"
#include "Data/VibeMMOUIDataAssets.h"
#include "Engine/LocalPlayer.h"
#include "Fonts/SlateFontInfo.h"
#include "EngineUtils.h"
#include "GameFramework/Pawn.h"
#include "GameFramework/PlayerController.h"
#include "HAL/PlatformTime.h"
#include "Kismet/GameplayStatics.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Materials/MaterialInterface.h"
#include "Misc/Paths.h"
#include "Persistence/VibeMMOHUDLayoutSubsystem.h"
#include "Styling/SlateBrush.h"

namespace VibeMMOHUD
{
	static const FLinearColor PanelFill(0.018f, 0.025f, 0.045f, 0.72f);
	static const FLinearColor PanelStroke(0.88f, 0.94f, 1.0f, 0.28f);
	static const FLinearColor WhiteFill(1.0f, 1.0f, 1.0f, 0.92f);
	static const FLinearColor GoldFill(1.0f, 0.68f, 0.02f, 0.95f);
	static const FLinearColor CyanFill(0.1f, 0.78f, 1.0f, 0.92f);

	static FText CompassCardinalText(const float HeadingDegrees)
	{
		static const TCHAR* CardinalLabels[] = {
			TEXT("N"), TEXT("NE"), TEXT("E"), TEXT("SE"),
			TEXT("S"), TEXT("SW"), TEXT("W"), TEXT("NW")
		};
		const float Normalized = FMath::Fmod(HeadingDegrees + 360.0f + 22.5f, 360.0f);
		const int32 Index = FMath::Clamp(FMath::FloorToInt(Normalized / 45.0f), 0, UE_ARRAY_COUNT(CardinalLabels) - 1);
		return FText::FromString(CardinalLabels[Index]);
	}

	/** Fortnite-style: cardinal/ordinal letters on 45° ticks, degree numbers elsewhere. */
	static FText CompassTickText(const float HeadingDegrees)
	{
		const float Normalized = FMath::Fmod(HeadingDegrees + 360.0f, 360.0f);
		const int32 Deg = FMath::RoundToInt(Normalized) % 360;
		const bool bCardinalOrOrdinal = (Deg % 45) == 0;
		if (bCardinalOrOrdinal)
		{
			return CompassCardinalText(static_cast<float>(Deg));
		}
		return FText::AsNumber(Deg);
	}

	static void ApplyCompassLabelStyle(UTextBlock* TextBlock, const bool bEmphasis)
	{
		if (!TextBlock)
		{
			return;
		}
		FSlateFontInfo Font = TextBlock->GetFont();
		Font.Size = bEmphasis ? 11 : 9;
		Font.OutlineSettings.OutlineSize = 1;
		TextBlock->SetFont(Font);
		TextBlock->SetShadowOffset(FVector2D(0.6f, 0.6f));
		TextBlock->SetColorAndOpacity(FSlateColor(
			bEmphasis ? FLinearColor(1.0f, 1.0f, 1.0f, 0.95f) : FLinearColor(0.85f, 0.9f, 1.0f, 0.72f)));
	}

	static void ApplyCompactStatusNumberStyle(UTextBlock* TextBlock)
	{
		if (!TextBlock)
		{
			return;
		}

		FSlateFontInfo Font = TextBlock->GetFont();
		Font.Size = 20;
		Font.OutlineSettings.OutlineSize = 1;
		TextBlock->SetFont(Font);
		TextBlock->SetShadowOffset(FVector2D(1.0f, 1.0f));
		TextBlock->SetMargin(FMargin(0.0f));
		TextBlock->SetClipping(EWidgetClipping::Inherit);
	}

	static void ApplyCompactWeaponNumberStyle(UTextBlock* TextBlock)
	{
		if (!TextBlock)
		{
			return;
		}

		FSlateFontInfo Font = TextBlock->GetFont();
		Font.Size = 12;
		Font.OutlineSettings.OutlineSize = 1;
		TextBlock->SetFont(Font);
		TextBlock->SetShadowOffset(FVector2D(0.8f, 0.8f));
		TextBlock->SetMargin(FMargin(0.0f));
		TextBlock->SetClipping(EWidgetClipping::ClipToBoundsAlways);
	}

	static void ApplyMinimapMarkerStyle(UTextBlock* TextBlock)
	{
		if (!TextBlock)
		{
			return;
		}

		FSlateFontInfo Font = TextBlock->GetFont();
		Font.Size = 13;
		Font.OutlineSettings.OutlineSize = 1;
		TextBlock->SetFont(Font);
		TextBlock->SetShadowOffset(FVector2D(1.0f, 1.0f));
		TextBlock->SetMargin(FMargin(0.0f));
	}
}

UVibeMMOHUDWidget::UVibeMMOHUDWidget()
	: bBuildDefaultHUDInCpp(true)
	// Runtime HUDs must never resurrect the kit's showcase numbers or labels during
	// a tree rebuild.  Projects that need a mock-up can still opt in per widget.
	, bUseMockValues(false)
	, MockShieldValue(1948)
	, MockHealthValue(4023)
	, MockResourceValue(100)
	, MockLevelValue(131)
	, bUseMockTargetingRectangles(false)
	, bDefaultHUDTreeBuilt(false)
{
	MinimapMode = EVibeMMOMinimapMode::Surface;
	SetVisibility(ESlateVisibility::HitTestInvisible);
}

void UVibeMMOHUDWidget::SetStatusValues(const int32 ShieldValue, const int32 HealthValue, const int32 ResourceValue)
{
	if (ShieldValueText)
	{
		ShieldValueText->SetText(FText::AsNumber(ShieldValue));
	}

	if (HealthValueText)
	{
		HealthValueText->SetText(FText::AsNumber(HealthValue));
	}

	if (ResourceValueText)
	{
		ResourceValueText->SetText(FText::AsNumber(ResourceValue));
	}
}

void UVibeMMOHUDWidget::SetResourceTally(const int32 StoneCount, const int32 IronCount, const int32 CrystalCount)
{
	bUseMockValues = false;
	if (ResourceValueText)
	{
		ResourceValueText->SetText(FText::FromString(
			FString::Printf(TEXT("S%d  I%d  C%d"), StoneCount, IronCount, CrystalCount)));
	}
}

void UVibeMMOHUDWidget::SetLiveStatus(const int32 ShieldValue, const int32 HealthValue, const float ShieldFrac, const float HealthFrac, const float FuelFrac)
{
	bUseMockValues = false;
	// Visual bars only — never show numeric overlays on HP/shield.
	if (ShieldValueText)
	{
		ShieldValueText->SetVisibility(ESlateVisibility::Collapsed);
	}
	if (HealthValueText)
	{
		HealthValueText->SetVisibility(ESlateVisibility::Collapsed);
	}
	(void)ShieldValue;
	(void)HealthValue;
	// 10 shield pips: light floor(ShieldValue/10) full segments (100 HP → 10 segments).
	if (ShieldSegmentBlocks.Num() > 0)
	{
		const int32 Lit = FMath::Clamp(FMath::RoundToInt(FMath::Clamp(ShieldFrac, 0.f, 1.f) * ShieldSegmentBlocks.Num()), 0, ShieldSegmentBlocks.Num());
		for (int32 i = 0; i < ShieldSegmentBlocks.Num(); ++i)
		{
			if (UBorder* Seg = ShieldSegmentBlocks[i])
			{
				const bool bOn = i < Lit;
				Seg->SetBrushColor(bOn
					? FLinearColor(0.15f, 0.55f, 1.0f, 1.0f)
					: FLinearColor(0.02f, 0.05f, 0.10f, 0.35f));
			}
		}
	}
	else if (ShieldBarBlock)
	{
		ShieldBarBlock->SetRenderTransformPivot(FVector2D(0.f, 0.5f));
		ShieldBarBlock->SetRenderScale(FVector2D(FMath::Clamp(ShieldFrac, 0.f, 1.f), 1.f));
	}
	if (HealthBarBlock)
	{
		HealthBarBlock->SetRenderTransformPivot(FVector2D(0.f, 0.5f));
		HealthBarBlock->SetRenderScale(FVector2D(FMath::Clamp(HealthFrac, 0.f, 1.f), 1.f));
	}
	if (FuelBarBlock)
	{
		FuelBarBlock->SetRenderTransformPivot(FVector2D(0.f, 0.5f));
		FuelBarBlock->SetRenderScale(FVector2D(FMath::Clamp(FuelFrac, 0.f, 1.f), 1.f));
	}
}

void UVibeMMOHUDWidget::SetAbilitySlotVisible(const int32 AbilityIndex, const bool bVisible)
{
	if (!AbilitySlotRoots.IsValidIndex(AbilityIndex) || !AbilitySlotRoots[AbilityIndex])
	{
		return;
	}
	AbilitySlotRoots[AbilityIndex]->SetVisibility(
		bVisible ? ESlateVisibility::SelfHitTestInvisible : ESlateVisibility::Collapsed);
}

void UVibeMMOHUDWidget::ClearAbilitySlot(const int32 AbilityIndex)
{
	if (AbilityIconImages.IsValidIndex(AbilityIndex) && AbilityIconImages[AbilityIndex])
	{
		AbilityIconImages[AbilityIndex]->SetBrush(FSlateBrush());
		AbilityIconImages[AbilityIndex]->SetVisibility(ESlateVisibility::Collapsed);
	}
	if (AbilityIconFallbackTexts.IsValidIndex(AbilityIndex) && AbilityIconFallbackTexts[AbilityIndex])
	{
		AbilityIconFallbackTexts[AbilityIndex]->SetVisibility(ESlateVisibility::Collapsed);
	}
	if (AbilityNameTexts.IsValidIndex(AbilityIndex) && AbilityNameTexts[AbilityIndex])
	{
		AbilityNameTexts[AbilityIndex]->SetText(FText::GetEmpty());
		AbilityNameTexts[AbilityIndex]->SetVisibility(ESlateVisibility::Collapsed);
	}
	SetAbilitySlotVisible(AbilityIndex, false);
}

void UVibeMMOHUDWidget::SetAbilityCooldownState(const int32 AbilityIndex,
	const float RemainingSeconds, const float DurationSeconds)
{
	const float SafeRemaining = FMath::Max(0.0f, RemainingSeconds);
	const float Ratio = DurationSeconds > KINDA_SMALL_NUMBER
		? FMath::Clamp(SafeRemaining / DurationSeconds, 0.0f, 1.0f)
		: 0.0f;
	const bool bCoolingDown = SafeRemaining > KINDA_SMALL_NUMBER;

	if (AbilityCooldownBars.IsValidIndex(AbilityIndex) && AbilityCooldownBars[AbilityIndex])
	{
		AbilityCooldownBars[AbilityIndex]->SetPercent(Ratio);
		AbilityCooldownBars[AbilityIndex]->SetFillColorAndOpacity(
			bCoolingDown ? FLinearColor(0.08f, 0.82f, 1.0f, 0.96f) : FLinearColor::Transparent);
		AbilityCooldownBars[AbilityIndex]->SetVisibility(
			bCoolingDown ? ESlateVisibility::HitTestInvisible : ESlateVisibility::Collapsed);
	}
	if (AbilityCooldownTexts.IsValidIndex(AbilityIndex) && AbilityCooldownTexts[AbilityIndex])
	{
		UTextBlock* CooldownText = AbilityCooldownTexts[AbilityIndex];
		if (bCoolingDown)
		{
			FNumberFormattingOptions Format;
			Format.SetMinimumFractionalDigits(SafeRemaining < 10.0f ? 1 : 0);
			Format.SetMaximumFractionalDigits(SafeRemaining < 10.0f ? 1 : 0);
			CooldownText->SetText(FText::AsNumber(SafeRemaining, &Format));
			CooldownText->SetVisibility(ESlateVisibility::HitTestInvisible);
		}
		else
		{
			CooldownText->SetVisibility(ESlateVisibility::Collapsed);
		}
	}
}

void UVibeMMOHUDWidget::SetAbilityLoadoutOverlayVisible(const bool bVisible, const bool bQIsGrapple)
{
	if (AbilityLoadoutQAssignmentText)
	{
		AbilityLoadoutQAssignmentText->SetText(FText::FromString(
			bQIsGrapple ? TEXT("Q   GRAPPLE") : TEXT("Q   SLAM")));
	}
	if (AbilityLoadoutEAssignmentText)
	{
		AbilityLoadoutEAssignmentText->SetText(FText::FromString(
			bQIsGrapple ? TEXT("E   SLAM") : TEXT("E   GRAPPLE")));
	}
	if (AbilityLoadoutOverlay)
	{
		AbilityLoadoutOverlay->SetVisibility(
			bVisible ? ESlateVisibility::Visible : ESlateVisibility::Collapsed);
	}

	// The normal combat HUD deliberately ignores pointer input.  HitTestInvisible also
	// suppresses every child, however, which made the correctly bound SWAP Q / E button
	// impossible to click.  While the editor is open, ignore only the HUD root itself so
	// interactive descendants can receive input; restore the fully passive mode on close.
	SetVisibility(bVisible
		? ESlateVisibility::SelfHitTestInvisible
		: ESlateVisibility::HitTestInvisible);
}

void UVibeMMOHUDWidget::HandleAbilityLoadoutSwapClicked()
{
	OnAbilityLoadoutSwapRequested.Broadcast();
}

void UVibeMMOHUDWidget::HideCompass()
{
	for (UTextBlock* Label : CompassLabelTexts)
	{
		if (Label)
		{
			Label->SetVisibility(ESlateVisibility::Collapsed);
		}
	}
}

void UVibeMMOHUDWidget::SetAbilityKeyLabels(const FText QLabel, const FText ELabel, const FText RLabel, const FText FLabel, const FText XLabel)
{
	if (AbilityKeyQText)
	{
		AbilityKeyQText->SetText(QLabel);
	}

	if (AbilityKeyEText)
	{
		AbilityKeyEText->SetText(ELabel);
	}

	if (AbilityKeyRText)
	{
		AbilityKeyRText->SetText(RLabel);
	}

	if (AbilityKeyFText)
	{
		AbilityKeyFText->SetText(FLabel);
	}

	if (AbilityKeyXText)
	{
		AbilityKeyXText->SetText(XLabel);
	}
}

void UVibeMMOHUDWidget::SetWeaponSlotLabels(const FText Slot1Label, const FText Slot2Label)
{
	if (WeaponSlot1Text)
	{
		WeaponSlot1Text->SetText(Slot1Label);
	}

	if (WeaponSlot2Text)
	{
		WeaponSlot2Text->SetText(Slot2Label);
	}
}

void UVibeMMOHUDWidget::SetCompassHeadingDegrees(const float HeadingDegrees)
{
	const float NormalizedHeading = FRotator::NormalizeAxis(HeadingDegrees);
	TargetCompassHeadingDegrees = NormalizedHeading;
	if (!bCompassHeadingInitialized)
	{
		DisplayedCompassHeadingDegrees = NormalizedHeading;
		bCompassHeadingInitialized = true;
	}

	RefreshCompassLabels();
}

void UVibeMMOHUDWidget::RefreshCompassLabels()
{
	if (CompassLabelTexts.Num() == 0)
	{
		return;
	}

	constexpr float StepDegrees = 15.0f;
	constexpr float LabelSpacing = 34.0f;
	const float CenterHeading = FMath::GridSnap(DisplayedCompassHeadingDegrees, StepDegrees);
	const float SlideAlpha = FRotator::NormalizeAxis(DisplayedCompassHeadingDegrees - CenterHeading) / StepDegrees;
	const int32 CenterIndex = CompassLabelTexts.Num() / 2;
	for (int32 Index = 0; Index < CompassLabelTexts.Num(); ++Index)
	{
		if (UTextBlock* Label = CompassLabelTexts[Index])
		{
			const float Offset = static_cast<float>(Index - CenterIndex) * StepDegrees;
			const float TickHeading = CenterHeading + Offset;
			const float Normalized = FMath::Fmod(TickHeading + 360.0f, 360.0f);
			const int32 Deg = FMath::RoundToInt(Normalized) % 360;
			const bool bEmphasis = (Deg % 45) == 0;
			Label->SetText(VibeMMOHUD::CompassTickText(TickHeading));
			VibeMMOHUD::ApplyCompassLabelStyle(Label, bEmphasis);
			Label->SetRenderTranslation(FVector2D(-SlideAlpha * LabelSpacing, 0.0f));
		}
	}
}

void UVibeMMOHUDWidget::SetHUDLayoutDataAsset(UVibeMMOHUDLayoutDataAsset* InHUDLayoutDataAsset)
{
	HUDLayoutDataAsset = InHUDLayoutDataAsset;
	RebuildDefaultHUDLayout();
}

void UVibeMMOHUDWidget::RebuildDefaultHUDLayout()
{
	if (!bBuildDefaultHUDInCpp || !WidgetTree)
	{
		return;
	}

	bDefaultHUDTreeBuilt = false;
	WidgetTree->RootWidget = nullptr;
	BuildDefaultHUDTree();
	ApplyVibeStyle();

	if (bUseMockValues)
	{
		ApplyMockTextValues();
	}

	if (bUseMockTargetingRectangles && !bTargetingRectanglesOverridden)
	{
		ApplyMockTargetingRectangles();
	}
	else
	{
		RebuildTargetingRectangles();
	}

	// Self-heal: if the widget is already in the viewport, the cached Slate realization
	// points at the OLD RootWidget. Re-add to viewport so Slate re-realizes against the
	// fresh tree, otherwise the screen keeps showing the orphaned (empty) old root.
	if (IsInViewport())
	{
		RemoveFromParent();
		AddToViewport(10);
	}
}

FVibeMMOHUDLayoutProfile UVibeMMOHUDWidget::GetHUDLayoutProfile() const
{
	return HUDLayoutSubsystem && HUDLayoutSubsystem->IsLayoutLoaded()
		? HUDLayoutSubsystem->GetLayoutProfile()
		: RuntimeHUDLayoutProfile;
}

bool UVibeMMOHUDWidget::SetHUDLayoutProfile(const FVibeMMOHUDLayoutProfile& Profile)
{
	FVibeMMOHUDLayoutProfile Sanitized = Profile;
	Sanitized.Sanitize();
	if (HUDLayoutSubsystem)
	{
		if (!HUDLayoutSubsystem->SetLayoutProfile(Sanitized))
		{
			RuntimeHUDLayoutProfile = HUDLayoutSubsystem->GetLayoutProfile();
			ApplyHUDLayoutProfile();
			return false;
		}
		RuntimeHUDLayoutProfile = HUDLayoutSubsystem->GetLayoutProfile();
	}
	else
	{
		RuntimeHUDLayoutProfile = MoveTemp(Sanitized);
	}
	ApplyHUDLayoutProfile();
	return true;
}

FVibeMMOHUDElementLayout UVibeMMOHUDWidget::GetHUDElementLayout(
	const EVibeMMOHUDElement Element) const
{
	return GetHUDLayoutProfile().GetElementLayout(Element);
}

bool UVibeMMOHUDWidget::NudgeHUDElement(
	const EVibeMMOHUDElement Element,
	const FVector2D NormalizedDelta)
{
	FVibeMMOHUDElementLayout Layout = GetHUDElementLayout(Element);
	if (Layout.bLocked)
	{
		return false;
	}
	Layout.NormalizedOffset += NormalizedDelta;
	return CommitHUDElementLayout(Element, Layout);
}

bool UVibeMMOHUDWidget::SetHUDElementScale(
	const EVibeMMOHUDElement Element,
	const float NewScale)
{
	FVibeMMOHUDElementLayout Layout = GetHUDElementLayout(Element);
	if (Layout.bLocked)
	{
		return false;
	}
	Layout.Scale = NewScale;
	return CommitHUDElementLayout(Element, Layout);
}

bool UVibeMMOHUDWidget::SetHUDElementOpacity(
	const EVibeMMOHUDElement Element,
	const float NewOpacity)
{
	FVibeMMOHUDElementLayout Layout = GetHUDElementLayout(Element);
	Layout.Opacity = NewOpacity;
	return CommitHUDElementLayout(Element, Layout);
}

bool UVibeMMOHUDWidget::SetHUDElementHidden(
	const EVibeMMOHUDElement Element,
	const bool bHidden)
{
	FVibeMMOHUDElementLayout Layout = GetHUDElementLayout(Element);
	Layout.bHidden = bHidden;
	return CommitHUDElementLayout(Element, Layout);
}

bool UVibeMMOHUDWidget::SetHUDElementLocked(
	const EVibeMMOHUDElement Element,
	const bool bLocked)
{
	FVibeMMOHUDElementLayout Layout = GetHUDElementLayout(Element);
	Layout.bLocked = bLocked;
	return CommitHUDElementLayout(Element, Layout);
}

bool UVibeMMOHUDWidget::ResetHUDElement(const EVibeMMOHUDElement Element)
{
	if (!VibeMMOHUDLayout::IsValidElement(Element))
	{
		return false;
	}
	if (GetHUDElementLayout(Element).IsDefault())
	{
		return false;
	}
	if (HUDLayoutSubsystem)
	{
		if (!HUDLayoutSubsystem->ResetElementLayout(Element))
		{
			RuntimeHUDLayoutProfile = HUDLayoutSubsystem->GetLayoutProfile();
			ApplyHUDElementLayout(Element);
			return false;
		}
		RuntimeHUDLayoutProfile = HUDLayoutSubsystem->GetLayoutProfile();
	}
	else
	{
		RuntimeHUDLayoutProfile.ResetElement(Element);
	}
	ApplyHUDElementLayout(Element);
	return true;
}

bool UVibeMMOHUDWidget::ResetAllHUDElements()
{
	if (GetHUDLayoutProfile().ElementOverrides.IsEmpty())
	{
		return false;
	}
	if (HUDLayoutSubsystem)
	{
		if (!HUDLayoutSubsystem->ResetLayout())
		{
			RuntimeHUDLayoutProfile = HUDLayoutSubsystem->GetLayoutProfile();
			ApplyHUDLayoutProfile();
			return false;
		}
		RuntimeHUDLayoutProfile = HUDLayoutSubsystem->GetLayoutProfile();
	}
	else
	{
		RuntimeHUDLayoutProfile.ResetToDefault();
	}
	ApplyHUDLayoutProfile();
	return true;
}

bool UVibeMMOHUDWidget::SaveHUDLayout()
{
	return HUDLayoutSubsystem && HUDLayoutSubsystem->SaveLayoutAsync();
}

void UVibeMMOHUDWidget::SetPortraitResource(UObject* PortraitResource)
{
	bool bUsedPortrait = false;
	if (PortraitResource)
	{
		ApplyBrushResource(PortraitImage, PortraitResource, FVector2D(68.0f, 68.0f));
		bUsedPortrait = true;
	}
	else
	{
		bUsedPortrait = TryApplyGeneratedPortrait();
	}

	if (PortraitFallbackText)
	{
		PortraitFallbackText->SetVisibility(bUsedPortrait ? ESlateVisibility::Collapsed : ESlateVisibility::HitTestInvisible);
	}
	if (PortraitImage)
	{
		PortraitImage->SetVisibility(bUsedPortrait ? ESlateVisibility::HitTestInvisible : ESlateVisibility::Collapsed);
		PortraitImage->SetColorAndOpacity(FLinearColor::White);
	}
}

void UVibeMMOHUDWidget::SetMinimapResource(UObject* MinimapResource)
{
	bHasRuntimeMinimapResource = MinimapResource != nullptr;
	ApplyBrushResource(MinimapImage, MinimapResource, FVector2D(202.0f, 202.0f));
	if (MinimapImage)
	{
		MinimapImage->SetColorAndOpacity(FLinearColor::White);
	}
	RefreshMinimapModeVisuals();
}

void UVibeMMOHUDWidget::SetMinimapMode(const EVibeMMOMinimapMode NewMode)
{
	if (MinimapMode != NewMode)
	{
		MinimapMode = NewMode;
		if (MinimapMode == EVibeMMOMinimapMode::Space)
		{
			SpaceMinimapRefreshAccumulator = 1.0f;
		}
	}

	RefreshMinimapModeVisuals();
}

void UVibeMMOHUDWidget::SetMinimapBlips(const TArray<FVector2D>& OffsetsPx)
{
	// Compact 210px map centered at (105,105); retain the existing 0.7 conversion
	// from the game's legacy 292px offsets and clamp contacts inside the frame.
	constexpr float MapRadius = 92.0f / 0.7f;
	constexpr float BlipHalf = 4.5f;
	for (int32 Index = 0; Index < MinimapBlipPool.Num(); ++Index)
	{
		UBorder* Blip = MinimapBlipPool[Index];
		if (!Blip)
		{
			continue;
		}
		if (!OffsetsPx.IsValidIndex(Index))
		{
			Blip->SetVisibility(ESlateVisibility::Collapsed);
			continue;
		}
		FVector2D Offset = OffsetsPx[Index];
		const float Len = Offset.Size();
		if (Len > MapRadius)
		{
			Offset *= MapRadius / Len;   // out-of-range hostiles pin to the rim as a direction hint
		}
		if (UCanvasPanelSlot* BlipSlot = Cast<UCanvasPanelSlot>(Blip->Slot))
		{
			BlipSlot->SetPosition(FVector2D(105.0f, 105.0f)
				+ Offset * 0.7f - FVector2D(BlipHalf, BlipHalf));
		}
		Blip->SetVisibility(ESlateVisibility::HitTestInvisible);
	}
}

void UVibeMMOHUDWidget::SetAbilityIconResource(const int32 AbilityIndex, UObject* IconResource)
{
	if (!AbilityIconImages.IsValidIndex(AbilityIndex))
	{
		return;
	}

	ApplyBrushResource(AbilityIconImages[AbilityIndex], IconResource, FVector2D(48.0f, 48.0f));
	if (AbilityIconImages[AbilityIndex])
	{
		AbilityIconImages[AbilityIndex]->SetVisibility(IconResource ? ESlateVisibility::HitTestInvisible : ESlateVisibility::Collapsed);
	}

	if (AbilityIconFallbackTexts.IsValidIndex(AbilityIndex) && AbilityIconFallbackTexts[AbilityIndex])
	{
		AbilityIconFallbackTexts[AbilityIndex]->SetVisibility(IconResource ? ESlateVisibility::Collapsed : ESlateVisibility::HitTestInvisible);
	}
	SetAbilitySlotVisible(AbilityIndex, IconResource != nullptr);
}

void UVibeMMOHUDWidget::SetAbilitySlotLabel(const int32 AbilityIndex, const FText Label)
{
	if (AbilityNameTexts.IsValidIndex(AbilityIndex) && AbilityNameTexts[AbilityIndex])
	{
		AbilityNameTexts[AbilityIndex]->SetText(Label);
		AbilityNameTexts[AbilityIndex]->SetVisibility(
			Label.IsEmpty() ? ESlateVisibility::Collapsed : ESlateVisibility::HitTestInvisible);
	}
}

void UVibeMMOHUDWidget::SetSelectedWeaponSlot(const int32 WeaponIndex)
{
	if (WeaponIndex < 0)
	{
		return;
	}

	SelectedWeaponSlot = WeaponIndex;
	RefreshWeaponSlotVisuals();
}

void UVibeMMOHUDWidget::SetWeaponSlotRarity(const int32 WeaponIndex, const EVibeMMOItemRarity Rarity)
{
	if (WeaponIndex < 0)
	{
		return;
	}

	if (WeaponSlotRarities.Num() <= WeaponIndex)
	{
		WeaponSlotRarities.SetNum(WeaponIndex + 1);
	}
	WeaponSlotRarities[WeaponIndex] = Rarity;
	RefreshWeaponSlotVisuals();
}

void UVibeMMOHUDWidget::SetWeaponHeatState(const int32 WeaponIndex, const float HeatFraction, const bool bOverheated, const bool bCooling)
{
	if (WeaponIndex < 0)
	{
		return;
	}

	const float ClampedHeat = FMath::Clamp(HeatFraction, 0.0f, 1.0f);
	const int32 RequiredSize = WeaponIndex + 1;
	if (TargetWeaponHeatRatios.Num() < RequiredSize)
	{
		TargetWeaponHeatRatios.SetNumZeroed(RequiredSize);
		DisplayedWeaponHeatRatios.SetNumZeroed(RequiredSize);
		WeaponOverheatedStates.SetNumZeroed(RequiredSize);
		WeaponCoolingStates.SetNumZeroed(RequiredSize);
	}
	TargetWeaponHeatRatios[WeaponIndex] = ClampedHeat;
	if (DisplayedWeaponHeatRatios[WeaponIndex] <= KINDA_SMALL_NUMBER && ClampedHeat > KINDA_SMALL_NUMBER)
	{
		DisplayedWeaponHeatRatios[WeaponIndex] = ClampedHeat;
	}
	WeaponOverheatedStates[WeaponIndex] = bOverheated ? 1 : 0;
	WeaponCoolingStates[WeaponIndex] = ClampedHeat > KINDA_SMALL_NUMBER && (bCooling || bOverheated) ? 1 : 0;
	RefreshWeaponSlotVisuals();
}

void UVibeMMOHUDWidget::SetReticleTargetAlpha(const float InTargetAlpha)
{
	TargetReticleAlpha = FMath::Clamp(InTargetAlpha, 0.0f, 1.0f);
}

FLinearColor UVibeMMOHUDWidget::ResolveWeaponRarityColor(const EVibeMMOItemRarity Rarity) const
{
	if (const UVibeMMOUIStyleDataAsset* Style = GetResolvedStyleDataAsset())
	{
		switch (Rarity)
		{
		case EVibeMMOItemRarity::Common:    return Style->CommonRarityColor;
		case EVibeMMOItemRarity::Uncommon:  return Style->UncommonRarityColor;
		case EVibeMMOItemRarity::Rare:      return Style->RareRarityColor;
		case EVibeMMOItemRarity::Epic:      return Style->EpicRarityColor;
		case EVibeMMOItemRarity::Legendary: return Style->LegendaryRarityColor;
		case EVibeMMOItemRarity::Mythic:    return Style->MythicRarityColor;
		default:                            break;
		}
	}

	switch (Rarity)
	{
	case EVibeMMOItemRarity::Uncommon:  return FLinearColor(0.16f, 0.92f, 0.36f, 1.0f);
	case EVibeMMOItemRarity::Rare:      return FLinearColor(0.12f, 0.46f, 1.0f, 1.0f);
	case EVibeMMOItemRarity::Epic:      return FLinearColor(0.68f, 0.22f, 1.0f, 1.0f);
	case EVibeMMOItemRarity::Legendary: return FLinearColor(1.0f, 0.66f, 0.08f, 1.0f);
	case EVibeMMOItemRarity::Mythic:    return FLinearColor(1.0f, 0.18f, 0.08f, 1.0f);
	case EVibeMMOItemRarity::Common:
	default:                            return FLinearColor(0.85f, 0.88f, 0.92f, 1.0f);
	}
}

void UVibeMMOHUDWidget::RefreshWeaponSlotVisuals()
{
	const FLinearColor CoolingColor(0.08f, 0.92f, 1.0f, 1.0f);
	const FLinearColor OverheatColor(1.0f, 0.07f, 0.025f, 1.0f);
	const FLinearColor WarmHeatColor(1.0f, 0.66f, 0.04f, 1.0f);
	const float PulseAlpha = 0.5f + 0.5f * FMath::Sin(static_cast<float>(FPlatformTime::Seconds()) * 7.0f);

	for (int32 Index = 0; Index < WeaponSlotRoots.Num(); ++Index)
	{
		const bool bSelected = Index == SelectedWeaponSlot;
		const float HeatRatio = DisplayedWeaponHeatRatios.IsValidIndex(Index)
			? DisplayedWeaponHeatRatios[Index] : 0.0f;
		const bool bOverheated = WeaponOverheatedStates.IsValidIndex(Index)
			&& WeaponOverheatedStates[Index] != 0;
		const bool bCooling = WeaponCoolingStates.IsValidIndex(Index)
			&& WeaponCoolingStates[Index] != 0 && !bOverheated;
		const bool bShowHeat = HeatRatio > KINDA_SMALL_NUMBER || bOverheated;
		const EVibeMMOItemRarity Rarity = WeaponSlotRarities.IsValidIndex(Index)
			? WeaponSlotRarities[Index] : EVibeMMOItemRarity::Common;
		const FLinearColor RarityColor = ResolveWeaponRarityColor(Rarity);

		// Rarity is the permanent card surface. Keep it fully opaque and independent of selection,
		// heat and cooling so the Epic purple / Legendary gold / Uncommon green never gets replaced
		// by a delayed state refresh. The authored weapon art has transparent pixels specifically so
		// this semantic color remains visible behind the rifle silhouette.
		FLinearColor RarityFillColor = RarityColor;
		RarityFillColor.A = 1.0f;

		// Selection is communicated by the outer outline and a very small icon scale change. It does
		// not tint or dim the rarity surface itself.
		FLinearColor BorderColor = bSelected
			? FMath::Lerp(RarityColor, FLinearColor::White, 0.34f)
			: FMath::Lerp(RarityColor, FLinearColor(0.015f, 0.02f, 0.035f, 1.0f), 0.28f);
		BorderColor.A = 1.0f;

		FLinearColor StateColor = FLinearColor::Transparent;
		if (bOverheated)
		{
			StateColor = OverheatColor;
			StateColor.A = 0.72f + PulseAlpha * 0.28f;
		}
		else if (bCooling)
		{
			StateColor = CoolingColor;
			StateColor.A = 0.92f;
		}

		if (WeaponRarityBorders.IsValidIndex(Index) && WeaponRarityBorders[Index])
		{
			WeaponRarityBorders[Index]->SetBrushColor(BorderColor);
		}
		if (WeaponRarityBackgrounds.IsValidIndex(Index) && WeaponRarityBackgrounds[Index])
		{
			WeaponRarityBackgrounds[Index]->SetBrushColor(RarityFillColor);
		}
		if (WeaponStateFrames.IsValidIndex(Index) && WeaponStateFrames[Index])
		{
			WeaponStateFrames[Index]->SetBrushColor(StateColor);
			WeaponStateFrames[Index]->SetVisibility(
				(bOverheated || bCooling) ? ESlateVisibility::HitTestInvisible : ESlateVisibility::Collapsed);
		}

		if (WeaponIconImages.IsValidIndex(Index) && WeaponIconImages[Index])
		{
			// Never fade the image alpha when a slot becomes inactive. The source cards use alpha to
			// reveal the solid rarity surface; multiplying that alpha again made a delayed dark overlay
			// appear once the per-frame heat refresh began. A mild RGB change is enough for hierarchy.
			WeaponIconImages[Index]->SetColorAndOpacity(
				bSelected ? FLinearColor::White : FLinearColor(0.80f, 0.82f, 0.86f, 1.0f));
			WeaponIconImages[Index]->SetRenderTransformPivot(FVector2D(0.5f, 0.5f));
			WeaponIconImages[Index]->SetRenderScale(bSelected ? FVector2D(1.0f, 1.0f) : FVector2D(0.96f, 0.96f));
		}

		if (WeaponHeatBars.IsValidIndex(Index) && WeaponHeatBars[Index])
		{
			UProgressBar* HeatBar = WeaponHeatBars[Index];
			HeatBar->SetPercent(HeatRatio);
			HeatBar->SetVisibility(bShowHeat ? ESlateVisibility::HitTestInvisible : ESlateVisibility::Collapsed);

			FLinearColor HeatColor;
			if (bOverheated)
			{
				HeatColor = OverheatColor;
				HeatColor.A = 0.82f + PulseAlpha * 0.18f;
			}
			else if (bCooling)
			{
				HeatColor = CoolingColor;
			}
			else if (HeatRatio < 0.68f)
			{
				HeatColor = FMath::Lerp(CoolingColor, WarmHeatColor, HeatRatio / 0.68f);
			}
			else
			{
				HeatColor = FMath::Lerp(WarmHeatColor, OverheatColor,
					(HeatRatio - 0.68f) / 0.32f);
			}
			HeatBar->SetFillColorAndOpacity(HeatColor);
		}
	}
}

void UVibeMMOHUDWidget::SetWeaponIconResource(const int32 WeaponIndex, UObject* IconResource)
{
	if (!WeaponIconImages.IsValidIndex(WeaponIndex))
	{
		return;
	}

	ApplyBrushResource(WeaponIconImages[WeaponIndex], IconResource, FVector2D(106.0f, 58.0f));

	if (WeaponIconFallbackTexts.IsValidIndex(WeaponIndex) && WeaponIconFallbackTexts[WeaponIndex])
	{
		WeaponIconFallbackTexts[WeaponIndex]->SetVisibility(IconResource ? ESlateVisibility::Collapsed : ESlateVisibility::HitTestInvisible);
	}
}

void UVibeMMOHUDWidget::SetTargetingRectangles(const TArray<FVibeMMOTargetingRectangle>& InRectangles)
{
	ActiveTargetingRectangles = InRectangles;
	bTargetingRectanglesOverridden = true;
	RebuildTargetingRectangles();
}

void UVibeMMOHUDWidget::AddTargetingRectangle(const FVibeMMOTargetingRectangle& InRectangle)
{
	ActiveTargetingRectangles.Add(InRectangle);
	bTargetingRectanglesOverridden = true;
	RebuildTargetingRectangles();
}

void UVibeMMOHUDWidget::ClearTargetingRectangles()
{
	ActiveTargetingRectangles.Reset();
	bTargetingRectanglesOverridden = true;
	RebuildTargetingRectangles();
}

void UVibeMMOHUDWidget::ApplyVibeStyle_Implementation()
{
	Super::ApplyVibeStyle_Implementation();
	ApplyHUDTextRoles();
	ApplyHUDColors();
	RebuildTargetingRectangles();
}

void UVibeMMOHUDWidget::NativePreConstruct()
{
	if (bBuildDefaultHUDInCpp)
	{
		BuildDefaultHUDTree();
	}

	Super::NativePreConstruct();

	if (bUseMockValues)
	{
		ApplyMockTextValues();
	}

	if (bUseMockTargetingRectangles && !bTargetingRectanglesOverridden)
	{
		ApplyMockTargetingRectangles();
	}
	else
	{
		RebuildTargetingRectangles();
	}
}

void UVibeMMOHUDWidget::NativeConstruct()
{
	Super::NativeConstruct();

	if (ULocalPlayer* LocalPlayer = GetOwningLocalPlayer())
	{
		HUDLayoutSubsystem = LocalPlayer->GetSubsystem<UVibeMMOHUDLayoutSubsystem>();
	}
	if (HUDLayoutSubsystem && HUDLayoutSubsystem->LoadOrCreateLayout())
	{
		HUDLayoutSubsystem->OnLayoutChanged.AddUniqueDynamic(
			this, &UVibeMMOHUDWidget::HandleHUDLayoutChanged);
		RuntimeHUDLayoutProfile = HUDLayoutSubsystem->GetLayoutProfile();
	}
	ApplyHUDLayoutProfile();
}

void UVibeMMOHUDWidget::NativeDestruct()
{
	if (HUDLayoutSubsystem)
	{
		HUDLayoutSubsystem->OnLayoutChanged.RemoveDynamic(
			this, &UVibeMMOHUDWidget::HandleHUDLayoutChanged);
	}
	HUDLayoutSubsystem = nullptr;
	Super::NativeDestruct();
}

void UVibeMMOHUDWidget::HandleHUDLayoutChanged()
{
	if (HUDLayoutSubsystem)
	{
		RuntimeHUDLayoutProfile = HUDLayoutSubsystem->GetLayoutProfile();
	}
	ApplyHUDLayoutProfile();
}

void UVibeMMOHUDWidget::NativeTick(const FGeometry& MyGeometry, float InDeltaTime)
{
	Super::NativeTick(MyGeometry, InDeltaTime);

	for (int32 Index = 0; Index < TargetWeaponHeatRatios.Num(); ++Index)
	{
		if (!DisplayedWeaponHeatRatios.IsValidIndex(Index))
		{
			break;
		}
		DisplayedWeaponHeatRatios[Index] = FMath::FInterpTo(
			DisplayedWeaponHeatRatios[Index], TargetWeaponHeatRatios[Index], InDeltaTime, 11.0f);
		if (FMath::IsNearlyEqual(
			DisplayedWeaponHeatRatios[Index], TargetWeaponHeatRatios[Index], 0.001f))
		{
			DisplayedWeaponHeatRatios[Index] = TargetWeaponHeatRatios[Index];
		}
	}
	// Refresh every frame while the HUD exists so the overheat frame can pulse even when the
	// compass is idle. All values here belong to the locally controlled pawn's retained widget.
	RefreshWeaponSlotVisuals();

	DisplayedReticleAlpha = FMath::FInterpTo(
		DisplayedReticleAlpha, TargetReticleAlpha, InDeltaTime, 12.0f);
	if (FMath::IsNearlyEqual(DisplayedReticleAlpha, TargetReticleAlpha, 0.001f))
	{
		DisplayedReticleAlpha = TargetReticleAlpha;
	}

	if (ReticleImage)
	{
		const float LockScale = FMath::Lerp(1.0f, 1.08f, DisplayedReticleAlpha);
		ReticleImage->SetRenderScale(FVector2D(LockScale, LockScale));
		ReticleImage->SetRenderOpacity(FMath::Lerp(0.90f, 1.0f, DisplayedReticleAlpha));
	}
	if (ReticleDynamicMaterial)
	{
		const FLinearColor DefaultRed(1.0f, 0.055f, 0.025f, 1.0f);
		const FLinearColor DefaultGreen(0.26f, 1.0f, 0.035f, 1.0f);
		const FLinearColor DefaultBlue(0.02f, 0.42f, 1.0f, 1.0f);
		const FLinearColor LockRed(1.0f, 0.025f, 0.01f, 1.0f);
		const FLinearColor LockOrange(1.0f, 0.16f, 0.015f, 1.0f);
		ReticleDynamicMaterial->SetVectorParameterValue(
			TEXT("Red channel color"), FMath::Lerp(DefaultRed, LockRed, DisplayedReticleAlpha));
		ReticleDynamicMaterial->SetVectorParameterValue(
			TEXT("Green channel color"), FMath::Lerp(DefaultGreen, LockOrange, DisplayedReticleAlpha));
		ReticleDynamicMaterial->SetVectorParameterValue(
			TEXT("Blue channel Color"), FMath::Lerp(DefaultBlue, LockRed, DisplayedReticleAlpha));
	}

	if (MinimapMode == EVibeMMOMinimapMode::Space)
	{
		SpaceMinimapRefreshAccumulator += InDeltaTime;
		if (SpaceMinimapRefreshAccumulator >= 0.20f)
		{
			SpaceMinimapRefreshAccumulator = 0.0f;
			RefreshSpaceMinimapNavigation();
		}
	}

	if (!bCompassHeadingInitialized || CompassLabelTexts.Num() == 0)
	{
		return;
	}

	const float Delta = FRotator::NormalizeAxis(TargetCompassHeadingDegrees - DisplayedCompassHeadingDegrees);
	if (FMath::IsNearlyZero(Delta, 0.05f))
	{
		return;
	}

	const float Blend = FMath::Clamp(InDeltaTime * 8.0f, 0.0f, 1.0f);
	DisplayedCompassHeadingDegrees = FRotator::NormalizeAxis(DisplayedCompassHeadingDegrees + Delta * Blend);
	RefreshCompassLabels();
}

void UVibeMMOHUDWidget::BuildDefaultHUDTree()
{
	if (!WidgetTree || bDefaultHUDTreeBuilt)
	{
		return;
	}

	if (WidgetTree->RootWidget && WidgetTree->RootWidget->GetFName() != FName(TEXT("DefaultVibeHUDRoot")))
	{
		// A WBP subclass may ship a default root panel; discard it and build our HUD so the
		// C++ default layout works from any Widget Blueprint child (not just an empty one).
		WidgetTree->RootWidget = nullptr;
	}

	StyledColorBlocks.Reset();
	HUDElementWidgets.Reset();
	HUDElementBaselineSlots.Reset();
	AbilityIconImages.Reset();
	AbilityIconFallbackTexts.Reset();
	AbilityNameTexts.Reset();
	AbilityCooldownBars.Reset();
	AbilityCooldownTexts.Reset();
	AbilitySlotRoots.Reset();
	WeaponIconImages.Reset();
	WeaponIconFallbackTexts.Reset();
	WeaponSlotRoots.Reset();
	WeaponRarityBorders.Reset();
	WeaponRarityBackgrounds.Reset();
	WeaponStateFrames.Reset();
	WeaponHeatBars.Reset();
	WeaponSlotRarities.Reset();
	TargetWeaponHeatRatios.Reset();
	DisplayedWeaponHeatRatios.Reset();
	WeaponOverheatedStates.Reset();
	WeaponCoolingStates.Reset();
	RuntimePortraitBrush.Reset();
	RuntimeMinimapBrush.Reset();
	TargetingRectangleWidgets.Reset();
	ShieldSegmentBlocks.Reset();
	PortraitImage = nullptr;
	PortraitFallbackText = nullptr;
	MinimapImage = nullptr;
	MinimapBaseImage = nullptr;
	MinimapSurfaceLayer = nullptr;
	MinimapSpaceLayer = nullptr;
	SpaceMinimapMarkerPool.Reset();
	SpaceMinimapHeadingText = nullptr;
	SpaceMinimapNearestText = nullptr;
	SpaceMinimapRefreshAccumulator = 0.0f;
	TargetingCanvas = nullptr;
	ReticleImage = nullptr;
	ReticleDynamicMaterial = nullptr;
	ShieldBarBlock = nullptr;
	HealthBarBlock = nullptr;
	FuelBarBlock = nullptr;
	ResourceBarBlock = nullptr;
	AbilityLoadoutOverlay = nullptr;
	AbilityLoadoutQAssignmentText = nullptr;
	AbilityLoadoutEAssignmentText = nullptr;

	UCanvasPanel* RootCanvas = WidgetTree->ConstructWidget<UCanvasPanel>(UCanvasPanel::StaticClass(), TEXT("DefaultVibeHUDRoot"));
	WidgetTree->RootWidget = RootCanvas;

	AddStatusPanel(RootCanvas);
	AddCompass(RootCanvas);
	AddMinimap(RootCanvas);
	AddTargetingLayer(RootCanvas);
	AddReticle(RootCanvas);
	AddAbilityBar(RootCanvas);
	AddWeaponSlots(RootCanvas);
	AddAbilityLoadoutOverlay(RootCanvas);
	ApplyHUDLayoutProfile();

	bDefaultHUDTreeBuilt = true;
}

void UVibeMMOHUDWidget::RegisterHUDElement(
	const EVibeMMOHUDElement Element,
	UWidget* Widget,
	const FVibeMMOHUDAnchorSlot& BaselineSlot)
{
	if (!Widget || !VibeMMOHUDLayout::IsValidElement(Element))
	{
		return;
	}
	HUDElementWidgets.Add(Element, Widget);
	HUDElementBaselineSlots.Add(Element, BaselineSlot);
	ApplyHUDElementLayout(Element);
}

FVector2D UVibeMMOHUDWidget::ResolveHUDSafeAreaSize() const
{
	FVector2D ViewportSize(1920.0f, 1080.0f);
	if (GetWorld())
	{
		ViewportSize = UWidgetLayoutLibrary::GetViewportSize(this);
		const float ViewportScale = FMath::Max(
			0.01f, UWidgetLayoutLibrary::GetViewportScale(this));
		ViewportSize /= ViewportScale;
	}
	if (ViewportSize.X < 1.0f || ViewportSize.Y < 1.0f)
	{
		ViewportSize = FVector2D(1920.0f, 1080.0f);
	}

	FMargin SafePadding(32.0f, 28.0f, 32.0f, 28.0f);
	if (const UVibeMMOHUDLayoutDataAsset* LayoutData = GetResolvedHUDLayoutDataAsset())
	{
		SafePadding = LayoutData->SafeZonePadding;
	}
	else if (const UVibeMMOUIStyleDataAsset* Style = GetResolvedStyleDataAsset())
	{
		SafePadding = Style->HUDSafeZonePadding;
	}

	return FVector2D(
		FMath::Max(1.0f, ViewportSize.X - SafePadding.Left - SafePadding.Right),
		FMath::Max(1.0f, ViewportSize.Y - SafePadding.Top - SafePadding.Bottom));
}

void UVibeMMOHUDWidget::ApplyHUDElementLayout(const EVibeMMOHUDElement Element)
{
	const TObjectPtr<UWidget>* WidgetPtr = HUDElementWidgets.Find(Element);
	const FVibeMMOHUDAnchorSlot* Baseline = HUDElementBaselineSlots.Find(Element);
	UWidget* Widget = WidgetPtr ? WidgetPtr->Get() : nullptr;
	if (!Widget || !Baseline)
	{
		return;
	}

	const FVibeMMOHUDElementLayout Layout = RuntimeHUDLayoutProfile.GetElementLayout(Element);
	if (UCanvasPanelSlot* CanvasSlot = Cast<UCanvasPanelSlot>(Widget->Slot))
	{
		CanvasSlot->SetAnchors(Baseline->Anchors);
		CanvasSlot->SetAlignment(Baseline->Alignment);
		CanvasSlot->SetPosition(
			Baseline->Position + Layout.NormalizedOffset * ResolveHUDSafeAreaSize());
		CanvasSlot->SetSize(Baseline->Size);
	}

	Widget->SetRenderTransformPivot(Baseline->Alignment);
	Widget->SetRenderScale(FVector2D(Layout.Scale, Layout.Scale));
	Widget->SetRenderOpacity(Layout.Opacity);
	const bool bMissingReticleResource = Element == EVibeMMOHUDElement::Reticle
		&& (!ReticleImage
			|| !IsValid(ReticleImage->GetBrush().GetResourceObject()));
	Widget->SetVisibility(Layout.bHidden || bMissingReticleResource
		? ESlateVisibility::Collapsed
		: ESlateVisibility::HitTestInvisible);
}

void UVibeMMOHUDWidget::ApplyHUDLayoutProfile()
{
	for (const EVibeMMOHUDElement Element : VibeMMOHUDLayout::GetElements())
	{
		ApplyHUDElementLayout(Element);
	}
}

bool UVibeMMOHUDWidget::CommitHUDElementLayout(
	const EVibeMMOHUDElement Element,
	const FVibeMMOHUDElementLayout& Layout)
{
	if (!VibeMMOHUDLayout::IsValidElement(Element))
	{
		return false;
	}

	FVibeMMOHUDElementLayout Sanitized = Layout;
	Sanitized.Sanitize();
	if (GetHUDElementLayout(Element).NearlyEquals(Sanitized))
	{
		return false;
	}
	RuntimeHUDLayoutProfile.SetElementLayout(Element, Sanitized);
	if (HUDLayoutSubsystem)
	{
		if (!HUDLayoutSubsystem->SetElementLayout(Element, Sanitized))
		{
			RuntimeHUDLayoutProfile = HUDLayoutSubsystem->GetLayoutProfile();
			ApplyHUDElementLayout(Element);
			return false;
		}
		RuntimeHUDLayoutProfile = HUDLayoutSubsystem->GetLayoutProfile();
	}
	ApplyHUDElementLayout(Element);
	return true;
}

const UVibeMMOHUDLayoutDataAsset* UVibeMMOHUDWidget::GetResolvedHUDLayoutDataAsset() const
{
	return HUDLayoutDataAsset;
}

void UVibeMMOHUDWidget::ApplyBrushResource(UImage* Image, UObject* Resource, const FVector2D& ImageSize) const
{
	if (!Image)
	{
		return;
	}

	if (!Resource)
	{
		// UImage begins with Slate's opaque white default brush. Clear it as well as
		// collapsing the widget so a later HUD-layout pass cannot reveal a white tile.
		Image->SetBrush(FSlateBrush());
		Image->SetVisibility(ESlateVisibility::Collapsed);
		return;
	}

	FSlateBrush Brush;
	Brush.SetResourceObject(Resource);
	Brush.ImageSize = ImageSize;
	Image->SetBrush(Brush);
	Image->SetVisibility(ESlateVisibility::HitTestInvisible);
}

bool UVibeMMOHUDWidget::ApplyRuntimePngBrush(UImage* Image, const FString& AbsolutePath, const FVector2D& ImageSize, TSharedPtr<FSlateDynamicImageBrush>& BrushStorage)
{
	if (!Image || AbsolutePath.IsEmpty() || !FPaths::FileExists(AbsolutePath))
	{
		return false;
	}

	BrushStorage = MakeShared<FSlateDynamicImageBrush>(FName(*AbsolutePath), ImageSize);
	Image->SetBrush(*BrushStorage);
	Image->SetVisibility(ESlateVisibility::HitTestInvisible);
	return true;
}

void UVibeMMOHUDWidget::RefreshMinimapModeVisuals()
{
	const bool bSpaceMode = MinimapMode == EVibeMMOMinimapMode::Space;
	const bool bShowGeneratedSurfaceMap = !bSpaceMode && !bHasRuntimeMinimapResource;
	const bool bShowLiveSurfaceMap = !bSpaceMode && bHasRuntimeMinimapResource;

	if (MinimapBaseImage)
	{
		MinimapBaseImage->SetVisibility(bShowGeneratedSurfaceMap ? ESlateVisibility::HitTestInvisible : ESlateVisibility::Collapsed);
	}

	if (MinimapImage)
	{
		MinimapImage->SetVisibility(bShowLiveSurfaceMap ? ESlateVisibility::HitTestInvisible : ESlateVisibility::Collapsed);
		MinimapImage->SetColorAndOpacity(FLinearColor(1.0f, 1.0f, 1.0f, bShowLiveSurfaceMap ? 1.0f : 0.0f));
	}

	if (MinimapSurfaceLayer)
	{
		MinimapSurfaceLayer->SetVisibility(bSpaceMode ? ESlateVisibility::Collapsed : ESlateVisibility::HitTestInvisible);
	}

	if (MinimapSpaceLayer)
	{
		MinimapSpaceLayer->SetVisibility(bSpaceMode ? ESlateVisibility::HitTestInvisible : ESlateVisibility::Collapsed);
	}

}

void UVibeMMOHUDWidget::RefreshSpaceMinimapNavigation()
{
	APlayerController* PlayerController = GetOwningPlayer();
	UWorld* World = GetWorld();
	AActor* ReferenceActor = PlayerController ? PlayerController->GetPawn() : nullptr;
	if (!ReferenceActor && PlayerController)
	{
		ReferenceActor = PlayerController->GetViewTarget();
	}
	if (!World || !IsValid(ReferenceActor))
	{
		return;
	}

	const float HeadingDegrees = FRotator::ClampAxis(ReferenceActor->GetActorRotation().Yaw);
	SetCompassHeadingDegrees(HeadingDegrees);
	if (SpaceMinimapHeadingText)
	{
		SpaceMinimapHeadingText->SetText(FText::FromString(FString::Printf(
			TEXT("%s  %03d"),
			*VibeMMOHUD::CompassCardinalText(HeadingDegrees).ToString(),
			FMath::RoundToInt(HeadingDegrees) % 360)));
	}

	enum class ESpaceContactType : uint8
	{
		Planet,
		Moon,
		Ore,
		MiningSite,
		Craft
	};
	struct FSpaceContact
	{
		FVector Location = FVector::ZeroVector;
		float DistanceCm = 0.0f;
		ESpaceContactType Type = ESpaceContactType::Ore;
	};

	TArray<FSpaceContact> Contacts;
	TSet<const AActor*> SeenActors;
	const FVector ReferenceLocation = ReferenceActor->GetActorLocation();
	auto AddContact = [&Contacts, &ReferenceLocation](
		const FVector& Location, const ESpaceContactType Type)
	{
		const float DistanceCm = FVector::Distance(ReferenceLocation, Location);
		if (DistanceCm > 2000.0f && FMath::IsFinite(DistanceCm))
		{
			Contacts.Add({ Location, DistanceCm, Type });
		}
	};

	TArray<AActor*> TaggedActors;
	UGameplayStatics::GetAllActorsWithTag(World, TEXT("RedMineableSpaceAsteroid"), TaggedActors);
	for (AActor* Actor : TaggedActors)
	{
		if (IsValid(Actor) && !Actor->IsHidden())
		{
			SeenActors.Add(Actor);
			AddContact(Actor->GetActorLocation(), ESpaceContactType::Ore);
		}
	}

	TaggedActors.Reset();
	UGameplayStatics::GetAllActorsWithTag(World, TEXT("VibeOrbitalMining"), TaggedActors);
	for (AActor* Actor : TaggedActors)
	{
		if (IsValid(Actor) && !Actor->IsHidden())
		{
			SeenActors.Add(Actor);
			AddContact(Actor->GetActorLocation(), ESpaceContactType::MiningSite);
		}
	}

	// The scenery actor is planet-centred and owns the physical moon component. Reading
	// those real transforms keeps the radar honest; no static demo MARS/MOON labels remain.
	TaggedActors.Reset();
	UGameplayStatics::GetAllActorsWithTag(World, TEXT("RedSpaceScenery"), TaggedActors);
	for (AActor* Actor : TaggedActors)
	{
		if (!IsValid(Actor))
		{
			continue;
		}
		AddContact(Actor->GetActorLocation(), ESpaceContactType::Planet);
		TInlineComponentArray<USceneComponent*> SceneComponents(Actor);
		for (const USceneComponent* Component : SceneComponents)
		{
			if (IsValid(Component)
				&& Component->ComponentHasTag(TEXT("RedGravityBody.Moon")))
			{
				AddContact(Component->GetComponentLocation(), ESpaceContactType::Moon);
			}
		}
	}

	for (TActorIterator<APawn> It(World); It; ++It)
	{
		APawn* Pawn = *It;
		if (!IsValid(Pawn) || Pawn == ReferenceActor || Pawn->IsHidden()
			|| SeenActors.Contains(Pawn))
		{
			continue;
		}
		const FString Identity = Pawn->GetClass()->GetName() + TEXT(" ") + Pawn->GetName();
		if (Identity.Contains(TEXT("Ship"), ESearchCase::IgnoreCase)
			|| Identity.Contains(TEXT("Shuttle"), ESearchCase::IgnoreCase)
			|| Identity.Contains(TEXT("Fighter"), ESearchCase::IgnoreCase))
		{
			AddContact(Pawn->GetActorLocation(), ESpaceContactType::Craft);
		}
	}

	Contacts.Sort([](const FSpaceContact& A, const FSpaceContact& B)
	{
		return A.DistanceCm < B.DistanceCm;
	});

	const FVector Forward = ReferenceActor->GetActorForwardVector().GetSafeNormal();
	const FVector Right = ReferenceActor->GetActorRightVector().GetSafeNormal();
	constexpr float RadarRangeCm = 5000000.0f; // 50 km tactical range
	constexpr float MapCenter = 105.0f;
	constexpr float MapRadius = 82.0f;
	for (int32 Index = 0; Index < SpaceMinimapMarkerPool.Num(); ++Index)
	{
		UBorder* Marker = SpaceMinimapMarkerPool[Index];
		if (!Marker)
		{
			continue;
		}
		if (!Contacts.IsValidIndex(Index))
		{
			Marker->SetVisibility(ESlateVisibility::Collapsed);
			continue;
		}

		const FSpaceContact& Contact = Contacts[Index];
		const FVector Delta = Contact.Location - ReferenceLocation;
		FVector2D RadarOffset(
			FVector::DotProduct(Delta, Right),
			-FVector::DotProduct(Delta, Forward));
		RadarOffset /= RadarRangeCm;
		const bool bPinnedToRim = RadarOffset.SizeSquared() > 1.0f;
		if (bPinnedToRim)
		{
			RadarOffset.Normalize();
		}

		FLinearColor Color(1.0f, 0.76f, 0.18f, 0.96f);
		float MarkerSize = 7.0f;
		switch (Contact.Type)
		{
		case ESpaceContactType::Planet:
			Color = FLinearColor(0.14f, 0.55f, 1.0f, 0.98f);
			MarkerSize = 11.0f;
			break;
		case ESpaceContactType::Moon:
			Color = FLinearColor(0.75f, 0.88f, 1.0f, 0.98f);
			MarkerSize = 9.0f;
			break;
		case ESpaceContactType::MiningSite:
			Color = FLinearColor(0.08f, 0.92f, 1.0f, 0.98f);
			MarkerSize = 9.0f;
			break;
		case ESpaceContactType::Craft:
			Color = FLinearColor(0.20f, 1.0f, 0.42f, 0.98f);
			MarkerSize = 8.0f;
			break;
		default:
			break;
		}
		Marker->SetBrushColor(Color);
		Marker->SetRenderOpacity(bPinnedToRim ? 0.68f : 1.0f);
		if (UCanvasPanelSlot* MarkerSlot = Cast<UCanvasPanelSlot>(Marker->Slot))
		{
			MarkerSlot->SetPosition(
				FVector2D(MapCenter) + RadarOffset * MapRadius - FVector2D(MarkerSize * 0.5f));
			MarkerSlot->SetSize(FVector2D(MarkerSize));
		}
		Marker->SetVisibility(ESlateVisibility::HitTestInvisible);
	}

	if (SpaceMinimapNearestText)
	{
		if (Contacts.IsEmpty())
		{
			SpaceMinimapNearestText->SetText(FText::FromString(TEXT("NO CONTACTS  <50 KM")));
		}
		else
		{
			const FSpaceContact& Nearest = Contacts[0];
			const TCHAR* ContactName = TEXT("ORE");
			switch (Nearest.Type)
			{
			case ESpaceContactType::Planet: ContactName = TEXT("PLANET"); break;
			case ESpaceContactType::Moon: ContactName = TEXT("MOON"); break;
			case ESpaceContactType::MiningSite: ContactName = TEXT("MINING SITE"); break;
			case ESpaceContactType::Craft: ContactName = TEXT("CRAFT"); break;
			default: break;
			}
			SpaceMinimapNearestText->SetText(FText::FromString(FString::Printf(
				TEXT("%s  %.1f KM"), ContactName, Nearest.DistanceCm / 100000.0f)));
		}
	}
}

bool UVibeMMOHUDWidget::TryApplyGeneratedPortrait()
{
	if (ApplyRuntimePngBrush(
		PortraitImage,
		FPaths::Combine(FPaths::ProjectSavedDir(), TEXT("VibeEngine/Generated/player_portrait_clean.png")),
		FVector2D(96.0f, 96.0f),
		RuntimePortraitBrush))
	{
		return true;
	}

	if (ApplyRuntimePngBrush(
		PortraitImage,
		FPaths::Combine(FPaths::ProjectSavedDir(), TEXT("VibeEngine/Generated/player_portrait_static.png")),
		FVector2D(96.0f, 96.0f),
		RuntimePortraitBrush))
	{
		return true;
	}

	UObject* CookedPortrait = LoadObject<UObject>(
		nullptr,
		TEXT("/Game/RedMMO/UI/Generated/player_portrait_static.player_portrait_static"));
	if (CookedPortrait)
	{
		ApplyBrushResource(PortraitImage, CookedPortrait, FVector2D(96.0f, 96.0f));
		return true;
	}

	return false;
}

bool UVibeMMOHUDWidget::TryApplyGeneratedMinimap()
{
	return ApplyRuntimePngBrush(
		MinimapBaseImage,
		FPaths::Combine(FPaths::ProjectSavedDir(), TEXT("VibeEngine/Generated/minimap_stylized_planet.png")),
		FVector2D(292.0f, 292.0f),
		RuntimeMinimapBrush);
}

void UVibeMMOHUDWidget::AddStatusPanel(UCanvasPanel* RootCanvas)
{
	// Compact TL status: portrait + shield + health + yellow fuel (no numeric overlays).
	const FVector2D PanelSize(350.0f, 108.0f);
	const FVibeMMOHUDAnchorSlot StatusAnchor(FAnchors(0.0f, 0.0f), FVector2D::ZeroVector, FVector2D(6.0f, 6.0f), PanelSize);

	UCanvasPanel* Panel = WidgetTree->ConstructWidget<UCanvasPanel>(UCanvasPanel::StaticClass(), TEXT("StatusPanel"));
	AddCanvasChild(RootCanvas, Panel, StatusAnchor.Anchors, StatusAnchor.Alignment, StatusAnchor.Position, StatusAnchor.Size);
	RegisterHUDElement(EVibeMMOHUDElement::StatusPanel, Panel, StatusAnchor);

	UOverlay* Portrait = WidgetTree->ConstructWidget<UOverlay>(UOverlay::StaticClass(), TEXT("Portrait"));
	AddCanvasChild(Panel, Portrait, FAnchors(0.0f, 0.0f), FVector2D::ZeroVector, FVector2D(0.0f, 6.0f), FVector2D(68.0f, 68.0f));

	UBorder* PortraitBackdrop = WidgetTree->ConstructWidget<UBorder>(
		UBorder::StaticClass(), TEXT("PortraitBackdrop"));
	PortraitBackdrop->SetBrushColor(FLinearColor(0.012f, 0.055f, 0.09f, 1.0f));
	PortraitBackdrop->SetPadding(FMargin(2.0f));
	if (UOverlaySlot* BackdropSlot = Portrait->AddChildToOverlay(PortraitBackdrop))
	{
		BackdropSlot->SetHorizontalAlignment(HAlign_Fill);
		BackdropSlot->SetVerticalAlignment(VAlign_Fill);
	}

	PortraitImage = WidgetTree->ConstructWidget<UImage>(UImage::StaticClass(), TEXT("PortraitImage"));
	PortraitImage->SetVisibility(ESlateVisibility::Collapsed);
	if (UOverlaySlot* PortraitImageSlot = Portrait->AddChildToOverlay(PortraitImage))
	{
		PortraitImageSlot->SetHorizontalAlignment(HAlign_Fill);
		PortraitImageSlot->SetVerticalAlignment(VAlign_Fill);
	}

	PortraitFallbackText = MakeTextBlock(TEXT("PortraitFallbackText"), FText::FromString(TEXT("AV")), EVibeMMOUIFontRole::ImportantLabel);
	if (UOverlaySlot* PortraitFallbackSlot = Portrait->AddChildToOverlay(PortraitFallbackText))
	{
		PortraitFallbackSlot->SetHorizontalAlignment(HAlign_Center);
		PortraitFallbackSlot->SetVerticalAlignment(VAlign_Center);
	}

	const UVibeMMOHUDLayoutDataAsset* LayoutData = GetResolvedHUDLayoutDataAsset();
	if (LayoutData && !LayoutData->DefaultPortraitTexture.IsNull())
	{
		SetPortraitResource(LayoutData->DefaultPortraitTexture.LoadSynchronous());
	}

	const UVibeMMOUIStyleDataAsset* Style = GetResolvedStyleDataAsset();
	const FLinearColor ShieldColor = Style ? Style->ShieldColor : FLinearColor(0.05f, 0.25f, 1.0f, 1.0f);
	const FLinearColor HealthColor = Style ? Style->HealthColor : FLinearColor(0.23f, 0.86f, 0.13f, 1.0f);
	const FLinearColor FuelColor = FLinearColor(1.0f, 0.82f, 0.08f, 1.0f);
	const float StatusBarWidth = 252.0f;
	const float StatusBarHeight = 18.0f;
	const float BarX = 78.0f;

	// Shield: 10 visual segments (blue).
	{
		const float SegY = 6.0f;
		const float SegGap = 2.0f;
		const float SegW = (StatusBarWidth - SegGap * 9.0f) / 10.0f;
		ShieldSegmentBlocks.Reset();
		for (int32 i = 0; i < 10; ++i)
		{
			UBorder* Seg = MakeColorBlock(
				*FString::Printf(TEXT("ShieldSeg_%d"), i),
				ShieldColor,
				FVector2D(SegW, StatusBarHeight),
				2.0f);
			AddCanvasChild(Panel, Seg, FAnchors(0.0f, 0.0f), FVector2D::ZeroVector,
				FVector2D(BarX + i * (SegW + SegGap), SegY), FVector2D(SegW, StatusBarHeight));
			ShieldSegmentBlocks.Add(Seg);
		}
		ShieldBarBlock = nullptr;
		ShieldValueText = nullptr;
	}

	// Health bar (green) — no number overlay.
	{
		const float HealthY = 30.0f;
		UBorder* Back = MakeColorBlock(TEXT("HealthBarBlock_Back"), FLinearColor(0.01f, 0.02f, 0.03f, 0.22f), FVector2D(StatusBarWidth, StatusBarHeight));
		AddCanvasChild(Panel, Back, FAnchors(0.0f, 0.0f), FVector2D::ZeroVector, FVector2D(BarX, HealthY), FVector2D(StatusBarWidth, StatusBarHeight));

		HealthBarBlock = MakeColorBlock(TEXT("HealthBarBlock"), HealthColor, FVector2D(StatusBarWidth, StatusBarHeight));
		AddCanvasChild(Panel, HealthBarBlock, FAnchors(0.0f, 0.0f), FVector2D::ZeroVector, FVector2D(BarX, HealthY), FVector2D(StatusBarWidth, StatusBarHeight));
		HealthValueText = nullptr;
	}

	// Fuel / sprint stamina (yellow).
	{
		const float FuelY = 54.0f;
		UBorder* Back = MakeColorBlock(TEXT("FuelBarBlock_Back"), FLinearColor(0.01f, 0.02f, 0.03f, 0.22f), FVector2D(StatusBarWidth, StatusBarHeight));
		AddCanvasChild(Panel, Back, FAnchors(0.0f, 0.0f), FVector2D::ZeroVector, FVector2D(BarX, FuelY), FVector2D(StatusBarWidth, StatusBarHeight));

		FuelBarBlock = MakeColorBlock(TEXT("FuelBarBlock"), FuelColor, FVector2D(StatusBarWidth, StatusBarHeight));
		AddCanvasChild(Panel, FuelBarBlock, FAnchors(0.0f, 0.0f), FVector2D::ZeroVector, FVector2D(BarX, FuelY), FVector2D(StatusBarWidth, StatusBarHeight));
	}
}

void UVibeMMOHUDWidget::AddCompass(UCanvasPanel* RootCanvas)
{
	const UVibeMMOHUDLayoutDataAsset* LayoutData = GetResolvedHUDLayoutDataAsset();
	// Smaller Fortnite-style strip: letters on 45° + degree ticks every 15°.
	const FVibeMMOHUDAnchorSlot CompassAnchor = LayoutData ? LayoutData->CompassSlot : FVibeMMOHUDAnchorSlot(FAnchors(0.5f, 0.0f), FVector2D(0.5f, 0.0f), FVector2D(0.0f, 2.0f), FVector2D(360.0f, 28.0f));
	FVibeMMOHUDAnchorSlot Resolved = CompassAnchor;
	Resolved.Position.Y = 2.0f;
	Resolved.Size = FVector2D(360.0f, 28.0f);

	UHorizontalBox* CompassRow = WidgetTree->ConstructWidget<UHorizontalBox>(UHorizontalBox::StaticClass(), TEXT("CompassRow"));
	AddCanvasChild(RootCanvas, CompassRow, Resolved.Anchors, Resolved.Alignment, Resolved.Position, Resolved.Size);
	RegisterHUDElement(EVibeMMOHUDElement::Compass, CompassRow, Resolved);

	CompassLabelTexts.Reset();

	constexpr int32 LabelCount = 11;
	for (int32 Index = 0; Index < LabelCount; ++Index)
	{
		UTextBlock* Label = MakeTextBlock(*FString::Printf(TEXT("CompassLabel_%d"), Index), VibeMMOHUD::CompassTickText(0.0f), EVibeMMOUIFontRole::Heading);
		VibeMMOHUD::ApplyCompassLabelStyle(Label, Index == LabelCount / 2);
		CompassLabelTexts.Add(Label);
		if (Index == LabelCount / 2)
		{
			CompassHeadingText = Label;
		}

		if (UHorizontalBoxSlot* CompassBoxSlot = CompassRow->AddChildToHorizontalBox(Label))
		{
			CompassBoxSlot->SetPadding(FMargin(4.0f, 0.0f));
			CompassBoxSlot->SetHorizontalAlignment(HAlign_Center);
			CompassBoxSlot->SetVerticalAlignment(VAlign_Center);
		}
	}

	SetCompassHeadingDegrees(0.0f);
}

void UVibeMMOHUDWidget::AddMinimap(UCanvasPanel* RootCanvas)
{
	const UVibeMMOHUDLayoutDataAsset* LayoutData = GetResolvedHUDLayoutDataAsset();
	const FVibeMMOHUDAnchorSlot MinimapAnchor = LayoutData ? LayoutData->MinimapSlot : FVibeMMOHUDAnchorSlot(FAnchors(1.0f, 0.0f), FVector2D(1.0f, 0.0f), FVector2D(-20.0f, 20.0f), FVector2D(210.0f, 210.0f));
	FVibeMMOHUDAnchorSlot Resolved = MinimapAnchor;
	const FMargin ProjectSafePadding = LayoutData
		? LayoutData->SafeZonePadding : FMargin(20.0f);
	Resolved.Position = FVector2D(
		-FMath::Max(12.0f, ProjectSafePadding.Right),
		FMath::Max(12.0f, ProjectSafePadding.Top));
	Resolved.Size = FVector2D(210.0f, 210.0f);

	// Let UMG apply platform/letterbox safe margins before the explicit project
	// padding above. DPI scaling is then handled by Slate exactly once.
	USafeZone* HardwareSafeZone = WidgetTree->ConstructWidget<USafeZone>(
		USafeZone::StaticClass(), TEXT("MinimapHardwareSafeZone"));
	HardwareSafeZone->SetSidesToPad(true, true, true, true);
	AddCanvasChild(RootCanvas, HardwareSafeZone,
		FAnchors(0.0f, 0.0f, 1.0f, 1.0f), FVector2D::ZeroVector,
		FVector2D::ZeroVector, FVector2D::ZeroVector);
	UCanvasPanel* SafeCanvas = WidgetTree->ConstructWidget<UCanvasPanel>(
		UCanvasPanel::StaticClass(), TEXT("MinimapSafeCanvas"));
	HardwareSafeZone->SetContent(SafeCanvas);

	UCanvasPanel* Panel = WidgetTree->ConstructWidget<UCanvasPanel>(UCanvasPanel::StaticClass(), TEXT("MinimapPanel"));
	AddCanvasChild(SafeCanvas, Panel, Resolved.Anchors, Resolved.Alignment, Resolved.Position, Resolved.Size);
	RegisterHUDElement(EVibeMMOHUDElement::Minimap, Panel, Resolved);

	UOverlay* MapFrame = MakeFramedSlot(TEXT("MinimapFrame"), FLinearColor(0.03f, 0.13f, 0.12f, 0.74f), VibeMMOHUD::PanelStroke, FVector2D(210.0f, 210.0f));
	AddCanvasChild(Panel, MapFrame, FAnchors(0.0f, 0.0f), FVector2D::ZeroVector, FVector2D(0.0f, 0.0f), FVector2D(210.0f, 210.0f));

	MinimapBaseImage = WidgetTree->ConstructWidget<UImage>(UImage::StaticClass(), TEXT("MinimapBaseImage"));
	MinimapBaseImage->SetVisibility(ESlateVisibility::Visible);
	if (UOverlaySlot* MinimapBaseImageSlot = MapFrame->AddChildToOverlay(MinimapBaseImage))
	{
		MinimapBaseImageSlot->SetPadding(FMargin(4.0f));
		MinimapBaseImageSlot->SetHorizontalAlignment(HAlign_Fill);
		MinimapBaseImageSlot->SetVerticalAlignment(VAlign_Fill);
	}
	TryApplyGeneratedMinimap();

	// Settable minimap background (a UTextureRenderTarget2D from a top-down SceneCapture
	// will be assigned by the game via SetMinimapResource) over the readable map art.
	MinimapImage = WidgetTree->ConstructWidget<UImage>(UImage::StaticClass(), TEXT("MinimapImage"));
	MinimapImage->SetVisibility(ESlateVisibility::Collapsed);
	MinimapImage->SetColorAndOpacity(FLinearColor(1.0f, 1.0f, 1.0f, 0.0f));
	if (UOverlaySlot* MinimapImageSlot = MapFrame->AddChildToOverlay(MinimapImage))
	{
		MinimapImageSlot->SetPadding(FMargin(4.0f));
		MinimapImageSlot->SetHorizontalAlignment(HAlign_Fill);
		MinimapImageSlot->SetVerticalAlignment(VAlign_Fill);
	}

	MinimapSurfaceLayer = WidgetTree->ConstructWidget<UCanvasPanel>(UCanvasPanel::StaticClass(), TEXT("MinimapSurfaceLayer"));
	AddCanvasChild(Panel, MinimapSurfaceLayer, FAnchors(0.0f, 0.0f), FVector2D::ZeroVector, FVector2D::ZeroVector, FVector2D(210.0f, 210.0f));

	// Hostile blips (pool, hidden until SetMinimapBlips positions them). Added BEFORE the player
	// chevron so the chevron always draws on top of overlapping blips.
	MinimapBlipPool.Reset();
	for (int32 BlipIndex = 0; BlipIndex < 8; ++BlipIndex)
	{
		UBorder* Blip = MakeColorBlock(FName(*FString::Printf(TEXT("MinimapEnemyBlip%d"), BlipIndex)), FLinearColor(1.0f, 0.13f, 0.10f, 0.95f), FVector2D(9.0f, 9.0f), 4.0f);
		Blip->SetVisibility(ESlateVisibility::Collapsed);
		AddCanvasChild(MinimapSurfaceLayer, Blip, FAnchors(0.0f, 0.0f), FVector2D::ZeroVector, FVector2D(100.5f, 100.5f), FVector2D(7.0f, 7.0f));
		MinimapBlipPool.Add(Blip);
	}

	// Small player chevron, centered on the minimap (the map follows the player). GREEN = you;
	// red is reserved for hostiles (the blips above).
	UTextBlock* PlayerArrow = MakeTextBlock(TEXT("MinimapPlayerArrow"), FText::FromString(TEXT("^")), EVibeMMOUIFontRole::SettingsBody);
	PlayerArrow->SetColorAndOpacity(FSlateColor(FLinearColor(0.20f, 1.0f, 0.35f, 1.0f)));
	AddCanvasChild(MinimapSurfaceLayer, PlayerArrow, FAnchors(0.0f, 0.0f), FVector2D::ZeroVector, FVector2D(98.0f, 98.0f), FVector2D(14.0f, 14.0f));

	// Demo POI markers (Q/B/R/M/S/!) removed — placeholder clutter sitting over the live minimap.
	// The player arrow above stays; hostile blips are driven from game data via SetMinimapBlips.

	MinimapSpaceLayer = WidgetTree->ConstructWidget<UCanvasPanel>(UCanvasPanel::StaticClass(), TEXT("MinimapSpaceLayer"));
	AddCanvasChild(Panel, MinimapSpaceLayer, FAnchors(0.0f, 0.0f), FVector2D::ZeroVector, FVector2D::ZeroVector, FVector2D(210.0f, 210.0f));

	UBorder* SpaceBackground = MakeColorBlock(TEXT("MinimapSpaceBackground"),
		FLinearColor(0.004f, 0.010f, 0.030f, 0.94f), FVector2D(202.0f, 202.0f), 4.0f);
	AddCanvasChild(MinimapSpaceLayer, SpaceBackground, FAnchors(0.0f, 0.0f),
		FVector2D::ZeroVector, FVector2D(4.0f, 4.0f), FVector2D(202.0f, 202.0f));
	AddCanvasChild(MinimapSpaceLayer,
		MakeColorBlock(TEXT("MinimapOrbitHorizontal"),
			FLinearColor(0.12f, 0.82f, 1.0f, 0.20f), FVector2D(164.0f, 1.0f), 1.0f),
		FAnchors(0.0f, 0.0f), FVector2D::ZeroVector,
		FVector2D(23.0f, 104.5f), FVector2D(164.0f, 1.0f));
	AddCanvasChild(MinimapSpaceLayer,
		MakeColorBlock(TEXT("MinimapOrbitVertical"),
			FLinearColor(0.12f, 0.82f, 1.0f, 0.20f), FVector2D(1.0f, 164.0f), 1.0f),
		FAnchors(0.0f, 0.0f), FVector2D::ZeroVector,
		FVector2D(104.5f, 23.0f), FVector2D(1.0f, 164.0f));

	UTextBlock* RadarTitle = MakeTextBlock(TEXT("MinimapSpaceRadarTitle"),
		FText::FromString(TEXT("SPACE RADAR")), EVibeMMOUIFontRole::SettingsBody);
	VibeMMOHUD::ApplyMinimapMarkerStyle(RadarTitle);
	RadarTitle->SetColorAndOpacity(FSlateColor(FLinearColor(0.60f, 0.94f, 1.0f, 0.82f)));
	AddCanvasChild(MinimapSpaceLayer, RadarTitle, FAnchors(0.0f, 0.0f),
		FVector2D::ZeroVector, FVector2D(8.0f, 8.0f), FVector2D(92.0f, 20.0f));

	SpaceMinimapHeadingText = MakeTextBlock(TEXT("MinimapSpaceHeading"),
		FText::FromString(TEXT("N  000")), EVibeMMOUIFontRole::SettingsBody);
	VibeMMOHUD::ApplyMinimapMarkerStyle(SpaceMinimapHeadingText);
	SpaceMinimapHeadingText->SetColorAndOpacity(
		FSlateColor(FLinearColor(0.94f, 0.98f, 1.0f, 0.95f)));
	AddCanvasChild(MinimapSpaceLayer, SpaceMinimapHeadingText, FAnchors(0.0f, 0.0f),
		FVector2D::ZeroVector, FVector2D(112.0f, 8.0f), FVector2D(88.0f, 20.0f));

	UTextBlock* ForwardLabel = MakeTextBlock(TEXT("MinimapSpaceForward"),
		FText::FromString(TEXT("FWD")), EVibeMMOUIFontRole::SettingsBody);
	VibeMMOHUD::ApplyMinimapMarkerStyle(ForwardLabel);
	ForwardLabel->SetColorAndOpacity(FSlateColor(FLinearColor(0.30f, 0.94f, 1.0f, 0.78f)));
	AddCanvasChild(MinimapSpaceLayer, ForwardLabel, FAnchors(0.0f, 0.0f),
		FVector2D::ZeroVector, FVector2D(87.0f, 27.0f), FVector2D(36.0f, 18.0f));

	SpaceMinimapMarkerPool.Reset();
	for (int32 MarkerIndex = 0; MarkerIndex < 18; ++MarkerIndex)
	{
		UBorder* Marker = MakeColorBlock(
			FName(*FString::Printf(TEXT("SpaceRadarContact_%02d"), MarkerIndex)),
			FLinearColor(1.0f, 0.76f, 0.18f, 0.96f), FVector2D(7.0f), 3.5f);
		Marker->SetVisibility(ESlateVisibility::Collapsed);
		AddCanvasChild(MinimapSpaceLayer, Marker, FAnchors(0.0f, 0.0f),
			FVector2D::ZeroVector, FVector2D(101.5f), FVector2D(7.0f));
		SpaceMinimapMarkerPool.Add(Marker);
	}

	UTextBlock* SpacePlayerArrow = MakeTextBlock(TEXT("MinimapSpacePlayer"),
		FText::FromString(TEXT("^")), EVibeMMOUIFontRole::ImportantLabel);
	VibeMMOHUD::ApplyMinimapMarkerStyle(SpacePlayerArrow);
	SpacePlayerArrow->SetColorAndOpacity(FSlateColor(FLinearColor(0.20f, 1.0f, 0.35f, 1.0f)));
	AddCanvasChild(MinimapSpaceLayer, SpacePlayerArrow, FAnchors(0.0f, 0.0f),
		FVector2D::ZeroVector, FVector2D(98.0f, 96.0f), FVector2D(14.0f, 18.0f));

	SpaceMinimapNearestText = MakeTextBlock(TEXT("MinimapSpaceNearest"),
		FText::FromString(TEXT("SCANNING")), EVibeMMOUIFontRole::SettingsBody);
	VibeMMOHUD::ApplyMinimapMarkerStyle(SpaceMinimapNearestText);
	SpaceMinimapNearestText->SetColorAndOpacity(
		FSlateColor(FLinearColor(1.0f, 0.82f, 0.30f, 0.92f)));
	AddCanvasChild(MinimapSpaceLayer, SpaceMinimapNearestText, FAnchors(0.0f, 0.0f),
		FVector2D::ZeroVector, FVector2D(18.0f, 181.0f), FVector2D(174.0f, 20.0f));

	RefreshMinimapModeVisuals();
}

void UVibeMMOHUDWidget::AddReticle(UCanvasPanel* RootCanvas)
{
	const UVibeMMOHUDLayoutDataAsset* LayoutData = GetResolvedHUDLayoutDataAsset();
	const FVector2D PackSightSize(78.0f, 78.0f);
	const FVibeMMOHUDAnchorSlot ReticleAnchor = LayoutData
		? FVibeMMOHUDAnchorSlot(LayoutData->ReticleSlot.Anchors, LayoutData->ReticleSlot.Alignment,
			LayoutData->ReticleSlot.Position, PackSightSize)
		: FVibeMMOHUDAnchorSlot(FAnchors(0.5f, 0.5f), FVector2D(0.5f, 0.5f),
			FVector2D::ZeroVector, PackSightSize);

	ReticleImage = WidgetTree->ConstructWidget<UImage>(UImage::StaticClass(), TEXT("UltimateStylizedArcSight"));
	ReticleImage->SetRenderTransformPivot(FVector2D(0.5f, 0.5f));
	// A newly constructed UImage has a white default brush.  Keep it collapsed
	// until the purchased crosshair material and its dynamic instance are both
	// valid so a missing/stale cook can never display a solid white square.
	ReticleImage->SetVisibility(ESlateVisibility::Collapsed);
	AddCanvasChild(RootCanvas, ReticleImage, ReticleAnchor.Anchors, ReticleAnchor.Alignment,
		ReticleAnchor.Position, ReticleAnchor.Size);
	RegisterHUDElement(EVibeMMOHUDElement::Reticle, ReticleImage, ReticleAnchor);

	// Design 38 is the open concentric-ring sight shown on the right side of the user's
	// reference crop. This project-local instance was duplicated and resaved through UE 5.8
	// from the purchased pack, then color-balanced to its red/green/blue showcase palette.
	static const TCHAR* ArcSightPath =
		TEXT("/Game/RedMMO/UI/Crosshair/MI_RedMMO_ArcSight.MI_RedMMO_ArcSight");
	if (UMaterialInterface* ArcSight = LoadObject<UMaterialInterface>(nullptr, ArcSightPath))
	{
		ApplyBrushResource(ReticleImage, ArcSight, PackSightSize);
		ReticleDynamicMaterial = ReticleImage->GetDynamicMaterial();
		if (ReticleDynamicMaterial)
		{
			ReticleImage->SetRenderOpacity(0.90f);
			ReticleImage->SetVisibility(ESlateVisibility::HitTestInvisible);
		}
	}
	else
	{
		// Never silently restore the rejected hand-drawn Canvas receptacle.
		ReticleImage->SetVisibility(ESlateVisibility::Collapsed);
	}
}

void UVibeMMOHUDWidget::AddTargetingLayer(UCanvasPanel* RootCanvas)
{
	TargetingCanvas = WidgetTree->ConstructWidget<UCanvasPanel>(UCanvasPanel::StaticClass(), TEXT("TargetingCanvas"));
	AddCanvasChild(RootCanvas, TargetingCanvas, FAnchors(0.0f, 0.0f, 1.0f, 1.0f), FVector2D::ZeroVector, FVector2D::ZeroVector, FVector2D::ZeroVector);
}

void UVibeMMOHUDWidget::AddAbilityBar(UCanvasPanel* RootCanvas)
{
	const UVibeMMOUIStyleDataAsset* Style = GetResolvedStyleDataAsset();
	const UVibeMMOHUDLayoutDataAsset* LayoutData = GetResolvedHUDLayoutDataAsset();
	// ~30% smaller slots; flush to bottom-center.
	const float SlotSize = LayoutData ? (LayoutData->AbilitySlotSize * 0.7f) : (Style ? Style->AbilitySlotSize * 0.7f : 52.0f);
	const int32 SlotsPerRow = FMath::Max(1, LayoutData ? LayoutData->AbilitySlotsPerRow : 5);
	FVibeMMOHUDAnchorSlot SlotLayout = LayoutData ? LayoutData->AbilityBarSlot : FVibeMMOHUDAnchorSlot(FAnchors(0.5f, 1.0f), FVector2D(0.5f, 1.0f), FVector2D(0.0f, -6.0f), FVector2D(400.0f, SlotSize + 10.0f));
	SlotLayout.Position.Y = -6.0f;
	SlotLayout.Size = FVector2D(400.0f, SlotSize + 10.0f);

	UVerticalBox* AbilityRows = WidgetTree->ConstructWidget<UVerticalBox>(UVerticalBox::StaticClass(), TEXT("AbilityRows"));
	AddCanvasChild(RootCanvas, AbilityRows, SlotLayout.Anchors, SlotLayout.Alignment, SlotLayout.Position, SlotLayout.Size);
	RegisterHUDElement(EVibeMMOHUDElement::AbilityBar, AbilityRows, SlotLayout);

	TArray<FText> Keys = LayoutData ? LayoutData->DefaultAbilityKeyLabels : TArray<FText>();
	if (Keys.IsEmpty())
	{
		Keys = {
			FText::FromString(TEXT("Q")),
			FText::FromString(TEXT("E")),
			FText::FromString(TEXT("R")),
			FText::FromString(TEXT("F")),
			FText::FromString(TEXT("X"))
		};
	}

	const TArray<FText> FallbackIconLabels = {
		FText::FromString(TEXT(">>")),
		FText::FromString(TEXT("[]")),
		FText::FromString(TEXT("O")),
		FText::FromString(TEXT("^")),
		FText::FromString(TEXT("*"))
	};

	const TArray<FLinearColor> SlotColors = {
		FLinearColor(0.0f, 0.46f, 0.88f, 0.92f),
		FLinearColor(0.0f, 0.28f, 0.78f, 0.92f),
		FLinearColor(0.42f, 0.1f, 0.95f, 0.92f),
		FLinearColor(1.0f, 0.42f, 0.0f, 0.92f),
		FLinearColor(0.5f, 0.08f, 0.92f, 0.92f)
	};

	AbilitySlotRoots.Reset();
	UHorizontalBox* CurrentRow = nullptr;
	for (int32 Index = 0; Index < Keys.Num(); ++Index)
	{
		if (Index % SlotsPerRow == 0)
		{
			CurrentRow = WidgetTree->ConstructWidget<UHorizontalBox>(UHorizontalBox::StaticClass(), *FString::Printf(TEXT("AbilityRow_%d"), Index / SlotsPerRow));
			if (UVerticalBoxSlot* RowStackSlot = AbilityRows->AddChildToVerticalBox(CurrentRow))
			{
				RowStackSlot->SetPadding(FMargin(0.0f, Index == 0 ? 0.0f : 8.0f, 0.0f, 0.0f));
				RowStackSlot->SetHorizontalAlignment(HAlign_Center);
			}
		}

		UVerticalBox* Stack = WidgetTree->ConstructWidget<UVerticalBox>(UVerticalBox::StaticClass(), *FString::Printf(TEXT("AbilityStack_%d"), Index));
		AbilitySlotRoots.Add(Stack);
		UOverlay* AbilitySlot = MakeFramedSlot(*FString::Printf(TEXT("AbilitySlot_%d"), Index), SlotColors[Index % SlotColors.Num()], VibeMMOHUD::PanelStroke, FVector2D(SlotSize, SlotSize));

		UImage* IconImage = WidgetTree->ConstructWidget<UImage>(UImage::StaticClass(), *FString::Printf(TEXT("AbilityIconImage_%d"), Index));
		IconImage->SetVisibility(ESlateVisibility::Collapsed);
		if (UOverlaySlot* IconImageSlot = AbilitySlot->AddChildToOverlay(IconImage))
		{
			IconImageSlot->SetPadding(FMargin(6.0f));
			IconImageSlot->SetHorizontalAlignment(HAlign_Fill);
			IconImageSlot->SetVerticalAlignment(VAlign_Fill);
		}
		AbilityIconImages.Add(IconImage);

		UTextBlock* IconText = MakeTextBlock(*FString::Printf(TEXT("AbilityIcon_%d"), Index), FallbackIconLabels[Index % FallbackIconLabels.Num()], EVibeMMOUIFontRole::ImportantLabel);
		if (UOverlaySlot* IconSlot = AbilitySlot->AddChildToOverlay(IconText))
		{
			IconSlot->SetHorizontalAlignment(HAlign_Center);
			IconSlot->SetVerticalAlignment(VAlign_Center);
		}
		AbilityIconFallbackTexts.Add(IconText);

		UTextBlock* AbilityName = MakeTextBlock(
			*FString::Printf(TEXT("AbilityName_%d"), Index), FText::GetEmpty(),
			EVibeMMOUIFontRole::SettingsBody);
		FSlateFontInfo AbilityNameFont = AbilityName->GetFont();
		AbilityNameFont.Size = 9;
		AbilityName->SetFont(AbilityNameFont);
		AbilityName->SetColorAndOpacity(FSlateColor(FLinearColor(0.88f, 0.96f, 1.0f, 0.96f)));
		AbilityName->SetShadowOffset(FVector2D(1.0f, 1.0f));
		AbilityName->SetShadowColorAndOpacity(FLinearColor(0.0f, 0.0f, 0.0f, 0.85f));
		AbilityName->SetVisibility(ESlateVisibility::Collapsed);
		AbilityNameTexts.Add(AbilityName);
		if (UOverlaySlot* AbilityNameSlot = AbilitySlot->AddChildToOverlay(AbilityName))
		{
			AbilityNameSlot->SetPadding(FMargin(3.0f, 2.0f, 3.0f, 0.0f));
			AbilityNameSlot->SetHorizontalAlignment(HAlign_Center);
			AbilityNameSlot->SetVerticalAlignment(VAlign_Top);
		}

		UProgressBar* CooldownBar = WidgetTree->ConstructWidget<UProgressBar>(
			UProgressBar::StaticClass(), *FString::Printf(TEXT("AbilityCooldownBar_%d"), Index));
		FProgressBarStyle CooldownStyle;
		CooldownStyle
			.SetBackgroundImage(FSlateRoundedBoxBrush(FLinearColor(0.005f, 0.008f, 0.018f, 0.82f), 2.5f))
			.SetFillImage(FSlateRoundedBoxBrush(FLinearColor::White, 2.5f))
			.SetMarqueeImage(FSlateRoundedBoxBrush(FLinearColor::Transparent, 2.5f));
		CooldownBar->SetWidgetStyle(CooldownStyle);
		CooldownBar->SetBarFillType(EProgressBarFillType::LeftToRight);
		CooldownBar->SetPercent(0.0f);
		CooldownBar->SetVisibility(ESlateVisibility::Collapsed);
		AbilityCooldownBars.Add(CooldownBar);

		USizeBox* CooldownBarBox = WidgetTree->ConstructWidget<USizeBox>(
			USizeBox::StaticClass(), *FString::Printf(TEXT("AbilityCooldownBarBox_%d"), Index));
		CooldownBarBox->SetHeightOverride(6.0f);
		CooldownBarBox->SetContent(CooldownBar);
		if (UOverlaySlot* CooldownBarSlot = AbilitySlot->AddChildToOverlay(CooldownBarBox))
		{
			CooldownBarSlot->SetPadding(FMargin(5.0f, 0.0f, 5.0f, 4.0f));
			CooldownBarSlot->SetHorizontalAlignment(HAlign_Fill);
			CooldownBarSlot->SetVerticalAlignment(VAlign_Bottom);
		}

		UTextBlock* CooldownText = MakeTextBlock(
			*FString::Printf(TEXT("AbilityCooldownText_%d"), Index), FText::GetEmpty(),
			EVibeMMOUIFontRole::ImportantLabel);
		CooldownText->SetColorAndOpacity(FSlateColor(FLinearColor::White));
		CooldownText->SetVisibility(ESlateVisibility::Collapsed);
		AbilityCooldownTexts.Add(CooldownText);
		if (UOverlaySlot* CooldownTextSlot = AbilitySlot->AddChildToOverlay(CooldownText))
		{
			CooldownTextSlot->SetHorizontalAlignment(HAlign_Center);
			CooldownTextSlot->SetVerticalAlignment(VAlign_Center);
		}

		if (LayoutData && LayoutData->DefaultAbilityIconTextures.IsValidIndex(Index) && !LayoutData->DefaultAbilityIconTextures[Index].IsNull())
		{
			SetAbilityIconResource(Index, LayoutData->DefaultAbilityIconTextures[Index].LoadSynchronous());
		}

		if (UVerticalBoxSlot* IconStackSlot = Stack->AddChildToVerticalBox(AbilitySlot))
		{
			IconStackSlot->SetHorizontalAlignment(HAlign_Center);
		}

		UTextBlock* KeyText = MakeTextBlock(*FString::Printf(TEXT("AbilityKeyText_%d"), Index), Keys[Index], EVibeMMOUIFontRole::AbilityKeybind);
		KeyText->SetColorAndOpacity(FSlateColor(FLinearColor(1.0f, 1.0f, 1.0f, 0.92f)));
		KeyText->SetVisibility(Index < 2
			? ESlateVisibility::HitTestInvisible : ESlateVisibility::Collapsed);

		if (Index == 0) { AbilityKeyQText = KeyText; }
		else if (Index == 1) { AbilityKeyEText = KeyText; }
		else if (Index == 2) { AbilityKeyRText = KeyText; }
		else if (Index == 3) { AbilityKeyFText = KeyText; }
		else if (Index == 4) { AbilityKeyXText = KeyText; }

		if (UVerticalBoxSlot* KeyStackSlot = Stack->AddChildToVerticalBox(KeyText))
		{
			KeyStackSlot->SetPadding(FMargin(0.0f, 4.0f, 0.0f, 0.0f));
			KeyStackSlot->SetHorizontalAlignment(HAlign_Center);
		}

		if (CurrentRow)
		{
			if (UHorizontalBoxSlot* RowSlot = CurrentRow->AddChildToHorizontalBox(Stack))
			{
				RowSlot->SetPadding(FMargin(7.0f, 0.0f));
				RowSlot->SetHorizontalAlignment(HAlign_Center);
				RowSlot->SetVerticalAlignment(VAlign_Bottom);
			}
		}
		if (Index >= 2)
		{
			Stack->SetVisibility(ESlateVisibility::Collapsed);
		}
	}
}

void UVibeMMOHUDWidget::AddAbilityLoadoutOverlay(UCanvasPanel* RootCanvas)
{
	AbilityLoadoutOverlay = WidgetTree->ConstructWidget<UOverlay>(
		UOverlay::StaticClass(), TEXT("AbilityLoadoutOverlay"));

	UBorder* ScreenDim = WidgetTree->ConstructWidget<UBorder>(
		UBorder::StaticClass(), TEXT("AbilityLoadoutScreenDim"));
	ScreenDim->SetBrushColor(FLinearColor(0.003f, 0.006f, 0.016f, 0.88f));
	if (UOverlaySlot* DimSlot = AbilityLoadoutOverlay->AddChildToOverlay(ScreenDim))
	{
		DimSlot->SetHorizontalAlignment(HAlign_Fill);
		DimSlot->SetVerticalAlignment(VAlign_Fill);
	}

	USizeBox* PanelBox = WidgetTree->ConstructWidget<USizeBox>(
		USizeBox::StaticClass(), TEXT("AbilityLoadoutPanelBox"));
	PanelBox->SetWidthOverride(620.0f);
	PanelBox->SetHeightOverride(430.0f);
	UBorder* Panel = WidgetTree->ConstructWidget<UBorder>(
		UBorder::StaticClass(), TEXT("AbilityLoadoutPanel"));
	Panel->SetBrush(FSlateRoundedBoxBrush(
		FLinearColor(0.018f, 0.032f, 0.070f, 0.98f), 18.0f,
		FLinearColor(0.08f, 0.78f, 1.0f, 0.95f), 3.0f));
	Panel->SetPadding(FMargin(42.0f, 32.0f));
	PanelBox->SetContent(Panel);
	if (UOverlaySlot* PanelSlot = AbilityLoadoutOverlay->AddChildToOverlay(PanelBox))
	{
		PanelSlot->SetHorizontalAlignment(HAlign_Center);
		PanelSlot->SetVerticalAlignment(VAlign_Center);
	}

	UVerticalBox* Content = WidgetTree->ConstructWidget<UVerticalBox>(
		UVerticalBox::StaticClass(), TEXT("AbilityLoadoutContent"));
	Panel->SetContent(Content);

	auto AddCenteredText = [this, Content](const FName Name, const FText& Text,
		const EVibeMMOUIFontRole Role, const FMargin& SlotPadding) -> UTextBlock*
	{
		UTextBlock* Label = MakeTextBlock(Name, Text, Role);
		if (UVerticalBoxSlot* Slot = Content->AddChildToVerticalBox(Label))
		{
			Slot->SetPadding(SlotPadding);
			Slot->SetHorizontalAlignment(HAlign_Center);
		}
		return Label;
	};

	AddCenteredText(TEXT("AbilityLoadoutTitle"), FText::FromString(TEXT("ABILITY LOADOUT")),
		EVibeMMOUIFontRole::ImportantLabel, FMargin(0.0f, 0.0f, 0.0f, 10.0f));
	AddCenteredText(TEXT("AbilityLoadoutSubtitle"),
		FText::FromString(TEXT("Assign the two combat abilities to Q and E")),
		EVibeMMOUIFontRole::SettingsBody, FMargin(0.0f, 0.0f, 0.0f, 26.0f));

	AbilityLoadoutQAssignmentText = AddCenteredText(TEXT("AbilityLoadoutQAssignment"),
		FText::FromString(TEXT("Q   GRAPPLE")), EVibeMMOUIFontRole::Heading,
		FMargin(0.0f, 0.0f, 0.0f, 14.0f));
	AbilityLoadoutEAssignmentText = AddCenteredText(TEXT("AbilityLoadoutEAssignment"),
		FText::FromString(TEXT("E   SLAM")), EVibeMMOUIFontRole::Heading,
		FMargin(0.0f, 0.0f, 0.0f, 30.0f));

	UButton* SwapButton = WidgetTree->ConstructWidget<UButton>(
		UButton::StaticClass(), TEXT("AbilityLoadoutSwapButton"));
	SwapButton->SetBackgroundColor(FLinearColor(0.02f, 0.62f, 0.95f, 1.0f));
	SwapButton->OnClicked.AddDynamic(this, &UVibeMMOHUDWidget::HandleAbilityLoadoutSwapClicked);
	UTextBlock* SwapText = MakeTextBlock(TEXT("AbilityLoadoutSwapText"),
		FText::FromString(TEXT("SWAP Q / E")), EVibeMMOUIFontRole::ImportantLabel);
	SwapText->SetColorAndOpacity(FSlateColor(FLinearColor::White));
	SwapButton->SetContent(SwapText);
	if (UVerticalBoxSlot* SwapSlot = Content->AddChildToVerticalBox(SwapButton))
	{
		SwapSlot->SetPadding(FMargin(120.0f, 0.0f, 120.0f, 22.0f));
		SwapSlot->SetHorizontalAlignment(HAlign_Fill);
	}

	AddCenteredText(TEXT("AbilityLoadoutCloseHint"),
		FText::FromString(TEXT("Press TAB to close")), EVibeMMOUIFontRole::SettingsBody,
		FMargin(0.0f));

	AddCanvasChild(RootCanvas, AbilityLoadoutOverlay,
		FAnchors(0.0f, 0.0f, 1.0f, 1.0f), FVector2D::ZeroVector,
		FVector2D::ZeroVector, FVector2D::ZeroVector);
	AbilityLoadoutOverlay->SetVisibility(ESlateVisibility::Collapsed);
}

void UVibeMMOHUDWidget::AddWeaponSlots(UCanvasPanel* RootCanvas)
{
	const UVibeMMOUIStyleDataAsset* Style = GetResolvedStyleDataAsset();
	const UVibeMMOHUDLayoutDataAsset* LayoutData = GetResolvedHUDLayoutDataAsset();
	const float SlotSize = LayoutData ? (LayoutData->WeaponSlotSize * 0.7f) : (Style ? Style->WeaponSlotSize * 0.7f : 64.0f);
	const float SlotWidth = SlotSize + 78.0f;
	// Pull up into frame so both weapon cards are fully visible (was clipped at -6).
	const FVibeMMOHUDAnchorSlot SlotLayout = FVibeMMOHUDAnchorSlot(
		FAnchors(1.0f, 1.0f), FVector2D(1.0f, 1.0f),
		FVector2D(-10.0f, -52.0f),
		FVector2D(SlotWidth, SlotSize * 2.0f + 28.0f));

	UVerticalBox* WeaponStack = WidgetTree->ConstructWidget<UVerticalBox>(UVerticalBox::StaticClass(), TEXT("WeaponStack"));
	AddCanvasChild(RootCanvas, WeaponStack, SlotLayout.Anchors, SlotLayout.Alignment, SlotLayout.Position, SlotLayout.Size);
	RegisterHUDElement(EVibeMMOHUDElement::WeaponStack, WeaponStack, SlotLayout);

	TArray<FText> SlotLabels = LayoutData ? LayoutData->DefaultWeaponSlotLabels : TArray<FText>();
	if (SlotLabels.IsEmpty())
	{
		SlotLabels = {
			FText::FromString(TEXT("1")),
			FText::FromString(TEXT("2"))
		};
	}

	for (int32 Index = 0; Index < SlotLabels.Num(); ++Index)
	{
		const EVibeMMOItemRarity DefaultRarity = Index == 0
			? EVibeMMOItemRarity::Epic
			: (Index == 1 ? EVibeMMOItemRarity::Legendary : EVibeMMOItemRarity::Common);
		WeaponSlotRarities.Add(DefaultRarity);
		const FLinearColor RarityColor = ResolveWeaponRarityColor(DefaultRarity);

		UBorder* RarityBorder = nullptr;
		UBorder* RarityBackground = nullptr;
		UOverlay* WeaponSlot = MakeFramedSlot(
			*FString::Printf(TEXT("WeaponSlot_%d"), Index), RarityColor, RarityColor,
			FVector2D(SlotWidth, SlotSize), &RarityBorder, &RarityBackground);
		WeaponSlotRoots.Add(WeaponSlot);
		WeaponRarityBorders.Add(RarityBorder);
		WeaponRarityBackgrounds.Add(RarityBackground);

		UImage* WeaponIconImage = WidgetTree->ConstructWidget<UImage>(UImage::StaticClass(), *FString::Printf(TEXT("WeaponIconImage_%d"), Index));
		WeaponIconImage->SetVisibility(ESlateVisibility::Collapsed);
		if (UOverlaySlot* WeaponIconSlot = WeaponSlot->AddChildToOverlay(WeaponIconImage))
		{
			// Leave the semantic rarity surface visible around the baked card art and reserve the
			// lower edge for the heat rail.
			WeaponIconSlot->SetPadding(FMargin(5.0f, 4.0f, 5.0f, 11.0f));
			WeaponIconSlot->SetHorizontalAlignment(HAlign_Fill);
			WeaponIconSlot->SetVerticalAlignment(VAlign_Fill);
		}
		WeaponIconImages.Add(WeaponIconImage);

		UTextBlock* SlotNumber = MakeTextBlock(*FString::Printf(TEXT("WeaponSlotNumber_%d"), Index), SlotLabels[Index], EVibeMMOUIFontRole::WeaponSlotNumber);
		VibeMMOHUD::ApplyCompactWeaponNumberStyle(SlotNumber);
		if (UOverlaySlot* NumberSlot = WeaponSlot->AddChildToOverlay(SlotNumber))
		{
			NumberSlot->SetPadding(FMargin(10.0f, 7.0f, 0.0f, 0.0f));
			NumberSlot->SetHorizontalAlignment(HAlign_Left);
			NumberSlot->SetVerticalAlignment(VAlign_Top);
		}

		UTextBlock* WeaponMark = MakeTextBlock(*FString::Printf(TEXT("WeaponMark_%d"), Index), Index == 0 ? FText::FromString(TEXT("ENERGY")) : FText::FromString(TEXT("RIFLE")), EVibeMMOUIFontRole::SettingsBody);
		if (UOverlaySlot* MarkSlot = WeaponSlot->AddChildToOverlay(WeaponMark))
		{
			MarkSlot->SetPadding(FMargin(44.0f, 8.0f, 10.0f, 0.0f));
			MarkSlot->SetHorizontalAlignment(HAlign_Left);
			MarkSlot->SetVerticalAlignment(VAlign_Top);
		}
		WeaponIconFallbackTexts.Add(WeaponMark);

		UBorder* StateFrame = WidgetTree->ConstructWidget<UBorder>(
			UBorder::StaticClass(), *FString::Printf(TEXT("WeaponStateFrame_%d"), Index));
		const FSlateRoundedBoxBrush StateFrameBrush(
			FLinearColor::Transparent, 8.0f, FLinearColor::White, 2.0f);
		StateFrame->SetBrush(StateFrameBrush);
		StateFrame->SetBrushColor(FLinearColor::Transparent);
		StateFrame->SetPadding(FMargin(0.0f));
		StateFrame->SetVisibility(ESlateVisibility::Collapsed);
		if (UOverlaySlot* StateFrameSlot = WeaponSlot->AddChildToOverlay(StateFrame))
		{
			StateFrameSlot->SetPadding(FMargin(1.0f));
			StateFrameSlot->SetHorizontalAlignment(HAlign_Fill);
			StateFrameSlot->SetVerticalAlignment(VAlign_Fill);
		}
		WeaponStateFrames.Add(StateFrame);

		UProgressBar* HeatBar = WidgetTree->ConstructWidget<UProgressBar>(
			UProgressBar::StaticClass(), *FString::Printf(TEXT("WeaponHeatBar_%d"), Index));
		FProgressBarStyle HeatBarStyle;
		HeatBarStyle
			.SetBackgroundImage(FSlateRoundedBoxBrush(FLinearColor(0.005f, 0.008f, 0.018f, 0.88f), 3.5f))
			.SetFillImage(FSlateRoundedBoxBrush(FLinearColor::White, 3.5f))
			.SetMarqueeImage(FSlateRoundedBoxBrush(FLinearColor::Transparent, 3.5f));
		HeatBar->SetWidgetStyle(HeatBarStyle);
		HeatBar->SetBarFillType(EProgressBarFillType::LeftToRight);
		HeatBar->SetPercent(0.0f);
		HeatBar->SetIsMarquee(false);
		HeatBar->SetVisibility(ESlateVisibility::Collapsed);
		WeaponHeatBars.Add(HeatBar);

		USizeBox* HeatBarBox = WidgetTree->ConstructWidget<USizeBox>(
			USizeBox::StaticClass(), *FString::Printf(TEXT("WeaponHeatBarBox_%d"), Index));
		HeatBarBox->SetHeightOverride(7.0f);
		HeatBarBox->SetContent(HeatBar);
		if (UOverlaySlot* HeatBarSlot = WeaponSlot->AddChildToOverlay(HeatBarBox))
		{
			HeatBarSlot->SetPadding(FMargin(10.0f, 0.0f, 10.0f, 6.0f));
			HeatBarSlot->SetHorizontalAlignment(HAlign_Fill);
			HeatBarSlot->SetVerticalAlignment(VAlign_Bottom);
		}

		if (LayoutData && LayoutData->DefaultWeaponIconTextures.IsValidIndex(Index) && !LayoutData->DefaultWeaponIconTextures[Index].IsNull())
		{
			SetWeaponIconResource(Index, LayoutData->DefaultWeaponIconTextures[Index].LoadSynchronous());
		}

		if (Index == 0)
		{
			WeaponSlot1Text = SlotNumber;
		}
		else
		{
			WeaponSlot2Text = SlotNumber;
		}

		if (UVerticalBoxSlot* StackSlot = WeaponStack->AddChildToVerticalBox(WeaponSlot))
		{
			StackSlot->SetPadding(FMargin(0.0f, Index == 0 ? 0.0f : 12.0f, 0.0f, 0.0f));
			StackSlot->SetHorizontalAlignment(HAlign_Right);
		}
	}

	RefreshWeaponSlotVisuals();
}

void UVibeMMOHUDWidget::AddCanvasChild(UCanvasPanel* RootCanvas, UWidget* Child, const FAnchors& Anchors, const FVector2D& Alignment, const FVector2D& Position, const FVector2D& Size) const
{
	if (!RootCanvas || !Child)
	{
		return;
	}

	if (UCanvasPanelSlot* CanvasSlot = RootCanvas->AddChildToCanvas(Child))
	{
		CanvasSlot->SetAnchors(Anchors);
		CanvasSlot->SetAlignment(Alignment);
		CanvasSlot->SetPosition(Position);
		CanvasSlot->SetSize(Size);
	}
}

UTextBlock* UVibeMMOHUDWidget::MakeTextBlock(const FName Name, const FText Text, const EVibeMMOUIFontRole Role)
{
	UTextBlock* TextBlock = WidgetTree->ConstructWidget<UTextBlock>(UTextBlock::StaticClass(), Name);
	TextBlock->SetText(Text);
	TextBlock->SetJustification(ETextJustify::Center);
	TextBlock->SetAutoWrapText(false);
	ApplyTextRole(TextBlock, Role);
	return TextBlock;
}

UBorder* UVibeMMOHUDWidget::MakeColorBlock(const FName Name, const FLinearColor Color, const FVector2D& MinSize, const float CornerRadius)
{
	(void)CornerRadius;

	UBorder* Border = WidgetTree->ConstructWidget<UBorder>(UBorder::StaticClass(), Name);
	Border->SetBrushColor(Color);
	Border->SetPadding(FMargin(0.0f));

	USizeBox* SizeBox = WidgetTree->ConstructWidget<USizeBox>(USizeBox::StaticClass(), *FString::Printf(TEXT("%s_Size"), *Name.ToString()));
	SizeBox->SetWidthOverride(MinSize.X);
	SizeBox->SetHeightOverride(MinSize.Y);
	Border->SetContent(SizeBox);

	StyledColorBlocks.Add(Border);
	return Border;
}

UOverlay* UVibeMMOHUDWidget::MakeFramedSlot(const FName Name, const FLinearColor FillColor, const FLinearColor BorderColor,
	const FVector2D& MinSize, UBorder** OutOuter, UBorder** OutInner)
{
	UOverlay* Overlay = WidgetTree->ConstructWidget<UOverlay>(UOverlay::StaticClass(), Name);
	const UVibeMMOUIStyleDataAsset* Style = GetResolvedStyleDataAsset();
	const FLinearColor GlassTint = Style ? Style->GlassPanelTint : FLinearColor(0.68f, 0.86f, 1.0f, 0.16f);
	const FLinearColor GlassBorder = Style ? Style->GlassPanelBorderColor : FLinearColor(0.86f, 0.95f, 1.0f, 0.36f);

	FLinearColor EffectiveBorder = BorderColor;
	EffectiveBorder.R = FMath::Lerp(EffectiveBorder.R, GlassBorder.R, 0.15f);
	EffectiveBorder.G = FMath::Lerp(EffectiveBorder.G, GlassBorder.G, 0.15f);
	EffectiveBorder.B = FMath::Lerp(EffectiveBorder.B, GlassBorder.B, 0.15f);
	EffectiveBorder.A = FMath::Clamp(EffectiveBorder.A, 0.42f, 0.92f);
	UBorder* Outer = MakeColorBlock(*FString::Printf(TEXT("%s_Outer"), *Name.ToString()), EffectiveBorder, MinSize);
	if (OutOuter)
	{
		*OutOuter = Outer;
	}
	if (UOverlaySlot* OuterSlot = Overlay->AddChildToOverlay(Outer))
	{
		OuterSlot->SetHorizontalAlignment(HAlign_Fill);
		OuterSlot->SetVerticalAlignment(VAlign_Fill);
	}

	const FVector2D InnerSize(FMath::Max(1.0f, MinSize.X - 6.0f), FMath::Max(1.0f, MinSize.Y - 6.0f));
	FLinearColor EffectiveFill = FillColor;
	EffectiveFill.R = FMath::Lerp(EffectiveFill.R, GlassTint.R, 0.45f);
	EffectiveFill.G = FMath::Lerp(EffectiveFill.G, GlassTint.G, 0.45f);
	EffectiveFill.B = FMath::Lerp(EffectiveFill.B, GlassTint.B, 0.45f);
	EffectiveFill.A = FMath::Clamp(EffectiveFill.A, 0.72f, 0.96f);
	UBorder* Inner = MakeColorBlock(*FString::Printf(TEXT("%s_Inner"), *Name.ToString()), EffectiveFill, InnerSize);
	if (OutInner)
	{
		*OutInner = Inner;
	}
	if (UOverlaySlot* InnerSlot = Overlay->AddChildToOverlay(Inner))
	{
		InnerSlot->SetPadding(FMargin(3.0f));
		InnerSlot->SetHorizontalAlignment(HAlign_Fill);
		InnerSlot->SetVerticalAlignment(VAlign_Fill);
	}

	return Overlay;
}

UOverlay* UVibeMMOHUDWidget::MakeTargetingRectangle(const FName Name, const FVibeMMOTargetingRectangle& Rectangle)
{
	const FVector2D RectSize(FMath::Max(48.0f, Rectangle.Size.X), FMath::Max(36.0f, Rectangle.Size.Y));
	FLinearColor AccentColor = Rectangle.AccentColor;
	AccentColor.A = Rectangle.bLocked ? FMath::Max(AccentColor.A, 0.84f) : FMath::Max(AccentColor.A, 0.62f);

	UOverlay* Overlay = WidgetTree->ConstructWidget<UOverlay>(UOverlay::StaticClass(), Name);

	const float FillAlpha = Rectangle.bLocked ? 0.10f : 0.055f;
	UBorder* Fill = MakeColorBlock(*FString::Printf(TEXT("%s_Fill"), *Name.ToString()), FLinearColor(AccentColor.R, AccentColor.G, AccentColor.B, FillAlpha), RectSize);
	if (UOverlaySlot* FillSlot = Overlay->AddChildToOverlay(Fill))
	{
		FillSlot->SetHorizontalAlignment(HAlign_Fill);
		FillSlot->SetVerticalAlignment(VAlign_Fill);
	}

	const float EdgeLength = FMath::Clamp(FMath::Min(RectSize.X, RectSize.Y) * 0.24f, 16.0f, 42.0f);
	const float Thickness = Rectangle.bLocked ? 4.0f : 3.0f;
	const FLinearColor CornerColor(AccentColor.R, AccentColor.G, AccentColor.B, AccentColor.A);

	UCanvasPanel* CornerCanvas = WidgetTree->ConstructWidget<UCanvasPanel>(UCanvasPanel::StaticClass(), *FString::Printf(TEXT("%s_Corners"), *Name.ToString()));
	if (UOverlaySlot* CornerSlot = Overlay->AddChildToOverlay(CornerCanvas))
	{
		CornerSlot->SetHorizontalAlignment(HAlign_Fill);
		CornerSlot->SetVerticalAlignment(VAlign_Fill);
	}

	AddCanvasChild(CornerCanvas, MakeColorBlock(*FString::Printf(TEXT("%s_TopLeftH"), *Name.ToString()), CornerColor, FVector2D(EdgeLength, Thickness)), FAnchors(0.0f, 0.0f), FVector2D::ZeroVector, FVector2D::ZeroVector, FVector2D(EdgeLength, Thickness));
	AddCanvasChild(CornerCanvas, MakeColorBlock(*FString::Printf(TEXT("%s_TopLeftV"), *Name.ToString()), CornerColor, FVector2D(Thickness, EdgeLength)), FAnchors(0.0f, 0.0f), FVector2D::ZeroVector, FVector2D::ZeroVector, FVector2D(Thickness, EdgeLength));
	AddCanvasChild(CornerCanvas, MakeColorBlock(*FString::Printf(TEXT("%s_TopRightH"), *Name.ToString()), CornerColor, FVector2D(EdgeLength, Thickness)), FAnchors(1.0f, 0.0f), FVector2D(1.0f, 0.0f), FVector2D::ZeroVector, FVector2D(EdgeLength, Thickness));
	AddCanvasChild(CornerCanvas, MakeColorBlock(*FString::Printf(TEXT("%s_TopRightV"), *Name.ToString()), CornerColor, FVector2D(Thickness, EdgeLength)), FAnchors(1.0f, 0.0f), FVector2D(1.0f, 0.0f), FVector2D::ZeroVector, FVector2D(Thickness, EdgeLength));
	AddCanvasChild(CornerCanvas, MakeColorBlock(*FString::Printf(TEXT("%s_BottomLeftH"), *Name.ToString()), CornerColor, FVector2D(EdgeLength, Thickness)), FAnchors(0.0f, 1.0f), FVector2D(0.0f, 1.0f), FVector2D::ZeroVector, FVector2D(EdgeLength, Thickness));
	AddCanvasChild(CornerCanvas, MakeColorBlock(*FString::Printf(TEXT("%s_BottomLeftV"), *Name.ToString()), CornerColor, FVector2D(Thickness, EdgeLength)), FAnchors(0.0f, 1.0f), FVector2D(0.0f, 1.0f), FVector2D::ZeroVector, FVector2D(Thickness, EdgeLength));
	AddCanvasChild(CornerCanvas, MakeColorBlock(*FString::Printf(TEXT("%s_BottomRightH"), *Name.ToString()), CornerColor, FVector2D(EdgeLength, Thickness)), FAnchors(1.0f, 1.0f), FVector2D(1.0f, 1.0f), FVector2D::ZeroVector, FVector2D(EdgeLength, Thickness));
	AddCanvasChild(CornerCanvas, MakeColorBlock(*FString::Printf(TEXT("%s_BottomRightV"), *Name.ToString()), CornerColor, FVector2D(Thickness, EdgeLength)), FAnchors(1.0f, 1.0f), FVector2D(1.0f, 1.0f), FVector2D::ZeroVector, FVector2D(Thickness, EdgeLength));

	const FString LabelString = Rectangle.Label.ToString();
	const FString TargetDisplayLabel = LabelString.IsEmpty() ? FString(Rectangle.bLocked ? TEXT("LOCKED") : TEXT("TARGET")) : LabelString;
	const FText LabelText = FText::FromString(TargetDisplayLabel);
	UTextBlock* Label = MakeTextBlock(*FString::Printf(TEXT("%s_Label"), *Name.ToString()), LabelText, EVibeMMOUIFontRole::InventoryRarityLabel);
	Label->SetColorAndOpacity(FSlateColor(CornerColor));
	if (UOverlaySlot* LabelSlot = Overlay->AddChildToOverlay(Label))
	{
		LabelSlot->SetPadding(FMargin(8.0f, 4.0f, 8.0f, 0.0f));
		LabelSlot->SetHorizontalAlignment(HAlign_Center);
		LabelSlot->SetVerticalAlignment(VAlign_Top);
	}

	const FString DetailString = Rectangle.Detail.ToString();
	if (!DetailString.IsEmpty())
	{
		UTextBlock* Detail = MakeTextBlock(*FString::Printf(TEXT("%s_Detail"), *Name.ToString()), Rectangle.Detail, EVibeMMOUIFontRole::SettingsBody);
		Detail->SetColorAndOpacity(FSlateColor(FLinearColor(1.0f, 1.0f, 1.0f, 0.86f)));
		if (UOverlaySlot* DetailSlot = Overlay->AddChildToOverlay(Detail))
		{
			DetailSlot->SetPadding(FMargin(8.0f, 0.0f, 8.0f, 5.0f));
			DetailSlot->SetHorizontalAlignment(HAlign_Center);
			DetailSlot->SetVerticalAlignment(VAlign_Bottom);
		}
	}

	return Overlay;
}

void UVibeMMOHUDWidget::RebuildTargetingRectangles()
{
	if (!TargetingCanvas)
	{
		return;
	}

	for (UWidget* Widget : TargetingRectangleWidgets)
	{
		if (Widget)
		{
			Widget->RemoveFromParent();
		}
	}
	TargetingRectangleWidgets.Reset();

	for (int32 Index = 0; Index < ActiveTargetingRectangles.Num(); ++Index)
	{
		const FVibeMMOTargetingRectangle& Rectangle = ActiveTargetingRectangles[Index];
		if (!Rectangle.bVisible)
		{
			continue;
		}

		UOverlay* RectangleWidget = MakeTargetingRectangle(*FString::Printf(TEXT("TargetingRectangle_%d"), Index), Rectangle);
		AddCanvasChild(TargetingCanvas, RectangleWidget, FAnchors(0.0f, 0.0f), FVector2D(0.5f, 0.5f), Rectangle.CenterPosition, Rectangle.Size);
		TargetingRectangleWidgets.Add(RectangleWidget);
	}
}

void UVibeMMOHUDWidget::ApplyMockTargetingRectangles()
{
	ActiveTargetingRectangles.Reset();

	FVibeMMOTargetingRectangle ScannedTarget;
	ScannedTarget.CenterPosition = FVector2D(820.0f, 420.0f);
	ScannedTarget.Size = FVector2D(196.0f, 132.0f);
	ScannedTarget.Label = FText::FromString(TEXT("SCANNED"));
	ScannedTarget.Detail = FText::FromString(TEXT("38M"));
	ScannedTarget.AccentColor = FLinearColor(0.72f, 0.94f, 1.0f, 0.78f);
	ActiveTargetingRectangles.Add(ScannedTarget);

	FVibeMMOTargetingRectangle LockedTarget;
	LockedTarget.CenterPosition = FVector2D(1068.0f, 492.0f);
	LockedTarget.Size = FVector2D(150.0f, 98.0f);
	LockedTarget.Label = FText::FromString(TEXT("LOCK"));
	LockedTarget.Detail = FText::FromString(TEXT("ELITE"));
	LockedTarget.AccentColor = FLinearColor(1.0f, 0.34f, 0.24f, 0.88f);
	LockedTarget.bLocked = true;
	ActiveTargetingRectangles.Add(LockedTarget);

	RebuildTargetingRectangles();
}

void UVibeMMOHUDWidget::ApplyHUDTextRoles()
{
	if (ShieldValueText)
	{
		ShieldValueText->SetVisibility(ESlateVisibility::Collapsed);
	}
	if (HealthValueText)
	{
		HealthValueText->SetVisibility(ESlateVisibility::Collapsed);
	}
	ApplyTextRole(ResourceValueText, EVibeMMOUIFontRole::HUDNumber);
	ApplyTextRole(LevelBadgeText, EVibeMMOUIFontRole::LevelBadge);
	ApplyTextRole(CompassHeadingText, EVibeMMOUIFontRole::Heading);
	for (UTextBlock* Label : CompassLabelTexts)
	{
		if (Label)
		{
			VibeMMOHUD::ApplyCompassLabelStyle(Label, Label == CompassHeadingText);
		}
	}

	ApplyTextRole(AbilityKeyQText, EVibeMMOUIFontRole::AbilityKeybind);
	ApplyTextRole(AbilityKeyEText, EVibeMMOUIFontRole::AbilityKeybind);
	ApplyTextRole(AbilityKeyRText, EVibeMMOUIFontRole::AbilityKeybind);
	ApplyTextRole(AbilityKeyFText, EVibeMMOUIFontRole::AbilityKeybind);
	ApplyTextRole(AbilityKeyXText, EVibeMMOUIFontRole::AbilityKeybind);

	ApplyTextRole(WeaponSlot1Text, EVibeMMOUIFontRole::WeaponSlotNumber);
	ApplyTextRole(WeaponSlot2Text, EVibeMMOUIFontRole::WeaponSlotNumber);
	VibeMMOHUD::ApplyCompactWeaponNumberStyle(WeaponSlot1Text);
	VibeMMOHUD::ApplyCompactWeaponNumberStyle(WeaponSlot2Text);
}

void UVibeMMOHUDWidget::ApplyHUDColors()
{
	const UVibeMMOUIStyleDataAsset* Style = GetResolvedStyleDataAsset();
	if (!Style)
	{
		return;
	}

	if (ShieldBarBlock)
	{
		ShieldBarBlock->SetBrushColor(Style->ShieldColor);
	}

	if (HealthBarBlock)
	{
		HealthBarBlock->SetBrushColor(Style->HealthColor);
	}

	if (FuelBarBlock)
	{
		FuelBarBlock->SetBrushColor(FLinearColor(1.0f, 0.82f, 0.08f, 1.0f));
	}

	if (ResourceBarBlock)
	{
		ResourceBarBlock->SetBrushColor(Style->EnergyColor);
	}

	RefreshWeaponSlotVisuals();
}

void UVibeMMOHUDWidget::ApplyMockTextValues()
{
	SetStatusValues(MockShieldValue, MockHealthValue, MockResourceValue);
	SetAbilityKeyLabels(FText::FromString(TEXT("Q")), FText::FromString(TEXT("E")), FText::FromString(TEXT("R")), FText::FromString(TEXT("F")), FText::FromString(TEXT("X")));
	SetWeaponSlotLabels(FText::FromString(TEXT("1")), FText::FromString(TEXT("2")));

	if (LevelBadgeText)
	{
		LevelBadgeText->SetText(FText::AsNumber(MockLevelValue));
	}
}
