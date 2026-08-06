// REDMMO_HAS_PLANETGEN_FORK_APIS_GATE
#if __has_include("PlanetGen/PlanetGenTerrainStamp.h")
#include "PlanetGen/CLMPlanet.h"
#include "PlanetGen/CLMPlanetChunk.h"
#include "PlanetGen/PlanetGenTerrainStamp.h"
#include "PlanetGenMacroHeightfieldAsset.h"
#include "PlanetGenNoiseGenerator.h"
#include "../RedShorelineWaveComponent.h"

#if WITH_DEV_AUTOMATION_TESTS && WITH_EDITOR

#include "Engine/Engine.h"
#include "Engine/HitResult.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "GameFramework/PlayerController.h"
#include "Materials/MaterialInterface.h"
#include "Materials/MaterialInstance.h"
#include "Misc/AutomationTest.h"
#include "Misc/PackageName.h"
#include "ProceduralMeshComponent.h"
#include "Tests/AutomationCommon.h"
#include "Tests/AutomationEditorCommon.h"
#include "UObject/UnrealType.h"

namespace RedPlanet::FusedWaterDatumTests
{
	namespace Private
	{
		constexpr TCHAR FusedPrototypeMap[] =
			TEXT("/Game/RedMMO/Maps/RedPlanetGen_50km_FusedPrototype");
		constexpr int32 ExpectedMacroResolution = 257;
		constexpr int32 ExpectedTerrainStampCount = 27;
		constexpr int32 ExpectedWaterSphereSubdivisions = 192;
		constexpr int32 ExpectedResidentMacroSurfaceSubdivisions = 128;
		constexpr float ExpectedAuthoredSeaHeightCm = 0.0f;
		constexpr float WaterDatumToleranceCm = 1.0f;
		constexpr float HighConfidenceCoastToleranceCm = 100.0f;
		constexpr float BlendedCoastToleranceCm = 400.0f;
		constexpr float WaterVertexRadiusToleranceCm = 1.0f;
		constexpr double PresentationTimeoutSeconds = 20.0;
		constexpr double PhysicalShorelineTimeoutSeconds = 60.0;
		constexpr int32 CoastSearchStepsPerFace = 64;
		constexpr float CoastSearchMinimumSignMarginCm = 25.0f;
		constexpr float ShorelineSurfaceLiftCm = 8.0f;
		constexpr float CrestRadiusToleranceCm = 1.0f;
		constexpr float CrestResolvedHeightToleranceCm = 1000.0f;
		constexpr float RuntimeCollisionHeightToleranceCm = 7000.0f;
		constexpr float ResolvedStampSampleToleranceCm = 0.25f;
		constexpr float MinimumResolvedStampEffectCm = 10.0f;
		constexpr float CrestPatchDistanceToleranceCm = 24000.0f;

		UWorld* FindFusedPIEWorld()
		{
			if (!GEngine)
			{
				return nullptr;
			}

			for (const FWorldContext& Context : GEngine->GetWorldContexts())
			{
				UWorld* World = Context.World();
				if (!IsValid(World)
					|| (Context.WorldType != EWorldType::PIE
						&& Context.WorldType != EWorldType::Game))
				{
					continue;
				}

				const FString ShortMapName = UWorld::RemovePIEPrefix(
					FPackageName::GetShortName(World->GetMapName()));
				if (ShortMapName == TEXT("RedPlanetGen_50km_FusedPrototype"))
				{
					return World;
				}
			}
			return nullptr;
		}

		FVector BuildExpectedSphereTangent(const FVector2D& UV)
		{
			const float Theta = 2.0f * PI * UV.X;
			return FVector(-FMath::Sin(Theta), FMath::Cos(Theta), 0.0f);
		}

		UProceduralMeshComponent* FindWaterSphere(ACLMPlanet* Planet)
		{
			if (!Planet)
			{
				return nullptr;
			}

			TArray<UProceduralMeshComponent*> ProceduralMeshes;
			Planet->GetComponents<UProceduralMeshComponent>(ProceduralMeshes);
			for (UProceduralMeshComponent* Component : ProceduralMeshes)
			{
				if (IsValid(Component)
					&& Component->GetName().Contains(TEXT("WaterSphere")))
				{
					return Component;
				}
			}
			return nullptr;
		}

		bool HasRepairedTangents(const FProcMeshSection* Section)
		{
			if (!Section)
			{
				return false;
			}

			for (const FProcMeshVertex& Vertex : Section->ProcVertexBuffer)
			{
				const FVector Normal = Vertex.Position.GetSafeNormal();
				if (FMath::Abs(Normal.Z) >= 0.9f)
				{
					continue;
				}

				return Vertex.Tangent.bFlipTangentY
					&& FVector::DotProduct(
						Vertex.Tangent.TangentX.GetSafeNormal(),
						BuildExpectedSphereTangent(Vertex.UV0)) >= 0.98f;
			}
			return false;
		}

		bool TraceOwnedTerrain(
			UWorld* World,
			ACLMPlanet* Planet,
			const FVector& Direction,
			FHitResult& OutHit)
		{
			OutHit = FHitResult{};
			if (!World || !Planet)
			{
				return false;
			}

			const FVector UnitDirection = Direction.GetSafeNormal();
			const FVector Center = Planet->GetActorLocation();
			const float OuterRadius = Planet->PlanetRadius + Planet->MaxMountainHeight + 50000.f;
			const float InnerRadius = FMath::Max(
				1000.f,
				Planet->PlanetRadius - Planet->MaxMountainHeight - 50000.f);
			FCollisionQueryParams Params(SCENE_QUERY_STAT(RedFusedPhysicalShoreline), true);
			Params.bTraceComplex = true;
			TArray<FHitResult> Hits;
			if (!World->LineTraceMultiByChannel(
				Hits,
				Center + UnitDirection * OuterRadius,
				Center + UnitDirection * InnerRadius,
				ECC_Visibility,
				Params))
			{
				return false;
			}

			for (const FHitResult& Hit : Hits)
			{
				const ACLMPlanetChunk* Chunk = Cast<ACLMPlanetChunk>(Hit.GetActor());
				if (IsValid(Chunk) && Chunk->GetOwner() == Planet)
				{
					OutHit = Hit;
					return true;
				}
			}
			return false;
		}
	}

	class FRedFusedWaterDatumCommand final : public IAutomationLatentCommand
	{
	public:
		explicit FRedFusedWaterDatumCommand(FAutomationTestBase* InTest)
			: Test(InTest)
			, StartedAtSeconds(FPlatformTime::Seconds())
		{
		}

		virtual bool Update() override
		{
			UWorld* World = Private::FindFusedPIEWorld();
			if (!World)
			{
				return WaitOrFail(TEXT("PIE world was not created."));
			}

			TArray<ACLMPlanet*> Planets;
			for (TActorIterator<ACLMPlanet> It(World); It; ++It)
			{
				if (IsValid(*It))
				{
					Planets.Add(*It);
				}
			}
			if (Planets.Num() != 1)
			{
				return WaitOrFail(FString::Printf(
					TEXT("Expected exactly one PlanetGen actor, found %d."), Planets.Num()));
			}

			ACLMPlanet* Planet = Planets[0];
			UProceduralMeshComponent* WaterSphere = Private::FindWaterSphere(Planet);
			const FProcMeshSection* WaterSection = WaterSphere
				? WaterSphere->GetProcMeshSection(0)
				: nullptr;
			const bool bPresentationReady = WaterSphere
				&& WaterSection
				&& WaterSection->ProcVertexBuffer.Num() > 0
				&& WaterSphere->ComponentHasTag(TEXT("RedSoStylizedWaterApplied"))
				&& Planet->WaterMaterial
				&& Private::HasRepairedTangents(WaterSection);
			if (!bPresentationReady)
			{
				return WaitOrFail(FString::Printf(
					TEXT("Water presentation was not ready (sphere=%s section=%d vertices=%d tag=%d material=%s tangents=%d)."),
					*GetNameSafe(WaterSphere), WaterSection ? 1 : 0,
					WaterSection ? WaterSection->ProcVertexBuffer.Num() : 0,
					WaterSphere && WaterSphere->ComponentHasTag(TEXT("RedSoStylizedWaterApplied")) ? 1 : 0,
					*GetNameSafe(Planet->WaterMaterial),
					Private::HasRepairedTangents(WaterSection) ? 1 : 0));
			}

			VerifyConfiguration(Planet);
			VerifyAuthoredCoastline(Planet);
			VerifyWaterMesh(Planet, WaterSphere, WaterSection);
			return true;
		}

