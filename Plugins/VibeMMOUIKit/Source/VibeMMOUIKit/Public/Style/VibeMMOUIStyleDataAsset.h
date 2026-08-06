#pragma once

#include "CoreMinimal.h"
#include "Engine/DataAsset.h"
#include "Styling/SlateTypes.h"
#include "VibeMMOUIStyleDataAsset.generated.h"

UENUM(BlueprintType)
enum class EVibeMMOUIFontRole : uint8
{
	HUDNumber,
	AbilityKeybind,
	WeaponSlotNumber,
	LevelBadge,
	Heading,
	MainMenuTitle,
	CharacterCreatorSectionHeader,
	TalentTreeTitle,
	InventoryRarityLabel,
	ImportantLabel,
	CompanionBody,
	TooltipBody,
	QuestBody,
	SettingsBody
};

USTRUCT(BlueprintType)
struct VIBEMMOUIKIT_API FVibeMMOFontRoleSizes
{
	GENERATED_BODY()

	FVibeMMOFontRoleSizes();

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Hero")
	int32 HUDNumberSize;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Hero")
	int32 AbilityKeybindSize;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Hero")
	int32 WeaponSlotNumberSize;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Hero")
	int32 LevelBadgeSize;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Hero")
	int32 HeadingSize;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Hero")
	int32 MainMenuTitleSize;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Hero")
	int32 CharacterCreatorSectionHeaderSize;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Hero")
	int32 TalentTreeTitleSize;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Hero")
	int32 InventoryRarityLabelSize;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Hero")
	int32 ImportantLabelSize;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Companion")
	int32 CompanionBodySize;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Companion")
	int32 TooltipBodySize;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Companion")
	int32 QuestBodySize;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Companion")
	int32 SettingsBodySize;
};

USTRUCT(BlueprintType)
struct VIBEMMOUIKIT_API FVibeMMOTextTreatment
{
	GENERATED_BODY()

	FVibeMMOTextTreatment();

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Text")
	FLinearColor TextColor;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Text")
	int32 OutlineSize;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Text")
	FLinearColor OutlineColor;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Text")
	FVector2D ShadowOffset;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Text")
	FLinearColor ShadowColor;
};

UCLASS(BlueprintType)
class VIBEMMOUIKIT_API UVibeMMOUIStyleDataAsset : public UPrimaryDataAsset
{
	GENERATED_BODY()

public:
	UVibeMMOUIStyleDataAsset();

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Typography", meta = (DisplayName = "Primary Hero Font (assign Saira Black 900 Italic here)"))
	FSlateFontInfo PrimaryHeroFont;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Typography")
	FSlateFontInfo CompanionFont;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Typography")
	FVibeMMOFontRoleSizes FontRoleSizes;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Typography")
	FVibeMMOTextTreatment HeroTextTreatment;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Typography")
	FVibeMMOTextTreatment CompanionTextTreatment;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "HUD Colors")
	FLinearColor ShieldColor;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "HUD Colors")
	FLinearColor HealthColor;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "HUD Colors")
	FLinearColor EnergyColor;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Rarity Colors")
	FLinearColor CommonRarityColor;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Rarity Colors")
	FLinearColor UncommonRarityColor;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Rarity Colors")
	FLinearColor RareRarityColor;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Rarity Colors")
	FLinearColor EpicRarityColor;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Rarity Colors")
	FLinearColor LegendaryRarityColor;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Rarity Colors")
	FLinearColor MythicRarityColor;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Glassmorphism")
	FLinearColor GlassPanelTint;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Glassmorphism")
	FLinearColor GlassPanelBorderColor;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Glassmorphism")
	FLinearColor GlassHighlightColor;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Glassmorphism", meta = (ClampMin = "0.0", ClampMax = "100.0"))
	float GlassBlurStrength;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Glassmorphism", meta = (ClampMin = "0.0", ClampMax = "255.0"))
	int32 GlassBlurRadius;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Glassmorphism", meta = (ClampMin = "0.0"))
	float GlassCornerRadius;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Layout")
	FMargin HUDSafeZonePadding;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Layout")
	float AbilitySlotSize;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Layout")
	float WeaponSlotSize;

	UFUNCTION(BlueprintPure, Category = "Vibe MMO UI|Typography")
	FSlateFontInfo GetFontForRole(EVibeMMOUIFontRole Role) const;

	UFUNCTION(BlueprintPure, Category = "Vibe MMO UI|Typography")
	FTextBlockStyle GetTextBlockStyleForRole(EVibeMMOUIFontRole Role) const;

	UFUNCTION(BlueprintPure, Category = "Vibe MMO UI|Typography")
	bool IsHeroFontRole(EVibeMMOUIFontRole Role) const;

private:
	int32 GetSizeForRole(EVibeMMOUIFontRole Role) const;
	const FVibeMMOTextTreatment& GetTreatmentForRole(EVibeMMOUIFontRole Role) const;
};
