#include "RedGameInstance.h"

#include "Engine/Engine.h"
#include "Engine/LocalPlayer.h"
#include "GameFramework/PlayerController.h"
#include "Misc/App.h"
#include "Misc/CommandLine.h"
#include "Misc/Parse.h"
#include "Online/OnlineSessionNames.h"
#include "OnlineSessionSettings.h"
#include "OnlineSubsystem.h"
#include "OnlineSubsystemUtils.h"
#include "Interfaces/OnlineExternalUIInterface.h"
#include "TimerManager.h"
#include "UObject/UObjectGlobals.h"

namespace RedSessionKeys
{
	const FName ProductId(TEXT("REDMMO_PRODUCT_ID"));
	const FName BuildId(TEXT("REDMMO_BUILD_ID"));
	const FName SessionType(TEXT("REDMMO_SESSION_TYPE"));
	const FName ServerName(TEXT("REDMMO_SERVER_NAME"));

	const FString DefaultProductId(TEXT("RedMMOTitan"));
	const FString DefaultBuildId(TEXT("RedMMOTitan-UE5.8-Windows"));
	const FString DefaultSessionType(TEXT("PvP"));
}

void URedGameInstance::Init()
{
	Super::Init();
	MaxPublicPlayers = FMath::Max(8, MaxPublicPlayers);
	MaxSearchResults = FMath::Max(1, MaxSearchResults);

	PostLoadMapHandle = FCoreUObjectDelegates::PostLoadMapWithWorld.AddUObject(
		this, &URedGameInstance::OnPostLoadMapWithWorld);
	if (GEngine)
	{
		NetworkFailureHandle = GEngine->OnNetworkFailure().AddUObject(this, &URedGameInstance::OnNetworkFailure);
		TravelFailureHandle = GEngine->OnTravelFailure().AddUObject(this, &URedGameInstance::OnTravelFailure);
	}

	if (IOnlineSubsystem* OSS = Online::GetSubsystem(GetWorld()))
	{
		const FName SubsystemName = OSS->GetSubsystemName();
		UE_LOG(LogTemp, Display, TEXT("[Red] OnlineSubsystem = %s"), *SubsystemName.ToString());
		Sessions = OSS->GetSessionInterface();
		if (Sessions.IsValid())
		{
			InviteDelegate = FOnSessionUserInviteAcceptedDelegate::CreateUObject(this, &URedGameInstance::OnInviteAccepted);
			InviteHandle = Sessions->AddOnSessionUserInviteAcceptedDelegate_Handle(InviteDelegate);
			SetSessionState(Sessions->GetNamedSession(NAME_GameSession)
				? ERedSessionState::InSession
				: ERedSessionState::Idle);

			int32 AutoMatchCommandLineValue = 1;
			FParse::Value(FCommandLine::Get(), TEXT("AutoMatch="), AutoMatchCommandLineValue);
			const bool bCommandLineOptOut = FParse::Param(FCommandLine::Get(), TEXT("NoAutoMatch"))
				|| FParse::Param(FCommandLine::Get(), TEXT("RedNoAutoMatch"))
				|| AutoMatchCommandLineValue == 0;
			const bool bNoSteam = FParse::Param(FCommandLine::Get(), TEXT("nosteam"));
			bAutoMatchEligible = bAutoMatchOnStartup
				&& !bCommandLineOptOut
				&& !bNoSteam
				&& !GIsEditor
				&& FApp::IsGame()
				&& !IsRunningCommandlet()
				&& !IsRunningDedicatedServer()
				&& SubsystemName == FName(TEXT("STEAM"));

			if (bAutoMatchEligible)
			{
				UE_LOG(LogTemp, Display, TEXT("[Red][QuickMatch] Armed for packaged Steam startup. "
					"Use -NoAutoMatch (or -AutoMatch=0) to open offline/manual instead."));
			}
			else
			{
				UE_LOG(LogTemp, Display, TEXT("[Red][QuickMatch] Disabled "
					"(configured=%s, opt-out=%s, nosteam=%s, editor=%s, game=%s, dedicated=%s, subsystem=%s)."),
					bAutoMatchOnStartup ? TEXT("true") : TEXT("false"),
					bCommandLineOptOut ? TEXT("true") : TEXT("false"),
					bNoSteam ? TEXT("true") : TEXT("false"),
					GIsEditor ? TEXT("true") : TEXT("false"),
					FApp::IsGame() ? TEXT("true") : TEXT("false"),
					IsRunningDedicatedServer() ? TEXT("true") : TEXT("false"),
					*SubsystemName.ToString());
			}
			return;
		}
	}

	ReportSessionError(TEXT("No online session interface. Start Steam and make sure the Steam subsystem is enabled."));
}

void URedGameInstance::Shutdown()
{
	if (UWorld* World = GetWorld())
	{
		World->GetTimerManager().ClearTimer(AutoMatchTimerHandle);
	}
	bAutoMatchActive = false;
	bAutoMatchSearchPending = false;
	bAutoMatchJoinPending = false;

	if (PostLoadMapHandle.IsValid())
	{
		FCoreUObjectDelegates::PostLoadMapWithWorld.Remove(PostLoadMapHandle);
		PostLoadMapHandle.Reset();
	}
	if (GEngine)
	{
		if (NetworkFailureHandle.IsValid())
		{
			GEngine->OnNetworkFailure().Remove(NetworkFailureHandle);
			NetworkFailureHandle.Reset();
		}
		if (TravelFailureHandle.IsValid())
		{
			GEngine->OnTravelFailure().Remove(TravelFailureHandle);
			TravelFailureHandle.Reset();
		}
	}

	if (Sessions.IsValid())
	{
		ClearOneShotDelegateHandles();
		if (InviteHandle.IsValid())
		{
			Sessions->ClearOnSessionUserInviteAcceptedDelegate_Handle(InviteHandle);
			InviteHandle.Reset();
		}
	}

	LastSearch.Reset();
	CompatibleSearchResultIndices.Reset();
	Sessions.Reset();
	Super::Shutdown();
}

// ---------------- HOST ----------------
void URedGameInstance::HostGame()
{
	CancelAutoMatch(TEXT("manual HostGame request"));
	if (!Sessions.IsValid())
	{
		ReportSessionError(TEXT("Cannot host: no online session interface (is Steam running?)."));
		return;
	}
	if (IsOperationInFlight())
	{
		ReportSessionError(TEXT("Cannot host while another multiplayer operation is in progress."), true);
		return;
	}

	LastSessionError.Reset();
	ReconnectSearchResult = FOnlineSessionSearchResult();
	LastSuccessfulConnectString.Reset();
	ReconnectSessionId.Reset();
	ReconnectControllerId = 0;
	QueueSessionAction(EPendingSessionAction::Host);
}

