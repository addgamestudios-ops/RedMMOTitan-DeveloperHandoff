#include "RedResourcePickup.h"

#include "Components/AudioComponent.h"
#include "Components/SphereComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "GameFramework/Pawn.h"
#include "Kismet/GameplayStatics.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Materials/MaterialInterface.h"
#include "Net/UnrealNetwork.h"
#include "Sound/SoundBase.h"
#include "UObject/ConstructorHelpers.h"
#include "RedPlayerCharacter.h"

ARedResourcePickup::ARedResourcePickup()
{
	PrimaryActorTick.bCanEverTick = true;
	bReplicates = true;
	bAlwaysRelevant = false;
	bNetLoadOnClient = false;
	SetReplicateMovement(false);
	SetNetCullDistanceSquared(FMath::Square(1500000.f));
	SetNetUpdateFrequency(2.f);
	SetMinNetUpdateFrequency(0.5f);

	SceneRoot = CreateDefaultSubobject<USceneComponent>(TEXT("SceneRoot"));
	SetRootComponent(SceneRoot);

	// Walk-over collect volume.
	CollectSphere = CreateDefaultSubobject<USphereComponent>(TEXT("CollectSphere"));
	CollectSphere->SetupAttachment(SceneRoot);
	CollectSphere->InitSphereRadius(120.f);
	CollectSphere->SetCollisionEnabled(ECollisionEnabled::QueryOnly);
	CollectSphere->SetCollisionObjectType(ECC_WorldDynamic);
	CollectSphere->SetCollisionResponseToAllChannels(ECR_Ignore);
	CollectSphere->SetCollisionResponseToChannel(ECC_Pawn, ECR_Overlap);
	CollectSphere->SetGenerateOverlapEvents(true);

	// Visible glowing chunk (non-colliding, so it never blocks the player or bolts).
	MeshComp = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("MeshComp"));
	MeshComp->SetupAttachment(SceneRoot);
	MeshComp->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	MeshComp->SetGenerateOverlapEvents(false);
	MeshComp->SetCastShadow(false);
	MeshComp->SetRelativeScale3D(FVector(0.35f));

	static ConstructorHelpers::FObjectFinder<UStaticMesh> CubeMesh(TEXT("/Engine/BasicShapes/Cube"));
	if (CubeMesh.Succeeded())
	{
		MeshComp->SetStaticMesh(CubeMesh.Object);
	}

	// Direct-credit depletion receipts use a short mining-impact accent as local owner feedback.
	// The receipt's replicated instigator selects the one listening player; observers stay silent.
	static ConstructorHelpers::FObjectFinder<USoundBase> RewardSoundAsset(
		TEXT("/Game/Vefects/Sand_VFX/Audio/SFX_Vefects_Sand_Rock_Hit_02_Cue.SFX_Vefects_Sand_Rock_Hit_02_Cue"));
	RewardSound = RewardSoundAsset.Succeeded() ? RewardSoundAsset.Object : nullptr;

	InitialLifeSpan = 120.f;  // resources linger a while, then despawn if uncollected
}

ERedResourceType ARedResourcePickup::TypeForDepth(float DepthBelowSurfaceCm)
{
	if (DepthBelowSurfaceCm >= 4000.f) return ERedResourceType::Crystal;
	if (DepthBelowSurfaceCm >= 1800.f) return ERedResourceType::Iron;
	return ERedResourceType::Stone;
}

FLinearColor ARedResourcePickup::ColorForType(ERedResourceType Type)
{
	switch (Type)
	{
	case ERedResourceType::Crystal: return FLinearColor(0.20f, 0.80f, 0.95f);
	case ERedResourceType::Iron:    return FLinearColor(0.85f, 0.45f, 0.20f);
	case ERedResourceType::Stone:
	default:                        return FLinearColor(0.55f, 0.55f, 0.55f);
	}
}

void ARedResourcePickup::InitResource(ERedResourceType InType, int32 InAmount,
	const FVector& PlanetCenter, const bool bInCollectible)
{
	if (!HasAuthority())
	{
		return;
	}

	ResourceType = InType;
	Amount = FMath::Max(1, InAmount);
	bCollectible = bInCollectible;
	if (!bCollectible)
	{
		// Directly granted inventory uses this actor only as a short replicated receipt.
		InitialLifeSpan = 4.f;
		if (HasActorBegunPlay())
		{
			SetLifeSpan(InitialLifeSpan);
		}
	}

	RadialUp = (GetActorLocation() - PlanetCenter).GetSafeNormal();
	if (RadialUp.IsNearlyZero())
	{
		RadialUp = FVector::UpVector;
	}

	ApplyResourcePresentation();
	ApplyCollectionState();
	TryStartLocalRewardSound();
	FlushNetDormancy();
	ForceNetUpdate();
}

