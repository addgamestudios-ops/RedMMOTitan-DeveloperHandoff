#pragma once

#include "CoreMinimal.h"
#include "Data/VibeMMOHUDLayoutTypes.h"
#include "Data/VibeMMOUIDataAssets.h"
#include "Widgets/Layout/Anchors.h"
#include "Widgets/VibeMMOBaseWidget.h"
#include "VibeMMOHUDWidget.generated.h"

class UTextBlock;
class UBorder;
class UButton;
class UCanvasPanel;
class UCanvasPanelSlot;
class UImage;
class UMaterialInstanceDynamic;
class UOverlay;
class UProgressBar;
class UWidget;
class UVibeMMOHUDLayoutDataAsset;
class UVibeMMOHUDLayoutSubsystem;
struct FSlateDynamicImageBrush;

DECLARE_DYNAMIC_MULTICAST_DELEGATE(FVibeMMOAbilityLoadoutSwapRequested);

UENUM(BlueprintType)
enum class EVibeMMOMinimapMode : uint8
{
	Surface UMETA(DisplayName = "Surface"),
	Space UMETA(DisplayName = "Space")
};

USTRUCT(BlueprintType)
struct VIBEMMOUIKIT_API FVibeMMOTargetingRectangle
{
	GENERATED_BODY()

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Targeting")
	FVector2D CenterPosition = FVector2D(960.0f, 540.0f);

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Targeting")
	FVector2D Size = FVector2D(180.0f, 120.0f);

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Targeting")
	FText Label;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Targeting")
	FText Detail;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Targeting")
	FLinearColor AccentColor = FLinearColor(0.72f, 0.94f, 1.0f, 0.82f);

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Targeting")
	bool bLocked = false;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Targeting")
	bool bVisible = true;
};

UCLASS(Blueprintable)
class VIBEMMOUIKIT_API UVibeMMOHUDWidget : public UVibeMMOBaseWidget
{
	GENERATED_BODY()

public:
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Vibe MMO UI|HUD")
	bool bBuildDefaultHUDInCpp;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Vibe MMO UI|HUD", meta = (ExposeOnSpawn = true))
	TObjectPtr<UVibeMMOHUDLayoutDataAsset> HUDLayoutDataAsset;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Vibe MMO UI|Mock Data")
	bool bUseMockValues;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Vibe MMO UI|Mock Data")
	int32 MockShieldValue;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Vibe MMO UI|Mock Data")
	int32 MockHealthValue;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Vibe MMO UI|Mock Data")
	int32 MockResourceValue;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Vibe MMO UI|Mock Data")
	int32 MockLevelValue;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Vibe MMO UI|Mock Data")
	bool bUseMockTargetingRectangles;

	UPROPERTY(BlueprintReadOnly, meta = (BindWidgetOptional), Category = "Vibe MMO UI|HUD Text")
	TObjectPtr<UTextBlock> ShieldValueText;

	UPROPERTY(BlueprintReadOnly, meta = (BindWidgetOptional), Category = "Vibe MMO UI|HUD Text")
	TObjectPtr<UTextBlock> HealthValueText;

	UPROPERTY(BlueprintReadOnly, meta = (BindWidgetOptional), Category = "Vibe MMO UI|HUD Text")
	TObjectPtr<UTextBlock> ResourceValueText;

	UPROPERTY(BlueprintReadOnly, meta = (BindWidgetOptional), Category = "Vibe MMO UI|HUD Text")
	TObjectPtr<UTextBlock> LevelBadgeText;

	UPROPERTY(BlueprintReadOnly, meta = (BindWidgetOptional), Category = "Vibe MMO UI|HUD Text")
	TObjectPtr<UTextBlock> CompassHeadingText;

	UPROPERTY(BlueprintReadOnly, meta = (BindWidgetOptional), Category = "Vibe MMO UI|HUD Text")
	TObjectPtr<UTextBlock> AbilityKeyQText;

	UPROPERTY(BlueprintReadOnly, meta = (BindWidgetOptional), Category = "Vibe MMO UI|HUD Text")
	TObjectPtr<UTextBlock> AbilityKeyEText;

