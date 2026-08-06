#pragma once

#include "CoreMinimal.h"
#include "Engine/GameInstance.h"
#include "Interfaces/OnlineSessionInterface.h"
#include "OnlineSessionSettings.h"
#include "TimerManager.h"
#include "RedGameInstance.generated.h"

/** High-level state exposed to both the native HUD and Blueprint menus. */
UENUM(BlueprintType)
enum class ERedSessionState : uint8
{
	Idle,
	Destroying,
	Creating,
	Searching,
	Joining,
	Traveling,
	InSession,
	Error
};

/** Stable, Blueprint-safe view of an online result. The opaque OSS result stays private. */
USTRUCT(BlueprintType)
struct REDMMO_API FRedSessionResultSummary
{
	GENERATED_BODY()

	/** Index to pass to JoinIndex; stable for the lifetime of the current browser result list. */
	UPROPERTY(BlueprintReadOnly, Category = "Red|Multiplayer") int32 SearchIndex = INDEX_NONE;
	UPROPERTY(BlueprintReadOnly, Category = "Red|Multiplayer") FString ServerName;
	UPROPERTY(BlueprintReadOnly, Category = "Red|Multiplayer") FString OwnerName;
	UPROPERTY(BlueprintReadOnly, Category = "Red|Multiplayer") FString SessionId;
	UPROPERTY(BlueprintReadOnly, Category = "Red|Multiplayer") FString MapName;
	UPROPERTY(BlueprintReadOnly, Category = "Red|Multiplayer") FString BuildId;
	UPROPERTY(BlueprintReadOnly, Category = "Red|Multiplayer") FString SessionType;
	UPROPERTY(BlueprintReadOnly, Category = "Red|Multiplayer") int32 PingMs = 9999;
	UPROPERTY(BlueprintReadOnly, Category = "Red|Multiplayer") int32 CurrentPlayers = 0;
	UPROPERTY(BlueprintReadOnly, Category = "Red|Multiplayer") int32 MaxPlayers = 0;
	UPROPERTY(BlueprintReadOnly, Category = "Red|Multiplayer") bool bJoinable = false;
};

DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FRedSessionStateChanged, ERedSessionState, NewState);
DECLARE_DYNAMIC_MULTICAST_DELEGATE_TwoParams(FRedSessionSearchFinished, bool, bSuccess, int32, ResultCount);
DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FRedSessionResultsChanged, int32, ResultCount);
DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FRedSessionTravelReady, const FString&, ConnectString);
DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FRedSessionStatus, const FString&, StatusMessage);
DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FRedSessionError, const FString&, ErrorMessage);

/**
 * Steam multiplayer game instance.
 *
 * Console commands remain available for quick testing:
 *   HostGame
 *   FindGames, then JoinIndex 0
 *   JoinHost <SteamID64>
 *   Reconnect
 *   InviteSteamFriends (host only; opens the Steam overlay friend picker)
 *
 * The same operations, state, result summaries, and completion delegates are Blueprint-accessible
 * so the in-game HUD can provide a proper host/server browser without exposing OSS-only types.
 */
UCLASS(Config = Game)
class REDMMO_API URedGameInstance : public UGameInstance
{
	GENERATED_BODY()

public:
	virtual void Init() override;
	virtual void Shutdown() override;

	UFUNCTION(Exec, BlueprintCallable, Category = "Red|Multiplayer") void HostGame();
	UFUNCTION(Exec, BlueprintCallable, Category = "Red|Multiplayer") void FindGames();
	UFUNCTION(Exec, BlueprintCallable, Category = "Red|Multiplayer") void JoinIndex(int32 Index = 0);
	/** Development-only direct SteamID64 fallback. Normal players should use FindGames or an invite. */
	UFUNCTION(Exec, BlueprintCallable, Category = "Red|Multiplayer|Development", meta = (DevelopmentOnly))
	void JoinHost(const FString& SteamId);
	UFUNCTION(Exec, BlueprintCallable, Category = "Red|Multiplayer") void Reconnect();
	UFUNCTION(Exec, BlueprintCallable, Category = "Red|Multiplayer") void LeaveGame();
	/** Opens Steam's friend picker for the active locally hosted NAME_GameSession lobby. */
	UFUNCTION(Exec, BlueprintCallable, Category = "Red|Multiplayer") void InviteSteamFriends();

	UFUNCTION(BlueprintPure, Category = "Red|Multiplayer")
	bool CanReconnect() const;

	/** True only after this local player has finished starting a listen-server Steam session. */
	UFUNCTION(BlueprintPure, Category = "Red|Multiplayer")
	bool CanInviteSteamFriends() const;

	UFUNCTION(BlueprintPure, Category = "Red|Multiplayer")
	bool GetSessionResultSummary(int32 Index, FRedSessionResultSummary& OutResult) const;

	/** Authoritative gameplay GameMode handshake. This covers same-map ServerTravel, where
	 *  PostLoadMapWithWorld may not fire even though the Steam listen socket is already live. */
	void NotifyGameplayWorldReady(UWorld* GameplayWorld);