void ARedResourcePickup::ApplyResourcePresentation()
{
	// Tint the mesh's existing cook-safe material to the resource color.
	if (MeshComp && MeshComp->GetStaticMesh())
	{
		if (!GlowMID)
		{
			GlowMID = MeshComp->CreateAndSetMaterialInstanceDynamic(0);
		}
		if (GlowMID)
		{
			const FLinearColor ResourceColor = ColorForType(ResourceType);
			GlowMID->SetVectorParameterValue(TEXT("Color"), ResourceColor);
			GlowMID->SetVectorParameterValue(TEXT("BaseColor"), ResourceColor);
			GlowMID->SetVectorParameterValue(TEXT("GlowColor"), ResourceColor);
		}
	}
}

void ARedResourcePickup::BeginPlay()
{
	Super::BeginPlay();
	ApplyResourcePresentation();
	ApplyCollectionState();
	TryStartLocalRewardSound();
	if (HasAuthority() && bCollectible && CollectSphere)
	{
		CollectSphere->OnComponentBeginOverlap.AddDynamic(this, &ARedResourcePickup::OnCollectOverlap);
	}
}

void ARedResourcePickup::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	TimeAlive += DeltaSeconds;

	// Spin around the local up + gently bob so it reads as a floating collectible.
	if (MeshComp)
	{
		MeshComp->AddLocalRotation(FRotator(0.f, 120.f * DeltaSeconds, 0.f));
		const float Bob = FMath::Sin(TimeAlive * 2.2f) * 6.f;
		MeshComp->SetRelativeLocation(RadialUp.IsNearlyZero() ? FVector(0, 0, Bob) : FVector::ZeroVector);
		MeshComp->SetWorldLocation(GetActorLocation() + RadialUp * Bob);
	}
}

void ARedResourcePickup::OnCollectOverlap(UPrimitiveComponent* /*OverlappedComp*/, AActor* OtherActor,
	UPrimitiveComponent* /*OtherComp*/, int32 /*OtherBodyIndex*/, bool /*bFromSweep*/, const FHitResult& /*Sweep*/)
{
	if (!HasAuthority() || !bCollectible || bConsumed)
	{
		return;
	}

	ARedPlayerCharacter* Player = Cast<ARedPlayerCharacter>(OtherActor);
	if (!Player || Player->bIsEnemy)
	{
		return;
	}
	bConsumed = true;
	if (CollectSphere)
	{
		CollectSphere->SetCollisionEnabled(ECollisionEnabled::NoCollision);
		CollectSphere->SetGenerateOverlapEvents(false);
	}
	Player->AddResource(ResourceType, Amount);
	Destroy();
}

void ARedResourcePickup::OnRep_ResourceDefinition()
{
	ApplyResourcePresentation();
	ApplyCollectionState();
	TryStartLocalRewardSound();
}

void ARedResourcePickup::OnRep_Instigator()
{
	Super::OnRep_Instigator();
	TryStartLocalRewardSound();
}

void ARedResourcePickup::TryStartLocalRewardSound()
{
	if (bLocalRewardSoundStarted
		|| bCollectible
		|| !RewardSound
		|| GetNetMode() == NM_DedicatedServer)
	{
		return;
	}

	const APawn* RewardInstigator = GetInstigator();
	if (!RewardInstigator || !RewardInstigator->IsLocallyControlled())
	{
		return;
	}

	RewardSoundComponent = UGameplayStatics::SpawnSound2D(
		this,
		RewardSound,
		0.82f,
		1.08f,
		0.f,
		nullptr,
		false,
		true);
	bLocalRewardSoundStarted = IsValid(RewardSoundComponent);
}

FString ARedResourcePickup::GetRewardSoundAssetPath() const
{
	return RewardSound ? RewardSound->GetPathName() : FString();
}

void ARedResourcePickup::ApplyCollectionState()
{
	if (!CollectSphere)
	{
		return;
	}
	const bool bEnableAuthorityCollection = HasAuthority() && bCollectible && !bConsumed;
	CollectSphere->SetCollisionEnabled(bEnableAuthorityCollection
		? ECollisionEnabled::QueryOnly : ECollisionEnabled::NoCollision);
	CollectSphere->SetGenerateOverlapEvents(bEnableAuthorityCollection);
}

void ARedResourcePickup::GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const
{
	Super::GetLifetimeReplicatedProps(OutLifetimeProps);
	DOREPLIFETIME(ARedResourcePickup, ResourceType);
	DOREPLIFETIME(ARedResourcePickup, Amount);
	DOREPLIFETIME(ARedResourcePickup, bCollectible);
	DOREPLIFETIME(ARedResourcePickup, RadialUp);
}
