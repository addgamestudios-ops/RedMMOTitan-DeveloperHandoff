#pragma once

#include "CoreMinimal.h"
#include "Containers/StaticArray.h"

/**
 * Project-owned macro terrain data for a cube-sphere planet.
 *
 * Six square rasters are the complete square topology of a cube: one raster for each signed
 * Cartesian axis. Face coordinates use PlanetGen's tangent-corrected projection
 * tan(signedUV*pi/4), then the cube is normalized onto the sphere when sampled. Higher-level
 * RED regions (including the existing 27-region layout) remain authoring/streaming metadata and
 * do not replace these six complete faces.
 */
namespace RedPlanet
{
	static constexpr int32 MacroCubeFaceCount = 6;

	enum class EPlanetCubeFace : uint8
	{
		PositiveX = 0,
		NegativeX,
		PositiveY,
		NegativeY,
		PositiveZ,
		NegativeZ
	};

	/** A deterministic cube face and normalized square coordinate. */
	struct REDMMO_API FPlanetCubeFaceAddress
	{
		EPlanetCubeFace Face = EPlanetCubeFace::PositiveX;
		FVector2d UV01 = FVector2d(0.5, 0.5);
		bool bIsValid = false;
	};

	/**
	 * One lossless imported macro-map texel.
	 *
	 * All channels are normalized unsigned 16-bit fields. Elevation01 is converted to the
	 * configured min/max terrain height by the eventual terrain-provider integration. LandMask01
	 * and BiomeMask01 deliberately stay continuous so they can be bilinearly sampled and blended.
	 */
	struct REDMMO_API FPlanetMacroTexel16
	{
		uint16 Elevation01 = 0;
		uint16 LandMask01 = 0;
		uint16 BiomeMask01 = 0;

		FPlanetMacroTexel16() = default;

		FPlanetMacroTexel16(uint16 InElevation01, uint16 InLandMask01, uint16 InBiomeMask01)
			: Elevation01(InElevation01)
			, LandMask01(InLandMask01)
			, BiomeMask01(InBiomeMask01)
		{
		}
	};

	/** Decoded sample returned to terrain, ocean, biome, PCG, and map systems. */
	struct REDMMO_API FPlanetMacroSample
	{
		float Elevation01 = 0.0f;
		float LandMask01 = 0.0f;
		float BiomeMask01 = 0.0f;
		EPlanetCubeFace SourceFace = EPlanetCubeFace::PositiveX;
		FVector2d SourceUV01 = FVector2d(0.5, 0.5);
		bool bIsValid = false;
	};

	/** Pure cube-sphere topology functions shared by import, runtime sampling, and tests. */
	class REDMMO_API FPlanetCubeTopology final
	{
	public:
		/**
		 * Maps a finite nonzero direction to exactly one face. Ties use X, then Y, then Z so
		 * exact edges and corners never oscillate between faces across runs or platforms.
		 */
		static bool TryDirectionToFaceUV(
			const FVector3d& Direction,
			FPlanetCubeFaceAddress& OutAddress);

		/** Maps tangent-corrected face UV back to a unit sphere direction. UV is clamped. */
		static FVector3d FaceUVToDirection(EPlanetCubeFace Face, const FVector2d& UV01);

		static FVector3d GetFaceNormal(EPlanetCubeFace Face);
		static FVector3d GetFaceUAxis(EPlanetCubeFace Face);
		static FVector3d GetFaceVAxis(EPlanetCubeFace Face);
		static bool IsValidFace(EPlanetCubeFace Face);
	};

	/** A row-major square raster for one cube face. */
	class REDMMO_API FPlanetMacroHeightGrid final
	{
	public:
		/** Resolution includes both shared border rows/columns and must be at least two. */
		bool Initialize(int32 InResolution, const FPlanetMacroTexel16& Fill = {});
		void Reset();

		bool IsValid() const;
		int32 GetResolution() const { return Resolution; }

		bool SetTexel(int32 X, int32 Y, const FPlanetMacroTexel16& Texel);
		const FPlanetMacroTexel16& GetTexelChecked(int32 X, int32 Y) const;
		FPlanetMacroTexel16& GetTexelChecked(int32 X, int32 Y);

		/** Clamped, deterministic bilinear decoding of all three normalized 16-bit channels. */
		FPlanetMacroSample SampleBilinear(const FVector2d& UV01) const;

	private:
		int32 Resolution = 0;
		TArray<FPlanetMacroTexel16> Texels;
	};

	/** Six equally sized face grids forming one complete macro planet. */
	class REDMMO_API FPlanetMacroHeightmap final
	{
	public:
		bool Initialize(int32 FaceResolution, const FPlanetMacroTexel16& Fill = {});
		void Reset();

		bool IsValid() const;
		int32 GetResolution() const;

		const FPlanetMacroHeightGrid& GetFaceChecked(EPlanetCubeFace Face) const;
		FPlanetMacroHeightGrid& GetFaceChecked(EPlanetCubeFace Face);

		/** Maps Direction to one cube face and bilinearly samples its normalized fields. */
		FPlanetMacroSample SampleDirection(const FVector3d& Direction) const;

		/**
		 * Averages duplicated border texels for every shared edge and three-face corner. Importers
		 * should call this once after filling all faces. Equal resolution is required. This makes
		 * the face boundary C0-continuous; interior relief and derivatives remain authored data.
		 */
		bool FuseSharedBorders();

	private:
		TStaticArray<FPlanetMacroHeightGrid, MacroCubeFaceCount> Faces;
	};
}
