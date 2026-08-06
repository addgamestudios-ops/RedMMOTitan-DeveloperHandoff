#pragma once

#include "CoreMinimal.h"
#include "Containers/StaticArray.h"

/**
 * Deterministic geometry and authoring metadata for RED's 50 km planet proof.
 *
 * This layer deliberately has no UObject or PlanetGen dependency. It can be used by runtime
 * streaming, editor tools, PCG, and save-game code without making any of those systems own the
 * planet layout. Distances are in Unreal centimetres unless a field explicitly says otherwise.
 */
namespace RedPlanet
{
	struct REDMMO_API FPlanet50KmProfile final
	{
		static constexpr int32 RegionCount = 27;
		static constexpr uint32 LayoutSeed = 0x52454435u; // "RED5"

		static constexpr double CircumferenceKm = 50.0;
		static constexpr double CircumferenceCm = 5000000.0;
		static constexpr double RadiusCm = 795774.7154594767;
		static constexpr double DiameterCm = RadiusCm * 2.0;
		static constexpr double GravityRadiusCm = RadiusCm * 2.0;
		static constexpr double SurfaceAreaSquareKm = 795.7747154594767;
		static constexpr double AverageRegionAreaSquareKm = SurfaceAreaSquareKm / RegionCount;

		// Conservative first-pass PlanetGen values. They describe the smoke-test profile; the
		// region service does not apply them to an actor or plugin by itself.
		static constexpr double SmokeTestTileSizeCm = 200000.0;
		static constexpr int32 SmokeTestMaxChunksPerFace = 8;
		static constexpr int32 SmokeTestChunkResolution = 32;
		static constexpr double SmokeTestMinTerrainHeightCm = -30000.0;
		static constexpr double SmokeTestMaxTerrainHeightCm = 30000.0;
		static constexpr double SmokeTestSeaLevel01 = 0.45;

		// Flattening is intentionally local. A region is a metadata territory, not a 5 km plane.
		static constexpr double MinAuthoringHubRadiusCm = 25000.0;
		static constexpr double MaxAuthoringHubRadiusCm = 50000.0;

		/** Cheap guard for tests and integration assertions. */
		static bool IsInternallyConsistent(double ToleranceCm = 0.01);
	};

	enum class ERegionArchetype : uint8
	{
		CoralCanopyCoast,
		EmberMagentaRift,
		FungalCathedral,
		MonolithicPillarCavern,
		VerdantSkyPlateau,
		PortalOasis,
		CliffsideSpaceport
	};

	struct REDMMO_API FPlanetTangentFrame
	{
		FVector3d UnitUp = FVector3d(0.0, 0.0, 1.0);
		FVector3d UnitEast = FVector3d(1.0, 0.0, 0.0);
		FVector3d UnitNorth = FVector3d(0.0, 1.0, 0.0);
	};

	struct REDMMO_API FPlanetRegionMetadata
	{
		int32 RegionIndex = INDEX_NONE;
		uint32 StableSeed = 0;
		uint8 VariationIndex = 0;
		FVector3d UnitSite = FVector3d(0.0, 0.0, 1.0);
		ERegionArchetype Archetype = ERegionArchetype::CoralCanopyCoast;

		double NominalAreaSquareKm = 0.0;
		double SuggestedHubRadiusCm = 0.0;
		double SuggestedFlattenCoreRadiusCm = 0.0;
		double SuggestedFlattenBlendRadiusCm = 0.0;

		// Seeded authoring signals. They are stable inputs for biome selection, not final terrain.
		float Temperature01 = 0.5f;
		float Moisture01 = 0.5f;
		float AlienIntensity01 = 0.5f;
		float ElevationBias = 0.0f;
	};

	struct REDMMO_API FPlanetRegionWeight
	{
		int32 RegionIndex = INDEX_NONE;
		double GreatCircleDistanceRadians = 0.0;
		double Weight = 0.0;
	};

	struct REDMMO_API FPlanetRegionBlend
	{
		static constexpr int32 MaxContributors = 4;

		TStaticArray<FPlanetRegionWeight, MaxContributors> Contributors;
		int32 NumContributors = 0;

		const FPlanetRegionWeight* GetDominant() const
		{
			return NumContributors > 0 ? &Contributors[0] : nullptr;
		}
	};

	/**
	 * Immutable deterministic region service.
	 *
	 * The 27 sites use a spherical-Fibonacci distribution. They are metadata/Voronoi anchors,
	 * not octosphere faces, so the surface remains seamless and contains no region walls.
	 */
	class REDMMO_API FPlanetRegionService final
	{
	public:
		static const FPlanetRegionService& Get();

		const TStaticArray<FPlanetRegionMetadata, FPlanet50KmProfile::RegionCount>& GetRegions() const;
		const FPlanetRegionMetadata& GetRegionChecked(int32 RegionIndex) const;

		int32 FindNearestRegion(const FVector3d& SurfaceDirection) const;

		/**
		 * Returns up to four normalized Gaussian weights ordered nearest-first. Angular great-circle
		 * distance drives the blend; SigmaRadians controls how softly neighbouring territories mix.
		 */
		FPlanetRegionBlend SampleBlendedRegions(
			const FVector3d& SurfaceDirection,
			int32 MaxContributors = FPlanetRegionBlend::MaxContributors,
			double SigmaRadians = 0.20) const;

		static double GreatCircleDistanceRadians(const FVector3d& A, const FVector3d& B);

		/** Builds an orthonormal tangent frame. PlanetNorthAxis only chooses the local heading. */
		static FPlanetTangentFrame MakeTangentFrame(
			const FVector3d& SurfaceDirection,
			const FVector3d& PlanetNorthAxis = FVector3d(0.0, 0.0, 1.0));

		/**
		 * Spherical exponential map. LocalOffsetCm.X is east and .Y is north in Anchor's tangent
		 * frame. This is the preferred way to place authored meshes around a region hub.
		 */
		static FVector3d ExpMapDirection(
			const FVector3d& AnchorSurfaceDirection,
			const FVector2d& LocalOffsetCm,
			double PlanetRadiusCm = FPlanet50KmProfile::RadiusCm,
			const FVector3d& PlanetNorthAxis = FVector3d(0.0, 0.0, 1.0));

		static FVector3d ExpMapPosition(
			const FVector3d& PlanetCenter,
			const FVector3d& AnchorSurfaceDirection,
			const FVector2d& LocalOffsetCm,
			double AltitudeCm = 0.0,
			double PlanetRadiusCm = FPlanet50KmProfile::RadiusCm,
			const FVector3d& PlanetNorthAxis = FVector3d(0.0, 0.0, 1.0));

		/** Inverse of ExpMapDirection away from the anchor's antipode. */
		static FVector2d LogMapOffsetCm(
			const FVector3d& AnchorSurfaceDirection,
			const FVector3d& TargetSurfaceDirection,
			double PlanetRadiusCm = FPlanet50KmProfile::RadiusCm,
			const FVector3d& PlanetNorthAxis = FVector3d(0.0, 0.0, 1.0));

	private:
		FPlanetRegionService();

		TStaticArray<FPlanetRegionMetadata, FPlanet50KmProfile::RegionCount> Regions;
	};
}
