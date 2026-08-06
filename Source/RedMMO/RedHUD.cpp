#include "RedHUD.h"
#include "RedPlayerCharacter.h"
#include "RedPauseMenuWidget.h"
#include "RedSessionBrowserWidget.h"
#include "RedHUDBlueprintLibrary.h"
#include "RedHUDWidget.h"
#include "Widgets/VibeMMOHUDWidget.h"
#include "Blueprint/UserWidget.h"
#include "Components/InputComponent.h"
#include "Engine/Canvas.h"
#include "Engine/Texture.h"
#include "Engine/World.h"
#include "GameFramework/PlayerController.h"
#include "InputCoreTypes.h"

void ARedHUD::BeginPlay()
{
	Super::BeginPlay();

	if (APlayerController* PlayerController = GetOwningPlayerController();
		PlayerController && PlayerController->IsLocalController())
	{
		PixelExactHUDWidget = URedHUDBlueprintLibrary::CreateAndAddRedHUD(
			PlayerController, 100);
		if (PixelExactHUDWidget)
		{
			// The supplied full composite is the literal pixel-approval view. No
			// generated, recolored, or reconstructed substitute is used here.
			PixelExactHUDWidget->SetInputScheme(ERedHUDInputScheme::KeyboardMouse);
            PixelExactHUDWidget->SetLiveDataMode(true);

			// BeginPlay order can vary between HUD and pawn. Hide an already-created
			// legacy combat tree, but keep it alive for the current loadout backend.
			if (ARedPlayerCharacter* Character = Cast<ARedPlayerCharacter>(PlayerController->GetPawn()))
			{
				UpdateReplacementHUDResources(
					Character->ResStone, Character->ResIron, Character->ResCrystal);
				if (UUserWidget* LegacyHUD = Character->GetActiveHUDWidget())
				{
					RegisterLegacyCombatHUD(Character, LegacyHUD);
					Character->RefreshReplacementHUDMinimapPresentation();
				}
			}
		}

		EnableInput(PlayerController);
		if (InputComponent)
		{
			InputComponent->BindKey(EKeys::Escape, IE_Pressed, this,
				&ARedHUD::TogglePauseMenu);
			InputComponent->BindKey(EKeys::Gamepad_Special_Right, IE_Pressed, this,
				&ARedHUD::TogglePauseMenu);
			InputComponent->BindKey(EKeys::F8, IE_Pressed, this,
				&ARedHUD::ToggleSessionBrowser);
#if WITH_EDITOR
			// Unreal Editor reserves F8 for Possess/Eject before gameplay receives the key.
			// Keep the requested F8 binding for packaged builds and provide an editor-only
			// fallback so multiplayer PIE can exercise the exact same native browser.
			InputComponent->BindKey(EKeys::F6, IE_Pressed, this,
				&ARedHUD::ToggleSessionBrowser);
#endif
		}
	}
}

bool ARedHUD::HasPixelExactHUD() const
{
	return IsValid(PixelExactHUDWidget);
}

URedHUDWidget* ARedHUD::GetPixelExactHUDWidget() const
{
	return IsValid(PixelExactHUDWidget) ? PixelExactHUDWidget.Get() : nullptr;
}

void ARedHUD::SetPixelExactHUDVisible(const bool bVisible)
{
	if (PixelExactHUDWidget)
	{
		// Clear target-specific data before either hiding or re-showing the root widget.
		// DrawHUD will republish a currently aimed enemy on the next visible frame.
		FRedHUDEnemyState HiddenEnemyState;
		HiddenEnemyState.bVisible = false;
		PixelExactHUDWidget->SetEnemyState(HiddenEnemyState);
		PixelExactHUDWidget->SetVisibility(
			bVisible ? ESlateVisibility::HitTestInvisible : ESlateVisibility::Collapsed);
		if (bVisible)
		{
			ReconcileCombatHUDLayers();
		}
	}
}

