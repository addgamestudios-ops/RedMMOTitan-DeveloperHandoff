#include "../RedMineableAsteroid.h"
#include "../RedPlayerCharacter.h"
#include "../RedResourcePickup.h"
#include "../RedShipExplosionFX.h"
#include "../RedSpaceScenery.h"

#if WITH_DEV_AUTOMATION_TESTS && WITH_EDITOR

#include "Components/PointLightComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Editor.h"
#include "Engine/Engine.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/GameStateBase.h"
#include "GameFramework/PlayerController.h"
#include "GameFramework/PlayerStart.h"
#include "GameFramework/PlayerState.h"
#include "HAL/PlatformProcess.h"
#include "HAL/PlatformTime.h"
#include "Misc/App.h"
#include "Misc/AutomationTest.h"
#include "Misc/CommandLine.h"
#include "Misc/Parse.h"
#include "PlayInEditorDataTypes.h"
#include "Settings/LevelEditorPlaySettings.h"
#include "Tests/AutomationEditorCommon.h"
#include "UObject/UnrealType.h"

namespace RedMMO::DEF0003ActualFieldLateJoinPIE
{
	namespace Private
	{
		constexpr TCHAR ProductionMap[] =
			TEXT("/Game/RedMMO/Maps/RedPlanetGen");
		constexpr TCHAR TargetStableIdText[] =
			TEXT("asteroid-field.red.mars.deep-space/0x4F524531/23");
		constexpr int32 MineableCount = 24;
		constexpr double ServerReadyTimeoutSeconds = 60.0;
		constexpr double JoinTimeoutSeconds = 60.0;
		constexpr double StageTimeoutSeconds = 20.0;
		constexpr double MissingProxyDiagnosticSeconds = 1.0;
		constexpr double DurableStabilitySeconds = 0.5;
		constexpr float DuringJoinPresentationSeconds = 8.f;
		constexpr float PawnHoldDistanceCm = 200000.f;
		constexpr float PawnHoldTangentOffsetCm = 100000.f;
		constexpr float ExplosionNetworkCullDistanceCm = 1500000.f;
		constexpr float AsteroidNetworkCullDistanceCm = 5000000.f;

		enum class ELateJoinScenario : uint8
		{
			DuringDepleting,
			InsideReplayWindow,
			OutsideReplayWindow,
			DurableAfterTransientExpiry
		};

		const TCHAR* ScenarioName(const ELateJoinScenario Scenario)
		{
			switch (Scenario)
			{
			case ELateJoinScenario::DuringDepleting:
				return TEXT("during_depleting");
			case ELateJoinScenario::InsideReplayWindow:
				return TEXT("inside_replay_window");
			case ELateJoinScenario::OutsideReplayWindow:
				return TEXT("outside_replay_window");
			case ELateJoinScenario::DurableAfterTransientExpiry:
				return TEXT("durable_after_transient_expiry");
			default:
				return TEXT("unknown");
			}
		}

		struct FAcceptanceState
		{
			explicit FAcceptanceState(const ELateJoinScenario InScenario)
				: Scenario(InScenario)
			{
			}

			ELateJoinScenario Scenario;
			bool bAccepted = false;
			bool bPIEEnded = false;
		};

		struct FWorldPair
		{
			UWorld* Server = nullptr;
			UWorld* Client = nullptr;
			int32 PIEWorldCount = 0;
			int32 ListenServerCount = 0;
			int32 ClientCount = 0;
			int32 ServerPIEInstance = INDEX_NONE;
			int32 ClientPIEInstance = INDEX_NONE;
		};

		struct FPlayerPair
		{
			APlayerController* HostController = nullptr;
			APlayerController* RemoteServerController = nullptr;
			APlayerController* RemoteClientController = nullptr;
			ARedPlayerCharacter* HostPawn = nullptr;
			ARedPlayerCharacter* RemoteServerPawn = nullptr;
			ARedPlayerCharacter* RemoteClientPawn = nullptr;
			int32 ServerPlayerCount = 0;
		};

		struct FExplosionStats
		{
			ARedShipExplosionFX* UniqueExplosion = nullptr;
			int32 Count = 0;
			int32 SimulatingDebris = 0;
			int32 VisibleLights = 0;
			float MaxLightIntensity = 0.f;
			bool bTickEnabled = false;
		};

		FWorldPair ResolvePIEWorlds()
		{
			FWorldPair Result;
			if (!GEngine)
			{
				return Result;
			}

			for (const FWorldContext& Context : GEngine->GetWorldContexts())
			{
				UWorld* World = Context.World();
				if (Context.WorldType != EWorldType::PIE || !IsValid(World))
				{
					continue;
				}

				++Result.PIEWorldCount;
				if (World->GetNetMode() == NM_ListenServer)
				{
					Result.Server = World;
					Result.ServerPIEInstance = Context.PIEInstance;
					++Result.ListenServerCount;
				}
				else if (World->GetNetMode() == NM_Client)
				{
					Result.Client = World;
					Result.ClientPIEInstance = Context.PIEInstance;
					++Result.ClientCount;
				}
			}
			return Result;
		}

		FPlayerPair ResolvePlayers(UWorld* ServerWorld, UWorld* ClientWorld)
		{
			FPlayerPair Result;
			if (!ServerWorld)
			{
				return Result;
			}

			for (FConstPlayerControllerIterator It =
					ServerWorld->GetPlayerControllerIterator();
				It; ++It)
			{
				APlayerController* Controller = It->Get();
				ARedPlayerCharacter* Pawn =
					Controller
						? Cast<ARedPlayerCharacter>(Controller->GetPawn())
						: nullptr;
				if (!Controller || !Pawn)
				{
					continue;
				}

				++Result.ServerPlayerCount;
				if (Controller->IsLocalController())
				{
					Result.HostController = Controller;
					Result.HostPawn = Pawn;
				}
				else
				{
					Result.RemoteServerController = Controller;
					Result.RemoteServerPawn = Pawn;
				}
			}

			if (!ClientWorld)
			{
				return Result;
			}
			for (FConstPlayerControllerIterator It =
					ClientWorld->GetPlayerControllerIterator();
				It; ++It)
			{
				APlayerController* Controller = It->Get();
				ARedPlayerCharacter* Pawn =
					Controller
						? Cast<ARedPlayerCharacter>(Controller->GetPawn())
						: nullptr;
				if (Controller && Pawn && Controller->IsLocalController())
				{
					Result.RemoteClientController = Controller;
					Result.RemoteClientPawn = Pawn;
					break;
				}
			}
			return Result;
		}

		bool PlayerIdentitiesMatch(const FPlayerPair& Players)
		{
			if (!Players.RemoteServerController
				|| !Players.RemoteClientController
				|| !Players.RemoteServerController->PlayerState
				|| !Players.RemoteClientController->PlayerState)
			{
				return false;
			}

			const int32 ServerId =
				Players.RemoteServerController->PlayerState->GetPlayerId();
			const int32 ClientId =
				Players.RemoteClientController->PlayerState->GetPlayerId();
			return ServerId >= 0 && ServerId == ClientId;
		}

