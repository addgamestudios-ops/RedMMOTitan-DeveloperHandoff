#include "RedHUDWidget.h"

#include "RedHUDLayout.h"

#include "Blueprint/WidgetTree.h"
#include "Components/Border.h"
#include "Components/CanvasPanel.h"
#include "Components/CanvasPanelSlot.h"
#include "Components/Image.h"
#include "Components/ScaleBox.h"
#include "Components/SizeBox.h"
#include "Components/TextBlock.h"
#include "Engine/Texture2D.h"
#include "Engine/Texture.h"
#include "Engine/LocalPlayer.h"
#include "Engine/World.h"
#include "Persistence/VibeMMOHUDLayoutSubsystem.h"
#include "Styling/SlateBrush.h"
#include "TimerManager.h"

namespace
{
    const FLinearColor LiveMaskColor(0.005f, 0.010f, 0.015f, 0.94f);
    const FLinearColor EnemyHealthColor(1.00f, 0.10f, 0.23f, 1.0f);
    const FLinearColor ObjectiveColor(0.10f, 0.95f, 0.84f, 1.0f);
    const FLinearColor OpaqueLiveMaskColor(0.005f, 0.010f, 0.015f, 1.0f);
    const FLinearColor MiningResultBackdropColor(0.018f, 0.008f, 0.055f, 1.0f);
    const FLinearColor MiningResultLabelColor(0.95f, 0.74f, 0.30f, 1.0f);
    const FLinearColor MinimapFrameColor(0.10f, 0.015f, 0.20f, 0.98f);
    const FLinearColor MinimapAccentColor(0.95f, 0.72f, 0.22f, 1.0f);
    const FLinearColor MinimapPlayerColor(0.10f, 0.95f, 0.84f, 1.0f);
    constexpr float MiningResultLifetimeSeconds = 3.25f;
    constexpr float MiningResultFadeSeconds = 0.70f;
    constexpr float MiningResultArtFadeSeconds = 0.12f;
    constexpr float MiningResultFadeTickSeconds = 1.0f / 30.0f;

    // One state-driven text widget is retained per logical ability. Gamepad art
    // and the supplied keyboard cluster occupy different authored rectangles,
    // so the widget is reflowed when the active input scheme changes.
    const FRedHUDRect GamepadAbilityStatusRects[4] =
    {
        FRedHUDRect(3315, 1035, 240, 80, 90),
        FRedHUDRect(3080, 1300, 240, 80, 90),
        FRedHUDRect(3530, 1300, 240, 80, 90),
        FRedHUDRect(3310, 1545, 240, 80, 90)
    };

    // Exact Q/E card bounds inside T_REDHUD_AbilityCluster_Keyboard. Indices
    // 0 (Ultimate) and 3 (Bottom/R) have no authoritative gameplay feed.
    const FRedHUDRect KeyboardAbilityStatusRects[2] =
    {
        FRedHUDRect(3418, 1643, 170, 147, 90),
        FRedHUDRect(3613, 1640, 185, 150, 90)
    };

    bool IsDormantLiveDataArtName(const FName Name)
    {
        return Name == FName(TEXT("Minimap"))
            || Name == FName(TEXT("PartyRow01"))
            || Name == FName(TEXT("PartyRow02"))
            || Name == FName(TEXT("PartyRow03"));
    }

    float SafePercent(const float Value, const float Maximum)
    {
        return Maximum > KINDA_SMALL_NUMBER
            ? FMath::Clamp(Value / Maximum, 0.0f, 1.0f)
            : 0.0f;
    }

}

void URedHUDWidget::NativeOnInitialized()
{
    Super::NativeOnInitialized();

    BuildWidgetTree();

    CachedWeaponStates.SetNum(2);
    CachedWeaponStates[0].bEquipped = true;
    CachedAbilityStates.SetNum(4);
    AbilityPresentationCache.SetNum(4);
    InvalidateAbilityPresentationCache();
    ApplyInputSchemeVisibility();
    SetLiveDataMode(true);
    BindHUDLayout();
}

void URedHUDWidget::NativeDestruct()
{
    if (UWorld* World = GetWorld())
    {
        World->GetTimerManager().ClearTimer(MiningResultFadeTimer);
    }
    if (HUDLayoutSubsystem)
    {
        HUDLayoutSubsystem->OnLayoutChanged.RemoveDynamic(this, &URedHUDWidget::HandleHUDLayoutChanged);
    }
    if (MinimapLiveImage)
    {
        MinimapLiveImage->SetBrushResourceObject(nullptr);
    }
    CachedMinimapSurfaceTexture = nullptr;
    CachedMinimapSourceOwner.Reset();
    CachedMinimapCelestialFrameId = NAME_None;
    CachedMinimapMode = ERedHUDMinimapMode::Absent;
    HUDLayoutSubsystem = nullptr;
    Super::NativeDestruct();
}

void URedHUDWidget::AdvanceMiningResultFade()
{
    if (MiningResultSecondsRemaining <= 0.0f)
    {
        return;
    }

    MiningResultSecondsRemaining = FMath::Max(
        0.0f,
        MiningResultSecondsRemaining - MiningResultFadeTickSeconds);

    float ArtOpacity = 1.0f;
    float LiveOpacity = 1.0f;
    if (MiningResultSecondsRemaining < MiningResultFadeSeconds)
    {
        // The authored row includes sample text below the opaque live mask.
        // Fade that source art out while the mask is still opaque, then fade
        // the live mask and authoritative text. Otherwise the baked sample
        // becomes visible through the mask during the receipt's final frames.
        const float FadeElapsed =
            MiningResultFadeSeconds - MiningResultSecondsRemaining;
        ArtOpacity = 1.0f - FMath::SmoothStep(
            0.0f,
            MiningResultArtFadeSeconds,
            FadeElapsed);
        LiveOpacity = FMath::SmoothStep(
            0.0f,
            MiningResultFadeSeconds - MiningResultArtFadeSeconds,
            MiningResultSecondsRemaining);
    }
    for (UWidget* Widget : MiningResultWidgets)
    {
        if (Widget)
        {
            Widget->SetRenderOpacity(
                Widget == MiningResultArt ? ArtOpacity : LiveOpacity);
        }
    }

    if (MiningResultSecondsRemaining <= 0.0f)
    {
        SetLiveGroupVisibility(MiningResultWidgets, false);
        if (UWorld* World = GetWorld())
        {
            World->GetTimerManager().ClearTimer(MiningResultFadeTimer);
        }
    }
}

void URedHUDWidget::BindHUDLayout()
{
    if (ULocalPlayer* LocalPlayer = GetOwningLocalPlayer())
    {
        HUDLayoutSubsystem = LocalPlayer->GetSubsystem<UVibeMMOHUDLayoutSubsystem>();
    }
    if (HUDLayoutSubsystem)
    {
        HUDLayoutSubsystem->OnLayoutChanged.AddUniqueDynamic(this, &URedHUDWidget::HandleHUDLayoutChanged);
    }
    ApplyHUDLayout();
}

void URedHUDWidget::HandleHUDLayoutChanged()
{
    ApplyHUDLayout();
}

FVibeMMOHUDElementLayout URedHUDWidget::GetHUDElementLayout(const EVibeMMOHUDElement Element) const
{
    return HUDLayoutSubsystem ? HUDLayoutSubsystem->GetElementLayout(Element) : FVibeMMOHUDElementLayout();
}

bool URedHUDWidget::CommitHUDElementLayout(
    const EVibeMMOHUDElement Element,
    const FVibeMMOHUDElementLayout& Layout)
{
    if (!HUDLayoutSubsystem || !VibeMMOHUDLayout::IsValidElement(Element))
    {
        return false;
    }

    FVibeMMOHUDElementLayout Sanitized = Layout;
    Sanitized.Sanitize();
    if (GetHUDElementLayout(Element).NearlyEquals(Sanitized))
    {
        return false;
    }
    return HUDLayoutSubsystem->SetElementLayout(Element, Sanitized);
}

bool URedHUDWidget::NudgeHUDElement(const EVibeMMOHUDElement Element, const FVector2D NormalizedDelta)
{
    FVibeMMOHUDElementLayout Layout = GetHUDElementLayout(Element);
    if (Layout.bLocked)
    {
        return false;
    }
    Layout.NormalizedOffset += NormalizedDelta;
    return CommitHUDElementLayout(Element, Layout);
}

bool URedHUDWidget::SetHUDElementScale(const EVibeMMOHUDElement Element, const float Scale)
{
    FVibeMMOHUDElementLayout Layout = GetHUDElementLayout(Element);
    if (Layout.bLocked)
    {
        return false;
    }
    Layout.Scale = Scale;
    return CommitHUDElementLayout(Element, Layout);
}

bool URedHUDWidget::SetHUDElementOpacity(const EVibeMMOHUDElement Element, const float Opacity)
{
    FVibeMMOHUDElementLayout Layout = GetHUDElementLayout(Element);
    Layout.Opacity = Opacity;
    return CommitHUDElementLayout(Element, Layout);
}