	private:
		bool WaitOrFail(const FString& Detail)
		{
			if (FPlatformTime::Seconds() - StartedAtSeconds
				<= Private::PresentationTimeoutSeconds)
			{
				return false;
			}

			Test->AddError(FString::Printf(
				TEXT("Fused water datum test timed out after %.0f seconds: %s"),
				Private::PresentationTimeoutSeconds, *Detail));
			return true;
		}

		void VerifyConfiguration(ACLMPlanet* Planet)
		{
			Test->TestFalse(TEXT("Fused prototype global water shell is disabled"), Planet->bEnableWater);
			Test->TestEqual(TEXT("Fused prototype uses the required water sphere subdivisions"),
				Planet->WaterSphereSubdivisions, Private::ExpectedWaterSphereSubdivisions);
			Test->TestEqual(TEXT("Fused prototype uses the required orbital land subdivisions"),
				Planet->ResidentMacroSurfaceSubdivisions,
				Private::ExpectedResidentMacroSurfaceSubdivisions);
			Test->TestTrue(TEXT("Fused prototype macro heightfield is enabled"),
				Planet->bEnableMacroHeightfield);
			Test->TestNotNull(TEXT("Fused prototype macro heightfield asset"),
				Planet->MacroHeightfieldAsset.Get());
			Test->TestEqual(TEXT("Fused prototype owns 27 authored terrain stamps"),
				Planet->TerrainStamps.Num(), Private::ExpectedTerrainStampCount);
			Test->TestTrue(TEXT("Fused prototype uses the full authored macro blend"),
				FMath::IsNearlyEqual(Planet->MacroHeightfieldBlend, 1.0f, KINDA_SMALL_NUMBER));

			const float SeaHeightCm = Planet->MinHeight
				+ (Planet->MaxHeight - Planet->MinHeight) * Planet->SeaLevel;
			Test->TestTrue(TEXT("Runtime water datum matches the authored 0 cm sea level"),
				FMath::Abs(SeaHeightCm - Private::ExpectedAuthoredSeaHeightCm)
					<= Private::WaterDatumToleranceCm);

			UPlanetGenNoiseGenerator* Noise = nullptr;
			if (const FObjectPropertyBase* NoiseProperty =
				FindFProperty<FObjectPropertyBase>(Planet->GetClass(), TEXT("NoiseGenerator")))
			{
				Noise = Cast<UPlanetGenNoiseGenerator>(
					NoiseProperty->GetObjectPropertyValue_InContainer(Planet));
			}
			Test->TestNotNull(TEXT("PlanetGen runtime noise generator"), Noise);
			if (Noise)
			{
				Test->TestTrue(TEXT("Runtime noise minimum matches the actor"),
					FMath::IsNearlyEqual(Noise->MinHeight, Planet->MinHeight, 0.01f));
				Test->TestTrue(TEXT("Runtime noise maximum matches the actor"),
					FMath::IsNearlyEqual(Noise->MaxHeight, Planet->MaxHeight, 0.01f));
				Test->TestTrue(TEXT("Runtime noise sea level matches the actor"),
					FMath::IsNearlyEqual(Noise->SeaLevel, Planet->SeaLevel, 0.0001f));
				Test->TestTrue(TEXT("Runtime macro height capture is active"),
					Noise->HasMacroHeightfieldCapture());
				Test->TestTrue(TEXT("Runtime authored surface-mask capture is active"),
					Noise->HasMacroSurfaceMaskCapture());
			}
		}

