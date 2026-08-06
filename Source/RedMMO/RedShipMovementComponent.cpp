#include "RedShipMovementComponent.h"

#include "CollisionQueryParams.h"
#include "CollisionShape.h"
#include "Components/BoxComponent.h"
#include "Components/PrimitiveComponent.h"
#include "Curves/CurveFloat.h"
#include "Engine/HitResult.h"
#include "Engine/OverlapResult.h"
#include "Engine/ScopedMovementUpdate.h"
#include "Engine/World.h"
#include "GameFramework/Controller.h"
#include "GameFramework/Pawn.h"
#include "RedGravityBodies.h"
#include "RedPlanetTerrainQuery.h"

DEFINE_LOG_CATEGORY(LogRedShip);

namespace
{
constexpr float RedShipNoAltitude = 1.0e12f;
constexpr float RedShipPassiveTerrainProbeIntervalSeconds = 0.1f;
constexpr float RedShipPassiveTerrainMaxSpeedCmPerSecond = 1.0f;
constexpr float RedShipTranslationEnvelopePullbackCm = 2.0f;
constexpr float RedShipAngularEnvelopeMaxTotalDegrees = 6.0f;
constexpr float RedShipAngularEnvelopeMaxSegmentDegrees = 2.0f;
constexpr float RedShipAngularEnvelopePaddingCm = 0.5f;
constexpr int32 RedShipAngularEnvelopeMaxSegments = 3;
constexpr float RedShipPlacementRouteMaxTranslationCm = 10000.0f;
constexpr int32 RedShipPlacementRouteMaxSegments = 90;
constexpr float RedShipSurfaceRecoveryMaxTranslationCm = 10000.0f;
constexpr float RedShipMinSpeedCap = 100.0f; // 1 m/s — never fully freeze the ship
}

URedShipMovementComponent::URedShipMovementComponent()
{
	PrimaryComponentTick.bCanEverTick = true;
}

void URedShipMovementComponent::TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction)
{
	if (ShouldSkipUpdate(DeltaTime))
	{
		return;
	}

	Super::TickComponent(DeltaTime, TickType, ThisTickFunction);

	if (!PawnOwner || !UpdatedComponent)
	{
		return;
	}

	// Multi-body: altitude/auto-level/surface-clamp all follow the DOMINANT gravity body (GravityCore
	// volumes — near a moon, the moon wins). In deep space between volumes the query fails and we
	// HOLD the last body, so altitude keeps growing and space handling stays engaged.
	{
		RedGravity::FBodyQueryResult Body;
		if (RedGravity::QueryDominantBodyDetailed(
			GetWorld(), UpdatedComponent->GetComponentLocation(), CurrentGravityBodyId,
			GravityBodySwitchHysteresis, Body))
		{
			CurrentGravityBodyId = Body.StableId;
			PlanetCenter = Body.Center;
			if (Body.SurfaceRadius > 0.f)
			{
				PlanetRadius = Body.SurfaceRadius;
			}
		}
	}

	TryResolvePassiveTerrainPenetration();
	ClampToPlanetSurface();

	const AController* Controller = PawnOwner->GetController();
	if (!Controller || !Controller->IsLocalController())
	{
		return;
	}

	LastMoveInput = PendingMoveInput.GetClampedToMaxSize(1.0f);
	LastRotationInput = FVector(
		FMath::Clamp(PendingRotationInput.X, -1.0f, 1.0f),
		FMath::Clamp(PendingRotationInput.Y, -1.0f, 1.0f),
		FMath::Clamp(PendingRotationInput.Z, -1.0f, 1.0f));
	bBoostActive = bPendingBoostInput;
	PendingMoveInput = FVector::ZeroVector;
	PendingRotationInput = FVector::ZeroVector;
	bPendingBoostInput = false;

	const float AltitudeAGL = GetAltitudeAGL();
	UpdateFlightMode(AltitudeAGL);

	float TargetMaxSpeed = EvaluateAltitudeSpeedCap(AltitudeAGL);
	if (!bInAtmosphere)
	{
		TargetMaxSpeed *= FMath::Max(1.f, SpaceSpeedMultiplier);
	}
	if (bBoostActive)
	{
		TargetMaxSpeed *= BoostSpeedMultiplier;
	}
	TargetMaxSpeed = FMath::Min(TargetMaxSpeed, FMath::Max(RedShipMinSpeedCap, AbsoluteMaxSpeed));

	const float GovernorCap = ExternalSpeedCap.IsBound() ? ExternalSpeedCap.Execute() : 0.0f;
	const bool bGovernorActive = (GovernorCap > 0.0f) && (GovernorCap < TargetMaxSpeed);
	if (bGovernorActive)
	{
		TargetMaxSpeed = GovernorCap;
	}
	bGovernorEngaged = bGovernorActive;

	TargetMaxSpeed = FMath::Max(TargetMaxSpeed, RedShipMinSpeedCap);
	CurrentMaxSpeed = (CurrentMaxSpeed < 0.0f)
		? TargetMaxSpeed
		: FMath::FInterpTo(CurrentMaxSpeed, TargetMaxSpeed, DeltaTime, SpeedCapInterpRate);

	const FQuat CurrentQuat = UpdatedComponent->GetComponentQuat();
	const FQuat NewRotation = ComputeNewRotation(CurrentQuat, LastRotationInput, DeltaTime);

	const FVector DesiredVelocity = NewRotation.RotateVector(LastMoveInput) * CurrentMaxSpeed;
	const float Responsiveness = bInAtmosphere
		? ResponsivenessAtmosphere
		: ResponsivenessSpace * FMath::Max(1.f, SpaceAccelerationMultiplier);
	Velocity = ComputeNewVelocity(Velocity, DesiredVelocity, Responsiveness, CurrentMaxSpeed, DeltaTime);

	const FVector Delta = Velocity * DeltaTime;
	const bool bRotationChanged = !NewRotation.Equals(CurrentQuat);
	if (!Delta.IsNearlyZero(1e-6f) || bRotationChanged)
	{
		MoveWithPlanetCollision(Delta, NewRotation, DeltaTime);
	}
	else
	{
		ClampToPlanetSurface();
		UpdateComponentVelocity();
	}
}

float URedShipMovementComponent::GetMaxSpeed() const
{
	return (CurrentMaxSpeed >= 0.0f) ? CurrentMaxSpeed : FallbackMaxSpeed;
}

bool URedShipMovementComponent::ResolvePenetrationImpl(const FVector& Adjustment, const FHitResult& Hit, const FQuat& NewRotationQuat)
{
	const ETranslationEnvelopeOverlapMode PendingMode =
		PendingTranslationEnvelopeOverlapMode;
	UPrimitiveComponent* PendingHitComponent =
		PendingTranslationEnvelopeHitComponent.Get();
	const FVector PendingRootStart = PendingTranslationEnvelopeRootStart;
	const FQuat PendingRootRotation = PendingTranslationEnvelopeRootRotation;
	ClearPendingTranslationEnvelopePenetration();

	if (PendingMode != ETranslationEnvelopeOverlapMode::None)
	{
		UWorld* World = GetWorld();
		UBoxComponent* Envelope = TranslationCollisionEnvelope.Get();
		const bool bPendingSignatureMatches = World
			&& PawnOwner
			&& UpdatedPrimitive
			&& Envelope
			&& Envelope != UpdatedPrimitive
			&& Envelope->GetOwner() == PawnOwner
			&& Envelope->IsRegistered()
			&& Envelope->IsPhysicsStateCreated()
			&& Envelope->IsQueryCollisionEnabled()
			&& Envelope->IsAttachedTo(UpdatedPrimitive)
			&& Hit.bBlockingHit
			&& Hit.bStartPenetrating
			&& Hit.GetComponent() == PendingHitComponent
			&& UpdatedPrimitive->GetComponentLocation().Equals(PendingRootStart, 0.01f)
			&& Hit.TraceStart.Equals(PendingRootStart, 0.01f)
			&& ((PendingMode == ETranslationEnvelopeOverlapMode::NativeDeferred
					&& UpdatedPrimitive->GetComponentQuat().Equals(
						PendingRootRotation, 1.0e-6f))
				|| (NewRotationQuat.Equals(PendingRootRotation, 1.0e-6f)
					&& NewRotationQuat.Equals(
						UpdatedPrimitive->GetComponentQuat(), 1.0e-6f)));
		if (!bPendingSignatureMatches)
		{
			// A child-envelope token may only ever be consumed by that exact child pose. Falling
			// back to the superclass here would depenetrate the oversized root sphere instead.
			return false;
		}

		// Native fitted-body overlaps are surfaced truthfully at time zero but remain fail-closed.
		// Combining multiple native MTDs is a separate gate; the oversized root sphere must never
		// be allowed to substitute its own recovery for the fitted body.
		if (PendingMode == ETranslationEnvelopeOverlapMode::NativeDeferred)
		{
			return false;
		}

		if (bResolvingTranslationEnvelopePenetration)
		{
			return false;
		}

		const FCollisionShape EnvelopeShape = Envelope->GetCollisionShape();
		const FVector EnvelopeStart = Envelope->GetComponentLocation();
		const FQuat EnvelopeRotation = Envelope->GetComponentQuat();
		FHitResult CurrentExactHit(1.0f);
		const ERedPlanetTerrainQueryResult CurrentExactResult =
			RedPlanetTerrainQuery::Sweep(
				World,
				PlanetCenter,
				EnvelopeStart,
				EnvelopeStart,
				EnvelopeRotation,
				EnvelopeShape,
				CurrentExactHit);
		const bool bFiniteExactNormal =
			FMath::IsFinite(CurrentExactHit.Normal.X)
			&& FMath::IsFinite(CurrentExactHit.Normal.Y)
			&& FMath::IsFinite(CurrentExactHit.Normal.Z)
			&& !CurrentExactHit.Normal.IsNearlyZero();
		const bool bExactOverlapReproduced =
			CurrentExactResult == ERedPlanetTerrainQueryResult::Hit
			&& CurrentExactHit.bBlockingHit
			&& CurrentExactHit.bStartPenetrating
			&& CurrentExactHit.GetComponent() == PendingHitComponent
			&& FMath::IsFinite(CurrentExactHit.PenetrationDepth)
			&& CurrentExactHit.PenetrationDepth > UE_KINDA_SMALL_NUMBER
			&& bFiniteExactNormal
			&& FMath::IsNearlyEqual(
				CurrentExactHit.PenetrationDepth, Hit.PenetrationDepth, 0.05f)
			&& FVector::DotProduct(
				CurrentExactHit.Normal.GetSafeNormal(), Hit.Normal.GetSafeNormal()) > 0.999f;
		if (!bExactOverlapReproduced)
		{
			return false;
		}

		const FVector RecoveryNormal = CurrentExactHit.Normal.GetSafeNormal();
		const FVector ProposedAdjustment = ConstrainDirectionToPlane(Adjustment);
		const FVector RecoveryAdjustment = ConstrainDirectionToPlane(
			RecoveryNormal
				* (CurrentExactHit.PenetrationDepth
					+ RedShipTranslationEnvelopePullbackCm));
		const float MaxBoundedAdjustment =
			EnvelopeShape.GetExtent().GetMax() * 2.0f
			+ RedShipTranslationEnvelopePullbackCm;
		const bool bValidRecoveryAdjustment =
			!ProposedAdjustment.ContainsNaN()
			&& FMath::IsFinite(ProposedAdjustment.X)
			&& FMath::IsFinite(ProposedAdjustment.Y)
			&& FMath::IsFinite(ProposedAdjustment.Z)
			&& !ProposedAdjustment.IsNearlyZero()
			&& FVector::DotProduct(
				ProposedAdjustment.GetSafeNormal(), RecoveryNormal) > 0.999f
			&& !RecoveryAdjustment.ContainsNaN()
			&& FMath::IsFinite(RecoveryAdjustment.X)
			&& FMath::IsFinite(RecoveryAdjustment.Y)
			&& FMath::IsFinite(RecoveryAdjustment.Z)
			&& !RecoveryAdjustment.IsNearlyZero()
			&& RecoveryAdjustment.Size() <= MaxBoundedAdjustment;
		if (!bValidRecoveryAdjustment)
		{
			return false;
		}

		const FVector RootStart = UpdatedPrimitive->GetComponentLocation();
		const FVector CandidateRoot = RootStart + RecoveryAdjustment;
		const FVector CandidateEnvelope = EnvelopeStart + RecoveryAdjustment;
		const bool bRootNativeEncroached = OverlapTest(
			CandidateRoot,
			NewRotationQuat,
			UpdatedPrimitive->GetCollisionObjectType(),
			UpdatedPrimitive->GetCollisionShape(0.1f),
			PawnOwner);

		FComponentQueryParams EnvelopeOverlapParams(
			SCENE_QUERY_STAT(RedShipTranslationEnvelopeRecoveryNative), PawnOwner);
		FCollisionResponseParams EnvelopeOverlapResponseParams;
		Envelope->InitSweepCollisionParams(
			EnvelopeOverlapParams, EnvelopeOverlapResponseParams);
		EnvelopeOverlapParams.bIgnoreTouches = true;
		TArray<FOverlapResult> CandidateNativeOverlaps;
		World->ComponentOverlapMulti(
			CandidateNativeOverlaps,
			Envelope,
			CandidateEnvelope,
			EnvelopeRotation,
			EnvelopeOverlapParams);
		const bool bEnvelopeNativeEncroached =
			CandidateNativeOverlaps.ContainsByPredicate(
				[](const FOverlapResult& Candidate)
				{
					return Candidate.bBlockingHit;
				});

		FHitResult CandidateExactHit(1.0f);
		const ERedPlanetTerrainQueryResult CandidateExactResult =
			RedPlanetTerrainQuery::Sweep(
				World,
				PlanetCenter,
				CandidateEnvelope,
				CandidateEnvelope,
				EnvelopeRotation,
				EnvelopeShape,
				CandidateExactHit);
		const bool bCandidateExactClear =
			CandidateExactResult == ERedPlanetTerrainQueryResult::NoHit
			&& !CandidateExactHit.bBlockingHit
			&& !CandidateExactHit.bStartPenetrating;
		if (bRootNativeEncroached
			|| bEnvelopeNativeEncroached
			|| !bCandidateExactClear)
		{
			return false;
		}

		TGuardValue<bool> ResolvingGuard(
			bResolvingTranslationEnvelopePenetration, true);
		const bool bCorrectionMoved = Super::MoveUpdatedComponentImpl(
			RecoveryAdjustment,
			NewRotationQuat,
			false,
			nullptr,
			ETeleportType::TeleportPhysics);
		const FVector CorrectedRoot = UpdatedPrimitive->GetComponentLocation();
		const FVector CorrectedEnvelope = Envelope->GetComponentLocation();
		const bool bCorrectionSynchronized = bCorrectionMoved
			&& CorrectedRoot.Equals(CandidateRoot, 0.05f)
			&& CorrectedEnvelope.Equals(CandidateEnvelope, 0.05f);

		FHitResult PostExactHit(1.0f);
		const ERedPlanetTerrainQueryResult PostExactResult =
			RedPlanetTerrainQuery::Sweep(
				World,
				PlanetCenter,
				CorrectedEnvelope,
				CorrectedEnvelope,
				Envelope->GetComponentQuat(),
				EnvelopeShape,
				PostExactHit);
		TArray<FOverlapResult> PostNativeOverlaps;
		World->ComponentOverlapMulti(
			PostNativeOverlaps,
			Envelope,
			CorrectedEnvelope,
			Envelope->GetComponentQuat(),
			EnvelopeOverlapParams);
		const bool bPostEnvelopeNativeEncroached =
			PostNativeOverlaps.ContainsByPredicate(
				[](const FOverlapResult& Candidate)
				{
					return Candidate.bBlockingHit;
				});
		const bool bPostRootNativeEncroached = OverlapTest(
			CorrectedRoot,
			NewRotationQuat,
			UpdatedPrimitive->GetCollisionObjectType(),
			UpdatedPrimitive->GetCollisionShape(0.1f),
			PawnOwner);
		const bool bPostClear = bCorrectionSynchronized
			&& PostExactResult == ERedPlanetTerrainQueryResult::NoHit
			&& !PostExactHit.bBlockingHit
			&& !PostExactHit.bStartPenetrating
			&& !bPostEnvelopeNativeEncroached
			&& !bPostRootNativeEncroached;
		if (!bPostClear)
		{
			if (bCorrectionMoved)
			{
				Super::MoveUpdatedComponentImpl(
					-RecoveryAdjustment,
					NewRotationQuat,
					false,
					nullptr,
					ETeleportType::TeleportPhysics);
			}
			return false;
		}

		bPositionCorrected = true;
		// SafeMove retries its original request exactly once after a successful correction. If
		// that retry unexpectedly starts penetrated, surface the hit but do not leave an
		// unconsumable second token behind after SafeMove returns.
		bSuppressNextTranslationEnvelopeOverlapToken = true;
		return true;
	}

	const bool bResolved = Super::ResolvePenetrationImpl(Adjustment, Hit, NewRotationQuat);
	bPositionCorrected |= bResolved;
	return bResolved;
}