void URedGameInstance::BeginCreateSession()
{
	if (!Sessions.IsValid())
	{
		ReportSessionError(TEXT("CreateSession aborted: the session interface is unavailable."));
		return;
	}

	FOnlineSessionSettings Settings;
	Settings.bIsLANMatch = false;
	Settings.NumPublicConnections = FMath::Max(8, MaxPublicPlayers);
	Settings.NumPrivateConnections = 0;
	Settings.bShouldAdvertise = true;
	Settings.bAllowJoinInProgress = true;
	Settings.bAllowInvites = true;
	Settings.bUsesPresence = true;
	Settings.bUseLobbiesIfAvailable = true;
	Settings.bAllowJoinViaPresence = true;
	Settings.bAllowJoinViaPresenceFriendsOnly = false;

	const FString ProductId = GetEffectiveProductId();
	const FString BuildId = GetEffectiveBuildId();
	const FString Type = GetEffectiveSessionType();
	// GetBuildUniqueId uses the stable release override in DefaultEngine.ini. The readable
	// SessionBuildId is retained as an independently advertised compatibility fence.
	Settings.BuildUniqueId = GetBuildUniqueId();
	Settings.Set(SETTING_MAPNAME, GameplayMap, EOnlineDataAdvertisementType::ViaOnlineService);
	Settings.Set(RedSessionKeys::ProductId, ProductId, EOnlineDataAdvertisementType::ViaOnlineService);
	Settings.Set(RedSessionKeys::BuildId, BuildId, EOnlineDataAdvertisementType::ViaOnlineService);
	Settings.Set(RedSessionKeys::SessionType, Type, EOnlineDataAdvertisementType::ViaOnlineService);
	Settings.Set(RedSessionKeys::ServerName,
		HostedServerName.IsEmpty() ? FString(TEXT("Red MMO Titan PvP")) : HostedServerName,
		EOnlineDataAdvertisementType::ViaOnlineService);

	CreateDelegate = FOnCreateSessionCompleteDelegate::CreateUObject(this, &URedGameInstance::OnCreateSessionComplete);
	CreateHandle = Sessions->AddOnCreateSessionCompleteDelegate_Handle(CreateDelegate);
	SetSessionState(ERedSessionState::Creating);

	if (!Sessions->CreateSession(0, NAME_GameSession, Settings))
	{
		Sessions->ClearOnCreateSessionCompleteDelegate_Handle(CreateHandle);
		CreateHandle.Reset();
		ReportSessionError(TEXT("Steam rejected the CreateSession request before it could start."));
	}
}

void URedGameInstance::OnCreateSessionComplete(FName SessionName, bool bSuccess)
{
	if (SessionName != NAME_GameSession)
	{
		return;
	}

	if (Sessions.IsValid() && CreateHandle.IsValid())
	{
		Sessions->ClearOnCreateSessionCompleteDelegate_Handle(CreateHandle);
		CreateHandle.Reset();
	}

	if (!bSuccess)
	{
		FailAndCleanupNamedSession(TEXT("CreateSession failed."));
		return;
	}

	UE_LOG(LogTemp, Display, TEXT("[Red] Session created (%d public slots, product=%s, build=%s) - becoming listen server"),
		FMath::Max(8, MaxPublicPlayers), *GetEffectiveProductId(), *GetEffectiveBuildId());
	const FString HostTravelURL = GetHostTravelURL();
	bHostTravelPending = true;
	bClientTravelPending = false;
	SetSessionState(ERedSessionState::Traveling);

	if (UWorld* World = GetWorld())
	{
		if (World->ServerTravel(HostTravelURL))
		{
			// State remains Traveling. OnPostLoadMapWithWorld starts the advertised session and
			// OnStartSessionComplete is the only path that marks the host InSession.
			OnSessionTravelReady.Broadcast(HostTravelURL);
			return;
		}
	}

	bHostTravelPending = false;
	FailAndCleanupNamedSession(TEXT("Session was created, but listen-server travel failed."));
}

void URedGameInstance::BeginStartHostedSession()
{
	if (SessionState != ERedSessionState::Traveling || StartHandle.IsValid())
	{
		return;
	}

	FNamedOnlineSession* NamedSession = Sessions.IsValid()
		? Sessions->GetNamedSession(NAME_GameSession) : nullptr;
	if (!NamedSession)
	{
		FailAndCleanupNamedSession(TEXT("The gameplay map loaded, but the hosted Steam session no longer exists."));
		return;
	}
	if (NamedSession->SessionState == EOnlineSessionState::InProgress)
	{
		LastSessionError.Reset();
		SetSessionState(ERedSessionState::InSession);
		return;
	}
	if (NamedSession->SessionState == EOnlineSessionState::Starting)
	{
		return;
	}

	UE_LOG(LogTemp, Display, TEXT("[Red] Gameplay world ready; starting hosted Steam session"));
	StartDelegate = FOnStartSessionCompleteDelegate::CreateUObject(this, &URedGameInstance::OnStartSessionComplete);
	StartHandle = Sessions->AddOnStartSessionCompleteDelegate_Handle(StartDelegate);
	if (!Sessions->StartSession(NAME_GameSession))
	{
		Sessions->ClearOnStartSessionCompleteDelegate_Handle(StartHandle);
		StartHandle.Reset();
		FailAndCleanupNamedSession(TEXT("Steam rejected StartSession after the host gameplay map loaded."));
	}
}

void URedGameInstance::NotifyGameplayWorldReady(UWorld* GameplayWorld)
{
	if (!GameplayWorld || GameplayWorld->GetGameInstance() != this
		|| SessionState != ERedSessionState::Traveling || !bHostTravelPending
		|| !IsGameplayWorld(GameplayWorld))
	{
		return;
	}

	UE_LOG(LogTemp, Display,
		TEXT("[Red] GameMode confirmed hosted gameplay world '%s' (netmode=%d)"),
		*GameplayWorld->GetMapName(), static_cast<int32>(GameplayWorld->GetNetMode()));
	bHostTravelPending = false;
	BeginStartHostedSession();
}

void URedGameInstance::OnStartSessionComplete(FName SessionName, bool bSuccess)
{
	if (SessionName != NAME_GameSession)
	{
		return;
	}

	if (Sessions.IsValid() && StartHandle.IsValid())
	{
		Sessions->ClearOnStartSessionCompleteDelegate_Handle(StartHandle);
		StartHandle.Reset();
	}

	if (!bSuccess)
	{
		FailAndCleanupNamedSession(TEXT("Steam StartSession failed after the host gameplay map loaded."));
		return;
	}

	LastSessionError.Reset();
	SetSessionState(ERedSessionState::InSession);
}

