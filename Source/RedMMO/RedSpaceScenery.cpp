#include "RedSpaceScenery.h"

#include "Components/HierarchicalInstancedStaticMeshComponent.h"
#include "Components/DirectionalLightComponent.h"
#include "Components/ExponentialHeightFogComponent.h"
#include "Components/LightComponent.h"
#include "Components/PostProcessComponent.h"
#include "Components/SceneComponent.h"
#include "Components/SkyLightComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "Camera/PlayerCameraManager.h"
#include "GameFramework/PlayerController.h"
#include "Kismet/GameplayStatics.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Materials/MaterialInterface.h"
#include "Misc/CommandLine.h"
#include "Misc/Parse.h"
#include "ProceduralMeshComponent.h"
#include "RedGravityBodies.h"
#include "RedPlanetPresentationTuning.h"
#include "RedMineableAsteroid.h"
#include "RedSpaceExposureCameraModifier.h"
#include "UObject/ConstructorHelpers.h"

DEFINE_LOG_CATEGORY_STATIC(LogRedSpaceScenery, Log, All);

namespace
{
// This is the rejected hand-built gas-giant-with-bands prototype, not PlanetGen
// 1.5's playable ACLMRingWorld. Keep the old implementation available for source
// rollback, but never spawn or register it in the production system.
constexpr bool bEnableLegacySaturnPrototype = false;

struct FStarSectionBuffers
{
	TArray<FVector> Vertices;
	TArray<int32> Triangles;
	TArray<FVector> Normals;
	TArray<FVector2D> UV0;
	TArray<FColor> Colors;
	TArray<FProcMeshTangent> Tangents;

	void Reserve(const int32 StarCapacity)
	{
		Vertices.Reserve(StarCapacity * 7);
		Triangles.Reserve(StarCapacity * 6 * 3);
		Normals.Reserve(StarCapacity * 7);
		UV0.Reserve(StarCapacity * 7);
		Colors.Reserve(StarCapacity * 7);
		Tangents.Reserve(StarCapacity * 7);
	}
};

void AddStarDisc(
	FStarSectionBuffers& Buffers, const FVector& Center, const float RadiusCm,
	const FVector& RadialDirection)
{
	// A flat, texture-free hexagonal disc is much more stable than the old tiny octahedron.
	// The camera remains at the centre of this shell, so the radial plane is a billboard
	// without per-star transforms. It also cannot read as a warm rock silhouette when TAA
	// resolves a sub-pixel facet.
	const FVector Direction = RadialDirection.GetSafeNormal();
	FVector TangentX = FVector::RightVector;
	FVector TangentY = FVector::UpVector;
	Direction.FindBestAxisVectors(TangentX, TangentY);
	const FVector InwardNormal = -Direction;
	const int32 BaseVertex = Buffers.Vertices.Num();
	Buffers.Vertices.Add(Center);
	Buffers.Normals.Add(InwardNormal);
	Buffers.UV0.Add(FVector2D(0.5f, 0.5f));
	Buffers.Colors.Add(FColor::White);
	Buffers.Tangents.Emplace(TangentX, false);

	constexpr int32 SideCount = 6;
	for (int32 Side = 0; Side < SideCount; ++Side)
	{
		const float Angle = (2.f * PI * Side) / SideCount;
		const float X = FMath::Cos(Angle);
		const float Y = FMath::Sin(Angle);
		Buffers.Vertices.Add(Center + (TangentX * X + TangentY * Y) * RadiusCm);
		Buffers.Normals.Add(InwardNormal);
		Buffers.UV0.Add(FVector2D(0.5f + X * 0.5f, 0.5f + Y * 0.5f));
		Buffers.Colors.Add(FColor::White);
		Buffers.Tangents.Emplace(TangentX, false);
	}

	for (int32 Side = 0; Side < SideCount; ++Side)
	{
		// FindBestAxisVectors returns Axis2 = Axis1 x Direction, so TangentX x
		// TangentY points inward. The player views this camera-relative shell from
		// inside; current-then-next therefore produces the inward front face.
		Buffers.Triangles.Add(BaseVertex);
		Buffers.Triangles.Add(BaseVertex + 1 + Side);
		Buffers.Triangles.Add(BaseVertex + 1 + ((Side + 1) % SideCount));
		// Include the reverse winding as a geometry-level fallback. The main player
		// view and auxiliary scene captures do not always agree on reverse-culling,
		// and the star field must remain visible from inside either way.
		Buffers.Triangles.Add(BaseVertex);
		Buffers.Triangles.Add(BaseVertex + 1 + ((Side + 1) % SideCount));
		Buffers.Triangles.Add(BaseVertex + 1 + Side);
	}
}
}