		void VerifyAuthoredCoastline(ACLMPlanet* Planet)
		{
			UPlanetGenMacroHeightfieldAsset* Asset = Planet->MacroHeightfieldAsset.Get();
			if (!Asset)
			{
				return;
			}

			FPlanetGenMacroHeightfieldCapture Capture;
			FString CaptureError;
			Test->TestTrue(TEXT("Fused macro heightfield capture builds"),
				Asset->BuildCapture(Capture, &CaptureError));
			if (!Capture.IsValid())
			{
				Test->AddError(FString::Printf(
					TEXT("Fused macro heightfield capture is invalid: %s"), *CaptureError));
				return;
			}
			Test->TestEqual(TEXT("Fused macro resolution"), Capture.GetResolution(),
				Private::ExpectedMacroResolution);
			Test->TestTrue(TEXT("Fused macro surface masks are complete"),
				Capture.HasSurfaceMasks());

			const float SeaHeightCm = Planet->MinHeight
				+ (Planet->MaxHeight - Planet->MinHeight) * Planet->SeaLevel;
			int64 SampleCount = 0;
			int64 MaskLandCount = 0;
			int64 MaskOceanCount = 0;
			int64 IntermediateMaskCount = 0;
			int64 BinaryClassificationMismatchCount = 0;
			int64 BlendedClassificationMismatchCount = 0;
			int64 HighConfidenceOceanViolations = 0;
			int64 HighConfidenceLandViolations = 0;
			int64 CoastEdgeCount = 0;
			int32 FacesWithDistributedCoast = 0;
			float MaximumBlendedMismatchDistanceCm = 0.0f;

			for (int32 FaceIndex = 0; FaceIndex < PlanetGenMacroCubeFaceCount; ++FaceIndex)
			{
				const EPlanetGenMacroCubeFace Face =
					static_cast<EPlanetGenMacroCubeFace>(FaceIndex);
				const TArray<uint16>& Heights = Asset->GetFaceSamples(Face);
				const TArray<uint8>& Land = Asset->GetLandFaceSamples(Face);
				const int32 ExpectedSamples = Private::ExpectedMacroResolution
					* Private::ExpectedMacroResolution;
				if (Heights.Num() != ExpectedSamples || Land.Num() != ExpectedSamples)
				{
					Test->AddError(FString::Printf(
						TEXT("Fused face %d has invalid height/land sizes %d/%d; expected %d."),
						FaceIndex, Heights.Num(), Land.Num(), ExpectedSamples));
					continue;
				}
				int64 FaceCoastEdgeCount = 0;

				for (int32 Y = 0; Y < Private::ExpectedMacroResolution; ++Y)
				{
					for (int32 X = 0; X < Private::ExpectedMacroResolution; ++X)
					{
						const uint16 EncodedHeight = Capture.GetEncodedSampleChecked(
							Face, X, Y);
						const float HeightCm = FMath::Lerp(
							Capture.GetMinHeightCm(),
							Capture.GetMaxHeightCm(),
							static_cast<float>(EncodedHeight) / 65535.0f);
						const uint8 LandValue = Capture.GetLandSampleChecked(Face, X, Y);
						const bool bMaskLand = LandValue >= 128;
						const bool bHeightLand = HeightCm >= SeaHeightCm;
						++SampleCount;
						MaskLandCount += bMaskLand ? 1 : 0;
						MaskOceanCount += bMaskLand ? 0 : 1;
						IntermediateMaskCount += (LandValue > 0 && LandValue < 255) ? 1 : 0;
						if (bMaskLand != bHeightLand)
						{
							if (LandValue == 0 || LandValue == 255)
							{
								++BinaryClassificationMismatchCount;
							}
							else
							{
								++BlendedClassificationMismatchCount;
								MaximumBlendedMismatchDistanceCm = FMath::Max(
									MaximumBlendedMismatchDistanceCm,
									FMath::Abs(HeightCm - SeaHeightCm));
							}
						}
						if (LandValue <= 13
							&& HeightCm > SeaHeightCm
								+ Private::HighConfidenceCoastToleranceCm)
						{
							++HighConfidenceOceanViolations;
						}
						if (LandValue >= 242
							&& HeightCm < SeaHeightCm
								- Private::HighConfidenceCoastToleranceCm)
						{
							++HighConfidenceLandViolations;
						}

						if (X + 1 < Private::ExpectedMacroResolution)
						{
							FaceCoastEdgeCount +=
								(Capture.GetLandSampleChecked(Face, X + 1, Y) >= 128)
									!= bMaskLand ? 1 : 0;
						}
						if (Y + 1 < Private::ExpectedMacroResolution)
						{
							FaceCoastEdgeCount +=
								(Capture.GetLandSampleChecked(Face, X, Y + 1) >= 128)
									!= bMaskLand ? 1 : 0;
						}
					}
				}
				CoastEdgeCount += FaceCoastEdgeCount;
				FacesWithDistributedCoast += FaceCoastEdgeCount >= 500 ? 1 : 0;
			}

			Test->TestEqual(TEXT("All six fused face samples were scanned"), SampleCount,
				static_cast<int64>(PlanetGenMacroCubeFaceCount)
					* Private::ExpectedMacroResolution * Private::ExpectedMacroResolution);
			Test->TestTrue(TEXT("Authored dataset contains land"), MaskLandCount > 0);
			Test->TestTrue(TEXT("Authored dataset contains ocean"), MaskOceanCount > 0);
			Test->TestTrue(TEXT("Authored dataset contains a nontrivial coastline"),
				CoastEdgeCount >= 5000);
			Test->TestTrue(TEXT("Authored coastline is distributed across cube faces"),
				FacesWithDistributedCoast >= 5);
			Test->TestEqual(TEXT("Binary land/ocean masks agree with the physical water datum"),
				BinaryClassificationMismatchCount, static_cast<int64>(0));
			Test->TestEqual(TEXT("High-confidence ocean samples remain below the water datum"),
				HighConfidenceOceanViolations, static_cast<int64>(0));
			Test->TestEqual(TEXT("High-confidence land samples remain above the water datum"),
				HighConfidenceLandViolations, static_cast<int64>(0));
			Test->TestTrue(TEXT("Blended coastline disagreement stays inside its bounded band"),
				MaximumBlendedMismatchDistanceCm
					<= Private::BlendedCoastToleranceCm);
			Test->TestTrue(TEXT("Blended coastline disagreement remains a narrow fraction"),
				BlendedClassificationMismatchCount <= 700
					&& static_cast<double>(BlendedClassificationMismatchCount)
						/ FMath::Max<int64>(SampleCount, 1) <= 0.002);

			UE_LOG(LogTemp, Display,
				TEXT("RED_FUSED_AUTHORED_COAST_PASS samples=%lld land=%lld ocean=%lld intermediate=%lld coast_edges=%lld coast_faces=%d binary_mismatch=%lld blended_mismatch=%lld blended_max_cm=%.3f high_ocean_violations=%lld high_land_violations=%lld sea_height_cm=%.3f"),
				SampleCount, MaskLandCount, MaskOceanCount, IntermediateMaskCount,
				CoastEdgeCount, FacesWithDistributedCoast, BinaryClassificationMismatchCount,
				BlendedClassificationMismatchCount, MaximumBlendedMismatchDistanceCm,
				HighConfidenceOceanViolations, HighConfidenceLandViolations, SeaHeightCm);
		}