void ARedHUD::RegisterLegacyCombatHUD(
	ARedPlayerCharacter* SourceOwner,
	UUserWidget* LegacyHUD)
{
	if (!IsValid(SourceOwner) || !IsValid(LegacyHUD))
	{
		return;
	}
	if (CachedLegacyHUDWidget.Get() != LegacyHUD)
	{
		ResetReplacementHUDMinimap();
	}
	CachedLegacyHUDWidget = LegacyHUD;
	if (IsValid(LegacyHUD) && IsValid(PixelExactHUDWidget)
		&& PixelExactHUDWidget->GetVisibility() != ESlateVisibility::Collapsed)
	{
		LegacyHUD->SetVisibility(ESlateVisibility::Collapsed);
	}
}

void ARedHUD::UnregisterLegacyCombatHUD(
	ARedPlayerCharacter* SourceOwner,
	UUserWidget* ExpectedLegacyHUD)
{
	if (!IsValid(SourceOwner)
		|| !IsValid(ExpectedLegacyHUD)
		|| CachedLegacyHUDWidget.Get() != ExpectedLegacyHUD)
	{
		return;
	}

	ClearReplacementHUDMinimap(SourceOwner);
	CachedLegacyHUDWidget.Reset();
}

void ARedHUD::UpdateReplacementHUDVitals(
	const float Shield, const float MaxShield,
	const float Health, const float MaxHealth,
	const float Energy, const float MaxEnergy)
{
	if (!PixelExactHUDWidget)
	{
		return;
	}

	FRedHUDPlayerVitals State;
	State.Shield = Shield;
	State.MaxShield = MaxShield;
	State.Health = Health;
	State.MaxHealth = MaxHealth;
	State.Energy = Energy;
	State.MaxEnergy = MaxEnergy;
	PixelExactHUDWidget->SetPlayerVitals(State);
}

void ARedHUD::UpdateReplacementHUDResources(
	const int32 Stone, const int32 Iron, const int32 Crystal)
{
	if (PixelExactHUDWidget)
	{
		PixelExactHUDWidget->SetResourceTally(Stone, Iron, Crystal);
	}
	if (PauseMenuWidget)
	{
		PauseMenuWidget->SetResourceInventoryTotals(Stone, Iron, Crystal);
	}
}

bool ARedHUD::QueryReplacementHUDResources(
	const int32 ExpectedStone, const int32 ExpectedIron, const int32 ExpectedCrystal,
	FString& OutText, bool& bOutVisible) const
{
	OutText = TEXT("unavailable");
	bOutVisible = false;
	if (!PixelExactHUDWidget)
	{
		return false;
	}

	int32 Stone = 0;
	int32 Iron = 0;
	int32 Crystal = 0;
	if (!PixelExactHUDWidget->GetResourceTallyState(
		Stone, Iron, Crystal, OutText, bOutVisible))
	{
		return false;
	}
	return Stone == FMath::Max(0, ExpectedStone)
		&& Iron == FMath::Max(0, ExpectedIron)
		&& Crystal == FMath::Max(0, ExpectedCrystal)
		&& OutText.IsEmpty()
		&& !bOutVisible;
}

void ARedHUD::ShowReplacementHUDMiningResult(
	const uint8 ResourceType, const int32 Amount)
{
	if (!PixelExactHUDWidget || Amount <= 0)
	{
		return;
	}

	FText ResourceName;
	FLinearColor AccentColor;
	switch (ResourceType)
	{
	case 2:
		ResourceName = FText::FromString(TEXT("Crystal"));
		AccentColor = FLinearColor(0.55f, 0.28f, 1.0f, 1.0f);
		break;
	case 1:
		ResourceName = FText::FromString(TEXT("Iron"));
		AccentColor = FLinearColor(1.0f, 0.55f, 0.18f, 1.0f);
		break;
	case 0:
	default:
		ResourceName = FText::FromString(TEXT("Stone"));
		AccentColor = FLinearColor(0.72f, 0.76f, 0.84f, 1.0f);
		break;
	}
	PixelExactHUDWidget->ShowMiningResult(
		ResourceName,
		Amount,
		AccentColor);
}