ARedSpaceScenery::ARedSpaceScenery()
{
	PrimaryActorTick.bCanEverTick = true;
	PrimaryActorTick.bStartWithTickEnabled = true;
	// The star shell follows only the local camera. A 5 Hz transform produced large temporal
	// motion-vector jumps and the visible elongated trails reported in the packaged build.
	// One lightweight component transform per frame keeps the celestial points stationary.
	PrimaryActorTick.TickInterval = 0.f;
	bReplicates = true;
	bAlwaysRelevant = true;
	SetReplicateMovement(false);
	Tags.Add(TEXT("RedSpaceScenery"));

	SceneryRoot = CreateDefaultSubobject<USceneComponent>(TEXT("SceneryRoot"));
	SetRootComponent(SceneryRoot);

	OrbitExposurePostProcess =
		CreateDefaultSubobject<UPostProcessComponent>(TEXT("OrbitExposurePostProcess"));
	OrbitExposurePostProcess->SetupAttachment(SceneryRoot);
	OrbitExposurePostProcess->bUnbound = true;
	OrbitExposurePostProcess->Priority = 10000.f;
	OrbitExposurePostProcess->BlendWeight = 0.f;
	// Kept for serialized compatibility, but the active camera modifier below is
	// the authoritative path. World components are blended before vehicle camera
	// overrides and did not survive the first/third-person ship camera hand-off.
	OrbitExposurePostProcess->bEnabled = false;
	FPostProcessSettings& OrbitExposure = OrbitExposurePostProcess->Settings;
	OrbitExposure.bOverride_AutoExposureMethod = true;
	// Manual exposure is unit-independent. Histogram min/max is interpreted in
	// different units depending on an early renderer flag and was still being
	// overridden by a late camera blend in the development client.
	OrbitExposure.AutoExposureMethod = AEM_Manual;
	OrbitExposure.bOverride_AutoExposureMinBrightness = true;
	OrbitExposure.AutoExposureMinBrightness =
		RedPlanetPresentationTuning::OrbitExposureTargetEv;
	OrbitExposure.bOverride_AutoExposureMaxBrightness = true;
	OrbitExposure.AutoExposureMaxBrightness =
		RedPlanetPresentationTuning::OrbitExposureTargetEv;
	OrbitExposure.bOverride_AutoExposureBias = true;
	OrbitExposure.AutoExposureBias =
		RedPlanetPresentationTuning::OrbitExposureBias;
	OrbitExposure.bOverride_AutoExposureApplyPhysicalCameraExposure = true;
	OrbitExposure.AutoExposureApplyPhysicalCameraExposure = false;
	OrbitExposure.bOverride_AutoExposureSpeedUp = true;
	OrbitExposure.AutoExposureSpeedUp = 4.f;
	OrbitExposure.bOverride_AutoExposureSpeedDown = true;
	OrbitExposure.AutoExposureSpeedDown = 2.f;
	// Prevent local-exposure contrast recovery from lifting the black surround and
	// clipping the sunlit planet after the global exposure has been pinned.
	OrbitExposure.bOverride_LocalExposureHighlightContrastScale = true;
	OrbitExposure.LocalExposureHighlightContrastScale = 1.f;
	OrbitExposure.bOverride_LocalExposureShadowContrastScale = true;
	OrbitExposure.LocalExposureShadowContrastScale = 1.f;
	OrbitExposure.bOverride_LocalExposureDetailStrength = true;
	OrbitExposure.LocalExposureDetailStrength = 0.f;

	static ConstructorHelpers::FObjectFinder<UMaterialInterface> SurfaceSkyMaterialFinder(
		TEXT("/Game/RedMMO/Environment/M_RedBabyBlueSurfaceSky.M_RedBabyBlueSurfaceSky"));
	SurfaceBabyBlueSkyMaterial = SurfaceSkyMaterialFinder.Object;

	StarField = CreateDefaultSubobject<UProceduralMeshComponent>(TEXT("StarField"));
	StarField->SetupAttachment(SceneryRoot);
	StarField->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	StarField->SetCastShadow(false);
	StarField->SetReceivesDecals(false);
	StarField->SetCanEverAffectNavigation(false);
	StarField->SetMobility(EComponentMobility::Movable);
	StarField->bUseAsyncCooking = false;
	StarField->bNeverDistanceCull = true;
	StarField->BoundsScale = 1.25f;
	StarField->SetVisibility(false, true);
	StarField->SetHiddenInGame(true, true);

	AnalyticStarDome = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("AnalyticStarDome"));
	AnalyticStarDome->SetupAttachment(SceneryRoot);
	AnalyticStarDome->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	AnalyticStarDome->SetGenerateOverlapEvents(false);
	AnalyticStarDome->SetCastShadow(false);
	AnalyticStarDome->SetReceivesDecals(false);
	AnalyticStarDome->SetCanEverAffectNavigation(false);
	AnalyticStarDome->SetMobility(EComponentMobility::Movable);
	AnalyticStarDome->bNeverDistanceCull = true;
	AnalyticStarDome->BoundsScale = 1.25f;
	AnalyticStarDome->SetVisibility(false, true);
	AnalyticStarDome->SetHiddenInGame(true, true);

	Asteroids = CreateDefaultSubobject<UHierarchicalInstancedStaticMeshComponent>(TEXT("Asteroids"));
	Asteroids->SetupAttachment(SceneryRoot);
	Asteroids->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	Asteroids->SetCastShadow(false);
	Asteroids->SetReceivesDecals(false);
	Asteroids->SetCanEverAffectNavigation(false);
	Asteroids->SetCullDistances(1200000, static_cast<int32>(
		RedPlanetPresentationTuning::AsteroidRenderCullDistanceCm));
	Asteroids->bNeverDistanceCull = false;
	Asteroids->BoundsScale = 1.f;

	Moon = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("Moon"));
	Moon->SetupAttachment(SceneryRoot);
	Moon->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	Moon->SetCastShadow(false);
	Moon->SetReceivesDecals(false);
	Moon->SetCanEverAffectNavigation(false);
	Moon->SetMobility(EComponentMobility::Movable);
	Moon->SetGenerateOverlapEvents(false);
	Moon->CanCharacterStepUpOn = ECB_Yes;
	Moon->bNeverDistanceCull = true;
	Moon->BoundsScale = 4.f;
	Moon->ComponentTags.Add(TEXT("RedGravityBody.Moon"));
	Moon->ComponentTags.Add(TEXT("RedGravityBodyId=moon.red.mars.primary"));

	// The rock material on the reachable moon is deliberately retained.  This very thin,
	// unlit shell only supplies the pale disc/limb that must remain visible from the dark
	// planet surface; it has no collision and cannot create the old invisible-wall problem.
	MoonGlow = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("MoonGlow"));
	MoonGlow->SetupAttachment(Moon);
	MoonGlow->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	MoonGlow->SetCastShadow(false);
	MoonGlow->SetReceivesDecals(false);
	MoonGlow->SetCanEverAffectNavigation(false);
	MoonGlow->SetGenerateOverlapEvents(false);
	MoonGlow->SetMobility(EComponentMobility::Movable);
	MoonGlow->SetRelativeScale3D(FVector(1.018f));
	MoonGlow->bNeverDistanceCull = true;
	MoonGlow->BoundsScale = 4.f;

	RingWorldBody = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("RingWorldBody"));
	RingWorldBody->SetupAttachment(SceneryRoot);
	RingWorldBody->SetMobility(EComponentMobility::Movable);
	// The ringed primary is a gas giant landmark. It has no walkable surface and must not
	// create a planet-sized invisible wall. The three rocky moons below are the playable bodies.
	RingWorldBody->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	RingWorldBody->SetCollisionResponseToAllChannels(ECR_Ignore);
	RingWorldBody->SetGenerateOverlapEvents(false);
	RingWorldBody->SetCanEverAffectNavigation(false);
	RingWorldBody->SetReceivesDecals(false);
	RingWorldBody->bNeverDistanceCull = true;
	RingWorldBody->BoundsScale = 6.f;
	RingWorldBody->ComponentTags.Add(TEXT("RedSpaceLandmark.RingWorld"));
	RingWorldBody->SetVisibility(false, true);
	RingWorldBody->SetHiddenInGame(true, true);

	// The annular mesh is visual only. Keeping it collision-free prevents a large invisible
	// wall while a ship crosses the rings; only the visible planet and moon surfaces collide.
	RingWorldBands = CreateDefaultSubobject<UProceduralMeshComponent>(TEXT("RingWorldBands"));
	RingWorldBands->SetupAttachment(SceneryRoot);
	RingWorldBands->SetMobility(EComponentMobility::Movable);
	RingWorldBands->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	RingWorldBands->SetGenerateOverlapEvents(false);
	RingWorldBands->SetCastShadow(false);
	RingWorldBands->SetReceivesDecals(false);
	RingWorldBands->SetCanEverAffectNavigation(false);
	RingWorldBands->bUseAsyncCooking = false;
	RingWorldBands->bNeverDistanceCull = true;
	RingWorldBands->BoundsScale = 8.f;
	RingWorldBands->SetVisibility(false, true);
	RingWorldBands->SetHiddenInGame(true, true);

	auto ConfigurePlayableMoon = [this](const FName Name)
	{
		UStaticMeshComponent* Component = CreateDefaultSubobject<UStaticMeshComponent>(Name);
		Component->SetupAttachment(SceneryRoot);
		Component->SetMobility(EComponentMobility::Movable);
		Component->SetCollisionEnabled(ECollisionEnabled::NoCollision);
		Component->SetCollisionObjectType(ECC_WorldStatic);
		Component->SetCollisionResponseToAllChannels(ECR_Ignore);
		Component->SetGenerateOverlapEvents(false);
		Component->SetCanEverAffectNavigation(false);
		Component->SetReceivesDecals(false);
		Component->CanCharacterStepUpOn = ECB_Yes;
		Component->bNeverDistanceCull = true;
		Component->BoundsScale = 5.f;
		Component->ComponentTags.Add(TEXT("RedGravityBody.PlayableRingMoon"));
		Component->SetVisibility(false, true);
		Component->SetHiddenInGame(true, true);
		return Component;
	};
	RingMoonA = ConfigurePlayableMoon(TEXT("RingMoonA"));
	RingMoonB = ConfigurePlayableMoon(TEXT("RingMoonB"));
	RingMoonC = ConfigurePlayableMoon(TEXT("RingMoonC"));
	RingMoonA->ComponentTags.Add(TEXT("RedGravityBodyId=moon.red.ring-01.a"));
	RingMoonB->ComponentTags.Add(TEXT("RedGravityBodyId=moon.red.ring-01.b"));
	RingMoonC->ComponentTags.Add(TEXT("RedGravityBodyId=moon.red.ring-01.c"));

	MoonAuditKeyLight = CreateDefaultSubobject<UDirectionalLightComponent>(TEXT("MoonAuditKeyLight"));
	MoonAuditKeyLight->SetupAttachment(SceneryRoot);
	MoonAuditKeyLight->SetMobility(EComponentMobility::Movable);
	// The T04 surface-night histogram needs a slightly stronger isolated key to
	// expose the purchased rock material without reintroducing solar clipping.
	MoonAuditKeyLight->SetIntensity(21.25f);
	MoonAuditKeyLight->SetLightColor(FLinearColor(0.42f, 0.60f, 0.98f));
	MoonAuditKeyLight->SetIndirectLightingIntensity(0.f);
	MoonAuditKeyLight->SetVolumetricScatteringIntensity(0.f);
	MoonAuditKeyLight->SetSpecularScale(0.15f);
	MoonAuditKeyLight->SetCastShadows(false);
	MoonAuditKeyLight->SetAtmosphereSunLight(false);
	MoonAuditKeyLight->SetForwardShadingPriority(0);
	MoonAuditKeyLight->SetLightingChannels(false, false, true);
	MoonAuditKeyLight->SetVisibility(false, true);
	MoonAuditKeyLight->SetHiddenInGame(true, true);

	static ConstructorHelpers::FObjectFinder<UStaticMesh> SphereMesh(
		TEXT("/Engine/BasicShapes/Sphere.Sphere"));
	static ConstructorHelpers::FObjectFinder<UStaticMesh> SkySphereMesh(
		TEXT("/Engine/EngineSky/SM_SkySphere.SM_SkySphere"));
	static ConstructorHelpers::FObjectFinder<UStaticMesh> AsteroidMesh(
		TEXT("/Game/StylizedDesertOasis/Meshes/Rocks/SM_Boulder_03.SM_Boulder_03"));
	if (SphereMesh.Succeeded())
	{
		NightT03BasicSphereMesh = SphereMesh.Object;
		Asteroids->SetStaticMesh(AsteroidMesh.Succeeded() ? AsteroidMesh.Object : SphereMesh.Object);
		AnalyticStarDome->SetStaticMesh(SphereMesh.Object);
		// Engine sphere radius is 50 cm. A 1000 km camera-relative radius remains behind
		// the physical moon and planet while requiring only one low-poly sky draw.
		AnalyticStarDome->SetRelativeScale3D(FVector(2000000.f));
		Moon->SetStaticMesh(SphereMesh.Object);
		MoonGlow->SetStaticMesh(SphereMesh.Object);
		RingWorldBody->SetStaticMesh(SphereMesh.Object);
		RingMoonA->SetStaticMesh(SphereMesh.Object);
		RingMoonB->SetStaticMesh(SphereMesh.Object);
		RingMoonC->SetStaticMesh(SphereMesh.Object);
	}
	NightT03SkySphereMesh = SkySphereMesh.Object;
	static ConstructorHelpers::FObjectFinder<UMaterialInterface> AnalyticStarDomeMaterialFinder(
		TEXT("/Game/RedMMO/Environment/M_RedAnalyticStarDomeCubeUV_V2.M_RedAnalyticStarDomeCubeUV_V2"));
	AnalyticStarDomeMaterial = AnalyticStarDomeMaterialFinder.Object;
	if (AnalyticStarDomeMaterial)
	{
		AnalyticStarDome->SetMaterial(0, AnalyticStarDomeMaterial);
	}
	static ConstructorHelpers::FObjectFinder<UMaterialInterface> NightT03StarDiagnosticMaterialFinder(
		TEXT("/Game/RedMMO/Environment/Tests/M_RedStar_T03Diagnostic.M_RedStar_T03Diagnostic"));
	NightT03StarDiagnosticMaterial = NightT03StarDiagnosticMaterialFinder.Object;
	static ConstructorHelpers::FObjectFinder<UMaterialInterface> NightWaterT04StarOverlayProofMaterialFinder(
		TEXT("/Game/RedMMO/Environment/Tests/M_RedStar_T03OverlayDiagnostic.M_RedStar_T03OverlayDiagnostic"));
	NightWaterT04StarOverlayProofMaterial =
		NightWaterT04StarOverlayProofMaterialFinder.Object;
	static ConstructorHelpers::FObjectFinder<UMaterialInterface> NightT03MilkyWayMaterialFinder(
		TEXT("/Game/RedMMO/Environment/Tests/M_RedStar_T03MilkyWayWorldDir.M_RedStar_T03MilkyWayWorldDir"));
	NightT03MilkyWayMaterial = NightT03MilkyWayMaterialFinder.Object;

	// Prefer the project-owned texture-free opaque IsSky material for the procedural
	// hexagons. The masked texture path and the translucent additive fallback were both
	// black in the main EV13.5 camera even though the geometry and visibility gates passed.
	static ConstructorHelpers::FObjectFinder<UMaterialInterface> SolidStarMaterial(
		TEXT("/Game/RedMMO/Environment/M_RedStarSolid.M_RedStarSolid"));
	static ConstructorHelpers::FObjectFinder<UMaterialInterface> AuthoredStarMaterial(
		TEXT("/Game/RedMMO/Environment/M_RedStarSpriteMasked.M_RedStarSpriteMasked"));
	static ConstructorHelpers::FObjectFinder<UMaterialInterface> FallbackStarMaterial(
		TEXT("/Game/ProjectilesVol1/Materials/M_Additive.M_Additive"));
	// V2 real-GPU evidence proved the masked sprite material on this exact local
	// procedural vertex factory. Keep it as the fallback behind the analytic sphere;
	// M_RedStarSolid is retained only as the final project-owned alternative.
	// The masked sprite asset depends on a texture-alpha path that compiled but rendered
	// fully transparent in the real SM6 viewport. Prefer the project-owned opaque, unlit,
	// two-sided material for the geometry-backed shell; keep the authored sprite only as
	// the fallback when that deterministic material is unavailable.
	UMaterialInterface* StarBase = SolidStarMaterial.Succeeded()
		? SolidStarMaterial.Object
		: (AuthoredStarMaterial.Succeeded()
			? AuthoredStarMaterial.Object : FallbackStarMaterial.Object);
	bStarMaterialUsesEmissionParameter = StarBase != FallbackStarMaterial.Object;
	if (StarBase)
	{
		StarField->SetMaterial(0, StarBase);
		StarField->SetMaterial(1, StarBase);
		StarField->SetMaterial(2, StarBase);
	}
	static ConstructorHelpers::FObjectFinder<UMaterialInterface> MoonFresnelGlowMaterialFinder(
		TEXT("/Game/StylizedFX_2/MI/MI_Fresnel_Glow_Purple.MI_Fresnel_Glow_Purple"));
	MoonFresnelGlowMaterial = MoonFresnelGlowMaterialFinder.Object;
	static ConstructorHelpers::FObjectFinder<UMaterialInterface> MoonAdditiveGlowMaterialFinder(
		TEXT("/Game/ProjectilesVol1/Materials/M_Additive.M_Additive"));
	MoonAdditiveGlowMaterial = MoonAdditiveGlowMaterialFinder.Object;
	if (MoonAdditiveGlowMaterial)
	{
		MoonGlow->SetMaterial(0, MoonAdditiveGlowMaterial);
	}
	static ConstructorHelpers::FObjectFinder<UMaterialInterface> RockMaterial(
		TEXT("/Engine/BasicShapes/BasicShapeMaterial.BasicShapeMaterial"));
	if (RockMaterial.Succeeded())
	{
		Asteroids->SetMaterial(0, RockMaterial.Object);
		Moon->SetMaterial(0, RockMaterial.Object);
		RingWorldBody->SetMaterial(0, RockMaterial.Object);
		RingWorldBands->SetMaterial(0, RockMaterial.Object);
		RingWorldBands->SetMaterial(1, RockMaterial.Object);
		RingWorldBands->SetMaterial(2, RockMaterial.Object);
		RingMoonA->SetMaterial(0, RockMaterial.Object);
		RingMoonB->SetMaterial(0, RockMaterial.Object);
		RingMoonC->SetMaterial(0, RockMaterial.Object);
	}
	static ConstructorHelpers::FObjectFinder<UMaterialInterface> MoonMaterial(
		TEXT("/Game/StylizedDesertOasis/Materials/Instances/Rocks/MI_Boulder_03.MI_Boulder_03"));
	if (MoonMaterial.Succeeded())
	{
		Moon->SetMaterial(0, MoonMaterial.Object);
		Asteroids->SetMaterial(0, MoonMaterial.Object);
		RingMoonA->SetMaterial(0, MoonMaterial.Object);
		RingMoonB->SetMaterial(0, MoonMaterial.Object);
		RingMoonC->SetMaterial(0, MoonMaterial.Object);
	}
}

void ARedSpaceScenery::BeginPlay()
{
	Super::BeginPlay();
	if (IsHidden() || !GetActorEnableCollision())
	{
		UE_LOG(LogRedSpaceScenery, Warning,
			TEXT("Recovering space scenery from actor-level suppression: hidden=%d collision=%d"),
			IsHidden() ? 1 : 0, GetActorEnableCollision() ? 1 : 0);
	}
	SetActorHiddenInGame(false);
	SetActorEnableCollision(true);
	ResolveHomePlanetFrame();
	BuildScenery();
	UpdateLocalSpacePresentation(0.f);
}

void ARedSpaceScenery::EndPlay(const EEndPlayReason::Type EndPlayReason)
{
	// PlayerCameraManager survives seamless travel.  Leaving a transient modifier behind
	// would make its last surface-night / fused-map exposure guard bleed into the next map.
	if (OrbitExposureCameraModifier)
	{
		OrbitExposureCameraModifier->SetSurfaceNightExposure(0.f);
		OrbitExposureCameraModifier->SetPlanetFrame(FVector::ZeroVector, 1.f, false);
		if (APlayerCameraManager* CameraManager =
			OrbitExposureCameraModifier->GetTypedOuter<APlayerCameraManager>())
		{
			CameraManager->RemoveCameraModifier(OrbitExposureCameraModifier);
		}
		OrbitExposureCameraModifier = nullptr;
	}
	Super::EndPlay(EndPlayReason);
}

void ARedSpaceScenery::Tick(const float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	if (!bHomePlanetFrameResolved || GetWorld()->GetTimeSeconds() >= NextPlanetFrameResolveTime)
	{
		NextPlanetFrameResolveTime = GetWorld()->GetTimeSeconds() + 2.f;
		ResolveHomePlanetFrame();
	}
	if (bHomePlanetFrameResolved && BuiltSurfaceRadiusCm > 0.f
		&& !FMath::IsNearlyEqual(BuiltSurfaceRadiusCm, HomePlanetSurfaceRadiusCm, 100.f))
	{
		// A client can receive this actor before its streamed PlanetGen mesh exists. Rebuild
		// once the real datum resolves so orbit bands are not left around the 6 km fallback.
		BuildScenery();
	}
	UpdateLocalSpacePresentation(DeltaSeconds);
}

