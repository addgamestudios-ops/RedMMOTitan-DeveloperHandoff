#include "../RedHUD.h"
#include "../RedGravityBodies.h"
#include "../RedMineableAsteroid.h"
#include "../RedPlanetPresentationTuning.h"
#include "../RedPlayerCharacter.h"
#include "../RedResourcePickup.h"
#include "../RedShipExplosionFX.h"

#if WITH_DEV_AUTOMATION_TESTS && WITH_EDITOR

#include "Camera/CameraActor.h"
#include "Camera/CameraComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Editor.h"
#include "Engine/Engine.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "Framework/Application/SlateApplication.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/PlayerController.h"
#include "GameFramework/PlayerState.h"
#include "HAL/FileManager.h"
#include "HAL/PlatformProcess.h"
#include "HAL/PlatformTime.h"
#include "ImageUtils.h"
#include "Kismet/GameplayStatics.h"
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

namespace RedMMO::DEF0003TwoClientPIE
{
	namespace Private
	{
		constexpr TCHAR ProductionMap[] = TEXT("/Game/RedMMO/Maps/RedPlanetGen");
		constexpr double TopologyTimeoutSeconds = 45.0;
		constexpr double StageTimeoutSeconds = 20.0;
		constexpr float MiningResultLifetimeSeconds = 3.25f;
		constexpr float RemotePawnTargetDistanceCm = 100000.f;

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

		struct FExplosionStats
		{
			int32 Count = 0;
			int32 SimulatingDebris = 0;
		};

		struct FProductionFieldStats
		{
			int32 Count = 0;
			int32 Pristine = 0;
			float MinimumAltitudeCm = TNumericLimits<float>::Max();
			float MaximumAltitudeCm = TNumericLimits<float>::Lowest();
			bool bPlanetFrameResolved = false;
			bool bContractPassed = true;
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

			for (FConstPlayerControllerIterator It = ServerWorld->GetPlayerControllerIterator(); It; ++It)
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

