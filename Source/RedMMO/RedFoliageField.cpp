#include "RedFoliageField.h"

#include "Components/HierarchicalInstancedStaticMeshComponent.h"
#include "Engine/CollisionProfile.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "Materials/MaterialInterface.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "RedGravityBodies.h"
#include "TimerManager.h"
#include "UObject/UnrealType.h"

DEFINE_LOG_CATEGORY_STATIC(LogRedFoliage, Log, All);

namespace
{
	void AddDefault(TArray<TSoftObjectPtr<UStaticMesh>>& Arr, const TCHAR* Path)
	{
		Arr.Add(TSoftObjectPtr<UStaticMesh>(FSoftObjectPath(Path)));
	}

	bool IsCLMPlanetClass(const UClass* Class)
	{
		for (const UClass* Current = Class; Current; Current = Current->GetSuperClass())
		{
			if (Current->GetName() == TEXT("CLMPlanet"))
			{
				return true;
			}
		}
		return false;
	}

	AActor* FindCLMPlanetActor(UWorld* World, const FVector& ExpectedCenter)
	{
		AActor* Fallback = nullptr;
		for (TActorIterator<AActor> It(World); It; ++It)
		{
			AActor* Actor = *It;
			if (!IsValid(Actor) || !IsCLMPlanetClass(Actor->GetClass()))
			{
				continue;
			}

			Fallback = Actor;
			if (Actor->GetActorLocation().Equals(ExpectedCenter, 1.f))
			{
				return Actor;
			}
		}
		return Fallback;
	}

	void AppendIdentity(const UObject* Object, FString& OutIdentity)
	{
		if (!Object)
		{
			return;
		}

		OutIdentity += TEXT(" ");
		OutIdentity += Object->GetName();
		for (const UClass* Class = Object->GetClass(); Class; Class = Class->GetSuperClass())
		{
			OutIdentity += TEXT(" ");
			OutIdentity += Class->GetName();
		}

		if (const AActor* Actor = Cast<AActor>(Object))
		{
#if WITH_EDITOR
			OutIdentity += TEXT(" ");
			OutIdentity += Actor->GetActorLabel();
#endif
			for (const FName Tag : Actor->Tags)
			{
				OutIdentity += TEXT(" ");
				OutIdentity += Tag.ToString();
			}
		}
	}

	bool IsKnownPlanetObject(const UObject* Object, const AActor* PlanetActor)
	{
		if (!Object)
		{
			return false;
		}
		if (Object == PlanetActor || IsCLMPlanetClass(Object->GetClass()))
		{
			return true;
		}

		FString Identity;
		AppendIdentity(Object, Identity);
		Identity.ToLowerInline();
		return Identity.Contains(TEXT("clmplanet"))
			|| Identity.Contains(TEXT("clm_planet"))
			|| Identity.Contains(TEXT("planetgen"));
	}

	bool ReferencesPlanet(const UObject* Object, const AActor* PlanetActor)
	{
		if (!Object)
		{
			return false;
		}

		for (TFieldIterator<FObjectPropertyBase> It(Object->GetClass(), EFieldIteratorFlags::IncludeSuper); It; ++It)
		{
			FString PropertyName = It->GetName();
			PropertyName.ToLowerInline();
			if (!PropertyName.Contains(TEXT("planet")) && !PropertyName.Contains(TEXT("clm")))
			{
				continue;
			}

			if (IsKnownPlanetObject(It->GetObjectPropertyValue_InContainer(Object), PlanetActor))
			{
				return true;
			}
		}
		return false;
	}

