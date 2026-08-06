#include "RedGravityBodies.h"

#include "Engine/World.h"
#include "EngineUtils.h"
#include "GameFramework/Actor.h"
#include "RedSpaceScenery.h"
#include "UObject/UnrealType.h"

namespace
{
	struct FMeshPlanetCacheEntry
	{
		TWeakObjectPtr<AActor> Planet;
		bool bUniquePlanetValidated = false;
		float NominalRadius = 0.f;
		float DatumRadius = 0.f;
		float PeakRadius = 0.f;
	};

	// Successful lookups are stable for the lifetime of their world. Failed lookups are deliberately
	// not stored because the PlanetGen actor may not have spawned yet during early startup.
	TMap<TWeakObjectPtr<UWorld>, FMeshPlanetCacheEntry> GMeshPlanetCache;

	void PruneMeshPlanetCache()
	{
		for (auto It = GMeshPlanetCache.CreateIterator(); It; ++It)
		{
			if (!It.Key().IsValid() || !It.Value().Planet.IsValid())
			{
				It.RemoveCurrent();
			}
		}
	}

	bool ReadCachedMeshPlanet(
		UWorld* World,
		FVector& OutCenter,
		float& OutRadius,
		float* OutPeakRadius,
		float* OutNominalRadius,
		const bool bRequireUniquePlanet)
	{
		const TWeakObjectPtr<UWorld> WorldKey(World);
		FMeshPlanetCacheEntry* Cached = GMeshPlanetCache.Find(WorldKey);
		AActor* Planet = Cached ? Cached->Planet.Get() : nullptr;
		if (!IsValid(Planet) || Planet->GetWorld() != World)
		{
			if (Cached)
			{
				GMeshPlanetCache.Remove(WorldKey);
			}
			return false;
		}
		if (bRequireUniquePlanet && !Cached->bUniquePlanetValidated)
		{
			return false;
		}

		OutCenter = Planet->GetActorLocation();
		OutRadius = Cached->DatumRadius;
		if (OutPeakRadius)
		{
			*OutPeakRadius = Cached->PeakRadius;
		}
		if (OutNominalRadius)
		{
			*OutNominalRadius = Cached->NominalRadius;
		}
		return true;
	}

	bool FindMeshPlanetInternal(
		UWorld* World,
		FVector& OutCenter,
		float& OutRadius,
		float* OutPeakRadius,
		float* OutNominalRadius,
		bool bRequireUniquePlanet);
}

bool RedGravity::SelectDominantBody(
	const TArray<FBodyCandidate>& Candidates, const FVector& Location,
	const FName PreviousBodyId, const float SwitchHysteresisCm, FBodyQueryResult& OutResult)
{
	OutResult = FBodyQueryResult();
	if (Location.ContainsNaN())
	{
		return false;
	}

	struct FEvaluatedCandidate
	{
		const FBodyCandidate* Candidate = nullptr;
		float SurfaceDistance = TNumericLimits<float>::Max();
		int64 DistanceBucket = TNumericLimits<int64>::Max();
	};

	TArray<FEvaluatedCandidate, TInlineAllocator<8>> ValidCandidates;
	TSet<FName> SeenStableIds;
	for (const FBodyCandidate& Candidate : Candidates)
	{
		if (!Candidate.StableId.IsNone())
		{
			if (SeenStableIds.Contains(Candidate.StableId))
			{
				// Duplicate IDs make save/replication identity ambiguous. Fail closed instead of
				// allowing actor iteration order to choose a physical body.
				return false;
			}
			SeenStableIds.Add(Candidate.StableId);
		}

		const float SelectionRadius = Candidate.SelectionSurfaceRadius > 0.f
			? Candidate.SelectionSurfaceRadius : Candidate.SurfaceRadius;
		if (Candidate.StableId.IsNone() || Candidate.Center.ContainsNaN()
			|| !FMath::IsFinite(Candidate.SurfaceRadius) || Candidate.SurfaceRadius <= 0.f
			|| !FMath::IsFinite(SelectionRadius) || SelectionRadius <= 0.f
			|| !FMath::IsFinite(Candidate.InfluenceRadius) || Candidate.InfluenceRadius <= 0.f)
		{
			continue;
		}

		const float CenterDistance = static_cast<float>((Location - Candidate.Center).Size());
		const float ExitMargin = Candidate.StableId == PreviousBodyId
			? FMath::Max(0.f, SwitchHysteresisCm) : 0.f;
		if (!FMath::IsFinite(CenterDistance)
			|| CenterDistance > Candidate.InfluenceRadius + ExitMargin)
		{
			continue;
		}
		const float SurfaceDistance = FMath::Abs(CenterDistance - SelectionRadius);
		// A fixed 0.1 cm bucket creates a total ordering; pairwise nearly-equal comparison is
		// non-transitive and can change the winner when actor iteration order changes.
		const int64 DistanceBucket = FMath::RoundToInt64(
			static_cast<double>(SurfaceDistance) * 10.0);
		ValidCandidates.Add({ &Candidate, SurfaceDistance, DistanceBucket });
	}

	if (ValidCandidates.IsEmpty())
	{
		return false;
	}

	auto IsBetter = [](const FEvaluatedCandidate& Candidate, const FEvaluatedCandidate& Best)
	{
		if (Candidate.Candidate->Priority != Best.Candidate->Priority)
		{
			return Candidate.Candidate->Priority > Best.Candidate->Priority;
		}
		if (Candidate.DistanceBucket != Best.DistanceBucket)
		{
			return Candidate.DistanceBucket < Best.DistanceBucket;
		}
		return Candidate.Candidate->StableId.ToString()
			< Best.Candidate->StableId.ToString();
	};

	const FEvaluatedCandidate* Selected = &ValidCandidates[0];
	for (int32 Index = 1; Index < ValidCandidates.Num(); ++Index)
	{
		if (IsBetter(ValidCandidates[Index], *Selected))
		{
			Selected = &ValidCandidates[Index];
		}
	}

	if (!PreviousBodyId.IsNone() && SwitchHysteresisCm > 0.f)
	{
		if (const FEvaluatedCandidate* Previous = ValidCandidates.FindByPredicate(
			[PreviousBodyId](const FEvaluatedCandidate& Candidate)
			{
				return Candidate.Candidate->StableId == PreviousBodyId;
			}))
		{
			if (Previous->Candidate->Priority == Selected->Candidate->Priority
				&& Previous->SurfaceDistance
				<= Selected->SurfaceDistance + FMath::Max(0.f, SwitchHysteresisCm))
			{
				Selected = Previous;
			}
		}
	}

	OutResult.StableId = Selected->Candidate->StableId;
	OutResult.Center = Selected->Candidate->Center;
	OutResult.SurfaceRadius = Selected->Candidate->SurfaceRadius;
	OutResult.InfluenceRadius = Selected->Candidate->InfluenceRadius;
	OutResult.SurfaceDistance = Selected->SurfaceDistance;
	OutResult.Priority = Selected->Candidate->Priority;
	return true;
}