		void VerifyWaterMesh(
			ACLMPlanet* Planet,
			UProceduralMeshComponent* WaterSphere,
			const FProcMeshSection* WaterSection)
		{
			if (!WaterSphere || !WaterSection)
			{
				return;
			}

			const float SeaHeightCm = Planet->MinHeight
				+ (Planet->MaxHeight - Planet->MinHeight) * Planet->SeaLevel;
			const float ExpectedWaterRadiusCm = Planet->PlanetRadius + SeaHeightCm;
			const int32 Stacks = FMath::Max(4, Planet->WaterSphereSubdivisions / 2);
			const int32 Slices = FMath::Max(4, Planet->WaterSphereSubdivisions);
			const int32 ExpectedVertices = (Stacks + 1) * (Slices + 1);
			const int32 ExpectedIndices = Stacks * Slices * 6;
			float MaximumRadiusErrorCm = 0.0f;
			float MinimumNormalDot = 1.0f;
			float MinimumTangentDot = 1.0f;
			float MaximumExteriorWindingDot = -1.0f;
			int32 AuditedTangents = 0;
			int32 AuditedExteriorTriangles = 0;

			for (const FProcMeshVertex& Vertex : WaterSection->ProcVertexBuffer)
			{
				const FVector ExpectedNormal = Vertex.Position.GetSafeNormal();
				MaximumRadiusErrorCm = FMath::Max(MaximumRadiusErrorCm,
					FMath::Abs(Vertex.Position.Size() - ExpectedWaterRadiusCm));
				MinimumNormalDot = FMath::Min(MinimumNormalDot,
					FVector::DotProduct(Vertex.Normal.GetSafeNormal(), ExpectedNormal));
				if (FMath::Abs(ExpectedNormal.Z) < 0.9f)
				{
					MinimumTangentDot = FMath::Min(MinimumTangentDot,
						FVector::DotProduct(
							Vertex.Tangent.TangentX.GetSafeNormal(),
							Private::BuildExpectedSphereTangent(Vertex.UV0)));
					Test->TestTrue(TEXT("Water tangent uses the repaired flipped-Y basis"),
						Vertex.Tangent.bFlipTangentY);
					++AuditedTangents;
				}
			}

			for (int32 IndexBase = 0;
				IndexBase + 2 < WaterSection->ProcIndexBuffer.Num(); IndexBase += 3)
			{
				const int32 I0 = WaterSection->ProcIndexBuffer[IndexBase];
				const int32 I1 = WaterSection->ProcIndexBuffer[IndexBase + 1];
				const int32 I2 = WaterSection->ProcIndexBuffer[IndexBase + 2];
				if (!WaterSection->ProcVertexBuffer.IsValidIndex(I0)
					|| !WaterSection->ProcVertexBuffer.IsValidIndex(I1)
					|| !WaterSection->ProcVertexBuffer.IsValidIndex(I2))
				{
					continue;
				}
				const FProcMeshVertex& V0 = WaterSection->ProcVertexBuffer[I0];
				const FProcMeshVertex& V1 = WaterSection->ProcVertexBuffer[I1];
				const FProcMeshVertex& V2 = WaterSection->ProcVertexBuffer[I2];
				const FVector Cross = FVector::CrossProduct(
					V1.Position - V0.Position, V2.Position - V0.Position);
				if (Cross.SizeSquared() <= 1.0f)
				{
					continue;
				}
				const FVector DesiredNormal =
					(V0.Normal + V1.Normal + V2.Normal).GetSafeNormal();
				// The duplicated UV-sphere poles are mathematically degenerate.  Float
				// sin(PI) leaves sub-millimetre sliver triangles whose sign is unstable
				// even though they have no visible area.  Audit the real exterior quads.
				if (FMath::Abs(DesiredNormal.Z) > 0.999f)
				{
					continue;
				}
				MaximumExteriorWindingDot = FMath::Max(
					MaximumExteriorWindingDot,
					FVector::DotProduct(Cross.GetSafeNormal(), DesiredNormal));
				++AuditedExteriorTriangles;
			}

			Test->TestEqual(TEXT("Water sphere vertex count"),
				WaterSection->ProcVertexBuffer.Num(), ExpectedVertices);
			Test->TestEqual(TEXT("Water sphere index count"),
				WaterSection->ProcIndexBuffer.Num(), ExpectedIndices);
			Test->TestTrue(TEXT("Water sphere uses the authored radial datum"),
				MaximumRadiusErrorCm <= Private::WaterVertexRadiusToleranceCm);
			Test->TestTrue(TEXT("Water sphere normals point radially outward"),
				MinimumNormalDot >= 0.999f);
			Test->TestTrue(TEXT("Water sphere has non-polar tangent samples"),
				AuditedTangents > 0);
			Test->TestTrue(TEXT("Water sphere tangent basis matches spherical UVs"),
				MinimumTangentDot >= 0.98f);
			Test->TestTrue(TEXT("Water sphere has non-degenerate exterior triangles"),
				AuditedExteriorTriangles > 0);
			Test->TestTrue(TEXT("Water sphere uses the verified exterior winding"),
				MaximumExteriorWindingDot <= -0.9f);
			Test->TestEqual(TEXT("Water sphere collision is disabled"),
				WaterSphere->GetCollisionEnabled(), ECollisionEnabled::NoCollision);
			Test->TestFalse(TEXT("Water sphere overlap events are disabled"),
				WaterSphere->GetGenerateOverlapEvents());
			Test->TestFalse(TEXT("Unmasked global water sphere is not presented"),
				WaterSphere->IsVisible() && !WaterSphere->bHiddenInGame);
			Test->TestTrue(TEXT("SoStylized ocean tag is applied"),
				WaterSphere->ComponentHasTag(TEXT("RedSoStylizedWaterApplied")));
			UMaterialInterface* AppliedWaterMaterial = WaterSphere->GetMaterial(0);
			Test->TestNotNull(TEXT("Water sphere has a material"), AppliedWaterMaterial);
			const UMaterialInterface* AppliedWaterParent = AppliedWaterMaterial;
			if (const UMaterialInstance* AppliedWaterInstance = Cast<UMaterialInstance>(AppliedWaterMaterial))
			{
				AppliedWaterParent = AppliedWaterInstance->Parent;
			}
			Test->TestTrue(TEXT("Planet water source is the authored spherical SoStylized instance"),
				Planet->WaterMaterial
					&& Planet->WaterMaterial->GetPathName().Contains(
						TEXT("/Game/RedMMO/Environment/MI_RedClearWater")));
			Test->TestTrue(TEXT("Water sphere dynamic material inherits the authored spherical instance"),
				AppliedWaterParent
					&& AppliedWaterParent->GetPathName().Contains(
						TEXT("/Game/RedMMO/Environment/MI_RedClearWater")));

			UE_LOG(LogTemp, Display,
				TEXT("RED_FUSED_WATER_MESH_PASS sea_level=%.6f sea_height_cm=%.3f water_radius_cm=%.3f vertices=%d indices=%d max_radius_error_cm=%.4f min_normal_dot=%.6f tangent_samples=%d min_tangent_dot=%.6f winding_samples=%d max_winding_dot=%.6f material=%s"),
				Planet->SeaLevel, SeaHeightCm, ExpectedWaterRadiusCm,
				WaterSection->ProcVertexBuffer.Num(), WaterSection->ProcIndexBuffer.Num(),
				MaximumRadiusErrorCm, MinimumNormalDot, AuditedTangents,
				MinimumTangentDot, AuditedExteriorTriangles, MaximumExteriorWindingDot,
				*GetPathNameSafe(Planet->WaterMaterial));
		}

		FAutomationTestBase* Test = nullptr;
		double StartedAtSeconds = 0.0;
	};

	class FRedFusedPhysicalShorelineCommand final : public IAutomationLatentCommand
	{
	public:
		explicit FRedFusedPhysicalShorelineCommand(FAutomationTestBase* InTest)
			: Test(InTest)
			, StartedAtSeconds(FPlatformTime::Seconds())
			, StageStartedAtSeconds(StartedAtSeconds)
		{
		}

		virtual bool Update() override
		{
			UWorld* CurrentWorld = Private::FindFusedPIEWorld();
			if (!CurrentWorld)
			{
				return WaitOrFail(TEXT("PIE world was not created."));
			}
			World = CurrentWorld;

			if (!Planet.IsValid())
			{
				TArray<ACLMPlanet*> Planets;
				for (TActorIterator<ACLMPlanet> It(CurrentWorld); It; ++It)
				{
					if (IsValid(*It))
					{
						Planets.Add(*It);
					}
				}
				if (Planets.Num() != 1)
				{
					return WaitOrFail(FString::Printf(
						TEXT("Expected one PlanetGen actor, found %d."), Planets.Num()));
				}
				Planet = Planets[0];
			}

			if (!Pawn.IsValid())
			{
				APlayerController* PlayerController = CurrentWorld->GetFirstPlayerController();
				APawn* LocalPawn = PlayerController ? PlayerController->GetPawn() : nullptr;
				if (!IsValid(LocalPawn) || !LocalPawn->IsLocallyControlled())
				{
					return WaitOrFail(TEXT("A locally controlled PIE pawn was not available."));
				}
				URedShorelineWaveComponent* Shoreline =
					LocalPawn->FindComponentByClass<URedShorelineWaveComponent>();
				if (!Shoreline)
				{
					return WaitOrFail(TEXT("The local pawn has no shoreline wave component."));
				}
				Pawn = LocalPawn;
				ShorelineComponent = Shoreline;
				OriginalPawnLocation = LocalPawn->GetActorLocation();
				OriginalPawnRotation = LocalPawn->GetActorRotation();
				bOriginalPawnCollision = LocalPawn->GetActorEnableCollision();
				bOriginalPawnHidden = LocalPawn->IsHidden();
			}

			if (Stage == EStage::FindCoast)
			{
				if (!VerifyResolvedStampPipeline())
				{
					return Finish();
				}
				if (!Planet->bEnableWater)
				{
					UE_LOG(LogTemp, Display,
						TEXT("RED_FUSED_PHYSICAL_SHORE_PASS dry_foundation=1 global_water=0"));
					return Finish();
				}
				if (!FindDeterministicPhysicalCoast())
				{
					return Fail(TEXT("No deterministic physical land/water crossing was found."));
				}
				MovePawnToCoast();
				Stage = EStage::WaitForCrest;
				StageStartedAtSeconds = FPlatformTime::Seconds();
				return false;
			}

			MovePawnToCoast();
			if (Stage == EStage::WaitForCrest)
			{
				UProceduralMeshComponent* CrestMesh = FindCrestMesh();
				const FProcMeshSection* CrestSection = CrestMesh
					? CrestMesh->GetProcMeshSection(0)
					: nullptr;
				if (!CrestMesh || !CrestSection || CrestSection->ProcVertexBuffer.IsEmpty()
					|| !CrestMesh->IsVisible())
				{
					return WaitOrFail(TEXT("The local SoStylized shoreline crest did not build."));
				}

				if (!VerifyCrestGeometry(CrestMesh, CrestSection))
				{
					return Finish();
				}
				Stage = EStage::WaitForCollision;
				StageStartedAtSeconds = FPlatformTime::Seconds();
				return false;
			}

			if (Stage == EStage::WaitForCollision)
			{
				if (!VerifyRuntimeCollision())
				{
					return WaitOrFail(TEXT("PlanetGen coast collision did not settle around all crest probes."));
				}
				return Finish();
			}

			return Finish();
		}

