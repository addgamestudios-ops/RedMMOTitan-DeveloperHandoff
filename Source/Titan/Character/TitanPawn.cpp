// Copyright Epic Games, Inc. All Rights Reserved.


#include "Character/TitanPawn.h"

#include "Logging/TitanLogChannels.h"

#include "Components/CapsuleComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Components/PoseableMeshComponent.h"
#include "TitanCameraComponent.h"

#include "InputAction.h"
#include "EnhancedInputComponent.h"
#include "Character/TitanInputEventSet.h"

#include "TitanAbilitySystemComponent.h"
#include "TitanAbilitySet.h"
#include "TitanGameplayAbility.h"

#include "TitanMoverComponent.h"
#include "TitanMoverTypes.h"
#include "MoveLibrary/MovementUtils.h"
#include "MoveLibrary/BasedMovementUtils.h"

#include "TitanRaftActor.h"
#include "TitanRaftTeleportEffect.h"
#include "TitanLayeredMove_Jump.h"

#include "Engine/CollisionProfile.h"
#include "TitanWaterDetectionComponent.h"
#include "Engine/World.h"
#include "TitanTeleportPreloader.h"
#include "TitanPlayerController.h"
#include "Animation/AnimMontage.h"
#include "Animation/AnimInstance.h"

UE_DEFINE_GAMEPLAY_TAG(TAG_Titan_Character_MovementModeChanged, "Titan.Character.MovementModeChanged");

ATitanPawn::ATitanPawn(const FObjectInitializer& ObjectInitializer)
: APawn(ObjectInitializer)
{
	PrimaryActorTick.bCanEverTick = true;

	WindVelocity = FVector::ZeroVector;

	// create the collision capsule
	PlayerCapsule = CreateDefaultSubobject<UCapsuleComponent>(TEXT("Player Capsule"));

	check(PlayerCapsule);

	SetRootComponent(PlayerCapsule);
	PlayerCapsule->InitCapsuleSize(34.0f, 88.0f);
	PlayerCapsule->SetCollisionProfileName(UCollisionProfile::Pawn_ProfileName);

	PlayerCapsule->CanCharacterStepUpOn = ECB_No;
	PlayerCapsule->SetShouldUpdatePhysicsVolume(true);
	PlayerCapsule->SetCanEverAffectNavigation(false);
	PlayerCapsule->bDynamicObstacle = true;

	// create the torso skeletal mesh
	TorsoMesh = CreateDefaultSubobject<USkeletalMeshComponent>(TEXT("Torso Mesh"));

	check(TorsoMesh);

	TorsoMesh->SetupAttachment(PlayerCapsule);
	TorsoMesh->AlwaysLoadOnClient = true;
	TorsoMesh->AlwaysLoadOnServer = true;
	TorsoMesh->bOwnerNoSee = false;
	TorsoMesh->VisibilityBasedAnimTickOption = EVisibilityBasedAnimTickOption::AlwaysTickPose;
	TorsoMesh->bCastDynamicShadow = true;
	TorsoMesh->bAffectDynamicIndirectLighting = true;
	TorsoMesh->PrimaryComponentTick.TickGroup = TG_PrePhysics;

	static FName MeshCollisionProfileName(TEXT("CharacterMesh"));
	TorsoMesh->SetCollisionProfileName(MeshCollisionProfileName);
	TorsoMesh->SetGenerateOverlapEvents(false);
	TorsoMesh->SetCanEverAffectNavigation(false);

	// create the head skinned mesh
	HeadMesh = CreateDefaultSubobject<USkeletalMeshComponent>(TEXT("Head Mesh"));

	check(HeadMesh);

	HeadMesh->SetupAttachment(TorsoMesh);
	HeadMesh->AlwaysLoadOnClient = true;
	HeadMesh->AlwaysLoadOnServer = true;
	HeadMesh->bOwnerNoSee = false;
	HeadMesh->VisibilityBasedAnimTickOption = EVisibilityBasedAnimTickOption::AlwaysTickPose;
	HeadMesh->bCastDynamicShadow = true;
	HeadMesh->bAffectDynamicIndirectLighting = true;
	HeadMesh->PrimaryComponentTick.TickGroup = TG_PrePhysics;

	HeadMesh->SetCollisionProfileName(MeshCollisionProfileName);
	HeadMesh->SetGenerateOverlapEvents(false);
	HeadMesh->SetCanEverAffectNavigation(false);

	// create the headwear mesh
	HeadwearMesh = CreateDefaultSubobject<USkeletalMeshComponent>(TEXT("Headwear Mesh"));

	check(HeadwearMesh);

 	HeadwearMesh->SetupAttachment(TorsoMesh);
	HeadwearMesh->AlwaysLoadOnClient = true;
	HeadwearMesh->AlwaysLoadOnServer = true;
	HeadwearMesh->bOwnerNoSee = false;
	HeadwearMesh->VisibilityBasedAnimTickOption = EVisibilityBasedAnimTickOption::AlwaysTickPose;
	HeadwearMesh->bCastDynamicShadow = true;
	HeadwearMesh->bAffectDynamicIndirectLighting = true;
	HeadwearMesh->PrimaryComponentTick.TickGroup = TG_PrePhysics;

	HeadwearMesh->SetCollisionProfileName(MeshCollisionProfileName);
	HeadwearMesh->SetGenerateOverlapEvents(false);
	HeadwearMesh->SetCanEverAffectNavigation(false);
	

	// create the lower body mesh
	LegsMesh = CreateDefaultSubobject<USkeletalMeshComponent>(TEXT("Legs Mesh"));

	check(LegsMesh);

	LegsMesh->SetupAttachment(TorsoMesh);
	LegsMesh->AlwaysLoadOnClient = true;
	LegsMesh->AlwaysLoadOnServer = true;
	LegsMesh->bOwnerNoSee = false;
	LegsMesh->VisibilityBasedAnimTickOption = EVisibilityBasedAnimTickOption::AlwaysTickPose;
	LegsMesh->bCastDynamicShadow = true;
	LegsMesh->bAffectDynamicIndirectLighting = true;
	LegsMesh->PrimaryComponentTick.TickGroup = TG_PrePhysics;

	LegsMesh->SetCollisionProfileName(MeshCollisionProfileName);
	LegsMesh->SetGenerateOverlapEvents(false);
	LegsMesh->SetCanEverAffectNavigation(false);
	
	// create the glider skeletal mesh
	GliderMesh = CreateDefaultSubobject<USkeletalMeshComponent>(TEXT("Glider Mesh"));

	check(GliderMesh);

	GliderMesh->SetupAttachment(PlayerCapsule);
	GliderMesh->AlwaysLoadOnClient = true;
	GliderMesh->AlwaysLoadOnClient = true;
	GliderMesh->AlwaysLoadOnServer = true;
	GliderMesh->bOwnerNoSee = false;
	GliderMesh->VisibilityBasedAnimTickOption = EVisibilityBasedAnimTickOption::AlwaysTickPose;
	GliderMesh->bCastDynamicShadow = true;
	GliderMesh->bAffectDynamicIndirectLighting = true;
	GliderMesh->PrimaryComponentTick.TickGroup = TG_PrePhysics;

	// create the camera
	Camera = CreateDefaultSubobject<UTitanCameraComponent>(TEXT("Camera"));

	check(Camera);

	Camera->SetupAttachment(PlayerCapsule);

	// create the Mover component
	CharacterMotionComponent = CreateDefaultSubobject<UTitanMoverComponent>(TEXT("MoverComponent"));
	ensure(CharacterMotionComponent);

	// create the ASC
	AbilitySystem = CreateDefaultSubobject<UTitanAbilitySystemComponent>(TEXT("AbilitySystemComponent"));

	check(AbilitySystem);

	// create the water detection comp
	WaterDetection = CreateDefaultSubobject<UTitanWaterDetectionComponent>(TEXT("Water Detection"));
	check(WaterDetection);

	// add water detection as a tick prerequisite
	AddTickPrerequisiteComponent(WaterDetection);

	// disable Actor-level movement replication, since our Mover component will handle it
	SetReplicatingMovement(false);
}