bool URedHUDWidget::SetHUDElementHidden(const EVibeMMOHUDElement Element, const bool bHidden)
{
    FVibeMMOHUDElementLayout Layout = GetHUDElementLayout(Element);
    Layout.bHidden = bHidden;
    return CommitHUDElementLayout(Element, Layout);
}

bool URedHUDWidget::SetHUDElementLocked(const EVibeMMOHUDElement Element, const bool bLocked)
{
    FVibeMMOHUDElementLayout Layout = GetHUDElementLayout(Element);
    Layout.bLocked = bLocked;
    return CommitHUDElementLayout(Element, Layout);
}

bool URedHUDWidget::ResetHUDElement(const EVibeMMOHUDElement Element)
{
    if (!HUDLayoutSubsystem || !VibeMMOHUDLayout::IsValidElement(Element)
        || GetHUDElementLayout(Element).IsDefault())
    {
        return false;
    }
    return HUDLayoutSubsystem->ResetElementLayout(Element);
}

bool URedHUDWidget::ResetAllHUDElements()
{
    if (!HUDLayoutSubsystem
        || HUDLayoutSubsystem->GetLayoutProfile().ElementOverrides.IsEmpty())
    {
        return false;
    }
    return HUDLayoutSubsystem->ResetLayout();
}

bool URedHUDWidget::SaveHUDLayout()
{
    return HUDLayoutSubsystem && HUDLayoutSubsystem->SaveLayoutNow();
}

TArray<UWidget*> URedHUDWidget::ResolveHUDElementWidgets(const EVibeMMOHUDElement Element) const
{
    TArray<UWidget*> Widgets;
    auto AddArt = [this, &Widgets](const FName Name)
    {
        if (const TObjectPtr<UImage>* Image = ArtImages.Find(Name))
        {
            Widgets.Add(Image->Get());
        }
    };
    auto AddGroup = [&Widgets](const TArray<TObjectPtr<UWidget>>& Group)
    {
        for (UWidget* Widget : Group)
        {
            Widgets.Add(Widget);
        }
    };

    switch (Element)
    {
    case EVibeMMOHUDElement::StatusPanel:
        AddArt(TEXT("PlayerStatus")); AddGroup(PlayerLiveWidgets); break;
    case EVibeMMOHUDElement::Compass:
        AddArt(TEXT("TopProgress")); AddGroup(CompassLiveWidgets); break;
    case EVibeMMOHUDElement::Minimap:
        AddArt(TEXT("Minimap")); AddGroup(MinimapLiveWidgets); break;
    case EVibeMMOHUDElement::AbilityBar:
        for (UImage* Image : GamepadAbilityArt) { Widgets.Add(Image); }
        Widgets.Add(KeyboardAbilityCluster);
        for (UTextBlock* Text : AbilityCooldownText) { Widgets.Add(Text); }
        break;
    case EVibeMMOHUDElement::WeaponStack:
        AddArt(TEXT("WeaponSlot01")); AddArt(TEXT("WeaponSlot02")); AddGroup(WeaponLiveWidgets); break;
    case EVibeMMOHUDElement::PartyPanel:
        AddArt(TEXT("PartyRow01")); AddArt(TEXT("PartyRow02")); AddArt(TEXT("PartyRow03")); break;
    case EVibeMMOHUDElement::EnemyPanel:
        AddArt(TEXT("EnemyNameplate")); AddGroup(EnemyLiveWidgets); break;
    case EVibeMMOHUDElement::UtilityBar:
        AddArt(TEXT("UtilityE")); AddArt(TEXT("UtilityF")); AddArt(TEXT("UtilityG")); AddArt(TEXT("UtilityM")); break;
    default:
        break;
    }
    Widgets.RemoveAll([](const UWidget* Widget) { return Widget == nullptr; });
    return Widgets;
}

void URedHUDWidget::ApplyHUDElementLayout(const EVibeMMOHUDElement Element)
{
    const FVibeMMOHUDElementLayout Layout = GetHUDElementLayout(Element);
    const FVector2D Translation = Layout.NormalizedOffset
        * FVector2D(RedHUDLayout::DesignWidth, RedHUDLayout::DesignHeight);
    const FVector2D MinimapOrigin =
        RedHUDLayout::Get(TEXT("Minimap")).Position();
    for (UWidget* Widget : ResolveHUDElementWidgets(Element))
    {
        FVector2D ElementTranslation = Translation;
        if (Element == EVibeMMOHUDElement::Minimap
            && MinimapLiveWidgets.Contains(Widget))
        {
            // The minimap is a composed frame/image/label/marker group. Scale
            // every child around the authored region's common top-left origin;
            // scaling each child around its own center makes the pieces drift.
            Widget->SetRenderTransformPivot(FVector2D::ZeroVector);
            if (const UCanvasPanelSlot* CanvasSlot =
                Cast<UCanvasPanelSlot>(Widget->Slot))
            {
                ElementTranslation +=
                    (CanvasSlot->GetPosition() - MinimapOrigin)
                    * (Layout.Scale - 1.0f);
            }
        }
        Widget->SetRenderTranslation(ElementTranslation);
        Widget->SetRenderScale(FVector2D(Layout.Scale));
        Widget->SetRenderOpacity(Layout.Opacity);
        if (Layout.bHidden)
        {
            Widget->SetVisibility(ESlateVisibility::Collapsed);
        }
    }
}

void URedHUDWidget::ApplyHUDLayout()
{
    SetLiveDataMode(bLiveDataMode);
    ApplyInputSchemeVisibility();
    for (const EVibeMMOHUDElement Element : VibeMMOHUDLayout::GetElements())
    {
        ApplyHUDElementLayout(Element);
    }
}

void URedHUDWidget::BuildWidgetTree()
{
    if (!WidgetTree || WidgetTree->RootWidget)
    {
        return;
    }

    UScaleBox* RootScale = WidgetTree->ConstructWidget<UScaleBox>(UScaleBox::StaticClass(), TEXT("REDHUD_RootScale"));
    RootScale->SetStretch(EStretch::ScaleToFit);
    RootScale->SetStretchDirection(EStretchDirection::Both);
    RootScale->SetVisibility(ESlateVisibility::SelfHitTestInvisible);
    WidgetTree->RootWidget = RootScale;

    USizeBox* DesignSize = WidgetTree->ConstructWidget<USizeBox>(USizeBox::StaticClass(), TEXT("REDHUD_DesignSize"));
    DesignSize->SetWidthOverride(RedHUDLayout::DesignWidth);
    DesignSize->SetHeightOverride(RedHUDLayout::DesignHeight);
    RootScale->AddChild(DesignSize);

    DesignCanvas = WidgetTree->ConstructWidget<UCanvasPanel>(UCanvasPanel::StaticClass(), TEXT("REDHUD_DesignCanvas"));
    DesignCanvas->SetVisibility(ESlateVisibility::SelfHitTestInvisible);
    DesignSize->AddChild(DesignCanvas);

    BuildArtwork();
    BuildLiveOverlay();
}

