#include "RedPlanetRegionBlueprintLibrary.h"

#include "RedPlanetRegionService.h"

namespace
{
	FName ToArchetypeTag(const RedPlanet::ERegionArchetype Archetype)
	{
		switch (Archetype)
		{
		case RedPlanet::ERegionArchetype::CoralCanopyCoast:
			return TEXT("CoralCanopyCoast");
		case RedPlanet::ERegionArchetype::EmberMagentaRift:
			return TEXT("EmberMagentaRift");
		case RedPlanet::ERegionArchetype::FungalCathedral:
			return TEXT("FungalCathedral");
		case RedPlanet::ERegionArchetype::MonolithicPillarCavern:
			return TEXT("MonolithicPillarCavern");
		case RedPlanet::ERegionArchetype::VerdantSkyPlateau:
			return TEXT("VerdantSkyPlateau");
		case RedPlanet::ERegionArchetype::PortalOasis:
			return TEXT("PortalOasis");
		case RedPlanet::ERegionArchetype::CliffsideSpaceport:
			return TEXT("CliffsideSpaceport");
		default:
			return NAME_None;
		}
	}

	FRedPlanetRegionQuery ToBlueprintQuery(const RedPlanet::FPlanetRegionMetadata& Metadata)
	{
		FRedPlanetRegionQuery Result;
		Result.RegionIndex = Metadata.RegionIndex;
		Result.Seed = static_cast<int64>(Metadata.StableSeed);
		Result.VariationIndex = static_cast<int32>(Metadata.VariationIndex);
		Result.ArchetypeTag = ToArchetypeTag(Metadata.Archetype);
		Result.UnitSite = FVector(Metadata.UnitSite);
		Result.NominalAreaSquareKm = Metadata.NominalAreaSquareKm;
		Result.SuggestedHubRadiusCm = Metadata.SuggestedHubRadiusCm;
		Result.SuggestedFlattenCoreRadiusCm = Metadata.SuggestedFlattenCoreRadiusCm;
		Result.SuggestedFlattenBlendRadiusCm = Metadata.SuggestedFlattenBlendRadiusCm;
		Result.Temperature01 = Metadata.Temperature01;
		Result.Moisture01 = Metadata.Moisture01;
		Result.AlienIntensity01 = Metadata.AlienIntensity01;
		Result.ElevationBias = Metadata.ElevationBias;
		return Result;
	}
}

int32 URedPlanetRegionBlueprintLibrary::GetPlanetRegionCount()
{
	return RedPlanet::FPlanet50KmProfile::RegionCount;
}

bool URedPlanetRegionBlueprintLibrary::GetPlanetRegion(
	const int32 RegionIndex,
	FRedPlanetRegionQuery& OutRegion)
{
	if (RegionIndex < 0 || RegionIndex >= RedPlanet::FPlanet50KmProfile::RegionCount)
	{
		OutRegion = FRedPlanetRegionQuery();
		return false;
	}

	OutRegion = ToBlueprintQuery(
		RedPlanet::FPlanetRegionService::Get().GetRegionChecked(RegionIndex));
	return true;
}

TArray<FRedPlanetRegionQuery> URedPlanetRegionBlueprintLibrary::GetAllPlanetRegions()
{
	TArray<FRedPlanetRegionQuery> Result;
	Result.Reserve(RedPlanet::FPlanet50KmProfile::RegionCount);
	for (const RedPlanet::FPlanetRegionMetadata& Metadata
		: RedPlanet::FPlanetRegionService::Get().GetRegions())
	{
		Result.Add(ToBlueprintQuery(Metadata));
	}
	return Result;
}

FRedPlanetRegionQuery URedPlanetRegionBlueprintLibrary::FindNearestPlanetRegion(
	const FVector& SurfaceDirection)
{
	const RedPlanet::FPlanetRegionService& Service = RedPlanet::FPlanetRegionService::Get();
	return ToBlueprintQuery(Service.GetRegionChecked(Service.FindNearestRegion(SurfaceDirection)));
}