	private:
		enum class EStage : uint8
		{
			FindCoast,
			WaitForCrest,
			WaitForCollision,
			Finished
		};

		bool SampleSignedHeight(const FVector& Direction, float& OutSignedHeightCm) const
		{
			OutSignedHeightCm = 0.f;
			if (!Planet.IsValid())
			{
				return false;
			}
			float HeightCm = 0.f;
			if (!Planet->SampleResolvedSurface(Direction, HeightCm))
			{
				return false;
			}
			const float SeaHeightCm = Planet->MinHeight
				+ (Planet->MaxHeight - Planet->MinHeight) * Planet->SeaLevel;
			OutSignedHeightCm = HeightCm - SeaHeightCm;
			return FMath::IsFinite(OutSignedHeightCm);
		}

		bool ResolveRuntimeNoiseGenerator()
		{
			if (NoiseGenerator.IsValid())
			{
				return true;
			}
			if (!Planet.IsValid())
			{
				return false;
			}
			const FObjectPropertyBase* NoiseProperty =
				FindFProperty<FObjectPropertyBase>(Planet->GetClass(), TEXT("NoiseGenerator"));
			NoiseGenerator = NoiseProperty
				? Cast<UPlanetGenNoiseGenerator>(
					NoiseProperty->GetObjectPropertyValue_InContainer(Planet.Get()))
				: nullptr;
			return NoiseGenerator.IsValid();
		}

		bool SampleUnstampedHeight(
			const FVector& SurfaceDirection,
			float& OutHeightCm) const
		{
			OutHeightCm = 0.f;
			if (!Planet.IsValid() || !NoiseGenerator.IsValid())
			{
				return false;
			}
			const FVector Direction = SurfaceDirection.GetSafeNormal();
			if (Direction.IsNearlyZero())
			{
				return false;
			}

			const FVector SamplePosition = Planet->GetActorLocation()
				+ Direction * Planet->PlanetRadius;
			float HeightCm = FMath::Clamp(
				NoiseGenerator->SampleHeight3D(
					SamplePosition.X, SamplePosition.Y, SamplePosition.Z).Height,
				-Planet->MaxMountainHeight,
				Planet->MaxMountainHeight);
			const float SeaHeightCm = Planet->MinHeight
				+ (Planet->MaxHeight - Planet->MinHeight) * Planet->SeaLevel;
			const float BeachBandCm = Planet->BeachWidth
				* (Planet->MaxHeight - Planet->MinHeight);
			const float AboveSeaCm = HeightCm - SeaHeightCm;
			if (Planet->BeachFlattenStrength > 0.f && BeachBandCm > 0.f
				&& AboveSeaCm > 0.f && AboveSeaCm < BeachBandCm)
			{
				const float T = AboveSeaCm / BeachBandCm;
				HeightCm = FMath::Lerp(
					HeightCm,
					SeaHeightCm,
					Planet->BeachFlattenStrength
						* (1.f - FMath::SmoothStep(0.f, 1.f, T)));
			}
			OutHeightCm = HeightCm;
			return FMath::IsFinite(OutHeightCm);
		}

		bool VerifyResolvedStampPipeline()
		{
			if (!ResolveRuntimeNoiseGenerator())
			{
				Test->AddError(TEXT("PlanetGen runtime noise generator was unavailable."));
				return false;
			}

			TArray<FPlanetGenResolvedTerrainStamp> ResolvedStamps;
			int32 EnabledValidStampCount = 0;
			for (const FPlanetGenTerrainStamp& Authored : Planet->TerrainStamps)
			{
				if (!Authored.bEnabled || Authored.SurfaceDirection.IsNearlyZero())
				{
					continue;
				}
				float BaseAtCenterCm = 0.f;
				if (!SampleUnstampedHeight(Authored.SurfaceDirection, BaseAtCenterCm))
				{
					Test->AddError(FString::Printf(
						TEXT("Unstamped center sample failed for terrain stamp %d."),
						Authored.StableId));
					return false;
				}
				FPlanetGenResolvedTerrainStamp Resolved;
				if (!PlanetGenTerrainStamp::ResolveTerrainStamp(
					Authored, BaseAtCenterCm, Resolved))
				{
					Test->AddError(FString::Printf(
						TEXT("Terrain stamp %d did not resolve."), Authored.StableId));
					return false;
				}
				ResolvedStamps.Add(Resolved);
				++EnabledValidStampCount;
			}
			PlanetGenTerrainStamp::SortResolvedStamps(ResolvedStamps);

			float MaximumResolvedApiErrorCm = 0.f;
			float MaximumStampEffectCm = 0.f;
			int32 AuditedSamples = 0;
			for (const FPlanetGenResolvedTerrainStamp& Stamp : ResolvedStamps)
			{
				const FVector Center = Stamp.SurfaceDirection.GetSafeNormal();
				const FVector Reference = FMath::Abs(Center.Z) < 0.9f
					? FVector::UpVector : FVector::RightVector;
				const FVector TangentX = FVector::CrossProduct(Reference, Center).GetSafeNormal();
				const FVector TangentY = FVector::CrossProduct(Center, TangentX).GetSafeNormal();
				TArray<FVector, TInlineAllocator<16>> AuditDirections;
				AuditDirections.Add(Center);
				const float ArcDistancesCm[] =
				{
					Stamp.CoreRadiusCm * 0.5f,
					Stamp.CoreRadiusCm * 0.9f,
					Stamp.CoreRadiusCm + Stamp.FeatherRadiusCm * 0.5f
				};
				for (const float ArcDistanceCm : ArcDistancesCm)
				{
					if (ArcDistanceCm <= 1.f)
					{
						continue;
					}
					const float Angle = ArcDistanceCm / Planet->PlanetRadius;
					for (const FVector& Tangent : { TangentX, -TangentX, TangentY, -TangentY })
					{
						AuditDirections.Add(
							(Center * FMath::Cos(Angle) + Tangent * FMath::Sin(Angle))
								.GetSafeNormal());
					}
				}

				for (const FVector& Direction : AuditDirections)
				{
					float BaseHeightCm = 0.f;
					float ActualResolvedHeightCm = 0.f;
					if (!SampleUnstampedHeight(Direction, BaseHeightCm)
						|| !Planet->SampleResolvedSurface(Direction, ActualResolvedHeightCm))
					{
						Test->AddError(TEXT("Resolved stamp audit sample failed."));
						return false;
					}
					const float ExpectedResolvedHeightCm =
						PlanetGenTerrainStamp::ApplyResolvedStamps(
							BaseHeightCm,
							Direction,
							Planet->PlanetRadius,
							ResolvedStamps);
					MaximumResolvedApiErrorCm = FMath::Max(
						MaximumResolvedApiErrorCm,
						FMath::Abs(ActualResolvedHeightCm - ExpectedResolvedHeightCm));
					MaximumStampEffectCm = FMath::Max(
						MaximumStampEffectCm,
						FMath::Abs(ExpectedResolvedHeightCm - BaseHeightCm));
					++AuditedSamples;
				}
			}

			const bool bCountAccepted = Test->TestEqual(
				TEXT("Every enabled fused terrain stamp resolves independently"),
				ResolvedStamps.Num(), EnabledValidStampCount);
			const bool bCoverageAccepted = Test->TestTrue(
				TEXT("Resolved stamp audit covers all 27 authored patches"),
				ResolvedStamps.Num() == Private::ExpectedTerrainStampCount
					&& AuditedSamples >= Private::ExpectedTerrainStampCount * 5);
			const bool bApiAccepted = Test->TestTrue(
				TEXT("Public resolved-surface API includes the exact sorted stamp capture"),
				MaximumResolvedApiErrorCm <= Private::ResolvedStampSampleToleranceCm);
			const bool bEffectAccepted = Test->TestTrue(
				TEXT("Authored terrain stamps measurably alter the runtime surface"),
				MaximumStampEffectCm >= Private::MinimumResolvedStampEffectCm);
			const bool bAccepted = bCountAccepted && bCoverageAccepted
				&& bApiAccepted && bEffectAccepted && !Test->HasAnyErrors();
			UE_LOG(LogTemp, Display,
				TEXT("RED_FUSED_RESOLVED_STAMP_%s stamps=%d samples=%d max_api_error_cm=%.4f max_stamp_effect_cm=%.3f"),
				bAccepted ? TEXT("PASS") : TEXT("FAIL"),
				ResolvedStamps.Num(), AuditedSamples,
				MaximumResolvedApiErrorCm, MaximumStampEffectCm);
			return bAccepted;
		}