void URedHUDWidget::BuildArtwork()
{
    AddImage(TEXT("TopProgress"),
        TEXT("/Game/UI/RedHUD/Textures/HighResSprites/T_REDHUD_TopProgress.T_REDHUD_TopProgress"),
        RedHUDLayout::Get(TEXT("TopProgress")));

    AddImage(TEXT("Minimap"),
        TEXT("/Game/UI/RedHUD/Textures/HighResSprites/T_REDHUD_Minimap.T_REDHUD_Minimap"),
        RedHUDLayout::Get(TEXT("Minimap")));

    AddImage(TEXT("PartyRow01"),
        TEXT("/Game/UI/RedHUD/Textures/IndividualSprites/T_REDHUD_PartyRow_01.T_REDHUD_PartyRow_01"),
        RedHUDLayout::Get(TEXT("PartyRow01")));
    AddImage(TEXT("PartyRow02"),
        TEXT("/Game/UI/RedHUD/Textures/IndividualSprites/T_REDHUD_PartyRow_02.T_REDHUD_PartyRow_02"),
        RedHUDLayout::Get(TEXT("PartyRow02")));
    AddImage(TEXT("PartyRow03"),
        TEXT("/Game/UI/RedHUD/Textures/IndividualSprites/T_REDHUD_PartyRow_03.T_REDHUD_PartyRow_03"),
        RedHUDLayout::Get(TEXT("PartyRow03")));

    AddImage(TEXT("PlayerStatus"),
        TEXT("/Game/UI/RedHUD/Textures/HighResSprites/T_REDHUD_PlayerStatus.T_REDHUD_PlayerStatus"),
        RedHUDLayout::Get(TEXT("PlayerStatus")));

    AddImage(TEXT("EnemyNameplate"),
        TEXT("/Game/UI/RedHUD/Textures/HighResSprites/T_REDHUD_EnemyNameplate.T_REDHUD_EnemyNameplate"),
        RedHUDLayout::Get(TEXT("EnemyNameplate")));

    AddImage(TEXT("WeaponSlot01"),
        TEXT("/Game/UI/RedHUD/Textures/IndividualSprites/T_REDHUD_WeaponSlot_01.T_REDHUD_WeaponSlot_01"),
        RedHUDLayout::Get(TEXT("WeaponSlot01")));
    AddImage(TEXT("WeaponSlot02"),
        TEXT("/Game/UI/RedHUD/Textures/IndividualSprites/T_REDHUD_WeaponSlot_02.T_REDHUD_WeaponSlot_02"),
        RedHUDLayout::Get(TEXT("WeaponSlot02")));

    GamepadAbilityArt.SetNum(4);
    GamepadAbilityArt[0] = AddImage(TEXT("AbilityUltimate"),
        TEXT("/Game/UI/RedHUD/Textures/IndividualSprites/T_REDHUD_AbilityGP_Ultimate.T_REDHUD_AbilityGP_Ultimate"),
        RedHUDLayout::Get(TEXT("AbilityUltimate")));
    GamepadAbilityArt[1] = AddImage(TEXT("AbilityLeft"),
        TEXT("/Game/UI/RedHUD/Textures/IndividualSprites/T_REDHUD_AbilityGP_Left.T_REDHUD_AbilityGP_Left"),
        RedHUDLayout::Get(TEXT("AbilityLeft")));
    GamepadAbilityArt[2] = AddImage(TEXT("AbilityRight"),
        TEXT("/Game/UI/RedHUD/Textures/IndividualSprites/T_REDHUD_AbilityGP_Right.T_REDHUD_AbilityGP_Right"),
        RedHUDLayout::Get(TEXT("AbilityRight")));
    GamepadAbilityArt[3] = AddImage(TEXT("AbilityBottom"),
        TEXT("/Game/UI/RedHUD/Textures/IndividualSprites/T_REDHUD_AbilityGP_Bottom.T_REDHUD_AbilityGP_Bottom"),
        RedHUDLayout::Get(TEXT("AbilityBottom")));

    KeyboardAbilityCluster = AddImage(TEXT("AbilityKeyboard"),
        TEXT("/Game/UI/RedHUD/Textures/HighResSprites/T_REDHUD_AbilityCluster_Keyboard.T_REDHUD_AbilityCluster_Keyboard"),
        RedHUDLayout::Get(TEXT("AbilityKeyboard")),
        false);

    AddImage(TEXT("UtilityE"),
        TEXT("/Game/UI/RedHUD/Textures/IndividualSprites/T_REDHUD_Utility_E.T_REDHUD_Utility_E"),
        RedHUDLayout::Get(TEXT("UtilityE")));
    AddImage(TEXT("UtilityF"),
        TEXT("/Game/UI/RedHUD/Textures/IndividualSprites/T_REDHUD_Utility_F.T_REDHUD_Utility_F"),
        RedHUDLayout::Get(TEXT("UtilityF")));
    AddImage(TEXT("UtilityG"),
        TEXT("/Game/UI/RedHUD/Textures/IndividualSprites/T_REDHUD_Utility_G.T_REDHUD_Utility_G"),
        RedHUDLayout::Get(TEXT("UtilityG")));
    AddImage(TEXT("UtilityM"),
        TEXT("/Game/UI/RedHUD/Textures/IndividualSprites/T_REDHUD_Utility_M.T_REDHUD_Utility_M"),
        RedHUDLayout::Get(TEXT("UtilityM")));

    // The full-screen sample composite is approval reference art, not a live HUD.
    // Runtime uses only the supplied per-element sprites so removed elements stay
    // removed and live state can replace every baked sample number.
    ReferenceOverlay = nullptr;
}

