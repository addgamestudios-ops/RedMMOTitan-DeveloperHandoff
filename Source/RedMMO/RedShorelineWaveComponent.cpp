#include "RedShorelineWaveComponent.h"

#include "RedPlanetPresentationTuning.h"
#include "RedPlanetGenCompat.h"

#include "EngineUtils.h"
#include "GameFramework/Pawn.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Materials/MaterialInterface.h"
#include "ProceduralMeshComponent.h"

#include "CLMPlanet.h"

DEFINE_LOG_CATEGORY_STATIC(LogRedShorelineWaves, Log, All);

namespace
{
constexpr int32 ShoreGridResolution = 33;
constexpr float ShorePatchHalfExtent = 15000.f; // 150 m around the local player at ~9.4 m cells.
constexpr float ShoreRibbonWidth = 650.f;       // 6.5 m of animated crest/foam into the water.
constexpr float ShoreSurfaceLift = 8.f;         // Avoid z-fighting with the base water sphere.
constexpr float MaxRadialDistanceFromWater = 65000.f;

struct FShoreSample
{
	FVector2D Plane = FVector2D::ZeroVector;
	float SignedHeight = 0.f;
};

FVector BuildSphereTangent(const FVector& Normal)
{
	FVector Tangent(-Normal.Y, Normal.X, 0.f);
	if (!Tangent.Normalize())
	{
		Tangent = FVector::CrossProduct(FVector::ForwardVector, Normal).GetSafeNormal();
	}
	if (Tangent.IsNearlyZero())
	{
		Tangent = FVector::RightVector;
	}
	return Tangent;
}

FVector BuildSphereTangentFromUV(const FVector2D& UV)
{
	const float Theta = 2.f * PI * UV.X;
	return FVector(-FMath::Sin(Theta), FMath::Cos(Theta), 0.f);
}
}

URedShorelineWaveComponent::URedShorelineWaveComponent()
{
	PrimaryComponentTick.bCanEverTick = true;
	PrimaryComponentTick.bStartWithTickEnabled = true;
	PrimaryComponentTick.TickInterval = 1.0f;
	SetIsReplicatedByDefault(false);
}

void URedShorelineWaveComponent::BeginPlay()
{
	Super::BeginPlay();
}

bool URedShorelineWaveComponent::EnsureLocalResources()
{
	if (WaveMesh && WaveMaterial)
	{
		return true;
	}
	UWorld* World = GetWorld();
	AActor* Owner = GetOwner();
	const APawn* OwnerPawn = Cast<APawn>(Owner);
	if (!World || World->GetNetMode() == NM_DedicatedServer || !Owner || !OwnerPawn
		|| !OwnerPawn->IsLocallyControlled() || !Owner->GetRootComponent())
	{
		return false;
	}

	if (!WaveMesh)
	{
		WaveMesh = NewObject<UProceduralMeshComponent>(
			Owner, TEXT("RedSoStylizedShorelineCrests"));
		if (!WaveMesh)
		{
			return false;
		}
		Owner->AddInstanceComponent(WaveMesh);
		WaveMesh->SetupAttachment(Owner->GetRootComponent());
		WaveMesh->SetAbsolute(true, true, true);
		WaveMesh->SetMobility(EComponentMobility::Movable);
		WaveMesh->SetCollisionEnabled(ECollisionEnabled::NoCollision);
		WaveMesh->SetGenerateOverlapEvents(false);
		WaveMesh->SetCastShadow(false);
		WaveMesh->SetReceivesDecals(false);
		WaveMesh->bUseAsyncCooking = false;
		WaveMesh->RegisterComponent();
		WaveMesh->SetHiddenInGame(true, true);
		WaveMesh->SetVisibility(false, true);
	}

	if (!WaveMaterial)
	{
		if (UMaterialInterface* CrestMaterial = LoadObject<UMaterialInterface>(nullptr,
			TEXT("/Game/SoStylized/Environment/Water/Materials/MI_WaterWaves.MI_WaterWaves")))
		{
			WaveMaterial = UMaterialInstanceDynamic::Create(CrestMaterial, this);
			WaveMesh->SetMaterial(0, WaveMaterial ? WaveMaterial.Get() : CrestMaterial);
		}
	}
	return WaveMesh && WaveMaterial;
}

