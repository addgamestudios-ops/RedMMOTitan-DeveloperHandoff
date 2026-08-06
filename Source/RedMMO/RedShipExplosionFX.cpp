#include "RedShipExplosionFX.h"

#include "Components/AudioComponent.h"
#include "Components/PointLightComponent.h"
#include "Components/SceneComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "GameFramework/GameStateBase.h"
#include "Kismet/GameplayStatics.h"
#include "Materials/MaterialInterface.h"
#include "Net/UnrealNetwork.h"
#include "Particles/ParticleSystem.h"
#include "Sound/SoundBase.h"
#include "TimerManager.h"
#include "UObject/ConstructorHelpers.h"

ARedShipExplosionFX::ARedShipExplosionFX()
{
	PrimaryActorTick.bCanEverTick = true;
	PrimaryActorTick.bStartWithTickEnabled = true;
	bReplicates = true;
	bAlwaysRelevant = true;
	bNetLoadOnClient = false;
	SetReplicateMovement(false);
	SetNetUpdateFrequency(20.f);
	SetMinNetUpdateFrequency(2.f);
	InitialLifeSpan = 7.f;

	SceneRoot = CreateDefaultSubobject<USceneComponent>(TEXT("ExplosionRoot"));
	RootComponent = SceneRoot;

	FlashLight = CreateDefaultSubobject<UPointLightComponent>(TEXT("ExplosionFlash"));
	FlashLight->SetupAttachment(SceneRoot);
	FlashLight->SetMobility(EComponentMobility::Movable);
	FlashLight->SetCastShadows(false);
	FlashLight->SetVolumetricScatteringIntensity(0.7f);
	FlashLight->SetLightColor(FLinearColor(1.f, 0.16f, 0.015f));
	FlashLight->SetIntensity(0.f);
	FlashLight->SetVisibility(false);

	// These are already installed with the project's StylizedFX_2 content. Cascade is used on
	// purpose: it is CPU-sim and remains visible on Metal as well as Windows, unlike several of
	// the older GPU-only Niagara impacts that disappeared on the Mac build.
	static ConstructorHelpers::FObjectFinder<UParticleSystem> PrimaryAsset(
		TEXT("/Game/StylizedFX_2/ParticleSystems/P_Explosion_1.P_Explosion_1"));
	static ConstructorHelpers::FObjectFinder<UParticleSystem> SecondaryAsset(
		TEXT("/Game/StylizedFX_2/ParticleSystems/P_Explosion_2.P_Explosion_2"));
	PrimaryExplosion = PrimaryAsset.Succeeded() ? PrimaryAsset.Object : nullptr;
	SecondaryExplosion = SecondaryAsset.Succeeded() ? SecondaryAsset.Object : nullptr;

	// The Sand FX eruption hit is the only locally installed one-shot with enough low-frequency
	// weight for a hull detonation. It is pitched down at playback so it reads as metal/ship mass.
	static ConstructorHelpers::FObjectFinder<USoundBase> ExplosionSoundAsset(
		TEXT("/Game/Vefects/Sand_VFX/Audio/SFX_Vefects_Sand_Rock_Eruption_Hit_Cue.SFX_Vefects_Sand_Rock_Eruption_Hit_Cue"));
	ExplosionSound = ExplosionSoundAsset.Succeeded() ? ExplosionSoundAsset.Object : nullptr;

	static ConstructorHelpers::FObjectFinder<UStaticMesh> DebrisMeshAsset(
		TEXT("/Engine/BasicShapes/Cube.Cube"));
	static ConstructorHelpers::FObjectFinder<UMaterialInterface> DarkDebrisAsset(
		TEXT("/Game/StylizedFX_2/Materials/M_BlackBall.M_BlackBall"));
	static ConstructorHelpers::FObjectFinder<UMaterialInterface> HotDebrisAsset(
		TEXT("/Game/StylizedFX_2/MI/MI_Boom_00.MI_Boom_00"));
	DebrisMesh = DebrisMeshAsset.Succeeded() ? DebrisMeshAsset.Object : nullptr;
	DarkDebrisMaterial = DarkDebrisAsset.Succeeded() ? DarkDebrisAsset.Object : nullptr;
	HotDebrisMaterial = HotDebrisAsset.Succeeded() ? HotDebrisAsset.Object : nullptr;
}