	bool IsLivePlanetTerrainComponent(const FHitResult& Hit, const AActor* PlanetActor,
		const FVector& PlanetCenter, float PeakRadius)
	{
		const UPrimitiveComponent* HitComponent = Hit.GetComponent();
		const AActor* HitActor = Hit.GetActor();
		if (!HitComponent || !HitActor)
		{
			return false;
		}

		FString Identity;
		AppendIdentity(HitComponent, Identity);
		bool bOwnedByPlanet = false;
		const AActor* Actor = HitActor;
		for (int32 OwnerDepth = 0; Actor && OwnerDepth < 8; ++OwnerDepth, Actor = Actor->GetOwner())
		{
			AppendIdentity(Actor, Identity);
			if (Actor == PlanetActor || IsCLMPlanetClass(Actor->GetClass()))
			{
				bOwnedByPlanet = true;
			}
		}
		Identity.ToLowerInline();

		// These are common blockers above the ground. A multi trace continues past them to the
		// generated CLM chunk, so rejecting one does not discard an otherwise valid sample.
		static const TCHAR* RejectedTokens[] =
		{
			TEXT("ship"), TEXT("shuttle"), TEXT("spacecraft"), TEXT("vehicle"),
			TEXT("character"), TEXT("player"), TEXT("pawn"), TEXT("weapon"),
			TEXT("projectile"), TEXT("bolt"), TEXT("building"), TEXT("structure"),
			TEXT("foliage"), TEXT("grass"), TEXT("flower"), TEXT("cactus"),
			TEXT("gameplaysurface"), TEXT("presentation"), TEXT("orbit"), TEXT("atmosphere"),
			TEXT("cloud"), TEXT("skydome"), TEXT("starlayer"), TEXT("reticle"), TEXT("hud")
		};
		for (const TCHAR* Token : RejectedTokens)
		{
			if (Identity.Contains(Token))
			{
				return false;
			}
		}
		if (bOwnedByPlanet)
		{
			return true;
		}

		if (ReferencesPlanet(HitComponent, PlanetActor) || ReferencesPlanet(HitActor, PlanetActor))
		{
			return true;
		}

		static const TCHAR* PlanetTerrainTokens[] =
		{
			TEXT("clm"), TEXT("planetgen"), TEXT("planet_chunk"), TEXT("planetchunk"),
			TEXT("terrain_chunk"), TEXT("terrainchunk")
		};
		for (const TCHAR* Token : PlanetTerrainTokens)
		{
			if (Identity.Contains(Token))
			{
				return true;
			}
		}

		const FString ComponentClass = HitComponent->GetClass()->GetName().ToLower();
		const bool bRuntimeMesh = ComponentClass.Contains(TEXT("procedural"))
			|| ComponentClass.Contains(TEXT("dynamicmesh"))
			|| ComponentClass.Contains(TEXT("realtimemesh"))
			|| ComponentClass.Contains(TEXT("runtimemesh"));
		const bool bTerrainNamed = Identity.Contains(TEXT("terrain"))
			|| Identity.Contains(TEXT("planet"))
			|| Identity.Contains(TEXT("chunk"))
			|| Identity.Contains(TEXT("octree"));
		if (bRuntimeMesh && bTerrainNamed)
		{
			return true;
		}

		// Some PlanetGen versions give streamed procedural components generic names. Their owning
		// actor remains at the planet origin, unlike ships and ordinary surface props.
		const float OriginTolerance = FMath::Max(5000.f, PeakRadius * 0.05f);
		return bRuntimeMesh
			&& FVector::DistSquared(HitActor->GetActorLocation(), PlanetCenter)
				<= FMath::Square(OriginTolerance);
	}

	bool HasLivePlanetCollision(UWorld* World, const AActor* IgnoreActor,
		const AActor* PlanetActor, const FVector& PlanetCenter, float DatumRadius, float PeakRadius,
		const FVector& SampleLocation)
	{
		FVector Direction = (SampleLocation - PlanetCenter).GetSafeNormal();
		if (Direction.IsNearlyZero())
		{
			Direction = FVector::UpVector;
		}

		FCollisionObjectQueryParams ObjectTypes;
		ObjectTypes.AddObjectTypesToQuery(ECC_WorldStatic);
		ObjectTypes.AddObjectTypesToQuery(ECC_WorldDynamic);
		FCollisionQueryParams Query(SCENE_QUERY_STAT(RedFoliageCollisionProbe), false, IgnoreActor);
		TArray<FHitResult> Hits;
		World->LineTraceMultiByObjectType(
			Hits,
			PlanetCenter + Direction * (PeakRadius + 5000.f),
			PlanetCenter + Direction * DatumRadius,
			ObjectTypes,
			Query);

		for (const FHitResult& Hit : Hits)
		{
			const float HitRadius = FVector::Distance(Hit.ImpactPoint, PlanetCenter);
			if (Hit.bBlockingHit && HitRadius >= DatumRadius && HitRadius <= PeakRadius + 5000.f
				&& IsLivePlanetTerrainComponent(Hit, PlanetActor, PlanetCenter, PeakRadius))
			{
				return true;
			}
		}
		return false;
	}
}

