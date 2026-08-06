#include "RedPlanetMacroHeightmap.h"

#if WITH_DEV_AUTOMATION_TESTS

#include "Containers/Set.h"
#include "Misc/AutomationTest.h"

#include <limits>

namespace RedPlanet::MacroHeightmapTests
{
	namespace Private
	{
		constexpr double DirectionTolerance = 1.0e-12;
		constexpr float ChannelTolerance = 1.0e-6f;

		struct FFaceCenterCase
		{
			EPlanetCubeFace Face;
			FVector3d Direction;
		};

		const FFaceCenterCase FaceCenters[] =
		{
			{ EPlanetCubeFace::PositiveX, FVector3d(1.0, 0.0, 0.0) },
			{ EPlanetCubeFace::NegativeX, FVector3d(-1.0, 0.0, 0.0) },
			{ EPlanetCubeFace::PositiveY, FVector3d(0.0, 1.0, 0.0) },
			{ EPlanetCubeFace::NegativeY, FVector3d(0.0, -1.0, 0.0) },
			{ EPlanetCubeFace::PositiveZ, FVector3d(0.0, 0.0, 1.0) },
			{ EPlanetCubeFace::NegativeZ, FVector3d(0.0, 0.0, -1.0) }
		};

		bool DirectionsMatch(const FVector3d& A, const FVector3d& B)
		{
			return FVector3d::DotProduct(A.GetSafeNormal(), B.GetSafeNormal())
				>= 1.0 - DirectionTolerance;
		}

		FIntVector QuantizeDirection(const FVector3d& Direction)
		{
			constexpr double Scale = 1000000.0;
			return FIntVector(
				FMath::RoundToInt(Direction.X * Scale),
				FMath::RoundToInt(Direction.Y * Scale),
				FMath::RoundToInt(Direction.Z * Scale));
		}
	}

	IMPLEMENT_SIMPLE_AUTOMATION_TEST(
		FRedPlanetMacroCubeTopologyTest,
		"RedMMO.Planet.MacroHeightmap.CubeTopology",
		EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::ProductFilter)

