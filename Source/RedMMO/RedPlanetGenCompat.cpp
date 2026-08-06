#include "RedPlanetGenCompat.h"

#include "CollisionQueryParams.h"
#include "CollisionShape.h"
#include "Components/PrimitiveComponent.h"
#include "Engine/HitResult.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "PlanetGen/CLMPlanet.h"
#include "PlanetGen/CLMPlanetChunk.h"

#if __has_include("PlanetGen/PlanetGenTerrainStamp.h")
#define REDMMO_HAS_PLANETGEN_FORK_APIS 1
#else
#define REDMMO_HAS_PLANETGEN_FORK_APIS 0
#endif

namespace
{
	constexpr float ActiveTerrainTieDistanceToleranceCm = 1.0f;

	bool IsOwnedActiveChunk(const ACLMPlanet* Planet, const ACLMPlanetChunk* Chunk)
	{
		return IsValid(Planet)
			&& IsValid(Chunk)
			&& Chunk->GetOwner() == Planet
			&& Chunk->bActive
			&& !Chunk->bBuilding
			&& Chunk->HasSurface();
	}

	float GetQueryHitDistanceCm(const FHitResult& Hit, float TraceLengthCm)
	{
		if (FMath::IsFinite(Hit.Distance) && Hit.Distance >= 0.f)
		{
			return Hit.Distance;
		}
		if (Hit.bBlockingHit)
		{
			return FVector::Distance(Hit.TraceStart, Hit.Location);
		}
		return TraceLengthCm;
	}

	bool QueryOwnedActiveTerrain(
		const ACLMPlanet* Planet,
		FHitResult& OutHit,
		const FVector& Start,
		const FVector& End,
		const FQuat& ShapeWorldRotation,
		const FCollisionShape* CollisionShape,
		FIntVector* OutChunkKey)
	{
		OutHit.Reset(1.f, false);
		OutHit.TraceStart = Start;
		OutHit.TraceEnd = End;
		if (OutChunkKey)
		{
			*OutChunkKey = FIntVector(INDEX_NONE, INDEX_NONE, INDEX_NONE);
		}

		if (!IsValid(Planet) || !IsInGameThread() || Start.ContainsNaN() || End.ContainsNaN())
		{
			return false;
		}

		UWorld* World = Planet->GetWorld();
		if (!IsValid(World))
		{
			return false;
		}

		FQuat SafeRotation = FQuat::Identity;
		if (CollisionShape)
		{
			const double RotationSizeSquared = ShapeWorldRotation.SizeSquared();
			if (ShapeWorldRotation.ContainsNaN()
				|| !FMath::IsFinite(RotationSizeSquared)
				|| RotationSizeSquared <= UE_SMALL_NUMBER)
			{
				return false;
			}
			SafeRotation = ShapeWorldRotation.IsNormalized()
				? ShapeWorldRotation
				: ShapeWorldRotation.GetNormalized();
		}

		const float TraceLengthCm = FVector::Distance(Start, End);
		FHitResult BestHit;
		float BestDistanceCm = TNumericLimits<float>::Max();
		FIntVector BestKey(INDEX_NONE, INDEX_NONE, INDEX_NONE);
		bool bFound = false;

		FCollisionQueryParams Params(SCENE_QUERY_STAT(RedPlanetGenCompatActiveTerrain), false);
		Params.bTraceComplex = true;
		Params.bReturnPhysicalMaterial = false;

		for (TActorIterator<ACLMPlanetChunk> It(World); It; ++It)
		{
			ACLMPlanetChunk* Chunk = *It;
			if (!IsOwnedActiveChunk(Planet, Chunk))
			{
				continue;
			}

			UPrimitiveComponent* Mesh = Cast<UPrimitiveComponent>(Chunk->GetRootComponent());
			if (!IsValid(Mesh) || !Mesh->IsRegistered() || !Mesh->IsCollisionEnabled())
			{
				continue;
			}

			FHitResult Candidate;
			bool bHit = false;
			if (CollisionShape)
			{
				bHit = Mesh->SweepComponent(
					Candidate,
					Start,
					End,
					SafeRotation,
					*CollisionShape,
					true);
			}
			else
			{
				bHit = Mesh->LineTraceComponent(
					Candidate,
					Start,
					End,
					Params);
			}

			if (!bHit || !Candidate.bBlockingHit)
			{
				continue;
			}

			const float DistanceCm = GetQueryHitDistanceCm(Candidate, TraceLengthCm);
			const FIntVector Key = Chunk->GetActorLocation().Equals(FVector::ZeroVector, 0.f)
				? FIntVector(INDEX_NONE, INDEX_NONE, INDEX_NONE)
				: FIntVector(
					FMath::RoundToInt(Chunk->GetActorLocation().X),
					FMath::RoundToInt(Chunk->GetActorLocation().Y),
					FMath::RoundToInt(Chunk->GetActorLocation().Z));

			const bool bCloser = DistanceCm + ActiveTerrainTieDistanceToleranceCm < BestDistanceCm;
			const bool bTiePreferStable = FMath::IsNearlyEqual(
				DistanceCm, BestDistanceCm, ActiveTerrainTieDistanceToleranceCm)
				&& (Key.X < BestKey.X
					|| (Key.X == BestKey.X && Key.Y < BestKey.Y)
					|| (Key.X == BestKey.X && Key.Y == BestKey.Y && Key.Z < BestKey.Z));

			if (!bFound || bCloser || bTiePreferStable)
			{
				BestHit = Candidate;
				BestDistanceCm = DistanceCm;
				BestKey = Key;
				bFound = true;
			}
		}

		if (!bFound)
		{
			return false;
		}

		OutHit = BestHit;
		if (OutChunkKey)
		{
			*OutChunkKey = BestKey;
		}
		return true;
	}
}