ARedFoliageField::ARedFoliageField()
{
	PrimaryActorTick.bCanEverTick = false;
	bReplicates = true;
	bAlwaysRelevant = true;
	SetNetUpdateFrequency(0.25f);
	RootComponent = CreateDefaultSubobject<USceneComponent>(TEXT("Root"));

	// Saturated, non-Earth ground cover. Keep only the two grass silhouettes here: the former
	// fern entries were immediately recognizable as ordinary terrestrial plants.
	AddDefault(GrassMeshes, TEXT("/Game/SoStylized/Environment/Foliage/SM_Grass1.SM_Grass1"));
	AddDefault(GrassMeshes, TEXT("/Game/SoStylized/Environment/Foliage/SM_Grass2.SM_Grass2"));

	// Alien silhouettes: clustered bulbs, tall marsh tails and oversized shield leaves.
	// These are the least fern/flower-like meshes in the currently installed SoStylized pack.
	AddDefault(FlowerMeshes, TEXT("/Game/SoStylized/Environment/Foliage/SM_FlowerDesertBulb01.SM_FlowerDesertBulb01"));
	AddDefault(FlowerMeshes, TEXT("/Game/SoStylized/Environment/Foliage/SM_FlowerDesertBulb02.SM_FlowerDesertBulb02"));
	AddDefault(FlowerMeshes, TEXT("/Game/SoStylized/Environment/Foliage/SM_FlowerDesertBulb03.SM_FlowerDesertBulb03"));
	AddDefault(FlowerMeshes, TEXT("/Game/SoStylized/Environment/Foliage/SM_FlowerDesertBulb04.SM_FlowerDesertBulb04"));
	AddDefault(FlowerMeshes, TEXT("/Game/SoStylized/Environment/Foliage/SM_FlowerDesertBulb05.SM_FlowerDesertBulb05"));
	AddDefault(FlowerMeshes, TEXT("/Game/SoStylized/Environment/Foliage/SM_Marshtail01.SM_Marshtail01"));
	AddDefault(FlowerMeshes, TEXT("/Game/SoStylized/Environment/Foliage/SM_Marshtail02.SM_Marshtail02"));
	AddDefault(FlowerMeshes, TEXT("/Game/SoStylized/Environment/Foliage/SM_Marshtail03.SM_Marshtail03"));
	AddDefault(FlowerMeshes, TEXT("/Game/SoStylized/Environment/Foliage/SM_Marshtail04.SM_Marshtail04"));
	AddDefault(FlowerMeshes, TEXT("/Game/SoStylized/Environment/Foliage/SM_CactusBulb01.SM_CactusBulb01"));
	AddDefault(FlowerMeshes, TEXT("/Game/SoStylized/Environment/Foliage/SM_CactusBulb02.SM_CactusBulb02"));
	AddDefault(FlowerMeshes, TEXT("/Game/SoStylized/Environment/Foliage/SM_ElephantEars02.SM_ElephantEars02"));
	AddDefault(FlowerMeshes, TEXT("/Game/SoStylized/Environment/Foliage/SM_ElephantEars03.SM_ElephantEars03"));

	AddDefault(RockMeshes, TEXT("/Game/SoStylized/Environment/Rocks/Desert/SM_RockDesert_Clump01.SM_RockDesert_Clump01"));
	AddDefault(RockMeshes, TEXT("/Game/SoStylized/Environment/Rocks/Desert/SM_RockDesert_Rock06.SM_RockDesert_Rock06"));
	AddDefault(RockMeshes, TEXT("/Game/SoStylized/Environment/Rocks/Desert/SM_RockDesert_Layered03.SM_RockDesert_Layered03"));
	AddDefault(RockMeshes, TEXT("/Game/SoStylized/Environment/Rocks/Desert/SM_RockDesert_Shelf04.SM_RockDesert_Shelf04"));

	AddDefault(CliffMeshes, TEXT("/Game/SoStylized/Environment/Rocks/Desert/SM_RockDesert_CliffA03.SM_RockDesert_CliffA03"));
	AddDefault(CliffMeshes, TEXT("/Game/SoStylized/Environment/Rocks/Desert/SM_RockDesert_CliffB06.SM_RockDesert_CliffB06"));
	AddDefault(CliffMeshes, TEXT("/Game/SoStylized/Environment/Rocks/Desert/SM_RockDesert_Hoodoo07.SM_RockDesert_Hoodoo07"));
	AddDefault(CliffMeshes, TEXT("/Game/SoStylized/Environment/Rocks/Desert/SM_RockDesert_HoodooCliff04.SM_RockDesert_HoodooCliff04"));

	AddDefault(SnowMeshes, TEXT("/Game/SoStylized/Environment/Foliage/SM_FlowersIce01.SM_FlowersIce01"));
	AddDefault(SnowMeshes, TEXT("/Game/SoStylized/Environment/Foliage/SM_FlowersIce02.SM_FlowersIce02"));
	AddDefault(SnowMeshes, TEXT("/Game/SoStylized/Environment/Foliage/SM_FlowersIce03.SM_FlowersIce03"));

	GrassOverrideMaterial = TSoftObjectPtr<UMaterialInterface>(FSoftObjectPath(
		TEXT("/Game/RedMMO/Environment/Materials/MI_AlienGrass_NoColorMap.MI_AlienGrass_NoColorMap")));

	// Deliberately synthetic rather than one uniformly purple field: violet and cyan ground
	// cover, with magenta/acid/cobalt/amber/violet accent clusters.
	GrassTintPalette = {
		FLinearColor(0.72f, 0.035f, 1.15f, 1.f),
		FLinearColor(0.015f, 0.82f, 1.20f, 1.f),
	};
	AlienAccentTintPalette = {
		FLinearColor(0.82f, 0.025f, 0.34f, 1.f),
		FLinearColor(0.025f, 0.72f, 0.30f, 1.f),
		FLinearColor(0.025f, 0.20f, 0.95f, 1.f),
		FLinearColor(0.95f, 0.24f, 0.015f, 1.f),
		FLinearColor(0.42f, 0.025f, 0.90f, 1.f),
	};
}

void ARedFoliageField::BeginPlay()
{
	Super::BeginPlay();

	if (bSuppressAllProceduralDressing)
	{
		GetWorldTimerManager().ClearTimer(RegenerateRetryTimer);
		ClearFoliage();
		SetActorHiddenInGame(true);
		SetActorEnableCollision(false);
		UE_LOG(LogRedFoliage, Display,
			TEXT("RedFoliageField disabled: desert/ocean-only presentation cleared all baked HISMs."));
		return;
	}

	if (bAutoGenerateOnPlay && GetInstanceTotal() == 0)
	{
		GetWorldTimerManager().SetTimer(
			RegenerateRetryTimer, this, &ARedFoliageField::Regenerate, 2.5f, false);
	}
}