void URedHUDWidget::BuildLiveOverlay()
{
    // Keep the authored gold, teal and purple bar pixels visible. Each right-
    // anchored mask covers only the depleted tail, instead of replacing the
    // painted bar with a hard-coded flat-color rectangle.
    PlayerShieldDepletionMask = AddDepletionMask(
        TEXT("PlayerShieldDepletionMask"),
        FRedHUDRect(190, 2013, 390, 12, 80),
        LiveMaskColor,
        &PlayerLiveWidgets);
    PlayerHealthDepletionMask = AddDepletionMask(
        TEXT("PlayerHealthDepletionMask"),
        FRedHUDRect(190, 2032, 465, 18, 80),
        LiveMaskColor,
        &PlayerLiveWidgets);
    PlayerEnergyDepletionMask = AddDepletionMask(
        TEXT("PlayerEnergyDepletionMask"),
        FRedHUDRect(190, 2059, 310, 14, 80),
        LiveMaskColor,
        &PlayerLiveWidgets);
    AddSolidRect(TEXT("PlayerHealthTextMask"), FRedHUDRect(535, 2074, 165, 34, 82), LiveMaskColor, &PlayerLiveWidgets);
    PlayerHealthText = AddText(TEXT("PlayerHealthText"), FRedHUDRect(535, 2075, 158, 30, 83), 20, ETextJustify::Right, FLinearColor::White, &PlayerLiveWidgets);

    // Resource totals belong to inventory, not the always-on combat HUD. A
    // compact purple-and-gold receipt appears only when authoritative mining
    // credit is granted, then fades without leaving an inventory tally behind.
    MiningResultArt = WidgetTree->ConstructWidget<UImage>(
        UImage::StaticClass(),
        TEXT("MiningResultArt"));
    if (UTexture2D* Texture = LoadTexture(
        TEXT("/Game/UI/RedHUD/Textures/IndividualSprites/T_REDHUD_BuffRow_01.T_REDHUD_BuffRow_01")))
    {
        MiningResultArt->SetBrushFromTexture(Texture, true);
    }
    MiningResultArt->SetVisibility(ESlateVisibility::Collapsed);
    UCanvasPanelSlot* MiningArtSlot =
        DesignCanvas->AddChildToCanvas(MiningResultArt);
    MiningArtSlot->SetAnchors(FAnchors(0.0f, 0.0f));
    MiningArtSlot->SetAlignment(FVector2D::ZeroVector);
    MiningArtSlot->SetPosition(FVector2D(78.0f, 1736.0f));
    MiningArtSlot->SetSize(FVector2D(700.0f, 127.0f));
    MiningArtSlot->SetZOrder(88);
    AllLiveWidgets.Add(MiningResultArt);
    MiningResultWidgets.Add(MiningResultArt);

    // The supplied row contains sample label/time text. Preserve its purple and
    // gold frame/icon, mask only the baked text band, and paint the live yield.
    MiningResultTextMask = AddSolidRect(
        TEXT("MiningResultTextMask"),
        FRedHUDRect(215, 1753, 552, 96, 89),
        MiningResultBackdropColor,
        &MiningResultWidgets);
    MiningResultAccent = AddSolidRect(
        TEXT("MiningResultAccent"),
        FRedHUDRect(216, 1758, 6, 82, 90),
        MiningResultLabelColor,
        &MiningResultWidgets);
    MiningResultLabelText = AddText(
        TEXT("MiningResultLabel"),
        FRedHUDRect(238, 1758, 500, 30, 91),
        17,
        ETextJustify::Left,
        MiningResultLabelColor,
        &MiningResultWidgets);
    MiningResultValueText = AddText(
        TEXT("MiningResultValue"),
        FRedHUDRect(238, 1794, 500, 47, 92),
        30,
        ETextJustify::Left,
        FLinearColor::White,
        &MiningResultWidgets);
    if (MiningResultLabelText)
    {
        MiningResultLabelText->SetText(FText::FromString(TEXT("MINING YIELD")));
    }
    SetLiveGroupVisibility(MiningResultWidgets, false);

	CompassText = AddText(TEXT("CompassHeading"), FRedHUDRect(1640, 70, 560, 42, 84), 26, ETextJustify::Center, FLinearColor::White, &CompassLiveWidgets);

    // The supplied minimap sprite is a monolithic sample with baked player,
    // objective and hostile markers. Keep it collapsed and place the real local
    // surface capture in the same authored/customizable region. No contact is
    // invented here; the centered cross only identifies the capture owner.
    AddSolidRect(
        TEXT("MinimapLiveFrame"),
        FRedHUDRect(3252, 32, 553, 548, 78),
        MinimapFrameColor,
        &MinimapLiveWidgets);
    AddSolidRect(
        TEXT("MinimapLiveAccent"),
        FRedHUDRect(3260, 40, 537, 532, 79),
        MinimapAccentColor,
        &MinimapLiveWidgets);
    AddSolidRect(
        TEXT("MinimapLiveBackdrop"),
        FRedHUDRect(3266, 46, 525, 520, 80),
        OpaqueLiveMaskColor,
        &MinimapLiveWidgets);

    MinimapLiveImage = WidgetTree->ConstructWidget<UImage>(
        UImage::StaticClass(),
        TEXT("MinimapLiveSurface"));
    MinimapLiveImage->SetVisibility(ESlateVisibility::Collapsed);
    UCanvasPanelSlot* MinimapImageSlot =
        DesignCanvas->AddChildToCanvas(MinimapLiveImage);
    MinimapImageSlot->SetAnchors(FAnchors(0.0f, 0.0f));
    MinimapImageSlot->SetAlignment(FVector2D::ZeroVector);
    MinimapImageSlot->SetPosition(FVector2D(3272.5f, 50.0f));
    MinimapImageSlot->SetSize(FVector2D(512.0f, 512.0f));
    MinimapImageSlot->SetZOrder(81);
    AllLiveWidgets.Add(MinimapLiveImage);
    MinimapLiveWidgets.Add(MinimapLiveImage);

    AddSolidRect(
        TEXT("MinimapLiveLabelMask"),
        FRedHUDRect(3270, 512, 517, 50, 82),
        FLinearColor(0.018f, 0.008f, 0.055f, 0.90f),
        &MinimapLiveWidgets);
    MinimapModeText = AddText(
        TEXT("MinimapLiveMode"),
        FRedHUDRect(3290, 520, 477, 34, 83),
        20,
        ETextJustify::Center,
        MinimapAccentColor,
        &MinimapLiveWidgets);
    if (MinimapModeText)
    {
        MinimapModeText->SetText(FText::FromString(TEXT("LOCAL SURFACE")));
    }
    AddSolidRect(
        TEXT("MinimapLocalMarkerHorizontal"),
        FRedHUDRect(3509, 302.5f, 39, 7, 84),
        MinimapPlayerColor,
        &MinimapLiveWidgets);
    AddSolidRect(
        TEXT("MinimapLocalMarkerVertical"),
        FRedHUDRect(3525, 286.5f, 7, 39, 84),
        MinimapPlayerColor,
        &MinimapLiveWidgets);
    SetLiveGroupVisibility(MinimapLiveWidgets, false);

    // Enemy live data.
    AddSolidRect(TEXT("EnemyNameMask"), FRedHUDRect(2350, 589, 690, 72, 82), LiveMaskColor, &EnemyLiveWidgets);
    EnemyNameText = AddText(TEXT("EnemyNameText"), FRedHUDRect(2370, 592, 640, 62, 83), 36, ETextJustify::Center, FLinearColor::White, &EnemyLiveWidgets);

    AddSolidRect(TEXT("EnemyHealthMask"), FRedHUDRect(2355, 678, 825, 48, 82), LiveMaskColor, &EnemyLiveWidgets);
    EnemyHealthFill = AddFill(TEXT("EnemyHealthFill"), FRedHUDRect(2355, 678, 825, 48, 83), EnemyHealthColor, &EnemyLiveWidgets);
    EnemyHealthText = AddText(TEXT("EnemyHealthText"), FRedHUDRect(3050, 681, 120, 42, 84), 22, ETextJustify::Right, FLinearColor::White, &EnemyLiveWidgets);

    // Quest live data.
    AddSolidRect(TEXT("QuestTextMask"), FRedHUDRect(1090, 1848, 675, 145, 82), LiveMaskColor, &QuestLiveWidgets);
    QuestTitleText = AddText(TEXT("QuestTitleText"), FRedHUDRect(1110, 1852, 575, 52, 83), 31, ETextJustify::Left, FLinearColor::White, &QuestLiveWidgets);
    QuestObjectiveText = AddText(TEXT("QuestObjectiveText"), FRedHUDRect(1110, 1910, 575, 48, 83), 27, ETextJustify::Left, ObjectiveColor, &QuestLiveWidgets);
    QuestProgressText = AddText(TEXT("QuestProgressText"), FRedHUDRect(1670, 1915, 88, 48, 84), 28, ETextJustify::Right, FLinearColor::White, &QuestLiveWidgets);

	// RED weapons use heat, never ammunition. Opaque masks remove the sample ammo
	// values baked into the supplied cards; live heat status replaces that band.
	WeaponHeatFills.SetNum(2);
	WeaponCooldownText.SetNum(2);
	const FRedHUDRect TelemetryMasks[2] = { FRedHUDRect(2990, 2057, 156, 47, 82), FRedHUDRect(3170, 2059, 155, 47, 82) };
	const FRedHUDRect HeatRects[2] = { FRedHUDRect(2991, 2088, 154, 9, 83), FRedHUDRect(3171, 2090, 153, 9, 83) };
	const FRedHUDRect HeatTextRects[2] = { FRedHUDRect(3000, 2058, 138, 28, 84), FRedHUDRect(3180, 2060, 138, 28, 84) };
	for (int32 Index = 0; Index < 2; ++Index)
	{
		AddSolidRect(*FString::Printf(TEXT("WeaponAmmoMask%d"), Index), TelemetryMasks[Index], OpaqueLiveMaskColor, &WeaponLiveWidgets);
		WeaponHeatFills[Index] = AddFill(*FString::Printf(TEXT("WeaponHeatFill%d"), Index), HeatRects[Index], FLinearColor(1.f, .22f, .05f, 1.f), &WeaponLiveWidgets);
		WeaponCooldownText[Index] = AddText(*FString::Printf(TEXT("WeaponHeatStatus%d"), Index), HeatTextRects[Index], 18, ETextJustify::Center, FLinearColor::White, &WeaponLiveWidgets);
		WeaponCooldownText[Index]->SetVisibility(ESlateVisibility::Collapsed);
	}

    // Consumable counts.
    ConsumableCountText.SetNum(3);
    const FRedHUDRect CountMasks[3] =
    {
        FRedHUDRect(188, 1375, 68, 72, 82),
        FRedHUDRect(390, 1382, 68, 72, 82),
        FRedHUDRect(585, 1382, 68, 72, 82)
    };
    const FRedHUDRect CountTexts[3] =
    {
        FRedHUDRect(190, 1378, 62, 62, 83),
        FRedHUDRect(392, 1385, 62, 62, 83),
        FRedHUDRect(587, 1385, 62, 62, 83)
    };

    for (int32 Index = 0; Index < 3; ++Index)
    {
        AddSolidRect(*FString::Printf(TEXT("ConsumableCountMask%d"), Index + 1), CountMasks[Index], LiveMaskColor, &ConsumableLiveWidgets);
        ConsumableCountText[Index] = AddText(
            *FString::Printf(TEXT("ConsumableCountText%d"), Index + 1),
            CountTexts[Index],
            36,
            ETextJustify::Right,
            FLinearColor::White,
            &ConsumableLiveWidgets);
    }

    // Cooldown numbers. These are not included in AllLiveWidgets because visibility is state-driven.
    AbilityCooldownText.SetNum(4);
    for (int32 Index = 0; Index < 4; ++Index)
    {
        AbilityCooldownText[Index] = AddText(
            *FString::Printf(TEXT("AbilityCooldownText%d"), Index),
            GamepadAbilityStatusRects[Index],
            48,
            ETextJustify::Center,
            FLinearColor::White,
            nullptr);
        AllLiveWidgets.Remove(AbilityCooldownText[Index]);
        AbilityCooldownText[Index]->SetVisibility(ESlateVisibility::Collapsed);
    }
}

UTexture2D* URedHUDWidget::LoadTexture(const TCHAR* ObjectPath) const
{
    UTexture2D* Texture = LoadObject<UTexture2D>(nullptr, ObjectPath);
    ensureMsgf(Texture != nullptr, TEXT("RED HUD texture missing: %s. Run Scripts/ImportRedHUD.py first."), ObjectPath);
    return Texture;
}

UImage* URedHUDWidget::AddImage(const FName Name, const TCHAR* TexturePath, const FRedHUDRect& Rect, const bool bInitiallyVisible)
{
    check(DesignCanvas);

    UImage* Image = WidgetTree->ConstructWidget<UImage>(UImage::StaticClass(), Name);
    if (UTexture2D* Texture = LoadTexture(TexturePath))
    {
        Image->SetBrushFromTexture(Texture, true);
    }

    Image->SetVisibility(bInitiallyVisible ? ESlateVisibility::HitTestInvisible : ESlateVisibility::Collapsed);

    UCanvasPanelSlot* CanvasSlot = DesignCanvas->AddChildToCanvas(Image);
    CanvasSlot->SetAnchors(FAnchors(0.0f, 0.0f));
    CanvasSlot->SetAlignment(FVector2D::ZeroVector);
    CanvasSlot->SetPosition(Rect.Position());
    CanvasSlot->SetSize(Rect.Size());
    CanvasSlot->SetZOrder(Rect.Z);

    ArtImages.Add(Name, Image);
    return Image;
}