void URedShorelineWaveComponent::EndPlay(const EEndPlayReason::Type EndPlayReason)
{
	if (WaveMesh)
	{
		WaveMesh->DestroyComponent();
		WaveMesh = nullptr;
	}
	Super::EndPlay(EndPlayReason);
}

void URedShorelineWaveComponent::TickComponent(float DeltaTime, ELevelTick TickType,
	FActorComponentTickFunction* ThisTickFunction)
{
	Super::TickComponent(DeltaTime, TickType, ThisTickFunction);

	const APawn* OwnerPawn = Cast<APawn>(GetOwner());
	if (!OwnerPawn || !OwnerPawn->IsLocallyControlled() || OwnerPawn->IsHidden())
	{
		HideRibbon();
		return;
	}

	UWorld* World = GetWorld();
	if (!World)
	{
		return;
	}
	if (!EnsureLocalResources())
	{
		return;
	}
	if (!CachedPlanet.IsValid()
		&& World->GetTimeSeconds() >= NextPlanetResolveTime)
	{
		NextPlanetResolveTime = World->GetTimeSeconds() + 1.f;
		ResolvePlanet();
	}
	if (!CachedPlanet.IsValid())
	{
		HideRibbon();
		return;
	}
	if (World->GetTimeSeconds() >= NextTangentAuditTime)
	{
		NextTangentAuditTime = World->GetTimeSeconds() + 10.f;
		RepairWaterSphereTangents();
	}
	if (!CachedPlanet->bEnableWater)
	{
		HideRibbon();
		return;
	}

	// The disposable T04 map uses WorldGen's radial ocean for a global-water A/B.
	// SoStylized's contour ribbons are authored for the flat demo water and currently
	// turn into detached, blinking white fragments on the 50 km spherical shoreline.
	// Keep the water-sphere tangent repair above, but suppress only those diagnostic
	// ribbons until a radial-safe shoreline treatment is validated on the real GPU.
	if (RedPlanetPresentationTuning::IsNightWaterT04MapName(World->GetMapName()))
	{
		HideRibbon();
		if (!bLoggedNightWaterT04Suppression)
		{
			bLoggedNightWaterT04Suppression = true;
			UE_LOG(LogRedShorelineWaves, Display,
				TEXT("NightWater_T04: suppressed incompatible flat-demo shoreline crest ribbons; retained radial water tangent repair"));
		}
		return;
	}

	const FVector PlanetCenter = CachedPlanet->GetActorLocation();
	const FVector OwnerLocation = OwnerPawn->GetActorLocation();
	const FVector Direction = (OwnerLocation - PlanetCenter).GetSafeNormal();
	const bool bMovedEnough = FVector::DistSquared(OwnerLocation, LastRibbonOwnerLocation)
		>= FMath::Square(2500.f);
	const bool bTurnedAroundPlanet = LastRibbonDirection.IsNearlyZero()
		|| FVector::DotProduct(Direction, LastRibbonDirection) < 0.9995f;
	if (bMovedEnough || bTurnedAroundPlanet)
	{
		RebuildShorelineRibbon();
	}
}

void URedShorelineWaveComponent::ResolvePlanet()
{
	CachedPlanet.Reset();
	UWorld* World = GetWorld();
	if (!World)
	{
		return;
	}

	const FVector OwnerLocation = GetOwner() ? GetOwner()->GetActorLocation() : FVector::ZeroVector;
	float BestSurfaceDistanceCm = TNumericLimits<float>::Max();
	for (TActorIterator<ACLMPlanet> It(World); It; ++It)
	{
		ACLMPlanet* Planet = *It;
		if (!IsValid(Planet))
		{
			continue;
		}
		const float SurfaceDistanceCm = FMath::Abs(
			FVector::Distance(OwnerLocation, Planet->GetActorLocation()) - Planet->PlanetRadius);
		if (SurfaceDistanceCm < BestSurfaceDistanceCm)
		{
			BestSurfaceDistanceCm = SurfaceDistanceCm;
			CachedPlanet = Planet;
		}
	}
}