void URedShipMovementComponent::ClearPendingTranslationEnvelopePenetration()
{
	PendingTranslationEnvelopeOverlapMode = ETranslationEnvelopeOverlapMode::None;
	PendingTranslationEnvelopeHitComponent.Reset();
	PendingTranslationEnvelopeRootStart = FVector::ZeroVector;
	PendingTranslationEnvelopeRootRotation = FQuat::Identity;
}

bool URedShipMovementComponent::TryResolvePassiveTerrainPenetration()
{
	// The fitted body is authoritative whenever it is live. The legacy passive sphere probe is
	// intentionally disabled in that state so an idle fighter cannot be popped by its hidden
	// 260 cm root. Fitted-body passive recovery is a later, separately tested response gate.
	if (UBoxComponent* Envelope = TranslationCollisionEnvelope.Get();
		Envelope
		&& UpdatedPrimitive
		&& Envelope != UpdatedPrimitive
		&& Envelope->GetOwner() == PawnOwner
		&& Envelope->IsRegistered()
		&& Envelope->IsPhysicsStateCreated()
		&& Envelope->IsQueryCollisionEnabled()
		&& Envelope->IsAttachedTo(UpdatedPrimitive))
	{
		return false;
	}

	UWorld* World = GetWorld();
	if (!World
		|| !PawnOwner
		|| !PawnOwner->HasAuthority()
		|| PawnOwner->GetAttachParentActor()
		|| !UpdatedPrimitive
		|| UpdatedPrimitive->Mobility != EComponentMobility::Movable
		|| !UpdatedPrimitive->IsQueryCollisionEnabled()
		|| PlanetRadius <= 0.0f
		|| (PawnOwner->GetController()
			&& Velocity.SizeSquared()
				> FMath::Square(RedShipPassiveTerrainMaxSpeedCmPerSecond))
		|| bResolvingPassiveTerrainPenetration)
	{
		return false;
	}

	const double WorldSeconds = World->GetTimeSeconds();
	if (WorldSeconds < NextPassiveTerrainProbeWorldSeconds)
	{
		return false;
	}
	NextPassiveTerrainProbeWorldSeconds =
		WorldSeconds + RedShipPassiveTerrainProbeIntervalSeconds;

	const FCollisionShape RootShape = UpdatedPrimitive->GetCollisionShape();
	if (!RootShape.IsSphere() && !RootShape.IsCapsule())
	{
		return false;
	}

	const FVector Location = UpdatedPrimitive->GetComponentLocation();
	const FQuat Rotation = UpdatedPrimitive->GetComponentQuat();
	FHitResult TerrainHit(1.0f);
	const ERedPlanetTerrainQueryResult TerrainResult = RedPlanetTerrainQuery::Sweep(
		World,
		PlanetCenter,
		Location,
		Location,
		Rotation,
		RootShape,
		TerrainHit);
	if (TerrainResult != ERedPlanetTerrainQueryResult::Hit
		|| !TerrainHit.bBlockingHit
		|| !TerrainHit.bStartPenetrating
		|| !FMath::IsFinite(TerrainHit.PenetrationDepth)
		|| TerrainHit.PenetrationDepth <= UE_KINDA_SMALL_NUMBER
		|| TerrainHit.Normal.ContainsNaN()
		|| TerrainHit.Normal.IsNearlyZero())
	{
		return false;
	}

	const FVector Adjustment = GetPenetrationAdjustment(TerrainHit);
	const float MaxBoundedAdjustment = RootShape.GetExtent().GetMax() * 2.0f + 1.0f;
	if (Adjustment.ContainsNaN()
		|| !FMath::IsFinite(Adjustment.X)
		|| !FMath::IsFinite(Adjustment.Y)
		|| !FMath::IsFinite(Adjustment.Z)
		|| Adjustment.IsNearlyZero()
		|| Adjustment.Size() > MaxBoundedAdjustment)
	{
		return false;
	}

	TGuardValue<bool> ResolvingGuard(bResolvingPassiveTerrainPenetration, true);
	const bool bResolved = ResolvePenetration(Adjustment, TerrainHit, Rotation);
	if (bResolved)
	{
		// An unpossessed ship returns before normal velocity integration. Clear any stale
		// pre-unpossess flight velocity once its stationary root has been corrected.
		if (!PawnOwner->GetController())
		{
			Velocity = FVector::ZeroVector;
		}
		UpdateComponentVelocity();
		PawnOwner->ForceNetUpdate();
		UE_LOG(LogRedShip, Verbose,
			TEXT("%s: passively resolved exact-terrain penetration depth=%.3f cm adjustment=%.3f cm"),
			*GetNameSafe(PawnOwner), TerrainHit.PenetrationDepth, Adjustment.Size());
	}
	return bResolved;
}

void URedShipMovementComponent::SetTranslationCollisionEnvelope(UBoxComponent* InEnvelope)
{
	ClearPendingTranslationEnvelopePenetration();
	TranslationCollisionEnvelope = InEnvelope
		&& InEnvelope->GetOwner() == GetOwner()
		? InEnvelope
		: nullptr;
}

UBoxComponent* URedShipMovementComponent::GetTranslationCollisionEnvelope() const
{
	return TranslationCollisionEnvelope.Get();
}

