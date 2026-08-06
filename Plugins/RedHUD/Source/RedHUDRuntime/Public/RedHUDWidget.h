#pragma once

#include "CoreMinimal.h"
#include "Blueprint/UserWidget.h"
#include "Components/TextBlock.h"
#include "Data/VibeMMOHUDLayoutTypes.h"
#include "RedHUDTypes.h"
#include "RedHUDWidget.generated.h"

class UBorder;
class UCanvasPanel;
class UCanvasPanelSlot;
class UImage;
class UTextBlock;
class UTexture;
class UTexture2D;
class UVibeMMOHUDLayoutSubsystem;
struct FRedHUDRect;

UCLASS(BlueprintType)
class REDHUDRUNTIME_API URedHUDWidget : public UUserWidget
{
    GENERATED_BODY()

public:
    UFUNCTION(BlueprintCallable, Category="RED HUD")
    void ApplySnapshot(const FRedHUDSnapshot& Snapshot);

    UFUNCTION(BlueprintCallable, Category="RED HUD")
    void SetInputScheme(ERedHUDInputScheme NewScheme);

    // ExactArt mode preserves every provided raster pixel. LiveData mode overlays masks,
    // live text and state-driven depletion occluders over flattened placeholder values.
    UFUNCTION(BlueprintCallable, Category="RED HUD")
    void SetLiveDataMode(bool bEnabled);

    UFUNCTION(BlueprintCallable, Category="RED HUD")
    void SetReferenceOverlayVisible(bool bVisible, float Opacity = 0.5f);

    UFUNCTION(BlueprintCallable, Category="RED HUD")
    void SetPlayerVitals(const FRedHUDPlayerVitals& State);

    /**
     * Stores authoritative mined-resource inventory totals without putting a
     * permanent inventory readout on the combat HUD.
     */
    UFUNCTION(BlueprintCallable, Category="RED HUD")
    void SetResourceTally(int32 Stone, int32 Iron, int32 Crystal);

    /** Native acceptance bridge for the hidden inventory cache. */
    bool GetResourceTallyState(
        int32& OutStone, int32& OutIron, int32& OutCrystal,
        FString& OutText, bool& bOutVisible) const;

    /** Shows one short owner-only mining receipt, then fades it away. */
    UFUNCTION(BlueprintCallable, Category="RED HUD")
    void ShowMiningResult(
        const FText& ResourceName,
        int32 Amount,
        FLinearColor AccentColor);

    /** Native acceptance bridge for the transient mining receipt. */
    bool GetMiningResultState(
        FString& OutText,
        bool& bOutVisible,
        float& OutSecondsRemaining) const;

    UFUNCTION(BlueprintCallable, Category="RED HUD")
    void SetCompassHeadingDegrees(float HeadingDegrees);

    /**
     * Publishes one local surface capture into the replacement HUD. The source
     * owner, stable celestial frame and monotonic presentation epoch are all
     * required; Space intentionally remains hidden rather than reusing surface
     * pixels or the supplied baked contacts.
     */
    bool SetMinimapPresentation(
        UObject* SourceOwner,
        UTexture* SurfaceTexture,
        FName CelestialFrameId,
        int64 PresentationEpoch,
        ERedHUDMinimapMode Mode);

    /** Clears only the matching current source; stale owners/epochs are rejected. */
    bool ClearMinimapPresentation(
        UObject* SourceOwner,
        int64 PresentationEpoch);

    /** HUD-owner reset used when the old weak source has already expired. */
    bool ResetMinimapPresentation(int64 PresentationEpoch);

    /** Native acceptance/capture-lifecycle query. */
    bool GetMinimapPresentationState(
        const UObject* ExpectedSourceOwner,
        int64 ExpectedPresentationEpoch,
        ERedHUDMinimapMode& OutMode,
        FName& OutCelestialFrameId,
        bool& bOutVisible) const;

    UFUNCTION(BlueprintCallable, Category="RED HUD")
    void SetWeaponState(int32 WeaponIndex, const FRedHUDWeaponState& State);

    UFUNCTION(BlueprintCallable, Category="RED HUD")
    void SetEnemyState(const FRedHUDEnemyState& State);

    UFUNCTION(BlueprintCallable, Category="RED HUD")
    void SetQuestState(const FRedHUDQuestState& State);

    UFUNCTION(BlueprintCallable, Category="RED HUD")
    void SetConsumableCount(int32 SlotIndex, int32 Count);

    UFUNCTION(BlueprintCallable, Category="RED HUD")
    void SetAbilityState(int32 AbilityIndex, const FRedHUDAbilityState& State);

    UFUNCTION(BlueprintCallable, Category="RED HUD")
    void SetElementVisible(FName ElementName, bool bVisible);

    UFUNCTION(BlueprintCallable, Category="RED HUD")
    void SetElementTint(FName ElementName, FLinearColor Tint);