	UPROPERTY(BlueprintReadOnly, meta = (BindWidgetOptional), Category = "Vibe MMO UI|HUD Text")
	TObjectPtr<UTextBlock> AbilityKeyRText;

	UPROPERTY(BlueprintReadOnly, meta = (BindWidgetOptional), Category = "Vibe MMO UI|HUD Text")
	TObjectPtr<UTextBlock> AbilityKeyFText;

	UPROPERTY(BlueprintReadOnly, meta = (BindWidgetOptional), Category = "Vibe MMO UI|HUD Text")
	TObjectPtr<UTextBlock> AbilityKeyXText;

	UPROPERTY(BlueprintReadOnly, meta = (BindWidgetOptional), Category = "Vibe MMO UI|HUD Text")
	TObjectPtr<UTextBlock> WeaponSlot1Text;

	UPROPERTY(BlueprintReadOnly, meta = (BindWidgetOptional), Category = "Vibe MMO UI|HUD Text")
	TObjectPtr<UTextBlock> WeaponSlot2Text;

	UVibeMMOHUDWidget();

	UFUNCTION(BlueprintCallable, Category = "Vibe MMO UI|HUD")
	void SetStatusValues(int32 ShieldValue, int32 HealthValue, int32 ResourceValue);

	/** Live status: drains shield/health/fuel bars by fraction (turns off mock). Numbers are visual-only off. */
	UFUNCTION(BlueprintCallable, Category = "Vibe MMO UI|HUD")
	void SetLiveStatus(int32 ShieldValue, int32 HealthValue, float ShieldFrac, float HealthFrac, float FuelFrac = 1.0f);

	/** Show/hide ability bar slots (0..4). Hidden slots leave empty loadout space. */
	UFUNCTION(BlueprintCallable, Category = "Vibe MMO UI|HUD|Icons")
	void SetAbilitySlotVisible(int32 AbilityIndex, bool bVisible);

	/** Clear icon + hide fallback for a slot (empty loadout cell). */
	UFUNCTION(BlueprintCallable, Category = "Vibe MMO UI|HUD|Icons")
	void ClearAbilitySlot(int32 AbilityIndex);

	/** Remaining/duration drives the visible cooldown rail and numeric countdown for Q/E. */
	UFUNCTION(BlueprintCallable, Category = "Vibe MMO UI|HUD|Abilities")
	void SetAbilityCooldownState(int32 AbilityIndex, float RemainingSeconds, float DurationSeconds);

	/** Native full-screen Tab overlay. Today it intentionally supports only swapping Grapple/Slam. */
	UFUNCTION(BlueprintCallable, Category = "Vibe MMO UI|HUD|Abilities")
	void SetAbilityLoadoutOverlayVisible(bool bVisible, bool bQIsGrapple);

	UPROPERTY(BlueprintAssignable, Category = "Vibe MMO UI|HUD|Abilities")
	FVibeMMOAbilityLoadoutSwapRequested OnAbilityLoadoutSwapRequested;

	/** Collapse the cardinal compass labels (declutter the top of the screen). */
	UFUNCTION(BlueprintCallable, Category = "Vibe MMO UI|HUD")
	void HideCompass();

	UFUNCTION(BlueprintCallable, Category = "Vibe MMO UI|HUD")
	void SetAbilityKeyLabels(FText QLabel, FText ELabel, FText RLabel, FText FLabel, FText XLabel);

	UFUNCTION(BlueprintCallable, Category = "Vibe MMO UI|HUD")
	void SetWeaponSlotLabels(FText Slot1Label, FText Slot2Label);

	UFUNCTION(BlueprintCallable, Category = "Vibe MMO UI|HUD")
	void SetCompassHeadingDegrees(float HeadingDegrees);

	/** Mined-resource tally: writes a compact "S# I# C#" string into the resource readout. */
	UFUNCTION(BlueprintCallable, Category = "Vibe MMO UI|HUD")
	void SetResourceTally(int32 StoneCount, int32 IronCount, int32 CrystalCount);