	/** Host capacity. Values below eight are clamped to eight when a session is created. */
	UPROPERTY(Config, EditAnywhere, BlueprintReadWrite, Category = "Red|Multiplayer",
		meta = (ClampMin = "8", UIMin = "8"))
	int32 MaxPublicPlayers = 8;

	/** Product/build/type are advertised and queried together, isolating RED from random App 480 lobbies. */
	UPROPERTY(Config, EditAnywhere, BlueprintReadWrite, Category = "Red|Multiplayer|Identity")
	FString SessionProductId = TEXT("RedMMOTitan");

	UPROPERTY(Config, EditAnywhere, BlueprintReadWrite, Category = "Red|Multiplayer|Identity")
	FString SessionBuildId = TEXT("RedMMOTitan-UE5.8-Windows");

	UPROPERTY(Config, EditAnywhere, BlueprintReadWrite, Category = "Red|Multiplayer|Identity")
	FString SessionType = TEXT("PvP");

	UPROPERTY(Config, EditAnywhere, BlueprintReadWrite, Category = "Red|Multiplayer|Identity")
	FString HostedServerName = TEXT("Red MMO Titan PvP");

	UPROPERTY(Config, EditAnywhere, BlueprintReadWrite, Category = "Red|Multiplayer",
		meta = (ClampMin = "1", UIMin = "1"))
	int32 MaxSearchResults = 100;

	/**
	 * Packaged Steam clients automatically find or create a compatible RED match on launch.
	 * Editor/PIE, dedicated servers, -nosteam, and -NoAutoMatch never run this flow.
	 */
	UPROPERTY(Config, EditAnywhere, BlueprintReadWrite, Category = "Red|Multiplayer|Quick Match")
	// Keep packaged startup deterministic: one player explicitly creates a lobby and the
	// other explicitly searches/joins it.  Silent auto-hosting made both friends become
	// separate hosts after the election timeout and disabled the browser's Create/Find
	// controls, which looked exactly like a broken multiplayer menu.
	bool bAutoMatchOnStartup = false;

	/** Successful empty searches before the randomized host-election verification search. */
	UPROPERTY(Config, EditAnywhere, BlueprintReadWrite, Category = "Red|Multiplayer|Quick Match",
		meta = (ClampMin = "1", ClampMax = "10", UIMin = "1", UIMax = "10"))
	int32 AutoMatchEmptySearchesBeforeHost = 3;

	UPROPERTY(Config, EditAnywhere, BlueprintReadWrite, Category = "Red|Multiplayer|Quick Match",
		meta = (ClampMin = "0.0", UIMin = "0.0"))
	float AutoMatchInitialDelayMin = 1.5f;

	UPROPERTY(Config, EditAnywhere, BlueprintReadWrite, Category = "Red|Multiplayer|Quick Match",
		meta = (ClampMin = "0.0", UIMin = "0.0"))
	float AutoMatchInitialDelayMax = 4.0f;

	UPROPERTY(Config, EditAnywhere, BlueprintReadWrite, Category = "Red|Multiplayer|Quick Match",
		meta = (ClampMin = "0.0", UIMin = "0.0"))
	float AutoMatchRetryDelayMin = 2.5f;

	UPROPERTY(Config, EditAnywhere, BlueprintReadWrite, Category = "Red|Multiplayer|Quick Match",
		meta = (ClampMin = "0.0", UIMin = "0.0"))
	float AutoMatchRetryDelayMax = 6.0f;

	/** Wider jitter before the final verification search makes two simultaneous clients unlikely to both host. */
	UPROPERTY(Config, EditAnywhere, BlueprintReadWrite, Category = "Red|Multiplayer|Quick Match",
		meta = (ClampMin = "0.0", UIMin = "0.0"))
	float AutoMatchHostElectionDelayMin = 4.0f;

	UPROPERTY(Config, EditAnywhere, BlueprintReadWrite, Category = "Red|Multiplayer|Quick Match",
		meta = (ClampMin = "0.0", UIMin = "0.0"))
	float AutoMatchHostElectionDelayMax = 10.0f;

	UPROPERTY(BlueprintReadOnly, Category = "Red|Multiplayer")
	ERedSessionState SessionState = ERedSessionState::Idle;

	UPROPERTY(BlueprintReadOnly, Category = "Red|Multiplayer")
	TArray<FRedSessionResultSummary> SessionResults;

	UPROPERTY(BlueprintReadOnly, Category = "Red|Multiplayer")
	FString LastSessionError;

	UPROPERTY(BlueprintAssignable, Category = "Red|Multiplayer") FRedSessionStateChanged OnSessionStateChanged;
	UPROPERTY(BlueprintAssignable, Category = "Red|Multiplayer") FRedSessionSearchFinished OnSessionSearchFinished;
	UPROPERTY(BlueprintAssignable, Category = "Red|Multiplayer") FRedSessionResultsChanged OnSessionResultsChanged;
	UPROPERTY(BlueprintAssignable, Category = "Red|Multiplayer") FRedSessionTravelReady OnSessionTravelReady;
	UPROPERTY(BlueprintAssignable, Category = "Red|Multiplayer") FRedSessionStatus OnSessionStatus;
	UPROPERTY(BlueprintAssignable, Category = "Red|Multiplayer") FRedSessionError OnSessionError;

private:
	/** Authoritative gameplay world. SoStylized assets dress this PlanetGen map. */
	const FString GameplayMap = TEXT("/Game/RedMMO/Maps/RedPlanetGen");

