// Copyright Epic Games, Inc. All Rights Reserved.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Pawn.h"
#include "MoverSimulationTypes.h"
#include "AbilitySystemInterface.h"
#include "NativeGameplayTags.h"
#include "Engine/DataTable.h"
#include "TitanRaftActor.h"
#include "TitanCameraComponent.h"
#include "TitanPawn.generated.h"

// forward declarations
class UCapsuleComponent;
class USkeletalMeshComponent;
class UPoseableMeshComponent;
class UAnimMontage;

class UTitanMoverComponent;

class UEnhancedInputComponent;
class UInputAction;
struct FInputActionInstance;
struct FInputActionValue;
class UTitanInputEventSet;

class UTitanAbilitySystemComponent;
class UTitanAbilitySet;

class UTitanWaterDetectionComponent;
class UTitanSaveGame;
class ATitanPlayerController;
struct FTitanUserPreferences;

// movement mode event tags
UE_DECLARE_GAMEPLAY_TAG_EXTERN(TAG_Titan_Character_MovementModeChanged);

// delegates
DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FTitanPawn_OnMoved, FVector2D, MoveInput);
DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FTitanPawn_OnJumped, bool, bPressed);
DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FTitanPawn_OnMovementDisabledStateChanged, bool, bNewState);

DECLARE_DYNAMIC_MULTICAST_DELEGATE(FTitanPawn_MoverEvent);
DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FTitanPawn_MoverEvent_Target, FVector, Target);
DECLARE_DYNAMIC_MULTICAST_DELEGATE_TwoParams(FTitanPawn_MoverEvent_GrappleLocation, FVector, Target, bool, bIsValidGrapplePoint);
DECLARE_DYNAMIC_MULTICAST_DELEGATE_TwoParams(FTitanPawn_MoverEvent_GrappleGoal, FVector, Target, FVector, Normal);
DECLARE_DYNAMIC_MULTICAST_DELEGATE_TwoParams(FTitanPawn_MoverEvent_Raft, FVector, RaftVelocity, FVector, RaftUp);
DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FTitanPawn_MoverEvent_Magnitude, float, Magnitude);

/**
 *  ATitanPawn
 *  Base class for the Titan playable pawn.
 */
UCLASS(abstract, notplaceable)
class TITAN_API ATitanPawn : public APawn,
	public IAbilitySystemInterface,
	public IMoverInputProducerInterface,
	public ITitanRaftPilotInterface,
	public ITitanCameraOwnerInterface
{
	GENERATED_BODY()

public:
	
	/** Class constructor */
	ATitanPawn(const FObjectInitializer& ObjectInitializer);

	/////////////////////////////////////
	// Components
private:

	/** Player collision capsule */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Titan Pawn", meta = (AllowPrivateAccess = "true"))
	TObjectPtr<UCapsuleComponent> PlayerCapsule;

	/** Torso skeletal mesh. This will be the leader pose. */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Titan Pawn", meta = (AllowPrivateAccess = "true"))
	TObjectPtr <USkeletalMeshComponent> TorsoMesh;

	/** Head poseable mesh. This will copy its pose from the torso. */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Titan Pawn", meta = (AllowPrivateAccess = "true"))
	TObjectPtr <USkeletalMeshComponent> HeadMesh;

	/** Headwear poseable mesh. This will copy its pose from the torso. */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Titan Pawn", meta = (AllowPrivateAccess = "true"))
	TObjectPtr <USkeletalMeshComponent> HeadwearMesh;

	/** Legs poseable mesh. This will copy its pose from the torso. */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Titan Pawn", meta = (AllowPrivateAccess = "true"))
	TObjectPtr <USkeletalMeshComponent> LegsMesh;

	/** Glider skeletal mesh. Independent of the rest of the character. */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Titan Pawn", meta = (AllowPrivateAccess = "true"))
	TObjectPtr <USkeletalMeshComponent> GliderMesh;

	/** Player camera */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Titan Pawn", meta = (AllowPrivateAccess = "true"))
	TObjectPtr <UTitanCameraComponent> Camera;

	/** Ability System Component */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Titan Pawn", meta = (AllowPrivateAccess = "true"))
	TObjectPtr <UTitanAbilitySystemComponent> AbilitySystem;

	/** Water Detection Component */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "Titan Pawn", meta = (AllowPrivateAccess = "true"))
	TObjectPtr <UTitanWaterDetectionComponent> WaterDetection;

	/** Mover Component */
	UPROPERTY(Category = Movement, VisibleAnywhere, BlueprintReadOnly, meta = (AllowPrivateAccess = "true"))
	TObjectPtr <UTitanMoverComponent> CharacterMotionComponent;