void ATitanPawn::BeginPlay()
{
	Super::BeginPlay();
}

void ATitanPawn::PostInitializeComponents()
{
	Super::PostInitializeComponents();

	if (ensure(CharacterMotionComponent))
	{
		CharacterMotionComponent->InputProducer = this;

		// register to the movement mode changed delegate
		CharacterMotionComponent->OnMovementModeChanged.AddDynamic(this, &ATitanPawn::OnMovementModeChanged);
	}

	if (TorsoMesh)
	{
		// force animation tick after movement component updates
		if (TorsoMesh->PrimaryComponentTick.bCanEverTick && GetMoverComponent())
		{
			TorsoMesh->PrimaryComponentTick.AddPrerequisite(GetMoverComponent(), GetMoverComponent()->PrimaryComponentTick);
		}


		if (HeadMesh && HeadwearMesh && LegsMesh)
		{
			// force animation tick after movement component updates
			if (HeadMesh->PrimaryComponentTick.bCanEverTick && GetMoverComponent())
			{
				HeadMesh->PrimaryComponentTick.AddPrerequisite(GetMoverComponent(), GetMoverComponent()->PrimaryComponentTick);
			}

			// force animation tick after movement component updates
			if (HeadwearMesh->PrimaryComponentTick.bCanEverTick && GetMoverComponent())
			{
				HeadwearMesh->PrimaryComponentTick.AddPrerequisite(GetMoverComponent(), GetMoverComponent()->PrimaryComponentTick);
			}

			// force animation tick after movement component updates
			if (LegsMesh->PrimaryComponentTick.bCanEverTick && GetMoverComponent())
			{
				LegsMesh->PrimaryComponentTick.AddPrerequisite(GetMoverComponent(), GetMoverComponent()->PrimaryComponentTick);
			}
		}
	}
}