bool ARedHUD::QueryReplacementHUDMiningResult(
	const uint8 ExpectedResourceType,
	const int32 ExpectedAmount,
	FString& OutText,
	bool& bOutVisible,
	float& OutSecondsRemaining) const
{
	OutText.Reset();
	bOutVisible = false;
	OutSecondsRemaining = 0.0f;
	if (!PixelExactHUDWidget)
	{
		return false;
	}
	if (!PixelExactHUDWidget->GetMiningResultState(
		OutText,
		bOutVisible,
		OutSecondsRemaining))
	{
		return false;
	}
	if (ExpectedAmount <= 0)
	{
		return OutText.IsEmpty()
			&& !bOutVisible
			&& OutSecondsRemaining <= 0.0f;
	}

	const TCHAR* ExpectedName = TEXT("STONE");
	switch (ExpectedResourceType)
	{
	case 2: ExpectedName = TEXT("CRYSTAL"); break;
	case 1: ExpectedName = TEXT("IRON"); break;
	case 0:
	default: break;
	}
	const FString ExpectedText = FString::Printf(
		TEXT("%s  +%d"),
		ExpectedName,
		FMath::Max(1, ExpectedAmount));
	return OutText == ExpectedText;
}

void ARedHUD::UpdateReplacementHUDWeaponState(
	const int32 WeaponIndex, const float HeatPercent, const bool bOverheated,
	const float OverheatCooldownRemaining, const bool bEquipped)
{
	if (!PixelExactHUDWidget)
	{
		return;
	}

	FRedHUDWeaponState State;
	State.HeatPercent = FMath::Clamp(HeatPercent, 0.f, 1.f);
	State.bOverheated = bOverheated;
	State.OverheatCooldownRemaining = FMath::Max(0.f, OverheatCooldownRemaining);
	State.bEquipped = bEquipped;
	PixelExactHUDWidget->SetWeaponState(WeaponIndex, State);
}

void ARedHUD::UpdateReplacementHUDAbilityState(
	const int32 AbilityIndex, const float CooldownRemaining,
	const float CooldownDuration, const bool bDisabled)
{
	if (!PixelExactHUDWidget)
	{
		return;
	}

	FRedHUDAbilityState State;
	State.CooldownDuration = FMath::Max(0.f, CooldownDuration);
	State.CooldownRemaining = FMath::Clamp(
		CooldownRemaining, 0.f, State.CooldownDuration);
	State.ChargePercent = 1.f;
	State.bReady = !bDisabled && State.CooldownRemaining <= KINDA_SMALL_NUMBER;
	State.bSelected = false;
	State.bDisabled = bDisabled;
	PixelExactHUDWidget->SetAbilityState(AbilityIndex, State);
}

void ARedHUD::UpdateReplacementHUDCompass(const float HeadingDegrees)
{
	if (PixelExactHUDWidget)
	{
		PixelExactHUDWidget->SetCompassHeadingDegrees(HeadingDegrees);
	}
}