bool RedPlanetGenCompat::SampleResolvedSurface(
	const ACLMPlanet* Planet,
	const FVector& SurfaceDirection,
	float& OutRadialHeightCm)
{
	OutRadialHeightCm = 0.f;
	if (!IsValid(Planet))
	{
		return false;
	}

#if REDMMO_HAS_PLANETGEN_FORK_APIS
	return Planet->SampleResolvedSurface(SurfaceDirection, OutRadialHeightCm);
#else
	const FVector Direction = SurfaceDirection.GetSafeNormal();
	if (Direction.IsNearlyZero())
	{
		return false;
	}

	UWorld* World = Planet->GetWorld();
	if (!IsValid(World) || !IsInGameThread())
	{
		return false;
	}

	const FVector Center = Planet->GetActorLocation();
	const float RadiusCm = Planet->PlanetRadiusCm();
	const float ProbeCm = FMath::Max(Planet->MaxMountainHeightCm(), 50000.f) + 25000.f;
	const FVector Start = Center + Direction * (RadiusCm + ProbeCm);
	const FVector End = Center + Direction * FMath::Max(RadiusCm - ProbeCm, 1.f);

	FHitResult Hit;
	if (!LineTraceActiveTerrain(Planet, Hit, Start, End, nullptr) || !Hit.bBlockingHit)
	{
		return false;
	}

	const float AbsoluteRadiusCm = FVector::Distance(Hit.Location, Center);
	if (!FMath::IsFinite(AbsoluteRadiusCm))
	{
		return false;
	}

	OutRadialHeightCm = AbsoluteRadiusCm - RadiusCm;
	return true;
#endif
}

bool RedPlanetGenCompat::LineTraceActiveTerrain(
	const ACLMPlanet* Planet,
	FHitResult& OutHit,
	const FVector& Start,
	const FVector& End,
	FIntVector* OutChunkKey)
{
#if REDMMO_HAS_PLANETGEN_FORK_APIS
	if (!IsValid(Planet))
	{
		OutHit.Reset(1.f, false);
		if (OutChunkKey)
		{
			*OutChunkKey = FIntVector(INDEX_NONE, INDEX_NONE, INDEX_NONE);
		}
		return false;
	}
	return Planet->LineTraceActiveTerrain(OutHit, Start, End, OutChunkKey);
#else
	return QueryOwnedActiveTerrain(
		Planet, OutHit, Start, End, FQuat::Identity, nullptr, OutChunkKey);
#endif
}

bool RedPlanetGenCompat::SweepActiveTerrain(
	const ACLMPlanet* Planet,
	FHitResult& OutHit,
	const FVector& Start,
	const FVector& End,
	const FQuat& ShapeWorldRotation,
	const FCollisionShape& CollisionShape,
	FIntVector* OutChunkKey)
{
#if REDMMO_HAS_PLANETGEN_FORK_APIS
	if (!IsValid(Planet))
	{
		OutHit.Reset(1.f, false);
		if (OutChunkKey)
		{
			*OutChunkKey = FIntVector(INDEX_NONE, INDEX_NONE, INDEX_NONE);
		}
		return false;
	}
	return Planet->SweepActiveTerrain(
		OutHit, Start, End, ShapeWorldRotation, CollisionShape, OutChunkKey);
#else
	return QueryOwnedActiveTerrain(
		Planet, OutHit, Start, End, ShapeWorldRotation, &CollisionShape, OutChunkKey);
#endif
}
