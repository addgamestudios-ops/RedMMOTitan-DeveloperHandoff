#include "../RedMineableAsteroid.h"
#include "../RedPlanetPresentationTuning.h"
#include "../RedPlayerCharacter.h"
#include "../RedSpaceScenery.h"

#if WITH_DEV_AUTOMATION_TESTS && WITH_EDITOR

#include "Camera/CameraActor.h"
#include "Camera/CameraComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Editor.h"
#include "Engine/Engine.h"
#include "Engine/StaticMesh.h"
#include "Engine/StaticMeshActor.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "Framework/Application/SlateApplication.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/PlayerController.h"
#include "GameFramework/PlayerState.h"
#include "HAL/FileManager.h"
#include "HAL/IConsoleManager.h"
#include "HAL/PlatformProcess.h"
#include "HAL/PlatformTime.h"
#include "ImageUtils.h"
#include "Misc/App.h"
#include "Misc/AutomationTest.h"
#include "Misc/CommandLine.h"
#include "Misc/FileHelper.h"
#include "Misc/Parse.h"
#include "Misc/Paths.h"
#include "PlayInEditorDataTypes.h"
#include "Settings/LevelEditorPlaySettings.h"
#include "Tests/AutomationEditorCommon.h"
#include "Widgets/SWindow.h"

namespace RedMMO::DEF0003ActualFieldTwoClientCullPIE
{
	namespace Private
	{
		constexpr TCHAR ProductionMap[] = TEXT("/Game/RedMMO/Maps/RedPlanetGen");
		constexpr TCHAR TargetStableIdText[] =
			TEXT("asteroid-field.red.mars.deep-space/0x4F524531/23");
		constexpr int32 MineableCount = 24;
		constexpr double TopologyTimeoutSeconds = 60.0;
		constexpr double StageTimeoutSeconds = 20.0;
		constexpr double InitialFarSampleSeconds = 1.5;
		constexpr double NearSampleSeconds = 1.0;
		constexpr double FinalFarBaselineSeconds = 0.45;
		constexpr double FinalFarSampleSeconds = 1.65;
		constexpr float RenderRecencySeconds = 0.35f;
		constexpr float TargetCullDistanceCm =
			RedPlanetPresentationTuning::AsteroidRenderCullDistanceCm;
		constexpr float NearCenterDistanceCm = TargetCullDistanceCm * 0.25f;
		constexpr float FarCenterDistanceCm = TargetCullDistanceCm * 1.15f;
		constexpr float PawnHoldDistanceCm = 200000.f;
		constexpr float PawnHoldTangentOffsetCm = 100000.f;

		struct FAcceptanceState
		{
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

		struct FPeerView
		{
			TWeakObjectPtr<ARedMineableAsteroid> Target;
			TWeakObjectPtr<UStaticMeshComponent> TargetMesh;
			TWeakObjectPtr<ACameraActor> Camera;
			TWeakObjectPtr<AStaticMeshActor> ReferenceActor;
			TWeakObjectPtr<UStaticMeshComponent> ReferenceMesh;
		};

		struct FFrameGeometry
		{
			bool bViewMatches = false;
			bool bTargetProjected = false;
			bool bTargetCentered = false;
			bool bReferenceProjected = false;
			bool bReferenceOnScreen = false;
			bool bTraceExactTarget = false;
			float CenterDistanceCm = 0.f;
			float BoundsRadiusCm = 0.f;
			float ClosestBoundsDistanceCm = 0.f;
			float ProjectedTargetDiameterPx = 0.f;
			FVector2D TargetScreen = FVector2D::ZeroVector;
			FVector2D ReferenceScreen = FVector2D::ZeroVector;
			int32 ViewportWidth = 0;
			int32 ViewportHeight = 0;
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
					++Result.ListenServerCount;
				}
				else if (World->GetNetMode() == NM_Client)
				{
					Result.Client = World;
					++Result.ClientCount;
				}
			}
			return Result;
		}

