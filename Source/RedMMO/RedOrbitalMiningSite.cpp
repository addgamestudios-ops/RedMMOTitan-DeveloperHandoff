#include "RedOrbitalMiningSite.h"

#include "Components/PointLightComponent.h"
#include "Components/SphereComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "UObject/ConstructorHelpers.h"

DEFINE_LOG_CATEGORY_STATIC(LogRedOrbitalMiningSite, Log, All);

namespace
{
FVector SiteSafeNormalOrUp(const FVector& Value)
{
	return Value.IsNearlyZero() ? FVector::UpVector : Value.GetSafeNormal();
}

FVector BuildTangent(const FVector& Up, const FVector& Seed)
{
	FVector Tangent = FVector::VectorPlaneProject(Seed, Up).GetSafeNormal();
	if (Tangent.IsNearlyZero())
	{
		Tangent = FVector::VectorPlaneProject(FVector::ForwardVector, Up).GetSafeNormal();
	}
	return Tangent.IsNearlyZero() ? FVector::RightVector : Tangent;
}
}

ARedOrbitalMiningSite::ARedOrbitalMiningSite()
{
	PrimaryActorTick.bCanEverTick = false;
	bReplicates = true;
	SetReplicateMovement(true);

	SceneRoot = CreateDefaultSubobject<USceneComponent>(TEXT("SceneRoot"));
	RootComponent = SceneRoot;

	static ConstructorHelpers::FObjectFinder<UStaticMesh> AsteroidPortAsset(
		TEXT("/Engine/BasicShapes/Sphere.Sphere"));
	static ConstructorHelpers::FObjectFinder<UStaticMesh> MiningAsteroidAsset(
		TEXT("/Engine/BasicShapes/Sphere.Sphere"));
	static ConstructorHelpers::FObjectFinder<UStaticMesh> FacilityAsset(
		TEXT("/Engine/BasicShapes/Cube.Cube"));
	static ConstructorHelpers::FObjectFinder<UStaticMesh> MiningRingAsset(
		TEXT("/Engine/BasicShapes/Cylinder.Cylinder"));
	static ConstructorHelpers::FObjectFinder<UStaticMesh> MiningTowerAsset(
		TEXT("/Engine/BasicShapes/Cylinder.Cylinder"));
	static ConstructorHelpers::FObjectFinder<UStaticMesh> MiningBridgeAsset(
		TEXT("/Engine/BasicShapes/Cube.Cube"));
	static ConstructorHelpers::FObjectFinder<UStaticMesh> MiningTorusAsset(
		TEXT("/Engine/BasicShapes/Cylinder.Cylinder"));
	static ConstructorHelpers::FObjectFinder<UStaticMesh> AntennaAsset(
		TEXT("/Engine/BasicShapes/Cone.Cone"));

	AsteroidPortMesh = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("AsteroidPortMesh"));
	AsteroidPortMesh->SetupAttachment(SceneRoot);
	if (AsteroidPortAsset.Succeeded())
	{
		AsteroidPortMesh->SetStaticMesh(AsteroidPortAsset.Object);
	}
	AsteroidPortMesh->SetRelativeLocation(FVector::ZeroVector);
	AsteroidPortMesh->SetRelativeRotation(FRotator(0.f, 35.f, -8.f));
	AsteroidPortMesh->SetRelativeScale3D(FVector(52.f));
	ConfigureMineableMesh(AsteroidPortMesh);

	MiningAsteroidMesh = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("MiningAsteroidMesh"));
	MiningAsteroidMesh->SetupAttachment(SceneRoot);
	if (MiningAsteroidAsset.Succeeded())
	{
		MiningAsteroidMesh->SetStaticMesh(MiningAsteroidAsset.Object);
	}
	MiningAsteroidMesh->SetRelativeLocation(FVector(-28000.f, -12000.f, -4500.f));
	MiningAsteroidMesh->SetRelativeRotation(FRotator(-12.f, -42.f, 18.f));
	MiningAsteroidMesh->SetRelativeScale3D(FVector(78.f));
	ConfigureMineableMesh(MiningAsteroidMesh);

	FacilityMesh = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("FacilityMesh"));
	FacilityMesh->SetupAttachment(SceneRoot);
	if (FacilityAsset.Succeeded())
	{
		FacilityMesh->SetStaticMesh(FacilityAsset.Object);
	}
	FacilityMesh->SetRelativeLocation(FVector(18000.f, 9500.f, 6500.f));
	FacilityMesh->SetRelativeRotation(FRotator(0.f, -18.f, 0.f));
	FacilityMesh->SetRelativeScale3D(FVector(36.f));
	ConfigureMineableMesh(FacilityMesh);

	MiningRingMesh = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("MiningRingMesh"));
	MiningRingMesh->SetupAttachment(SceneRoot);
	if (MiningRingAsset.Succeeded())
	{
		MiningRingMesh->SetStaticMesh(MiningRingAsset.Object);
	}
	MiningRingMesh->SetRelativeLocation(FVector(42000.f, -4000.f, 26000.f));
	MiningRingMesh->SetRelativeRotation(FRotator(0.f, 20.f, 90.f));
	MiningRingMesh->SetRelativeScale3D(FVector(80.f));
	ConfigureMineableMesh(MiningRingMesh);

	MiningTowerMesh = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("MiningTowerMesh"));
	MiningTowerMesh->SetupAttachment(SceneRoot);
	if (MiningTowerAsset.Succeeded())
	{
		MiningTowerMesh->SetStaticMesh(MiningTowerAsset.Object);
	}
	MiningTowerMesh->SetRelativeLocation(FVector(62000.f, 16000.f, -8000.f));
	MiningTowerMesh->SetRelativeRotation(FRotator(0.f, -28.f, 0.f));
	MiningTowerMesh->SetRelativeScale3D(FVector(55.f));
	ConfigureMineableMesh(MiningTowerMesh);

	MiningBridgeMesh = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("MiningBridgeMesh"));
	MiningBridgeMesh->SetupAttachment(SceneRoot);
	if (MiningBridgeAsset.Succeeded())
	{
		MiningBridgeMesh->SetStaticMesh(MiningBridgeAsset.Object);
	}
	MiningBridgeMesh->SetRelativeLocation(FVector(35000.f, -28000.f, 10000.f));
	MiningBridgeMesh->SetRelativeRotation(FRotator(0.f, 70.f, 0.f));
	MiningBridgeMesh->SetRelativeScale3D(FVector(65.f));
	ConfigureMineableMesh(MiningBridgeMesh);

	MiningTorusMesh = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("MiningTorusMesh"));
	MiningTorusMesh->SetupAttachment(SceneRoot);
	if (MiningTorusAsset.Succeeded())
	{
		MiningTorusMesh->SetStaticMesh(MiningTorusAsset.Object);
	}
	MiningTorusMesh->SetRelativeLocation(FVector(-15000.f, 46000.f, 16000.f));
	MiningTorusMesh->SetRelativeRotation(FRotator(20.f, 20.f, 70.f));
	MiningTorusMesh->SetRelativeScale3D(FVector(60.f));
	ConfigureMineableMesh(MiningTorusMesh);

	AntennaMesh = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("AntennaMesh"));
	AntennaMesh->SetupAttachment(SceneRoot);
	if (AntennaAsset.Succeeded())
	{
		AntennaMesh->SetStaticMesh(AntennaAsset.Object);
	}
	AntennaMesh->SetRelativeLocation(FVector(31000.f, 12000.f, 18000.f));
	AntennaMesh->SetRelativeRotation(FRotator(0.f, 0.f, 18.f));
	AntennaMesh->SetRelativeScale3D(FVector(42.f));
	ConfigureMineableMesh(AntennaMesh);

	MiningRange = CreateDefaultSubobject<USphereComponent>(TEXT("MiningRange"));
	MiningRange->SetupAttachment(SceneRoot);
	MiningRange->InitSphereRadius(180000.f);
	MiningRange->SetCollisionEnabled(ECollisionEnabled::QueryOnly);
	MiningRange->SetCollisionObjectType(ECC_WorldDynamic);
	MiningRange->SetCollisionResponseToAllChannels(ECR_Ignore);
	MiningRange->SetCollisionResponseToChannel(ECC_Pawn, ECR_Overlap);
	MiningRange->SetGenerateOverlapEvents(true);

	BeaconLight = CreateDefaultSubobject<UPointLightComponent>(TEXT("MiningBeaconLight"));
	BeaconLight->SetupAttachment(SceneRoot);
	BeaconLight->SetRelativeLocation(FVector(0.f, 0.f, 52000.f));
	BeaconLight->SetIntensity(750000.f);
	BeaconLight->SetAttenuationRadius(850000.f);
	BeaconLight->SetLightColor(FLinearColor(0.05f, 0.75f, 1.0f));

	Tags.Add(TEXT("VibeOrbitalMining"));
	Tags.Add(TEXT("VibeMarsMoonOuterEdge"));
}

