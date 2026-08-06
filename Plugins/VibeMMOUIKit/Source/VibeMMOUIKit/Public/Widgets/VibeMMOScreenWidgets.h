#pragma once

#include "CoreMinimal.h"
#include "Components/Button.h"
#include "Widgets/Layout/Anchors.h"
#include "Widgets/VibeMMOBaseWidget.h"
#include "VibeMMOScreenWidgets.generated.h"

class UBorder;
class UCanvasPanel;
class UImage;
class UTextBlock;
class UWidget;
class UVibeMMOCharacterCreationDataAsset;

UENUM(BlueprintType)
enum class EVibeMMOInventoryCategory : uint8
{
	All,
	Weapons,
	Resources,
	Consumables
};

USTRUCT(BlueprintType)
struct VIBEMMOUIKIT_API FVibeMMOInventoryItemPresentation
{
	GENERATED_BODY()

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Vibe MMO UI|Inventory")
	bool bIsPopulated = false;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Vibe MMO UI|Inventory")
	EVibeMMOInventoryCategory Category = EVibeMMOInventoryCategory::Weapons;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Vibe MMO UI|Inventory")
	FText DisplayName;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Vibe MMO UI|Inventory")
	FText Rarity;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Vibe MMO UI|Inventory", meta = (MultiLine = true))
	FText Description;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Vibe MMO UI|Inventory")
	TObjectPtr<UObject> IconResource = nullptr;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Vibe MMO UI|Inventory")
	FLinearColor RarityColor = FLinearColor::White;
};

DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(
	FVibeMMOInventoryItemSelectedEvent, int32, StableItemIndex);

class UVibeMMOInventoryWidget;

/**
 * Native forwarding button used by the default inventory grid.  Its visual
 * position may change when a category is filtered, while StableItemIndex
 * always identifies the original inventory entry.
 */
UCLASS()
class VIBEMMOUIKIT_API UVibeMMOInventorySlotButton : public UButton
{
	GENERATED_BODY()

public:
	void InitializeInventorySlot(UVibeMMOInventoryWidget* InOwner, int32 InVisualSlotIndex);
	void SetStableItemIndex(int32 InStableItemIndex);

	UFUNCTION(BlueprintPure, Category = "Vibe MMO UI|Inventory")
	int32 GetStableItemIndex() const { return StableItemIndex; }

	UFUNCTION(BlueprintPure, Category = "Vibe MMO UI|Inventory")
	int32 GetVisualSlotIndex() const { return VisualSlotIndex; }

private:
	UFUNCTION()
	void HandleSlotClicked();

	TWeakObjectPtr<UVibeMMOInventoryWidget> InventoryOwner;
	int32 StableItemIndex = INDEX_NONE;
	int32 VisualSlotIndex = INDEX_NONE;
};

UCLASS(Blueprintable)
class VIBEMMOUIKIT_API UVibeMMOMainMenuWidget : public UVibeMMOBaseWidget
{
	GENERATED_BODY()

public:
	UVibeMMOMainMenuWidget();

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Vibe MMO UI|Menu")
	bool bBuildDefaultMenuInCpp;

	UPROPERTY(BlueprintReadOnly, meta = (BindWidgetOptional), Category = "Vibe MMO UI|Text")
	TObjectPtr<UTextBlock> TitleText;

	virtual void ApplyVibeStyle_Implementation() override;

protected:
	virtual void NativePreConstruct() override;

private:
	UPROPERTY(Transient)
	bool bDefaultMenuTreeBuilt = false;

	void BuildDefaultMenuTree();
};

UCLASS(Blueprintable)
class VIBEMMOUIKIT_API UVibeMMOServerSelectWidget : public UVibeMMOBaseWidget
{
	GENERATED_BODY()

public:
	UVibeMMOServerSelectWidget();

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Vibe MMO UI|Server Select")
	bool bBuildDefaultServerSelectInCpp;

	UPROPERTY(BlueprintReadOnly, meta = (BindWidgetOptional), Category = "Vibe MMO UI|Text")
	TObjectPtr<UTextBlock> TitleText;