void URedShorelineWaveComponent::RepairWaterSphereTangents()
{
	ACLMPlanet* Planet = CachedPlanet.Get();
	if (!Planet)
	{
		return;
	}

	TArray<UProceduralMeshComponent*> ProceduralMeshes;
	Planet->GetComponents<UProceduralMeshComponent>(ProceduralMeshes);
	for (UProceduralMeshComponent* WaterSphere : ProceduralMeshes)
	{
		if (!WaterSphere || !WaterSphere->GetName().Contains(TEXT("WaterSphere")))
		{
			continue;
		}
		const FProcMeshSection* Section = WaterSphere->GetProcMeshSection(0);
		if (!Section || Section->ProcVertexBuffer.Num() < 16)
		{
			continue;
		}

		bool bNeedsRepair = Section->ProcVertexBuffer.Num() != LastRepairedWaterVertexCount;
		if (!bNeedsRepair)
		{
			for (const FProcMeshVertex& Vertex : Section->ProcVertexBuffer)
			{
				const FVector Normal = Vertex.Position.GetSafeNormal();
				if (FMath::Abs(Normal.Z) < 0.9f)
				{
					bNeedsRepair = FVector::DotProduct(Vertex.Tangent.TangentX.GetSafeNormal(),
						BuildSphereTangentFromUV(Vertex.UV0)) < 0.98f
						|| !Vertex.Tangent.bFlipTangentY;
					break;
				}
			}
		}
		if (!bNeedsRepair)
		{
			continue;
		}

		TArray<FVector> Vertices;
		TArray<FVector> Normals;
		TArray<FVector2D> UV0;
		TArray<FColor> Colors;
		TArray<FProcMeshTangent> Tangents;
		const int32 VertexCount = Section->ProcVertexBuffer.Num();
		Vertices.Reserve(VertexCount);
		Normals.Reserve(VertexCount);
		UV0.Reserve(VertexCount);
		Colors.Reserve(VertexCount);
		Tangents.Reserve(VertexCount);
		for (const FProcMeshVertex& Vertex : Section->ProcVertexBuffer)
		{
			const FVector Normal = Vertex.Position.GetSafeNormal();
			Vertices.Add(Vertex.Position);
			Normals.Add(Normal);
			UV0.Add(Vertex.UV0);
			Colors.Add(Vertex.Color);
			Tangents.Emplace(BuildSphereTangentFromUV(Vertex.UV0), true);
		}
		WaterSphere->UpdateMeshSection(0, Vertices, Normals, UV0, Colors, Tangents);
		WaterSphere->MarkRenderStateDirty();
		LastRepairedWaterVertexCount = VertexCount;
		UE_LOG(LogRedShorelineWaves, Display,
			TEXT("Repaired spherical SoStylized water tangent basis on %s (%d vertices)"),
			*GetNameSafe(Planet), VertexCount);
	}
}

float URedShorelineWaveComponent::SampleSignedShoreHeight(
	const FVector& SphereDirection) const
{
	const ACLMPlanet* Planet = CachedPlanet.Get();
	if (!Planet)
	{
		return 100000.f;
	}

	float HeightCm = 0.f;
	if (!RedPlanetGenCompat::SampleResolvedSurface(Planet, SphereDirection, HeightCm))
	{
		return 100000.f;
	}
	const float SeaHeightCm = Planet->MinHeight
		+ (Planet->MaxHeight - Planet->MinHeight) * Planet->SeaLevel;
	return HeightCm - SeaHeightCm;
}

