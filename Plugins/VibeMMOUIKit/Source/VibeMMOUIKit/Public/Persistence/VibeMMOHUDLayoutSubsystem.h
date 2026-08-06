#pragma once

#include "CoreMinimal.h"
#include "Data/VibeMMOHUDLayoutTypes.h"
#include "Subsystems/LocalPlayerSubsystem.h"
#include "VibeMMOHUDLayoutSubsystem.generated.h"

class UVibeMMOHUDLayoutSaveGame;

DECLARE_DYNAMIC_MULTICAST_DELEGATE(FVibeMMOHUDLayoutChanged);

/**
 * Per-local-player owner for the HUD layout profile. It survives pawn replacement
 * and map travel, while remote players and dedicated servers never share its state.
 */
UCLASS()
class VIBEMMOUIKIT_API UVibeMMOHUDLayoutSubsystem final : public ULocalPlayerSubsystem
{
	GENERATED_BODY()

public:
	virtual void Initialize(FSubsystemCollectionBase& Collection) override;
	virtual void Deinitialize() override;

	/** Synchronously loads the tiny profile, or creates a versioned default profile. */
	UFUNCTION(BlueprintCallable, Category = "Vibe MMO UI|HUD Layout")
	bool LoadOrCreateLayout();

	UFUNCTION(BlueprintPure, Category = "Vibe MMO UI|HUD Layout")
	bool IsLayoutLoaded() const;

	UFUNCTION(BlueprintPure, Category = "Vibe MMO UI|HUD Layout")
	bool IsLayoutDirty() const;

	/** False if a newer save schema was loaded and is being preserved read-only. */
	UFUNCTION(BlueprintPure, Category = "Vibe MMO UI|HUD Layout")
	bool IsLayoutWritable() const;

	UFUNCTION(BlueprintPure, Category = "Vibe MMO UI|HUD Layout")
	FString GetActiveSaveSlotName() const;

	UFUNCTION(BlueprintPure, Category = "Vibe MMO UI|HUD Layout")
	FVibeMMOHUDLayoutProfile GetLayoutProfile() const;

	UFUNCTION(BlueprintPure, Category = "Vibe MMO UI|HUD Layout")
	FVibeMMOHUDElementLayout GetElementLayout(EVibeMMOHUDElement Element) const;

	UFUNCTION(BlueprintCallable, Category = "Vibe MMO UI|HUD Layout")
	bool SetLayoutProfile(const FVibeMMOHUDLayoutProfile& Profile);

	UFUNCTION(BlueprintCallable, Category = "Vibe MMO UI|HUD Layout")
	bool SetElementLayout(EVibeMMOHUDElement Element, const FVibeMMOHUDElementLayout& Layout);

	UFUNCTION(BlueprintCallable, Category = "Vibe MMO UI|HUD Layout")
	bool ResetElementLayout(EVibeMMOHUDElement Element);

	UFUNCTION(BlueprintCallable, Category = "Vibe MMO UI|HUD Layout")
	bool ResetLayout();

	/** Commits the tiny profile synchronously; Apply/Done should call this explicitly. */
	UFUNCTION(BlueprintCallable, Category = "Vibe MMO UI|HUD Layout")
	bool SaveLayoutNow();

	/** Compatibility commit entrypoint; intentionally synchronous for shutdown safety. */
	UFUNCTION(BlueprintCallable, Category = "Vibe MMO UI|HUD Layout")
	bool SaveLayoutAsync();

	UPROPERTY(BlueprintAssignable, Category = "Vibe MMO UI|HUD Layout")
	FVibeMMOHUDLayoutChanged OnLayoutChanged;

	/** Builds an account slot when identity is ready, with a platform-user fallback. */
	static FString BuildSaveSlotName(const ULocalPlayer* LocalPlayer);

	/** Deterministic seam used by the runtime and automation tests. */
	static FString BuildSaveSlotNameForIdentity(
		const FString& BaseSlot,
		const FString& UserIdentity,
		int32 PlatformUserIndex);

private:
	UPROPERTY(Transient)
	TObjectPtr<UVibeMMOHUDLayoutSaveGame> CurrentSaveGame;

	bool bDirty = false;
	FString PendingFallbackSlotToDelete;
	int32 PendingFallbackPlatformUserIndex = INDEX_NONE;

	void MarkChanged();
	void HandleSaveCompleted(bool bSuccess);
};