ARedSpaceScenery* ARedSpaceScenery::EnsureForWorld(UWorld* World, const FVector& AnchorCenter)
{
	if (!World) { return nullptr; }
	for (TActorIterator<ARedSpaceScenery> It(World); It; ++It)
	{
		if (IsValid(*It))
		{
			It->SetActorHiddenInGame(false);
			It->SetActorEnableCollision(true);
			return *It;
		}
	}
	if (World->GetNetMode() == NM_Client)
	{
		return nullptr;
	}

	FActorSpawnParameters Params;
	Params.Name = TEXT("Red_DeterministicSpaceScenery");
	Params.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
	return World->SpawnActor<ARedSpaceScenery>(
		ARedSpaceScenery::StaticClass(), AnchorCenter, FRotator::ZeroRotator, Params);
}

void ARedSpaceScenery::BuildScenery()
{
	if (!StarField || !AnalyticStarDome || !Asteroids || !Moon || !MoonGlow
		|| !Asteroids->GetStaticMesh())
	{
		return;
	}

	StarField->ClearAllMeshSections();
	Asteroids->ClearInstances();
	if (!bEnableLegacySaturnPrototype)
	{
		DisableLegacySaturnPrototype();
	}
	const bool bNightStarTuningTest = GetWorld()
		&& GetWorld()->GetMapName().Contains(TEXT("Night_T03"));
	bUsingNightWaterT04StarOverlayProof = false;
	bUsingNightWaterT04MoonAudit = false;
#if !UE_BUILD_SHIPPING
	bUsingNightWaterT04StarOverlayProof = GetWorld()
		&& RedPlanetPresentationTuning::IsNightWaterT04MapName(GetWorld()->GetMapName())
		&& RedPlanetPresentationTuning::UseNightWaterT04SoStylizedRadial()
		&& FParse::Param(FCommandLine::Get(), TEXT("RedNightWaterT04AutoCapture"))
		&& FParse::Param(FCommandLine::Get(), TEXT("RedNightWaterT04StarAudit"))
		&& NightWaterT04StarOverlayProofMaterial != nullptr;
	bUsingNightWaterT04MoonAudit = GetWorld()
		&& RedPlanetPresentationTuning::IsNightWaterT04MapName(GetWorld()->GetMapName())
		&& RedPlanetPresentationTuning::UseNightWaterT04SoStylizedRadial()
		&& FParse::Param(FCommandLine::Get(), TEXT("RedNightWaterT04AutoCapture"))
		&& FParse::Param(FCommandLine::Get(), TEXT("RedNightWaterT04MoonAudit"));
#endif
	Moon->SetLightingChannels(!bUsingNightWaterT04MoonAudit, false, bUsingNightWaterT04MoonAudit);
	MoonAuditKeyLight->SetVisibility(bUsingNightWaterT04MoonAudit, true);
	MoonAuditKeyLight->SetHiddenInGame(!bUsingNightWaterT04MoonAudit, true);
	UMaterialInterface* ResolvedMoonGlowMaterial = bUsingNightWaterT04MoonAudit
		&& MoonFresnelGlowMaterial ? MoonFresnelGlowMaterial.Get() : MoonAdditiveGlowMaterial.Get();
	if (ResolvedMoonGlowMaterial)
	{
		MoonGlow->SetMaterial(0, ResolvedMoonGlowMaterial);
	}
	if (bUsingNightWaterT04StarOverlayProof)
	{
		StarField->SetMaterial(0, NightWaterT04StarOverlayProofMaterial);
		StarField->SetMaterial(1, NightWaterT04StarOverlayProofMaterial);
		StarField->SetMaterial(2, NightWaterT04StarOverlayProofMaterial);
		bStarMaterialUsesEmissionParameter = true;
		UE_LOG(LogRedSpaceScenery, Display,
			TEXT("NightWater_T04 procedural star overlay proof enabled: material=%s additive=1 depthTest=0 autoCapture=1 starAudit=1"),
			*GetNameSafe(NightWaterT04StarOverlayProofMaterial));
	}
	else if (bNightStarTuningTest && NightT03StarDiagnosticMaterial)
	{
		// This replaces only the disposable test map's material parent before its
		// MIDs are created below. The opaque, two-sided IsSky material is a strict
		// render-layer diagnostic; production keeps M_RedStarSolid unchanged.
		StarField->SetMaterial(0, NightT03StarDiagnosticMaterial);
		StarField->SetMaterial(1, NightT03StarDiagnosticMaterial);
		StarField->SetMaterial(2, NightT03StarDiagnosticMaterial);
		// Reuse the collision-free shell as a camera-correlated visual proxy. The
		// solid reachable moon remains aligned to the fill light and authoritative
		// for gravity/collision.
		// Keep the moon on its additive parent.  Treating the nearby diagnostic disc
		// as opaque IsSky geometry moved it into the sky pass, where it could be
		// occluded by the full-dome Milky Way shell.
		bStarMaterialUsesEmissionParameter = true;
		UE_LOG(LogRedSpaceScenery, Display,
			TEXT("Night_T03 using project-owned opaque IsSky diagnostic parent=%s for stars and visual moon proxy"),
			*GetNameSafe(NightT03StarDiagnosticMaterial));
	}
	DimStarCount = 0;
	MediumStarCount = 0;
	BrightStarCount = 0;
	AnalyticStarDomeMaterialDynamic = nullptr;
	bUsingNightT03MilkyWaySky = false;
	const bool bRequestNightT03MilkyWaySky = bNightStarTuningTest
		&& NightT03MilkyWayMaterial != nullptr && NightT03BasicSphereMesh != nullptr;
	if (bRequestNightT03MilkyWaySky)
	{
		// SM_SkySphere reported ready but contributed zero visible pixels in repeated
		// D3D12 captures.  The world-direction material does not depend on imported UVs,
		// so audition it on the same BasicSphere path that already renders the moon.
		AnalyticStarDome->SetStaticMesh(NightT03BasicSphereMesh.Get());
		// Keep the harness shell camera-relative and behind the 60 km diagnostic moon.
		// A 100 km shell avoids the precision/coverage risk of the former 1000 km
		// shell while remaining far beyond the 8 km Night_T03 planet surface.
		constexpr double TargetStarDomeRadiusCm = 10000000.0;
		const double SourceStarDomeRadiusCm = FMath::Max(
			NightT03BasicSphereMesh->GetBounds().SphereRadius, 1.0);
		AnalyticStarDome->SetRelativeScale3D(
			FVector(TargetStarDomeRadiusCm / SourceStarDomeRadiusCm));
	}
	UMaterialInterface* StarDomeParent = bRequestNightT03MilkyWaySky
		? NightT03MilkyWayMaterial.Get() : AnalyticStarDomeMaterial.Get();
	if (StarDomeParent)
	{
		// Reset to the authored base before rebuilding so a streamed-planet datum refresh
		// cannot accidentally parent a new MID to the previous transient MID.
		AnalyticStarDome->SetMaterial(0, StarDomeParent);
		AnalyticStarDomeMaterialDynamic =
			AnalyticStarDome->CreateAndSetMaterialInstanceDynamic(0);
	}
	// The older texture-free analytic prototypes rendered black in repeated real-GPU
	// captures. Keep production on the procedural fallback while Night_T03 auditions
	// the installed Milky Way atlas through this project-owned material.
	bUsingNightT03MilkyWaySky = bRequestNightT03MilkyWaySky
		&& AnalyticStarDomeMaterialDynamic != nullptr
		&& AnalyticStarDome->GetStaticMesh() == NightT03BasicSphereMesh.Get();
	bAnalyticStarDomeReady = bUsingNightT03MilkyWaySky;
	if (AnalyticStarDomeMaterialDynamic)
	{
		AnalyticStarDomeMaterialDynamic->SetScalarParameterValue(TEXT("Visibility"), 0.f);
		AnalyticStarDomeMaterialDynamic->SetScalarParameterValue(
			TEXT("Emission"), bUsingNightT03MilkyWaySky ? 12.f : 64.f);
		if (!bUsingNightT03MilkyWaySky)
		{
			AnalyticStarDomeMaterialDynamic->SetScalarParameterValue(TEXT("CellScale"), 160.f);
			AnalyticStarDomeMaterialDynamic->SetScalarParameterValue(TEXT("Density"), 0.23f);
			AnalyticStarDomeMaterialDynamic->SetScalarParameterValue(TEXT("PointRadius"), 0.13f);
			AnalyticStarDomeMaterialDynamic->SetScalarParameterValue(TEXT("Seed"), 17.f);
		}
	}
	if (bUsingNightT03MilkyWaySky)
	{
		UE_LOG(LogRedSpaceScenery, Display,
			TEXT("Night_T03 Milky Way sky ready: mesh=%s material=%s radius=%.0fcm projection=world-direction atlas=/Game/SpaceColony/Textures/T_milky_way"),
			*GetNameSafe(AnalyticStarDome->GetStaticMesh()),
			*GetNameSafe(StarDomeParent),
			AnalyticStarDome->GetStaticMesh()
				? AnalyticStarDome->GetStaticMesh()->GetBounds().SphereRadius
					* AnalyticStarDome->GetRelativeScale3D().GetAbsMax()
				: 0.f);
	}
	const auto ScaleStarRgb = [](const FLinearColor& Color, const float Gain)
	{
		return FLinearColor(Color.R * Gain, Color.G * Gain, Color.B * Gain, 1.f);
	};
	StarMaterialDynamic = StarField->CreateAndSetMaterialInstanceDynamic(0);
	if (StarMaterialDynamic)
	{
		StarMaterialDynamic->SetVectorParameterValue(
			TEXT("Color"), ScaleStarRgb(FLinearColor(0.55f, 0.72f, 1.05f), 5.f));
		if (bStarMaterialUsesEmissionParameter)
		{
			StarMaterialDynamic->SetScalarParameterValue(TEXT("Emission"), 1.f);
		}
	}
	MediumStarMaterialDynamic = StarField->CreateAndSetMaterialInstanceDynamic(1);
	if (MediumStarMaterialDynamic)
	{
		MediumStarMaterialDynamic->SetVectorParameterValue(
			TEXT("Color"), ScaleStarRgb(FLinearColor(1.25f, 1.52f, 2.15f), 8.f));
		if (bStarMaterialUsesEmissionParameter)
		{
			MediumStarMaterialDynamic->SetScalarParameterValue(TEXT("Emission"), 1.f);
		}
	}
	BrightStarMaterialDynamic = StarField->CreateAndSetMaterialInstanceDynamic(2);
	if (BrightStarMaterialDynamic)
	{
		// Keep the navigation layer neutral/cool. Warm emissive points were indistinguishable
		// from the decorative brown asteroids in the first GPU capture.
		BrightStarMaterialDynamic->SetVectorParameterValue(
			TEXT("Color"), ScaleStarRgb(FLinearColor(3.5f, 3.9f, 4.8f), 12.f));
		if (bStarMaterialUsesEmissionParameter)
		{
			BrightStarMaterialDynamic->SetScalarParameterValue(TEXT("Emission"), 1.f);
		}
	}
	MoonGlowMaterialDynamic = MoonGlow->CreateAndSetMaterialInstanceDynamic(0);
	if (MoonGlowMaterialDynamic)
	{
		// A low-energy blue-white rim explains the cool directional fill without
		// bleaching the boulder material into a textureless white disc. The first two
		// parameters belong to the installed StylizedFX Fresnel material; Color keeps
		// the older additive fallback restrained as well.
		const FLinearColor MoonRimColor = bUsingNightWaterT04MoonAudit
			? FLinearColor(0.035f, 0.038f, 0.042f, 1.f)
			: FLinearColor(1.35f, 1.65f, 2.55f, 1.f);
		MoonGlowMaterialDynamic->SetVectorParameterValue(TEXT("Highlight_Color"), MoonRimColor);
		MoonGlowMaterialDynamic->SetVectorParameterValue(
			TEXT("In_Color"), FLinearColor(0.f, 0.f, 0.f, 0.f));
		MoonGlowMaterialDynamic->SetVectorParameterValue(TEXT("Color"), MoonRimColor);
		if (bNightStarTuningTest && NightT03StarDiagnosticMaterial)
		{
			MoonGlowMaterialDynamic->SetScalarParameterValue(TEXT("Emission"), 18.f);
		}
	}
	FRandomStream Stream(0x524544); // "RED"; identical layout on server and clients.

	// A scrambled, jittered Fibonacci sphere keeps coverage even while breaking the
	// exact latitude/ring spacing of the old shell. Three magnitude layers make the
	// result read as a star field rather than an invisible geodesic cage.
	// Night_T03 is an isolated visual-test map.  Its denser/larger star field lets us
	// validate the procedural fallback on a real GPU without changing the protected
	// 50 km checkpoint or the production presentation budget.
	// Keep the production field restrained and inexpensive. The previous 3,200-disc
	// fallback was visually noisy and doubled the procedural geometry cost without
	// improving navigation readability. The isolated Night_T03 proof remains dense.
	const int32 StarCount = bNightStarTuningTest ? 9000 : 1600;
	const float StarDiscRadiusScale = bNightStarTuningTest ? 2.25f : 1.f;
	constexpr double GoldenAngle = 2.39996322972865332;
	const bool bBuildLocalStarGeometry =
		!bAnalyticStarDomeReady && GetNetMode() != NM_DedicatedServer;
	FStarSectionBuffers DimStars;
	FStarSectionBuffers MediumStars;
	FStarSectionBuffers BrightStars;
	if (bBuildLocalStarGeometry)
	{
		DimStars.Reserve(3400);
		MediumStars.Reserve(720);
		BrightStars.Reserve(160);
	}
	for (int32 Index = 0; Index < StarCount; ++Index)
	{
		// 937 is coprime to 2800, so this visits every stratum in a visually scrambled order.
		const int32 ScrambledIndex = (Index * 937 + 421) % StarCount;
		const double StratumJitter = Stream.FRandRange(-0.46f, 0.46f);
		const double Z = 1.0 - 2.0
			* (static_cast<double>(ScrambledIndex) + 0.5 + StratumJitter) / StarCount;
		const double Ring = FMath::Sqrt(FMath::Max(0.0, 1.0 - Z * Z));
		const double Angle = GoldenAngle * ScrambledIndex
			+ Stream.FRandRange(-0.78f, 0.78f);
		const FVector Direction(Ring * FMath::Cos(Angle), Ring * FMath::Sin(Angle), Z);
		// Keep the camera-relative shell inside the inspection camera's proven render
		// distance. The previous 70-90 km shell produced valid mesh sections and active
		// visibility logs but no pixels in repeated real-GPU captures.
		const float Radius = Stream.FRandRange(3800000.f, 4800000.f);
		const float MagnitudeRoll = Stream.FRand();
		FStarSectionBuffers* Layer = &DimStars;
		int32* LayerCount = &DimStarCount;
		float DiscRadiusCm = Stream.FRandRange(2200.f, 4200.f) * StarDiscRadiusScale;
		if (MagnitudeRoll > 0.965f)
		{
			Layer = &BrightStars;
			LayerCount = &BrightStarCount;
			DiscRadiusCm = Stream.FRandRange(8000.f, 13000.f) * StarDiscRadiusScale;
		}
		else if (MagnitudeRoll > 0.79f)
		{
			Layer = &MediumStars;
			LayerCount = &MediumStarCount;
			DiscRadiusCm = Stream.FRandRange(4500.f, 7500.f) * StarDiscRadiusScale;
		}
		++(*LayerCount);
		if (bBuildLocalStarGeometry)
		{
			AddStarDisc(*Layer, Direction * Radius, DiscRadiusCm, Direction);
		}
	}
	if (bBuildLocalStarGeometry)
	{
		StarField->CreateMeshSection(0, DimStars.Vertices, DimStars.Triangles,
			DimStars.Normals, DimStars.UV0, DimStars.Colors, DimStars.Tangents, false);
		StarField->CreateMeshSection(1, MediumStars.Vertices, MediumStars.Triangles,
			MediumStars.Normals, MediumStars.UV0, MediumStars.Colors, MediumStars.Tangents, false);
		StarField->CreateMeshSection(2, BrightStars.Vertices, BrightStars.Triangles,
			BrightStars.Normals, BrightStars.UV0, BrightStars.Colors, BrightStars.Tangents, false);
		if (StarMaterialDynamic)
		{
			StarField->SetMaterial(0, StarMaterialDynamic);
		}
		if (MediumStarMaterialDynamic)
		{
			StarField->SetMaterial(1, MediumStarMaterialDynamic);
		}
		if (BrightStarMaterialDynamic)
		{
			StarField->SetMaterial(2, BrightStarMaterialDynamic);
		}
		StarField->MarkRenderStateDirty();
	}

	// Decorative rocks live in a few loose, irregular fields instead of a uniform
	// spherical lattice. Mineable rocks below remain separate replicated actors.
	float DecorativeMinAltitudeCm = TNumericLimits<float>::Max();
	float DecorativeMaxAltitudeCm = TNumericLimits<float>::Lowest();
	constexpr int32 AsteroidCount = 72;
	constexpr int32 FieldCount = 5;
	FRandomStream DecorativeAsteroidStream(0x4D415253); // "MARS"
	FVector FieldDirections[FieldCount];
	for (FVector& FieldDirection : FieldDirections)
	{
		do
		{
			FieldDirection = FVector(
				DecorativeAsteroidStream.FRandRange(-1.f, 1.f),
				DecorativeAsteroidStream.FRandRange(-1.f, 1.f),
				DecorativeAsteroidStream.FRandRange(-0.55f, 0.55f)).GetSafeNormal();
		}
		while (FieldDirection.IsNearlyZero());
	}
	for (int32 Index = 0; Index < AsteroidCount; ++Index)
	{
		const FVector Scatter = FVector(
			DecorativeAsteroidStream.FRandRange(-1.f, 1.f),
			DecorativeAsteroidStream.FRandRange(-1.f, 1.f),
			DecorativeAsteroidStream.FRandRange(-0.7f, 0.7f));
		const FVector Direction = (FieldDirections[DecorativeAsteroidStream.RandRange(0, FieldCount - 1)]
			+ Scatter * DecorativeAsteroidStream.FRandRange(0.10f, 0.58f)).GetSafeNormal();
		// Keep the decorative belt in deep space. It must never read as rocks floating
		// inside the atmosphere or immediately above the surface.
		const float AltitudeCm = DecorativeAsteroidStream.FRandRange(
			RedPlanetPresentationTuning::DeepSpaceAsteroidInnerAltitudeCm,
			RedPlanetPresentationTuning::DeepSpaceAsteroidOuterAltitudeCm);
		const float Radius = HomePlanetSurfaceRadiusCm + AltitudeCm;
		DecorativeMinAltitudeCm = FMath::Min(DecorativeMinAltitudeCm, AltitudeCm);
		DecorativeMaxAltitudeCm = FMath::Max(DecorativeMaxAltitudeCm, AltitudeCm);
		const float Scale = DecorativeAsteroidStream.FRandRange(22.f, 145.f);
		const FVector ShapeScale(
			Scale * DecorativeAsteroidStream.FRandRange(1.1f, 2.2f),
			Scale * DecorativeAsteroidStream.FRandRange(0.55f, 1.1f),
			Scale * DecorativeAsteroidStream.FRandRange(0.55f, 1.2f));
		const FQuat Rotation = FRotator(
			DecorativeAsteroidStream.FRandRange(-180.f, 180.f),
			DecorativeAsteroidStream.FRandRange(-180.f, 180.f),
			DecorativeAsteroidStream.FRandRange(-180.f, 180.f)).Quaternion();
		Asteroids->AddInstance(FTransform(Rotation, Direction * Radius, ShapeScale), false);
	}

	// Decorative HISMs provide depth; these replicated actors are the nearby, collidable ore
	// targets that ship bolts can actually mine. Spawn only once on the authority.
	constexpr int32 MineableCount = 24;
	if (HasAuthority())
	{
		bool bHasMineableField = false;
		for (TActorIterator<ARedMineableAsteroid> It(GetWorld()); It; ++It)
		{
			if (IsValid(*It) && It->ActorHasTag(TEXT("RedMarsMineableBelt")))
			{
				bHasMineableField = true;
				break;
			}
		}
		if (!bHasMineableField)
		{
			FRandomStream MineableAsteroidStream(0x4F524531); // "ORE1"
			for (int32 Index = 0; Index < MineableCount; ++Index)
			{
				FVector Direction;
				do
				{
					Direction = FVector(MineableAsteroidStream.FRandRange(-1.f, 1.f),
						MineableAsteroidStream.FRandRange(-1.f, 1.f),
						MineableAsteroidStream.FRandRange(-0.7f, 0.7f)).GetSafeNormal();
				}
				while (Direction.IsNearlyZero());
				const float Radius = HomePlanetSurfaceRadiusCm
					+ MineableAsteroidStream.FRandRange(
						RedPlanetPresentationTuning::DeepSpaceAsteroidInnerAltitudeCm,
						RedPlanetPresentationTuning::DeepSpaceAsteroidOuterAltitudeCm);
				const FVector Location = GetActorLocation() + Direction * Radius;
				const FRotator Rotation(MineableAsteroidStream.FRandRange(-180.f, 180.f),
					MineableAsteroidStream.FRandRange(-180.f, 180.f),
					MineableAsteroidStream.FRandRange(-180.f, 180.f));
				const float UniformScale = MineableAsteroidStream.FRandRange(12.f, 42.f);
				const FVector ShapeScale(UniformScale,
					UniformScale * MineableAsteroidStream.FRandRange(0.65f, 1.25f),
					UniformScale * MineableAsteroidStream.FRandRange(0.65f, 1.25f));
				const FTransform SpawnTransform(Rotation, Location, ShapeScale);
				FActorSpawnParameters Params;
				Params.Name = FName(*FString::Printf(TEXT("RedMineableAsteroid_%02d"), Index));
				Params.Owner = this;
				Params.bDeferConstruction = true;
				Params.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
				if (ARedMineableAsteroid* Mineable = GetWorld()->SpawnActor<ARedMineableAsteroid>(
					ARedMineableAsteroid::StaticClass(), SpawnTransform, Params))
				{
					const FName StableMemberId(*FString::Printf(
						TEXT("asteroid-field.red.mars.deep-space/0x4F524531/%02d"),
						Index));
					if (!Mineable->InitializeStableMemberId(StableMemberId))
					{
						UE_LOG(LogRedSpaceScenery, Error,
							TEXT("Failed to initialize Mars asteroid stable member ID %s."),
							*StableMemberId.ToString());
						Mineable->Destroy();
						continue;
					}
					Mineable->Tags.AddUnique(TEXT("RedMarsMineableBelt"));
					Mineable->SetPresentationCullDistance(
						RedPlanetPresentationTuning::AsteroidRenderCullDistanceCm);
					UGameplayStatics::FinishSpawningActor(Mineable, SpawnTransform);
					Mineable->ForceNetUpdate();
				}
			}
		}
	}

	int32 MineableFieldCount = 0;
	float MineableMinAltitudeCm = TNumericLimits<float>::Max();
	float MineableMaxAltitudeCm = TNumericLimits<float>::Lowest();
	bool bMineableDistanceContractSatisfied = true;
	bool bMineableCullContractSatisfied = true;
	if (HasAuthority())
	{
		for (TActorIterator<ARedMineableAsteroid> It(GetWorld()); It; ++It)
		{
			ARedMineableAsteroid* Mineable = *It;
			if (!IsValid(Mineable) || !Mineable->ActorHasTag(TEXT("RedMarsMineableBelt")))
			{
				continue;
			}

			++MineableFieldCount;
			const float AltitudeCm = FVector::Distance(Mineable->GetActorLocation(), GetActorLocation())
				- HomePlanetSurfaceRadiusCm;
			MineableMinAltitudeCm = FMath::Min(MineableMinAltitudeCm, AltitudeCm);
			MineableMaxAltitudeCm = FMath::Max(MineableMaxAltitudeCm, AltitudeCm);
			bMineableDistanceContractSatisfied &=
				AltitudeCm >= RedPlanetPresentationTuning::DeepSpaceAsteroidInnerAltitudeCm - 1.f
				&& AltitudeCm <= RedPlanetPresentationTuning::DeepSpaceAsteroidOuterAltitudeCm + 1.f;
			bMineableCullContractSatisfied &= FMath::IsNearlyEqual(
				Mineable->GetPresentationCullDistance(),
				RedPlanetPresentationTuning::AsteroidRenderCullDistanceCm, 1.f);
		}
		bMineableDistanceContractSatisfied &= MineableFieldCount == MineableCount;
	}

	Moon->SetRelativeLocation(MoonRelativeLocation);
	constexpr float EngineSphereRadiusCm = 50.f;
	Moon->SetRelativeScale3D(FVector(MoonSurfaceRadiusCm / EngineSphereRadiusCm));
	Moon->SetCollisionObjectType(ECC_WorldStatic);
	Moon->SetCollisionEnabled(ECollisionEnabled::QueryAndPhysics);
	Moon->SetCollisionResponseToAllChannels(ECR_Block);
	Moon->SetVisibility(true, true);
	Moon->SetHiddenInGame(false, true);
	MoonGlow->SetVisibility(true, true);
	MoonGlow->SetHiddenInGame(false, true);
	Moon->MarkRenderStateDirty();
	MoonGlow->MarkRenderStateDirty();
	bMoonAlignedToFill = false;
	if (bEnableLegacySaturnPrototype)
	{
		BuildRingWorld();
		SpawnRingMineableAsteroids();
	}

	// Force the decorative asteroid HISM tree to exist before the first camera transition.
	Asteroids->BuildTreeIfOutdated(false, true);
	BuiltSurfaceRadiusCm = HomePlanetSurfaceRadiusCm;
	UE_LOG(LogRedSpaceScenery, Display,
		TEXT("Built scenery: stars=%d/%d/%d mode=%s decorativeAsteroids=%d surfaceRadius=%.0fcm materials=%s/%s/%s analytic=%s"),
		DimStarCount, MediumStarCount, BrightStarCount,
		bUsingNightT03MilkyWaySky ? TEXT("milkyway-dome")
			: (bAnalyticStarDomeReady ? TEXT("analytic-dome") : TEXT("procedural-fallback")),
		Asteroids->GetInstanceCount(), HomePlanetSurfaceRadiusCm,
		*GetNameSafe(StarField->GetMaterial(0)), *GetNameSafe(StarField->GetMaterial(1)),
		*GetNameSafe(StarField->GetMaterial(2)), *GetNameSafe(AnalyticStarDome->GetMaterial(0)));
	UE_LOG(LogRedSpaceScenery, Display,
		TEXT("Deep-space asteroid distance contract: configured=[%.2f,%.2f]km presentationTop=%.2fkm cull=%.2fkm clearance=%.2fkm decorative=%d actual=[%.2f,%.2f]km mineable=%d/%d actual=[%.2f,%.2f]km distancePass=%d cullPass=%d"),
		RedPlanetPresentationTuning::DeepSpaceAsteroidInnerAltitudeCm * 0.00001f,
		RedPlanetPresentationTuning::DeepSpaceAsteroidOuterAltitudeCm * 0.00001f,
		RedPlanetPresentationTuning::AsteroidPresentationTopCm * 0.00001f,
		RedPlanetPresentationTuning::AsteroidRenderCullDistanceCm * 0.00001f,
		RedPlanetPresentationTuning::AsteroidAtmosphereClearanceCm * 0.00001f,
		Asteroids->GetInstanceCount(),
		DecorativeMinAltitudeCm * 0.00001f, DecorativeMaxAltitudeCm * 0.00001f,
		MineableFieldCount, MineableCount,
		MineableFieldCount > 0 ? MineableMinAltitudeCm * 0.00001f : 0.f,
		MineableFieldCount > 0 ? MineableMaxAltitudeCm * 0.00001f : 0.f,
		bMineableDistanceContractSatisfied ? 1 : 0,
		bMineableCullContractSatisfied ? 1 : 0);
	if (!bMineableDistanceContractSatisfied || !bMineableCullContractSatisfied)
	{
		UE_LOG(LogRedSpaceScenery, Error,
			TEXT("The RedMarsMineableBelt count, altitude, or client-safe render-cull contract failed."));
	}
}

