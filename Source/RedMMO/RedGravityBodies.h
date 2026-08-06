#pragma once

#include "CoreMinimal.h"

class UWorld;

/**
 * Radial gravity queries for the PlanetGen mesh planet. PlanetGen is discovered by reflection so
 * this module does not take a hard build dependency on the plugin. Successful discovery is cached
 * per world; calls made before the planet exists continue scanning until it becomes available.
 */
namespace RedGravity
{
	/** One deterministic gravity-body candidate, independent of its rendering implementation. */
	struct REDMMO_API FBodyCandidate
	{
		FName StableId = NAME_None;
		FVector Center = FVector::ZeroVector;
		float SurfaceRadius = -1.f;
		float SelectionSurfaceRadius = -1.f;
		float InfluenceRadius = -1.f;
		int32 Priority = 0;
	};

	/** Durable result used by movement code to carry its previous stable body across ticks. */
	struct REDMMO_API FBodyQueryResult
	{
		FName StableId = NAME_None;
		FVector Center = FVector::ZeroVector;
		float SurfaceRadius = -1.f;
		float InfluenceRadius = -1.f;
		float SurfaceDistance = TNumericLimits<float>::Max();
		int32 Priority = 0;
	};

	/**
	 * Pure deterministic selector. Explicit priority wins first, then quantized surface distance,
	 * then lexical stable ID. A previous body gets an influence exit margin and, among equal-priority
	 * bodies, remains selected while within the caller-provided switch hysteresis distance.
	 */
	REDMMO_API bool SelectDominantBody(
		const TArray<FBodyCandidate>& Candidates, const FVector& Location,
		FName PreviousBodyId, float SwitchHysteresisCm, FBodyQueryResult& OutResult);

	/** Stable-ID query for stateful movement callers that need overlap hysteresis. */
	REDMMO_API bool QueryDominantBodyDetailed(
		UWorld* World, const FVector& Location, FName PreviousBodyId,
		float SwitchHysteresisCm, FBodyQueryResult& OutResult);

	/** Nearest active gravity body: the PlanetGen home world or any nearby scenery moon. */
	REDMMO_API bool QueryDominantBody(UWorld* World, const FVector& Location, FVector& OutCenter, float& OutSurfaceRadius);

	/** Radial up at Location from the mesh planet's center; Fallback while no planet is available. */
	REDMMO_API FVector UpAt(UWorld* World, const FVector& Location, const FVector& Fallback);

	/**
	 * Detects and caches a CLM PlanetGen mesh planet (ACLMPlanet or a BP subclass like BP_CLMPlanet_C)
	 * by reflection — no PlanetGen build dependency. Returns the planet center (actor location) and the
	 * gameplay DATUM radius (a margin BELOW the deepest terrain, so RED's datum catcher never fires on
	 * the surface). OutPeakRadius (optional) receives a conservative radius above the authored terrain
	 * envelope for starting radial placement traces safely above the ground. OutNominalRadius (optional)
	 * receives PlanetGen's reflected physical PlanetRadius; it must not be inferred from the datum.
	 */
	REDMMO_API bool FindMeshPlanet(
		UWorld* World,
		FVector& OutCenter,
		float& OutRadius,
		float* OutPeakRadius = nullptr);

	/**
	 * Strict frame query that also returns the raw reflected PlanetRadius. It succeeds only when
	 * exactly one valid PlanetGen actor exists, so callers cannot silently depend on actor order.
	 */
	REDMMO_API bool FindMeshPlanet(
		UWorld* World,
		FVector& OutCenter,
		float& OutRadius,
		float* OutPeakRadius,
		float* OutNominalRadius);
}