    UFUNCTION(BlueprintPure, Category="RED HUD|Layout")
    FVibeMMOHUDElementLayout GetHUDElementLayout(EVibeMMOHUDElement Element) const;

    /**
     * Mutation results are change signals: true means the sanitized per-player
     * layout changed; false also covers clamped/already-equal no-ops.
     */
    UFUNCTION(BlueprintCallable, Category="RED HUD|Layout")
    bool NudgeHUDElement(EVibeMMOHUDElement Element, FVector2D NormalizedDelta);

    UFUNCTION(BlueprintCallable, Category="RED HUD|Layout")
    bool SetHUDElementScale(EVibeMMOHUDElement Element, float Scale);

    UFUNCTION(BlueprintCallable, Category="RED HUD|Layout")
    bool SetHUDElementOpacity(EVibeMMOHUDElement Element, float Opacity);

    UFUNCTION(BlueprintCallable, Category="RED HUD|Layout")
    bool SetHUDElementHidden(EVibeMMOHUDElement Element, bool bHidden);

    UFUNCTION(BlueprintCallable, Category="RED HUD|Layout")
    bool SetHUDElementLocked(EVibeMMOHUDElement Element, bool bLocked);

    UFUNCTION(BlueprintCallable, Category="RED HUD|Layout")
    bool ResetHUDElement(EVibeMMOHUDElement Element);

    UFUNCTION(BlueprintCallable, Category="RED HUD|Layout")
    bool ResetAllHUDElements();

    UFUNCTION(BlueprintCallable, Category="RED HUD|Layout")
    bool SaveHUDLayout();

protected:
    virtual void NativeOnInitialized() override;
    virtual void NativeDestruct() override;

private:
    struct FMutableFill
    {
        TObjectPtr<UBorder> Widget = nullptr;
        TObjectPtr<UCanvasPanelSlot> Slot = nullptr;
        float MaxWidth = 0.0f;
        float Height = 0.0f;
    };

    struct FMutableDepletionMask
    {
        TObjectPtr<UBorder> Widget = nullptr;
        TObjectPtr<UCanvasPanelSlot> Slot = nullptr;
        float MaxWidth = 0.0f;
        float Height = 0.0f;
    };

    struct FAbilityPresentationCache
    {
        ERedHUDInputScheme InputScheme = ERedHUDInputScheme::Gamepad;
        FString StatusText;
        uint8 ArtTintMode = 0;
        uint8 StatusMode = 0;
        bool bLiveMode = false;
        bool bAbilityBarHidden = false;
        bool bInitialized = false;
    };

    void BuildWidgetTree();
    void BuildArtwork();
    void BuildLiveOverlay();
    void ApplyInputSchemeVisibility();

    UTexture2D* LoadTexture(const TCHAR* ObjectPath) const;
    UImage* AddImage(FName Name, const TCHAR* TexturePath, const FRedHUDRect& Rect, bool bInitiallyVisible = true);
    UBorder* AddSolidRect(FName Name, const FRedHUDRect& Rect, FLinearColor Color, TArray<TObjectPtr<UWidget>>* Group = nullptr);
    UTextBlock* AddText(
        FName Name,
        const FRedHUDRect& Rect,
        int32 FontSize,
        ETextJustify::Type Justification,
        FLinearColor Color,
        TArray<TObjectPtr<UWidget>>* Group = nullptr);
    FMutableFill AddFill(FName Name, const FRedHUDRect& Rect, FLinearColor Color, TArray<TObjectPtr<UWidget>>* Group = nullptr);
    FMutableDepletionMask AddDepletionMask(
        FName Name,
        const FRedHUDRect& Rect,
        FLinearColor Color,
        TArray<TObjectPtr<UWidget>>* Group = nullptr);

    void SetFillPercent(FMutableFill& Fill, float Percent);
    void SetDepletionPercent(FMutableDepletionMask& Fill, float Percent);
    void SetLiveGroupVisibility(const TArray<TObjectPtr<UWidget>>& Group, bool bVisible);
    void RefreshMinimapPresentationVisibility();
    void SetAbilityArtTint(int32 AbilityIndex, const FRedHUDAbilityState& State);
    void InvalidateAbilityPresentationCache(int32 AbilityIndex = INDEX_NONE);
    void AdvanceMiningResultFade();
    void BindHUDLayout();
    void ApplyHUDLayout();
    void ApplyHUDElementLayout(EVibeMMOHUDElement Element);
    bool CommitHUDElementLayout(EVibeMMOHUDElement Element, const FVibeMMOHUDElementLayout& Layout);
    TArray<UWidget*> ResolveHUDElementWidgets(EVibeMMOHUDElement Element) const;

    UFUNCTION()
    void HandleHUDLayoutChanged();

private:
    UPROPERTY(Transient)
    TObjectPtr<UCanvasPanel> DesignCanvas = nullptr;