public:

	/** public component getters */
	FORCEINLINE UCapsuleComponent* GetPlayerCapsule() const { return PlayerCapsule; }
	FORCEINLINE USkeletalMeshComponent* GetTorsoMesh() const { return TorsoMesh; }
	FORCEINLINE USkeletalMeshComponent* GetHeadMesh() const { return HeadMesh; }
	FORCEINLINE USkeletalMeshComponent* GetHeadwearMesh() const { return HeadwearMesh; }
	FORCEINLINE USkeletalMeshComponent* GetLegsMesh() const { return LegsMesh; }
	FORCEINLINE UTitanCameraComponent* GetCamera() const { return Camera; }

	/** Accessor for the Mover component */
	UFUNCTION(BlueprintPure, Category = Mover)
	UTitanMoverComponent* GetMoverComponent() const { return CharacterMotionComponent; }

protected:

	/** BeginPlay initialization */
	virtual void BeginPlay() override;

	/** PostInitializeComponents initialization */
	virtual void PostInitializeComponents() override;

	/** PossessedBy initialization */
	virtual void PossessedBy(AController* NewController) override;

	/** UnPossesed cleanup */
	virtual void UnPossessed() override;

	/** BP handler called after the pawn is possessed and all possess initialization is complete */
	UFUNCTION(BlueprintImplementableEvent, Category="Titan")
	void OnPawnInitialized(ATitanPlayerController* PlayerController);

public:	

	/** Tick */
	virtual void Tick(float DeltaTime) override;

protected:

	/** Reference to the PlayerController that possesses this pawn */
	TObjectPtr<ATitanPlayerController> PC;

	/////////////////////////////////////
	// Input

protected:

	/** Move Input Action */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category ="Input")
	TObjectPtr <UInputAction> MoveAction;

	/** Look Input Action */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category ="Input")
	TObjectPtr <UInputAction> LookAction;

	/** Jump Input Action */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category ="Input")
	TObjectPtr<UInputAction> JumpAction;

	/** Auto walk Input Action */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category ="Input")
	TObjectPtr<UInputAction> AutoWalkAction;

	/** Camera distance adjustment Input Action */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category ="Input")
	TObjectPtr<UInputAction> CameraDistanceAction;

public:
	/** Setup player input */
	virtual void SetupPlayerInputComponent(class UInputComponent* PlayerInputComponent) override;

protected:

	/** Called for movement input */
	void Move(const FInputActionValue& Value);
	void MoveCompleted(const FInputActionValue& Value);

	/** Called for looking input */
	void Look(const FInputActionValue& Value);
	void LookCompleted(const FInputActionValue& Value);

	/** Called when the player wants to jump */
	void Jump();

	/** Called when the player wants to stop jumping */
	void StopJumping();

	/** Called for autorun input */
	void AutoWalk();

	/** Called for camera distance adjust input */
	void AdjustCameraDistance(const FInputActionValue& Value);

	/** Called to add wind speed to the Mover inputs */
	UFUNCTION(BlueprintCallable, Category="Titan|Input")
	void AddWind(const FVector& Wind);

public:

	/** Called when the player wants to sprint */
	UFUNCTION(BlueprintCallable, Category="Titan|Input")
	void Sprint();

	/** Called when the player wants to stop sprinting */
	UFUNCTION(BlueprintCallable, Category="Titan|Input")
	void StopSprinting();

	/** Called when the player wants to glide */
	UFUNCTION(BlueprintCallable, Category="Titan|Input")
	void Glide();

	/** Called when the player wants to stop gliding */
	UFUNCTION(BlueprintCallable, Category="Titan|Input")
	void StopGliding();

	/** Called when the player wants to aim */
	UFUNCTION(BlueprintCallable, Category="Titan|Input")
	void Aim();

	/** Called when the player wants to stop aiming */
	UFUNCTION(BlueprintCallable, Category="Titan|Input")
	void StopAiming();

	// indirect input delegates other Actors can subscribe to