			for (FConstPlayerControllerIterator It = ClientWorld->GetPlayerControllerIterator(); It; ++It)
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
			if (!Players.RemoteServerController || !Players.RemoteClientController
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

		ARedMineableAsteroid* FindUniqueAuditAsteroid(UWorld* World)
		{
			ARedMineableAsteroid* Result = nullptr;
			int32 MatchCount = 0;
			for (TActorIterator<ARedMineableAsteroid> It(World); It; ++It)
			{
				ARedMineableAsteroid* Asteroid = *It;
				if (!IsValid(Asteroid) || !FMath::IsNearlyEqual(Asteroid->OreCapacity, 18.f))
				{
					continue;
				}
				Result = Asteroid;
				++MatchCount;
			}
			return MatchCount == 1 ? Result : nullptr;
		}

		int32 CountReceipts(UWorld* World, ARedMineableAsteroid* ExpectedOwner)
		{
			int32 Count = 0;
			for (TActorIterator<ARedResourcePickup> It(World); It; ++It)
			{
				ARedResourcePickup* Receipt = *It;
				if (IsValid(Receipt) && Receipt->GetOwner() == ExpectedOwner
					&& Receipt->ResourceType == ERedResourceType::Iron
					&& Receipt->Amount == 6 && !Receipt->bCollectible)
				{
					++Count;
				}
			}
			return Count;
		}

		FExplosionStats GetExplosionStats(
			UWorld* World, ARedMineableAsteroid* ExpectedOwner)
		{
			FExplosionStats Result;
			for (TActorIterator<ARedShipExplosionFX> It(World); It; ++It)
			{
				ARedShipExplosionFX* Explosion = *It;
				if (!IsValid(Explosion) || Explosion->GetOwner() != ExpectedOwner)
				{
					continue;
				}

				++Result.Count;
				TArray<UStaticMeshComponent*> Components;
				Explosion->GetComponents<UStaticMeshComponent>(Components);
				for (const UStaticMeshComponent* Component : Components)
				{
					if (Component && Component->IsSimulatingPhysics())
					{
						++Result.SimulatingDebris;
					}
				}
			}
			return Result;
		}

		FProductionFieldStats GetProductionFieldStats(UWorld* World)
		{
			FProductionFieldStats Result;
			if (!World)
			{
				Result.bContractPassed = false;
				return Result;
			}

			FVector PlanetCenter = FVector::ZeroVector;
			float DatumRadius = 0.f;
			float PeakRadius = 0.f;
			Result.bPlanetFrameResolved = RedGravity::FindMeshPlanet(
				World, PlanetCenter, DatumRadius, &PeakRadius)
				&& DatumRadius > 0.f && PeakRadius >= DatumRadius;
			if (!Result.bPlanetFrameResolved)
			{
				Result.bContractPassed = false;
				return Result;
			}
			const float SurfaceRadius = (DatumRadius + PeakRadius) * 0.5f;

			TSet<FName> StableIds;
			for (TActorIterator<ARedMineableAsteroid> It(World); It; ++It)
			{
				const ARedMineableAsteroid* Asteroid = *It;
				if (!IsValid(Asteroid)
					|| !Asteroid->ActorHasTag(TEXT("RedMarsMineableBelt")))
				{
					continue;
				}

				++Result.Count;
				const float AltitudeCm =
					FVector::Distance(Asteroid->GetActorLocation(), PlanetCenter)
						- SurfaceRadius;
				Result.MinimumAltitudeCm =
					FMath::Min(Result.MinimumAltitudeCm, AltitudeCm);
				Result.MaximumAltitudeCm =
					FMath::Max(Result.MaximumAltitudeCm, AltitudeCm);
				const FName StableId = Asteroid->GetStableMemberId();
				const bool bIdentityPassed =
					!StableId.IsNone() && !StableIds.Contains(StableId);
				if (bIdentityPassed)
				{
					StableIds.Add(StableId);
				}
				const bool bMemberPassed = bIdentityPassed
					&& AltitudeCm
						>= RedPlanetPresentationTuning::DeepSpaceAsteroidInnerAltitudeCm
							- 1.f
					&& AltitudeCm
						<= RedPlanetPresentationTuning::DeepSpaceAsteroidOuterAltitudeCm
							+ 1.f
					&& FMath::IsNearlyEqual(
						Asteroid->GetPresentationCullDistance(),
						RedPlanetPresentationTuning::AsteroidRenderCullDistanceCm,
						1.f)
					&& Asteroid->DepletionState.Phase
						== ERedMineableAsteroidDepletionPhase::Active
					&& FMath::IsNearlyEqual(
						Asteroid->OreRemaining, Asteroid->OreCapacity);
				Result.bContractPassed &= bMemberPassed;
				if (bMemberPassed)
				{
					++Result.Pristine;
				}
			}
			Result.bContractPassed &=
				Result.Count == 24 && Result.Pristine == 24
				&& StableIds.Num() == 24;
			return Result;
		}

		bool QueryPlayerHUD(
			const APlayerController* Controller,
			const ARedPlayerCharacter* Pawn,
			const int32 ExpectedAmount,
			FString& OutText,
			bool& bOutVisible,
			float& OutSecondsRemaining)
		{
			OutText.Reset();
			bOutVisible = false;
			OutSecondsRemaining = 0.0f;
			if (!Controller || !Pawn)
			{
				return false;
			}

			const ARedHUD* HUD =
				Cast<ARedHUD>(Controller->GetHUD());
			if (!HUD)
			{
				return false;
			}

			FString InventoryText;
			bool bPersistentTallyVisible = true;
			const bool bInventoryCachePassed =
				HUD->QueryReplacementHUDResources(
					Pawn->ResStone,
					Pawn->ResIron,
					Pawn->ResCrystal,
					InventoryText,
					bPersistentTallyVisible)
				&& InventoryText.IsEmpty()
				&& !bPersistentTallyVisible;
			return bInventoryCachePassed
				&& HUD->QueryReplacementHUDMiningResult(
					static_cast<uint8>(ERedResourceType::Iron),
					ExpectedAmount,
					OutText,
					bOutVisible,
					OutSecondsRemaining);
		}

		bool QueryRemoteHUD(
			const FPlayerPair& Players,
			const int32 ExpectedAmount,
			FString& OutText,
			bool& bOutVisible,
			float& OutSecondsRemaining)
		{
			return QueryPlayerHUD(
				Players.RemoteClientController,
				Players.RemoteClientPawn,
				ExpectedAmount,
				OutText,
				bOutVisible,
				OutSecondsRemaining);
		}

		bool QueryHostHUD(
			const FPlayerPair& Players,
			const int32 ExpectedAmount,
			FString& OutText,
			bool& bOutVisible,
			float& OutSecondsRemaining)
		{
			return QueryPlayerHUD(
				Players.HostController,
				Players.HostPawn,
				ExpectedAmount,
				OutText,
				bOutVisible,
				OutSecondsRemaining);
		}

		bool CaptureRemoteClientWindow(
			const FString& Filename, FString& OutWindowTitle)
		{
			OutWindowTitle.Reset();
			if (!FSlateApplication::IsInitialized())
			{
				return false;
			}

			TSharedPtr<SWindow> RemoteWindow;
			for (const TSharedRef<SWindow>& Window :
				FSlateApplication::Get().GetTopLevelWindows())
			{
				const FString Title = Window->GetTitle().ToString();
				if (Title.Contains(TEXT("NetMode: Client 1")))
				{
					RemoteWindow = Window;
					OutWindowTitle = Title;
					break;
				}
			}
			if (!RemoteWindow.IsValid())
			{
				return false;
			}

			TArray<FColor> Pixels;
			FIntVector Size = FIntVector::ZeroValue;
			if (!FSlateApplication::Get().TakeScreenshot(
					RemoteWindow.ToSharedRef(), Pixels, Size)
				|| Size.X <= 0 || Size.Y <= 0
				|| Pixels.Num() < Size.X * Size.Y)
			{
				return false;
			}

			IFileManager::Get().MakeDirectory(*FPaths::GetPath(Filename), true);
			TArray64<uint8> PNG;
			FImageUtils::PNGCompressImageArray(
				Size.X, Size.Y,
				TArrayView64<const FColor>(Pixels.GetData(), Pixels.Num()), PNG);
			return PNG.Num() > 0 && FFileHelper::SaveArrayToFile(PNG, *Filename);
		}

		class FTwoClientAcceptanceCommand final : public IAutomationLatentCommand
		{
		public:
			FTwoClientAcceptanceCommand(
				FAutomationTestBase* InTest,
				TSharedRef<FAcceptanceState> InAcceptanceState)
				: Test(InTest)
				, AcceptanceState(MoveTemp(InAcceptanceState))
			{
				FParse::Value(
					FCommandLine::Get(), TEXT("RedDEF0003MPCaptureDir="),
					CaptureDirectory);
				if (CaptureDirectory.IsEmpty())
				{
					CaptureDirectory = FPaths::Combine(
						FPaths::ProjectSavedDir(),
						TEXT("Automation/DEF0003TwoClientPIE"));
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
				case EStage::AwaitProxy:
					return AwaitProxy(Worlds, Players, Now);
				case EStage::SubmitHits:
					return SubmitHits(Worlds, Players);
				case EStage::AwaitTransition:
					return AwaitTransition(Worlds, Players, Now);
				case EStage::AwaitFinal:
					return AwaitFinal(Worlds, Players, Now);
				case EStage::AwaitReceiptExpiry:
					return AwaitReceiptExpiry(Worlds, Players, Now);
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
				AwaitProxy,
				SubmitHits,
				AwaitTransition,
				AwaitFinal,
				AwaitReceiptExpiry,
				Complete
			};

			bool Fail(const FString& Reason)
			{
				Test->AddError(FString::Printf(
					TEXT("DEF-0003 two-client PIE acceptance failed: %s"),
					*Reason));
				UE_LOG(LogTemp, Error,
					TEXT("RED_DEF0003_MP_RESULT acceptancePass=0 reason=\"%s\""),
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
			}

			bool AwaitTopology(
				const FWorldPair& Worlds, const FPlayerPair& Players,
				const double Now)
			{
				if (Now - StartedAtSeconds > TopologyTimeoutSeconds)
				{
					return Fail(FString::Printf(
						TEXT("topology timeout pieWorlds=%d listen=%d clients=%d serverPlayers=%d"),
						Worlds.PIEWorldCount, Worlds.ListenServerCount,
						Worlds.ClientCount, Players.ServerPlayerCount));
				}

				FString RemoteHUDText;
				bool bRemoteHUDVisible = false;
				float RemoteHUDSeconds = 0.0f;
				const bool bRemoteHUDReady =
					QueryRemoteHUD(
						Players, 0, RemoteHUDText,
						bRemoteHUDVisible, RemoteHUDSeconds)
					&& !bRemoteHUDVisible
					&& RemoteHUDSeconds <= 0.0f;
				FString HostHUDText;
				bool bHostHUDVisible = false;
				float HostHUDSeconds = 0.0f;
				const bool bHostHUDReady =
					QueryHostHUD(
						Players, 0, HostHUDText,
						bHostHUDVisible, HostHUDSeconds)
					&& !bHostHUDVisible
					&& HostHUDSeconds <= 0.0f;
				const FProductionFieldStats ProductionStats =
					GetProductionFieldStats(Worlds.Server);
				if (Worlds.PIEWorldCount != 2 || Worlds.ListenServerCount != 1
					|| Worlds.ClientCount != 1 || Players.ServerPlayerCount != 2
					|| !Players.HostPawn || !Players.RemoteServerPawn
					|| !Players.RemoteClientPawn || !PlayerIdentitiesMatch(Players)
					|| !bRemoteHUDReady || !bHostHUDReady
					|| !ProductionStats.bContractPassed)
				{
					return false;
				}

				InitialHostIron = Players.HostPawn->ResIron;
				InitialRemoteIron = Players.RemoteServerPawn->ResIron;
				RemotePlayerId =
					Players.RemoteServerController->PlayerState->GetPlayerId();

				FVector PlanetCenter = FVector::ZeroVector;
				float DatumRadius = 0.f;
				float PeakRadius = 0.f;
				if (!RedGravity::FindMeshPlanet(
						Worlds.Server, PlanetCenter, DatumRadius, &PeakRadius)
					|| DatumRadius <= 0.f || PeakRadius < DatumRadius)
				{
					return Fail(TEXT("authority planet frame could not be resolved"));
				}
				const float SurfaceRadius = (DatumRadius + PeakRadius) * 0.5f;
				FVector Up =
					(Players.RemoteServerPawn->GetActorLocation() - PlanetCenter)
						.GetSafeNormal();
				if (Up.IsNearlyZero())
				{
					Up =
						Players.RemoteServerPawn->GetActorUpVector().GetSafeNormal();
				}
				if (Up.IsNearlyZero())
				{
					Up = FVector::UpVector;
				}
				FVector Forward = FVector::VectorPlaneProject(
					Players.RemoteServerPawn->GetActorForwardVector(), Up).GetSafeNormal();
				if (Forward.IsNearlyZero())
				{
					FVector Unused;
					Up.FindBestAxisVectors(Forward, Unused);
				}

				const float TargetAltitudeCm =
					(RedPlanetPresentationTuning::DeepSpaceAsteroidInnerAltitudeCm
						+ RedPlanetPresentationTuning::DeepSpaceAsteroidOuterAltitudeCm)
					* 0.5f;
				const FVector AsteroidLocation =
					PlanetCenter + Up * (SurfaceRadius + TargetAltitudeCm);
				const FVector HoldLocation =
					AsteroidLocation - Forward * RemotePawnTargetDistanceCm;
				const FRotator HoldRotation =
					(AsteroidLocation - HoldLocation).Rotation();
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
				ExpectedRemotePawnLocation = HoldLocation;

				const FTransform Transform(
					HoldRotation, AsteroidLocation, FVector::OneVector);
				ARedMineableAsteroid* Asteroid =
					Worlds.Server->SpawnActorDeferred<ARedMineableAsteroid>(
						ARedMineableAsteroid::StaticClass(), Transform,
						Players.RemoteServerPawn, Players.RemoteServerPawn,
						ESpawnActorCollisionHandlingMethod::AlwaysSpawn);
				if (!Asteroid)
				{
					return Fail(TEXT("authority asteroid spawn failed"));
				}

				Asteroid->SetFlags(RF_Transient);
				Asteroid->Tags.Add(TEXT("RedDEF0003TwoClientAuditAsteroid"));
				Asteroid->OreCapacity = 18.f;
				Asteroid->DepletionPresentationSeconds = 2.f;
				Asteroid->DepletionRewardType = ERedResourceType::Iron;
				Asteroid->DepletionRewardAmount = 6;
				UGameplayStatics::FinishSpawningActor(Asteroid, Transform);
				Asteroid->SetActorScale3D(FVector::OneVector);
				Asteroid->SetPresentationCullDistance(
					RedPlanetPresentationTuning::AsteroidRenderCullDistanceCm);
				Asteroid->ForceNetUpdate();
				const float TargetAltitudeMeasuredCm =
					FVector::Distance(Asteroid->GetActorLocation(), PlanetCenter)
						- SurfaceRadius;
				const bool bDeepSpaceSetupPassed =
					Asteroid->GetActorScale3D().Equals(FVector::OneVector, 0.001f)
					&& FMath::IsNearlyEqual(
						Asteroid->GetPresentationCullDistance(),
						RedPlanetPresentationTuning::AsteroidRenderCullDistanceCm,
						1.f)
					&& TargetAltitudeMeasuredCm
						>= RedPlanetPresentationTuning::DeepSpaceAsteroidInnerAltitudeCm
							- 1.f
					&& TargetAltitudeMeasuredCm
						<= RedPlanetPresentationTuning::DeepSpaceAsteroidOuterAltitudeCm
							+ 1.f
					&& TargetAltitudeMeasuredCm
						>= RedPlanetPresentationTuning::SpaceTransitionAltitudeCm
					&& !Asteroid->ActorHasTag(TEXT("RedMarsMineableBelt"));
				if (!bDeepSpaceSetupPassed)
				{
					return Fail(TEXT("deep-space authority target contract failed"));
				}
				ServerAsteroid = Asteroid;

				UE_LOG(LogTemp, Display,
					TEXT("RED_DEF0003_MP_TOPOLOGY pass=1 pid=%u pieWorlds=%d listen=%d clients=%d serverPlayers=%d remotePlayerId=%d hostRole=%d remoteServerRole=%d remoteClientRole=%d"),
					FPlatformProcess::GetCurrentProcessId(),
					Worlds.PIEWorldCount, Worlds.ListenServerCount,
					Worlds.ClientCount, Players.ServerPlayerCount,
					RemotePlayerId,
					static_cast<int32>(Players.HostPawn->GetLocalRole()),
					static_cast<int32>(Players.RemoteServerPawn->GetLocalRole()),
					static_cast<int32>(Players.RemoteClientPawn->GetLocalRole()));
				UE_LOG(LogTemp, Display,
					TEXT("RED_DEF0003_MP_DEEP_SPACE_SETUP pass=1 deepSpace=1 atmosphericTarget=0 targetAltitudeKm=%.3f spaceTransitionKm=%.3f pawnDistanceKm=%.3f productionField=%d pristineProduction=%d minimumFieldAltitudeKm=%.3f maximumFieldAltitudeKm=%.3f cullKm=%.3f scaleOverridden=0 cutoffOverridden=0 staticMesh=%s voxel=0"),
					TargetAltitudeMeasuredCm * 0.00001f,
					RedPlanetPresentationTuning::SpaceTransitionAltitudeCm * 0.00001f,
					FVector::Distance(HoldLocation, AsteroidLocation) * 0.00001f,
					ProductionStats.Count,
					ProductionStats.Pristine,
					ProductionStats.MinimumAltitudeCm * 0.00001f,
					ProductionStats.MaximumAltitudeCm * 0.00001f,
					RedPlanetPresentationTuning::AsteroidRenderCullDistanceCm
						* 0.00001f,
					*GetNameSafe(
						Asteroid->FindComponentByClass<UStaticMeshComponent>()
							? Asteroid->FindComponentByClass<UStaticMeshComponent>()
								->GetStaticMesh()
							: nullptr));
				Advance(EStage::AwaitProxy, Now);
				return false;
			}

			bool AwaitProxy(
				const FWorldPair& Worlds, const FPlayerPair& Players,
				const double Now)
			{
				if (StageTimedOut(Now))
				{
					return Fail(TEXT("client asteroid proxy or remote framing timeout"));
				}
				ARedMineableAsteroid* AuthorityAsteroid = ServerAsteroid.Get();
				ARedMineableAsteroid* ProxyAsteroid =
					Worlds.Client ? FindUniqueAuditAsteroid(Worlds.Client) : nullptr;
				if (!AuthorityAsteroid || !ProxyAsteroid
					|| !Players.RemoteClientController
					|| !Players.RemoteClientPawn
					|| FVector::Distance(
						Players.RemoteClientPawn->GetActorLocation(),
						ExpectedRemotePawnLocation) > 1000.f)
				{
					return false;
				}

				if (!RemoteCamera.IsValid())
				{
					FVector PlanetCenter = FVector::ZeroVector;
					float DatumRadius = 0.f;
					float PeakRadius = 0.f;
					if (!RedGravity::FindMeshPlanet(
							Worlds.Client, PlanetCenter, DatumRadius, &PeakRadius)
						|| DatumRadius <= 0.f || PeakRadius < DatumRadius)
					{
						return Fail(TEXT("client planet frame could not be resolved"));
					}
					const float SurfaceRadius =
						(DatumRadius + PeakRadius) * 0.5f;
					FVector BoundsOrigin;
					FVector BoundsExtent;
					ProxyAsteroid->GetActorBounds(
						false, BoundsOrigin, BoundsExtent, true);
					FVector Up = (BoundsOrigin - PlanetCenter).GetSafeNormal();
					if (Up.IsNearlyZero())
					{
						Up = FVector::UpVector;
					}
					FVector Forward =
						(BoundsOrigin - Players.RemoteClientPawn->GetActorLocation())
							.GetSafeNormal();
					Forward =
						FVector::VectorPlaneProject(Forward, Up).GetSafeNormal();
					if (Forward.IsNearlyZero())
					{
						FVector Unused;
						Up.FindBestAxisVectors(Forward, Unused);
					}
					const float FramingRadius =
						FMath::Max(1.f, BoundsExtent.Size());
					const float FramingDistance = FMath::Clamp(
						FramingRadius * 10.f,
						35000.f,
						RedPlanetPresentationTuning::AsteroidRenderCullDistanceCm
							* 0.25f);
					const FVector CameraLocation =
						BoundsOrigin - Forward * FramingDistance
							+ Up * (FramingRadius * 0.20f);
					const FRotator CameraRotation =
						(BoundsOrigin - CameraLocation).Rotation();
					const float TargetAltitudeCm =
						FVector::Distance(BoundsOrigin, PlanetCenter) - SurfaceRadius;
					const float CameraAltitudeCm =
						FVector::Distance(CameraLocation, PlanetCenter) - SurfaceRadius;
					const float CameraDistanceCm =
						FVector::Distance(CameraLocation, BoundsOrigin);
					const float AngularDiameterDegrees = FMath::RadiansToDegrees(
						2.f * FMath::Atan2(
							FramingRadius, CameraDistanceCm));
					const bool bFramingPassed =
						ProxyAsteroid->GetActorScale3D().Equals(
							FVector::OneVector, 0.001f)
						&& FMath::IsNearlyEqual(
							AuthorityAsteroid->GetPresentationCullDistance(),
							RedPlanetPresentationTuning::AsteroidRenderCullDistanceCm,
							1.f)
						&& FMath::IsNearlyEqual(
							ProxyAsteroid->GetPresentationCullDistance(),
							RedPlanetPresentationTuning::AsteroidRenderCullDistanceCm,
							1.f)
						&& TargetAltitudeCm
							>= RedPlanetPresentationTuning::DeepSpaceAsteroidInnerAltitudeCm
								- 1.f
						&& TargetAltitudeCm
							<= RedPlanetPresentationTuning::DeepSpaceAsteroidOuterAltitudeCm
								+ 1.f
						&& CameraAltitudeCm
							>= RedPlanetPresentationTuning::SpaceTransitionAltitudeCm
						&& CameraDistanceCm
							< RedPlanetPresentationTuning::AsteroidRenderCullDistanceCm
						&& AngularDiameterDegrees >= 3.f
						&& AngularDiameterDegrees <= 14.f;
					if (!bFramingPassed)
					{
						return Fail(TEXT("remote deep-space framing contract failed"));
					}

					FActorSpawnParameters CameraParameters;
					CameraParameters.ObjectFlags |= RF_Transient;
					ACameraActor* Camera = Worlds.Client->SpawnActor<ACameraActor>(
						CameraLocation, CameraRotation, CameraParameters);
					if (!Camera)
					{
						return Fail(TEXT("remote client camera spawn failed"));
					}
					Camera->GetCameraComponent()->SetFieldOfView(52.f);
					Players.RemoteClientController->SetViewTarget(Camera);
					RemoteCamera = Camera;
					ClientAsteroid = ProxyAsteroid;
					DeepSpaceTargetAltitudeCm = TargetAltitudeCm;
					DeepSpaceCameraAltitudeCm = CameraAltitudeCm;
					DeepSpaceCameraDistanceCm = CameraDistanceCm;
					DeepSpaceAngularDiameterDegrees = AngularDiameterDegrees;
					CameraReadyAtSeconds = Now;
					return false;
				}

				// The gameplay camera can reclaim the view target on a later tick.
				// Pin it throughout the acceptance stages so the screenshot is
				// evidence of the asteroid state rather than merely the client HUD.
				Players.RemoteClientController->SetViewTarget(RemoteCamera.Get());
				if (Players.RemoteClientController->GetViewTarget() != RemoteCamera.Get())
				{
					return false;
				}

				if (Now - CameraReadyAtSeconds < 0.35)
				{
					return false;
				}

				FCollisionQueryParams QueryParams(
					SCENE_QUERY_STAT(RedDEF0003MPBeforeTrace),
					false,
					Players.RemoteClientPawn);
				FHitResult Hit;
				const FVector TraceStart = RemoteCamera->GetActorLocation();
				const FVector TraceDirection =
					(ProxyAsteroid->GetActorLocation() - TraceStart).GetSafeNormal();
				const bool bTraceHit = Worlds.Client->LineTraceSingleByChannel(
					Hit,
					TraceStart,
					ProxyAsteroid->GetActorLocation()
						+ TraceDirection * 2500.f,
					ECC_Visibility,
					QueryParams);
				const bool bTraceExact =
					bTraceHit && Hit.GetActor() == ProxyAsteroid;
				const bool bRecentlyRendered =
					ProxyAsteroid->WasRecentlyRendered(1.0f);
				const bool bBeforePassed =
					AuthorityAsteroid->DepletionState.Phase
						== ERedMineableAsteroidDepletionPhase::Active
					&& ProxyAsteroid->DepletionState.Phase
						== ERedMineableAsteroidDepletionPhase::Active
					&& AuthorityAsteroid->GetActorEnableCollision()
					&& ProxyAsteroid->GetActorEnableCollision()
					&& !AuthorityAsteroid->IsHidden()
					&& !ProxyAsteroid->IsHidden()
					&& bTraceExact
					&& bRecentlyRendered;
				if (!bBeforePassed)
				{
					return false;
				}

				FString WindowTitle;
				const FString Filename = FPaths::Combine(
					CaptureDirectory,
					TEXT("DEF0003_MP_Remote_SpaceBefore.png"));
				if (!CaptureRemoteClientWindow(Filename, WindowTitle))
				{
					return false;
				}

				UE_LOG(LogTemp, Display,
					TEXT("RED_DEF0003_MP_BEFORE pass=1 deepSpace=1 serverPhase=%d clientPhase=%d collision=%d/%d hidden=%d/%d traceExact=%d recentlyRendered=%d targetAltitudeKm=%.3f cameraAltitudeKm=%.3f cameraDistanceKm=%.3f angularDiameterDeg=%.2f capture=\"%s\" window=\"%s\""),
					static_cast<int32>(AuthorityAsteroid->DepletionState.Phase),
					static_cast<int32>(ProxyAsteroid->DepletionState.Phase),
					AuthorityAsteroid->GetActorEnableCollision() ? 1 : 0,
					ProxyAsteroid->GetActorEnableCollision() ? 1 : 0,
					AuthorityAsteroid->IsHidden() ? 1 : 0,
					ProxyAsteroid->IsHidden() ? 1 : 0,
					bTraceExact ? 1 : 0,
					bRecentlyRendered ? 1 : 0,
					DeepSpaceTargetAltitudeCm * 0.00001f,
					DeepSpaceCameraAltitudeCm * 0.00001f,
					DeepSpaceCameraDistanceCm * 0.00001f,
					DeepSpaceAngularDiameterDegrees,
					*Filename, *WindowTitle.ReplaceCharWithEscapedChar());
				Advance(EStage::SubmitHits, Now);
				return false;
			}

			bool SubmitHits(
				const FWorldPair& Worlds, const FPlayerPair& Players)
			{
				ARedMineableAsteroid* Asteroid = ServerAsteroid.Get();
				if (!Worlds.Server || !Asteroid || !Players.HostPawn
					|| !Players.RemoteServerPawn || !PlayerIdentitiesMatch(Players))
				{
					return Fail(TEXT("players or authority asteroid invalid at hit barrier"));
				}

				const uint64 FrameBefore = GFrameCounter;
				const float RemoteExtracted =
					Asteroid->RegisterMiningHit(1.f, Players.RemoteServerPawn);
				const float HostRejected =
					Asteroid->RegisterMiningHit(1.f, Players.HostPawn);
				const uint64 FrameAfter = GFrameCounter;
				const int32 HostDelta =
					Players.HostPawn->ResIron - InitialHostIron;
				const int32 RemoteDelta =
					Players.RemoteServerPawn->ResIron - InitialRemoteIron;
				const int32 AggregateDelta = HostDelta + RemoteDelta;
				const bool bPassed = FrameBefore == FrameAfter
					&& FMath::IsNearlyEqual(RemoteExtracted, 18.f)
					&& FMath::IsNearlyZero(HostRejected)
					&& AggregateDelta == 6 && RemoteDelta == 6 && HostDelta == 0
					&& Asteroid->DepletionState.Phase
						== ERedMineableAsteroidDepletionPhase::Depleting
					&& Asteroid->DepletionState.Sequence == 1
					&& !Asteroid->GetActorEnableCollision();

				UE_LOG(LogTemp, Display,
					TEXT("RED_DEF0003_MP_HITS pass=%d sameServerFrame=%d frame=%llu first=%.0f second=%.0f aggregateIronDelta=%d remoteDelta=%d hostDelta=%d phase=%d sequence=%u collision=%d"),
					bPassed ? 1 : 0, FrameBefore == FrameAfter ? 1 : 0,
					FrameAfter, RemoteExtracted, HostRejected,
					AggregateDelta, RemoteDelta, HostDelta,
					static_cast<int32>(Asteroid->DepletionState.Phase),
					Asteroid->DepletionState.Sequence,
					Asteroid->GetActorEnableCollision() ? 1 : 0);
				if (!bPassed)
				{
					return Fail(TEXT("same-frame competing final-hit idempotence failed"));
				}

				RewardSubmittedAtSeconds = FPlatformTime::Seconds();
				Advance(EStage::AwaitTransition, RewardSubmittedAtSeconds);
				return false;
			}

			bool AwaitTransition(
				const FWorldPair& Worlds, const FPlayerPair& Players,
				const double Now)
			{
				if (StageTimedOut(Now))
				{
					return Fail(TEXT("remote depleting-phase parity timeout"));
				}
				ARedMineableAsteroid* AuthorityAsteroid = ServerAsteroid.Get();
				ARedMineableAsteroid* ProxyAsteroid = ClientAsteroid.Get();
				if (!AuthorityAsteroid || !ProxyAsteroid)
				{
					return false;
				}
				if (!Players.RemoteClientController || !RemoteCamera.IsValid())
				{
					return false;
				}
				Players.RemoteClientController->SetViewTarget(RemoteCamera.Get());
				if (Players.RemoteClientController->GetViewTarget() != RemoteCamera.Get())
				{
					return false;
				}
				if (AuthorityAsteroid->DepletionState.Phase
					== ERedMineableAsteroidDepletionPhase::Depleted)
				{
					return Fail(TEXT("client transition/HUD was not accepted before authority completed"));
				}

				const int32 ServerReceipts =
					CountReceipts(Worlds.Server, AuthorityAsteroid);
				const int32 ClientReceipts =
					CountReceipts(Worlds.Client, ProxyAsteroid);
				FString RemoteHUDText;
				bool bRemoteHUDVisible = false;
				float RemoteHUDSeconds = 0.0f;
				const bool bRemoteHUDBackend =
					QueryRemoteHUD(
						Players, 6, RemoteHUDText,
						bRemoteHUDVisible, RemoteHUDSeconds);
				FString HostHUDText;
				bool bHostHUDVisible = false;
				float HostHUDSeconds = 0.0f;
				const bool bHostHUDBackend =
					QueryHostHUD(
						Players, 0, HostHUDText,
						bHostHUDVisible, HostHUDSeconds);
				const bool bPassed =
					AuthorityAsteroid->DepletionState.Phase
						== ERedMineableAsteroidDepletionPhase::Depleting
					&& ProxyAsteroid->DepletionState.Phase
						== ERedMineableAsteroidDepletionPhase::Depleting
					&& AuthorityAsteroid->DepletionState.Sequence == 1
					&& ProxyAsteroid->DepletionState.Sequence == 1
					&& !AuthorityAsteroid->GetActorEnableCollision()
					&& !ProxyAsteroid->GetActorEnableCollision()
					&& !AuthorityAsteroid->IsHidden()
					&& !ProxyAsteroid->IsHidden()
					&& ServerReceipts == 1 && ClientReceipts == 1
					&& Players.RemoteServerPawn
					&& Players.RemoteServerPawn->ResIron == InitialRemoteIron + 6
					&& Players.RemoteClientPawn
					&& Players.RemoteClientPawn->ResIron == InitialRemoteIron + 6
					&& Players.HostPawn
					&& Players.HostPawn->ResIron == InitialHostIron
					&& bRemoteHUDBackend
					&& RemoteHUDText == TEXT("IRON  +6")
					&& bRemoteHUDVisible
					&& RemoteHUDSeconds > 0.0f
					&& RemoteHUDSeconds
						<= MiningResultLifetimeSeconds + 0.10f
					&& bHostHUDBackend
					&& HostHUDText.IsEmpty()
					&& !bHostHUDVisible
					&& HostHUDSeconds <= 0.0f;
				if (!bPassed)
				{
					return false;
				}

				FString WindowTitle;
				const FString Filename = FPaths::Combine(
					CaptureDirectory,
					TEXT("DEF0003_MP_Remote_SpaceReward.png"));
				if (!CaptureRemoteClientWindow(Filename, WindowTitle))
				{
					return false;
				}

				UE_LOG(LogTemp, Display,
					TEXT("RED_DEF0003_MP_REWARD pass=1 deepSpace=1 phase=%d/%d sequence=%u/%u collision=%d/%d hidden=%d/%d receipt=%d/%d remoteIron=%d/%d hostIron=%d remoteHUDBackend=%d remoteVisible=%d remoteSeconds=%.2f hudText=\"%s\" remoteOwner=1 hostHUDBackend=%d hostVisible=%d persistentResourceTally=0 capture=\"%s\" window=\"%s\""),
					static_cast<int32>(AuthorityAsteroid->DepletionState.Phase),
					static_cast<int32>(ProxyAsteroid->DepletionState.Phase),
					AuthorityAsteroid->DepletionState.Sequence,
					ProxyAsteroid->DepletionState.Sequence,
					AuthorityAsteroid->GetActorEnableCollision() ? 1 : 0,
					ProxyAsteroid->GetActorEnableCollision() ? 1 : 0,
					AuthorityAsteroid->IsHidden() ? 1 : 0,
					ProxyAsteroid->IsHidden() ? 1 : 0,
					ServerReceipts, ClientReceipts,
					Players.RemoteServerPawn->ResIron,
					Players.RemoteClientPawn->ResIron,
					Players.HostPawn->ResIron,
					bRemoteHUDBackend ? 1 : 0,
					bRemoteHUDVisible ? 1 : 0,
					RemoteHUDSeconds,
					*RemoteHUDText.ReplaceCharWithEscapedChar(),
					bHostHUDBackend ? 1 : 0,
					bHostHUDVisible ? 1 : 0,
					*Filename,
					*WindowTitle.ReplaceCharWithEscapedChar());
				RemoteReceiptObservedAtSeconds = Now;
				Advance(EStage::AwaitFinal, Now);
				return false;
			}

			bool AwaitFinal(
				const FWorldPair& Worlds, const FPlayerPair& Players,
				const double Now)
			{
				if (StageTimedOut(Now))
				{
					return Fail(TEXT("remote depleted/explosion parity timeout"));
				}
				ARedMineableAsteroid* AuthorityAsteroid = ServerAsteroid.Get();
				ARedMineableAsteroid* ProxyAsteroid = ClientAsteroid.Get();
				if (!AuthorityAsteroid || !ProxyAsteroid)
				{
					return false;
				}
				if (!Players.RemoteClientController || !RemoteCamera.IsValid())
				{
					return false;
				}
				Players.RemoteClientController->SetViewTarget(RemoteCamera.Get());
				if (Players.RemoteClientController->GetViewTarget() != RemoteCamera.Get())
				{
					return false;
				}

				const FExplosionStats ServerExplosion =
					GetExplosionStats(Worlds.Server, AuthorityAsteroid);
				const FExplosionStats ClientExplosion =
					GetExplosionStats(Worlds.Client, ProxyAsteroid);
				const int32 ServerReceipts =
					CountReceipts(Worlds.Server, AuthorityAsteroid);
				const int32 ClientReceipts =
					CountReceipts(Worlds.Client, ProxyAsteroid);
				FString RemoteHUDText;
				bool bRemoteHUDVisible = false;
				float RemoteHUDSeconds = 0.0f;
				const bool bRemoteHUDBackend =
					QueryRemoteHUD(
						Players, 6, RemoteHUDText,
						bRemoteHUDVisible, RemoteHUDSeconds);
				FString HostHUDText;
				bool bHostHUDVisible = false;
				float HostHUDSeconds = 0.0f;
				const bool bHostHUDBackend =
					QueryHostHUD(
						Players, 0, HostHUDText,
						bHostHUDVisible, HostHUDSeconds);
				const bool bReady =
					AuthorityAsteroid->DepletionState.Phase
						== ERedMineableAsteroidDepletionPhase::Depleted
					&& ProxyAsteroid->DepletionState.Phase
						== ERedMineableAsteroidDepletionPhase::Depleted
					&& AuthorityAsteroid->DepletionState.Sequence == 2
					&& ProxyAsteroid->DepletionState.Sequence == 2
					&& !AuthorityAsteroid->GetActorEnableCollision()
					&& !ProxyAsteroid->GetActorEnableCollision()
					&& AuthorityAsteroid->IsHidden()
					&& ProxyAsteroid->IsHidden()
					&& ServerExplosion.Count == 1
					&& ClientExplosion.Count == 1
					&& ClientExplosion.SimulatingDebris >= 8
					&& ServerReceipts == 1 && ClientReceipts == 1
					&& Players.RemoteServerPawn
					&& Players.RemoteServerPawn->ResIron == InitialRemoteIron + 6
					&& Players.RemoteClientPawn
					&& Players.RemoteClientPawn->ResIron == InitialRemoteIron + 6
					&& Players.HostPawn
					&& Players.HostPawn->ResIron == InitialHostIron
					&& bRemoteHUDBackend
					&& RemoteHUDText == TEXT("IRON  +6")
					&& RemoteHUDSeconds >= 0.0f
					&& bHostHUDBackend
					&& HostHUDText.IsEmpty()
					&& !bHostHUDVisible
					&& HostHUDSeconds <= 0.0f;
				if (!bReady)
				{
					return false;
				}

				const float PostHit =
					AuthorityAsteroid->RegisterMiningHit(1.f, Players.HostPawn);
				if (!FMath::IsNearlyZero(PostHit))
				{
					return Fail(TEXT("post-depletion hit extracted additional ore"));
				}

				FString WindowTitle;
				const FString Filename = FPaths::Combine(
					CaptureDirectory,
					TEXT("DEF0003_MP_Remote_SpaceExplosion.png"));
				if (!CaptureRemoteClientWindow(Filename, WindowTitle))
				{
					return false;
				}

				UE_LOG(LogTemp, Display,
					TEXT("RED_DEF0003_MP_FINAL pass=1 deepSpace=1 phase=%d/%d sequence=%u/%u collision=%d/%d hidden=%d/%d explosion=%d/%d debris=%d/%d receipt=%d/%d postHit=%.0f remoteIron=%d/%d hostIron=%d remoteHUDBackend=%d remoteVisible=%d remoteSeconds=%.2f hudText=\"%s\" hostVisible=%d capture=\"%s\" window=\"%s\""),
					static_cast<int32>(AuthorityAsteroid->DepletionState.Phase),
					static_cast<int32>(ProxyAsteroid->DepletionState.Phase),
					AuthorityAsteroid->DepletionState.Sequence,
					ProxyAsteroid->DepletionState.Sequence,
					AuthorityAsteroid->GetActorEnableCollision() ? 1 : 0,
					ProxyAsteroid->GetActorEnableCollision() ? 1 : 0,
					AuthorityAsteroid->IsHidden() ? 1 : 0,
					ProxyAsteroid->IsHidden() ? 1 : 0,
					ServerExplosion.Count, ClientExplosion.Count,
					ServerExplosion.SimulatingDebris,
					ClientExplosion.SimulatingDebris,
					ServerReceipts, ClientReceipts, PostHit,
					Players.RemoteServerPawn->ResIron,
					Players.RemoteClientPawn->ResIron,
					Players.HostPawn->ResIron,
					bRemoteHUDBackend ? 1 : 0,
					bRemoteHUDVisible ? 1 : 0,
					RemoteHUDSeconds,
					*RemoteHUDText.ReplaceCharWithEscapedChar(),
					bHostHUDVisible ? 1 : 0,
					*Filename,
					*WindowTitle.ReplaceCharWithEscapedChar());
				Advance(EStage::AwaitReceiptExpiry, Now);
				return false;
			}

			bool AwaitReceiptExpiry(
				const FWorldPair& Worlds, const FPlayerPair& Players,
				const double Now)
			{
				if (StageTimedOut(Now))
				{
					return Fail(TEXT("remote mining receipt expiry timeout"));
				}
				ARedMineableAsteroid* AuthorityAsteroid = ServerAsteroid.Get();
				ARedMineableAsteroid* ProxyAsteroid = ClientAsteroid.Get();
				if (!AuthorityAsteroid || !ProxyAsteroid
					|| !Players.RemoteClientController
					|| !RemoteCamera.IsValid())
				{
					return false;
				}
				Players.RemoteClientController->SetViewTarget(RemoteCamera.Get());
				if (Players.RemoteClientController->GetViewTarget()
					!= RemoteCamera.Get())
				{
					return false;
				}

				FString RemoteHUDText;
				bool bRemoteHUDVisible = true;
				float RemoteHUDSeconds = -1.0f;
				const bool bRemoteHUDBackend =
					QueryRemoteHUD(
						Players, 6, RemoteHUDText,
						bRemoteHUDVisible, RemoteHUDSeconds);
				FString HostHUDText;
				bool bHostHUDVisible = true;
				float HostHUDSeconds = -1.0f;
				const bool bHostHUDBackend =
					QueryHostHUD(
						Players, 0, HostHUDText,
						bHostHUDVisible, HostHUDSeconds);
				const FProductionFieldStats ProductionStats =
					GetProductionFieldStats(Worlds.Server);
				const double VisibleElapsedSeconds =
					RemoteReceiptObservedAtSeconds > 0.0
						? Now - RemoteReceiptObservedAtSeconds : 0.0;
				const bool bExpired =
					AuthorityAsteroid->DepletionState.Phase
						== ERedMineableAsteroidDepletionPhase::Depleted
					&& ProxyAsteroid->DepletionState.Phase
						== ERedMineableAsteroidDepletionPhase::Depleted
					&& AuthorityAsteroid->IsHidden()
					&& ProxyAsteroid->IsHidden()
					&& bRemoteHUDBackend
					&& RemoteHUDText == TEXT("IRON  +6")
					&& !bRemoteHUDVisible
					&& RemoteHUDSeconds <= 0.0f
					&& VisibleElapsedSeconds
						>= MiningResultLifetimeSeconds - 0.25f
					&& bHostHUDBackend
					&& HostHUDText.IsEmpty()
					&& !bHostHUDVisible
					&& HostHUDSeconds <= 0.0f
					&& ProductionStats.bContractPassed;
				if (!bExpired)
				{
					return false;
				}

				FString WindowTitle;
				const FString Filename = FPaths::Combine(
					CaptureDirectory,
					TEXT("DEF0003_MP_Remote_SpaceAfter.png"));
				if (!CaptureRemoteClientWindow(Filename, WindowTitle))
				{
					return false;
				}

				UE_LOG(LogTemp, Display,
					TEXT("RED_DEF0003_MP_RECEIPT_EXPIRED pass=1 deepSpace=1 remoteOwner=1 visible=0 secondsRemaining=%.2f visibleElapsed=%.2f hudText=\"%s\" hostVisible=0 persistentResourceTally=0 productionField=%d pristineProduction=%d productionUnaffected=1 capture=\"%s\" window=\"%s\""),
					RemoteHUDSeconds,
					VisibleElapsedSeconds,
					*RemoteHUDText.ReplaceCharWithEscapedChar(),
					ProductionStats.Count,
					ProductionStats.Pristine,
					*Filename,
					*WindowTitle.ReplaceCharWithEscapedChar());
				UE_LOG(LogTemp, Display,
					TEXT("RED_DEF0003_MP_RESULT acceptancePass=1 evidenceClass=automation topology=in_process_two_client deepSpace=1 remoteOwnerReceipt=1 transientMiningReceipt=1 receiptExpired=1 persistentResourceTally=0 productionField=24 pristineProduction=24 productionUnaffected=1 cutoffOverridden=0 scaleOverridden=0 atmosphericTarget=0 steamTransport=0"));
				AcceptanceState->bAccepted = true;
				Advance(EStage::Complete, Now);
				return true;
			}

			FAutomationTestBase* Test = nullptr;
			TSharedRef<FAcceptanceState> AcceptanceState;
			EStage Stage = EStage::AwaitTopology;
			double StartedAtSeconds = 0.0;
			double StageStartedAtSeconds = 0.0;
			double CameraReadyAtSeconds = 0.0;
			double RewardSubmittedAtSeconds = 0.0;
			double RemoteReceiptObservedAtSeconds = 0.0;
			int32 InitialHostIron = 0;
			int32 InitialRemoteIron = 0;
			int32 RemotePlayerId = INDEX_NONE;
			FVector ExpectedRemotePawnLocation = FVector::ZeroVector;
			float DeepSpaceTargetAltitudeCm = 0.f;
			float DeepSpaceCameraAltitudeCm = 0.f;
			float DeepSpaceCameraDistanceCm = 0.f;
			float DeepSpaceAngularDiameterDegrees = 0.f;
			FString CaptureDirectory;
			TWeakObjectPtr<ARedMineableAsteroid> ServerAsteroid;
			TWeakObjectPtr<ARedMineableAsteroid> ClientAsteroid;
			TWeakObjectPtr<ACameraActor> RemoteCamera;
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
						TEXT("RED_DEF0003_MP_COMPLETE pieEnded=1 acceptancePass=%d"),
						AcceptanceState->bAccepted ? 1 : 0);
					return true;
				}
				if (FPlatformTime::Seconds() - StartedAtSeconds > 15.0)
				{
					Test->AddError(TEXT("DEF-0003 PIE did not end within 15 seconds."));
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
		FRedDEF0003TwoClientPIETest,
		"RedMMO.Mining.DEF0003.TwoClientPIEParity",
		EAutomationTestFlags::EditorContext | EAutomationTestFlags::ProductFilter)

	bool FRedDEF0003TwoClientPIETest::RunTest(const FString& Parameters)
	{
		(void)Parameters;
		if (!FApp::CanEverRender()
			|| FParse::Param(FCommandLine::Get(), TEXT("nullrhi")))
		{
			AddError(TEXT(
				"DEF-0003 two-client visual acceptance requires a rendered non-NullRHI editor."));
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
		ADD_LATENT_AUTOMATION_COMMAND(FEditorLoadMap(Private::ProductionMap));
		ADD_LATENT_AUTOMATION_COMMAND(FWaitForShadersToFinishCompiling());
		ADD_LATENT_AUTOMATION_COMMAND(FStartPIEForAutomationCommand(RequestParams));
		ADD_LATENT_AUTOMATION_COMMAND(
			Private::FTwoClientAcceptanceCommand(this, AcceptanceState));
		ADD_LATENT_AUTOMATION_COMMAND(FEndPlayMapCommand());
		ADD_LATENT_AUTOMATION_COMMAND(
			Private::FWaitForPIEEndCommand(this, AcceptanceState));
		return true;
	}
}

#endif // WITH_DEV_AUTOMATION_TESTS && WITH_EDITOR