	virtual void ApplyVibeStyle_Implementation() override;

protected:
	virtual void NativePreConstruct() override;

private:
	UPROPERTY(Transient)
	bool bDefaultServerTreeBuilt = false;

	void BuildDefaultServerSelectTree();
};

UCLASS(Blueprintable)
class VIBEMMOUIKIT_API UVibeMMOCharacterSelectWidget : public UVibeMMOBaseWidget
{
	GENERATED_BODY()

public:
	UVibeMMOCharacterSelectWidget();

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Vibe MMO UI|Character Select")
	bool bBuildDefaultCharacterSelectInCpp;

	UPROPERTY(BlueprintReadOnly, meta = (BindWidgetOptional), Category = "Vibe MMO UI|Text")
	TObjectPtr<UTextBlock> TitleText;

	UFUNCTION(BlueprintCallable, Category = "Vibe MMO UI|Character Select")
	void SetCharacterPreviewResource(int32 CharacterIndex, UObject* PreviewResource);

	virtual void ApplyVibeStyle_Implementation() override;

protected:
	virtual void NativePreConstruct() override;

private:
	UPROPERTY(Transient)
	bool bDefaultCharacterSelectTreeBuilt = false;

	UPROPERTY(Transient)
	TArray<TObjectPtr<UImage>> CharacterPreviewImages;

	void BuildDefaultCharacterSelectTree();
	void ApplyCharacterSelectTextRoles();
};

UCLASS(Blueprintable)
class VIBEMMOUIKIT_API UVibeMMOCharacterCreatorWidget : public UVibeMMOBaseWidget
{
	GENERATED_BODY()

public:
	UVibeMMOCharacterCreatorWidget();

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Vibe MMO UI|Character Creator")
	bool bBuildDefaultCharacterCreatorInCpp;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Vibe MMO UI|Character Creator", meta = (ExposeOnSpawn = true))
	TObjectPtr<UVibeMMOCharacterCreationDataAsset> CharacterCreatorDataAsset;

	UPROPERTY(BlueprintReadOnly, meta = (BindWidgetOptional), Category = "Vibe MMO UI|Text")
	TObjectPtr<UTextBlock> SectionHeaderText;

	UPROPERTY(BlueprintReadOnly, meta = (BindWidgetOptional), Category = "Vibe MMO UI|Text")
	TObjectPtr<UTextBlock> DescriptionText;

	UPROPERTY(BlueprintReadOnly, meta = (BindWidgetOptional), Category = "Vibe MMO UI|Character Creator")
	TObjectPtr<UImage> CharacterPreviewImage;

	UFUNCTION(BlueprintCallable, Category = "Vibe MMO UI|Character Creator")
	void SetCharacterPreviewResource(UObject* PreviewResource);

	virtual void ApplyVibeStyle_Implementation() override;

protected:
	virtual void NativePreConstruct() override;

private:
	UPROPERTY(Transient)
	bool bDefaultCharacterCreatorTreeBuilt = false;

	void BuildDefaultCharacterCreatorTree();
	void ApplyCharacterCreatorTextRoles();
};

UCLASS(Blueprintable)
class VIBEMMOUIKIT_API UVibeMMOInventoryWidget : public UVibeMMOBaseWidget
{
	GENERATED_BODY()

public:
	static constexpr int32 InventoryCapacity = 40;

	UVibeMMOInventoryWidget();

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Vibe MMO UI|Inventory")
	bool bBuildDefaultInventoryInCpp;

	UPROPERTY(BlueprintReadOnly, meta = (BindWidgetOptional), Category = "Vibe MMO UI|Text")
	TObjectPtr<UTextBlock> TitleText;

	UPROPERTY(BlueprintReadOnly, meta = (BindWidgetOptional), Category = "Vibe MMO UI|Text")
	TObjectPtr<UTextBlock> RarityLabelText;

	UPROPERTY(BlueprintReadOnly, meta = (BindWidgetOptional), Category = "Vibe MMO UI|Text")
	TObjectPtr<UTextBlock> ItemDescriptionText;

	UPROPERTY(BlueprintReadOnly, meta = (BindWidgetOptional), Category = "Vibe MMO UI|Text")
	TObjectPtr<UTextBlock> ItemNameText;