void URedShorelineWaveComponent::RebuildShorelineRibbon()
{
	APawn* OwnerPawn = Cast<APawn>(GetOwner());
	ACLMPlanet* Planet = CachedPlanet.Get();
	if (!OwnerPawn || !OwnerPawn->IsLocallyControlled() || !Planet
		|| !WaveMesh || !WaveMaterial)
	{
		HideRibbon();
		return;
	}

	const FVector PlanetCenter = Planet->GetActorLocation();
	const FVector OwnerLocation = OwnerPawn->GetActorLocation();
	const float SeaHeight = Planet->MinHeight
		+ (Planet->MaxHeight - Planet->MinHeight) * Planet->SeaLevel;
	const float WaterRadius = Planet->PlanetRadius + SeaHeight;
	const FVector CenterDirection = (OwnerLocation - PlanetCenter).GetSafeNormal();
	if (CenterDirection.IsNearlyZero()
		|| FMath::Abs(FVector::Distance(OwnerLocation, PlanetCenter) - WaterRadius)
			> MaxRadialDistanceFromWater)
	{
		HideRibbon();
		return;
	}

	FVector AxisX = FVector::VectorPlaneProject(OwnerPawn->GetActorForwardVector(),
		CenterDirection).GetSafeNormal();
	if (AxisX.IsNearlyZero())
	{
		AxisX = BuildSphereTangent(CenterDirection);
	}
	const FVector AxisY = FVector::CrossProduct(CenterDirection, AxisX).GetSafeNormal();
	const float Step = (ShorePatchHalfExtent * 2.f) / (ShoreGridResolution - 1);

	TArray<FShoreSample> Grid;
	Grid.SetNum(ShoreGridResolution * ShoreGridResolution);
	auto GridIndex = [](const int32 X, const int32 Y)
	{
		return Y * ShoreGridResolution + X;
	};
	auto PlaneToDirection = [&](const FVector2D& Plane)
	{
		return (CenterDirection * WaterRadius + AxisX * Plane.X + AxisY * Plane.Y)
			.GetSafeNormal();
	};
	for (int32 Y = 0; Y < ShoreGridResolution; ++Y)
	{
		for (int32 X = 0; X < ShoreGridResolution; ++X)
		{
			FShoreSample& Sample = Grid[GridIndex(X, Y)];
			Sample.Plane = FVector2D(-ShorePatchHalfExtent + X * Step,
				-ShorePatchHalfExtent + Y * Step);
			Sample.SignedHeight = SampleSignedShoreHeight(
				PlaneToDirection(Sample.Plane));
		}
	}

	TArray<FVector> Vertices;
	TArray<int32> Triangles;
	TArray<FVector> Normals;
	TArray<FVector2D> UV0;
	TArray<FColor> Colors;
	TArray<FProcMeshTangent> Tangents;
	auto AddOrientedTriangle = [&](const int32 A, const int32 B, const int32 C)
	{
		const FVector FaceNormal = FVector::CrossProduct(
			Vertices[B] - Vertices[A], Vertices[C] - Vertices[A]);
		const FVector DesiredNormal = (Normals[A] + Normals[B] + Normals[C]).GetSafeNormal();
		Triangles.Add(A);
		// Unreal's default front face is clockwise. A right-handed cross that points along
		// the desired outward normal is counter-clockwise when viewed from above, so emit
		// the opposite winding for the one-sided SoStylized wave material.
		if (FVector::DotProduct(FaceNormal, DesiredNormal) < 0.f)
		{
			Triangles.Add(B); Triangles.Add(C);
		}
		else
		{
			Triangles.Add(C); Triangles.Add(B);
		}
	};
	auto AddRibbonSegment = [&](const FVector2D& P0, const FVector2D& P1)
	{
		const float SegmentLength = FVector2D::Distance(P0, P1);
		if (SegmentLength < 40.f)
		{
			return;
		}
		const FVector2D Along = (P1 - P0).GetSafeNormal();
		FVector2D WaterDirection(-Along.Y, Along.X);
		const FVector2D Midpoint = (P0 + P1) * 0.5f;
		const float ProbeDistance = FMath::Min(ShoreRibbonWidth * 0.5f, Step * 0.35f);
		const float LeftHeight = SampleSignedShoreHeight(
			PlaneToDirection(Midpoint + WaterDirection * ProbeDistance));
		const float RightHeight = SampleSignedShoreHeight(
			PlaneToDirection(Midpoint - WaterDirection * ProbeDistance));
		if (RightHeight < LeftHeight)
		{
			WaterDirection *= -1.f;
		}
		const FVector2D WaterP0 = P0 + WaterDirection * ShoreRibbonWidth;
		const FVector2D WaterP1 = P1 + WaterDirection * ShoreRibbonWidth;
		const FVector2D PlanePoints[] = {P0, WaterP0, P1, WaterP1};
		const int32 Base = Vertices.Num();
		const FVector SegmentTangent = (AxisX * (P1.X - P0.X)
			+ AxisY * (P1.Y - P0.Y)).GetSafeNormal();
		for (int32 Index = 0; Index < 4; ++Index)
		{
			const FVector Direction = PlaneToDirection(PlanePoints[Index]);
			Vertices.Add(Direction * (WaterRadius + ShoreSurfaceLift));
			Normals.Add(Direction);
			Tangents.Emplace(SegmentTangent, false);
			Colors.Add(FColor::White);
		}
		const float UEnd = FMath::Max(0.25f, SegmentLength / 900.f);
		UV0.Add(FVector2D(0.f, 0.f));
		UV0.Add(FVector2D(0.f, 1.f));
		UV0.Add(FVector2D(UEnd, 0.f));
		UV0.Add(FVector2D(UEnd, 1.f));
		AddOrientedTriangle(Base + 0, Base + 1, Base + 2);
		AddOrientedTriangle(Base + 2, Base + 1, Base + 3);
	};

	for (int32 Y = 0; Y < ShoreGridResolution - 1; ++Y)
	{
		for (int32 X = 0; X < ShoreGridResolution - 1; ++X)
		{
			const FShoreSample& S00 = Grid[GridIndex(X, Y)];
			const FShoreSample& S10 = Grid[GridIndex(X + 1, Y)];
			const FShoreSample& S11 = Grid[GridIndex(X + 1, Y + 1)];
			const FShoreSample& S01 = Grid[GridIndex(X, Y + 1)];
			TArray<FVector2D, TInlineAllocator<4>> Crossings;
			auto AddCrossing = [&Crossings](const FShoreSample& A, const FShoreSample& B)
			{
				const bool bAWater = A.SignedHeight <= 0.f;
				const bool bBWater = B.SignedHeight <= 0.f;
				if (bAWater == bBWater)
				{
					return;
				}
				const float Denominator = A.SignedHeight - B.SignedHeight;
				const float T = FMath::IsNearlyZero(Denominator) ? 0.5f
					: FMath::Clamp(A.SignedHeight / Denominator, 0.f, 1.f);
				Crossings.Add(FMath::Lerp(A.Plane, B.Plane, T));
			};
			AddCrossing(S00, S10);
			AddCrossing(S10, S11);
			AddCrossing(S11, S01);
			AddCrossing(S01, S00);
			if (Crossings.Num() < 2)
			{
				continue;
			}

			if (Crossings.Num() == 2)
			{
				AddRibbonSegment(Crossings[0], Crossings[1]);
			}
			else if (Crossings.Num() == 4)
			{
				const bool bCenterWater =
					(S00.SignedHeight + S10.SignedHeight + S11.SignedHeight
						+ S01.SignedHeight) * 0.25f <= 0.f;
				const bool bS00Water = S00.SignedHeight <= 0.f;
				if (bCenterWater == bS00Water)
				{
					AddRibbonSegment(Crossings[0], Crossings[1]);
					AddRibbonSegment(Crossings[2], Crossings[3]);
				}
				else
				{
					AddRibbonSegment(Crossings[0], Crossings[3]);
					AddRibbonSegment(Crossings[1], Crossings[2]);
				}
			}
		}
	}

	LastRibbonDirection = CenterDirection;
	LastRibbonOwnerLocation = OwnerLocation;
	if (Vertices.IsEmpty())
	{
		HideRibbon();
		return;
	}

	WaveMesh->SetWorldTransform(FTransform(FQuat::Identity, PlanetCenter, FVector::OneVector));
	WaveMesh->CreateMeshSection(0, Vertices, Triangles, Normals, UV0, Colors, Tangents, false);
	WaveMesh->SetMaterial(0, WaveMaterial);
	WaveMesh->SetHiddenInGame(false, true);
	WaveMesh->SetVisibility(true, true);
	WaveMesh->MarkRenderStateDirty();
	UE_LOG(LogRedShorelineWaves, Verbose,
		TEXT("Built %d local SoStylized shoreline crest segments near %s"),
		Vertices.Num() / 4, *GetNameSafe(OwnerPawn));
}

void URedShorelineWaveComponent::HideRibbon()
{
	// Force a rebuild when a hidden/local-control/empty-state condition clears, even if
	// the pawn returns at the same transform. Otherwise the movement cache can keep a
	// valid existing mesh hidden or prevent an empty shoreline patch from retrying.
	LastRibbonDirection = FVector::ZeroVector;
	LastRibbonOwnerLocation = FVector(FLT_MAX);
	if (WaveMesh)
	{
		WaveMesh->SetHiddenInGame(true, true);
		WaveMesh->SetVisibility(false, true);
	}
}
