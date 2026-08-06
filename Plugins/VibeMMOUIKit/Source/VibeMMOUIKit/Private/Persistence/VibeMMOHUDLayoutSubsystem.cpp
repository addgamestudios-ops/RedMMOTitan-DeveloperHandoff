#include "Persistence/VibeMMOHUDLayoutSubsystem.h"

#include "Engine/LocalPlayer.h"
#include "GameFramework/OnlineReplStructs.h"
#include "Kismet/GameplayStatics.h"
#include "Misc/SecureHash.h"
#include "Persistence/VibeMMOHUDLayoutSaveGame.h"

DEFINE_LOG_CATEGORY_STATIC(LogVibeMMOHUDLayout, Log, All);

void UVibeMMOHUDLayoutSubsystem::Initialize(FSubsystemCollectionBase& Collection)
{
	Super::Initialize(Collection);
	LoadOrCreateLayout();
}

void UVibeMMOHUDLayoutSubsystem::Deinitialize()
{
	if (bDirty && CurrentSaveGame)
	{
		// The profile is tiny and this is the last guaranteed game-thread save point.
		// Synchronous persistence avoids depending on an async completion tick at shutdown.
		SaveLayoutNow();
	}

	if (CurrentSaveGame)
	{
		CurrentSaveGame->OnSaveCompletedNative.RemoveAll(this);
	}
	CurrentSaveGame = nullptr;
	Super::Deinitialize();
}

bool UVibeMMOHUDLayoutSubsystem::LoadOrCreateLayout()
{
	if (CurrentSaveGame)
	{
		return true;
	}

	ULocalPlayer* LocalPlayer = GetLocalPlayer();
	if (!LocalPlayer)
	{
		return false;
	}

	const int32 PlatformUserIndex = LocalPlayer->GetPlatformUserIndex();
	const FString PlatformFallbackSlot = BuildSaveSlotNameForIdentity(
		UVibeMMOHUDLayoutSaveGame::DefaultSlotBase, FString(), PlatformUserIndex);
	const FString SlotName = BuildSaveSlotName(LocalPlayer);
	FString SlotToLoad = SlotName;
	bool bMigratePlatformFallback = false;

	// An online ID may not exist during an earlier offline run. If it is now ready,
	// claim the device/index fallback exactly once instead of silently losing that layout.
	if (SlotName != PlatformFallbackSlot
		&& !UGameplayStatics::DoesSaveGameExist(SlotName, PlatformUserIndex)
		&& UGameplayStatics::DoesSaveGameExist(PlatformFallbackSlot, PlatformUserIndex))
	{
		SlotToLoad = PlatformFallbackSlot;
		bMigratePlatformFallback = true;
	}

	CurrentSaveGame = Cast<UVibeMMOHUDLayoutSaveGame>(
		ULocalPlayerSaveGame::LoadOrCreateSaveGameForLocalPlayer(
			UVibeMMOHUDLayoutSaveGame::StaticClass(), LocalPlayer, SlotToLoad));
	if (!CurrentSaveGame)
	{
		UE_LOG(LogVibeMMOHUDLayout, Error,
			TEXT("Could not load or create HUD layout slot '%s'."), *SlotToLoad);
		return false;
	}

	CurrentSaveGame->OnSaveCompletedNative.AddUObject(
		this, &UVibeMMOHUDLayoutSubsystem::HandleSaveCompleted);

	const bool bCanMigrateFallback =
		bMigratePlatformFallback && CurrentSaveGame->IsLoadedDataSupported();
	if (bCanMigrateFallback)
	{
		CurrentSaveGame->SetSaveSlotName(SlotName);
		PendingFallbackSlotToDelete = PlatformFallbackSlot;
		PendingFallbackPlatformUserIndex = PlatformUserIndex;
	}

	bDirty = CurrentSaveGame->NeedsResaveAfterLoad() || bCanMigrateFallback;
	if (bDirty)
	{
		if (!SaveLayoutNow())
		{
			UE_LOG(LogVibeMMOHUDLayout, Warning,
				TEXT("Could not persist the migrated HUD layout slot '%s'."), *SlotName);
		}
	}
	return true;
}

