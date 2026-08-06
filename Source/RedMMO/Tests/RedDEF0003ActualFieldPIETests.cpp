#include "../RedGravityBodies.h"
#include "../RedHUD.h"
#include "../RedMineableAsteroid.h"
#include "../RedPlanetPresentationTuning.h"
#include "../RedPlayerCharacter.h"
#include "../RedResourcePickup.h"
#include "../RedShipExplosionFX.h"
#include "../RedSpaceScenery.h"

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
#include "Settings/LevelEditorPlaySettings.h"
#include "Tests/AutomationEditorCommon.h"
#include "Widgets/SWindow.h"

namespace RedMMO::DEF0003ActualFieldPIE
{
	namespace Private
	{
		constexpr TCHAR ProductionMap[] = TEXT("/Game/RedMMO/Maps/RedPlanetGen");
		constexpr int32 MineableSeed = 0x4F524531;
		constexpr int32 MineableCount = 24;
		constexpr int32 TargetOrdinal = 23;
		constexpr double ReadyTimeoutSeconds = 60.0;
		constexpr double StageTimeoutSeconds = 20.0;
		constexpr float SurfaceGapCm = 15000.f;

		struct FAcceptanceState
		{
			bool bAccepted = false;
			bool bPIEEnded = false;
		};

		struct FRuntimeContext
		{
			UWorld* World = nullptr;
			APlayerController* Controller = nullptr;
			ARedPlayerCharacter* Pawn = nullptr;
			int32 PIEWorldCount = 0;
			int32 StandaloneWorldCount = 0;
		};

		struct FExpectedMemberTransform
		{
			FVector Location = FVector::ZeroVector;
			FQuat Rotation = FQuat::Identity;
			FVector Scale = FVector::OneVector;
		};

		struct FExplosionStats
		{
			int32 Count = 0;
			int32 SimulatingDebris = 0;
			int32 RecentlyRenderedDebris = 0;
		};

		FName StableMemberId(const int32 Ordinal)
		{
			return FName(*FString::Printf(
				TEXT("asteroid-field.red.mars.deep-space/0x4F524531/%02d"),
				Ordinal));
		}

		FRuntimeContext ResolveRuntimeContext()
		{
			FRuntimeContext Result;
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
				if (World->GetNetMode() == NM_Standalone)
				{
					Result.World = World;
					++Result.StandaloneWorldCount;
				}
			}

			if (Result.World)
			{
				Result.Controller = Result.World->GetFirstPlayerController();
				Result.Pawn = Result.Controller
					? Cast<ARedPlayerCharacter>(Result.Controller->GetPawn())
					: nullptr;
			}
			return Result;
		}

		bool ResolveFieldCohort(
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
			if (TaggedCount != MineableCount || OutMembers.Num() != MineableCount)
			{
				return false;
			}
			for (int32 Ordinal = 0; Ordinal < MineableCount; ++Ordinal)
			{
				if (!OutMembers.Contains(StableMemberId(Ordinal)))
				{
					return false;
				}
			}
			return true;
		}

		FExpectedMemberTransform ReplayExpectedTransform(
			const int32 WantedOrdinal,
			const FVector& FieldCenter,
			const float PlanetSurfaceRadiusCm)
		{
			FExpectedMemberTransform Result;
			FRandomStream Stream(MineableSeed);
			for (int32 Ordinal = 0; Ordinal < MineableCount; ++Ordinal)
			{
				FVector Direction;
				do
				{
					Direction = FVector(
						Stream.FRandRange(-1.f, 1.f),
						Stream.FRandRange(-1.f, 1.f),
						Stream.FRandRange(-0.7f, 0.7f)).GetSafeNormal();
				}
				while (Direction.IsNearlyZero());
				const float Radius = PlanetSurfaceRadiusCm + Stream.FRandRange(
					RedPlanetPresentationTuning::DeepSpaceAsteroidInnerAltitudeCm,
					RedPlanetPresentationTuning::DeepSpaceAsteroidOuterAltitudeCm);
				const FRotator Rotation(
					Stream.FRandRange(-180.f, 180.f),
					Stream.FRandRange(-180.f, 180.f),
					Stream.FRandRange(-180.f, 180.f));
				const float UniformScale = Stream.FRandRange(12.f, 42.f);
				const FVector ShapeScale(
					UniformScale,
					UniformScale * Stream.FRandRange(0.65f, 1.25f),
					UniformScale * Stream.FRandRange(0.65f, 1.25f));

				if (Ordinal == WantedOrdinal)
				{
					Result.Location = FieldCenter + Direction * Radius;
					Result.Rotation = Rotation.Quaternion();
					Result.Scale = ShapeScale;
				}
			}
			return Result;
		}

