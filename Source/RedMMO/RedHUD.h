#pragma once

#include "CoreMinimal.h"
#include "GameFramework/HUD.h"
#include "RedHUD.generated.h"

/**
 * Lightweight bridge around the primary Vibe MMO UI: traces the aimed pawn,
 * forwards lock state to the purchased sight, draws enemy status bars, and
 * owns the native Steam session browser. It deliberately draws no legacy
 * square reticle or center-screen heat indicator.
 */
UCLASS()
class REDMMO_API ARedHUD : public AHUD
{
	GENERATED_BODY()

public:
	virtual void BeginPlay() override;
	virtual void DrawHUD() override;

	/** True when the supplied RED pixel-exact gameplay HUD was created locally. */
	bool HasPixelExactHUD() const;

	/** Active replacement widget used by the pause-menu layout customizer. */
	class URedHUDWidget* GetPixelExactHUDWidget() const;

	/** Temporarily hides the gameplay art while a full-screen legacy menu is open. */
	void SetPixelExactHUDVisible(bool bVisible);
	void RegisterLegacyCombatHUD(
		class ARedPlayerCharacter* SourceOwner,
		class UUserWidget* LegacyHUD);
	void UnregisterLegacyCombatHUD(
		class ARedPlayerCharacter* SourceOwner,
		class UUserWidget* ExpectedLegacyHUD);

	/** Primitive-only bridge used by gameplay code without exposing the HUD plugin state structs. */
	void UpdateReplacementHUDVitals(
		float Shield, float MaxShield, float Health, float MaxHealth, float Energy, float MaxEnergy);
	void UpdateReplacementHUDResources(int32 Stone, int32 Iron, int32 Crystal);
	bool QueryReplacementHUDResources(
		int32 ExpectedStone, int32 ExpectedIron, int32 ExpectedCrystal,
		FString& OutText, bool& bOutVisible) const;
	void ShowReplacementHUDMiningResult(uint8 ResourceType, int32 Amount);
	bool QueryReplacementHUDMiningResult(
		uint8 ExpectedResourceType, int32 ExpectedAmount,
		FString& OutText, bool& bOutVisible,
		float& OutSecondsRemaining) const;
	void UpdateReplacementHUDWeaponState(
		int32 WeaponIndex, float HeatPercent, bool bOverheated,
		float OverheatCooldownRemaining, bool bEquipped);
	void UpdateReplacementHUDAbilityState(
		int32 AbilityIndex, float CooldownRemaining, float CooldownDuration,
		bool bDisabled);
	void UpdateReplacementHUDCompass(float HeadingDegrees);
	void UpdateReplacementHUDMinimap(
		class ARedPlayerCharacter* SourceOwner,
		class UTexture* SurfaceTexture,
		FName CelestialFrameId,
		bool bSpaceMode);
	void ClearReplacementHUDMinimap(class ARedPlayerCharacter* SourceOwner);
	bool IsReplacementHUDMinimapActive(
		const class ARedPlayerCharacter* SourceOwner) const;

	/** Escape toggles this local menu from any possessed pawn or vehicle. */
	UFUNCTION(BlueprintCallable, Category = "Red|UI")
	void TogglePauseMenu();

	UFUNCTION(BlueprintCallable, Category = "Red|UI")
	void ClosePauseMenu();

	/** Closes Escape and opens the existing interactive Tab loadout when on foot. */
	bool OpenAbilityLoadoutFromPauseMenu();

	/** Closes Escape, unpauses standalone play, and opens the Steam host/join lobby. */
	bool OpenSessionBrowserFromPauseMenu();

	/** Opens or closes the Steam browser. F8 is runtime; PIE also accepts F6 because the editor owns F8. */
	UFUNCTION(Exec, BlueprintCallable, Category = "Red|Multiplayer")
	void ToggleSessionBrowser();

private:
	class URedSessionBrowserWidget* EnsureSessionBrowser();
	void ReconcileCombatHUDLayers();
	void ResetReplacementHUDMinimap();

	UPROPERTY(Transient)
	TObjectPtr<class URedSessionBrowserWidget> SessionBrowserWidget;

	UPROPERTY(Transient)
	TObjectPtr<class URedPauseMenuWidget> PauseMenuWidget;

	/** Exact supplied RED artwork. The legacy widget stays alive only as a data/menu backend. */
	UPROPERTY(Transient)
	TObjectPtr<class URedHUDWidget> PixelExactHUDWidget;

	/** Last discovered legacy combat tree; weak so vehicle possession cannot resurrect or retain it. */
	TWeakObjectPtr<class UUserWidget> CachedLegacyHUDWidget;

	/** Local-only source identity and monotonic ownership epoch for the live surface minimap. */
	TWeakObjectPtr<class ARedPlayerCharacter> MinimapSourceOwner;
	TWeakObjectPtr<class UTexture> MinimapSurfaceTexture;
	FName MinimapCelestialFrameId = NAME_None;
	int64 MinimapPresentationEpoch = 0;
	bool bMinimapSpaceMode = false;
	bool bHasMinimapPresentationMode = false;

	/** True only when this local standalone world was paused by Escape. */
	bool bPausedStandaloneForMenu = false;

	/** Eased 0..1 "aimed at a target" value so the reticle reacts smoothly. */
	float TargetAlpha = 0.f;
};
