#pragma once

#include "CoreMinimal.h"
#include "VibeMMOHUDLayoutTypes.generated.h"

/** Stable identifiers for the independently customizable gameplay HUD groups. */
UENUM(BlueprintType)
enum class EVibeMMOHUDElement : uint8
{
	StatusPanel = 0 UMETA(DisplayName = "Status Panel"),
	Compass = 1 UMETA(DisplayName = "Compass"),
	Minimap = 2 UMETA(DisplayName = "Minimap"),
	Reticle = 3 UMETA(DisplayName = "Reticle"),
	AbilityBar = 4 UMETA(DisplayName = "Ability Bar"),
	WeaponStack = 5 UMETA(DisplayName = "Weapon Stack"),
	PartyPanel = 6 UMETA(DisplayName = "Party Panel"),
	EnemyPanel = 7 UMETA(DisplayName = "Enemy Panel"),
	UtilityBar = 8 UMETA(DisplayName = "Utility Bar"),
	Count = 9 UMETA(Hidden)
};

namespace VibeMMOHUDLayout
{
	inline constexpr float MinimumScale = 0.50f;
	inline constexpr float MaximumScale = 1.50f;
	inline constexpr float MinimumOpacity = 0.10f;
	inline constexpr float MaximumOpacity = 1.00f;
	inline constexpr float MaximumNormalizedOffset = 1.00f;

	VIBEMMOUIKIT_API bool IsValidElement(EVibeMMOHUDElement Element);
	VIBEMMOUIKIT_API const TArray<EVibeMMOHUDElement>& GetElements();
}

/**
 * A player-authored delta layered over the immutable HUD layout data asset.
 * NormalizedOffset is measured against the resolved safe-area size, which keeps a
 * moved element in the same relative place when resolution or DPI scale changes.
 */
USTRUCT(BlueprintType)
struct VIBEMMOUIKIT_API FVibeMMOHUDElementLayout
{
	GENERATED_BODY()

	UPROPERTY(EditAnywhere, BlueprintReadWrite, SaveGame, Category = "HUD Layout")
	FVector2D NormalizedOffset = FVector2D::ZeroVector;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, SaveGame, Category = "HUD Layout",
		meta = (ClampMin = "0.50", ClampMax = "1.50"))
	float Scale = 1.0f;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, SaveGame, Category = "HUD Layout",
		meta = (ClampMin = "0.10", ClampMax = "1.00"))
	float Opacity = 1.0f;

	/** Prevents accidental move/scale operations while customization mode is active. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, SaveGame, Category = "HUD Layout")
	bool bLocked = false;

	/** Hidden elements remain discoverable and resettable from the customization UI. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, SaveGame, Category = "HUD Layout")
	bool bHidden = false;

	/** Repairs non-finite and out-of-range data loaded from disk or supplied by Blueprint. */
	void Sanitize();

	/** True when this value contributes no delta to the authored HUD baseline. */
	bool IsDefault() const;

	bool NearlyEquals(const FVibeMMOHUDElementLayout& Other) const;
};

/** Sparse set of per-element deltas. Default-valued entries are removed automatically. */
USTRUCT(BlueprintType)
struct VIBEMMOUIKIT_API FVibeMMOHUDLayoutProfile
{
	GENERATED_BODY()

	UPROPERTY(EditAnywhere, BlueprintReadOnly, SaveGame, Category = "HUD Layout")
	TMap<EVibeMMOHUDElement, FVibeMMOHUDElementLayout> ElementOverrides;

	FVibeMMOHUDElementLayout GetElementLayout(EVibeMMOHUDElement Element) const;
	bool HasElementOverride(EVibeMMOHUDElement Element) const;
	void SetElementLayout(EVibeMMOHUDElement Element, const FVibeMMOHUDElementLayout& Layout);
	void ResetElement(EVibeMMOHUDElement Element);
	void ResetToDefault();
	void Sanitize();
	bool NearlyEquals(const FVibeMMOHUDLayoutProfile& Other) const;
};