		bool ResolveAuthorityField(
			UWorld* World,
			TMap<FName, ARedMineableAsteroid*>& OutMembers,
			ARedSpaceScenery*& OutScenery)
		{
			OutMembers.Reset();
			OutScenery = nullptr;
			if (!World)
			{
				return false;
			}

			int32 SceneryCount = 0;
			for (TActorIterator<ARedSpaceScenery> It(World); It; ++It)
			{
				if (IsValid(*It))
				{
					OutScenery = *It;
					++SceneryCount;
				}
			}
			if (SceneryCount != 1 || !OutScenery)
			{
				return false;
			}

			int32 TaggedCount = 0;
			for (TActorIterator<ARedMineableAsteroid> It(World); It; ++It)
			{
				ARedMineableAsteroid* Member = *It;
				if (!IsValid(Member)
					|| !Member->ActorHasTag(TEXT("RedMarsMineableBelt")))
				{
					continue;
				}
				++TaggedCount;
				const FName StableId = Member->GetStableMemberId();
				if (StableId.IsNone() || OutMembers.Contains(StableId))
				{
					return false;
				}
				OutMembers.Add(StableId, Member);
			}
			return TaggedCount == MineableCount
				&& OutMembers.Num() == MineableCount;
		}

		ARedMineableAsteroid* FindUniqueStableMember(
			UWorld* World,
			const FName StableId)
		{
			ARedMineableAsteroid* Result = nullptr;
			int32 MatchCount = 0;
			if (!World || StableId.IsNone())
			{
				return nullptr;
			}

			for (TActorIterator<ARedMineableAsteroid> It(World); It; ++It)
			{
				ARedMineableAsteroid* Member = *It;
				if (IsValid(Member) && Member->GetStableMemberId() == StableId)
				{
					Result = Member;
					++MatchCount;
				}
			}
			return MatchCount == 1 ? Result : nullptr;
		}

		int32 CountOtherPristineMembers(
			UWorld* World,
			const FName TargetId)
		{
			int32 Count = 0;
			for (TActorIterator<ARedMineableAsteroid> It(World); It; ++It)
			{
				const ARedMineableAsteroid* Member = *It;
				if (!IsValid(Member)
					|| !Member->ActorHasTag(TEXT("RedMarsMineableBelt"))
					|| Member->GetStableMemberId() == TargetId)
				{
					continue;
				}
				if (!Member->GetStableMemberId().IsNone()
					&& Member->DepletionState.Phase
						== ERedMineableAsteroidDepletionPhase::Active
					&& FMath::IsNearlyEqual(Member->OreCapacity, 6000.f)
					&& FMath::IsNearlyEqual(
						Member->OreRemaining,
						Member->OreCapacity)
					&& Member->GetActorEnableCollision()
					&& !Member->IsHidden())
				{
					++Count;
				}
			}
			return Count;
		}

		int32 CountReceipts(
			UWorld* World,
			ARedMineableAsteroid* ExpectedOwner)
		{
			int32 Count = 0;
			if (!World)
			{
				return Count;
			}
			for (TActorIterator<ARedResourcePickup> It(World); It; ++It)
			{
				const ARedResourcePickup* Receipt = *It;
				if (IsValid(Receipt)
					&& Receipt->GetOwner() == ExpectedOwner
					&& Receipt->ResourceType == ERedResourceType::Iron
					&& Receipt->Amount == 6
					&& !Receipt->bCollectible)
				{
					++Count;
				}
			}
			return Count;
		}

		ARedShipExplosionFX* FindOwnedExplosion(
			UWorld* World,
			ARedMineableAsteroid* ExpectedOwner)
		{
			ARedShipExplosionFX* Result = nullptr;
			int32 Count = 0;
			if (!World || !ExpectedOwner)
			{
				return nullptr;
			}
			for (TActorIterator<ARedShipExplosionFX> It(World); It; ++It)
			{
				ARedShipExplosionFX* Explosion = *It;
				if (IsValid(Explosion) && Explosion->GetOwner() == ExpectedOwner)
				{
					Result = Explosion;
					++Count;
				}
			}
			return Count == 1 ? Result : nullptr;
		}

		FExplosionStats GetExplosionStats(UWorld* World)
		{
			FExplosionStats Result;
			if (!World)
			{
				return Result;
			}

			for (TActorIterator<ARedShipExplosionFX> It(World); It; ++It)
			{
				ARedShipExplosionFX* Explosion = *It;
				if (!IsValid(Explosion))
				{
					continue;
				}
				Result.UniqueExplosion = Explosion;
				++Result.Count;
				Result.bTickEnabled |= Explosion->IsActorTickEnabled();

				TArray<UStaticMeshComponent*> Debris;
				Explosion->GetComponents<UStaticMeshComponent>(Debris);
				for (const UStaticMeshComponent* Component : Debris)
				{
					if (Component && Component->IsSimulatingPhysics())
					{
						++Result.SimulatingDebris;
					}
				}

				TArray<UPointLightComponent*> Lights;
				Explosion->GetComponents<UPointLightComponent>(Lights);
				const FFloatProperty* IntensityProperty =
					FindFProperty<FFloatProperty>(
						UPointLightComponent::StaticClass(),
						TEXT("Intensity"));
				for (const UPointLightComponent* Light : Lights)
				{
					if (!Light)
					{
						continue;
					}
					const float Intensity =
						IntensityProperty
							? IntensityProperty->GetPropertyValue_InContainer(
								Light)
							: 0.f;
					Result.MaxLightIntensity =
						FMath::Max(Result.MaxLightIntensity, Intensity);
					if (Light->IsVisible()
						&& Intensity > KINDA_SMALL_NUMBER)
					{
						++Result.VisibleLights;
					}
				}
			}
			if (Result.Count != 1)
			{
				Result.UniqueExplosion = nullptr;
			}
			return Result;
		}

		bool ReadExplosionReplayTiming(
			const ARedShipExplosionFX* Explosion,
			float& OutStartedServerTimeSeconds,
			float& OutReplayWindowSeconds)
		{
			OutStartedServerTimeSeconds = -1.f;
			OutReplayWindowSeconds = -1.f;
			if (!Explosion)
			{
				return false;
			}

			const FFloatProperty* StartedProperty =
				FindFProperty<FFloatProperty>(
					ARedShipExplosionFX::StaticClass(),
					TEXT("PresentationStartedServerTimeSeconds"));
			const FFloatProperty* WindowProperty =
				FindFProperty<FFloatProperty>(
					ARedShipExplosionFX::StaticClass(),
					TEXT("PresentationReplayWindowSeconds"));
			if (!StartedProperty || !WindowProperty)
			{
				return false;
			}

			OutStartedServerTimeSeconds =
				StartedProperty->GetPropertyValue_InContainer(Explosion);
			OutReplayWindowSeconds =
				WindowProperty->GetPropertyValue_InContainer(Explosion);
			return OutStartedServerTimeSeconds >= 0.f
				&& OutReplayWindowSeconds >= 0.f;
		}