public:

	/** Move input delegate */
	UPROPERTY(BlueprintAssignable, Category="Input");
	FTitanPawn_OnMoved OnMoved;

	/** Jump input delegate */
	UPROPERTY(BlueprintAssignable, Category="Input");
	FTitanPawn_OnJumped OnJumped;
	
protected:

	/** Input Event Set to grant for triggering Gameplay Abilities */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category ="Input")
	TObjectPtr<UTitanInputEventSet> InputEventSet;

	/** Input Event Map holding all translated input events and their triggering actions */
	TMap<const UInputAction*, FGameplayTag> InputEventMap;

public:
	/** Binds an input event set to an enhanced input component */
	void BindInputEventSet(const UTitanInputEventSet* EventSet, UEnhancedInputComponent* EnhancedInputComponent);

	/** Binds an input action to a gameplay event */
	void BindInputEvent(const UInputAction* InputAction, FGameplayTag EventTag, UEnhancedInputComponent* EnhancedInputComponent);

	/** Clears all input events for an enhanced input component */
	void ClearInputEvents(UEnhancedInputComponent* EnhancedInputComponent);

protected:
	/** Ability input event handlers */
	void HandleInputPressed(const FInputActionInstance& ActionInstance);
	void HandleInputOngoing(const FInputActionInstance& ActionInstance);
	void HandleInputReleased(const FInputActionInstance& ActionInstance);


	/////////////////////////////////////
	// Mover Interface

protected:

	virtual UPrimitiveComponent* GetMovementBase() const override;

private:

	/* last nonzero movement intent input */
	FVector LastAffirmativeMoveInput = FVector::ZeroVector;

	/* cached move variables */
	FVector CachedMoveInputIntent = FVector::ZeroVector;
	FRotator CachedTurnInput = FRotator::ZeroRotator;
	FRotator CachedLookInput = FRotator::ZeroRotator;

	/* cached jump variables */
	bool bWantsToJump = false;
	bool bIsJumpPressed = false;

	/** cached sprint variables */
	bool bWantsToSprint = false;
	bool bIsSprintPressed = false;

	/** cached glide variables */
	bool bWantsToGlide = false;
	bool bIsGlidePressed = false;

	/** cached aim variables */
	bool bIsAimPressed = false;

	/** cached wind velocity */
	FVector WindVelocity;

	bool bWantsToAutoWalk = false;

	/** Set to true if a teleport is queued */
	bool bTeleportQueued = false;

	/** Set to true when the teleport target location is preloaded by WP */
	bool bCompletedPreloadingTeleport = false;

	/** Set to true when the pre-teleport animation has completed */
	bool bCompletedTeleportAnimation = false;

	/** Cached teleport target location */
	FVector QueuedTeleportLocation;

protected:

	/** Anim montage to play while teleporting */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category ="Titan|Mover")
	TObjectPtr<UAnimMontage> TeleportMontage;

	/** Teleport montage section to play while looping the preload */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category ="Titan|Mover")
	FName TeleportLoopSection;

	/** Teleport montage section to play when exiting the teleport */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category ="Titan|Mover")
	FName TeleportEndSection;

	/** Max distance to extend the grapple aim sweep */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category ="Titan|Mover")
	float GrappleAimDistance = 2000.0f;
	
	/** Multiplies the grapple aim sweep distance. Set from developer preferences. */
	float GrappleAimMultiplier = 1.0f;

