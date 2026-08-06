#pragma once

#include "CoreMinimal.h"
#include "Blueprint/UserWidget.h"
#include "Data/VibeMMOHUDLayoutTypes.h"
#include "Widgets/VibeMMOScreenWidgets.h"
#include "RedPauseMenuWidget.generated.h"

class ARedHUD;
class ARedPlayerCharacter;
class APlayerController;
class UButton;
class UTextBlock;
class UWidget;
class UWidgetSwitcher;
class URedHUDWidget;
class UVibeMMOHUDLayoutSubsystem;

/** Makes the kit inventory's C++ default tree available without requiring a
 * throwaway Blueprint wrapper asset. */
UCLASS()
class REDMMO_API URedEmbeddedInventoryWidget : public UVibeMMOInventoryWidget
{
	GENERATED_BODY()

public:
	/** Project-owned quantity strip for the three replicated mining resources. */
	void SetResourceTotals(int32 Stone, int32 Iron, int32 Crystal);
	bool GetResourceTotals(
		int32& OutStone, int32& OutIron, int32& OutCrystal,
		FString& OutSummary) const;
	bool FocusControllerCategory(int32 CategoryIndex, APlayerController* PlayerController);
	bool ActivateControllerCategory(int32 CategoryIndex);
	bool FocusControllerVisibleSlot(int32 VisualSlotIndex, APlayerController* PlayerController);
	bool ActivateControllerVisibleSlot(int32 VisualSlotIndex);
	FName GetControllerCategoryWidgetName(int32 CategoryIndex) const;
	FName GetControllerVisibleSlotWidgetName(int32 VisualSlotIndex) const;

protected:
	virtual TSharedRef<SWidget> RebuildWidget() override;

private:
	UPROPERTY(Transient)
	TObjectPtr<UTextBlock> StoneQuantityText;

	UPROPERTY(Transient)
	TObjectPtr<UTextBlock> IronQuantityText;

	UPROPERTY(Transient)
	TObjectPtr<UTextBlock> CrystalQuantityText;

	int32 CachedStone = 0;
	int32 CachedIron = 0;
	int32 CachedCrystal = 0;

	void ApplyGridLabelPolish();
	void ApplyInventoryLayoutPolish();
	void BuildResourceLedger();
	void RefreshResourceLedger();
};

/**
 * Native, asset-independent in-game menu owned by ARedHUD.  Keeping it on the
 * HUD means Escape continues to work while the local controller possesses a
 * character, fighter, or shuttle.
 */
UCLASS()
class REDMMO_API URedPauseMenuWidget : public UUserWidget
{
	GENERATED_BODY()

public:
	URedPauseMenuWidget(const FObjectInitializer& ObjectInitializer);

	void InitializeForHUD(ARedHUD* InOwnerHUD);
	void PrepareForOpen();
	void SetResourceInventoryTotals(int32 Stone, int32 Iron, int32 Crystal);
	void FocusInitialControllerTarget(APlayerController* PlayerController);
	bool RouteControllerKey(const FKey& Key, bool bIsRepeat = false);
	bool GetControllerInventoryState(
		FString& OutRegion,
		int32& OutPrimaryIndex,
		int32& OutCategoryIndex,
		int32& OutVisualSlotIndex,
		int32& OutStableItemIndex,
		FString& OutFocusedWidget,
		bool& bOutHasUserFocus) const;

protected:
	virtual TSharedRef<SWidget> RebuildWidget() override;
	virtual void NativeOnInitialized() override;
	virtual void NativeConstruct() override;
	virtual FReply NativeOnPreviewKeyDown(
		const FGeometry& InGeometry, const FKeyEvent& InKeyEvent) override;
	virtual FReply NativeOnKeyDown(const FGeometry& InGeometry, const FKeyEvent& InKeyEvent) override;

private:
	enum class EControllerFocusRegion : uint8
	{
		PrimaryMenu,
		InventoryCategory,
		InventoryGrid
	};

	UPROPERTY(Transient)
	TObjectPtr<ARedHUD> OwnerHUD;

	UPROPERTY(Transient)
	TObjectPtr<UWidgetSwitcher> PageSwitcher;

	UPROPERTY(Transient)
	TObjectPtr<UTextBlock> SectionTitleText;

	UPROPERTY(Transient)
	TObjectPtr<UTextBlock> SessionStateText;

	UPROPERTY(Transient)
	TObjectPtr<UTextBlock> AbilityQText;

	UPROPERTY(Transient)
	TObjectPtr<UTextBlock> AbilityEText;

	UPROPERTY(Transient)
	TObjectPtr<UTextBlock> SkillsHelpText;

	UPROPERTY(Transient)
	TObjectPtr<UTextBlock> GraphicsStatusText;