void ARedSpaceScenery::DisableLegacySaturnPrototype()
{
	bRingWorldBuilt = false;

	auto DisableStaticBody = [](UStaticMeshComponent* Component)
	{
		if (!Component)
		{
			return;
		}
		Component->SetVisibility(false, true);
		Component->SetHiddenInGame(true, true);
		Component->SetCollisionEnabled(ECollisionEnabled::NoCollision);
		Component->SetCollisionResponseToAllChannels(ECR_Ignore);
		Component->SetGenerateOverlapEvents(false);
	};
	DisableStaticBody(RingWorldBody);
	DisableStaticBody(RingMoonA);
	DisableStaticBody(RingMoonB);
	DisableStaticBody(RingMoonC);

	if (RingWorldBands)
	{
		RingWorldBands->ClearAllMeshSections();
		RingWorldBands->SetVisibility(false, true);
		RingWorldBands->SetHiddenInGame(true, true);
		RingWorldBands->SetCollisionEnabled(ECollisionEnabled::NoCollision);
		RingWorldBands->SetGenerateOverlapEvents(false);
	}
	RingWorldMaterialDynamic = nullptr;
	RingBandMaterialDynamics.Reset();

	int32 RemovedLegacyAsteroids = 0;
	if (HasAuthority() && GetWorld())
	{
		for (TActorIterator<ARedMineableAsteroid> It(GetWorld()); It; ++It)
		{
			if (IsValid(*It) && It->ActorHasTag(TEXT("RedRingMineableBelt")))
			{
				It->Destroy();
				++RemovedLegacyAsteroids;
			}
		}
	}

	UE_LOG(LogRedSpaceScenery, Display,
		TEXT("Legacy Saturn prototype disabled: body=hidden bands=cleared moons=disabled ringAsteroidsRemoved=%d"),
		RemovedLegacyAsteroids);
}