UBorder* URedHUDWidget::AddSolidRect(
    const FName Name,
    const FRedHUDRect& Rect,
    const FLinearColor Color,
    TArray<TObjectPtr<UWidget>>* Group)
{
    UBorder* Border = WidgetTree->ConstructWidget<UBorder>(UBorder::StaticClass(), Name);

    FSlateBrush Brush;
    Brush.DrawAs = ESlateBrushDrawType::Box;
    Brush.TintColor = FSlateColor(FLinearColor::White);
    Border->SetBrush(Brush);
    Border->SetBrushColor(Color);
    Border->SetVisibility(ESlateVisibility::Collapsed);

    UCanvasPanelSlot* CanvasSlot = DesignCanvas->AddChildToCanvas(Border);
    CanvasSlot->SetAnchors(FAnchors(0.0f, 0.0f));
    CanvasSlot->SetAlignment(FVector2D::ZeroVector);
    CanvasSlot->SetPosition(Rect.Position());
    CanvasSlot->SetSize(Rect.Size());
    CanvasSlot->SetZOrder(Rect.Z);

    AllLiveWidgets.Add(Border);
    if (Group)
    {
        Group->Add(Border);
    }

    return Border;
}

UTextBlock* URedHUDWidget::AddText(
    const FName Name,
    const FRedHUDRect& Rect,
    const int32 FontSize,
    const ETextJustify::Type Justification,
    const FLinearColor Color,
    TArray<TObjectPtr<UWidget>>* Group)
{
    UTextBlock* Text = WidgetTree->ConstructWidget<UTextBlock>(UTextBlock::StaticClass(), Name);
    Text->SetText(FText::GetEmpty());
    Text->SetJustification(Justification);
    Text->SetColorAndOpacity(FSlateColor(Color));
    Text->SetShadowOffset(FVector2D(2.0f, 2.0f));
    Text->SetShadowColorAndOpacity(FLinearColor(0.0f, 0.0f, 0.0f, 0.95f));
    Text->SetAutoWrapText(false);
    Text->SetVisibility(ESlateVisibility::Collapsed);

    FSlateFontInfo FontInfo = Text->GetFont();
    FontInfo.Size = FontSize;
    FontInfo.OutlineSettings.OutlineSize = 2;
    Text->SetFont(FontInfo);

    UCanvasPanelSlot* CanvasSlot = DesignCanvas->AddChildToCanvas(Text);
    CanvasSlot->SetAnchors(FAnchors(0.0f, 0.0f));
    CanvasSlot->SetAlignment(FVector2D::ZeroVector);
    CanvasSlot->SetPosition(Rect.Position());
    CanvasSlot->SetSize(Rect.Size());
    CanvasSlot->SetZOrder(Rect.Z);

    AllLiveWidgets.Add(Text);
    if (Group)
    {
        Group->Add(Text);
    }

    return Text;
}

URedHUDWidget::FMutableFill URedHUDWidget::AddFill(
    const FName Name,
    const FRedHUDRect& Rect,
    const FLinearColor Color,
    TArray<TObjectPtr<UWidget>>* Group)
{
    FMutableFill Result;
    Result.Widget = AddSolidRect(Name, Rect, Color, Group);
    Result.Slot = CastChecked<UCanvasPanelSlot>(Result.Widget->Slot);
    Result.MaxWidth = Rect.W;
    Result.Height = Rect.H;
    return Result;
}

URedHUDWidget::FMutableDepletionMask URedHUDWidget::AddDepletionMask(
    const FName Name,
    const FRedHUDRect& Rect,
    const FLinearColor Color,
    TArray<TObjectPtr<UWidget>>* Group)
{
    FMutableDepletionMask Result;
    Result.Widget = AddSolidRect(Name, Rect, Color, Group);
    Result.Slot = CastChecked<UCanvasPanelSlot>(Result.Widget->Slot);
    Result.Slot->SetAlignment(FVector2D(1.0f, 0.0f));
    Result.Slot->SetPosition(FVector2D(Rect.X + Rect.W, Rect.Y));
    Result.MaxWidth = Rect.W;
    Result.Height = Rect.H;
    SetDepletionPercent(Result, 1.0f);
    return Result;
}

void URedHUDWidget::SetFillPercent(FMutableFill& Fill, const float Percent)
{
    if (!Fill.Slot)
    {
        return;
    }

    const float Clamped = FMath::Clamp(Percent, 0.0f, 1.0f);
    Fill.Slot->SetSize(FVector2D(Fill.MaxWidth * Clamped, Fill.Height));
}

void URedHUDWidget::SetDepletionPercent(
    FMutableDepletionMask& Fill,
    const float Percent)
{
    if (!Fill.Slot)
    {
        return;
    }

    const float Clamped = FMath::Clamp(Percent, 0.0f, 1.0f);
    Fill.Slot->SetSize(FVector2D(
        Fill.MaxWidth * (1.0f - Clamped),
        Fill.Height));
}

void URedHUDWidget::SetLiveGroupVisibility(const TArray<TObjectPtr<UWidget>>& Group, const bool bVisible)
{
    for (UWidget* Widget : Group)
    {
        if (Widget)
        {
            Widget->SetVisibility(bVisible ? ESlateVisibility::HitTestInvisible : ESlateVisibility::Collapsed);
        }
    }
}

void URedHUDWidget::SetLiveDataMode(const bool bEnabled)
{
    bLiveDataMode = bEnabled;

    // This function deliberately collapses every live widget before rebuilding
    // the selected groups. Force the change-only ability path to repaint even
    // when a layout replay reapplies the same live-data mode.
    InvalidateAbilityPresentationCache();

    // ExactArt is a literal presentation of the supplied 3840x2160 reference.
    // Reconstructing that image from separately filtered translucent sprites can
    // change edge pixels, so the authored composite is the only artwork shown in
    // exact mode.  LiveData mode deliberately swaps to the supplied component
    // sprites so gameplay values can be overlaid and updated.
    for (const TPair<FName, TObjectPtr<UImage>>& Pair : ArtImages)
    {
        UImage* Image = Pair.Value;
        if (!Image || Image == ReferenceOverlay)
        {
            continue;
        }

        // These supplied sprites contain baked sample gameplay state. Keep them
        // fail-closed until each domain has a trustworthy live consumer.
        Image->SetVisibility(bLiveDataMode && !IsDormantLiveDataArtName(Pair.Key)
            ? ESlateVisibility::HitTestInvisible
            : ESlateVisibility::Collapsed);
    }

    if (ReferenceOverlay)
    {
        ReferenceOverlay->SetColorAndOpacity(FLinearColor::White);
        ReferenceOverlay->SetVisibility(bLiveDataMode
            ? ESlateVisibility::Collapsed
            : ESlateVisibility::HitTestInvisible);
    }

    for (UWidget* Widget : AllLiveWidgets)
    {
        if (Widget)
        {
            Widget->SetVisibility(ESlateVisibility::Collapsed);
        }
    }

    if (bLiveDataMode)
    {
        ApplyInputSchemeVisibility();
        RefreshMinimapPresentationVisibility();

        if (const TObjectPtr<UImage>* EnemyArt = ArtImages.Find(TEXT("EnemyNameplate")))
        {
            (*EnemyArt)->SetVisibility(bEnemyVisible
                ? ESlateVisibility::HitTestInvisible
                : ESlateVisibility::Collapsed);
        }

        if (const TObjectPtr<UImage>* QuestArt = ArtImages.Find(TEXT("QuestPanel")))
        {
            (*QuestArt)->SetVisibility(bQuestVisible
                ? ESlateVisibility::HitTestInvisible
                : ESlateVisibility::Collapsed);
        }

        SetLiveGroupVisibility(PlayerLiveWidgets, true);
        SetLiveGroupVisibility(CompassLiveWidgets, true);
        SetLiveGroupVisibility(WeaponLiveWidgets, true);
        SetLiveGroupVisibility(ConsumableLiveWidgets, false);
        SetLiveGroupVisibility(EnemyLiveWidgets, bEnemyVisible);
        SetLiveGroupVisibility(QuestLiveWidgets, bQuestVisible);
        SetLiveGroupVisibility(
            MiningResultWidgets,
            MiningResultSecondsRemaining > 0.0f);

        for (int32 Index = 0; Index < CachedAbilityStates.Num() && Index < 4; ++Index)
        {
            SetAbilityState(Index, CachedAbilityStates[Index]);
        }
        for (int32 Index = 0; Index < CachedWeaponStates.Num() && Index < 2; ++Index)
        {
            SetWeaponState(Index, CachedWeaponStates[Index]);
        }
    }
    else
    {
        for (UTextBlock* Text : AbilityCooldownText)
        {
            if (Text)
            {
                Text->SetVisibility(ESlateVisibility::Collapsed);
            }
        }
    }
}

void URedHUDWidget::RefreshMinimapPresentationVisibility()
{
    const bool bLayoutVisible =
        !GetHUDElementLayout(EVibeMMOHUDElement::Minimap).bHidden;
    const bool bShowSurface =
        bLiveDataMode
        && bLayoutVisible
        && CachedMinimapMode == ERedHUDMinimapMode::Surface
        && CachedMinimapPresentationEpoch > 0
        && CachedMinimapSourceOwner.IsValid()
        && !CachedMinimapCelestialFrameId.IsNone()
        && IsValid(CachedMinimapSurfaceTexture)
        && IsValid(MinimapLiveImage);
    SetLiveGroupVisibility(MinimapLiveWidgets, bShowSurface);
}