ARedShipExplosionFX* ARedShipExplosionFX::SpawnForDestroyedShip(AActor* DestroyedShip)
{
	return SpawnForDestroyedActor(DestroyedShip, 3.5f, 12.f,
		/*bInAlwaysRelevant=*/true, /*NetCullDistanceCm=*/0.f, /*LifeSpanSeconds=*/7.f,
		/*StartedServerTimeSeconds=*/0.f, /*ReplayWindowSeconds=*/0.f);
}

ARedShipExplosionFX* ARedShipExplosionFX::SpawnForDepletedAsteroid(AActor* DepletedAsteroid,
	const float StartedServerTimeSeconds, const float ReplayWindowSeconds)
{
	// Deep-space asteroid fields can deplete concurrently across many facets. Limit this transient
	// cosmetic channel to nearby observers rather than broadcasting it to the entire server.
	return SpawnForDestroyedActor(DepletedAsteroid, 3.5f, 9.f,
		/*bInAlwaysRelevant=*/false, /*NetCullDistanceCm=*/1500000.f,
		/*LifeSpanSeconds=*/5.f, StartedServerTimeSeconds, ReplayWindowSeconds);
}

ARedShipExplosionFX* ARedShipExplosionFX::SpawnForDestroyedActor(AActor* DestroyedActor,
	const float MinEffectScale, const float MaxEffectScale, const bool bInAlwaysRelevant,
	const float NetCullDistanceCm, const float LifeSpanSeconds,
	const float StartedServerTimeSeconds, const float ReplayWindowSeconds)
{
	if (!IsValid(DestroyedActor) || !DestroyedActor->HasAuthority() || !DestroyedActor->GetWorld())
	{
		return nullptr;
	}

	FVector BoundsOrigin = DestroyedActor->GetActorLocation();
	FVector BoundsExtent(800.f);
	DestroyedActor->GetActorBounds(/*bOnlyCollidingComponents=*/false, BoundsOrigin, BoundsExtent,
		/*bIncludeFromChildActors=*/true);
	if (BoundsOrigin.ContainsNaN() || BoundsExtent.ContainsNaN())
	{
		BoundsOrigin = DestroyedActor->GetActorLocation();
		BoundsExtent = FVector(800.f);
	}

	const float SelectedScale = FMath::Clamp(
		static_cast<float>(BoundsExtent.GetMax() / 420.0), MinEffectScale, MaxEffectScale);
	FVector SelectedVelocity = DestroyedActor->GetVelocity();
	if (SelectedVelocity.ContainsNaN())
	{
		SelectedVelocity = FVector::ZeroVector;
	}
	SelectedVelocity = SelectedVelocity.GetClampedToMaxSize(6000.f);

	const FTransform SpawnTransform(DestroyedActor->GetActorQuat(), BoundsOrigin);
	ARedShipExplosionFX* Explosion = DestroyedActor->GetWorld()->SpawnActorDeferred<ARedShipExplosionFX>(
		ARedShipExplosionFX::StaticClass(), SpawnTransform, DestroyedActor, DestroyedActor->GetInstigator(),
		ESpawnActorCollisionHandlingMethod::AlwaysSpawn);
	if (!Explosion)
	{
		return nullptr;
	}
	Explosion->EffectScale = SelectedScale;
	Explosion->SourceVelocity = SelectedVelocity;
	Explosion->PresentationStartedServerTimeSeconds = FMath::Max(0.f, StartedServerTimeSeconds);
	Explosion->PresentationReplayWindowSeconds = FMath::Max(0.f, ReplayWindowSeconds);
	Explosion->bAlwaysRelevant = bInAlwaysRelevant;
	if (!bInAlwaysRelevant)
	{
		Explosion->SetNetCullDistanceSquared(FMath::Square(FMath::Max(10000.f, NetCullDistanceCm)));
	}
	Explosion->InitialLifeSpan = FMath::Clamp(LifeSpanSeconds, 1.f, 10.f);
	UGameplayStatics::FinishSpawningActor(Explosion, SpawnTransform);
	Explosion->ForceNetUpdate();
	return Explosion;
}

void ARedShipExplosionFX::BeginPlay()
{
	Super::BeginPlay();
	if (GetNetMode() == NM_DedicatedServer)
	{
		SetActorTickEnabled(false);
		return;
	}
	TryStartPresentation();
}

