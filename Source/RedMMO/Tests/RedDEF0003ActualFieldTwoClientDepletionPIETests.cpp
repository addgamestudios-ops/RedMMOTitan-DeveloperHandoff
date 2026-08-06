#include "../RedHUD.h"
#include "../RedBolt.h"
#include "../RedMineableAsteroid.h"
#include "../RedPlanetPresentationTuning.h"
#include "../RedPlayerCharacter.h"
#include "../RedResourcePickup.h"
#include "../RedShipExplosionFX.h"
#include "../RedSpaceScenery.h"

#if WITH_DEV_AUTOMATION_TESTS && WITH_EDITOR

#include "AudioDevice.h"
#include "AudioDeviceHandle.h"
#include "AudioDeviceManager.h"
#include "AudioMixerBlueprintLibrary.h"
#include "Camera/CameraActor.h"
#include "Camera/CameraComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Editor.h"
#include "Engine/Engine.h"
#include "Engine/GameViewportClient.h"
#include "Engine/LocalPlayer.h"
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
#include "Misc/App.h"
#include "Misc/AutomationTest.h"
#include "Misc/CommandLine.h"
#include "Misc/FileHelper.h"
#include "Misc/Parse.h"
#include "Misc/Paths.h"
#include "PlayInEditorDataTypes.h"
#include "Settings/LevelEditorMiscSettings.h"
#include "Settings/LevelEditorPlaySettings.h"
#include "Tests/AutomationEditorCommon.h"
#include "UnrealClient.h"
#include "UObject/StructOnScope.h"
#include "UObject/UnrealType.h"
#include "Widgets/SWindow.h"

namespace RedMMO::DEF0003ActualFieldTwoClientDepletionPIE
{
	namespace Private
	{
		constexpr TCHAR ProductionMap[] =
			TEXT("/Game/RedMMO/Maps/RedPlanetGen");
		constexpr TCHAR TargetStableIdText[] =
			TEXT("asteroid-field.red.mars.deep-space/0x4F524531/23");
		constexpr TCHAR RewardSoundAssetPath[] =
			TEXT("/Game/Vefects/Sand_VFX/Audio/SFX_Vefects_Sand_Rock_Hit_02_Cue.SFX_Vefects_Sand_Rock_Hit_02_Cue");
		constexpr TCHAR ExplosionSoundAssetPath[] =
			TEXT("/Game/Vefects/Sand_VFX/Audio/SFX_Vefects_Sand_Rock_Eruption_Hit_Cue.SFX_Vefects_Sand_Rock_Eruption_Hit_Cue");
		constexpr int32 MineableCount = 24;
		constexpr double TopologyTimeoutSeconds = 60.0;
		constexpr double StageTimeoutSeconds = 20.0;
		constexpr float CameraDistanceCm = 500000.f;
		constexpr float DestructionCameraDistanceCm = 30000.f;
		constexpr float DestructionCameraFOVDegrees = 55.f;
		constexpr double FlashCaptureDelaySeconds = 0.12;
		constexpr double DebrisCaptureDelaySeconds = 0.85;
		constexpr double DebrisMotionCaptureDelaySeconds = 1.15;
		constexpr double MinimumCapturedAudioSeconds = 1.5;
		constexpr float ProjectileStandOffDistanceCm = 12000.f;
		constexpr float ProjectileAimPenetrationCm = 250.f;
		constexpr float ExpectedProjectileExtraction = 180.f;
		constexpr uint16 ProjectileFireSequence = 60001;

		struct FAcceptanceState
		{
			bool bAccepted = false;
			bool bPIEEnded = false;
			bool bRestoreAllowBackgroundAudio = false;
			bool bOriginalAllowBackgroundAudio = false;
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
			int32 SoundStarted = 0;
			int32 ExpectedSoundAsset = 0;
		};

		struct FReceiptAudioStats
		{
			int32 Count = 0;
			int32 SoundStarted = 0;
			int32 ExpectedSoundAsset = 0;
			int32 LocallyControlledInstigator = 0;
		};

		struct FWavStats
		{
			bool bValid = false;
			int32 Channels = 0;
			int32 SampleRate = 0;
			int32 BitsPerSample = 0;
			int64 SampleCount = 0;
			int64 ActiveSampleCount = 0;
			int32 PeakAbsoluteSample = 0;
			double Rms = 0.0;
		};

		struct FViewportCapture
		{
			FIntPoint Size = FIntPoint::ZeroValue;
			TArray<FColor> Pixels;
		};

		struct FDebrisProjectionStats
		{
			int32 Simulating = 0;
			int32 RecentlyRendered = 0;
			int32 ProjectedPixelSized = 0;
			int32 HotMaterialPieces = 0;
			int32 HotProjectedPixelSized = 0;
			int32 HotPixelMatched = 0;
			float MaxProjectedWidthPixels = 0.f;
			TMap<FName, FVector2D> HotProjectedCenters;
		};

		bool InvokeClientServerFireRPC(
			ARedPlayerCharacter* ClientPawn,
			const FVector& ClientMuzzleLocation,
			const FVector& AimDirection,
			const uint16 FireSequence,
			FString& OutFailure)
		{
			OutFailure.Reset();
			if (!ClientPawn
				|| ClientPawn->HasAuthority()
				|| ClientPawn->GetLocalRole() != ROLE_AutonomousProxy
				|| !ClientPawn->IsLocallyControlled()
				|| !ClientPawn->GetWorld()
				|| ClientPawn->GetWorld()->GetNetMode() != NM_Client)
			{
				OutFailure = TEXT(
					"client pawn is not a locally owned autonomous proxy in NM_Client");
				return false;
			}

			UFunction* ServerFireFunction =
				ClientPawn->FindFunction(TEXT("ServerFire"));
			const EFunctionFlags RequiredFlags =
				FUNC_Net | FUNC_NetServer | FUNC_NetReliable;
			if (!ServerFireFunction
				|| !ServerFireFunction->HasAllFunctionFlags(RequiredFlags))
			{
				OutFailure = TEXT(
					"ServerFire reflection or required Net/NetServer/NetReliable flags missing");
				return false;
			}

			FStructProperty* MuzzleProperty =
				FindFProperty<FStructProperty>(
					ServerFireFunction,
					TEXT("ClientMuzzleLocation"));
			FStructProperty* AimProperty =
				FindFProperty<FStructProperty>(
					ServerFireFunction,
					TEXT("AimDirection"));
			FUInt16Property* SequenceProperty =
				FindFProperty<FUInt16Property>(
					ServerFireFunction,
					TEXT("ClientFireSequence"));
			if (!MuzzleProperty || !AimProperty || !SequenceProperty)
			{
				OutFailure = TEXT("ServerFire reflected parameter layout missing");
				return false;
			}

			FStructOnScope Parameters(ServerFireFunction);
			uint8* ParameterMemory = Parameters.GetStructMemory();
			if (!ParameterMemory)
			{
				OutFailure = TEXT("ServerFire parameter allocation failed");
				return false;
			}

			FVector_NetQuantize* MuzzleValue =
				MuzzleProperty->ContainerPtrToValuePtr<FVector_NetQuantize>(
					ParameterMemory);
			FVector_NetQuantizeNormal* AimValue =
				AimProperty->ContainerPtrToValuePtr<FVector_NetQuantizeNormal>(
					ParameterMemory);
			uint16* SequenceValue =
				SequenceProperty->ContainerPtrToValuePtr<uint16>(
					ParameterMemory);
			if (!MuzzleValue || !AimValue || !SequenceValue)
			{
				OutFailure = TEXT("ServerFire reflected parameter access failed");
				return false;
			}

			*MuzzleValue = FVector_NetQuantize(ClientMuzzleLocation);
			*AimValue = FVector_NetQuantizeNormal(AimDirection.GetSafeNormal());
			*SequenceValue = FireSequence;
			ClientPawn->ProcessEvent(
				ServerFireFunction,
				Parameters.GetStructMemory());
			return true;
		}

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

		FReceiptAudioStats GetReceiptAudioStats(
			UWorld* World,
			ARedMineableAsteroid* ExpectedOwner)
		{
			FReceiptAudioStats Result;
			for (TActorIterator<ARedResourcePickup> It(World); It; ++It)
			{
				const ARedResourcePickup* Receipt = *It;
				if (!IsValid(Receipt)
					|| Receipt->GetOwner() != ExpectedOwner
					|| Receipt->ResourceType != ERedResourceType::Iron
					|| Receipt->Amount != 6
					|| Receipt->bCollectible)
				{
					continue;
				}

				++Result.Count;
				if (Receipt->DidStartLocalRewardSound())
				{
					++Result.SoundStarted;
				}
				if (Receipt->GetRewardSoundAssetPath() == RewardSoundAssetPath)
				{
					++Result.ExpectedSoundAsset;
				}
				const APawn* ReceiptInstigator = Receipt->GetInstigator();
				if (ReceiptInstigator && ReceiptInstigator->IsLocallyControlled())
				{
					++Result.LocallyControlledInstigator;
				}
			}
			return Result;
		}

		FExplosionStats GetExplosionStats(
			UWorld* World,
			ARedMineableAsteroid* ExpectedOwner)
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
				if (Explosion->DidStartLocalExplosionSound())
				{
					++Result.SoundStarted;
				}
				if (Explosion->GetExplosionSoundAssetPath() == ExplosionSoundAssetPath)
				{
					++Result.ExpectedSoundAsset;
				}
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

		uint16 ReadLittleEndianUInt16(const TArray<uint8>& Bytes, const int32 Offset)
		{
			return static_cast<uint16>(Bytes[Offset])
				| (static_cast<uint16>(Bytes[Offset + 1]) << 8);
		}

		uint32 ReadLittleEndianUInt32(const TArray<uint8>& Bytes, const int32 Offset)
		{
			return static_cast<uint32>(Bytes[Offset])
				| (static_cast<uint32>(Bytes[Offset + 1]) << 8)
				| (static_cast<uint32>(Bytes[Offset + 2]) << 16)
				| (static_cast<uint32>(Bytes[Offset + 3]) << 24);
		}

		bool ChunkIdEquals(
			const TArray<uint8>& Bytes,
			const int32 Offset,
			const ANSICHAR A,
			const ANSICHAR B,
			const ANSICHAR C,
			const ANSICHAR D)
		{
			return Offset >= 0
				&& Offset + 4 <= Bytes.Num()
				&& Bytes[Offset] == static_cast<uint8>(A)
				&& Bytes[Offset + 1] == static_cast<uint8>(B)
				&& Bytes[Offset + 2] == static_cast<uint8>(C)
				&& Bytes[Offset + 3] == static_cast<uint8>(D);
		}

