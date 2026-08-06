#include "RedCloningStation.h"

#include "Components/PointLightComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "UObject/ConstructorHelpers.h"

ARedCloningStation::ARedCloningStation()
{
	PrimaryActorTick.bCanEverTick = false;
	bReplicates = true;
	SetReplicateMovement(false);  // static once placed — no per-frame movement replication (unlike the mining site)

	SceneRoot = CreateDefaultSubobject<USceneComponent>(TEXT("SceneRoot"));
	RootComponent = SceneRoot;

	// Engine basic shapes are always present + Metal-safe. The AsteroidSpaceport pack the mining site
	// references is NOT in this project (it spawns invisible), so we build the platform from primitives.
	static ConstructorHelpers::FObjectFinder<UStaticMesh> CylAsset(TEXT("/Engine/BasicShapes/Cylinder.Cylinder"));
	static ConstructorHelpers::FObjectFinder<UStaticMesh> CubeAsset(TEXT("/Engine/BasicShapes/Cube.Cube"));

	// Deck: wide flat disc you stand on. Basic Cylinder is 100cm dia x 100cm tall (pivot centered);
	// scale (14,14,0.35) => ~700cm radius, ~35cm thick.
	DeckMesh = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("DeckMesh"));
	DeckMesh->SetupAttachment(SceneRoot);
	if (CylAsset.Succeeded()) { DeckMesh->SetStaticMesh(CylAsset.Object); }
	DeckMesh->SetRelativeScale3D(FVector(14.f, 14.f, 0.35f));
	DeckMesh->SetMobility(EComponentMobility::Movable);
	DeckMesh->SetCollisionEnabled(ECollisionEnabled::QueryAndPhysics);
	DeckMesh->SetCollisionObjectType(ECC_WorldStatic);
	DeckMesh->SetCollisionResponseToAllChannels(ECR_Block);  // incl. ECC_Pawn — this is the stand surface
	DeckMesh->SetCanEverAffectNavigation(false);

	// Core: decorative pillar under the deck for visual mass; ignore Pawn so it can't snag the diver.
	CoreMesh = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("CoreMesh"));
	CoreMesh->SetupAttachment(SceneRoot);
	if (CubeAsset.Succeeded()) { CoreMesh->SetStaticMesh(CubeAsset.Object); }
	CoreMesh->SetRelativeLocation(FVector(0.f, 0.f, -280.f));
	CoreMesh->SetRelativeScale3D(FVector(5.f, 5.f, 5.f));
	CoreMesh->SetMobility(EComponentMobility::Movable);
	CoreMesh->SetCollisionEnabled(ECollisionEnabled::QueryOnly);
	CoreMesh->SetCollisionResponseToAllChannels(ECR_Block);
	CoreMesh->SetCollisionResponseToChannel(ECC_Pawn, ECR_Ignore);
	CoreMesh->SetCanEverAffectNavigation(false);

	BeaconLight = CreateDefaultSubobject<UPointLightComponent>(TEXT("BeaconLight"));
	BeaconLight->SetupAttachment(SceneRoot);
	BeaconLight->SetRelativeLocation(FVector(0.f, 0.f, 320.f));
	BeaconLight->SetIntensity(500000.f);
	BeaconLight->SetAttenuationRadius(6000.f);
	BeaconLight->SetLightColor(FLinearColor(0.2f, 0.9f, 1.0f));

	Tags.Add(TEXT("VibeCloningStation"));
}

void ARedCloningStation::SetupDrop(const FVector& InGroundPoint, const FVector& InDropUp, float InDropAltitude, float InVirtualRadius)
{
	DropUp = InDropUp.GetSafeNormal();
	if (DropUp.IsNearlyZero()) { DropUp = FVector::UpVector; }
	DropAltitude = InDropAltitude;
	VirtualPlanetRadius = InVirtualRadius;
	// Center straight below the landing spot: pawn falls (roughly) toward it, so altitude = height and
	// the octant flips by the sign of horizontal steering. See ARedOctosphereManager::UpdateDropState.
	VirtualPlanetCenter = InGroundPoint - DropUp * VirtualPlanetRadius;

	const FVector Loc = InGroundPoint + DropUp * DropAltitude;
	FVector Forward = FVector::VectorPlaneProject(FVector::ForwardVector, DropUp).GetSafeNormal();
	if (Forward.IsNearlyZero()) { Forward = FVector::VectorPlaneProject(FVector::RightVector, DropUp).GetSafeNormal(); }
	if (Forward.IsNearlyZero()) { Forward = FVector::ForwardVector; }
	SetActorLocationAndRotation(Loc, FRotationMatrix::MakeFromZX(DropUp, Forward).Rotator());
}

FTransform ARedCloningStation::GetDropTransform() const
{
	// Deck top = origin + up * (deck half-thickness). Deck is a 100cm cylinder scaled Z 0.35 => 35cm, half 17.5.
	const FVector DeckTop = GetActorLocation() + GetActorUpVector() * (17.5f + DeckClearance);
	return FTransform(GetActorRotation(), DeckTop);
}