	UPROPERTY(Transient)
	TObjectPtr<UTextBlock> HUDSelectedElementText;

	UPROPERTY(Transient)
	TObjectPtr<UTextBlock> HUDCustomizationStatusText;

	UPROPERTY(Transient)
	TObjectPtr<UTextBlock> ExitButtonText;

	UPROPERTY(Transient)
	TObjectPtr<UButton> CharacterButton;

	UPROPERTY(Transient)
	TObjectPtr<URedEmbeddedInventoryWidget> InventoryWidget;

	UPROPERTY(Transient)
	TArray<TObjectPtr<UButton>> PrimaryMenuButtons;

	UPROPERTY(Transient)
	TObjectPtr<UWidget> ControllerFocusedWidget;

	bool bMenuTreeBuilt = false;
	bool bExitArmed = false;
	bool bHUDCustomizationPreviewActive = false;
	bool bHUDResetAllArmed = false;
	EControllerFocusRegion ControllerFocusRegion =
		EControllerFocusRegion::PrimaryMenu;
	int32 ControllerPrimaryIndex = 0;
	int32 ControllerInventoryCategoryIndex = 0;
	int32 ControllerInventoryVisualSlotIndex = 0;
	EVibeMMOHUDElement SelectedHUDElement = EVibeMMOHUDElement::StatusPanel;
	FVibeMMOHUDLayoutProfile HUDCustomizationOriginalProfile;

	void BuildMenuTree();
	UWidget* BuildOverviewPage();
	UWidget* BuildSkillsPage();
	UWidget* BuildSettingsPage();
	UWidget* BuildHUDCustomizationPage();
	UButton* MakeMenuButton(const FString& Label, UTextBlock*& OutLabel, const FLinearColor& Tint);
	UTextBlock* MakeText(const FString& Text, int32 Size, const FLinearColor& Color, bool bWrap = false);
	void ShowPage(int32 PageIndex, const FString& PageTitle);
	void RefreshSessionState();
	void RefreshSkillsState();
	void RefreshGraphicsState();
	void RefreshCharacterControl();
	void RefreshInventoryResources();
	bool SetControllerFocus(UWidget* Target, APlayerController* PlayerController = nullptr);
	bool FocusControllerPrimary(int32 RequestedIndex);
	bool MoveControllerPrimary(int32 Direction);
	bool FocusControllerInventoryCategory(int32 RequestedIndex);
	bool FocusControllerInventorySlot(int32 RequestedVisualSlotIndex);
	bool ActivateControllerTarget();
	bool BeginHUDCustomizationPreview();
	void RefreshHUDCustomizationState(const FString& Feedback = FString());
	bool CancelHUDCustomizationPreview();
	URedHUDWidget* FindActiveReplacementHUD() const;
	UVibeMMOHUDLayoutSubsystem* FindHUDLayoutSubsystem() const;
	ARedPlayerCharacter* FindLocalPlayerCharacter() const;
	void DisarmExit();

	UFUNCTION()
	void HandleResume();

	UFUNCTION()
	void HandleOverview();

	UFUNCTION()
	void HandleMultiplayer();

	UFUNCTION()
	void HandleInventory();

	UFUNCTION()
	void HandleCharacter();

	UFUNCTION()
	void HandleSkills();

	UFUNCTION()
	void HandleSettings();

	UFUNCTION()
	void HandleHUDCustomization();

	UFUNCTION()
	void HandleHUDPreviousElement();

	UFUNCTION()
	void HandleHUDNextElement();

	UFUNCTION()
	void HandleHUDMoveLeft();

	UFUNCTION()
	void HandleHUDMoveRight();

	UFUNCTION()
	void HandleHUDMoveUp();

	UFUNCTION()
	void HandleHUDMoveDown();

	UFUNCTION()
	void HandleHUDScaleDown();

	UFUNCTION()
	void HandleHUDScaleUp();

	UFUNCTION()
	void HandleHUDOpacityDown();

	UFUNCTION()
	void HandleHUDOpacityUp();

	UFUNCTION()
	void HandleHUDToggleVisibility();

	UFUNCTION()
	void HandleHUDToggleLock();

	UFUNCTION()
	void HandleHUDResetElement();

	UFUNCTION()
	void HandleHUDResetAll();

	UFUNCTION()
	void HandleHUDApply();

	UFUNCTION()
	void HandleHUDCancel();

	UFUNCTION()
	void HandleOpenAbilityLoadout();

	UFUNCTION()
	void HandlePerformanceQuality();

	UFUNCTION()
	void HandleBalancedQuality();

	UFUNCTION()
	void HandleCinematicQuality();

	UFUNCTION()
	void HandleToggleWindowMode();

	UFUNCTION()
	void HandleExit();
};