bool URedShipMovementComponent::TryCommitClearPlacement(
	const FVector& TargetRootLocation,
	const FQuat& TargetRootRotation,
	const bool bRequireMatchingPlanet,
	const ETeleportType Teleport)
{
	UWorld* World = GetWorld();
	UBoxComponent* Envelope = TranslationCollisionEnvelope.Get();
	auto IsFiniteNormalizedQuat = [](const FQuat& Quat)
	{
		return FMath::IsFinite(Quat.X)
			&& FMath::IsFinite(Quat.Y)
			&& FMath::IsFinite(Quat.Z)
			&& FMath::IsFinite(Quat.W)
			&& !Quat.ContainsNaN()
			&& Quat.IsNormalized();
	};

	const bool bPlacementReady = World
		&& PawnOwner
		&& UpdatedComponent
		&& UpdatedPrimitive
		&& UpdatedPrimitive->GetOwner() == PawnOwner
		&& UpdatedPrimitive->GetMobility() == EComponentMobility::Movable
		&& UpdatedPrimitive->IsRegistered()
		&& UpdatedPrimitive->IsPhysicsStateCreated()
		&& UpdatedPrimitive->IsQueryCollisionEnabled()
		&& Envelope
		&& Envelope != UpdatedPrimitive
		&& Envelope->GetOwner() == PawnOwner
		&& Envelope->IsRegistered()
		&& Envelope->IsPhysicsStateCreated()
		&& Envelope->IsQueryCollisionEnabled()
		&& Envelope->GetAttachParent() == UpdatedPrimitive
		&& !Envelope->IsUsingAbsoluteLocation()
		&& !Envelope->IsUsingAbsoluteRotation()
		&& !Envelope->IsUsingAbsoluteScale()
		&& !PlanetCenter.ContainsNaN()
		&& FMath::IsFinite(PlanetRadius)
		&& PlanetRadius > 0.0f
		&& !TargetRootLocation.ContainsNaN()
		&& IsFiniteNormalizedQuat(TargetRootRotation);
	if (!bPlacementReady)
	{
		return false;
	}

	const FCollisionShape RootShape = UpdatedPrimitive->GetCollisionShape();
	const FCollisionShape EnvelopeShape = Envelope->GetCollisionShape();
	if (!RootShape.IsSphere() || !EnvelopeShape.IsBox())
	{
		return false;
	}

	const FTransform CurrentRootTransform = UpdatedPrimitive->GetComponentTransform();
	const FVector RootStart = CurrentRootTransform.GetLocation();
	const FQuat CurrentRootRotation = CurrentRootTransform.GetRotation();
	const FVector PlacementDelta = TargetRootLocation - RootStart;
	const FVector ConstrainedPlacementDelta =
		ConstrainDirectionToPlane(PlacementDelta);
	const float PlacementDistance = PlacementDelta.Size();
	if (RootStart.ContainsNaN()
		|| !IsFiniteNormalizedQuat(CurrentRootRotation)
		|| PlacementDelta.ContainsNaN()
		|| !FMath::IsFinite(PlacementDistance)
		|| PlacementDistance > RedShipPlacementRouteMaxTranslationCm
		|| !ConstrainedPlacementDelta.Equals(PlacementDelta, 0.01f))
	{
		return false;
	}
	const float PlacementAngleDegrees = FMath::RadiansToDegrees(
		CurrentRootRotation.AngularDistance(TargetRootRotation));
	if (!FMath::IsFinite(PlacementAngleDegrees))
	{
		return false;
	}
	const int32 PlacementSegmentCount = FMath::Max(
		1,
		FMath::CeilToInt(
			PlacementAngleDegrees / RedShipAngularEnvelopeMaxSegmentDegrees));
	if (PlacementSegmentCount < 1
		|| PlacementSegmentCount > RedShipPlacementRouteMaxSegments)
	{
		return false;
	}
	FQuat RouteTargetRootRotation = TargetRootRotation;
	if ((CurrentRootRotation | RouteTargetRootRotation) < 0.0f)
	{
		RouteTargetRootRotation = FQuat(
			-RouteTargetRootRotation.X,
			-RouteTargetRootRotation.Y,
			-RouteTargetRootRotation.Z,
			-RouteTargetRootRotation.W);
	}
	const FVector RootToEnvelopeScaledLocal =
		CurrentRootRotation.UnrotateVector(
			Envelope->GetComponentLocation() - RootStart);
	const FQuat EnvelopeRelativeRotation = (
		CurrentRootRotation.Inverse() * Envelope->GetComponentQuat()).GetNormalized();
	const FVector TargetEnvelopeLocation =
		TargetRootLocation
		+ TargetRootRotation.RotateVector(RootToEnvelopeScaledLocal);
	const FQuat TargetEnvelopeRotation = (
		TargetRootRotation * EnvelopeRelativeRotation).GetNormalized();
	if (RootToEnvelopeScaledLocal.ContainsNaN()
		|| TargetEnvelopeLocation.ContainsNaN()
		|| !IsFiniteNormalizedQuat(TargetEnvelopeRotation))
	{
		return false;
	}

	FComponentQueryParams EnvelopeNativeParams(
		SCENE_QUERY_STAT(RedShipClearPlacementEnvelopeNative), PawnOwner);
	FCollisionResponseParams EnvelopeResponseParams;
	Envelope->InitSweepCollisionParams(
		EnvelopeNativeParams, EnvelopeResponseParams);
	EnvelopeNativeParams.bTraceComplex = true;
	EnvelopeNativeParams.bFindInitialOverlaps = true;
	EnvelopeNativeParams.bReturnFaceIndex = true;
	EnvelopeNativeParams.bIgnoreTouches = true;

	FComponentQueryParams RootNativeParams(
		SCENE_QUERY_STAT(RedShipClearPlacementRootNative), PawnOwner);
	FCollisionResponseParams RootResponseParams;
	UpdatedPrimitive->InitSweepCollisionParams(
		RootNativeParams, RootResponseParams);
	RootNativeParams.bFindInitialOverlaps = true;
	RootNativeParams.bReturnFaceIndex = true;
	RootNativeParams.bIgnoreTouches = true;

	auto HasBlockingRouteHit = [](const TArray<FHitResult>& Hits)
	{
		return Hits.ContainsByPredicate([](const FHitResult& Candidate)
		{
			return Candidate.bBlockingHit || Candidate.bStartPenetrating;
		});
	};

	// The root is a sphere, so one component sweep proves its complete native
	// translation route regardless of the fitted hull's changing orientation.
	TArray<FHitResult> RootRouteHits;
	World->ComponentSweepMulti(
		RootRouteHits,
		UpdatedPrimitive,
		RootStart,
		TargetRootLocation,
		CurrentRootRotation,
		RootNativeParams);
	if (HasBlockingRouteHit(RootRouteHits))
	{
		return false;
	}

	const bool bPlacementRotationChanged =
		!CurrentRootRotation.Equals(TargetRootRotation, 1.0e-6f);
	if (!bPlacementRotationChanged)
	{
		TArray<FHitResult> EnvelopeRouteHits;
		World->ComponentSweepMulti(
			EnvelopeRouteHits,
			Envelope,
			Envelope->GetComponentLocation(),
			TargetEnvelopeLocation,
			Envelope->GetComponentQuat(),
			EnvelopeNativeParams);
		FHitResult ExactRouteHit(1.0f);
		const ERedPlanetTerrainQueryResult ExactRouteResult =
			RedPlanetTerrainQuery::Sweep(
				World,
				PlanetCenter,
				Envelope->GetComponentLocation(),
				TargetEnvelopeLocation,
				Envelope->GetComponentQuat(),
				EnvelopeShape,
				ExactRouteHit);
		const bool bExactRouteRejected =
			ExactRouteResult == ERedPlanetTerrainQueryResult::Hit
			|| (bRequireMatchingPlanet
				&& ExactRouteResult
					== ERedPlanetTerrainQueryResult::NoMatchingPlanet)
			|| ExactRouteHit.bBlockingHit
			|| ExactRouteHit.bStartPenetrating;
		if (HasBlockingRouteHit(EnvelopeRouteHits) || bExactRouteRejected)
		{
			return false;
		}
	}
	else
	{
		// Approximate the complete shortest-path screw motion with conservative
		// two-degree box corridors. The padding is the maximum pivot-corner arc
		// deviation inside each segment, so a blocker cannot hide between samples.
		const FTransform EnvelopeStartTransform =
			Envelope->GetComponentTransform();
		double PivotCornerRadiusCm = 0.0;
		const FVector UnscaledBoxExtent = Envelope->GetUnscaledBoxExtent();
		for (int32 CornerIndex = 0; CornerIndex < 8; ++CornerIndex)
		{
			const FVector LocalCorner(
				(CornerIndex & 1) ? UnscaledBoxExtent.X : -UnscaledBoxExtent.X,
				(CornerIndex & 2) ? UnscaledBoxExtent.Y : -UnscaledBoxExtent.Y,
				(CornerIndex & 4) ? UnscaledBoxExtent.Z : -UnscaledBoxExtent.Z);
			PivotCornerRadiusCm = FMath::Max(
				PivotCornerRadiusCm,
				FVector::Distance(
					RootStart,
					EnvelopeStartTransform.TransformPosition(LocalCorner)));
		}
		const FVector ScaledBoxExtent = Envelope->GetScaledBoxExtent();
		const bool bValidEnvelopeBounds =
			FMath::IsFinite(PivotCornerRadiusCm)
			&& PivotCornerRadiusCm > UE_KINDA_SMALL_NUMBER
			&& !ScaledBoxExtent.ContainsNaN()
			&& ScaledBoxExtent.X > UE_KINDA_SMALL_NUMBER
			&& ScaledBoxExtent.Y > UE_KINDA_SMALL_NUMBER
			&& ScaledBoxExtent.Z > UE_KINDA_SMALL_NUMBER;
		if (!bValidEnvelopeBounds)
		{
			return false;
		}

		for (int32 SegmentIndex = 0;
			SegmentIndex < PlacementSegmentCount;
			++SegmentIndex)
		{
			const float Alpha0 =
				static_cast<float>(SegmentIndex) / PlacementSegmentCount;
			const float Alpha1 =
				static_cast<float>(SegmentIndex + 1) / PlacementSegmentCount;
			const float AlphaMid = (Alpha0 + Alpha1) * 0.5f;
			const FQuat RootRotation0 = FQuat::Slerp(
				CurrentRootRotation,
				RouteTargetRootRotation,
				Alpha0).GetNormalized();
			const FQuat RootRotation1 = FQuat::Slerp(
				CurrentRootRotation,
				RouteTargetRootRotation,
				Alpha1).GetNormalized();
			const FQuat RootRotationMid = FQuat::Slerp(
				CurrentRootRotation,
				RouteTargetRootRotation,
				AlphaMid).GetNormalized();
			const FVector EnvelopeLocation0 =
				RootStart + PlacementDelta * Alpha0
				+ RootRotation0.RotateVector(RootToEnvelopeScaledLocal);
			const FVector EnvelopeLocation1 =
				RootStart + PlacementDelta * Alpha1
				+ RootRotation1.RotateVector(RootToEnvelopeScaledLocal);
			const FQuat EnvelopeRotationMid = (
				RootRotationMid * EnvelopeRelativeRotation).GetNormalized();
			const float SegmentAngleRadians =
				RootRotation0.AngularDistance(RootRotation1);
			const float RotationPaddingCm = static_cast<float>(
				2.0 * PivotCornerRadiusCm
					* FMath::Sin(SegmentAngleRadians * 0.25))
				+ RedShipAngularEnvelopePaddingCm;
			if (!FMath::IsFinite(RotationPaddingCm)
				|| RotationPaddingCm < 0.0f)
			{
				return false;
			}
			const FCollisionShape ProxyShape = FCollisionShape::MakeBox(
				ScaledBoxExtent + FVector(RotationPaddingCm));

			TArray<FHitResult> ProxyNativeHits;
			World->SweepMultiByChannel(
				ProxyNativeHits,
				EnvelopeLocation0,
				EnvelopeLocation1,
				EnvelopeRotationMid,
				Envelope->GetCollisionObjectType(),
				ProxyShape,
				EnvelopeNativeParams,
				EnvelopeResponseParams);
			FHitResult ProxyExactHit(1.0f);
			const ERedPlanetTerrainQueryResult ProxyExactResult =
				RedPlanetTerrainQuery::Sweep(
					World,
					PlanetCenter,
					EnvelopeLocation0,
					EnvelopeLocation1,
					EnvelopeRotationMid,
					ProxyShape,
					ProxyExactHit);
			const bool bProxyExactRejected =
				ProxyExactResult == ERedPlanetTerrainQueryResult::Hit
				|| (bRequireMatchingPlanet
					&& ProxyExactResult
						== ERedPlanetTerrainQueryResult::NoMatchingPlanet)
				|| ProxyExactHit.bBlockingHit
				|| ProxyExactHit.bStartPenetrating;
			if (HasBlockingRouteHit(ProxyNativeHits)
				|| bProxyExactRejected)
			{
				return false;
			}
		}
	}

	FScopedMovementUpdate ScopedMove(
		UpdatedComponent, EScopedUpdate::DeferredUpdates);
	FHitResult PlacementHit(1.0f);
	const bool bPoseChanged = !RootStart.Equals(TargetRootLocation, 0.01f)
		|| !CurrentRootRotation.Equals(TargetRootRotation, 1.0e-6f);
	const bool bMoveReported = Super::MoveUpdatedComponentImpl(
		PlacementDelta,
		TargetRootRotation,
		false,
		&PlacementHit,
		Teleport);

	// Attached-child transforms can be stale inside a deferred scope, so all endpoint probes use
	// the analytically composed target fitted-envelope pose rather than cached component state.
	const bool bPostEnvelopeNativeBlocked =
		World->OverlapBlockingTestByChannel(
			TargetEnvelopeLocation,
			TargetEnvelopeRotation,
			Envelope->GetCollisionObjectType(),
			EnvelopeShape,
			EnvelopeNativeParams,
			EnvelopeResponseParams);
	const bool bPostRootNativeBlocked =
		World->OverlapBlockingTestByChannel(
			TargetRootLocation,
			TargetRootRotation,
			UpdatedPrimitive->GetCollisionObjectType(),
			RootShape,
			RootNativeParams,
			RootResponseParams);
	FHitResult PostExactHit(1.0f);
	const ERedPlanetTerrainQueryResult PostExactResult =
		RedPlanetTerrainQuery::Sweep(
			World,
			PlanetCenter,
			TargetEnvelopeLocation,
			TargetEnvelopeLocation,
			TargetEnvelopeRotation,
			EnvelopeShape,
			PostExactHit);
	const bool bPostExactClear =
		(PostExactResult == ERedPlanetTerrainQueryResult::NoHit
			|| (!bRequireMatchingPlanet
				&& PostExactResult == ERedPlanetTerrainQueryResult::NoMatchingPlanet))
		&& !PostExactHit.bBlockingHit
		&& !PostExactHit.bStartPenetrating;
	const bool bTargetPoseReached = (!bPoseChanged || bMoveReported)
		&& !PlacementHit.bBlockingHit
		&& !PlacementHit.bStartPenetrating
		&& UpdatedPrimitive->GetComponentLocation().Equals(TargetRootLocation, 0.05f)
		&& UpdatedPrimitive->GetComponentQuat().Equals(
			TargetRootRotation, 1.0e-6f);
	if (!bTargetPoseReached
		|| bPostEnvelopeNativeBlocked
		|| bPostRootNativeBlocked
		|| !bPostExactClear)
	{
		ScopedMove.RevertMove();
		return false;
	}

	return true;
}