public:

	/** Called when the character starts sprinting */
	UPROPERTY(BlueprintAssignable, BlueprintCallable, Category="Titan Events")
	FTitanPawn_MoverEvent OnSprintStarted;

	/** Called when the character stops sprinting */
	UPROPERTY(BlueprintAssignable, BlueprintCallable, Category="Titan Events")
	FTitanPawn_MoverEvent OnSprintEnded;

	/** Called when the character becomes exhausted */
	UPROPERTY(BlueprintAssignable, BlueprintCallable, Category="Titan Events")
	FTitanPawn_MoverEvent OnExhausted;

	/** Called when the character recovers from exhaustion */
	UPROPERTY(BlueprintAssignable, BlueprintCallable, Category="Titan Events")
	FTitanPawn_MoverEvent OnExhaustRecovered;

	/** Called when the character starts gliding */
	UPROPERTY(BlueprintAssignable, BlueprintCallable, Category="Titan Events")
	FTitanPawn_MoverEvent OnGlideStarted;

	/** Called when the character stops gliding */
	UPROPERTY(BlueprintAssignable, BlueprintCallable, Category="Titan Events")
	FTitanPawn_MoverEvent OnGlideEnded;

	/** Called when the character starts a soft landing */
	UPROPERTY(BlueprintAssignable, BlueprintCallable, Category="Titan Events")
	FTitanPawn_MoverEvent OnSoftLand;

	/** Called when the character finishes a soft landing */
	UPROPERTY(BlueprintAssignable, BlueprintCallable, Category="Titan Events")
	FTitanPawn_MoverEvent OnSoftLandEnded;

	/** Called when the character lands on ground. Receives the vertical speed prior to landing */
	UPROPERTY(BlueprintAssignable, BlueprintCallable, Category="Titan Events")
	FTitanPawn_MoverEvent_Magnitude OnLanded;

	/** Called when the character starts aiming the grapple */
	UPROPERTY(BlueprintAssignable, BlueprintCallable, Category="Titan Events")
	FTitanPawn_MoverEvent OnGrappleAimStarted;

	/** Called when the character stops aiming the grapple */
	UPROPERTY(BlueprintAssignable, BlueprintCallable, Category="Titan Events")
	FTitanPawn_MoverEvent OnGrappleAimEnded;

	/** Called while the character aims the grapple */
	UPROPERTY(BlueprintAssignable, BlueprintCallable, Category="Titan Events")
	FTitanPawn_MoverEvent_GrappleLocation OnGrappleAimUpdate;

	/** Called when the character fires the grapple and starts moving towards the target */
	UPROPERTY(BlueprintAssignable, BlueprintCallable, Category="Titan Events")
	FTitanPawn_MoverEvent_GrappleGoal OnGrappleFire;

	/** Called while the character finishes grapple movement */
	UPROPERTY(BlueprintAssignable, BlueprintCallable, Category="Titan Events")
	FTitanPawn_MoverEvent OnGrappleEnded;

	/** Called when the character arrives at the grapple destination normally */
	UPROPERTY(BlueprintAssignable, BlueprintCallable, Category="Titan Events")
	FTitanPawn_MoverEvent_GrappleGoal OnGrappleArrival;

	/** Called when the character starts grapple boosting */
	UPROPERTY(BlueprintAssignable, BlueprintCallable, Category="Titan Events")
	FTitanPawn_MoverEvent OnGrappleBoost;

	/** Called when the character jumps at the end of a grapple boost */
	UPROPERTY(BlueprintAssignable, BlueprintCallable, Category="Titan Events")
	FTitanPawn_MoverEvent OnGrappleJump;

	/** Called when the character starts riding the raft */
	UPROPERTY(BlueprintAssignable, BlueprintCallable, Category="Titan Events")
	FTitanPawn_MoverEvent OnRaftStarted;

	/** Called when the character finishes riding the raft */
	UPROPERTY(BlueprintAssignable, BlueprintCallable, Category="Titan Events")
	FTitanPawn_MoverEvent OnRaftEnded;

	/** Called while the character is moving on the raft */
	UPROPERTY(BlueprintAssignable, BlueprintCallable, Category="Titan Events")
	FTitanPawn_MoverEvent_Raft OnRaftUpdate;

	/** Called when movement is enabled or disabled */
	UPROPERTY(BlueprintAssignable, Category="Titan|Mover");
	FTitanPawn_OnMovementDisabledStateChanged OnMovementDisabledStateChanged;