		float GetSynchronizedServerTime(UWorld* World)
		{
			const AGameStateBase* GameState =
				World ? World->GetGameState() : nullptr;
			return GameState
				? static_cast<float>(GameState->GetServerWorldTimeSeconds())
				: -1.f;
		}

		bool PositionHostAndPlayerStarts(
			UWorld* ServerWorld,
			ARedSpaceScenery* Scenery,
			ARedMineableAsteroid* Target,
			ARedPlayerCharacter* HostPawn,
			APlayerController* HostController,
			FVector& OutHoldLocation,
			FRotator& OutHoldRotation)
		{
			if (!ServerWorld || !Scenery || !Target || !HostPawn || !HostController)
			{
				return false;
			}

			FVector BoundsOrigin;
			FVector BoundsExtent;
			Target->GetActorBounds(
				false,
				BoundsOrigin,
				BoundsExtent,
				true);
			const FVector RadialOut =
				(BoundsOrigin - Scenery->GetActorLocation()).GetSafeNormal();
			if (RadialOut.IsNearlyZero())
			{
				return false;
			}

			FVector Tangent;
			FVector Bitangent;
			RadialOut.FindBestAxisVectors(Tangent, Bitangent);
			OutHoldLocation =
				BoundsOrigin
				+ RadialOut * PawnHoldDistanceCm
				+ Tangent * PawnHoldTangentOffsetCm;
			OutHoldRotation = (BoundsOrigin - OutHoldLocation).Rotation();

			if (UCharacterMovementComponent* Movement =
				HostPawn->GetCharacterMovement())
			{
				Movement->StopMovementImmediately();
				Movement->DisableMovement();
			}
			HostPawn->SetActorLocationAndRotation(
				OutHoldLocation - Tangent * 50000.f,
				OutHoldRotation,
				false,
				nullptr,
				ETeleportType::TeleportPhysics);
			HostController->SetControlRotation(OutHoldRotation);
			HostPawn->ForceNetUpdate();

			int32 StartIndex = 0;
			for (TActorIterator<APlayerStart> It(ServerWorld); It; ++It)
			{
				APlayerStart* PlayerStart = *It;
				if (!IsValid(PlayerStart))
				{
					continue;
				}
				const FVector StartLocation =
					OutHoldLocation
					+ Bitangent * static_cast<float>(StartIndex * 2500);
				PlayerStart->SetActorLocationAndRotation(
					StartLocation,
					OutHoldRotation,
					false,
					nullptr,
					ETeleportType::TeleportPhysics);
				++StartIndex;
			}
			return true;
		}

		void PositionRemoteServerPawn(
			const FPlayerPair& Players,
			const FVector& HoldLocation,
			const FRotator& HoldRotation)
		{
			if (!Players.RemoteServerPawn || !Players.RemoteServerController)
			{
				return;
			}
			if (UCharacterMovementComponent* Movement =
				Players.RemoteServerPawn->GetCharacterMovement())
			{
				Movement->StopMovementImmediately();
				Movement->DisableMovement();
			}
			Players.RemoteServerPawn->SetActorLocationAndRotation(
				HoldLocation,
				HoldRotation,
				false,
				nullptr,
				ETeleportType::TeleportPhysics);
			Players.RemoteServerController->SetControlRotation(HoldRotation);
			Players.RemoteServerPawn->ForceNetUpdate();
		}