bool URedShipMovementComponent::MoveUpdatedComponentImpl(
	const FVector& Delta,
	const FQuat& NewRotation,
	const bool bSweep,
	FHitResult* OutHit,
	const ETeleportType Teleport)
{
	bAngularEnvelopeMoveVetoed = false;
	const bool bSuppressOverlapTokenForThisMove =
		bSuppressNextTranslationEnvelopeOverlapToken;
	bSuppressNextTranslationEnvelopeOverlapToken = false;
	if (!bResolvingTranslationEnvelopePenetration)
	{
		ClearPendingTranslationEnvelopePenetration();
	}

	const FVector ConstrainedDelta = ConstrainDirectionToPlane(Delta);
	if (!bSweep || !UpdatedPrimitive)
	{
		return Super::MoveUpdatedComponentImpl(Delta, NewRotation, bSweep, OutHit, Teleport);
	}
	UBoxComponent* Envelope = TranslationCollisionEnvelope.Get();
	const FQuat CurrentRootRotation = UpdatedPrimitive->GetComponentQuat();
	const bool bRotationChanged = !NewRotation.Equals(CurrentRootRotation, 1.0e-6f);
	const bool bConfiguredAngularEnvelope = bRotationChanged && Envelope;
	if ((!UpdatedPrimitive->IsQueryCollisionEnabled() || PlanetRadius <= 0.0f)
		&& !bConfiguredAngularEnvelope)
	{
		return Super::MoveUpdatedComponentImpl(Delta, NewRotation, bSweep, OutHit, Teleport);
	}

	const FCollisionShape RootShape = UpdatedPrimitive->GetCollisionShape();
	if (!RootShape.IsSphere() && !RootShape.IsCapsule())
	{
		if (bConfiguredAngularEnvelope)
		{
			bAngularEnvelopeMoveVetoed = true;
			if (OutHit)
			{
				*OutHit = FHitResult(1.0f);
			}
			return false;
		}
		return Super::MoveUpdatedComponentImpl(Delta, NewRotation, bSweep, OutHit, Teleport);
	}

	const FVector TraceStart = UpdatedPrimitive->GetComponentLocation();
	const FVector TraceEnd = TraceStart + ConstrainedDelta;
	const float FullDistance = ConstrainedDelta.Size();
	const bool bEnvelopeReady = Envelope
		&& Envelope != UpdatedPrimitive
		&& Envelope->GetOwner() == PawnOwner
		&& Envelope->IsRegistered()
		&& Envelope->IsPhysicsStateCreated()
		&& Envelope->IsQueryCollisionEnabled()
		&& Envelope->IsAttachedTo(UpdatedPrimitive);
	const bool bFixedRotationEnvelopeReady = bEnvelopeReady && !bRotationChanged;
	if (bRotationChanged && Envelope)
	{
		// UE/Chaos sweeps a primitive at one fixed orientation and applies the requested
		// rotation unswept. A fitted child box therefore needs an explicit conservative
		// screw-motion corridor before the sphere root may commit translation + rotation.
		bAngularEnvelopeMoveVetoed = true;
		if (OutHit)
		{
			*OutHit = FHitResult(1.0f);
		}

		auto IsFiniteQuat = [](const FQuat& Quat)
		{
			return FMath::IsFinite(Quat.X)
				&& FMath::IsFinite(Quat.Y)
				&& FMath::IsFinite(Quat.Z)
				&& FMath::IsFinite(Quat.W)
				&& !Quat.ContainsNaN();
		};
		auto PublishAngularVeto =
			[this, OutHit, TraceStart, TraceEnd](const FHitResult* SourceHit)
			{
				if (OutHit)
				{
					*OutHit = SourceHit ? *SourceHit : FHitResult(1.0f);
					if (SourceHit)
					{
						OutHit->bBlockingHit = true;
						OutHit->bStartPenetrating = false;
						OutHit->PenetrationDepth = 0.0f;
						OutHit->Time = 0.0f;
						OutHit->Distance = 0.0f;
						OutHit->TraceStart = TraceStart;
						OutHit->TraceEnd = TraceEnd;
						OutHit->Location = TraceStart;
						OutHit->ImpactPoint = TraceStart;
					}
				}
				return false;
			};
		auto PublishAngularStartOverlap =
			[this,
				OutHit,
				TraceStart,
				TraceEnd,
				CurrentRootRotation,
				bSuppressOverlapTokenForThisMove](const FHitResult& SourceHit)
			{
				if (OutHit)
				{
					*OutHit = SourceHit;
					OutHit->bBlockingHit = true;
					OutHit->bStartPenetrating = true;
					OutHit->Time = 0.0f;
					OutHit->Distance = 0.0f;
					OutHit->TraceStart = TraceStart;
					OutHit->TraceEnd = TraceEnd;
					OutHit->Location = TraceStart;
					OutHit->ImpactPoint = TraceStart;
					if (!bSuppressOverlapTokenForThisMove)
					{
						PendingTranslationEnvelopeOverlapMode =
							ETranslationEnvelopeOverlapMode::NativeDeferred;
						PendingTranslationEnvelopeHitComponent =
							SourceHit.GetComponent();
						PendingTranslationEnvelopeRootStart = TraceStart;
						PendingTranslationEnvelopeRootRotation =
							CurrentRootRotation;
					}
				}
				return false;
			};

		UWorld* World = GetWorld();
		const bool bRigidDirectEnvelope = bEnvelopeReady
			&& Envelope->GetAttachParent() == UpdatedPrimitive
			&& !Envelope->IsUsingAbsoluteLocation()
			&& !Envelope->IsUsingAbsoluteRotation()
			&& !Envelope->IsUsingAbsoluteScale();
		const bool bValidQuaternions = IsFiniteQuat(CurrentRootRotation)
			&& IsFiniteQuat(NewRotation)
			&& CurrentRootRotation.IsNormalized()
			&& NewRotation.IsNormalized();
		const float TotalAngleRadians = bValidQuaternions
			? CurrentRootRotation.AngularDistance(NewRotation)
			: TNumericLimits<float>::Max();
		const float TotalAngleDegrees = FMath::RadiansToDegrees(TotalAngleRadians);
		const int32 SegmentCount = FMath::CeilToInt(
			TotalAngleDegrees / RedShipAngularEnvelopeMaxSegmentDegrees);
		const FCollisionShape EnvelopeShape = Envelope->GetCollisionShape();
		const bool bSupportedAngularRequest = World
			&& bRigidDirectEnvelope
			&& RootShape.IsSphere()
			&& EnvelopeShape.IsBox()
			&& !ConstrainedDelta.ContainsNaN()
			&& bValidQuaternions
			&& FMath::IsFinite(TotalAngleRadians)
			&& TotalAngleDegrees > UE_KINDA_SMALL_NUMBER
			&& TotalAngleDegrees
				<= RedShipAngularEnvelopeMaxTotalDegrees + 1.0e-3f
			&& SegmentCount >= 1
			&& SegmentCount <= RedShipAngularEnvelopeMaxSegments;
		if (!bSupportedAngularRequest)
		{
			return PublishAngularVeto(nullptr);
		}

		FComponentQueryParams EnvelopeNativeParams(
			SCENE_QUERY_STAT(RedShipAngularEnvelopeNative), PawnOwner);
		FCollisionResponseParams EnvelopeResponseParams;
		Envelope->InitSweepCollisionParams(
			EnvelopeNativeParams, EnvelopeResponseParams);
		EnvelopeNativeParams.bTraceComplex = true;
		EnvelopeNativeParams.bFindInitialOverlaps = true;
		EnvelopeNativeParams.bReturnFaceIndex = true;
		EnvelopeNativeParams.bIgnoreTouches = true;

		// Reproduce actual start overlaps with the real component so SafeMove never derives
		// an MTD from the inflated corridor proxy or from the oversized sphere root.
		TArray<FHitResult> ActualEnvelopeStartHits;
		World->ComponentSweepMulti(
			ActualEnvelopeStartHits,
			Envelope,
			Envelope->GetComponentLocation(),
			Envelope->GetComponentLocation() + ConstrainedDelta,
			Envelope->GetComponentQuat(),
			EnvelopeNativeParams);
		const FHitResult* ActualNativeStartOverlap =
			ActualEnvelopeStartHits.FindByPredicate([](const FHitResult& Candidate)
			{
				return Candidate.bBlockingHit && Candidate.bStartPenetrating;
			});
		if (ActualNativeStartOverlap)
		{
			return PublishAngularStartOverlap(*ActualNativeStartOverlap);
		}

		FHitResult ActualExactStartHit(1.0f);
		const ERedPlanetTerrainQueryResult ActualExactStartResult =
			RedPlanetTerrainQuery::Sweep(
				World,
				PlanetCenter,
				Envelope->GetComponentLocation(),
				Envelope->GetComponentLocation(),
				Envelope->GetComponentQuat(),
				EnvelopeShape,
				ActualExactStartHit);
		if (ActualExactStartResult == ERedPlanetTerrainQueryResult::Hit
			&& ActualExactStartHit.bBlockingHit
			&& ActualExactStartHit.bStartPenetrating)
		{
			return PublishAngularStartOverlap(ActualExactStartHit);
		}

		// Preflight the complete native root route. The later engine move must never clip
		// translation at an earlier root contact and then apply the full target rotation.
		FComponentQueryParams RootNativeParams(
			SCENE_QUERY_STAT(RedShipAngularRootNative), PawnOwner);
		FCollisionResponseParams RootResponseParams;
		UpdatedPrimitive->InitSweepCollisionParams(
			RootNativeParams, RootResponseParams);
		RootNativeParams.bFindInitialOverlaps = true;
		RootNativeParams.bReturnFaceIndex = true;
		RootNativeParams.bIgnoreTouches = true;
		TArray<FHitResult> RootNativeHits;
		World->ComponentSweepMulti(
			RootNativeHits,
			UpdatedPrimitive,
			TraceStart,
			TraceEnd,
			CurrentRootRotation,
			RootNativeParams);
		const FHitResult* RootNativeHit = RootNativeHits.FindByPredicate(
			[](const FHitResult& Candidate)
			{
				return Candidate.bBlockingHit;
			});
		if (RootNativeHit)
		{
			return PublishAngularVeto(RootNativeHit);
		}

		const FTransform EnvelopeStartTransform = Envelope->GetComponentTransform();
		const FVector RootToEnvelopeLocal = CurrentRootRotation.UnrotateVector(
			EnvelopeStartTransform.GetLocation() - TraceStart);
		const FQuat EnvelopeRelativeRotation = (
			CurrentRootRotation.Inverse()
				* EnvelopeStartTransform.GetRotation()).GetNormalized();

		double PivotCornerRadiusCm = 0.0;
		const FVector UnscaledBoxExtent = Envelope->GetUnscaledBoxExtent();
		for (int32 CornerIndex = 0; CornerIndex < 8; ++CornerIndex)
		{
			const FVector LocalCorner(
				(CornerIndex & 1) ? UnscaledBoxExtent.X : -UnscaledBoxExtent.X,
				(CornerIndex & 2) ? UnscaledBoxExtent.Y : -UnscaledBoxExtent.Y,
				(CornerIndex & 4) ? UnscaledBoxExtent.Z : -UnscaledBoxExtent.Z);
			const FVector WorldCorner =
				EnvelopeStartTransform.TransformPosition(LocalCorner);
			PivotCornerRadiusCm = FMath::Max(
				PivotCornerRadiusCm,
				FVector::Distance(TraceStart, WorldCorner));
		}
		if (!FMath::IsFinite(PivotCornerRadiusCm)
			|| PivotCornerRadiusCm <= UE_KINDA_SMALL_NUMBER)
		{
			return PublishAngularVeto(nullptr);
		}

		FQuat TargetRootRotation = NewRotation;
		if ((CurrentRootRotation | TargetRootRotation) < 0.0f)
		{
			TargetRootRotation = FQuat(
				-TargetRootRotation.X,
				-TargetRootRotation.Y,
				-TargetRootRotation.Z,
				-TargetRootRotation.W);
		}
		const FVector ScaledBoxExtent = Envelope->GetScaledBoxExtent();
		for (int32 SegmentIndex = 0; SegmentIndex < SegmentCount; ++SegmentIndex)
		{
			const float Alpha0 = static_cast<float>(SegmentIndex) / SegmentCount;
			const float Alpha1 = static_cast<float>(SegmentIndex + 1) / SegmentCount;
			const float AlphaMid = (Alpha0 + Alpha1) * 0.5f;
			const FQuat RootRotation0 = FQuat::Slerp(
				CurrentRootRotation, TargetRootRotation, Alpha0).GetNormalized();
			const FQuat RootRotation1 = FQuat::Slerp(
				CurrentRootRotation, TargetRootRotation, Alpha1).GetNormalized();
			const FQuat RootRotationMid = FQuat::Slerp(
				CurrentRootRotation, TargetRootRotation, AlphaMid).GetNormalized();
			const FVector EnvelopeLocation0 =
				FMath::Lerp(TraceStart, TraceEnd, Alpha0)
					+ RootRotation0.RotateVector(RootToEnvelopeLocal);
			const FVector EnvelopeLocation1 =
				FMath::Lerp(TraceStart, TraceEnd, Alpha1)
					+ RootRotation1.RotateVector(RootToEnvelopeLocal);
			const FQuat EnvelopeRotationMid = (
				RootRotationMid * EnvelopeRelativeRotation).GetNormalized();
			const float SegmentAngleRadians =
				RootRotation0.AngularDistance(RootRotation1);
			const float RotationPaddingCm = static_cast<float>(
				2.0 * PivotCornerRadiusCm
					* FMath::Sin(SegmentAngleRadians * 0.25))
				+ RedShipAngularEnvelopePaddingCm;
			const FCollisionShape ProxyShape = FCollisionShape::MakeBox(
				ScaledBoxExtent + FVector(RotationPaddingCm));

			TArray<FHitResult> ProxyNativeHits;
			World->SweepMultiByChannel(
				ProxyNativeHits,
				EnvelopeLocation0,
				EnvelopeLocation1,
				EnvelopeRotationMid,
				Envelope->GetCollisionObjectType(),
				ProxyShape,
				EnvelopeNativeParams,
				EnvelopeResponseParams);
			const FHitResult* ProxyNativeHit = ProxyNativeHits.FindByPredicate(
				[](const FHitResult& Candidate)
				{
					return Candidate.bBlockingHit;
				});

			FHitResult ProxyExactHit(1.0f);
			const ERedPlanetTerrainQueryResult ProxyExactResult =
				RedPlanetTerrainQuery::Sweep(
					World,
					PlanetCenter,
					EnvelopeLocation0,
					EnvelopeLocation1,
					EnvelopeRotationMid,
					ProxyShape,
					ProxyExactHit);
			const bool bProxyExactHit =
				ProxyExactResult == ERedPlanetTerrainQueryResult::Hit
				&& (ProxyExactHit.bBlockingHit
					|| ProxyExactHit.bStartPenetrating);
			if (ProxyNativeHit || bProxyExactHit)
			{
				const FHitResult* LimitingHit = ProxyNativeHit;
				if (bProxyExactHit
					&& (!LimitingHit || ProxyExactHit.Time < LimitingHit->Time))
				{
					LimitingHit = &ProxyExactHit;
				}
				return PublishAngularVeto(LimitingHit);
			}
		}

		const FVector TargetEnvelopeLocation = TraceEnd
			+ TargetRootRotation.RotateVector(RootToEnvelopeLocal);
		const FQuat TargetEnvelopeRotation = (
			TargetRootRotation * EnvelopeRelativeRotation).GetNormalized();
		FScopedMovementUpdate ScopedMove(
			UpdatedComponent, EScopedUpdate::DeferredUpdates);
		FHitResult NativeMoveHit(1.0f);
		const bool bMoved = Super::MoveUpdatedComponentImpl(
			ConstrainedDelta,
			TargetRootRotation,
			true,
			&NativeMoveHit,
			Teleport);

		// Deferred scoped moves do not guarantee attached-child cached transforms have
		// propagated yet, so endpoint probes use the analytically composed target pose.
		const bool bPostEnvelopeNativeBlocked =
			World->OverlapBlockingTestByChannel(
				TargetEnvelopeLocation,
				TargetEnvelopeRotation,
				Envelope->GetCollisionObjectType(),
				EnvelopeShape,
				EnvelopeNativeParams,
				EnvelopeResponseParams);
		FHitResult PostExactHit(1.0f);
		const ERedPlanetTerrainQueryResult PostExactResult =
			RedPlanetTerrainQuery::Sweep(
				World,
				PlanetCenter,
				TargetEnvelopeLocation,
				TargetEnvelopeLocation,
				TargetEnvelopeRotation,
				EnvelopeShape,
				PostExactHit);
		const bool bPostExactClear =
			PostExactResult != ERedPlanetTerrainQueryResult::Hit
			&& !PostExactHit.bBlockingHit
			&& !PostExactHit.bStartPenetrating;
		const bool bPostRootNativeBlocked =
			World->OverlapBlockingTestByChannel(
				TraceEnd,
				TargetRootRotation,
				UpdatedPrimitive->GetCollisionObjectType(),
				RootShape,
				RootNativeParams,
				RootResponseParams);
		const bool bTargetPoseReached = bMoved
			&& !NativeMoveHit.bBlockingHit
			&& !NativeMoveHit.bStartPenetrating
			&& UpdatedPrimitive->GetComponentLocation().Equals(TraceEnd, 0.05f)
			&& UpdatedPrimitive->GetComponentQuat().Equals(
				TargetRootRotation, 1.0e-6f);
		if (!bTargetPoseReached
			|| bPostEnvelopeNativeBlocked
			|| bPostRootNativeBlocked
			|| !bPostExactClear)
		{
			ScopedMove.RevertMove();
			const FHitResult* FailureHit = NativeMoveHit.bBlockingHit
				? &NativeMoveHit
				: (PostExactHit.bBlockingHit ? &PostExactHit : nullptr);
			return PublishAngularVeto(FailureHit);
		}

		bAngularEnvelopeMoveVetoed = false;
		if (OutHit)
		{
			*OutHit = NativeMoveHit;
		}
		return bMoved;
	}

	if (ConstrainedDelta.IsNearlyZero(1.0e-6f))
	{
		return Super::MoveUpdatedComponentImpl(
			Delta, NewRotation, bSweep, OutHit, Teleport);
	}
	if (bFixedRotationEnvelopeReady)
	{
		const FCollisionShape EnvelopeShape = Envelope->GetCollisionShape();
		const FVector EnvelopeStart = Envelope->GetComponentLocation();
		const FVector EnvelopeEnd = EnvelopeStart + ConstrainedDelta;
		const FQuat EnvelopeRotation = Envelope->GetComponentQuat();
		FHitResult EnvelopeTerrainHit(1.0f);
		const ERedPlanetTerrainQueryResult EnvelopeTerrainResult =
			RedPlanetTerrainQuery::Sweep(
				GetWorld(),
				PlanetCenter,
				EnvelopeStart,
				EnvelopeEnd,
				EnvelopeRotation,
				EnvelopeShape,
				EnvelopeTerrainHit);
		const bool bUsableTerrainHit =
			EnvelopeTerrainResult == ERedPlanetTerrainQueryResult::Hit
			&& EnvelopeTerrainHit.bBlockingHit
			&& !EnvelopeTerrainHit.bStartPenetrating;
		const bool bUnsupportedTerrainOverlap =
			EnvelopeTerrainResult == ERedPlanetTerrainQueryResult::Hit
			&& EnvelopeTerrainHit.bStartPenetrating;

		const float NativeLimitTime = bUsableTerrainHit
			? FMath::Clamp(EnvelopeTerrainHit.Time, 0.0f, 1.0f)
			: 1.0f;
		FComponentQueryParams EnvelopeNativeParams(
			SCENE_QUERY_STAT(RedShipTranslationEnvelopeNative), PawnOwner);
		FCollisionResponseParams EnvelopeResponseParams;
		Envelope->InitSweepCollisionParams(
			EnvelopeNativeParams, EnvelopeResponseParams);
		EnvelopeNativeParams.bFindInitialOverlaps = true;
		EnvelopeNativeParams.bReturnFaceIndex = true;
		EnvelopeNativeParams.bIgnoreTouches = true;
		TArray<FHitResult> EnvelopeNativeHits;
		GetWorld()->ComponentSweepMulti(
			EnvelopeNativeHits,
			Envelope,
			EnvelopeStart,
			EnvelopeStart + ConstrainedDelta * NativeLimitTime,
			EnvelopeRotation,
			EnvelopeNativeParams);
		const FVector MoveDirection = ConstrainedDelta.GetSafeNormal();
		const FHitResult* EnvelopeNativeOverlapHit = nullptr;
		for (const FHitResult& Candidate : EnvelopeNativeHits)
		{
			if (!Candidate.bBlockingHit || !Candidate.bStartPenetrating)
			{
				continue;
			}
			if (!EnvelopeNativeOverlapHit)
			{
				EnvelopeNativeOverlapHit = &Candidate;
				continue;
			}

			const float CandidateOpposition = FVector::DotProduct(
				Candidate.ImpactNormal.GetSafeNormal(), MoveDirection);
			const float CurrentOpposition = FVector::DotProduct(
				EnvelopeNativeOverlapHit->ImpactNormal.GetSafeNormal(), MoveDirection);
			const bool bMoreOpposed = CandidateOpposition < CurrentOpposition - 1.0e-6f;
			const bool bSameOpposition = FMath::IsNearlyEqual(
				CandidateOpposition, CurrentOpposition, 1.0e-6f);
			const bool bDeeper = bSameOpposition
				&& Candidate.PenetrationDepth
					> EnvelopeNativeOverlapHit->PenetrationDepth + 0.001f;
			const bool bSameDepth = bSameOpposition
				&& FMath::IsNearlyEqual(
					Candidate.PenetrationDepth,
					EnvelopeNativeOverlapHit->PenetrationDepth,
					0.001f);
			const FString CandidatePath = GetPathNameSafe(Candidate.GetComponent());
			const FString CurrentPath = GetPathNameSafe(
				EnvelopeNativeOverlapHit->GetComponent());
			const bool bStablePathWins = bSameDepth
				&& (CandidatePath.Compare(
						CurrentPath, ESearchCase::CaseSensitive) < 0
					|| (CandidatePath == CurrentPath
						&& Candidate.FaceIndex < EnvelopeNativeOverlapHit->FaceIndex));
			if (bMoreOpposed || bDeeper || bStablePathWins)
			{
				EnvelopeNativeOverlapHit = &Candidate;
			}
		}
		const FHitResult* EnvelopeNativeHit = EnvelopeNativeHits.FindByPredicate(
			[](const FHitResult& Candidate)
			{
				return Candidate.IsValidBlockingHit();
			});

		auto PublishEnvelopeOverlap =
			[this,
				OutHit,
				TraceStart,
				TraceEnd,
				NewRotation,
				bSuppressOverlapTokenForThisMove](
				const FHitResult& SourceHit,
				const ETranslationEnvelopeOverlapMode Mode)
			{
				if (OutHit)
				{
					*OutHit = SourceHit;
					OutHit->bBlockingHit = true;
					OutHit->bStartPenetrating = true;
					OutHit->Time = 0.0f;
					OutHit->Distance = 0.0f;
					OutHit->TraceStart = TraceStart;
					OutHit->TraceEnd = TraceEnd;
					OutHit->Location = TraceStart;
					OutHit->ImpactPoint = TraceStart;
					if (!bSuppressOverlapTokenForThisMove)
					{
						PendingTranslationEnvelopeOverlapMode = Mode;
						PendingTranslationEnvelopeHitComponent = SourceHit.GetComponent();
						PendingTranslationEnvelopeRootStart = TraceStart;
						PendingTranslationEnvelopeRootRotation = NewRotation;
					}
				}
				return false;
			};

		if (EnvelopeNativeOverlapHit)
		{
			return PublishEnvelopeOverlap(
				*EnvelopeNativeOverlapHit,
				ETranslationEnvelopeOverlapMode::NativeDeferred);
		}
		if (bUnsupportedTerrainOverlap)
		{
			const bool bUsableExactOverlap = EnvelopeTerrainHit.bBlockingHit
				&& FMath::IsFinite(EnvelopeTerrainHit.PenetrationDepth)
				&& EnvelopeTerrainHit.PenetrationDepth > UE_KINDA_SMALL_NUMBER
				&& FMath::IsFinite(EnvelopeTerrainHit.Normal.X)
				&& FMath::IsFinite(EnvelopeTerrainHit.Normal.Y)
				&& FMath::IsFinite(EnvelopeTerrainHit.Normal.Z)
				&& !EnvelopeTerrainHit.Normal.IsNearlyZero();
			return PublishEnvelopeOverlap(
				EnvelopeTerrainHit,
				bUsableExactOverlap
					? ETranslationEnvelopeOverlapMode::ExactTerrain
					: ETranslationEnvelopeOverlapMode::NativeDeferred);
		}

		if (!bUnsupportedTerrainOverlap)
		{
			const FHitResult* LimitingHit = nullptr;
			if (EnvelopeNativeHit
				&& (!bUsableTerrainHit
					|| EnvelopeNativeHit->Distance <= EnvelopeTerrainHit.Distance))
			{
				LimitingHit = EnvelopeNativeHit;
			}
			else if (bUsableTerrainHit)
			{
				LimitingHit = &EnvelopeTerrainHit;
			}

			if (LimitingHit && FullDistance > UE_KINDA_SMALL_NUMBER)
			{
				const float ContactDistance = FMath::Clamp(
					LimitingHit->Distance, 0.0f, FullDistance);
				const float AcceptedDistance = FMath::Max(
					0.0f, ContactDistance - RedShipTranslationEnvelopePullbackCm);
				const float AcceptedTime = FMath::Clamp(
					AcceptedDistance / FullDistance, 0.0f, 1.0f);
				FHitResult RootNativeHit(1.0f);
				const bool bMoved = Super::MoveUpdatedComponentImpl(
					ConstrainedDelta * AcceptedTime,
					NewRotation,
					true,
					&RootNativeHit,
					Teleport);
				if (RootNativeHit.bBlockingHit || RootNativeHit.bStartPenetrating)
				{
					RootNativeHit.Time = FMath::Clamp(
						RootNativeHit.Time * AcceptedTime, 0.0f, 1.0f);
					RootNativeHit.TraceStart = TraceStart;
					RootNativeHit.TraceEnd = TraceEnd;
					if (OutHit)
					{
						*OutHit = RootNativeHit;
					}
					return bMoved;
				}

				if (OutHit)
				{
					*OutHit = *LimitingHit;
					OutHit->Time = AcceptedTime;
					OutHit->Distance = ContactDistance;
					OutHit->TraceStart = TraceStart;
					OutHit->TraceEnd = TraceEnd;
					OutHit->Location = TraceStart
						+ ConstrainedDelta * (ContactDistance / FullDistance);
					OutHit->bStartPenetrating = false;
					OutHit->PenetrationDepth = 0.0f;
				}
				return bMoved;
			}

			// A fitted, supported, non-overlapping envelope is authoritative for exact terrain.
			// If it is clear, move the root over the complete request and let only the root's native
			// collision participate. Falling through to the legacy root exact query would retain the
			// oversized 260 cm sphere as a hidden terrain limiter beneath the fitted fighter body.
			return Super::MoveUpdatedComponentImpl(
				Delta, NewRotation, bSweep, OutHit, Teleport);
		}
	}

	FHitResult TerrainHit(1.0f);
	const ERedPlanetTerrainQueryResult TerrainResult = RedPlanetTerrainQuery::Sweep(
		GetWorld(),
		PlanetCenter,
		TraceStart,
		TraceEnd,
		NewRotation,
		RootShape,
		TerrainHit);
	if (TerrainResult != ERedPlanetTerrainQueryResult::Hit
		|| (!TerrainHit.bBlockingHit && !TerrainHit.bStartPenetrating))
	{
		return Super::MoveUpdatedComponentImpl(Delta, NewRotation, bSweep, OutHit, Teleport);
	}

	// PlanetGen chunks intentionally use WorldDynamic while the ship root ignores generic
	// WorldDynamic actors. Clip the native sweep to the exact owned terrain contact so a bolt,
	// pickup, or presentation mesh can never become ground. Native WorldStatic/Vehicle collision
	// still executes over the clipped segment and wins whenever it is encountered first.
	const float TerrainTime = FMath::Clamp(TerrainHit.Time, 0.0f, 1.0f);
	FHitResult NativeHit(1.0f);
	const bool bMoved = Super::MoveUpdatedComponentImpl(
		ConstrainedDelta * TerrainTime,
		NewRotation,
		true,
		&NativeHit,
		Teleport);
	if (NativeHit.bBlockingHit || NativeHit.bStartPenetrating)
	{
		NativeHit.Time = FMath::Clamp(NativeHit.Time * TerrainTime, 0.0f, 1.0f);
		NativeHit.TraceStart = TraceStart;
		NativeHit.TraceEnd = TraceEnd;
		if (OutHit)
		{
			*OutHit = NativeHit;
		}
		return bMoved;
	}

	if (OutHit)
	{
		*OutHit = TerrainHit;
	}
	return bMoved;
}