void URedGameInstance::InviteSteamFriends()
{
	if (!Sessions.IsValid())
	{
		ReportSessionError(TEXT("Steam invite unavailable: the online session interface is not active."), true);
		return;
	}

	FNamedOnlineSession* NamedSession = Sessions->GetNamedSession(NAME_GameSession);
	if (!NamedSession)
	{
		ReportSessionError(TEXT("Steam invite unavailable: host a RED server before inviting friends."), true);
		return;
	}
	if (!NamedSession->bHosting)
	{
		ReportSessionError(TEXT("Steam invite unavailable: only the current RED session host can send invites."), true);
		return;
	}
	if (SessionState != ERedSessionState::InSession || IsOperationInFlight())
	{
		ReportSessionError(TEXT("Steam invite unavailable: wait until the hosted RED server is fully connected."), true);
		return;
	}

	ULocalPlayer* LocalPlayer = GetFirstGamePlayer();
	if (!LocalPlayer || LocalPlayer->GetControllerId() < 0)
	{
		ReportSessionError(TEXT("Steam invite unavailable: no signed-in local player was found."), true);
		return;
	}

	IOnlineSubsystem* OSS = Online::GetSubsystem(GetWorld());
	if (!OSS || OSS->GetSubsystemName() != FName(TEXT("STEAM")))
	{
		ReportSessionError(TEXT("Steam invite unavailable: launch the packaged game through Steam with the Steam client online."), true);
		return;
	}

	const IOnlineExternalUIPtr ExternalUI = OSS->GetExternalUIInterface();
	if (!ExternalUI.IsValid())
	{
		ReportSessionError(TEXT("Steam invite unavailable: this Steam subsystem has no external overlay UI."), true);
		return;
	}

	const int32 LocalUserNum = LocalPlayer->GetControllerId();
	if (!ExternalUI->ShowInviteUI(LocalUserNum, NAME_GameSession))
	{
		ReportSessionError(TEXT("Steam could not open the friend invite dialog. Check that the Steam overlay is enabled and you are signed in."), true);
		return;
	}

	LastSessionError.Reset();
	const FString StatusMessage = TEXT("Steam invite dialog opened. Select a friend and send the RED PvP lobby invite.");
	UE_LOG(LogTemp, Display, TEXT("[Red][SteamInvite] Opened Steam invite UI for %s (local user %d)."),
		*FName(NAME_GameSession).ToString(), LocalUserNum);
	OnSessionStatus.Broadcast(StatusMessage);
}

bool URedGameInstance::CanInviteSteamFriends() const
{
	if (!Sessions.IsValid() || SessionState != ERedSessionState::InSession
		|| IsOperationInFlight() || !GetFirstGamePlayer())
	{
		return false;
	}

	const FNamedOnlineSession* NamedSession = Sessions->GetNamedSession(NAME_GameSession);
	return NamedSession && NamedSession->bHosting;
}

// ---------------- DESTROY / TRANSITION ----------------
void URedGameInstance::QueueSessionAction(EPendingSessionAction Action)
{
	PendingAction = Action;

	if (!Sessions.IsValid() || Sessions->GetNamedSession(NAME_GameSession) == nullptr)
	{
		ExecutePendingAction();
		return;
	}

	DestroyDelegate = FOnDestroySessionCompleteDelegate::CreateUObject(this, &URedGameInstance::OnDestroySessionComplete);
	DestroyHandle = Sessions->AddOnDestroySessionCompleteDelegate_Handle(DestroyDelegate);
	if (Action != EPendingSessionAction::CleanupFailure)
	{
		SetSessionState(ERedSessionState::Destroying);
	}

	if (!Sessions->DestroySession(NAME_GameSession))
	{
		Sessions->ClearOnDestroySessionCompleteDelegate_Handle(DestroyHandle);
		DestroyHandle.Reset();
		const bool bWasFailureCleanup = PendingAction == EPendingSessionAction::CleanupFailure;
		PendingAction = EPendingSessionAction::None;
		if (bWasFailureCleanup)
		{
			ReportSessionError(LastSessionError + TEXT(" Steam also rejected stale-session cleanup."));
		}
		else
		{
			ReportSessionError(TEXT("Steam rejected the request to leave the existing session."));
		}
	}
}

void URedGameInstance::OnDestroySessionComplete(FName SessionName, bool bSuccess)
{
	if (SessionName != NAME_GameSession)
	{
		return;
	}

	if (Sessions.IsValid() && DestroyHandle.IsValid())
	{
		Sessions->ClearOnDestroySessionCompleteDelegate_Handle(DestroyHandle);
		DestroyHandle.Reset();
	}

	if (!bSuccess)
	{
		const bool bWasFailureCleanup = PendingAction == EPendingSessionAction::CleanupFailure;
		PendingAction = EPendingSessionAction::None;
		if (bWasFailureCleanup)
		{
			ReportSessionError(LastSessionError + TEXT(" Steam also failed to clear stale session membership."));
		}
		else
		{
			ReportSessionError(TEXT("Could not leave the existing Steam session."));
		}
		return;
	}

	ExecutePendingAction();
}

void URedGameInstance::ExecutePendingAction()
{
	const EPendingSessionAction Action = PendingAction;
	PendingAction = EPendingSessionAction::None;

	switch (Action)
	{
	case EPendingSessionAction::Host:
		BeginCreateSession();
		break;
	case EPendingSessionAction::JoinSearchResult:
		BeginJoinSearchResult();
		break;
	case EPendingSessionAction::DirectTravel:
		BeginDirectTravel();
		break;
	case EPendingSessionAction::ReconnectSearch:
		BeginFindGames(true);
		break;
	case EPendingSessionAction::AutoMatchRetry:
		SetSessionState(ERedSessionState::Idle);
		ScheduleAutoMatchSearch(AutoMatchRetryDelayMin, AutoMatchRetryDelayMax, false,
			TEXT("the selected server disappeared before the join completed"));
		break;
	case EPendingSessionAction::Leave:
		CompleteLeaveGame();
		break;
	case EPendingSessionAction::CleanupFailure:
		SetSessionState(ERedSessionState::Error);
		break;
	default:
		SetSessionState(ERedSessionState::Idle);
		break;
	}
}

// ---------------- FIND ----------------
void URedGameInstance::FindGames()
{
	CancelAutoMatch(TEXT("manual server-browser search"));
	if (!Sessions.IsValid())
	{
		ReportSessionError(TEXT("Cannot search: no online session interface (is Steam running?)."));
		return;
	}
	if (IsOperationInFlight())
	{
		ReportSessionError(TEXT("Cannot search while another multiplayer operation is in progress."), true);
		return;
	}
	BeginFindGames(false);
}