		class FActualFieldLateJoinCommand final
			: public IAutomationLatentCommand
		{
		public:
			FActualFieldLateJoinCommand(
				FAutomationTestBase* InTest,
				TSharedRef<FAcceptanceState> InAcceptanceState)
				: Test(InTest)
				, AcceptanceState(MoveTemp(InAcceptanceState))
				, Scenario(AcceptanceState->Scenario)
				, TargetId(TargetStableIdText)
			{
			}

			virtual bool Update() override
			{
				const double Now = FPlatformTime::Seconds();
				if (StartedAtSeconds <= 0.0)
				{
					StartedAtSeconds = Now;
					StageStartedAtSeconds = Now;
				}

				const FWorldPair Worlds = ResolvePIEWorlds();
				switch (Stage)
				{
				case EStage::AwaitServerReady:
					return AwaitServerReady(Worlds, Now);
				case EStage::AwaitRequestBarrier:
					return AwaitRequestBarrier(Worlds, Now);
				case EStage::AwaitLateClient:
					return AwaitLateClient(Worlds, Now);
				case EStage::AwaitScenario:
					return AwaitScenario(Worlds, Now);
				case EStage::AwaitPostScenario:
					return AwaitPostScenario(Worlds, Now);
				case EStage::Complete:
					return true;
				default:
					return Fail(TEXT("unknown late-join acceptance stage"));
				}
			}

		private:
			enum class EStage : uint8
			{
				AwaitServerReady,
				AwaitRequestBarrier,
				AwaitLateClient,
				AwaitScenario,
				AwaitPostScenario,
				Complete
			};

			bool Fail(const FString& Reason)
			{
				Test->AddError(FString::Printf(
					TEXT("DEF-0003 actual-field late-join %s failed: %s"),
					ScenarioName(Scenario),
					*Reason));
				UE_LOG(
					LogTemp,
					Error,
					TEXT("RED_DEF0003_FIELD_LATE_JOIN_RESULT acceptancePass=0 scenario=%s reason=\"%s\""),
					ScenarioName(Scenario),
					*Reason.ReplaceCharWithEscapedChar());
				Stage = EStage::Complete;
				return true;
			}

			bool Pass(const FString& Detail)
			{
				UE_LOG(
					LogTemp,
					Display,
					TEXT("RED_DEF0003_FIELD_LATE_JOIN_RESULT acceptancePass=1 scenario=%s evidenceClass=multiplayer topology=in_process_listen_plus_true_late_client actualFieldMember=1 stableIdentity=1 lateJoin=1 pristinePeers=23 testTeleport=1 presentationDurationOverride=%d steamTransport=0 clientOriginatedRPC=0 detail=\"%s\""),
					ScenarioName(Scenario),
					Scenario == ELateJoinScenario::DuringDepleting ? 1 : 0,
					*Detail.ReplaceCharWithEscapedChar());
				AcceptanceState->bAccepted = true;
				Stage = EStage::Complete;
				return true;
			}

			bool StageTimedOut(const double Now) const
			{
				return Now - StageStartedAtSeconds > StageTimeoutSeconds;
			}

			void Advance(const EStage NextStage, const double Now)
			{
				Stage = NextStage;
				StageStartedAtSeconds = Now;
			}

			bool RequestLateJoin(const FWorldPair& Worlds, const double Now)
			{
				if (!GEditor || !Worlds.Server)
				{
					return Fail(TEXT("GEditor or listen world unavailable at late-join request"));
				}
				const float ServerTime = GetSynchronizedServerTime(Worlds.Server);
				GEditor->RequestLateJoin();
				LateJoinRequestedAtSeconds = Now;
				UE_LOG(
					LogTemp,
					Display,
					TEXT("RED_DEF0003_FIELD_LATE_JOIN_REQUEST scenario=%s pass=1 serverTime=%.3f authorityPhase=%d sequence=%u targetHidden=%d targetCollision=%d"),
					ScenarioName(Scenario),
					ServerTime,
					ServerTarget.IsValid()
						? static_cast<int32>(
							ServerTarget->DepletionState.Phase)
						: -1,
					ServerTarget.IsValid()
						? ServerTarget->DepletionState.Sequence
						: 0,
					ServerTarget.IsValid() && ServerTarget->IsHidden()
						? 1
						: 0,
					ServerTarget.IsValid()
						&& ServerTarget->GetActorEnableCollision()
						? 1
						: 0);
				Advance(EStage::AwaitLateClient, Now);
				return false;
			}

			bool AwaitServerReady(
				const FWorldPair& Worlds,
				const double Now)
			{
				if (Now - StartedAtSeconds > ServerReadyTimeoutSeconds)
				{
					return Fail(FString::Printf(
						TEXT("listen-server readiness timeout pie=%d listen=%d clients=%d"),
						Worlds.PIEWorldCount,
						Worlds.ListenServerCount,
						Worlds.ClientCount));
				}
				if (Worlds.PIEWorldCount != 1
					|| Worlds.ListenServerCount != 1
					|| Worlds.ClientCount != 0
					|| Worlds.ServerPIEInstance != 0)
				{
					return false;
				}

				const FPlayerPair Players =
					ResolvePlayers(Worlds.Server, nullptr);
				if (Players.ServerPlayerCount != 1
					|| !Players.HostController
					|| !Players.HostPawn)
				{
					return false;
				}

				TMap<FName, ARedMineableAsteroid*> Members;
				ARedSpaceScenery* Scenery = nullptr;
				if (!ResolveAuthorityField(Worlds.Server, Members, Scenery))
				{
					return false;
				}
				ARedMineableAsteroid* Target = Members.FindRef(TargetId);
				if (!Target
					|| Target->GetOwner() != Scenery
					|| Target->GetStableMemberId() != TargetId
					|| Target->HasAnyFlags(RF_Transient)
					|| Target->DepletionState.Phase
						!= ERedMineableAsteroidDepletionPhase::Active
					|| !FMath::IsNearlyEqual(Target->OreCapacity, 6000.f)
					|| !FMath::IsNearlyEqual(
						Target->OreRemaining,
						Target->OreCapacity)
					|| CountOtherPristineMembers(Worlds.Server, TargetId)
						!= MineableCount - 1)
				{
					return Fail(TEXT("authority actual-field identity failed"));
				}
				if (!PositionHostAndPlayerStarts(
						Worlds.Server,
						Scenery,
						Target,
						Players.HostPawn,
						Players.HostController,
						HoldLocation,
						HoldRotation))
				{
					return Fail(TEXT("could not place runtime-only join starts near target"));
				}

				InitialHostIron = Players.HostPawn->ResIron;
				ServerTarget = Target;
				if (Scenario == ELateJoinScenario::DuringDepleting)
				{
					Target->DepletionPresentationSeconds =
						DuringJoinPresentationSeconds;
				}

				float TotalExtracted = 0.f;
				for (int32 HitIndex = 0; HitIndex < 7; ++HitIndex)
				{
					TotalExtracted +=
						Target->RegisterMiningHit(55.f, Players.HostPawn);
				}
				const float PostDepletionRejected =
					Target->RegisterMiningHit(55.f, Players.HostPawn);
				const bool bPrepared =
					FMath::IsNearlyEqual(TotalExtracted, 6000.f)
					&& FMath::IsNearlyZero(PostDepletionRejected)
					&& FMath::IsNearlyZero(Target->OreRemaining)
					&& Target->DepletionState.Phase
						== ERedMineableAsteroidDepletionPhase::Depleting
					&& Target->DepletionState.Sequence == 1
					&& !Target->IsHidden()
					&& !Target->GetActorEnableCollision()
					&& Target->DepletionState.bRewardSpawned
					&& Target->DepletionState.bRewardGranted
					&& Players.HostPawn->ResIron - InitialHostIron == 6
					&& CountReceipts(Worlds.Server, Target) == 1
					&& CountOtherPristineMembers(Worlds.Server, TargetId)
						== MineableCount - 1;
				if (!bPrepared)
				{
					return Fail(TEXT("authority depletion preparation failed"));
				}

				UE_LOG(
					LogTemp,
					Display,
					TEXT("RED_DEF0003_FIELD_LATE_JOIN_PREPARED scenario=%s pass=1 stableId=%s phase=%d sequence=%u ore=%.0f duration=%.2f hostIronDelta=%d receipt=%d pristinePeers=%d testTeleport=1"),
					ScenarioName(Scenario),
					*TargetId.ToString(),
					static_cast<int32>(Target->DepletionState.Phase),
					Target->DepletionState.Sequence,
					Target->OreRemaining,
					Target->DepletionState.PresentationDurationSeconds,
					Players.HostPawn->ResIron - InitialHostIron,
					CountReceipts(Worlds.Server, Target),
					CountOtherPristineMembers(Worlds.Server, TargetId));

				if (Scenario == ELateJoinScenario::DuringDepleting)
				{
					return RequestLateJoin(Worlds, Now);
				}
				Advance(EStage::AwaitRequestBarrier, Now);
				return false;
			}

			bool AwaitRequestBarrier(
				const FWorldPair& Worlds,
				const double Now)
			{
				if (StageTimedOut(Now))
				{
					return Fail(TEXT("late-join request timing barrier timed out"));
				}
				ARedMineableAsteroid* Target = ServerTarget.Get();
				if (!Worlds.Server || !Target)
				{
					return Fail(TEXT("authority target invalid at request barrier"));
				}

				ARedShipExplosionFX* ServerExplosion =
					FindOwnedExplosion(Worlds.Server, Target);
				if (ServerExplosion && ExplosionStartedServerTimeSeconds < 0.f)
				{
					if (!ReadExplosionReplayTiming(
							ServerExplosion,
							ExplosionStartedServerTimeSeconds,
							ExplosionReplayWindowSeconds))
					{
						return Fail(TEXT("could not read immutable server FX replay timing"));
					}
				}
				const float ServerTime = GetSynchronizedServerTime(Worlds.Server);
				const float ExplosionAge =
					ExplosionStartedServerTimeSeconds >= 0.f
						&& ServerTime >= 0.f
					? ServerTime - ExplosionStartedServerTimeSeconds
					: -1.f;

				if (Scenario == ELateJoinScenario::InsideReplayWindow
					&& Target->DepletionState.Phase
						== ERedMineableAsteroidDepletionPhase::Depleted
					&& Target->DepletionState.Sequence == 2
					&& ServerExplosion
					&& ExplosionAge >= 0.f)
				{
					return RequestLateJoin(Worlds, Now);
				}
				if (Scenario == ELateJoinScenario::OutsideReplayWindow
					&& ServerExplosion
					&& ExplosionAge >= 0.75f
					&& ExplosionAge < 1.25f)
				{
					return RequestLateJoin(Worlds, Now);
				}
				if (Scenario
						== ELateJoinScenario::DurableAfterTransientExpiry
					&& ExplosionStartedServerTimeSeconds >= 0.f
					&& ExplosionAge > 5.15f
					&& !ServerExplosion
					&& CountReceipts(Worlds.Server, Target) == 0)
				{
					return RequestLateJoin(Worlds, Now);
				}
				return false;
			}

			bool AwaitLateClient(
				const FWorldPair& Worlds,
				const double Now)
			{
				if (Now - LateJoinRequestedAtSeconds > JoinTimeoutSeconds)
				{
					return Fail(FString::Printf(
						TEXT("true late-client topology timeout pie=%d listen=%d clients=%d serverPIE=%d clientPIE=%d"),
						Worlds.PIEWorldCount,
						Worlds.ListenServerCount,
						Worlds.ClientCount,
						Worlds.ServerPIEInstance,
						Worlds.ClientPIEInstance));
				}
				if (Worlds.PIEWorldCount != 2
					|| Worlds.ListenServerCount != 1
					|| Worlds.ClientCount != 1
					|| Worlds.ServerPIEInstance != 0
					|| Worlds.ClientPIEInstance != 1)
				{
					return false;
				}

				const FPlayerPair Players =
					ResolvePlayers(Worlds.Server, Worlds.Client);
				if (Players.RemoteServerPawn
					&& Players.RemoteServerController)
				{
					PositionRemoteServerPawn(
						Players,
						HoldLocation,
						HoldRotation);
				}
				if (Players.ServerPlayerCount != 2
					|| !Players.HostPawn
					|| !Players.RemoteServerPawn
					|| !Players.RemoteClientPawn
					|| !PlayerIdentitiesMatch(Players)
					|| GetSynchronizedServerTime(Worlds.Server) < 0.f
					|| GetSynchronizedServerTime(Worlds.Client) < 0.f)
				{
					return false;
				}

				const float ServerDistance =
					ServerTarget.IsValid()
						? FVector::Distance(
							Players.RemoteServerPawn->GetActorLocation(),
							ServerTarget->GetActorLocation())
						: TNumericLimits<float>::Max();
				if (ServerDistance >= ExplosionNetworkCullDistanceCm * 0.9f)
				{
					return Fail(FString::Printf(
						TEXT("late server pawn outside FX relevance distance distanceCm=%.0f"),
						ServerDistance));
				}

				if (ARedMineableAsteroid* Target = ServerTarget.Get())
				{
					Target->ForceNetUpdate();
				}
				if (ARedShipExplosionFX* Explosion =
					FindOwnedExplosion(Worlds.Server, ServerTarget.Get()))
				{
					Explosion->ForceNetUpdate();
				}

				LateTopologyReadyAtSeconds = Now;
				UE_LOG(
					LogTemp,
					Display,
					TEXT("RED_DEF0003_FIELD_LATE_JOIN_TOPOLOGY scenario=%s pass=1 pid=%u pieWorlds=2 listen=1 clients=1 serverPIE=0 clientPIE=1 serverPlayers=2 playerIdentity=1 targetDistanceCm=%.0f"),
					ScenarioName(Scenario),
					FPlatformProcess::GetCurrentProcessId(),
					ServerDistance);
				Advance(EStage::AwaitScenario, Now);
				return false;
			}

			bool EmitMissingProxyDiagnostic(
				const FWorldPair& Worlds,
				const FPlayerPair& Players,
				const double Now)
			{
				if (Now - LateTopologyReadyAtSeconds
					< MissingProxyDiagnosticSeconds)
				{
					return false;
				}
				const ARedMineableAsteroid* Target = ServerTarget.Get();
				const float ClientDistance =
					Target && Players.RemoteServerPawn
					? FVector::Distance(
						Players.RemoteServerPawn->GetActorLocation(),
						Target->GetActorLocation())
					: -1.f;
				const FExplosionStats ClientFX =
					GetExplosionStats(Worlds.Client);
				UE_LOG(
					LogTemp,
					Error,
					TEXT("RED_DEF0003_FIELD_LATE_JOIN_MISSING_PROXY scenario=%s lateJoinTargetPresent=0 authorityPhase=%d authoritySequence=%u authorityHidden=%d authorityCollision=%d expectedNetCullCm=%.0f clientDistanceCm=%.0f connectionHealthy=1 clientExplosion=%d clientDebris=%d"),
					ScenarioName(Scenario),
					Target
						? static_cast<int32>(Target->DepletionState.Phase)
						: -1,
					Target ? Target->DepletionState.Sequence : 0,
					Target && Target->IsHidden() ? 1 : 0,
					Target && Target->GetActorEnableCollision() ? 1 : 0,
					AsteroidNetworkCullDistanceCm,
					ClientDistance,
					ClientFX.Count,
					ClientFX.SimulatingDebris);
				return Fail(TEXT(
					"healthy in-range late client did not receive retained actual-field asteroid proxy"));
			}

			bool ValidateCommonLateState(
				const FWorldPair& Worlds,
				const FPlayerPair& Players,
				ARedMineableAsteroid* ClientTarget,
				FString& OutReason) const
			{
				OutReason.Reset();
				const ARedMineableAsteroid* Target = ServerTarget.Get();
				if (!Target || !ClientTarget)
				{
					OutReason = TEXT("server or client target invalid");
					return false;
				}
				if (ClientTarget->GetStableMemberId() != TargetId
					|| ClientTarget->HasAuthority()
					|| !FMath::IsNearlyZero(ClientTarget->OreRemaining)
					|| ClientTarget->DepletionState.Phase
						!= ERedMineableAsteroidDepletionPhase::Depleted
					|| ClientTarget->DepletionState.Sequence != 2
					|| !ClientTarget->IsHidden()
					|| ClientTarget->GetActorEnableCollision()
					|| !ClientTarget->DepletionState.bRewardSpawned
					|| !ClientTarget->DepletionState.bRewardGranted)
				{
					OutReason = TEXT("client retained Depleted payload/presentation mismatch");
					return false;
				}
				if (Target->DepletionState.Phase
						!= ERedMineableAsteroidDepletionPhase::Depleted
					|| Target->DepletionState.Sequence != 2
					|| !Target->IsHidden()
					|| Target->GetActorEnableCollision()
					|| CountOtherPristineMembers(Worlds.Server, TargetId)
						!= MineableCount - 1
					|| !Players.HostPawn
					|| Players.HostPawn->ResIron - InitialHostIron != 6
					|| !Players.RemoteServerPawn
					|| !Players.RemoteClientPawn
					|| Players.RemoteServerPawn->ResIron != 0
					|| Players.RemoteClientPawn->ResIron != 0)
				{
					OutReason = TEXT("authority durability, reward, or pristine-peer mismatch");
					return false;
				}
				return true;
			}

			bool AwaitScenario(
				const FWorldPair& Worlds,
				const double Now)
			{
				if (StageTimedOut(Now))
				{
					return Fail(TEXT("late-join scenario observation timed out"));
				}
				if (!Worlds.Server || !Worlds.Client)
				{
					return false;
				}

				const FPlayerPair Players =
					ResolvePlayers(Worlds.Server, Worlds.Client);
				if (Players.RemoteServerPawn
					&& Players.RemoteServerController)
				{
					PositionRemoteServerPawn(
						Players,
						HoldLocation,
						HoldRotation);
				}
				if (Players.ServerPlayerCount != 2
					|| !Players.RemoteServerPawn
					|| !Players.RemoteClientPawn
					|| !PlayerIdentitiesMatch(Players))
				{
					return false;
				}

				ARedMineableAsteroid* ClientTarget =
					FindUniqueStableMember(Worlds.Client, TargetId);
				if (Scenario == ELateJoinScenario::DuringDepleting)
				{
					ARedMineableAsteroid* Target = ServerTarget.Get();
					if (!Target)
					{
						return Fail(TEXT("authority target invalid during Depleting join"));
					}
					if (!ClientTarget)
					{
						if (Target->DepletionState.Phase
							== ERedMineableAsteroidDepletionPhase::Depleted)
						{
							return Fail(TEXT(
								"late proxy did not arrive during bounded eight-second Depleting phase"));
						}
						return false;
					}

					const float ClientClock =
						GetSynchronizedServerTime(Worlds.Client);
					const float ServerClock =
						GetSynchronizedServerTime(Worlds.Server);
					const float Remaining =
						ClientTarget->DepletionState.StartedServerTimeSeconds
						+ ClientTarget->DepletionState.PresentationDurationSeconds
						- ClientClock;
					const float ClockErrorMs =
						FMath::Abs(ServerClock - ClientClock) * 1000.f;
					const bool bPassed =
						Target->DepletionState.Phase
							== ERedMineableAsteroidDepletionPhase::Depleting
						&& ClientTarget->DepletionState.Phase
							== ERedMineableAsteroidDepletionPhase::Depleting
						&& Target->DepletionState.Sequence == 1
						&& ClientTarget->DepletionState.Sequence == 1
						&& FMath::IsNearlyZero(ClientTarget->OreRemaining)
						&& !ClientTarget->IsHidden()
						&& !ClientTarget->GetActorEnableCollision()
						&& ClientTarget->DepletionState.bRewardSpawned
						&& ClientTarget->DepletionState.bRewardGranted
						&& Remaining > 0.25f
						&& Remaining
							< DuringJoinPresentationSeconds - 0.1f
						&& ClockErrorMs < 500.f
						&& GetExplosionStats(Worlds.Client).Count == 0;
					UE_LOG(
						LogTemp,
						Display,
						TEXT("RED_DEF0003_FIELD_LATE_JOIN_DEPLETING pass=%d phase=%d/%d sequence=%u/%u ore=%.0f hidden=%d collision=%d remaining=%.3f clockErrorMs=%.1f explosion=%d"),
						bPassed ? 1 : 0,
						static_cast<int32>(Target->DepletionState.Phase),
						static_cast<int32>(
							ClientTarget->DepletionState.Phase),
						Target->DepletionState.Sequence,
						ClientTarget->DepletionState.Sequence,
						ClientTarget->OreRemaining,
						ClientTarget->IsHidden() ? 1 : 0,
						ClientTarget->GetActorEnableCollision() ? 1 : 0,
						Remaining,
						ClockErrorMs,
						GetExplosionStats(Worlds.Client).Count);
					if (!bPassed)
					{
						return Fail(TEXT("Depleting initial-bunch state or synchronized remaining time failed"));
					}
					ClientTargetHandle = ClientTarget;
					Advance(EStage::AwaitPostScenario, Now);
					return false;
				}

				const FExplosionStats ClientFX =
					GetExplosionStats(Worlds.Client);
				if (!ClientTarget)
				{
					return EmitMissingProxyDiagnostic(
						Worlds,
						Players,
						Now);
				}

				FString CommonReason;
				if (!ValidateCommonLateState(
						Worlds,
						Players,
						ClientTarget,
						CommonReason))
				{
					return Fail(CommonReason);
				}
				const float ClientClock =
					GetSynchronizedServerTime(Worlds.Client);
				const float ServerClock =
					GetSynchronizedServerTime(Worlds.Server);
				const float ClockErrorMs =
					FMath::Abs(ServerClock - ClientClock) * 1000.f;

				if (Scenario == ELateJoinScenario::InsideReplayWindow)
				{
					if (ClientFX.Count != 1
						|| !ClientFX.UniqueExplosion)
					{
						return false;
					}
					float ClientFXStarted = -1.f;
					float ClientFXWindow = -1.f;
					if (!ReadExplosionReplayTiming(
							ClientFX.UniqueExplosion,
							ClientFXStarted,
							ClientFXWindow))
					{
						return Fail(TEXT("could not read client FX replay timing"));
					}
					const float FXAgeAtFirstObservation =
						ClientClock - ClientFXStarted;
					const bool bPassed =
						FMath::IsNearlyEqual(ClientFXWindow, 0.5f, 0.001f)
						&& FXAgeAtFirstObservation >= 0.f
						&& FXAgeAtFirstObservation < 1.25f
						&& ClientFX.SimulatingDebris >= 8
						&& ClientFX.UniqueExplosion->GetOwner()
							== ClientTarget
						&& ClockErrorMs < 500.f;
					UE_LOG(
						LogTemp,
						Display,
						TEXT("RED_DEF0003_FIELD_LATE_JOIN_REPLAY_INSIDE pass=%d fxAgeAtFirstObservation=%.3f replayWindow=%.3f debris=%d visibleLights=%d tick=%d ownerResolved=%d phase=%d sequence=%u clockErrorMs=%.1f"),
						bPassed ? 1 : 0,
						FXAgeAtFirstObservation,
						ClientFXWindow,
						ClientFX.SimulatingDebris,
						ClientFX.VisibleLights,
						ClientFX.bTickEnabled ? 1 : 0,
						ClientFX.UniqueExplosion->GetOwner()
								== ClientTarget
							? 1
							: 0,
						static_cast<int32>(
							ClientTarget->DepletionState.Phase),
						ClientTarget->DepletionState.Sequence,
						ClockErrorMs);
					if (!bPassed)
					{
						return Fail(TEXT("inside-window initial FX replay did not create bounded local presentation"));
					}
					return Pass(FString::Printf(
						TEXT("insideReplay=1 debris=%d fxAge=%.3f"),
						ClientFX.SimulatingDebris,
						FXAgeAtFirstObservation));
				}

				if (Scenario == ELateJoinScenario::OutsideReplayWindow)
				{
					if (ClientFX.Count != 1
						|| !ClientFX.UniqueExplosion)
					{
						return false;
					}
					float ClientFXStarted = -1.f;
					float ClientFXWindow = -1.f;
					if (!ReadExplosionReplayTiming(
							ClientFX.UniqueExplosion,
							ClientFXStarted,
							ClientFXWindow))
					{
						return Fail(TEXT("could not read stale client FX timing"));
					}
					const float FXAgeAtFirstObservation =
						ClientClock - ClientFXStarted;
					const bool bPassed =
						FMath::IsNearlyEqual(ClientFXWindow, 0.5f, 0.001f)
						&& FXAgeAtFirstObservation > ClientFXWindow
						&& FXAgeAtFirstObservation < 5.f
						&& ClientFX.SimulatingDebris == 0
						&& ClientFX.VisibleLights == 0
						&& ClientFX.MaxLightIntensity
							<= KINDA_SMALL_NUMBER
						&& !ClientFX.bTickEnabled
						&& ClientFX.UniqueExplosion->GetOwner()
							== ClientTarget
						&& ClockErrorMs < 500.f;
					UE_LOG(
						LogTemp,
						Display,
						TEXT("RED_DEF0003_FIELD_LATE_JOIN_REPLAY_OUTSIDE pass=%d fxAgeAtFirstObservation=%.3f replayWindow=%.3f debris=%d visibleLights=%d maxLight=%.1f tick=%d ownerResolved=%d phase=%d sequence=%u clockErrorMs=%.1f"),
						bPassed ? 1 : 0,
						FXAgeAtFirstObservation,
						ClientFXWindow,
						ClientFX.SimulatingDebris,
						ClientFX.VisibleLights,
						ClientFX.MaxLightIntensity,
						ClientFX.bTickEnabled ? 1 : 0,
						ClientFX.UniqueExplosion->GetOwner()
								== ClientTarget
							? 1
							: 0,
						static_cast<int32>(
							ClientTarget->DepletionState.Phase),
						ClientTarget->DepletionState.Sequence,
						ClockErrorMs);
					if (!bPassed)
					{
						return Fail(TEXT("outside-window FX actor did not suppress all fresh local presentation"));
					}
					return Pass(FString::Printf(
						TEXT("outsideReplaySuppressed=1 fxAge=%.3f"),
						FXAgeAtFirstObservation));
				}

				const bool bDurableNow =
					ClientFX.Count == 0
					&& CountReceipts(Worlds.Client, ClientTarget) == 0
					&& ClockErrorMs < 500.f;
				if (!bDurableNow)
				{
					DurableStateStartedAtSeconds = 0.0;
					return false;
				}
				if (DurableStateStartedAtSeconds <= 0.0)
				{
					DurableStateStartedAtSeconds = Now;
					return false;
				}
				if (Now - DurableStateStartedAtSeconds
					< DurableStabilitySeconds)
				{
					return false;
				}

				UE_LOG(
					LogTemp,
					Display,
					TEXT("RED_DEF0003_FIELD_LATE_JOIN_DURABLE pass=1 phase=%d sequence=%u ore=%.0f hidden=%d collision=%d explosion=0 receipt=0 remoteIron=%d/%d pristinePeers=%d stability=%.2f clockErrorMs=%.1f"),
					static_cast<int32>(
						ClientTarget->DepletionState.Phase),
					ClientTarget->DepletionState.Sequence,
					ClientTarget->OreRemaining,
					ClientTarget->IsHidden() ? 1 : 0,
					ClientTarget->GetActorEnableCollision() ? 1 : 0,
					Players.RemoteServerPawn->ResIron,
					Players.RemoteClientPawn->ResIron,
					CountOtherPristineMembers(Worlds.Server, TargetId),
					Now - DurableStateStartedAtSeconds,
					ClockErrorMs);
				return Pass(TEXT(
					"depletedDurable=1 transientFXExpired=1 duplicateReward=0"));
			}

			bool AwaitPostScenario(
				const FWorldPair& Worlds,
				const double Now)
			{
				if (StageTimedOut(Now))
				{
					return Fail(TEXT("Depleting late join did not converge to durable Depleted state"));
				}
				const FPlayerPair Players =
					ResolvePlayers(Worlds.Server, Worlds.Client);
				ARedMineableAsteroid* Target = ServerTarget.Get();
				ARedMineableAsteroid* ClientTarget =
					ClientTargetHandle.Get();
				if (!Target
					|| !ClientTarget
					|| !Players.HostPawn
					|| !Players.RemoteServerPawn
					|| !Players.RemoteClientPawn)
				{
					return Fail(TEXT("Depleting join proxy or player disappeared before convergence"));
				}
				if (Target->DepletionState.Phase
						!= ERedMineableAsteroidDepletionPhase::Depleted
					|| ClientTarget->DepletionState.Phase
						!= ERedMineableAsteroidDepletionPhase::Depleted
					|| Target->DepletionState.Sequence != 2
					|| ClientTarget->DepletionState.Sequence != 2)
				{
					return false;
				}

				FString CommonReason;
				if (!ValidateCommonLateState(
						Worlds,
						Players,
						ClientTarget,
						CommonReason))
				{
					return Fail(CommonReason);
				}
				if (FinalStateStartedAtSeconds <= 0.0)
				{
					FinalStateStartedAtSeconds = Now;
					return false;
				}
				if (Now - FinalStateStartedAtSeconds < 0.25)
				{
					return false;
				}

				const float ClockErrorMs =
					FMath::Abs(
						GetSynchronizedServerTime(Worlds.Server)
						- GetSynchronizedServerTime(Worlds.Client))
					* 1000.f;
				UE_LOG(
					LogTemp,
					Display,
					TEXT("RED_DEF0003_FIELD_LATE_JOIN_DEPLETING_CONVERGED pass=1 phase=%d/%d sequence=%u/%u hidden=%d collision=%d hostIronDelta=%d remoteIron=%d/%d pristinePeers=%d clockErrorMs=%.1f"),
					static_cast<int32>(Target->DepletionState.Phase),
					static_cast<int32>(
						ClientTarget->DepletionState.Phase),
					Target->DepletionState.Sequence,
					ClientTarget->DepletionState.Sequence,
					ClientTarget->IsHidden() ? 1 : 0,
					ClientTarget->GetActorEnableCollision() ? 1 : 0,
					Players.HostPawn->ResIron - InitialHostIron,
					Players.RemoteServerPawn->ResIron,
					Players.RemoteClientPawn->ResIron,
					CountOtherPristineMembers(Worlds.Server, TargetId),
					ClockErrorMs);
				return Pass(TEXT(
					"lateJoinDepleting=1 synchronizedRemaining=1 convergedDepleted=1"));
			}

			FAutomationTestBase* Test = nullptr;
			TSharedRef<FAcceptanceState> AcceptanceState;
			const ELateJoinScenario Scenario;
			const FName TargetId;
			EStage Stage = EStage::AwaitServerReady;
			double StartedAtSeconds = 0.0;
			double StageStartedAtSeconds = 0.0;
			double LateJoinRequestedAtSeconds = 0.0;
			double LateTopologyReadyAtSeconds = 0.0;
			double DurableStateStartedAtSeconds = 0.0;
			double FinalStateStartedAtSeconds = 0.0;
			float ExplosionStartedServerTimeSeconds = -1.f;
			float ExplosionReplayWindowSeconds = -1.f;
			int32 InitialHostIron = 0;
			FVector HoldLocation = FVector::ZeroVector;
			FRotator HoldRotation = FRotator::ZeroRotator;
			TWeakObjectPtr<ARedMineableAsteroid> ServerTarget;
			TWeakObjectPtr<ARedMineableAsteroid> ClientTargetHandle;
		};

