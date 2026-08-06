#include "RedStylizedPlanetPresentationAdapter.h"

namespace RedStylizedPlanetPresentation
{
	float ClampWeight(const float Value)
	{
		return FMath::IsFinite(Value) ? FMath::Clamp(Value, 0.0f, 1.0f) : 0.0f;
	}

	float SafeProtectionWeight(const FRedPlanetHubProtectionQuery& Query)
	{
		return Query.bQueryValid ? ClampWeight(Query.ProtectionWeight) : 1.0f;
	}

	bool IsEligibleFoliageRole(const ERedWorldAssetRole Role)
	{
		return Role == ERedWorldAssetRole::BiomeAnchor
			|| Role == ERedWorldAssetRole::Satellite
			|| Role == ERedWorldAssetRole::GroundCover;
	}

	void ResolveApprovedEntries(
		const FRedStylizedBiomePresentationBinding& Binding,
		const TArray<FName>& EntryIds,
		const bool bRockEntries,
		TArray<FRedWorldAssetPaletteEntry>& OutEntries)
	{
		OutEntries.Reset();
		if (!Binding.AssetPalette)
		{
			return;
		}

		TSet<FName> AddedIds;
		for (const FName EntryId : EntryIds)
		{
			FRedWorldAssetPaletteEntry Entry;
			if (EntryId.IsNone()
				|| AddedIds.Contains(EntryId)
				|| !Binding.AssetPalette->FindEntry(EntryId, Entry)
				|| Entry.Mesh.IsNull()
				|| !Entry.bApprovedForPCG
				|| Entry.bHandPlacementOnly)
			{
				continue;
			}

			const bool bRoleEligible = bRockEntries
				? Entry.Role == ERedWorldAssetRole::Rock
				: IsEligibleFoliageRole(Entry.Role);
			if (!bRoleEligible)
			{
				continue;
			}

			AddedIds.Add(EntryId);
			OutEntries.Add(MoveTemp(Entry));
		}
	}

	FRedStylizedSurfaceLayerWeights DecodeSurfaceLayers(
		const FRedStylizedPlanetSourceSignal& SourceSignal)
	{
		FRedStylizedSurfaceLayerWeights Result;
		Result.Water = ClampWeight(SourceSignal.TerrainLayerVertexWeights.R);
		Result.Grass = ClampWeight(SourceSignal.TerrainLayerVertexWeights.G);
		Result.Rock = ClampWeight(SourceSignal.TerrainLayerVertexWeights.B);
		Result.Snow = ClampWeight(SourceSignal.TerrainLayerVertexWeights.A);
		Result.Beach = ClampWeight(SourceSignal.AuxiliaryLayerWeights.X);
		Result.DesertSand = ClampWeight(SourceSignal.AuxiliaryLayerWeights.Y);
		return Result;
	}

	FName FindDominantSurfaceLayer(const FRedStylizedSurfaceLayerWeights& Weights)
	{
		struct FLayerCandidate
		{
			FName Id;
			float Weight;
		};

		// The ordering makes equal water/beach weights resolve to Water, preserving
		// the generator's below-sea classification.
		const FLayerCandidate Candidates[] = {
			{ TEXT("Water"), Weights.Water },
			{ TEXT("Grass"), Weights.Grass },
			{ TEXT("Rock"), Weights.Rock },
			{ TEXT("Snow"), Weights.Snow },
			{ TEXT("Beach"), Weights.Beach },
			{ TEXT("DesertSand"), Weights.DesertSand }
		};

		FName BestId = NAME_None;
		float BestWeight = 0.0f;
		for (const FLayerCandidate& Candidate : Candidates)
		{
			if (Candidate.Weight > BestWeight)
			{
				BestId = Candidate.Id;
				BestWeight = Candidate.Weight;
			}
		}
		return BestId;
	}

	const FRedPlanetHubProtectionQuery& ChooseStrongestReservation(
		const FRedPlanetHubProtectionQuery& FoliageProtection,
		const FRedPlanetHubProtectionQuery& RockProtection,
		const FRedPlanetHubProtectionQuery& WaterProtection)
	{
		const FRedPlanetHubProtectionQuery* Best = &FoliageProtection;
		float BestWeight = SafeProtectionWeight(FoliageProtection);
		for (const FRedPlanetHubProtectionQuery* Candidate :
			{ &RockProtection, &WaterProtection })
		{
			const float CandidateWeight = SafeProtectionWeight(*Candidate);
			if (CandidateWeight > BestWeight)
			{
				Best = Candidate;
				BestWeight = CandidateWeight;
			}
		}
		return *Best;
	}
}

const FRedStylizedBiomePresentationBinding&
URedStylizedPlanetPresentationProfile::ResolveBinding(
	const FRedStylizedPlanetSourceSignal& SourceSignal,
	bool& bOutUsedFallback) const
{
	bOutUsedFallback = false;

	if (SourceContract == ERedStylizedPlanetSourceContract::PPG10NamedBiomes
		&& !SourceSignal.NamedBiomeId.IsNone())
	{
		for (const FRedStylizedBiomePresentationBinding& Binding : BiomeBindings)
		{
			if (Binding.SourceBiomeId == SourceSignal.NamedBiomeId)
			{
				return Binding;
			}
		}
	}
	else if (SourceContract
		== ERedStylizedPlanetSourceContract::PlanetGen14VertexLayers)
	{
		for (const FRedStylizedBiomePresentationBinding& Binding : BiomeBindings)
		{
			if (Binding.SourceBiomeIndex == SourceSignal.ClimateBiomeIndex)
			{
				return Binding;
			}
		}
	}

	bOutUsedFallback = true;
	return FallbackBinding;
}