void URedGameInstance::BeginFindGames(bool bForReconnect)
{
	if (!Sessions.IsValid())
	{
		ReportSessionError(TEXT("Cannot search: the online session interface is unavailable."));
		return;
	}

	LastSessionError.Reset();
	bReconnectSearchPending = bForReconnect;
	SessionResults.Reset();
	CompatibleSearchResultIndices.Reset();
	OnSessionResultsChanged.Broadcast(0);
	LastSearch = MakeShared<FOnlineSessionSearch>();
	LastSearch->bIsLanQuery = false;
	LastSearch->MaxSearchResults = FMath::Max(1, MaxSearchResults);
	// The Marketplace Steam Integration Kit 1.9 replacement keys lobby discovery
	// with the legacy SEARCH_PRESENCE name. Titan.uproject deliberately enables
	// SIK as the sole Steam stack, so do not also add UE 5.8's SEARCH_LOBBIES key:
	// SIK reports it as an unsupported lobby filter even though the search works.
	LastSearch->QuerySettings.Set(FName(TEXT("SEARCH_PRESENCE")), true, EOnlineComparisonOp::Equals);
	LastSearch->QuerySettings.Set(RedSessionKeys::ProductId, GetEffectiveProductId(), EOnlineComparisonOp::Equals);
	LastSearch->QuerySettings.Set(RedSessionKeys::BuildId, GetEffectiveBuildId(), EOnlineComparisonOp::Equals);
	LastSearch->QuerySettings.Set(RedSessionKeys::SessionType, GetEffectiveSessionType(), EOnlineComparisonOp::Equals);

	FindDelegate = FOnFindSessionsCompleteDelegate::CreateUObject(this, &URedGameInstance::OnFindSessionsComplete);
	FindHandle = Sessions->AddOnFindSessionsCompleteDelegate_Handle(FindDelegate);
	SetSessionState(ERedSessionState::Searching);

	if (!Sessions->FindSessions(0, LastSearch.ToSharedRef()))
	{
		Sessions->ClearOnFindSessionsCompleteDelegate_Handle(FindHandle);
		FindHandle.Reset();
		bReconnectSearchPending = false;
		const bool bWasAutoMatch = bAutoMatchSearchPending;
		const bool bWasFinalVerification = bAutoMatchFinalVerificationPending;
		bAutoMatchSearchPending = false;
		bAutoMatchFinalVerificationPending = false;
		if (bWasAutoMatch)
		{
			LastSessionError.Reset();
			SetSessionState(ERedSessionState::Idle);
			UE_LOG(LogTemp, Warning, TEXT("[Red][QuickMatch] Steam rejected FindSessions before it started; retrying safely."));
		}
		else
		{
			ReportSessionError(TEXT("Steam rejected the FindSessions request before it could start."));
		}
		OnSessionSearchFinished.Broadcast(false, 0);
		if (bWasAutoMatch)
		{
			HandleAutoMatchSearchComplete(false, bWasFinalVerification);
		}
	}
}

void URedGameInstance::OnFindSessionsComplete(bool bSuccess)
{
	if (Sessions.IsValid() && FindHandle.IsValid())
	{
		Sessions->ClearOnFindSessionsCompleteDelegate_Handle(FindHandle);
		FindHandle.Reset();
	}

	const bool bCompleteReconnect = bReconnectSearchPending;
	const bool bCompleteAutoMatch = bAutoMatchSearchPending;
	const bool bFinalAutoMatchVerification = bAutoMatchFinalVerificationPending;
	bReconnectSearchPending = false;
	bAutoMatchSearchPending = false;
	bAutoMatchFinalVerificationPending = false;
	BuildSessionResultSummaries();
	if (bSuccess)
	{
		LastSessionError.Reset();
		SetSessionState(Sessions.IsValid() && Sessions->GetNamedSession(NAME_GameSession)
			? ERedSessionState::InSession
			: ERedSessionState::Idle);
		const int32 RawResultCount = LastSearch.IsValid() ? LastSearch->SearchResults.Num() : 0;
		UE_LOG(LogTemp, Display,
			TEXT("[Red] Steam search returned %d raw lobbies / %d compatible RED sessions - JoinIndex <n> to join, or accept a Steam invite"),
			RawResultCount, SessionResults.Num());
	}
	else
	{
		if (bCompleteAutoMatch)
		{
			LastSessionError.Reset();
			SetSessionState(ERedSessionState::Idle);
			UE_LOG(LogTemp, Warning, TEXT("[Red][QuickMatch] Steam session search failed; no host will be created from an unverified result."));
		}
		else
		{
			ReportSessionError(TEXT("Steam session search failed."));
		}
	}

	OnSessionResultsChanged.Broadcast(SessionResults.Num());
	OnSessionSearchFinished.Broadcast(bSuccess, SessionResults.Num());

	if (bSuccess && bCompleteReconnect)
	{
		int32 MatchingBrowserIndex = INDEX_NONE;
		for (int32 Index = 0; Index < SessionResults.Num(); ++Index)
		{
			if (SessionResults[Index].SessionId == ReconnectSessionId)
			{
				MatchingBrowserIndex = Index;
				break;
			}
		}

		if (MatchingBrowserIndex == INDEX_NONE
			|| !CompatibleSearchResultIndices.IsValidIndex(MatchingBrowserIndex)
			|| !LastSearch.IsValid())
		{
			ReportSessionError(TEXT("The previous server is no longer advertising a compatible RED session."));
			return;
		}
		if (!SessionResults[MatchingBrowserIndex].bJoinable)
		{
			ReportSessionError(TEXT("The previous server was refreshed successfully but currently has no open player slot."));
			return;
		}

		const int32 RawIndex = CompatibleSearchResultIndices[MatchingBrowserIndex];
		if (!LastSearch->SearchResults.IsValidIndex(RawIndex))
		{
			ReportSessionError(TEXT("The refreshed reconnect result expired. Search again before joining."));
			return;
		}

		JoinSearchResult(ReconnectControllerId, LastSearch->SearchResults[RawIndex]);
	}

	if (bCompleteAutoMatch)
	{
		HandleAutoMatchSearchComplete(bSuccess, bFinalAutoMatchVerification);
	}
}

void URedGameInstance::BuildSessionResultSummaries()
{
	SessionResults.Reset();
	CompatibleSearchResultIndices.Reset();
	if (!LastSearch.IsValid())
	{
		return;
	}

	for (int32 RawIndex = 0; RawIndex < LastSearch->SearchResults.Num(); ++RawIndex)
	{
		const FOnlineSessionSearchResult& Result = LastSearch->SearchResults[RawIndex];
		if (!IsCompatibleResult(Result))
		{
			continue;
		}

		FRedSessionResultSummary Summary;
		Summary.SearchIndex = SessionResults.Num();
		Summary.OwnerName = Result.Session.OwningUserName;
		Summary.SessionId = Result.GetSessionIdStr();
		Summary.PingMs = Result.PingInMs;
		Summary.MaxPlayers = Result.Session.SessionSettings.NumPublicConnections;
		Summary.CurrentPlayers = FMath::Max(0,
			Summary.MaxPlayers - Result.Session.NumOpenPublicConnections);
		Summary.bJoinable = Result.IsValid() && Result.Session.NumOpenPublicConnections > 0;

		Result.Session.SessionSettings.Get(RedSessionKeys::ServerName, Summary.ServerName);
		Result.Session.SessionSettings.Get(RedSessionKeys::BuildId, Summary.BuildId);
		Result.Session.SessionSettings.Get(RedSessionKeys::SessionType, Summary.SessionType);
		Result.Session.SessionSettings.Get(SETTING_MAPNAME, Summary.MapName);
		if (Summary.ServerName.IsEmpty())
		{
			Summary.ServerName = Summary.OwnerName.IsEmpty() ? FString(TEXT("Red MMO Titan Server")) : Summary.OwnerName;
		}

		CompatibleSearchResultIndices.Add(RawIndex);
		SessionResults.Add(MoveTemp(Summary));
	}
}