void URedShipMovementComponent::AddMoveInput(const FVector& LocalInput) { PendingMoveInput += LocalInput; }
void URedShipMovementComponent::AddRotationInput(const FVector& RotationInput) { PendingRotationInput += RotationInput; }
void URedShipMovementComponent::SetBoostInput(const bool bInBoost) { bPendingBoostInput = bInBoost; }

void URedShipMovementComponent::ClearFlightInputState()
{
	PendingMoveInput = FVector::ZeroVector;
	PendingRotationInput = FVector::ZeroVector;
	LastMoveInput = FVector::ZeroVector;
	LastRotationInput = FVector::ZeroVector;
	bPendingBoostInput = false;
	bBoostActive = false;
}

float URedShipMovementComponent::GetAltitudeAGL() const
{
	if (PlanetRadius <= 0.0f || !UpdatedComponent)
	{
		return RedShipNoAltitude;
	}
	const double DistanceToCenter = (UpdatedComponent->GetComponentLocation() - PlanetCenter).Size();
	return static_cast<float>(DistanceToCenter) - PlanetRadius;
}

bool URedShipMovementComponent::IsInAtmosphere() const { return bInAtmosphere; }
float URedShipMovementComponent::GetCurrentMaxSpeed() const { return GetMaxSpeed(); }
bool URedShipMovementComponent::IsBoosting() const { return bBoostActive; }
FVector URedShipMovementComponent::GetLastMoveInput() const { return LastMoveInput; }
FVector URedShipMovementComponent::GetLastRotationInput() const { return LastRotationInput; }