void ATitanPawn::PossessedBy(AController* NewController)
{
	Super::PossessedBy(NewController);

	// cast the player controller
	PC = Cast<ATitanPlayerController>(NewController);

	if (PC)
	{
		// initialize the ability system
		if (AbilitySystem)
		{
			AbilitySystem->InitAbilityActorInfo(this, this);

			// grant the ability set but only once
			if (AbilitySet && !bInitializedAbilities)
			{
				bInitializedAbilities = true;

				AbilitySet->GiveToAbilitySystem(AbilitySystem, nullptr);

				// call the BP initialization handle
				OnPawnInitialized(PC);
			}
		}

		// initialize the camera pitch limits
		Camera->InitializeCameraForPlayer();

	}
}

void ATitanPawn::UnPossessed()
{
	if (PC)
	{
		if (UEnhancedInputComponent* EIC = Cast<UEnhancedInputComponent>(PC->InputComponent))
		{
			ClearInputEvents(EIC);
		}
	}

	// clear the player controller pointer
	PC = nullptr;

	Super::UnPossessed();
}

void ATitanPawn::Tick(float DeltaTime)
{
	Super::Tick(DeltaTime);

	// spin the camera based on input
	if (PC)
	{
		// apply control inputs
		PC->AddYawInput(CachedLookInput.Yaw * CameraRotationRateYaw * DeltaTime / GetActorTimeDilation());
		PC->AddPitchInput(-CachedLookInput.Pitch * CameraRotationRatePitch * DeltaTime / GetActorTimeDilation());

		if (CachedMoveInputIntent.Size() > 0.0f)
		{
			if (ShouldAlignCameraOnMovement())
			{
				AlignCameraToFacing(DeltaTime, CameraMovementAlignSpeed * CachedMoveInputIntent.GetClampedToMaxSize(1.0f).Size());
			}
		}

		// calculate the time since our last relevant input
		float TimeSinceLastInput = GetWorld()->GetTimeSeconds() - CameraAutoAlignLastInputTime;

		float AutoAlignTime = bOverrideCameraAutoAlign ? OverrideCameraAutoAlignTime : CameraAutoAlignTime;

		// check if it's time to auto align the camera
		if (ShouldAutoAlignCamera() && TimeSinceLastInput >= AutoAlignTime)
		{
			float AutoAlignSpeed = bOverrideCameraAutoAlign ? OverrideCameraAutoAlignSpeed : CameraAutoAlignSpeed;

			AlignCameraToFacing(DeltaTime, AutoAlignSpeed);
		}
	}

}

void ATitanPawn::SetupPlayerInputComponent(UInputComponent* PlayerInputComponent)
{
	Super::SetupPlayerInputComponent(PlayerInputComponent);

	// Set up action bindings
	if (UEnhancedInputComponent* EnhancedInputComponent = Cast<UEnhancedInputComponent>(PlayerInputComponent))
	{
		// Move
		EnhancedInputComponent->BindAction(MoveAction, ETriggerEvent::Triggered, this, &ATitanPawn::Move);
		EnhancedInputComponent->BindAction(MoveAction, ETriggerEvent::Completed, this, &ATitanPawn::MoveCompleted);

		// Look
		EnhancedInputComponent->BindAction(LookAction, ETriggerEvent::Triggered, this, &ATitanPawn::Look);
		EnhancedInputComponent->BindAction(LookAction, ETriggerEvent::Completed, this, &ATitanPawn::LookCompleted);

		// Jump
		EnhancedInputComponent->BindAction(JumpAction, ETriggerEvent::Started, this, &ATitanPawn::Jump);
		EnhancedInputComponent->BindAction(JumpAction, ETriggerEvent::Completed, this, &ATitanPawn::StopJumping);

		// Autorun
		EnhancedInputComponent->BindAction(AutoWalkAction, ETriggerEvent::Completed, this, &ATitanPawn::AutoWalk);

		// Camera distance adjust
		EnhancedInputComponent->BindAction(CameraDistanceAction, ETriggerEvent::Triggered, this, &ATitanPawn::AdjustCameraDistance);

		// bind the input event set
		BindInputEventSet(InputEventSet, EnhancedInputComponent);
	}
}

void ATitanPawn::Move(const FInputActionValue& Value)
{
	// input is a Vector2D
	FVector2D MovementVector = Value.Get<FVector2D>();

	// set up the input vector. We flip the axis so they correspond with the expected Mover input
	CachedMoveInputIntent.X = FMath::Clamp(MovementVector.Y, -1.0f, 1.0f);
	CachedMoveInputIntent.Y = FMath::Clamp(MovementVector.X, -1.0f, 1.0f);

	// cancel autorun if the input intent is nonzero
	if (!CachedMoveInputIntent.IsNearlyZero())
	{
		bWantsToAutoWalk = false;
	}

	// broadcast the delegate
	OnMoved.Broadcast(MovementVector);

	// update the camera auto align timeout
	UpdateCameraAutoAlignInputTime();
}

void ATitanPawn::MoveCompleted(const FInputActionValue& Value)
{
	// zero out the cached input
	CachedMoveInputIntent = FVector::ZeroVector;

	// broadcast the delegate
	OnMoved.Broadcast(FVector2D::ZeroVector);
}