    UPROPERTY(Transient)
    TObjectPtr<UVibeMMOHUDLayoutSubsystem> HUDLayoutSubsystem = nullptr;

    UPROPERTY(Transient)
    TMap<FName, TObjectPtr<UImage>> ArtImages;

    UPROPERTY(Transient)
    TObjectPtr<UImage> KeyboardAbilityCluster = nullptr;

    UPROPERTY(Transient)
    TObjectPtr<UImage> ReferenceOverlay = nullptr;

    UPROPERTY(Transient)
    TArray<TObjectPtr<UImage>> GamepadAbilityArt;

    UPROPERTY(Transient)
    TArray<TObjectPtr<UTextBlock>> AbilityCooldownText;

    UPROPERTY(Transient)
    TArray<TObjectPtr<UWidget>> AllLiveWidgets;

    UPROPERTY(Transient)
    TArray<TObjectPtr<UWidget>> PlayerLiveWidgets;

    UPROPERTY(Transient)
    TArray<TObjectPtr<UWidget>> CompassLiveWidgets;

    UPROPERTY(Transient)
    TArray<TObjectPtr<UWidget>> MinimapLiveWidgets;

    UPROPERTY(Transient)
    TArray<TObjectPtr<UWidget>> EnemyLiveWidgets;

    UPROPERTY(Transient)
    TArray<TObjectPtr<UWidget>> QuestLiveWidgets;

    UPROPERTY(Transient)
    TArray<TObjectPtr<UWidget>> WeaponLiveWidgets;

    UPROPERTY(Transient)
    TArray<TObjectPtr<UWidget>> ConsumableLiveWidgets;

    UPROPERTY(Transient)
    TArray<TObjectPtr<UWidget>> MiningResultWidgets;

    UPROPERTY(Transient)
    TObjectPtr<UTextBlock> PlayerHealthText = nullptr;

    UPROPERTY(Transient)
    TObjectPtr<UImage> MiningResultArt = nullptr;

    UPROPERTY(Transient)
    TObjectPtr<UBorder> MiningResultTextMask = nullptr;

    UPROPERTY(Transient)
    TObjectPtr<UBorder> MiningResultAccent = nullptr;

    UPROPERTY(Transient)
    TObjectPtr<UTextBlock> MiningResultLabelText = nullptr;

    UPROPERTY(Transient)
    TObjectPtr<UTextBlock> MiningResultValueText = nullptr;

    UPROPERTY(Transient)
    TObjectPtr<UTextBlock> CompassText = nullptr;

    UPROPERTY(Transient)
    TObjectPtr<UImage> MinimapLiveImage = nullptr;

    UPROPERTY(Transient)
    TObjectPtr<UTextBlock> MinimapModeText = nullptr;

    UPROPERTY(Transient)
    TObjectPtr<UTexture> CachedMinimapSurfaceTexture = nullptr;

    UPROPERTY(Transient)
    TObjectPtr<UTextBlock> EnemyNameText = nullptr;

    UPROPERTY(Transient)
    TObjectPtr<UTextBlock> EnemyHealthText = nullptr;

    UPROPERTY(Transient)
    TObjectPtr<UTextBlock> QuestTitleText = nullptr;

    UPROPERTY(Transient)
    TObjectPtr<UTextBlock> QuestObjectiveText = nullptr;

    UPROPERTY(Transient)
    TObjectPtr<UTextBlock> QuestProgressText = nullptr;

	TArray<FMutableFill> WeaponHeatFills;

	UPROPERTY(Transient)
	TArray<TObjectPtr<UTextBlock>> WeaponCooldownText;

    UPROPERTY(Transient)
    TArray<TObjectPtr<UTextBlock>> ConsumableCountText;

    FMutableDepletionMask PlayerShieldDepletionMask;
    FMutableDepletionMask PlayerHealthDepletionMask;
    FMutableDepletionMask PlayerEnergyDepletionMask;
    FMutableFill EnemyHealthFill;

    ERedHUDInputScheme InputScheme = ERedHUDInputScheme::Gamepad;
    bool bLiveDataMode = false;
    bool bEnemyVisible = false;
    bool bQuestVisible = false;
    TWeakObjectPtr<UObject> CachedMinimapSourceOwner;
    FName CachedMinimapCelestialFrameId = NAME_None;
    int64 CachedMinimapPresentationEpoch = 0;
    ERedHUDMinimapMode CachedMinimapMode = ERedHUDMinimapMode::Absent;
    int32 CachedResourceStone = 0;
    int32 CachedResourceIron = 0;
    int32 CachedResourceCrystal = 0;
    FString CachedMiningResultText;
    float MiningResultSecondsRemaining = 0.0f;
    FTimerHandle MiningResultFadeTimer;
    TArray<FRedHUDWeaponState> CachedWeaponStates;
    TArray<FRedHUDAbilityState> CachedAbilityStates;
    TArray<FAbilityPresentationCache> AbilityPresentationCache;
};
