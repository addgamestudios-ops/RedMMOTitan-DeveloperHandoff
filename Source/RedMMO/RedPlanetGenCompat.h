#pragma once

#include "CoreMinimal.h"

class ACLMPlanet;
struct FCollisionShape;
struct FHitResult;

/**
 * Project-owned PlanetGen surface/query adapters.
 *
 * When the pinned RedMMO PlanetGen fork is mounted (PlanetGenTerrainStamp /
 * MacroHeightfield + ACLMPlanet::SampleResolvedSurface/LineTraceActiveTerrain/
 * SweepActiveTerrain), calls forward to those APIs.
 *
 * When only stock Marketplace PlanetGen 1.7 is present, these free functions
 * provide working substitutes so TitanEditor can link without the missing fork
 * payload. Restore Plugins/PlanetGenPinned_1_4_0_RedMMO (or a 1.7-based successor
 * with the same public APIs) to return to official fork behavior.
 */
namespace RedPlanetGenCompat
{
	bool SampleResolvedSurface(
		const ACLMPlanet* Planet,
		const FVector& SurfaceDirection,
		float& OutRadialHeightCm);

	bool LineTraceActiveTerrain(
		const ACLMPlanet* Planet,
		FHitResult& OutHit,
		const FVector& Start,
		const FVector& End,
		FIntVector* OutChunkKey = nullptr);

	bool SweepActiveTerrain(
		const ACLMPlanet* Planet,
		FHitResult& OutHit,
		const FVector& Start,
		const FVector& End,
		const FQuat& ShapeWorldRotation,
		const FCollisionShape& CollisionShape,
		FIntVector* OutChunkKey = nullptr);
}