	UFUNCTION(BlueprintCallable, Category = "Vibe MMO UI|HUD")
	void SetHUDLayoutDataAsset(UVibeMMOHUDLayoutDataAsset* InHUDLayoutDataAsset);

	UFUNCTION(BlueprintCallable, Category = "Vibe MMO UI|HUD")
	void RebuildDefaultHUDLayout();

	/** Current per-local-player sparse layout overrides. */
	UFUNCTION(BlueprintPure, Category = "Vibe MMO UI|HUD Layout")
	FVibeMMOHUDLayoutProfile GetHUDLayoutProfile() const;

	/** Replace the live preview profile. Use SaveHUDLayout after the user presses Apply. */
	UFUNCTION(BlueprintCallable, Category = "Vibe MMO UI|HUD Layout")
	bool SetHUDLayoutProfile(const FVibeMMOHUDLayoutProfile& Profile);

	UFUNCTION(BlueprintPure, Category = "Vibe MMO UI|HUD Layout")
	FVibeMMOHUDElementLayout GetHUDElementLayout(EVibeMMOHUDElement Element) const;

	/** Move an unlocked element by a normalized safe-area delta. */
	UFUNCTION(BlueprintCallable, Category = "Vibe MMO UI|HUD Layout")
	bool NudgeHUDElement(EVibeMMOHUDElement Element, FVector2D NormalizedDelta);

	/** Uniform resize, clamped by the persistence schema. */
	UFUNCTION(BlueprintCallable, Category = "Vibe MMO UI|HUD Layout")
	bool SetHUDElementScale(EVibeMMOHUDElement Element, float NewScale);

	/** Independent per-element opacity. */
	UFUNCTION(BlueprintCallable, Category = "Vibe MMO UI|HUD Layout")
	bool SetHUDElementOpacity(EVibeMMOHUDElement Element, float NewOpacity);

	UFUNCTION(BlueprintCallable, Category = "Vibe MMO UI|HUD Layout")
	bool SetHUDElementHidden(EVibeMMOHUDElement Element, bool bHidden);

	UFUNCTION(BlueprintCallable, Category = "Vibe MMO UI|HUD Layout")
	bool SetHUDElementLocked(EVibeMMOHUDElement Element, bool bLocked);

	UFUNCTION(BlueprintCallable, Category = "Vibe MMO UI|HUD Layout")
	bool ResetHUDElement(EVibeMMOHUDElement Element);

	UFUNCTION(BlueprintCallable, Category = "Vibe MMO UI|HUD Layout")
	bool ResetAllHUDElements();

	/** Persist the previewed profile to the owning local player's versioned save slot. */
	UFUNCTION(BlueprintCallable, Category = "Vibe MMO UI|HUD Layout")
	bool SaveHUDLayout();

	UFUNCTION(BlueprintCallable, Category = "Vibe MMO UI|HUD|Portrait")
	void SetPortraitResource(UObject* PortraitResource);

	UFUNCTION(BlueprintCallable, Category = "Vibe MMO UI|HUD|Icons")
	void SetAbilityIconResource(int32 AbilityIndex, UObject* IconResource);

	/** Short semantic label kept visible inside each active Q/E combat card. */
	UFUNCTION(BlueprintCallable, Category = "Vibe MMO UI|HUD|Icons")
	void SetAbilitySlotLabel(int32 AbilityIndex, FText Label);

	UFUNCTION(BlueprintCallable, Category = "Vibe MMO UI|HUD|Icons")
	void SetWeaponIconResource(int32 WeaponIndex, UObject* IconResource);

	/** Highlight the ACTIVE weapon slot: full color + full size; the other slot dims and shrinks. */
	UFUNCTION(BlueprintCallable, Category = "Vibe MMO UI|HUD|Icons")
	void SetSelectedWeaponSlot(int32 WeaponIndex);

	/** Apply a semantic rarity color to a weapon card's background and frame. */
	UFUNCTION(BlueprintCallable, Category = "Vibe MMO UI|HUD|Weapons")
	void SetWeaponSlotRarity(int32 WeaponIndex, EVibeMMOItemRarity Rarity);