		FPlayerPair ResolvePlayers(UWorld* ServerWorld, UWorld* ClientWorld)
		{
			FPlayerPair Result;
			if (!ServerWorld || !ClientWorld)
			{
				return Result;
			}

			for (FConstPlayerControllerIterator It =
					ServerWorld->GetPlayerControllerIterator();
				It; ++It)
			{
				APlayerController* Controller = It->Get();
				ARedPlayerCharacter* Pawn =
					Controller ? Cast<ARedPlayerCharacter>(Controller->GetPawn()) : nullptr;
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

			for (FConstPlayerControllerIterator It =
					ClientWorld->GetPlayerControllerIterator();
				It; ++It)
			{
				APlayerController* Controller = It->Get();
				ARedPlayerCharacter* Pawn =
					Controller ? Cast<ARedPlayerCharacter>(Controller->GetPawn()) : nullptr;
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

		bool TargetStateIsUnchanged(
			const ARedMineableAsteroid* Target,
			const FName StableId,
			const bool bExpectAuthority)
		{
			const UStaticMeshComponent* Mesh = Target
				? Cast<UStaticMeshComponent>(Target->GetRootComponent())
				: nullptr;
			return IsValid(Target)
				&& Target->GetStableMemberId() == StableId
				&& Target->HasAuthority() == bExpectAuthority
				&& !Target->HasAnyFlags(RF_Transient)
				&& Target->DepletionState.Phase
					== ERedMineableAsteroidDepletionPhase::Active
				&& FMath::IsNearlyEqual(Target->OreCapacity, 6000.f)
				&& FMath::IsNearlyEqual(Target->OreRemaining, 6000.f)
				&& Target->GetActorEnableCollision()
				&& !Target->IsHidden()
				&& FMath::IsNearlyEqual(
					Target->GetPresentationCullDistance(),
					TargetCullDistanceCm,
					1.f)
				&& Mesh
				&& Mesh->GetWorld() == Target->GetWorld()
				&& Mesh->IsRegistered()
				&& Mesh->IsVisible()
				&& FMath::IsNearlyEqual(
					Mesh->LDMaxDrawDistance,
					TargetCullDistanceCm,
					1.f)
				&& FMath::IsNearlyEqual(
					Mesh->CachedMaxDrawDistance,
					TargetCullDistanceCm,
					1.f);
		}

		bool TraceExactTarget(
			UWorld* World,
			const FVector& Start,
			const FVector& End,
			const AActor* Target,
			const AActor* Pawn,
			const AActor* ReferenceActor)
		{
			FCollisionQueryParams Params(
				SCENE_QUERY_STAT(RedDEF0003ActualFieldTwoClientCullTrace),
				true);
			if (Pawn)
			{
				Params.AddIgnoredActor(Pawn);
			}
			if (ReferenceActor)
			{
				Params.AddIgnoredActor(ReferenceActor);
			}
			FHitResult Hit;
			return World
				&& World->LineTraceSingleByChannel(
					Hit,
					Start,
					End,
					ECC_Visibility,
					Params)
				&& Hit.GetActor() == Target;
		}

		bool CapturePIEWindow(
			const FString& RequiredTitleText,
			const FString& Filename,
			FString& OutWindowTitle)
		{
			OutWindowTitle.Reset();
			if (!FSlateApplication::IsInitialized())
			{
				return false;
			}

			TSharedPtr<SWindow> MatchedWindow;
			int32 MatchCount = 0;
			for (const TSharedRef<SWindow>& Window :
				FSlateApplication::Get().GetTopLevelWindows())
			{
				const FString Title = Window->GetTitle().ToString();
				if (Title.Contains(RequiredTitleText))
				{
					MatchedWindow = Window;
					OutWindowTitle = Title;
					++MatchCount;
				}
			}
			if (MatchCount != 1 || !MatchedWindow.IsValid())
			{
				return false;
			}

			TArray<FColor> Pixels;
			FIntVector Size = FIntVector::ZeroValue;
			if (!FSlateApplication::Get().TakeScreenshot(
					MatchedWindow.ToSharedRef(),
					Pixels,
					Size)
				|| Size.X <= 0
				|| Size.Y <= 0
				|| Pixels.Num() < Size.X * Size.Y)
			{
				return false;
			}

			IFileManager::Get().MakeDirectory(*FPaths::GetPath(Filename), true);
			TArray64<uint8> PNG;
			FImageUtils::PNGCompressImageArray(
				Size.X,
				Size.Y,
				TArrayView64<const FColor>(Pixels.GetData(), Pixels.Num()),
				PNG);
			return PNG.Num() > 0
				&& FFileHelper::SaveArrayToFile(PNG, *Filename);
		}

		class FActualFieldTwoClientCullCommand final
			: public IAutomationLatentCommand
		{
		public:
			FActualFieldTwoClientCullCommand(
				FAutomationTestBase* InTest,
				TSharedRef<FAcceptanceState> InAcceptanceState)
				: Test(InTest)
				, AcceptanceState(MoveTemp(InAcceptanceState))
				, TargetId(TargetStableIdText)
			{
				FParse::Value(
					FCommandLine::Get(),
					TEXT("RedDEF0003FieldMPCullCaptureDir="),
					CaptureDirectory);
				if (CaptureDirectory.IsEmpty())
				{
					CaptureDirectory = FPaths::Combine(
						FPaths::ProjectSavedDir(),
						TEXT("Automation/DEF0003ActualFieldTwoClientCullPIE"));
				}
				CaptureDirectory =
					FPaths::ConvertRelativePathToFull(CaptureDirectory);
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
				const FPlayerPair Players =
					ResolvePlayers(Worlds.Server, Worlds.Client);
				switch (Stage)
				{
				case EStage::AwaitTopology:
					return AwaitTopology(Worlds, Players, Now);
				case EStage::AwaitClientProxy:
					return AwaitClientProxy(Worlds, Players, Now);
				case EStage::AwaitInitialFar:
					return AwaitInitialFar(Worlds, Players, Now);
				case EStage::AwaitNear:
					return AwaitNear(Worlds, Players, Now);
				case EStage::AwaitFinalFar:
					return AwaitFinalFar(Worlds, Players, Now);
				case EStage::AwaitServerFar:
					return AwaitServerFar(Worlds, Players, Now);
				case EStage::Complete:
					return true;
				default:
					return Fail(TEXT("unknown acceptance stage"));
				}
			}

		private:
			enum class EStage : uint8
			{
				AwaitTopology,
				AwaitClientProxy,
				AwaitInitialFar,
				AwaitNear,
				AwaitFinalFar,
				AwaitServerFar,
				Complete
			};

			bool Fail(const FString& Reason)
			{
				Test->AddError(FString::Printf(
					TEXT("DEF-0003 actual-field two-client cull acceptance failed: %s"),
					*Reason));
				UE_LOG(LogTemp, Error,
					TEXT("RED_DEF0003_FIELD_MP_CULL_RESULT acceptancePass=0 reason=\"%s\""),
					*Reason.ReplaceCharWithEscapedChar());
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
				bFarBaselineCaptured = false;
			}

			float ReadViewDistanceScale() const
			{
				const IConsoleVariable* Variable =
					IConsoleManager::Get().FindConsoleVariable(
						TEXT("r.ViewDistanceScale"));
				return Variable ? Variable->GetFloat() : -1.f;
			}

			bool AwaitTopology(
				const FWorldPair& Worlds,
				const FPlayerPair& Players,
				const double Now)
			{
				if (Now - StartedAtSeconds > TopologyTimeoutSeconds)
				{
					return Fail(FString::Printf(
						TEXT("topology timeout pie=%d listen=%d clients=%d serverPlayers=%d"),
						Worlds.PIEWorldCount,
						Worlds.ListenServerCount,
						Worlds.ClientCount,
						Players.ServerPlayerCount));
				}
				if (Worlds.PIEWorldCount != 2
					|| Worlds.ListenServerCount != 1
					|| Worlds.ClientCount != 1
					|| Players.ServerPlayerCount != 2
					|| !Players.HostController
					|| !Players.RemoteServerController
					|| !Players.RemoteClientController
					|| !Players.HostPawn
					|| !Players.RemoteServerPawn
					|| !Players.RemoteClientPawn
					|| !PlayerIdentitiesMatch(Players))
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
					|| !TargetStateIsUnchanged(Target, TargetId, true)
					|| Target->GetOwner() != Scenery
					|| !Target->ActorHasTag(TEXT("RedMarsMineableBelt"))
					|| Target->GetLocalRole() != ROLE_Authority)
				{
					return Fail(TEXT("authority production field identity failed"));
				}

				FVector BoundsOrigin;
				FVector BoundsExtent;
				Target->GetActorBounds(
					false,
					BoundsOrigin,
					BoundsExtent,
					true);
				RadialOut =
					(BoundsOrigin - Scenery->GetActorLocation()).GetSafeNormal();
				if (RadialOut.IsNearlyZero())
				{
					return Fail(TEXT("authority target radial direction is zero"));
				}

				ViewDistanceScale = ReadViewDistanceScale();
				if (ViewDistanceScale < 0.95f || ViewDistanceScale > 1.05f)
				{
					return Fail(FString::Printf(
						TEXT("unsupported r.ViewDistanceScale=%.3f"),
						ViewDistanceScale));
				}
				ActualNetCullDistanceCm =
					FMath::Sqrt(Target->GetNetCullDistanceSquared());
				if (ActualNetCullDistanceCm
					<= FarCenterDistanceCm * 1.25f)
				{
					return Fail(FString::Printf(
						TEXT("actual network cull %.1f lacks far-camera margin"),
						ActualNetCullDistanceCm));
				}

				ServerTarget = Target;
				ServerTargetLocation = Target->GetActorLocation();
				ServerTargetRotation = Target->GetActorQuat();
				ServerTargetScale = Target->GetActorScale3D();
				FVector HoldTangent;
				FVector HoldBitangent;
				RadialOut.FindBestAxisVectors(
					HoldTangent,
					HoldBitangent);
				RemotePawnHoldLocation =
					BoundsOrigin
					+ RadialOut * PawnHoldDistanceCm
					+ HoldTangent * PawnHoldTangentOffsetCm;
				const FRotator HoldRotation =
					(BoundsOrigin - RemotePawnHoldLocation).Rotation();

				if (UCharacterMovementComponent* Movement =
					Players.RemoteServerPawn->GetCharacterMovement())
				{
					Movement->StopMovementImmediately();
					Movement->DisableMovement();
				}
				Players.RemoteServerPawn->SetActorLocationAndRotation(
					RemotePawnHoldLocation,
					HoldRotation,
					false,
					nullptr,
					ETeleportType::TeleportPhysics);
				Players.RemoteServerController->SetControlRotation(HoldRotation);
				Players.RemoteServerPawn->ForceNetUpdate();

				UE_LOG(LogTemp, Display,
					TEXT("RED_DEF0003_FIELD_MP_CULL_TOPOLOGY pass=1 pid=%u pieWorlds=%d listen=%d clients=%d serverPlayers=%d remotePlayerId=%d viewDistanceScale=%.3f"),
					FPlatformProcess::GetCurrentProcessId(),
					Worlds.PIEWorldCount,
					Worlds.ListenServerCount,
					Worlds.ClientCount,
					Players.ServerPlayerCount,
					Players.RemoteServerController->PlayerState->GetPlayerId(),
					ViewDistanceScale);
				Advance(EStage::AwaitClientProxy, Now);
				return false;
			}

			bool AwaitClientProxy(
				const FWorldPair& Worlds,
				const FPlayerPair& Players,
				const double Now)
			{
				if (StageTimedOut(Now))
				{
					return Fail(TEXT("remote actual-field proxy replication timeout"));
				}
				ARedMineableAsteroid* AuthorityTarget = ServerTarget.Get();
				ARedMineableAsteroid* ProxyTarget =
					FindUniqueStableMember(Worlds.Client, TargetId);
				if (!AuthorityTarget
					|| !ProxyTarget
					|| !Players.RemoteClientPawn
					|| !PlayerIdentitiesMatch(Players))
				{
					return false;
				}
				if (!TargetStateIsUnchanged(AuthorityTarget, TargetId, true)
					|| !TargetStateIsUnchanged(ProxyTarget, TargetId, false)
					|| ProxyTarget->GetLocalRole() != ROLE_SimulatedProxy
					|| ProxyTarget->GetWorld() != Worlds.Client
					|| AuthorityTarget->GetWorld() != Worlds.Server
					|| !ProxyTarget->GetActorLocation().Equals(
						ServerTargetLocation,
						1.f)
					|| FMath::Abs(
						ProxyTarget->GetActorQuat().GetNormalized()
							| ServerTargetRotation.GetNormalized()) < 0.99999f
					|| !ProxyTarget->GetActorScale3D().Equals(
						ServerTargetScale,
						0.001f)
					|| !FMath::IsNearlyEqual(
						FMath::Sqrt(
							ProxyTarget->GetNetCullDistanceSquared()),
						ActualNetCullDistanceCm,
						1.f))
				{
					return Fail(TEXT("remote stable identity/transform/cull parity failed"));
				}

				const float ClientPawnDistance =
					FVector::Distance(
						Players.RemoteClientPawn->GetActorLocation(),
						ProxyTarget->GetActorLocation());
				if (ClientPawnDistance
					>= ActualNetCullDistanceCm * 0.9f)
				{
					return false;
				}

				ClientTarget = ProxyTarget;
				if (!CreatePeerView(
						Worlds.Server,
						AuthorityTarget,
						ServerView)
					|| !CreatePeerView(
						Worlds.Client,
						ProxyTarget,
						ClientView))
				{
					return Fail(TEXT("peer cameras/reference primitives failed"));
				}
				if (!PositionViews(Players, FarCenterDistanceCm))
				{
					return Fail(TEXT("initial far camera positioning failed"));
				}

				UE_LOG(LogTemp, Display,
					TEXT("RED_DEF0003_FIELD_MP_CULL_IDENTITY pass=1 stableId=%s authorityRole=%d remoteRole=%d transformParity=1 scaleParity=1 serverCull=%.1f clientCull=%.1f clientPawnDistanceCm=%.1f cutoffOverridden=0"),
					*TargetId.ToString(),
					static_cast<int32>(AuthorityTarget->GetLocalRole()),
					static_cast<int32>(ProxyTarget->GetLocalRole()),
					AuthorityTarget->GetPresentationCullDistance(),
					ProxyTarget->GetPresentationCullDistance(),
					ClientPawnDistance);
				Advance(EStage::AwaitInitialFar, Now);
				return false;
			}

			bool AwaitInitialFar(
				const FWorldPair& Worlds,
				const FPlayerPair& Players,
				const double Now)
			{
				if (StageTimedOut(Now))
				{
					return Fail(TEXT("initial far cull/reference render timeout"));
				}
				if (!PinViews(Players)
					|| !ValidateActorContinuity(Worlds))
				{
					return false;
				}
				if (!bFarBaselineCaptured
					&& Now - StageStartedAtSeconds >= FinalFarBaselineSeconds)
				{
					InitialFarServerBaseline =
						ServerView.TargetMesh->GetLastRenderTimeOnScreen();
					InitialFarClientBaseline =
						ClientView.TargetMesh->GetLastRenderTimeOnScreen();
					bFarBaselineCaptured = true;
				}
				if (!bFarBaselineCaptured
					|| Now - StageStartedAtSeconds < InitialFarSampleSeconds)
				{
					return false;
				}

				FFrameGeometry ServerGeometry;
				FFrameGeometry ClientGeometry;
				const bool bServerGeometry =
					QueryFrameGeometry(
						Worlds.Server,
						Players.HostController,
						Players.HostPawn,
						ServerView,
						ServerGeometry);
				const bool bClientGeometry =
					QueryFrameGeometry(
						Worlds.Client,
						Players.RemoteClientController,
						Players.RemoteClientPawn,
						ClientView,
						ClientGeometry);
				const float ServerLast =
					ServerView.TargetMesh->GetLastRenderTimeOnScreen();
				const float ClientLast =
					ClientView.TargetMesh->GetLastRenderTimeOnScreen();
				const bool bPassed =
					bServerGeometry
					&& bClientGeometry
					&& FarGeometryPassed(ServerGeometry)
					&& FarGeometryPassed(ClientGeometry)
					&& ReferenceIsRendering(Worlds.Server, ServerView)
					&& ReferenceIsRendering(Worlds.Client, ClientView)
					&& !ServerView.TargetMesh->WasRecentlyRendered(
						RenderRecencySeconds)
					&& !ClientView.TargetMesh->WasRecentlyRendered(
						RenderRecencySeconds)
					&& ServerLast <= InitialFarServerBaseline + 0.1f
					&& ClientLast <= InitialFarClientBaseline + 0.1f;
				if (!bPassed)
				{
					if (Now - LastDiagnosticAtSeconds >= 1.0)
					{
						LastDiagnosticAtSeconds = Now;
						UE_LOG(LogTemp, Warning,
							TEXT("RED_DEF0003_FIELD_MP_CULL_INITIAL_FAR_WAIT serverGeometry=%d clientGeometry=%d serverFarGeometry=%d clientFarGeometry=%d serverView=%d clientView=%d serverProjected=%d clientProjected=%d serverCentered=%d clientCentered=%d serverReferenceProjected=%d clientReferenceProjected=%d serverReferenceOnScreen=%d clientReferenceOnScreen=%d serverTrace=%d clientTrace=%d serverViewport=%dx%d clientViewport=%dx%d serverScreen=(%.1f,%.1f) clientScreen=(%.1f,%.1f) serverDiameterPx=%.1f clientDiameterPx=%.1f serverTargetRecent=%d clientTargetRecent=%d serverReferenceRecent=%d clientReferenceRecent=%d serverTargetLast=%.3f clientTargetLast=%.3f serverReferenceLast=%.3f clientReferenceLast=%.3f serverWorldTime=%.3f clientWorldTime=%.3f serverBaseline=%.3f clientBaseline=%.3f"),
							bServerGeometry ? 1 : 0,
							bClientGeometry ? 1 : 0,
							FarGeometryPassed(ServerGeometry) ? 1 : 0,
							FarGeometryPassed(ClientGeometry) ? 1 : 0,
							ServerGeometry.bViewMatches ? 1 : 0,
							ClientGeometry.bViewMatches ? 1 : 0,
							ServerGeometry.bTargetProjected ? 1 : 0,
							ClientGeometry.bTargetProjected ? 1 : 0,
							ServerGeometry.bTargetCentered ? 1 : 0,
							ClientGeometry.bTargetCentered ? 1 : 0,
							ServerGeometry.bReferenceProjected ? 1 : 0,
							ClientGeometry.bReferenceProjected ? 1 : 0,
							ServerGeometry.bReferenceOnScreen ? 1 : 0,
							ClientGeometry.bReferenceOnScreen ? 1 : 0,
							ServerGeometry.bTraceExactTarget ? 1 : 0,
							ClientGeometry.bTraceExactTarget ? 1 : 0,
							ServerGeometry.ViewportWidth,
							ServerGeometry.ViewportHeight,
							ClientGeometry.ViewportWidth,
							ClientGeometry.ViewportHeight,
							ServerGeometry.TargetScreen.X,
							ServerGeometry.TargetScreen.Y,
							ClientGeometry.TargetScreen.X,
							ClientGeometry.TargetScreen.Y,
							ServerGeometry.ProjectedTargetDiameterPx,
							ClientGeometry.ProjectedTargetDiameterPx,
							ServerView.TargetMesh->WasRecentlyRendered(
								RenderRecencySeconds) ? 1 : 0,
							ClientView.TargetMesh->WasRecentlyRendered(
								RenderRecencySeconds) ? 1 : 0,
							ReferenceIsRendering(
								Worlds.Server,
								ServerView) ? 1 : 0,
							ReferenceIsRendering(
								Worlds.Client,
								ClientView) ? 1 : 0,
							ServerLast,
							ClientLast,
							ServerView.ReferenceMesh->GetLastRenderTimeOnScreen(),
							ClientView.ReferenceMesh->GetLastRenderTimeOnScreen(),
							Worlds.Server->GetTimeSeconds(),
							Worlds.Client->GetTimeSeconds(),
							InitialFarServerBaseline,
							InitialFarClientBaseline);
					}
					return false;
				}

				UE_LOG(LogTemp, Display,
					TEXT("RED_DEF0003_FIELD_MP_CULL_INITIAL_FAR pass=1 stableId=%s serverCenterCm=%.1f clientCenterCm=%.1f serverClosestCm=%.1f clientClosestCm=%.1f serverLast=%.3f clientLast=%.3f serverReferenceRecent=1 clientReferenceRecent=1 targetRecent=0/0"),
					*TargetId.ToString(),
					ServerGeometry.CenterDistanceCm,
					ClientGeometry.CenterDistanceCm,
					ServerGeometry.ClosestBoundsDistanceCm,
					ClientGeometry.ClosestBoundsDistanceCm,
					ServerLast,
					ClientLast);
				if (!PositionViews(Players, NearCenterDistanceCm))
				{
					return Fail(TEXT("near camera positioning failed"));
				}
				ServerNearStartedWorldSeconds =
					Worlds.Server->GetTimeSeconds();
				ClientNearStartedWorldSeconds =
					Worlds.Client->GetTimeSeconds();
				Advance(EStage::AwaitNear, Now);
				return false;
			}

			bool AwaitNear(
				const FWorldPair& Worlds,
				const FPlayerPair& Players,
				const double Now)
			{
				if (StageTimedOut(Now))
				{
					return Fail(TEXT("near peer render/capture timeout"));
				}
				if (!PinViews(Players)
					|| !ValidateActorContinuity(Worlds)
					|| Now - StageStartedAtSeconds < NearSampleSeconds)
				{
					return false;
				}

				FFrameGeometry ServerGeometry;
				FFrameGeometry ClientGeometry;
				const bool bServerGeometry =
					QueryFrameGeometry(
						Worlds.Server,
						Players.HostController,
						Players.HostPawn,
						ServerView,
						ServerGeometry);
				const bool bClientGeometry =
					QueryFrameGeometry(
						Worlds.Client,
						Players.RemoteClientController,
						Players.RemoteClientPawn,
						ClientView,
						ClientGeometry);
				const float ServerLast =
					ServerView.TargetMesh->GetLastRenderTimeOnScreen();
				const float ClientLast =
					ClientView.TargetMesh->GetLastRenderTimeOnScreen();
				const bool bPassed =
					bServerGeometry
					&& bClientGeometry
					&& NearGeometryPassed(ServerGeometry)
					&& NearGeometryPassed(ClientGeometry)
					&& ReferenceIsRendering(Worlds.Server, ServerView)
					&& ReferenceIsRendering(Worlds.Client, ClientView)
					&& ServerView.TargetMesh->WasRecentlyRendered(
						RenderRecencySeconds)
					&& ClientView.TargetMesh->WasRecentlyRendered(
						RenderRecencySeconds)
					&& ServerLast >= ServerNearStartedWorldSeconds - 0.1f
					&& ClientLast >= ClientNearStartedWorldSeconds - 0.1f;
				if (!bPassed)
				{
					return false;
				}

				FString ServerWindowTitle;
				FString ClientWindowTitle;
				const FString ServerCapture = FPaths::Combine(
					CaptureDirectory,
					TEXT("DEF0003_Field_MP_Server_Near.png"));
				const FString ClientCapture = FPaths::Combine(
					CaptureDirectory,
					TEXT("DEF0003_Field_MP_Client_Near.png"));
				if (!CapturePIEWindow(
						TEXT("NetMode: Server 0"),
						ServerCapture,
						ServerWindowTitle)
					|| !CapturePIEWindow(
						TEXT("NetMode: Client 1"),
						ClientCapture,
						ClientWindowTitle))
				{
					return false;
				}

				UE_LOG(LogTemp, Display,
					TEXT("RED_DEF0003_FIELD_MP_CULL_NEAR pass=1 stableId=%s serverCenterCm=%.1f clientCenterCm=%.1f serverClosestCm=%.1f clientClosestCm=%.1f cullCm=%.1f serverLast=%.3f clientLast=%.3f targetRecent=1/1 referenceRecent=1/1 serverCapture=\"%s\" clientCapture=\"%s\" serverWindow=\"%s\" clientWindow=\"%s\""),
					*TargetId.ToString(),
					ServerGeometry.CenterDistanceCm,
					ClientGeometry.CenterDistanceCm,
					ServerGeometry.ClosestBoundsDistanceCm,
					ClientGeometry.ClosestBoundsDistanceCm,
					TargetCullDistanceCm,
					ServerLast,
					ClientLast,
					*ServerCapture,
					*ClientCapture,
					*ServerWindowTitle.ReplaceCharWithEscapedChar(),
					*ClientWindowTitle.ReplaceCharWithEscapedChar());
				if (!PositionPeerView(
						Players.RemoteClientController,
						ClientView,
						FarCenterDistanceCm))
				{
					return Fail(TEXT("client-far camera positioning failed"));
				}
				Advance(EStage::AwaitFinalFar, Now);
				return false;
			}

			bool AwaitFinalFar(
				const FWorldPair& Worlds,
				const FPlayerPair& Players,
				const double Now)
			{
				if (StageTimedOut(Now))
				{
					return Fail(TEXT("client-far/host-near cull timeout"));
				}
				if (!PinViews(Players)
					|| !ValidateActorContinuity(Worlds))
				{
					return false;
				}
				if (!bFarBaselineCaptured
					&& Now - StageStartedAtSeconds >= FinalFarBaselineSeconds)
				{
					FinalFarServerBaseline =
						ServerView.TargetMesh->GetLastRenderTimeOnScreen();
					FinalFarClientBaseline =
						ClientView.TargetMesh->GetLastRenderTimeOnScreen();
					bFarBaselineCaptured = true;
				}
				if (!bFarBaselineCaptured
					|| Now - StageStartedAtSeconds < FinalFarSampleSeconds)
				{
					return false;
				}

				FFrameGeometry ServerGeometry;
				FFrameGeometry ClientGeometry;
				const bool bServerGeometry =
					QueryFrameGeometry(
						Worlds.Server,
						Players.HostController,
						Players.HostPawn,
						ServerView,
						ServerGeometry);
				const bool bClientGeometry =
					QueryFrameGeometry(
						Worlds.Client,
						Players.RemoteClientController,
						Players.RemoteClientPawn,
						ClientView,
						ClientGeometry);
				const float ServerLast =
					ServerView.TargetMesh->GetLastRenderTimeOnScreen();
				const float ClientLast =
					ClientView.TargetMesh->GetLastRenderTimeOnScreen();
				const bool bPassed =
					bServerGeometry
					&& bClientGeometry
					&& NearGeometryPassed(ServerGeometry)
					&& FarGeometryPassed(ClientGeometry)
					&& ReferenceIsRendering(Worlds.Server, ServerView)
					&& ReferenceIsRendering(Worlds.Client, ClientView)
					&& ServerView.TargetMesh->WasRecentlyRendered(
						RenderRecencySeconds)
					&& !ClientView.TargetMesh->WasRecentlyRendered(
						RenderRecencySeconds)
					&& ServerLast > FinalFarServerBaseline + 0.2f
					&& ClientLast <= FinalFarClientBaseline + 0.1f;
				if (!bPassed)
				{
					return false;
				}

				FString ClientWindowTitle;
				const FString ClientCapture = FPaths::Combine(
					CaptureDirectory,
					TEXT("DEF0003_Field_MP_Client_Far.png"));
				if (!CapturePIEWindow(
						TEXT("NetMode: Client 1"),
						ClientCapture,
						ClientWindowTitle))
				{
					return false;
				}

				UE_LOG(LogTemp, Display,
					TEXT("RED_DEF0003_FIELD_MP_CULL_CLIENT_FAR pass=1 stableId=%s serverCenterCm=%.1f clientCenterCm=%.1f serverClosestCm=%.1f clientClosestCm=%.1f serverProjectedDiameterPx=%.1f clientProjectedDiameterPx=%.1f cullCm=%.1f netCullCm=%.1f serverLast=%.3f clientLast=%.3f serverBaseline=%.3f clientBaseline=%.3f targetRecent=1/0 referenceRecent=1/1 proxyRetained=1 traceExact=1/1 projected=1/1 clientCapture=\"%s\" clientWindow=\"%s\""),
					*TargetId.ToString(),
					ServerGeometry.CenterDistanceCm,
					ClientGeometry.CenterDistanceCm,
					ServerGeometry.ClosestBoundsDistanceCm,
					ClientGeometry.ClosestBoundsDistanceCm,
					ServerGeometry.ProjectedTargetDiameterPx,
					ClientGeometry.ProjectedTargetDiameterPx,
					TargetCullDistanceCm,
					ActualNetCullDistanceCm,
					ServerLast,
					ClientLast,
					FinalFarServerBaseline,
					FinalFarClientBaseline,
					*ClientCapture,
					*ClientWindowTitle.ReplaceCharWithEscapedChar());
				if (!PositionPeerView(
						Players.HostController,
						ServerView,
						FarCenterDistanceCm)
					|| !PositionPeerView(
						Players.RemoteClientController,
						ClientView,
						NearCenterDistanceCm))
				{
					return Fail(TEXT("server-far/client-near positioning failed"));
				}
				ClientReNearStartedWorldSeconds =
					Worlds.Client->GetTimeSeconds();
				Advance(EStage::AwaitServerFar, Now);
				return false;
			}

			bool AwaitServerFar(
				const FWorldPair& Worlds,
				const FPlayerPair& Players,
				const double Now)
			{
				if (StageTimedOut(Now))
				{
					return Fail(TEXT("server-far/client-near cull timeout"));
				}
				if (!PinViews(Players)
					|| !ValidateActorContinuity(Worlds))
				{
					return false;
				}
				if (!bFarBaselineCaptured
					&& Now - StageStartedAtSeconds >= FinalFarBaselineSeconds)
				{
					ServerReciprocalFarBaseline =
						ServerView.TargetMesh->GetLastRenderTimeOnScreen();
					ClientReciprocalNearBaseline =
						ClientView.TargetMesh->GetLastRenderTimeOnScreen();
					bFarBaselineCaptured = true;
				}
				if (!bFarBaselineCaptured
					|| Now - StageStartedAtSeconds < FinalFarSampleSeconds)
				{
					return false;
				}

				FFrameGeometry ServerGeometry;
				FFrameGeometry ClientGeometry;
				const bool bServerGeometry =
					QueryFrameGeometry(
						Worlds.Server,
						Players.HostController,
						Players.HostPawn,
						ServerView,
						ServerGeometry);
				const bool bClientGeometry =
					QueryFrameGeometry(
						Worlds.Client,
						Players.RemoteClientController,
						Players.RemoteClientPawn,
						ClientView,
						ClientGeometry);
				const float ServerLast =
					ServerView.TargetMesh->GetLastRenderTimeOnScreen();
				const float ClientLast =
					ClientView.TargetMesh->GetLastRenderTimeOnScreen();
				const bool bPassed =
					bServerGeometry
					&& bClientGeometry
					&& FarGeometryPassed(ServerGeometry)
					&& NearGeometryPassed(ClientGeometry)
					&& ReferenceIsRendering(Worlds.Server, ServerView)
					&& ReferenceIsRendering(Worlds.Client, ClientView)
					&& !ServerView.TargetMesh->WasRecentlyRendered(
						RenderRecencySeconds)
					&& ClientView.TargetMesh->WasRecentlyRendered(
						RenderRecencySeconds)
					&& ServerLast <= ServerReciprocalFarBaseline + 0.1f
					&& ClientLast > ClientReciprocalNearBaseline + 0.2f
					&& ClientLast >= ClientReNearStartedWorldSeconds - 0.1f;
				if (!bPassed)
				{
					return false;
				}

				FString ServerWindowTitle;
				const FString ServerCapture = FPaths::Combine(
					CaptureDirectory,
					TEXT("DEF0003_Field_MP_Server_Far.png"));
				if (!CapturePIEWindow(
						TEXT("NetMode: Server 0"),
						ServerCapture,
						ServerWindowTitle))
				{
					return false;
				}

				UE_LOG(LogTemp, Display,
					TEXT("RED_DEF0003_FIELD_MP_CULL_SERVER_FAR pass=1 stableId=%s serverCenterCm=%.1f clientCenterCm=%.1f serverClosestCm=%.1f clientClosestCm=%.1f serverProjectedDiameterPx=%.1f clientProjectedDiameterPx=%.1f cullCm=%.1f netCullCm=%.1f serverLast=%.3f clientLast=%.3f serverBaseline=%.3f clientBaseline=%.3f targetRecent=0/1 referenceRecent=1/1 proxyRetained=1 traceExact=1/1 projected=1/1 serverCapture=\"%s\" serverWindow=\"%s\""),
					*TargetId.ToString(),
					ServerGeometry.CenterDistanceCm,
					ClientGeometry.CenterDistanceCm,
					ServerGeometry.ClosestBoundsDistanceCm,
					ClientGeometry.ClosestBoundsDistanceCm,
					ServerGeometry.ProjectedTargetDiameterPx,
					ClientGeometry.ProjectedTargetDiameterPx,
					TargetCullDistanceCm,
					ActualNetCullDistanceCm,
					ServerLast,
					ClientLast,
					ServerReciprocalFarBaseline,
					ClientReciprocalNearBaseline,
					*ServerCapture,
					*ServerWindowTitle.ReplaceCharWithEscapedChar());
				UE_LOG(LogTemp, Display,
					TEXT("RED_DEF0003_FIELD_MP_CULL_RESULT acceptancePass=1 evidenceClass=real_gpu_visual topology=in_process_two_client actualFieldMember=1 stableIdentity=1 reciprocalNearFarCull=1 cutoffOverridden=0 mining=0 playerControlledTravel=0 projectileDelivery=0 steamTransport=0"));
				AcceptanceState->bAccepted = true;
				Advance(EStage::Complete, Now);
				return true;
			}

			bool CreatePeerView(
				UWorld* World,
				ARedMineableAsteroid* Target,
				FPeerView& OutView)
			{
				if (!World || !Target)
				{
					return false;
				}
				UStaticMeshComponent* TargetMesh =
					Cast<UStaticMeshComponent>(Target->GetRootComponent());
				UStaticMesh* ReferenceAsset = LoadObject<UStaticMesh>(
					nullptr,
					TEXT("/Engine/BasicShapes/Cube.Cube"));
				if (!TargetMesh || !ReferenceAsset)
				{
					return false;
				}

				FActorSpawnParameters CameraParams;
				CameraParams.ObjectFlags |= RF_Transient;
				CameraParams.SpawnCollisionHandlingOverride =
					ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
				ACameraActor* Camera = World->SpawnActor<ACameraActor>(
					FVector::ZeroVector,
					FRotator::ZeroRotator,
					CameraParams);

				FActorSpawnParameters ReferenceParams;
				ReferenceParams.ObjectFlags |= RF_Transient;
				ReferenceParams.SpawnCollisionHandlingOverride =
					ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
				AStaticMeshActor* Reference =
					World->SpawnActor<AStaticMeshActor>(
						FVector::ZeroVector,
						FRotator::ZeroRotator,
						ReferenceParams);
				UStaticMeshComponent* ReferenceMesh =
					Reference ? Reference->GetStaticMeshComponent() : nullptr;
				if (!Camera || !Reference || !ReferenceMesh)
				{
					return false;
				}

				Camera->GetCameraComponent()->SetFieldOfView(52.f);
				Reference->SetReplicates(false);
				ReferenceMesh->SetMobility(EComponentMobility::Movable);
				ReferenceMesh->SetStaticMesh(ReferenceAsset);
				ReferenceMesh->SetCollisionEnabled(ECollisionEnabled::NoCollision);
				ReferenceMesh->SetGenerateOverlapEvents(false);
				ReferenceMesh->SetCastShadow(false);
				ReferenceMesh->SetCullDistance(0.f);
				Reference->SetActorScale3D(FVector(6.f));

				OutView.Target = Target;
				OutView.TargetMesh = TargetMesh;
				OutView.Camera = Camera;
				OutView.ReferenceActor = Reference;
				OutView.ReferenceMesh = ReferenceMesh;
				return true;
			}

			bool PositionPeerView(
				APlayerController* Controller,
				FPeerView& View,
				const float CenterDistanceCm)
			{
				ARedMineableAsteroid* Target = View.Target.Get();
				ACameraActor* Camera = View.Camera.Get();
				AStaticMeshActor* Reference = View.ReferenceActor.Get();
				if (!Controller || !Target || !Camera || !Reference)
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
				const FVector CameraLocation =
					BoundsOrigin + RadialOut * CenterDistanceCm;
				const FRotator CameraRotation =
					(BoundsOrigin - CameraLocation).Rotation();
				Camera->SetActorLocationAndRotation(
					CameraLocation,
					CameraRotation,
					false,
					nullptr,
					ETeleportType::TeleportPhysics);
				const FVector ReferenceLocation =
					CameraLocation
					+ Camera->GetActorForwardVector() * 20000.f
					+ Camera->GetActorRightVector() * 8000.f
					+ Camera->GetActorUpVector() * 5000.f;
				Reference->SetActorLocationAndRotation(
					ReferenceLocation,
					CameraRotation,
					false,
					nullptr,
					ETeleportType::TeleportPhysics);
				Controller->SetViewTarget(Camera);
				return Controller->GetViewTarget() == Camera;
			}

			bool PositionViews(
				const FPlayerPair& Players,
				const float CenterDistanceCm)
			{
				return PositionPeerView(
						Players.HostController,
						ServerView,
						CenterDistanceCm)
					&& PositionPeerView(
						Players.RemoteClientController,
						ClientView,
						CenterDistanceCm);
			}

			bool PinViews(const FPlayerPair& Players)
			{
				ACameraActor* ServerCamera = ServerView.Camera.Get();
				ACameraActor* ClientCamera = ClientView.Camera.Get();
				if (!Players.HostController
					|| !Players.RemoteClientController
					|| !ServerCamera
					|| !ClientCamera)
				{
					return false;
				}
				Players.HostController->SetViewTarget(ServerCamera);
				Players.RemoteClientController->SetViewTarget(ClientCamera);
				return Players.HostController->GetViewTarget() == ServerCamera
					&& Players.RemoteClientController->GetViewTarget()
						== ClientCamera;
			}

			bool ValidateActorContinuity(const FWorldPair& Worlds) const
			{
				ARedMineableAsteroid* AuthorityTarget = ServerTarget.Get();
				ARedMineableAsteroid* ProxyTarget = ClientTarget.Get();
				return AuthorityTarget
					&& ProxyTarget
					&& AuthorityTarget
						== FindUniqueStableMember(Worlds.Server, TargetId)
					&& ProxyTarget
						== FindUniqueStableMember(Worlds.Client, TargetId)
					&& TargetStateIsUnchanged(
						AuthorityTarget,
						TargetId,
						true)
					&& TargetStateIsUnchanged(
						ProxyTarget,
						TargetId,
						false)
					&& ProxyTarget->GetActorLocation().Equals(
						ServerTargetLocation,
						1.f)
					&& ProxyTarget->GetActorScale3D().Equals(
						ServerTargetScale,
						0.001f);
			}

			bool QueryFrameGeometry(
				UWorld* World,
				APlayerController* Controller,
				const AActor* Pawn,
				const FPeerView& View,
				FFrameGeometry& OutGeometry) const
			{
				ARedMineableAsteroid* Target = View.Target.Get();
				ACameraActor* Camera = View.Camera.Get();
				AStaticMeshActor* Reference = View.ReferenceActor.Get();
				if (!World
					|| !Controller
					|| !Target
					|| !Camera
					|| !Reference)
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
				OutGeometry.CenterDistanceCm =
					FVector::Distance(Camera->GetActorLocation(), BoundsOrigin);
				OutGeometry.BoundsRadiusCm = BoundsExtent.Size();
				OutGeometry.ClosestBoundsDistanceCm =
					FMath::Max(
						0.f,
						OutGeometry.CenterDistanceCm
							- OutGeometry.BoundsRadiusCm);
				Controller->GetViewportSize(
					OutGeometry.ViewportWidth,
					OutGeometry.ViewportHeight);
				OutGeometry.bTargetProjected =
					Controller->ProjectWorldLocationToScreen(
						BoundsOrigin,
						OutGeometry.TargetScreen,
						true);
				OutGeometry.bReferenceProjected =
					Controller->ProjectWorldLocationToScreen(
						Reference->GetActorLocation(),
						OutGeometry.ReferenceScreen,
						true);
				FVector2D TargetRadiusScreen = FVector2D::ZeroVector;
				const bool bTargetRadiusProjected =
					Controller->ProjectWorldLocationToScreen(
						BoundsOrigin
							+ Camera->GetActorRightVector()
								* OutGeometry.BoundsRadiusCm,
						TargetRadiusScreen,
						true);
				if (OutGeometry.bTargetProjected && bTargetRadiusProjected)
				{
					OutGeometry.ProjectedTargetDiameterPx =
						FVector2D::Distance(
							OutGeometry.TargetScreen,
							TargetRadiusScreen) * 2.f;
				}
				FVector ActualViewLocation;
				FRotator ActualViewRotation;
				Controller->GetPlayerViewPoint(
					ActualViewLocation,
					ActualViewRotation);
				OutGeometry.bViewMatches =
					ActualViewLocation.Equals(
						Camera->GetActorLocation(),
						10.f)
					&& ActualViewRotation.Equals(
						Camera->GetActorRotation(),
						0.1f);
				OutGeometry.bTargetCentered =
					OutGeometry.bTargetProjected
					&& FVector::DotProduct(
						Camera->GetActorForwardVector(),
						(BoundsOrigin - Camera->GetActorLocation())
							.GetSafeNormal()) >= 0.9999f;
				OutGeometry.bReferenceOnScreen =
					OutGeometry.bReferenceProjected
					&& OutGeometry.ReferenceScreen.X >= 0.f
					&& OutGeometry.ReferenceScreen.X
						< OutGeometry.ViewportWidth
					&& OutGeometry.ReferenceScreen.Y >= 0.f
					&& OutGeometry.ReferenceScreen.Y
						< OutGeometry.ViewportHeight;
				OutGeometry.bTraceExactTarget =
					TraceExactTarget(
						World,
						Camera->GetActorLocation(),
						BoundsOrigin,
						Target,
						Pawn,
						Reference);
				return OutGeometry.bViewMatches
					&& OutGeometry.bTargetCentered
					&& OutGeometry.bReferenceOnScreen
					&& OutGeometry.ProjectedTargetDiameterPx >= 8.f
					&& OutGeometry.bTraceExactTarget;
			}

			bool NearGeometryPassed(const FFrameGeometry& Geometry) const
			{
				return FMath::IsNearlyEqual(
						Geometry.CenterDistanceCm,
						NearCenterDistanceCm,
						100.f)
					&& Geometry.ClosestBoundsDistanceCm
						< TargetCullDistanceCm * 0.5f;
			}

			bool FarGeometryPassed(const FFrameGeometry& Geometry) const
			{
				return FMath::IsNearlyEqual(
						Geometry.CenterDistanceCm,
						FarCenterDistanceCm,
						100.f)
					&& Geometry.ClosestBoundsDistanceCm
						> TargetCullDistanceCm * 1.05f
					&& Geometry.CenterDistanceCm
						< ActualNetCullDistanceCm * 0.9f;
			}

			bool ReferenceIsRendering(
				UWorld* World,
				const FPeerView& View) const
			{
				const UStaticMeshComponent* ReferenceMesh =
					View.ReferenceMesh.Get();
				return World
					&& ReferenceMesh
					&& ReferenceMesh->GetWorld() == World
					&& ReferenceMesh->IsRegistered()
					&& ReferenceMesh->IsVisible()
					&& ReferenceMesh->WasRecentlyRendered(
						RenderRecencySeconds)
					&& ReferenceMesh->GetLastRenderTimeOnScreen()
						>= World->GetTimeSeconds()
							- RenderRecencySeconds - 0.1f;
			}

			FAutomationTestBase* Test = nullptr;
			TSharedRef<FAcceptanceState> AcceptanceState;
			EStage Stage = EStage::AwaitTopology;
			double StartedAtSeconds = 0.0;
			double StageStartedAtSeconds = 0.0;
			double LastDiagnosticAtSeconds = 0.0;
			bool bFarBaselineCaptured = false;
			float ViewDistanceScale = -1.f;
			float ActualNetCullDistanceCm = 0.f;
			float InitialFarServerBaseline = 0.f;
			float InitialFarClientBaseline = 0.f;
			float ServerNearStartedWorldSeconds = 0.f;
			float ClientNearStartedWorldSeconds = 0.f;
			float FinalFarServerBaseline = 0.f;
			float FinalFarClientBaseline = 0.f;
			float ClientReNearStartedWorldSeconds = 0.f;
			float ServerReciprocalFarBaseline = 0.f;
			float ClientReciprocalNearBaseline = 0.f;
			FName TargetId = NAME_None;
			FString CaptureDirectory;
			FVector RadialOut = FVector::ZeroVector;
			FVector ServerTargetLocation = FVector::ZeroVector;
			FQuat ServerTargetRotation = FQuat::Identity;
			FVector ServerTargetScale = FVector::OneVector;
			FVector RemotePawnHoldLocation = FVector::ZeroVector;
			TWeakObjectPtr<ARedMineableAsteroid> ServerTarget;
			TWeakObjectPtr<ARedMineableAsteroid> ClientTarget;
			FPeerView ServerView;
			FPeerView ClientView;
		};

		class FWaitForPIEEndCommand final : public IAutomationLatentCommand
		{
		public:
			FWaitForPIEEndCommand(
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
					UE_LOG(LogTemp, Display,
						TEXT("RED_DEF0003_FIELD_MP_CULL_COMPLETE pieEnded=1 acceptancePass=%d"),
						AcceptanceState->bAccepted ? 1 : 0);
					return true;
				}
				if (FPlatformTime::Seconds() - StartedAtSeconds > 15.0)
				{
					Test->AddError(TEXT(
						"DEF-0003 actual-field two-client cull PIE did not end within 15 seconds."));
					return true;
				}
				return false;
			}

		private:
			FAutomationTestBase* Test = nullptr;
			TSharedRef<FAcceptanceState> AcceptanceState;
			double StartedAtSeconds = 0.0;
		};
	}

