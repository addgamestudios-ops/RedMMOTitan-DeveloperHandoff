#pragma once

#include "CoreMinimal.h"
#include "Data/VibeMMOHUDLayoutTypes.h"
#include "GameFramework/SaveGame.h"
#include "VibeMMOHUDLayoutSaveGame.generated.h"

DECLARE_MULTICAST_DELEGATE_OneParam(FVibeMMOHUDLayoutSaveCompletedNative, bool /* bSuccess */);

/** Versioned, local-player-owned storage for sparse HUD layout overrides. */
UCLASS()
class VIBEMMOUIKIT_API UVibeMMOHUDLayoutSaveGame final : public ULocalPlayerSaveGame
{
	GENERATED_BODY()

public:
	static constexpr int32 LatestDataVersion = 1;
	// Keep the physical slot stable across schema versions. SavedDataVersion drives migration.
	static constexpr const TCHAR* DefaultSlotBase = TEXT("VibeMMOHUDLayout");

	virtual int32 GetLatestDataVersion() const override;
	virtual void ResetToDefault() override;
	virtual void HandlePostLoad() override;
	virtual void HandlePostSave(bool bSuccess) override;

	UFUNCTION(BlueprintPure, Category = "Vibe MMO UI|HUD Layout")
	FVibeMMOHUDLayoutProfile GetLayoutProfile() const;

	UFUNCTION(BlueprintCallable, Category = "Vibe MMO UI|HUD Layout")
	bool SetLayoutProfile(const FVibeMMOHUDLayoutProfile& InProfile);

	/** False when this runtime loaded a newer schema that must not be overwritten. */
	bool IsLoadedDataSupported() const;

	/** True when an older supported schema was upgraded and should be written back. */
	bool NeedsResaveAfterLoad() const;

	FVibeMMOHUDLayoutSaveCompletedNative OnSaveCompletedNative;

private:
	UPROPERTY(SaveGame)
	FVibeMMOHUDLayoutProfile LayoutProfile;

	bool bLoadedDataSupported = true;
	bool bNeedsResaveAfterLoad = false;
};