		FWavStats AnalyzePcmWav(const FString& Filename)
		{
			FWavStats Result;
			TArray<uint8> Bytes;
			if (!FFileHelper::LoadFileToArray(Bytes, *Filename)
				|| Bytes.Num() < 44
				|| !ChunkIdEquals(Bytes, 0, 'R', 'I', 'F', 'F')
				|| !ChunkIdEquals(Bytes, 8, 'W', 'A', 'V', 'E'))
			{
				return Result;
			}

			uint16 AudioFormat = 0;
			int32 DataOffset = INDEX_NONE;
			uint32 DataSize = 0;
			for (int32 Offset = 12; Offset + 8 <= Bytes.Num();)
			{
				const uint32 ChunkSize = ReadLittleEndianUInt32(Bytes, Offset + 4);
				const int64 ChunkEnd64 =
					static_cast<int64>(Offset) + 8 + static_cast<int64>(ChunkSize);
				if (ChunkEnd64 > Bytes.Num())
				{
					return Result;
				}

				if (ChunkIdEquals(Bytes, Offset, 'f', 'm', 't', ' ')
					&& ChunkSize >= 16)
				{
					AudioFormat = ReadLittleEndianUInt16(Bytes, Offset + 8);
					Result.Channels = ReadLittleEndianUInt16(Bytes, Offset + 10);
					Result.SampleRate = static_cast<int32>(
						ReadLittleEndianUInt32(Bytes, Offset + 12));
					Result.BitsPerSample =
						ReadLittleEndianUInt16(Bytes, Offset + 22);
				}
				else if (ChunkIdEquals(Bytes, Offset, 'd', 'a', 't', 'a'))
				{
					DataOffset = Offset + 8;
					DataSize = ChunkSize;
				}

				const int64 NextOffset64 =
					ChunkEnd64 + static_cast<int64>(ChunkSize & 1u);
				if (NextOffset64 <= Offset || NextOffset64 > MAX_int32)
				{
					return Result;
				}
				Offset = static_cast<int32>(NextOffset64);
			}

			if (AudioFormat != 1
				|| Result.Channels <= 0
				|| Result.SampleRate <= 0
				|| Result.BitsPerSample != 16
				|| DataOffset == INDEX_NONE
				|| DataSize < 2
				|| static_cast<int64>(DataOffset) + DataSize > Bytes.Num())
			{
				return Result;
			}

			Result.SampleCount = DataSize / sizeof(int16);
			double SumSquares = 0.0;
			for (int64 Index = 0; Index < Result.SampleCount; ++Index)
			{
				const int32 ByteOffset =
					DataOffset + static_cast<int32>(Index * sizeof(int16));
				const int16 Sample = static_cast<int16>(
					ReadLittleEndianUInt16(Bytes, ByteOffset));
				const int32 AbsoluteSample =
					Sample == MIN_int16 ? MAX_int16 : FMath::Abs(Sample);
				Result.PeakAbsoluteSample =
					FMath::Max(Result.PeakAbsoluteSample, AbsoluteSample);
				if (AbsoluteSample >= 128)
				{
					++Result.ActiveSampleCount;
				}
				SumSquares +=
					static_cast<double>(Sample) * static_cast<double>(Sample);
			}
			Result.Rms = Result.SampleCount > 0
				? FMath::Sqrt(SumSquares / static_cast<double>(Result.SampleCount))
				: 0.0;
			Result.bValid = Result.SampleCount > 0;
			return Result;
		}

		ARedShipExplosionFX* FindOwnedExplosion(
			UWorld* World,
			ARedMineableAsteroid* ExpectedOwner)
		{
			ARedShipExplosionFX* Result = nullptr;
			int32 MatchCount = 0;
			for (TActorIterator<ARedShipExplosionFX> It(World); It; ++It)
			{
				ARedShipExplosionFX* Explosion = *It;
				if (IsValid(Explosion) && Explosion->GetOwner() == ExpectedOwner)
				{
					Result = Explosion;
					++MatchCount;
				}
			}
			return MatchCount == 1 ? Result : nullptr;
		}

		bool QueryRemoteHUD(
			const FPlayerPair& Players,
			const int32 ExpectedAmount,
			FString& OutText,
			bool& bOutVisible)
		{
			OutText.Reset();
			bOutVisible = false;
			if (!Players.RemoteClientController || !Players.RemoteClientPawn)
			{
				return false;
			}

			const ARedHUD* HUD =
				Cast<ARedHUD>(Players.RemoteClientController->GetHUD());
			if (!HUD)
			{
				return false;
			}

			FString InventoryText;
			bool bPersistentTallyVisible = true;
			const bool bInventoryCachePassed =
				HUD->QueryReplacementHUDResources(
					Players.RemoteClientPawn->ResStone,
					Players.RemoteClientPawn->ResIron,
					Players.RemoteClientPawn->ResCrystal,
					InventoryText,
					bPersistentTallyVisible)
				&& InventoryText.IsEmpty()
				&& !bPersistentTallyVisible;
			float SecondsRemaining = 0.0f;
			return bInventoryCachePassed
				&& HUD->QueryReplacementHUDMiningResult(
					static_cast<uint8>(ERedResourceType::Iron),
					ExpectedAmount,
					OutText,
					bOutVisible,
					SecondsRemaining);
		}

		bool CaptureRemoteClientWindow(
			const FString& Filename,
			FString& OutWindowTitle)
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
					RemoteWindow.ToSharedRef(),
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

		bool CaptureRemoteClientViewport(
			APlayerController* RemoteClientController,
			const FString& Filename,
			FViewportCapture& OutCapture)
		{
			OutCapture = FViewportCapture();
			ULocalPlayer* LocalPlayer =
				RemoteClientController
					? RemoteClientController->GetLocalPlayer()
					: nullptr;
			UGameViewportClient* ViewportClient =
				LocalPlayer ? LocalPlayer->ViewportClient : nullptr;
			FViewport* Viewport =
				ViewportClient ? ViewportClient->Viewport : nullptr;
			if (!Viewport)
			{
				return false;
			}

			OutCapture.Size = Viewport->GetSizeXY();
			if (OutCapture.Size.X <= 0
				|| OutCapture.Size.Y <= 0
				|| !Viewport->ReadPixels(OutCapture.Pixels)
				|| OutCapture.Pixels.Num()
					< OutCapture.Size.X * OutCapture.Size.Y)
			{
				OutCapture = FViewportCapture();
				return false;
			}

			IFileManager::Get().MakeDirectory(*FPaths::GetPath(Filename), true);
			TArray64<uint8> PNG;
			FImageUtils::PNGCompressImageArray(
				OutCapture.Size.X,
				OutCapture.Size.Y,
				TArrayView64<const FColor>(
					OutCapture.Pixels.GetData(),
					OutCapture.Pixels.Num()),
				PNG);
			return PNG.Num() > 0
				&& FFileHelper::SaveArrayToFile(PNG, *Filename);
		}

		int32 CountPixelsInRect(
			const FViewportCapture& Capture,
			FIntRect Rect,
			const bool bWarmOnly)
		{
			if (Capture.Size.X <= 0
				|| Capture.Size.Y <= 0
				|| Capture.Pixels.Num()
					< Capture.Size.X * Capture.Size.Y)
			{
				return 0;
			}

			Rect.Min.X = FMath::Clamp(Rect.Min.X, 0, Capture.Size.X);
			Rect.Min.Y = FMath::Clamp(Rect.Min.Y, 0, Capture.Size.Y);
			Rect.Max.X = FMath::Clamp(Rect.Max.X, 0, Capture.Size.X);
			Rect.Max.Y = FMath::Clamp(Rect.Max.Y, 0, Capture.Size.Y);
			int32 Count = 0;
			for (int32 Y = Rect.Min.Y; Y < Rect.Max.Y; ++Y)
			{
				for (int32 X = Rect.Min.X; X < Rect.Max.X; ++X)
				{
					const FColor& Pixel =
						Capture.Pixels[Y * Capture.Size.X + X];
					const bool bWarm =
						Pixel.R >= 120
						&& Pixel.R >= Pixel.B + 24
						&& Pixel.G >= 45;
					const bool bLuminous =
						FMath::Max3(Pixel.R, Pixel.G, Pixel.B) >= 80;
					if (bWarmOnly ? bWarm : bLuminous)
					{
						++Count;
					}
				}
			}
			return Count;
		}

		int32 CountPixelsNearProjectedRect(
			const FViewportCapture& Capture,
			const FIntRect& ProjectedRect,
			const bool bWarmOnly)
		{
			const FIntRect Expanded(
				ProjectedRect.Min - FIntPoint(4, 4),
				ProjectedRect.Max + FIntPoint(5, 5));
			const int32 Direct =
				CountPixelsInRect(Capture, Expanded, bWarmOnly);
			const FIntRect VerticallyMirrored(
				FIntPoint(
					Expanded.Min.X,
					Capture.Size.Y - Expanded.Max.Y),
				FIntPoint(
					Expanded.Max.X,
					Capture.Size.Y - Expanded.Min.Y));
			return FMath::Max(
				Direct,
				CountPixelsInRect(
					Capture,
					VerticallyMirrored,
					bWarmOnly));
		}

		int32 CountChangedPixelsInRect(
			const FViewportCapture& Before,
			const FViewportCapture& After,
			FIntRect Rect)
		{
			if (Before.Size != After.Size
				|| Before.Pixels.Num() < Before.Size.X * Before.Size.Y
				|| After.Pixels.Num() < After.Size.X * After.Size.Y)
			{
				return 0;
			}

			Rect.Min.X = FMath::Clamp(Rect.Min.X, 0, Before.Size.X);
			Rect.Min.Y = FMath::Clamp(Rect.Min.Y, 0, Before.Size.Y);
			Rect.Max.X = FMath::Clamp(Rect.Max.X, 0, Before.Size.X);
			Rect.Max.Y = FMath::Clamp(Rect.Max.Y, 0, Before.Size.Y);
			int32 Changed = 0;
			for (int32 Y = Rect.Min.Y; Y < Rect.Max.Y; ++Y)
			{
				for (int32 X = Rect.Min.X; X < Rect.Max.X; ++X)
				{
					const int32 Index = Y * Before.Size.X + X;
					const FColor& A = Before.Pixels[Index];
					const FColor& B = After.Pixels[Index];
					const int32 ChannelDelta =
						FMath::Abs(static_cast<int32>(A.R) - B.R)
						+ FMath::Abs(static_cast<int32>(A.G) - B.G)
						+ FMath::Abs(static_cast<int32>(A.B) - B.B);
					if (ChannelDelta >= 60)
					{
						++Changed;
					}
				}
			}
			return Changed;
		}

		int32 CountCentralFlashPixels(
			const FViewportCapture& Capture,
			const FVector2D& Center,
			const bool bWarmOnly)
		{
			constexpr int32 HalfExtent = 128;
			return CountPixelsInRect(
				Capture,
				FIntRect(
					FIntPoint(
						FMath::RoundToInt(Center.X) - HalfExtent,
						FMath::RoundToInt(Center.Y) - HalfExtent),
					FIntPoint(
						FMath::RoundToInt(Center.X) + HalfExtent,
						FMath::RoundToInt(Center.Y) + HalfExtent)),
				bWarmOnly);
		}