void ARedShipExplosionFX::EndPlay(const EEndPlayReason::Type EndPlayReason)
{
	GetWorldTimerManager().ClearTimer(PresentationRetryTimer);
	GetWorldTimerManager().ClearTimer(SecondaryBurstTimer);
	Super::EndPlay(EndPlayReason);
}


void ARedShipExplosionFX::TryStartPresentation()
{
	if (bPresentationStarted || GetNetMode() == NM_DedicatedServer || !GetWorld())
	{
		return;
	}

	if (PresentationReplayWindowSeconds > 0.f)
	{
		const AGameStateBase* GameState = GetWorld()->GetGameState();
		if (!GameState)
		{
			GetWorldTimerManager().SetTimer(PresentationRetryTimer, this,
				&ARedShipExplosionFX::TryStartPresentation, 0.05f, false);
			return;
		}
		const float Elapsed = FMath::Max(0.f,
			static_cast<float>(GameState->GetServerWorldTimeSeconds())
			- PresentationStartedServerTimeSeconds);
		if (Elapsed > PresentationReplayWindowSeconds)
		{
			SetActorTickEnabled(false);
			return;
		}
	}

	bPresentationStarted = true;
	SpawnPrimaryCosmetics();
	if (SecondaryExplosion)
	{
		GetWorldTimerManager().SetTimer(SecondaryBurstTimer, this,
			&ARedShipExplosionFX::SpawnSecondaryBurst, 0.12f, false);
	}
}

void ARedShipExplosionFX::SpawnPrimaryCosmetics()
{
	UWorld* World = GetWorld();
	if (!World)
	{
		return;
	}

	const float Scale = FMath::Clamp(EffectScale, 3.5f, 12.f);
	if (PrimaryExplosion)
	{
		UGameplayStatics::SpawnEmitterAtLocation(World, PrimaryExplosion, GetActorLocation(),
			GetActorRotation(), FVector(Scale), true, EPSCPoolMethod::AutoRelease, true);
	}
	if (ExplosionSound)
	{
		ExplosionSoundComponent = UGameplayStatics::SpawnSoundAtLocation(
			this,
			ExplosionSound,
			GetActorLocation(),
			GetActorRotation(),
			FMath::Clamp(0.75f + Scale * 0.08f, 1.f, 1.7f),
			0.68f);
		bLocalExplosionSoundStarted = IsValid(ExplosionSoundComponent);
	}

	PeakLightIntensity = FMath::Clamp(Scale * 90000.f, 350000.f, 1000000.f);
	if (FlashLight)
	{
		FlashLight->SetAttenuationRadius(FMath::Clamp(Scale * 1350.f, 5000.f, 18000.f));
		FlashLight->SetIntensity(PeakLightIntensity);
		FlashLight->SetVisibility(true);
	}
	SpawnChaosDebris();
}

FString ARedShipExplosionFX::GetExplosionSoundAssetPath() const
{
	return ExplosionSound ? ExplosionSound->GetPathName() : FString();
}

void ARedShipExplosionFX::SpawnSecondaryBurst()
{
	if (!SecondaryExplosion || !GetWorld() || GetNetMode() == NM_DedicatedServer)
	{
		return;
	}
	const float Scale = FMath::Clamp(EffectScale * 0.58f, 2.5f, 7.f);
	const FVector Offset = GetActorUpVector() * EffectScale * 18.f;
	const FRotator Rotation = (GetActorQuat() * FQuat(FVector::RightVector, HALF_PI)).Rotator();
	UGameplayStatics::SpawnEmitterAtLocation(GetWorld(), SecondaryExplosion,
		GetActorLocation() + Offset, Rotation, FVector(Scale), true,
		EPSCPoolMethod::AutoRelease, true);
}