void ARedHUD::UpdateReplacementHUDMinimap(
	ARedPlayerCharacter* SourceOwner,
	UTexture* SurfaceTexture,
	const FName CelestialFrameId,
	const bool bSpaceMode)
{
	APlayerController* PlayerController = GetOwningPlayerController();
	if (!IsValid(PixelExactHUDWidget)
		|| !IsValid(SourceOwner)
		|| !PlayerController
		|| !PlayerController->IsLocalController()
		|| CachedLegacyHUDWidget.Get() != SourceOwner->GetActiveHUDWidget())
	{
		return;
	}

	const FName EffectiveFrameId = bSpaceMode ? NAME_None : CelestialFrameId;
	const bool bSourceChanged = MinimapSourceOwner.Get() != SourceOwner;
	const bool bTextureChanged = MinimapSurfaceTexture.Get() != SurfaceTexture;
	const bool bFrameChanged = MinimapCelestialFrameId != EffectiveFrameId;
	const bool bModeChanged =
		!bHasMinimapPresentationMode || bMinimapSpaceMode != bSpaceMode;
	if (bSourceChanged || bTextureChanged || bFrameChanged || bModeChanged)
	{
		++MinimapPresentationEpoch;
	}
	MinimapSourceOwner = SourceOwner;
	MinimapSurfaceTexture = SurfaceTexture;
	MinimapCelestialFrameId = EffectiveFrameId;
	bMinimapSpaceMode = bSpaceMode;
	bHasMinimapPresentationMode = true;
	if (MinimapPresentationEpoch <= 0)
	{
		MinimapPresentationEpoch = 1;
	}

	const ERedHUDMinimapMode Mode = bSpaceMode
		? ERedHUDMinimapMode::Space
		: (!CelestialFrameId.IsNone() && IsValid(SurfaceTexture)
			? ERedHUDMinimapMode::Surface
			: ERedHUDMinimapMode::Absent);
	PixelExactHUDWidget->SetMinimapPresentation(
		SourceOwner,
		SurfaceTexture,
		CelestialFrameId,
		MinimapPresentationEpoch,
		Mode);
}

void ARedHUD::ClearReplacementHUDMinimap(ARedPlayerCharacter* SourceOwner)
{
	if (!IsValid(SourceOwner) || MinimapSourceOwner.Get() != SourceOwner)
	{
		return;
	}

	ResetReplacementHUDMinimap();
}

void ARedHUD::ResetReplacementHUDMinimap()
{
	++MinimapPresentationEpoch;
	if (PixelExactHUDWidget)
	{
		PixelExactHUDWidget->ResetMinimapPresentation(
			MinimapPresentationEpoch);
	}
	MinimapSourceOwner.Reset();
	MinimapSurfaceTexture.Reset();
	MinimapCelestialFrameId = NAME_None;
	bMinimapSpaceMode = false;
	bHasMinimapPresentationMode = false;
}

bool ARedHUD::IsReplacementHUDMinimapActive(
	const ARedPlayerCharacter* SourceOwner) const
{
	if (!IsValid(PixelExactHUDWidget)
		|| !IsValid(SourceOwner)
		|| MinimapSourceOwner.Get() != SourceOwner)
	{
		return false;
	}

	ERedHUDMinimapMode Mode = ERedHUDMinimapMode::Absent;
	FName CelestialFrameId = NAME_None;
	bool bVisible = false;
	return PixelExactHUDWidget->GetMinimapPresentationState(
			SourceOwner,
			MinimapPresentationEpoch,
			Mode,
			CelestialFrameId,
			bVisible)
		&& Mode == ERedHUDMinimapMode::Surface
		&& !CelestialFrameId.IsNone()
		&& bVisible;
}

void ARedHUD::TogglePauseMenu()
{
	APlayerController* PlayerController = GetOwningPlayerController();
	if (!PlayerController || !PlayerController->IsLocalController())
	{
		return;
	}

	if (PauseMenuWidget && PauseMenuWidget->IsInViewport()
		&& PauseMenuWidget->GetVisibility() != ESlateVisibility::Collapsed)
	{
		ClosePauseMenu();
		return;
	}

	if (!PauseMenuWidget)
	{
		PauseMenuWidget = CreateWidget<URedPauseMenuWidget>(
			PlayerController, URedPauseMenuWidget::StaticClass());
		if (!PauseMenuWidget)
		{
			return;
		}
		PauseMenuWidget->InitializeForHUD(this);
		PauseMenuWidget->AddToViewport(500);
	}

	if (ARedPlayerCharacter* Character = Cast<ARedPlayerCharacter>(PlayerController->GetPawn()))
	{
		Character->PrepareForPauseMenu();
	}

	PauseMenuWidget->SetVisibility(ESlateVisibility::Visible);
	PauseMenuWidget->PrepareForOpen();

	// Pausing a listen server would freeze the world for every connected player.
	// Only a truly standalone session uses world pause; online sessions remain live.
	bPausedStandaloneForMenu = GetWorld() && GetWorld()->GetNetMode() == NM_Standalone;
	if (bPausedStandaloneForMenu)
	{
		PlayerController->SetPause(true);
	}

	PlayerController->SetIgnoreMoveInput(true);
	PlayerController->SetIgnoreLookInput(true);
	PlayerController->bShowMouseCursor = true;
	FInputModeUIOnly InputMode;
	InputMode.SetLockMouseToViewportBehavior(EMouseLockMode::DoNotLock);
	InputMode.SetWidgetToFocus(PauseMenuWidget->TakeWidget());
	PlayerController->SetInputMode(InputMode);
	PauseMenuWidget->SetUserFocus(PlayerController);
	PauseMenuWidget->FocusInitialControllerTarget(PlayerController);
}