	IMPLEMENT_SIMPLE_AUTOMATION_TEST(
		FRedDEF0003ActualFieldTwoClientCullPIETest,
		"RedMMO.Mining.DEF0003.ActualFieldTwoClientCullPIE",
		EAutomationTestFlags::EditorContext | EAutomationTestFlags::ProductFilter)

	bool FRedDEF0003ActualFieldTwoClientCullPIETest::RunTest(
		const FString& Parameters)
	{
		(void)Parameters;
		if (!FApp::CanEverRender()
			|| FParse::Param(FCommandLine::Get(), TEXT("nullrhi")))
		{
			AddError(TEXT(
				"DEF-0003 actual-field two-client cull acceptance requires a rendered non-NullRHI editor."));
			return false;
		}
		if (Private::ResolvePIEWorlds().PIEWorldCount != 0)
		{
			AddError(TEXT("A PIE session is already running."));
			return false;
		}

		ULevelEditorPlaySettings* PlaySettings =
			NewObject<ULevelEditorPlaySettings>(GetTransientPackage());
		if (!PlaySettings)
		{
			AddError(TEXT("Could not allocate transient PIE settings."));
			return false;
		}
		PlaySettings->SetPlayNetMode(EPlayNetMode::PIE_ListenServer);
		PlaySettings->SetPlayNumberOfClients(2);
		PlaySettings->SetRunUnderOneProcess(true);
		PlaySettings->bLaunchSeparateServer = false;
		PlaySettings->GameGetsMouseControl = false;
		PlaySettings->bShouldMinimizeEditorOnNonVRPIE = false;
		PlaySettings->PIEAlwaysOnTop = false;
		PlaySettings->NewWindowWidth = 1280;
		PlaySettings->NewWindowHeight = 720;
		PlaySettings->AddToRoot();

		FRequestPlaySessionParams RequestParams;
		RequestParams.WorldType = EPlaySessionWorldType::PlayInEditor;
		RequestParams.EditorPlaySettings = PlaySettings;
		RequestParams.GlobalMapOverride = Private::ProductionMap;
		RequestParams.bAllowOnlineSubsystem = false;

		const TSharedRef<Private::FAcceptanceState> AcceptanceState =
			MakeShared<Private::FAcceptanceState>();
		ADD_LATENT_AUTOMATION_COMMAND(
			FEditorLoadMap(Private::ProductionMap));
		ADD_LATENT_AUTOMATION_COMMAND(FWaitForShadersToFinishCompiling());
		ADD_LATENT_AUTOMATION_COMMAND(
			FStartPIEForAutomationCommand(RequestParams));
		ADD_LATENT_AUTOMATION_COMMAND(
			Private::FActualFieldTwoClientCullCommand(
				this,
				AcceptanceState));
		ADD_LATENT_AUTOMATION_COMMAND(FEndPlayMapCommand());
		ADD_LATENT_AUTOMATION_COMMAND(
			Private::FWaitForPIEEndCommand(
				this,
				AcceptanceState));
		return true;
	}
}

#endif // WITH_DEV_AUTOMATION_TESTS && WITH_EDITOR