int32 ARedFoliageField::GetInstanceTotal() const
{
	int32 Total = 0;
	TArray<UHierarchicalInstancedStaticMeshComponent*> Found;
	GetComponents(Found);
	for (const UHierarchicalInstancedStaticMeshComponent* H : Found)
	{
		if (H)
		{
			Total += H->GetInstanceCount();
		}
	}
	return Total;
}

void ARedFoliageField::ScheduleRegenerationRetry(const TCHAR* Reason)
{
	if (!bWaitingForPlanetTerrain)
	{
		UE_LOG(LogRedFoliage, Warning,
			TEXT("RedFoliageField is waiting for PlanetGen terrain collision (%s); retrying in 2 seconds."),
			Reason);
	}
	bWaitingForPlanetTerrain = true;
	if (UWorld* World = GetWorld())
	{
		World->GetTimerManager().SetTimer(
			RegenerateRetryTimer, this, &ARedFoliageField::Regenerate, 2.f, false);
	}
}

UHierarchicalInstancedStaticMeshComponent* ARedFoliageField::MakeHism(
	UStaticMesh* Mesh, bool bOverrideMaterial, bool bEnableCollision,
	EScatterLayer Layer, int32 MaterialVariant)
{
	UHierarchicalInstancedStaticMeshComponent* H = NewObject<UHierarchicalInstancedStaticMeshComponent>(this);
	H->SetStaticMesh(Mesh);
	H->SetupAttachment(RootComponent);
	H->SetCollisionEnabled(bEnableCollision
		? ECollisionEnabled::QueryAndPhysics : ECollisionEnabled::NoCollision);
	if (bEnableCollision)
	{
		H->SetCollisionProfileName(UCollisionProfile::BlockAll_ProfileName);
	}
	// Dense alpha-tested ground cover is the expensive case: thousands of tiny shadow
	// casters and distance-field contributors cost far more than their readable result.
	// Keep authored rock/cliff shadows, but make grass, accent plants, and snow tufts cheap.
	const bool bDenseGroundCover = Layer == EScatterLayer::Grass
		|| Layer == EScatterLayer::AlienAccent
		|| Layer == EScatterLayer::SnowAccent;
	H->SetCastShadow(!bDenseGroundCover);
	H->bAffectDistanceFieldLighting = !bDenseGroundCover;
	H->SetCullDistances(0, bEnableCollision ? 90000 : 60000);
	if (bOverrideMaterial)
	{
		if (UMaterialInterface* Override = GrassOverrideMaterial.LoadSynchronous())
		{
			if (UMaterialInstanceDynamic* Dynamic = UMaterialInstanceDynamic::Create(Override, H))
			{
				if (!GrassTintPalette.IsEmpty())
				{
					Dynamic->SetVectorParameterValue(
						TEXT("Base Color"), GrassTintPalette[MaterialVariant % GrassTintPalette.Num()]);
				}
				H->SetMaterial(0, Dynamic);
			}
			else
			{
				H->SetMaterial(0, Override);
			}
		}
	}
	else if (Layer == EScatterLayer::AlienAccent && Mesh && Mesh->GetMaterial(0))
	{
		// The installed bulb/marsh-tail/leaf materials all inherit the same exposed "Base Color"
		// control. A MID keeps their opacity mask, normal map and wind while removing Earth tones.
		if (UMaterialInstanceDynamic* Dynamic = UMaterialInstanceDynamic::Create(Mesh->GetMaterial(0), H))
		{
			if (!AlienAccentTintPalette.IsEmpty())
			{
				Dynamic->SetVectorParameterValue(TEXT("Base Color"),
					AlienAccentTintPalette[MaterialVariant % AlienAccentTintPalette.Num()]);
			}
			Dynamic->SetScalarParameterValue(TEXT("Hue Variation"), 0.18f);
			Dynamic->SetScalarParameterValue(TEXT("Hue Shift"),
				0.16f + 0.14f * static_cast<float>(MaterialVariant % 5));
			Dynamic->SetScalarParameterValue(TEXT("Emissive Strength"),
				0.18f + 0.06f * static_cast<float>(MaterialVariant % 4));
			H->SetMaterial(0, Dynamic);
		}
	}
	H->RegisterComponent();
	Hisms.Add(H);
	return H;
}

void ARedFoliageField::ClearFoliage()
{
	TArray<UHierarchicalInstancedStaticMeshComponent*> Found;
	GetComponents(Found);
	for (UHierarchicalInstancedStaticMeshComponent* H : Found)
	{
		if (H)
		{
			H->DestroyComponent();
		}
	}
	Hisms.Empty();
}