void ATitanPawn::Look(const FInputActionValue& Value)
{
	// input is a Vector2D
	FVector2D LookAxisVector = Value.Get<FVector2D>();

	// set up the look input rotator
	CachedLookInput.Yaw = CachedTurnInput.Yaw = FMath::Clamp(LookAxisVector.X, -1.0f, 1.0f);
	CachedLookInput.Pitch = CachedTurnInput.Pitch = FMath::Clamp(LookAxisVector.Y, -1.0f, 1.0f);

	// update the camera auto align timeout
	UpdateCameraAutoAlignInputTime();
}

void ATitanPawn::LookCompleted(const FInputActionValue& Value)
{
	// zero out the cached input
	CachedLookInput = FRotator::ZeroRotator;
}

void ATitanPawn::Jump()
{
	// is this the first frame we want to jump?
	bWantsToJump = !bIsJumpPressed;

	// update the flag
	bIsJumpPressed = true;

	// broadcast the delegate
	OnJumped.Broadcast(true);

	// update the camera auto align timeout
	UpdateCameraAutoAlignInputTime();
}

void ATitanPawn::StopJumping()
{
	// reset the flag
	bIsJumpPressed = bWantsToJump = false;

	// broadcast the delegate
	OnJumped.Broadcast(false);
}

void ATitanPawn::AutoWalk()
{
	// toggle autorun
	bWantsToAutoWalk = !bWantsToAutoWalk;
}

void ATitanPawn::AdjustCameraDistance(const FInputActionValue& Value)
{
	Camera->AdjustArmLengthMultiplier(Value.Get<float>());
}

void ATitanPawn::AddWind(const FVector& Wind)
{
	WindVelocity += Wind;
}

void ATitanPawn::Sprint()
{
	// is this the first frame we want to sprint?
	bWantsToSprint = !bIsSprintPressed;

	// update the flag
	bIsSprintPressed = true;
}

void ATitanPawn::StopSprinting()
{
	// reset the flag
	bIsSprintPressed = bWantsToSprint = false;
}

void ATitanPawn::Glide()
{
	// is this the first frame we want to glide?
	bWantsToGlide = !bIsGlidePressed;

	// update the flag
	bIsGlidePressed = true;
}

void ATitanPawn::StopGliding()
{
	// reset the flag
	bIsGlidePressed = bWantsToGlide = false;
}

void ATitanPawn::Aim()
{
	// set the flag
	bIsAimPressed = true;
}

void ATitanPawn::StopAiming()
{
	// reset the flag
	bIsAimPressed = false;
}

void ATitanPawn::BindInputEventSet(const UTitanInputEventSet* EventSet, UEnhancedInputComponent* EnhancedInputComponent)
{
	if (!EventSet)
	{
		return;
	}

	// grant the input event set to this pawn
	EventSet->GiveToPawn(this, EnhancedInputComponent);
}

void ATitanPawn::BindInputEvent(const UInputAction* InputAction, FGameplayTag EventTag, UEnhancedInputComponent* EnhancedInputComponent)
{
	// ensure the input action is valid
	if (!IsValid(InputAction))
	{
		return;
	}

	// ensure we only have one binding per input action
	if (InputEventMap.Find(InputAction))
	{
		return;
	}

	// ensure the event tag is valid
	if (EventTag == FGameplayTag::EmptyTag)
	{
		return;
	}

	// save the event tag to the action map
	InputEventMap.Add(InputAction, EventTag);

	// create the bindings
	EnhancedInputComponent->BindAction(InputAction, ETriggerEvent::Started, this, &ATitanPawn::HandleInputPressed);
	EnhancedInputComponent->BindAction(InputAction, ETriggerEvent::Ongoing, this, &ATitanPawn::HandleInputOngoing);
	EnhancedInputComponent->BindAction(InputAction, ETriggerEvent::Completed, this, &ATitanPawn::HandleInputReleased);
}

void ATitanPawn::ClearInputEvents(UEnhancedInputComponent* EnhancedInputComponent)
{
	if (EnhancedInputComponent)
	{
		// clear all bindings for this pawn
		EnhancedInputComponent->ClearBindingsForObject(this);

		// clear the input event map
		InputEventMap.Empty();
	}
}

void ATitanPawn::HandleInputPressed(const FInputActionInstance& ActionInstance)
{
	const UInputAction* InputAction = ActionInstance.GetSourceAction();

	if (FGameplayTag* EventMapping = InputEventMap.Find(InputAction))
	{
		FGameplayEventData Payload;
		Payload.InstigatorTags.AddTag(TAG_Titan_Input_Pressed);

		AbilitySystem->HandleGameplayEvent(*EventMapping, &Payload);
	}
}

void ATitanPawn::HandleInputOngoing(const FInputActionInstance& ActionInstance)
{
	const UInputAction* InputAction = ActionInstance.GetSourceAction();

	if (FGameplayTag* EventMapping = InputEventMap.Find(InputAction))
	{
		FGameplayEventData Payload;
		Payload.InstigatorTags.AddTag(TAG_Titan_Input_Ongoing);

		AbilitySystem->HandleGameplayEvent(*EventMapping, &Payload);
	}
}