		FDebrisProjectionStats GetDebrisProjectionStats(
			ARedShipExplosionFX* Explosion,
			APlayerController* RemoteClientController,
			const FViewportCapture* OptionalCapture)
		{
			FDebrisProjectionStats Result;
			if (!Explosion || !RemoteClientController)
			{
				return Result;
			}

			int32 ViewportWidth = 0;
			int32 ViewportHeight = 0;
			RemoteClientController->GetViewportSize(
				ViewportWidth,
				ViewportHeight);
			if (OptionalCapture)
			{
				ViewportWidth = OptionalCapture->Size.X;
				ViewportHeight = OptionalCapture->Size.Y;
			}
			if (ViewportWidth <= 0 || ViewportHeight <= 0)
			{
				return Result;
			}

			TArray<UStaticMeshComponent*> Components;
			Explosion->GetComponents<UStaticMeshComponent>(Components);
			for (UStaticMeshComponent* Component : Components)
			{
				if (!Component || !Component->IsSimulatingPhysics())
				{
					continue;
				}
				++Result.Simulating;
				if (Component->WasRecentlyRendered(0.25f))
				{
					++Result.RecentlyRendered;
				}

				const UMaterialInterface* Material = Component->GetMaterial(0);
				const bool bHotMaterial =
					Material
					&& Material->GetPathName().Contains(TEXT("MI_Boom_00"));
				if (bHotMaterial)
				{
					++Result.HotMaterialPieces;
				}

				const FBox Bounds = Component->Bounds.GetBox();
				const FVector Corners[8] =
				{
					FVector(Bounds.Min.X, Bounds.Min.Y, Bounds.Min.Z),
					FVector(Bounds.Min.X, Bounds.Min.Y, Bounds.Max.Z),
					FVector(Bounds.Min.X, Bounds.Max.Y, Bounds.Min.Z),
					FVector(Bounds.Min.X, Bounds.Max.Y, Bounds.Max.Z),
					FVector(Bounds.Max.X, Bounds.Min.Y, Bounds.Min.Z),
					FVector(Bounds.Max.X, Bounds.Min.Y, Bounds.Max.Z),
					FVector(Bounds.Max.X, Bounds.Max.Y, Bounds.Min.Z),
					FVector(Bounds.Max.X, Bounds.Max.Y, Bounds.Max.Z)
				};
				FVector2D ScreenMin(
					TNumericLimits<float>::Max(),
					TNumericLimits<float>::Max());
				FVector2D ScreenMax(
					TNumericLimits<float>::Lowest(),
					TNumericLimits<float>::Lowest());
				bool bAllProjected = true;
				for (const FVector& Corner : Corners)
				{
					FVector2D Screen;
					if (!RemoteClientController->ProjectWorldLocationToScreen(
							Corner,
							Screen,
							true))
					{
						bAllProjected = false;
						break;
					}
					ScreenMin.X = FMath::Min(ScreenMin.X, Screen.X);
					ScreenMin.Y = FMath::Min(ScreenMin.Y, Screen.Y);
					ScreenMax.X = FMath::Max(ScreenMax.X, Screen.X);
					ScreenMax.Y = FMath::Max(ScreenMax.Y, Screen.Y);
				}
				if (!bAllProjected
					|| ScreenMin.X < 0.f
					|| ScreenMin.Y < 0.f
					|| ScreenMax.X >= ViewportWidth
					|| ScreenMax.Y >= ViewportHeight)
				{
					continue;
				}

				const float Width = ScreenMax.X - ScreenMin.X;
				const float Height = ScreenMax.Y - ScreenMin.Y;
				Result.MaxProjectedWidthPixels =
					FMath::Max(Result.MaxProjectedWidthPixels, Width);
				if (Width < 3.f || Height < 2.f)
				{
					continue;
				}
				++Result.ProjectedPixelSized;

				if (!bHotMaterial)
				{
					continue;
				}
				++Result.HotProjectedPixelSized;
				const FVector2D Center = (ScreenMin + ScreenMax) * 0.5f;
				Result.HotProjectedCenters.Add(Component->GetFName(), Center);
				if (OptionalCapture)
				{
					const FIntRect PixelRect(
						FIntPoint(
							FMath::FloorToInt(ScreenMin.X),
							FMath::FloorToInt(ScreenMin.Y)),
						FIntPoint(
							FMath::CeilToInt(ScreenMax.X) + 1,
							FMath::CeilToInt(ScreenMax.Y) + 1));
					if (CountPixelsNearProjectedRect(
							*OptionalCapture,
							PixelRect,
							true) >= 6)
					{
						++Result.HotPixelMatched;
					}
				}
			}
			return Result;
		}

		int32 CountMovingHotPieces(
			const FDebrisProjectionStats& Before,
			const FDebrisProjectionStats& After)
		{
			int32 Moving = 0;
			for (const TPair<FName, FVector2D>& Pair :
				Before.HotProjectedCenters)
			{
				const FVector2D* Later =
					After.HotProjectedCenters.Find(Pair.Key);
				if (Later
					&& FVector2D::Distance(Pair.Value, *Later) >= 1.f)
				{
					++Moving;
				}
			}
			return Moving;
		}