TArray<FRedPlanetRegionBlendEntry> URedPlanetRegionBlueprintLibrary::SamplePlanetRegionBlend(
	const FVector& SurfaceDirection,
	const int32 MaxContributors,
	const double SigmaRadians)
{
	const RedPlanet::FPlanetRegionService& Service = RedPlanet::FPlanetRegionService::Get();
	const RedPlanet::FPlanetRegionBlend Blend = Service.SampleBlendedRegions(
		SurfaceDirection,
		FMath::Clamp(MaxContributors, 1, RedPlanet::FPlanetRegionBlend::MaxContributors),
		FMath::Max(SigmaRadians, 1.0e-6));

	TArray<FRedPlanetRegionBlendEntry> Result;
	Result.Reserve(Blend.NumContributors);
	for (int32 ContributorIndex = 0; ContributorIndex < Blend.NumContributors; ++ContributorIndex)
	{
		const RedPlanet::FPlanetRegionWeight& Source = Blend.Contributors[ContributorIndex];
		FRedPlanetRegionBlendEntry& Entry = Result.AddDefaulted_GetRef();
		Entry.Region = ToBlueprintQuery(Service.GetRegionChecked(Source.RegionIndex));
		Entry.GreatCircleDistanceRadians = Source.GreatCircleDistanceRadians;
		Entry.Weight = Source.Weight;
	}
	return Result;
}

FRedPlanetTangentFrameQuery URedPlanetRegionBlueprintLibrary::MakePlanetTangentFrame(
	const FVector& SurfaceDirection,
	const FVector& PlanetNorthAxis)
{
	const RedPlanet::FPlanetTangentFrame Frame =
		RedPlanet::FPlanetRegionService::MakeTangentFrame(SurfaceDirection, PlanetNorthAxis);
	FRedPlanetTangentFrameQuery Result;
	Result.UnitUp = FVector(Frame.UnitUp);
	Result.UnitEast = FVector(Frame.UnitEast);
	Result.UnitNorth = FVector(Frame.UnitNorth);
	return Result;
}

FVector URedPlanetRegionBlueprintLibrary::PlanetTangentOffsetToDirection(
	const FVector& AnchorSurfaceDirection,
	const FVector2D& LocalOffsetCm,
	const double PlanetRadiusCm,
	const FVector& PlanetNorthAxis)
{
	return FVector(RedPlanet::FPlanetRegionService::ExpMapDirection(
		AnchorSurfaceDirection,
		FVector2d(LocalOffsetCm.X, LocalOffsetCm.Y),
		PlanetRadiusCm,
		PlanetNorthAxis));
}

FVector URedPlanetRegionBlueprintLibrary::PlanetTangentOffsetToPosition(
	const FVector& PlanetCenter,
	const FVector& AnchorSurfaceDirection,
	const FVector2D& LocalOffsetCm,
	const double AltitudeCm,
	const double PlanetRadiusCm,
	const FVector& PlanetNorthAxis)
{
	return FVector(RedPlanet::FPlanetRegionService::ExpMapPosition(
		PlanetCenter,
		AnchorSurfaceDirection,
		FVector2d(LocalOffsetCm.X, LocalOffsetCm.Y),
		AltitudeCm,
		PlanetRadiusCm,
		PlanetNorthAxis));
}

FVector2D URedPlanetRegionBlueprintLibrary::PlanetDirectionToTangentOffset(
	const FVector& AnchorSurfaceDirection,
	const FVector& TargetSurfaceDirection,
	const double PlanetRadiusCm,
	const FVector& PlanetNorthAxis)
{
	const FVector2d Offset = RedPlanet::FPlanetRegionService::LogMapOffsetCm(
		AnchorSurfaceDirection,
		TargetSurfaceDirection,
		PlanetRadiusCm,
		PlanetNorthAxis);
	return FVector2D(Offset.X, Offset.Y);
}