		bool QueryHUD(
			const FRuntimeContext& Runtime,
			const int32 ExpectedAmount,
			FString& OutText,
			bool& bOutVisible)
		{
			OutText.Reset();
			bOutVisible = false;
			if (!Runtime.Controller || !Runtime.Pawn)
			{
				return false;
			}
			const ARedHUD* HUD = Cast<ARedHUD>(Runtime.Controller->GetHUD());
			if (!HUD)
			{
				return false;
			}

			FString InventoryText;
			bool bPersistentTallyVisible = true;
			const bool bInventoryCachePassed =
				HUD->QueryReplacementHUDResources(
					Runtime.Pawn->ResStone,
					Runtime.Pawn->ResIron,
					Runtime.Pawn->ResCrystal,
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

		int32 CountReceipts(UWorld* World, ARedMineableAsteroid* ExpectedOwner)
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
				TArray<UStaticMeshComponent*> Components;
				Explosion->GetComponents<UStaticMeshComponent>(Components);
				for (const UStaticMeshComponent* Component : Components)
				{
					if (Component && Component->IsSimulatingPhysics())
					{
						++Result.SimulatingDebris;
						if (Component->WasRecentlyRendered(1.5f))
						{
							++Result.RecentlyRenderedDebris;
						}
					}
				}
			}
			return Result;
		}

		int32 CountOtherPristineMembers(
			const TMap<FName, ARedMineableAsteroid*>& Members,
			const FName TargetId)
		{
			int32 Count = 0;
			for (const TPair<FName, ARedMineableAsteroid*>& Pair : Members)
			{
				const ARedMineableAsteroid* Member = Pair.Value;
				if (Pair.Key == TargetId)
				{
					continue;
				}
				if (IsValid(Member)
					&& Member->GetStableMemberId() == Pair.Key
					&& Member->DepletionState.Phase
						== ERedMineableAsteroidDepletionPhase::Active
					&& FMath::IsNearlyEqual(Member->OreCapacity, 6000.f)
					&& FMath::IsNearlyEqual(Member->OreRemaining, Member->OreCapacity)
					&& Member->GetActorEnableCollision()
					&& !Member->IsHidden())
				{
					++Count;
				}
			}
			return Count;
		}

		bool TraceExactTarget(
			UWorld* World,
			const FVector& Start,
			const FVector& End,
			const AActor* Target,
			const AActor* IgnoredActor,
			FHitResult& OutHit)
		{
			FCollisionQueryParams Params(
				SCENE_QUERY_STAT(RedDEF0003ActualFieldTrace),
				true);
			if (IgnoredActor)
			{
				Params.AddIgnoredActor(IgnoredActor);
			}
			const bool bHit = World && World->LineTraceSingleByChannel(
				OutHit,
				Start,
				End,
				ECC_Visibility,
				Params);
			return bHit && OutHit.GetActor() == Target;
		}