		class FWaitForLateJoinPIEEndCommand final
			: public IAutomationLatentCommand
		{
		public:
			FWaitForLateJoinPIEEndCommand(
				FAutomationTestBase* InTest,
				TSharedRef<FAcceptanceState> InAcceptanceState)
				: Test(InTest)
				, AcceptanceState(MoveTemp(InAcceptanceState))
			{
			}

			virtual bool Update() override
			{
				if (StartedAtSeconds <= 0.0)
				{
					StartedAtSeconds = FPlatformTime::Seconds();
				}
				if (ResolvePIEWorlds().PIEWorldCount == 0)
				{
					AcceptanceState->bPIEEnded = true;
					UE_LOG(
						LogTemp,
						Display,
						TEXT("RED_DEF0003_FIELD_LATE_JOIN_COMPLETE scenario=%s pieEnded=1 acceptancePass=%d"),
						ScenarioName(AcceptanceState->Scenario),
						AcceptanceState->bAccepted ? 1 : 0);
					return true;
				}
				if (FPlatformTime::Seconds() - StartedAtSeconds > 15.0)
				{
					Test->AddError(FString::Printf(
						TEXT("DEF-0003 %s PIE did not end within 15 seconds."),
						ScenarioName(AcceptanceState->Scenario)));
					return true;
				}
				return false;
			}

		private:
			FAutomationTestBase* Test = nullptr;
			TSharedRef<FAcceptanceState> AcceptanceState;
			double StartedAtSeconds = 0.0;
		};