	bool FRedPlanetMacroCubeTopologyTest::RunTest(const FString& Parameters)
	{
		(void)Parameters;

		for (int32 CaseIndex = 0; CaseIndex < UE_ARRAY_COUNT(Private::FaceCenters); ++CaseIndex)
		{
			const Private::FFaceCenterCase& Center = Private::FaceCenters[CaseIndex];
			FPlanetCubeFaceAddress Address;
			const FString Prefix = FString::Printf(TEXT("Face center %d: "), CaseIndex);
			TestTrue(Prefix + TEXT("direction maps successfully"),
				FPlanetCubeTopology::TryDirectionToFaceUV(Center.Direction, Address));
			TestEqual(Prefix + TEXT("maps to the expected signed axis"),
				static_cast<uint8>(Address.Face), static_cast<uint8>(Center.Face));
			TestTrue(Prefix + TEXT("maps to the square center"),
				Address.UV01.Equals(FVector2d(0.5, 0.5), Private::DirectionTolerance));
			TestTrue(Prefix + TEXT("round trips to the original direction"),
				Private::DirectionsMatch(
					FPlanetCubeTopology::FaceUVToDirection(Address.Face, Address.UV01),
					Center.Direction));
		}

		FPlanetCubeFaceAddress InvalidAddress;
		TestFalse(TEXT("A zero direction has no cube face"),
			FPlanetCubeTopology::TryDirectionToFaceUV(FVector3d::ZeroVector, InvalidAddress));
		TestFalse(TEXT("A non-finite direction has no cube face"),
			FPlanetCubeTopology::TryDirectionToFaceUV(
				FVector3d(std::numeric_limits<double>::quiet_NaN(), 0.0, 0.0), InvalidAddress));

		const FVector2d EdgeMidpoints[] =
		{
			FVector2d(0.0, 0.5),
			FVector2d(1.0, 0.5),
			FVector2d(0.5, 0.0),
			FVector2d(0.5, 1.0)
		};
		const FVector2d Corners[] =
		{
			FVector2d(0.0, 0.0),
			FVector2d(1.0, 0.0),
			FVector2d(0.0, 1.0),
			FVector2d(1.0, 1.0)
		};
		TSet<FIntVector> UniqueEdgeDirections;
		TSet<FIntVector> UniqueCornerDirections;

		for (int32 FaceIndex = 0; FaceIndex < MacroCubeFaceCount; ++FaceIndex)
		{
			const EPlanetCubeFace Face = static_cast<EPlanetCubeFace>(FaceIndex);
			const FVector2d InteriorUV(0.19, 0.73);
			const FVector3d InteriorDirection = FPlanetCubeTopology::FaceUVToDirection(Face, InteriorUV);
			FPlanetCubeFaceAddress InteriorAddress;
			const FString InteriorPrefix = FString::Printf(TEXT("Face %d tangent interior: "), FaceIndex);
			TestTrue(InteriorPrefix + TEXT("direction maps successfully"),
				FPlanetCubeTopology::TryDirectionToFaceUV(InteriorDirection, InteriorAddress));
			TestEqual(InteriorPrefix + TEXT("remains on the authored face"),
				static_cast<uint8>(InteriorAddress.Face), static_cast<uint8>(Face));
			TestTrue(InteriorPrefix + TEXT("UV round trip preserves the tangent projection"),
				InteriorAddress.UV01.Equals(InteriorUV, Private::DirectionTolerance));

			for (const FVector2d& FaceUV : EdgeMidpoints)
			{
				const FVector3d OriginalDirection = FPlanetCubeTopology::FaceUVToDirection(Face, FaceUV);
				FPlanetCubeFaceAddress CanonicalAddress;
				const FString Prefix = FString::Printf(
					TEXT("Face %d edge (%g,%g): "), FaceIndex, FaceUV.X, FaceUV.Y);
				TestTrue(Prefix + TEXT("canonical mapping succeeds"),
					FPlanetCubeTopology::TryDirectionToFaceUV(OriginalDirection, CanonicalAddress));
				TestTrue(Prefix + TEXT("canonical mapping preserves the physical direction"),
					Private::DirectionsMatch(
						OriginalDirection,
						FPlanetCubeTopology::FaceUVToDirection(
							CanonicalAddress.Face, CanonicalAddress.UV01)));

				FPlanetCubeFaceAddress RepeatedAddress;
				TestTrue(Prefix + TEXT("repeated mapping succeeds"),
					FPlanetCubeTopology::TryDirectionToFaceUV(OriginalDirection, RepeatedAddress));
				TestEqual(Prefix + TEXT("tie-break face is deterministic"),
					static_cast<uint8>(RepeatedAddress.Face),
					static_cast<uint8>(CanonicalAddress.Face));
				TestTrue(Prefix + TEXT("tie-break UV is deterministic"),
					RepeatedAddress.UV01.Equals(CanonicalAddress.UV01, 0.0));
				UniqueEdgeDirections.Add(Private::QuantizeDirection(OriginalDirection));
			}

			for (const FVector2d& FaceUV : Corners)
			{
				const FVector3d OriginalDirection = FPlanetCubeTopology::FaceUVToDirection(Face, FaceUV);
				FPlanetCubeFaceAddress CanonicalAddress;
				const FString Prefix = FString::Printf(
					TEXT("Face %d corner (%g,%g): "), FaceIndex, FaceUV.X, FaceUV.Y);
				TestTrue(Prefix + TEXT("canonical mapping succeeds"),
					FPlanetCubeTopology::TryDirectionToFaceUV(OriginalDirection, CanonicalAddress));
				TestTrue(Prefix + TEXT("canonical mapping preserves the physical direction"),
					Private::DirectionsMatch(
						OriginalDirection,
						FPlanetCubeTopology::FaceUVToDirection(
							CanonicalAddress.Face, CanonicalAddress.UV01)));
				UniqueCornerDirections.Add(Private::QuantizeDirection(OriginalDirection));
			}
		}

		TestEqual(TEXT("The 24 face-edge presentations fuse into exactly 12 physical edges"),
			UniqueEdgeDirections.Num(), 12);
		TestEqual(TEXT("The 24 face-corner presentations fuse into exactly 8 physical corners"),
			UniqueCornerDirections.Num(), 8);

		// Representative +X/+Y shared edge. Matching V values must describe identical directions.
		for (int32 Step = 0; Step <= 4; ++Step)
		{
			const double V = static_cast<double>(Step) / 4.0;
			TestTrue(
				FString::Printf(TEXT("+X/+Y shared edge sample %d has one physical direction"), Step),
				Private::DirectionsMatch(
					FPlanetCubeTopology::FaceUVToDirection(
						EPlanetCubeFace::PositiveX, FVector2d(1.0, V)),
					FPlanetCubeTopology::FaceUVToDirection(
						EPlanetCubeFace::PositiveY, FVector2d(0.0, V))));
		}

		return true;
	}