		bool CapturePIEWindow(
			const FString& Filename,
			FString& OutWindowTitle)
		{
			OutWindowTitle.Reset();
			if (!FSlateApplication::IsInitialized())
			{
				return false;
			}

			TSharedPtr<SWindow> PIEWindow;
			for (const TSharedRef<SWindow>& Window :
				FSlateApplication::Get().GetTopLevelWindows())
			{
				const FString Title = Window->GetTitle().ToString();
				if (Title.Contains(TEXT("Titan Preview")))
				{
					PIEWindow = Window;
					OutWindowTitle = Title;
					break;
				}
			}
			if (!PIEWindow.IsValid())
			{
				return false;
			}

			TArray<FColor> Pixels;
			FIntVector Size = FIntVector::ZeroValue;
			if (!FSlateApplication::Get().TakeScreenshot(
					PIEWindow.ToSharedRef(),
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

		class FActualFieldAcceptanceCommand final : public IAutomationLatentCommand
		{
		public:
			FActualFieldAcceptanceCommand(
				FAutomationTestBase* InTest,
				TSharedRef<FAcceptanceState> InAcceptanceState)
				: Test(InTest)
				, AcceptanceState(MoveTemp(InAcceptanceState))
				, TargetId(StableMemberId(TargetOrdinal))
			{
				FParse::Value(
					FCommandLine::Get(),
					TEXT("RedDEF0003FieldCaptureDir="),
					CaptureDirectory);
				if (CaptureDirectory.IsEmpty())
				{
					CaptureDirectory = FPaths::Combine(
						FPaths::ProjectSavedDir(),
						TEXT("Automation/DEF0003ActualFieldPIE"));
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

				const FRuntimeContext Runtime = ResolveRuntimeContext();
				switch (Stage)
				{
				case EStage::AwaitReady:
					return AwaitReady(Runtime, Now);
				case EStage::AwaitRendered:
					return AwaitRendered(Runtime, Now);
				case EStage::Mine:
					return Mine(Runtime, Now);
				case EStage::AwaitTransition:
					return AwaitTransition(Runtime, Now);
				case EStage::AwaitFinal:
					return AwaitFinal(Runtime, Now);
				case EStage::Complete:
					return true;
				default:
					return Fail(TEXT("unknown acceptance stage"));
				}
			}

		private:
			enum class EStage : uint8
			{
				AwaitReady,
				AwaitRendered,
				Mine,
				AwaitTransition,
				AwaitFinal,
				Complete
			};

			bool Fail(const FString& Reason)
			{
				Test->AddError(FString::Printf(
					TEXT("DEF-0003 actual-field PIE acceptance failed: %s"),
					*Reason));
				UE_LOG(LogTemp, Error,
					TEXT("RED_DEF0003_FIELD_RESULT acceptancePass=0 reason=\"%s\""),
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

			bool AwaitReady(const FRuntimeContext& Runtime, const double Now)
			{
				if (Now - StartedAtSeconds > ReadyTimeoutSeconds)
				{
					return Fail(FString::Printf(
						TEXT("runtime/field timeout pie=%d standalone=%d"),
						Runtime.PIEWorldCount,
						Runtime.StandaloneWorldCount));
				}
				if (Runtime.PIEWorldCount != 1
					|| Runtime.StandaloneWorldCount != 1
					|| !Runtime.World
					|| !Runtime.Controller
					|| !Runtime.Controller->IsLocalController()
					|| !Runtime.Pawn)
				{
					return false;
				}

				ARedSpaceScenery* Scenery = nullptr;
				TMap<FName, ARedMineableAsteroid*> Members;
				if (!ResolveFieldCohort(Runtime.World, Members, Scenery))
				{
					return false;
				}
				ARedMineableAsteroid* Target = Members.FindRef(TargetId);
				if (!Target)
				{
					return false;
				}

				FVector PlanetCenter = FVector::ZeroVector;
				float DatumRadius = 0.f;
				float PeakRadius = 0.f;
				float NominalRadius = 0.f;
				if (!RedGravity::FindMeshPlanet(
						Runtime.World,
						PlanetCenter,
						DatumRadius,
						&PeakRadius,
						&NominalRadius)
					|| DatumRadius <= 0.f
					|| PeakRadius < DatumRadius
					|| !Scenery->GetActorLocation().Equals(PlanetCenter, 1.f))
				{
					return false;
				}
				const float PlanetSurfaceRadiusCm =
					(DatumRadius + PeakRadius) * 0.5f;
				const float AltitudeCm =
					FVector::Distance(Target->GetActorLocation(), PlanetCenter)
					- PlanetSurfaceRadiusCm;
				const FExpectedMemberTransform Expected = ReplayExpectedTransform(
					TargetOrdinal,
					Scenery->GetActorLocation(),
					PlanetSurfaceRadiusCm);
				const float RotationDot = FMath::Abs(
					Expected.Rotation
						| Target->GetActorQuat().GetNormalized());
				const bool bTransformPassed =
					Target->GetActorLocation().Equals(Expected.Location, 1.f)
					&& RotationDot >= 0.99999f
					&& Target->GetActorScale3D().Equals(Expected.Scale, 0.001f);
				const bool bIdentityPassed =
					Target->GetStableMemberId() == TargetId
					&& Target->GetFName()
						== FName(TEXT("RedMineableAsteroid_23"))
					&& Target->ActorHasTag(TEXT("RedMarsMineableBelt"))
					&& Target->ActorHasTag(TEXT("RedMineableSpaceAsteroid"))
					&& Target->GetOwner() == Scenery
					&& !Target->HasAnyFlags(RF_Transient)
					&& Target->HasAuthority()
					&& Target->HasActorBegunPlay()
					&& Target->DepletionState.Phase
						== ERedMineableAsteroidDepletionPhase::Active
					&& FMath::IsNearlyEqual(Target->OreCapacity, 6000.f)
					&& FMath::IsNearlyEqual(
						Target->OreRemaining,
						Target->OreCapacity)
					&& FMath::IsNearlyEqual(
						Target->GetPresentationCullDistance(),
						RedPlanetPresentationTuning::AsteroidRenderCullDistanceCm,
						1.f)
					&& AltitudeCm
						>= RedPlanetPresentationTuning::DeepSpaceAsteroidInnerAltitudeCm - 1.f
					&& AltitudeCm
						<= RedPlanetPresentationTuning::DeepSpaceAsteroidOuterAltitudeCm + 1.f
					&& bTransformPassed
					&& CountOtherPristineMembers(Members, TargetId)
						== MineableCount - 1;
				if (!bIdentityPassed)
				{
					return Fail(FString::Printf(
						TEXT("stable identity/cohort/transform failed altitude=%.1f rotationDot=%.6f"),
						AltitudeCm,
						RotationDot));
				}

				UStaticMeshComponent* RockMesh =
					Cast<UStaticMeshComponent>(Target->GetRootComponent());
				if (!RockMesh)
				{
					return Fail(TEXT("actual field target has no static-mesh root"));
				}
				FVector BoundsOrigin;
				FVector BoundsExtent;
				Target->GetActorBounds(
					false,
					BoundsOrigin,
					BoundsExtent,
					true);
				FVector RadialOut =
					(BoundsOrigin - PlanetCenter).GetSafeNormal();
				if (RadialOut.IsNearlyZero())
				{
					return Fail(TEXT("target radial-out vector is zero"));
				}

				FHitResult SurfaceHit;
				const FVector TraceStart =
					BoundsOrigin
					+ RadialOut * (BoundsExtent.Size() + 500000.f);
				if (!TraceExactTarget(
						Runtime.World,
						TraceStart,
						BoundsOrigin,
						Target,
						Runtime.Pawn,
						SurfaceHit))
				{
					return Fail(TEXT("outward surface trace did not hit exact target"));
				}
				FVector SurfaceNormal = SurfaceHit.ImpactNormal.GetSafeNormal();
				if (SurfaceNormal.IsNearlyZero())
				{
					SurfaceNormal = RadialOut;
				}
				const FVector FrameLocation =
					SurfaceHit.ImpactPoint + SurfaceNormal * SurfaceGapCm;
				const FRotator FrameRotation =
					(SurfaceHit.ImpactPoint - FrameLocation).Rotation();
				const float CameraDistanceCm =
					FVector::Distance(FrameLocation, BoundsOrigin);
				if (CameraDistanceCm
					>= RedPlanetPresentationTuning::AsteroidRenderCullDistanceCm * 0.9f)
				{
					return Fail(TEXT("safe framing point exceeds cull-distance margin"));
				}

				InitialPawnLocation = Runtime.Pawn->GetActorLocation();
				InitialIron = Runtime.Pawn->ResIron;
				InitialCapacity = Target->OreCapacity;
				InitialScale = Target->GetActorScale3D();
				TargetLocation = Target->GetActorLocation();
				TargetAltitudeCm = AltitudeCm;
				CameraToBoundsCm = CameraDistanceCm;
				SurfaceImpactPoint = SurfaceHit.ImpactPoint;
				TargetBoundsOrigin = BoundsOrigin;
				MembersById = Members;
				TargetActor = Target;
				TargetMesh = RockMesh;

				if (UCharacterMovementComponent* Movement =
					Runtime.Pawn->GetCharacterMovement())
				{
					Movement->StopMovementImmediately();
					Movement->DisableMovement();
				}
				Runtime.Pawn->SetActorLocationAndRotation(
					FrameLocation,
					FrameRotation,
					false,
					nullptr,
					ETeleportType::TeleportPhysics);
				Runtime.Controller->SetControlRotation(FrameRotation);

				FActorSpawnParameters CameraParams;
				CameraParams.ObjectFlags |= RF_Transient;
				CameraParams.SpawnCollisionHandlingOverride =
					ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
				ACameraActor* Camera = Runtime.World->SpawnActor<ACameraActor>(
					FrameLocation,
					FrameRotation,
					CameraParams);
				if (!Camera)
				{
					return Fail(TEXT("transient field camera spawn failed"));
				}
				Camera->GetCameraComponent()->SetFieldOfView(52.f);
				Runtime.Controller->SetViewTarget(Camera);
				FieldCamera = Camera;
				CameraReadyAtSeconds = Now;

				UE_LOG(LogTemp, Display,
					TEXT("RED_DEF0003_FIELD_IDENTITY pass=1 stableId=%s seed=0x4F524531 ordinal=%d cohort=%d owner=%s actorName=%s transformPass=1 location=(%.1f,%.1f,%.1f) scale=(%.5f,%.5f,%.5f)"),
					*TargetId.ToString(),
					TargetOrdinal,
					MembersById.Num(),
					*GetNameSafe(Scenery),
					*Target->GetName(),
					TargetLocation.X,
					TargetLocation.Y,
					TargetLocation.Z,
					InitialScale.X,
					InitialScale.Y,
					InitialScale.Z);
				Advance(EStage::AwaitRendered, Now);
				return false;
			}

			bool AwaitRendered(
				const FRuntimeContext& Runtime,
				const double Now)
			{
				if (StageTimedOut(Now))
				{
					return Fail(TEXT("actual field member did not become visibly rendered"));
				}
				ARedMineableAsteroid* Target = TargetActor.Get();
				UStaticMeshComponent* RockMesh = TargetMesh.Get();
				ACameraActor* Camera = FieldCamera.Get();
				if (!Runtime.World
					|| !Runtime.Controller
					|| !Runtime.Pawn
					|| !Target
					|| !RockMesh
					|| !Camera)
				{
					return false;
				}
				Runtime.Controller->SetViewTarget(Camera);
				if (Runtime.Controller->GetViewTarget() != Camera
					|| Now - CameraReadyAtSeconds < 0.75)
				{
					return false;
				}

				FHitResult ViewHit;
				const bool bTraceExact = TraceExactTarget(
					Runtime.World,
					Camera->GetActorLocation(),
					TargetBoundsOrigin,
					Target,
					Runtime.Pawn,
					ViewHit);
				const float SurfaceGapMeasuredCm =
					FVector::Distance(
						Camera->GetActorLocation(),
						SurfaceImpactPoint);
				const float PlayerTravelCm =
					FVector::Distance(
						Runtime.Pawn->GetActorLocation(),
						InitialPawnLocation);
				const bool bRangePassed =
					bTraceExact
					&& Target->GetStableMemberId() == TargetId
					&& RockMesh->IsRegistered()
					&& RockMesh->IsVisible()
					&& RockMesh->WasRecentlyRendered(1.5f)
					&& FMath::IsNearlyEqual(
						RockMesh->LDMaxDrawDistance,
						RedPlanetPresentationTuning::AsteroidRenderCullDistanceCm,
						1.f)
					&& FMath::IsNearlyEqual(
						RockMesh->CachedMaxDrawDistance,
						RedPlanetPresentationTuning::AsteroidRenderCullDistanceCm,
						1.f)
					&& CameraToBoundsCm
						< RedPlanetPresentationTuning::AsteroidRenderCullDistanceCm
					&& FMath::IsNearlyEqual(
						SurfaceGapMeasuredCm,
						SurfaceGapCm,
						10.f)
					&& PlayerTravelCm
						> RedPlanetPresentationTuning::DeepSpaceAsteroidInnerAltitudeCm * 0.75f;
				if (!bRangePassed)
				{
					return false;
				}

				FString HUDText;
				bool bHUDVisible = false;
				if (!QueryHUD(Runtime, 0, HUDText, bHUDVisible)
					|| bHUDVisible)
				{
					return false;
				}
				FString WindowTitle;
				const FString Filename = FPaths::Combine(
					CaptureDirectory,
					TEXT("DEF0003_Field_Before.png"));
				if (!CapturePIEWindow(Filename, WindowTitle))
				{
					return false;
				}

				UE_LOG(LogTemp, Display,
					TEXT("RED_DEF0003_FIELD_RANGE pass=1 stableId=%s altitudeKm=%.3f playerTravelKm=%.3f surfaceGapCm=%.1f cameraToBoundsCm=%.1f cullCm=%.1f traceExact=1 recentlyRendered=1 ldCull=%.1f cachedCull=%.1f hudVisible=1 capture=\"%s\" window=\"%s\""),
					*TargetId.ToString(),
					TargetAltitudeCm * 0.00001f,
					PlayerTravelCm * 0.00001f,
					SurfaceGapMeasuredCm,
					CameraToBoundsCm,
					RedPlanetPresentationTuning::AsteroidRenderCullDistanceCm,
					RockMesh->LDMaxDrawDistance,
					RockMesh->CachedMaxDrawDistance,
					*Filename,
					*WindowTitle.ReplaceCharWithEscapedChar());
				Advance(EStage::Mine, Now);
				return false;
			}

			bool Mine(const FRuntimeContext& Runtime, const double Now)
			{
				ARedMineableAsteroid* Target = TargetActor.Get();
				if (!Runtime.Pawn || !Target)
				{
					return Fail(TEXT("actual field target/pawn invalid at mining barrier"));
				}

				float TotalExtracted = 0.f;
				for (int32 HitIndex = 0; HitIndex < 7; ++HitIndex)
				{
					TotalExtracted +=
						Target->RegisterMiningHit(55.f, Runtime.Pawn);
				}
				const int32 OtherPristine =
					CountOtherPristineMembers(MembersById, TargetId);
				const bool bPassed =
					Target->GetStableMemberId() == TargetId
					&& FMath::IsNearlyEqual(Target->OreCapacity, InitialCapacity)
					&& Target->GetActorScale3D().Equals(InitialScale, 0.001f)
					&& FMath::IsNearlyEqual(
						Target->GetPresentationCullDistance(),
						RedPlanetPresentationTuning::AsteroidRenderCullDistanceCm,
						1.f)
					&& FMath::IsNearlyEqual(TotalExtracted, InitialCapacity)
					&& FMath::IsNearlyZero(Target->OreRemaining)
					&& Target->DepletionState.Phase
						== ERedMineableAsteroidDepletionPhase::Depleting
					&& Target->DepletionState.Sequence == 1
					&& !Target->GetActorEnableCollision()
					&& !Target->IsHidden()
					&& Runtime.Pawn->ResIron == InitialIron + 6
					&& CountReceipts(Runtime.World, Target) == 1
					&& OtherPristine == MineableCount - 1;
				UE_LOG(LogTemp, Display,
					TEXT("RED_DEF0003_FIELD_HIT pass=%d stableId=%s actualFieldMember=1 hits=7 extracted=%.0f capacity=%.0f capacityUnchanged=%d phase=%d sequence=%u rewardDelta=%d receipt=%d otherMembersPristine=%d"),
					bPassed ? 1 : 0,
					*TargetId.ToString(),
					TotalExtracted,
					Target->OreCapacity,
					FMath::IsNearlyEqual(Target->OreCapacity, InitialCapacity) ? 1 : 0,
					static_cast<int32>(Target->DepletionState.Phase),
					Target->DepletionState.Sequence,
					Runtime.Pawn->ResIron - InitialIron,
					CountReceipts(Runtime.World, Target),
					OtherPristine);
				if (!bPassed)
				{
					return Fail(TEXT("actual generated member depletion contract failed"));
				}
				Advance(EStage::AwaitTransition, Now);
				return false;
			}

			bool AwaitTransition(
				const FRuntimeContext& Runtime,
				const double Now)
			{
				if (StageTimedOut(Now))
				{
					return Fail(TEXT("actual field transition/HUD timeout"));
				}
				ARedMineableAsteroid* Target = TargetActor.Get();
				ACameraActor* Camera = FieldCamera.Get();
				if (!Runtime.Controller || !Runtime.Pawn || !Target || !Camera)
				{
					return false;
				}
				Runtime.Controller->SetViewTarget(Camera);
				if (Target->DepletionState.Phase
					== ERedMineableAsteroidDepletionPhase::Depleted)
				{
					return Fail(TEXT("transition capture missed two-second readable window"));
				}

				FString HUDText;
				bool bHUDVisible = false;
				const bool bHUDPassed =
					QueryHUD(Runtime, 6, HUDText, bHUDVisible)
					&& bHUDVisible;
				const bool bReady =
					Target->GetStableMemberId() == TargetId
					&& Target->DepletionState.Phase
						== ERedMineableAsteroidDepletionPhase::Depleting
					&& Target->DepletionState.Sequence == 1
					&& !Target->GetActorEnableCollision()
					&& !Target->IsHidden()
					&& Runtime.Pawn->ResIron == InitialIron + 6
					&& CountReceipts(Runtime.World, Target) == 1
					&& bHUDPassed;
				if (!bReady)
				{
					return false;
				}

				FString WindowTitle;
				const FString Filename = FPaths::Combine(
					CaptureDirectory,
					TEXT("DEF0003_Field_Transition.png"));
				if (!CapturePIEWindow(Filename, WindowTitle))
				{
					return false;
				}
				UE_LOG(LogTemp, Display,
					TEXT("RED_DEF0003_FIELD_TRANSITION pass=1 stableId=%s phase=%d sequence=%u collision=%d hidden=%d rewardDelta=%d receipt=%d hudVisible=%d hudText=\"%s\" capture=\"%s\""),
					*TargetId.ToString(),
					static_cast<int32>(Target->DepletionState.Phase),
					Target->DepletionState.Sequence,
					Target->GetActorEnableCollision() ? 1 : 0,
					Target->IsHidden() ? 1 : 0,
					Runtime.Pawn->ResIron - InitialIron,
					CountReceipts(Runtime.World, Target),
					bHUDVisible ? 1 : 0,
					*HUDText.ReplaceCharWithEscapedChar(),
					*Filename);
				Advance(EStage::AwaitFinal, Now);
				return false;
			}

			bool AwaitFinal(
				const FRuntimeContext& Runtime,
				const double Now)
			{
				if (StageTimedOut(Now))
				{
					return Fail(TEXT("actual field final explosion/debris timeout"));
				}
				ARedMineableAsteroid* Target = TargetActor.Get();
				ACameraActor* Camera = FieldCamera.Get();
				if (!Runtime.Controller || !Runtime.Pawn || !Target || !Camera)
				{
					return false;
				}
				Runtime.Controller->SetViewTarget(Camera);

				const FExplosionStats Explosion =
					GetExplosionStats(Runtime.World, Target);
				FString HUDText;
				bool bHUDVisible = false;
				const bool bHUDPassed =
					QueryHUD(Runtime, 6, HUDText, bHUDVisible)
					&& bHUDVisible;
				TMap<FName, ARedMineableAsteroid*> CurrentMembers;
				ARedSpaceScenery* CurrentScenery = nullptr;
				const bool bCohortStillComplete = ResolveFieldCohort(
					Runtime.World,
					CurrentMembers,
					CurrentScenery);
				const int32 OtherPristine =
					CountOtherPristineMembers(CurrentMembers, TargetId);
				const bool bReady =
					Target->GetStableMemberId() == TargetId
					&& Target->DepletionState.Phase
						== ERedMineableAsteroidDepletionPhase::Depleted
					&& Target->DepletionState.Sequence == 2
					&& !Target->GetActorEnableCollision()
					&& Target->IsHidden()
					&& Explosion.Count == 1
					&& Explosion.SimulatingDebris >= 8
					&& Runtime.Pawn->ResIron == InitialIron + 6
					&& CountReceipts(Runtime.World, Target) == 1
					&& bCohortStillComplete
					&& CurrentMembers.Num() == MineableCount
					&& OtherPristine == MineableCount - 1
					&& bHUDPassed;
				if (!bReady)
				{
					return false;
				}

				const float PostHit =
					Target->RegisterMiningHit(1.f, Runtime.Pawn);
				if (!FMath::IsNearlyZero(PostHit)
					|| Target->GetStableMemberId() != TargetId)
				{
					return Fail(TEXT("post-depletion hit or stable identity changed"));
				}
				FString WindowTitle;
				const FString Filename = FPaths::Combine(
					CaptureDirectory,
					TEXT("DEF0003_Field_Explosion.png"));
				if (!CapturePIEWindow(Filename, WindowTitle))
				{
					return false;
				}

				UE_LOG(LogTemp, Display,
					TEXT("RED_DEF0003_FIELD_FINAL pass=1 stableId=%s phase=%d sequence=%u hidden=%d explosion=%d debris=%d recentlyRenderedDebris=%d rewardDelta=%d receipt=%d postHit=%.0f fieldCount=%d otherMembersPristine=%d hudVisible=%d hudText=\"%s\" capture=\"%s\""),
					*TargetId.ToString(),
					static_cast<int32>(Target->DepletionState.Phase),
					Target->DepletionState.Sequence,
					Target->IsHidden() ? 1 : 0,
					Explosion.Count,
					Explosion.SimulatingDebris,
					Explosion.RecentlyRenderedDebris,
					Runtime.Pawn->ResIron - InitialIron,
					CountReceipts(Runtime.World, Target),
					PostHit,
					CurrentMembers.Num(),
					OtherPristine,
					bHUDVisible ? 1 : 0,
					*HUDText.ReplaceCharWithEscapedChar(),
					*Filename);
				UE_LOG(LogTemp, Display,
					TEXT("RED_DEF0003_FIELD_RESULT acceptancePass=1 evidenceClass=real_gpu_visual actualFieldMember=1 stableIdentity=1 testTeleport=1 playerControlledTravel=0 projectileDelivery=0 multiplayer=0 steamTransport=0"));
				AcceptanceState->bAccepted = true;
				Advance(EStage::Complete, Now);
				return true;
			}

			FAutomationTestBase* Test = nullptr;
			TSharedRef<FAcceptanceState> AcceptanceState;
			EStage Stage = EStage::AwaitReady;
			double StartedAtSeconds = 0.0;
			double StageStartedAtSeconds = 0.0;
			double CameraReadyAtSeconds = 0.0;
			int32 InitialIron = 0;
			float InitialCapacity = 0.f;
			float TargetAltitudeCm = 0.f;
			float CameraToBoundsCm = 0.f;
			FName TargetId = NAME_None;
			FString CaptureDirectory;
			FVector InitialPawnLocation = FVector::ZeroVector;
			FVector InitialScale = FVector::OneVector;
			FVector TargetLocation = FVector::ZeroVector;
			FVector SurfaceImpactPoint = FVector::ZeroVector;
			FVector TargetBoundsOrigin = FVector::ZeroVector;
			TMap<FName, ARedMineableAsteroid*> MembersById;
			TWeakObjectPtr<ARedMineableAsteroid> TargetActor;
			TWeakObjectPtr<UStaticMeshComponent> TargetMesh;
			TWeakObjectPtr<ACameraActor> FieldCamera;
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
				if (ResolveRuntimeContext().PIEWorldCount == 0)
				{
					AcceptanceState->bPIEEnded = true;
					UE_LOG(LogTemp, Display,
						TEXT("RED_DEF0003_FIELD_COMPLETE pieEnded=1 acceptancePass=%d"),
						AcceptanceState->bAccepted ? 1 : 0);
					return true;
				}
				if (FPlatformTime::Seconds() - StartedAtSeconds > 15.0)
				{
					Test->AddError(TEXT(
						"DEF-0003 actual-field PIE did not end within 15 seconds."));
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
		FRedDEF0003ActualFieldPIETest,
		"RedMMO.Mining.DEF0003.ActualGeneratedFieldMemberPIE",
		EAutomationTestFlags::EditorContext | EAutomationTestFlags::ProductFilter)

	bool FRedDEF0003ActualFieldPIETest::RunTest(const FString& Parameters)
	{
		(void)Parameters;
		if (!FApp::CanEverRender()
			|| FParse::Param(FCommandLine::Get(), TEXT("nullrhi")))
		{
			AddError(TEXT(
				"DEF-0003 actual-field visual acceptance requires a rendered non-NullRHI editor."));
			return false;
		}
		if (Private::ResolveRuntimeContext().PIEWorldCount != 0)
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
		PlaySettings->SetPlayNetMode(EPlayNetMode::PIE_Standalone);
		PlaySettings->SetPlayNumberOfClients(1);
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
			Private::FActualFieldAcceptanceCommand(this, AcceptanceState));
		ADD_LATENT_AUTOMATION_COMMAND(FEndPlayMapCommand());
		ADD_LATENT_AUTOMATION_COMMAND(
			Private::FWaitForPIEEndCommand(this, AcceptanceState));
		return true;
	}
}

#endif // WITH_DEV_AUTOMATION_TESTS && WITH_EDITOR