bool URedGameInstance::IsCompatibleResult(const FOnlineSessionSearchResult& Result) const
{
	if (!Result.IsValid())
	{
		return false;
	}

	FString ProductId;
	FString BuildId;
	FString Type;
	return Result.Session.SessionSettings.Get(RedSessionKeys::ProductId, ProductId)
		&& Result.Session.SessionSettings.Get(RedSessionKeys::BuildId, BuildId)
		&& Result.Session.SessionSettings.Get(RedSessionKeys::SessionType, Type)
		&& ProductId.Equals(GetEffectiveProductId(), ESearchCase::CaseSensitive)
		&& BuildId.Equals(GetEffectiveBuildId(), ESearchCase::CaseSensitive)
		&& Type.Equals(GetEffectiveSessionType(), ESearchCase::CaseSensitive);
}

bool URedGameInstance::GetSessionResultSummary(int32 Index, FRedSessionResultSummary& OutResult) const
{
	if (!SessionResults.IsValidIndex(Index))
	{
		return false;
	}

	OutResult = SessionResults[Index];
	return true;
}

// ---------------- PACKAGED STEAM QUICK MATCH ----------------
void URedGameInstance::TryStartAutoMatch(UWorld* LoadedWorld)
{
	if (!bAutoMatchEligible || bAutoMatchStarted || !LoadedWorld || !LoadedWorld->IsGameWorld())
	{
		return;
	}
	if (Sessions.IsValid() && Sessions->GetNamedSession(NAME_GameSession) != nullptr)
	{
		UE_LOG(LogTemp, Display, TEXT("[Red][QuickMatch] Startup already has a named session; automatic matchmaking is not needed."));
		bAutoMatchStarted = true;
		return;
	}

	bAutoMatchStarted = true;
	bAutoMatchActive = true;
	AutoMatchSuccessfulEmptySearches = 0;
	AutoMatchConsecutiveSearchFailures = 0;
	UE_LOG(LogTemp, Display, TEXT("[Red][QuickMatch] Starting automatic RED PvP matchmaking on world '%s'. "
		"Filters: product=%s, build=%s, type=%s."),
		*LoadedWorld->GetMapName(), *GetEffectiveProductId(), *GetEffectiveBuildId(),
		*GetEffectiveSessionType());
	ScheduleAutoMatchSearch(AutoMatchInitialDelayMin, AutoMatchInitialDelayMax, false,
		TEXT("initial Steam lobby discovery"));
}

void URedGameInstance::ScheduleAutoMatchSearch(float MinDelay, float MaxDelay,
	bool bFinalVerification, const TCHAR* Reason)
{
	if (!bAutoMatchEligible || !bAutoMatchActive)
	{
		return;
	}

	UWorld* World = GetWorld();
	if (!World || !World->IsGameWorld())
	{
		UE_LOG(LogTemp, Warning, TEXT("[Red][QuickMatch] Cannot schedule the next search because no game world is active; use F8 for the manual browser."));
		bAutoMatchActive = false;
		return;
	}

	const float SafeMin = FMath::Max(0.0f, MinDelay);
	const float SafeMax = FMath::Max(SafeMin, MaxDelay);
	const float Delay = FMath::FRandRange(SafeMin, SafeMax);
	bScheduledAutoMatchFinalVerification = bFinalVerification;
	World->GetTimerManager().ClearTimer(AutoMatchTimerHandle);
	World->GetTimerManager().SetTimer(AutoMatchTimerHandle, this,
		&URedGameInstance::StartScheduledAutoMatchSearch, Delay, false);
	UE_LOG(LogTemp, Display, TEXT("[Red][QuickMatch] Next %s search in %.2f seconds (%s)."),
		bFinalVerification ? TEXT("host-election verification") : TEXT("discovery"),
		Delay, Reason ? Reason : TEXT("retry"));
}

void URedGameInstance::StartScheduledAutoMatchSearch()
{
	if (!bAutoMatchEligible || !bAutoMatchActive)
	{
		return;
	}
	if (!Sessions.IsValid())
	{
		UE_LOG(LogTemp, Warning, TEXT("[Red][QuickMatch] Session interface disappeared; automatic matchmaking stopped. F8 remains available."));
		bAutoMatchActive = false;
		return;
	}
	if (Sessions->GetNamedSession(NAME_GameSession) != nullptr || IsOperationInFlight())
	{
		CancelAutoMatch(TEXT("another session operation became active"));
		return;
	}

	bAutoMatchSearchPending = true;
	bAutoMatchFinalVerificationPending = bScheduledAutoMatchFinalVerification;
	UE_LOG(LogTemp, Display, TEXT("[Red][QuickMatch] Searching Steam for open compatible RED sessions%s..."),
		bAutoMatchFinalVerificationPending ? TEXT(" (final check before hosting)") : TEXT(""));
	BeginFindGames(false);
}

void URedGameInstance::HandleAutoMatchSearchComplete(bool bSuccess, bool bFinalVerification)
{
	if (!bAutoMatchEligible || !bAutoMatchActive)
	{
		return;
	}

	if (!bSuccess)
	{
		++AutoMatchConsecutiveSearchFailures;
		if (AutoMatchConsecutiveSearchFailures >= 3)
		{
			bAutoMatchActive = false;
			SetSessionState(ERedSessionState::Idle);
			UE_LOG(LogTemp, Error, TEXT("[Red][QuickMatch] Three Steam searches failed. "
				"No listen host was created because an empty result was never verified; press F8 to retry manually."));
			return;
		}

		ScheduleAutoMatchSearch(AutoMatchRetryDelayMin, AutoMatchRetryDelayMax,
			bFinalVerification, TEXT("transient Steam search failure"));
		return;
	}

	AutoMatchConsecutiveSearchFailures = 0;
	const int32 BestIndex = FindBestAutoMatchResult();
	if (BestIndex != INDEX_NONE
		&& CompatibleSearchResultIndices.IsValidIndex(BestIndex)
		&& LastSearch.IsValid())
	{
		const int32 RawIndex = CompatibleSearchResultIndices[BestIndex];
		if (LastSearch->SearchResults.IsValidIndex(RawIndex))
		{
			const FRedSessionResultSummary& Best = SessionResults[BestIndex];
			UE_LOG(LogTemp, Display, TEXT("[Red][QuickMatch] Joining best open session '%s' "
				"(%d/%d players, %d ms, id=%s)."), *Best.ServerName,
				Best.CurrentPlayers, Best.MaxPlayers, Best.PingMs, *Best.SessionId);
			bAutoMatchJoinPending = true;
			JoinSearchResult(0, LastSearch->SearchResults[RawIndex]);
			return;
		}
	}

	++AutoMatchSuccessfulEmptySearches;
	UE_LOG(LogTemp, Display, TEXT("[Red][QuickMatch] No open compatible RED session found (successful empty search %d/%d)."),
		AutoMatchSuccessfulEmptySearches, FMath::Max(1, AutoMatchEmptySearchesBeforeHost));

	if (bFinalVerification)
	{
		bAutoMatchActive = false;
		UE_LOG(LogTemp, Display, TEXT("[Red][QuickMatch] Final randomized verification is still empty; "
			"creating the listen host now."));
		QueueSessionAction(EPendingSessionAction::Host);
		return;
	}

	if (AutoMatchSuccessfulEmptySearches < FMath::Max(1, AutoMatchEmptySearchesBeforeHost))
	{
		ScheduleAutoMatchSearch(AutoMatchRetryDelayMin, AutoMatchRetryDelayMax, false,
			TEXT("no open RED session yet"));
		return;
	}

	ScheduleAutoMatchSearch(AutoMatchHostElectionDelayMin, AutoMatchHostElectionDelayMax, true,
		TEXT("randomized host election to prevent simultaneous clients from both hosting"));
}

