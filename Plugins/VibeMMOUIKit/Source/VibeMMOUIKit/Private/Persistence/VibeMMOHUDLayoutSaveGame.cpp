#include "Persistence/VibeMMOHUDLayoutSaveGame.h"

int32 UVibeMMOHUDLayoutSaveGame::GetLatestDataVersion() const
{
	return LatestDataVersion;
}

void UVibeMMOHUDLayoutSaveGame::ResetToDefault()
{
	LayoutProfile.ResetToDefault();
	bLoadedDataSupported = true;
	bNeedsResaveAfterLoad = false;
	Super::ResetToDefault();
}

void UVibeMMOHUDLayoutSaveGame::HandlePostLoad()
{
	const int32 LoadedVersion = GetSavedDataVersion();
	if (LoadedVersion > GetLatestDataVersion())
	{
		// Preserve the physical file and reject writes. Known fields can still be shown
		// safely after validation, but this runtime must not downgrade future data.
		bLoadedDataSupported = false;
		bNeedsResaveAfterLoad = false;
		LayoutProfile.Sanitize();
	}
	else if (LoadedVersion < 0)
	{
		ResetToDefault();
		bNeedsResaveAfterLoad = true;
	}
	else
	{
		// Version 0 did not have every current field. Default member initialization plus
		// sanitization safely upgrades it to the latest sparse profile representation.
		bLoadedDataSupported = true;
		const FVibeMMOHUDLayoutProfile ProfileBeforeRepair = LayoutProfile;
		LayoutProfile.Sanitize();
		bNeedsResaveAfterLoad = LoadedVersion < GetLatestDataVersion()
			|| !ProfileBeforeRepair.NearlyEquals(LayoutProfile);
	}

	// Native state is valid before inherited Blueprint post-load hooks observe it.
	Super::HandlePostLoad();
}

void UVibeMMOHUDLayoutSaveGame::HandlePostSave(const bool bSuccess)
{
	Super::HandlePostSave(bSuccess);
	if (bSuccess)
	{
		bNeedsResaveAfterLoad = false;
	}
	OnSaveCompletedNative.Broadcast(bSuccess);
}

FVibeMMOHUDLayoutProfile UVibeMMOHUDLayoutSaveGame::GetLayoutProfile() const
{
	return LayoutProfile;
}

bool UVibeMMOHUDLayoutSaveGame::SetLayoutProfile(const FVibeMMOHUDLayoutProfile& InProfile)
{
	if (!bLoadedDataSupported)
	{
		return false;
	}

	LayoutProfile = InProfile;
	LayoutProfile.Sanitize();
	return true;
}

bool UVibeMMOHUDLayoutSaveGame::IsLoadedDataSupported() const
{
	return bLoadedDataSupported;
}

bool UVibeMMOHUDLayoutSaveGame::NeedsResaveAfterLoad() const
{
	return bNeedsResaveAfterLoad;
}
