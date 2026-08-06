#pragma once

#include "CoreMinimal.h"

class UWorld;
struct FCollisionShape;
struct FHitResult;

/**
 * Result of an exact query against the currently streamed PlanetGen terrain.
 * NoMatchingPlanet means the caller is on a legacy/static body and may use its old fallback.
 * NoHit deliberately remains distinct: a matching PlanetGen actor exists, but no owned active
 * terrain component was hit, so unrelated WorldDynamic/WorldStatic presentation geometry must not
 * be accepted as ground.
 */
enum class ERedPlanetTerrainQueryResult : uint8
{
	NoMatchingPlanet,
	NoHit,
	Hit
};

namespace RedPlanetTerrainQuery
{
	/** Trace only exact active terrain owned by the PlanetGen actor at ExpectedPlanetCenter. */
	REDMMO_API ERedPlanetTerrainQueryResult LineTrace(
		UWorld* World,
		const FVector& ExpectedPlanetCenter,
		const FVector& Start,
		const FVector& End,
		FHitResult& OutHit,
		FIntVector* OutChunkKey = nullptr);

	/** Sweep a supported sphere/capsule/oriented box only against exact active terrain owned by that planet. */
	REDMMO_API ERedPlanetTerrainQueryResult Sweep(
		UWorld* World,
		const FVector& ExpectedPlanetCenter,
		const FVector& Start,
		const FVector& End,
		const FQuat& ShapeWorldRotation,
		const FCollisionShape& CollisionShape,
		FHitResult& OutHit,
		FIntVector* OutChunkKey = nullptr);
}