	UPROPERTY(BlueprintAssignable, Category = "Vibe MMO UI|Inventory")
	FVibeMMOInventoryItemSelectedEvent OnInventoryItemSelected;

	UFUNCTION(BlueprintCallable, Category = "Vibe MMO UI|Inventory")
	void SetInventoryItemResource(int32 ItemIndex, UObject* IconResource);

	/** Rebuilds the kit-native inventory tree when no WBP-authored tree exists. */
	UFUNCTION(BlueprintCallable, Category = "Vibe MMO UI|Inventory")
	void RebuildDefaultInventoryLayout();

	/** Supplies all visual data for one stable backend inventory index. */
	UFUNCTION(BlueprintCallable, Category = "Vibe MMO UI|Inventory")
	void SetInventoryItemPresentation(int32 StableItemIndex, const FVibeMMOInventoryItemPresentation& Presentation);

	UFUNCTION(BlueprintCallable, Category = "Vibe MMO UI|Inventory")
	void ClearInventoryItemPresentation(int32 StableItemIndex);

	UFUNCTION(BlueprintPure, Category = "Vibe MMO UI|Inventory")
	bool GetInventoryItemPresentation(int32 StableItemIndex, FVibeMMOInventoryItemPresentation& OutPresentation) const;

	UFUNCTION(BlueprintCallable, Category = "Vibe MMO UI|Inventory")
	void SetInventoryCategory(EVibeMMOInventoryCategory Category);

	UFUNCTION(BlueprintPure, Category = "Vibe MMO UI|Inventory")
	EVibeMMOInventoryCategory GetInventoryCategory() const { return ActiveCategory; }

	UFUNCTION(BlueprintCallable, Category = "Vibe MMO UI|Inventory")
	bool SelectInventoryItem(int32 StableItemIndex);

	UFUNCTION(BlueprintPure, Category = "Vibe MMO UI|Inventory")
	int32 GetSelectedInventoryItemIndex() const { return SelectedStableItemIndex; }

	UFUNCTION(BlueprintPure, Category = "Vibe MMO UI|Inventory")
	TArray<int32> GetVisibleInventoryItemIndices() const { return VisibleStableItemIndices; }

	virtual void ApplyVibeStyle_Implementation() override;

protected:
	virtual void NativePreConstruct() override;

private:
	UPROPERTY(Transient)
	bool bDefaultInventoryTreeBuilt = false;

	UPROPERTY(Transient)
	TArray<TObjectPtr<UImage>> InventoryItemImages;

	UPROPERTY(Transient)
	TArray<TObjectPtr<UTextBlock>> InventoryPlaceholderTexts;

	UPROPERTY(Transient)
	TArray<TObjectPtr<UVibeMMOInventorySlotButton>> InventorySlotButtons;

	UPROPERTY(Transient)
	TArray<TObjectPtr<UBorder>> InventorySlotBorders;

	UPROPERTY(Transient)
	TArray<TObjectPtr<UButton>> InventoryCategoryButtons;

	UPROPERTY(Transient)
	TArray<TObjectPtr<UTextBlock>> InventoryCategoryLabels;

	UPROPERTY(Transient)
	TArray<FVibeMMOInventoryItemPresentation> InventoryItems;

	UPROPERTY(Transient)
	TObjectPtr<UTextBlock> InventoryCountText;

	UPROPERTY(Transient)
	EVibeMMOInventoryCategory ActiveCategory = EVibeMMOInventoryCategory::All;

	UPROPERTY(Transient)
	int32 SelectedStableItemIndex = INDEX_NONE;

	TArray<int32> VisibleStableItemIndices;

	void BuildDefaultInventoryTree();
	void ApplyInventoryTextRoles();
	void RefreshInventorySlots();
	void RefreshInventoryDetails();
	void RefreshInventoryCategoryTabs();
	bool IsPresentationVisible(const FVibeMMOInventoryItemPresentation& Presentation) const;

	UFUNCTION()
	void HandleAllCategoryClicked();

	UFUNCTION()
	void HandleWeaponsCategoryClicked();