bool URedHUDWidget::SetMinimapPresentation(
    UObject* SourceOwner,
    UTexture* SurfaceTexture,
    const FName CelestialFrameId,
    const int64 PresentationEpoch,
    const ERedHUDMinimapMode Mode)
{
    if (!IsValid(SourceOwner) || PresentationEpoch <= 0)
    {
        return false;
    }
    if (PresentationEpoch < CachedMinimapPresentationEpoch)
    {
        return false;
    }
    if (PresentationEpoch == CachedMinimapPresentationEpoch)
    {
        if (!CachedMinimapSourceOwner.IsValid())
        {
            // ResetMinimapPresentation leaves an epoch tombstone. A stale
            // producer may not resurrect state at that same epoch.
            return false;
        }
        if (CachedMinimapSourceOwner.Get() != SourceOwner)
        {
            return false;
        }
        const UTexture* ExpectedTexture =
            Mode == ERedHUDMinimapMode::Surface ? SurfaceTexture : nullptr;
        const FName ExpectedFrame =
            Mode == ERedHUDMinimapMode::Surface ? CelestialFrameId : NAME_None;
        if (CachedMinimapMode != Mode
            || CachedMinimapSurfaceTexture.Get() != ExpectedTexture
            || CachedMinimapCelestialFrameId != ExpectedFrame)
        {
            return false;
        }
        return true;
    }
    if (Mode == ERedHUDMinimapMode::Surface
        && (!IsValid(SurfaceTexture) || CelestialFrameId.IsNone()))
    {
        return false;
    }

    CachedMinimapSourceOwner = SourceOwner;
    CachedMinimapPresentationEpoch = PresentationEpoch;
    CachedMinimapMode = Mode;
    CachedMinimapCelestialFrameId =
        Mode == ERedHUDMinimapMode::Surface ? CelestialFrameId : NAME_None;
    CachedMinimapSurfaceTexture =
        Mode == ERedHUDMinimapMode::Surface ? SurfaceTexture : nullptr;
    if (MinimapLiveImage)
    {
        MinimapLiveImage->SetBrushResourceObject(CachedMinimapSurfaceTexture);
    }
    RefreshMinimapPresentationVisibility();
    return true;
}

bool URedHUDWidget::ClearMinimapPresentation(
    UObject* SourceOwner,
    const int64 PresentationEpoch)
{
    if (!IsValid(SourceOwner)
        || CachedMinimapSourceOwner.Get() != SourceOwner
        || PresentationEpoch < CachedMinimapPresentationEpoch)
    {
        return false;
    }

    return ResetMinimapPresentation(PresentationEpoch);
}

bool URedHUDWidget::ResetMinimapPresentation(
    const int64 PresentationEpoch)
{
    if (PresentationEpoch < CachedMinimapPresentationEpoch)
    {
        return false;
    }

    CachedMinimapPresentationEpoch = PresentationEpoch;
    CachedMinimapMode = ERedHUDMinimapMode::Absent;
    CachedMinimapCelestialFrameId = NAME_None;
    CachedMinimapSurfaceTexture = nullptr;
    CachedMinimapSourceOwner.Reset();
    if (MinimapLiveImage)
    {
        MinimapLiveImage->SetBrushResourceObject(nullptr);
    }
    RefreshMinimapPresentationVisibility();
    return true;
}

bool URedHUDWidget::GetMinimapPresentationState(
    const UObject* ExpectedSourceOwner,
    const int64 ExpectedPresentationEpoch,
    ERedHUDMinimapMode& OutMode,
    FName& OutCelestialFrameId,
    bool& bOutVisible) const
{
    OutMode = CachedMinimapMode;
    OutCelestialFrameId = CachedMinimapCelestialFrameId;
    bOutVisible =
        IsValid(ExpectedSourceOwner)
        && CachedMinimapSourceOwner.Get() == ExpectedSourceOwner
        && CachedMinimapPresentationEpoch == ExpectedPresentationEpoch
        && CachedMinimapMode == ERedHUDMinimapMode::Surface
        && IsValid(CachedMinimapSurfaceTexture)
        && IsValid(MinimapLiveImage)
        && MinimapLiveImage->GetVisibility() != ESlateVisibility::Collapsed
        && MinimapLiveImage->GetVisibility() != ESlateVisibility::Hidden
        && GetVisibility() != ESlateVisibility::Collapsed
        && GetVisibility() != ESlateVisibility::Hidden
        && IsInViewport();
    return IsValid(ExpectedSourceOwner)
        && CachedMinimapSourceOwner.Get() == ExpectedSourceOwner
        && CachedMinimapPresentationEpoch == ExpectedPresentationEpoch;
}

void URedHUDWidget::SetReferenceOverlayVisible(const bool bVisible, const float Opacity)
{
    if (!ReferenceOverlay)
    {
        return;
    }

    // ExactArt always remains the untouched, fully opaque authored composite.
    // This function is retained as a comparison overlay for LiveData mode only.
    if (!bLiveDataMode)
    {
        ReferenceOverlay->SetColorAndOpacity(FLinearColor::White);
        ReferenceOverlay->SetVisibility(ESlateVisibility::HitTestInvisible);
        return;
    }

    ReferenceOverlay->SetColorAndOpacity(FLinearColor(1.0f, 1.0f, 1.0f, FMath::Clamp(Opacity, 0.0f, 1.0f)));
    ReferenceOverlay->SetVisibility(bVisible ? ESlateVisibility::HitTestInvisible : ESlateVisibility::Collapsed);
}

void URedHUDWidget::SetInputScheme(const ERedHUDInputScheme NewScheme)
{
    InputScheme = NewScheme;
    ApplyInputSchemeVisibility();

    for (int32 Index = 0; Index < CachedAbilityStates.Num() && Index < 4; ++Index)
    {
        SetAbilityState(Index, CachedAbilityStates[Index]);
    }
}

void URedHUDWidget::ApplyInputSchemeVisibility()
{
    if (!bLiveDataMode)
    {
        return;
    }

    const bool bGamepad = InputScheme == ERedHUDInputScheme::Gamepad;
    const bool bAbilityBarHidden =
        GetHUDElementLayout(EVibeMMOHUDElement::AbilityBar).bHidden;
    const bool bShowGamepad = bGamepad && !bAbilityBarHidden;
    const bool bShowKeyboard = !bGamepad && !bAbilityBarHidden;

    for (UImage* AbilityImage : GamepadAbilityArt)
    {
        if (AbilityImage)
        {
            AbilityImage->SetVisibility(bShowGamepad ? ESlateVisibility::HitTestInvisible : ESlateVisibility::Collapsed);
        }
    }

    const FName GamepadOnlyNames[] = { TEXT("GlyphLB"), TEXT("GlyphPlus"), TEXT("GlyphRB") };
    for (const FName Name : GamepadOnlyNames)
    {
        if (const TObjectPtr<UImage>* Found = ArtImages.Find(Name))
        {
            (*Found)->SetVisibility(bShowGamepad ? ESlateVisibility::HitTestInvisible : ESlateVisibility::Collapsed);
        }
    }

    if (KeyboardAbilityCluster)
    {
        KeyboardAbilityCluster->SetVisibility(bShowKeyboard ? ESlateVisibility::HitTestInvisible : ESlateVisibility::Collapsed);
    }

    if (const TObjectPtr<UImage>* Combo = ArtImages.Find(TEXT("ComboPrompt")))
    {
        (*Combo)->SetVisibility(bShowGamepad ? ESlateVisibility::HitTestInvisible : ESlateVisibility::Collapsed);
    }
}

void URedHUDWidget::ApplySnapshot(const FRedHUDSnapshot& Snapshot)
{
    SetPlayerVitals(Snapshot.Player);
    SetWeaponState(0, Snapshot.Weapon1);
    SetWeaponState(1, Snapshot.Weapon2);
    SetEnemyState(Snapshot.Enemy);
    SetQuestState(Snapshot.Quest);

    for (int32 Index = 0; Index < Snapshot.ConsumableCounts.Num() && Index < 3; ++Index)
    {
        SetConsumableCount(Index, Snapshot.ConsumableCounts[Index]);
    }

    for (int32 Index = 0; Index < Snapshot.Abilities.Num() && Index < 4; ++Index)
    {
        SetAbilityState(Index, Snapshot.Abilities[Index]);
    }
}