void ARedSpaceScenery::BuildRingWorld()
{
	if (!bEnableLegacySaturnPrototype
		|| !RingWorldBody || !RingWorldBands || !RingMoonA || !RingMoonB || !RingMoonC)
	{
		return;
	}

	constexpr float EngineSphereRadiusCm = 50.f;
	RingWorldBody->SetRelativeLocation(RingWorldRelativeLocation);
	RingWorldBody->SetRelativeScale3D(FVector(
		FMath::Max(50000.f, RingWorldSurfaceRadiusCm) / EngineSphereRadiusCm));
	RingWorldBody->SetVisibility(true, true);
	RingWorldBody->SetHiddenInGame(false, true);
	RingWorldBody->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	RingWorldBody->SetCollisionResponseToAllChannels(ECR_Ignore);

	// A tilted, multi-band annulus reads clearly from both Mars and the local moons. The mesh
	// is generated from a few hundred vertices and uses only an Engine material, avoiding the
	// texture/VRAM cost of another full planetary asset set.
	const FRotator RingTilt(17.f, -12.f, 28.f);
	RingWorldBands->SetRelativeLocation(RingWorldRelativeLocation);
	RingWorldBands->SetRelativeRotation(RingTilt);
	RingWorldBands->ClearAllMeshSections();

	struct FRingBand
	{
		float InnerRadiusCm;
		float OuterRadiusCm;
		FLinearColor Color;
	};
	const FRingBand Bands[] = {
		{ RingWorldSurfaceRadiusCm * 1.42f, RingWorldSurfaceRadiusCm * 1.78f,
			FLinearColor(0.96f, 0.62f, 0.30f, 1.f) },
		{ RingWorldSurfaceRadiusCm * 1.84f, RingWorldSurfaceRadiusCm * 2.16f,
			FLinearColor(0.72f, 0.34f, 0.90f, 1.f) },
		{ RingWorldSurfaceRadiusCm * 2.23f, RingWorldSurfaceRadiusCm * 2.54f,
			FLinearColor(0.30f, 0.76f, 0.94f, 1.f) }
	};

	UMaterialInterface* RingBaseMaterial = LoadObject<UMaterialInterface>(
		nullptr, TEXT("/Engine/BasicShapes/BasicShapeMaterial.BasicShapeMaterial"));
	RingBandMaterialDynamics.Reset();
	constexpr int32 RingSegments = 128;
	for (int32 SectionIndex = 0; SectionIndex < UE_ARRAY_COUNT(Bands); ++SectionIndex)
	{
		const FRingBand& Band = Bands[SectionIndex];
		TArray<FVector> Vertices;
		TArray<int32> Triangles;
		TArray<FVector> Normals;
		TArray<FVector2D> UV0;
		TArray<FColor> Colors;
		TArray<FProcMeshTangent> Tangents;
		Vertices.Reserve((RingSegments + 1) * 2);
		Normals.Reserve((RingSegments + 1) * 2);
		UV0.Reserve((RingSegments + 1) * 2);
		Colors.Reserve((RingSegments + 1) * 2);
		Tangents.Reserve((RingSegments + 1) * 2);
		Triangles.Reserve(RingSegments * 12);

		for (int32 Segment = 0; Segment <= RingSegments; ++Segment)
		{
			const float Alpha = static_cast<float>(Segment) / static_cast<float>(RingSegments);
			const float Angle = Alpha * 2.f * PI;
			const FVector Radial(FMath::Cos(Angle), FMath::Sin(Angle), 0.f);
			const FVector Tangent(-FMath::Sin(Angle), FMath::Cos(Angle), 0.f);
			Vertices.Add(Radial * Band.InnerRadiusCm);
			Vertices.Add(Radial * Band.OuterRadiusCm);
			Normals.Add(FVector::UpVector);
			Normals.Add(FVector::UpVector);
			UV0.Add(FVector2D(Alpha, 0.f));
			UV0.Add(FVector2D(Alpha, 1.f));
			Colors.Add(Band.Color.ToFColor(true));
			Colors.Add(Band.Color.ToFColor(true));
			Tangents.Emplace(Tangent, false);
			Tangents.Emplace(Tangent, false);
		}

		for (int32 Segment = 0; Segment < RingSegments; ++Segment)
		{
			const int32 Inner0 = Segment * 2;
			const int32 Outer0 = Inner0 + 1;
			const int32 Inner1 = Inner0 + 2;
			const int32 Outer1 = Inner0 + 3;
			// Top winding.
			Triangles.Append({ Inner0, Outer0, Outer1, Inner0, Outer1, Inner1 });
			// Reverse winding keeps the rings visible from underneath without a two-sided shader.
			Triangles.Append({ Inner0, Outer1, Outer0, Inner0, Inner1, Outer1 });
		}

		RingWorldBands->CreateMeshSection(SectionIndex, Vertices, Triangles, Normals,
			UV0, Colors, Tangents, false);
		if (RingBaseMaterial)
		{
			UMaterialInstanceDynamic* DynamicMaterial =
				UMaterialInstanceDynamic::Create(RingBaseMaterial, this);
			if (DynamicMaterial)
			{
				DynamicMaterial->SetVectorParameterValue(TEXT("Color"), Band.Color);
				RingBandMaterialDynamics.Add(DynamicMaterial);
				RingWorldBands->SetMaterial(SectionIndex, DynamicMaterial);
			}
		}
	}
	RingWorldBands->SetVisibility(true, true);
	RingWorldBands->SetHiddenInGame(false, true);
	RingWorldBands->MarkRenderStateDirty();

	if (RingBaseMaterial)
	{
		RingWorldMaterialDynamic = UMaterialInstanceDynamic::Create(RingBaseMaterial, this);
		if (RingWorldMaterialDynamic)
		{
			RingWorldMaterialDynamic->SetVectorParameterValue(
				TEXT("Color"), FLinearColor(0.13f, 0.20f, 0.48f, 1.f));
			RingWorldBody->SetMaterial(0, RingWorldMaterialDynamic);
		}
	}

	auto PlaceMoon = [this, EngineSphereRadiusCm](
		UStaticMeshComponent* Component, const FVector& LocalOffset,
		const float SurfaceRadiusCm, const FRotator& Rotation)
	{
		if (!Component)
		{
			return;
		}
		Component->SetRelativeLocation(RingWorldRelativeLocation + LocalOffset);
		Component->SetRelativeRotation(Rotation);
		Component->SetRelativeScale3D(FVector(
			FMath::Max(10000.f, SurfaceRadiusCm) / EngineSphereRadiusCm));
		Component->SetCollisionEnabled(ECollisionEnabled::QueryAndPhysics);
		Component->SetCollisionObjectType(ECC_WorldStatic);
		Component->SetCollisionResponseToAllChannels(ECR_Block);
		Component->SetVisibility(true, true);
		Component->SetHiddenInGame(false, true);
		Component->MarkRenderStateDirty();
	};
	PlaceMoon(RingMoonA, RingMoonARelativeOffset, RingMoonSurfaceRadiiCm.X,
		FRotator(12.f, 38.f, -7.f));
	PlaceMoon(RingMoonB, RingMoonBRelativeOffset, RingMoonSurfaceRadiiCm.Y,
		FRotator(-18.f, -64.f, 21.f));
	PlaceMoon(RingMoonC, RingMoonCRelativeOffset, RingMoonSurfaceRadiiCm.Z,
		FRotator(32.f, 115.f, -16.f));

	bRingWorldBuilt = true;
	UE_LOG(LogRedSpaceScenery, Display,
		TEXT("Ring world built: center=(%.0f,%.0f,%.0f) radius=%.0fcm bands=%d playableMoons=3 collision=moons-only"),
		RingWorldRelativeLocation.X, RingWorldRelativeLocation.Y, RingWorldRelativeLocation.Z,
		RingWorldSurfaceRadiusCm, UE_ARRAY_COUNT(Bands));
}

void ARedSpaceScenery::SpawnRingMineableAsteroids()
{
	if (!bEnableLegacySaturnPrototype || !HasAuthority() || !GetWorld()
		|| !bRingWorldBuilt || RingMineableAsteroidCount <= 0)
	{
		return;
	}
	for (TActorIterator<ARedMineableAsteroid> It(GetWorld()); It; ++It)
	{
		if (IsValid(*It) && It->ActorHasTag(TEXT("RedRingMineableBelt")))
		{
			return;
		}
	}

	FRandomStream Stream(0x52494E47); // "RING" - deterministic on every server run.
	const FVector RingCenter = GetActorLocation() + RingWorldRelativeLocation;
	const FQuat RingRotation = FRotator(17.f, -12.f, 28.f).Quaternion();
	for (int32 Index = 0; Index < RingMineableAsteroidCount; ++Index)
	{
		const float BaseAlpha = static_cast<float>(Index)
			/ static_cast<float>(RingMineableAsteroidCount);
		const float Angle = (BaseAlpha + Stream.FRandRange(-0.012f, 0.012f)) * 2.f * PI;
		const float BeltRadius = Stream.FRandRange(
			RingWorldSurfaceRadiusCm * 2.75f, RingWorldSurfaceRadiusCm * 4.25f);
		const FVector RingLocal(
			FMath::Cos(Angle) * BeltRadius,
			FMath::Sin(Angle) * BeltRadius,
			Stream.FRandRange(-90000.f, 90000.f));
		const FVector Location = RingCenter + RingRotation.RotateVector(RingLocal);
		const FRotator Rotation(
			Stream.FRandRange(-180.f, 180.f), Stream.FRandRange(-180.f, 180.f),
			Stream.FRandRange(-180.f, 180.f));
		FActorSpawnParameters Params;
		Params.Name = FName(*FString::Printf(TEXT("RedRingMineableAsteroid_%02d"), Index));
		Params.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
		if (ARedMineableAsteroid* Mineable = GetWorld()->SpawnActor<ARedMineableAsteroid>(
			ARedMineableAsteroid::StaticClass(), Location, Rotation, Params))
		{
			Mineable->Tags.AddUnique(TEXT("RedRingMineableBelt"));
			const float UniformScale = Stream.FRandRange(5.f, 18.f);
			Mineable->SetActorScale3D(FVector(
				UniformScale * Stream.FRandRange(1.0f, 1.8f),
				UniformScale * Stream.FRandRange(0.65f, 1.25f),
				UniformScale * Stream.FRandRange(0.65f, 1.25f)));
			Mineable->ForceNetUpdate();
		}
	}
	UE_LOG(LogRedSpaceScenery, Display,
		TEXT("Ring mineable belt spawned: count=%d center=(%.0f,%.0f,%.0f)"),
		RingMineableAsteroidCount, RingCenter.X, RingCenter.Y, RingCenter.Z);
}