	enum class EPendingSessionAction : uint8
	{
		None,
		Host,
		JoinSearchResult,
		DirectTravel,
		ReconnectSearch,
		AutoMatchRetry,
		Leave,
		CleanupFailure
	};

	IOnlineSessionPtr Sessions;
	TSharedPtr<FOnlineSessionSearch> LastSearch;
	TArray<int32> CompatibleSearchResultIndices;

	FOnCreateSessionCompleteDelegate CreateDelegate;
	FOnStartSessionCompleteDelegate StartDelegate;
	FOnDestroySessionCompleteDelegate DestroyDelegate;
	FOnFindSessionsCompleteDelegate FindDelegate;
	FOnJoinSessionCompleteDelegate JoinDelegate;
	FOnSessionUserInviteAcceptedDelegate InviteDelegate;
	FDelegateHandle CreateHandle;
	FDelegateHandle StartHandle;
	FDelegateHandle DestroyHandle;
	FDelegateHandle FindHandle;
	FDelegateHandle JoinHandle;
	FDelegateHandle InviteHandle;
	FDelegateHandle PostLoadMapHandle;
	FDelegateHandle NetworkFailureHandle;
	FDelegateHandle TravelFailureHandle;

	EPendingSessionAction PendingAction = EPendingSessionAction::None;
	FOnlineSessionSearchResult PendingJoinResult;
	int32 PendingJoinControllerId = 0;
	FString PendingDirectConnectString;
	bool bHostTravelPending = false;
	bool bClientTravelPending = false;
	bool bReconnectSearchPending = false;
	bool bAutoMatchEligible = false;
	bool bAutoMatchStarted = false;
	bool bAutoMatchActive = false;
	bool bAutoMatchSearchPending = false;
	bool bAutoMatchFinalVerificationPending = false;
	bool bAutoMatchJoinPending = false;
	bool bScheduledAutoMatchFinalVerification = false;
	int32 AutoMatchSuccessfulEmptySearches = 0;
	int32 AutoMatchConsecutiveSearchFailures = 0;
	FTimerHandle AutoMatchTimerHandle;

	FOnlineSessionSearchResult ReconnectSearchResult;
	FString LastSuccessfulConnectString;
	FString ReconnectSessionId;
	int32 ReconnectControllerId = 0;

	void QueueSessionAction(EPendingSessionAction Action);
	void ExecutePendingAction();
	void BeginCreateSession();
	void BeginStartHostedSession();
	void BeginFindGames(bool bForReconnect);
	void BeginJoinSearchResult();
	void BeginDirectTravel();
	void CompleteLeaveGame();
	void JoinSearchResult(int32 ControllerId, const FOnlineSessionSearchResult& Result);
	void TryStartAutoMatch(UWorld* LoadedWorld);
	void ScheduleAutoMatchSearch(float MinDelay, float MaxDelay, bool bFinalVerification,
		const TCHAR* Reason);
	void StartScheduledAutoMatchSearch();
	void HandleAutoMatchSearchComplete(bool bSuccess, bool bFinalVerification);
	void HandleAutoMatchJoinFailure(const FString& Message);
	void CancelAutoMatch(const TCHAR* Reason);
	int32 FindBestAutoMatchResult() const;

	void OnCreateSessionComplete(FName SessionName, bool bSuccess);
	void OnStartSessionComplete(FName SessionName, bool bSuccess);
	void OnDestroySessionComplete(FName SessionName, bool bSuccess);
	void OnFindSessionsComplete(bool bSuccess);
	void OnJoinSessionComplete(FName SessionName, EOnJoinSessionCompleteResult::Type Result);
	void OnInviteAccepted(const bool bSuccess, const int32 ControllerId,
		FUniqueNetIdPtr UserId, const FOnlineSessionSearchResult& Invite);
	void OnPostLoadMapWithWorld(UWorld* LoadedWorld);
	void OnNetworkFailure(UWorld* World, class UNetDriver* NetDriver,
		ENetworkFailure::Type FailureType, const FString& ErrorString);
	void OnTravelFailure(UWorld* World, ETravelFailure::Type FailureType, const FString& ErrorString);

	void SetSessionState(ERedSessionState NewState);
	void ReportSessionError(const FString& Message, bool bPreserveCurrentState = false);
	void FailAndCleanupNamedSession(const FString& Message);
	bool IsOperationInFlight() const;
	void ClearOneShotDelegateHandles();
	void BuildSessionResultSummaries();
	bool IsCompatibleResult(const FOnlineSessionSearchResult& Result) const;

	FString GetEffectiveProductId() const;
	FString GetEffectiveBuildId() const;
	FString GetEffectiveSessionType() const;
	FString GetHostTravelURL() const;
	bool IsGameplayWorld(const UWorld* World) const;
};