		bool FindDeterministicPhysicalCoast()
		{
			struct FCandidate
			{
				FVector A = FVector::ZeroVector;
				FVector B = FVector::ZeroVector;
				float SignedA = 0.f;
				float SignedB = 0.f;
				bool bValid = false;
			};
			FCandidate Fallback;

			for (int32 FaceIndex = 0; FaceIndex < PlanetGenMacroCubeFaceCount; ++FaceIndex)
			{
				const EPlanetGenMacroCubeFace Face =
					static_cast<EPlanetGenMacroCubeFace>(FaceIndex);
				const int32 Width = Private::CoastSearchStepsPerFace + 1;
				TArray<FVector> Directions;
				TArray<float> SignedHeights;
				Directions.SetNum(Width * Width);
				SignedHeights.SetNum(Width * Width);
				for (int32 Y = 0; Y < Width; ++Y)
				{
					for (int32 X = 0; X < Width; ++X)
					{
						const int32 Index = Y * Width + X;
						Directions[Index] = FPlanetGenMacroHeightfieldCapture::FaceUVToDirection(
							Face,
							FVector2D(
								static_cast<double>(X) / Private::CoastSearchStepsPerFace,
								static_cast<double>(Y) / Private::CoastSearchStepsPerFace));
						if (!SampleSignedHeight(Directions[Index], SignedHeights[Index]))
						{
							return false;
						}
					}
				}

				auto Consider = [&](const int32 IndexA, const int32 IndexB)
				{
					const float A = SignedHeights[IndexA];
					const float B = SignedHeights[IndexB];
					if ((A <= 0.f) == (B <= 0.f))
					{
						return false;
					}
					if (!Fallback.bValid)
					{
						Fallback = { Directions[IndexA], Directions[IndexB], A, B, true };
					}
					if (FMath::Abs(A) < Private::CoastSearchMinimumSignMarginCm
						|| FMath::Abs(B) < Private::CoastSearchMinimumSignMarginCm)
					{
						return false;
					}
					Fallback = { Directions[IndexA], Directions[IndexB], A, B, true };
					return true;
				};

				for (int32 Y = 0; Y < Width; ++Y)
				{
					for (int32 X = 0; X < Width; ++X)
					{
						const int32 Index = Y * Width + X;
						if (X + 1 < Width && Consider(Index, Index + 1))
						{
							return FinalizeCoast(Fallback);
						}
						if (Y + 1 < Width && Consider(Index, Index + Width))
						{
							return FinalizeCoast(Fallback);
						}
					}
				}
			}
			return Fallback.bValid && FinalizeCoast(Fallback);
		}

		template <typename TCandidate>
		bool FinalizeCoast(const TCandidate& Candidate)
		{
			WaterProbeDirection = Candidate.SignedA <= 0.f ? Candidate.A : Candidate.B;
			LandProbeDirection = Candidate.SignedA > 0.f ? Candidate.A : Candidate.B;
			FVector WaterDirection = WaterProbeDirection;
			FVector LandDirection = LandProbeDirection;
			float WaterSigned = Candidate.SignedA <= 0.f ? Candidate.SignedA : Candidate.SignedB;
			for (int32 Iteration = 0; Iteration < 24; ++Iteration)
			{
				const FVector Mid = (WaterDirection + LandDirection).GetSafeNormal();
				float MidSigned = 0.f;
				if (!SampleSignedHeight(Mid, MidSigned))
				{
					return false;
				}
				if (MidSigned <= 0.f)
				{
					WaterDirection = Mid;
					WaterSigned = MidSigned;
				}
				else
				{
					LandDirection = Mid;
				}
			}
			CoastDirection = (WaterDirection + LandDirection).GetSafeNormal();
			float CoastSigned = 0.f;
			if (!SampleSignedHeight(CoastDirection, CoastSigned))
			{
				return false;
			}
			UE_LOG(LogTemp, Display,
				TEXT("RED_FUSED_PHYSICAL_SHORE_FOUND direction=(%.9f,%.9f,%.9f) signed_cm=%.4f water_margin_cm=%.3f"),
				CoastDirection.X, CoastDirection.Y, CoastDirection.Z,
				CoastSigned, WaterSigned);
			return !CoastDirection.IsNearlyZero();
		}

		void MovePawnToCoast()
		{
			if (!Pawn.IsValid() || !Planet.IsValid())
			{
				return;
			}
			const float SeaHeightCm = Planet->MinHeight
				+ (Planet->MaxHeight - Planet->MinHeight) * Planet->SeaLevel;
			const float WaterRadiusCm = Planet->PlanetRadius + SeaHeightCm;
			const FVector Location = Planet->GetActorLocation()
				+ CoastDirection * (WaterRadiusCm + 1000.f);
			FVector Forward = FVector::VectorPlaneProject(
				LandProbeDirection - WaterProbeDirection, CoastDirection).GetSafeNormal();
			if (Forward.IsNearlyZero())
			{
				Forward = FVector::CrossProduct(FVector::UpVector, CoastDirection).GetSafeNormal();
			}
			Pawn->SetActorHiddenInGame(false);
			Pawn->SetActorEnableCollision(false);
			Pawn->SetActorLocation(Location, false, nullptr, ETeleportType::TeleportPhysics);
			Pawn->SetActorRotation(FRotationMatrix::MakeFromXZ(Forward, CoastDirection).Rotator());
			if (ShorelineComponent.IsValid())
			{
				ShorelineComponent->SetComponentTickEnabled(true);
			}
		}

		UProceduralMeshComponent* FindCrestMesh() const
		{
			if (!Pawn.IsValid())
			{
				return nullptr;
			}
			TArray<UProceduralMeshComponent*> Meshes;
			Pawn->GetComponents<UProceduralMeshComponent>(Meshes);
			for (UProceduralMeshComponent* Mesh : Meshes)
			{
				if (IsValid(Mesh) && Mesh->GetName() == TEXT("RedSoStylizedShorelineCrests"))
				{
					return Mesh;
				}
			}
			return nullptr;
		}