void URedGameInstance::HandleAutoMatchJoinFailure(const FString& Message)
{
	bAutoMatchJoinPending = false;
	bAutoMatchActive = true;
	bClientTravelPending = false;
	bHostTravelPending = false;
	LastSessionError.Reset();
	UE_LOG(LogTemp, Warning, TEXT("[Red][QuickMatch] %s The lobby may have closed; returning to discovery."), *Message);

	if (Sessions.IsValid() && Sessions->GetNamedSession(NAME_GameSession) != nullptr)
	{
		QueueSessionAction(EPendingSessionAction::AutoMatchRetry);
		return;
	}

	SetSessionState(ERedSessionState::Idle);
	ScheduleAutoMatchSearch(AutoMatchRetryDelayMin, AutoMatchRetryDelayMax, false,
		TEXT("automatic join did not complete"));
}

void URedGameInstance::CancelAutoMatch(const TCHAR* Reason)
{
	const bool bWasActive = bAutoMatchActive || bAutoMatchSearchPending || bAutoMatchJoinPending;
	if (UWorld* World = GetWorld())
	{
		World->GetTimerManager().ClearTimer(AutoMatchTimerHandle);
	}
	bAutoMatchActive = false;
	bAutoMatchSearchPending = false;
	bAutoMatchFinalVerificationPending = false;
	bAutoMatchJoinPending = false;
	if (bWasActive)
	{
		UE_LOG(LogTemp, Display, TEXT("[Red][QuickMatch] Automatic flow cancelled: %s. Manual F8 controls remain available."),
			Reason ? Reason : TEXT("manual action"));
	}
}

int32 URedGameInstance::FindBestAutoMatchResult() const
{
	int32 BestIndex = INDEX_NONE;
	for (int32 Index = 0; Index < SessionResults.Num(); ++Index)
	{
		const FRedSessionResultSummary& Candidate = SessionResults[Index];
		if (!Candidate.bJoinable)
		{
			continue;
		}

		if (BestIndex == INDEX_NONE)
		{
			BestIndex = Index;
			continue;
		}

		const FRedSessionResultSummary& Best = SessionResults[BestIndex];
		const int32 CandidatePing = Candidate.PingMs >= 0 ? Candidate.PingMs : MAX_int32;
		const int32 BestPing = Best.PingMs >= 0 ? Best.PingMs : MAX_int32;
		if (Candidate.CurrentPlayers > Best.CurrentPlayers
			|| (Candidate.CurrentPlayers == Best.CurrentPlayers && CandidatePing < BestPing)
			|| (Candidate.CurrentPlayers == Best.CurrentPlayers && CandidatePing == BestPing
				&& Candidate.SessionId < Best.SessionId))
		{
			BestIndex = Index;
		}
	}
	return BestIndex;
}

// ---------------- JOIN ----------------
void URedGameInstance::JoinIndex(int32 Index)
{
	CancelAutoMatch(TEXT("manual JoinIndex request"));
	if (!Sessions.IsValid())
	{
		ReportSessionError(TEXT("Cannot join: no online session interface (is Steam running?)."));
		return;
	}
	if (IsOperationInFlight())
	{
		ReportSessionError(TEXT("Cannot join while another multiplayer operation is in progress."), true);
		return;
	}
	if (!SessionResults.IsValidIndex(Index) || !LastSearch.IsValid())
	{
		ReportSessionError(FString::Printf(TEXT("No compatible session result at browser index %d (run FindGames first)."), Index));
		return;
	}
	if (!SessionResults[Index].bJoinable)
	{
		ReportSessionError(TEXT("The selected session has no open public player slots."));
		return;
	}

	if (!CompatibleSearchResultIndices.IsValidIndex(Index))
	{
		ReportSessionError(TEXT("The selected browser result is no longer available. Refresh the server list."));
		return;
	}

	const int32 RawSearchIndex = CompatibleSearchResultIndices[Index];
	if (!LastSearch->SearchResults.IsValidIndex(RawSearchIndex))
	{
		ReportSessionError(TEXT("The selected session result is no longer available. Refresh the server list."));
		return;
	}

	JoinSearchResult(0, LastSearch->SearchResults[RawSearchIndex]);
}

void URedGameInstance::JoinHost(const FString& SteamId)
{
	CancelAutoMatch(TEXT("manual JoinHost request"));
#if UE_BUILD_SHIPPING
	ReportSessionError(TEXT("JoinHost is a development-only fallback. Use the RED server browser or a Steam invite."));
	return;
#else
	if (IsOperationInFlight())
	{
		ReportSessionError(TEXT("Cannot direct-connect while another multiplayer operation is in progress."), true);
		return;
	}

	FString SanitizedId = SteamId;
	SanitizedId.TrimStartAndEndInline();
	SanitizedId.RemoveFromStart(TEXT("steam."), ESearchCase::IgnoreCase);
	bool bAllAsciiDigits = !SanitizedId.IsEmpty();
	for (const TCHAR Character : SanitizedId)
	{
		if (Character < TEXT('0') || Character > TEXT('9'))
		{
			bAllAsciiDigits = false;
			break;
		}
	}

	TCHAR* ParseEnd = nullptr;
	const uint64 ParsedSteamId = bAllAsciiDigits
		? FCString::Strtoui64(*SanitizedId, &ParseEnd, 10)
		: 0;
	const FString CanonicalSteamId = FString::Printf(TEXT("%llu"),
		static_cast<unsigned long long>(ParsedSteamId));
	if (!bAllAsciiDigits || ParsedSteamId == 0 || ParseEnd == nullptr || *ParseEnd != TEXT('\0')
		|| CanonicalSteamId != SanitizedId)
	{
		ReportSessionError(TEXT("JoinHost requires a canonical unsigned 64-bit SteamID containing ASCII digits only."));
		return;
	}

	LastSessionError.Reset();
	ReconnectSearchResult = FOnlineSessionSearchResult();
	ReconnectSessionId.Reset();
	ReconnectControllerId = 0;
	LastSuccessfulConnectString.Reset();
	PendingJoinControllerId = 0;
	PendingDirectConnectString = FString::Printf(TEXT("steam.%s"), *SanitizedId);
	QueueSessionAction(EPendingSessionAction::DirectTravel);
#endif
}

void URedGameInstance::JoinSearchResult(int32 ControllerId, const FOnlineSessionSearchResult& Result)
{
	if (!Sessions.IsValid() || !Result.IsValid())
	{
		ReportSessionError(TEXT("Cannot join an invalid or expired session result."));
		return;
	}

	LastSessionError.Reset();
	PendingJoinControllerId = ControllerId;
	PendingJoinResult = Result;
	QueueSessionAction(EPendingSessionAction::JoinSearchResult);
}

