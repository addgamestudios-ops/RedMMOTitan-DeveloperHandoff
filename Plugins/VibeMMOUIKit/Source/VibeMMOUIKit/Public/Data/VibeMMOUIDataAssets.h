#pragma once

#include "CoreMinimal.h"
#include "Engine/DataAsset.h"
#include "InputCoreTypes.h"
#include "Layout/Margin.h"
#include "Widgets/Layout/Anchors.h"
#include "VibeMMOUIDataAssets.generated.h"

class UTexture2D;
class UTexture;

USTRUCT(BlueprintType)
struct VIBEMMOUIKIT_API FVibeMMOHUDAnchorSlot
{
	GENERATED_BODY()

	FVibeMMOHUDAnchorSlot();
	FVibeMMOHUDAnchorSlot(const FAnchors& InAnchors, const FVector2D& InAlignment, const FVector2D& InPosition, const FVector2D& InSize);

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Layout")
	FAnchors Anchors;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Layout")
	FVector2D Alignment;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Layout")
	FVector2D Position;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Layout")
	FVector2D Size;
};

UENUM(BlueprintType)
enum class EVibeMMOItemRarity : uint8
{
	Common,
	Uncommon,
	Rare,
	Epic,
	Legendary,
	Mythic
};

UENUM(BlueprintType)
enum class EVibeMMOAbilityType : uint8
{
	Active,
	Passive,
	Ultimate
};

UENUM(BlueprintType)
enum class EVibeMMOTalentNodeState : uint8
{
	Locked,
	Available,
	Selected
};

USTRUCT(BlueprintType)
struct VIBEMMOUIKIT_API FVibeMMOInputGlyphEntry
{
	GENERATED_BODY()

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Input")
	FKey InputKey;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Input")
	TSoftObjectPtr<UTexture2D> GlyphTexture;
};

UCLASS(BlueprintType)
class VIBEMMOUIKIT_API UVibeMMOHUDLayoutDataAsset : public UPrimaryDataAsset
{
	GENERATED_BODY()

public:
	UVibeMMOHUDLayoutDataAsset();

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "HUD")
	FMargin SafeZonePadding = FMargin(32.0f, 28.0f, 32.0f, 28.0f);

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "HUD|Layout")
	FVibeMMOHUDAnchorSlot StatusPanelSlot;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "HUD|Layout")
	FVibeMMOHUDAnchorSlot CompassSlot;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "HUD|Layout")
	FVibeMMOHUDAnchorSlot MinimapSlot;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "HUD|Layout")
	FVibeMMOHUDAnchorSlot ReticleSlot;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "HUD|Layout")
	FVibeMMOHUDAnchorSlot AbilityBarSlot;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "HUD|Layout")
	FVibeMMOHUDAnchorSlot WeaponStackSlot;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "HUD|Layout")
	float StatusBarWidth = 176.0f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "HUD|Layout")
	float StatusBarHeight = 32.0f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "HUD|Layout")
	float AbilitySlotSize = 74.0f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "HUD|Layout")
	float WeaponSlotSize = 92.0f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "HUD|Layout", meta = (ClampMin = "1"))
	int32 AbilitySlotsPerRow = 5;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "HUD")
	TArray<FText> DefaultAbilityKeyLabels;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "HUD")
	TArray<FText> DefaultWeaponSlotLabels;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "HUD|Portrait")
	TSoftObjectPtr<UTexture> DefaultPortraitTexture;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "HUD|Icons")
	TArray<TSoftObjectPtr<UTexture>> DefaultAbilityIconTextures;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "HUD|Icons")
	TArray<TSoftObjectPtr<UTexture>> DefaultWeaponIconTextures;
};

UCLASS(BlueprintType)
class VIBEMMOUIKIT_API UVibeMMOCharacterCreationDataAsset : public UPrimaryDataAsset
{
	GENERATED_BODY()

public:
	UVibeMMOCharacterCreationDataAsset();

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Character Creator")
	TArray<FText> FactionNames;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Character Creator")
	TArray<FText> RaceNames;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Character Creator")
	TArray<FText> BodyTypeLabels;
};

UCLASS(BlueprintType)
class VIBEMMOUIKIT_API UVibeMMOInventoryItemDataAsset : public UPrimaryDataAsset
{
	GENERATED_BODY()

public:
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Item")
	FText ItemName;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Item")
	FText Description;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Item")
	EVibeMMOItemRarity Rarity = EVibeMMOItemRarity::Common;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Item")
	TSoftObjectPtr<UTexture2D> IconTexture;
};

UCLASS(BlueprintType)
class VIBEMMOUIKIT_API UVibeMMOAbilityDataAsset : public UPrimaryDataAsset
{
	GENERATED_BODY()

public:
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Ability")
	FText AbilityName;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Ability")
	FText Description;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Ability")
	FText DefaultKeyLabel;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Ability")
	EVibeMMOAbilityType AbilityType = EVibeMMOAbilityType::Active;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Ability")
	TSoftObjectPtr<UTexture2D> IconTexture;
};

UCLASS(BlueprintType)
class VIBEMMOUIKIT_API UVibeMMOTalentNodeDataAsset : public UPrimaryDataAsset
{
	GENERATED_BODY()

public:
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Talent")
	FName NodeId;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Talent")
	FText TalentName;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Talent")
	FText Description;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Talent")
	TArray<FName> RequiredNodeIds;
};

UCLASS(BlueprintType)
class VIBEMMOUIKIT_API UVibeMMOCraftingRecipeDataAsset : public UPrimaryDataAsset
{
	GENERATED_BODY()

public:
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Crafting")
	FText RecipeName;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Crafting")
	TArray<TSoftObjectPtr<UVibeMMOInventoryItemDataAsset>> RequiredItems;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Crafting")
	TSoftObjectPtr<UVibeMMOInventoryItemDataAsset> OutputItem;
};

UCLASS(BlueprintType)
class VIBEMMOUIKIT_API UVibeMMOQuestDataAsset : public UPrimaryDataAsset
{
	GENERATED_BODY()

public:
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Quest")
	FText QuestTitle;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Quest")
	FText QuestBody;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Quest")
	TArray<FText> Objectives;
};

UCLASS(BlueprintType)
class VIBEMMOUIKIT_API UVibeMMOInputGlyphDataAsset : public UPrimaryDataAsset
{
	GENERATED_BODY()

public:
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Input")
	TArray<FVibeMMOInputGlyphEntry> Glyphs;
};