void ARedSpaceScenery::ResolveHomePlanetFrame()
{
	UWorld* World = GetWorld();
	if (!World)
	{
		return;
	}

	FVector Center = HomePlanetCenter;
	float DatumRadius = 0.f;
	float PeakRadius = 0.f;
	if (!RedGravity::FindMeshPlanet(World, Center, DatumRadius, &PeakRadius)
		|| DatumRadius <= 0.f || PeakRadius < DatumRadius)
	{
		return;
	}

	HomePlanetCenter = Center;
	HomePlanetSurfaceRadiusCm = (DatumRadius + PeakRadius) * 0.5f;
	bHomePlanetFrameResolved = true;
	if (!GetActorLocation().Equals(HomePlanetCenter, 1.f))
	{
		// The scenery layout is deterministic, so every peer can centre its local copy
		// without replicating continuous movement for an otherwise static actor.
		SetActorLocation(HomePlanetCenter, false, nullptr, ETeleportType::TeleportPhysics);
	}
}

void ARedSpaceScenery::ResolveSunLight()
{
	if (CachedSunLight.IsValid() || !GetWorld())
	{
		return;
	}
	const float Now = GetWorld()->GetTimeSeconds();
	if (Now < NextSunLookupTime)
	{
		return;
	}
	NextSunLookupTime = Now + 2.f;

	UDirectionalLightComponent* AtmosphereSun = nullptr;
	float AtmosphereSunIntensity = -1.f;
	UDirectionalLightComponent* Brightest = nullptr;
	float BrightestIntensity = -1.f;
	for (TActorIterator<AActor> It(GetWorld()); It; ++It)
	{
		TArray<UDirectionalLightComponent*> Lights;
		It->GetComponents<UDirectionalLightComponent>(Lights);
		for (UDirectionalLightComponent* Light : Lights)
		{
			const AActor* LightOwner = IsValid(Light) ? Light->GetOwner() : nullptr;
			const bool bIsNightFill = IsValid(Light)
				&& (Light->GetName().Contains(TEXT("MoonLight"))
					|| (IsValid(LightOwner) && LightOwner->ActorHasTag(TEXT("RedNightFill"))));
			if (!IsValid(Light) || bIsNightFill)
			{
				continue;
			}
			if (Light->IsUsedAsAtmosphereSunLight()
				&& Light->GetAtmosphereSunLightIndex() == 0u)
			{
				// Match the renderer when a broken map contains duplicate index-0 suns.
				if (Light->Intensity > AtmosphereSunIntensity)
				{
					AtmosphereSunIntensity = Light->Intensity;
					AtmosphereSun = Light;
				}
				continue;
			}
			if (Light->Intensity > BrightestIntensity)
			{
				BrightestIntensity = Light->Intensity;
				Brightest = Light;
			}
		}
	}
	if (AtmosphereSun)
	{
		CachedSunLight = AtmosphereSun;
		UE_LOG(LogRedSpaceScenery, Display,
			TEXT("Bound atmosphere sun %s (index=0 intensity=%.2f)"),
			*GetNameSafe(AtmosphereSun), AtmosphereSun->Intensity);
		return;
	}
	CachedSunLight = Brightest;
	if (Brightest)
	{
		UE_LOG(LogRedSpaceScenery, Display,
			TEXT("Atmosphere sun index 0 unavailable; brightest fallback=%s intensity=%.2f"),
			*GetNameSafe(Brightest), Brightest->Intensity);
	}
}

void ARedSpaceScenery::ResolveMoonLight()
{
	if (CachedMoonLight.IsValid() || !GetWorld())
	{
		return;
	}
	const float Now = GetWorld()->GetTimeSeconds();
	if (Now < NextMoonLookupTime)
	{
		return;
	}
	NextMoonLookupTime = Now + 2.f;

	for (TActorIterator<AActor> It(GetWorld()); It; ++It)
	{
		TArray<UDirectionalLightComponent*> Lights;
		It->GetComponents<UDirectionalLightComponent>(Lights);
		for (UDirectionalLightComponent* Light : Lights)
		{
			if (IsValid(Light) && (Light->GetName().Contains(TEXT("MoonLight"))
				|| It->ActorHasTag(TEXT("RedNightFill"))))
			{
				CachedMoonLight = Light;
				UE_LOG(LogRedSpaceScenery, Display, TEXT("Bound coherent moon fill %s"),
					*GetNameSafe(Light));
				return;
			}
		}
	}
}

void ARedSpaceScenery::UpdateMoonAlignment(const float DeltaSeconds)
{
	if (!Moon || !CachedMoonLight.IsValid())
	{
		return;
	}

	// A directional light's forward vector is the direction its rays travel.  The light
	// source is therefore in the opposite direction.  Keeping the solid, reachable moon on
	// that ray makes the object in the sky and the reflection/highlight on the ground agree.
	const FVector SourceDirection = -CachedMoonLight->GetForwardVector().GetSafeNormal();
	if (SourceDirection.IsNearlyZero())
	{
		return;
	}
	const float OrbitRadius = FMath::Max(
		MoonRelativeLocation.Size(), HomePlanetSurfaceRadiusCm + MoonSurfaceRadiusCm + 3000000.f);
	const FVector TargetLocation = SourceDirection * OrbitRadius;
	if (!bMoonAlignedToFill)
	{
		Moon->SetRelativeLocation(TargetLocation, false, nullptr, ETeleportType::TeleportPhysics);
		bMoonAlignedToFill = true;
	}
	else
	{
		// RedDayNight deliberately advances its shadowed sun in two-second increments for
		// performance.  Ease the visible body between those tiny 0.1-degree steps.
		const FVector SmoothedLocation = FMath::VInterpTo(
			Moon->GetRelativeLocation(), TargetLocation,
			FMath::Max(DeltaSeconds, UE_KINDA_SMALL_NUMBER), 2.5f);
		Moon->SetRelativeLocation(SmoothedLocation, false, nullptr, ETeleportType::TeleportPhysics);
	}
}

float ARedSpaceScenery::ComputeLocalNightFactor(const FVector& ViewLocation) const
{
	const UDirectionalLightComponent* MoonFill = CachedMoonLight.Get();
	const UDirectionalLightComponent* Sun = CachedSunLight.Get();
	const FVector LocalUp = (ViewLocation - HomePlanetCenter).GetSafeNormal();
	if (LocalUp.IsNearlyZero())
	{
		return 0.f;
	}
	if (Sun)
	{
		// A directional light's forward vector is the direction its rays travel, so the vector
		// toward the sun is the opposite. Stars begin after the actual atmosphere sun is below
		// the local horizon and reach full strength during astronomical night.
		const float SunElevation = FVector::DotProduct(LocalUp, -Sun->GetForwardVector());
		const float Night = FMath::Clamp((-SunElevation - 0.02f) / 0.28f, 0.f, 1.f);
		return Night * Night * (3.f - 2.f * Night);
	}
	if (!MoonFill)
	{
		return 0.f;
	}

	// RedDayNight keeps this fill opposite the sun. It is a fallback for maps where no valid
	// atmosphere sun exists, rather than overriding the light that actually composes the sky.
	const float MoonElevation = FVector::DotProduct(LocalUp, -MoonFill->GetForwardVector());
	const float Night = FMath::Clamp((MoonElevation - 0.02f) / 0.28f, 0.f, 1.f);
	return Night * Night * (3.f - 2.f * Night);
}