		class FActualFieldTwoClientDepletionCommand final
			: public IAutomationLatentCommand
		{
		public:
			FActualFieldTwoClientDepletionCommand(
				FAutomationTestBase* InTest,
				TSharedRef<FAcceptanceState> InAcceptanceState)
				: Test(InTest)
				, AcceptanceState(MoveTemp(InAcceptanceState))
				, TargetId(TargetStableIdText)
			{
				FParse::Value(
					FCommandLine::Get(),
					TEXT("RedDEF0003FieldMPDepletionCaptureDir="),
					CaptureDirectory);
				if (CaptureDirectory.IsEmpty())
				{
					const FString SessionDirectoryName = FString::Printf(
						TEXT("DEF0003ActualFieldTwoClientDepletionPIE_%s_%u_%s"),
						*FDateTime::UtcNow().ToString(TEXT("%Y%m%dT%H%M%SZ")),
						FPlatformProcess::GetCurrentProcessId(),
						*FGuid::NewGuid().ToString(EGuidFormats::Digits));
					CaptureDirectory = FPaths::Combine(
						FPaths::ProjectSavedDir(),
						TEXT("Automation"),
						SessionDirectoryName);
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
				case EStage::AwaitProjectileDelivery:
					return AwaitProjectileDelivery(Worlds, Players, Now);
				case EStage::SubmitHits:
					return SubmitHits(Worlds, Players, Now);
				case EStage::AwaitTransition:
					return AwaitTransition(Worlds, Players, Now);
				case EStage::AwaitFinal:
					return AwaitFinal(Worlds, Players, Now);
				case EStage::AwaitDestructionPixels:
					return AwaitDestructionPixels(Worlds, Players, Now);
				case EStage::AwaitAudioFile:
					return AwaitAudioFile(Worlds, Players, Now);
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
				AwaitProjectileDelivery,
				SubmitHits,
				AwaitTransition,
				AwaitFinal,
				AwaitDestructionPixels,
				AwaitAudioFile,
				Complete
			};

			bool Fail(const FString& Reason)
			{
				if (bAudioRecordingStarted && !bAudioRecordingStopped)
				{
					const FWorldPair Worlds = ResolvePIEWorlds();
					if (Worlds.Client)
					{
						UAudioMixerBlueprintLibrary::StopRecordingOutput(
							Worlds.Client,
							EAudioRecordingExportType::WavFile,
							TEXT("DEF0003_Field_MP_Depletion_Audio_Failed"),
							CaptureDirectory);
					}
					bAudioRecordingStopped = true;
				}
				RestorePIEAudioOverride();
				Test->AddError(FString::Printf(
					TEXT("DEF-0003 actual-field two-client depletion acceptance failed: %s"),
					*Reason));
				UE_LOG(
					LogTemp,
					Error,
					TEXT("RED_DEF0003_FIELD_MP_DEPLETION_RESULT acceptancePass=0 reason=\"%s\""),
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

			bool EnsurePIEAudioIsUnmuted(const FWorldPair& Worlds)
			{
				if (!Worlds.Server || !Worlds.Client)
					{
						return false;
					}
				const FAudioDeviceHandle ServerAudio =
					Worlds.Server->GetAudioDevice();
				const FAudioDeviceHandle ClientAudio =
					Worlds.Client->GetAudioDevice();
				if (!ServerAudio.IsValid() || !ClientAudio.IsValid())
					{
						return false;
					}
				if (ServerAudio.GetDeviceID() == ClientAudio.GetDeviceID())
					{
						return false;
					}
				FAudioDeviceManager* DeviceManager =
					GEngine ? GEngine->GetAudioDeviceManager() : nullptr;
				if (!DeviceManager)
				{
					return false;
				}
				if (FApp::GetVolumeMultiplier() <= UE_KINDA_SMALL_NUMBER)
				{
					return false;
				}
				if (DeviceManager->IsPlayAllDeviceAudio())
				{
					if (ClientAudio->IsAudioDeviceMuted()
						|| ClientAudio->GetPrimaryVolume()
							<= UE_KINDA_SMALL_NUMBER)
						{
							return false;
						}
					ServerAudioDeviceId = ServerAudio.GetDeviceID();
					ClientAudioDeviceId = ClientAudio.GetDeviceID();
					ClientPrimaryVolume = ClientAudio->GetPrimaryVolume();
					bPIEAudioUnmutedReady = true;
					return true;
				}
				if (!bPIEAudioOverrideRequested)
				{
					DeviceManager->TogglePlayAllDeviceAudio();
					bPIEAudioOverrideRequested = true;
					bPIEAudioOverrideWasApplied = true;
				}
				return false;
			}

			void RestorePIEAudioOverride()
			{
				if (!bPIEAudioOverrideRequested)
				{
					return;
				}
				if (FAudioDeviceManager* DeviceManager =
					GEngine ? GEngine->GetAudioDeviceManager() : nullptr)
				{
					if (DeviceManager->IsPlayAllDeviceAudio())
						{
							DeviceManager->TogglePlayAllDeviceAudio();
						}
				}
				bPIEAudioOverrideRequested = false;
			}

			bool PinRemoteView(const FPlayerPair& Players)
			{
				if (!Players.RemoteClientController || !RemoteCamera.IsValid())
				{
					return false;
				}
				Players.RemoteClientController->SetViewTarget(RemoteCamera.Get());
				return Players.RemoteClientController->GetViewTarget()
					== RemoteCamera.Get();
			}

			bool TargetIdentityAndCutoffPass(
				const ARedMineableAsteroid* Target,
				const bool bExpectAuthority) const
			{
				const UStaticMeshComponent* Mesh =
					Target
						? Cast<UStaticMeshComponent>(Target->GetRootComponent())
						: nullptr;
				return IsValid(Target)
					&& Target->GetStableMemberId() == TargetId
					&& Target->HasAuthority() == bExpectAuthority
					&& !Target->HasAnyFlags(RF_Transient)
					&& FMath::IsNearlyEqual(
						Target->OreCapacity,
						InitialCapacity > 0.f ? InitialCapacity : 6000.f)
					&& Target->GetActorScale3D().Equals(
						InitialScale.IsNearlyZero()
							? Target->GetActorScale3D()
							: InitialScale,
						0.001f)
					&& FMath::IsNearlyEqual(
						Target->GetPresentationCullDistance(),
						RedPlanetPresentationTuning::
							AsteroidRenderCullDistanceCm,
						1.f)
					&& Mesh
					&& Mesh->IsRegistered()
					&& FMath::IsNearlyEqual(
						Mesh->LDMaxDrawDistance,
						RedPlanetPresentationTuning::
							AsteroidRenderCullDistanceCm,
						1.f)
					&& FMath::IsNearlyEqual(
						Mesh->CachedMaxDrawDistance,
						RedPlanetPresentationTuning::
							AsteroidRenderCullDistanceCm,
						1.f);
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

				FString InitialHUDText;
				bool bInitialHUDVisible = false;
				const bool bHUDReady =
					QueryRemoteHUD(
						Players,
						0,
						InitialHUDText,
						bInitialHUDVisible)
					&& !bInitialHUDVisible;
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
					|| !PlayerIdentitiesMatch(Players)
					|| !bHUDReady)
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
					|| Target->GetStableMemberId() != TargetId
					|| Target->GetOwner() != Scenery
					|| !Target->ActorHasTag(TEXT("RedMarsMineableBelt"))
					|| Target->GetLocalRole() != ROLE_Authority
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
					return Fail(TEXT("authority production field identity failed"));
				}
				const FAudioDeviceHandle ServerAudio =
					Worlds.Server->GetAudioDevice();
				const FAudioDeviceHandle ClientAudio =
					Worlds.Client->GetAudioDevice();
				if (ServerAudio.IsValid()
					&& ClientAudio.IsValid()
					&& ServerAudio.GetDeviceID() == ClientAudio.GetDeviceID())
					{
						return Fail(TEXT(
							"server/client PIE audio devices are not distinct"));
					}
				if (!EnsurePIEAudioIsUnmuted(Worlds))
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
				RadialOut =
					(BoundsOrigin - Scenery->GetActorLocation()).GetSafeNormal();
				if (RadialOut.IsNearlyZero())
				{
					return Fail(TEXT("authority target radial direction is zero"));
				}

				UStaticMeshComponent* TargetMesh =
					Cast<UStaticMeshComponent>(Target->GetRootComponent());
				FHitResult SurfaceHit;
				const FVector SurfaceTraceStart =
					BoundsOrigin
					+ RadialOut * (BoundsExtent.Size() * 2.f + 50000.f);
				const FVector SurfaceTraceEnd =
					BoundsOrigin - RadialOut * BoundsExtent.Size();
				FCollisionQueryParams SurfaceTraceParams(
					SCENE_QUERY_STAT(DEF0003ProjectileSurface),
					false);
				if (!TargetMesh
					|| !TargetMesh->LineTraceComponent(
						SurfaceHit,
						SurfaceTraceStart,
						SurfaceTraceEnd,
						SurfaceTraceParams))
				{
					return Fail(TEXT(
						"authority target surface trace failed for projectile placement"));
				}
				ProjectileSurfacePoint = SurfaceHit.ImpactPoint;
				ProjectileAimPoint =
					ProjectileSurfacePoint
					- RadialOut * ProjectileAimPenetrationCm;
				const FVector HoldLocation =
					ProjectileSurfacePoint
					+ RadialOut * ProjectileStandOffDistanceCm;
				const FRotator HoldRotation =
					(ProjectileAimPoint - HoldLocation).Rotation();
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

				ServerTarget = Target;
				InitialCapacity = Target->OreCapacity;
				InitialScale = Target->GetActorScale3D();
				InitialTargetLocation = Target->GetActorLocation();
				InitialTargetRotation = Target->GetActorQuat();
				InitialHostIron = Players.HostPawn->ResIron;
				InitialRemoteIron = Players.RemoteServerPawn->ResIron;
				InitialRemoteStone = Players.RemoteServerPawn->ResStone;
				InitialRemoteCrystal = Players.RemoteServerPawn->ResCrystal;

				UE_LOG(
					LogTemp,
					Display,
					TEXT("RED_DEF0003_FIELD_MP_DEPLETION_TOPOLOGY pass=1 pid=%u pieWorlds=%d listen=%d clients=%d serverPlayers=%d stableId=%s cohort=%d testTeleport=1 pieAudioDeviceUnmuted=%d playAllPIEAudioOverride=%d appVolume=%.2f clientPrimaryVolume=%.2f audioDeviceIds=%u/%u backgroundAudioOverride=%d"),
					FPlatformProcess::GetCurrentProcessId(),
					Worlds.PIEWorldCount,
					Worlds.ListenServerCount,
					Worlds.ClientCount,
					Players.ServerPlayerCount,
					*TargetId.ToString(),
					Members.Num(),
					bPIEAudioUnmutedReady ? 1 : 0,
					bPIEAudioOverrideWasApplied ? 1 : 0,
					FApp::GetVolumeMultiplier(),
					ClientPrimaryVolume,
					ServerAudioDeviceId,
					ClientAudioDeviceId,
					AcceptanceState->bRestoreAllowBackgroundAudio ? 1 : 0);
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
					return Fail(TEXT("remote actual-field proxy/HUD timeout"));
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
				if (!TargetIdentityAndCutoffPass(AuthorityTarget, true)
					|| !TargetIdentityAndCutoffPass(ProxyTarget, false)
					|| ProxyTarget->GetLocalRole() != ROLE_SimulatedProxy
					|| !ProxyTarget->GetActorLocation().Equals(
						InitialTargetLocation,
						1.f)
					|| FMath::Abs(
						ProxyTarget->GetActorQuat().GetNormalized()
							| InitialTargetRotation.GetNormalized())
						< 0.99999f
					|| !FMath::IsNearlyEqual(
						ProxyTarget->OreRemaining,
						InitialCapacity))
				{
					return Fail(TEXT("remote stable identity/transform/cutoff parity failed"));
				}
				const float NetCullDistanceCm =
					FMath::Sqrt(
						AuthorityTarget->GetNetCullDistanceSquared());
				if (FVector::Distance(
						Players.RemoteClientPawn->GetActorLocation(),
						ProxyTarget->GetActorLocation())
					>= NetCullDistanceCm * 0.9f)
				{
					return false;
				}

				if (!RemoteCamera.IsValid())
				{
					FVector BoundsOrigin;
					FVector BoundsExtent;
					ProxyTarget->GetActorBounds(
						false,
						BoundsOrigin,
						BoundsExtent,
						true);
					const float SafeCameraDistance =
						FMath::Max(
							CameraDistanceCm,
							BoundsExtent.Size() * 3.25f);
					const FVector CameraLocation =
						BoundsOrigin + RadialOut * SafeCameraDistance;
					const FRotator CameraRotation =
						(BoundsOrigin - CameraLocation).Rotation();
					FActorSpawnParameters CameraParameters;
					CameraParameters.ObjectFlags |= RF_Transient;
					CameraParameters.SpawnCollisionHandlingOverride =
						ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
					ACameraActor* Camera =
						Worlds.Client->SpawnActor<ACameraActor>(
							CameraLocation,
							CameraRotation,
							CameraParameters);
					if (!Camera)
					{
						return Fail(TEXT("remote client camera spawn failed"));
					}
					Camera->GetCameraComponent()->SetFieldOfView(52.f);
					Players.RemoteClientController->SetViewTarget(Camera);
					RemoteCamera = Camera;
					ClientTarget = ProxyTarget;
					CameraReadyAtSeconds = Now;
					return false;
				}

				if (!PinRemoteView(Players)
					|| Now - CameraReadyAtSeconds < 0.75)
				{
					return false;
				}
				const UStaticMeshComponent* ProxyMesh =
					Cast<UStaticMeshComponent>(ProxyTarget->GetRootComponent());
				FString HUDText;
				bool bHUDVisible = false;
				if (!ProxyMesh
					|| !ProxyMesh->WasRecentlyRendered(1.5f)
					|| !QueryRemoteHUD(Players, 0, HUDText, bHUDVisible)
					|| bHUDVisible
					|| !HUDText.IsEmpty())
				{
					return false;
				}

				FString WindowTitle;
				const FString Filename = FPaths::Combine(
					CaptureDirectory,
					TEXT("DEF0003_Field_MP_Depletion_Before.png"));
				if (!CaptureRemoteClientWindow(Filename, WindowTitle))
				{
					return false;
				}

				AudioCaptureFilename = FPaths::Combine(
					CaptureDirectory,
					TEXT("DEF0003_Field_MP_Depletion_Audio.wav"));
				if (IFileManager::Get().FileSize(*AudioCaptureFilename) >= 0)
				{
					return Fail(FString::Printf(
						TEXT("audio capture target already exists: %s"),
						*AudioCaptureFilename));
				}
				UAudioMixerBlueprintLibrary::StartRecordingOutput(
					Worlds.Client,
					8.f);
				bAudioRecordingStarted = true;
				AudioRecordingStartedAtSeconds = Now;

				UE_LOG(
					LogTemp,
					Display,
					TEXT("RED_DEF0003_FIELD_MP_DEPLETION_BEFORE pass=1 stableId=%s phase=%d/%d ore=%.0f/%.0f pristinePeers=%d hudText=\"%s\" capture=\"%s\" audioRecording=1 audioTarget=\"%s\""),
					*TargetId.ToString(),
					static_cast<int32>(
						AuthorityTarget->DepletionState.Phase),
					static_cast<int32>(ProxyTarget->DepletionState.Phase),
					AuthorityTarget->OreRemaining,
					ProxyTarget->OreRemaining,
					CountOtherPristineMembers(Worlds.Server, TargetId),
					*HUDText.ReplaceCharWithEscapedChar(),
					*Filename,
					*AudioCaptureFilename);
				Advance(EStage::AwaitProjectileDelivery, Now);
				return false;
			}

			bool AwaitProjectileDelivery(
				const FWorldPair& Worlds,
				const FPlayerPair& Players,
				const double Now)
			{
				ARedMineableAsteroid* AuthorityTarget = ServerTarget.Get();
				ARedMineableAsteroid* ProxyTarget = ClientTarget.Get();
				if (StageTimedOut(Now))
				{
					return Fail(FString::Printf(
						TEXT("client ServerFire projectile delivery timed out submitted=%d authorityBolt=%d clientBolt=%d authorityOre=%.0f clientOre=%.0f"),
						bProjectileRPCSubmitted ? 1 : 0,
						bSawAuthorityProjectile ? 1 : 0,
						bSawClientProjectile ? 1 : 0,
						AuthorityTarget ? AuthorityTarget->OreRemaining : -1.f,
						ProxyTarget ? ProxyTarget->OreRemaining : -1.f));
				}
				if (!Worlds.Server
					|| !Worlds.Client
					|| !AuthorityTarget
					|| !ProxyTarget
					|| !Players.HostPawn
					|| !Players.RemoteServerPawn
					|| !Players.RemoteClientPawn
					|| !PlayerIdentitiesMatch(Players)
					|| !PinRemoteView(Players))
				{
					return false;
				}

				if (!bProjectileRPCSubmitted)
				{
					if (AuthorityTarget->DepletionState.Phase
							!= ERedMineableAsteroidDepletionPhase::Active
						|| ProxyTarget->DepletionState.Phase
							!= ERedMineableAsteroidDepletionPhase::Active
						|| !FMath::IsNearlyEqual(
							AuthorityTarget->OreRemaining,
							InitialCapacity)
						|| !FMath::IsNearlyEqual(
							ProxyTarget->OreRemaining,
							InitialCapacity)
						|| Players.RemoteServerPawn->ResIron
							!= InitialRemoteIron
						|| Players.RemoteClientPawn->ResIron
							!= InitialRemoteIron)
					{
						return Fail(TEXT(
							"projectile pre-submit ore/resource state was not pristine"));
					}

					const FVector ServerMuzzle =
						Players.RemoteServerPawn->GetMuzzleWorldLocation();
					const FVector ClientMuzzle =
						Players.RemoteClientPawn->GetMuzzleWorldLocation();
					const float MuzzleParityCm =
						FVector::Distance(ServerMuzzle, ClientMuzzle);
					const FVector AimDirection =
						(ProjectileAimPoint - ClientMuzzle).GetSafeNormal();
					if (AimDirection.IsNearlyZero()
						|| AimDirection.ContainsNaN()
						|| MuzzleParityCm > 175.f)
					{
						return false;
					}

					FHitResult PathHit;
					FCollisionQueryParams PathParams(
						SCENE_QUERY_STAT(DEF0003ProjectilePath),
						false,
						Players.RemoteServerPawn);
					PathParams.AddIgnoredActor(Players.HostPawn);
					const FVector ServerPathStart =
						ServerMuzzle + AimDirection * 10.f;
					const bool bPathHit =
						Worlds.Server->LineTraceSingleByChannel(
							PathHit,
							ServerPathStart,
							ProjectileAimPoint,
							ECC_Visibility,
							PathParams);
					const float PathDistanceCm =
						bPathHit
							? FVector::Distance(
								ServerPathStart,
								PathHit.ImpactPoint)
							: TNumericLimits<float>::Max();
					if (!bPathHit
						|| PathHit.GetActor() != AuthorityTarget
						|| PathDistanceCm > 18000.f)
					{
						return Fail(FString::Printf(
							TEXT("authority projectile path preflight failed hit=%s distanceCm=%.1f"),
							*GetNameSafe(PathHit.GetActor()),
							PathDistanceCm));
					}

					FString RPCFailure;
					if (!InvokeClientServerFireRPC(
							Players.RemoteClientPawn,
							ClientMuzzle,
							AimDirection,
							ProjectileFireSequence,
							RPCFailure))
					{
						return Fail(FString::Printf(
							TEXT("client ServerFire RPC submit failed: %s"),
							*RPCFailure));
					}
					if (!FMath::IsNearlyEqual(
							ProxyTarget->OreRemaining,
							InitialCapacity))
					{
						return Fail(TEXT(
							"client proxy mutated ore locally during ServerFire submit"));
					}

					bProjectileRPCSubmitted = true;
					ProjectileRPCSubmittedAtSeconds = Now;
					ProjectileServerMuzzle = ServerMuzzle;
					ProjectileClientMuzzle = ClientMuzzle;
					ProjectileAimDirection = AimDirection;
					ProjectilePathDistanceCm = PathDistanceCm;
					UE_LOG(
						LogTemp,
						Display,
						TEXT("RED_DEF0003_FIELD_MP_PROJECTILE_RPC_SUBMIT pass=1 clientOriginatedRPC=1 localRole=%d remoteRole=%d netMode=%d sequence=%u serverMuzzle=%s clientMuzzle=%s muzzleParityCm=%.2f aim=%s pathHit=%s pathDistanceCm=%.1f localProxyOre=%.0f"),
						static_cast<int32>(
							Players.RemoteClientPawn->GetLocalRole()),
						static_cast<int32>(
							Players.RemoteClientPawn->GetRemoteRole()),
						static_cast<int32>(Worlds.Client->GetNetMode()),
						ProjectileFireSequence,
						*ServerMuzzle.ToCompactString(),
						*ClientMuzzle.ToCompactString(),
						MuzzleParityCm,
						*AimDirection.ToCompactString(),
						*GetNameSafe(PathHit.GetActor()),
						PathDistanceCm,
						ProxyTarget->OreRemaining);
					return false;
				}

				for (TActorIterator<ARedBolt> It(Worlds.Server); It; ++It)
				{
					ARedBolt* Bolt = *It;
					if (IsValid(Bolt)
						&& Bolt->HasAuthority()
						&& Bolt->GetOwner() == Players.RemoteServerPawn
						&& Bolt->GetInstigator()
							== Players.RemoteServerPawn)
					{
						bSawAuthorityProjectile = true;
						ProjectileAuthorityBoltSpeed =
							FMath::Max(
								ProjectileAuthorityBoltSpeed,
								Bolt->GetVelocity().Size());
					}
				}
				for (TActorIterator<ARedBolt> It(Worlds.Client); It; ++It)
				{
					ARedBolt* Bolt = *It;
					if (IsValid(Bolt)
						&& !Bolt->HasAuthority()
						&& Bolt->GetOwner() == Players.RemoteClientPawn
						&& Bolt->GetInstigator()
							== Players.RemoteClientPawn)
					{
						bSawClientProjectile = true;
					}
				}

				const float AuthorityExtracted =
					InitialCapacity - AuthorityTarget->OreRemaining;
				if (AuthorityExtracted > ExpectedProjectileExtraction + 0.5f)
				{
					return Fail(FString::Printf(
						TEXT("more than one projectile extraction observed: %.1f"),
						AuthorityExtracted));
				}
				const bool bDeliveryPassed =
					bSawAuthorityProjectile
					&& bSawClientProjectile
					&& FMath::IsNearlyEqual(
						AuthorityExtracted,
						ExpectedProjectileExtraction)
					&& FMath::IsNearlyEqual(
						ProxyTarget->OreRemaining,
						AuthorityTarget->OreRemaining)
					&& AuthorityTarget->DepletionState.Phase
						== ERedMineableAsteroidDepletionPhase::Active
					&& ProxyTarget->DepletionState.Phase
						== ERedMineableAsteroidDepletionPhase::Active
					&& AuthorityTarget->GetActorEnableCollision()
					&& ProxyTarget->GetActorEnableCollision()
					&& CountReceipts(Worlds.Server, AuthorityTarget) == 0
					&& CountReceipts(Worlds.Client, ProxyTarget) == 0
					&& Players.RemoteServerPawn->ResIron
						== InitialRemoteIron
					&& Players.RemoteClientPawn->ResIron
						== InitialRemoteIron
					&& Players.HostPawn->ResIron == InitialHostIron
					&& CountOtherPristineMembers(Worlds.Server, TargetId)
						== MineableCount - 1;
				if (!bDeliveryPassed)
				{
					return false;
				}

				ProjectileExtracted = AuthorityExtracted;
				UE_LOG(
					LogTemp,
					Display,
					TEXT("RED_DEF0003_FIELD_MP_PROJECTILE_DELIVERY pass=1 clientOriginatedRPC=1 projectileDelivery=1 authorityBolt=1 remoteClientBolt=1 ownerInstigatorParity=1 stableId=%s sequence=%u oreBefore=%.0f oreAfter=%.0f/%.0f extracted=%.0f boltSpeedCmPerSec=%.1f pathDistanceCm=%.1f elapsed=%.3f pristinePeers=%d"),
					*TargetId.ToString(),
					ProjectileFireSequence,
					InitialCapacity,
					AuthorityTarget->OreRemaining,
					ProxyTarget->OreRemaining,
					ProjectileExtracted,
					ProjectileAuthorityBoltSpeed,
					ProjectilePathDistanceCm,
					Now - ProjectileRPCSubmittedAtSeconds,
					CountOtherPristineMembers(
						Worlds.Server,
						TargetId));
				Advance(EStage::SubmitHits, Now);
				return false;
			}

			bool SubmitHits(
				const FWorldPair& Worlds,
				const FPlayerPair& Players,
				const double Now)
			{
				ARedMineableAsteroid* Target = ServerTarget.Get();
				if (!Worlds.Server
					|| !Target
					|| !Players.HostPawn
					|| !Players.RemoteServerPawn
					|| !PlayerIdentitiesMatch(Players))
				{
					return Fail(TEXT("players or actual field target invalid at hit barrier"));
				}
				if (!bAudioRecordingStarted
					|| Now - AudioRecordingStartedAtSeconds < 0.25)
				{
					return false;
				}
				if (!FMath::IsNearlyEqual(
						ProjectileExtracted,
						ExpectedProjectileExtraction)
					|| !FMath::IsNearlyEqual(
						Target->OreRemaining,
						InitialCapacity - ProjectileExtracted))
				{
					return Fail(TEXT(
						"projectile extraction was not preserved at direct-hit barrier"));
				}

				float TotalExtracted = ProjectileExtracted;
				float DirectExtracted = 0.f;
				for (int32 HitIndex = 0; HitIndex < 5; ++HitIndex)
				{
					DirectExtracted += Target->RegisterMiningHit(
						55.f,
						Players.RemoteServerPawn);
				}
				const uint64 FrameBefore = GFrameCounter;
				const float RemoteFinalExtracted =
					Target->RegisterMiningHit(55.f, Players.RemoteServerPawn);
				const float HostRejected =
					Target->RegisterMiningHit(55.f, Players.HostPawn);
				const uint64 FrameAfter = GFrameCounter;
				DirectExtracted += RemoteFinalExtracted;
				TotalExtracted += DirectExtracted;

				const int32 HostDelta =
					Players.HostPawn->ResIron - InitialHostIron;
				const int32 RemoteDelta =
					Players.RemoteServerPawn->ResIron - InitialRemoteIron;
				const int32 AggregateDelta = HostDelta + RemoteDelta;
				const bool bPassed =
					FrameBefore == FrameAfter
					&& FMath::IsNearlyEqual(TotalExtracted, InitialCapacity)
					&& FMath::IsNearlyEqual(RemoteFinalExtracted, 870.f)
					&& FMath::IsNearlyZero(HostRejected)
					&& AggregateDelta == 6 && RemoteDelta == 6 && HostDelta == 0
					&& FMath::IsNearlyZero(Target->OreRemaining)
					&& Target->DepletionState.Phase
						== ERedMineableAsteroidDepletionPhase::Depleting
					&& Target->DepletionState.Sequence == 1
					&& !Target->GetActorEnableCollision()
					&& !Target->IsHidden()
					&& CountReceipts(Worlds.Server, Target) == 1
					&& CountOtherPristineMembers(Worlds.Server, TargetId)
						== MineableCount - 1;
				UE_LOG(
					LogTemp,
					Display,
					TEXT("RED_DEF0003_FIELD_MP_DEPLETION_HITS pass=%d sameServerFrame=%d frame=%llu acceptedHits=7 projectileHits=1 directAcceptedHits=6 projectileExtracted=%.0f directExtracted=%.0f totalExtracted=%.0f finalRemote=%.0f hostRejected=%.0f aggregateDelta=%d remoteDelta=%d hostDelta=%d phase=%d sequence=%u receipt=%d pristinePeers=%d"),
					bPassed ? 1 : 0,
					FrameBefore == FrameAfter ? 1 : 0,
					FrameAfter,
					ProjectileExtracted,
					DirectExtracted,
					TotalExtracted,
					RemoteFinalExtracted,
					HostRejected,
					AggregateDelta,
					RemoteDelta,
					HostDelta,
					static_cast<int32>(Target->DepletionState.Phase),
					Target->DepletionState.Sequence,
					CountReceipts(Worlds.Server, Target),
					CountOtherPristineMembers(Worlds.Server, TargetId));
				if (!bPassed)
				{
					return Fail(TEXT("actual-field same-frame depletion/reward idempotence failed"));
				}

				Advance(EStage::AwaitTransition, Now);
				return false;
			}

			bool AwaitTransition(
				const FWorldPair& Worlds,
				const FPlayerPair& Players,
				const double Now)
			{
				if (StageTimedOut(Now))
				{
					return Fail(TEXT("remote actual-field transition/HUD parity timeout"));
				}
				ARedMineableAsteroid* AuthorityTarget = ServerTarget.Get();
				ARedMineableAsteroid* ProxyTarget = ClientTarget.Get();
				if (!AuthorityTarget
					|| !ProxyTarget
					|| !PinRemoteView(Players))
				{
					return false;
				}
				if (AuthorityTarget->DepletionState.Phase
					== ERedMineableAsteroidDepletionPhase::Depleted)
				{
					return Fail(TEXT("authority completed before remote transition acceptance"));
				}

				const int32 ServerReceipts =
					CountReceipts(Worlds.Server, AuthorityTarget);
				const int32 ClientReceipts =
					CountReceipts(Worlds.Client, ProxyTarget);
				const FReceiptAudioStats ServerRewardAudio =
					GetReceiptAudioStats(Worlds.Server, AuthorityTarget);
				const FReceiptAudioStats ClientRewardAudio =
					GetReceiptAudioStats(Worlds.Client, ProxyTarget);
				const bool bRewardAudioPassed =
					ServerRewardAudio.Count == 1
					&& ClientRewardAudio.Count == 1
					&& ServerRewardAudio.SoundStarted == 0
					&& ClientRewardAudio.SoundStarted == 1
					&& ServerRewardAudio.ExpectedSoundAsset == 1
					&& ClientRewardAudio.ExpectedSoundAsset == 1
					&& ServerRewardAudio.LocallyControlledInstigator == 0
					&& ClientRewardAudio.LocallyControlledInstigator == 1;
				FString HUDText;
				bool bHUDVisible = false;
				const bool bHUDPassed =
					QueryRemoteHUD(Players, 6, HUDText, bHUDVisible)
					&& bHUDVisible
					&& HUDText == TEXT("IRON  +6");
				const bool bPassed =
					AuthorityTarget->GetStableMemberId() == TargetId
					&& ProxyTarget->GetStableMemberId() == TargetId
					&& AuthorityTarget->DepletionState.Phase
						== ERedMineableAsteroidDepletionPhase::Depleting
					&& ProxyTarget->DepletionState.Phase
						== ERedMineableAsteroidDepletionPhase::Depleting
					&& AuthorityTarget->DepletionState.Sequence == 1
					&& ProxyTarget->DepletionState.Sequence == 1
					&& FMath::IsNearlyZero(
						AuthorityTarget->OreRemaining)
					&& FMath::IsNearlyZero(ProxyTarget->OreRemaining)
					&& !AuthorityTarget->GetActorEnableCollision()
					&& !ProxyTarget->GetActorEnableCollision()
					&& !AuthorityTarget->IsHidden()
					&& !ProxyTarget->IsHidden()
					&& ServerReceipts == 1 && ClientReceipts == 1
					&& Players.RemoteServerPawn
					&& Players.RemoteServerPawn->ResIron
						== InitialRemoteIron + 6
					&& Players.RemoteClientPawn
					&& Players.RemoteClientPawn->ResIron
						== InitialRemoteIron + 6
					&& Players.HostPawn
					&& Players.HostPawn->ResIron == InitialHostIron
					&& CountOtherPristineMembers(
						Worlds.Server,
						TargetId)
						== MineableCount - 1
					&& bHUDPassed
					&& bRewardAudioPassed;
				if (!bPassed)
				{
					return false;
				}

				FString WindowTitle;
				const FString Filename = FPaths::Combine(
					CaptureDirectory,
					TEXT("DEF0003_Field_MP_Depletion_Transition.png"));
				if (!CaptureRemoteClientWindow(Filename, WindowTitle))
				{
					return false;
				}

				UE_LOG(
					LogTemp,
					Display,
					TEXT("RED_DEF0003_FIELD_MP_DEPLETION_TRANSITION pass=1 phase=%d/%d sequence=%u/%u collision=%d/%d hidden=%d/%d receipt=%d/%d remoteIron=%d/%d hostIron=%d pristinePeers=%d hudText=\"%s\" rewardAudioStarted=%d/%d rewardAudioAsset=%d/%d rewardLocalInstigator=%d/%d capture=\"%s\""),
					static_cast<int32>(
						AuthorityTarget->DepletionState.Phase),
					static_cast<int32>(ProxyTarget->DepletionState.Phase),
					AuthorityTarget->DepletionState.Sequence,
					ProxyTarget->DepletionState.Sequence,
					AuthorityTarget->GetActorEnableCollision() ? 1 : 0,
					ProxyTarget->GetActorEnableCollision() ? 1 : 0,
					AuthorityTarget->IsHidden() ? 1 : 0,
					ProxyTarget->IsHidden() ? 1 : 0,
					ServerReceipts,
					ClientReceipts,
					Players.RemoteServerPawn->ResIron,
					Players.RemoteClientPawn->ResIron,
					Players.HostPawn->ResIron,
					CountOtherPristineMembers(Worlds.Server, TargetId),
					*HUDText.ReplaceCharWithEscapedChar(),
					ServerRewardAudio.SoundStarted,
					ClientRewardAudio.SoundStarted,
					ServerRewardAudio.ExpectedSoundAsset,
					ClientRewardAudio.ExpectedSoundAsset,
					ServerRewardAudio.LocallyControlledInstigator,
					ClientRewardAudio.LocallyControlledInstigator,
					*Filename);
				bRewardAudioRoutingAccepted = true;
				Advance(EStage::AwaitFinal, Now);
				return false;
			}

			bool AwaitFinal(
				const FWorldPair& Worlds,
				const FPlayerPair& Players,
				const double Now)
			{
				if (StageTimedOut(Now))
				{
					return Fail(TEXT("remote actual-field depleted/explosion parity timeout"));
				}
				ARedMineableAsteroid* AuthorityTarget = ServerTarget.Get();
				ARedMineableAsteroid* ProxyTarget = ClientTarget.Get();
				if (!AuthorityTarget
					|| !ProxyTarget
					|| !PinRemoteView(Players))
				{
					return false;
				}

				const FExplosionStats ServerExplosion =
					GetExplosionStats(Worlds.Server, AuthorityTarget);
				const FExplosionStats ClientExplosion =
					GetExplosionStats(Worlds.Client, ProxyTarget);
				const int32 ServerReceipts =
					CountReceipts(Worlds.Server, AuthorityTarget);
				const int32 ClientReceipts =
					CountReceipts(Worlds.Client, ProxyTarget);
				FString HUDText;
				bool bHUDVisible = false;
				const bool bHUDPassed =
					QueryRemoteHUD(Players, 6, HUDText, bHUDVisible)
					&& bHUDVisible
					&& HUDText == TEXT("IRON  +6");
				const bool bReady =
					AuthorityTarget->GetStableMemberId() == TargetId
					&& ProxyTarget->GetStableMemberId() == TargetId
					&& AuthorityTarget->DepletionState.Phase
						== ERedMineableAsteroidDepletionPhase::Depleted
					&& ProxyTarget->DepletionState.Phase
						== ERedMineableAsteroidDepletionPhase::Depleted
					&& AuthorityTarget->DepletionState.Sequence == 2
					&& ProxyTarget->DepletionState.Sequence == 2
					&& !AuthorityTarget->GetActorEnableCollision()
					&& !ProxyTarget->GetActorEnableCollision()
					&& AuthorityTarget->IsHidden()
					&& ProxyTarget->IsHidden()
					&& ServerExplosion.Count == 1
					&& ClientExplosion.Count == 1
					&& ClientExplosion.SimulatingDebris >= 8
					&& ServerExplosion.SoundStarted == 1
					&& ClientExplosion.SoundStarted == 1
					&& ServerExplosion.ExpectedSoundAsset == 1
					&& ClientExplosion.ExpectedSoundAsset == 1
					&& ServerReceipts == 1 && ClientReceipts == 1
					&& Players.RemoteServerPawn
					&& Players.RemoteServerPawn->ResIron
						== InitialRemoteIron + 6
					&& Players.RemoteClientPawn
					&& Players.RemoteClientPawn->ResIron
						== InitialRemoteIron + 6
					&& Players.HostPawn
					&& Players.HostPawn->ResIron == InitialHostIron
					&& CountOtherPristineMembers(
						Worlds.Server,
						TargetId)
						== MineableCount - 1
					&& TargetIdentityAndCutoffPass(AuthorityTarget, true)
					&& TargetIdentityAndCutoffPass(ProxyTarget, false)
					&& bHUDPassed;
				if (!bReady)
				{
					return false;
				}

				const float PostHit =
					AuthorityTarget->RegisterMiningHit(
						55.f,
						Players.HostPawn);
				if (!FMath::IsNearlyZero(PostHit))
				{
					return Fail(TEXT("post-depletion hit extracted additional ore"));
				}

				ARedShipExplosionFX* ClientExplosionActor =
					FindOwnedExplosion(Worlds.Client, ProxyTarget);
				ACameraActor* Camera = RemoteCamera.Get();
				if (!ClientExplosionActor || !Camera)
				{
					return false;
				}

				FVector ViewTangent;
				FVector ViewBitangent;
				RadialOut.FindBestAxisVectors(ViewTangent, ViewBitangent);
				VisualOrigin = ClientExplosionActor->GetActorLocation();
				VisualCameraLocation =
					VisualOrigin
					+ ViewTangent.GetSafeNormal()
						* DestructionCameraDistanceCm;
				VisualCameraRotation =
					(VisualOrigin - VisualCameraLocation).Rotation();
				Camera->SetActorLocationAndRotation(
					VisualCameraLocation,
					VisualCameraRotation,
					false,
					nullptr,
					ETeleportType::TeleportPhysics);
				Camera->GetCameraComponent()->SetFieldOfView(
					DestructionCameraFOVDegrees);
				if (!PinRemoteView(Players))
				{
					return false;
				}

				ClientExplosionHandle = ClientExplosionActor;
				bExplosionAudioRoutingAccepted = true;
				PostDepletionRejected = PostHit;
				VisualCameraReadyAtSeconds = Now;
				VisualCameraReadyFrame = GFrameCounter;
				UE_LOG(
					LogTemp,
					Display,
					TEXT("RED_DEF0003_FIELD_MP_DEPLETION_VISUAL_FRAME pass=1 origin=%s camera=%s distanceCm=%.0f fov=%.0f readyFrame=%llu postHit=%.0f hudText=\"%s\" explosionAudioStarted=%d/%d explosionAudioAsset=%d/%d"),
					*VisualOrigin.ToCompactString(),
					*VisualCameraLocation.ToCompactString(),
					FVector::Distance(VisualOrigin, VisualCameraLocation),
					DestructionCameraFOVDegrees,
					VisualCameraReadyFrame,
					PostHit,
					*HUDText.ReplaceCharWithEscapedChar(),
					ServerExplosion.SoundStarted,
					ClientExplosion.SoundStarted,
					ServerExplosion.ExpectedSoundAsset,
					ClientExplosion.ExpectedSoundAsset);
				Advance(EStage::AwaitDestructionPixels, Now);
				return false;
			}

			bool AwaitDestructionPixels(
				const FWorldPair& Worlds,
				const FPlayerPair& Players,
				const double Now)
			{
				if (StageTimedOut(Now))
				{
					return Fail(TEXT(
						"Client 1 destruction-pixel capture timed out"));
				}

				ARedMineableAsteroid* AuthorityTarget = ServerTarget.Get();
				ARedMineableAsteroid* ProxyTarget = ClientTarget.Get();
				ARedShipExplosionFX* Explosion =
					ClientExplosionHandle.Get();
				ACameraActor* Camera = RemoteCamera.Get();
				if (!AuthorityTarget
					|| !ProxyTarget
					|| !Explosion
					|| !Camera
					|| !Players.RemoteClientController)
				{
					return Fail(TEXT(
						"destruction-pixel actors became invalid"));
				}

				Camera->SetActorLocationAndRotation(
					VisualCameraLocation,
					VisualCameraRotation,
					false,
					nullptr,
					ETeleportType::TeleportPhysics);
				Camera->GetCameraComponent()->SetFieldOfView(
					DestructionCameraFOVDegrees);
				if (!PinRemoteView(Players))
				{
					return false;
				}

				const FExplosionStats ServerExplosion =
					GetExplosionStats(Worlds.Server, AuthorityTarget);
				const FExplosionStats ClientExplosionStats =
					GetExplosionStats(Worlds.Client, ProxyTarget);
				const FReceiptAudioStats ServerRewardAudio =
					GetReceiptAudioStats(Worlds.Server, AuthorityTarget);
				const FReceiptAudioStats ClientRewardAudio =
					GetReceiptAudioStats(Worlds.Client, ProxyTarget);
				FString HUDText;
				bool bHUDVisible = false;
				const bool bPersistentRuntimePass =
					AuthorityTarget->DepletionState.Phase
						== ERedMineableAsteroidDepletionPhase::Depleted
					&& ProxyTarget->DepletionState.Phase
						== ERedMineableAsteroidDepletionPhase::Depleted
					&& AuthorityTarget->DepletionState.Sequence == 2
					&& ProxyTarget->DepletionState.Sequence == 2
					&& AuthorityTarget->IsHidden()
					&& ProxyTarget->IsHidden()
					&& !AuthorityTarget->GetActorEnableCollision()
					&& !ProxyTarget->GetActorEnableCollision()
					&& TargetIdentityAndCutoffPass(AuthorityTarget, true)
					&& TargetIdentityAndCutoffPass(ProxyTarget, false)
					&& ServerExplosion.Count == 1
					&& ClientExplosionStats.Count == 1
					&& ClientExplosionStats.SimulatingDebris == 12
					&& ServerExplosion.SoundStarted == 1
					&& ClientExplosionStats.SoundStarted == 1
					&& ServerExplosion.ExpectedSoundAsset == 1
					&& ClientExplosionStats.ExpectedSoundAsset == 1
					&& CountReceipts(Worlds.Server, AuthorityTarget) == 1
					&& CountReceipts(Worlds.Client, ProxyTarget) == 1
					&& ServerRewardAudio.SoundStarted == 0
					&& ClientRewardAudio.SoundStarted == 1
					&& ServerRewardAudio.ExpectedSoundAsset == 1
					&& ClientRewardAudio.ExpectedSoundAsset == 1
					&& ServerRewardAudio.LocallyControlledInstigator == 0
					&& ClientRewardAudio.LocallyControlledInstigator == 1
					&& CountOtherPristineMembers(
						Worlds.Server,
						TargetId) == MineableCount - 1
					&& Players.RemoteServerPawn
					&& Players.RemoteServerPawn->ResIron
						== InitialRemoteIron + 6
					&& Players.RemoteClientPawn
					&& Players.RemoteClientPawn->ResIron
						== InitialRemoteIron + 6
					&& Players.HostPawn
					&& Players.HostPawn->ResIron == InitialHostIron
					&& QueryRemoteHUD(Players, 6, HUDText, bHUDVisible)
					&& !bHUDVisible
					&& HUDText == TEXT("IRON  +6")
					&& bRewardAudioRoutingAccepted
					&& bExplosionAudioRoutingAccepted
					&& FMath::IsNearlyZero(PostDepletionRejected);
				if (!bPersistentRuntimePass)
				{
					return Fail(TEXT(
						"accepted runtime state changed during pixel capture"));
				}

				const double VisualElapsed =
					Now - VisualCameraReadyAtSeconds;
				if (GFrameCounter < VisualCameraReadyFrame + 2)
				{
					return false;
				}

				if (!bFlashCaptured
					&& VisualElapsed >= FlashCaptureDelaySeconds)
				{
					FVector2D ExplosionScreen;
					if (!Players.RemoteClientController->
							ProjectWorldLocationToScreen(
								VisualOrigin,
								ExplosionScreen,
								true))
					{
						return Fail(TEXT(
							"explosion origin did not project into Client 1"));
					}

					const FString Filename = FPaths::Combine(
						CaptureDirectory,
						TEXT("DEF0003_Field_MP_Depletion_Explosion.png"));
					if (!CaptureRemoteClientViewport(
							Players.RemoteClientController,
							Filename,
							FlashCapture))
					{
						return false;
					}
					if (FlashCapture.Size.X < 1200
						|| FlashCapture.Size.Y < 700)
					{
						return Fail(FString::Printf(
							TEXT("Client 1 viewport is %dx%d, expected at least 1200x700"),
							FlashCapture.Size.X,
							FlashCapture.Size.Y));
					}

					const FVector2D ViewportCenter(
						FlashCapture.Size.X * 0.5f,
						FlashCapture.Size.Y * 0.5f);
					if (FMath::Abs(
							ExplosionScreen.X - ViewportCenter.X)
							> FlashCapture.Size.X * 0.1f
						|| FMath::Abs(
							ExplosionScreen.Y - ViewportCenter.Y)
							> FlashCapture.Size.Y * 0.1f)
					{
						return Fail(TEXT(
							"explosion origin is outside central 20 percent of Client 1"));
					}

					FlashLuminousPixels =
						CountCentralFlashPixels(
							FlashCapture,
							ExplosionScreen,
							false);
					FlashWarmPixels =
						CountCentralFlashPixels(
							FlashCapture,
							ExplosionScreen,
							true);
					if (FlashLuminousPixels < 1000
						|| FlashWarmPixels < 100)
					{
						return Fail(FString::Printf(
							TEXT("flash pixel gate failed luminous=%d warm=%d"),
							FlashLuminousPixels,
							FlashWarmPixels));
					}

					bFlashCaptured = true;
					UE_LOG(
						LogTemp,
						Display,
						TEXT("RED_DEF0003_FIELD_MP_DEPLETION_FLASH_PIXELS pass=1 elapsed=%.3f frameDelta=%llu viewport=%dx%d center=(%.1f,%.1f) luminous=%d warm=%d capture=\"%s\""),
						VisualElapsed,
						GFrameCounter - VisualCameraReadyFrame,
						FlashCapture.Size.X,
						FlashCapture.Size.Y,
						ExplosionScreen.X,
						ExplosionScreen.Y,
						FlashLuminousPixels,
						FlashWarmPixels,
						*Filename);
					return false;
				}

				if (!bDebrisCaptureAComplete
					&& VisualElapsed >= DebrisCaptureDelaySeconds)
				{
					const FString Filename = FPaths::Combine(
						CaptureDirectory,
						TEXT("DEF0003_Field_MP_Depletion_Debris_A.png"));
					if (!CaptureRemoteClientViewport(
							Players.RemoteClientController,
							Filename,
							DebrisCaptureA))
					{
						return false;
					}
					DebrisStatsA = GetDebrisProjectionStats(
						Explosion,
						Players.RemoteClientController,
						&DebrisCaptureA);
					bDebrisCaptureAComplete = true;
					UE_LOG(
						LogTemp,
						Display,
						TEXT("RED_DEF0003_FIELD_MP_DEPLETION_DEBRIS_A elapsed=%.3f sim=%d recent=%d projected=%d hot=%d hotProjected=%d hotPixelMatched=%d maxWidthPx=%.2f capture=\"%s\""),
						VisualElapsed,
						DebrisStatsA.Simulating,
						DebrisStatsA.RecentlyRendered,
						DebrisStatsA.ProjectedPixelSized,
						DebrisStatsA.HotMaterialPieces,
						DebrisStatsA.HotProjectedPixelSized,
						DebrisStatsA.HotPixelMatched,
						DebrisStatsA.MaxProjectedWidthPixels,
						*Filename);
					return false;
				}

				if (!bFlashCaptured
					|| !bDebrisCaptureAComplete
					|| VisualElapsed < DebrisMotionCaptureDelaySeconds)
				{
					return false;
				}

				const FString DebrisBFilename = FPaths::Combine(
					CaptureDirectory,
					TEXT("DEF0003_Field_MP_Depletion_Debris_B.png"));
				FViewportCapture DebrisCaptureB;
				if (!CaptureRemoteClientViewport(
						Players.RemoteClientController,
						DebrisBFilename,
						DebrisCaptureB))
				{
					return false;
				}
				const FDebrisProjectionStats DebrisStatsB =
					GetDebrisProjectionStats(
						Explosion,
						Players.RemoteClientController,
						&DebrisCaptureB);
				const int32 MovingHotPieces =
					CountMovingHotPieces(DebrisStatsA, DebrisStatsB);
				const FIntRect CentralMotionRect(
					FIntPoint(
						DebrisCaptureB.Size.X / 2 - 256,
						DebrisCaptureB.Size.Y / 2 - 256),
					FIntPoint(
						DebrisCaptureB.Size.X / 2 + 256,
						DebrisCaptureB.Size.Y / 2 + 256));
				const int32 DebrisChangedPixels =
					CountChangedPixelsInRect(
						DebrisCaptureA,
						DebrisCaptureB,
						CentralMotionRect);
				const FVector2D LateCenter(
					DebrisCaptureB.Size.X * 0.5f,
					DebrisCaptureB.Size.Y * 0.5f);
				const int32 LateLuminousPixels =
					CountCentralFlashPixels(
						DebrisCaptureB,
						LateCenter,
						false);
				const int32 LateWarmPixels =
					CountCentralFlashPixels(
						DebrisCaptureB,
						LateCenter,
						true);
				const bool bDebrisPixelPass =
					DebrisCaptureA.Size == FlashCapture.Size
					&& DebrisCaptureB.Size == FlashCapture.Size
					&& DebrisStatsA.Simulating == 12
					&& DebrisStatsB.Simulating == 12
					&& DebrisStatsA.RecentlyRendered >= 6
					&& DebrisStatsB.RecentlyRendered >= 6
					&& DebrisStatsA.ProjectedPixelSized >= 6
					&& DebrisStatsB.ProjectedPixelSized >= 6
					&& DebrisStatsA.HotMaterialPieces == 4
					&& DebrisStatsB.HotMaterialPieces == 4
					&& DebrisStatsA.HotProjectedPixelSized >= 3
					&& DebrisStatsB.HotProjectedPixelSized >= 3
					&& DebrisStatsA.HotPixelMatched >= 3
					&& DebrisStatsB.HotPixelMatched >= 3
					&& MovingHotPieces >= 3
					&& DebrisChangedPixels >= 256
					&& LateLuminousPixels
						< FlashLuminousPixels * 3 / 4
					&& LateWarmPixels < FlashWarmPixels * 3 / 4;
				UE_LOG(
					LogTemp,
					Display,
					TEXT("RED_DEF0003_FIELD_MP_DEPLETION_DEBRIS_PIXELS pass=%d elapsed=%.3f sim=%d/%d recent=%d/%d projected=%d/%d hot=%d/%d hotProjected=%d/%d hotPixelMatched=%d/%d movingHot=%d changedPixels=%d flashDecayLuminous=%d/%d flashDecayWarm=%d/%d maxWidthPx=%.2f/%.2f capture=\"%s\""),
					bDebrisPixelPass ? 1 : 0,
					VisualElapsed,
					DebrisStatsA.Simulating,
					DebrisStatsB.Simulating,
					DebrisStatsA.RecentlyRendered,
					DebrisStatsB.RecentlyRendered,
					DebrisStatsA.ProjectedPixelSized,
					DebrisStatsB.ProjectedPixelSized,
					DebrisStatsA.HotMaterialPieces,
					DebrisStatsB.HotMaterialPieces,
					DebrisStatsA.HotProjectedPixelSized,
					DebrisStatsB.HotProjectedPixelSized,
					DebrisStatsA.HotPixelMatched,
					DebrisStatsB.HotPixelMatched,
					MovingHotPieces,
					DebrisChangedPixels,
					FlashLuminousPixels,
					LateLuminousPixels,
					FlashWarmPixels,
					LateWarmPixels,
					DebrisStatsA.MaxProjectedWidthPixels,
					DebrisStatsB.MaxProjectedWidthPixels,
					*DebrisBFilename);
				if (!bDebrisPixelPass)
				{
					return Fail(TEXT(
						"Client 1 debris projection/pixel/motion gate failed"));
				}

				UE_LOG(
					LogTemp,
					Display,
					TEXT("RED_DEF0003_FIELD_MP_DEPLETION_FINAL pass=1 phase=%d/%d sequence=%u/%u explosion=%d/%d debris=%d/%d receipt=1/1 postHit=%.0f remoteIron=%d/%d hostIron=%d pristinePeers=%d hudText=\"%s\" rewardAudioStarted=%d/%d explosionAudioStarted=%d/%d flashLuminous=%d flashWarm=%d debrisHotPixels=%d/%d movingHot=%d changedPixels=%d lateLuminous=%d lateWarm=%d"),
					static_cast<int32>(
						AuthorityTarget->DepletionState.Phase),
					static_cast<int32>(ProxyTarget->DepletionState.Phase),
					AuthorityTarget->DepletionState.Sequence,
					ProxyTarget->DepletionState.Sequence,
					ServerExplosion.Count,
					ClientExplosionStats.Count,
					ServerExplosion.SimulatingDebris,
					ClientExplosionStats.SimulatingDebris,
					PostDepletionRejected,
					Players.RemoteServerPawn->ResIron,
					Players.RemoteClientPawn->ResIron,
					Players.HostPawn->ResIron,
					CountOtherPristineMembers(Worlds.Server, TargetId),
					*HUDText.ReplaceCharWithEscapedChar(),
					ServerRewardAudio.SoundStarted,
					ClientRewardAudio.SoundStarted,
					ServerExplosion.SoundStarted,
					ClientExplosionStats.SoundStarted,
					FlashLuminousPixels,
					FlashWarmPixels,
					DebrisStatsA.HotPixelMatched,
					DebrisStatsB.HotPixelMatched,
					MovingHotPieces,
					DebrisChangedPixels,
					LateLuminousPixels,
					LateWarmPixels);

				if (!bAudioRecordingStarted || bAudioRecordingStopped)
				{
					return Fail(TEXT("audio recording state invalid at final capture"));
				}
				UAudioMixerBlueprintLibrary::StopRecordingOutput(
					Worlds.Client,
					EAudioRecordingExportType::WavFile,
					TEXT("DEF0003_Field_MP_Depletion_Audio"),
					CaptureDirectory);
				bAudioRecordingStopped = true;
				AudioRecordingStoppedAtSeconds = Now;
				Advance(EStage::AwaitAudioFile, Now);
				return false;
			}

			bool AwaitAudioFile(
				const FWorldPair& Worlds,
				const FPlayerPair& Players,
				const double Now)
			{
				if (StageTimedOut(Now))
				{
					return Fail(FString::Printf(
						TEXT("WAV output timed out path=%s size=%lld"),
						*AudioCaptureFilename,
						LastAudioFileSize));
				}
				if (!Worlds.Client
					|| !Players.RemoteClientPawn
					|| !bAudioRecordingStopped
					|| !bRewardAudioRoutingAccepted
					|| !bExplosionAudioRoutingAccepted)
				{
					return false;
				}

				const int64 CurrentSize =
					IFileManager::Get().FileSize(*AudioCaptureFilename);
				if (CurrentSize <= 44)
				{
					return false;
				}
				if (CurrentSize != LastAudioFileSize)
				{
					LastAudioFileSize = CurrentSize;
					AudioFileStableAtSeconds = Now;
					return false;
				}
				if (Now - AudioFileStableAtSeconds < 0.25)
				{
					return false;
				}

				const FWavStats Wav = AnalyzePcmWav(AudioCaptureFilename);
				const double DurationSeconds =
					Wav.bValid && Wav.Channels > 0 && Wav.SampleRate > 0
						? static_cast<double>(Wav.SampleCount)
							/ static_cast<double>(Wav.Channels * Wav.SampleRate)
						: 0.0;
				const bool bWavPassed =
					Wav.bValid
					&& Wav.Channels >= 1
					&& Wav.SampleRate >= 22050
					&& Wav.BitsPerSample == 16
					&& DurationSeconds >= MinimumCapturedAudioSeconds
					&& Wav.PeakAbsoluteSample >= 256
					&& Wav.ActiveSampleCount >= 1000
					&& Wav.Rms >= 1.0;
				UE_LOG(
					LogTemp,
					Display,
					TEXT("RED_DEF0003_FIELD_MP_DEPLETION_AUDIO_CAPTURE pass=%d path=\"%s\" bytes=%lld channels=%d sampleRate=%d bits=%d duration=%.3f samples=%lld activeSamples=%lld peak=%d rms=%.3f recordingElapsed=%.3f writeElapsed=%.3f"),
					bWavPassed ? 1 : 0,
					*AudioCaptureFilename,
					CurrentSize,
					Wav.Channels,
					Wav.SampleRate,
					Wav.BitsPerSample,
					DurationSeconds,
					Wav.SampleCount,
					Wav.ActiveSampleCount,
					Wav.PeakAbsoluteSample,
					Wav.Rms,
					AudioRecordingStoppedAtSeconds
						- AudioRecordingStartedAtSeconds,
					Now - AudioRecordingStoppedAtSeconds);
				if (!bWavPassed)
				{
					return Fail(TEXT("master-output WAV validity/non-silence gate failed"));
				}

				RestorePIEAudioOverride();
				UE_LOG(
					LogTemp,
					Display,
					TEXT("RED_DEF0003_FIELD_MP_DEPLETION_RESULT acceptancePass=1 evidenceClass=automation topology=in_process_two_client actualFieldMember=1 stableIdentity=1 exactOnceReward=1 resourceTotalsParity=1 transientMiningReceipt=1 persistentResourceTally=0 rewardAudioOwnerComponent=1 destructionAudioComponents=1 separatePIEAudioDevices=1 pieAudioDeviceUnmuted=1 clientMixerWavNonSilent=1 destructionPixels=1 flashPixels=1 debrisPixels=1 debrisMotion=1 pristinePeers=23 cutoffOverridden=0 testTeleport=1 playerControlledTravel=0 projectileDelivery=1 clientOriginatedRPC=1 physicalFireInput=0 independentPlayerListening=0 mixQuality=0 packageAudio=0 steamTransport=0"));
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
			double VisualCameraReadyAtSeconds = 0.0;
			double AudioRecordingStartedAtSeconds = 0.0;
			double AudioRecordingStoppedAtSeconds = 0.0;
			double AudioFileStableAtSeconds = 0.0;
			uint64 VisualCameraReadyFrame = 0;
			const FName TargetId;
			int32 InitialHostIron = 0;
			int32 InitialRemoteStone = 0;
			int32 InitialRemoteIron = 0;
			int32 InitialRemoteCrystal = 0;
			float InitialCapacity = 0.f;
			FVector InitialScale = FVector::ZeroVector;
			FVector InitialTargetLocation = FVector::ZeroVector;
			FQuat InitialTargetRotation = FQuat::Identity;
			FVector RadialOut = FVector::ZeroVector;
			FVector ProjectileSurfacePoint = FVector::ZeroVector;
			FVector ProjectileAimPoint = FVector::ZeroVector;
			FVector ProjectileServerMuzzle = FVector::ZeroVector;
			FVector ProjectileClientMuzzle = FVector::ZeroVector;
			FVector ProjectileAimDirection = FVector::ZeroVector;
			FVector VisualOrigin = FVector::ZeroVector;
			FVector VisualCameraLocation = FVector::ZeroVector;
			FRotator VisualCameraRotation = FRotator::ZeroRotator;
			float ProjectileExtracted = 0.f;
			float ProjectileAuthorityBoltSpeed = 0.f;
			float ProjectilePathDistanceCm = 0.f;
			float PostDepletionRejected = 0.f;
			float ClientPrimaryVolume = 0.f;
			uint32 ServerAudioDeviceId = INDEX_NONE;
			uint32 ClientAudioDeviceId = INDEX_NONE;
			bool bFlashCaptured = false;
			bool bDebrisCaptureAComplete = false;
			bool bAudioRecordingStarted = false;
			bool bAudioRecordingStopped = false;
			bool bRewardAudioRoutingAccepted = false;
			bool bExplosionAudioRoutingAccepted = false;
			bool bProjectileRPCSubmitted = false;
			bool bSawAuthorityProjectile = false;
			bool bSawClientProjectile = false;
			bool bPIEAudioOverrideRequested = false;
			bool bPIEAudioOverrideWasApplied = false;
			bool bPIEAudioUnmutedReady = false;
			int32 FlashLuminousPixels = 0;
			int32 FlashWarmPixels = 0;
			int64 LastAudioFileSize = -1;
			double ProjectileRPCSubmittedAtSeconds = 0.0;
			FString CaptureDirectory;
			FString AudioCaptureFilename;
			FViewportCapture FlashCapture;
			FViewportCapture DebrisCaptureA;
			FDebrisProjectionStats DebrisStatsA;
			TWeakObjectPtr<ARedMineableAsteroid> ServerTarget;
			TWeakObjectPtr<ARedMineableAsteroid> ClientTarget;
			TWeakObjectPtr<ARedShipExplosionFX> ClientExplosionHandle;
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
					if (AcceptanceState->bRestoreAllowBackgroundAudio)
						{
							if (ULevelEditorMiscSettings* MiscSettings =
								GetMutableDefault<ULevelEditorMiscSettings>())
								{
									MiscSettings->bAllowBackgroundAudio =
										AcceptanceState->
											bOriginalAllowBackgroundAudio;
								}
							AcceptanceState->bRestoreAllowBackgroundAudio = false;
						}
					AcceptanceState->bPIEEnded = true;
					UE_LOG(
						LogTemp,
						Display,
						TEXT("RED_DEF0003_FIELD_MP_DEPLETION_COMPLETE pieEnded=1 acceptancePass=%d"),
						AcceptanceState->bAccepted ? 1 : 0);
					return true;
				}
				if (FPlatformTime::Seconds() - StartedAtSeconds > 15.0)
				{
					Test->AddError(TEXT(
						"DEF-0003 actual-field two-client PIE did not end within 15 seconds."));
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
		FRedDEF0003ActualFieldTwoClientDepletionPIETest,
		"RedMMO.Mining.DEF0003.ActualFieldTwoClientDepletionPIE",
		EAutomationTestFlags::EditorContext
			| EAutomationTestFlags::ProductFilter)

	bool FRedDEF0003ActualFieldTwoClientDepletionPIETest::RunTest(
		const FString& Parameters)
	{
		(void)Parameters;
		if (!FApp::CanEverRender()
			|| FParse::Param(FCommandLine::Get(), TEXT("nullrhi")))
		{
			AddError(TEXT(
				"DEF-0003 actual-field two-client visual acceptance requires a rendered non-NullRHI editor."));
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
		FIntProperty* PrimaryClientProperty =
			FindFProperty<FIntProperty>(
				ULevelEditorPlaySettings::StaticClass(),
				TEXT("PrimaryPIEClientIndex"));
		if (!PrimaryClientProperty)
		{
			AddError(TEXT(
				"Could not resolve PrimaryPIEClientIndex on UE 5.8 PIE settings."));
			return false;
		}
		PrimaryClientProperty->SetPropertyValue_InContainer(PlaySettings, 1);
		if (PlaySettings->GetPrimaryPIEClientIndex() != 1)
		{
			AddError(TEXT("Could not select Client 1 as the primary PIE window."));
			return false;
		}
		PlaySettings->SetRunUnderOneProcess(true);
		PlaySettings->bLaunchSeparateServer = false;
		FBoolProperty* EnableGameSoundProperty =
			FindFProperty<FBoolProperty>(
				ULevelEditorPlaySettings::StaticClass(),
				TEXT("EnableGameSound"));
		FBoolProperty* PerPlayerAudioProperty =
			FindFProperty<FBoolProperty>(
				ULevelEditorPlaySettings::StaticClass(),
				TEXT("CreateAudioDeviceForEveryPlayer"));
		FBoolProperty* SoloAudioProperty =
			FindFProperty<FBoolProperty>(
				ULevelEditorPlaySettings::StaticClass(),
				TEXT("SoloAudioInFirstPIEClient"));
		if (!EnableGameSoundProperty
			|| !PerPlayerAudioProperty
			|| !SoloAudioProperty)
		{
			AddError(TEXT(
				"Could not resolve UE 5.8 PIE audio settings."));
			return false;
		}
		EnableGameSoundProperty->SetPropertyValue_InContainer(
			PlaySettings,
			true);
		PerPlayerAudioProperty->SetPropertyValue_InContainer(
			PlaySettings,
			true);
		SoloAudioProperty->SetPropertyValue_InContainer(
			PlaySettings,
			false);
		if (!EnableGameSoundProperty->GetPropertyValue_InContainer(PlaySettings)
			|| !PlaySettings->IsCreateAudioDeviceForEveryPlayer()
			|| SoloAudioProperty->GetPropertyValue_InContainer(PlaySettings))
		{
			AddError(TEXT(
				"Could not enable a distinct audio device for each PIE player."));
			return false;
		}
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
		if (ULevelEditorMiscSettings* MiscSettings =
			GetMutableDefault<ULevelEditorMiscSettings>())
			{
				AcceptanceState->bOriginalAllowBackgroundAudio =
					MiscSettings->bAllowBackgroundAudio;
				if (!MiscSettings->bAllowBackgroundAudio)
					{
						MiscSettings->bAllowBackgroundAudio = true;
						AcceptanceState->bRestoreAllowBackgroundAudio = true;
					}
			}
		else
			{
				AddError(TEXT(
					"Could not resolve UE 5.8 level-editor audio settings."));
				return false;
			}
		ADD_LATENT_AUTOMATION_COMMAND(
			FEditorLoadMap(Private::ProductionMap));
		ADD_LATENT_AUTOMATION_COMMAND(
			FWaitForShadersToFinishCompiling());
		ADD_LATENT_AUTOMATION_COMMAND(
			FStartPIEForAutomationCommand(RequestParams));
		ADD_LATENT_AUTOMATION_COMMAND(
			Private::FActualFieldTwoClientDepletionCommand(
				this,
				AcceptanceState));
		ADD_LATENT_AUTOMATION_COMMAND(FEndPlayMapCommand());
		ADD_LATENT_AUTOMATION_COMMAND(
			Private::FWaitForPIEEndCommand(this, AcceptanceState));
		return true;
	}
}

#endif // WITH_DEV_AUTOMATION_TESTS && WITH_EDITOR