void URedShipMovementComponent::MoveWithPlanetCollision(
	const FVector& Delta,
	const FQuat& NewRotation,
	const float DeltaTime)
{
	if (!UpdatedComponent)
	{
		return;
	}

	const FVector OldLocation = UpdatedComponent->GetComponentLocation();
	bPositionCorrected = false;
	bSurfaceVelocityAdjusted = false;
	FHitResult Hit(1.0f);
	SafeMoveUpdatedComponent(Delta, NewRotation, true, Hit);
	if (Hit.IsValidBlockingHit() && !bAngularEnvelopeMoveVetoed)
	{
		HandleImpact(Hit, DeltaTime, Delta);
		SlideAlongSurface(Delta, 1.0f - Hit.Time, Hit.Normal, Hit, true);
	}
	bAngularEnvelopeMoveVetoed = false;

	ClampToPlanetSurface();
	if (!bPositionCorrected
		&& !bSurfaceVelocityAdjusted
		&& DeltaTime > UE_KINDA_SMALL_NUMBER)
	{
		Velocity = (UpdatedComponent->GetComponentLocation() - OldLocation) / DeltaTime;
	}
	UpdateComponentVelocity();
}

FVector URedShipMovementComponent::ComputeNewVelocity(const FVector& CurrentVelocity, const FVector& DesiredVelocity, const float Responsiveness, const float MaxSpeed, const float DeltaTime)
{
	const FVector NewVelocity = FMath::VInterpTo(CurrentVelocity, DesiredVelocity, DeltaTime, Responsiveness);
	return NewVelocity.GetClampedToMaxSize(MaxSpeed);
}

float URedShipMovementComponent::EvaluateAltitudeSpeedCap(const float AltitudeAGL) const
{
	if (!AltitudeSpeedCurve)
	{
		if (!bWarnedMissingCurve)
		{
			bWarnedMissingCurve = true;
			UE_LOG(LogRedShip, Warning, TEXT("%s: AltitudeSpeedCurve not set — using FallbackMaxSpeed %.0f m/s"),
				*GetNameSafe(PawnOwner), FallbackMaxSpeed / 100.0f);
		}
		return FallbackMaxSpeed;
	}
	const float AltitudeKm = FMath::Max(AltitudeAGL, 0.0f) / 100000.0f;
	const float MaxSpeedMs = AltitudeSpeedCurve->GetFloatValue(AltitudeKm);
	return FMath::Max(MaxSpeedMs * 100.0f, RedShipMinSpeedCap);
}

FQuat URedShipMovementComponent::ComputeNewRotation(const FQuat& CurrentQuat, const FVector& ClampedRotationInput, const float DeltaTime) const
{
	const float PitchRad = FMath::DegreesToRadians(PitchRateDeg) * ClampedRotationInput.X * DeltaTime;
	const float YawRad = FMath::DegreesToRadians(YawRateDeg) * ClampedRotationInput.Y * DeltaTime;
	const float RollRad = FMath::DegreesToRadians(RollRateDeg) * ClampedRotationInput.Z * DeltaTime;

	const FQuat DeltaQuat =
		FQuat(FVector::XAxisVector, -RollRad) *
		FQuat(FVector::YAxisVector, -PitchRad) *
		FQuat(FVector::ZAxisVector, YawRad);

	FQuat NewQuat = CurrentQuat * DeltaQuat;

	const bool bSteering = ClampedRotationInput.SizeSquared() > UE_KINDA_SMALL_NUMBER;
	if (bInAtmosphere && AutoLevelStrength > 0.0f && PlanetRadius > 0.0f && !bSteering)
	{
		const FVector RadialUp = (UpdatedComponent->GetComponentLocation() - PlanetCenter).GetSafeNormal();
		if (!RadialUp.IsNearlyZero())
		{
			const float AltitudeAGL = FMath::Max(0.0f, static_cast<float>((UpdatedComponent->GetComponentLocation() - PlanetCenter).Size() - PlanetRadius));
			const float AltitudeFade = (AtmosphereTopAltitude > 0.0f)
				? FMath::Clamp(1.0f - AltitudeAGL / AtmosphereTopAltitude, 0.0f, 1.0f)
				: 1.0f;
			const FQuat AlignDelta = FQuat::FindBetweenNormals(NewQuat.GetUpVector(), RadialUp);
			const float Alpha = FMath::Clamp(AutoLevelStrength * AltitudeFade * DeltaTime, 0.0f, 1.0f);
			NewQuat = FQuat::Slerp(NewQuat, AlignDelta * NewQuat, Alpha);
		}
	}

	NewQuat.Normalize();
	return NewQuat;
}

void URedShipMovementComponent::UpdateFlightMode(const float AltitudeAGL)
{
	const bool bNowInAtmosphere = (PlanetRadius > 0.0f) && (AltitudeAGL < AtmosphereTopAltitude);
	if (!bFlightModeInitialized)
	{
		bFlightModeInitialized = true;
		bInAtmosphere = bNowInAtmosphere;
		return;
	}
	if (bNowInAtmosphere != bInAtmosphere)
	{
		bInAtmosphere = bNowInAtmosphere;
		UE_LOG(LogRedShip, Log, TEXT("%s: %s (altitude AGL %.0f m, speed %.0f m/s)"),
			*GetNameSafe(PawnOwner),
			bInAtmosphere ? TEXT("entered ATMOSPHERE") : TEXT("entered SPACE"),
			AltitudeAGL / 100.0f, Velocity.Size() / 100.0);
	}
}

