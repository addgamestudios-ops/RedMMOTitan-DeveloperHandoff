#include "RedPlanetTerrainQuery.h"

#include "Engine/World.h"
#include "EngineUtils.h"
#include "PlanetGen/CLMPlanet.h"
#include "RedPlanetGenCompat.h"

namespace
{
	constexpr float PlanetCenterMatchToleranceCm = 100.0f;

	struct FPlanetQueryCacheEntry
	{
		TWeakObjectPtr<ACLMPlanet> Planet;
	};

	TMap<TWeakObjectPtr<UWorld>, FPlanetQueryCacheEntry> GPlanetQueryCache;

	ACLMPlanet* ResolvePlanet(UWorld* World, const FVector& ExpectedPlanetCenter)
	{
		if (!World)
		{
			return nullptr;
		}

		const TWeakObjectPtr<UWorld> WorldKey(World);
		if (const FPlanetQueryCacheEntry* Cached = GPlanetQueryCache.Find(WorldKey))
		{
			ACLMPlanet* Planet = Cached->Planet.Get();
			if (IsValid(Planet)
				&& Planet->GetWorld() == World
				&& Planet->GetActorLocation().Equals(ExpectedPlanetCenter, PlanetCenterMatchToleranceCm))
			{
				return Planet;
			}
			GPlanetQueryCache.Remove(WorldKey);
		}

		for (auto It = GPlanetQueryCache.CreateIterator(); It; ++It)
		{
			if (!It.Key().IsValid() || !It.Value().Planet.IsValid())
			{
				It.RemoveCurrent();
			}
		}

		ACLMPlanet* BestPlanet = nullptr;
		double BestDistanceSquared = TNumericLimits<double>::Max();
		for (TActorIterator<ACLMPlanet> It(World); It; ++It)
		{
			ACLMPlanet* Candidate = *It;
			if (!IsValid(Candidate))
			{
				continue;
			}
			const double DistanceSquared = FVector::DistSquared(
				Candidate->GetActorLocation(), ExpectedPlanetCenter);
			if (DistanceSquared <= FMath::Square(static_cast<double>(PlanetCenterMatchToleranceCm))
				&& DistanceSquared < BestDistanceSquared)
			{
				BestDistanceSquared = DistanceSquared;
				BestPlanet = Candidate;
			}
		}

		if (BestPlanet)
		{
			FPlanetQueryCacheEntry Entry;
			Entry.Planet = BestPlanet;
			GPlanetQueryCache.Add(WorldKey, Entry);
		}
		return BestPlanet;
	}

	void ResetMiss(FHitResult& OutHit, FIntVector* OutChunkKey)
	{
		OutHit = FHitResult();
		if (OutChunkKey)
		{
			*OutChunkKey = FIntVector(INDEX_NONE, INDEX_NONE, INDEX_NONE);
		}
	}
}

ERedPlanetTerrainQueryResult RedPlanetTerrainQuery::LineTrace(
	UWorld* World,
	const FVector& ExpectedPlanetCenter,
	const FVector& Start,
	const FVector& End,
	FHitResult& OutHit,
	FIntVector* OutChunkKey)
{
	ResetMiss(OutHit, OutChunkKey);
	ACLMPlanet* Planet = ResolvePlanet(World, ExpectedPlanetCenter);
	if (!Planet)
	{
		return ERedPlanetTerrainQueryResult::NoMatchingPlanet;
	}
	return RedPlanetGenCompat::LineTraceActiveTerrain(Planet, OutHit, Start, End, OutChunkKey)
		? ERedPlanetTerrainQueryResult::Hit
		: ERedPlanetTerrainQueryResult::NoHit;
}

ERedPlanetTerrainQueryResult RedPlanetTerrainQuery::Sweep(
	UWorld* World,
	const FVector& ExpectedPlanetCenter,
	const FVector& Start,
	const FVector& End,
	const FQuat& ShapeWorldRotation,
	const FCollisionShape& CollisionShape,
	FHitResult& OutHit,
	FIntVector* OutChunkKey)
{
	ResetMiss(OutHit, OutChunkKey);
	ACLMPlanet* Planet = ResolvePlanet(World, ExpectedPlanetCenter);
	if (!Planet)
	{
		return ERedPlanetTerrainQueryResult::NoMatchingPlanet;
	}
	return RedPlanetGenCompat::SweepActiveTerrain(
		Planet, OutHit, Start, End, ShapeWorldRotation, CollisionShape, OutChunkKey)
		? ERedPlanetTerrainQueryResult::Hit
		: ERedPlanetTerrainQueryResult::NoHit;
}