void ARedHUD::ClosePauseMenu()
{
	APlayerController* PlayerController = GetOwningPlayerController();
	if (!PlayerController || !PlayerController->IsLocalController())
	{
		return;
	}

	if (PauseMenuWidget)
	{
		PauseMenuWidget->SetVisibility(ESlateVisibility::Collapsed);
	}
	if (bPausedStandaloneForMenu)
	{
		PlayerController->SetPause(false);
		bPausedStandaloneForMenu = false;
	}
	PlayerController->SetIgnoreMoveInput(false);
	PlayerController->SetIgnoreLookInput(false);
	PlayerController->bShowMouseCursor = false;
	PlayerController->SetInputMode(FInputModeGameOnly());
}

bool ARedHUD::OpenAbilityLoadoutFromPauseMenu()
{
	APlayerController* PlayerController = GetOwningPlayerController();
	ARedPlayerCharacter* Character = PlayerController
		? Cast<ARedPlayerCharacter>(PlayerController->GetPawn()) : nullptr;
	if (!Character || !Character->CanOpenAbilityLoadout())
	{
		return false;
	}

	ClosePauseMenu();
	Character->OpenAbilityLoadoutFromMenu();
	return true;
}

URedSessionBrowserWidget* ARedHUD::EnsureSessionBrowser()
{
	APlayerController* PlayerController = GetOwningPlayerController();
	if (!PlayerController || !PlayerController->IsLocalController())
	{
		return nullptr;
	}

	if (!SessionBrowserWidget)
	{
		SessionBrowserWidget = CreateWidget<URedSessionBrowserWidget>(
			PlayerController, URedSessionBrowserWidget::StaticClass());
		if (SessionBrowserWidget)
		{
			// Keep the lobby above Escape and every normal gameplay HUD layer.
			SessionBrowserWidget->AddToViewport(700);
			SessionBrowserWidget->SetVisibility(ESlateVisibility::Collapsed);
		}
	}
	return SessionBrowserWidget;
}

bool ARedHUD::OpenSessionBrowserFromPauseMenu()
{
	URedSessionBrowserWidget* Browser = EnsureSessionBrowser();
	if (!Browser)
	{
		return false;
	}

	ClosePauseMenu();
	Browser->SetBrowserOpen(true);
	return true;
}

void ARedHUD::ToggleSessionBrowser()
{
	APlayerController* PlayerController = GetOwningPlayerController();
	if (!PlayerController || !PlayerController->IsLocalController())
	{
		return;
	}

	if (URedSessionBrowserWidget* Browser = EnsureSessionBrowser())
	{
		const bool bOpening = !Browser->IsBrowserOpen();
		if (bOpening && PauseMenuWidget
			&& PauseMenuWidget->GetVisibility() != ESlateVisibility::Collapsed)
		{
			ClosePauseMenu();
		}
		Browser->SetBrowserOpen(bOpening);
	}
}