void ARedOrbitalMiningSite::BeginPlay()
{
	Super::BeginPlay();
	RefreshBeacon();
}

void ARedOrbitalMiningSite::AlignToPlanet(const FVector& InPlanetCenter)
{
	PlanetCenter = InPlanetCenter;
	const FVector Up = SiteSafeNormalOrUp(GetActorLocation() - PlanetCenter);
	const FVector Forward = BuildTangent(Up, FVector::ForwardVector + FVector::RightVector * 0.35f);
	SetActorRotation(FRotationMatrix::MakeFromZX(Up, Forward).Rotator());
}

float ARedOrbitalMiningSite::RegisterMiningHit(const FHitResult& Hit, const float MiningStrength, AActor* MiningInstigator)
{
	if (OreRemaining <= 0.f)
	{
		return 0.f;
	}

	const float Extracted = FMath::Clamp(MiningStrength * ShipBoltMiningMultiplier, 0.f, OreRemaining);
	OreRemaining -= Extracted;
	RefreshBeacon();

	UE_LOG(LogRedOrbitalMiningSite, Display,
		TEXT("Mining hit: Site=%s Instigator=%s Extracted=%.0f Remaining=%.0f Impact=%s"),
		*GetName(),
		*GetNameSafe(MiningInstigator),
		Extracted,
		OreRemaining,
		*Hit.ImpactPoint.ToCompactString());

	return Extracted;
}