		bool QueueLateJoinScenario(
			FAutomationTestBase* Test,
			const ELateJoinScenario Scenario)
		{
			if (!Test)
			{
				return false;
			}
			if (!FApp::CanEverRender()
				|| FParse::Param(FCommandLine::Get(), TEXT("nullrhi")))
			{
				Test->AddError(TEXT(
					"DEF-0003 actual-field late-join acceptance requires a rendered non-NullRHI editor."));
				return false;
			}
			if (ResolvePIEWorlds().PIEWorldCount != 0)
			{
				Test->AddError(TEXT("A PIE session is already running."));
				return false;
			}

			ULevelEditorPlaySettings* PlaySettings =
				NewObject<ULevelEditorPlaySettings>(GetTransientPackage());
			if (!PlaySettings)
			{
				Test->AddError(TEXT(
					"Could not allocate transient late-join PIE settings."));
				return false;
			}
			PlaySettings->SetPlayNetMode(EPlayNetMode::PIE_ListenServer);
			PlaySettings->SetPlayNumberOfClients(1);
			PlaySettings->SetRunUnderOneProcess(true);
			PlaySettings->bLaunchSeparateServer = false;
			PlaySettings->GameGetsMouseControl = false;
			PlaySettings->bShouldMinimizeEditorOnNonVRPIE = false;
			PlaySettings->PIEAlwaysOnTop = false;
			PlaySettings->NewWindowWidth = 640;
			PlaySettings->NewWindowHeight = 360;
			PlaySettings->AddToRoot();

			FRequestPlaySessionParams RequestParams;
			RequestParams.WorldType = EPlaySessionWorldType::PlayInEditor;
			RequestParams.EditorPlaySettings = PlaySettings;
			RequestParams.GlobalMapOverride = ProductionMap;
			RequestParams.bAllowOnlineSubsystem = false;

			const TSharedRef<FAcceptanceState> AcceptanceState =
				MakeShared<FAcceptanceState>(Scenario);
			ADD_LATENT_AUTOMATION_COMMAND(
				FEditorLoadMap(ProductionMap));
			ADD_LATENT_AUTOMATION_COMMAND(
				FWaitForShadersToFinishCompiling());
			ADD_LATENT_AUTOMATION_COMMAND(
				FStartPIEForAutomationCommand(RequestParams));
			ADD_LATENT_AUTOMATION_COMMAND(
				FActualFieldLateJoinCommand(
					Test,
					AcceptanceState));
			ADD_LATENT_AUTOMATION_COMMAND(FEndPlayMapCommand());
			ADD_LATENT_AUTOMATION_COMMAND(
				FWaitForLateJoinPIEEndCommand(
					Test,
					AcceptanceState));
			return true;
		}
	}