public:

	/* Request the character starts moving with an intended directional magnitude. A length of 1 indicates maximum acceleration. */
	UFUNCTION(BlueprintCallable, Category="Titan|Mover")
	virtual void RequestMoveByIntent(const FVector& DesiredIntent);

	/* Request the character starts moving with a desired velocity. This will be used in lieu of any other input. */
	UFUNCTION(BlueprintCallable, Category="Titan|Mover")
	virtual void RequestMoveByVelocity(const FVector& DesiredVelocity);

	/** Returns the current stamina value */
	UFUNCTION(BlueprintPure, Category="Titan|Mover")
	float GetStamina() const;

	/** Returns the current stamina percentage */
	UFUNCTION(BlueprintPure, Category="Titan|Mover")
	float GetStaminaPercent() const;

	/** Returns true if stamina was depleted and the pawn is recovering */
	UFUNCTION(BlueprintPure, Category="Titan|Mover")
	bool IsExhausted() const;

	/** Returns true if the pawn has the exact leaf movement tag */
	UFUNCTION(BlueprintPure, Category="Titan|Mover")
	bool HasMovementTagExact(const FGameplayTag& Tag);

	/** Returns true if the pawn has the movement tag as part of its hierarchy */
	UFUNCTION(BlueprintPure, Category=Titan)
	bool HasMovementTagAny(const FGameplayTag& Tag);

	/** Queues a teleport, accounting for Mover and World Partition */
	UFUNCTION(BlueprintCallable, Category="Titan|Mover")
	void QueueTeleportMove(const FVector& TeleportLocation);

	/** Returns true when the character is ready to teleport to a preloaded WP location */
	UFUNCTION(BlueprintCallable, Category="Titan|Mover")
	bool IsTeleporting() const;

	/** Called by the teleport animation when the character ready to teleport  */
	UFUNCTION(BlueprintCallable, Category="Titan|Mover")
	void OnTeleportAnimationReady();

	/** Called by the teleport animation to trigger the exit state of the teleport montage */
	UFUNCTION(BlueprintCallable, Category="Titan|Mover")
	void CheckTeleportReady();

	/** Disables or re-enables movement at the Mover Component level */
	UFUNCTION(BlueprintCallable, Category="Titan|Mover")
	void SetMovementDisabled(bool bNewDisabledState);

	/** Returns the scaled grapple aim distance */
	UFUNCTION(BlueprintPure, Category="Titan|Mover")
	float GetGrappleAimDistance() const { return GrappleAimDistance * GrappleAimMultiplier; }

	/** Sets the grapple aim distance multiplier */
	UFUNCTION(BlueprintCallable, Category="Titan|Mover")
	void SetGrappleAimDistanceMultiplier(float Multiplier) { GrappleAimMultiplier = Multiplier; }

protected:

	/** Called when the WP region we want to teleport to is ready */
	UFUNCTION()
	void OnTeleportPreloadReady();

	/** Finalizes the teleport process */
	void FinalizeTeleport();

	/** Allows the character to react to movement mode changes */
	UFUNCTION()
	void OnMovementModeChanged(const FName& PreviousModeName, const FName& NewModeName);

	/* Entry point for input production. */
	virtual void ProduceInput_Implementation(int32 SimTimeMs, FMoverInputCmdContext& InputCmdResult) override;

	/////////////////////////////////////
	// Ability System Interface

protected:

	/** Ability Set to grant to the pawn on initialization */
	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Abilities")
	TObjectPtr<UTitanAbilitySet> AbilitySet;

	/** Ensures Ability Sets are only granted upon first Possess only */
	bool bInitializedAbilities = false;

public:
	/* Implement IAbilitySystemInterface*/
	virtual UAbilitySystemComponent* GetAbilitySystemComponent() const override;

	/////////////////////////////////////
	// Camera Controls

protected:

	/** Scaling factor for camera yaw rotation */
	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Camera|Controls")
	float CameraRotationRateYaw = 100.0f;

	/** Scaling factor for camera pitch rotation */
	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Camera|Controls")
	float CameraRotationRatePitch = 100.0f;

	/** Last cached input time. Used to calculate time elapsed for camera auto align */
	float CameraAutoAlignLastInputTime = 0.0f;

	/** Time elapsed without input before the camera auto align kicks in */
	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Camera|Auto Alignment")
	float CameraAutoAlignTime = 3.0f;

	/** Speed at which the camera should auto align due to idling */
	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Camera|Auto Alignment")
	float CameraAutoAlignSpeed = 25.0f;

	/** If true, camera auto align override values will be used instead */
	bool bOverrideCameraAutoAlign = false;

	/** Override auto align time */
	float OverrideCameraAutoAlignTime = 0.0f;

	/** Override auto align speed */
	float OverrideCameraAutoAlignSpeed = 10.0f;

	/** Attempts to align the camera yaw towards the pawn's facing direction through move inputs */
	void AlignCameraToFacing(float DeltaTime, float AlignSpeed);

	/** Returns true if the camera should be automatically aligned to the pawn's facing direction */
	bool ShouldAutoAlignCamera();

	/** Updates the cached input time to determine camera auto alignment timeout */
	void UpdateCameraAutoAlignInputTime();