float ARedOrbitalMiningSite::GetOreFraction() const
{
	return OreCapacity > 0.f ? FMath::Clamp(OreRemaining / OreCapacity, 0.f, 1.f) : 0.f;
}

void ARedOrbitalMiningSite::ConfigureMineableMesh(UStaticMeshComponent* Mesh) const
{
	if (!Mesh)
	{
		return;
	}

	Mesh->SetMobility(EComponentMobility::Movable);
	Mesh->SetCollisionEnabled(ECollisionEnabled::QueryAndPhysics);
	Mesh->SetCollisionObjectType(ECC_WorldStatic);
	Mesh->SetCollisionResponseToAllChannels(ECR_Block);
	Mesh->SetCollisionResponseToChannel(ECC_Pawn, ECR_Ignore);
	Mesh->SetGenerateOverlapEvents(false);
	Mesh->SetCanEverAffectNavigation(false);
	Mesh->SetCullDistance(0);
}

void ARedOrbitalMiningSite::RefreshBeacon()
{
	if (!BeaconLight)
	{
		return;
	}

	const float Fraction = GetOreFraction();
	const FLinearColor FullColor(0.05f, 0.75f, 1.0f);
	const FLinearColor EmptyColor(1.0f, 0.22f, 0.05f);
	BeaconLight->SetLightColor(FLinearColor::LerpUsingHSV(EmptyColor, FullColor, Fraction));
	BeaconLight->SetIntensity(FMath::Lerp(180000.f, 750000.f, Fraction));
}