void ARedSpaceScenery::UpdateLocalSpacePresentation(const float DeltaSeconds)
{
	if (!StarField || !AnalyticStarDome || !GetWorld())
	{
		return;
	}
	// Celestial-body state must also advance on a dedicated server, which has no local
	// viewport but remains authoritative for moon gravity and collision.
	ResolveSunLight();
	ResolveMoonLight();
	UpdateMoonAlignment(DeltaSeconds);

	APlayerController* LocalController = GetWorld()->GetFirstPlayerController();
	if (!LocalController || !LocalController->IsLocalController())
	{
		if (OrbitExposurePostProcess)
		{
			OrbitExposurePostProcess->BlendWeight = 0.f;
		}
		SetLocalSurfaceSkyVisible(false);
		StarField->SetVisibility(false, true);
		StarField->SetHiddenInGame(true, true);
		AnalyticStarDome->SetVisibility(false, true);
		AnalyticStarDome->SetHiddenInGame(true, true);
		Asteroids->SetVisibility(false, true);
		Asteroids->SetHiddenInGame(true, true);
		return;
	}

	FVector ViewLocation = FVector::ZeroVector;
	FRotator ViewRotation = FRotator::ZeroRotator;
	LocalController->GetPlayerViewPoint(ViewLocation, ViewRotation);
	if (bUsingNightWaterT04MoonAudit && MoonAuditKeyLight && Moon)
	{
		const FVector ViewToMoon = (Moon->GetComponentLocation() - ViewLocation).GetSafeNormal();
		const FRotationMatrix ViewBasis(ViewRotation);
		const FVector KeyRayDirection = (
			ViewToMoon
			+ ViewBasis.GetUnitAxis(EAxis::Y) * 0.35f
			+ ViewBasis.GetUnitAxis(EAxis::Z) * 0.18f).GetSafeNormal();
		if (!KeyRayDirection.IsNearlyZero())
		{
			MoonAuditKeyLight->SetWorldRotation(KeyRayDirection.Rotation());
		}
	}
	if (APlayerCameraManager* CameraManager = LocalController->PlayerCameraManager)
	{
		// A seamless-travel/local-camera recreation can leave the old modifier object
		// valid but outered to the previous CameraManager. Rebind in that case rather
		// than silently applying the guard to a camera no longer rendering this view.
		if (!IsValid(OrbitExposureCameraModifier)
			|| OrbitExposureCameraModifier->GetTypedOuter<APlayerCameraManager>() != CameraManager)
		{
			OrbitExposureCameraModifier = Cast<URedSpaceExposureCameraModifier>(
				CameraManager->FindCameraModifierByClass(
					URedSpaceExposureCameraModifier::StaticClass()));
			if (!OrbitExposureCameraModifier)
			{
				OrbitExposureCameraModifier = Cast<URedSpaceExposureCameraModifier>(
					CameraManager->AddNewCameraModifier(
						URedSpaceExposureCameraModifier::StaticClass()));
			}
		}
		if (OrbitExposureCameraModifier)
		{
			OrbitExposureCameraModifier->SetPlanetFrame(
				HomePlanetCenter, HomePlanetSurfaceRadiusCm,
				GetWorld()->GetMapName().Contains(TEXT("50km_FusedPrototype")));
		}
	}
	// The fused prototype uses the single physical SkyAtmosphere configured by
	// RedGameMode.  Do not even spawn the legacy opaque surface dome here: creating
	// it and hiding it later in this tick can still expose one bright frame during
	// PIE startup or an altitude transition.
	if (GetWorld()->GetMapName().Contains(TEXT("50km_FusedPrototype")))
	{
		SetLocalSurfaceSkyVisible(false);
	}
	StarField->SetWorldLocation(ViewLocation, false, nullptr, ETeleportType::TeleportPhysics);
	AnalyticStarDome->SetWorldLocation(
		ViewLocation, false, nullptr, ETeleportType::TeleportPhysics);

	// Match the shared physical atmosphere configured by RedGameMode. Stars stay
	// absent from daylight/atmosphere and appear after the camera clears the shell.
	constexpr float SpaceStarVisibleAltitudeCm =
		RedPlanetPresentationTuning::SpaceTransitionAltitudeCm;
	const float ViewAltitudeCm =
		static_cast<float>((ViewLocation - HomePlanetCenter).Size()) - HomePlanetSurfaceRadiusCm;
	// Preserve the accepted bright baby-blue surface exposure exactly. Only begin
	// constraining histogram adaptation near the top of the atmosphere, then reach
	// the orbit exposure at the same point where stars finish fading in.
	const float OrbitExposureStartCm =
		RedPlanetPresentationTuning::AtmosphereHeightCm
		* RedPlanetPresentationTuning::OrbitExposureStartFraction;
	const float OrbitExposureEndCm =
		RedPlanetPresentationTuning::AtmosphereHeightCm
		* RedPlanetPresentationTuning::OrbitExposureEndFraction;
	const bool bFusedPrototype =
		GetWorld()->GetMapName().Contains(TEXT("50km_FusedPrototype"));
	const bool bNightWaterT04OrbitValidation =
		RedPlanetPresentationTuning::IsNightWaterT04MapName(GetWorld()->GetMapName())
		&& RedPlanetPresentationTuning::UseNightWaterT04SoStylizedRadial();
	// Star visibility is a world-space presentation rule, not a map-name rule. The
	// previous implementation calculated the altitude fade only for fused prototype
	// maps, so production maps could mark the geometry visible in space while still
	// feeding every star material zero emission. Keep exposure handling fused-only,
	// but let every supported world reach a visible star field above the gameplay
	// atmosphere transition.
	const float SpaceStarAlpha = FMath::SmoothStep(
		OrbitExposureStartCm,
		OrbitExposureEndCm,
		ViewAltitudeCm);
	const float OrbitExposureAlpha = bFusedPrototype ? SpaceStarAlpha : 0.f;
	if (OrbitExposurePostProcess)
	{
		OrbitExposurePostProcess->BlendWeight = 0.f;
	}
	if (OrbitExposureAlpha >= 0.99f && !bHasLoggedOrbitExposureActive)
	{
		bHasLoggedOrbitExposureActive = true;
		const float LoggedOrbitMinEv = bNightWaterT04OrbitValidation
			? RedPlanetPresentationTuning::NightWaterT04OrbitExposureMinEv
			: RedPlanetPresentationTuning::OrbitExposureTargetEv;
		const float LoggedOrbitMaxEv = bNightWaterT04OrbitValidation
			? RedPlanetPresentationTuning::NightWaterT04OrbitExposureMaxEv
			: RedPlanetPresentationTuning::OrbitExposureTargetEv;
		UE_LOG(LogRedSpaceScenery, Display,
			TEXT("Orbit exposure active: altitude=%.2fkm alpha=%.2f priority=%.0f targetEV=[%.2f,%.2f] bias=%.2f nightWaterT04=%d"),
			ViewAltitudeCm * 0.00001f, OrbitExposureAlpha,
			OrbitExposureCameraModifier ? 255.f : -1.f,
			LoggedOrbitMinEv, LoggedOrbitMaxEv,
			RedPlanetPresentationTuning::OrbitExposureBias,
			bNightWaterT04OrbitValidation ? 1 : 0);
	}
	else if (OrbitExposureAlpha <= 0.01f)
	{
		bHasLoggedOrbitExposureActive = false;
	}
	// The painted surface sky is deliberately gone well before the physical
	// atmosphere ends. Hysteresis prevents a visible flicker while a ship hovers
	// around the hand-off altitude.
	constexpr float HideSurfaceSkyAboveCm =
		RedPlanetPresentationTuning::AtmosphereHeightCm * 0.85f;
	constexpr float ShowSurfaceSkyBelowCm =
		RedPlanetPresentationTuning::AtmosphereHeightCm * 0.70f;
	const float NightFactor = ComputeLocalNightFactor(ViewLocation);
	const bool bNightT03VisualDiagnostic = GetWorld()->GetMapName().Contains(TEXT("Night_T03"));
	if (bNightT03VisualDiagnostic && MoonGlow && NightFactor >= 0.015f)
	{
		// Keep a readable, test-only disc inside the active camera rather than
		// guessing where the pawn is looking. This moves only the collision-free
		// glow shell; the physical moon remains on the coherent fill-light ray.
		const FRotationMatrix ViewBasis(ViewRotation);
		const FVector VisualDirection = (
			ViewBasis.GetUnitAxis(EAxis::X)
			+ ViewBasis.GetUnitAxis(EAxis::Y) * 0.32f
			+ ViewBasis.GetUnitAxis(EAxis::Z) * 0.24f).GetSafeNormal();
		constexpr float DiagnosticMoonDistanceCm = 6000000.f;
		constexpr float DiagnosticMoonRadiusCm = 150000.f;
		constexpr float EngineSphereRadiusCm = 50.f;
		MoonGlow->SetWorldLocation(
			ViewLocation + VisualDirection * DiagnosticMoonDistanceCm,
			false, nullptr, ETeleportType::TeleportPhysics);
		MoonGlow->SetWorldScale3D(FVector(DiagnosticMoonRadiusCm / EngineSphereRadiusCm));
		MoonGlow->SetVisibility(true, true);
		MoonGlow->SetHiddenInGame(false, true);
	}
	// Bring the guard fully in BEFORE the opaque fallback sky is disabled below.
	// The old 0.10 -> 0.55 ramp left a .015 -> .10 interval with a black physical
	// sky and the legacy -10 EV histogram still active: that was the white-frame
	// failure. This short twilight ramp finishes exactly at the sky hand-off.
	const float SurfaceNightExposureAlpha = bFusedPrototype
		&& ViewAltitudeCm < SpaceStarVisibleAltitudeCm
		? FMath::SmoothStep(0.f, 0.015f, NightFactor)
		: 0.f;
	if (OrbitExposureCameraModifier)
	{
		OrbitExposureCameraModifier->SetSurfaceNightExposure(SurfaceNightExposureAlpha);
	}
	// The fused planet must have one continuous atmosphere.  The old opaque
	// emissive dome was a second sky shell with its own altitude hysteresis; it
	// produced the white/blue layers and planet-sized flare seen during ascent.
	// Keep it available only for isolated legacy/diagnostic maps and let the
	// canonical SkyAtmosphere own the fused surface-to-space transition.
	const bool bShouldShowSurfaceSky = !bFusedPrototype && LocalStylizedSurfaceSky
		&& (bLocalSurfaceSkyVisible
			? ViewAltitudeCm < HideSurfaceSkyAboveCm
			: ViewAltitudeCm < ShowSurfaceSkyBelowCm)
		// The daytime fallback is an opaque emissive dome. Leaving it enabled after
		// sunset covered both the physical SkyAtmosphere night and every correctly
		// activated star disc. Hand the view back to the physical sky at true night.
		&& NightFactor < 0.015f;
	SetLocalSurfaceSkyVisible(bShouldShowSurfaceSky);
	const bool bInSpace = bHomePlanetFrameResolved && ViewAltitudeCm >= SpaceStarVisibleAltitudeCm;
	const float StarVisibility = FMath::Max(
		SpaceStarAlpha, FMath::Pow(NightFactor, 0.72f));
	// The orbit guard deliberately closes exposure by several stops. Compensate the
	// authored unlit stars locally so the dense field remains visible without leaking
	// stars into the daytime atmosphere.
	const float OrbitStarCompensationBase = bUsingNightWaterT04StarOverlayProof
		? RedPlanetPresentationTuning::OrbitStarEmissionCompensation
		: bNightWaterT04OrbitValidation
		? RedPlanetPresentationTuning::NightWaterT04OrbitStarEmissionCompensation
		: RedPlanetPresentationTuning::OrbitStarEmissionCompensation;
	const float StarExposureCompensation = FMath::Pow(
		OrbitStarCompensationBase,
		OrbitExposureAlpha);
	// Do not use a material default for the test: the MIDs below overwrite Emission
	// every frame.  Keep the multiplier strictly scoped to the disposable Night_T03
	// map so the shipped surface-night balance and the protected checkpoint remain
	// byte-for-byte unaffected.
	const bool bNightStarTuningTest = GetWorld()
		&& GetWorld()->GetMapName().Contains(TEXT("Night_T03"));
	if (bNightStarTuningTest && MoonGlowMaterialDynamic)
	{
		// F9 deliberately closes the camera exposure by several stops. Keep the
		// disposable diagnostic moon readable in both surface and orbit views;
		// production moon presentation is unchanged by this test-map-only branch.
		MoonGlowMaterialDynamic->SetScalarParameterValue(
			TEXT("Emission"), 18.f * StarExposureCompensation);
	}
	const float StarPresentationGain = StarVisibility * StarExposureCompensation
		* (bNightStarTuningTest ? 6.f : 1.f);
	// The fused orbit camera is intentionally pinned to EV13.5 so the planet stays
	// readable. Small unlit star discs need absolute emissive targets at that EV;
	// a 3x multiplier only produced values of 21/48/108, which tone-mapped to black.
	// Keep the accepted low-EV surface-night and NightWater validation values intact.
	const bool bHighEvFusedOrbit = bFusedPrototype && !bNightWaterT04OrbitValidation;
	const float StarTestGain = bNightStarTuningTest ? 6.f : 1.f;
	const float DimStarEmission = StarVisibility * StarTestGain * (bHighEvFusedOrbit
		? FMath::Lerp(7.f, 3500.f, OrbitExposureAlpha)
		: 7.f * StarExposureCompensation);
	const float MediumStarEmission = StarVisibility * StarTestGain * (bHighEvFusedOrbit
		? FMath::Lerp(16.f, 8000.f, OrbitExposureAlpha)
		: 16.f * StarExposureCompensation);
	const float BrightStarEmission = StarVisibility * StarTestGain * (bHighEvFusedOrbit
		? FMath::Lerp(36.f, 18000.f, OrbitExposureAlpha)
		: 36.f * StarExposureCompensation);
	const auto ScaleStarRgb = [](const FLinearColor& Color, const float Gain)
	{
		return FLinearColor(Color.R * Gain, Color.G * Gain, Color.B * Gain, 1.f);
	};
	const bool bSurfaceNight = bHomePlanetFrameResolved
		&& ViewAltitudeCm < SpaceStarVisibleAltitudeCm && StarVisibility >= 0.015f;
	// Render state must follow the same non-zero presentation alpha written to the
	// materials. This keeps telemetry honest and prevents a visible component whose
	// stars are all black because an unrelated boolean said the camera was in space.
	const bool bShowStars = bHomePlanetFrameResolved && StarVisibility >= 0.015f;
	if (AnalyticStarDomeMaterialDynamic)
	{
		AnalyticStarDomeMaterialDynamic->SetScalarParameterValue(
			TEXT("Visibility"), StarVisibility);
		AnalyticStarDomeMaterialDynamic->SetScalarParameterValue(
			TEXT("Emission"),
			(bUsingNightT03MilkyWaySky ? 12.f : 64.f) * StarExposureCompensation);
	}
	if (StarMaterialDynamic)
	{
		const FLinearColor BaseColor(0.62f, 0.75f, 1.00f, 1.f);
		if (bStarMaterialUsesEmissionParameter)
		{
			StarMaterialDynamic->SetVectorParameterValue(TEXT("Color"), BaseColor);
			StarMaterialDynamic->SetScalarParameterValue(
				TEXT("Emission"), DimStarEmission);
		}
		else
		{
			StarMaterialDynamic->SetVectorParameterValue(
				TEXT("Color"), ScaleStarRgb(BaseColor, 12.f * StarPresentationGain));
		}
	}
	if (MediumStarMaterialDynamic)
	{
		const FLinearColor BaseColor(0.88f, 0.94f, 1.00f, 1.f);
		if (bStarMaterialUsesEmissionParameter)
		{
			MediumStarMaterialDynamic->SetVectorParameterValue(TEXT("Color"), BaseColor);
			MediumStarMaterialDynamic->SetScalarParameterValue(
				TEXT("Emission"), MediumStarEmission);
		}
		else
		{
			MediumStarMaterialDynamic->SetVectorParameterValue(
				TEXT("Color"), ScaleStarRgb(BaseColor, 28.f * StarPresentationGain));
		}
	}
	if (BrightStarMaterialDynamic)
	{
		const FLinearColor BaseColor(0.96f, 0.98f, 1.00f, 1.f);
		if (bStarMaterialUsesEmissionParameter)
		{
			BrightStarMaterialDynamic->SetVectorParameterValue(TEXT("Color"), BaseColor);
			BrightStarMaterialDynamic->SetScalarParameterValue(
				TEXT("Emission"), BrightStarEmission);
		}
		else
		{
			BrightStarMaterialDynamic->SetVectorParameterValue(
				TEXT("Color"), ScaleStarRgb(BaseColor, 70.f * StarPresentationGain));
		}
	}
	const bool bShowAnalyticStars = bShowStars && bAnalyticStarDomeReady;
	const bool bShowProceduralStars = bShowStars && !bAnalyticStarDomeReady;
	AnalyticStarDome->SetVisibility(bShowAnalyticStars, true);
	AnalyticStarDome->SetHiddenInGame(!bShowAnalyticStars, true);
	StarField->SetVisibility(bShowProceduralStars, true);
	StarField->SetHiddenInGame(!bShowProceduralStars, true);
	// Enable the field only after the gameplay atmosphere hand-off. Its radial gap and
	// per-instance cull distance still prevent any rock from rendering through the limb.
	const bool bShowAsteroids = bHomePlanetFrameResolved
		&& ViewAltitudeCm >= RedPlanetPresentationTuning::AsteroidVisibleAltitudeCm;
	Asteroids->SetVisibility(bShowAsteroids, true);
	Asteroids->SetHiddenInGame(!bShowAsteroids, true);
	const bool bInitialVisibilityLog = !bHasLoggedStarVisibility;
	if (bInitialVisibilityLog || bShowStars != bLastStarsVisible)
	{
		bHasLoggedStarVisibility = true;
		bLastStarsVisible = bShowStars;
		const FVector LocalUp = (ViewLocation - HomePlanetCenter).GetSafeNormal();
		const UDirectionalLightComponent* ResolvedSun = CachedSunLight.Get();
		const UDirectionalLightComponent* ResolvedMoon = CachedMoonLight.Get();
		const float SunElevation = ResolvedSun && !LocalUp.IsNearlyZero()
			? FVector::DotProduct(LocalUp, -ResolvedSun->GetForwardVector()) : -2.f;
		const float MoonElevation = ResolvedMoon && !LocalUp.IsNearlyZero()
			? FVector::DotProduct(LocalUp, -ResolvedMoon->GetForwardVector()) : -2.f;
		UE_LOG(LogRedSpaceScenery, Display,
			TEXT("Stars %s: initial=%d mode=%s planetFrame=%d inSpace=%d surfaceNight=%d altitude=%.0fcm transition=%.0fcm night=%.3f nightPP=%.3f spaceAlpha=%.3f exposureAlpha=%.3f starAlpha=%.3f compensation=%.1f proceduralEmission=%.1f/%.1f/%.1f overlayProof=%d sun=%s sunElev=%.3f atmSun=%d atmIndex=%d moon=%s moonElev=%.3f geometry=%d/%d/%d"),
			bShowStars ? TEXT("visible") : TEXT("hidden"), bInitialVisibilityLog ? 1 : 0,
			bUsingNightT03MilkyWaySky ? TEXT("milkyway-dome")
				: (bAnalyticStarDomeReady ? TEXT("analytic-dome") : TEXT("procedural-fallback")),
			bHomePlanetFrameResolved ? 1 : 0, bInSpace ? 1 : 0, bSurfaceNight ? 1 : 0,
			ViewAltitudeCm, SpaceStarVisibleAltitudeCm, NightFactor, SurfaceNightExposureAlpha,
			SpaceStarAlpha, OrbitExposureAlpha, StarVisibility,
			StarExposureCompensation,
			7.f * StarPresentationGain, 16.f * StarPresentationGain,
			36.f * StarPresentationGain,
			bUsingNightWaterT04StarOverlayProof ? 1 : 0,
			*GetNameSafe(ResolvedSun), SunElevation,
			ResolvedSun && ResolvedSun->IsUsedAsAtmosphereSunLight() ? 1 : 0,
			ResolvedSun ? static_cast<int32>(ResolvedSun->GetAtmosphereSunLightIndex()) : -1,
			*GetNameSafe(ResolvedMoon), MoonElevation,
			DimStarCount, MediumStarCount, BrightStarCount);
	}
}