void ARedFoliageField::Regenerate()
{
	UWorld* World = GetWorld();
	if (!World)
	{
		return;
	}
	if (bSuppressAllProceduralDressing)
	{
		World->GetTimerManager().ClearTimer(RegenerateRetryTimer);
		bWaitingForPlanetTerrain = false;
		ClearFoliage();
		UE_LOG(LogRedFoliage, Display,
			TEXT("RedFoliageField regeneration skipped: desert/ocean-only presentation is active."));
		return;
	}

	FVector PlanetCenter = FVector::ZeroVector;
	float DatumRadius = 0.f;
	float PeakRadius = 0.f;
	if (!RedGravity::FindMeshPlanet(World, PlanetCenter, DatumRadius, &PeakRadius)
		|| DatumRadius < 1000.f || PeakRadius <= DatumRadius)
	{
		ScheduleRegenerationRetry(TEXT("the CLM planet is not available yet"));
		return;
	}

	const AActor* PlanetActor = FindCLMPlanetActor(World, PlanetCenter);
	if (!HasLivePlanetCollision(
		World, this, PlanetActor, PlanetCenter, DatumRadius, PeakRadius, GetActorLocation()))
	{
		ScheduleRegenerationRetry(TEXT("the local streamed CLM chunk has no collision yet"));
		return;
	}

	ClearFoliage();
	FRandomStream Rng(Seed);
	bool bLoadedAnyMesh = false;
	bool bFoundTerrainHit = false;
	const int32 GrassInstances = ScatterSet(
		GrassMeshes, GrassCount, GrassMinHeight, GrassMaxHeight,
		/*override*/ true, /*collision*/ false, EScatterLayer::Grass, Rng,
		PlanetCenter, DatumRadius, PeakRadius, PlanetActor, bLoadedAnyMesh, bFoundTerrainHit);
	const int32 FlowerInstances = ScatterSet(
		FlowerMeshes, FlowerCount, 60.f, 165.f,
		/*override*/ false, /*collision*/ false, EScatterLayer::AlienAccent, Rng,
		PlanetCenter, DatumRadius, PeakRadius, PlanetActor, bLoadedAnyMesh, bFoundTerrainHit);
	const int32 RockInstances = ScatterSet(
		RockMeshes, RockCount, 120.f, 520.f,
		/*override*/ false, /*collision*/ true, EScatterLayer::DesertRock, Rng,
		PlanetCenter, DatumRadius, PeakRadius, PlanetActor, bLoadedAnyMesh, bFoundTerrainHit);
	const int32 CliffInstances = ScatterSet(
		CliffMeshes, CliffCount, 900.f, 2400.f,
		/*override*/ false, /*collision*/ true, EScatterLayer::DesertCliff, Rng,
		PlanetCenter, DatumRadius, PeakRadius, PlanetActor, bLoadedAnyMesh, bFoundTerrainHit);
	const int32 SnowInstances = ScatterSet(
		SnowMeshes, SnowAccentCount, 28.f, 75.f,
		/*override*/ false, /*collision*/ false, EScatterLayer::SnowAccent, Rng,
		PlanetCenter, DatumRadius, PeakRadius, PlanetActor, bLoadedAnyMesh, bFoundTerrainHit);
	const int32 Total = GrassInstances + FlowerInstances + RockInstances + CliffInstances + SnowInstances;

	if (!bLoadedAnyMesh)
	{
		ClearFoliage();
		World->GetTimerManager().ClearTimer(RegenerateRetryTimer);
		bWaitingForPlanetTerrain = false;
		UE_LOG(LogRedFoliage, Error,
			TEXT("RedFoliageField could not load any configured SoStylized foliage meshes."));
		return;
	}

	if (Total == 0)
	{
		ClearFoliage();
		if (!bFoundTerrainHit)
		{
			ScheduleRegenerationRetry(TEXT("streamed CLM chunk collision is not ready across the field"));
		}
		else
		{
			World->GetTimerManager().ClearTimer(RegenerateRetryTimer);
			bWaitingForPlanetTerrain = false;
			UE_LOG(LogRedFoliage, Warning,
				TEXT("RedFoliageField found PlanetGen terrain, but its configured filters produced zero instances."));
		}
		return;
	}

	World->GetTimerManager().ClearTimer(RegenerateRetryTimer);
	bWaitingForPlanetTerrain = false;
	UE_LOG(LogRedFoliage, Log,
		TEXT("RedFoliageField regenerated: total=%d grass=%d alien=%d rocks=%d cliffs=%d snow=%d across %d HISMs."),
		Total, GrassInstances, FlowerInstances, RockInstances, CliffInstances, SnowInstances, Hisms.Num());
}

