#if WITH_DEV_AUTOMATION_TESTS

#include "Data/VibeMMOHUDLayoutTypes.h"
#include "Kismet/GameplayStatics.h"
#include "Misc/AutomationTest.h"
#include "Persistence/VibeMMOHUDLayoutSaveGame.h"
#include "Persistence/VibeMMOHUDLayoutSubsystem.h"
#include "UObject/UnrealType.h"

#include <limits>

IMPLEMENT_SIMPLE_AUTOMATION_TEST(
	FVibeMMOHUDLayoutValidationTest,
	"VibeMMO.UI.HUDLayout.Validation",
	EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::ProductFilter)

bool FVibeMMOHUDLayoutValidationTest::RunTest(const FString& Parameters)
{
	FVibeMMOHUDLayoutProfile Profile;
	FVibeMMOHUDElementLayout Invalid;
	Invalid.NormalizedOffset = FVector2D(4.0, std::numeric_limits<double>::quiet_NaN());
	Invalid.Scale = std::numeric_limits<float>::infinity();
	Invalid.Opacity = -5.0f;
	Invalid.bLocked = true;
	Profile.ElementOverrides.Add(EVibeMMOHUDElement::Minimap, Invalid);
	Profile.ElementOverrides.Add(
		static_cast<EVibeMMOHUDElement>(255), FVibeMMOHUDElementLayout());

	Profile.Sanitize();
	const FVibeMMOHUDElementLayout Sanitized =
		Profile.GetElementLayout(EVibeMMOHUDElement::Minimap);
	TestEqual(TEXT("X offset is clamped"), Sanitized.NormalizedOffset.X, 1.0);
	TestEqual(TEXT("Non-finite Y offset resets"), Sanitized.NormalizedOffset.Y, 0.0);
	TestEqual(TEXT("Non-finite scale resets"), Sanitized.Scale, 1.0f);
	TestEqual(TEXT("Opacity is clamped"), Sanitized.Opacity, VibeMMOHUDLayout::MinimumOpacity);
	TestTrue(TEXT("Boolean state survives validation"), Sanitized.bLocked);
	TestEqual(TEXT("Unknown element keys are discarded"), Profile.ElementOverrides.Num(), 1);

	FVibeMMOHUDElementLayout DefaultLayout;
	Profile.SetElementLayout(EVibeMMOHUDElement::Minimap, DefaultLayout);
	TestTrue(TEXT("Default values are stored sparsely"), Profile.ElementOverrides.IsEmpty());
	return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(
	FVibeMMOHUDLayoutMemoryRoundTripTest,
	"VibeMMO.UI.HUDLayout.MemoryRoundTrip",
	EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::ProductFilter)

bool FVibeMMOHUDLayoutMemoryRoundTripTest::RunTest(const FString& Parameters)
{
	UVibeMMOHUDLayoutSaveGame* SaveGame = NewObject<UVibeMMOHUDLayoutSaveGame>();
	FVibeMMOHUDLayoutProfile Profile;
	for (int32 Index = 0; Index < VibeMMOHUDLayout::GetElements().Num(); ++Index)
	{
		FVibeMMOHUDElementLayout Layout;
		Layout.NormalizedOffset = FVector2D(Index * 0.03, Index * -0.02);
		Layout.Scale = 0.75f + Index * 0.1f;
		Layout.Opacity = 1.0f - Index * 0.1f;
		Layout.bLocked = (Index % 2) == 0;
		Layout.bHidden = Index == 5;
		Profile.SetElementLayout(VibeMMOHUDLayout::GetElements()[Index], Layout);
	}
	TestTrue(TEXT("Supported save accepts profile changes"),
		SaveGame->SetLayoutProfile(Profile));
	SaveGame->HandlePreSave();

	TArray<uint8> Bytes;
	TestTrue(TEXT("Profile serializes to memory"),
		UGameplayStatics::SaveGameToMemory(SaveGame, Bytes));
	UVibeMMOHUDLayoutSaveGame* Loaded = Cast<UVibeMMOHUDLayoutSaveGame>(
		UGameplayStatics::LoadGameFromMemory(Bytes));
	TestNotNull(TEXT("Profile deserializes as the expected class"), Loaded);
	if (!Loaded)
	{
		return false;
	}

	Loaded->InitializeSaveGame(nullptr, TEXT("MemoryRoundTrip"), true);
	TestEqual(TEXT("Saved data version round-trips"),
		Loaded->GetSavedDataVersion(), UVibeMMOHUDLayoutSaveGame::LatestDataVersion);
	TestTrue(TEXT("All element overrides round-trip"),
		Profile.NearlyEquals(Loaded->GetLayoutProfile()));
	return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(
	FVibeMMOHUDLayoutVersionSafetyTest,
	"VibeMMO.UI.HUDLayout.VersionSafety",
	EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::ProductFilter)

bool FVibeMMOHUDLayoutVersionSafetyTest::RunTest(const FString& Parameters)
{
	FVibeMMOHUDLayoutProfile OriginalProfile;
	FVibeMMOHUDElementLayout OriginalLayout;
	OriginalLayout.Scale = 1.25f;
	OriginalProfile.SetElementLayout(EVibeMMOHUDElement::Reticle, OriginalLayout);

	// ULocalPlayerSaveGame defaults SavedDataVersion to 0, exercising the supported
	// legacy migration path without writing a physical save file.
	UVibeMMOHUDLayoutSaveGame* Legacy = NewObject<UVibeMMOHUDLayoutSaveGame>();
	TestTrue(TEXT("Legacy save accepts its profile"),
		Legacy->SetLayoutProfile(OriginalProfile));
	Legacy->InitializeSaveGame(nullptr, TEXT("LegacyVersion"), true);
	TestTrue(TEXT("Version zero remains supported"), Legacy->IsLoadedDataSupported());
	TestTrue(TEXT("Version zero is marked for durable resave"), Legacy->NeedsResaveAfterLoad());
	TestTrue(TEXT("Legacy profile survives migration"),
		OriginalProfile.NearlyEquals(Legacy->GetLayoutProfile()));
	Legacy->HandlePostSave(true);
	TestFalse(TEXT("Successful persistence clears the migration marker"),
		Legacy->NeedsResaveAfterLoad());

	UVibeMMOHUDLayoutSaveGame* Future = NewObject<UVibeMMOHUDLayoutSaveGame>();
	TestTrue(TEXT("Future fixture accepts its initial profile"),
		Future->SetLayoutProfile(OriginalProfile));
	FIntProperty* SavedVersionProperty = FindFProperty<FIntProperty>(
		ULocalPlayerSaveGame::StaticClass(), TEXT("SavedDataVersion"));
	TestNotNull(TEXT("Engine exposes SavedDataVersion for serialization"), SavedVersionProperty);
	if (!SavedVersionProperty)
	{
		return false;
	}
	SavedVersionProperty->SetPropertyValue_InContainer(
		Future, UVibeMMOHUDLayoutSaveGame::LatestDataVersion + 1);
	Future->InitializeSaveGame(nullptr, TEXT("FutureVersion"), true);

	TestFalse(TEXT("Future schema is opened read-only"), Future->IsLoadedDataSupported());
	TestFalse(TEXT("Future schema is never queued for downgrade"), Future->NeedsResaveAfterLoad());
	FVibeMMOHUDLayoutProfile ReplacementProfile;
	FVibeMMOHUDElementLayout ReplacementLayout;
	ReplacementLayout.Opacity = 0.25f;
	ReplacementProfile.SetElementLayout(EVibeMMOHUDElement::Reticle, ReplacementLayout);
	TestFalse(TEXT("Future schema rejects mutations"),
		Future->SetLayoutProfile(ReplacementProfile));
	TestTrue(TEXT("Rejected mutation leaves future known fields intact"),
		OriginalProfile.NearlyEquals(Future->GetLayoutProfile()));
	return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(
	FVibeMMOHUDLayoutSlotIdentityTest,
	"VibeMMO.UI.HUDLayout.SlotIdentity",
	EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::ProductFilter)

bool FVibeMMOHUDLayoutSlotIdentityTest::RunTest(const FString& Parameters)
{
	const FString AccountA0 = UVibeMMOHUDLayoutSubsystem::BuildSaveSlotNameForIdentity(
		TEXT("HUD"), TEXT("Steam:111"), 0);
	const FString AccountA1 = UVibeMMOHUDLayoutSubsystem::BuildSaveSlotNameForIdentity(
		TEXT("HUD"), TEXT("Steam:111"), 1);
	const FString AccountB = UVibeMMOHUDLayoutSubsystem::BuildSaveSlotNameForIdentity(
		TEXT("HUD"), TEXT("Steam:222"), 0);
	const FString Player0 = UVibeMMOHUDLayoutSubsystem::BuildSaveSlotNameForIdentity(
		TEXT("HUD"), FString(), 0);
	const FString Player1 = UVibeMMOHUDLayoutSubsystem::BuildSaveSlotNameForIdentity(
		TEXT("HUD"), FString(), 1);
	const FString InvalidIndex = UVibeMMOHUDLayoutSubsystem::BuildSaveSlotNameForIdentity(
		TEXT("HUD"), FString(), INDEX_NONE);

	TestEqual(TEXT("Account identity is stable across local indices"), AccountA0, AccountA1);
	TestNotEqual(TEXT("Different accounts do not share a slot"), AccountA0, AccountB);
	TestTrue(TEXT("Raw account identity is not exposed"), !AccountA0.Contains(TEXT("Steam:111")));
	TestNotEqual(TEXT("Split-screen fallback users do not collide"), Player0, Player1);
	TestEqual(TEXT("Invalid platform indices safely use player zero"), InvalidIndex, Player0);
	return true;
}

#endif // WITH_DEV_AUTOMATION_TESTS