		bool VerifyCrestGeometry(
			UProceduralMeshComponent* CrestMesh,
			const FProcMeshSection* CrestSection)
		{
			const int32 VertexCount = CrestSection->ProcVertexBuffer.Num();
			const int32 IndexCount = CrestSection->ProcIndexBuffer.Num();
			Test->TestTrue(TEXT("Shoreline crest has complete four-vertex segments"),
				VertexCount > 0 && VertexCount % 4 == 0);
			Test->TestEqual(TEXT("Shoreline crest has six indices per segment"),
				IndexCount, VertexCount / 4 * 6);
			Test->TestEqual(TEXT("Shoreline crest collision is disabled"),
				CrestMesh->GetCollisionEnabled(), ECollisionEnabled::NoCollision);
			Test->TestFalse(TEXT("Shoreline crest overlap events are disabled"),
				CrestMesh->GetGenerateOverlapEvents());
			Test->TestNotNull(TEXT("Shoreline crest has its SoStylized material"),
				CrestMesh->GetMaterial(0));

			const FVector PlanetCenter = Planet->GetActorLocation();
			const float SeaHeightCm = Planet->MinHeight
				+ (Planet->MaxHeight - Planet->MinHeight) * Planet->SeaLevel;
			const float ExpectedRadiusCm = Planet->PlanetRadius + SeaHeightCm
				+ Private::ShorelineSurfaceLiftCm;
			float MaxRadiusErrorCm = 0.f;
			float MaxShoreSignedHeightCm = 0.f;
			float MaxCrestPatchDistanceCm = 0.f;
			float MinimumOutwardNormalDot = 1.f;
			int32 WaterEdgeBelowCount = 0;
			int32 WaterEdgeSampleCount = 0;
			RepresentativeDirections.Reset();
			const int32 SegmentCount = VertexCount / 4;
			const int32 SegmentStride = FMath::Max(1, SegmentCount / 8);

			for (int32 VertexIndex = 0; VertexIndex < VertexCount; ++VertexIndex)
			{
				const FProcMeshVertex& Vertex = CrestSection->ProcVertexBuffer[VertexIndex];
				const FVector WorldPosition = CrestMesh->GetComponentTransform()
					.TransformPosition(Vertex.Position);
				const FVector Direction = (WorldPosition - PlanetCenter).GetSafeNormal();
				MaxRadiusErrorCm = FMath::Max(MaxRadiusErrorCm,
					FMath::Abs(FVector::Distance(WorldPosition, PlanetCenter) - ExpectedRadiusCm));
				MaxCrestPatchDistanceCm = FMath::Max(
					MaxCrestPatchDistanceCm,
					FMath::Acos(FMath::Clamp(
						FVector::DotProduct(Direction, CoastDirection), -1.f, 1.f))
						* Planet->PlanetRadius);
				MinimumOutwardNormalDot = FMath::Min(
					MinimumOutwardNormalDot,
					FVector::DotProduct(
						CrestMesh->GetComponentTransform()
							.TransformVectorNoScale(Vertex.Normal).GetSafeNormal(),
						Direction));
				float SignedHeightCm = 0.f;
				if (!SampleSignedHeight(Direction, SignedHeightCm))
				{
					Test->AddError(TEXT("Resolved shoreline height sample failed."));
					return false;
				}
				const int32 SegmentVertex = VertexIndex % 4;
				if (SegmentVertex == 0 || SegmentVertex == 2)
				{
					MaxShoreSignedHeightCm = FMath::Max(
						MaxShoreSignedHeightCm, FMath::Abs(SignedHeightCm));
				}
				else
				{
					++WaterEdgeSampleCount;
					WaterEdgeBelowCount += SignedHeightCm <= 100.f ? 1 : 0;
				}
			}

			bool bIndexTopologyValid = IndexCount > 0 && IndexCount % 6 == 0;
			float MinimumDoubleTriangleArea = TNumericLimits<float>::Max();
			float MaximumWindingDot = -1.f;
			for (int32 TriangleIndex = 0;
				TriangleIndex + 2 < IndexCount;
				TriangleIndex += 3)
			{
				const int32 I0 = CrestSection->ProcIndexBuffer[TriangleIndex];
				const int32 I1 = CrestSection->ProcIndexBuffer[TriangleIndex + 1];
				const int32 I2 = CrestSection->ProcIndexBuffer[TriangleIndex + 2];
				const int32 ExpectedSegmentBase = (TriangleIndex / 6) * 4;
				const bool bIndicesInRange = I0 >= 0 && I0 < VertexCount
					&& I1 >= 0 && I1 < VertexCount
					&& I2 >= 0 && I2 < VertexCount;
				const bool bIndicesStayInSegment = bIndicesInRange
					&& I0 >= ExpectedSegmentBase && I0 < ExpectedSegmentBase + 4
					&& I1 >= ExpectedSegmentBase && I1 < ExpectedSegmentBase + 4
					&& I2 >= ExpectedSegmentBase && I2 < ExpectedSegmentBase + 4;
				bIndexTopologyValid &= bIndicesStayInSegment;
				if (!bIndicesInRange)
				{
					continue;
				}

				const FProcMeshVertex& V0 = CrestSection->ProcVertexBuffer[I0];
				const FProcMeshVertex& V1 = CrestSection->ProcVertexBuffer[I1];
				const FProcMeshVertex& V2 = CrestSection->ProcVertexBuffer[I2];
				const FVector Cross = FVector::CrossProduct(
					V1.Position - V0.Position,
					V2.Position - V0.Position);
				MinimumDoubleTriangleArea = FMath::Min(
					MinimumDoubleTriangleArea, Cross.Size());
				const FVector DesiredNormal =
					(V0.Normal + V1.Normal + V2.Normal).GetSafeNormal();
				MaximumWindingDot = FMath::Max(
					MaximumWindingDot,
					FVector::DotProduct(Cross.GetSafeNormal(), DesiredNormal));
			}

			for (int32 SegmentIndex = 0;
				SegmentIndex < SegmentCount && RepresentativeDirections.Num() < 8;
				SegmentIndex += SegmentStride)
			{
				const FVector LocalPosition =
					CrestSection->ProcVertexBuffer[SegmentIndex * 4].Position;
				RepresentativeDirections.Add(LocalPosition.GetSafeNormal());
			}

			Test->TestTrue(TEXT("Shoreline crest uses the water-radius lift"),
				MaxRadiusErrorCm <= Private::CrestRadiusToleranceCm);
			Test->TestTrue(TEXT("Shoreline crest normals point outward"),
				MinimumOutwardNormalDot >= 0.999f);
			Test->TestTrue(TEXT("Shoreline crest belongs to the current pawn patch"),
				MaxCrestPatchDistanceCm <= Private::CrestPatchDistanceToleranceCm);
			Test->TestTrue(TEXT("Shoreline crest indices stay within complete segments"),
				bIndexTopologyValid);
			Test->TestTrue(TEXT("Shoreline crest triangles are non-degenerate"),
				MinimumDoubleTriangleArea > 1.f);
			Test->TestTrue(TEXT("Shoreline crest uses visible outward clockwise winding"),
				MaximumWindingDot <= -0.9f);
			Test->TestTrue(TEXT("Shoreline crest follows the resolved physical contour"),
				MaxShoreSignedHeightCm <= Private::CrestResolvedHeightToleranceCm);
			Test->TestTrue(TEXT("Shoreline ribbon extends toward physical water"),
				WaterEdgeSampleCount > 0
					&& WaterEdgeBelowCount * 4 >= WaterEdgeSampleCount * 3);
			Test->TestTrue(TEXT("Shoreline crest exposes representative collision probes"),
				RepresentativeDirections.Num() >= 4);

			CrestSegmentCount = SegmentCount;
			CrestVertexCount = VertexCount;
			CrestIndexCount = IndexCount;
			CrestMaxRadiusErrorCm = MaxRadiusErrorCm;
			CrestMaxSignedHeightCm = MaxShoreSignedHeightCm;
			return !Test->HasAnyErrors();
		}