void URedHUDWidget::SetPlayerVitals(const FRedHUDPlayerVitals& State)
{
    SetDepletionPercent(
        PlayerShieldDepletionMask,
        SafePercent(State.Shield, State.MaxShield));
    SetDepletionPercent(
        PlayerHealthDepletionMask,
        SafePercent(State.Health, State.MaxHealth));
    SetDepletionPercent(
        PlayerEnergyDepletionMask,
        SafePercent(State.Energy, State.MaxEnergy));

    if (PlayerHealthText)
    {
        PlayerHealthText->SetText(FText::FromString(FString::Printf(
            TEXT("%d / %d"),
            FMath::RoundToInt(State.Health),
            FMath::RoundToInt(State.MaxHealth))));
    }
}

void URedHUDWidget::SetResourceTally(
	const int32 Stone, const int32 Iron, const int32 Crystal)
{
	CachedResourceStone = FMath::Max(0, Stone);
	CachedResourceIron = FMath::Max(0, Iron);
	CachedResourceCrystal = FMath::Max(0, Crystal);
}

bool URedHUDWidget::GetResourceTallyState(
	int32& OutStone, int32& OutIron, int32& OutCrystal,
	FString& OutText, bool& bOutVisible) const
{
	OutStone = CachedResourceStone;
	OutIron = CachedResourceIron;
	OutCrystal = CachedResourceCrystal;
	OutText.Reset();
	bOutVisible = false;
	return true;
}

void URedHUDWidget::ShowMiningResult(
    const FText& ResourceName,
    const int32 Amount,
    const FLinearColor AccentColor)
{
    if (Amount <= 0 || ResourceName.IsEmpty())
    {
        return;
    }

    CachedMiningResultText = FString::Printf(
        TEXT("%s  +%d"),
        *ResourceName.ToString().ToUpper(),
        Amount);
    MiningResultSecondsRemaining = MiningResultLifetimeSeconds;

    if (MiningResultValueText)
    {
        MiningResultValueText->SetText(
            FText::FromString(CachedMiningResultText));
        MiningResultValueText->SetColorAndOpacity(
            FSlateColor(AccentColor));
    }
    if (MiningResultAccent)
    {
        MiningResultAccent->SetBrushColor(AccentColor);
    }
    for (UWidget* Widget : MiningResultWidgets)
    {
        if (Widget)
        {
            Widget->SetRenderOpacity(1.0f);
        }
    }
    SetLiveGroupVisibility(MiningResultWidgets, bLiveDataMode);
    if (UWorld* World = GetWorld())
    {
        World->GetTimerManager().ClearTimer(MiningResultFadeTimer);
        World->GetTimerManager().SetTimer(
            MiningResultFadeTimer,
            this,
            &URedHUDWidget::AdvanceMiningResultFade,
            MiningResultFadeTickSeconds,
            true);
    }
}

bool URedHUDWidget::GetMiningResultState(
    FString& OutText,
    bool& bOutVisible,
    float& OutSecondsRemaining) const
{
    OutText = CachedMiningResultText;
    OutSecondsRemaining = MiningResultSecondsRemaining;

    const ESlateVisibility RootVisibility = GetVisibility();
    const ESlateVisibility ResultVisibility = MiningResultValueText
        ? MiningResultValueText->GetVisibility()
        : ESlateVisibility::Collapsed;
    bOutVisible = IsInViewport()
        && bLiveDataMode
        && MiningResultSecondsRemaining > 0.0f
        && RootVisibility != ESlateVisibility::Collapsed
        && RootVisibility != ESlateVisibility::Hidden
        && ResultVisibility != ESlateVisibility::Collapsed
        && ResultVisibility != ESlateVisibility::Hidden;
    return MiningResultValueText != nullptr;
}

void URedHUDWidget::SetCompassHeadingDegrees(const float HeadingDegrees)
{
	if (!CompassText)
	{
		return;
	}

	const float Heading = FRotator::ClampAxis(HeadingDegrees);
	static const TCHAR* Directions[] =
	{
		TEXT("N"), TEXT("NE"), TEXT("E"), TEXT("SE"),
		TEXT("S"), TEXT("SW"), TEXT("W"), TEXT("NW")
	};
	const int32 DirectionIndex = FMath::RoundToInt(Heading / 45.f) & 7;
	CompassText->SetText(FText::FromString(FString::Printf(
		TEXT("%s   %03d"), Directions[DirectionIndex], FMath::RoundToInt(Heading) % 360)));
}

void URedHUDWidget::SetWeaponState(const int32 WeaponIndex, const FRedHUDWeaponState& State)
{
	if (!CachedWeaponStates.IsValidIndex(WeaponIndex))
	{
		return;
	}
	CachedWeaponStates[WeaponIndex] = State;

	if (!WeaponHeatFills.IsValidIndex(WeaponIndex))
	{
		return;
	}
	SetFillPercent(WeaponHeatFills[WeaponIndex], State.HeatPercent);
	if (WeaponCooldownText.IsValidIndex(WeaponIndex) && WeaponCooldownText[WeaponIndex])
	{
		WeaponCooldownText[WeaponIndex]->SetVisibility(
			bLiveDataMode ? ESlateVisibility::HitTestInvisible : ESlateVisibility::Collapsed);
		if (State.bOverheated && State.OverheatCooldownRemaining > 0.f)
		{
			WeaponCooldownText[WeaponIndex]->SetText(FText::FromString(FString::Printf(TEXT("COOL %.1f"), State.OverheatCooldownRemaining)));
		}
		else if (State.bOverheated)
		{
			WeaponCooldownText[WeaponIndex]->SetText(FText::FromString(TEXT("OVERHEAT")));
		}
		else
		{
			const int32 HeatPercent = FMath::RoundToInt(FMath::Clamp(State.HeatPercent, 0.f, 1.f) * 100.f);
			WeaponCooldownText[WeaponIndex]->SetText(FText::FromString(FString::Printf(TEXT("HEAT %03d%%"), HeatPercent)));
		}
	}

    const FName ImageName = WeaponIndex == 0 ? TEXT("WeaponSlot01") : TEXT("WeaponSlot02");
    if (const TObjectPtr<UImage>* Image = ArtImages.Find(ImageName))
    {
        const FLinearColor SelectedTint = State.bEquipped
            ? FLinearColor(1.12f, 1.02f, 0.72f, 1.0f)
            : FLinearColor::White;
        (*Image)->SetColorAndOpacity(SelectedTint);
    }
}

void URedHUDWidget::SetEnemyState(const FRedHUDEnemyState& State)
{
    // DrawHUD publishes a hidden state while no valid enemy is aimed at. Once the
    // panel is already hidden, avoid rebuilding its text and layout every frame.
    if (!State.bVisible && !bEnemyVisible)
    {
        return;
    }

    bEnemyVisible = State.bVisible;

    if (const TObjectPtr<UImage>* EnemyArt = ArtImages.Find(TEXT("EnemyNameplate")))
    {
        (*EnemyArt)->SetVisibility(bLiveDataMode && State.bVisible
            ? ESlateVisibility::HitTestInvisible
            : ESlateVisibility::Collapsed);
    }

    SetLiveGroupVisibility(EnemyLiveWidgets, bLiveDataMode && State.bVisible);

    if (EnemyNameText)
    {
        const FString UpperName = State.Name.ToUpper();
        EnemyNameText->SetText(FText::FromString(State.Level > 0
            ? FString::Printf(TEXT("LV %d  %s"), State.Level, *UpperName)
            : UpperName));
    }

    SetFillPercent(EnemyHealthFill, SafePercent(State.Health, State.MaxHealth));

    if (EnemyHealthText)
    {
        const int32 Percent = FMath::RoundToInt(SafePercent(State.Health, State.MaxHealth) * 100.0f);
        EnemyHealthText->SetText(FText::FromString(FString::Printf(TEXT("%d%%"), Percent)));
    }
}

void URedHUDWidget::SetQuestState(const FRedHUDQuestState& State)
{
    bQuestVisible = State.bVisible;

    if (const TObjectPtr<UImage>* QuestArt = ArtImages.Find(TEXT("QuestPanel")))
    {
        (*QuestArt)->SetVisibility(bLiveDataMode && State.bVisible
            ? ESlateVisibility::HitTestInvisible
            : ESlateVisibility::Collapsed);
    }

    SetLiveGroupVisibility(QuestLiveWidgets, bLiveDataMode && State.bVisible);

    if (QuestTitleText)
    {
        QuestTitleText->SetText(FText::FromString(State.Title));
    }

    if (QuestObjectiveText)
    {
        QuestObjectiveText->SetText(FText::FromString(State.Objective));
    }

    if (QuestProgressText)
    {
        QuestProgressText->SetText(FText::FromString(FString::Printf(TEXT("%d/%d"), State.Current, State.Target)));
    }
}

void URedHUDWidget::SetConsumableCount(const int32 SlotIndex, const int32 Count)
{
    if (ConsumableCountText.IsValidIndex(SlotIndex))
    {
        ConsumableCountText[SlotIndex]->SetText(FText::AsNumber(FMath::Max(0, Count)));
    }
}