void URedGameInstance::BeginJoinSearchResult()
{
	if (!Sessions.IsValid() || !PendingJoinResult.IsValid())
	{
		ReportSessionError(TEXT("JoinSession aborted: the selected session expired."));
		return;
	}

	JoinDelegate = FOnJoinSessionCompleteDelegate::CreateUObject(this, &URedGameInstance::OnJoinSessionComplete);
	JoinHandle = Sessions->AddOnJoinSessionCompleteDelegate_Handle(JoinDelegate);
	SetSessionState(ERedSessionState::Joining);

	if (!Sessions->JoinSession(PendingJoinControllerId, NAME_GameSession, PendingJoinResult))
	{
		Sessions->ClearOnJoinSessionCompleteDelegate_Handle(JoinHandle);
		JoinHandle.Reset();
		if (bAutoMatchJoinPending)
		{
			HandleAutoMatchJoinFailure(TEXT("Steam rejected the automatic JoinSession request before it could start."));
		}
		else
		{
			FailAndCleanupNamedSession(TEXT("Steam rejected the JoinSession request before it could start."));
		}
	}
}

void URedGameInstance::OnJoinSessionComplete(FName SessionName, EOnJoinSessionCompleteResult::Type Result)
{
	if (SessionName != NAME_GameSession)
	{
		return;
	}

	if (Sessions.IsValid() && JoinHandle.IsValid())
	{
		Sessions->ClearOnJoinSessionCompleteDelegate_Handle(JoinHandle);
		JoinHandle.Reset();
	}

	if (Result != EOnJoinSessionCompleteResult::Success)
	{
		const FString FailureMessage = FString::Printf(TEXT("JoinSession failed: %s."), LexToString(Result));
		if (bAutoMatchJoinPending)
		{
			HandleAutoMatchJoinFailure(FailureMessage);
		}
		else
		{
			FailAndCleanupNamedSession(FailureMessage);
		}
		return;
	}

	FString ConnectString;
	if (!Sessions.IsValid() || !Sessions->GetResolvedConnectString(NAME_GameSession, ConnectString) || ConnectString.IsEmpty())
	{
		if (bAutoMatchJoinPending)
		{
			HandleAutoMatchJoinFailure(TEXT("Joined the Steam lobby, but could not resolve the host address."));
		}
		else
		{
			FailAndCleanupNamedSession(TEXT("Joined the Steam lobby, but could not resolve the host address."));
		}
		return;
	}

	ReconnectSearchResult = PendingJoinResult;
	ReconnectSessionId = PendingJoinResult.GetSessionIdStr();
	ReconnectControllerId = PendingJoinControllerId;
	PendingDirectConnectString = ConnectString;
	BeginDirectTravel();
}

void URedGameInstance::BeginDirectTravel()
{
	if (PendingDirectConnectString.IsEmpty())
	{
		if (bAutoMatchJoinPending)
		{
			HandleAutoMatchJoinFailure(TEXT("Automatic travel could not start because no connect address is available."));
		}
		else
		{
			FailAndCleanupNamedSession(TEXT("Direct travel aborted: no connect address is available."));
		}
		return;
	}

	APlayerController* PlayerController = nullptr;
	if (ULocalPlayer* ControllerPlayer = FindLocalPlayerFromControllerId(PendingJoinControllerId))
	{
		PlayerController = ControllerPlayer->GetPlayerController(GetWorld());
	}
	if (!PlayerController)
	{
		if (ULocalPlayer* IndexedPlayer = GetLocalPlayerByIndex(PendingJoinControllerId))
		{
			PlayerController = IndexedPlayer->GetPlayerController(GetWorld());
		}
	}

	if (PlayerController)
	{
		const FString ConnectString = PendingDirectConnectString;
		bClientTravelPending = true;
		bHostTravelPending = false;
		SetSessionState(ERedSessionState::Traveling);
		OnSessionTravelReady.Broadcast(ConnectString);
		PlayerController->ClientTravel(ConnectString, TRAVEL_Absolute);
		// OnPostLoadMapWithWorld confirms the actual gameplay world before InSession.
		return;
	}

	const FString FailureMessage = FString::Printf(
		TEXT("Travel failed: there is no local player controller for controller ID %d."),
		PendingJoinControllerId);
	if (bAutoMatchJoinPending)
	{
		HandleAutoMatchJoinFailure(FailureMessage);
	}
	else
	{
		FailAndCleanupNamedSession(FailureMessage);
	}
}

// ---------------- RECONNECT ----------------
void URedGameInstance::Reconnect()
{
	CancelAutoMatch(TEXT("manual Reconnect request"));
	if (IsOperationInFlight())
	{
		ReportSessionError(TEXT("Cannot reconnect while another multiplayer operation is in progress."), true);
		return;
	}

	LastSessionError.Reset();
	if (!ReconnectSessionId.IsEmpty() && Sessions.IsValid())
	{
		// Do not blindly reuse a stale lobby object. Clear any lingering membership, refresh
		// the RED-only browser, and rejoin only the same still-advertised session ID.
		QueueSessionAction(EPendingSessionAction::ReconnectSearch);
		return;
	}

	if (!LastSuccessfulConnectString.IsEmpty())
	{
		PendingDirectConnectString = LastSuccessfulConnectString;
		QueueSessionAction(EPendingSessionAction::DirectTravel);
		return;
	}

	ReportSessionError(TEXT("No previous server is available to reconnect to."));
}

bool URedGameInstance::CanReconnect() const
{
	return !ReconnectSessionId.IsEmpty() || !LastSuccessfulConnectString.IsEmpty();
}

void URedGameInstance::LeaveGame()
{
	CancelAutoMatch(TEXT("manual LeaveGame request"));
	if (IsOperationInFlight())
	{
		ReportSessionError(TEXT("Cannot leave while another multiplayer operation is in progress."), true);
		return;
	}

	LastSessionError.Reset();
	QueueSessionAction(EPendingSessionAction::Leave);
}

void URedGameInstance::CompleteLeaveGame()
{
	bHostTravelPending = false;
	bClientTravelPending = false;
	bReconnectSearchPending = false;
	PendingJoinResult = FOnlineSessionSearchResult();
	PendingDirectConnectString.Reset();
	SetSessionState(ERedSessionState::Idle);

	if (UWorld* World = GetWorld())
	{
		if (World->GetNetMode() == NM_Client || World->GetNetMode() == NM_ListenServer)
		{
			ReturnToMainMenu();
		}
	}
}

// ---------------- INVITE ACCEPTED ----------------
void URedGameInstance::OnInviteAccepted(const bool bSuccess, const int32 ControllerId,
	FUniqueNetIdPtr UserId, const FOnlineSessionSearchResult& Invite)
{
	if (!bSuccess || !Invite.IsValid())
	{
		ReportSessionError(TEXT("The Steam session invite could not be accepted."));
		return;
	}
	if (IsOperationInFlight())
	{
		ReportSessionError(TEXT("Cannot accept a Steam invite while another multiplayer operation is in progress."), true);
		return;
	}
	if (!IsCompatibleResult(Invite))
	{
		ReportSessionError(TEXT("The Steam invite is not for this RED product, build, and PvP session type."));
		return;
	}

	// Retain the accepting controller ID through JoinSession and ClientTravel. Destroying any
	// local named session first prevents AlreadyInSession during repeated invite tests.
	CancelAutoMatch(TEXT("accepted Steam invite"));
	JoinSearchResult(ControllerId, Invite);
}