	IMPLEMENT_SIMPLE_AUTOMATION_TEST(
		FRedDEF0003ActualFieldLateJoinDuringDepletingPIETest,
		"RedMMO.Mining.DEF0003.ActualFieldLateJoinPIE.DuringDepleting",
		EAutomationTestFlags::EditorContext
			| EAutomationTestFlags::ProductFilter)

	bool FRedDEF0003ActualFieldLateJoinDuringDepletingPIETest::RunTest(
		const FString& Parameters)
	{
		(void)Parameters;
		return Private::QueueLateJoinScenario(
			this,
			Private::ELateJoinScenario::DuringDepleting);
	}

	IMPLEMENT_SIMPLE_AUTOMATION_TEST(
		FRedDEF0003ActualFieldLateJoinInsideReplayPIETest,
		"RedMMO.Mining.DEF0003.ActualFieldLateJoinPIE.InsideReplayWindow",
		EAutomationTestFlags::EditorContext
			| EAutomationTestFlags::ProductFilter)

	bool FRedDEF0003ActualFieldLateJoinInsideReplayPIETest::RunTest(
		const FString& Parameters)
	{
		(void)Parameters;
		return Private::QueueLateJoinScenario(
			this,
			Private::ELateJoinScenario::InsideReplayWindow);
	}