void ATitanPawn::HandleInputReleased(const FInputActionInstance& ActionInstance)
{
	const UInputAction* InputAction = ActionInstance.GetSourceAction();

	if (FGameplayTag* EventMapping = InputEventMap.Find(InputAction))
	{
		FGameplayEventData Payload;
		Payload.InstigatorTags.AddTag(TAG_Titan_Input_Released);

		AbilitySystem->HandleGameplayEvent(*EventMapping, &Payload);
	}
}

UPrimitiveComponent* ATitanPawn::GetMovementBase() const
{
	return CharacterMotionComponent ? CharacterMotionComponent->GetMovementBase() : nullptr;
}

void ATitanPawn::RequestMoveByIntent(const FVector& DesiredIntent)
{
	CachedMoveInputIntent = DesiredIntent;
}

void ATitanPawn::RequestMoveByVelocity(const FVector& DesiredVelocity)
{
	// left as stub on purpose. We're not an AI so we move by intent, not velocity
}

float ATitanPawn::GetStamina() const
{
	// get the mover component
	if (UMoverComponent* MoverComp = GetMoverComponent())
	{
		// get the sync state
		if (const FTitanStaminaSyncState* SyncState = MoverComp->GetSyncState().SyncStateCollection.FindDataByType<FTitanStaminaSyncState>())
		{
			// return the current stamina value
			return SyncState->GetStamina();
		}
	}

	return 0.0f;
}

float ATitanPawn::GetStaminaPercent() const
{
	// get the mover component
	if (UMoverComponent* MoverComp = GetMoverComponent())
	{
		// get the sync state
		if (const FTitanStaminaSyncState* SyncState = MoverComp->GetSyncState().SyncStateCollection.FindDataByType<FTitanStaminaSyncState>())
		{
			
			// return the stamina ratio
			return SyncState->GetStamina() / SyncState->GetMaxStamina();
			
		}
	}

	return 0.0f;
}

bool ATitanPawn::IsExhausted() const
{
	// get the mover component
	if (UMoverComponent* MoverComp = GetMoverComponent())
	{
		// get the sync state
		if (const FTitanStaminaSyncState* SyncState = MoverComp->GetSyncState().SyncStateCollection.FindDataByType<FTitanStaminaSyncState>())
		{

			// return the stamina ratio
			return SyncState->IsExhausted();
		}		
	}

	return false;
}

bool ATitanPawn::HasMovementTagExact(const FGameplayTag& Tag)
{
	// get the mover component
	if (UMoverComponent* MoverComp = GetMoverComponent())
	{
		// get the sync state
		if (const FTitanTagsSyncState* SyncState = MoverComp->GetSyncState().SyncStateCollection.FindDataByType<FTitanTagsSyncState>())
		{
			// return the tag match
			return SyncState->HasTagExact(Tag);
		}
	}

	return false;
}

bool ATitanPawn::HasMovementTagAny(const FGameplayTag& Tag)
{
	// get the mover component
	if (UMoverComponent* MoverComp = GetMoverComponent())
	{
		// get the sync state
		if (const FTitanTagsSyncState* SyncState = MoverComp->GetSyncState().SyncStateCollection.FindDataByType<FTitanTagsSyncState>())
		{
			// return the tag match
			return SyncState->HasTagAny(Tag);
		}
	}

	return false;
}

void ATitanPawn::QueueTeleportMove(const FVector& TeleportLocation)
{
	if (bTeleportQueued)
	{
		UE_LOG(LogTitan, Warning, TEXT("Teleport already queued."));

		return;
	}

	bTeleportQueued = true;
	bCompletedPreloadingTeleport = bCompletedTeleportAnimation = false;

	QueuedTeleportLocation = TeleportLocation;

	FTransform PreloaderTransform(FRotator::ZeroRotator, QueuedTeleportLocation, FVector::OneVector);

	ATitanTeleportPreloader* Preloader = GetWorld()->SpawnActor<ATitanTeleportPreloader>(ATitanTeleportPreloader::StaticClass(), PreloaderTransform);

	if (Preloader)
	{
		GetMoverComponent()->WaitForTeleport();

		Preloader->OnPreloadComplete.BindDynamic(this, &ATitanPawn::OnTeleportPreloadReady);

		if (UAnimInstance* AnimInstance = TorsoMesh->GetAnimInstance())
		{
			if (TeleportMontage)
			{
				AnimInstance->Montage_Play(TeleportMontage, 1.0f, EMontagePlayReturnType::Duration, 0.0f, true);
				AnimInstance->Montage_SetNextSection(TeleportLoopSection, TeleportLoopSection, TeleportMontage);

				UE_LOG(LogTitan, Error, TEXT("Teleport Queued"));
			}
		}

	}
	else {
		UE_LOG(LogTitan, Error, TEXT("Could not spawn teleport preloader"));
	}
}

bool ATitanPawn::IsTeleporting() const
{
	return bTeleportQueued;
}

void ATitanPawn::OnTeleportAnimationReady()
{
	if (bTeleportQueued)
	{
		UE_LOG(LogTitan, Error, TEXT("Teleport Animation Ready"));

		bCompletedTeleportAnimation = true;

		FinalizeTeleport();
	}	
}