	IMPLEMENT_SIMPLE_AUTOMATION_TEST(
		FRedPlanetMacroHeightmapSamplingTest,
		"RedMMO.Planet.MacroHeightmap.DeterministicSampling",
		EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::ProductFilter)

	bool FRedPlanetMacroHeightmapSamplingTest::RunTest(const FString& Parameters)
	{
		(void)Parameters;

		FPlanetMacroHeightmap Heightmap;
		TestTrue(TEXT("A two-by-two six-face macro heightmap initializes"), Heightmap.Initialize(2));
		TestTrue(TEXT("The initialized six-face macro heightmap is valid"), Heightmap.IsValid());
		TestEqual(TEXT("All initialized faces use the requested resolution"), Heightmap.GetResolution(), 2);

		FPlanetMacroHeightGrid& PositiveX = Heightmap.GetFaceChecked(EPlanetCubeFace::PositiveX);
		TestTrue(TEXT("Set +X lower-left texel"), PositiveX.SetTexel(
			0, 0, FPlanetMacroTexel16(0, 65535, 0)));
		TestTrue(TEXT("Set +X lower-right texel"), PositiveX.SetTexel(
			1, 0, FPlanetMacroTexel16(65535, 65535, 0)));
		TestTrue(TEXT("Set +X upper-left texel"), PositiveX.SetTexel(
			0, 1, FPlanetMacroTexel16(65535, 0, 65535)));
		TestTrue(TEXT("Set +X upper-right texel"), PositiveX.SetTexel(
			1, 1, FPlanetMacroTexel16(0, 0, 65535)));

		const FPlanetMacroSample CenterSample = Heightmap.SampleDirection(FVector3d(1.0, 0.0, 0.0));
		TestTrue(TEXT("The +X center sample is valid"), CenterSample.bIsValid);
		TestTrue(TEXT("Elevation bilinearly decodes to one half"),
			FMath::IsNearlyEqual(CenterSample.Elevation01, 0.5f, Private::ChannelTolerance));
		TestTrue(TEXT("Land mask bilinearly decodes to one half"),
			FMath::IsNearlyEqual(CenterSample.LandMask01, 0.5f, Private::ChannelTolerance));
		TestTrue(TEXT("Biome mask bilinearly decodes to one half"),
			FMath::IsNearlyEqual(CenterSample.BiomeMask01, 0.5f, Private::ChannelTolerance));
		TestFalse(TEXT("A zero direction cannot sample the heightmap"),
			Heightmap.SampleDirection(FVector3d::ZeroVector).bIsValid);

		for (int32 Repeat = 0; Repeat < 32; ++Repeat)
		{
			const FPlanetMacroSample Repeated = Heightmap.SampleDirection(FVector3d(1.0, 0.0, 0.0));
			TestEqual(TEXT("Repeated elevation sampling is bit-stable"),
				Repeated.Elevation01, CenterSample.Elevation01);
			TestEqual(TEXT("Repeated land-mask sampling is bit-stable"),
				Repeated.LandMask01, CenterSample.LandMask01);
			TestEqual(TEXT("Repeated biome-mask sampling is bit-stable"),
				Repeated.BiomeMask01, CenterSample.BiomeMask01);
		}

		FPlanetMacroHeightmap SeamMap;
		TestTrue(TEXT("A four-by-four seam fixture initializes"), SeamMap.Initialize(4));
		FPlanetMacroHeightGrid& SeamPositiveX = SeamMap.GetFaceChecked(EPlanetCubeFace::PositiveX);
		FPlanetMacroHeightGrid& SeamPositiveY = SeamMap.GetFaceChecked(EPlanetCubeFace::PositiveY);
		SeamPositiveX.GetTexelChecked(1, 1) = FPlanetMacroTexel16(12345, 23456, 34567);
		for (int32 Y = 0; Y < 4; ++Y)
		{
			SeamPositiveX.GetTexelChecked(3, Y) = FPlanetMacroTexel16(
				static_cast<uint16>(1000 + Y),
				static_cast<uint16>(2000 + Y),
				static_cast<uint16>(3000 + Y));
			SeamPositiveY.GetTexelChecked(0, Y) = FPlanetMacroTexel16(
				static_cast<uint16>(5000 + Y),
				static_cast<uint16>(6000 + Y),
				static_cast<uint16>(7000 + Y));
		}

		TestTrue(TEXT("All duplicated cube borders and corners fuse successfully"),
			SeamMap.FuseSharedBorders());
		for (int32 Y = 0; Y < 4; ++Y)
		{
			const FPlanetMacroTexel16& XEdge = SeamPositiveX.GetTexelChecked(3, Y);
			const FPlanetMacroTexel16& YEdge = SeamPositiveY.GetTexelChecked(0, Y);
			const FString Prefix = FString::Printf(TEXT("Fused +X/+Y edge row %d: "), Y);
			TestEqual(Prefix + TEXT("elevation texels match"), XEdge.Elevation01, YEdge.Elevation01);
			TestEqual(Prefix + TEXT("land texels match"), XEdge.LandMask01, YEdge.LandMask01);
			TestEqual(Prefix + TEXT("biome texels match"), XEdge.BiomeMask01, YEdge.BiomeMask01);
		}
		const FPlanetMacroTexel16& UntouchedInterior = SeamPositiveX.GetTexelChecked(1, 1);
		TestEqual(TEXT("Border fusion leaves interior elevation untouched"),
			UntouchedInterior.Elevation01, static_cast<uint16>(12345));
		TestEqual(TEXT("Border fusion leaves interior land mask untouched"),
			UntouchedInterior.LandMask01, static_cast<uint16>(23456));
		TestEqual(TEXT("Border fusion leaves interior biome mask untouched"),
			UntouchedInterior.BiomeMask01, static_cast<uint16>(34567));

		const FPlanetMacroTexel16& CornerX = SeamPositiveX.GetTexelChecked(3, 3);
		const FPlanetMacroTexel16& CornerY = SeamPositiveY.GetTexelChecked(0, 3);
		const FPlanetMacroTexel16& CornerZ = SeamMap.GetFaceChecked(
			EPlanetCubeFace::PositiveZ).GetTexelChecked(3, 3);
		TestEqual(TEXT("Three-face corner elevation is fused"), CornerX.Elevation01, CornerY.Elevation01);
		TestEqual(TEXT("Three-face corner elevation reaches +Z"), CornerX.Elevation01, CornerZ.Elevation01);
		TestEqual(TEXT("Three-face corner land mask is fused"), CornerX.LandMask01, CornerZ.LandMask01);
		TestEqual(TEXT("Three-face corner biome mask is fused"), CornerX.BiomeMask01, CornerZ.BiomeMask01);

		return true;
	}
}

#endif // WITH_DEV_AUTOMATION_TESTS