bool UVibeMMOHUDLayoutSubsystem::IsLayoutLoaded() const
{
	return CurrentSaveGame != nullptr;
}

bool UVibeMMOHUDLayoutSubsystem::IsLayoutDirty() const
{
	return bDirty;
}

bool UVibeMMOHUDLayoutSubsystem::IsLayoutWritable() const
{
	return CurrentSaveGame && CurrentSaveGame->IsLoadedDataSupported();
}

FString UVibeMMOHUDLayoutSubsystem::GetActiveSaveSlotName() const
{
	return CurrentSaveGame ? CurrentSaveGame->GetSaveSlotName() : FString();
}

FVibeMMOHUDLayoutProfile UVibeMMOHUDLayoutSubsystem::GetLayoutProfile() const
{
	return CurrentSaveGame
		? CurrentSaveGame->GetLayoutProfile()
		: FVibeMMOHUDLayoutProfile();
}

FVibeMMOHUDElementLayout UVibeMMOHUDLayoutSubsystem::GetElementLayout(
	const EVibeMMOHUDElement Element) const
{
	return GetLayoutProfile().GetElementLayout(Element);
}

bool UVibeMMOHUDLayoutSubsystem::SetLayoutProfile(const FVibeMMOHUDLayoutProfile& Profile)
{
	if (!CurrentSaveGame && !LoadOrCreateLayout())
	{
		return false;
	}
	if (!CurrentSaveGame->IsLoadedDataSupported())
	{
		UE_LOG(LogVibeMMOHUDLayout, Warning,
			TEXT("HUD layout slot '%s' uses a newer schema and is read-only."),
			*CurrentSaveGame->GetSaveSlotName());
		return false;
	}

	FVibeMMOHUDLayoutProfile Sanitized = Profile;
	Sanitized.Sanitize();
	if (CurrentSaveGame->GetLayoutProfile().NearlyEquals(Sanitized))
	{
		return true;
	}

	if (!CurrentSaveGame->SetLayoutProfile(Sanitized))
	{
		return false;
	}
	MarkChanged();
	return true;
}

bool UVibeMMOHUDLayoutSubsystem::SetElementLayout(
	const EVibeMMOHUDElement Element,
	const FVibeMMOHUDElementLayout& Layout)
{
	if (!VibeMMOHUDLayout::IsValidElement(Element))
	{
		return false;
	}
	if (!CurrentSaveGame && !LoadOrCreateLayout())
	{
		return false;
	}
	if (!CurrentSaveGame->IsLoadedDataSupported())
	{
		return false;
	}

	FVibeMMOHUDLayoutProfile Profile = CurrentSaveGame->GetLayoutProfile();
	const FVibeMMOHUDElementLayout Before = Profile.GetElementLayout(Element);
	Profile.SetElementLayout(Element, Layout);
	if (Before.NearlyEquals(Profile.GetElementLayout(Element)))
	{
		return true;
	}
	return SetLayoutProfile(Profile);
}

bool UVibeMMOHUDLayoutSubsystem::ResetElementLayout(const EVibeMMOHUDElement Element)
{
	if (!VibeMMOHUDLayout::IsValidElement(Element))
	{
		return false;
	}
	if (!CurrentSaveGame && !LoadOrCreateLayout())
	{
		return false;
	}
	if (!CurrentSaveGame->IsLoadedDataSupported())
	{
		return false;
	}

	FVibeMMOHUDLayoutProfile Profile = CurrentSaveGame->GetLayoutProfile();
	if (!Profile.HasElementOverride(Element))
	{
		return true;
	}
	Profile.ResetElement(Element);
	if (!CurrentSaveGame->SetLayoutProfile(Profile))
	{
		return false;
	}
	MarkChanged();
	return true;
}