void ATitanPawn::CheckTeleportReady()
{
	if (bTeleportQueued && bCompletedPreloadingTeleport)
	{
		if (TeleportMontage)
		{
			if (UAnimInstance* AnimInstance = TorsoMesh->GetAnimInstance())
			{
				UE_LOG(LogTitan, Error, TEXT("Exiting Teleport Loop"));

				AnimInstance->Montage_SetNextSection(TeleportLoopSection, TeleportEndSection, TeleportMontage);
			}
		}
	}	
}

void ATitanPawn::SetMovementDisabled(bool bNewDisabledState)
{
	// cache the previous state
	const bool bLastState = GetMoverComponent()->IsMovementDisabled();

	// is there a change?
	if (bLastState != bNewDisabledState)
	{
		// set the mover comp to the new value
		GetMoverComponent()->SetMovementDisabled(bNewDisabledState);
		
		// call the delegate
		OnMovementDisabledStateChanged.Broadcast(bNewDisabledState);
	}
}

void ATitanPawn::OnTeleportPreloadReady()
{
	UE_LOG(LogTitan, Error, TEXT("Teleport Preload Ready"));

	bCompletedPreloadingTeleport = true;

	FinalizeTeleport();
}

void ATitanPawn::FinalizeTeleport()
{
	if (bTeleportQueued && bCompletedPreloadingTeleport && bCompletedTeleportAnimation)
	{
		UE_LOG(LogTitan, Error, TEXT("Finalizing Teleport"));

		bTeleportQueued = false;

		GetMoverComponent()->TeleportAndFall(QueuedTeleportLocation);
	}
	
}

void ATitanPawn::OnMovementModeChanged(const FName& PreviousModeName, const FName& NewModeName)
{
	FGameplayEventData Payload;

	// pass the gameplay event to the ability system so abilities can react to the mode change
	AbilitySystem->HandleGameplayEvent(TAG_Titan_Character_MovementModeChanged, &Payload);
}

void ATitanPawn::ProduceInput_Implementation(int32 SimTimeMs, FMoverInputCmdContext& InputCmdResult)
{
	float DeltaMs = (float)SimTimeMs;

	FCharacterDefaultInputs& DefaultKinematicInputs = InputCmdResult.InputCollection.FindOrAddMutableDataByType<FCharacterDefaultInputs>();
	FTitanMovementInputs& TitanInputs = InputCmdResult.InputCollection.FindOrAddMutableDataByType<FTitanMovementInputs>();

	static const FCharacterDefaultInputs DoNothingInput;

	// do we have a controller?
	if (Controller == nullptr)
	{
		// are we the authority?
		if (GetLocalRole() == ENetRole::ROLE_Authority && GetRemoteRole() == ENetRole::ROLE_SimulatedProxy)
		{
			// no controller, so pass a do nothing input
			DefaultKinematicInputs = DoNothingInput;
		}

		// no need to run input code without a controller
		return;
	}

	// is movement disabled ?
	if (GetMoverComponent()->IsMovementDisabled())
	{
		// pass a do nothing input
		DefaultKinematicInputs = DoNothingInput;
	}

	DefaultKinematicInputs.ControlRotation = FRotator::ZeroRotator;

	// copy the control rotation
	if (PC)
	{
		DefaultKinematicInputs.ControlRotation = PC->GetControlRotation();
	}

	// force the forward input intent if autowalk is on
	FVector MoveInputIntent = CachedMoveInputIntent;

	if (bWantsToAutoWalk)
	{
		MoveInputIntent.X = 1.0f;
	}

	// use only the control rotation yaw to avoid tapering our inputs if looking at the character from a too low or too high angle
	FRotator ControlFacing = FRotator::ZeroRotator;
	ControlFacing.Yaw = DefaultKinematicInputs.ControlRotation.Yaw;

	// set the move input
	DefaultKinematicInputs.SetMoveInput(EMoveInputType::DirectionalIntent, ControlFacing.RotateVector(MoveInputIntent));

	// check if we have a nonzero input
	static float RotationMagMin(1e-3);
	const bool bHasAffirmativeMoveInput = (DefaultKinematicInputs.GetMoveInput().Size() >= RotationMagMin);

	// Figure out the orientation intent for the character
	DefaultKinematicInputs.OrientationIntent = FVector::ZeroVector;

	if (bIsAimPressed)
	{
		// set the orientation intent to the camera forward vector
		DefaultKinematicInputs.OrientationIntent = Camera->GetViewRotation().RotateVector(FVector::ForwardVector);

		// save the last nonzero input
		LastAffirmativeMoveInput = DefaultKinematicInputs.OrientationIntent;
	}
	// do we have an affirmative input intent?
	else if (bHasAffirmativeMoveInput)
	{
		// set the orientation intent to the movement direction
		DefaultKinematicInputs.OrientationIntent = DefaultKinematicInputs.GetMoveInput();

		// save the last nonzero input
		LastAffirmativeMoveInput = DefaultKinematicInputs.OrientationIntent;

	}
	else
	{
		// no input intent, so keep the last orientation from input
		DefaultKinematicInputs.OrientationIntent = LastAffirmativeMoveInput;
	}

	// cancel out any z intent to keep the actor vertical
	DefaultKinematicInputs.OrientationIntent = DefaultKinematicInputs.OrientationIntent.GetSafeNormal2D();

	// set the jump inputs
	DefaultKinematicInputs.bIsJumpPressed = bIsJumpPressed;
	DefaultKinematicInputs.bIsJumpJustPressed = bWantsToJump;

	// set the sprint inputs
	TitanInputs.bIsSprintPressed = bIsSprintPressed;
	TitanInputs.bIsSprintJustPressed = bWantsToSprint;

	// set the glide inputs
	TitanInputs.bIsGlidePressed = bIsGlidePressed;
	TitanInputs.bIsGlideJustPressed = bWantsToGlide;

	// set the wind velocity
	TitanInputs.Wind = WindVelocity;
	
	// Convert inputs to be relative to the current movement base (depending on options and state)
	DefaultKinematicInputs.bUsingMovementBase = false;
	
	// get the Mover component
	if (const UMoverComponent* MoverComp = GetMoverComponent())
	{
		// do we have a base?
		if (UPrimitiveComponent* MovementBase = MoverComp->GetMovementBase())
		{
			FName MovementBaseBoneName = MoverComp->GetMovementBaseBoneName();

			FVector RelativeMoveInput, RelativeOrientDir;


			UBasedMovementUtils::TransformWorldDirectionToBased(MovementBase, MovementBaseBoneName, DefaultKinematicInputs.GetMoveInput(), RelativeMoveInput);
			UBasedMovementUtils::TransformWorldDirectionToBased(MovementBase, MovementBaseBoneName, DefaultKinematicInputs.OrientationIntent, RelativeOrientDir);

			DefaultKinematicInputs.SetMoveInput(DefaultKinematicInputs.GetMoveInputType(), RelativeMoveInput);
			DefaultKinematicInputs.OrientationIntent = RelativeOrientDir;

			DefaultKinematicInputs.bUsingMovementBase = true;
			DefaultKinematicInputs.MovementBase = MovementBase;
			DefaultKinematicInputs.MovementBaseBoneName = MovementBaseBoneName;
		}
	}

	// Clear/consume the inputs
	bWantsToJump = false;
	bWantsToGlide = false;
	bWantsToSprint = false;
}

