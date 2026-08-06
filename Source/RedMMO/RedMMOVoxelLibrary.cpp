#include "RedMMOVoxelLibrary.h"

#include "Curves/CurveLinearColor.h"
#include "Curves/CurveLinearColorAtlas.h"

DEFINE_LOG_CATEGORY_STATIC(LogRedMMOVoxel, Log, All);

bool URedMMOVoxelLibrary::SetColorCurveKeys(
	const FString& CurvePath,
	const FString& AtlasPath,
	const TArray<float>& Times,
	const TArray<FLinearColor>& Colors)
{
#if WITH_EDITOR
	if (Times.Num() == 0 || Times.Num() != Colors.Num())
	{
		UE_LOG(LogRedMMOVoxel, Warning, TEXT("[Sky] SetColorCurveKeys: empty or mismatched Times(%d)/Colors(%d)"),
			Times.Num(), Colors.Num());
		return false;
	}

	UCurveLinearColor* Curve = LoadObject<UCurveLinearColor>(nullptr, *CurvePath);
	if (!Curve)
	{
		UE_LOG(LogRedMMOVoxel, Warning, TEXT("[Sky] SetColorCurveKeys: curve not found: %s"), *CurvePath);
		return false;
	}

	// Rewrite the 4 channel curves (R,G,B,A). FloatCurves is a fixed C array of FRichCurve.
	for (int32 c = 0; c < 4; ++c)
	{
		Curve->FloatCurves[c].Reset();
	}
	for (int32 i = 0; i < Times.Num(); ++i)
	{
		Curve->FloatCurves[0].AddKey(Times[i], Colors[i].R);
		Curve->FloatCurves[1].AddKey(Times[i], Colors[i].G);
		Curve->FloatCurves[2].AddKey(Times[i], Colors[i].B);
		Curve->FloatCurves[3].AddKey(Times[i], Colors[i].A);
	}
	Curve->MarkPackageDirty();

	// The material samples the BAKED atlas texture, not the curve directly, so rebake it.
	UCurveLinearColorAtlas* Atlas = LoadObject<UCurveLinearColorAtlas>(nullptr, *AtlasPath);
	if (Atlas)
	{
		Atlas->UpdateTextures();
		Atlas->MarkPackageDirty();
	}
	else
	{
		UE_LOG(LogRedMMOVoxel, Warning, TEXT("[Sky] SetColorCurveKeys: atlas not found (curve edited but not rebaked): %s"), *AtlasPath);
	}

	UE_LOG(LogRedMMOVoxel, Log, TEXT("[Sky] SetColorCurveKeys: wrote %d keys to %s, atlas rebaked=%s"),
		Times.Num(), *CurvePath, Atlas ? TEXT("yes") : TEXT("no"));
	return true;
#else
	UE_LOG(LogRedMMOVoxel, Warning, TEXT("[Sky] SetColorCurveKeys is editor-only"));
	return false;
#endif
}