int32 ARedFoliageField::ScatterSet(const TArray<TSoftObjectPtr<UStaticMesh>>& Meshes, int32 Count,
	float MinH, float MaxH, bool bOverrideMaterial, bool bEnableCollision,
	EScatterLayer Layer, FRandomStream& Rng,
	const FVector& PlanetCenter, float DatumRadius, float PeakRadius,
	const AActor* PlanetActor, bool& bOutLoadedAnyMesh, bool& bOutFoundTerrainHit)
{
	TArray<UHierarchicalInstancedStaticMeshComponent*> Comps;
	TArray<float> BaseHeights;
	TArray<float> BottomBelow;
	for (const TSoftObjectPtr<UStaticMesh>& Soft : Meshes)
	{
		UStaticMesh* M = Soft.LoadSynchronous();
		if (!M)
		{
			continue;
		}
		Comps.Add(MakeHism(M, bOverrideMaterial, bEnableCollision, Layer, Comps.Num()));
		const FBoxSphereBounds B = M->GetBounds();
		BaseHeights.Add(FMath::Max(1.f, B.BoxExtent.Z * 2.f));
		BottomBelow.Add(FMath::Max(0.f, B.BoxExtent.Z - B.Origin.Z));
	}
	if (Comps.Num() == 0)
	{
		return 0;
	}
	bOutLoadedAnyMesh = true;

	const FVector Origin = GetActorLocation();
	FVector Up0 = (Origin - PlanetCenter).GetSafeNormal();
	if (Up0.IsNearlyZero())
	{
		Up0 = FVector::UpVector;
	}
	const FVector Ref = FMath::Abs(Up0.Z) > 0.9f ? FVector(1, 0, 0) : FVector(0, 0, 1);
	const FVector Fwd = (Ref - Up0 * FVector::DotProduct(Ref, Up0)).GetSafeNormal();
	const FVector Side = FVector::CrossProduct(Up0, Fwd).GetSafeNormal();

	UWorld* W = GetWorld();
	FCollisionObjectQueryParams SurfaceObjectTypes;
	SurfaceObjectTypes.AddObjectTypesToQuery(ECC_WorldStatic);
	SurfaceObjectTypes.AddObjectTypesToQuery(ECC_WorldDynamic);
	FCollisionQueryParams SurfaceQuery(SCENE_QUERY_STAT(RedFoliageSurfaceTrace), false, this);
	TMap<const UPrimitiveComponent*, bool> TerrainComponentCache;
	TArray<FHitResult> Hits;
	Hits.Reserve(8);
	int32 AddedInstances = 0;
	// Each layer owns deterministic ecology colonies instead of covering the entire sphere. Samples
	// below are drawn from irregular, differently weighted ellipses with macro voids between them;
	// this intentionally leaves large areas empty instead of producing an even procedural lawn.
	float LayerRadius = Radius;
	FVector PatchOffset = FVector::ZeroVector;
	float MinimumUpDot = 0.55f;
	float MinimumNormalizedHeight = 0.f;
	float MaximumNormalizedHeight = 1.f;
	bool bRequirePolarOrHigh = false;
	switch (Layer)
	{
	case EScatterLayer::Grass:
		// Several overlapping ground-cover meadows near deployment, separated by bare sand lanes.
		LayerRadius = Radius * 0.18f;
		PatchOffset = Fwd * (Radius * 0.10f);
		MinimumUpDot = FMath::Cos(FMath::DegreesToRadians(32.f));
		MaximumNormalizedHeight = 0.72f;
		break;
	case EScatterLayer::AlienAccent:
		LayerRadius = Radius * 0.38f;
		PatchOffset = Fwd * (Radius * 0.24f) + Side * (Radius * 0.08f);
		MinimumUpDot = FMath::Cos(FMath::DegreesToRadians(35.f));
		MaximumNormalizedHeight = 0.78f;
		break;
	case EScatterLayer::DesertRock:
		LayerRadius = Radius * 0.82f;
		PatchOffset = -Fwd * (Radius * 0.12f);
		MinimumUpDot = FMath::Cos(FMath::DegreesToRadians(58.f));
		break;
	case EScatterLayer::DesertCliff:
		LayerRadius = Radius * 0.74f;
		PatchOffset = Side * (Radius * 0.22f) - Fwd * (Radius * 0.10f);
		MinimumUpDot = FMath::Cos(FMath::DegreesToRadians(30.f));
		MinimumNormalizedHeight = 0.12f;
		break;
	case EScatterLayer::SnowAccent:
		LayerRadius = Radius * 0.48f;
		PatchOffset = -Side * (Radius * 0.18f);
		MinimumUpDot = FMath::Cos(FMath::DegreesToRadians(38.f));
		bRequirePolarOrHigh = true;
		break;
	}

	struct FLocalColony
	{
		FVector2D Center = FVector2D::ZeroVector;
		FVector2D MajorAxis = FVector2D(1.f, 0.f);
		FVector2D MinorAxis = FVector2D(0.f, 1.f);
		int32 PrimarySpecies = 0;
		float Weight = 1.f;
		float HeightScale = 1.f;
	};

	int32 ColonyCount = 8;
	float MinColonyRadius = LayerRadius * 0.045f;
	float MaxColonyRadius = LayerRadius * 0.16f;
	float MinAspect = 0.30f;
	float MacroVoidThreshold = -0.55f;
	float SecondarySpeciesChance = 0.16f;
	switch (Layer)
	{
	case EScatterLayer::Grass:
		ColonyCount = 17;
		MinColonyRadius = 550.f;
		MaxColonyRadius = 1850.f;
		MinAspect = 0.24f;
		MacroVoidThreshold = -0.32f;
		SecondarySpeciesChance = 0.20f;
		break;
	case EScatterLayer::AlienAccent:
		ColonyCount = 12;
		MinColonyRadius = 650.f;
		MaxColonyRadius = 2400.f;
		MinAspect = 0.28f;
		MacroVoidThreshold = -0.02f;
		SecondarySpeciesChance = 0.10f;
		break;
	case EScatterLayer::DesertRock:
		ColonyCount = 9;
		MinColonyRadius = 900.f;
		MaxColonyRadius = 4300.f;
		MinAspect = 0.20f;
		MacroVoidThreshold = -0.72f;
		SecondarySpeciesChance = 0.24f;
		break;
	case EScatterLayer::DesertCliff:
		ColonyCount = 4;
		MinColonyRadius = 1100.f;
		MaxColonyRadius = 3800.f;
		MinAspect = 0.13f; // ridge-like formations, not isolated points on a grid
		MacroVoidThreshold = -1.25f;
		SecondarySpeciesChance = 0.18f;
		break;
	case EScatterLayer::SnowAccent:
		ColonyCount = 8;
		MinColonyRadius = 700.f;
		MaxColonyRadius = 2800.f;
		MinAspect = 0.25f;
		MacroVoidThreshold = -0.20f;
		SecondarySpeciesChance = 0.18f;
		break;
	}

	auto PickColonySpecies = [&]() -> int32
	{
		if (Comps.Num() <= 1)
		{
			return 0;
		}

		// Ground cover and rocks favour a recognizable dominant silhouette. Alien accents are
		// biased toward the bulb families but each colony can still be marsh-tail/cactus/leaf.
		float BiasPower = 1.f;
		switch (Layer)
		{
		case EScatterLayer::Grass:       BiasPower = 1.65f; break;
		case EScatterLayer::AlienAccent: BiasPower = 1.35f; break;
		case EScatterLayer::DesertRock:  BiasPower = 1.45f; break;
		default:                         BiasPower = 1.f; break;
		}
		return FMath::Clamp(
			FMath::FloorToInt(FMath::Pow(Rng.FRand(), BiasPower) * Comps.Num()),
			0, Comps.Num() - 1);
	};

	TArray<FLocalColony> Colonies;
	Colonies.Reserve(ColonyCount);
	float ColonyWeightTotal = 0.f;
	for (int32 ColonyIndex = 0; ColonyIndex < ColonyCount; ++ColonyIndex)
	{
		const float CenterAngle = Rng.FRandRange(0.f, 2.f * PI);
		// Keep centres away from a common radius and nudge every other colony inward, which avoids
		// the procedural "ring" that uniformly sampled patch centres otherwise create.
		float CenterDistance = LayerRadius * FMath::Sqrt(Rng.FRandRange(0.015f, 0.82f));
		if ((ColonyIndex & 1) == 0)
		{
			CenterDistance *= Rng.FRandRange(0.42f, 0.78f);
		}

		const float Orientation = Rng.FRandRange(0.f, 2.f * PI);
		const FVector2D AxisDirection(FMath::Cos(Orientation), FMath::Sin(Orientation));
		const FVector2D AxisPerpendicular(-AxisDirection.Y, AxisDirection.X);
		const float MajorRadius = Rng.FRandRange(MinColonyRadius, MaxColonyRadius);
		const float Aspect = Rng.FRandRange(MinAspect, 0.78f);

		FLocalColony& Colony = Colonies.AddDefaulted_GetRef();
		Colony.Center = FVector2D(FMath::Cos(CenterAngle), FMath::Sin(CenterAngle)) * CenterDistance;
		Colony.MajorAxis = AxisDirection * MajorRadius;
		Colony.MinorAxis = AxisPerpendicular * MajorRadius * Aspect;
		Colony.PrimarySpecies = PickColonySpecies();
		Colony.Weight = Rng.FRandRange(0.35f, 1.75f);
		Colony.HeightScale = Rng.FRandRange(0.72f, 1.28f);
		ColonyWeightTotal += Colony.Weight;
	}

	auto PickColony = [&]() -> const FLocalColony&
	{
		float Ticket = Rng.FRandRange(0.f, ColonyWeightTotal);
		for (const FLocalColony& Colony : Colonies)
		{
			Ticket -= Colony.Weight;
			if (Ticket <= 0.f)
			{
				return Colony;
			}
		}
		return Colonies.Last();
	};

	for (int32 i = 0; i < Count; ++i)
	{
		const FLocalColony& Colony = PickColony();
		// Box-Muller gives dense cores and ragged sparse edges. Clamp the extreme tail so a colony
		// cannot leak isolated plants far into an intended empty area.
		const float BoxMullerRadius = FMath::Sqrt(-2.f * FMath::Loge(FMath::Max(0.0001f, Rng.FRand())));
		const float BoxMullerAngle = Rng.FRandRange(0.f, 2.f * PI);
		FVector2D Gaussian(FMath::Cos(BoxMullerAngle) * BoxMullerRadius,
			FMath::Sin(BoxMullerAngle) * BoxMullerRadius);
		if (Gaussian.SizeSquared() > FMath::Square(2.35f))
		{
			Gaussian = Gaussian.GetSafeNormal() * 2.35f;
		}
		const FVector2D LocalOffset = Colony.Center
			+ Colony.MajorAxis * Gaussian.X + Colony.MinorAxis * Gaussian.Y;
		if (LocalOffset.SizeSquared() > FMath::Square(LayerRadius))
		{
			continue;
		}

		// Low-frequency deterministic voids cut broad bare-sand corridors through even overlapping
		// colonies. This is deliberately independent from per-instance random dropout.
		const float MacroScale = FMath::Max(1800.f, LayerRadius * 0.22f);
		const float MacroField =
			FMath::Sin((LocalOffset.X + Seed * 31.7f) / MacroScale)
			+ 0.72f * FMath::Cos((LocalOffset.Y - Seed * 19.3f) / (MacroScale * 0.83f))
			+ 0.38f * FMath::Sin((LocalOffset.X + LocalOffset.Y) / (MacroScale * 0.47f));
		if (MacroField < MacroVoidThreshold)
		{
			continue;
		}

		const FVector P = Origin + PatchOffset
			+ Side * LocalOffset.X + Fwd * LocalOffset.Y;
		const FVector Dir = (P - PlanetCenter).GetSafeNormal();
		if (Dir.IsNearlyZero())
		{
			continue;
		}

		const FVector Start = PlanetCenter + Dir * (PeakRadius + 5000.f);
		const FVector End = PlanetCenter + Dir * DatumRadius;
		Hits.Reset();
		if (!W->LineTraceMultiByObjectType(Hits, Start, End, SurfaceObjectTypes, SurfaceQuery))
		{
			continue;
		}

		// Continue past ships and props until the multi trace reaches a live PlanetGen chunk.
		const FHitResult* SurfaceHit = nullptr;
		for (const FHitResult& Hit : Hits)
		{
			if (!Hit.bBlockingHit)
			{
				continue;
			}

			const float HitRadius = FVector::Distance(Hit.ImpactPoint, PlanetCenter);
			if (HitRadius < DatumRadius || HitRadius > PeakRadius + 5000.f)
			{
				continue;
			}

			const UPrimitiveComponent* HitComponent = Hit.GetComponent();
			bool bIsPlanetTerrain = false;
			if (const bool* Cached = TerrainComponentCache.Find(HitComponent))
			{
				bIsPlanetTerrain = *Cached;
			}
			else
			{
				bIsPlanetTerrain = IsLivePlanetTerrainComponent(
					Hit, PlanetActor, PlanetCenter, PeakRadius);
				TerrainComponentCache.Add(HitComponent, bIsPlanetTerrain);
			}

			if (bIsPlanetTerrain)
			{
				SurfaceHit = &Hit;
				break;
			}
		}
		if (!SurfaceHit)
		{
			continue;
		}
		bOutFoundTerrainHit = true;

		const FVector Ip = SurfaceHit->ImpactPoint;
		if (SeaLevelRadius > 0.f && (Ip - PlanetCenter).Size() < SeaLevelRadius)
		{
			continue;
		}
		const FVector Up = (Ip - PlanetCenter).GetSafeNormal();
		const FVector SurfaceNormal = SurfaceHit->ImpactNormal.GetSafeNormal();
		const float SurfaceUpDot = FVector::DotProduct(SurfaceNormal, Up);
		const float HeightRange = FMath::Max(1.f, PeakRadius - DatumRadius);
		const float NormalizedHeight = FMath::Clamp(
			((Ip - PlanetCenter).Size() - DatumRadius) / HeightRange, 0.f, 1.f);
		const float AbsoluteLatitudeDegrees = FMath::RadiansToDegrees(
			FMath::Asin(FMath::Clamp(FMath::Abs(Up.Z), 0.f, 1.f)));
		if (SurfaceUpDot < MinimumUpDot
			|| NormalizedHeight < MinimumNormalizedHeight
			|| NormalizedHeight > MaximumNormalizedHeight
			|| (bRequirePolarOrHigh
				&& NormalizedHeight < 0.58f && AbsoluteLatitudeDegrees < 55.f))
		{
			continue;
		}
		const FVector PlantUp = FVector::DotProduct(SurfaceNormal, Up) > 0.f
			? SurfaceNormal : Up;
		const float Ya = Rng.FRandRange(0.f, 2.f * PI);
		FVector F2 = (Fwd - PlantUp * FVector::DotProduct(Fwd, PlantUp)).GetSafeNormal();
		const FVector Cr = FVector::CrossProduct(PlantUp, F2);
		F2 = (F2 * FMath::Cos(Ya) + Cr * FMath::Sin(Ya)).GetSafeNormal();
		const FRotator Rot = FRotationMatrix::MakeFromZX(PlantUp, F2).Rotator();

		int32 Mi = Colony.PrimarySpecies;
		if (Comps.Num() > 1 && Rng.FRand() < SecondarySpeciesChance)
		{
			// A nearby variant breaks repetition without destroying the colony's species identity.
			Mi = (Mi + (Rng.FRand() < 0.78f ? 1 : Rng.RandRange(1, Comps.Num() - 1))) % Comps.Num();
		}
		const float HeightAlpha = FMath::Pow(Rng.FRand(),
			Layer == EScatterLayer::Grass ? 1.55f : 1.15f);
		const float H = FMath::Lerp(MinH, MaxH, HeightAlpha) * Colony.HeightScale;
		const float Sc = H / BaseHeights[Mi];
		const float WidthJit = Rng.FRandRange(0.70f, 1.32f);
		const float DepthJit = Rng.FRandRange(0.78f, 1.22f);

		const float Lift = BottomBelow[Mi] * Sc - Rng.FRandRange(1.5f, 5.5f);
		FTransform X;
		X.SetLocation(Ip + PlantUp * Lift);
		X.SetRotation(Rot.Quaternion());
		X.SetScale3D(FVector(Sc * WidthJit, Sc * DepthJit, Sc));
		Comps[Mi]->AddInstance(X, /*bWorldSpace*/ true);
		++AddedInstances;
	}

	return AddedInstances;
}