void ARedHUD::DrawHUD()
{
	Super::DrawHUD();
	ReconcileCombatHUDLayers();
	if (!Canvas || !IsValid(PixelExactHUDWidget)
		|| PixelExactHUDWidget->GetVisibility() == ESlateVisibility::Collapsed)
	{
		return;
	}

	// Trace only against pawns so voxel terrain and ship geometry cannot shadow a valid target.
	// The result drives the pack-authored UMG sight and the enemy's projected shield/health bars.
	bool bOnTarget = false;
	ARedPlayerCharacter* TargetCharacter = nullptr;
	if (APlayerController* PC = GetOwningPlayerController())
	{
		FVector ViewLocation;
		FRotator ViewRotation;
		PC->GetPlayerViewPoint(ViewLocation, ViewRotation);
		const FVector ViewForward = ViewRotation.Vector();

		FCollisionQueryParams QueryParams;
		QueryParams.AddIgnoredActor(GetOwningPawn());
		FCollisionObjectQueryParams PawnObjectQuery;
		PawnObjectQuery.AddObjectTypesToQuery(ECC_Pawn);

		FHitResult Hit;
		const FVector SweepStart = ViewLocation + ViewForward * 50.0f;
		const FVector SweepEnd = ViewLocation + ViewForward * 100000.0f;
		if (GetWorld() && GetWorld()->SweepSingleByObjectType(
			Hit, SweepStart, SweepEnd, FQuat::Identity, PawnObjectQuery,
			FCollisionShape::MakeSphere(35.0f), QueryParams)
			&& Hit.GetActor() != GetOwningPawn())
		{
			bOnTarget = true;
			TargetCharacter = Cast<ARedPlayerCharacter>(Hit.GetActor());
		}
	}

	// The replacement enemy panel consumes only data already authenticated by the
	// existing aimed-pawn trace. Publish a hidden state every frame so misses,
	// friendlies, invalid actors, and downed enemies cannot leave stale target data.
	FRedHUDEnemyState EnemyState;
	EnemyState.bVisible = false;
	EnemyState.Name = TEXT("HOSTILE");
	EnemyState.Level = 0;
	EnemyState.Health = 0.0f;
	EnemyState.MaxHealth = 1.0f;
	EnemyState.bBoss = false;
	if (IsValid(TargetCharacter) && TargetCharacter->bIsEnemy
		&& !TargetCharacter->IsDowned())
	{
		EnemyState.bVisible = true;
		EnemyState.Health = FMath::Clamp(
			TargetCharacter->GetHealthFraction(), 0.0f, 1.0f);
	}
	PixelExactHUDWidget->SetEnemyState(EnemyState);

	const float DeltaSeconds = GetWorld() ? GetWorld()->GetDeltaSeconds() : 0.0f;
	TargetAlpha = FMath::FInterpTo(TargetAlpha, bOnTarget ? 1.0f : 0.0f, DeltaSeconds, 12.0f);
	// The replacement HUD collapses the legacy widget, so draw the project's compact
	// cyan arc sight directly. It remains resolution-independent and reacts to targets.
	const FVector2D Center(Canvas->ClipX * 0.5f, Canvas->ClipY * 0.5f);
	const float Radius = FMath::Clamp(FMath::Min(Canvas->ClipX, Canvas->ClipY) * 0.016f, 10.f, 22.f);
	const FLinearColor SightColor = FLinearColor::LerpUsingHSV(
		FLinearColor(0.05f, 0.85f, 1.f, 0.95f), FLinearColor(0.35f, 1.f, 0.25f, 1.f), TargetAlpha);
	for (int32 Segment = 0; Segment < 24; ++Segment)
	{
		if ((Segment % 6) == 0 || (Segment % 6) == 5) { continue; }
		const float A0 = UE_TWO_PI * static_cast<float>(Segment) / 24.f;
		const float A1 = UE_TWO_PI * static_cast<float>(Segment + 1) / 24.f;
		DrawLine(Center.X + FMath::Cos(A0) * Radius, Center.Y + FMath::Sin(A0) * Radius,
			Center.X + FMath::Cos(A1) * Radius, Center.Y + FMath::Sin(A1) * Radius, SightColor, 2.f);
	}
	DrawRect(SightColor, Center.X - 1.5f, Center.Y - 1.5f, 3.f, 3.f);
	if (ARedPlayerCharacter* LocalCharacter = Cast<ARedPlayerCharacter>(GetOwningPawn()))
	{
		// The purchased crosshair now owns screen-center presentation. Canvas intentionally draws
		// no receptacle and no heat indicator, preventing both of the rejected legacy elements.
		LocalCharacter->SetHUDReticleTargetAlpha(TargetAlpha);
	}

	// The target's bars remain projected in world space. The local player's status stays in the
	// upper-left HUD, so aiming can never display the player's own bars.
	if (!TargetCharacter)
	{
		return;
	}

	const FVector HeadWorld = TargetCharacter->GetActorLocation() + FVector(0.0f, 0.0f, 110.0f);
	const FVector Projected = Project(HeadWorld);
	const FVector2D Screen(Projected.X, Projected.Y);
	if (Projected.Z <= 0.0f || Screen.X <= 0.0f || Screen.Y <= 0.0f)
	{
		return;
	}

	constexpr float BarWidth = 120.0f;
	constexpr float BarHeight = 6.0f;
	constexpr float Pad = 1.0f;
	const float TopY = Screen.Y - 38.0f;

	const float ShieldFraction = FMath::Clamp(TargetCharacter->GetShieldFraction(), 0.0f, 1.0f);
	DrawRect(FLinearColor(0.0f, 0.0f, 0.0f, 0.7f),
		Screen.X - BarWidth * 0.5f - Pad, TopY - Pad,
		BarWidth + Pad * 2.0f, BarHeight + Pad * 2.0f);
	DrawRect(FLinearColor(0.1f, 0.78f, 1.0f, 1.0f),
		Screen.X - BarWidth * 0.5f, TopY, BarWidth * ShieldFraction, BarHeight);

	const float HealthFraction = FMath::Clamp(TargetCharacter->GetHealthFraction(), 0.0f, 1.0f);
	const float HealthY = TopY + BarHeight + 4.0f;
	DrawRect(FLinearColor(0.0f, 0.0f, 0.0f, 0.7f),
		Screen.X - BarWidth * 0.5f - Pad, HealthY - Pad,
		BarWidth + Pad * 2.0f, BarHeight + Pad * 2.0f);
	DrawRect(FLinearColor(1.0f, 0.18f, 0.18f, 1.0f),
		Screen.X - BarWidth * 0.5f, HealthY, BarWidth * HealthFraction, BarHeight);
}

void ARedHUD::ReconcileCombatHUDLayers()
{
	// HUD and pawn BeginPlay order is not guaranteed. Keep the old combat tree
	// alive as the data/loadout backend, but never let it draw beneath the exact
	// supplied composite. When the exact HUD is intentionally collapsed for the
	// loadout, this leaves the legacy widget visible and interactive.
	if (!PixelExactHUDWidget
		|| PixelExactHUDWidget->GetVisibility() == ESlateVisibility::Collapsed)
	{
		return;
	}

	if (APlayerController* PlayerController = GetOwningPlayerController())
	{
		if (ARedPlayerCharacter* Character = Cast<ARedPlayerCharacter>(PlayerController->GetPawn()))
		{
			if (UUserWidget* LegacyHUD = Character->GetActiveHUDWidget())
			{
				RegisterLegacyCombatHUD(Character, LegacyHUD);
			}
		}
	}

	if (UUserWidget* LegacyHUD = CachedLegacyHUDWidget.Get();
		IsValid(LegacyHUD) && LegacyHUD->GetVisibility() != ESlateVisibility::Collapsed)
	{
		LegacyHUD->SetVisibility(ESlateVisibility::Collapsed);
	}
}