UAbilitySystemComponent* ATitanPawn::GetAbilitySystemComponent() const
{
	return AbilitySystem;
}

void ATitanPawn::AlignCameraToFacing(float DeltaTime, float AlignSpeed)
{
	// get the camera facing vector
	FVector CameraFacing = Camera->GetViewRotation().RotateVector(FVector::ForwardVector);
	CameraFacing = CameraFacing.GetSafeNormal2D();

	// dot product with our right vector to get the yaw input strength
	float FacingDot = -FVector::DotProduct(CameraFacing, GetActorRightVector());

	// rotate the camera facing through a controller yaw input
	PC->AddYawInput(FacingDot * AlignSpeed * DeltaTime);

}

bool ATitanPawn::ShouldAutoAlignCamera()
{
	// skip auto alignment if we're aiming the grapple
	return !bIsAimPressed || bOverrideCameraAutoAlign;
}

void ATitanPawn::UpdateCameraAutoAlignInputTime()
{
	CameraAutoAlignLastInputTime = GetWorld()->GetTimeSeconds();
}

void ATitanPawn::SetCameraAutoAlignState(bool bEnable, float AutoAlignTime, float AutoAlignSpeed)
{
	bOverrideCameraAutoAlign = bEnable;

	OverrideCameraAutoAlignTime = AutoAlignTime;
	OverrideCameraAutoAlignSpeed = AutoAlignSpeed;
}

bool ATitanPawn::ShouldAlignCameraOnMovement()
{
	return (bAlignCameraOnMovement && !bIsAimPressed);
}

const ATitanRaft* ATitanPawn::GetRaft() const
{
	return CurrentRaft;
}

void ATitanPawn::InitializeRaft(ATitanRaft* PilotedRaft)
{
	// ensure the raft is valid
	check(PilotedRaft);

	// save a reference to the raft
	CurrentRaft = PilotedRaft;

	// disable collision
	SetActorEnableCollision(false);

	// subscribe to the input delegates
	OnMoved.AddDynamic(PilotedRaft, &ATitanRaft::OnMoveInput);
	OnJumped.AddDynamic(PilotedRaft, &ATitanRaft::OnJumpInput);
	OnMovementDisabledStateChanged.AddDynamic(PilotedRaft, &ATitanRaft::OnMovementDisabledStateChanged);

	// queue an instant move to attach the pilot to the raft
	TSharedPtr<FTitanRaftTeleportEffect> RaftTeleport = MakeShared<FTitanRaftTeleportEffect>();
	RaftTeleport->Raft = PilotedRaft;

	GetMoverComponent()->QueueInstantMovementEffect(RaftTeleport);

	const UTitanMovementSettings* TitanSettings = GetMoverComponent()->FindSharedSettings<UTitanMovementSettings>();
	check(TitanSettings);

	GetMoverComponent()->QueueNextMode(TitanSettings->RaftMovementModeName, false);

	// add ourselves as a tick prereq for the camera
	GetCamera()->PrimaryComponentTick.AddPrerequisite(PilotedRaft, PilotedRaft->PostPhysicsTickFunction);

	// check if the pawn started out with movement disabled
	PilotedRaft->SetInitialMovementDisabledState(GetMoverComponent()->IsMovementDisabled());
}