	/** Smooth active-slot heat rail plus cooling/overheat frame state. Heat never appears at the reticle. */
	UFUNCTION(BlueprintCallable, Category = "Vibe MMO UI|HUD|Weapons")
	void SetWeaponHeatState(int32 WeaponIndex, float HeatFraction, bool bOverheated, bool bCooling);

	/** Drives the selected Ultimate Stylized UI Crosshair Pack sight's target-lock reaction. */
	UFUNCTION(BlueprintCallable, Category = "Vibe MMO UI|HUD|Targeting")
	void SetReticleTargetAlpha(float TargetAlpha);

	/** Set the minimap background (typically a UTextureRenderTarget2D from a top-down SceneCapture). */
	UFUNCTION(BlueprintCallable, Category = "Vibe MMO UI|HUD|Minimap")
	void SetMinimapResource(UObject* MinimapResource);

	UFUNCTION(BlueprintCallable, Category = "Vibe MMO UI|HUD|Minimap")
	void SetMinimapMode(EVibeMMOMinimapMode NewMode);

	/** Position red hostile blips on the surface minimap. Offsets are in minimap PIXELS from the
	 *  map center, already rotated into map space by the game (map-up = player forward). Blips
	 *  beyond the map radius clamp to the rim as direction hints; extra pool blips hide. */
	UFUNCTION(BlueprintCallable, Category = "Vibe MMO UI|HUD|Minimap")
	void SetMinimapBlips(const TArray<FVector2D>& OffsetsPx);

	UFUNCTION(BlueprintCallable, Category = "Vibe MMO UI|HUD|Targeting")
	void SetTargetingRectangles(const TArray<FVibeMMOTargetingRectangle>& InRectangles);

	UFUNCTION(BlueprintCallable, Category = "Vibe MMO UI|HUD|Targeting")
	void AddTargetingRectangle(const FVibeMMOTargetingRectangle& InRectangle);

	UFUNCTION(BlueprintCallable, Category = "Vibe MMO UI|HUD|Targeting")
	void ClearTargetingRectangles();

	virtual void ApplyVibeStyle_Implementation() override;

protected:
	virtual void NativePreConstruct() override;
	virtual void NativeConstruct() override;
	virtual void NativeDestruct() override;
	virtual void NativeTick(const FGeometry& MyGeometry, float InDeltaTime) override;

private:
	UPROPERTY(Transient)
	bool bDefaultHUDTreeBuilt;

	UPROPERTY(Transient)
	TObjectPtr<UVibeMMOHUDLayoutSubsystem> HUDLayoutSubsystem;

	UPROPERTY(Transient)
	FVibeMMOHUDLayoutProfile RuntimeHUDLayoutProfile;

	UPROPERTY(Transient)
	TMap<EVibeMMOHUDElement, TObjectPtr<UWidget>> HUDElementWidgets;

	UPROPERTY(Transient)
	TMap<EVibeMMOHUDElement, FVibeMMOHUDAnchorSlot> HUDElementBaselineSlots;

	UPROPERTY(Transient)
	TArray<TObjectPtr<UBorder>> StyledColorBlocks;

	UPROPERTY(Transient)
	TObjectPtr<UImage> PortraitImage;

	UPROPERTY(Transient)
	TObjectPtr<UTextBlock> PortraitFallbackText;

	UPROPERTY(Transient)
	TArray<TObjectPtr<UImage>> AbilityIconImages;

	UPROPERTY(Transient)
	TArray<TObjectPtr<UTextBlock>> AbilityIconFallbackTexts;

	UPROPERTY(Transient)
	TArray<TObjectPtr<UTextBlock>> AbilityNameTexts;

	UPROPERTY(Transient)
	TArray<TObjectPtr<UProgressBar>> AbilityCooldownBars;

	UPROPERTY(Transient)
	TArray<TObjectPtr<UTextBlock>> AbilityCooldownTexts;