	UFUNCTION()
	void HandleResourcesCategoryClicked();

	UFUNCTION()
	void HandleConsumablesCategoryClicked();

	friend class UVibeMMOInventorySlotButton;
};

UCLASS(Blueprintable)
class VIBEMMOUIKIT_API UVibeMMOEquipmentWidget : public UVibeMMOBaseWidget
{
	GENERATED_BODY()

public:
	UVibeMMOEquipmentWidget();

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Vibe MMO UI|Equipment")
	bool bBuildDefaultEquipmentInCpp;

	UPROPERTY(BlueprintReadOnly, meta = (BindWidgetOptional), Category = "Vibe MMO UI|Text")
	TObjectPtr<UTextBlock> TitleText;

	UPROPERTY(BlueprintReadOnly, meta = (BindWidgetOptional), Category = "Vibe MMO UI|Equipment")
	TObjectPtr<UImage> CharacterPreviewImage;

	UFUNCTION(BlueprintCallable, Category = "Vibe MMO UI|Equipment")
	void SetCharacterPreviewResource(UObject* PreviewResource);

	UFUNCTION(BlueprintCallable, Category = "Vibe MMO UI|Equipment")
	void SetEquipmentSlotResource(int32 SlotIndex, UObject* IconResource);

	virtual void ApplyVibeStyle_Implementation() override;

protected:
	virtual void NativePreConstruct() override;

private:
	UPROPERTY(Transient)
	bool bDefaultEquipmentTreeBuilt = false;

	UPROPERTY(Transient)
	TArray<TObjectPtr<UImage>> EquipmentSlotImages;

	void BuildDefaultEquipmentTree();
	void ApplyEquipmentTextRoles();
};

UCLASS(Abstract, Blueprintable)
class VIBEMMOUIKIT_API UVibeMMOAbilityBarWidget : public UVibeMMOBaseWidget
{
	GENERATED_BODY()

public:
	UPROPERTY(BlueprintReadOnly, meta = (BindWidgetOptional), Category = "Vibe MMO UI|Text")
	TObjectPtr<UTextBlock> AbilityKeyQText;

	UPROPERTY(BlueprintReadOnly, meta = (BindWidgetOptional), Category = "Vibe MMO UI|Text")
	TObjectPtr<UTextBlock> AbilityKeyEText;

	UPROPERTY(BlueprintReadOnly, meta = (BindWidgetOptional), Category = "Vibe MMO UI|Text")
	TObjectPtr<UTextBlock> AbilityKeyRText;

	UPROPERTY(BlueprintReadOnly, meta = (BindWidgetOptional), Category = "Vibe MMO UI|Text")
	TObjectPtr<UTextBlock> AbilityKeyFText;

	UPROPERTY(BlueprintReadOnly, meta = (BindWidgetOptional), Category = "Vibe MMO UI|Text")
	TObjectPtr<UTextBlock> AbilityKeyXText;

	virtual void ApplyVibeStyle_Implementation() override;
};

UCLASS(Abstract, Blueprintable)
class VIBEMMOUIKIT_API UVibeMMOTalentTreeWidget : public UVibeMMOBaseWidget
{
	GENERATED_BODY()

public:
	UPROPERTY(BlueprintReadOnly, meta = (BindWidgetOptional), Category = "Vibe MMO UI|Text")
	TObjectPtr<UTextBlock> TitleText;

	UPROPERTY(BlueprintReadOnly, meta = (BindWidgetOptional), Category = "Vibe MMO UI|Text")
	TObjectPtr<UTextBlock> TalentTooltipText;

	virtual void ApplyVibeStyle_Implementation() override;
};

UCLASS(Abstract, Blueprintable)
class VIBEMMOUIKIT_API UVibeMMOCraftingWidget : public UVibeMMOBaseWidget
{
	GENERATED_BODY()

public:
	UPROPERTY(BlueprintReadOnly, meta = (BindWidgetOptional), Category = "Vibe MMO UI|Text")
	TObjectPtr<UTextBlock> SectionHeaderText;

	virtual void ApplyVibeStyle_Implementation() override;
};