URedShipMovementComponent::ESurfaceRecoveryResult
URedShipMovementComponent::TryCommitBoundedSurfaceRecovery(
	const FVector& RequestedRootLocation,
	const ESurfaceRecoveryPolicy Policy,
	const FHitResult* AuthenticatedSurfaceHit,
	const FIntVector* AuthenticatedSurfaceChunkKey)
{
	UWorld* World = GetWorld();
	UBoxComponent* Envelope = TranslationCollisionEnvelope.Get();
	const FIntVector InvalidChunkKey(INDEX_NONE, INDEX_NONE, INDEX_NONE);
	auto IsFiniteNormalizedQuat = [](const FQuat& Quat)
	{
		return FMath::IsFinite(Quat.X)
			&& FMath::IsFinite(Quat.Y)
			&& FMath::IsFinite(Quat.Z)
			&& FMath::IsFinite(Quat.W)
			&& !Quat.ContainsNaN()
			&& Quat.IsNormalized();
	};
	const bool bExactPolicy =
		Policy == ESurfaceRecoveryPolicy::ExactTerrainPenetration;
	const bool bLegacyPolicy =
		Policy == ESurfaceRecoveryPolicy::LegacyVoid;

	const bool bRecoveryReady = World
		&& PawnOwner
		&& PawnOwner->HasAuthority()
		&& !PawnOwner->GetAttachParentActor()
		&& UpdatedComponent
		&& UpdatedPrimitive
		&& UpdatedPrimitive->GetOwner() == PawnOwner
		&& UpdatedPrimitive->GetMobility() == EComponentMobility::Movable
		&& UpdatedPrimitive->IsRegistered()
		&& UpdatedPrimitive->IsPhysicsStateCreated()
		&& UpdatedPrimitive->IsQueryCollisionEnabled()
		&& Envelope
		&& Envelope != UpdatedPrimitive
		&& Envelope->GetOwner() == PawnOwner
		&& Envelope->IsRegistered()
		&& Envelope->IsPhysicsStateCreated()
		&& Envelope->IsQueryCollisionEnabled()
		&& Envelope->GetAttachParent() == UpdatedPrimitive
		&& !Envelope->IsUsingAbsoluteLocation()
		&& !Envelope->IsUsingAbsoluteRotation()
		&& !Envelope->IsUsingAbsoluteScale()
		&& !PlanetCenter.ContainsNaN()
		&& FMath::IsFinite(PlanetRadius)
		&& PlanetRadius > 0.0f
		&& FMath::IsFinite(MinimumSurfaceClearance)
		&& MinimumSurfaceClearance >= 0.0f
		&& !RequestedRootLocation.ContainsNaN();
	if (!bRecoveryReady)
	{
		return ESurfaceRecoveryResult::Rejected;
	}
	if (!bExactPolicy && !bLegacyPolicy)
	{
		return ESurfaceRecoveryResult::Rejected;
	}

	const FCollisionShape RootShape = UpdatedPrimitive->GetCollisionShape();
	const FCollisionShape EnvelopeShape = Envelope->GetCollisionShape();
	if (!RootShape.IsSphere() || !EnvelopeShape.IsBox())
	{
		return ESurfaceRecoveryResult::Rejected;
	}

	const FTransform CurrentRootTransform = UpdatedPrimitive->GetComponentTransform();
	const FVector RootStart = CurrentRootTransform.GetLocation();
	const FQuat CurrentRootRotation = CurrentRootTransform.GetRotation();
	const FVector RootFromCenter = RootStart - PlanetCenter;
	const FVector RequestedFromCenter = RequestedRootLocation - PlanetCenter;
	const double RootStartRadius = RootFromCenter.Size();
	const double RequestedRadius = RequestedFromCenter.Size();
	if (RootStart.ContainsNaN()
		|| !IsFiniteNormalizedQuat(CurrentRootRotation)
		|| !FMath::IsFinite(RootStartRadius)
		|| RootStartRadius <= UE_KINDA_SMALL_NUMBER
		|| !FMath::IsFinite(RequestedRadius)
		|| RequestedRadius <= UE_KINDA_SMALL_NUMBER)
	{
		return ESurfaceRecoveryResult::Rejected;
	}
	const FVector RadialUp = RootFromCenter / RootStartRadius;
	const FVector RequestedRadialUp = RequestedFromCenter / RequestedRadius;
	if (FVector::DotProduct(RadialUp, RequestedRadialUp) < 0.999999f)
	{
		return ESurfaceRecoveryResult::Rejected;
	}
	const double LegacyDatumRadius =
		static_cast<double>(PlanetRadius + MinimumSurfaceClearance);
	if (bLegacyPolicy
		&& (FMath::Abs(RequestedRadius - LegacyDatumRadius) > 0.05
			|| RootStartRadius + 0.01 >= RequestedRadius))
	{
		return ESurfaceRecoveryResult::Rejected;
	}

	UPrimitiveComponent* ExactWitnessComponent = nullptr;
	AActor* ExactWitnessActor = nullptr;
	FIntVector ExactWitnessChunkKey = InvalidChunkKey;
	FVector ExactWitnessNormal = FVector::ZeroVector;
	double ExactWitnessSurfaceRadius = 0.0;
	if (bExactPolicy)
	{
		if (!AuthenticatedSurfaceHit
			|| !AuthenticatedSurfaceChunkKey
			|| *AuthenticatedSurfaceChunkKey == InvalidChunkKey)
		{
			return ESurfaceRecoveryResult::Rejected;
		}

		ExactWitnessComponent = AuthenticatedSurfaceHit->GetComponent();
		ExactWitnessActor = AuthenticatedSurfaceHit->GetActor();
		ExactWitnessChunkKey = *AuthenticatedSurfaceChunkKey;
		const FVector WitnessImpactFromCenter =
			AuthenticatedSurfaceHit->ImpactPoint - PlanetCenter;
		ExactWitnessSurfaceRadius = WitnessImpactFromCenter.Size();
		ExactWitnessNormal =
			AuthenticatedSurfaceHit->ImpactNormal.GetSafeNormal();
		const FVector WitnessTraceDelta =
			AuthenticatedSurfaceHit->TraceEnd
			- AuthenticatedSurfaceHit->TraceStart;
		const FVector WitnessTraceDirection =
			WitnessTraceDelta.GetSafeNormal();
		const FVector WitnessRadialUp =
			WitnessImpactFromCenter.GetSafeNormal();
		const FVector ExpectedRequestedRootLocation =
			AuthenticatedSurfaceHit->ImpactPoint
			+ RadialUp * MinimumSurfaceClearance;
		const bool bAuthenticatedWitnessReady =
			AuthenticatedSurfaceHit->bBlockingHit
			&& !AuthenticatedSurfaceHit->bStartPenetrating
			&& IsValid(ExactWitnessComponent)
			&& IsValid(ExactWitnessActor)
			&& ExactWitnessComponent->GetOwner() == ExactWitnessActor
			&& ExactWitnessChunkKey.X != INDEX_NONE
			&& ExactWitnessChunkKey.Y != INDEX_NONE
			&& ExactWitnessChunkKey.Z != INDEX_NONE
			&& !AuthenticatedSurfaceHit->ImpactPoint.ContainsNaN()
			&& !AuthenticatedSurfaceHit->ImpactNormal.ContainsNaN()
			&& !AuthenticatedSurfaceHit->TraceStart.ContainsNaN()
			&& !AuthenticatedSurfaceHit->TraceEnd.ContainsNaN()
			&& FMath::IsFinite(AuthenticatedSurfaceHit->Time)
			&& AuthenticatedSurfaceHit->Time >= 0.0f
			&& AuthenticatedSurfaceHit->Time <= 1.0f
			&& FMath::IsFinite(ExactWitnessSurfaceRadius)
			&& ExactWitnessSurfaceRadius > UE_KINDA_SMALL_NUMBER
			&& !ExactWitnessNormal.IsNearlyZero()
			&& !WitnessTraceDirection.IsNearlyZero()
			&& !WitnessRadialUp.IsNearlyZero()
			&& FVector::DotProduct(WitnessTraceDirection, -RadialUp)
				> 0.999999f
			&& FVector::DotProduct(WitnessRadialUp, RadialUp)
				> 0.999999f
			&& FVector::DotProduct(ExactWitnessNormal, RadialUp) > 0.01f
			&& FVector::DotProduct(
				AuthenticatedSurfaceHit->TraceStart - PlanetCenter,
				RadialUp) > ExactWitnessSurfaceRadius
			&& AuthenticatedSurfaceHit->TraceEnd.Equals(
				PlanetCenter, 0.1f)
			&& RequestedRootLocation.Equals(
				ExpectedRequestedRootLocation, 0.1f);
		if (!bAuthenticatedWitnessReady)
		{
			return ESurfaceRecoveryResult::Rejected;
		}
	}
	else if (AuthenticatedSurfaceHit || AuthenticatedSurfaceChunkKey)
	{
		return ESurfaceRecoveryResult::Rejected;
	}

	const FVector CurrentEnvelopeLocation = Envelope->GetComponentLocation();
	const FQuat CurrentEnvelopeRotation = Envelope->GetComponentQuat();
	const FVector RootToEnvelopeScaledLocal =
		CurrentRootRotation.UnrotateVector(
			CurrentEnvelopeLocation - RootStart);
	const FQuat EnvelopeRelativeRotation = (
		CurrentRootRotation.Inverse() * CurrentEnvelopeRotation).GetNormalized();
	const FQuat TargetEnvelopeRotation = (
		CurrentRootRotation * EnvelopeRelativeRotation).GetNormalized();
	const FVector RequestedEnvelopeLocation =
		RequestedRootLocation
		+ CurrentRootRotation.RotateVector(RootToEnvelopeScaledLocal);
	const FVector BoxExtent = EnvelopeShape.GetExtent();
	const FVector EnvelopeAxisX =
		TargetEnvelopeRotation.RotateVector(FVector::XAxisVector);
	const FVector EnvelopeAxisY =
		TargetEnvelopeRotation.RotateVector(FVector::YAxisVector);
	const FVector EnvelopeAxisZ =
		TargetEnvelopeRotation.RotateVector(FVector::ZAxisVector);
	const double EnvelopeRadialSupport =
		FMath::Abs(FVector::DotProduct(RadialUp, EnvelopeAxisX)) * BoxExtent.X
		+ FMath::Abs(FVector::DotProduct(RadialUp, EnvelopeAxisY)) * BoxExtent.Y
		+ FMath::Abs(FVector::DotProduct(RadialUp, EnvelopeAxisZ)) * BoxExtent.Z;
	const double RequestedEnvelopeMinimumRadius =
		FVector::DotProduct(
			RequestedEnvelopeLocation - PlanetCenter, RadialUp)
		- EnvelopeRadialSupport;
	const double FittedEnvelopeLift = FMath::Max(
		0.0, RequestedRadius - RequestedEnvelopeMinimumRadius);
	const FVector TargetRootLocation =
		RequestedRootLocation + RadialUp * FittedEnvelopeLift;
	const FVector TargetEnvelopeLocation =
		TargetRootLocation
		+ CurrentRootRotation.RotateVector(RootToEnvelopeScaledLocal);
	const double TargetRootRadius =
		(TargetRootLocation - PlanetCenter).Size();
	const double CurrentEnvelopeCenterRadius =
		FVector::DotProduct(
			CurrentEnvelopeLocation - PlanetCenter, RadialUp);
	const double CurrentEnvelopeMinimumRadius =
		CurrentEnvelopeCenterRadius - EnvelopeRadialSupport;
	const double CurrentEnvelopeMaximumRadius =
		CurrentEnvelopeCenterRadius + EnvelopeRadialSupport;
	const double TargetEnvelopeMinimumRadius =
		FVector::DotProduct(
			TargetEnvelopeLocation - PlanetCenter, RadialUp)
		- EnvelopeRadialSupport;
	const double ExpectedTargetEnvelopeMinimumRadius =
		RequestedEnvelopeMinimumRadius + FittedEnvelopeLift;
	const FVector RecoveryDelta = TargetRootLocation - RootStart;
	const FVector ConstrainedRecoveryDelta =
		ConstrainDirectionToPlane(RecoveryDelta);
	const double RecoveryDistance = RecoveryDelta.Size();
	const bool bValidFittedGeometry =
		!RootToEnvelopeScaledLocal.ContainsNaN()
		&& IsFiniteNormalizedQuat(EnvelopeRelativeRotation)
		&& IsFiniteNormalizedQuat(TargetEnvelopeRotation)
		&& TargetEnvelopeRotation.Equals(CurrentEnvelopeRotation, 1.0e-6f)
		&& !RequestedEnvelopeLocation.ContainsNaN()
		&& !BoxExtent.ContainsNaN()
		&& BoxExtent.X > UE_KINDA_SMALL_NUMBER
		&& BoxExtent.Y > UE_KINDA_SMALL_NUMBER
		&& BoxExtent.Z > UE_KINDA_SMALL_NUMBER
		&& FMath::IsFinite(EnvelopeRadialSupport)
		&& FMath::IsFinite(RequestedEnvelopeMinimumRadius)
		&& FMath::IsFinite(FittedEnvelopeLift)
		&& !TargetRootLocation.ContainsNaN()
		&& !TargetEnvelopeLocation.ContainsNaN()
		&& FMath::IsFinite(TargetRootRadius)
		&& TargetRootRadius > UE_KINDA_SMALL_NUMBER
		&& FMath::IsFinite(CurrentEnvelopeCenterRadius)
		&& FMath::IsFinite(CurrentEnvelopeMinimumRadius)
		&& FMath::IsFinite(CurrentEnvelopeMaximumRadius)
		&& FMath::IsFinite(TargetEnvelopeMinimumRadius)
		&& FMath::IsFinite(ExpectedTargetEnvelopeMinimumRadius)
		&& TargetEnvelopeMinimumRadius + 0.05 >= RequestedRadius
		&& FMath::Abs(
			TargetEnvelopeMinimumRadius
				- ExpectedTargetEnvelopeMinimumRadius) <= 0.05;
	if (!bValidFittedGeometry)
	{
		return ESurfaceRecoveryResult::Rejected;
	}

	FHitResult InitialExactHit(1.0f);
	FIntVector InitialExactChunkKey = InvalidChunkKey;
	const ERedPlanetTerrainQueryResult InitialExactResult =
		RedPlanetTerrainQuery::Sweep(
			World,
			PlanetCenter,
			CurrentEnvelopeLocation,
			CurrentEnvelopeLocation,
			CurrentEnvelopeRotation,
			EnvelopeShape,
			InitialExactHit,
			&InitialExactChunkKey);
	const bool bInitialExactCleanNoHit =
		InitialExactResult == ERedPlanetTerrainQueryResult::NoHit
		&& !InitialExactHit.bBlockingHit
		&& !InitialExactHit.bStartPenetrating
		&& InitialExactChunkKey == InvalidChunkKey;
	const bool bInitialExactWitnessPenetration =
		InitialExactResult == ERedPlanetTerrainQueryResult::Hit
		&& InitialExactHit.bBlockingHit
		&& InitialExactHit.bStartPenetrating
		&& InitialExactHit.GetComponent() == ExactWitnessComponent
		&& InitialExactHit.GetActor() == ExactWitnessActor
		&& InitialExactChunkKey == ExactWitnessChunkKey;
	if (bExactPolicy)
	{
		if (!bInitialExactCleanNoHit
			&& !bInitialExactWitnessPenetration)
		{
			return ESurfaceRecoveryResult::Rejected;
		}
		if (bInitialExactCleanNoHit
			&& CurrentEnvelopeMinimumRadius
				> ExactWitnessSurfaceRadius + 0.05)
		{
			return ESurfaceRecoveryResult::NotRequired;
		}
		if (bInitialExactCleanNoHit
			&& CurrentEnvelopeMaximumRadius + 0.05
				>= ExactWitnessSurfaceRadius)
		{
			return ESurfaceRecoveryResult::Rejected;
		}
	}
	else
	{
		const bool bLegacyInitialStateClear =
			InitialExactResult
				== ERedPlanetTerrainQueryResult::NoMatchingPlanet
			&& !InitialExactHit.bBlockingHit
			&& !InitialExactHit.bStartPenetrating
			&& InitialExactChunkKey == InvalidChunkKey;
		if (!bLegacyInitialStateClear)
		{
			return ESurfaceRecoveryResult::Rejected;
		}
	}

	const bool bValidRecoveryGeometry =
		!RecoveryDelta.ContainsNaN()
		&& FMath::IsFinite(RecoveryDistance)
		&& RecoveryDistance > UE_KINDA_SMALL_NUMBER
		&& RecoveryDistance <= RedShipSurfaceRecoveryMaxTranslationCm
		&& ConstrainedRecoveryDelta.Equals(RecoveryDelta, 0.01f)
		&& FVector::DotProduct(
			RecoveryDelta.GetSafeNormal(), RadialUp) > 0.999999f;
	if (!bValidRecoveryGeometry)
	{
		return ESurfaceRecoveryResult::Rejected;
	}

	FComponentQueryParams EnvelopeNativeParams(
		SCENE_QUERY_STAT(RedShipSurfaceRecoveryEnvelopeNative), PawnOwner);
	FCollisionResponseParams EnvelopeResponseParams;
	Envelope->InitSweepCollisionParams(
		EnvelopeNativeParams, EnvelopeResponseParams);
	EnvelopeNativeParams.bTraceComplex = true;
	EnvelopeNativeParams.bFindInitialOverlaps = true;
	EnvelopeNativeParams.bReturnFaceIndex = true;
	EnvelopeNativeParams.bIgnoreTouches = true;
	if (bExactPolicy)
	{
		EnvelopeNativeParams.AddIgnoredComponent(ExactWitnessComponent);
	}

	FComponentQueryParams RootNativeParams(
		SCENE_QUERY_STAT(RedShipSurfaceRecoveryRootNative), PawnOwner);
	FCollisionResponseParams RootResponseParams;
	UpdatedPrimitive->InitSweepCollisionParams(
		RootNativeParams, RootResponseParams);
	RootNativeParams.bFindInitialOverlaps = true;
	RootNativeParams.bReturnFaceIndex = true;
	RootNativeParams.bIgnoreTouches = true;
	if (bExactPolicy)
	{
		RootNativeParams.AddIgnoredComponent(ExactWitnessComponent);
	}

	auto IsDisallowedNativeRouteHit = [](const FHitResult& Candidate)
		{
			return Candidate.bBlockingHit || Candidate.bStartPenetrating;
		};

	TArray<FHitResult> RootRouteHits;
	World->ComponentSweepMulti(
		RootRouteHits,
		UpdatedPrimitive,
		RootStart,
		TargetRootLocation,
		CurrentRootRotation,
		RootNativeParams);
	TArray<FHitResult> EnvelopeRouteHits;
	World->ComponentSweepMulti(
		EnvelopeRouteHits,
		Envelope,
		CurrentEnvelopeLocation,
		TargetEnvelopeLocation,
		CurrentEnvelopeRotation,
		EnvelopeNativeParams);
	if (RootRouteHits.ContainsByPredicate(IsDisallowedNativeRouteHit)
		|| EnvelopeRouteHits.ContainsByPredicate(IsDisallowedNativeRouteHit))
	{
		return ESurfaceRecoveryResult::Rejected;
	}

	FHitResult ExactForwardRouteHit(1.0f);
	FIntVector ExactForwardRouteChunkKey = InvalidChunkKey;
	const ERedPlanetTerrainQueryResult ExactForwardRouteResult =
		RedPlanetTerrainQuery::Sweep(
			World,
			PlanetCenter,
			CurrentEnvelopeLocation,
			TargetEnvelopeLocation,
			CurrentEnvelopeRotation,
			EnvelopeShape,
			ExactForwardRouteHit,
			&ExactForwardRouteChunkKey);
	FHitResult ExactReverseRouteHit(1.0f);
	FIntVector ExactReverseRouteChunkKey = InvalidChunkKey;
	const ERedPlanetTerrainQueryResult ExactReverseRouteResult =
		RedPlanetTerrainQuery::Sweep(
			World,
			PlanetCenter,
			TargetEnvelopeLocation,
			CurrentEnvelopeLocation,
			CurrentEnvelopeRotation,
			EnvelopeShape,
			ExactReverseRouteHit,
			&ExactReverseRouteChunkKey);
	const double ExactWitnessToleranceCm =
		FMath::Max(
			50.0,
			static_cast<double>(BoxExtent.Size()) * 2.0 + 50.0);
	auto IsAuthenticatedExactRouteHit =
		[&](const FHitResult& Candidate,
			const FIntVector& CandidateChunkKey,
			const bool bExpectedStartPenetrating,
			const bool bRequireOutwardNormal)
		{
			if (!Candidate.bBlockingHit
				|| Candidate.bStartPenetrating
					!= bExpectedStartPenetrating
				|| Candidate.GetComponent() != ExactWitnessComponent
				|| Candidate.GetActor() != ExactWitnessActor
				|| CandidateChunkKey != ExactWitnessChunkKey)
			{
				return false;
			}
			if (Candidate.bStartPenetrating)
			{
				return true;
			}
			const FVector CandidateNormal =
				Candidate.ImpactNormal.GetSafeNormal();
			const double CandidateSurfaceRadius =
				(Candidate.ImpactPoint - PlanetCenter).Size();
			const float WitnessNormalAlignment =
				FVector::DotProduct(CandidateNormal, ExactWitnessNormal);
			const float RadialNormalAlignment =
				FVector::DotProduct(CandidateNormal, RadialUp);
			return !Candidate.ImpactPoint.ContainsNaN()
				&& !Candidate.ImpactNormal.ContainsNaN()
				&& !CandidateNormal.IsNearlyZero()
				&& FMath::IsFinite(CandidateSurfaceRadius)
				&& FVector::Dist(
					Candidate.ImpactPoint,
					AuthenticatedSurfaceHit->ImpactPoint)
					<= ExactWitnessToleranceCm
				&& FMath::Abs(
					CandidateSurfaceRadius
						- ExactWitnessSurfaceRadius)
					<= ExactWitnessToleranceCm
				&& (bRequireOutwardNormal
					? WitnessNormalAlignment > 0.1f
					: FMath::Abs(WitnessNormalAlignment) > 0.1f)
				&& (bRequireOutwardNormal
					? RadialNormalAlignment > 0.01f
					: FMath::Abs(RadialNormalAlignment) > 0.01f);
		};
	const bool bExactRoutesAuthenticated =
		(bExactPolicy
			&& ExactForwardRouteResult
				== ERedPlanetTerrainQueryResult::Hit
			&& ExactReverseRouteResult
				== ERedPlanetTerrainQueryResult::Hit
			&& IsAuthenticatedExactRouteHit(
				ExactForwardRouteHit,
				ExactForwardRouteChunkKey,
				bInitialExactWitnessPenetration,
				false)
			&& IsAuthenticatedExactRouteHit(
				ExactReverseRouteHit,
				ExactReverseRouteChunkKey,
				false,
				true))
		|| (bLegacyPolicy
			&& ExactForwardRouteResult
				== ERedPlanetTerrainQueryResult::NoMatchingPlanet
			&& ExactReverseRouteResult
				== ERedPlanetTerrainQueryResult::NoMatchingPlanet
			&& !ExactForwardRouteHit.bBlockingHit
			&& !ExactForwardRouteHit.bStartPenetrating
			&& !ExactReverseRouteHit.bBlockingHit
			&& !ExactReverseRouteHit.bStartPenetrating
			&& ExactForwardRouteChunkKey == InvalidChunkKey
			&& ExactReverseRouteChunkKey == InvalidChunkKey);
	if (!bExactRoutesAuthenticated)
	{
		return ESurfaceRecoveryResult::Rejected;
	}

	auto IsTargetEndpointClear = [&]()
	{
		const bool bEnvelopeNativeBlocked =
			World->OverlapBlockingTestByChannel(
				TargetEnvelopeLocation,
				TargetEnvelopeRotation,
				Envelope->GetCollisionObjectType(),
				EnvelopeShape,
				EnvelopeNativeParams,
				EnvelopeResponseParams);
		const bool bRootNativeBlocked =
			World->OverlapBlockingTestByChannel(
				TargetRootLocation,
				CurrentRootRotation,
				UpdatedPrimitive->GetCollisionObjectType(),
				RootShape,
				RootNativeParams,
				RootResponseParams);
		FHitResult EndpointExactHit(1.0f);
		FIntVector EndpointExactChunkKey = InvalidChunkKey;
		const ERedPlanetTerrainQueryResult EndpointExactResult =
			RedPlanetTerrainQuery::Sweep(
				World,
				PlanetCenter,
				TargetEnvelopeLocation,
				TargetEnvelopeLocation,
				TargetEnvelopeRotation,
				EnvelopeShape,
				EndpointExactHit,
				&EndpointExactChunkKey);
		const bool bExactEndpointClear =
			(bExactPolicy
				&& EndpointExactResult == ERedPlanetTerrainQueryResult::NoHit)
			|| (bLegacyPolicy
				&& EndpointExactResult
					== ERedPlanetTerrainQueryResult::NoMatchingPlanet);
		return !bEnvelopeNativeBlocked
			&& !bRootNativeBlocked
			&& bExactEndpointClear
			&& !EndpointExactHit.bBlockingHit
			&& !EndpointExactHit.bStartPenetrating
			&& EndpointExactChunkKey == InvalidChunkKey;
	};
	if (!IsTargetEndpointClear())
	{
		return ESurfaceRecoveryResult::Rejected;
	}

	{
		FScopedMovementUpdate ScopedMove(
			UpdatedComponent, EScopedUpdate::DeferredUpdates);
		FHitResult RecoveryMoveHit(1.0f);
		const bool bMoveReported = Super::MoveUpdatedComponentImpl(
			RecoveryDelta,
			CurrentRootRotation,
			false,
			&RecoveryMoveHit,
			ETeleportType::TeleportPhysics);
		const bool bTargetPoseReached = bMoveReported
			&& !RecoveryMoveHit.bBlockingHit
			&& !RecoveryMoveHit.bStartPenetrating
			&& UpdatedPrimitive->GetComponentLocation().Equals(
				TargetRootLocation, 0.05f)
			&& UpdatedPrimitive->GetComponentQuat().Equals(
				CurrentRootRotation, 1.0e-6f);
		if (!bTargetPoseReached || !IsTargetEndpointClear())
		{
			ScopedMove.RevertMove();
			return ESurfaceRecoveryResult::Rejected;
		}
	}
	return ESurfaceRecoveryResult::Committed;
}