bool RedGravity::QueryDominantBodyDetailed(
	UWorld* World, const FVector& Location, const FName PreviousBodyId,
	const float SwitchHysteresisCm, FBodyQueryResult& OutResult)
{
	OutResult = FBodyQueryResult();
	if (!World)
	{
		return false;
	}

	TArray<FBodyCandidate> Candidates;
	Candidates.Reserve(8);
	FVector HomeCenter = FVector::ZeroVector;
	float HomeDatumRadius = -1.f;
	float HomePeakRadius = -1.f;
	const bool bHasHome = FindMeshPlanet(
		World, HomeCenter, HomeDatumRadius, &HomePeakRadius);
	if (bHasHome)
	{
		const float HomeVisualSurfaceRadius = (HomeDatumRadius + HomePeakRadius) * 0.5f;
		Candidates.Add({ TEXT("planet.red.mars"), HomeCenter, HomeDatumRadius,
			HomeVisualSurfaceRadius, TNumericLimits<float>::Max(), 100 });
	}

	for (TActorIterator<ARedSpaceScenery> It(World); It; ++It)
	{
		if (!IsValid(*It))
		{
			continue;
		}
		TArray<FName> BodyStableIds;
		TArray<int32> BodyPriorities;
		TArray<FVector> BodyCenters;
		TArray<float> BodySurfaceRadii;
		TArray<float> BodyInfluenceRadii;
		It->AppendGravityBodies(BodyStableIds, BodyPriorities,
			BodyCenters, BodySurfaceRadii, BodyInfluenceRadii);
		const int32 BodyCount = FMath::Min(
			FMath::Min(BodyStableIds.Num(), BodyPriorities.Num()),
			FMath::Min(BodyCenters.Num(), FMath::Min(
				BodySurfaceRadii.Num(), BodyInfluenceRadii.Num())));
		for (int32 BodyIndex = 0; BodyIndex < BodyCount; ++BodyIndex)
		{
			Candidates.Add({ BodyStableIds[BodyIndex], BodyCenters[BodyIndex],
				BodySurfaceRadii[BodyIndex], BodySurfaceRadii[BodyIndex],
				BodyInfluenceRadii[BodyIndex], BodyPriorities[BodyIndex] });
		}
	}
	return SelectDominantBody(Candidates, Location, PreviousBodyId,
		SwitchHysteresisCm, OutResult);
}

bool RedGravity::QueryDominantBody(
	UWorld* World, const FVector& Location, FVector& OutCenter, float& OutSurfaceRadius)
{
	FBodyQueryResult Result;
	const bool bFoundBody = QueryDominantBodyDetailed(
		World, Location, NAME_None, 0.f, Result);
	OutCenter = bFoundBody ? Result.Center : FVector::ZeroVector;
	OutSurfaceRadius = bFoundBody ? Result.SurfaceRadius : -1.f;
	return bFoundBody;
}