	UPROPERTY(Transient)
	TObjectPtr<UOverlay> AbilityLoadoutOverlay;

	UPROPERTY(Transient)
	TObjectPtr<UTextBlock> AbilityLoadoutQAssignmentText;

	UPROPERTY(Transient)
	TObjectPtr<UTextBlock> AbilityLoadoutEAssignmentText;

	UPROPERTY(Transient)
	TObjectPtr<UImage> MinimapImage;

	UPROPERTY(Transient)
	TObjectPtr<UImage> MinimapBaseImage;

	UPROPERTY(Transient)
	TObjectPtr<UCanvasPanel> MinimapSurfaceLayer;

	UPROPERTY(Transient)
	TArray<TObjectPtr<UBorder>> MinimapBlipPool;

	UPROPERTY(Transient)
	TObjectPtr<UCanvasPanel> MinimapSpaceLayer;

	/** Dynamic, range-clamped ore/site/craft contacts used only by the compact orbit radar. */
	UPROPERTY(Transient)
	TArray<TObjectPtr<UBorder>> SpaceMinimapMarkerPool;

	UPROPERTY(Transient)
	TObjectPtr<UTextBlock> SpaceMinimapHeadingText;

	UPROPERTY(Transient)
	TObjectPtr<UTextBlock> SpaceMinimapNearestText;

	UPROPERTY(Transient)
	EVibeMMOMinimapMode MinimapMode;

	UPROPERTY(Transient)
	TArray<TObjectPtr<UImage>> WeaponIconImages;

	UPROPERTY(Transient)
	TArray<TObjectPtr<UTextBlock>> WeaponIconFallbackTexts;

	UPROPERTY(Transient)
	TArray<TObjectPtr<UOverlay>> WeaponSlotRoots;

	UPROPERTY(Transient)
	TArray<TObjectPtr<UBorder>> WeaponRarityBorders;

	UPROPERTY(Transient)
	TArray<TObjectPtr<UBorder>> WeaponRarityBackgrounds;

	UPROPERTY(Transient)
	TArray<TObjectPtr<UBorder>> WeaponStateFrames;

	UPROPERTY(Transient)
	TArray<TObjectPtr<UProgressBar>> WeaponHeatBars;

	UPROPERTY(Transient)
	TArray<EVibeMMOItemRarity> WeaponSlotRarities;

	UPROPERTY(Transient)
	TObjectPtr<UBorder> ShieldBarBlock;

	/** 10 shield pip segments (10 HP each when MaxShield=100). */
	UPROPERTY(Transient)
	TArray<TObjectPtr<UBorder>> ShieldSegmentBlocks;

	UPROPERTY(Transient)
	TObjectPtr<UBorder> HealthBarBlock;

	/** Yellow jetpack fuel / sprint stamina bar. */
	UPROPERTY(Transient)
	TObjectPtr<UBorder> FuelBarBlock;

	/** Root widget per ability slot (VerticalBox stack) for show/hide. */
	UPROPERTY(Transient)
	TArray<TObjectPtr<UWidget>> AbilitySlotRoots;

	UPROPERTY(Transient)
	TObjectPtr<UBorder> ResourceBarBlock;

	UPROPERTY(Transient)
	TArray<TObjectPtr<UTextBlock>> CompassLabelTexts;

	UPROPERTY(Transient)
	float DisplayedCompassHeadingDegrees = 0.0f;

	UPROPERTY(Transient)
	float TargetCompassHeadingDegrees = 0.0f;

	UPROPERTY(Transient)
	bool bCompassHeadingInitialized = false;

	UPROPERTY(Transient)
	TObjectPtr<UCanvasPanel> TargetingCanvas;

	/** Live pack-authored design 38 (open concentric ring + precise center point). */
	UPROPERTY(Transient)
	TObjectPtr<UImage> ReticleImage;

	/** Runtime copy used only to blend the pack's three color channels during target lock. */
	UPROPERTY(Transient)
	TObjectPtr<UMaterialInstanceDynamic> ReticleDynamicMaterial;