void URedShipMovementComponent::ClampToPlanetSurface()
{
	UWorld* World = GetWorld();
	if (!World
		|| !PawnOwner
		|| !PawnOwner->HasAuthority()
		|| PawnOwner->GetAttachParentActor()
		|| !UpdatedComponent
		|| PlanetCenter.ContainsNaN()
		|| !FMath::IsFinite(PlanetRadius)
		|| PlanetRadius <= 0.0f
		|| !FMath::IsFinite(MinimumSurfaceClearance)
		|| MinimumSurfaceClearance < 0.0f)
	{
		return;
	}

	const FVector FromCenter = UpdatedComponent->GetComponentLocation() - PlanetCenter;
	const double Distance = FromCenter.Size();
	if (Distance <= UE_KINDA_SMALL_NUMBER)
	{
		return;
	}

	const double MinDistance = static_cast<double>(PlanetRadius + MinimumSurfaceClearance);
	if (Distance >= MinDistance)
	{
		return;
	}

	const FVector RadialUp = FromCenter / Distance;
	auto FinalizeSurfaceAttempt = [&](const bool bPoseCommitted)
	{
		const float InwardSpeed = FVector::DotProduct(Velocity, -RadialUp);
		const bool bVelocityAdjusted = InwardSpeed > 0.0f;
		if (bVelocityAdjusted)
		{
			Velocity += RadialUp * InwardSpeed;
			bSurfaceVelocityAdjusted = true;
		}
		if (bPoseCommitted)
		{
			bPositionCorrected = true;
		}
		if (bPoseCommitted || bVelocityAdjusted)
		{
			UpdateComponentVelocity();
			PawnOwner->ForceNetUpdate();
		}
	};

	// Reaching the nominal datum is only a trigger for an exact active-terrain query. The authored
	// surface can legitimately sit below that datum, so a clean hull with terrain still ahead keeps
	// descending. A hull already overlapping the authenticated surface, or fully behind its radial
	// shell, may use the bounded fitted-envelope recovery below. A matching planet with no ready
	// chunk defers pose correction and contains only inward velocity.
	{
		float OuterTraceRadius = static_cast<float>(Distance)
			+ MinimumSurfaceClearance + 60000.0f;
		FVector HomeCenter = FVector::ZeroVector;
		float HomeDatumRadius = 0.0f;
		float HomePeakRadius = 0.0f;
		if (RedGravity::FindMeshPlanet(
			World, HomeCenter, HomeDatumRadius, &HomePeakRadius)
			&& HomeCenter.Equals(PlanetCenter, 100.0f))
		{
			OuterTraceRadius = FMath::Max(OuterTraceRadius, HomePeakRadius + 50000.0f);
		}

		FHitResult TerrainHit;
		FIntVector TerrainChunkKey(INDEX_NONE, INDEX_NONE, INDEX_NONE);
		const ERedPlanetTerrainQueryResult TerrainResult = RedPlanetTerrainQuery::LineTrace(
			World,
			PlanetCenter,
			PlanetCenter + RadialUp * OuterTraceRadius,
			PlanetCenter,
			TerrainHit,
			&TerrainChunkKey);
		switch (TerrainResult)
		{
		case ERedPlanetTerrainQueryResult::Hit:
			if (!TerrainHit.bBlockingHit)
			{
				FinalizeSurfaceAttempt(false);
				return;
			}
			{
				const FVector TerrainCorrectedLocation =
					TerrainHit.ImpactPoint
					+ RadialUp * MinimumSurfaceClearance;
				const ESurfaceRecoveryResult RecoveryResult =
					TryCommitBoundedSurfaceRecovery(
						TerrainCorrectedLocation,
						ESurfaceRecoveryPolicy::ExactTerrainPenetration,
						&TerrainHit,
						&TerrainChunkKey);
				if (RecoveryResult == ESurfaceRecoveryResult::NotRequired)
				{
					return;
				}
				FinalizeSurfaceAttempt(
					RecoveryResult == ESurfaceRecoveryResult::Committed);
			}
			return;
		case ERedPlanetTerrainQueryResult::NoHit:
			FinalizeSurfaceAttempt(false);
			return;
		case ERedPlanetTerrainQueryResult::NoMatchingPlanet:
			break;
		default:
			FinalizeSurfaceAttempt(false);
			return;
		}
	}

	// Physical-first: if REAL terrain exists below the hull, physics owns the landing — this
	// analytic floor only catches falling into NOT-YET-COOKED voxel. Craters and stamp smoothing
	// sit BELOW the nominal datum; unconditionally clamping to the datum there teleported the
	// ship off cooked ground it had every right to rest on, every tick ("phasing/fluttering").
	{
		AActor* OwnerActor = GetOwner();
		if (OwnerActor)
		{
			// WorldStatic ONLY (the voxel world): a WorldDynamic hit (own bolt just fired downward,
			// a resource pickup) would suppress the void-catch exactly while diving into uncooked
			// terrain — one-tick dips below the datum, then a bounded recovery back out.
			FCollisionObjectQueryParams ObjectParams;
			ObjectParams.AddObjectTypesToQuery(ECC_WorldStatic);
			FCollisionQueryParams QueryParams(SCENE_QUERY_STAT(RedShipVoidCheck), false);
			QueryParams.AddIgnoredActor(OwnerActor);
			TArray<AActor*> Attached;
			OwnerActor->GetAttachedActors(Attached);
			for (AActor* AttachedActor : Attached)
			{
				QueryParams.AddIgnoredActor(AttachedActor);
			}
			FHitResult GroundHit;
			const FVector Start = UpdatedComponent->GetComponentLocation();
			// Reach: full clearance + 600m — deeper than any carved crater below the datum.
			const FVector End = Start - RadialUp * (MinimumSurfaceClearance + 60000.0f);
			if (World->LineTraceSingleByObjectType(GroundHit, Start, End, ObjectParams, QueryParams)
				&& GroundHit.bBlockingHit)
			{
				return;
			}
		}
	}
	const FVector CorrectedLocation = PlanetCenter + RadialUp * MinDistance;
	const ESurfaceRecoveryResult RecoveryResult = TryCommitBoundedSurfaceRecovery(
		CorrectedLocation,
		ESurfaceRecoveryPolicy::LegacyVoid,
		nullptr,
		nullptr);
	FinalizeSurfaceAttempt(
		RecoveryResult == ESurfaceRecoveryResult::Committed);
}