public:

	/** Enables or disables camera auto-align */
	virtual void SetCameraAutoAlignState(bool bEnable, float AutoAlignTime, float AutoAlignSpeed) override;

protected:

	/** If true, the camera will be automatically turn to align towards the character when moving sideways */
	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Camera|Auto Alignment")
	bool bAlignCameraOnMovement = true;

	/** Speed at which the camera should auto align due to movement */
	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Camera|Auto Alignment")
	float CameraMovementAlignSpeed = 25.0f;

	/** Returns true if the camera should be automatically aligned to the pawn's facing direction as a result of movement */
	bool ShouldAlignCameraOnMovement();

	/////////////////////////////////////
	// Raft

	/** Pointer to the current raft the pawn is riding */
	TObjectPtr<ATitanRaft> CurrentRaft;

public:

	/** Returns a pointer to the current raft if any */
	UFUNCTION(BlueprintPure, Category="Titan|Raft")
	const ATitanRaft* GetRaft() const;

	//~ Begin ITitanRaftPilotInterface interface

	/** Initializes the pilot for the raft they're piloting */
	virtual void InitializeRaft(ATitanRaft* PilotedRaft) override;

	/** De-initializes the pilot and restores movement functionality */
	virtual void DeInitRaft(ATitanRaft* PilotedRaft, bool bDismount) override;

	/** Updates the pilot when the raft's post physics tick is called */
	virtual void RaftPostPhysicsTick(float DeltaTime, ATitanRaft* PilotedRaft) override;

	/** Returns the pilot's current velocity */
	virtual FVector GetPilotVelocity() const override;

	/** Returns the pilot's control rotation */
	virtual FRotator GetPilotControlRotation() const override;

	/** Sets the height of the camera clipping plane so it stays above water */
	virtual void SetWaterPlaneHeight(float Height, bool bEnable) override;

	virtual void AlignCameraToVector(const FVector& InFacing, float DeltaTime, float AlignSpeed) override;

	//~ End ITitanRaftPilotInterface interface


	/////////////////////////////////////
	// Glider

public:

	/** Blueprint overrideable event to return the IK target Transform for the glider's left hand */
	UFUNCTION(BlueprintNativeEvent, BlueprintPure, Category="Titan|Glider")
	FTransform GetGliderLeftHandTransform() const;

	/** Blueprint overrideable event to return the IK target Transform for the glider's right hand */
	UFUNCTION(BlueprintNativeEvent, BlueprintPure, Category="Titan|Glider")
	FTransform GetGliderRightHandTransform() const;

	/** Blueprint overrideable event to return the IK target Transform for the glider's pelvis socket */
	UFUNCTION(BlueprintNativeEvent, BlueprintPure, Category="Titan|Glider")
	FTransform GetGliderPelvisTransform() const;

	/** Blueprint overrideable event to return the IK target Transform for the glider's feet target socket */
	UFUNCTION(BlueprintNativeEvent, BlueprintPure, Category="Titan|Glider")
	FTransform GetGliderFeetTransform() const;

	/** Blueprint overrideable event to return the IK target Transform for the raft's left hand */
	UFUNCTION(BlueprintNativeEvent, BlueprintPure, Category="Titan|Raft")
	FTransform GetRaftLeftHandTransform() const;

	/** Blueprint overrideable event to return the IK target Transform for the raft's right hand */
	UFUNCTION(BlueprintNativeEvent, BlueprintPure, Category="Titan|Raft")
	FTransform GetRaftRightHandTransform() const;

	/** Blueprint overrideable event to return the IK target Transform for the raft's left foot */
	UFUNCTION(BlueprintNativeEvent, BlueprintPure, Category="Titan|Raft")
	FTransform GetRaftLeftFootTransform() const;

	/** Blueprint overrideable event to return the IK target Transform for the raft's right foot */
	UFUNCTION(BlueprintNativeEvent, BlueprintPure, Category="Titan|Raft")
	FTransform GetRaftRightFootTransform() const;

	/** Blueprint overrideable event to return the IK target Transform for the raft's pelvis socket */
	UFUNCTION(BlueprintNativeEvent, BlueprintPure, Category="Titan|Raft")
	FTransform GetRaftPelvisTransform() const;
};