// ---------------- TRAVEL / NETWORK LIFECYCLE ----------------
void URedGameInstance::OnPostLoadMapWithWorld(UWorld* LoadedWorld)
{
	if (!LoadedWorld || LoadedWorld->GetGameInstance() != this)
	{
		return;
	}

	if (SessionState != ERedSessionState::Traveling)
	{
		TryStartAutoMatch(LoadedWorld);
		return;
	}

	if (!IsGameplayWorld(LoadedWorld))
	{
		const FString FailureMessage = FString::Printf(
			TEXT("Travel completed on unexpected world '%s' instead of RedPlanetGen."),
			*LoadedWorld->GetMapName());
		if (bAutoMatchJoinPending)
		{
			HandleAutoMatchJoinFailure(FailureMessage);
		}
		else
		{
			FailAndCleanupNamedSession(FailureMessage);
		}
		return;
	}

	if (bHostTravelPending)
	{
		NotifyGameplayWorldReady(LoadedWorld);
		return;
	}

	if (bClientTravelPending)
	{
		bClientTravelPending = false;
		// Keep the automatic join armed through address resolution and travel. Only a confirmed
		// gameplay-world load completes Quick Match; any earlier failure returns to discovery.
		bAutoMatchJoinPending = false;
		bAutoMatchActive = false;
		LastSuccessfulConnectString = PendingDirectConnectString;
		LastSessionError.Reset();
		SetSessionState(ERedSessionState::InSession);
	}
}

void URedGameInstance::OnNetworkFailure(UWorld* World, UNetDriver* NetDriver,
	ENetworkFailure::Type FailureType, const FString& ErrorString)
{
	(void)NetDriver;
	if (!World || World->GetGameInstance() != this
		|| (SessionState != ERedSessionState::Traveling && SessionState != ERedSessionState::InSession))
	{
		return;
	}

	const FString FailureMessage = FString::Printf(TEXT("Network failure (%s): %s"),
		ENetworkFailure::ToString(FailureType), *ErrorString);
	if (bAutoMatchJoinPending && SessionState == ERedSessionState::Traveling)
	{
		HandleAutoMatchJoinFailure(FailureMessage);
	}
	else
	{
		FailAndCleanupNamedSession(FailureMessage);
	}
}

void URedGameInstance::OnTravelFailure(UWorld* World, ETravelFailure::Type FailureType,
	const FString& ErrorString)
{
	if (!World || World->GetGameInstance() != this
		|| (SessionState != ERedSessionState::Traveling && SessionState != ERedSessionState::InSession))
	{
		return;
	}

	const FString FailureMessage = FString::Printf(TEXT("Travel failure (%s): %s"),
		ETravelFailure::ToString(FailureType), *ErrorString);
	if (bAutoMatchJoinPending && SessionState == ERedSessionState::Traveling)
	{
		HandleAutoMatchJoinFailure(FailureMessage);
	}
	else
	{
		FailAndCleanupNamedSession(FailureMessage);
	}
}

// ---------------- STATE / HELPERS ----------------
void URedGameInstance::SetSessionState(ERedSessionState NewState)
{
	if (SessionState == NewState)
	{
		return;
	}

	SessionState = NewState;
	OnSessionStateChanged.Broadcast(NewState);
}

void URedGameInstance::ReportSessionError(const FString& Message, bool bPreserveCurrentState)
{
	LastSessionError = Message;
	UE_LOG(LogTemp, Error, TEXT("[Red] %s"), *Message);
	if (!bPreserveCurrentState)
	{
		SetSessionState(ERedSessionState::Error);
	}
	OnSessionError.Broadcast(LastSessionError);
}

void URedGameInstance::FailAndCleanupNamedSession(const FString& Message)
{
	bHostTravelPending = false;
	bClientTravelPending = false;
	bReconnectSearchPending = false;

	if (Sessions.IsValid() && StartHandle.IsValid())
	{
		Sessions->ClearOnStartSessionCompleteDelegate_Handle(StartHandle);
		StartHandle.Reset();
	}

	ReportSessionError(Message);
	if (Sessions.IsValid() && Sessions->GetNamedSession(NAME_GameSession) != nullptr
		&& !DestroyHandle.IsValid())
	{
		QueueSessionAction(EPendingSessionAction::CleanupFailure);
	}
}

bool URedGameInstance::IsOperationInFlight() const
{
	return CreateHandle.IsValid()
		|| StartHandle.IsValid()
		|| DestroyHandle.IsValid()
		|| FindHandle.IsValid()
		|| JoinHandle.IsValid()
		|| SessionState == ERedSessionState::Destroying
		|| SessionState == ERedSessionState::Creating
		|| SessionState == ERedSessionState::Searching
		|| SessionState == ERedSessionState::Joining
		|| SessionState == ERedSessionState::Traveling;
}

void URedGameInstance::ClearOneShotDelegateHandles()
{
	if (!Sessions.IsValid())
	{
		return;
	}

	if (CreateHandle.IsValid())
	{
		Sessions->ClearOnCreateSessionCompleteDelegate_Handle(CreateHandle);
		CreateHandle.Reset();
	}
	if (StartHandle.IsValid())
	{
		Sessions->ClearOnStartSessionCompleteDelegate_Handle(StartHandle);
		StartHandle.Reset();
	}
	if (DestroyHandle.IsValid())
	{
		Sessions->ClearOnDestroySessionCompleteDelegate_Handle(DestroyHandle);
		DestroyHandle.Reset();
	}
	if (FindHandle.IsValid())
	{
		Sessions->ClearOnFindSessionsCompleteDelegate_Handle(FindHandle);
		FindHandle.Reset();
	}
	if (JoinHandle.IsValid())
	{
		Sessions->ClearOnJoinSessionCompleteDelegate_Handle(JoinHandle);
		JoinHandle.Reset();
	}
}

FString URedGameInstance::GetEffectiveProductId() const
{
	return SessionProductId.IsEmpty() ? RedSessionKeys::DefaultProductId : SessionProductId;
}

FString URedGameInstance::GetEffectiveBuildId() const
{
	return SessionBuildId.IsEmpty() ? RedSessionKeys::DefaultBuildId : SessionBuildId;
}

FString URedGameInstance::GetEffectiveSessionType() const
{
	return SessionType.IsEmpty() ? RedSessionKeys::DefaultSessionType : SessionType;
}

FString URedGameInstance::GetHostTravelURL() const
{
	return FString::Printf(TEXT("%s?listen?MaxPlayers=%d"),
		*GameplayMap, FMath::Max(8, MaxPublicPlayers));
}

bool URedGameInstance::IsGameplayWorld(const UWorld* World) const
{
	return World && World->GetMapName().EndsWith(TEXT("RedPlanetGen"), ESearchCase::CaseSensitive);
}