void ARedSpaceScenery::EnsureLocalSurfaceSky()
{
	if (IsValid(LocalStylizedSurfaceSky) || !GetWorld()
		|| GetNetMode() == NM_DedicatedServer
		|| !GetWorld()->GetMapName().Contains(TEXT("50km_FusedPrototype")))
	{
		return;
	}
	// A live editor can keep an older native CDO after this hard reference is
	// introduced. Retry the exact package at runtime as well; packaged clients
	// still retain the constructor reference and explicit cook assertion.
	if (!SurfaceBabyBlueSkyMaterial)
	{
		SurfaceBabyBlueSkyMaterial = LoadObject<UMaterialInterface>(nullptr,
			TEXT("/Game/RedMMO/Environment/M_RedBabyBlueSurfaceSky.M_RedBabyBlueSurfaceSky"));
		if (!SurfaceBabyBlueSkyMaterial)
		{
			UE_LOG(LogRedSpaceScenery, Error,
				TEXT("Surface baby-blue sky material failed to load; refusing to claim the bright-sky gate"));
		}
	}

	UClass* SkyClass = LoadClass<AActor>(nullptr,
		TEXT("/Game/SoStylized/Environment/Sky/BP_StylizedSky_Lite.BP_StylizedSky_Lite_C"));
	if (!SkyClass)
	{
		UE_LOG(LogRedSpaceScenery, Warning,
			TEXT("Surface sky fallback unavailable: BP_StylizedSky_Lite did not load"));
		return;
	}

	FActorSpawnParameters Params;
	Params.Name = TEXT("Red_LocalStylizedSurfaceSkyFallback");
	Params.ObjectFlags |= RF_Transient;
	Params.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
	LocalStylizedSurfaceSky = GetWorld()->SpawnActor<AActor>(
		SkyClass, HomePlanetCenter, FRotator::ZeroRotator, Params);
	if (!LocalStylizedSurfaceSky)
	{
		return;
	}
	LocalStylizedSurfaceSky->SetReplicates(false);
	LocalStylizedSurfaceSky->SetReplicateMovement(false);
	LocalStylizedSurfaceSky->SetActorEnableCollision(false);

	TInlineComponentArray<UActorComponent*> Components(LocalStylizedSurfaceSky);
	for (UActorComponent* Component : Components)
	{
		if (!IsValid(Component))
		{
			continue;
		}
		const bool bIsSkyDome = Component->GetName().Equals(TEXT("SkyDome"));
		if (UPrimitiveComponent* Primitive = Cast<UPrimitiveComponent>(Component))
		{
			Primitive->SetCollisionEnabled(ECollisionEnabled::NoCollision);
			Primitive->SetGenerateOverlapEvents(false);
			Primitive->SetCastShadow(false);
			Primitive->SetReceivesDecals(false);
			Primitive->SetCanEverAffectNavigation(false);
			Primitive->SetVisibility(bIsSkyDome, true);
			Primitive->SetHiddenInGame(!bIsSkyDome, true);
		}
		if (bIsSkyDome)
		{
			LocalStylizedSkyDome = Cast<UStaticMeshComponent>(Component);
			continue;
		}
		if (UDirectionalLightComponent* Directional =
			Cast<UDirectionalLightComponent>(Component))
		{
			Directional->SetAtmosphereSunLight(false);
		}
		if (ULightComponent* Light = Cast<ULightComponent>(Component))
		{
			Light->SetIntensity(0.f);
			Light->SetVisibility(false, true);
			Light->Deactivate();
		}
		if (USkyLightComponent* SkyLight = Cast<USkyLightComponent>(Component))
		{
			SkyLight->SetIntensity(0.f);
			SkyLight->bRealTimeCapture = false;
			SkyLight->SetVisibility(false, true);
			SkyLight->Deactivate();
		}
		if (UExponentialHeightFogComponent* Fog =
			Cast<UExponentialHeightFogComponent>(Component))
		{
			Fog->SetFogDensity(0.f);
			Fog->SetVisibility(false, true);
			Fog->Deactivate();
		}
		if (UPostProcessComponent* PostProcess = Cast<UPostProcessComponent>(Component))
		{
			PostProcess->bEnabled = false;
			PostProcess->BlendWeight = 0.f;
			PostProcess->SetVisibility(false, true);
			PostProcess->Deactivate();
		}
	}

	if (LocalStylizedSkyDome)
	{
		LocalStylizedSkyDome->bNeverDistanceCull = true;
		LocalStylizedSkyDome->BoundsScale = 2.f;
		// Keep the pack's proven inside-facing dome geometry, but use a deterministic
		// project sky material. The So Stylized curve atlas still graded the fused
		// prototype toward a muted teal under its physical daylight exposure, whereas
		// this surface-only material is authored to the requested clear baby blue. It
		// is hidden before orbit, so SkyAtmosphere continues to own the distant limb.
		if (SurfaceBabyBlueSkyMaterial)
		{
			LocalStylizedSkyDome->SetMaterial(0, SurfaceBabyBlueSkyMaterial);
		}
		LocalStylizedSkyMaterial =
			LocalStylizedSkyDome->CreateAndSetMaterialInstanceDynamic(0);
		if (LocalStylizedSkyMaterial && SurfaceBabyBlueSkyMaterial)
		{
			LocalStylizedSkyMaterial->SetVectorParameterValue(
				TEXT("SkyColor"), RedPlanetPresentationTuning::SurfaceBabyBlueColor);
			LocalStylizedSkyMaterial->SetScalarParameterValue(
				TEXT("Emission"), RedPlanetPresentationTuning::SurfaceBabyBlueEmission);
		}
		else if (LocalStylizedSkyMaterial)
		{
			// Cook/load failure fallback: preserve the old pack material as a clear
			// cloudless daytime sky instead of restoring its muted default grade.
			LocalStylizedSkyMaterial->SetScalarParameterValue(TEXT("BG Clouds Strength"), 0.f);
			LocalStylizedSkyMaterial->SetScalarParameterValue(TEXT("Day Curve"), 0.f);
			LocalStylizedSkyMaterial->SetScalarParameterValue(TEXT("Sky Brightness"), 32000.f);
			LocalStylizedSkyMaterial->SetScalarParameterValue(TEXT("Saturation"), 0.65f);
		}
	}

	bLocalSurfaceSkyVisible = true;
	SetLocalSurfaceSkyVisible(true);
	UE_LOG(LogRedSpaceScenery, Display,
		TEXT("Surface sky fallback spawned: actor=%s dome=%s material=%s clouds/lights/fog/post disabled"),
		*GetNameSafe(LocalStylizedSurfaceSky), *GetNameSafe(LocalStylizedSkyDome),
		*GetNameSafe(LocalStylizedSkyDome ? LocalStylizedSkyDome->GetMaterial(0) : nullptr));
}

void ARedSpaceScenery::SetLocalSurfaceSkyVisible(const bool bVisible)
{
	if (!LocalStylizedSkyDome)
	{
		bLocalSurfaceSkyVisible = false;
		return;
	}
	if (bLocalSurfaceSkyVisible == bVisible
		&& LocalStylizedSkyDome->IsVisible() == bVisible
		&& (!LocalStylizedSurfaceSky
			|| LocalStylizedSurfaceSky->IsHidden() == !bVisible))
	{
		return;
	}
	bLocalSurfaceSkyVisible = bVisible;
	// Hide the whole local-only Blueprint at night, not just its primary dome mesh.
	// BP_StylizedSky_Lite also owns helper/cloud components which can finish streaming
	// after the initial component pass.  A late helper becoming visible was enough to
	// leave an opaque emissive white hemisphere over the physical night sky even while
	// the primary SkyDome reported hidden.  This actor contains no canonical atmosphere;
	// RedGameMode owns the separate SunSky atmosphere used for the planet and orbital limb.
	if (LocalStylizedSurfaceSky)
	{
		LocalStylizedSurfaceSky->SetActorHiddenInGame(!bVisible);
	}
	LocalStylizedSkyDome->SetVisibility(bVisible, true);
	LocalStylizedSkyDome->SetHiddenInGame(!bVisible, true);
	LocalStylizedSkyDome->MarkRenderStateDirty();
	UE_LOG(LogRedSpaceScenery, Display,
		TEXT("Surface sky fallback %s: actorHidden=%d domeVisible=%d domeHidden=%d"),
		bVisible ? TEXT("visible") : TEXT("hidden"),
		LocalStylizedSurfaceSky && LocalStylizedSurfaceSky->IsHidden() ? 1 : 0,
		LocalStylizedSkyDome->IsVisible() ? 1 : 0,
		LocalStylizedSkyDome->bHiddenInGame ? 1 : 0);
}

bool ARedSpaceScenery::GetMoonGravityBody(
	FVector& OutCenter, float& OutSurfaceRadius, float& OutInfluenceRadius) const
{
	if (!IsValid(Moon) || MoonSurfaceRadiusCm <= 0.f || MoonGravityInfluenceRadiusCm <= 0.f)
	{
		return false;
	}
	OutCenter = Moon->GetComponentLocation();
	OutSurfaceRadius = MoonSurfaceRadiusCm;
	OutInfluenceRadius = FMath::Max(MoonGravityInfluenceRadiusCm, MoonSurfaceRadiusCm);
	return !OutCenter.ContainsNaN();
}

void ARedSpaceScenery::AppendGravityBodies(
	TArray<FName>& OutStableIds, TArray<int32>& OutPriorities,
	TArray<FVector>& OutCenters, TArray<float>& OutSurfaceRadii,
	TArray<float>& OutInfluenceRadii) const
{
	auto AppendBody = [&OutStableIds, &OutPriorities, &OutCenters,
		&OutSurfaceRadii, &OutInfluenceRadii](
		const FName StableId, const int32 Priority,
		const UStaticMeshComponent* Component, const float SurfaceRadiusCm,
		const float InfluenceRadiusCm)
	{
		if (StableId.IsNone() || !IsValid(Component)
			|| SurfaceRadiusCm <= 0.f || InfluenceRadiusCm <= 0.f)
		{
			return;
		}
		const FVector Center = Component->GetComponentLocation();
		if (Center.ContainsNaN())
		{
			return;
		}
		OutStableIds.Add(StableId);
		OutPriorities.Add(Priority);
		OutCenters.Add(Center);
		OutSurfaceRadii.Add(SurfaceRadiusCm);
		OutInfluenceRadii.Add(FMath::Max(InfluenceRadiusCm, SurfaceRadiusCm));
	};

	AppendBody(TEXT("moon.red.mars.primary"), 150,
		Moon, MoonSurfaceRadiusCm, MoonGravityInfluenceRadiusCm);
	if (!bEnableLegacySaturnPrototype || !bRingWorldBuilt)
	{
		return;
	}
	AppendBody(TEXT("moon.red.ring-01.a"), 200,
		RingMoonA, RingMoonSurfaceRadiiCm.X, RingMoonGravityInfluenceRadiiCm.X);
	AppendBody(TEXT("moon.red.ring-01.b"), 200,
		RingMoonB, RingMoonSurfaceRadiiCm.Y, RingMoonGravityInfluenceRadiiCm.Y);
	AppendBody(TEXT("moon.red.ring-01.c"), 200,
		RingMoonC, RingMoonSurfaceRadiiCm.Z, RingMoonGravityInfluenceRadiiCm.Z);
}