	UPROPERTY(Transient)
	TArray<FVibeMMOTargetingRectangle> ActiveTargetingRectangles;

	UPROPERTY(Transient)
	TArray<TObjectPtr<UWidget>> TargetingRectangleWidgets;

	UPROPERTY(Transient)
	bool bTargetingRectanglesOverridden = false;

	TSharedPtr<FSlateDynamicImageBrush> RuntimePortraitBrush;
	TSharedPtr<FSlateDynamicImageBrush> RuntimeMinimapBrush;
	bool bHasRuntimeMinimapResource = false;
	int32 SelectedWeaponSlot = 0;
	TArray<float> TargetWeaponHeatRatios;
	TArray<float> DisplayedWeaponHeatRatios;
	TArray<uint8> WeaponOverheatedStates;
	TArray<uint8> WeaponCoolingStates;
	float TargetReticleAlpha = 0.0f;
	float DisplayedReticleAlpha = 0.0f;
	float SpaceMinimapRefreshAccumulator = 0.0f;

	void BuildDefaultHUDTree();
	void RegisterHUDElement(EVibeMMOHUDElement Element, UWidget* Widget, const FVibeMMOHUDAnchorSlot& BaselineSlot);
	void ApplyHUDLayoutProfile();
	void ApplyHUDElementLayout(EVibeMMOHUDElement Element);
	FVector2D ResolveHUDSafeAreaSize() const;
	bool CommitHUDElementLayout(EVibeMMOHUDElement Element, const FVibeMMOHUDElementLayout& Layout);
	UFUNCTION()
	void HandleHUDLayoutChanged();
	const UVibeMMOHUDLayoutDataAsset* GetResolvedHUDLayoutDataAsset() const;
	void ApplyBrushResource(UImage* Image, UObject* Resource, const FVector2D& ImageSize) const;
	bool ApplyRuntimePngBrush(UImage* Image, const FString& AbsolutePath, const FVector2D& ImageSize, TSharedPtr<FSlateDynamicImageBrush>& BrushStorage);
	bool TryApplyGeneratedPortrait();
	bool TryApplyGeneratedMinimap();
	void AddStatusPanel(UCanvasPanel* RootCanvas);
	void AddCompass(UCanvasPanel* RootCanvas);
	void AddMinimap(UCanvasPanel* RootCanvas);
	void AddReticle(UCanvasPanel* RootCanvas);
	void AddTargetingLayer(UCanvasPanel* RootCanvas);
	void AddAbilityBar(UCanvasPanel* RootCanvas);
	void AddAbilityLoadoutOverlay(UCanvasPanel* RootCanvas);
	void AddWeaponSlots(UCanvasPanel* RootCanvas);
	void AddCanvasChild(UCanvasPanel* RootCanvas, UWidget* Child, const FAnchors& Anchors, const FVector2D& Alignment, const FVector2D& Position, const FVector2D& Size) const;
	void RefreshCompassLabels();
	void RefreshMinimapModeVisuals();
	void RefreshSpaceMinimapNavigation();
	void RefreshWeaponSlotVisuals();
	FLinearColor ResolveWeaponRarityColor(EVibeMMOItemRarity Rarity) const;
	UTextBlock* MakeTextBlock(const FName Name, const FText Text, EVibeMMOUIFontRole Role);
	UBorder* MakeColorBlock(const FName Name, const FLinearColor Color, const FVector2D& MinSize, float CornerRadius = 6.0f);
	UOverlay* MakeFramedSlot(const FName Name, const FLinearColor FillColor, const FLinearColor BorderColor,
		const FVector2D& MinSize, UBorder** OutOuter = nullptr, UBorder** OutInner = nullptr);
	UOverlay* MakeTargetingRectangle(const FName Name, const FVibeMMOTargetingRectangle& Rectangle);
	void RebuildTargetingRectangles();
	void ApplyMockTargetingRectangles();
	void ApplyHUDTextRoles();
	void ApplyHUDColors();
	void ApplyMockTextValues();
	UFUNCTION()
	void HandleAbilityLoadoutSwapClicked();
};