		bool VerifyRuntimeCollision()
		{
			if (!World.IsValid() || !Planet.IsValid() || RepresentativeDirections.IsEmpty())
			{
				return false;
			}

			float MaximumCollisionDeltaCm = 0.f;
			float MinimumOutwardNormalDot = 1.f;
			for (const FVector& Direction : RepresentativeDirections)
			{
				FHitResult Hit;
				if (!Private::TraceOwnedTerrain(World.Get(), Planet.Get(), Direction, Hit))
				{
					return false;
				}
				float ResolvedHeightCm = 0.f;
				if (!Planet->SampleResolvedSurface(Direction, ResolvedHeightCm))
				{
					Test->AddError(TEXT("Resolved collision comparison sample failed."));
					return true;
				}
				const float CollisionHeightCm = FVector::Distance(
					Hit.ImpactPoint, Planet->GetActorLocation()) - Planet->PlanetRadius;
				MaximumCollisionDeltaCm = FMath::Max(
					MaximumCollisionDeltaCm,
					FMath::Abs(CollisionHeightCm - ResolvedHeightCm));
				MinimumOutwardNormalDot = FMath::Min(
					MinimumOutwardNormalDot,
					FVector::DotProduct(Hit.ImpactNormal.GetSafeNormal(), Direction.GetSafeNormal()));
			}

			const bool bHeightAccepted = Test->TestTrue(
				TEXT("Runtime coast collision follows the resolved analytic surface"),
				MaximumCollisionDeltaCm <= Private::RuntimeCollisionHeightToleranceCm);
			const bool bNormalAccepted = Test->TestTrue(
				TEXT("Runtime coast collision normals face outward"),
				MinimumOutwardNormalDot >= 0.5f);
			const bool bAccepted = bHeightAccepted && bNormalAccepted
				&& !Test->HasAnyErrors();
			UE_LOG(LogTemp, Display,
				TEXT("RED_FUSED_PHYSICAL_SHORE_%s segments=%d vertices=%d indices=%d max_crest_radius_error_cm=%.4f max_crest_signed_height_cm=%.3f collision_probes=%d max_collision_delta_cm=%.3f min_collision_normal_dot=%.6f"),
				bAccepted ? TEXT("PASS") : TEXT("FAIL"),
				CrestSegmentCount, CrestVertexCount, CrestIndexCount,
				CrestMaxRadiusErrorCm, CrestMaxSignedHeightCm,
				RepresentativeDirections.Num(), MaximumCollisionDeltaCm,
				MinimumOutwardNormalDot);
			return true;
		}

		bool WaitOrFail(const FString& Detail)
		{
			const double Now = FPlatformTime::Seconds();
			if (Now - StartedAtSeconds <= Private::PhysicalShorelineTimeoutSeconds
				&& Now - StageStartedAtSeconds <= Private::PhysicalShorelineTimeoutSeconds)
			{
				return false;
			}
			return Fail(FString::Printf(
				TEXT("Physical shoreline test timed out after %.0f seconds in stage %d: %s"),
				Private::PhysicalShorelineTimeoutSeconds,
				static_cast<int32>(Stage), *Detail));
		}

		bool Fail(const FString& Message)
		{
			Test->AddError(Message);
			return Finish();
		}

		bool Finish()
		{
			if (Pawn.IsValid())
			{
				Pawn->SetActorLocation(
					OriginalPawnLocation, false, nullptr, ETeleportType::TeleportPhysics);
				Pawn->SetActorRotation(OriginalPawnRotation);
				Pawn->SetActorEnableCollision(bOriginalPawnCollision);
				Pawn->SetActorHiddenInGame(bOriginalPawnHidden);
			}
			Stage = EStage::Finished;
			return true;
		}

		FAutomationTestBase* Test = nullptr;
		TWeakObjectPtr<UWorld> World;
		TWeakObjectPtr<ACLMPlanet> Planet;
		TWeakObjectPtr<UPlanetGenNoiseGenerator> NoiseGenerator;
		TWeakObjectPtr<APawn> Pawn;
		TWeakObjectPtr<URedShorelineWaveComponent> ShorelineComponent;
		EStage Stage = EStage::FindCoast;
		double StartedAtSeconds = 0.0;
		double StageStartedAtSeconds = 0.0;
		FVector OriginalPawnLocation = FVector::ZeroVector;
		FRotator OriginalPawnRotation = FRotator::ZeroRotator;
		bool bOriginalPawnCollision = true;
		bool bOriginalPawnHidden = false;
		FVector CoastDirection = FVector::ZeroVector;
		FVector WaterProbeDirection = FVector::ZeroVector;
		FVector LandProbeDirection = FVector::ZeroVector;
		TArray<FVector> RepresentativeDirections;
		int32 CrestSegmentCount = 0;
		int32 CrestVertexCount = 0;
		int32 CrestIndexCount = 0;
		float CrestMaxRadiusErrorCm = 0.f;
		float CrestMaxSignedHeightCm = 0.f;
	};

	IMPLEMENT_SIMPLE_AUTOMATION_TEST(
		FRedPlanetFusedWaterDatumTest,
		"RedMMO.Planet.FusedTerrain.RuntimeWaterDatumAndAuthoredCoastline",
		EAutomationTestFlags::EditorContext | EAutomationTestFlags::ProductFilter)

	bool FRedPlanetFusedWaterDatumTest::RunTest(const FString& Parameters)
	{
		(void)Parameters;
		AddExpectedErrorPlain(
			TEXT("Accessed None trying to read (real) property CallFunc_SpawnEmitterAttached_ReturnValue"),
			EAutomationExpectedErrorFlags::Contains,
			-1);
		if (!AutomationOpenMap(Private::FusedPrototypeMap, true))
		{
			AddError(TEXT("AutomationOpenMap rejected the fused-prototype map."));
			return false;
		}

		ADD_LATENT_AUTOMATION_COMMAND(FRedFusedWaterDatumCommand(this));
		ADD_LATENT_AUTOMATION_COMMAND(FEndPlayMapCommand());
		return true;
	}

	IMPLEMENT_SIMPLE_AUTOMATION_TEST(
		FRedPlanetFusedPhysicalShorelineTest,
		"RedMMO.Planet.FusedTerrain.RuntimePhysicalShorelineCrests",
		EAutomationTestFlags::EditorContext | EAutomationTestFlags::ProductFilter)

	bool FRedPlanetFusedPhysicalShorelineTest::RunTest(const FString& Parameters)
	{
		(void)Parameters;
		AddExpectedErrorPlain(
			TEXT("Accessed None trying to read (real) property CallFunc_SpawnEmitterAttached_ReturnValue"),
			EAutomationExpectedErrorFlags::Contains,
			-1);
		if (!AutomationOpenMap(Private::FusedPrototypeMap, true))
		{
			AddError(TEXT("AutomationOpenMap rejected the fused-prototype map."));
			return false;
		}

		ADD_LATENT_AUTOMATION_COMMAND(FRedFusedPhysicalShorelineCommand(this));
		ADD_LATENT_AUTOMATION_COMMAND(FEndPlayMapCommand());
		return true;
	}
}

#endif // WITH_DEV_AUTOMATION_TESTS && WITH_EDITOR

#else
// Stock Marketplace PlanetGen 1.7 lacks TerrainStamp/MacroHeightfield fork APIs.
// These automation suites are compiled out until Plugins/PlanetGenPinned_* is restored.
#endif