void URedHUDWidget::SetAbilityArtTint(const int32 AbilityIndex, const FRedHUDAbilityState& State)
{
    if (!GamepadAbilityArt.IsValidIndex(AbilityIndex) || !GamepadAbilityArt[AbilityIndex])
    {
        return;
    }

    FLinearColor Tint = FLinearColor::White;

    if (State.bDisabled)
    {
        Tint = FLinearColor(0.28f, 0.28f, 0.30f, 0.45f);
    }
    else if (State.CooldownRemaining > 0.0f || !State.bReady)
    {
        Tint = FLinearColor(0.42f, 0.42f, 0.48f, 0.72f);
    }
    else if (State.bSelected)
    {
        Tint = FLinearColor(1.18f, 1.04f, 0.62f, 1.0f);
    }

    GamepadAbilityArt[AbilityIndex]->SetColorAndOpacity(Tint);
}

void URedHUDWidget::InvalidateAbilityPresentationCache(const int32 AbilityIndex)
{
    if (AbilityIndex == INDEX_NONE)
    {
        for (FAbilityPresentationCache& Presentation : AbilityPresentationCache)
        {
            Presentation.bInitialized = false;
        }
        return;
    }

    if (AbilityPresentationCache.IsValidIndex(AbilityIndex))
    {
        AbilityPresentationCache[AbilityIndex].bInitialized = false;
    }
}

void URedHUDWidget::SetAbilityState(const int32 AbilityIndex, const FRedHUDAbilityState& State)
{
    if (AbilityIndex < 0 || AbilityIndex >= 4)
    {
        return;
    }

    if (CachedAbilityStates.Num() < 4)
    {
        CachedAbilityStates.SetNum(4);
    }
    CachedAbilityStates[AbilityIndex] = State;

    const bool bKeyboard = InputScheme == ERedHUDInputScheme::KeyboardMouse;
    const bool bKeyboardQOrE = AbilityIndex >= 1 && AbilityIndex <= 2;
    const FRedHUDRect& StatusRect = bKeyboard && bKeyboardQOrE
        ? KeyboardAbilityStatusRects[AbilityIndex - 1]
        : GamepadAbilityStatusRects[AbilityIndex];

    // Layout hiding must win over later status ticks; otherwise a cooldown can
    // resurrect after the player intentionally hides the whole ability bar.
    const bool bAbilityBarHidden =
        GetHUDElementLayout(EVibeMMOHUDElement::AbilityBar).bHidden;
    const bool bShowGamepadCooldown =
        bLiveDataMode &&
        !bAbilityBarHidden &&
        !bKeyboard &&
        State.CooldownRemaining > KINDA_SMALL_NUMBER;
    const bool bShowKeyboardStatus =
        bLiveDataMode &&
        !bAbilityBarHidden &&
        bKeyboard &&
        bKeyboardQOrE &&
        (State.bDisabled ||
            State.CooldownRemaining > KINDA_SMALL_NUMBER ||
            !State.bReady);
    const bool bShowStatus = bShowGamepadCooldown || bShowKeyboardStatus;

    // Modes intentionally mirror the exact branch ordering below. Duration and
    // charge are not keyed because the current HUD does not paint either value.
    uint8 ArtTintMode = 0;
    if (State.bDisabled)
    {
        ArtTintMode = 1;
    }
    else if (State.CooldownRemaining > 0.0f || !State.bReady)
    {
        ArtTintMode = 2;
    }
    else if (State.bSelected)
    {
        ArtTintMode = 3;
    }

    uint8 StatusMode = 0;
    FString StatusText;
    if (bShowKeyboardStatus && State.bDisabled)
    {
        StatusMode = 1;
        StatusText = TEXT("X");
    }
    else if (bShowStatus && State.CooldownRemaining > KINDA_SMALL_NUMBER)
    {
        StatusMode = 2;
        StatusText = FString::Printf(
            TEXT("%.1f"),
            FMath::Max(0.0f, State.CooldownRemaining));
    }
    else if (bShowKeyboardStatus)
    {
        StatusMode = 3;
        StatusText = TEXT("...");
    }

    if (AbilityPresentationCache.Num() < 4)
    {
        AbilityPresentationCache.SetNum(4);
    }

    FAbilityPresentationCache* Presentation = bKeyboardQOrE
        ? &AbilityPresentationCache[AbilityIndex]
        : nullptr;
    const bool bPresentationUnchanged =
        Presentation &&
        Presentation->bInitialized &&
        Presentation->InputScheme == InputScheme &&
        Presentation->bLiveMode == bLiveDataMode &&
        Presentation->bAbilityBarHidden == bAbilityBarHidden &&
        Presentation->ArtTintMode == ArtTintMode &&
        Presentation->StatusMode == StatusMode &&
        Presentation->StatusText == StatusText;
    if (bPresentationUnchanged)
    {
        return;
    }

    if (Presentation)
    {
        // Validity is restored only after all required Q/E targets are applied.
        Presentation->bInitialized = false;
        Presentation->InputScheme = InputScheme;
        Presentation->bLiveMode = bLiveDataMode;
        Presentation->bAbilityBarHidden = bAbilityBarHidden;
        Presentation->ArtTintMode = ArtTintMode;
        Presentation->StatusMode = StatusMode;
        Presentation->StatusText = StatusText;
    }

    SetAbilityArtTint(AbilityIndex, State);

    if (!AbilityCooldownText.IsValidIndex(AbilityIndex) || !AbilityCooldownText[AbilityIndex])
    {
        return;
    }

    UCanvasPanelSlot* StatusSlot = Cast<UCanvasPanelSlot>(AbilityCooldownText[AbilityIndex]->Slot);
    if (StatusSlot)
    {
        StatusSlot->SetPosition(StatusRect.Position());
        StatusSlot->SetSize(StatusRect.Size());
        StatusSlot->SetZOrder(StatusRect.Z);
    }

    AbilityCooldownText[AbilityIndex]->SetVisibility(
        bShowStatus ? ESlateVisibility::HitTestInvisible : ESlateVisibility::Collapsed);

    if (bShowKeyboardStatus && State.bDisabled)
    {
        AbilityCooldownText[AbilityIndex]->SetText(FText::FromString(TEXT("X")));
        AbilityCooldownText[AbilityIndex]->SetColorAndOpacity(
            FSlateColor(FLinearColor(0.62f, 0.62f, 0.66f, 1.0f)));
    }
    else if (bShowStatus && State.CooldownRemaining > KINDA_SMALL_NUMBER)
    {
        AbilityCooldownText[AbilityIndex]->SetText(FText::FromString(StatusText));
        AbilityCooldownText[AbilityIndex]->SetColorAndOpacity(FSlateColor(FLinearColor::White));
    }
    else if (bShowKeyboardStatus)
    {
        // Fail visibly closed if a future producer reports not-ready without a
        // cooldown or disabled reason; do not let untouched art imply readiness.
        AbilityCooldownText[AbilityIndex]->SetText(FText::FromString(TEXT("...")));
        AbilityCooldownText[AbilityIndex]->SetColorAndOpacity(
            FSlateColor(FLinearColor(0.72f, 0.72f, 0.78f, 1.0f)));
    }

    if (Presentation)
    {
        const bool bHasRequiredTargets =
            GamepadAbilityArt.IsValidIndex(AbilityIndex) &&
            GamepadAbilityArt[AbilityIndex] &&
            AbilityCooldownText[AbilityIndex] &&
            StatusSlot;
        Presentation->bInitialized = bHasRequiredTargets;
    }
}

void URedHUDWidget::SetElementVisible(const FName ElementName, const bool bVisible)
{
    if (const TObjectPtr<UImage>* Found = ArtImages.Find(ElementName))
    {
        if (*Found == ReferenceOverlay)
        {
            SetReferenceOverlayVisible(bVisible, 1.0f);
            return;
        }

        (*Found)->SetVisibility(bLiveDataMode && bVisible && !IsDormantLiveDataArtName(ElementName)
            ? ESlateVisibility::HitTestInvisible
            : ESlateVisibility::Collapsed);
    }
}

void URedHUDWidget::SetElementTint(const FName ElementName, const FLinearColor Tint)
{
    if (const TObjectPtr<UImage>* Found = ArtImages.Find(ElementName))
    {
        if (*Found == ReferenceOverlay && !bLiveDataMode)
        {
            // ExactArt mode is a literal display of the supplied full composite.
            // Never allow runtime tinting to alter its authored pixels.
            ReferenceOverlay->SetColorAndOpacity(FLinearColor::White);
            return;
        }

        (*Found)->SetColorAndOpacity(Tint);

        // The authoritative ability presentation historically restored these
        // semantic tints on the next status tick. Preserve that behavior when
        // Q/E writes are otherwise suppressed as unchanged.
        if (ElementName == FName(TEXT("AbilityLeft")))
        {
            InvalidateAbilityPresentationCache(1);
        }
        else if (ElementName == FName(TEXT("AbilityRight")))
        {
            InvalidateAbilityPresentationCache(2);
        }
    }
}