FRedStylizedPlanetPresentationResult
URedStylizedPlanetPresentationAdapter::EvaluateFromSignals(
	const URedStylizedPlanetPresentationProfile* Profile,
	const FRedStylizedPlanetSourceSignal& SourceSignal,
	const FRedPlanetHubProtectionQuery& FoliageProtection,
	const FRedPlanetHubProtectionQuery& RockProtection,
	const FRedPlanetHubProtectionQuery& WaterDecorationProtection)
{
	using namespace RedStylizedPlanetPresentation;

	FRedStylizedPlanetPresentationResult Result;
	Result.SurfaceLayers = DecodeSurfaceLayers(SourceSignal);
	Result.DominantSurfaceLayer = FindDominantSurfaceLayer(Result.SurfaceLayers);

	const float FoliageProtectionWeight =
		SafeProtectionWeight(FoliageProtection);
	const float RockProtectionWeight =
		SafeProtectionWeight(RockProtection);
	const float WaterProtectionWeight =
		SafeProtectionWeight(WaterDecorationProtection);

	Result.bProtectionQueryValid =
		FoliageProtection.bQueryValid
		&& RockProtection.bQueryValid
		&& WaterDecorationProtection.bQueryValid;
	Result.AuthoredHubBlendWeight = FMath::Max3(
		FoliageProtectionWeight,
		RockProtectionWeight,
		WaterProtectionWeight);
	Result.ProceduralTerrainPresentationWeight =
		1.0f - Result.AuthoredHubBlendWeight;
	Result.ProceduralFoliageWeight = 1.0f - FoliageProtectionWeight;
	Result.ProceduralRockWeight = 1.0f - RockProtectionWeight;
	Result.ProceduralWaterDecorationWeight = 1.0f - WaterProtectionWeight;

	const FRedPlanetHubProtectionQuery& StrongestReservation =
		ChooseStrongestReservation(
			FoliageProtection, RockProtection, WaterDecorationProtection);
	if (StrongestReservation.bQueryValid)
	{
		Result.ReservationId = StrongestReservation.ReservationId;
		Result.ReservationGuid = StrongestReservation.StableGuid;
	}

	if (!Profile || Profile->ProfileId.IsNone() || Profile->BodyId.IsNone())
	{
		return Result;
	}

	const FRedStylizedBiomePresentationBinding& Binding =
		Profile->ResolveBinding(SourceSignal, Result.bUsedFallbackBiomeBinding);
	Result.ResolvedBiomeId = Binding.SourceBiomeId;
	Result.ResolvedBiomeIndex = Binding.SourceBiomeIndex;

	Result.TerrainMaterialHook = Profile->StylizedTerrainMaterialHook;
	if (Profile->SourceContract
			== ERedStylizedPlanetSourceContract::PPG10NamedBiomes
		&& !Binding.PPGSurfaceMaterialHook.IsNull())
	{
		Result.TerrainMaterialHook = Binding.PPGSurfaceMaterialHook;
	}
	Result.WaterMaterialHook = Profile->StylizedWaterMaterialHook;
	Result.bHasTerrainMaterialHook = !Result.TerrainMaterialHook.IsNull();
	Result.bHasWaterMaterialHook = !Result.WaterMaterialHook.IsNull();

	ResolveApprovedEntries(
		Binding, Binding.FoliageEntryIds, false, Result.FoliageMeshHooks);
	ResolveApprovedEntries(
		Binding, Binding.RockEntryIds, true, Result.RockMeshHooks);

	Result.bMappingValid = true;
	Result.bReadyForScratchBinding =
		Result.bMappingValid
		&& Result.bProtectionQueryValid
		&& Result.bHasTerrainMaterialHook;
	return Result;
}

FRedStylizedPlanetPresentationResult
URedStylizedPlanetPresentationAdapter::EvaluateAtWorldPoint(
	const UObject* WorldContextObject,
	const URedStylizedPlanetPresentationProfile* Profile,
	const FRedStylizedPlanetSourceSignal& SourceSignal,
	const FVector& WorldPoint)
{
	const FName BodyId = Profile ? Profile->BodyId : NAME_None;
	const FRedPlanetHubProtectionQuery FoliageProtection =
		URedPlanetHubReservationRegistry::QueryFeatureProtection(
			WorldContextObject, BodyId, TEXT("Foliage"), WorldPoint);
	const FRedPlanetHubProtectionQuery RockProtection =
		URedPlanetHubReservationRegistry::QueryFeatureProtection(
			WorldContextObject, BodyId, TEXT("Rock"), WorldPoint);
	const FRedPlanetHubProtectionQuery WaterDecorationProtection =
		URedPlanetHubReservationRegistry::QueryFeatureProtection(
			WorldContextObject, BodyId, TEXT("Water"), WorldPoint);

	return EvaluateFromSignals(
		Profile,
		SourceSignal,
		FoliageProtection,
		RockProtection,
		WaterDecorationProtection);
}