void ATitanPawn::DeInitRaft(ATitanRaft* PilotedRaft, bool bDismount)
{
	check(PilotedRaft);

	if (bDismount)
	{
		// change the movement mode on the pilot
		GetMoverComponent()->QueueNextMode(PilotedRaft->GetDismountMovementMode());

		// queue a jump layered move to dismount the raft
		TSharedPtr<FTitanLayeredMove_Jump> JumpMove = MakeShared<FTitanLayeredMove_Jump>();
		JumpMove->UpwardsSpeed = PilotedRaft->GetDismountImpulse();
		JumpMove->Momentum = PilotedRaft->GetDismountMomentum();

		GetMoverComponent()->QueueLayeredMove(JumpMove);

		// unsubscribe from the pilot's delegates
		OnJumped.RemoveDynamic(PilotedRaft, &ATitanRaft::OnJumpInput);
		OnMoved.RemoveDynamic(PilotedRaft, &ATitanRaft::OnMoveInput);
		OnMovementDisabledStateChanged.RemoveDynamic(PilotedRaft, &ATitanRaft::OnMovementDisabledStateChanged);
	}

	// enable collision
	SetActorEnableCollision(true);

	// remove ourselves as a tick prereq for the camera
	GetCamera()->PrimaryComponentTick.RemovePrerequisite(PilotedRaft, PilotedRaft->PostPhysicsTickFunction);

	// clear the reference to the raft
	CurrentRaft = nullptr;
}

void ATitanPawn::RaftPostPhysicsTick(float DeltaTime, ATitanRaft* PilotedRaft)
{
	// once the raft has updated, we tell Mover to teleport the Pawn to the pilot's spot
	// this prevents sync lag due to the raft and the Pawn updating on different threads and frequencies
	GetMoverComponent()->TeleportImmediately(PilotedRaft->GetPilotLocation(), PilotedRaft->GetPilotRotation(), PilotedRaft->GetPilotVelocity());
}

FVector ATitanPawn::GetPilotVelocity() const
{
	// pass the bounding capsule's velocity
	return GetRootComponent()->GetComponentVelocity();
}

FRotator ATitanPawn::GetPilotControlRotation() const
{
	// pass back the pawn's control rotation
	return GetControlRotation();
}

void ATitanPawn::SetWaterPlaneHeight(float Height, bool bEnable)
{
	// if we're on water, enable camera vertical min bounds so the camera stays above the water surface
	GetCamera()->SetCameraBoundsMinZ(bEnable, Height);
}

void ATitanPawn::AlignCameraToVector(const FVector& InFacing, float DeltaTime, float AlignSpeed)
{
	// get the camera right vector
	FVector CameraRight = Camera->GetViewRotation().RotateVector(FVector::RightVector);
	CameraRight = CameraRight.GetSafeNormal2D();

	// dot product with our right vector to get the yaw input strength
	float FacingDot = FVector::DotProduct(CameraRight, InFacing);

	// rotate the camera facing through a controller yaw input
	PC->AddYawInput(FacingDot * AlignSpeed * DeltaTime);
}

FTransform ATitanPawn::GetGliderLeftHandTransform_Implementation() const
{
	// stub, override from BP
	return FTransform::Identity;
}

FTransform ATitanPawn::GetGliderRightHandTransform_Implementation() const
{
	// stub, override from BP
	return FTransform::Identity;
}

FTransform ATitanPawn::GetGliderPelvisTransform_Implementation() const
{
	// stub, override from BP
	return FTransform::Identity;
}

FTransform ATitanPawn::GetGliderFeetTransform_Implementation() const
{
	// stub, override from BP
	return FTransform::Identity;
}

FTransform ATitanPawn::GetRaftLeftHandTransform_Implementation() const
{
	if (CurrentRaft)
	{
		return CurrentRaft->GetLeftHandTransform();
	}

	return FTransform::Identity;
}

FTransform ATitanPawn::GetRaftRightHandTransform_Implementation() const
{
	if (CurrentRaft)
	{
		return CurrentRaft->GetRightHandTransform();
	}

	return FTransform::Identity;
}

FTransform ATitanPawn::GetRaftLeftFootTransform_Implementation() const
{
	if (CurrentRaft)
	{
		return CurrentRaft->GetLeftFootTransform();
	}

	return FTransform::Identity;
}

FTransform ATitanPawn::GetRaftRightFootTransform_Implementation() const
{
	if (CurrentRaft)
	{
		return CurrentRaft->GetRightFootTransform();
	}

	return FTransform::Identity;
}

FTransform ATitanPawn::GetRaftPelvisTransform_Implementation() const
{
	if (CurrentRaft)
	{
		return CurrentRaft->GetPelvisTransform();
	}

	return FTransform::Identity;
}