bool UVibeMMOHUDLayoutSubsystem::ResetLayout()
{
	if (!CurrentSaveGame && !LoadOrCreateLayout())
	{
		return false;
	}
	if (!CurrentSaveGame->IsLoadedDataSupported())
	{
		return false;
	}
	if (CurrentSaveGame->GetLayoutProfile().ElementOverrides.IsEmpty())
	{
		return true;
	}

	FVibeMMOHUDLayoutProfile Profile;
	if (!CurrentSaveGame->SetLayoutProfile(Profile))
	{
		return false;
	}
	MarkChanged();
	return true;
}

bool UVibeMMOHUDLayoutSubsystem::SaveLayoutNow()
{
	if (!CurrentSaveGame && !LoadOrCreateLayout())
	{
		return false;
	}
	if (!CurrentSaveGame->IsLoadedDataSupported())
	{
		return false;
	}
	if (!bDirty)
	{
		return true;
	}
	if (CurrentSaveGame->IsSaveInProgress())
	{
		return false;
	}

	const bool bRequested = CurrentSaveGame->SaveGameToSlotForLocalPlayer();
	return bRequested && CurrentSaveGame->WasLastSaveSuccessful();
}

bool UVibeMMOHUDLayoutSubsystem::SaveLayoutAsync()
{
	// HUD Apply/Done already calls this name. The payload is tiny, and a synchronous
	// commit guarantees there is no older async snapshot left to overwrite teardown edits.
	return SaveLayoutNow();
}

FString UVibeMMOHUDLayoutSubsystem::BuildSaveSlotName(const ULocalPlayer* LocalPlayer)
{
	if (!LocalPlayer)
	{
		return BuildSaveSlotNameForIdentity(
			UVibeMMOHUDLayoutSaveGame::DefaultSlotBase, FString(), 0);
	}

	const FUniqueNetIdRepl PreferredId = LocalPlayer->GetPreferredUniqueNetId();
	return BuildSaveSlotNameForIdentity(
		UVibeMMOHUDLayoutSaveGame::DefaultSlotBase,
		PreferredId.IsValid() ? PreferredId.ToString() : FString(),
		LocalPlayer->GetPlatformUserIndex());
}

FString UVibeMMOHUDLayoutSubsystem::BuildSaveSlotNameForIdentity(
	const FString& BaseSlot,
	const FString& UserIdentity,
	const int32 PlatformUserIndex)
{
	const FString SafeBase = BaseSlot.IsEmpty()
		? FString(UVibeMMOHUDLayoutSaveGame::DefaultSlotBase)
		: BaseSlot;
	if (!UserIdentity.IsEmpty())
	{
		return FString::Printf(TEXT("%s_Account_%s"),
			*SafeBase, *FMD5::HashAnsiString(*UserIdentity));
	}

	return FString::Printf(TEXT("%s_Platform_%d"),
		*SafeBase, FMath::Max(0, PlatformUserIndex));
}

void UVibeMMOHUDLayoutSubsystem::MarkChanged()
{
	bDirty = true;
	OnLayoutChanged.Broadcast();
}

void UVibeMMOHUDLayoutSubsystem::HandleSaveCompleted(const bool bSuccess)
{
	if (bSuccess)
	{
		bDirty = false;
		if (!PendingFallbackSlotToDelete.IsEmpty())
		{
			if (!UGameplayStatics::DeleteGameInSlot(
				PendingFallbackSlotToDelete, PendingFallbackPlatformUserIndex))
			{
				UE_LOG(LogVibeMMOHUDLayout, Warning,
					TEXT("Migrated HUD layout but could not remove fallback slot '%s'."),
					*PendingFallbackSlotToDelete);
			}
			PendingFallbackSlotToDelete.Reset();
			PendingFallbackPlatformUserIndex = INDEX_NONE;
		}
	}

	if (!bSuccess)
	{
		UE_LOG(LogVibeMMOHUDLayout, Warning,
			TEXT("Failed to persist HUD layout slot '%s'."),
			CurrentSaveGame ? *CurrentSaveGame->GetSaveSlotName() : TEXT("<none>"));
	}
}