FVector RedGravity::UpAt(UWorld* World, const FVector& Location, const FVector& Fallback)
{
	FVector Center;
	float SurfaceRadius;
	if (QueryDominantBody(World, Location, Center, SurfaceRadius))
	{
		const FVector Up = (Location - Center).GetSafeNormal();
		if (!Up.IsNearlyZero())
		{
			return Up;
		}
	}
	return Fallback;
}

bool RedGravity::FindMeshPlanet(
	UWorld* World,
	FVector& OutCenter,
	float& OutRadius,
	float* OutPeakRadius)
{
	return FindMeshPlanetInternal(
		World, OutCenter, OutRadius, OutPeakRadius, nullptr, false);
}

namespace
{
bool FindMeshPlanetInternal(
	UWorld* World,
	FVector& OutCenter,
	float& OutRadius,
	float* OutPeakRadius,
	float* OutNominalRadius,
	const bool bRequireUniquePlanet)
{
	if (!World)
	{
		return false;
	}

	if (ReadCachedMeshPlanet(
		World, OutCenter, OutRadius, OutPeakRadius, OutNominalRadius,
		bRequireUniquePlanet))
	{
		return true;
	}

	PruneMeshPlanetCache();
	FMeshPlanetCacheEntry Candidate;
	int32 ValidPlanetCount = 0;
	for (TActorIterator<AActor> It(World); It; ++It)
	{
		AActor* Actor = *It;
		if (!IsValid(Actor))
		{
			continue;
		}
		// Match ACLMPlanet or any subclass (BP_CLMPlanet_C) by walking the class chain — avoids a
		// hard build dependency on the PlanetGen plugin module.
		bool bIsPlanet = false;
		for (const UClass* C = Actor->GetClass(); C; C = C->GetSuperClass())
		{
			if (C->GetName() == TEXT("CLMPlanet"))
			{
				bIsPlanet = true;
				break;
			}
		}
		if (!bIsPlanet)
		{
			continue;
		}
		// Authored surface radius (cm) read via reflection from the CLM planet actor.
		float Radius = 0.f;
		if (const FFloatProperty* Prop = FindFProperty<FFloatProperty>(Actor->GetClass(), TEXT("PlanetRadius")))
		{
			Radius = Prop->GetPropertyValue_InContainer(Actor);
		}
		if (!FMath::IsFinite(Radius) || Radius <= 0.f)
		{
			continue;
		}
		// The analytic datum must sit BELOW the lowest terrain. CLM displaces terrain INWARD from
		// PlanetRadius by up to MaxMountainHeight; if the datum stays at PlanetRadius (above the ground
		// the pawn actually stands on), RED's datum "catcher" sky-trace fires EVERY frame, which starves
		// the chunk-collision cook, so the pawn never resolves ground = a 3 fps hover-lock on landing.
		// Put the datum a margin below the deepest terrain so the catcher never triggers on the surface.
		float MountainHeight = 50000.f;
		if (const FFloatProperty* MP = FindFProperty<FFloatProperty>(Actor->GetClass(), TEXT("MaxMountainHeight")))
		{
			MountainHeight = MP->GetPropertyValue_InContainer(Actor);
		}
		++ValidPlanetCount;
		if (ValidPlanetCount == 1)
		{
			Candidate.Planet = Actor;
			Candidate.NominalRadius = Radius;
			Candidate.DatumRadius = FMath::Max(
				1000.f, Radius - MountainHeight - 20000.f);
			Candidate.PeakRadius = Radius + MountainHeight + 20000.f;
		}

		if (!bRequireUniquePlanet)
		{
			break;
		}
		if (ValidPlanetCount > 1)
		{
			// Multiple unlabelled PlanetGen actors cannot be mapped safely to the home body.
			// Strict callers fail closed instead of accepting actor iteration order.
			return false;
		}
	}

	if (ValidPlanetCount != 1 || !Candidate.Planet.IsValid())
	{
		return false;
	}

	Candidate.bUniquePlanetValidated = bRequireUniquePlanet;
	GMeshPlanetCache.Add(TWeakObjectPtr<UWorld>(World), Candidate);
	OutCenter = Candidate.Planet->GetActorLocation();
	OutRadius = Candidate.DatumRadius;
	if (OutPeakRadius)
	{
		*OutPeakRadius = Candidate.PeakRadius;
	}
	if (OutNominalRadius)
	{
		*OutNominalRadius = Candidate.NominalRadius;
	}
	return true;
}
}

bool RedGravity::FindMeshPlanet(
	UWorld* World,
	FVector& OutCenter,
	float& OutRadius,
	float* OutPeakRadius,
	float* OutNominalRadius)
{
	return FindMeshPlanetInternal(
		World, OutCenter, OutRadius, OutPeakRadius, OutNominalRadius, true);
}