void ARedShipExplosionFX::SpawnChaosDebris()
{
	if (!DebrisMesh || !GetWorld())
	{
		return;
	}

	const float Scale = FMath::Clamp(EffectScale, 3.5f, 12.f);
	const int32 PieceCount = FMath::Clamp(FMath::RoundToInt(Scale * 1.35f), 8, 16);
	const uint32 LocationHash = GetTypeHash(GetActorLocation());
	FRandomStream Random(static_cast<int32>(LocationHash ^ 0x6D2B79F5u));
	DebrisPieces.Reserve(PieceCount);

	for (int32 Index = 0; Index < PieceCount; ++Index)
	{
		UStaticMeshComponent* Piece = NewObject<UStaticMeshComponent>(this, NAME_None, RF_Transient);
		if (!Piece)
		{
			continue;
		}
		AddInstanceComponent(Piece);
		Piece->SetMobility(EComponentMobility::Movable);
		Piece->SetStaticMesh(DebrisMesh);
		if (Index % 3 == 0 && HotDebrisMaterial)
		{
			Piece->SetMaterial(0, HotDebrisMaterial);
		}
		else if (DarkDebrisMaterial)
		{
			Piece->SetMaterial(0, DarkDebrisMaterial);
		}
		Piece->SetCollisionEnabled(ECollisionEnabled::PhysicsOnly);
		Piece->SetCollisionObjectType(ECC_PhysicsBody);
		Piece->SetCollisionResponseToAllChannels(ECR_Ignore);
		Piece->SetCollisionResponseToChannel(ECC_WorldStatic, ECR_Block);
		Piece->SetCollisionResponseToChannel(static_cast<ECollisionChannel>(13), ECR_Block);
		Piece->SetGenerateOverlapEvents(false);
		Piece->SetNotifyRigidBodyCollision(false);
		Piece->SetCanEverAffectNavigation(false);
		Piece->SetCastShadow(true);
		Piece->RegisterComponentWithWorld(GetWorld());

		FVector Direction = Random.VRand();
		if (Direction.IsNearlyZero())
		{
			Direction = FVector::UpVector;
		}
		const float PieceScale = Scale * Random.FRandRange(0.12f, 0.34f);
		FVector IrregularScale(PieceScale,
			PieceScale * Random.FRandRange(0.22f, 0.62f),
			PieceScale * Random.FRandRange(0.18f, 0.55f));
		if (Index & 1)
		{
			Swap(IrregularScale.X, IrregularScale.Z);
		}
		Piece->SetWorldLocation(GetActorLocation() + Direction * Scale * Random.FRandRange(10.f, 42.f));
		Piece->SetWorldRotation(FRotator(Random.FRandRange(-180.f, 180.f),
			Random.FRandRange(-180.f, 180.f), Random.FRandRange(-180.f, 180.f)));
		Piece->SetWorldScale3D(IrregularScale);
		Piece->SetSimulatePhysics(true);
		Piece->SetEnableGravity(false);
		Piece->SetLinearDamping(0.18f);
		Piece->SetAngularDamping(0.12f);
		Piece->SetMassOverrideInKg(NAME_None, Random.FRandRange(12.f, 45.f), true);
		const FVector EjectionVelocity = Direction * Scale * Random.FRandRange(130.f, 260.f);
		Piece->SetPhysicsLinearVelocity(SourceVelocity * 0.45f + EjectionVelocity);
		Piece->SetPhysicsAngularVelocityInDegrees(Random.VRand() * Random.FRandRange(120.f, 420.f));
		Piece->WakeAllRigidBodies();
		DebrisPieces.Add(Piece);
	}
}

void ARedShipExplosionFX::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	ElapsedSeconds += FMath::Max(0.f, DeltaSeconds);
	const float Alpha = 1.f - FMath::Clamp(ElapsedSeconds / 0.78f, 0.f, 1.f);
	if (FlashLight)
	{
		FlashLight->SetIntensity(PeakLightIntensity * Alpha * Alpha);
		if (Alpha <= 0.f)
		{
			FlashLight->SetVisibility(false);
		}
	}
	if (ElapsedSeconds >= 0.8f)
	{
		SetActorTickEnabled(false);
	}
}

void ARedShipExplosionFX::GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const
{
	Super::GetLifetimeReplicatedProps(OutLifetimeProps);
	DOREPLIFETIME(ARedShipExplosionFX, EffectScale);
	DOREPLIFETIME(ARedShipExplosionFX, SourceVelocity);
	DOREPLIFETIME(ARedShipExplosionFX, PresentationStartedServerTimeSeconds);
	DOREPLIFETIME(ARedShipExplosionFX, PresentationReplayWindowSeconds);
}