	IMPLEMENT_SIMPLE_AUTOMATION_TEST(
		FRedDEF0003ActualFieldLateJoinOutsideReplayPIETest,
		"RedMMO.Mining.DEF0003.ActualFieldLateJoinPIE.OutsideReplayWindow",
		EAutomationTestFlags::EditorContext
			| EAutomationTestFlags::ProductFilter)

	bool FRedDEF0003ActualFieldLateJoinOutsideReplayPIETest::RunTest(
		const FString& Parameters)
	{
		(void)Parameters;
		return Private::QueueLateJoinScenario(
			this,
			Private::ELateJoinScenario::OutsideReplayWindow);
	}

	IMPLEMENT_SIMPLE_AUTOMATION_TEST(
		FRedDEF0003ActualFieldLateJoinDurablePIETest,
		"RedMMO.Mining.DEF0003.ActualFieldLateJoinPIE.DurableAfterTransientExpiry",
		EAutomationTestFlags::EditorContext
			| EAutomationTestFlags::ProductFilter)

	bool FRedDEF0003ActualFieldLateJoinDurablePIETest::RunTest(
		const FString& Parameters)
	{
		(void)Parameters;
		return Private::QueueLateJoinScenario(
			this,
			Private::ELateJoinScenario::DurableAfterTransientExpiry);
	}
}

#endif // WITH_DEV_AUTOMATION_TESTS && WITH_EDITOR
