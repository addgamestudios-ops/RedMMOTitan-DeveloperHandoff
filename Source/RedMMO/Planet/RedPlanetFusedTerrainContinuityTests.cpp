// REDMMO_HAS_PLANETGEN_FORK_APIS_GATE
#if __has_include("PlanetGen/PlanetGenTerrainStamp.h")
#include "PlanetGen/CLMPlanet.h"
#include "PlanetGen/CLMPlanetChunk.h"
#include "PlanetGen/PlanetGenTerrainStamp.h"
#include "PlanetGenMacroHeightfieldAsset.h"
#include "RedPlanetRegionService.h"
#include "../RedPlanetTerrainQuery.h"
#include "../RedShip.h"
#include "../RedShipCollisionDriver.h"
#include "../RedShipMovementComponent.h"
#include "../RedShuttleBase.h"

#if WITH_DEV_AUTOMATION_TESTS && WITH_EDITOR

#include "Components/BoxComponent.h"
#include "Components/SphereComponent.h"
#include "Components/StaticMeshComponent.h"
#include "CollisionShape.h"
#include "Engine/Engine.h"
#include "Engine/OverlapResult.h"
#include "Engine/StaticMesh.h"
#include "Engine/TargetPoint.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "GameFramework/Pawn.h"
#include "Misc/AutomationTest.h"
#include "Misc/PackageName.h"
#include "ProceduralMeshComponent.h"
#include "Tests/AutomationCommon.h"
#include "Tests/AutomationEditorCommon.h"
#include "UObject/Package.h"
#include "UObject/UObjectGlobals.h"

namespace RedPlanet::FusedTerrainContinuityTests
{
	namespace Private
	{
		constexpr TCHAR FusedPrototypeMap[] =
			TEXT("/Game/RedMMO/Maps/RedPlanetGen_50km_FusedPrototype");
		constexpr TCHAR FusedHeightfieldPath[] =
			TEXT("/Game/RedMMO/Environment/DA_RED_Planet50Km_FusedHeightfield.DA_RED_Planet50Km_FusedHeightfield");
		constexpr int32 ExpectedMacroResolution = 257;
		constexpr int32 ExpectedTerrainStampCount = 27;
		constexpr int32 AuthoringPatchIndex = 13;
		constexpr double PhaseTimeoutSeconds = 60.0;
		constexpr float RadialTraceMarginCm = 50000.0f;
		constexpr float StreamingSourceClearanceCm = 5000.0f;
		constexpr float LiftedSweepClearanceCm = 1000.0f;
		constexpr float LiftedSweepRadiusCm = 50.0f;
		constexpr float PawnTraversalCapsuleRadiusCm = 34.0f;
		constexpr float PawnTraversalCapsuleHalfHeightCm = 88.0f;
		constexpr float PawnTraversalClearanceCm = 20.0f;
		constexpr float SharedSeamPositionToleranceCm = 1.0f;
		constexpr float SharedSeamNormalDotTolerance = 0.999f;
		constexpr double DirectionMatchDotTolerance = 1.0 - 1.0e-10;
		constexpr float ChunkActorDirectionMatchDotTolerance = 0.9999f;
		constexpr int32 MovingWaypointCount = 4;
		constexpr int32 MovingRouteProbeCount = 25;
		constexpr int32 ExpectedCollisionChunksPerWaypoint = 21;
		constexpr int32 ExpectedRetainedChunksPerMove = 16;
		constexpr int32 ExpectedEnteredChunksPerMove = 5;
		constexpr int32 ExpectedExitedChunksPerMove = 5;
		constexpr int32 ExpectedStaticRoutePawnSweepCount = 43;
		constexpr int32 ExpectedMovingRoutePawnSweepCount = 72;
		constexpr int32 ExpectedTotalPawnSweepCount =
			ExpectedStaticRoutePawnSweepCount + ExpectedMovingRoutePawnSweepCount;

		enum class EVerificationPhase : uint8
		{
			WaitForWorld,
			CubeFaceSeam,
			AuthoringPatchFeather,
			TerrainStampFeather,
			MovingCollisionRing,
			Finished
		};

		enum class EMovingVerificationStage : uint8
		{
			WaitForInitialSettle,
			WaitForTransition
		};

		struct FProbe
		{
			FVector Direction = FVector::UpVector;
			FString Label;
			FIntVector ExpectedChunkKey = FIntVector(INDEX_NONE, INDEX_NONE, INDEX_NONE);
		};

		struct FProbeHit
		{
			FVector Direction = FVector::UpVector;
			FVector Position = FVector::ZeroVector;
			FVector Normal = FVector::UpVector;
			TWeakObjectPtr<ACLMPlanetChunk> Chunk;
			TWeakObjectPtr<UProceduralMeshComponent> Component;
		};

		struct FSeamVertex
		{
			FVector Direction = FVector::UpVector;
			FVector Position = FVector::ZeroVector;
			FVector Normal = FVector::UpVector;
		};

		struct FStreamingPawnState
		{
			TWeakObjectPtr<APawn> Pawn;
			FVector OriginalLocation = FVector::ZeroVector;
			bool bOriginalCollisionEnabled = true;
			bool bOriginalHidden = false;
			bool bOriginalTickEnabled = true;
		};

		UWorld* FindFusedPIEWorld()
		{
			if (!GEngine)
			{
				return nullptr;
			}

			for (const FWorldContext& Context : GEngine->GetWorldContexts())
			{
				UWorld* World = Context.World();
				if (!IsValid(World)
					|| (Context.WorldType != EWorldType::PIE && Context.WorldType != EWorldType::Game))
				{
					continue;
				}

				const FString ShortMapName = UWorld::RemovePIEPrefix(
					FPackageName::GetShortName(World->GetMapName()));
				if (ShortMapName == TEXT("RedPlanetGen_50km_FusedPrototype"))
				{
					return World;
				}
			}

			return nullptr;
		}

		FVector RotateAlongGreatCircle(
			const FVector& UnitDirection,
			const FVector& UnitRotationAxis,
			const double ArcDistanceCm,
			const double PlanetRadiusCm)
		{
			return FQuat(
				UnitRotationAxis.GetSafeNormal(),
				static_cast<float>(ArcDistanceCm / FMath::Max(PlanetRadiusCm, 1.0)))
				.RotateVector(UnitDirection.GetSafeNormal())
				.GetSafeNormal();
		}

		FVector SlerpDirection(const FVector& A, const FVector& B, const float Alpha)
		{
			const FVector UnitA = A.GetSafeNormal();
			const FVector UnitB = B.GetSafeNormal();
			const FQuat Delta = FQuat::FindBetweenNormals(UnitA, UnitB);
			return FQuat::Slerp(FQuat::Identity, Delta, Alpha)
				.RotateVector(UnitA)
				.GetSafeNormal();
		}

		int32 GetChunksPerFace(const ACLMPlanet* Planet)
		{
			if (!Planet)
			{
				return 0;
			}
			const int32 Raw = FMath::Max(
				1,
				FMath::RoundToInt(Planet->PlanetRadius * PI * 0.5f / Planet->TileSize));
			return FMath::Min(Raw, FMath::Max(1, Planet->MaxChunksPerFace));
		}

		FVector GetFaceNormal(const int32 Face)
		{
			switch (Face)
			{
			case 0: return FVector(1.0f, 0.0f, 0.0f);
			case 1: return FVector(-1.0f, 0.0f, 0.0f);
			case 2: return FVector(0.0f, 1.0f, 0.0f);
			case 3: return FVector(0.0f, -1.0f, 0.0f);
			case 4: return FVector(0.0f, 0.0f, 1.0f);
			case 5: return FVector(0.0f, 0.0f, -1.0f);
			default: return FVector::ZeroVector;
			}
		}

		FVector GetFaceU(const int32 Face)
		{
			switch (Face)
			{
			case 0: return FVector(0.0f, 1.0f, 0.0f);
			case 1: return FVector(0.0f, -1.0f, 0.0f);
			case 2: return FVector(-1.0f, 0.0f, 0.0f);
			case 3: return FVector(1.0f, 0.0f, 0.0f);
			case 4:
			case 5: return FVector(1.0f, 0.0f, 0.0f);
			default: return FVector::ZeroVector;
			}
		}

		FVector GetFaceV(const int32 Face)
		{
			switch (Face)
			{
			case 0:
			case 1:
			case 2:
			case 3: return FVector(0.0f, 0.0f, 1.0f);
			case 4: return FVector(0.0f, 1.0f, 0.0f);
			case 5: return FVector(0.0f, -1.0f, 0.0f);
			default: return FVector::ZeroVector;
			}
		}

		FVector GetChunkCenterDirection(
			const int32 ChunksPerFace,
			const FIntVector& Key)
		{
			const float UCenter = (Key.Y + 0.5f) / ChunksPerFace * 2.0f - 1.0f;
			const float VCenter = (Key.Z + 0.5f) / ChunksPerFace * 2.0f - 1.0f;
			auto TangentCorrect = [](const float Value)
			{
				return FMath::Tan(Value * PI / 4.0f);
			};
			return (GetFaceNormal(Key.X)
				+ GetFaceU(Key.X) * TangentCorrect(UCenter)
				+ GetFaceV(Key.X) * TangentCorrect(VCenter))
				.GetSafeNormal();
		}

		TSet<FIntVector> GetExpectedCollisionKeys(
			const ACLMPlanet* Planet,
			const FVector& StreamingDirection)
		{
			TSet<FIntVector> Result;
			const int32 ChunksPerFace = GetChunksPerFace(Planet);
			if (!Planet || ChunksPerFace <= 0)
			{
				return Result;
			}

			const float ChunkAngleRad = (PI * 0.5f) / ChunksPerFace;
			const float HalfChunkDiagonalRad = ChunkAngleRad * 0.75f;
			const float CollisionAngleRad = FMath::Min(
				PI,
				ChunkAngleRad * FMath::Max(Planet->TerrainCollisionViewDistance, 0.5f)
					+ HalfChunkDiagonalRad);
			const float Threshold = FMath::Cos(CollisionAngleRad);
			const FVector SourceDirection = StreamingDirection.GetSafeNormal();
			for (int32 Face = 0; Face < 6; ++Face)
			{
				for (int32 U = 0; U < ChunksPerFace; ++U)
				{
					for (int32 V = 0; V < ChunksPerFace; ++V)
					{
						const FIntVector Key(Face, U, V);
						if (FVector::DotProduct(
							SourceDirection,
							GetChunkCenterDirection(ChunksPerFace, Key)) >= Threshold)
						{
							Result.Add(Key);
						}
					}
				}
			}
			return Result;
		}

		bool IsOwnedPlanetChunk(const FHitResult& Hit, const ACLMPlanet* Planet)
		{
			const ACLMPlanetChunk* Chunk = Cast<ACLMPlanetChunk>(Hit.GetActor());
			return IsValid(Chunk) && Chunk->GetOwner() == Planet;
		}

		bool TraceOwnedTerrain(
			UWorld* World,
			ACLMPlanet* Planet,
			const FVector& Direction,
			FProbeHit& OutHit)
		{
			if (!IsValid(World) || !IsValid(Planet))
			{
				return false;
			}

			const FVector UnitDirection = Direction.GetSafeNormal();
			const FVector Center = Planet->GetActorLocation();
			const float OuterRadius = Planet->PlanetRadius
				+ FMath::Max(Planet->MaxMountainHeight, Planet->MaxHeight)
				+ RadialTraceMarginCm;
			const float InnerRadius = FMath::Max(
				100.0f,
				Planet->PlanetRadius
					+ FMath::Min(-Planet->MaxMountainHeight, Planet->MinHeight)
					- RadialTraceMarginCm);

			FCollisionQueryParams Params(SCENE_QUERY_STAT(RedFusedTerrainRadialTrace), true);
			Params.bTraceComplex = true;
			TArray<FHitResult> Hits;
			const bool bAnyHit = World->LineTraceMultiByObjectType(
				Hits,
				Center + UnitDirection * OuterRadius,
				Center + UnitDirection * InnerRadius,
				FCollisionObjectQueryParams(ECC_WorldDynamic),
				Params);
			if (!bAnyHit)
			{
				return false;
			}

			for (const FHitResult& Hit : Hits)
			{
				if (!Hit.bBlockingHit || !IsOwnedPlanetChunk(Hit, Planet))
				{
					continue;
				}
				ACLMPlanetChunk* Chunk = Cast<ACLMPlanetChunk>(Hit.GetActor());
				UProceduralMeshComponent* Mesh =
					Chunk ? Chunk->FindComponentByClass<UProceduralMeshComponent>() : nullptr;
				if (!Mesh || Hit.GetComponent() != Mesh
					|| Mesh->GetCollisionEnabled() != ECollisionEnabled::QueryAndPhysics
					|| Mesh->GetCollisionObjectType() != ECC_WorldDynamic
					|| Mesh->GetCollisionResponseToChannel(ECC_Pawn) != ECR_Block)
				{
					continue;
				}

				// The world Chaos hit names the exact cooked procedural component. Expected-key
				// validation at the call site prevents an adjacent face from masking this side.
				OutHit.Direction = UnitDirection;
				OutHit.Position = Hit.ImpactPoint;
				OutHit.Normal = Hit.ImpactNormal.GetSafeNormal();
				OutHit.Chunk = Chunk;
				OutHit.Component = Mesh;
				return true;
			}

			return false;
		}

		bool HasPawnTraversalBlocker(
			UWorld* World,
			const FProbeHit& A,
			const FProbeHit& B,
			FHitResult* OutBlockingHit = nullptr)
		{
			if (!World)
			{
				return true;
			}
			const FVector MidDirection = (A.Direction + B.Direction).GetSafeNormal();
			const FQuat CapsuleRotation = FQuat::FindBetweenNormals(
				FVector::UpVector, MidDirection);
			const float CenterClearance = PawnTraversalCapsuleHalfHeightCm
				+ PawnTraversalClearanceCm;
			const FVector Start = A.Position + A.Direction * CenterClearance;
			const FVector End = B.Position + B.Direction * CenterClearance;
			FCollisionQueryParams Params(SCENE_QUERY_STAT(RedFusedTerrainPawnTraversal), true);
			Params.bTraceComplex = true;
			TArray<FHitResult> Hits;
			World->SweepMultiByChannel(
				Hits,
				Start,
				End,
				CapsuleRotation,
				ECC_Pawn,
				FCollisionShape::MakeCapsule(
					PawnTraversalCapsuleRadiusCm,
					PawnTraversalCapsuleHalfHeightCm),
				Params);
			for (const FHitResult& Hit : Hits)
			{
				const bool bOutwardFloorContact = Hit.bBlockingHit
					&& !Hit.bStartPenetrating
					&& FVector::DotProduct(
						Hit.ImpactNormal.GetSafeNormal(), MidDirection) > 0.5f;
				if ((Hit.bBlockingHit || Hit.bStartPenetrating) && !bOutwardFloorContact)
				{
					if (OutBlockingHit)
					{
						*OutBlockingHit = Hit;
					}
					return true;
				}
			}
			return false;
		}

		void LogPawnTraversalBlocker(
			const TCHAR* Marker,
			const FString& Context,
			const int32 SegmentIndex,
			const FHitResult& Hit)
		{
			const UPrimitiveComponent* Component = Hit.GetComponent();
			UE_LOG(LogTemp, Error,
				TEXT("%s context=%s segment=%d actor=%s component=%s profile=%s object_channel=%d collision_enabled=%d pawn_response=%d start_penetrating=%d penetration_depth_cm=%.6f time=%.6f impact_normal=(%.6f,%.6f,%.6f)"),
				Marker,
				*Context,
				SegmentIndex,
				Hit.GetActor() ? *Hit.GetActor()->GetName() : TEXT("none"),
				Component ? *Component->GetName() : TEXT("none"),
				Component ? *Component->GetCollisionProfileName().ToString() : TEXT("none"),
				Component ? static_cast<int32>(Component->GetCollisionObjectType()) : INDEX_NONE,
				Component ? static_cast<int32>(Component->GetCollisionEnabled()) : INDEX_NONE,
				Component ? static_cast<int32>(Component->GetCollisionResponseToChannel(ECC_Pawn)) : INDEX_NONE,
				Hit.bStartPenetrating ? 1 : 0,
				Hit.PenetrationDepth,
				Hit.Time,
				Hit.ImpactNormal.X,
				Hit.ImpactNormal.Y,
				Hit.ImpactNormal.Z);
		}

		bool HasLiftedTerrainBlocker(
			UWorld* World,
			ACLMPlanet* Planet,
			const FProbeHit& A,
			const FProbeHit& B)
		{
			FCollisionQueryParams Params(SCENE_QUERY_STAT(RedFusedTerrainLiftedSweep), true);
			Params.bTraceComplex = true;
			TArray<FHitResult> Hits;
			World->SweepMultiByObjectType(
				Hits,
				A.Position + A.Direction * LiftedSweepClearanceCm,
				B.Position + B.Direction * LiftedSweepClearanceCm,
				FQuat::Identity,
				FCollisionObjectQueryParams(ECC_WorldDynamic),
				FCollisionShape::MakeSphere(LiftedSweepRadiusCm),
				Params);

			for (const FHitResult& Hit : Hits)
			{
				if (IsOwnedPlanetChunk(Hit, Planet))
				{
					return true;
				}
			}
			return false;
		}

		void CollectSeamVertices(
			ACLMPlanet* Planet,
			TArray<FSeamVertex>& OutPositiveX,
			TArray<FSeamVertex>& OutPositiveY)
		{
			UWorld* World = Planet ? Planet->GetWorld() : nullptr;
			if (!World)
			{
				return;
			}

			const FVector Center = Planet->GetActorLocation();
			for (TActorIterator<ACLMPlanetChunk> It(World); It; ++It)
			{
				ACLMPlanetChunk* Chunk = *It;
				if (!IsValid(Chunk) || Chunk->GetOwner() != Planet || !Chunk->bActive
					|| Chunk->bBuilding || !Chunk->IsTerrainCollisionEnabled())
				{
					continue;
				}

				UProceduralMeshComponent* Mesh = Chunk->FindComponentByClass<UProceduralMeshComponent>();
				const FProcMeshSection* Section = Mesh ? Mesh->GetProcMeshSection(0) : nullptr;
				if (!Section
					|| Mesh->GetCollisionEnabled() != ECollisionEnabled::QueryAndPhysics
					|| Mesh->GetCollisionObjectType() != ECC_WorldDynamic
					|| Mesh->GetCollisionResponseToChannel(ECC_Pawn) != ECR_Block)
				{
					continue;
				}

				const FVector ChunkDirection = (Chunk->GetActorLocation() - Center).GetSafeNormal();
				TArray<FSeamVertex>* Destination = nullptr;
				if (ChunkDirection.X > 0.0f && ChunkDirection.Y > 0.0f)
				{
					Destination = ChunkDirection.X > ChunkDirection.Y ? &OutPositiveX : &OutPositiveY;
				}
				if (!Destination)
				{
					continue;
				}

				for (const FProcMeshVertex& Vertex : Section->ProcVertexBuffer)
				{
					const FVector WorldPosition = Chunk->GetActorTransform().TransformPosition(Vertex.Position);
					const FVector SurfaceDirection = (WorldPosition - Center).GetSafeNormal();
					if (SurfaceDirection.X <= 0.0f || SurfaceDirection.Y <= 0.0f
						|| FMath::Abs(SurfaceDirection.X - SurfaceDirection.Y) > 1.0e-5f)
					{
						continue;
					}

					FSeamVertex& SeamVertex = Destination->AddDefaulted_GetRef();
					SeamVertex.Direction = SurfaceDirection;
					SeamVertex.Position = WorldPosition;
					SeamVertex.Normal = Vertex.Normal.GetSafeNormal();
				}
			}
		}

		int32 ResolveDominantCubeFace(const FVector& Direction)
		{
			const FVector UnitDirection = Direction.GetSafeNormal();
			int32 BestFace = INDEX_NONE;
			float BestDot = -1.0f;
			for (int32 Face = 0; Face < PlanetGenMacroCubeFaceCount; ++Face)
			{
				const float Dot = FVector::DotProduct(UnitDirection, GetFaceNormal(Face));
				if (Dot > BestDot)
				{
					BestDot = Dot;
					BestFace = Face;
				}
			}
			return BestFace;
		}

		FIntVector ResolveDirectionChunkKey(
			const ACLMPlanet* Planet,
			const FVector& Direction)
		{
			FPlanetGenMacroCubeAddress Address;
			const int32 ChunksPerFace = GetChunksPerFace(Planet);
			if (ChunksPerFace <= 0
				|| !FPlanetGenMacroHeightfieldCapture::DirectionToFaceUV(Direction, Address)
				|| !Address.bIsValid)
			{
				return FIntVector(INDEX_NONE, INDEX_NONE, INDEX_NONE);
			}
			return FIntVector(
				static_cast<int32>(Address.Face),
				FMath::Clamp(FMath::FloorToInt(Address.UV01.X * ChunksPerFace),
					0, ChunksPerFace - 1),
				FMath::Clamp(FMath::FloorToInt(Address.UV01.Y * ChunksPerFace),
					0, ChunksPerFace - 1));
		}

		FIntVector ResolveActorChunkKey(
			const ACLMPlanet* Planet,
			const ACLMPlanetChunk* Chunk)
		{
			if (!Planet || !Chunk)
			{
				return FIntVector(INDEX_NONE, INDEX_NONE, INDEX_NONE);
			}
			const int32 ChunksPerFace = GetChunksPerFace(Planet);
			const FVector ChunkDirection =
				(Chunk->GetActorLocation() - Planet->GetActorLocation()).GetSafeNormal();
			FIntVector BestKey(INDEX_NONE, INDEX_NONE, INDEX_NONE);
			float BestDot = -1.f;
			for (int32 Face = 0; Face < PlanetGenMacroCubeFaceCount; ++Face)
			{
				for (int32 U = 0; U < ChunksPerFace; ++U)
				{
					for (int32 V = 0; V < ChunksPerFace; ++V)
					{
						const FIntVector Candidate(Face, U, V);
						const float Dot = FVector::DotProduct(
							ChunkDirection, GetChunkCenterDirection(ChunksPerFace, Candidate));
						if (Dot > BestDot)
						{
							BestDot = Dot;
							BestKey = Candidate;
						}
					}
				}
			}
			return BestDot >= ChunkActorDirectionMatchDotTolerance
				? BestKey
				: FIntVector(INDEX_NONE, INDEX_NONE, INDEX_NONE);
		}

		void CollectExactBoundaryVertices(
			ACLMPlanet* Planet,
			TConstArrayView<int32> ExpectedFaces,
			const FVector& BoundaryDirection,
			const bool bCorner,
			TMap<int32, TArray<FSeamVertex>>& OutVerticesByFace)
		{
			OutVerticesByFace.Reset();
			UWorld* World = Planet ? Planet->GetWorld() : nullptr;
			if (!World || ExpectedFaces.Num() < 2)
			{
				return;
			}

			const FVector Center = Planet->GetActorLocation();
			const FVector UnitBoundary = BoundaryDirection.GetSafeNormal();
			for (TActorIterator<ACLMPlanetChunk> It(World); It; ++It)
			{
				ACLMPlanetChunk* Chunk = *It;
				if (!IsValid(Chunk) || Chunk->GetOwner() != Planet || !Chunk->bActive
					|| Chunk->bBuilding || !Chunk->IsTerrainCollisionEnabled())
				{
					continue;
				}

				const int32 Face = ResolveDominantCubeFace(
					Chunk->GetActorLocation() - Center);
				bool bExpectedFace = false;
				for (const int32 ExpectedFace : ExpectedFaces)
				{
					bExpectedFace |= Face == ExpectedFace;
				}
				if (!bExpectedFace)
				{
					continue;
				}

				UProceduralMeshComponent* Mesh =
					Chunk->FindComponentByClass<UProceduralMeshComponent>();
				const FProcMeshSection* Section = Mesh ? Mesh->GetProcMeshSection(0) : nullptr;
				if (!Section || Mesh->GetCollisionEnabled() == ECollisionEnabled::NoCollision)
				{
					continue;
				}

				for (const FProcMeshVertex& Vertex : Section->ProcVertexBuffer)
				{
					const FVector WorldPosition =
						Chunk->GetActorTransform().TransformPosition(Vertex.Position);
					const FVector SurfaceDirection = (WorldPosition - Center).GetSafeNormal();
					bool bOnBoundary = FVector::DotProduct(
						SurfaceDirection, UnitBoundary) >= 1.0f - 1.0e-7f;
					if (!bCorner)
					{
						const float FaceADot = FVector::DotProduct(
							SurfaceDirection, GetFaceNormal(ExpectedFaces[0]));
						const float FaceBDot = FVector::DotProduct(
							SurfaceDirection, GetFaceNormal(ExpectedFaces[1]));
						bOnBoundary = FaceADot > 0.0f && FaceBDot > 0.0f
							&& FMath::Abs(FaceADot - FaceBDot) <= 1.0e-5f;
					}
					if (!bOnBoundary)
					{
						continue;
					}

					FSeamVertex& BoundaryVertex =
						OutVerticesByFace.FindOrAdd(Face).AddDefaulted_GetRef();
					BoundaryVertex.Direction = SurfaceDirection;
					BoundaryVertex.Position = WorldPosition;
					BoundaryVertex.Normal = Chunk->GetActorTransform()
						.TransformVectorNoScale(Vertex.Normal).GetSafeNormal();
				}
			}
		}
	}

	class FRedFusedTerrainContinuityCommand final : public IAutomationLatentCommand
	{
	public:
		explicit FRedFusedTerrainContinuityCommand(FAutomationTestBase* InTest)
			: Test(InTest)
			, PhaseStartedAtSeconds(FPlatformTime::Seconds())
		{
		}

		virtual bool Update() override
		{
			if (!Test)
			{
				return true;
			}

			if (Phase == Private::EVerificationPhase::WaitForWorld)
			{
				return UpdateWaitForWorld();
			}

			if (!IsValid(World.Get()) || !IsValid(Planet.Get()) || !IsValid(StreamingSource.Get()))
			{
				return Fail(TEXT("The PIE world, fused planet, or transient streaming source became invalid."));
			}

			if (Phase == Private::EVerificationPhase::MovingCollisionRing)
			{
				return UpdateMovingCollisionRing();
			}

			TArray<Private::FProbeHit> Hits;
			Hits.Reserve(Probes.Num());
			for (const Private::FProbe& Probe : Probes)
			{
				Private::FProbeHit& Hit = Hits.AddDefaulted_GetRef();
				if (!Private::TraceOwnedTerrain(World.Get(), Planet.Get(), Probe.Direction, Hit))
				{
					if (HasPhaseTimedOut())
					{
						return Fail(FString::Printf(
							TEXT("Timed out waiting for cooked PlanetGen collision during %s at probe %s."),
							*PhaseName(), *Probe.Label));
					}
					return false;
				}
			}
			if (!ValidateCommonProbeResults(Hits))
			{
				return Finish();
			}

			switch (Phase)
			{
			case Private::EVerificationPhase::CubeFaceSeam:
				if (!ValidateCubeFaceSeam(Hits))
				{
					return Finish();
				}
				PrepareAuthoringPatchFeather();
				return false;

			case Private::EVerificationPhase::AuthoringPatchFeather:
				UE_LOG(LogTemp, Display,
					TEXT("RED_FUSED_CONTINUITY_PATCH patch=%d probes=%d status=pass"),
					Private::AuthoringPatchIndex, Hits.Num());
				PrepareTerrainStampFeather();
				return false;

			case Private::EVerificationPhase::TerrainStampFeather:
				if (!ValidateTerrainStampFeather())
				{
					return Finish();
				}
				UE_LOG(LogTemp, Display,
					TEXT("RED_FUSED_CONTINUITY_STAMP stable_id=%d probes=%d status=pass"),
					VerifiedStampStableId, Hits.Num());
				StampProbeCount = Hits.Num();
				PrepareMovingCollisionRing();
				return false;

		default:
				return Finish();
			}
		}

	private:
		bool UpdateWaitForWorld()
		{
			UWorld* FoundWorld = Private::FindFusedPIEWorld();
			if (!FoundWorld)
			{
				if (HasPhaseTimedOut())
				{
					return Fail(TEXT("Timed out waiting for the fused-prototype PIE world."));
				}
				return false;
			}

			ACLMPlanet* FoundPlanet = nullptr;
			for (TActorIterator<ACLMPlanet> It(FoundWorld); It; ++It)
			{
				if (FoundPlanet)
				{
					return Fail(TEXT("Expected exactly one ACLMPlanet in the fused prototype."));
				}
				FoundPlanet = *It;
			}
			if (!IsValid(FoundPlanet))
			{
				if (HasPhaseTimedOut())
				{
					return Fail(TEXT("Timed out waiting for ACLMPlanet in the fused prototype."));
				}
				return false;
			}

			World = FoundWorld;
			Planet = FoundPlanet;
			if (!ValidateConfiguration())
			{
				return Finish();
			}

			FActorSpawnParameters SpawnParameters;
			SpawnParameters.ObjectFlags |= RF_Transient;
			SpawnParameters.Name = TEXT("RED_FusedTerrainContinuityStreamingSource");
			ATargetPoint* Source = FoundWorld->SpawnActor<ATargetPoint>(
				ATargetPoint::StaticClass(), FTransform::Identity, SpawnParameters);
			if (!IsValid(Source))
			{
				return Fail(TEXT("Failed to spawn the transient fused-terrain streaming source."));
			}
			Source->SetActorEnableCollision(false);
			Source->SetActorHiddenInGame(true);
			StreamingSource = Source;
			FoundPlanet->AdditionalStreamingSources.AddUnique(Source);

			UE_LOG(LogTemp, Display,
				TEXT("RED_FUSED_CONTINUITY_CONFIG map=%s radius_cm=%.3f macro_resolution=%d stamps=%d"),
				*FoundWorld->GetMapName(), FoundPlanet->PlanetRadius,
				FoundPlanet->MacroHeightfieldAsset ? FoundPlanet->MacroHeightfieldAsset->Resolution : 0,
				FoundPlanet->TerrainStamps.Num());

			PrepareCubeFaceSeam();
			return false;
		}

		bool ValidateConfiguration()
		{
			ACLMPlanet* P = Planet.Get();
			bool bValid = true;
			bValid &= Test->TestTrue(
				TEXT("The fused prototype uses the 50 km radius"),
				FMath::IsNearlyEqual(
					static_cast<double>(P->PlanetRadius),
					RedPlanet::FPlanet50KmProfile::RadiusCm,
					1.0));
			bValid &= Test->TestEqual(TEXT("The fused prototype uses 2 km chunks"), P->TileSize, 200000.0f);
			bValid &= Test->TestEqual(TEXT("The fused prototype caps at eight chunks per face"), P->MaxChunksPerFace, 8);
			bValid &= Test->TestEqual(TEXT("The fused prototype uses the verified blockout resolution"), P->Resolution, 32);
			bValid &= Test->TestTrue(TEXT("The fused macro heightfield is enabled"), P->bEnableMacroHeightfield);
			bValid &= Test->TestTrue(TEXT("The fused macro heightfield owns the terrain baseline"),
				FMath::IsNearlyEqual(P->MacroHeightfieldBlend, 1.0f));
			bValid &= Test->TestNotNull(TEXT("The fused macro heightfield asset is assigned"), P->MacroHeightfieldAsset.Get());
			if (!P->MacroHeightfieldAsset)
			{
				return false;
			}

			const UPlanetGenMacroHeightfieldAsset* Asset = P->MacroHeightfieldAsset;
			bValid &= Test->TestEqual(TEXT("The fused asset path is stable"), Asset->GetPathName(),
				FString(Private::FusedHeightfieldPath));
			bValid &= Test->TestEqual(TEXT("The fused asset is 257 by 257 per face"),
				Asset->Resolution, Private::ExpectedMacroResolution);
			const int32 ExpectedSamples = Private::ExpectedMacroResolution * Private::ExpectedMacroResolution;
			const TArray<uint16>* HeightFaces[] =
			{
				&Asset->PositiveX, &Asset->NegativeX, &Asset->PositiveY,
				&Asset->NegativeY, &Asset->PositiveZ, &Asset->NegativeZ
			};
			const TArray<uint8>* LandFaces[] =
			{
				&Asset->LandPositiveX, &Asset->LandNegativeX, &Asset->LandPositiveY,
				&Asset->LandNegativeY, &Asset->LandPositiveZ, &Asset->LandNegativeZ
			};
			const TArray<FColor>* BiomeFaces[] =
			{
				&Asset->BiomePositiveX, &Asset->BiomeNegativeX, &Asset->BiomePositiveY,
				&Asset->BiomeNegativeY, &Asset->BiomePositiveZ, &Asset->BiomeNegativeZ
			};
			for (int32 FaceIndex = 0; FaceIndex < PlanetGenMacroCubeFaceCount; ++FaceIndex)
			{
				bValid &= Test->TestEqual(
					FString::Printf(TEXT("Height face %d has every sample"), FaceIndex),
					HeightFaces[FaceIndex]->Num(), ExpectedSamples);
				bValid &= Test->TestEqual(
					FString::Printf(TEXT("Land face %d has every sample"), FaceIndex),
					LandFaces[FaceIndex]->Num(), ExpectedSamples);
				bValid &= Test->TestEqual(
					FString::Printf(TEXT("Biome face %d has every sample"), FaceIndex),
					BiomeFaces[FaceIndex]->Num(), ExpectedSamples);
			}

			bValid &= Test->TestEqual(TEXT("The fused prototype has 27 terrain stamps"),
				P->TerrainStamps.Num(), Private::ExpectedTerrainStampCount);
			TSet<int32> StableIds;
			for (const FPlanetGenTerrainStamp& Stamp : P->TerrainStamps)
			{
				bValid &= Test->TestTrue(
					FString::Printf(TEXT("Terrain stamp %d is enabled"), Stamp.StableId), Stamp.bEnabled);
				StableIds.Add(Stamp.StableId);
			}
			for (int32 StableId = 0; StableId < Private::ExpectedTerrainStampCount; ++StableId)
			{
				bValid &= Test->TestTrue(
					FString::Printf(TEXT("Terrain stamp stable ID %d exists"), StableId),
					StableIds.Contains(StableId));
			}

			return bValid;
		}

		bool ValidateCommonProbeResults(const TArray<Private::FProbeHit>& Hits)
		{
			bool bValid = true;
			for (int32 Index = 0; Index < Hits.Num(); ++Index)
			{
				const Private::FProbeHit& Hit = Hits[Index];
				bValid &= Test->TestTrue(
					FString::Printf(TEXT("%s probe %d has an outward collision normal"), *PhaseName(), Index),
					FVector::DotProduct(Hit.Normal, Hit.Direction) > 0.5f);
				bValid &= Test->TestTrue(
					FString::Printf(TEXT("%s probe %d hit a collision-enabled chunk"), *PhaseName(), Index),
					Hit.Chunk.IsValid() && Hit.Chunk->IsTerrainCollisionEnabled());
			}

			for (int32 Index = 0; Index + 1 < Hits.Num(); ++Index)
			{
				bValid &= Test->TestFalse(
					FString::Printf(TEXT("%s lifted segment %d has no PlanetGen collision wall"), *PhaseName(), Index),
					Private::HasLiftedTerrainBlocker(
						World.Get(), Planet.Get(), Hits[Index], Hits[Index + 1]));
			}

			if (!bWorldStaticPositiveControlValidated && Hits.Num() >= 2)
			{
				bValid &= ValidateWorldStaticPositiveControl(Hits[0], Hits[1]);
			}

			int32 PawnBlockerCount = 0;
			for (int32 Index = 0; Index + 1 < Hits.Num(); ++Index)
			{
				++StaticRoutePawnSweepTotal;
				FHitResult BlockingHit;
				if (Private::HasPawnTraversalBlocker(
					World.Get(), Hits[Index], Hits[Index + 1], &BlockingHit))
				{
					++PawnBlockerCount;
					Private::LogPawnTraversalBlocker(
						TEXT("RED_FUSED_PAWN_ROUTE_BLOCKER"), PhaseName(), Index, BlockingHit);
				}
			}
			bValid &= Test->TestEqual(
				FString::Printf(TEXT("%s pawn route has no blocking wall"), *PhaseName()),
				PawnBlockerCount, 0);
			return bValid;
		}

		bool ValidateWorldStaticPositiveControl(
			const Private::FProbeHit& A,
			const Private::FProbeHit& B)
		{
			UWorld* TestWorld = World.Get();
			if (!TestWorld)
			{
				Test->AddError(TEXT("The WorldStatic pawn-route positive control has no PIE world."));
				return false;
			}

			const FVector MidDirection = (A.Direction + B.Direction).GetSafeNormal();
			const float CenterClearance = Private::PawnTraversalCapsuleHalfHeightCm
				+ Private::PawnTraversalClearanceCm;
			const FVector Start = A.Position + A.Direction * CenterClearance;
			const FVector End = B.Position + B.Direction * CenterClearance;
			FVector TravelDirection = FVector::VectorPlaneProject(
				End - Start, MidDirection).GetSafeNormal();
			if (TravelDirection.IsNearlyZero())
			{
				Test->AddError(TEXT("The WorldStatic pawn-route positive control has no tangent travel direction."));
				return false;
			}

			const FVector WallLocation = FMath::Lerp(Start, End, 0.5f);
			const FQuat WallRotation = FRotationMatrix::MakeFromXZ(
				TravelDirection, MidDirection).ToQuat();
			FActorSpawnParameters SpawnParameters;
			SpawnParameters.ObjectFlags |= RF_Transient;
			SpawnParameters.Name = MakeUniqueObjectName(
				TestWorld, AActor::StaticClass(), TEXT("RED_WorldStaticPawnRoutePositiveControl"));
			AActor* WallActor = TestWorld->SpawnActor<AActor>(
				AActor::StaticClass(), FTransform(WallRotation, WallLocation), SpawnParameters);
			if (!WallActor)
			{
				Test->AddError(TEXT("Failed to spawn the WorldStatic pawn-route positive-control actor."));
				return false;
			}

			UBoxComponent* Wall = NewObject<UBoxComponent>(
				WallActor, TEXT("RED_WorldStaticPawnRoutePositiveControlBox"), RF_Transient);
			if (!Wall)
			{
				WallActor->Destroy();
				Test->AddError(TEXT("Failed to create the WorldStatic pawn-route positive-control box."));
				return false;
			}
			WallActor->SetRootComponent(Wall);
			WallActor->AddInstanceComponent(Wall);
			Wall->SetBoxExtent(FVector(
				5.0f,
				Private::PawnTraversalCapsuleRadiusCm * 3.0f,
				Private::PawnTraversalCapsuleHalfHeightCm * 2.0f), false);
			Wall->SetCollisionEnabled(ECollisionEnabled::QueryOnly);
			Wall->SetCollisionObjectType(ECC_WorldStatic);
			Wall->SetCollisionResponseToAllChannels(ECR_Ignore);
			Wall->SetCollisionResponseToChannel(ECC_Pawn, ECR_Block);
			Wall->SetGenerateOverlapEvents(false);
			Wall->RegisterComponent();
			Wall->SetWorldTransform(FTransform(WallRotation, WallLocation));
			Wall->UpdateBounds();
			Wall->UpdateOverlaps();

			FHitResult BlockingHit;
			const bool bDetected = Private::HasPawnTraversalBlocker(
				TestWorld, A, B, &BlockingHit);
			bool bValid = true;
			bValid &= Test->TestTrue(
				TEXT("The pawn-route detector catches a transient WorldStatic wall"), bDetected);
			bValid &= Test->TestTrue(
				TEXT("The WorldStatic positive control reports the exact box component"),
				bDetected && BlockingHit.GetComponent() == Wall);
			bValid &= Test->TestEqual(
				TEXT("The positive-control box is WorldStatic"),
				Wall->GetCollisionObjectType(), ECC_WorldStatic);
			bValid &= Test->TestEqual(
				TEXT("The positive-control box blocks the Pawn channel"),
				Wall->GetCollisionResponseToChannel(ECC_Pawn), ECR_Block);
			if (bDetected)
			{
				UE_LOG(LogTemp, Display,
					TEXT("RED_FUSED_WORLDSTATIC_POSITIVE_CONTROL actor=%s component=%s profile=%s object_channel=%d pawn_response=%d status=%s"),
					*WallActor->GetName(), *Wall->GetName(),
					*Wall->GetCollisionProfileName().ToString(),
					static_cast<int32>(Wall->GetCollisionObjectType()),
					static_cast<int32>(Wall->GetCollisionResponseToChannel(ECC_Pawn)),
					bValid ? TEXT("pass") : TEXT("fail"));
			}

			Wall->SetCollisionEnabled(ECollisionEnabled::NoCollision);
			WallActor->Destroy();
			if (bValid)
			{
				bWorldStaticPositiveControlValidated = true;
				++WorldStaticPositiveControlCount;
			}
			return bValid;
		}

		bool ValidateCubeFaceSeam(const TArray<Private::FProbeHit>& Hits)
		{
			bool bPositiveXHit = false;
			bool bPositiveYHit = false;
			for (const Private::FProbeHit& Hit : Hits)
			{
				if (!Hit.Chunk.IsValid())
				{
					continue;
				}
				const FVector ChunkDirection =
					(Hit.Chunk->GetActorLocation() - Planet->GetActorLocation()).GetSafeNormal();
				bPositiveXHit |= ChunkDirection.X > ChunkDirection.Y;
				bPositiveYHit |= ChunkDirection.Y > ChunkDirection.X;
			}

			bool bValid = true;
			bValid &= Test->TestTrue(TEXT("Radial collision probes represented the +X cube face"), bPositiveXHit);
			bValid &= Test->TestTrue(TEXT("Radial collision probes represented the +Y cube face"), bPositiveYHit);

			TArray<Private::FSeamVertex> PositiveXVertices;
			TArray<Private::FSeamVertex> PositiveYVertices;
			Private::CollectSeamVertices(Planet.Get(), PositiveXVertices, PositiveYVertices);
			int32 MatchedPairs = 0;
			float MaxPositionDeltaCm = 0.0f;
			float MinNormalDot = 1.0f;
			for (const Private::FSeamVertex& XVertex : PositiveXVertices)
			{
				const Private::FSeamVertex* BestYVertex = nullptr;
				float BestDirectionDot = -1.0f;
				for (const Private::FSeamVertex& YVertex : PositiveYVertices)
				{
					const float DirectionDot = FVector::DotProduct(XVertex.Direction, YVertex.Direction);
					if (DirectionDot > BestDirectionDot)
					{
						BestDirectionDot = DirectionDot;
						BestYVertex = &YVertex;
					}
				}
				if (!BestYVertex || BestDirectionDot < Private::DirectionMatchDotTolerance)
				{
					continue;
				}

				++MatchedPairs;
				MaxPositionDeltaCm = FMath::Max(
					MaxPositionDeltaCm, FVector::Distance(XVertex.Position, BestYVertex->Position));
				MinNormalDot = FMath::Min(
					MinNormalDot, FVector::DotProduct(XVertex.Normal, BestYVertex->Normal));
			}

			bValid &= Test->TestTrue(TEXT("At least two runtime seam vertices matched across +X/+Y"),
				MatchedPairs >= 2);
			bValid &= Test->TestTrue(TEXT("Matched runtime seam positions stay within one centimetre"),
				MaxPositionDeltaCm <= Private::SharedSeamPositionToleranceCm);
			bValid &= Test->TestTrue(TEXT("Matched runtime seam normals remain continuous"),
				MinNormalDot >= Private::SharedSeamNormalDotTolerance);

			UE_LOG(LogTemp, Display,
				TEXT("RED_FUSED_CONTINUITY_SEAM probes=%d pairs=%d max_position_delta_cm=%.6f min_normal_dot=%.9f status=%s"),
				Hits.Num(), MatchedPairs, MaxPositionDeltaCm, MinNormalDot,
				bValid ? TEXT("pass") : TEXT("fail"));
			return bValid;
		}

		bool ValidateTerrainStampFeather()
		{
			bool bCore = false;
			bool bFeather = false;
			bool bOutside = false;
			for (const float Influence : StampInfluences)
			{
				bCore |= FMath::IsNearlyEqual(Influence, 1.0f);
				bFeather |= Influence > 0.0f && Influence < 1.0f;
				bOutside |= FMath::IsNearlyZero(Influence);
			}

			bool bValid = true;
			bValid &= Test->TestTrue(TEXT("The live terrain-stamp path samples its constant core"), bCore);
			bValid &= Test->TestTrue(TEXT("The live terrain-stamp path samples its smooth feather"), bFeather);
			bValid &= Test->TestTrue(TEXT("The live terrain-stamp path samples outside its influence"), bOutside);
			return bValid;
		}

		void PrepareCubeFaceSeam()
		{
			Probes.Reset();
			const FVector SeamDirection = FVector(1.0f, 1.0f, 0.0f).GetSafeNormal();
			constexpr int32 ProbeCount = 13;
			for (int32 Index = 0; Index < ProbeCount; ++Index)
			{
				const double Alpha = static_cast<double>(Index) / static_cast<double>(ProbeCount - 1);
				const double ArcDistanceCm = FMath::Lerp(-20000.0, 20000.0, Alpha);
				Private::FProbe& Probe = Probes.AddDefaulted_GetRef();
				Probe.Direction = Private::RotateAlongGreatCircle(
					SeamDirection, FVector::UpVector, ArcDistanceCm, Planet->PlanetRadius);
				Probe.Label = FString::Printf(TEXT("cube_seam_%02d"), Index);
			}
			CubeProbeCount = Probes.Num();
			StartPhase(Private::EVerificationPhase::CubeFaceSeam, SeamDirection);
		}

		void PrepareAuthoringPatchFeather()
		{
			Probes.Reset();
			const FPlanetRegionMetadata& Region =
				FPlanetRegionService::Get().GetRegionChecked(Private::AuthoringPatchIndex);
			constexpr int32 ProbeCount = 25;
			for (int32 Index = 0; Index < ProbeCount; ++Index)
			{
				const double Alpha = static_cast<double>(Index) / static_cast<double>(ProbeCount - 1);
				const double EastOffsetCm = FMath::Lerp(240000.0, 430000.0, Alpha);
				Private::FProbe& Probe = Probes.AddDefaulted_GetRef();
				Probe.Direction = FVector(FPlanetRegionService::ExpMapDirection(
					Region.UnitSite,
					FVector2d(EastOffsetCm, 0.0),
					Planet->PlanetRadius));
				Probe.Label = FString::Printf(TEXT("patch_13_feather_%02d"), Index);
			}
			PatchProbeCount = Probes.Num();
			StartPhase(Private::EVerificationPhase::AuthoringPatchFeather,
				Probes[ProbeCount / 2].Direction);
		}

		void PrepareTerrainStampFeather()
		{
			Probes.Reset();
			StampInfluences.Reset();
			const FPlanetGenTerrainStamp* Stamp = Planet->TerrainStamps.FindByPredicate(
				[](const FPlanetGenTerrainStamp& Candidate)
				{
					return Candidate.bEnabled
						&& Candidate.StableId == Private::AuthoringPatchIndex
						&& Candidate.CoreRadiusCm > 0.0f
						&& Candidate.FeatherRadiusCm > 0.0f;
				});
			if (!Stamp)
			{
				Test->AddError(TEXT("The fused prototype has no usable enabled terrain stamp with stable ID 13."));
				Phase = Private::EVerificationPhase::Finished;
				return;
			}

			VerifiedStampStableId = Stamp->StableId;
			const double OuterRadiusCm = Stamp->CoreRadiusCm + Stamp->FeatherRadiusCm;
			const double DistancesCm[] =
			{
				0.0,
				Stamp->CoreRadiusCm * 0.5,
				Stamp->CoreRadiusCm,
				Stamp->CoreRadiusCm + Stamp->FeatherRadiusCm * 0.25,
				Stamp->CoreRadiusCm + Stamp->FeatherRadiusCm * 0.50,
				Stamp->CoreRadiusCm + Stamp->FeatherRadiusCm * 0.75,
				OuterRadiusCm,
				OuterRadiusCm + 5000.0
			};
			const FPlanetTangentFrame Frame = FPlanetRegionService::MakeTangentFrame(
				FVector3d(Stamp->SurfaceDirection));
			const FVector RotationAxis = FVector3d::CrossProduct(
				FVector3d(Stamp->SurfaceDirection).GetSafeNormal(), Frame.UnitEast).GetSafeNormal();
			for (int32 Index = 0; Index < UE_ARRAY_COUNT(DistancesCm); ++Index)
			{
				Private::FProbe& Probe = Probes.AddDefaulted_GetRef();
				Probe.Direction = Private::RotateAlongGreatCircle(
					Stamp->SurfaceDirection, RotationAxis, DistancesCm[Index], Planet->PlanetRadius);
				Probe.Label = FString::Printf(TEXT("stamp_13_feather_%02d"), Index);
				StampInfluences.Add(PlanetGenTerrainStamp::EvaluateInfluence(
					static_cast<float>(DistancesCm[Index]),
					Stamp->CoreRadiusCm,
					Stamp->FeatherRadiusCm));
			}
			StartPhase(Private::EVerificationPhase::TerrainStampFeather,
				Probes[Probes.Num() / 2].Direction);
		}

		void PrepareMovingCollisionRing()
		{
			Probes.Reset();
			Phase = Private::EVerificationPhase::MovingCollisionRing;
			PhaseStartedAtSeconds = FPlatformTime::Seconds();
			MovingStage = Private::EMovingVerificationStage::WaitForInitialSettle;
			MovingWaypointIndex = 0;
			MovingTransitionCount = 0;
			MovingRouteProbeTotal = 0;
			MovingLiftedSweepTotal = 0;
			MovingImmediateRetainedHitTotal = 0;
			MovingVisitedChunkKeys.Reset();
			MovingWaypoints.Reset();

			const int32 ChunksPerFace = Private::GetChunksPerFace(Planet.Get());
			if (!Test->TestEqual(TEXT("The moving collision-ring fixture resolves six chunks per face"),
				ChunksPerFace, 6))
			{
				Phase = Private::EVerificationPhase::Finished;
				return;
			}

			for (int32 U = 1; U <= 4; ++U)
			{
				MovingWaypoints.Add(Private::GetChunkCenterDirection(
					ChunksPerFace, FIntVector(0, U, 3)));
			}
			if (!Test->TestEqual(TEXT("The moving collision-ring fixture has four waypoints"),
				MovingWaypoints.Num(), Private::MovingWaypointCount))
			{
				Phase = Private::EVerificationPhase::Finished;
				return;
			}

			CapturePlayerStreamingSources();
			MoveAllStreamingSources(MovingWaypoints[0]);
			MovingTargetKeys = Private::GetExpectedCollisionKeys(
				Planet.Get(), MovingWaypoints[0]);
			MovingStartKeys = MovingTargetKeys;
			Test->TestEqual(TEXT("The initial moving collision ring contains 21 chunks"),
				MovingTargetKeys.Num(), Private::ExpectedCollisionChunksPerWaypoint);

			UE_LOG(LogTemp, Display,
				TEXT("RED_FUSED_MOVING_RING_BEGIN waypoints=%d chunks_per_face=%d collision_chunks=%d"),
				MovingWaypoints.Num(), ChunksPerFace, MovingTargetKeys.Num());
		}

		bool UpdateMovingCollisionRing()
		{
			SyncPlayerStreamingSources();

			int32 ReadyTargetCount = 0;
			int32 ReadyExitedCount = 0;
			if (!IsMovingTransitionSettled(ReadyTargetCount, ReadyExitedCount))
			{
				if (HasPhaseTimedOut())
				{
					LogMovingSettleDiagnostics();
					return Fail(FString::Printf(
						TEXT("Timed out settling moving collision ring at waypoint %d: target_ready=%d/%d exited_ready=%d/%d."),
						MovingWaypointIndex,
						ReadyTargetCount, MovingTargetKeys.Num(),
						ReadyExitedCount, MovingExitedKeys.Num()));
				}
				return false;
			}

			if (MovingStage == Private::EMovingVerificationStage::WaitForInitialSettle)
			{
				MovingPreviousKeys = MovingTargetKeys;
				UE_LOG(LogTemp, Display,
					TEXT("RED_FUSED_MOVING_RING_SETTLED waypoint=0 collision_chunks=%d"),
					MovingPreviousKeys.Num());
				if (!BeginMovingTransition(1))
				{
					return Finish();
				}
				return false;
			}

			if (!ValidateMovingRoute(
				MovingWaypoints[MovingWaypointIndex - 1],
				MovingWaypoints[MovingWaypointIndex]))
			{
				return Finish();
			}

			++MovingTransitionCount;
			UE_LOG(LogTemp, Display,
				TEXT("RED_FUSED_MOVING_RING_TRANSITION move=%d retained=%d entered=%d exited=%d immediate_retained_hits=%d route_probes=%d status=pass"),
				MovingTransitionCount,
				MovingRetainedKeys.Num(), MovingEnteredKeys.Num(), MovingExitedKeys.Num(),
				MovingLastImmediateRetainedHits, Private::MovingRouteProbeCount);

			MovingPreviousKeys = MovingTargetKeys;
			if (MovingWaypointIndex + 1 < MovingWaypoints.Num())
			{
				if (!BeginMovingTransition(MovingWaypointIndex + 1))
				{
					return Finish();
				}
				return false;
			}

			TSet<FIntVector> StartEndOverlap;
			for (const FIntVector& Key : MovingStartKeys)
			{
				if (MovingTargetKeys.Contains(Key))
				{
					StartEndOverlap.Add(Key);
				}
			}
			bool bValid = true;
			bValid &= Test->TestEqual(TEXT("The moving collision ring completed three transitions"),
				MovingTransitionCount, Private::MovingWaypointCount - 1);
			bValid &= Test->TestEqual(TEXT("The moving route sampled 75 grounded points"),
				MovingRouteProbeTotal,
				Private::MovingRouteProbeCount * (Private::MovingWaypointCount - 1));
			bValid &= Test->TestEqual(TEXT("The moving route performed 72 lifted sweeps"),
				MovingLiftedSweepTotal,
				(Private::MovingRouteProbeCount - 1) * (Private::MovingWaypointCount - 1));
			bValid &= Test->TestEqual(TEXT("The static seam, patch, and stamp routes performed 43 pawn sweeps"),
				StaticRoutePawnSweepTotal, Private::ExpectedStaticRoutePawnSweepCount);
			bValid &= Test->TestEqual(TEXT("The moving route performed 72 pawn sweeps"),
				MovingPawnSweepTotal, Private::ExpectedMovingRoutePawnSweepCount);
			bValid &= Test->TestEqual(TEXT("The bounded continuity gate performed 115 pawn sweeps"),
				StaticRoutePawnSweepTotal + MovingPawnSweepTotal,
				Private::ExpectedTotalPawnSweepCount);
			bValid &= Test->TestEqual(TEXT("The WorldStatic positive control was detected exactly once"),
				WorldStaticPositiveControlCount, 1);
			bValid &= Test->TestTrue(TEXT("The moving route crossed at least four distinct terrain chunks"),
				MovingVisitedChunkKeys.Num() >= 4);
			bValid &= Test->TestEqual(TEXT("The start and end collision rings overlap by six chunks"),
				StartEndOverlap.Num(), 6);
			bValid &= Test->TestEqual(TEXT("Every retained collision chunk stayed queryable during all moves"),
				MovingImmediateRetainedHitTotal,
				Private::ExpectedRetainedChunksPerMove * (Private::MovingWaypointCount - 1));
			if (!bValid)
			{
				return Finish();
			}

			UE_LOG(LogTemp, Display,
				TEXT("RED_FUSED_CONTINUITY_MOVING_PASS transitions=%d collision_chunks=%d retained_hits=%d route_probes=%d lifted_sweeps=%d pawn_sweeps=%d distinct_chunks=%d start_end_overlap=%d"),
				MovingTransitionCount, MovingTargetKeys.Num(), MovingImmediateRetainedHitTotal,
				MovingRouteProbeTotal, MovingLiftedSweepTotal, MovingPawnSweepTotal,
				MovingVisitedChunkKeys.Num(),
				StartEndOverlap.Num());
			UE_LOG(LogTemp, Display,
				TEXT("RED_FUSED_CONTINUITY_PASS seam_probes=%d patch_probes=%d stamp_probes=%d moving_transitions=%d static_pawn_sweeps=%d moving_pawn_sweeps=%d total_pawn_sweeps=%d worldstatic_positive_control=%d"),
				CubeProbeCount, PatchProbeCount, StampProbeCount, MovingTransitionCount,
				StaticRoutePawnSweepTotal, MovingPawnSweepTotal,
				StaticRoutePawnSweepTotal + MovingPawnSweepTotal,
				WorldStaticPositiveControlCount);
			return Finish();
		}

		bool BeginMovingTransition(const int32 NextWaypointIndex)
		{
			MovingTargetKeys = Private::GetExpectedCollisionKeys(
				Planet.Get(), MovingWaypoints[NextWaypointIndex]);
			MovingRetainedKeys.Reset();
			MovingEnteredKeys.Reset();
			MovingExitedKeys.Reset();
			for (const FIntVector& Key : MovingTargetKeys)
			{
				(MovingPreviousKeys.Contains(Key) ? MovingRetainedKeys : MovingEnteredKeys).Add(Key);
			}
			for (const FIntVector& Key : MovingPreviousKeys)
			{
				if (!MovingTargetKeys.Contains(Key))
				{
					MovingExitedKeys.Add(Key);
				}
			}

			bool bValid = true;
			bValid &= Test->TestEqual(TEXT("A moving collision-ring waypoint contains 21 chunks"),
				MovingTargetKeys.Num(), Private::ExpectedCollisionChunksPerWaypoint);
			bValid &= Test->TestEqual(TEXT("A one-chunk move retains 16 collision chunks"),
				MovingRetainedKeys.Num(), Private::ExpectedRetainedChunksPerMove);
			bValid &= Test->TestEqual(TEXT("A one-chunk move enters five collision chunks"),
				MovingEnteredKeys.Num(), Private::ExpectedEnteredChunksPerMove);
			bValid &= Test->TestEqual(TEXT("A one-chunk move exits five collision chunks"),
				MovingExitedKeys.Num(), Private::ExpectedExitedChunksPerMove);
			if (!bValid)
			{
				return false;
			}

			MovingWaypointIndex = NextWaypointIndex;
			MoveAllStreamingSources(MovingWaypoints[MovingWaypointIndex]);
			MovingLastImmediateRetainedHits = 0;
			for (const FIntVector& Key : MovingRetainedKeys)
			{
				Private::FProbeHit Hit;
				if (Private::TraceOwnedTerrain(
					World.Get(), Planet.Get(),
					Private::GetChunkCenterDirection(Private::GetChunksPerFace(Planet.Get()), Key),
					Hit))
				{
					++MovingLastImmediateRetainedHits;
				}
			}
			MovingImmediateRetainedHitTotal += MovingLastImmediateRetainedHits;
			bValid &= Test->TestEqual(
				TEXT("Retained collision chunks remain queryable immediately after the source moves"),
				MovingLastImmediateRetainedHits, MovingRetainedKeys.Num());
			MovingStage = Private::EMovingVerificationStage::WaitForTransition;
			PhaseStartedAtSeconds = FPlatformTime::Seconds();
			return bValid;
		}

		bool IsMovingTransitionSettled(
			int32& OutReadyTargetCount,
			int32& OutReadyExitedCount) const
		{
			OutReadyTargetCount = 0;
			OutReadyExitedCount = 0;
			const int32 ChunksPerFace = Private::GetChunksPerFace(Planet.Get());
			for (const FIntVector& Key : MovingTargetKeys)
			{
				ACLMPlanetChunk* Chunk = FindActiveChunk(Key);
				Private::FProbeHit Hit;
				if (IsValid(Chunk) && !Chunk->bBuilding && Chunk->HasSurface()
					&& Chunk->IsTerrainCollisionEnabled()
					&& Private::TraceOwnedTerrain(
						World.Get(), Planet.Get(),
						Private::GetChunkCenterDirection(ChunksPerFace, Key), Hit))
				{
					++OutReadyTargetCount;
				}
			}

			for (const FIntVector& Key : MovingExitedKeys)
			{
				ACLMPlanetChunk* Chunk = FindActiveChunk(Key);
				Private::FProbeHit UnexpectedHit;
				const bool bStillHits = Private::TraceOwnedTerrain(
					World.Get(), Planet.Get(),
					Private::GetChunkCenterDirection(ChunksPerFace, Key), UnexpectedHit);
				if (IsValid(Chunk) && !Chunk->bBuilding && Chunk->HasSurface()
					&& !Chunk->IsTerrainCollisionEnabled() && !bStillHits)
				{
					++OutReadyExitedCount;
				}
			}

			return OutReadyTargetCount == MovingTargetKeys.Num()
				&& OutReadyExitedCount == MovingExitedKeys.Num();
		}

		ACLMPlanetChunk* FindActiveChunk(const FIntVector& Key) const
		{
			const FVector ExpectedDirection = Private::GetChunkCenterDirection(
				Private::GetChunksPerFace(Planet.Get()), Key);
			const FVector PlanetCenter = Planet->GetActorLocation();
			for (TActorIterator<ACLMPlanetChunk> It(World.Get()); It; ++It)
			{
				ACLMPlanetChunk* Chunk = *It;
				if (!IsValid(Chunk) || Chunk->GetOwner() != Planet.Get() || !Chunk->bActive)
				{
					continue;
				}
				const FVector Direction = (Chunk->GetActorLocation() - PlanetCenter).GetSafeNormal();
				if (FVector::DotProduct(Direction, ExpectedDirection)
					>= Private::ChunkActorDirectionMatchDotTolerance)
				{
					return Chunk;
				}
			}
			return nullptr;
		}

		void LogMovingSettleDiagnostics() const
		{
			const int32 ChunksPerFace = Private::GetChunksPerFace(Planet.Get());
			for (const FIntVector& Key : MovingTargetKeys)
			{
				ACLMPlanetChunk* Chunk = FindActiveChunk(Key);
				Private::FProbeHit Hit;
				const bool bHit = Private::TraceOwnedTerrain(
					World.Get(), Planet.Get(),
					Private::GetChunkCenterDirection(ChunksPerFace, Key), Hit);
				UE_LOG(LogTemp, Display,
					TEXT("RED_FUSED_MOVING_RING_TARGET key=(%d,%d,%d) actor=%s active=%d building=%d surface=%d collision=%d radial_hit=%d"),
					Key.X, Key.Y, Key.Z,
					Chunk ? *Chunk->GetName() : TEXT("none"),
					Chunk && Chunk->bActive ? 1 : 0,
					Chunk && Chunk->bBuilding ? 1 : 0,
					Chunk && Chunk->HasSurface() ? 1 : 0,
					Chunk && Chunk->IsTerrainCollisionEnabled() ? 1 : 0,
					bHit ? 1 : 0);
			}
			for (const FIntVector& Key : MovingExitedKeys)
			{
				ACLMPlanetChunk* Chunk = FindActiveChunk(Key);
				Private::FProbeHit Hit;
				const bool bHit = Private::TraceOwnedTerrain(
					World.Get(), Planet.Get(),
					Private::GetChunkCenterDirection(ChunksPerFace, Key), Hit);
				UE_LOG(LogTemp, Display,
					TEXT("RED_FUSED_MOVING_RING_EXIT key=(%d,%d,%d) actor=%s building=%d surface=%d collision=%d radial_hit=%d"),
					Key.X, Key.Y, Key.Z,
					Chunk ? *Chunk->GetName() : TEXT("none"),
					Chunk && Chunk->bBuilding ? 1 : 0,
					Chunk && Chunk->HasSurface() ? 1 : 0,
					Chunk && Chunk->IsTerrainCollisionEnabled() ? 1 : 0,
					bHit ? 1 : 0);
			}
		}

		FIntVector ResolveChunkKey(const ACLMPlanetChunk* Chunk) const
		{
			if (!Chunk)
			{
				return FIntVector(INDEX_NONE, INDEX_NONE, INDEX_NONE);
			}
			const FVector Direction =
				(Chunk->GetActorLocation() - Planet->GetActorLocation()).GetSafeNormal();
			const int32 ChunksPerFace = Private::GetChunksPerFace(Planet.Get());
			float BestDot = -1.0f;
			FIntVector BestKey(INDEX_NONE, INDEX_NONE, INDEX_NONE);
			for (int32 Face = 0; Face < 6; ++Face)
			{
				for (int32 U = 0; U < ChunksPerFace; ++U)
				{
					for (int32 V = 0; V < ChunksPerFace; ++V)
					{
						const FIntVector Key(Face, U, V);
						const float Dot = FVector::DotProduct(
							Direction, Private::GetChunkCenterDirection(ChunksPerFace, Key));
						if (Dot > BestDot)
						{
							BestDot = Dot;
							BestKey = Key;
						}
					}
				}
			}
			return BestKey;
		}

		bool ValidateMovingRoute(const FVector& StartDirection, const FVector& EndDirection)
		{
			TArray<Private::FProbeHit> RouteHits;
			RouteHits.Reserve(Private::MovingRouteProbeCount);
			for (int32 Index = 0; Index < Private::MovingRouteProbeCount; ++Index)
			{
				const float Alpha = static_cast<float>(Index)
					/ static_cast<float>(Private::MovingRouteProbeCount - 1);
				Private::FProbeHit& Hit = RouteHits.AddDefaulted_GetRef();
				if (!Private::TraceOwnedTerrain(
					World.Get(), Planet.Get(),
					Private::SlerpDirection(StartDirection, EndDirection, Alpha), Hit))
				{
					Test->AddError(FString::Printf(
						TEXT("Moving collision-ring route probe %d/%d found no cooked terrain."),
						Index, Private::MovingRouteProbeCount));
					return false;
				}
				if (FVector::DotProduct(Hit.Normal, Hit.Direction) <= 0.5f)
				{
					Test->AddError(FString::Printf(
						TEXT("Moving collision-ring route probe %d has an inward collision normal."), Index));
					return false;
				}
				MovingVisitedChunkKeys.Add(ResolveChunkKey(Hit.Chunk.Get()));
			}

			for (int32 Index = 0; Index + 1 < RouteHits.Num(); ++Index)
			{
				if (Private::HasLiftedTerrainBlocker(
					World.Get(), Planet.Get(), RouteHits[Index], RouteHits[Index + 1]))
				{
					Test->AddError(FString::Printf(
						TEXT("Moving collision-ring lifted route segment %d found a PlanetGen collision wall."),
						Index));
					return false;
				}

				++MovingPawnSweepTotal;
				FHitResult BlockingHit;
				if (Private::HasPawnTraversalBlocker(
					World.Get(), RouteHits[Index], RouteHits[Index + 1], &BlockingHit))
				{
					Private::LogPawnTraversalBlocker(
						TEXT("RED_FUSED_MOVING_PAWN_ROUTE_BLOCKER"),
						FString::Printf(TEXT("moving_transition_%d"), MovingWaypointIndex),
						Index,
						BlockingHit);
					Test->AddError(FString::Printf(
						TEXT("Moving collision-ring pawn route segment %d found a blocking wall."),
						Index));
					return false;
				}
			}
			MovingRouteProbeTotal += RouteHits.Num();
			MovingLiftedSweepTotal += FMath::Max(0, RouteHits.Num() - 1);
			return true;
		}

		void CapturePlayerStreamingSources()
		{
			StreamingPawnStates.Reset();
			for (TActorIterator<APawn> It(World.Get()); It; ++It)
			{
				APawn* Pawn = *It;
				if (!IsValid(Pawn) || (!Pawn->IsPlayerControlled() && Pawn->GetPlayerState() == nullptr))
				{
					continue;
				}
				Private::FStreamingPawnState& State = StreamingPawnStates.AddDefaulted_GetRef();
				State.Pawn = Pawn;
				State.OriginalLocation = Pawn->GetActorLocation();
				State.bOriginalCollisionEnabled = Pawn->GetActorEnableCollision();
				State.bOriginalHidden = Pawn->IsHidden();
				State.bOriginalTickEnabled = Pawn->IsActorTickEnabled();
				Pawn->SetActorEnableCollision(false);
				Pawn->SetActorTickEnabled(false);
			}
		}

		void MoveAllStreamingSources(const FVector& Direction)
		{
			MovingSourcePosition = Planet->GetActorLocation()
				+ Direction.GetSafeNormal()
					* (Planet->PlanetRadius + Planet->MaxHeight
						+ Private::StreamingSourceClearanceCm);
			StreamingSource->SetActorLocation(
				MovingSourcePosition, false, nullptr, ETeleportType::TeleportPhysics);
			SyncPlayerStreamingSources();
		}

		void SyncPlayerStreamingSources()
		{
			for (const Private::FStreamingPawnState& State : StreamingPawnStates)
			{
				if (State.Pawn.IsValid())
				{
					State.Pawn->SetActorLocation(
						MovingSourcePosition, false, nullptr, ETeleportType::TeleportPhysics);
				}
			}
		}

		void StartPhase(Private::EVerificationPhase NewPhase, const FVector& StreamingDirection)
		{
			Phase = NewPhase;
			PhaseStartedAtSeconds = FPlatformTime::Seconds();
			if (StreamingSource.IsValid() && Planet.IsValid())
			{
				StreamingSource->SetActorLocation(
					Planet->GetActorLocation()
						+ StreamingDirection.GetSafeNormal()
							* (Planet->PlanetRadius + Planet->MaxHeight + Private::StreamingSourceClearanceCm),
					false, nullptr, ETeleportType::TeleportPhysics);
			}
		}

		bool HasPhaseTimedOut() const
		{
			return FPlatformTime::Seconds() - PhaseStartedAtSeconds > Private::PhaseTimeoutSeconds;
		}

		FString PhaseName() const
		{
			switch (Phase)
			{
			case Private::EVerificationPhase::WaitForWorld: return TEXT("world startup");
			case Private::EVerificationPhase::CubeFaceSeam: return TEXT("cube-face seam");
			case Private::EVerificationPhase::AuthoringPatchFeather: return TEXT("authoring-patch feather");
			case Private::EVerificationPhase::TerrainStampFeather: return TEXT("terrain-stamp feather");
			case Private::EVerificationPhase::MovingCollisionRing: return TEXT("moving collision ring");
			default: return TEXT("finished");
			}
		}

		bool Fail(const FString& Message)
		{
			Test->AddError(Message);
			UE_LOG(LogTemp, Error, TEXT("RED_FUSED_CONTINUITY_FAIL phase=%s error=%s"),
				*PhaseName(), *Message);
			return Finish();
		}

		bool Finish()
		{
			for (const Private::FStreamingPawnState& State : StreamingPawnStates)
			{
				if (!State.Pawn.IsValid())
				{
					continue;
				}
				State.Pawn->SetActorLocation(
					State.OriginalLocation, false, nullptr, ETeleportType::TeleportPhysics);
				State.Pawn->SetActorEnableCollision(State.bOriginalCollisionEnabled);
				State.Pawn->SetActorHiddenInGame(State.bOriginalHidden);
				State.Pawn->SetActorTickEnabled(State.bOriginalTickEnabled);
			}
			StreamingPawnStates.Reset();
			if (Planet.IsValid() && StreamingSource.IsValid())
			{
				Planet->AdditionalStreamingSources.Remove(StreamingSource.Get());
			}
			if (StreamingSource.IsValid())
			{
				StreamingSource->Destroy();
			}
			Phase = Private::EVerificationPhase::Finished;
			return true;
		}

		FAutomationTestBase* Test = nullptr;
		TWeakObjectPtr<UWorld> World;
		TWeakObjectPtr<ACLMPlanet> Planet;
		TWeakObjectPtr<ATargetPoint> StreamingSource;
		Private::EVerificationPhase Phase = Private::EVerificationPhase::WaitForWorld;
		double PhaseStartedAtSeconds = 0.0;
		TArray<Private::FProbe> Probes;
		TArray<float> StampInfluences;
		TArray<Private::FStreamingPawnState> StreamingPawnStates;
		TArray<FVector> MovingWaypoints;
		TSet<FIntVector> MovingStartKeys;
		TSet<FIntVector> MovingPreviousKeys;
		TSet<FIntVector> MovingTargetKeys;
		TSet<FIntVector> MovingRetainedKeys;
		TSet<FIntVector> MovingEnteredKeys;
		TSet<FIntVector> MovingExitedKeys;
		TSet<FIntVector> MovingVisitedChunkKeys;
		FVector MovingSourcePosition = FVector::ZeroVector;
		Private::EMovingVerificationStage MovingStage =
			Private::EMovingVerificationStage::WaitForInitialSettle;
		int32 VerifiedStampStableId = INDEX_NONE;
		int32 CubeProbeCount = 0;
		int32 PatchProbeCount = 0;
		int32 StampProbeCount = 0;
		int32 MovingWaypointIndex = 0;
		int32 MovingTransitionCount = 0;
		int32 MovingRouteProbeTotal = 0;
		int32 MovingLiftedSweepTotal = 0;
		int32 StaticRoutePawnSweepTotal = 0;
		int32 MovingPawnSweepTotal = 0;
		int32 WorldStaticPositiveControlCount = 0;
		bool bWorldStaticPositiveControlValidated = false;
		int32 MovingLastImmediateRetainedHits = 0;
		int32 MovingImmediateRetainedHitTotal = 0;
	};

	class FRedFusedAllCubeBoundaryCommand final : public IAutomationLatentCommand
	{
	public:
		explicit FRedFusedAllCubeBoundaryCommand(FAutomationTestBase* InTest)
			: Test(InTest)
			, TestStartedAtSeconds(FPlatformTime::Seconds())
			, CaseStartedAtSeconds(FPlatformTime::Seconds())
		{
		}

		virtual bool Update() override
		{
			if (!Test)
			{
				return true;
			}
			if (Stage == EStage::WaitForWorld)
			{
				return InitializeWorld();
			}
			if (!World.IsValid() || !Planet.IsValid() || !StreamingSource.IsValid())
			{
				return Fail(TEXT("The all-boundary PIE world, planet, or streaming source became invalid."));
			}

			TArray<Private::FProbeHit> Hits;
			Hits.Reserve(Probes.Num());
			for (const Private::FProbe& Probe : Probes)
			{
				Private::FProbeHit& Hit = Hits.AddDefaulted_GetRef();
				if (!Private::TraceOwnedTerrain(World.Get(), Planet.Get(), Probe.Direction, Hit))
				{
					return WaitOrFail(FString::Printf(
						TEXT("Cooked collision was unavailable at %s."), *Probe.Label));
				}
			}
			TArray<Private::FProbeHit> TraversalHits;
			TraversalHits.Reserve(TraversalProbes.Num());
			for (const Private::FProbe& Probe : TraversalProbes)
			{
				Private::FProbeHit& Hit = TraversalHits.AddDefaulted_GetRef();
				if (!Private::TraceOwnedTerrain(World.Get(), Planet.Get(), Probe.Direction, Hit))
				{
					return WaitOrFail(FString::Printf(
						TEXT("Pawn-route support was unavailable at %s."), *Probe.Label));
				}
			}

			FBoundaryMeshAudit MeshAudit;
			const bool bCorner = Stage == EStage::Corners;
			if (!TryAuditBoundaryMesh(bCorner, MeshAudit))
			{
				FString Counts;
				for (const int32 Face : ExpectedFaces)
				{
					Counts += FString::Printf(
						TEXT(" face=%d raw=%d unique=%d"),
						Face,
						MeshAudit.RawSamplesPerFace.FindRef(Face),
						MeshAudit.UniqueSamplesPerFace.FindRef(Face));
				}
				return WaitOrFail(FString::Printf(
					TEXT("Exact shared runtime boundary vertices were not ready:%s"),
					*Counts));
			}
			if (!ValidateProbeSet(Hits, Probes, !bCorner)
				|| !ValidateTraversalSet(TraversalHits, TraversalProbes)
				|| !ValidateBoundaryMesh(MeshAudit, bCorner))
			{
				return Finish();
			}
			if (!ValidatePhysicalShipTraversal(TraversalHits, bCorner))
			{
				return Finish();
			}

			if (Stage == EStage::Edges)
			{
				++ValidatedEdgeCount;
				TotalEdgeProbeCount += Hits.Num();
				TotalEdgeLiftedSweepCount += FMath::Max(0, Hits.Num() - 1);
				TotalEdgePawnSweepCount += FMath::Max(0, TraversalHits.Num() - 1);
				TotalEdgeMatchedVertexPairs += MeshAudit.MatchedPairs;
				MaxEdgePositionDeltaCm = FMath::Max(
					MaxEdgePositionDeltaCm, MeshAudit.MaxPositionDeltaCm);
				MinEdgeNormalDot = FMath::Min(MinEdgeNormalDot, MeshAudit.MinNormalDot);
				UE_LOG(LogTemp, Display,
					TEXT("RED_FUSED_BOUNDARY_EDGE_PASS case=%d face_a=%d face_b=%d probes=%d pairs=%d max_position_delta_cm=%.6f min_normal_dot=%.9f"),
					EdgeCaseIndex, ExpectedFaces[0], ExpectedFaces[1], Hits.Num(),
					MeshAudit.MatchedPairs, MeshAudit.MaxPositionDeltaCm, MeshAudit.MinNormalDot);
				++EdgeCaseIndex;
				if (EdgeCaseIndex < EdgeCases.Num())
				{
					PrepareEdgeCase();
					return false;
				}
				Stage = EStage::Corners;
				PrepareCornerCase();
				return false;
			}

			++ValidatedCornerCount;
			TotalCornerProbeCount += Hits.Num();
			// Long lifted chord sweeps around a three-face corner can intersect valid raised
			// terrain. Player-sized closed traversal below is the corner wall acceptance.
			TotalCornerPawnSweepCount += FMath::Max(0, TraversalHits.Num() - 1);
			TotalCornerMatchedVertexPairs += MeshAudit.MatchedPairs;
			MaxCornerPositionDeltaCm = FMath::Max(
				MaxCornerPositionDeltaCm, MeshAudit.MaxPositionDeltaCm);
			MinCornerNormalDot = FMath::Min(MinCornerNormalDot, MeshAudit.MinNormalDot);
			UE_LOG(LogTemp, Display,
				TEXT("RED_FUSED_BOUNDARY_CORNER_PASS case=%d signs=(%.0f,%.0f,%.0f) probes=%d pairs=%d max_position_delta_cm=%.6f min_normal_dot=%.9f"),
				CornerCaseIndex,
				BoundaryDirection.X, BoundaryDirection.Y, BoundaryDirection.Z,
				Hits.Num(), MeshAudit.MatchedPairs,
				MeshAudit.MaxPositionDeltaCm, MeshAudit.MinNormalDot);
			++CornerCaseIndex;
			if (CornerCaseIndex < CornerDirections.Num())
			{
				PrepareCornerCase();
				return false;
			}

			bool bValid = true;
			bValid &= Test->TestEqual(TEXT("Every unique cube edge was verified"),
				ValidatedEdgeCount, 12);
			bValid &= Test->TestEqual(TEXT("Every cube corner was verified"),
				ValidatedCornerCount, 8);
			bValid &= Test->TestEqual(TEXT("All edge collision probes completed"),
				TotalEdgeProbeCount, 12 * BoundaryProbeCount);
			bValid &= Test->TestEqual(TEXT("All corner collision probes completed"),
				TotalCornerProbeCount, 8 * CornerProbeCount);
			bValid &= Test->TestEqual(TEXT("Every edge pawn route completed"),
				TotalEdgePawnSweepCount, 12 * (TraversalProbeCount - 1));
			bValid &= Test->TestEqual(TEXT("Every corner pawn route completed"),
				TotalCornerPawnSweepCount, 8 * (CornerTraversalProbeCount - 1));
			bValid &= Test->TestEqual(TEXT("Every cube edge received one production ship move"),
				TotalShipEdgeMoveCount, 12);
			bValid &= Test->TestEqual(TEXT("Every cube corner received a three-leg production ship loop"),
				TotalShipCornerMoveCount, 8 * 3);
			bValid &= Test->TestEqual(TEXT("All eight production ship corner loops closed"),
				ValidatedShipCornerLoopCount, 8);
			bValid &= Test->TestTrue(TEXT("Production ship boundary endpoints stay within two centimetres"),
				MaxShipEndpointErrorCm <= ShipEndpointToleranceCm);
			bValid &= Test->TestTrue(TEXT("Production ship boundary moves remain high speed"),
				MinShipObservedSpeedCmPerSecond >= ShipMinimumTestSpeedCmPerSecond);
			if (bValid && !Test->HasAnyErrors())
			{
				UE_LOG(LogTemp, Display,
					TEXT("RED_FUSED_ALL_BOUNDARIES_PASS edges=%d corners=%d edge_probes=%d corner_probes=%d edge_lifted_sweeps=%d corner_lifted_sweeps=%d edge_pawn_sweeps=%d corner_pawn_sweeps=%d edge_pairs=%d corner_pairs=%d max_edge_position_delta_cm=%.6f min_edge_normal_dot=%.9f max_corner_position_delta_cm=%.6f min_corner_normal_dot=%.9f ship_edge_moves=%d ship_corner_moves=%d ship_corner_loops=%d ship_max_endpoint_error_cm=%.6f ship_min_speed_cm_s=%.3f"),
					ValidatedEdgeCount, ValidatedCornerCount,
					TotalEdgeProbeCount, TotalCornerProbeCount,
					TotalEdgeLiftedSweepCount, TotalCornerLiftedSweepCount,
					TotalEdgePawnSweepCount, TotalCornerPawnSweepCount,
					TotalEdgeMatchedVertexPairs, TotalCornerMatchedVertexPairs,
					MaxEdgePositionDeltaCm, MinEdgeNormalDot,
					MaxCornerPositionDeltaCm, MinCornerNormalDot,
					TotalShipEdgeMoveCount, TotalShipCornerMoveCount,
					ValidatedShipCornerLoopCount, MaxShipEndpointErrorCm,
					MinShipObservedSpeedCmPerSecond);
			}
			return Finish();
		}

	private:
		enum class EStage : uint8
		{
			WaitForWorld,
			Edges,
			Corners,
			Finished
		};

		struct FBoundaryMeshAudit
		{
			int32 MatchedPairs = 0;
			TMap<int32, int32> RawSamplesPerFace;
			TMap<int32, int32> UniqueSamplesPerFace;
			float MaxPositionDeltaCm = 0.f;
			float MinNormalDot = 1.f;
		};

		// Even counts deliberately straddle mathematical ownership ties without firing a
		// zero-width ray exactly down them. Exact topology is audited from runtime vertices;
		// the capsule sweep physically crosses between the paired support points.
		static constexpr int32 BoundaryProbeCount = 12;
		static constexpr int32 TraversalProbeCount = 6;
		static constexpr int32 CornerProbeCount = 6;
		static constexpr int32 CornerTraversalProbeCount = 4;
		static constexpr double BoundaryCrossingArcCm = 20000.0;
		static constexpr double PawnCrossingArcCm = 500.0;
		static constexpr float ShipRouteClearanceCm = 100.0f;
		static constexpr float ShipRouteChordAllowanceCm = 5.0f;
		static constexpr float ShipRouteStepSeconds = 1.0f / 30.0f;
		static constexpr float ShipEndpointToleranceCm = 2.0f;
		static constexpr float ShipMinimumTestSpeedCmPerSecond = 20000.0f;
		static constexpr double AbsoluteTestTimeoutSeconds = 120.0;
		static constexpr double CaseNoProgressTimeoutSeconds = 30.0;

		bool InitializeWorld()
		{
			UWorld* FoundWorld = Private::FindFusedPIEWorld();
			if (!FoundWorld)
			{
				return WaitOrFail(TEXT("The fused-prototype PIE world was not ready."));
			}

			ACLMPlanet* FoundPlanet = nullptr;
			for (TActorIterator<ACLMPlanet> It(FoundWorld); It; ++It)
			{
				if (FoundPlanet)
				{
					return Fail(TEXT("Expected exactly one ACLMPlanet in the fused prototype."));
				}
				FoundPlanet = *It;
			}
			if (!IsValid(FoundPlanet))
			{
				return WaitOrFail(TEXT("The fused ACLMPlanet was not ready."));
			}

			World = FoundWorld;
			Planet = FoundPlanet;
			OriginalViewDistance = FoundPlanet->ViewDistance;
			OriginalTerrainCollisionViewDistance =
				FoundPlanet->TerrainCollisionViewDistance;
			bool bConfigValid = true;
			bConfigValid &= Test->TestTrue(TEXT("All-boundary test uses the 50 km radius"),
				FMath::IsNearlyEqual(
					static_cast<double>(FoundPlanet->PlanetRadius),
					RedPlanet::FPlanet50KmProfile::RadiusCm,
					1.0));
			bConfigValid &= Test->TestTrue(TEXT("All-boundary test uses the fused macro field"),
				FoundPlanet->bEnableMacroHeightfield
					&& IsValid(FoundPlanet->MacroHeightfieldAsset));
			bConfigValid &= Test->TestEqual(TEXT("All-boundary test retains all 27 stamps"),
				FoundPlanet->TerrainStamps.Num(), Private::ExpectedTerrainStampCount);
			if (!bConfigValid)
			{
				return Finish();
			}
			// The test fixture is only 216 low-resolution chunks. Cook it once in full so
			// all 12 complete edges and 8 corners can be compared without source-order or
			// asynchronous recook bias. Streaming transitions remain covered separately.
			FoundPlanet->ViewDistance = 100.0f;
			FoundPlanet->TerrainCollisionViewDistance = 100.0f;

			OriginalAdditionalStreamingSources = FoundPlanet->AdditionalStreamingSources;
			FoundPlanet->AdditionalStreamingSources.Reset();
			for (int32 SourceIndex = 0; SourceIndex < 3; ++SourceIndex)
			{
				FActorSpawnParameters SpawnParameters;
				SpawnParameters.ObjectFlags |= RF_Transient;
				SpawnParameters.Name = FName(*FString::Printf(
					TEXT("RED_FusedAllCubeBoundaryStreamingSource_%d"), SourceIndex));
				ATargetPoint* Source = FoundWorld->SpawnActor<ATargetPoint>(
					ATargetPoint::StaticClass(), FTransform::Identity, SpawnParameters);
				if (!IsValid(Source))
				{
					return Fail(TEXT("Failed to spawn an all-boundary streaming source."));
				}
				Source->SetActorEnableCollision(false);
				Source->SetActorHiddenInGame(true);
				BoundaryStreamingSources.Add(Source);
				FoundPlanet->AdditionalStreamingSources.Add(Source);
			}
			StreamingSource = BoundaryStreamingSources[0];
			for (TActorIterator<APawn> It(FoundWorld); It; ++It)
			{
				APawn* Pawn = *It;
				if (!IsValid(Pawn)
					|| (!Pawn->IsPlayerControlled() && Pawn->GetPlayerState() == nullptr))
				{
					continue;
				}
				Private::FStreamingPawnState& State =
					StreamingPawnStates.AddDefaulted_GetRef();
				State.Pawn = Pawn;
				State.OriginalLocation = Pawn->GetActorLocation();
				State.bOriginalCollisionEnabled = Pawn->GetActorEnableCollision();
				State.bOriginalHidden = Pawn->IsHidden();
				State.bOriginalTickEnabled = Pawn->IsActorTickEnabled();
				Pawn->SetActorEnableCollision(false);
				Pawn->SetActorHiddenInGame(true);
				Pawn->SetActorTickEnabled(false);
			}

			for (int32 FaceA = 0; FaceA < PlanetGenMacroCubeFaceCount; ++FaceA)
			{
				for (int32 FaceB = FaceA + 1; FaceB < PlanetGenMacroCubeFaceCount; ++FaceB)
				{
					if (FMath::Abs(FVector::DotProduct(
						Private::GetFaceNormal(FaceA), Private::GetFaceNormal(FaceB))) < 0.5f)
					{
						EdgeCases.Emplace(FaceA, FaceB);
					}
				}
			}
			for (const float X : { -1.f, 1.f })
			{
				for (const float Y : { -1.f, 1.f })
				{
					for (const float Z : { -1.f, 1.f })
					{
						CornerDirections.Add(FVector(X, Y, Z).GetSafeNormal());
					}
				}
			}
			if (!Test->TestEqual(TEXT("Cube topology owns twelve unique edges"), EdgeCases.Num(), 12)
				|| !Test->TestEqual(TEXT("Cube topology owns eight corners"), CornerDirections.Num(), 8))
			{
				return Finish();
			}
			if (!InitializePhysicalShipFixture())
			{
				return Finish();
			}

			Stage = EStage::Edges;
			PrepareEdgeCase();
			return false;
		}

		bool InitializePhysicalShipFixture()
		{
			UWorld* TestWorld = World.Get();
			ACLMPlanet* TestPlanet = Planet.Get();
			if (!TestWorld || !TestPlanet)
			{
				Test->AddError(TEXT("The production ship boundary fixture has no valid world or planet."));
				return false;
			}

			const FVector SpawnDirection = FVector(1.0f, 1.0f, 0.0f).GetSafeNormal();
			const FVector SpawnLocation = TestPlanet->GetActorLocation()
				+ SpawnDirection * (TestPlanet->PlanetRadius
					+ FMath::Max(TestPlanet->MaxMountainHeight, TestPlanet->MaxHeight)
					+ 10000.0f);
			FActorSpawnParameters SpawnParameters;
			SpawnParameters.ObjectFlags |= RF_Transient;
			SpawnParameters.SpawnCollisionHandlingOverride =
				ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
			SpawnParameters.Name = MakeUniqueObjectName(
				TestWorld, ARedShip::StaticClass(), TEXT("RED_AllBoundaryPhysicalShip"));
			ARedShip* Ship = TestWorld->SpawnActor<ARedShip>(
				ARedShip::StaticClass(),
				FTransform(FRotationMatrix::MakeFromZ(SpawnDirection).ToQuat(), SpawnLocation),
				SpawnParameters);
			USphereComponent* RootSphere = Ship
				? Cast<USphereComponent>(Ship->GetRootComponent())
				: nullptr;
			URedShipMovementComponent* Movement = Ship
				? Cast<URedShipMovementComponent>(Ship->GetMovementComponent())
				: nullptr;

			bool bValid = true;
			bValid &= Test->TestNotNull(
				TEXT("All-boundary physical traversal spawns the native production ship"), Ship);
			bValid &= Test->TestNotNull(
				TEXT("All-boundary physical traversal uses the production sphere root"), RootSphere);
			bValid &= Test->TestNotNull(
				TEXT("All-boundary physical traversal uses the production movement component"), Movement);
			if (!Ship || !RootSphere || !Movement)
			{
				if (Ship)
				{
					Ship->Destroy();
				}
				return false;
			}

			Ship->SetActorTickEnabled(false);
			Ship->SetActorHiddenInGame(true);
			Ship->SetActorEnableCollision(true);
			TArray<UActorComponent*> Components;
			Ship->GetComponents(Components);
			for (UActorComponent* Component : Components)
			{
				if (Component)
				{
					Component->SetComponentTickEnabled(false);
				}
			}
			RootSphere->SetCollisionEnabled(ECollisionEnabled::QueryAndPhysics);
			RootSphere->UpdateBounds();
			RootSphere->UpdateOverlaps();
			Movement->SetUpdatedComponent(RootSphere);
			Movement->PlanetCenter = TestPlanet->GetActorLocation();
			Movement->PlanetRadius = TestPlanet->PlanetRadius;
			Movement->Velocity = FVector::ZeroVector;

			bValid &= Test->TestTrue(
				TEXT("All-boundary production root radius remains 260 cm"),
				FMath::IsNearlyEqual(RootSphere->GetScaledSphereRadius(), 260.0f, 0.1f));
			bValid &= Test->TestEqual(
				TEXT("All-boundary production root uses QueryAndPhysics"),
				RootSphere->GetCollisionEnabled(), ECollisionEnabled::QueryAndPhysics);
			bValid &= Test->TestTrue(
				TEXT("All-boundary production root has a physics state"),
				RootSphere->IsPhysicsStateCreated());
			bValid &= Test->TestEqual(
				TEXT("All-boundary production root is Vehicle collision"),
				RootSphere->GetCollisionObjectType(), ECC_Vehicle);
			bValid &= Test->TestEqual(
				TEXT("All-boundary production root ignores generic WorldDynamic"),
				RootSphere->GetCollisionResponseToChannel(ECC_WorldDynamic), ECR_Ignore);
			bValid &= Test->TestEqual(
				TEXT("All-boundary production root preserves WorldStatic blocking"),
				RootSphere->GetCollisionResponseToChannel(ECC_WorldStatic), ECR_Block);
			if (bValid)
			{
				PhysicalShip = Ship;
				PhysicalShipRoot = RootSphere;
				PhysicalShipMovement = Movement;
			}
			else
			{
				RootSphere->SetCollisionEnabled(ECollisionEnabled::NoCollision);
				Ship->Destroy();
			}
			return bValid;
		}

		bool ValidatePhysicalShipTraversal(
			const TArray<Private::FProbeHit>& Hits,
			const bool bCorner)
		{
			ARedShip* Ship = PhysicalShip.Get();
			USphereComponent* RootSphere = PhysicalShipRoot.Get();
			URedShipMovementComponent* Movement = PhysicalShipMovement.Get();
			ACLMPlanet* TestPlanet = Planet.Get();
			UWorld* TestWorld = World.Get();
			const int32 ExpectedHitCount = bCorner
				? CornerTraversalProbeCount
				: TraversalProbeCount;
			if (!Ship || !RootSphere || !Movement || !TestPlanet || !TestWorld
				|| Hits.Num() != ExpectedHitCount)
			{
				Test->AddError(FString::Printf(
					TEXT("Production ship boundary fixture is invalid for %s traversal (%d/%d supports)."),
					bCorner ? TEXT("corner") : TEXT("edge"), Hits.Num(), ExpectedHitCount));
				return false;
			}

			TArray<int32, TInlineAllocator<4>> RouteIndices;
			if (bCorner)
			{
				RouteIndices.Add(0);
				RouteIndices.Add(1);
				RouteIndices.Add(2);
				RouteIndices.Add(3);
			}
			else
			{
				RouteIndices.Add(0);
				RouteIndices.Add(Hits.Num() - 1);
			}

			const FVector PlanetCenter = TestPlanet->GetActorLocation();
			const float RootRadius = RootSphere->GetScaledSphereRadius();
			double RouteRadius = static_cast<double>(TestPlanet->PlanetRadius)
				+ static_cast<double>(Movement->MinimumSurfaceClearance)
				+ ShipRouteClearanceCm;
			bool bValid = true;
			for (int32 RoutePointIndex = 0; RoutePointIndex < RouteIndices.Num(); ++RoutePointIndex)
			{
				const Private::FProbeHit& Support = Hits[RouteIndices[RoutePointIndex]];
				const FVector Direction = Support.Direction.GetSafeNormal();
				const FVector Normal = Support.Normal.GetSafeNormal();
				const float NormalRadialDot = FVector::DotProduct(Normal, Direction);
				bValid &= Test->TestTrue(
					TEXT("Production ship route support has an outward radial normal"),
					NormalRadialDot > 0.5f);
				if (NormalRadialDot <= 0.5f)
				{
					return false;
				}
				const double SurfaceRadius = FVector::DotProduct(
					Support.Position - PlanetCenter, Direction);
				const double RequiredRadius = SurfaceRadius
					+ static_cast<double>(RootRadius + ShipRouteClearanceCm)
						/ static_cast<double>(NormalRadialDot);
				RouteRadius = FMath::Max(RouteRadius, RequiredRadius);

				const FIntVector ChunkKey = Private::ResolveActorChunkKey(
					TestPlanet, Support.Chunk.Get());
				const int32 ExpectedFace = bCorner
					? ExpectedFaces[RoutePointIndex % ExpectedFaces.Num()]
					: ExpectedFaces[RoutePointIndex == 0 ? 0 : 1];
				bValid &= Test->TestEqual(
					TEXT("Production ship route support belongs to the expected cube face"),
					ChunkKey.X, ExpectedFace);
			}
			if (!bValid || !FMath::IsFinite(RouteRadius))
			{
				return false;
			}
			RouteRadius += ShipRouteChordAllowanceCm;

			TArray<FVector, TInlineAllocator<4>> RouteCenters;
			RouteCenters.Reserve(RouteIndices.Num());
			for (const int32 HitIndex : RouteIndices)
			{
				const Private::FProbeHit& Support = Hits[HitIndex];
				const FVector Center = PlanetCenter
					+ Support.Direction.GetSafeNormal() * RouteRadius;
				const float NormalClearance = FVector::DotProduct(
					Center - Support.Position, Support.Normal.GetSafeNormal());
				bValid &= Test->TestTrue(
					TEXT("Production ship route starts above its planned normal clearance"),
					NormalClearance >= RootRadius + ShipRouteClearanceCm - 0.5f);
				RouteCenters.Add(Center);
			}
			if (!bValid)
			{
				return false;
			}

			const FVector FirstDelta = RouteCenters[1] - RouteCenters[0];
			const FVector FirstForward = FVector::VectorPlaneProject(
				FirstDelta, Hits[RouteIndices[0]].Direction).GetSafeNormal();
			const FQuat FirstRotation = FRotationMatrix::MakeFromZX(
				Hits[RouteIndices[0]].Direction.GetSafeNormal(), FirstForward).ToQuat();
			Ship->SetActorLocationAndRotation(
				RouteCenters[0], FirstRotation, false, nullptr,
				ETeleportType::TeleportPhysics);
			RootSphere->UpdateBounds();
			RootSphere->UpdateOverlaps();
			Movement->Velocity = FVector::ZeroVector;

			for (int32 LegIndex = 0; LegIndex + 1 < RouteCenters.Num(); ++LegIndex)
			{
				const FVector ActualStart = RootSphere->GetComponentLocation();
				const FVector Target = RouteCenters[LegIndex + 1];
				const FVector Delta = Target - ActualStart;
				const float RequestedSpeed = Delta.Size() / ShipRouteStepSeconds;
				const FVector TargetUp = Hits[RouteIndices[LegIndex + 1]].Direction.GetSafeNormal();
				const FVector Forward = FVector::VectorPlaneProject(Delta, TargetUp).GetSafeNormal();
				const FQuat NewRotation = FRotationMatrix::MakeFromZX(TargetUp, Forward).ToQuat();
				bValid &= Test->TestTrue(
					TEXT("Production ship boundary move remains finite and nonzero"),
					!ActualStart.ContainsNaN() && !Target.ContainsNaN()
						&& !Delta.IsNearlyZero() && FMath::IsFinite(RequestedSpeed));
				bValid &= Test->TestTrue(
					TEXT("Production ship boundary move is at least 200 m/s"),
					RequestedSpeed >= ShipMinimumTestSpeedCmPerSecond);
				bValid &= Test->TestTrue(
					TEXT("Production ship boundary move stays within its absolute speed cap"),
					RequestedSpeed <= Movement->AbsoluteMaxSpeed + 1.0f);
				if (!bValid)
				{
					return false;
				}

				FHitResult PreflightHit(1.0f);
				const ERedPlanetTerrainQueryResult PreflightResult =
					RedPlanetTerrainQuery::Sweep(
						TestWorld,
						PlanetCenter,
						ActualStart,
						Target,
						NewRotation,
						FCollisionShape::MakeSphere(RootRadius),
						PreflightHit);
				if (!Test->TestTrue(
					TEXT("Exact PlanetGen preflight finds a clear production ship boundary route"),
					PreflightResult == ERedPlanetTerrainQueryResult::NoHit
						&& !PreflightHit.bBlockingHit
						&& !PreflightHit.bStartPenetrating))
				{
					return false;
				}

				const FVector RequestedVelocity = Delta / ShipRouteStepSeconds;
				Movement->Velocity = RequestedVelocity;
				Movement->MoveWithPlanetCollision(Delta, NewRotation, ShipRouteStepSeconds);
				const FVector FinalLocation = RootSphere->GetComponentLocation();
				const float EndpointError = FVector::Distance(FinalLocation, Target);
				const float ActualDistance = FVector::Distance(ActualStart, FinalLocation);
				const float VelocityError = FVector::Distance(
					Movement->Velocity, RequestedVelocity);
				const Private::FProbeHit& DestinationSupport =
					Hits[RouteIndices[LegIndex + 1]];
				const float FinalNormalClearance = FVector::DotProduct(
					FinalLocation - DestinationSupport.Position,
					DestinationSupport.Normal.GetSafeNormal());
				MaxShipEndpointErrorCm = FMath::Max(MaxShipEndpointErrorCm, EndpointError);
				MinShipObservedSpeedCmPerSecond = FMath::Min(
					MinShipObservedSpeedCmPerSecond, RequestedSpeed);
				if (bCorner)
				{
					++TotalShipCornerMoveCount;
				}
				else
				{
					++TotalShipEdgeMoveCount;
				}

				bValid &= Test->TestTrue(
					TEXT("Production ship completes the requested boundary endpoint"),
					EndpointError <= ShipEndpointToleranceCm);
				bValid &= Test->TestTrue(
					TEXT("Production ship boundary displacement has no stop, slide loss, or overshoot"),
					FMath::Abs(ActualDistance - Delta.Size()) <= ShipEndpointToleranceCm);
				bValid &= Test->TestTrue(
					TEXT("Production ship boundary velocity bookkeeping matches the physical move"),
					VelocityError <= 100.0f);
				bValid &= Test->TestTrue(
					TEXT("Production ship retains root clearance after the boundary move"),
					FinalNormalClearance >= RootRadius + 50.0f);
				bValid &= Test->TestTrue(
					TEXT("Production ship root collision remains live after the boundary move"),
					RootSphere->GetCollisionEnabled() == ECollisionEnabled::QueryAndPhysics
						&& RootSphere->IsPhysicsStateCreated());
				if (!bValid)
				{
					UE_LOG(LogTemp, Error,
						TEXT("RED_SHIP_ALL_BOUNDARY_MOVE_FAIL stage=%d edge=%d corner=%d leg=%d speed_cm_s=%.3f endpoint_error_cm=%.6f velocity_error_cm_s=%.3f final_clearance_cm=%.3f"),
						static_cast<int32>(Stage), EdgeCaseIndex, CornerCaseIndex,
						LegIndex, RequestedSpeed, EndpointError, VelocityError,
						FinalNormalClearance);
					return false;
				}
			}

			if (bCorner)
			{
				const float ClosureError = FVector::Distance(
					RootSphere->GetComponentLocation(), RouteCenters[0]);
				bValid &= Test->TestTrue(
					TEXT("Production ship corner route closes its three-face loop"),
					ClosureError <= ShipEndpointToleranceCm);
				if (bValid)
				{
					++ValidatedShipCornerLoopCount;
				}
			}
			return bValid;
		}

		void PrepareEdgeCase()
		{
			ExpectedFaces.Reset();
			ExpectedFaces.Add(EdgeCases[EdgeCaseIndex].X);
			ExpectedFaces.Add(EdgeCases[EdgeCaseIndex].Y);
			const FVector FaceA = Private::GetFaceNormal(ExpectedFaces[0]);
			const FVector FaceB = Private::GetFaceNormal(ExpectedFaces[1]);
			BoundaryDirection = (FaceA + FaceB).GetSafeNormal();
			const FVector EdgeAxis = FVector::CrossProduct(FaceA, FaceB).GetSafeNormal();
			Probes.Reset();
			for (int32 Index = 0; Index < BoundaryProbeCount; ++Index)
			{
				const double Alpha = static_cast<double>(Index)
					/ static_cast<double>(BoundaryProbeCount - 1);
				Private::FProbe& Probe = Probes.AddDefaulted_GetRef();
				Probe.Direction = Private::RotateAlongGreatCircle(
					BoundaryDirection,
					EdgeAxis,
					FMath::Lerp(-BoundaryCrossingArcCm, BoundaryCrossingArcCm, Alpha),
					Planet->PlanetRadius);
				Probe.Label = FString::Printf(
					TEXT("edge_%02d_faces_%d_%d_probe_%02d"),
					EdgeCaseIndex, ExpectedFaces[0], ExpectedFaces[1], Index);
				AssignExpectedChunkKey(Probe);
			}
			TraversalProbes.Reset();
			for (int32 Index = 0; Index < TraversalProbeCount; ++Index)
			{
				const double Alpha = static_cast<double>(Index)
					/ static_cast<double>(TraversalProbeCount - 1);
				Private::FProbe& Probe = TraversalProbes.AddDefaulted_GetRef();
				Probe.Direction = Private::RotateAlongGreatCircle(
					BoundaryDirection,
					EdgeAxis,
					FMath::Lerp(-PawnCrossingArcCm, PawnCrossingArcCm, Alpha),
					Planet->PlanetRadius);
				Probe.Label = FString::Printf(
					TEXT("edge_%02d_pawn_probe_%02d"), EdgeCaseIndex, Index);
				AssignExpectedChunkKey(Probe);
			}
			MoveStreamingSource();
			CaseStartedAtSeconds = FPlatformTime::Seconds();
		}

		void PrepareCornerCase()
		{
			BoundaryDirection = CornerDirections[CornerCaseIndex];
			ExpectedFaces.Reset();
			ExpectedFaces.Add(BoundaryDirection.X > 0.f ? 0 : 1);
			ExpectedFaces.Add(BoundaryDirection.Y > 0.f ? 2 : 3);
			ExpectedFaces.Add(BoundaryDirection.Z > 0.f ? 4 : 5);
			Probes.Reset();
			for (int32 FaceIndex = 0; FaceIndex < ExpectedFaces.Num(); ++FaceIndex)
			{
				const FVector FaceNormal =
					Private::GetFaceNormal(ExpectedFaces[FaceIndex]);
				const FVector FaceTangent = FVector::VectorPlaneProject(
					FaceNormal, BoundaryDirection).GetSafeNormal();
				const FVector RotationAxis = FVector::CrossProduct(
					BoundaryDirection, FaceTangent).GetSafeNormal();
				for (int32 DistanceIndex = 1; DistanceIndex <= 2; ++DistanceIndex)
				{
					Private::FProbe& Probe = Probes.AddDefaulted_GetRef();
					Probe.Direction = Private::RotateAlongGreatCircle(
						BoundaryDirection,
						RotationAxis,
						BoundaryCrossingArcCm * 0.5 * DistanceIndex,
						Planet->PlanetRadius);
					Probe.Label = FString::Printf(
						TEXT("corner_%02d_face_%d_probe_%02d"),
						CornerCaseIndex, ExpectedFaces[FaceIndex], DistanceIndex - 1);
					AssignExpectedChunkKey(Probe);
				}
			}
			TraversalProbes.Reset();
			for (int32 Index = 0; Index < CornerTraversalProbeCount; ++Index)
			{
				const int32 FaceIndex = Index % ExpectedFaces.Num();
				const FVector FaceNormal =
					Private::GetFaceNormal(ExpectedFaces[FaceIndex]);
				const FVector FaceTangent = FVector::VectorPlaneProject(
					FaceNormal, BoundaryDirection).GetSafeNormal();
				const FVector RotationAxis = FVector::CrossProduct(
					BoundaryDirection, FaceTangent).GetSafeNormal();
				Private::FProbe& Probe = TraversalProbes.AddDefaulted_GetRef();
				Probe.Direction = Private::RotateAlongGreatCircle(
					BoundaryDirection,
					RotationAxis,
					PawnCrossingArcCm,
					Planet->PlanetRadius);
				Probe.Label = FString::Printf(
					TEXT("corner_%02d_pawn_probe_%02d"), CornerCaseIndex, Index);
				AssignExpectedChunkKey(Probe);
			}
			MoveStreamingSource();
			CaseStartedAtSeconds = FPlatformTime::Seconds();
		}

		void AssignExpectedChunkKey(Private::FProbe& Probe) const
		{
			const FVector AbsDirection = Probe.Direction.GetSafeNormal().GetAbs();
			TArray<double, TInlineAllocator<3>> Axes = {
				AbsDirection.X, AbsDirection.Y, AbsDirection.Z };
			Axes.Sort(TGreater<double>());
			if (Axes.Num() >= 2 && FMath::IsNearlyEqual(Axes[0], Axes[1], 1.0e-6f))
			{
				// Exact edge/corner ties have multiple legitimate triangle owners. Interior
				// probes on both sides still prove each intended component is Chaos-ready.
				Probe.ExpectedChunkKey = FIntVector(INDEX_NONE, INDEX_NONE, INDEX_NONE);
				return;
			}
			Probe.ExpectedChunkKey = Private::ResolveDirectionChunkKey(
				Planet.Get(), Probe.Direction);
		}

		void MoveStreamingSource()
		{
			TArray<FVector, TInlineAllocator<3>> SourceDirections;
			SourceDirections.Add(BoundaryDirection);
			if (Stage == EStage::Edges && ExpectedFaces.Num() == 2)
			{
				const FVector EdgeAxis = FVector::CrossProduct(
					Private::GetFaceNormal(ExpectedFaces[0]),
					Private::GetFaceNormal(ExpectedFaces[1])).GetSafeNormal();
				SourceDirections.Add((BoundaryDirection * FMath::Sqrt(2.0)
					+ EdgeAxis).GetSafeNormal());
				SourceDirections.Add((BoundaryDirection * FMath::Sqrt(2.0)
					- EdgeAxis).GetSafeNormal());
			}
			else
			{
				SourceDirections.Add(BoundaryDirection);
				SourceDirections.Add(BoundaryDirection);
			}
			const double SourceRadius = Planet->PlanetRadius + Planet->MaxHeight
				+ Private::StreamingSourceClearanceCm;
			for (int32 Index = 0; Index < BoundaryStreamingSources.Num(); ++Index)
			{
				if (BoundaryStreamingSources[Index].IsValid())
				{
					BoundaryStreamingSources[Index]->SetActorLocation(
						Planet->GetActorLocation() + SourceDirections[Index] * SourceRadius,
						false, nullptr, ETeleportType::TeleportPhysics);
				}
			}
			const FVector SourceLocation =
				Planet->GetActorLocation() + BoundaryDirection * SourceRadius;
			for (const Private::FStreamingPawnState& State : StreamingPawnStates)
			{
				if (State.Pawn.IsValid())
				{
					State.Pawn->SetActorLocation(
						SourceLocation, false, nullptr, ETeleportType::TeleportPhysics);
				}
			}
		}

		bool ValidateProbeOwnership(
			const TArray<Private::FProbeHit>& Hits,
			const TArray<Private::FProbe>& ProbeSpecs,
			const TCHAR* Context)
		{
			if (Hits.Num() != ProbeSpecs.Num())
			{
				Test->AddError(FString::Printf(
					TEXT("%s probe/spec count mismatch: %d versus %d."),
					Context, Hits.Num(), ProbeSpecs.Num()));
				return false;
			}
			int32 ExactComponentHits = 0;
			int32 ExactKeyHits = 0;
			int32 KeyedProbeCount = 0;
			for (int32 Index = 0; Index < Hits.Num(); ++Index)
			{
				const Private::FProbeHit& Hit = Hits[Index];
				UProceduralMeshComponent* ExpectedMesh = Hit.Chunk.IsValid()
					? Hit.Chunk->FindComponentByClass<UProceduralMeshComponent>()
					: nullptr;
				if (ExpectedMesh && Hit.Component.Get() == ExpectedMesh
					&& ExpectedMesh->GetCollisionEnabled() == ECollisionEnabled::QueryAndPhysics
					&& ExpectedMesh->GetCollisionObjectType() == ECC_WorldDynamic
					&& ExpectedMesh->GetCollisionResponseToChannel(ECC_Pawn) == ECR_Block)
				{
					++ExactComponentHits;
				}
				if (ProbeSpecs[Index].ExpectedChunkKey.X != INDEX_NONE)
				{
					++KeyedProbeCount;
					if (Private::ResolveActorChunkKey(Planet.Get(), Hit.Chunk.Get())
						== ProbeSpecs[Index].ExpectedChunkKey)
					{
						++ExactKeyHits;
					}
				}
			}
			bool bValid = true;
			bValid &= Test->TestEqual(
				FString::Printf(TEXT("%s hits exact cooked procedural components"), Context),
				ExactComponentHits, Hits.Num());
			bValid &= Test->TestEqual(
				FString::Printf(TEXT("%s interior probes hit their exact chunk keys"), Context),
				ExactKeyHits, KeyedProbeCount);
			return bValid;
		}

		bool ValidateProbeSet(
			const TArray<Private::FProbeHit>& Hits,
			const TArray<Private::FProbe>& ProbeSpecs,
			const bool bCheckLiftedRoute)
		{
			float MinimumOutwardNormalDot = 1.f;
			int32 LiftedBlockerCount = 0;
			TSet<int32> ObservedFaces;
			for (const Private::FProbeHit& Hit : Hits)
			{
				MinimumOutwardNormalDot = FMath::Min(
					MinimumOutwardNormalDot,
					FVector::DotProduct(Hit.Normal, Hit.Direction));
				if (Hit.Chunk.IsValid())
				{
					ObservedFaces.Add(Private::ResolveDominantCubeFace(
						Hit.Chunk->GetActorLocation() - Planet->GetActorLocation()));
				}
			}
			if (bCheckLiftedRoute)
			{
				for (int32 Index = 0; Index + 1 < Hits.Num(); ++Index)
				{
					LiftedBlockerCount += Private::HasLiftedTerrainBlocker(
						World.Get(), Planet.Get(), Hits[Index], Hits[Index + 1]) ? 1 : 0;
				}
			}

			bool bExpectedFacesObserved = true;
			for (const int32 Face : ExpectedFaces)
			{
				bExpectedFacesObserved &= ObservedFaces.Contains(Face);
			}
			bool bValid = true;
			bValid &= ValidateProbeOwnership(Hits, ProbeSpecs, TEXT("Boundary"));
			bValid &= Test->TestTrue(TEXT("Boundary collision normals face outward"),
				MinimumOutwardNormalDot > 0.5f);
			if (bCheckLiftedRoute)
			{
				bValid &= Test->TestEqual(TEXT("Boundary route has no lifted PlanetGen blocker"),
					LiftedBlockerCount, 0);
			}
			bValid &= Test->TestTrue(TEXT("Boundary probes hit every expected cube face"),
				bExpectedFacesObserved);
			return bValid;
		}

		bool ValidateTraversalSet(
			const TArray<Private::FProbeHit>& Hits,
			const TArray<Private::FProbe>& ProbeSpecs)
		{
			int32 PawnBlockerCount = 0;
			float MinimumOutwardNormalDot = 1.f;
			for (const Private::FProbeHit& Hit : Hits)
			{
				MinimumOutwardNormalDot = FMath::Min(
					MinimumOutwardNormalDot,
					FVector::DotProduct(Hit.Normal, Hit.Direction));
			}
			for (int32 Index = 0; Index + 1 < Hits.Num(); ++Index)
			{
				FHitResult BlockingHit;
				if (Private::HasPawnTraversalBlocker(
					World.Get(), Hits[Index], Hits[Index + 1], &BlockingHit))
				{
					++PawnBlockerCount;
					UE_LOG(LogTemp, Error,
						TEXT("RED_FUSED_PAWN_BOUNDARY_BLOCKER stage=%d edge=%d corner=%d segment=%d actor=%s component=%s start_penetrating=%d penetration_depth_cm=%.6f time=%.6f impact_normal=(%.6f,%.6f,%.6f)"),
						static_cast<int32>(Stage), EdgeCaseIndex, CornerCaseIndex, Index,
						BlockingHit.GetActor() ? *BlockingHit.GetActor()->GetName() : TEXT("none"),
						BlockingHit.GetComponent() ? *BlockingHit.GetComponent()->GetName() : TEXT("none"),
						BlockingHit.bStartPenetrating ? 1 : 0,
						BlockingHit.PenetrationDepth,
						BlockingHit.Time,
						BlockingHit.ImpactNormal.X,
						BlockingHit.ImpactNormal.Y,
						BlockingHit.ImpactNormal.Z);
				}
			}
			bool bValid = ValidateProbeOwnership(Hits, ProbeSpecs, TEXT("Pawn route"));
			bValid &= Test->TestTrue(TEXT("Pawn-route support normals face outward"),
				MinimumOutwardNormalDot > 0.5f);
			bValid &= Test->TestEqual(
				TEXT("Pawn capsule crosses the boundary without a blocking wall"),
				PawnBlockerCount, 0);
			return bValid;
		}

		bool TryAuditBoundaryMesh(const bool bCorner, FBoundaryMeshAudit& OutAudit) const
		{
			TMap<int32, TArray<Private::FSeamVertex>> RawVerticesByFace;
			Private::CollectExactBoundaryVertices(
				Planet.Get(), ExpectedFaces, BoundaryDirection, bCorner, RawVerticesByFace);
			TMap<int32, TArray<Private::FSeamVertex>> UniqueVerticesByFace;
			const int32 ExpectedUniqueSamples = bCorner
				? 1
				: Private::GetChunksPerFace(Planet.Get())
					* FMath::Max(1, Planet->Resolution - 1) + 1;
			const FVector SortAxis = bCorner
				? FVector::ZeroVector
				: FVector::CrossProduct(
					Private::GetFaceNormal(ExpectedFaces[0]),
					Private::GetFaceNormal(ExpectedFaces[1])).GetSafeNormal();
			for (const int32 Face : ExpectedFaces)
			{
				TArray<Private::FSeamVertex>* RawVertices = RawVerticesByFace.Find(Face);
				OutAudit.RawSamplesPerFace.Add(Face, RawVertices ? RawVertices->Num() : 0);
				if (!RawVertices || RawVertices->IsEmpty())
				{
					return false;
				}
				RawVertices->Sort([&SortAxis](
					const Private::FSeamVertex& A,
					const Private::FSeamVertex& B)
				{
					return FVector::DotProduct(A.Direction, SortAxis)
						< FVector::DotProduct(B.Direction, SortAxis);
				});
				TArray<Private::FSeamVertex>& UniqueVertices =
					UniqueVerticesByFace.FindOrAdd(Face);
				for (const Private::FSeamVertex& Vertex : *RawVertices)
				{
					if (!UniqueVertices.IsEmpty()
						&& FVector::DotProduct(
							UniqueVertices.Last().Direction,
							Vertex.Direction) >= Private::DirectionMatchDotTolerance)
					{
						// Adjacent chunks duplicate their endpoint sample. Audit those copies too,
						// then retain one canonical sample for reciprocal cross-face matching.
						OutAudit.MaxPositionDeltaCm = FMath::Max(
							OutAudit.MaxPositionDeltaCm,
							FVector::Distance(UniqueVertices.Last().Position, Vertex.Position));
						OutAudit.MinNormalDot = FMath::Min(
							OutAudit.MinNormalDot,
							FVector::DotProduct(UniqueVertices.Last().Normal, Vertex.Normal));
						continue;
					}
					UniqueVertices.Add(Vertex);
				}
				OutAudit.UniqueSamplesPerFace.Add(Face, UniqueVertices.Num());
				if (UniqueVertices.Num() != ExpectedUniqueSamples)
				{
					return false;
				}
			}

			for (int32 FaceAIndex = 0; FaceAIndex < ExpectedFaces.Num(); ++FaceAIndex)
			{
				for (int32 FaceBIndex = FaceAIndex + 1;
					FaceBIndex < ExpectedFaces.Num(); ++FaceBIndex)
				{
					const TArray<Private::FSeamVertex>& FaceAVertices =
						UniqueVerticesByFace.FindChecked(ExpectedFaces[FaceAIndex]);
					const TArray<Private::FSeamVertex>& FaceBVertices =
						UniqueVerticesByFace.FindChecked(ExpectedFaces[FaceBIndex]);
					if (FaceAVertices.Num() != FaceBVertices.Num())
					{
						return false;
					}
					for (int32 SampleIndex = 0;
						SampleIndex < FaceAVertices.Num(); ++SampleIndex)
					{
						const Private::FSeamVertex& A = FaceAVertices[SampleIndex];
						const Private::FSeamVertex& B = FaceBVertices[SampleIndex];
						if (FVector::DotProduct(A.Direction, B.Direction)
							< Private::DirectionMatchDotTolerance)
						{
							return false;
						}
						++OutAudit.MatchedPairs;
						OutAudit.MaxPositionDeltaCm = FMath::Max(
							OutAudit.MaxPositionDeltaCm,
							FVector::Distance(A.Position, B.Position));
						OutAudit.MinNormalDot = FMath::Min(
							OutAudit.MinNormalDot,
							FVector::DotProduct(A.Normal, B.Normal));
					}
				}
			}
			return true;
		}

		bool ValidateBoundaryMesh(const FBoundaryMeshAudit& Audit, const bool bCorner)
		{
			const int32 ExpectedUniqueSamples = bCorner
				? 1
				: Private::GetChunksPerFace(Planet.Get())
					* FMath::Max(1, Planet->Resolution - 1) + 1;
			const int32 ExpectedPairCount = bCorner
				? 3
				: ExpectedUniqueSamples;
			bool bValid = true;
			for (const int32 Face : ExpectedFaces)
			{
				const int32* UniqueCount = Audit.UniqueSamplesPerFace.Find(Face);
				bValid &= Test->TestEqual(
					TEXT("Each owning face supplies the complete canonical boundary"),
					UniqueCount ? *UniqueCount : 0,
					ExpectedUniqueSamples);
			}
			bValid &= Test->TestEqual(
				bCorner
					? TEXT("All three corner faces share an exact runtime vertex")
					: TEXT("Both edge faces share every canonical runtime vertex"),
				Audit.MatchedPairs,
				ExpectedPairCount);
			bValid &= Test->TestTrue(TEXT("Boundary runtime positions stay within one centimetre"),
				Audit.MaxPositionDeltaCm <= Private::SharedSeamPositionToleranceCm);
			bValid &= Test->TestTrue(TEXT("Boundary runtime normals remain continuous"),
				Audit.MinNormalDot >= Private::SharedSeamNormalDotTolerance);
			return bValid;
		}

		bool WaitOrFail(const FString& Detail)
		{
			const double Now = FPlatformTime::Seconds();
			if (Now - TestStartedAtSeconds <= AbsoluteTestTimeoutSeconds
				&& Now - CaseStartedAtSeconds <= CaseNoProgressTimeoutSeconds)
			{
				return false;
			}
			return Fail(FString::Printf(
				TEXT("All-boundary test timed out in stage %d, edge %d, corner %d: %s"),
				static_cast<int32>(Stage), EdgeCaseIndex, CornerCaseIndex, *Detail));
		}

		bool Fail(const FString& Message)
		{
			Test->AddError(Message);
			UE_LOG(LogTemp, Error, TEXT("RED_FUSED_ALL_BOUNDARIES_FAIL error=%s"), *Message);
			return Finish();
		}

		bool Finish()
		{
			if (PhysicalShipRoot.IsValid())
			{
				PhysicalShipRoot->SetCollisionEnabled(ECollisionEnabled::NoCollision);
			}
			if (PhysicalShip.IsValid())
			{
				PhysicalShip->Destroy();
			}
			PhysicalShip.Reset();
			PhysicalShipRoot.Reset();
			PhysicalShipMovement.Reset();
			if (Planet.IsValid())
			{
				Planet->ViewDistance = OriginalViewDistance;
				Planet->TerrainCollisionViewDistance =
					OriginalTerrainCollisionViewDistance;
				Planet->AdditionalStreamingSources = OriginalAdditionalStreamingSources;
			}
			for (const Private::FStreamingPawnState& State : StreamingPawnStates)
			{
				if (!State.Pawn.IsValid())
				{
					continue;
				}
				State.Pawn->SetActorLocation(
					State.OriginalLocation, false, nullptr, ETeleportType::TeleportPhysics);
				State.Pawn->SetActorEnableCollision(State.bOriginalCollisionEnabled);
				State.Pawn->SetActorHiddenInGame(State.bOriginalHidden);
				State.Pawn->SetActorTickEnabled(State.bOriginalTickEnabled);
			}
			for (const TWeakObjectPtr<ATargetPoint>& Source : BoundaryStreamingSources)
			{
				if (Source.IsValid())
				{
					Source->Destroy();
				}
			}
			Stage = EStage::Finished;
			return true;
		}

		FAutomationTestBase* Test = nullptr;
		TWeakObjectPtr<UWorld> World;
		TWeakObjectPtr<ACLMPlanet> Planet;
		TWeakObjectPtr<ARedShip> PhysicalShip;
		TWeakObjectPtr<USphereComponent> PhysicalShipRoot;
		TWeakObjectPtr<URedShipMovementComponent> PhysicalShipMovement;
		TWeakObjectPtr<ATargetPoint> StreamingSource;
		TArray<TWeakObjectPtr<ATargetPoint>> BoundaryStreamingSources;
		TArray<TObjectPtr<AActor>> OriginalAdditionalStreamingSources;
		TArray<Private::FStreamingPawnState> StreamingPawnStates;
		EStage Stage = EStage::WaitForWorld;
		double TestStartedAtSeconds = 0.0;
		double CaseStartedAtSeconds = 0.0;
		TArray<FIntPoint> EdgeCases;
		TArray<FVector> CornerDirections;
		TArray<int32> ExpectedFaces;
		TArray<Private::FProbe> Probes;
		TArray<Private::FProbe> TraversalProbes;
		FVector BoundaryDirection = FVector::ZeroVector;
		int32 EdgeCaseIndex = 0;
		int32 CornerCaseIndex = 0;
		int32 ValidatedEdgeCount = 0;
		int32 ValidatedCornerCount = 0;
		int32 TotalEdgeProbeCount = 0;
		int32 TotalCornerProbeCount = 0;
		int32 TotalEdgeLiftedSweepCount = 0;
		int32 TotalCornerLiftedSweepCount = 0;
		int32 TotalEdgePawnSweepCount = 0;
		int32 TotalCornerPawnSweepCount = 0;
		int32 TotalShipEdgeMoveCount = 0;
		int32 TotalShipCornerMoveCount = 0;
		int32 ValidatedShipCornerLoopCount = 0;
		int32 TotalEdgeMatchedVertexPairs = 0;
		int32 TotalCornerMatchedVertexPairs = 0;
		float MaxEdgePositionDeltaCm = 0.f;
		float MaxCornerPositionDeltaCm = 0.f;
		float MinEdgeNormalDot = 1.f;
		float MinCornerNormalDot = 1.f;
		float MaxShipEndpointErrorCm = 0.f;
		float MinShipObservedSpeedCmPerSecond = TNumericLimits<float>::Max();
		float OriginalViewDistance = 0.f;
		float OriginalTerrainCollisionViewDistance = 0.f;
	};

	class FRedFusedActiveTerrainQueryCommand final : public IAutomationLatentCommand
	{
	public:
		explicit FRedFusedActiveTerrainQueryCommand(FAutomationTestBase* InTest)
			: Test(InTest)
			, StartedAtSeconds(FPlatformTime::Seconds())
		{
		}

		virtual bool Update() override
		{
			if (!Test)
			{
				return Finish();
			}

			switch (Stage)
			{
			case EStage::WaitForWorld:
				return UpdateWaitForWorld();
			case EStage::WaitForCookedTerrain:
				return UpdateWaitForCookedTerrain();
			case EStage::WaitForPassiveZeroInput:
				return UpdateWaitForPassiveZeroInput();
			default:
				return true;
			}
		}

	private:
		enum class EStage : uint8
		{
			WaitForWorld,
			WaitForCookedTerrain,
			WaitForPassiveZeroInput,
			Finished
		};

		bool UpdateWaitForWorld()
		{
			UWorld* FoundWorld = Private::FindFusedPIEWorld();
			if (!FoundWorld)
			{
				return WaitOrFail(TEXT("the fused-prototype PIE world"));
			}

			ACLMPlanet* FoundPlanet = nullptr;
			for (TActorIterator<ACLMPlanet> It(FoundWorld); It; ++It)
			{
				if (FoundPlanet)
				{
					return Fail(TEXT("Expected exactly one ACLMPlanet in the fused prototype."));
				}
				FoundPlanet = *It;
			}
			if (!IsValid(FoundPlanet))
			{
				return WaitOrFail(TEXT("ACLMPlanet in the fused prototype"));
			}

			World = FoundWorld;
			Planet = FoundPlanet;
			OriginalAdditionalStreamingSources = FoundPlanet->AdditionalStreamingSources;
			SeamDirection = FVector(1.0f, 1.0f, 0.0f).GetSafeNormal();
			const FVector Center = FoundPlanet->GetActorLocation();
			const float TerrainEnvelopeCm = FMath::Max(
				FoundPlanet->MaxMountainHeight, FoundPlanet->MaxHeight);
			const float OuterRadiusCm = FoundPlanet->PlanetRadius
				+ TerrainEnvelopeCm + Private::RadialTraceMarginCm;
			PositiveStart = Center + SeamDirection * OuterRadiusCm;
			NegativeStart = Center - SeamDirection * OuterRadiusCm;

			const float StreamingRadiusCm = FoundPlanet->PlanetRadius
				+ TerrainEnvelopeCm + Private::StreamingSourceClearanceCm;
			if (!SpawnStreamingSource(
				TEXT("RED_ActiveTerrainQueryPositiveSource"),
				Center + SeamDirection * StreamingRadiusCm)
				|| !SpawnStreamingSource(
					TEXT("RED_ActiveTerrainQueryNegativeSource"),
					Center - SeamDirection * StreamingRadiusCm))
			{
				return Fail(TEXT("Failed to spawn the active-terrain query streaming sources."));
			}

			Stage = EStage::WaitForCookedTerrain;
			return false;
		}

		bool UpdateWaitForCookedTerrain()
		{
			if (!World.IsValid() || !Planet.IsValid())
			{
				return Fail(TEXT("The fused PIE world or planet became invalid."));
			}

			const FVector Center = Planet->GetActorLocation();
			FHitResult PositiveReadyHit;
			FHitResult NegativeReadyHit;
			FIntVector PositiveReadyKey;
			FIntVector NegativeReadyKey;
			const bool bPositiveReady = Planet->LineTraceActiveTerrain(
				PositiveReadyHit, PositiveStart, Center, &PositiveReadyKey);
			const bool bNegativeReady = Planet->LineTraceActiveTerrain(
				NegativeReadyHit, NegativeStart, Center, &NegativeReadyKey);
			if (!bPositiveReady || !bNegativeReady)
			{
				return WaitOrFail(TEXT("cooked terrain collision at both antipodal seam probes"));
			}

			if (!SpawnWorldDynamicBlocker())
			{
				return Fail(TEXT("Failed to spawn the transient WorldDynamic query blocker."));
			}

			const bool bPassed = RunAssertions();
			if (!bPassed)
			{
				UE_LOG(LogTemp, Display,
					TEXT("RED_FUSED_ACTIVE_TERRAIN_QUERY status=fail"));
				return Finish();
			}
			if (!PassiveShip.IsValid()
				|| !PassiveMovement.IsValid()
				|| !PassiveRootSphere.IsValid())
			{
				return Fail(TEXT("The passive zero-input ship fixture was not prepared."));
			}

			PassiveStageStartedAtSeconds = FPlatformTime::Seconds();
			PassiveLastObservedWorldSeconds = World->GetTimeSeconds();
			Stage = EStage::WaitForPassiveZeroInput;
			return false;
		}

		bool UpdateWaitForPassiveZeroInput()
		{
			UWorld* TestWorld = World.Get();
			ACLMPlanet* TestPlanet = Planet.Get();
			ARedShip* Ship = PassiveShip.Get();
			URedShipMovementComponent* Movement = PassiveMovement.Get();
			USphereComponent* RootSphere = PassiveRootSphere.Get();
			if (!TestWorld || !TestPlanet || !Ship || !Movement || !RootSphere)
			{
				return Fail(TEXT("The passive zero-input ship fixture became invalid."));
			}

			const double WorldSeconds = TestWorld->GetTimeSeconds();
			if (WorldSeconds <= PassiveLastObservedWorldSeconds + UE_SMALL_NUMBER)
			{
				return WaitForPassiveOrFail();
			}
			PassiveLastObservedWorldSeconds = WorldSeconds;
			++PassiveObservedWorldTicks;

			const FVector Location = RootSphere->GetComponentLocation();
			FHitResult ProbeHit(1.0f);
			const ERedPlanetTerrainQueryResult ProbeResult = RedPlanetTerrainQuery::Sweep(
				TestWorld,
				TestPlanet->GetActorLocation(),
				Location,
				Location,
				PassiveRotation,
				PassiveRootShape,
				ProbeHit);

			if (PassiveObservedWorldTicks == 1)
			{
				PassiveFirstResolvedWorldSeconds = WorldSeconds;
				PassiveResolvedLocation = Location;
				PassiveOutwardDisplacementCm = FVector::DotProduct(
					Location - PassivePenetratingStart, PassiveContactOut);
				PassiveTangentDisplacementCm = FVector::DotProduct(
					Location - PassivePenetratingStart, PassiveTangentDirection);
				PassiveExpectedLocationErrorCm = FVector::Dist(
					Location,
					PassivePenetratingStart + PassiveExpectedAdjustment);

				bool bValid = true;
				bValid &= Test->TestTrue(
					TEXT("One authoritative world tick passively clears the exact terrain overlap"),
					ProbeResult == ERedPlanetTerrainQueryResult::NoHit
						&& !ProbeHit.bBlockingHit
						&& !ProbeHit.bStartPenetrating);
				bValid &= Test->TestTrue(
					TEXT("Passive zero-input recovery applies only the expected outward MTD"),
					PassiveOutwardDisplacementCm
						>= PassiveExpectedAdjustment.Size() - 2.0f
						&& PassiveOutwardDisplacementCm
							<= PassiveExpectedAdjustment.Size() + 2.0f
						&& FMath::Abs(PassiveTangentDisplacementCm) <= 1.0f
						&& PassiveExpectedLocationErrorCm <= 5.0f);
				bValid &= Test->TestTrue(
					TEXT("Passive recovery preserves zero velocity and actor/root synchronization"),
					Movement->Velocity.IsNearlyZero(0.1f)
						&& FVector::Dist(Ship->GetActorLocation(), Location) <= 1.0f);
				if (!bValid)
				{
					UE_LOG(LogTemp, Error,
						TEXT("RED_SHIP_PASSIVE_ZERO_INPUT_FAIL stage=first_tick result=%d outward_cm=%.6f tangent_cm=%.6f expected_error_cm=%.6f velocity_cm_s=%.6f"),
						static_cast<int32>(ProbeResult),
						PassiveOutwardDisplacementCm,
						PassiveTangentDisplacementCm,
						PassiveExpectedLocationErrorCm,
						Movement->Velocity.Size());
					return Finish();
				}
			}
			else
			{
				PassiveMaxSettleDriftCm = FMath::Max(
					PassiveMaxSettleDriftCm,
					FVector::Dist(Location, PassiveResolvedLocation));
			}

			if (PassiveObservedWorldTicks < 4
				|| WorldSeconds - PassiveFirstResolvedWorldSeconds < 0.12)
			{
				return false;
			}

			bool bValid = true;
			bValid &= Test->TestTrue(
				TEXT("Passive ship remains clear after four authoritative zero-input ticks and a second probe interval"),
				ProbeResult == ERedPlanetTerrainQueryResult::NoHit
					&& !ProbeHit.bBlockingHit
					&& !ProbeHit.bStartPenetrating);
			bValid &= Test->TestTrue(
				TEXT("Passive recovery settles without drift, velocity, or actor/root divergence"),
				PassiveMaxSettleDriftCm <= 1.0f
					&& Movement->Velocity.IsNearlyZero(0.1f)
					&& FVector::Dist(Ship->GetActorLocation(), Location) <= 1.0f);
			UE_LOG(LogTemp, Display,
				TEXT("RED_SHIP_PASSIVE_ZERO_INPUT_%s repeats=%d ticks=%d depth_cm=%.6f adjustment_cm=%.6f outward_displacement_cm=%.6f tangent_displacement_cm=%.6f expected_error_cm=%.6f settle_drift_cm=%.6f final_probe=%d"),
				bValid ? TEXT("PASS") : TEXT("FAIL"),
				PassiveOverlapRepeatCount,
				PassiveObservedWorldTicks,
				PassiveInitialDepthCm,
				PassiveExpectedAdjustment.Size(),
				PassiveOutwardDisplacementCm,
				PassiveTangentDisplacementCm,
				PassiveExpectedLocationErrorCm,
				PassiveMaxSettleDriftCm,
				static_cast<int32>(ProbeResult));
			UE_LOG(LogTemp, Display,
				TEXT("RED_FUSED_ACTIVE_TERRAIN_QUERY status=%s"),
				bValid ? TEXT("pass") : TEXT("fail"));
			return Finish();
		}

		bool SpawnStreamingSource(const FName BaseName, const FVector& Location)
		{
			UWorld* TestWorld = World.Get();
			ACLMPlanet* TestPlanet = Planet.Get();
			if (!TestWorld || !TestPlanet)
			{
				return false;
			}

			FActorSpawnParameters SpawnParameters;
			SpawnParameters.ObjectFlags |= RF_Transient;
			SpawnParameters.Name = MakeUniqueObjectName(
				TestWorld, ATargetPoint::StaticClass(), BaseName);
			ATargetPoint* Source = TestWorld->SpawnActor<ATargetPoint>(
				ATargetPoint::StaticClass(),
				FTransform(FQuat::Identity, Location),
				SpawnParameters);
			if (!IsValid(Source))
			{
				return false;
			}

			Source->SetActorEnableCollision(false);
			Source->SetActorHiddenInGame(true);
			StreamingSources.Add(Source);
			TestPlanet->AdditionalStreamingSources.AddUnique(Source);
			return true;
		}

		bool SpawnWorldDynamicBlocker()
		{
			UWorld* TestWorld = World.Get();
			if (!TestWorld)
			{
				return false;
			}

			const FVector TravelDirection = (NegativeStart - PositiveStart).GetSafeNormal();
			const FVector BlockerLocation = PositiveStart + TravelDirection * 1000.0f;
			FActorSpawnParameters SpawnParameters;
			SpawnParameters.ObjectFlags |= RF_Transient;
			SpawnParameters.Name = MakeUniqueObjectName(
				TestWorld, AActor::StaticClass(), TEXT("RED_ActiveTerrainQueryWorldDynamic"));
			AActor* BlockerActor = TestWorld->SpawnActor<AActor>(
				AActor::StaticClass(), FTransform(FQuat::Identity, BlockerLocation), SpawnParameters);
			if (!IsValid(BlockerActor))
			{
				return false;
			}

			UBoxComponent* Blocker = NewObject<UBoxComponent>(
				BlockerActor, TEXT("RED_ActiveTerrainQueryWorldDynamicBox"), RF_Transient);
			if (!Blocker)
			{
				BlockerActor->Destroy();
				return false;
			}

			BlockerActor->SetRootComponent(Blocker);
			BlockerActor->AddInstanceComponent(Blocker);
			Blocker->SetBoxExtent(FVector(250.0f), false);
			Blocker->SetCollisionEnabled(ECollisionEnabled::QueryOnly);
			Blocker->SetCollisionObjectType(ECC_WorldDynamic);
			Blocker->SetCollisionResponseToAllChannels(ECR_Block);
			Blocker->SetGenerateOverlapEvents(false);
			Blocker->RegisterComponent();
			Blocker->SetWorldLocation(BlockerLocation);
			Blocker->UpdateBounds();
			Blocker->UpdateOverlaps();
			WorldDynamicBlockerActor = BlockerActor;
			WorldDynamicBlocker = Blocker;
			return true;
		}

		bool RunAssertions()
		{
			UWorld* TestWorld = World.Get();
			ACLMPlanet* TestPlanet = Planet.Get();
			UBoxComponent* Blocker = WorldDynamicBlocker.Get();
			if (!TestWorld || !TestPlanet || !Blocker)
			{
				Test->AddError(TEXT("The active-terrain query fixture became invalid."));
				return false;
			}

			FCollisionQueryParams RawParams(SCENE_QUERY_STAT(RedFusedActiveTerrainRawControl), true);
			RawParams.bTraceComplex = true;
			const FCollisionObjectQueryParams WorldDynamicObjects(ECC_WorldDynamic);
			const FCollisionShape SweepShape = FCollisionShape::MakeSphere(50.0f);
			const FCollisionShape CapsuleShape = FCollisionShape::MakeCapsule(50.0f, 120.0f);
			const FQuat CapsuleRotation(FVector::ForwardVector, FMath::DegreesToRadians(37.0f));
			const FVector BoxHalfExtent(550.0f, 450.0f, 150.0f);
			const FCollisionShape BoxShape = FCollisionShape::MakeBox(BoxHalfExtent);
			const FVector BoxRadialUp = SeamDirection.GetSafeNormal();
			const FVector BoxForward = FVector::VectorPlaneProject(
				FVector::UpVector, BoxRadialUp).GetSafeNormal();
			const FQuat BoxBaseRotation = FRotationMatrix::MakeFromZX(
				BoxRadialUp, BoxForward).ToQuat();
			const FQuat BoxRotation = FQuat(
				BoxRadialUp, FMath::DegreesToRadians(37.0f)) * BoxBaseRotation;
			const double ExtremeRotationComponent = TNumericLimits<double>::Max();
			const FQuat OverflowRotation(
				ExtremeRotationComponent,
				0.0,
				0.0,
				ExtremeRotationComponent);
			FHitResult OverflowRotationHit;
			FIntVector OverflowRotationKey;
			const bool bOverflowRotationHit = TestPlanet->SweepActiveTerrain(
				OverflowRotationHit,
				PositiveStart,
				NegativeStart,
				OverflowRotation,
				BoxShape,
				&OverflowRotationKey);

			FHitResult RawLineHit;
			const bool bRawLineHit = TestWorld->LineTraceSingleByObjectType(
				RawLineHit, PositiveStart, NegativeStart, WorldDynamicObjects, RawParams);
			FHitResult RawSweepHit;
			const bool bRawSweepHit = TestWorld->SweepSingleByObjectType(
				RawSweepHit, PositiveStart, NegativeStart, FQuat::Identity,
				WorldDynamicObjects, SweepShape, RawParams);
			FHitResult RawCapsuleHit;
			const bool bRawCapsuleHit = TestWorld->SweepSingleByObjectType(
				RawCapsuleHit, PositiveStart, NegativeStart, CapsuleRotation,
				WorldDynamicObjects, CapsuleShape, RawParams);
			FHitResult RawBoxHit;
			const bool bRawBoxHit = TestWorld->SweepSingleByObjectType(
				RawBoxHit, PositiveStart, NegativeStart, BoxRotation,
				WorldDynamicObjects, BoxShape, RawParams);

			FHitResult ForwardLineHit;
			FHitResult ReverseLineHit;
			FHitResult ForwardSweepHit;
			FHitResult ReverseSweepHit;
			FHitResult ForwardCapsuleHit;
			FHitResult ForwardBoxHit;
			FHitResult ReverseBoxHit;
			FHitResult WrappedBoxHit;
			FIntVector ForwardLineKey;
			FIntVector ReverseLineKey;
			FIntVector ForwardSweepKey;
			FIntVector ReverseSweepKey;
			FIntVector ForwardCapsuleKey;
			FIntVector ForwardBoxKey;
			FIntVector ReverseBoxKey;
			FIntVector WrappedBoxKey;
			const bool bForwardLineHit = TestPlanet->LineTraceActiveTerrain(
				ForwardLineHit, PositiveStart, NegativeStart, &ForwardLineKey);
			const bool bReverseLineHit = TestPlanet->LineTraceActiveTerrain(
				ReverseLineHit, NegativeStart, PositiveStart, &ReverseLineKey);
			const bool bForwardSweepHit = TestPlanet->SweepActiveTerrain(
				ForwardSweepHit, PositiveStart, NegativeStart, FQuat::Identity,
				SweepShape, &ForwardSweepKey);
			const bool bReverseSweepHit = TestPlanet->SweepActiveTerrain(
				ReverseSweepHit, NegativeStart, PositiveStart, FQuat::Identity,
				SweepShape, &ReverseSweepKey);
			const bool bForwardCapsuleHit = TestPlanet->SweepActiveTerrain(
				ForwardCapsuleHit, PositiveStart, NegativeStart, CapsuleRotation,
				CapsuleShape, &ForwardCapsuleKey);
			const bool bForwardBoxHit = TestPlanet->SweepActiveTerrain(
				ForwardBoxHit, PositiveStart, NegativeStart, BoxRotation,
				BoxShape, &ForwardBoxKey);
			const bool bReverseBoxHit = TestPlanet->SweepActiveTerrain(
				ReverseBoxHit, NegativeStart, PositiveStart, BoxRotation,
				BoxShape, &ReverseBoxKey);
			const ERedPlanetTerrainQueryResult WrappedBoxResult =
				RedPlanetTerrainQuery::Sweep(
					TestWorld,
					TestPlanet->GetActorLocation(),
					PositiveStart,
					NegativeStart,
					BoxRotation,
					BoxShape,
					WrappedBoxHit,
					&WrappedBoxKey);

			bool bValid = true;
			bValid &= Test->TestTrue(
				TEXT("A raw WorldDynamic line trace hits the closer blocker"), bRawLineHit);
			bValid &= Test->TestTrue(
				TEXT("The raw line trace reports the exact blocker component"),
				bRawLineHit && RawLineHit.GetComponent() == Blocker);
			bValid &= Test->TestTrue(
				TEXT("A raw WorldDynamic sphere sweep hits the closer blocker"), bRawSweepHit);
			bValid &= Test->TestTrue(
				TEXT("The raw sphere sweep reports the exact blocker component"),
				bRawSweepHit && RawSweepHit.GetComponent() == Blocker);
			bValid &= Test->TestTrue(
				TEXT("A raw WorldDynamic rotated capsule sweep hits the closer blocker"), bRawCapsuleHit);
			bValid &= Test->TestTrue(
				TEXT("The raw rotated capsule sweep reports the exact blocker component"),
				bRawCapsuleHit && RawCapsuleHit.GetComponent() == Blocker);

			bool bBoxValid = true;
			bBoxValid &= Test->TestTrue(
				TEXT("An overflowing finite box rotation is rejected before Chaos"),
				!bOverflowRotationHit
					&& !OverflowRotationHit.bBlockingHit
					&& !OverflowRotationHit.bStartPenetrating
					&& OverflowRotationKey
						== FIntVector(INDEX_NONE, INDEX_NONE, INDEX_NONE));
			bBoxValid &= Test->TestTrue(
				TEXT("A raw WorldDynamic rotated fitted-hull box sweep hits the closer blocker"),
				bRawBoxHit);
			bBoxValid &= Test->TestTrue(
				TEXT("The raw rotated fitted-hull box sweep reports the exact blocker component"),
				bRawBoxHit && RawBoxHit.GetComponent() == Blocker);

			bValid &= Test->TestTrue(TEXT("The forward active-terrain line trace succeeds"), bForwardLineHit);
			bValid &= Test->TestTrue(TEXT("The reverse active-terrain line trace succeeds"), bReverseLineHit);
			bValid &= Test->TestTrue(TEXT("The forward active-terrain sweep succeeds"), bForwardSweepHit);
			bValid &= Test->TestTrue(TEXT("The reverse active-terrain sweep succeeds"), bReverseSweepHit);
			bValid &= Test->TestTrue(
				TEXT("The forward active-terrain rotated capsule sweep succeeds"), bForwardCapsuleHit);
			bBoxValid &= Test->TestTrue(
				TEXT("The forward active-terrain rotated fitted-hull box sweep succeeds"),
				bForwardBoxHit);
			bBoxValid &= Test->TestTrue(
				TEXT("The reverse active-terrain rotated fitted-hull box sweep succeeds"),
				bReverseBoxHit);
			bBoxValid &= Test->TestTrue(
				TEXT("The project exact-terrain adapter accepts the rotated fitted-hull box"),
				WrappedBoxResult == ERedPlanetTerrainQueryResult::Hit);
			if (bForwardLineHit)
			{
				bValid &= ValidateActiveTerrainHit(
					TEXT("Forward line"), ForwardLineHit, ForwardLineKey, SeamDirection);
				bValid &= Test->TestEqual(
					TEXT("The +X face deterministically owns the positive X/Y seam line hit"),
					ForwardLineKey.X,
					static_cast<int32>(EPlanetGenMacroCubeFace::PositiveX));
			}
			if (bReverseLineHit)
			{
				bValid &= ValidateActiveTerrainHit(
					TEXT("Reverse line"), ReverseLineHit, ReverseLineKey, -SeamDirection);
			}
			if (bForwardSweepHit)
			{
				bValid &= ValidateActiveTerrainHit(
					TEXT("Forward sweep"), ForwardSweepHit, ForwardSweepKey, SeamDirection);
			}
			if (bReverseSweepHit)
			{
				bValid &= ValidateActiveTerrainHit(
					TEXT("Reverse sweep"), ReverseSweepHit, ReverseSweepKey, -SeamDirection);
			}
			if (bForwardCapsuleHit)
			{
				bValid &= ValidateActiveTerrainHit(
					TEXT("Forward rotated capsule sweep"),
					ForwardCapsuleHit,
					ForwardCapsuleKey,
					SeamDirection);
			}
			if (bForwardBoxHit)
			{
				bBoxValid &= ValidateActiveTerrainHit(
					TEXT("Forward rotated fitted-hull box sweep"),
					ForwardBoxHit,
					ForwardBoxKey,
					SeamDirection);
			}
			if (bReverseBoxHit)
			{
				bBoxValid &= ValidateActiveTerrainHit(
					TEXT("Reverse rotated fitted-hull box sweep"),
					ReverseBoxHit,
					ReverseBoxKey,
					-SeamDirection);
			}
			if (WrappedBoxResult == ERedPlanetTerrainQueryResult::Hit)
			{
				bBoxValid &= ValidateActiveTerrainHit(
					TEXT("Adapter rotated fitted-hull box sweep"),
					WrappedBoxHit,
					WrappedBoxKey,
					SeamDirection);
				bBoxValid &= Test->TestTrue(
					TEXT("The adapter and direct rotated box queries select one component/key"),
					bForwardBoxHit
						&& WrappedBoxKey == ForwardBoxKey
						&& WrappedBoxHit.GetComponent() == ForwardBoxHit.GetComponent()
						&& FMath::IsNearlyEqual(
							WrappedBoxHit.Distance, ForwardBoxHit.Distance, 0.01f));
			}

			if (bRawLineHit && bForwardLineHit)
			{
				bValid &= Test->TestTrue(
					TEXT("The ignored WorldDynamic line blocker is closer than the terrain hit"),
					RawLineHit.Distance < ForwardLineHit.Distance);
			}
			if (bRawSweepHit && bForwardSweepHit)
			{
				bValid &= Test->TestTrue(
					TEXT("The ignored WorldDynamic sweep blocker is closer than the terrain hit"),
					RawSweepHit.Distance < ForwardSweepHit.Distance);
			}
			if (bRawCapsuleHit && bForwardCapsuleHit)
			{
				bValid &= Test->TestTrue(
					TEXT("The ignored WorldDynamic rotated capsule blocker is closer than the terrain hit"),
					RawCapsuleHit.Distance < ForwardCapsuleHit.Distance);
			}
			if (bRawBoxHit && bForwardBoxHit)
			{
				bBoxValid &= Test->TestTrue(
					TEXT("The ignored WorldDynamic rotated box blocker is closer than the terrain hit"),
					RawBoxHit.Distance < ForwardBoxHit.Distance);
			}

			if (bForwardLineHit)
			{
				bValid &= ValidateStableLineSelection(ForwardLineHit, ForwardLineKey);
			}
			if (bForwardSweepHit)
			{
				bValid &= ValidateStableSweepSelection(
					TEXT("sphere"), ForwardSweepHit, ForwardSweepKey, SweepShape, FQuat::Identity);
			}
			if (bForwardCapsuleHit)
			{
				bValid &= ValidateStableSweepSelection(
					TEXT("rotated-capsule"),
					ForwardCapsuleHit,
					ForwardCapsuleKey,
					CapsuleShape,
					CapsuleRotation);
			}
			if (bForwardBoxHit)
			{
				bBoxValid &= ValidateStableSweepSelection(
					TEXT("rotated-fitted-hull-box"),
					ForwardBoxHit,
					ForwardBoxKey,
					BoxShape,
					BoxRotation);
				bBoxValid &= ValidateRotatedBoxCandidateExpansion(
					ForwardBoxHit,
					ForwardBoxKey,
					BoxShape,
					BoxHalfExtent,
					BoxRotation);
				bBoxValid &= ValidateRotatedBoxDepenetration(
					ForwardBoxHit,
					ForwardBoxKey,
					BoxShape,
					BoxRotation);
			}
			if (bBoxValid)
			{
				UE_LOG(LogTemp, Display,
					TEXT("RED_FUSED_ACTIVE_TERRAIN_BOX_PASS half_extent_cm=(%.1f,%.1f,%.1f) rotation_deg=37.0 key=(%d,%d,%d) direct_distance_cm=%.6f adapter_distance_cm=%.6f"),
					BoxHalfExtent.X,
					BoxHalfExtent.Y,
					BoxHalfExtent.Z,
					ForwardBoxKey.X,
					ForwardBoxKey.Y,
					ForwardBoxKey.Z,
					ForwardBoxHit.Distance,
					WrappedBoxHit.Distance);
			}
			bValid &= bBoxValid;
			if (bForwardLineHit)
			{
				if (bBoxValid)
				{
					bValid &= ValidateProductionDerivedLiveFighterHullQuery(ForwardLineHit);
				}
				bValid &= ValidateVehicleSurfaceIntegration(ForwardLineHit);
			}
			return bValid;
		}

		bool ValidateProductionDerivedLiveFighterHullQuery(
			const FHitResult& BaselineTerrainHit)
		{
			UWorld* TestWorld = World.Get();
			ACLMPlanet* TestPlanet = Planet.Get();
			UBoxComponent* Blocker = WorldDynamicBlocker.Get();
			if (!TestWorld || !TestPlanet || !Blocker)
			{
				return Test->TestTrue(
					TEXT("The live fighter hull query fixture remains valid"), false);
			}

			constexpr TCHAR FighterClassPath[] =
				TEXT("/Game/RedMMO/Ships/BP_RedModularStarSparrow.BP_RedModularStarSparrow_C");
			constexpr TCHAR FighterPackagePath[] =
				TEXT("/Game/RedMMO/Ships/BP_RedModularStarSparrow");
			UPackage* PreexistingFighterPackage = FindPackage(nullptr, FighterPackagePath);
			const bool bExpectedPackageDirty = PreexistingFighterPackage
				? PreexistingFighterPackage->IsDirty()
				: false;
			UClass* FighterClass = StaticLoadClass(
				ARedShip::StaticClass(), nullptr, FighterClassPath);
			bool bValid = true;
			bValid &= Test->TestNotNull(
				TEXT("The production modular fighter Blueprint class loads"), FighterClass);
			bValid &= Test->TestTrue(
				TEXT("The production modular fighter Blueprint derives from ARedShip"),
				FighterClass
					&& FighterClass != ARedShip::StaticClass()
					&& FighterClass->IsChildOf(ARedShip::StaticClass()));
			if (!FighterClass || !FighterClass->IsChildOf(ARedShip::StaticClass()))
			{
				return false;
			}

			UPackage* FighterPackage = FighterClass->GetOutermost();
			bValid &= Test->TestTrue(
				TEXT("Loading the production fighter class preserves its package dirty state"),
				FighterPackage
					&& FighterPackage->IsDirty() == bExpectedPackageDirty
					&& (!PreexistingFighterPackage
						|| PreexistingFighterPackage == FighterPackage));
			const FVector PlanetCenter = TestPlanet->GetActorLocation();
			const FVector RadialOut =
				(BaselineTerrainHit.ImpactPoint - PlanetCenter).GetSafeNormal();
			FVector TangentUp = FVector::VectorPlaneProject(
				FVector::UpVector, RadialOut).GetSafeNormal();
			if (TangentUp.IsNearlyZero())
			{
				TangentUp = FVector::VectorPlaneProject(
					FVector::RightVector, RadialOut).GetSafeNormal();
			}
			// Deliberately exercise a valid 6DOF nose-radial attitude. The live hull's long X support
			// must become the limiting terrain query before the production 260 cm root sphere.
			const FQuat FighterRotation = FRotationMatrix::MakeFromXZ(
				RadialOut, TangentUp).ToQuat();
			FActorSpawnParameters SpawnParameters;
			SpawnParameters.ObjectFlags |= RF_Transient;
			SpawnParameters.SpawnCollisionHandlingOverride =
				ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
			SpawnParameters.Name = MakeUniqueObjectName(
				TestWorld, FighterClass, TEXT("RED_LiveModularFighterHullQuery"));
			ARedShip* Fighter = TestWorld->SpawnActor<ARedShip>(
				FighterClass,
				FTransform(FighterRotation, PositiveStart),
				SpawnParameters);
			bValid &= Test->TestNotNull(
				TEXT("The transient production modular fighter spawns"), Fighter);
			if (!Fighter)
			{
				return false;
			}

			Fighter->SetActorTickEnabled(false);
			URedShipMovementComponent* ProductionMovement =
				Cast<URedShipMovementComponent>(Fighter->GetMovementComponent());
			if (ProductionMovement)
			{
				ProductionMovement->SetComponentTickEnabled(false);
				ProductionMovement->Velocity = FVector::ZeroVector;
				ProductionMovement->PlanetCenter = TestPlanet->GetActorLocation();
				ProductionMovement->PlanetRadius = TestPlanet->PlanetRadius;
			}
			const FTransform SpawnedActorTransform = Fighter->GetActorTransform();
			UBoxComponent* LiveHull = Cast<UBoxComponent>(
				Fighter->GetDefaultSubobjectByName(TEXT("RuntimeHullCollision")));
			if (!LiveHull)
			{
				TArray<UBoxComponent*> BoxComponents;
				Fighter->GetComponents<UBoxComponent>(BoxComponents);
				for (UBoxComponent* Candidate : BoxComponents)
				{
					if (Candidate
						&& Candidate->GetName().Contains(TEXT("RuntimeHullCollision")))
					{
						LiveHull = Candidate;
						break;
					}
				}
			}

			USphereComponent* RootSphere =
				Cast<USphereComponent>(Fighter->GetRootComponent());
			bValid &= Test->TestTrue(
				TEXT("The spawned fighter is transient and has begun play"),
				Fighter->HasAnyFlags(RF_Transient) && Fighter->HasActorBegunPlay());
			bValid &= Test->TestNotNull(
				TEXT("The live Blueprint exposes RuntimeHullCollision"), LiveHull);
			bValid &= Test->TestNotNull(
				TEXT("The live Blueprint retains its production sphere root"), RootSphere);
			bValid &= Test->TestNotNull(
				TEXT("The live Blueprint owns its production movement component"),
				ProductionMovement);
			if (!LiveHull || !RootSphere || !ProductionMovement)
			{
				Fighter->Destroy();
				return false;
			}
			bValid &= Test->TestTrue(
				TEXT("Production movement keeps the sphere root as UpdatedComponent"),
				ProductionMovement->UpdatedComponent == RootSphere);
			bValid &= Test->TestTrue(
				TEXT("BeginPlay publishes the completed live fit as the translation envelope"),
				ProductionMovement->GetTranslationCollisionEnvelope() == LiveHull);

			const FVector LiveRelativeCenter = LiveHull->GetRelativeLocation();
			const FVector LiveUnscaledHalfExtent = LiveHull->GetUnscaledBoxExtent();
			const FVector LiveScaledHalfExtent = LiveHull->GetScaledBoxExtent();
			const FVector LiveBoxStart = LiveHull->GetComponentLocation();
			const FQuat LiveBoxRotation = LiveHull->GetComponentQuat();
			const FVector RequestedDelta = NegativeStart - PositiveStart;
			const FVector LiveBoxEnd = LiveBoxStart + RequestedDelta;
			const FCollisionShape LiveBoxShape =
				FCollisionShape::MakeBox(LiveScaledHalfExtent);

			FBox ExpectedVisibleBounds(ForceInit);
			int32 IncludedVisibleMeshCount = 0;
			UStaticMeshComponent* ResponseWitnessMesh = nullptr;
			double ResponseWitnessRootDistanceCm = -1.0;
			const FTransform RootTransform = RootSphere->GetComponentTransform();
			TArray<UStaticMeshComponent*> MeshComponents;
			Fighter->GetComponents<UStaticMeshComponent>(MeshComponents);
			for (UStaticMeshComponent* Mesh : MeshComponents)
			{
				if (!Mesh || !Mesh->IsRegistered() || !Mesh->GetStaticMesh()
					|| Mesh->GetName().Contains(TEXT("Plume"))
					|| Mesh->GetStaticMesh()->GetPathName().Contains(
						TEXT("/Engine/BasicShapes/Cube")))
				{
					continue;
				}

				const FBox AssetBounds = Mesh->GetStaticMesh()->GetBoundingBox();
				if (!AssetBounds.IsValid)
				{
					continue;
				}
				const FTransform MeshTransform = Mesh->GetComponentTransform();
				double MeshMaxRootDistanceCm = 0.0;
				for (int32 CornerIndex = 0; CornerIndex < 8; ++CornerIndex)
				{
					const FVector AssetCorner(
						(CornerIndex & 1) ? AssetBounds.Max.X : AssetBounds.Min.X,
						(CornerIndex & 2) ? AssetBounds.Max.Y : AssetBounds.Min.Y,
						(CornerIndex & 4) ? AssetBounds.Max.Z : AssetBounds.Min.Z);
					const FVector RootLocalCorner =
						RootTransform.InverseTransformPosition(
							MeshTransform.TransformPosition(AssetCorner));
					ExpectedVisibleBounds += RootLocalCorner;
					MeshMaxRootDistanceCm = FMath::Max(
						MeshMaxRootDistanceCm, RootLocalCorner.Size());
				}
				if (MeshMaxRootDistanceCm > ResponseWitnessRootDistanceCm)
				{
					ResponseWitnessRootDistanceCm = MeshMaxRootDistanceCm;
					ResponseWitnessMesh = Mesh;
				}
				++IncludedVisibleMeshCount;
			}

			const FVector ExpectedCenter = ExpectedVisibleBounds.IsValid
				? ExpectedVisibleBounds.GetCenter()
				: FVector::ZeroVector;
			const FVector RawExpectedExtent = ExpectedVisibleBounds.IsValid
				? ExpectedVisibleBounds.GetExtent()
				: FVector::ZeroVector;
			const FVector ExpectedExtent(
				FMath::Clamp(RawExpectedExtent.X, 250.0, 8000.0),
				FMath::Clamp(RawExpectedExtent.Y, 150.0, 5000.0),
				FMath::Clamp(RawExpectedExtent.Z, 80.0, 2500.0));

			bValid &= Test->TestTrue(
				TEXT("The runtime hull is registered with a production physics state"),
				LiveHull->IsRegistered() && LiveHull->IsPhysicsStateCreated());
			bValid &= Test->TestTrue(
				TEXT("RuntimeHullCollision remains attached directly to the sphere root"),
				LiveHull->GetAttachParent() == RootSphere);
			bValid &= Test->TestTrue(
				TEXT("RuntimeHullCollision retains the production Vehicle response mask"),
				LiveHull->GetCollisionObjectType() == ECC_Vehicle
					&& LiveHull->GetCollisionResponseToChannel(ECC_WorldStatic) == ECR_Block
					&& LiveHull->GetCollisionResponseToChannel(ECC_WorldDynamic) == ECR_Ignore);
			bValid &= Test->TestTrue(
				TEXT("The live fitted hull transform and extent are finite and positive"),
				!LiveRelativeCenter.ContainsNaN()
					&& !LiveScaledHalfExtent.ContainsNaN()
					&& LiveScaledHalfExtent.GetMin() > 0.0
					&& LiveBoxRotation.IsNormalized());
			bValid &= Test->TestTrue(
				TEXT("The live hull fit includes the modular visible mesh stack"),
				ExpectedVisibleBounds.IsValid && IncludedVisibleMeshCount >= 2);
			bValid &= Test->TestTrue(
				TEXT("The live RuntimeHullCollision centre matches the visible mesh union"),
				ExpectedVisibleBounds.IsValid
					&& LiveRelativeCenter.Equals(ExpectedCenter, 0.1));
			bValid &= Test->TestTrue(
				TEXT("The live RuntimeHullCollision extent matches the visible mesh union"),
				ExpectedVisibleBounds.IsValid
					&& LiveUnscaledHalfExtent.Equals(ExpectedExtent, 0.1));
			bValid &= Test->TestTrue(
				TEXT("The live Blueprint fit is not the smaller hardcoded query box"),
				!LiveScaledHalfExtent.Equals(FVector(550.0, 450.0, 150.0), 1.0));
			// The acceptance below uses only copied component transforms and FCollisionShape queries.
			// Disable the transient actor's live primitives so it cannot participate in its controls.
			Fighter->SetActorEnableCollision(false);

			FCollisionQueryParams RawParams(
				SCENE_QUERY_STAT(RedLiveFighterHullRawControl), true);
			RawParams.bTraceComplex = true;
			RawParams.bFindInitialOverlaps = true;
			RawParams.bReturnFaceIndex = true;
			RawParams.AddIgnoredActor(Fighter);
			const FCollisionObjectQueryParams WorldDynamicObjects(ECC_WorldDynamic);
			FHitResult RawBlockerHit(1.0f);
			const bool bRawBlockerHit = TestWorld->SweepSingleByObjectType(
				RawBlockerHit,
				LiveBoxStart,
				LiveBoxEnd,
				LiveBoxRotation,
				WorldDynamicObjects,
				LiveBoxShape,
				RawParams);

			FHitResult DirectHit(1.0f);
			FHitResult AdapterHit(1.0f);
			FIntVector DirectKey;
			FIntVector AdapterKey;
			const bool bDirectHit = TestPlanet->SweepActiveTerrain(
				DirectHit,
				LiveBoxStart,
				LiveBoxEnd,
				LiveBoxRotation,
				LiveBoxShape,
				&DirectKey);
			const ERedPlanetTerrainQueryResult AdapterResult =
				RedPlanetTerrainQuery::Sweep(
					TestWorld,
					PlanetCenter,
					LiveBoxStart,
					LiveBoxEnd,
					LiveBoxRotation,
					LiveBoxShape,
					AdapterHit,
					&AdapterKey);

			FCollisionQueryParams RawTerrainParams(RawParams);
			if (AActor* BlockerOwner = Blocker->GetOwner())
			{
				RawTerrainParams.AddIgnoredActor(BlockerOwner);
			}
			TArray<FHitResult> RawTerrainHits;
			const bool bAnyRawTerrainHit = TestWorld->SweepMultiByObjectType(
				RawTerrainHits,
				LiveBoxStart,
				LiveBoxEnd,
				LiveBoxRotation,
				WorldDynamicObjects,
				LiveBoxShape,
				RawTerrainParams);
			const FHitResult* RawSelectedTerrainHit = bDirectHit
				? RawTerrainHits.FindByPredicate([&DirectHit](const FHitResult& Candidate)
				{
					return Candidate.GetComponent() == DirectHit.GetComponent()
						&& FMath::IsNearlyEqual(
							Candidate.Distance, DirectHit.Distance, 0.1f);
				})
				: nullptr;

			const float RootRadius = RootSphere->GetScaledSphereRadius();
			const FCollisionShape RootShape = FCollisionShape::MakeSphere(RootRadius);
			const FVector RootStart = RootSphere->GetComponentLocation();
			FHitResult RootHit(1.0f);
			FIntVector RootKey;
			const bool bRootHit = TestPlanet->SweepActiveTerrain(
				RootHit,
				RootStart,
				RootStart + RequestedDelta,
				RootSphere->GetComponentQuat(),
				RootShape,
				&RootKey);
			const FVector MoveDirection = RequestedDelta.GetSafeNormal();
			const double ProjectedLiveBoxSupportCm = FVector::DotProduct(
				LiveBoxStart - RootStart, MoveDirection)
				+ FMath::Abs(FVector::DotProduct(
					LiveBoxRotation.GetAxisX(), MoveDirection)) * LiveScaledHalfExtent.X
				+ FMath::Abs(FVector::DotProduct(
					LiveBoxRotation.GetAxisY(), MoveDirection)) * LiveScaledHalfExtent.Y
				+ FMath::Abs(FVector::DotProduct(
					LiveBoxRotation.GetAxisZ(), MoveDirection)) * LiveScaledHalfExtent.Z;
			const double ExpectedLiveBoxLeadCm =
				ProjectedLiveBoxSupportCm - RootRadius;
			const double ObservedLiveBoxLeadCm =
				RootHit.Distance - DirectHit.Distance;

			bValid &= Test->TestTrue(
				TEXT("Raw Chaos sees the deliberately closer arbitrary WorldDynamic blocker"),
				bRawBlockerHit && RawBlockerHit.GetComponent() == Blocker);
			bValid &= Test->TestTrue(
				TEXT("The production-derived live hull hits exact active terrain"), bDirectHit);
			bValid &= Test->TestTrue(
				TEXT("The exact-terrain adapter accepts the production-derived live hull"),
				AdapterResult == ERedPlanetTerrainQueryResult::Hit);
			if (bDirectHit)
			{
				bValid &= ValidateActiveTerrainHit(
					TEXT("Production-derived live fighter hull"),
					DirectHit,
					DirectKey,
					RadialOut);
			}
			bValid &= Test->TestTrue(
				TEXT("Filtered raw Chaos contains the exact selected owned terrain contact"),
				bAnyRawTerrainHit && RawSelectedTerrainHit != nullptr);
			bValid &= Test->TestTrue(
				TEXT("Filtered raw Chaos preserves the selected live-hull contact data"),
				RawSelectedTerrainHit
					&& RawSelectedTerrainHit->bBlockingHit == DirectHit.bBlockingHit
					&& RawSelectedTerrainHit->bStartPenetrating
						== DirectHit.bStartPenetrating
					&& RawSelectedTerrainHit->FaceIndex == DirectHit.FaceIndex
					&& FMath::IsNearlyEqual(
						RawSelectedTerrainHit->Time, DirectHit.Time, 1.0e-5f)
					&& FVector::Dist(
						RawSelectedTerrainHit->Location, DirectHit.Location) <= 0.1f
					&& FVector::Dist(
						RawSelectedTerrainHit->ImpactPoint, DirectHit.ImpactPoint) <= 0.1f
					&& FVector::DotProduct(
						RawSelectedTerrainHit->Normal, DirectHit.Normal) >= 0.9999f);
			bValid &= Test->TestTrue(
				TEXT("Direct and adapter live-hull queries preserve one complete contact"),
				bDirectHit
					&& AdapterResult == ERedPlanetTerrainQueryResult::Hit
					&& DirectKey == AdapterKey
					&& DirectHit.GetComponent() == AdapterHit.GetComponent()
					&& DirectHit.FaceIndex == AdapterHit.FaceIndex
					&& FMath::IsNearlyEqual(DirectHit.Time, AdapterHit.Time, 1.0e-5f)
					&& FMath::IsNearlyEqual(DirectHit.Distance, AdapterHit.Distance, 0.1f)
					&& FVector::Dist(DirectHit.Location, AdapterHit.Location) <= 0.1f
					&& FVector::Dist(DirectHit.ImpactPoint, AdapterHit.ImpactPoint) <= 0.1f
					&& FVector::DotProduct(DirectHit.Normal, AdapterHit.Normal) >= 0.9999f);
			bValid &= Test->TestTrue(
				TEXT("The arbitrary blocker is closer but excluded from exact terrain"),
				bRawBlockerHit && bDirectHit
					&& RawBlockerHit.Distance < DirectHit.Distance
					&& DirectHit.GetComponent() != Blocker);
			bValid &= Test->TestTrue(
				TEXT("The live box and root comparison starts clear and non-penetrating"),
				bDirectHit && bRootHit
					&& !DirectHit.bStartPenetrating
					&& !RootHit.bStartPenetrating
					&& DirectHit.Distance > 0.0f
					&& RootHit.Distance > 0.0f);
			bValid &= Test->TestTrue(
				TEXT("The live box is the mathematically limiting terrain shape in the nose-radial attitude"),
				bDirectHit && bRootHit
					&& ExpectedLiveBoxLeadCm > 0.0
					&& ObservedLiveBoxLeadCm > 0.0
					&& FMath::IsNearlyEqual(
						ObservedLiveBoxLeadCm, ExpectedLiveBoxLeadCm, 10.0));

			bool bRepeatedStable = bDirectHit
				&& AdapterResult == ERedPlanetTerrainQueryResult::Hit;
			for (int32 Repeat = 0; Repeat < 8 && bRepeatedStable; ++Repeat)
			{
				FHitResult RepeatedDirectHit(1.0f);
				FHitResult RepeatedAdapterHit(1.0f);
				FIntVector RepeatedDirectKey;
				FIntVector RepeatedAdapterKey;
				const bool bRepeatedDirect = TestPlanet->SweepActiveTerrain(
					RepeatedDirectHit,
					LiveBoxStart,
					LiveBoxEnd,
					LiveBoxRotation,
					LiveBoxShape,
					&RepeatedDirectKey);
				const ERedPlanetTerrainQueryResult RepeatedAdapterResult =
					RedPlanetTerrainQuery::Sweep(
						TestWorld,
						PlanetCenter,
						LiveBoxStart,
						LiveBoxEnd,
						LiveBoxRotation,
						LiveBoxShape,
						RepeatedAdapterHit,
						&RepeatedAdapterKey);
				bRepeatedStable &= bRepeatedDirect
					&& RepeatedAdapterResult == ERedPlanetTerrainQueryResult::Hit
					&& RepeatedDirectKey == DirectKey
					&& RepeatedAdapterKey == DirectKey
					&& RepeatedDirectHit.GetComponent() == DirectHit.GetComponent()
					&& RepeatedAdapterHit.GetComponent() == DirectHit.GetComponent()
					&& RepeatedDirectHit.FaceIndex == DirectHit.FaceIndex
					&& RepeatedAdapterHit.FaceIndex == DirectHit.FaceIndex
					&& FMath::IsNearlyEqual(
						RepeatedDirectHit.Time, DirectHit.Time, 1.0e-5f)
					&& FMath::IsNearlyEqual(
						RepeatedAdapterHit.Time, DirectHit.Time, 1.0e-5f)
					&& FMath::IsNearlyEqual(
						RepeatedDirectHit.Distance, DirectHit.Distance, 0.1f)
					&& FMath::IsNearlyEqual(
						RepeatedAdapterHit.Distance, DirectHit.Distance, 0.1f)
					&& FVector::Dist(
						RepeatedDirectHit.Location, DirectHit.Location) <= 0.1f
					&& FVector::Dist(
						RepeatedDirectHit.ImpactPoint, DirectHit.ImpactPoint) <= 0.1f
					&& FVector::DotProduct(
						RepeatedDirectHit.Normal, DirectHit.Normal) >= 0.9999f;
			}
			bValid &= Test->TestTrue(
				TEXT("Eight live-fighter hull queries preserve component, key, face, time, distance, position, and normal"),
				bRepeatedStable);

			bValid &= Test->TestTrue(
				TEXT("The query-only phase does not move the spawned fighter"),
				Fighter->GetActorTransform().Equals(SpawnedActorTransform, 0.001));

			// First response gate for the production-derived fitted hull. Keep this deliberately
			// translation-only and single-piece: arbitrate an explicit native WorldStatic sweep
			// against the exact owned PlanetGen contact, pull the whole actor back from the winning
			// contact, and prove that arbitrary WorldDynamic presentation/gameplay actors never enter
			// the exact-terrain branch. Rotation, overlap recovery, and compound wing/body response are
			// later gates.
			float ResponseTerrainDistanceCm = 0.0f;
			float ResponseStaticDistanceCm = 0.0f;
			float ResponseDynamicDistanceCm = 0.0f;
			float ResponseStaticAcceptedDistanceCm = 0.0f;
			float ResponseAcceptedDistanceCm = 0.0f;
			FIntVector ResponseTerrainKey(INDEX_NONE, INDEX_NONE, INDEX_NONE);
			bool bTranslationResponseValid = bDirectHit && !MoveDirection.IsNearlyZero();
			AActor* StaticControlActor = nullptr;
			UBoxComponent* StaticControl = nullptr;
			const FTransform SavedDynamicTransform = Blocker->GetComponentTransform();
			const FVector SavedDynamicExtent = Blocker->GetUnscaledBoxExtent();
			const ECollisionEnabled::Type SavedDynamicCollision =
				Blocker->GetCollisionEnabled();
			if (bTranslationResponseValid)
			{
				constexpr float ApproachDistanceCm = 100.0f;
				constexpr float OvertravelDistanceCm = 20.0f;
				constexpr float ContactPullbackCm = 2.0f;
				const FVector ResponseBoxStart =
					DirectHit.Location - MoveDirection * ApproachDistanceCm;
				const FVector ResponseDelta = MoveDirection
					* (ApproachDistanceCm + OvertravelDistanceCm);
				const FVector ResponseBoxEnd = ResponseBoxStart + ResponseDelta;
				const FVector RootToBoxOffset = RootStart - LiveBoxStart;
				const FVector ResponseRootStart = ResponseBoxStart + RootToBoxOffset;
				const FTransform ResponseActorStart(
					SpawnedActorTransform.GetRotation(),
					ResponseRootStart,
					SpawnedActorTransform.GetScale3D());
				const FVector RelativeCenterBeforeResponse = LiveHull->GetRelativeLocation();
				const FQuat RelativeRotationBeforeResponse =
					LiveHull->GetRelativeRotation().Quaternion();
				const FVector ExtentBeforeResponse = LiveHull->GetScaledBoxExtent();
				const FQuat ActorRotationBeforeResponse = Fighter->GetActorQuat();

				Fighter->SetActorTransform(
					ResponseActorStart, false, nullptr, ETeleportType::TeleportPhysics);
				LiveHull->UpdateBounds();
				bTranslationResponseValid &= FVector::Dist(
					LiveHull->GetComponentLocation(), ResponseBoxStart) <= 0.1f;

				const double MovingSupportCm =
					FMath::Abs(FVector::DotProduct(
						LiveBoxRotation.GetAxisX(), MoveDirection)) * LiveScaledHalfExtent.X
					+ FMath::Abs(FVector::DotProduct(
						LiveBoxRotation.GetAxisY(), MoveDirection)) * LiveScaledHalfExtent.Y
					+ FMath::Abs(FVector::DotProduct(
						LiveBoxRotation.GetAxisZ(), MoveDirection)) * LiveScaledHalfExtent.Z;
				const FVector ControlExtent(10.0f, 2000.0f, 2000.0f);
				const FQuat ControlRotation =
					FRotationMatrix::MakeFromX(MoveDirection).ToQuat();
				const double ControlSupportCm =
					FMath::Abs(FVector::DotProduct(
						ControlRotation.GetAxisX(), MoveDirection)) * ControlExtent.X
					+ FMath::Abs(FVector::DotProduct(
						ControlRotation.GetAxisY(), MoveDirection)) * ControlExtent.Y
					+ FMath::Abs(FVector::DotProduct(
						ControlRotation.GetAxisZ(), MoveDirection)) * ControlExtent.Z;

				// A generic WorldDynamic control sits first in the route. Exact terrain must ignore it.
				Blocker->SetBoxExtent(ControlExtent, false);
				Blocker->SetCollisionEnabled(ECollisionEnabled::QueryOnly);
				Blocker->SetWorldTransform(FTransform(
					ControlRotation,
					ResponseBoxStart + MoveDirection
						* (MovingSupportCm + ControlSupportCm + 25.0)));
				Blocker->UpdateBounds();
				Blocker->UpdateOverlaps();

				FActorSpawnParameters StaticSpawnParameters;
				StaticSpawnParameters.ObjectFlags |= RF_Transient;
				StaticSpawnParameters.SpawnCollisionHandlingOverride =
					ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
				StaticSpawnParameters.Name = MakeUniqueObjectName(
					TestWorld,
					AActor::StaticClass(),
					TEXT("RED_LiveFighterHullWorldStaticControl"));
				StaticControlActor = TestWorld->SpawnActor<AActor>(
					AActor::StaticClass(), FTransform::Identity, StaticSpawnParameters);
				StaticControl = StaticControlActor
					? NewObject<UBoxComponent>(
						StaticControlActor,
						TEXT("RED_LiveFighterHullWorldStaticControlBox"),
						RF_Transient)
					: nullptr;
				bTranslationResponseValid &= StaticControl != nullptr;
				if (StaticControlActor && StaticControl)
				{
					StaticControlActor->SetRootComponent(StaticControl);
					StaticControlActor->AddInstanceComponent(StaticControl);
					StaticControl->SetBoxExtent(ControlExtent, false);
					StaticControl->SetCollisionEnabled(ECollisionEnabled::QueryAndPhysics);
					StaticControl->SetCollisionObjectType(ECC_WorldStatic);
					StaticControl->SetCollisionResponseToAllChannels(ECR_Block);
					StaticControl->SetGenerateOverlapEvents(false);
					StaticControl->RegisterComponent();
					StaticControl->SetWorldTransform(FTransform(
						ControlRotation,
						ResponseBoxStart + MoveDirection
							* (MovingSupportCm + ControlSupportCm + 50.0)));
					StaticControl->UpdateBounds();
					StaticControl->UpdateOverlaps();
				}

				Fighter->SetActorEnableCollision(true);
				const FCollisionShape ResponseHullShape = LiveHull->GetCollisionShape();
				FCollisionQueryParams ResponseParams(
					SCENE_QUERY_STAT(RedLiveFighterHullTranslationResponse), true);
				ResponseParams.bTraceComplex = true;
				ResponseParams.bFindInitialOverlaps = true;
				ResponseParams.bReturnFaceIndex = true;
				ResponseParams.AddIgnoredActor(Fighter);
				FHitResult DynamicControlHit(1.0f);
				FHitResult ExactResponseHit(1.0f);
				const bool bDynamicControlHit = TestWorld->SweepSingleByObjectType(
					DynamicControlHit,
					ResponseBoxStart,
					ResponseBoxEnd,
					LiveBoxRotation,
					FCollisionObjectQueryParams(ECC_WorldDynamic),
					ResponseHullShape,
					ResponseParams);
				const ERedPlanetTerrainQueryResult ExactResponseResult =
					RedPlanetTerrainQuery::Sweep(
						TestWorld,
						PlanetCenter,
						ResponseBoxStart,
						ResponseBoxEnd,
						LiveBoxRotation,
						ResponseHullShape,
						ExactResponseHit,
						&ResponseTerrainKey);

				// Sweep the actual registered component only through the exact-terrain interval. This
				// exercises RuntimeHullCollision's Vehicle response container rather than bypassing it
				// with a WorldStatic object query. Its response mask ignores the deliberately closer
				// WorldDynamic control and admits the WorldStatic control.
				const FVector NativeSweepEnd = ResponseBoxStart + ResponseDelta
					* FMath::Clamp(ExactResponseHit.Time, 0.0f, 1.0f);
				FComponentQueryParams NativeResponseParams(
					SCENE_QUERY_STAT(RedLiveFighterHullNativeResponse), Fighter);
				NativeResponseParams.bTraceComplex = true;
				NativeResponseParams.bFindInitialOverlaps = true;
				NativeResponseParams.bReturnFaceIndex = true;
				TArray<FHitResult> NativeResponseHits;
				const bool bAnyNativeResponseHit = TestWorld->ComponentSweepMulti(
					NativeResponseHits,
					LiveHull,
					ResponseBoxStart,
					NativeSweepEnd,
					LiveBoxRotation,
					NativeResponseParams);
				const FHitResult* NativeStaticHit = NativeResponseHits.FindByPredicate(
					[](const FHitResult& Candidate)
					{
						return Candidate.IsValidBlockingHit();
					});
				ResponseDynamicDistanceCm = DynamicControlHit.Distance;
				ResponseStaticDistanceCm = NativeStaticHit
					? NativeStaticHit->Distance
					: 0.0f;
				ResponseTerrainDistanceCm = ExactResponseHit.Distance;

				bTranslationResponseValid &= bDynamicControlHit
					&& DynamicControlHit.GetComponent() == Blocker
					&& !DynamicControlHit.bStartPenetrating;
				bTranslationResponseValid &= bAnyNativeResponseHit
					&& NativeStaticHit
					&& NativeStaticHit->GetComponent() == StaticControl
					&& !NativeStaticHit->bStartPenetrating;
				bTranslationResponseValid &=
					ExactResponseResult == ERedPlanetTerrainQueryResult::Hit
					&& ExactResponseHit.bBlockingHit
					&& !ExactResponseHit.bStartPenetrating
					&& ExactResponseHit.GetComponent() != Blocker
					&& ExactResponseHit.GetComponent() != StaticControl;
				bTranslationResponseValid &= NativeStaticHit
					&& DynamicControlHit.Distance < NativeStaticHit->Distance
					&& NativeStaticHit->Distance < ExactResponseHit.Distance;
				bTranslationResponseValid &= ResponseTerrainKey == DirectKey
					&& ExactResponseHit.GetComponent() == DirectHit.GetComponent()
					&& ExactResponseHit.FaceIndex == DirectHit.FaceIndex
					&& FVector::DotProduct(
						ExactResponseHit.Normal, DirectHit.Normal) >= 0.9999f;
				const FHitResult* StaticProbeWinner = NativeStaticHit
					&& NativeStaticHit->Distance <= ExactResponseHit.Distance
					? NativeStaticHit
					: &ExactResponseHit;
				bTranslationResponseValid &= StaticProbeWinner == NativeStaticHit
					&& StaticProbeWinner
					&& StaticProbeWinner->GetComponent() == StaticControl
					&& Fighter->GetActorTransform().Equals(ResponseActorStart, 0.001);

				// Counterfactuals: neither the legacy 260 cm root exact query nor the root's
				// native response reaches either fitted-hull contact over this short route. A later
				// production stop at 50/100 cm therefore proves the movement component consumed the
				// BeginPlay-published live box rather than the root sphere.
				const FCollisionShape ResponseRootShape =
					FCollisionShape::MakeSphere(RootSphere->GetScaledSphereRadius());
				FHitResult RootExactCounterfactualHit(1.0f);
				const ERedPlanetTerrainQueryResult RootExactCounterfactualResult =
					RedPlanetTerrainQuery::Sweep(
						TestWorld,
						PlanetCenter,
						ResponseRootStart,
						ResponseRootStart + ResponseDelta,
						RootSphere->GetComponentQuat(),
						ResponseRootShape,
						RootExactCounterfactualHit);
				bTranslationResponseValid &=
					RootExactCounterfactualResult == ERedPlanetTerrainQueryResult::NoHit
					&& !RootExactCounterfactualHit.bBlockingHit
					&& !RootExactCounterfactualHit.bStartPenetrating;

				FComponentQueryParams RootNativeCounterfactualParams(
					SCENE_QUERY_STAT(RedLiveFighterRootNativeCounterfactual), Fighter);
				FCollisionResponseParams RootNativeCounterfactualResponse;
				RootSphere->InitSweepCollisionParams(
					RootNativeCounterfactualParams,
					RootNativeCounterfactualResponse);
				RootNativeCounterfactualParams.bFindInitialOverlaps = true;
				RootNativeCounterfactualParams.bIgnoreTouches = true;
				TArray<FHitResult> RootNativeCounterfactualHits;
				TestWorld->ComponentSweepMulti(
					RootNativeCounterfactualHits,
					RootSphere,
					ResponseRootStart,
					ResponseRootStart + ResponseDelta,
					RootSphere->GetComponentQuat(),
					RootNativeCounterfactualParams);
				const FHitResult* RootNativeCounterfactualHit =
					RootNativeCounterfactualHits.FindByPredicate([](const FHitResult& Candidate)
					{
						return Candidate.IsValidBlockingHit();
					});
				bTranslationResponseValid &= RootNativeCounterfactualHit == nullptr;

				// Phase one: drive the actual production movement API with the WorldStatic control
				// enabled. The nearer WorldDynamic control is geometrically real but ignored by the
				// fitted Vehicle response container.
				const FVector StaticActorStart = Fighter->GetActorLocation();
				const FVector StaticRootStart = RootSphere->GetComponentLocation();
				const FVector StaticHullStart = LiveHull->GetComponentLocation();
				const FVector StaticWitnessStart = ResponseWitnessMesh
					? ResponseWitnessMesh->GetComponentLocation()
					: FVector::ZeroVector;
				ResponseStaticAcceptedDistanceCm = NativeStaticHit
					? FMath::Max(0.0f, NativeStaticHit->Distance - ContactPullbackCm)
					: 0.0f;
				const FVector StaticAcceptedDelta =
					MoveDirection * ResponseStaticAcceptedDistanceCm;
				ProductionMovement->Velocity = FVector::ZeroVector;
				FHitResult ProductionStaticHit(1.0f);
				ProductionMovement->SafeMoveUpdatedComponent(
					ResponseDelta,
					ActorRotationBeforeResponse,
					true,
					ProductionStaticHit);
				bTranslationResponseValid &= ProductionStaticHit.bBlockingHit
					&& !ProductionStaticHit.bStartPenetrating
					&& ProductionStaticHit.GetComponent() == StaticControl
					&& ProductionStaticHit.GetComponent() != Blocker
					&& ResponseWitnessMesh != nullptr
					&& (Fighter->GetActorLocation() - StaticActorStart).Equals(
						StaticAcceptedDelta, 0.05f)
					&& (RootSphere->GetComponentLocation() - StaticRootStart).Equals(
						StaticAcceptedDelta, 0.05f)
					&& (LiveHull->GetComponentLocation() - StaticHullStart).Equals(
						StaticAcceptedDelta, 0.05f)
					&& (ResponseWitnessMesh->GetComponentLocation() - StaticWitnessStart).Equals(
						StaticAcceptedDelta, 0.05f)
					&& FMath::IsNearlyEqual(
						ProductionStaticHit.Time,
						ResponseStaticAcceptedDistanceCm / ResponseDelta.Size(),
						1.0e-4f)
					&& FMath::IsNearlyEqual(
						ProductionStaticHit.Distance, ResponseStaticDistanceCm, 0.05f)
					&& ProductionStaticHit.Location.Equals(
						ResponseRootStart + MoveDirection * ResponseStaticDistanceCm, 0.05f)
					&& ProductionStaticHit.TraceStart.Equals(ResponseRootStart, 0.05f)
					&& ProductionStaticHit.TraceEnd.Equals(
						ResponseRootStart + ResponseDelta, 0.05f)
					&& ProductionMovement->UpdatedComponent == RootSphere
					&& ProductionMovement->GetTranslationCollisionEnvelope() == LiveHull;

				// Reset the complete actor, not the child envelope, for the exact-terrain phase.
				Fighter->SetActorTransform(
					ResponseActorStart, false, nullptr, ETeleportType::TeleportPhysics);
				RootSphere->UpdateBounds();
				RootSphere->UpdateOverlaps();
				LiveHull->UpdateBounds();
				LiveHull->UpdateOverlaps();

				if (StaticControl)
				{
					StaticControl->SetCollisionEnabled(ECollisionEnabled::NoCollision);
				}
				TArray<FHitResult> TerrainOnlyNativeHits;
				const bool bTerrainOnlyNativeHit = TestWorld->ComponentSweepMulti(
					TerrainOnlyNativeHits,
					LiveHull,
					ResponseBoxStart,
					NativeSweepEnd,
					LiveBoxRotation,
					NativeResponseParams);
				const FHitResult* UnexpectedTerrainOnlyNativeHit =
					TerrainOnlyNativeHits.FindByPredicate([](const FHitResult& Candidate)
					{
						return Candidate.IsValidBlockingHit();
					});
				bTranslationResponseValid &= !bTerrainOnlyNativeHit
					&& UnexpectedTerrainOnlyNativeHit == nullptr;

				bool bRepeatedResponseStable = true;
				for (int32 Repeat = 0; Repeat < 8 && bRepeatedResponseStable; ++Repeat)
				{
					FHitResult RepeatedTerrainHit(1.0f);
					FIntVector RepeatedTerrainKey;
					const ERedPlanetTerrainQueryResult RepeatedTerrainResult =
						RedPlanetTerrainQuery::Sweep(
							TestWorld,
							PlanetCenter,
							ResponseBoxStart,
							ResponseBoxEnd,
							LiveBoxRotation,
							ResponseHullShape,
							RepeatedTerrainHit,
							&RepeatedTerrainKey);
					bRepeatedResponseStable &=
						RepeatedTerrainResult == ERedPlanetTerrainQueryResult::Hit
						&& RepeatedTerrainKey == ResponseTerrainKey
						&& RepeatedTerrainHit.GetComponent()
							== ExactResponseHit.GetComponent()
						&& FMath::IsNearlyEqual(
							RepeatedTerrainHit.Distance,
							ExactResponseHit.Distance,
							0.05f)
						&& RepeatedTerrainHit.FaceIndex == ExactResponseHit.FaceIndex
						&& FVector::DotProduct(
							RepeatedTerrainHit.Normal,
							ExactResponseHit.Normal) >= 0.9999f;
				}
				bTranslationResponseValid &= bRepeatedResponseStable;

				// Phase two: with only the static control disabled, the same production move must
				// ignore the still-present dynamic object and stop the complete actor at exact
				// PlanetGen terrain. SafeMove drives the production override; there is no test-only
				// actor teleport or direct child movement in this acceptance.
				const FVector ActorStartLocation = Fighter->GetActorLocation();
				const FVector RootStartLocation = RootSphere->GetComponentLocation();
				const FVector HullStartLocation = LiveHull->GetComponentLocation();
				const FVector WitnessStartLocation = ResponseWitnessMesh
					? ResponseWitnessMesh->GetComponentLocation()
					: FVector::ZeroVector;
				ResponseAcceptedDistanceCm = FMath::Max(
					0.0f, ExactResponseHit.Distance - ContactPullbackCm);
				const FVector AcceptedDelta =
					MoveDirection * ResponseAcceptedDistanceCm;
				ProductionMovement->Velocity = FVector::ZeroVector;
				FHitResult ProductionTerrainHit(1.0f);
				ProductionMovement->SafeMoveUpdatedComponent(
					ResponseDelta,
					ActorRotationBeforeResponse,
					true,
					ProductionTerrainHit);
				LiveHull->UpdateBounds();
				bTranslationResponseValid &= ProductionTerrainHit.bBlockingHit
					&& !ProductionTerrainHit.bStartPenetrating
					&& ProductionTerrainHit.GetComponent() == ExactResponseHit.GetComponent()
					&& ProductionTerrainHit.GetComponent() != Blocker
					&& ProductionTerrainHit.GetComponent() != StaticControl
					&& ResponseWitnessMesh != nullptr
					&& (Fighter->GetActorLocation() - ActorStartLocation).Equals(
						AcceptedDelta, 0.05f)
					&& (RootSphere->GetComponentLocation() - RootStartLocation).Equals(
						AcceptedDelta, 0.05f)
					&& (LiveHull->GetComponentLocation() - HullStartLocation).Equals(
						AcceptedDelta, 0.05f)
					&& (ResponseWitnessMesh->GetComponentLocation() - WitnessStartLocation).Equals(
						AcceptedDelta, 0.05f)
					&& FMath::IsNearlyEqual(
						ProductionTerrainHit.Time,
						ResponseAcceptedDistanceCm / ResponseDelta.Size(),
						1.0e-4f)
					&& FMath::IsNearlyEqual(
						ProductionTerrainHit.Distance, ResponseTerrainDistanceCm, 0.05f)
					&& ProductionTerrainHit.Location.Equals(
						ResponseRootStart + MoveDirection * ResponseTerrainDistanceCm, 0.05f)
					&& ProductionTerrainHit.ImpactPoint.Equals(
						ExactResponseHit.ImpactPoint, 0.05f)
					&& ProductionTerrainHit.TraceStart.Equals(ResponseRootStart, 0.05f)
					&& ProductionTerrainHit.TraceEnd.Equals(
						ResponseRootStart + ResponseDelta, 0.05f)
					&& Fighter->GetActorQuat().Equals(
						ActorRotationBeforeResponse, 1.0e-6f)
					&& RootSphere->GetComponentQuat().Equals(
						ActorRotationBeforeResponse, 1.0e-6f)
					&& LiveHull->GetComponentQuat().Equals(
						LiveBoxRotation, 1.0e-6f)
					&& LiveHull->GetRelativeLocation().Equals(
						RelativeCenterBeforeResponse, 0.001f)
					&& LiveHull->GetRelativeRotation().Quaternion().Equals(
						RelativeRotationBeforeResponse, 1.0e-6f)
					&& LiveHull->GetScaledBoxExtent().Equals(
						ExtentBeforeResponse, 0.001f)
					&& Fighter->GetActorScale3D().Equals(
						ResponseActorStart.GetScale3D(), 1.0e-6f)
					&& ProductionMovement->UpdatedComponent == RootSphere
					&& ProductionMovement->GetTranslationCollisionEnvelope() == LiveHull;
				bTranslationResponseValid &= ResponseAcceptedDistanceCm >= 95.0f
					&& ResponseAcceptedDistanceCm
						< ApproachDistanceCm + OvertravelDistanceCm;

				FHitResult FinalClearHit(1.0f);
				const ERedPlanetTerrainQueryResult FinalClearResult =
					RedPlanetTerrainQuery::Sweep(
						TestWorld,
						PlanetCenter,
						LiveHull->GetComponentLocation(),
						LiveHull->GetComponentLocation(),
						LiveHull->GetComponentQuat(),
						ResponseHullShape,
						FinalClearHit);
				bTranslationResponseValid &=
					FinalClearResult == ERedPlanetTerrainQueryResult::NoHit
					&& !FinalClearHit.bBlockingHit
					&& !FinalClearHit.bStartPenetrating;

				FHitResult FollowupTerrainHit(1.0f);
				FIntVector FollowupTerrainKey;
				const ERedPlanetTerrainQueryResult FollowupTerrainResult =
					RedPlanetTerrainQuery::Sweep(
						TestWorld,
						PlanetCenter,
						LiveHull->GetComponentLocation(),
						LiveHull->GetComponentLocation() + MoveDirection * 4.0f,
						LiveHull->GetComponentQuat(),
						ResponseHullShape,
						FollowupTerrainHit,
						&FollowupTerrainKey);
				bTranslationResponseValid &=
					FollowupTerrainResult == ERedPlanetTerrainQueryResult::Hit
					&& FollowupTerrainHit.bBlockingHit
					&& !FollowupTerrainHit.bStartPenetrating
					&& FollowupTerrainHit.GetComponent() == ExactResponseHit.GetComponent()
					&& FollowupTerrainKey == ResponseTerrainKey
					&& FMath::IsNearlyEqual(
						FollowupTerrainHit.Distance, ContactPullbackCm, 0.05f);
			}

			if (StaticControl)
			{
				StaticControl->SetCollisionEnabled(ECollisionEnabled::NoCollision);
			}
			if (StaticControlActor)
			{
				StaticControlActor->Destroy();
			}
			Blocker->SetBoxExtent(SavedDynamicExtent, false);
			Blocker->SetCollisionEnabled(SavedDynamicCollision);
			Blocker->SetWorldTransform(SavedDynamicTransform);
			Blocker->UpdateBounds();
			Blocker->UpdateOverlaps();
			bValid &= Test->TestTrue(
				TEXT("Production SafeMove consumes the live fitted hull for deterministic static and exact-terrain translation"),
				bTranslationResponseValid);
			if (bTranslationResponseValid)
			{
				UE_LOG(LogTemp, Display,
					TEXT("RED_FUSED_ACTIVE_TERRAIN_PRODUCTION_FIGHTER_HULL_TRANSLATION_PASS dynamic_distance_cm=%.6f static_contact_cm=%.6f static_move_cm=%.6f terrain_contact_cm=%.6f terrain_move_cm=%.6f key=(%d,%d,%d) pullback_cm=2.0 root_counterfactual=clear iterations=2 repeats=8"),
					ResponseDynamicDistanceCm,
					ResponseStaticDistanceCm,
					ResponseStaticAcceptedDistanceCm,
					ResponseTerrainDistanceCm,
					ResponseAcceptedDistanceCm,
					ResponseTerrainKey.X,
					ResponseTerrainKey.Y,
					ResponseTerrainKey.Z);
			}

			// One production SafeMove must recover the BeginPlay-published fitted box from a
			// deterministic exact-terrain overlap, then retain the complete fixed-rotation request.
			// The root sphere is deliberately exact-clear so it cannot produce a false pass.
			bool bInitialOverlapResponseValid = bTranslationResponseValid
				&& ResponseWitnessMesh != nullptr;
			constexpr float OverlapEmbedCm = 50.0f;
			constexpr float OverlapPullbackCm = 2.0f;
			constexpr float OverlapOutwardRequestCm = 25.0f;
			constexpr float OverlapTangentRequestCm = 100.0f;
			constexpr int32 OverlapRepeatCount = 8;
			float OverlapDepthCm = 0.0f;
			float OverlapAdjustmentCm = 0.0f;
			float ObservedOverlapOutwardCm = 0.0f;
			float ObservedOverlapTangentCm = 0.0f;
			float OverlapEndpointErrorCm = 0.0f;
			FIntVector InitialOverlapKey(INDEX_NONE, INDEX_NONE, INDEX_NONE);

			const FVector OverlapRadialOut =
				(DirectHit.ImpactPoint - PlanetCenter).GetSafeNormal();
			const FVector RootToBoxOffset = RootStart - LiveBoxStart;
			const FVector EmbeddedBoxCenter =
				DirectHit.Location - OverlapRadialOut * OverlapEmbedCm;
			const FVector EmbeddedRootStart =
				EmbeddedBoxCenter + RootToBoxOffset;
			Fighter->SetActorLocationAndRotation(
				EmbeddedRootStart,
				FighterRotation,
				false,
				nullptr,
				ETeleportType::TeleportPhysics);
			RootSphere->UpdateBounds();
			RootSphere->UpdateOverlaps();
			LiveHull->UpdateBounds();
			LiveHull->UpdateOverlaps();
			ProductionMovement->Velocity = FVector::ZeroVector;

			FHitResult InitialOverlapHit(1.0f);
			const ERedPlanetTerrainQueryResult InitialOverlapResult =
				RedPlanetTerrainQuery::Sweep(
					TestWorld,
					PlanetCenter,
					EmbeddedBoxCenter,
					EmbeddedBoxCenter,
					LiveBoxRotation,
					LiveBoxShape,
					InitialOverlapHit,
					&InitialOverlapKey);
			OverlapDepthCm = InitialOverlapHit.PenetrationDepth;
			const bool bFiniteInitialNormal =
				FMath::IsFinite(InitialOverlapHit.Normal.X)
				&& FMath::IsFinite(InitialOverlapHit.Normal.Y)
				&& FMath::IsFinite(InitialOverlapHit.Normal.Z)
				&& !InitialOverlapHit.Normal.IsNearlyZero();
			const FVector OverlapNormal =
				bFiniteInitialNormal
					? InitialOverlapHit.Normal.GetSafeNormal()
					: OverlapRadialOut;
			bInitialOverlapResponseValid &=
				InitialOverlapResult == ERedPlanetTerrainQueryResult::Hit
				&& InitialOverlapHit.bBlockingHit
				&& InitialOverlapHit.bStartPenetrating
				&& FMath::IsNearlyZero(InitialOverlapHit.Time, 1.0e-6f)
				&& InitialOverlapHit.Distance <= 0.01f
				&& InitialOverlapHit.GetComponent() == DirectHit.GetComponent()
				&& InitialOverlapKey == DirectKey
				&& FMath::IsFinite(InitialOverlapHit.PenetrationDepth)
				&& InitialOverlapHit.PenetrationDepth >= 40.0f
				&& InitialOverlapHit.PenetrationDepth <= 60.0f
				&& bFiniteInitialNormal
				&& FVector::DotProduct(OverlapNormal, OverlapRadialOut) > 0.9f;

			FCollisionQueryParams RawOverlapParams(
				SCENE_QUERY_STAT(RedLiveFighterHullInitialOverlapRaw), true);
			RawOverlapParams.bTraceComplex = true;
			RawOverlapParams.bFindInitialOverlaps = true;
			RawOverlapParams.bReturnFaceIndex = true;
			RawOverlapParams.AddIgnoredActor(Fighter);
			RawOverlapParams.AddIgnoredComponent(Blocker);
			TArray<FHitResult> RawOverlapHits;
			TestWorld->SweepMultiByObjectType(
				RawOverlapHits,
				EmbeddedBoxCenter,
				EmbeddedBoxCenter,
				LiveBoxRotation,
				FCollisionObjectQueryParams(ECC_WorldDynamic),
				LiveBoxShape,
				RawOverlapParams);
			const FHitResult* RawInitialOverlapHit =
				RawOverlapHits.FindByPredicate(
					[&InitialOverlapHit](const FHitResult& Candidate)
					{
						return Candidate.bBlockingHit
							&& Candidate.bStartPenetrating
							&& Candidate.GetComponent()
								== InitialOverlapHit.GetComponent();
					});
			bInitialOverlapResponseValid &= RawInitialOverlapHit
				&& FMath::IsNearlyEqual(
					RawInitialOverlapHit->PenetrationDepth,
					InitialOverlapHit.PenetrationDepth,
					0.01f)
				&& FVector::DotProduct(
					RawInitialOverlapHit->Normal.GetSafeNormal(), OverlapNormal) > 0.9999f;

			bool bRepeatedOverlapStable = bInitialOverlapResponseValid;
			for (int32 Repeat = 0;
				Repeat < OverlapRepeatCount && bRepeatedOverlapStable;
				++Repeat)
			{
				FHitResult RepeatedOverlapHit(1.0f);
				FIntVector RepeatedOverlapKey(INDEX_NONE, INDEX_NONE, INDEX_NONE);
				const ERedPlanetTerrainQueryResult RepeatedOverlapResult =
					RedPlanetTerrainQuery::Sweep(
						TestWorld,
						PlanetCenter,
						EmbeddedBoxCenter,
						EmbeddedBoxCenter,
						LiveBoxRotation,
						LiveBoxShape,
						RepeatedOverlapHit,
						&RepeatedOverlapKey);
				bRepeatedOverlapStable &=
					RepeatedOverlapResult == ERedPlanetTerrainQueryResult::Hit
					&& RepeatedOverlapHit.bBlockingHit
					&& RepeatedOverlapHit.bStartPenetrating
					&& FMath::IsNearlyZero(RepeatedOverlapHit.Time, 1.0e-6f)
					&& RepeatedOverlapHit.Distance <= 0.01f
					&& RepeatedOverlapKey == InitialOverlapKey
					&& RepeatedOverlapHit.GetComponent()
						== InitialOverlapHit.GetComponent()
					&& RepeatedOverlapHit.FaceIndex == InitialOverlapHit.FaceIndex
					&& FMath::IsNearlyEqual(
						RepeatedOverlapHit.PenetrationDepth,
						InitialOverlapHit.PenetrationDepth,
						0.01f)
					&& FVector::Dist(
						RepeatedOverlapHit.Location,
						InitialOverlapHit.Location) <= 0.1f
					&& FVector::Dist(
						RepeatedOverlapHit.ImpactPoint,
						InitialOverlapHit.ImpactPoint) <= 0.1f
					&& FVector::DotProduct(
						RepeatedOverlapHit.Normal.GetSafeNormal(),
						OverlapNormal) > 0.9999f;
			}
			bInitialOverlapResponseValid &= bRepeatedOverlapStable;

			const FVector RequestedEngineAdjustment =
				ProductionMovement->GetPenetrationAdjustment(InitialOverlapHit);
			const FVector ExpectedOverlapAdjustment = OverlapNormal
				* (InitialOverlapHit.PenetrationDepth + OverlapPullbackCm);
			OverlapAdjustmentCm = ExpectedOverlapAdjustment.Size();
			bInitialOverlapResponseValid &=
				!RequestedEngineAdjustment.ContainsNaN()
				&& !RequestedEngineAdjustment.IsNearlyZero()
				&& FVector::DotProduct(
					RequestedEngineAdjustment.GetSafeNormal(), OverlapNormal) > 0.999f
				&& RequestedEngineAdjustment.Size()
					>= InitialOverlapHit.PenetrationDepth
				&& RequestedEngineAdjustment.Size()
					<= InitialOverlapHit.PenetrationDepth + 1.0f
				&& !ExpectedOverlapAdjustment.ContainsNaN()
				&& ExpectedOverlapAdjustment.Size()
					<= LiveBoxShape.GetExtent().GetMax() * 2.0f + OverlapPullbackCm;

			const FVector TangentReference =
				FMath::Abs(FVector::DotProduct(
					OverlapNormal, FVector::UpVector)) < 0.9f
					? FVector::UpVector
					: FVector::ForwardVector;
			const FVector BaseTangent = FVector::CrossProduct(
				OverlapNormal, TangentReference).GetSafeNormal();
			FVector OverlapTangent = BaseTangent;
			FVector OverlapRequestedDelta =
				OverlapNormal * OverlapOutwardRequestCm
				+ OverlapTangent * OverlapTangentRequestCm;
			const FVector CorrectedBoxStart =
				EmbeddedBoxCenter + ExpectedOverlapAdjustment;
			bool bFoundClearTangent = false;
			for (const float TangentSign : {1.0f, -1.0f})
			{
				const FVector CandidateTangent = BaseTangent * TangentSign;
				const FVector CandidateRequest =
					OverlapNormal * OverlapOutwardRequestCm
					+ CandidateTangent * OverlapTangentRequestCm;
				FHitResult CandidateRouteHit(1.0f);
				const ERedPlanetTerrainQueryResult CandidateRouteResult =
					RedPlanetTerrainQuery::Sweep(
						TestWorld,
						PlanetCenter,
						CorrectedBoxStart,
						CorrectedBoxStart + CandidateRequest,
						LiveBoxRotation,
						LiveBoxShape,
						CandidateRouteHit);
				if (CandidateRouteResult == ERedPlanetTerrainQueryResult::NoHit
					&& !CandidateRouteHit.bBlockingHit
					&& !CandidateRouteHit.bStartPenetrating)
				{
					OverlapTangent = CandidateTangent;
					OverlapRequestedDelta = CandidateRequest;
					bFoundClearTangent = true;
					break;
				}
			}
			bInitialOverlapResponseValid &= bFoundClearTangent
				&& !OverlapTangent.IsNearlyZero()
				&& FMath::Abs(FVector::DotProduct(
					OverlapTangent, OverlapNormal)) <= 0.001f;

			FHitResult RootOverlapCounterfactualHit(1.0f);
			const ERedPlanetTerrainQueryResult RootOverlapCounterfactualResult =
				RedPlanetTerrainQuery::Sweep(
					TestWorld,
					PlanetCenter,
					EmbeddedRootStart,
					EmbeddedRootStart,
					FighterRotation,
					RootShape,
					RootOverlapCounterfactualHit);
			FHitResult RootRouteCounterfactualHit(1.0f);
			const ERedPlanetTerrainQueryResult RootRouteCounterfactualResult =
				RedPlanetTerrainQuery::Sweep(
					TestWorld,
					PlanetCenter,
					EmbeddedRootStart,
					EmbeddedRootStart + OverlapRequestedDelta,
					FighterRotation,
					RootShape,
					RootRouteCounterfactualHit);
			bInitialOverlapResponseValid &=
				RootOverlapCounterfactualResult == ERedPlanetTerrainQueryResult::NoHit
				&& !RootOverlapCounterfactualHit.bBlockingHit
				&& !RootOverlapCounterfactualHit.bStartPenetrating
				&& RootRouteCounterfactualResult == ERedPlanetTerrainQueryResult::NoHit
				&& !RootRouteCounterfactualHit.bBlockingHit
				&& !RootRouteCounterfactualHit.bStartPenetrating;

			FComponentQueryParams OverlapNativeParams(
				SCENE_QUERY_STAT(RedLiveFighterHullInitialOverlapNative), Fighter);
			FCollisionResponseParams OverlapNativeResponse;
			LiveHull->InitSweepCollisionParams(
				OverlapNativeParams, OverlapNativeResponse);
			OverlapNativeParams.bFindInitialOverlaps = true;
			OverlapNativeParams.bIgnoreTouches = true;
			TArray<FHitResult> NativeCorrectedRouteHits;
			TestWorld->ComponentSweepMulti(
				NativeCorrectedRouteHits,
				LiveHull,
				CorrectedBoxStart,
				CorrectedBoxStart + OverlapRequestedDelta,
				LiveBoxRotation,
				OverlapNativeParams);
			const FHitResult* NativeCorrectedRouteHit =
				NativeCorrectedRouteHits.FindByPredicate(
					[](const FHitResult& Candidate)
					{
						return Candidate.bBlockingHit;
					});
			bInitialOverlapResponseValid &= NativeCorrectedRouteHit == nullptr;

			bValid &= Test->TestTrue(
				TEXT("Production fitted-hull initial-overlap fixture is deterministic and root-clear"),
				bInitialOverlapResponseValid);

			const FVector OverlapActorStart = Fighter->GetActorLocation();
			const FVector OverlapRootStart = RootSphere->GetComponentLocation();
			const FVector OverlapHullStart = LiveHull->GetComponentLocation();
			const FVector OverlapWitnessStart = ResponseWitnessMesh
				? ResponseWitnessMesh->GetComponentLocation()
				: FVector::ZeroVector;
			const FQuat OverlapActorRotation = Fighter->GetActorQuat();
			const FQuat OverlapRootRotation = RootSphere->GetComponentQuat();
			const FQuat OverlapHullRotation = LiveHull->GetComponentQuat();
			const FQuat OverlapHullRelativeRotation =
				LiveHull->GetRelativeRotation().Quaternion();
			const FQuat OverlapWitnessRotation = ResponseWitnessMesh
				? ResponseWitnessMesh->GetComponentQuat()
				: FQuat::Identity;
			FHitResult ProductionOverlapResolvedHit(1.0f);
			const bool bProductionOverlapResolved =
				ProductionMovement->SafeMoveUpdatedComponent(
					OverlapRequestedDelta,
					OverlapRootRotation,
					true,
					ProductionOverlapResolvedHit);
			LiveHull->UpdateBounds();
			LiveHull->UpdateOverlaps();
			const FVector ActualOverlapDelta =
				RootSphere->GetComponentLocation() - OverlapRootStart;
			const FVector ObservedOverlapAdjustment =
				ActualOverlapDelta - OverlapRequestedDelta;
			const FVector ExpectedFinalRoot = OverlapRootStart
				+ ExpectedOverlapAdjustment + OverlapRequestedDelta;
			ObservedOverlapOutwardCm = FVector::DotProduct(
				ActualOverlapDelta, OverlapNormal);
			ObservedOverlapTangentCm = FVector::DotProduct(
				ActualOverlapDelta, OverlapTangent);
			OverlapEndpointErrorCm = FVector::Dist(
				RootSphere->GetComponentLocation(), ExpectedFinalRoot);

			bInitialOverlapResponseValid &= bProductionOverlapResolved
				&& !ProductionOverlapResolvedHit.bBlockingHit
				&& !ProductionOverlapResolvedHit.bStartPenetrating
				&& FMath::IsNearlyEqual(
					ProductionOverlapResolvedHit.Time, 1.0f, 1.0e-6f)
				&& ObservedOverlapAdjustment.Equals(
					ExpectedOverlapAdjustment, 0.05f)
				&& RootSphere->GetComponentLocation().Equals(
					ExpectedFinalRoot, 0.05f)
				&& (Fighter->GetActorLocation() - OverlapActorStart).Equals(
					ActualOverlapDelta, 0.05f)
				&& (LiveHull->GetComponentLocation() - OverlapHullStart).Equals(
					ActualOverlapDelta, 0.05f)
				&& ResponseWitnessMesh
				&& (ResponseWitnessMesh->GetComponentLocation()
					- OverlapWitnessStart).Equals(ActualOverlapDelta, 0.05f)
				&& Fighter->GetActorQuat().Equals(OverlapActorRotation, 1.0e-6f)
				&& RootSphere->GetComponentQuat().Equals(OverlapRootRotation, 1.0e-6f)
				&& LiveHull->GetComponentQuat().Equals(OverlapHullRotation, 1.0e-6f)
				&& LiveHull->GetRelativeRotation().Quaternion().Equals(
					OverlapHullRelativeRotation, 1.0e-6f)
				&& ResponseWitnessMesh->GetComponentQuat().Equals(
					OverlapWitnessRotation, 1.0e-6f)
				&& LiveHull->GetRelativeLocation().Equals(LiveRelativeCenter, 0.001f)
				&& LiveHull->GetScaledBoxExtent().Equals(LiveScaledHalfExtent, 0.001f)
				&& Fighter->GetActorScale3D().Equals(
					SpawnedActorTransform.GetScale3D(), 1.0e-6f)
				&& ProductionMovement->UpdatedComponent == RootSphere
				&& ProductionMovement->GetTranslationCollisionEnvelope() == LiveHull
				&& FMath::IsNearlyEqual(
					ObservedOverlapOutwardCm,
					OverlapAdjustmentCm + OverlapOutwardRequestCm,
					0.1f)
				&& FMath::IsNearlyEqual(
					ObservedOverlapTangentCm,
					OverlapTangentRequestCm,
					0.1f)
				&& OverlapEndpointErrorCm <= 0.05f
				&& ActualOverlapDelta.Size() < 250.0f;

			FHitResult FinalOverlapExactHit(1.0f);
			const ERedPlanetTerrainQueryResult FinalOverlapExactResult =
				RedPlanetTerrainQuery::Sweep(
					TestWorld,
					PlanetCenter,
					LiveHull->GetComponentLocation(),
					LiveHull->GetComponentLocation(),
					LiveHull->GetComponentQuat(),
					LiveBoxShape,
					FinalOverlapExactHit);
			TArray<FOverlapResult> FinalOverlapNativeHits;
			TestWorld->ComponentOverlapMulti(
				FinalOverlapNativeHits,
				LiveHull,
				LiveHull->GetComponentLocation(),
				LiveHull->GetComponentQuat(),
				OverlapNativeParams);
			const FOverlapResult* FinalOverlapNativeHit =
				FinalOverlapNativeHits.FindByPredicate(
					[](const FOverlapResult& Candidate)
					{
						return Candidate.bBlockingHit;
					});
			bInitialOverlapResponseValid &=
				FinalOverlapExactResult == ERedPlanetTerrainQueryResult::NoHit
				&& !FinalOverlapExactHit.bBlockingHit
				&& !FinalOverlapExactHit.bStartPenetrating
				&& FinalOverlapNativeHit == nullptr
				&& FighterPackage->IsDirty() == bExpectedPackageDirty;

			bValid &= Test->TestTrue(
				TEXT("One production SafeMove resolves the fitted hull and preserves its complete fixed-rotation request"),
				bInitialOverlapResponseValid);
			if (bInitialOverlapResponseValid)
			{
				UE_LOG(LogTemp, Display,
					TEXT("RED_FUSED_ACTIVE_TERRAIN_PRODUCTION_FIGHTER_HULL_INITIAL_OVERLAP_PASS embed_cm=%.3f depth_cm=%.6f adjustment_cm=%.6f request_out_cm=%.3f request_tangent_cm=%.3f observed_out_cm=%.6f observed_tangent_cm=%.6f endpoint_error_cm=%.6f key=(%d,%d,%d) pieces=1 root_counterfactual=clear iterations=1 repeats=%d final=clear"),
					OverlapEmbedCm,
					OverlapDepthCm,
					OverlapAdjustmentCm,
					OverlapOutwardRequestCm,
					OverlapTangentRequestCm,
					ObservedOverlapOutwardCm,
					ObservedOverlapTangentCm,
					OverlapEndpointErrorCm,
					InitialOverlapKey.X,
					InitialOverlapKey.Y,
					InitialOverlapKey.Z,
					OverlapRepeatCount);
			}

			// Bounded angular corridor gate: the production sphere root and its off-centre
			// fitted box request one 30 cm translation plus a 6 degree local roll. A tiny
			// WorldStatic control touches only a wing-corner mid-arc pose; start/end hull
			// poses and the complete root route remain clear. An earlier WorldDynamic control
			// is geometrically real but must remain ignored by the live Vehicle response mask.
			bool bAngularCorridorValid = bInitialOverlapResponseValid
				&& ResponseWitnessMesh != nullptr;
			constexpr float AngularTranslationCm = 30.0f;
			constexpr float AngularRotationDegrees = 6.0f;
			constexpr int32 AngularBlockedRepeats = 8;
			constexpr int32 AngularClearRepeats = 8;
			const FTransform AngularSavedDynamicTransform =
				Blocker->GetComponentTransform();
			const FVector AngularSavedDynamicExtent = Blocker->GetUnscaledBoxExtent();
			const ECollisionEnabled::Type AngularSavedDynamicCollision =
				Blocker->GetCollisionEnabled();
			const FVector AngularStartRoot = DirectHit.ImpactPoint
				+ OverlapRadialOut * 25000.0f;
			const FQuat AngularStartRotation = FighterRotation;
			const FQuat AngularTargetRotation = (
				AngularStartRotation
					* FQuat(
						FVector::XAxisVector,
						FMath::DegreesToRadians(AngularRotationDegrees))).GetNormalized();
			const FVector AngularDelta = OverlapTangent * AngularTranslationCm;
			Fighter->SetActorLocationAndRotation(
				AngularStartRoot,
				AngularStartRotation,
				false,
				nullptr,
				ETeleportType::TeleportPhysics);
			Fighter->SetActorEnableCollision(true);
			RootSphere->UpdateBounds();
			RootSphere->UpdateOverlaps();
			LiveHull->UpdateBounds();
			LiveHull->UpdateOverlaps();
			ProductionMovement->Velocity = FVector::ZeroVector;

			const FVector AngularRootToHullLocal =
				AngularStartRotation.UnrotateVector(
					LiveHull->GetComponentLocation() - AngularStartRoot);
			const FQuat AngularHullRelativeRotation = (
				AngularStartRotation.Inverse()
					* LiveHull->GetComponentQuat()).GetNormalized();
			const FVector AngularRootToWitnessLocal =
				AngularStartRotation.UnrotateVector(
					ResponseWitnessMesh->GetComponentLocation() - AngularStartRoot);
			const FQuat AngularWitnessRelativeRotation = (
				AngularStartRotation.Inverse()
					* ResponseWitnessMesh->GetComponentQuat()).GetNormalized();
			const FVector AngularHullRelativeCenterBefore =
				LiveHull->GetRelativeLocation();
			const FQuat AngularHullRelativeRotationBefore =
				LiveHull->GetRelativeRotation().Quaternion();
			const FVector AngularHullExtentBefore = LiveHull->GetScaledBoxExtent();
			const FVector AngularActorScaleBefore = Fighter->GetActorScale3D();
			const FName AngularHullProfileBefore = LiveHull->GetCollisionProfileName();
			const FVector AngularWitnessScaleBefore =
				ResponseWitnessMesh->GetComponentScale();

			auto AngularRootRotationAt =
				[AngularStartRotation, AngularTargetRotation](const float Alpha)
				{
					return FQuat::Slerp(
						AngularStartRotation,
						AngularTargetRotation,
						Alpha).GetNormalized();
				};
			auto AngularHullLocationAt =
				[AngularStartRoot,
					AngularDelta,
					AngularRootToHullLocal,
					&AngularRootRotationAt](const float Alpha)
				{
					const FQuat RootRotationAt = AngularRootRotationAt(Alpha);
					return AngularStartRoot + AngularDelta * Alpha
						+ RootRotationAt.RotateVector(AngularRootToHullLocal);
				};
			auto AngularHullRotationAt =
				[AngularHullRelativeRotation,
					&AngularRootRotationAt](const float Alpha)
				{
					return (AngularRootRotationAt(Alpha)
						* AngularHullRelativeRotation).GetNormalized();
				};

			int32 AngularCornerIndex = 0;
			double AngularCornerClearanceCm = -1.0;
			FVector AngularMidCorner = FVector::ZeroVector;
			for (int32 CornerIndex = 0; CornerIndex < 8; ++CornerIndex)
			{
				const FVector LocalScaledCorner(
					(CornerIndex & 1)
						? LiveScaledHalfExtent.X : -LiveScaledHalfExtent.X,
					(CornerIndex & 2)
						? LiveScaledHalfExtent.Y : -LiveScaledHalfExtent.Y,
					(CornerIndex & 4)
						? LiveScaledHalfExtent.Z : -LiveScaledHalfExtent.Z);
				const FVector StartCorner = AngularHullLocationAt(0.0f)
					+ AngularHullRotationAt(0.0f).RotateVector(LocalScaledCorner);
				const FVector MidCorner = AngularHullLocationAt(0.5f)
					+ AngularHullRotationAt(0.5f).RotateVector(LocalScaledCorner);
				const FVector EndCorner = AngularHullLocationAt(1.0f)
					+ AngularHullRotationAt(1.0f).RotateVector(LocalScaledCorner);
				const double ClearanceCm = FMath::Min(
					FVector::Distance(MidCorner, StartCorner),
					FVector::Distance(MidCorner, EndCorner));
				if (ClearanceCm > AngularCornerClearanceCm)
				{
					AngularCornerIndex = CornerIndex;
					AngularCornerClearanceCm = ClearanceCm;
					AngularMidCorner = MidCorner;
				}
			}
			const FVector AngularLocalCorner(
				(AngularCornerIndex & 1)
					? LiveScaledHalfExtent.X : -LiveScaledHalfExtent.X,
				(AngularCornerIndex & 2)
					? LiveScaledHalfExtent.Y : -LiveScaledHalfExtent.Y,
				(AngularCornerIndex & 4)
					? LiveScaledHalfExtent.Z : -LiveScaledHalfExtent.Z);
			const FVector AngularMidOutward =
				AngularHullRotationAt(0.5f).RotateVector(
					AngularLocalCorner).GetSafeNormal();
			const FVector AngularStaticCenter =
				AngularMidCorner - AngularMidOutward;
			const float AngularDynamicAlpha = 1.0f / 6.0f;
			const FVector AngularDynamicCorner =
				AngularHullLocationAt(AngularDynamicAlpha)
				+ AngularHullRotationAt(AngularDynamicAlpha).RotateVector(
					AngularLocalCorner);
			const FVector AngularDynamicOutward =
				AngularHullRotationAt(AngularDynamicAlpha).RotateVector(
					AngularLocalCorner).GetSafeNormal();
			const FVector AngularDynamicCenter =
				AngularDynamicCorner - AngularDynamicOutward;

			FActorSpawnParameters AngularStaticSpawnParameters;
			AngularStaticSpawnParameters.ObjectFlags |= RF_Transient;
			AngularStaticSpawnParameters.SpawnCollisionHandlingOverride =
				ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
			AngularStaticSpawnParameters.Name = MakeUniqueObjectName(
				TestWorld,
				AActor::StaticClass(),
				TEXT("RED_LiveFighterHullAngularWorldStaticControl"));
			AActor* AngularStaticActor = TestWorld->SpawnActor<AActor>(
				AActor::StaticClass(),
				FTransform::Identity,
				AngularStaticSpawnParameters);
			UBoxComponent* AngularStaticControl = AngularStaticActor
				? NewObject<UBoxComponent>(
					AngularStaticActor,
					TEXT("RED_LiveFighterHullAngularWorldStaticControlBox"),
					RF_Transient)
				: nullptr;
			bAngularCorridorValid &= AngularStaticControl != nullptr
				&& !AngularMidOutward.IsNearlyZero()
				&& AngularCornerClearanceCm > 10.0;
			if (AngularStaticActor && AngularStaticControl)
			{
				AngularStaticActor->SetRootComponent(AngularStaticControl);
				AngularStaticActor->AddInstanceComponent(AngularStaticControl);
				AngularStaticControl->SetBoxExtent(FVector(3.0f), false);
				AngularStaticControl->SetCollisionEnabled(
					ECollisionEnabled::QueryAndPhysics);
				AngularStaticControl->SetCollisionObjectType(ECC_WorldStatic);
				AngularStaticControl->SetCollisionResponseToAllChannels(ECR_Block);
				AngularStaticControl->SetGenerateOverlapEvents(false);
				AngularStaticControl->RegisterComponent();
				AngularStaticControl->SetWorldLocation(
					AngularStaticCenter,
					false,
					nullptr,
					ETeleportType::TeleportPhysics);
				AngularStaticControl->UpdateBounds();
				AngularStaticControl->UpdateOverlaps();
			}

			Blocker->SetBoxExtent(FVector(3.0f), false);
			Blocker->SetCollisionEnabled(ECollisionEnabled::QueryOnly);
			Blocker->SetWorldLocation(
				AngularDynamicCenter,
				false,
				nullptr,
				ETeleportType::TeleportPhysics);
			Blocker->UpdateBounds();
			Blocker->UpdateOverlaps();

			FComponentQueryParams AngularHullParams(
				SCENE_QUERY_STAT(RedLiveFighterHullAngularFixture), Fighter);
			FCollisionResponseParams AngularHullResponses;
			LiveHull->InitSweepCollisionParams(
				AngularHullParams, AngularHullResponses);
			AngularHullParams.bFindInitialOverlaps = true;
			AngularHullParams.bIgnoreTouches = true;
			AngularHullParams.bReturnFaceIndex = true;
			const bool bAngularStartBlocked =
				TestWorld->OverlapBlockingTestByChannel(
					AngularHullLocationAt(0.0f),
					AngularHullRotationAt(0.0f),
					LiveHull->GetCollisionObjectType(),
					LiveBoxShape,
					AngularHullParams,
					AngularHullResponses);
			const bool bAngularMidBlocked =
				TestWorld->OverlapBlockingTestByChannel(
					AngularHullLocationAt(0.5f),
					AngularHullRotationAt(0.5f),
					LiveHull->GetCollisionObjectType(),
					LiveBoxShape,
					AngularHullParams,
					AngularHullResponses);
			const bool bAngularEndBlocked =
				TestWorld->OverlapBlockingTestByChannel(
					AngularHullLocationAt(1.0f),
					AngularHullRotationAt(1.0f),
					LiveHull->GetCollisionObjectType(),
					LiveBoxShape,
					AngularHullParams,
					AngularHullResponses);

			FCollisionQueryParams AngularRawDynamicParams(
				SCENE_QUERY_STAT(RedLiveFighterHullAngularDynamicControl), true);
			AngularRawDynamicParams.AddIgnoredActor(Fighter);
			const bool bAngularDynamicGeometricallyPresent =
				TestWorld->OverlapAnyTestByObjectType(
					AngularHullLocationAt(AngularDynamicAlpha),
					AngularHullRotationAt(AngularDynamicAlpha),
					FCollisionObjectQueryParams(ECC_WorldDynamic),
					LiveBoxShape,
					AngularRawDynamicParams);

			FComponentQueryParams AngularRootParams(
				SCENE_QUERY_STAT(RedLiveFighterHullAngularRootRoute), Fighter);
			FCollisionResponseParams AngularRootResponses;
			RootSphere->InitSweepCollisionParams(
				AngularRootParams, AngularRootResponses);
			AngularRootParams.bFindInitialOverlaps = true;
			AngularRootParams.bIgnoreTouches = true;
			TArray<FHitResult> AngularRootRouteHits;
			TestWorld->ComponentSweepMulti(
				AngularRootRouteHits,
				RootSphere,
				AngularStartRoot,
				AngularStartRoot + AngularDelta,
				AngularStartRotation,
				AngularRootParams);
			const FHitResult* AngularRootRouteHit =
				AngularRootRouteHits.FindByPredicate([](const FHitResult& Candidate)
				{
					return Candidate.bBlockingHit;
				});

			bool bAngularExactClear = true;
			for (const float Alpha : {0.0f, 0.5f, 1.0f})
			{
				FHitResult AngularExactHit(1.0f);
				const ERedPlanetTerrainQueryResult AngularExactResult =
					RedPlanetTerrainQuery::Sweep(
						TestWorld,
						PlanetCenter,
						AngularHullLocationAt(Alpha),
						AngularHullLocationAt(Alpha),
						AngularHullRotationAt(Alpha),
						LiveBoxShape,
						AngularExactHit);
				bAngularExactClear &=
					AngularExactResult == ERedPlanetTerrainQueryResult::NoHit
					&& !AngularExactHit.bBlockingHit
					&& !AngularExactHit.bStartPenetrating;
			}
			bAngularCorridorValid &= !bAngularStartBlocked
				&& bAngularMidBlocked
				&& !bAngularEndBlocked
				&& bAngularDynamicGeometricallyPresent
				&& AngularRootRouteHit == nullptr
				&& bAngularExactClear;

			FVector StableAngularNormal = FVector::ZeroVector;
			bool bAngularBlockedStable = true;
			for (int32 Repeat = 0;
				Repeat < AngularBlockedRepeats && bAngularBlockedStable;
				++Repeat)
			{
				Fighter->SetActorLocationAndRotation(
					AngularStartRoot,
					AngularStartRotation,
					false,
					nullptr,
					ETeleportType::TeleportPhysics);
				RootSphere->UpdateBounds();
				RootSphere->UpdateOverlaps();
				LiveHull->UpdateBounds();
				LiveHull->UpdateOverlaps();
				const FTransform ActorBefore = Fighter->GetActorTransform();
				const FTransform RootBefore = RootSphere->GetComponentTransform();
				const FTransform HullBefore = LiveHull->GetComponentTransform();
				const FTransform WitnessBefore =
					ResponseWitnessMesh->GetComponentTransform();
				FHitResult AngularBlockedHit(1.0f);
				const bool bAngularMoved =
					ProductionMovement->SafeMoveUpdatedComponent(
						AngularDelta,
						AngularTargetRotation,
						true,
						AngularBlockedHit);
				if (Repeat == 0)
				{
					StableAngularNormal = AngularBlockedHit.Normal;
				}
				bAngularBlockedStable &= !bAngularMoved
					&& AngularBlockedHit.bBlockingHit
					&& !AngularBlockedHit.bStartPenetrating
					&& AngularBlockedHit.GetComponent() == AngularStaticControl
					&& FMath::IsNearlyZero(AngularBlockedHit.Time, 1.0e-6f)
					&& FMath::IsNearlyZero(AngularBlockedHit.Distance, 0.001f)
					&& AngularBlockedHit.TraceStart.Equals(
						AngularStartRoot, 0.01f)
					&& AngularBlockedHit.TraceEnd.Equals(
						AngularStartRoot + AngularDelta, 0.01f)
					&& FVector::DotProduct(
						AngularBlockedHit.Normal.GetSafeNormal(),
						StableAngularNormal.GetSafeNormal()) > 0.9999f
					&& Fighter->GetActorTransform().Equals(ActorBefore, 0.001)
					&& RootSphere->GetComponentTransform().Equals(RootBefore, 0.001)
					&& LiveHull->GetComponentTransform().Equals(HullBefore, 0.001)
					&& ResponseWitnessMesh->GetComponentTransform().Equals(
						WitnessBefore, 0.001);
			}

			Fighter->SetActorLocationAndRotation(
				AngularStartRoot,
				AngularStartRotation,
				false,
				nullptr,
				ETeleportType::TeleportPhysics);
			RootSphere->UpdateBounds();
			RootSphere->UpdateOverlaps();
			LiveHull->UpdateBounds();
			LiveHull->UpdateOverlaps();
			const FTransform MoveWithActorBefore = Fighter->GetActorTransform();
			const FTransform MoveWithHullBefore = LiveHull->GetComponentTransform();
			ProductionMovement->MoveWithPlanetCollision(
				AngularDelta, AngularTargetRotation, 1.0f / 60.0f);
			const bool bAngularMoveWithDidNotSlide =
				Fighter->GetActorTransform().Equals(MoveWithActorBefore, 0.001)
				&& LiveHull->GetComponentTransform().Equals(
					MoveWithHullBefore, 0.001);

			if (AngularStaticControl)
			{
				AngularStaticControl->SetCollisionEnabled(ECollisionEnabled::NoCollision);
			}
			bool bAngularClearStable = true;
			for (int32 Repeat = 0;
				Repeat < AngularClearRepeats && bAngularClearStable;
				++Repeat)
			{
				Fighter->SetActorLocationAndRotation(
					AngularStartRoot,
					AngularStartRotation,
					false,
					nullptr,
					ETeleportType::TeleportPhysics);
				RootSphere->UpdateBounds();
				RootSphere->UpdateOverlaps();
				LiveHull->UpdateBounds();
				LiveHull->UpdateOverlaps();
				ProductionMovement->Velocity = FVector::ZeroVector;
				FHitResult AngularClearHit(1.0f);
				const bool bAngularMoved =
					ProductionMovement->SafeMoveUpdatedComponent(
						AngularDelta,
						AngularTargetRotation,
						true,
						AngularClearHit);
				const FVector ExpectedHullLocation = AngularStartRoot + AngularDelta
					+ AngularTargetRotation.RotateVector(AngularRootToHullLocal);
				const FQuat ExpectedHullRotation = (
					AngularTargetRotation
						* AngularHullRelativeRotation).GetNormalized();
				const FVector ExpectedWitnessLocation = AngularStartRoot + AngularDelta
					+ AngularTargetRotation.RotateVector(
						AngularRootToWitnessLocal);
				const FQuat ExpectedWitnessRotation = (
					AngularTargetRotation
						* AngularWitnessRelativeRotation).GetNormalized();
				bAngularClearStable &= bAngularMoved
					&& !AngularClearHit.bBlockingHit
					&& !AngularClearHit.bStartPenetrating
					&& FMath::IsNearlyEqual(AngularClearHit.Time, 1.0f, 1.0e-6f)
					&& Fighter->GetActorLocation().Equals(
						AngularStartRoot + AngularDelta, 0.05f)
					&& Fighter->GetActorQuat().Equals(
						AngularTargetRotation, 1.0e-6f)
					&& RootSphere->GetComponentLocation().Equals(
						AngularStartRoot + AngularDelta, 0.05f)
					&& RootSphere->GetComponentQuat().Equals(
						AngularTargetRotation, 1.0e-6f)
					&& LiveHull->GetComponentLocation().Equals(
						ExpectedHullLocation, 0.05f)
					&& LiveHull->GetComponentQuat().Equals(
						ExpectedHullRotation, 1.0e-6f)
					&& ResponseWitnessMesh->GetComponentLocation().Equals(
						ExpectedWitnessLocation, 0.05f)
					&& ResponseWitnessMesh->GetComponentQuat().Equals(
						ExpectedWitnessRotation, 1.0e-6f)
					&& LiveHull->GetRelativeLocation().Equals(
						AngularHullRelativeCenterBefore, 0.001f)
					&& LiveHull->GetRelativeRotation().Quaternion().Equals(
						AngularHullRelativeRotationBefore, 1.0e-6f)
					&& LiveHull->GetScaledBoxExtent().Equals(
						AngularHullExtentBefore, 0.001f)
					&& Fighter->GetActorScale3D().Equals(
						AngularActorScaleBefore, 1.0e-6f)
					&& ResponseWitnessMesh->GetComponentScale().Equals(
						AngularWitnessScaleBefore, 1.0e-6f)
					&& LiveHull->GetCollisionProfileName() == AngularHullProfileBefore
					&& ProductionMovement->UpdatedComponent == RootSphere
					&& ProductionMovement->GetTranslationCollisionEnvelope() == LiveHull;
			}

			// Pure-rotation native corridor: keep the root fixed and replay the same
			// six-degree off-centre child arc. The live Vehicle response must ignore an
			// earlier WorldDynamic control, reject a WorldStatic mid-arc corner contact,
			// then commit the exact target rotation once only that static control is off.
			constexpr int32 AngularPureBlockedRepeats = 8;
			constexpr int32 AngularPureClearRepeats = 8;
			auto AngularPureHullLocationAt =
				[AngularStartRoot,
					AngularRootToHullLocal,
					&AngularRootRotationAt](const float Alpha)
				{
					return AngularStartRoot
						+ AngularRootRotationAt(Alpha).RotateVector(
							AngularRootToHullLocal);
				};
			const FVector AngularPureMidCorner =
				AngularPureHullLocationAt(0.5f)
				+ AngularHullRotationAt(0.5f).RotateVector(AngularLocalCorner);
			const FVector AngularPureMidOutward =
				AngularHullRotationAt(0.5f).RotateVector(
					AngularLocalCorner).GetSafeNormal();
			const FVector AngularPureStaticCenter =
				AngularPureMidCorner - AngularPureMidOutward;
			const FVector AngularPureDynamicCorner =
				AngularPureHullLocationAt(AngularDynamicAlpha)
				+ AngularHullRotationAt(AngularDynamicAlpha).RotateVector(
					AngularLocalCorner);
			const FVector AngularPureDynamicOutward =
				AngularHullRotationAt(AngularDynamicAlpha).RotateVector(
					AngularLocalCorner).GetSafeNormal();
			const FVector AngularPureDynamicCenter =
				AngularPureDynamicCorner - AngularPureDynamicOutward;
			if (AngularStaticControl)
			{
				AngularStaticControl->SetWorldLocation(
					AngularPureStaticCenter,
					false,
					nullptr,
					ETeleportType::TeleportPhysics);
				AngularStaticControl->SetCollisionEnabled(
					ECollisionEnabled::QueryAndPhysics);
				AngularStaticControl->UpdateBounds();
				AngularStaticControl->UpdateOverlaps();
			}
			Blocker->SetWorldLocation(
				AngularPureDynamicCenter,
				false,
				nullptr,
				ETeleportType::TeleportPhysics);
			Blocker->SetCollisionEnabled(ECollisionEnabled::QueryOnly);
			Blocker->UpdateBounds();
			Blocker->UpdateOverlaps();

			const bool bAngularPureStartBlocked =
				TestWorld->OverlapBlockingTestByChannel(
					AngularPureHullLocationAt(0.0f),
					AngularHullRotationAt(0.0f),
					LiveHull->GetCollisionObjectType(),
					LiveBoxShape,
					AngularHullParams,
					AngularHullResponses);
			const bool bAngularPureMidBlocked =
				TestWorld->OverlapBlockingTestByChannel(
					AngularPureHullLocationAt(0.5f),
					AngularHullRotationAt(0.5f),
					LiveHull->GetCollisionObjectType(),
					LiveBoxShape,
					AngularHullParams,
					AngularHullResponses);
			const bool bAngularPureEndBlocked =
				TestWorld->OverlapBlockingTestByChannel(
					AngularPureHullLocationAt(1.0f),
					AngularHullRotationAt(1.0f),
					LiveHull->GetCollisionObjectType(),
					LiveBoxShape,
					AngularHullParams,
					AngularHullResponses);
			const bool bAngularPureDynamicGeometricallyPresent =
				TestWorld->OverlapAnyTestByObjectType(
					AngularPureHullLocationAt(AngularDynamicAlpha),
					AngularHullRotationAt(AngularDynamicAlpha),
					FCollisionObjectQueryParams(ECC_WorldDynamic),
					LiveBoxShape,
					AngularRawDynamicParams);
			TArray<FHitResult> AngularPureRootNativeHits;
			TestWorld->ComponentSweepMulti(
				AngularPureRootNativeHits,
				RootSphere,
				AngularStartRoot,
				AngularStartRoot,
				AngularStartRotation,
				AngularRootParams);
			const FHitResult* AngularPureRootNativeHit =
				AngularPureRootNativeHits.FindByPredicate(
					[](const FHitResult& Candidate)
					{
						return Candidate.bBlockingHit;
					});
			bool bAngularPureExactClear = true;
			for (const float Alpha : {0.0f, 0.5f, 1.0f})
			{
				FHitResult AngularPureExactHit(1.0f);
				const ERedPlanetTerrainQueryResult AngularPureExactResult =
					RedPlanetTerrainQuery::Sweep(
						TestWorld,
						PlanetCenter,
						AngularPureHullLocationAt(Alpha),
						AngularPureHullLocationAt(Alpha),
						AngularHullRotationAt(Alpha),
						LiveBoxShape,
						AngularPureExactHit);
				bAngularPureExactClear &=
					AngularPureExactResult == ERedPlanetTerrainQueryResult::NoHit
					&& !AngularPureExactHit.bBlockingHit
					&& !AngularPureExactHit.bStartPenetrating;
			}
			bool bAngularPureBlockedStable = AngularStaticControl
				&& !bAngularPureStartBlocked
				&& bAngularPureMidBlocked
				&& !bAngularPureEndBlocked
				&& bAngularPureDynamicGeometricallyPresent
				&& AngularPureRootNativeHit == nullptr
				&& bAngularPureExactClear;
			for (int32 Repeat = 0;
				Repeat < AngularPureBlockedRepeats && bAngularPureBlockedStable;
				++Repeat)
			{
				Fighter->SetActorLocationAndRotation(
					AngularStartRoot,
					AngularStartRotation,
					false,
					nullptr,
					ETeleportType::TeleportPhysics);
				RootSphere->UpdateBounds();
				RootSphere->UpdateOverlaps();
				LiveHull->UpdateBounds();
				LiveHull->UpdateOverlaps();
				ProductionMovement->Velocity = FVector::ZeroVector;
				const FTransform ActorBefore = Fighter->GetActorTransform();
				const FTransform RootBefore = RootSphere->GetComponentTransform();
				const FTransform HullBefore = LiveHull->GetComponentTransform();
				const FTransform WitnessBefore =
					ResponseWitnessMesh->GetComponentTransform();
				FHitResult AngularPureBlockedHit(1.0f);
				const bool bAngularPureMoved =
					ProductionMovement->SafeMoveUpdatedComponent(
						FVector::ZeroVector,
						AngularTargetRotation,
						true,
						AngularPureBlockedHit);
				bAngularPureBlockedStable &= !bAngularPureMoved
					&& AngularPureBlockedHit.bBlockingHit
					&& !AngularPureBlockedHit.bStartPenetrating
					&& AngularPureBlockedHit.GetComponent() == AngularStaticControl
					&& FMath::IsNearlyZero(AngularPureBlockedHit.Time, 1.0e-6f)
					&& FMath::IsNearlyZero(AngularPureBlockedHit.Distance, 0.001f)
					&& AngularPureBlockedHit.TraceStart.Equals(
						AngularStartRoot, 0.01f)
					&& AngularPureBlockedHit.TraceEnd.Equals(
						AngularStartRoot, 0.01f)
					&& Fighter->GetActorTransform().Equals(ActorBefore, 0.001)
					&& RootSphere->GetComponentTransform().Equals(RootBefore, 0.001)
					&& LiveHull->GetComponentTransform().Equals(HullBefore, 0.001)
					&& ResponseWitnessMesh->GetComponentTransform().Equals(
						WitnessBefore, 0.001);
			}

			Fighter->SetActorLocationAndRotation(
				AngularStartRoot,
				AngularStartRotation,
				false,
				nullptr,
				ETeleportType::TeleportPhysics);
			RootSphere->UpdateBounds();
			RootSphere->UpdateOverlaps();
			LiveHull->UpdateBounds();
			LiveHull->UpdateOverlaps();
			const FTransform AngularPureMoveWithActorBefore =
				Fighter->GetActorTransform();
			const FTransform AngularPureMoveWithHullBefore =
				LiveHull->GetComponentTransform();
			ProductionMovement->MoveWithPlanetCollision(
				FVector::ZeroVector,
				AngularTargetRotation,
				1.0f / 60.0f);
			const bool bAngularPureMoveWithDidNotSlide =
				Fighter->GetActorTransform().Equals(
					AngularPureMoveWithActorBefore, 0.001)
				&& LiveHull->GetComponentTransform().Equals(
					AngularPureMoveWithHullBefore, 0.001);

			if (AngularStaticControl)
			{
				AngularStaticControl->SetCollisionEnabled(ECollisionEnabled::NoCollision);
			}
			bool bAngularPureClearStable = true;
			for (int32 Repeat = 0;
				Repeat < AngularPureClearRepeats && bAngularPureClearStable;
				++Repeat)
			{
				Fighter->SetActorLocationAndRotation(
					AngularStartRoot,
					AngularStartRotation,
					false,
					nullptr,
					ETeleportType::TeleportPhysics);
				RootSphere->UpdateBounds();
				RootSphere->UpdateOverlaps();
				LiveHull->UpdateBounds();
				LiveHull->UpdateOverlaps();
				ProductionMovement->Velocity = FVector::ZeroVector;
				FHitResult AngularPureClearHit(1.0f);
				const bool bAngularPureMoved =
					ProductionMovement->SafeMoveUpdatedComponent(
						FVector::ZeroVector,
						AngularTargetRotation,
						true,
						AngularPureClearHit);
				const FVector ExpectedHullLocation = AngularStartRoot
					+ AngularTargetRotation.RotateVector(AngularRootToHullLocal);
				const FQuat ExpectedHullRotation = (
					AngularTargetRotation
						* AngularHullRelativeRotation).GetNormalized();
				const FVector ExpectedWitnessLocation = AngularStartRoot
					+ AngularTargetRotation.RotateVector(
						AngularRootToWitnessLocal);
				const FQuat ExpectedWitnessRotation = (
					AngularTargetRotation
						* AngularWitnessRelativeRotation).GetNormalized();
				bAngularPureClearStable &= bAngularPureMoved
					&& !AngularPureClearHit.bBlockingHit
					&& !AngularPureClearHit.bStartPenetrating
					&& FMath::IsNearlyEqual(
						AngularPureClearHit.Time, 1.0f, 1.0e-6f)
					&& FMath::IsNearlyZero(
						AngularPureClearHit.Distance, 0.001f)
					&& Fighter->GetActorLocation().Equals(
						AngularStartRoot, 0.05f)
					&& Fighter->GetActorQuat().Equals(
						AngularTargetRotation, 1.0e-6f)
					&& RootSphere->GetComponentLocation().Equals(
						AngularStartRoot, 0.05f)
					&& RootSphere->GetComponentQuat().Equals(
						AngularTargetRotation, 1.0e-6f)
					&& LiveHull->GetComponentLocation().Equals(
						ExpectedHullLocation, 0.05f)
					&& LiveHull->GetComponentQuat().Equals(
						ExpectedHullRotation, 1.0e-6f)
					&& ResponseWitnessMesh->GetComponentLocation().Equals(
						ExpectedWitnessLocation, 0.05f)
					&& ResponseWitnessMesh->GetComponentQuat().Equals(
						ExpectedWitnessRotation, 1.0e-6f);
			}
			Fighter->SetActorLocationAndRotation(
				AngularStartRoot,
				AngularStartRotation,
				false,
				nullptr,
				ETeleportType::TeleportPhysics);
			RootSphere->UpdateBounds();
			RootSphere->UpdateOverlaps();
			LiveHull->UpdateBounds();
			LiveHull->UpdateOverlaps();
			ProductionMovement->Velocity = FVector::ZeroVector;
			ProductionMovement->MoveWithPlanetCollision(
				FVector::ZeroVector,
				AngularTargetRotation,
				1.0f / 60.0f);
			const FVector AngularPureExpectedHull = AngularStartRoot
				+ AngularTargetRotation.RotateVector(AngularRootToHullLocal);
			const FQuat AngularPureExpectedHullRotation = (
				AngularTargetRotation
					* AngularHullRelativeRotation).GetNormalized();
			const FVector AngularPureExpectedWitness = AngularStartRoot
				+ AngularTargetRotation.RotateVector(AngularRootToWitnessLocal);
			const FQuat AngularPureExpectedWitnessRotation = (
				AngularTargetRotation
					* AngularWitnessRelativeRotation).GetNormalized();
			const bool bAngularPureClearMoveWithValid =
				Fighter->GetActorLocation().Equals(AngularStartRoot, 0.05f)
				&& Fighter->GetActorQuat().Equals(
					AngularTargetRotation, 1.0e-6f)
				&& RootSphere->GetComponentLocation().Equals(
					AngularStartRoot, 0.05f)
				&& RootSphere->GetComponentQuat().Equals(
					AngularTargetRotation, 1.0e-6f)
				&& LiveHull->GetComponentLocation().Equals(
					AngularPureExpectedHull, 0.05f)
				&& LiveHull->GetComponentQuat().Equals(
					AngularPureExpectedHullRotation, 1.0e-6f)
				&& ResponseWitnessMesh->GetComponentLocation().Equals(
					AngularPureExpectedWitness, 0.05f)
				&& ResponseWitnessMesh->GetComponentQuat().Equals(
					AngularPureExpectedWitnessRotation, 1.0e-6f)
				&& ProductionMovement->Velocity.IsNearlyZero(1.0e-6f);
			const bool bAngularPureNativeValid = bAngularPureBlockedStable
				&& bAngularPureMoveWithDidNotSlide
				&& bAngularPureClearStable
				&& bAngularPureClearMoveWithValid;
			bAngularCorridorValid &= bAngularPureNativeValid;

			// Exact-terrain-only angular corridor: search the actual fitted box for a local
			// rotation phase whose inward radial support is greatest at the middle of the
			// same six-degree request. Place that true midpoint just inside the owned cooked
			// terrain while both endpoint boxes remain exact-clear. PlanetGen chunks are
			// WorldDynamic and the production Vehicle response ignores them, so native overlap
			// controls must stay clear; only RedPlanetTerrainQuery may veto this request.
			constexpr int32 AngularExactBlockedRepeats = 8;
			constexpr float AngularExactTranslationCm = 30.0f;
			constexpr float AngularExactHalfAngleDegrees =
				AngularRotationDegrees * 0.5f;
			const FVector AngularExactDelta =
				OverlapTangent * AngularExactTranslationCm;
			const FVector AngularExactAxes[] =
			{
				FVector::XAxisVector,
				FVector::YAxisVector,
				FVector::ZAxisVector
			};
			FVector AngularExactLocalAxis = FVector::ZeroVector;
			float AngularExactCenterDegrees = 0.0f;
			double AngularExactArcSupportClearanceCm = -1.0;
			auto AngularExactRotationAtDegrees =
				[FighterRotation](const FVector& LocalAxis, const float Degrees)
				{
					return (FighterRotation
						* FQuat(
							LocalAxis,
							FMath::DegreesToRadians(Degrees))).GetNormalized();
				};
			auto AngularExactMinimumRadialSupport =
				[&](const FQuat& RootRotation)
				{
					const FVector HullCenterOffset =
						RootRotation.RotateVector(AngularRootToHullLocal);
					const FQuat HullRotation = (
						RootRotation * AngularHullRelativeRotation).GetNormalized();
					double MinimumRadialSupport = TNumericLimits<double>::Max();
					for (int32 CornerIndex = 0; CornerIndex < 8; ++CornerIndex)
					{
						const FVector LocalScaledCorner(
							(CornerIndex & 1)
								? LiveScaledHalfExtent.X : -LiveScaledHalfExtent.X,
							(CornerIndex & 2)
								? LiveScaledHalfExtent.Y : -LiveScaledHalfExtent.Y,
							(CornerIndex & 4)
								? LiveScaledHalfExtent.Z : -LiveScaledHalfExtent.Z);
						const FVector RootToCorner = HullCenterOffset
							+ HullRotation.RotateVector(LocalScaledCorner);
						MinimumRadialSupport = FMath::Min(
							MinimumRadialSupport,
							FVector::DotProduct(RootToCorner, OverlapRadialOut));
					}
					return MinimumRadialSupport;
				};
			for (const FVector& LocalAxis : AngularExactAxes)
			{
				for (int32 HalfDegreeIndex = -360;
					HalfDegreeIndex <= 360;
					++HalfDegreeIndex)
				{
					const float CenterDegrees = HalfDegreeIndex * 0.5f;
					const double StartSupport = AngularExactMinimumRadialSupport(
						AngularExactRotationAtDegrees(
							LocalAxis,
							CenterDegrees - AngularExactHalfAngleDegrees));
					const double MidSupport = AngularExactMinimumRadialSupport(
						AngularExactRotationAtDegrees(LocalAxis, CenterDegrees));
					const double EndSupport = AngularExactMinimumRadialSupport(
						AngularExactRotationAtDegrees(
							LocalAxis,
							CenterDegrees + AngularExactHalfAngleDegrees));
					const double EndpointClearanceCm = FMath::Min(
						StartSupport - MidSupport,
						EndSupport - MidSupport);
					if (EndpointClearanceCm > AngularExactArcSupportClearanceCm)
					{
						AngularExactArcSupportClearanceCm = EndpointClearanceCm;
						AngularExactLocalAxis = LocalAxis;
						AngularExactCenterDegrees = CenterDegrees;
					}
				}
			}

			const FQuat AngularExactStartRotation = AngularExactRotationAtDegrees(
				AngularExactLocalAxis,
				AngularExactCenterDegrees - AngularExactHalfAngleDegrees);
			const FQuat AngularExactTargetRotation = (
				AngularExactStartRotation
					* FQuat(
						AngularExactLocalAxis,
						FMath::DegreesToRadians(AngularRotationDegrees))).GetNormalized();
			const FQuat AngularExactMidRotation = FQuat::Slerp(
				AngularExactStartRotation,
				AngularExactTargetRotation,
				0.5f).GetNormalized();
			const FVector AngularExactMidHullOffset =
				AngularExactMidRotation.RotateVector(AngularRootToHullLocal);
			const FQuat AngularExactMidHullRotation = (
				AngularExactMidRotation
					* AngularHullRelativeRotation).GetNormalized();
			const FVector AngularExactSweepRootReference = DirectHit.ImpactPoint;
			const FVector AngularExactSweepStart = AngularExactSweepRootReference
				+ OverlapRadialOut * 5000.0f
				+ AngularExactMidHullOffset;
			const FVector AngularExactSweepEnd = AngularExactSweepRootReference
				- OverlapRadialOut * 5000.0f
				+ AngularExactMidHullOffset;
			FHitResult AngularExactContactHit(1.0f);
			FIntVector AngularExactContactKey(
				INDEX_NONE, INDEX_NONE, INDEX_NONE);
			const ERedPlanetTerrainQueryResult AngularExactContactResult =
				RedPlanetTerrainQuery::Sweep(
					TestWorld,
					PlanetCenter,
					AngularExactSweepStart,
					AngularExactSweepEnd,
					AngularExactMidHullRotation,
					LiveBoxShape,
					AngularExactContactHit,
					&AngularExactContactKey);
			ACLMPlanetChunk* AngularExactContactChunk =
				Cast<ACLMPlanetChunk>(AngularExactContactHit.GetActor());
			const FVector AngularExactContactRoot =
				AngularExactContactHit.Location - AngularExactMidHullOffset;

			FVector AngularExactStartRoot = FVector::ZeroVector;
			float AngularExactEmbedCm = 0.0f;
			FHitResult AngularExactStartHit(1.0f);
			FHitResult AngularExactMidHit(1.0f);
			FHitResult AngularExactEndHit(1.0f);
			FIntVector AngularExactMidKey(INDEX_NONE, INDEX_NONE, INDEX_NONE);
			bool bAngularExactPoseFound = false;
			auto QueryAngularExactPose =
				[&](
					const FVector& RootLocation,
					const FQuat& RootRotation,
					FHitResult& OutExactHit,
					FIntVector* OutKey)
				{
					const FVector HullLocation = RootLocation
						+ RootRotation.RotateVector(AngularRootToHullLocal);
					const FQuat HullRotation = (
						RootRotation * AngularHullRelativeRotation).GetNormalized();
					return RedPlanetTerrainQuery::Sweep(
						TestWorld,
						PlanetCenter,
						HullLocation,
						HullLocation,
						HullRotation,
						LiveBoxShape,
						OutExactHit,
						OutKey);
				};
			if (AngularExactContactResult == ERedPlanetTerrainQueryResult::Hit
				&& AngularExactContactHit.bBlockingHit
				&& !AngularExactContactHit.bStartPenetrating
				&& AngularExactContactChunk
				&& AngularExactContactChunk->GetOwner() == TestPlanet
				&& AngularExactArcSupportClearanceCm > 0.1)
			{
				for (int32 EmbedStep = 1;
					EmbedStep <= 9 && !bAngularExactPoseFound;
					++EmbedStep)
				{
					const float CandidateEmbedCm = static_cast<float>(
						AngularExactArcSupportClearanceCm
							* (static_cast<double>(EmbedStep) * 0.1));
					const FVector CandidateStartRoot = AngularExactContactRoot
						- AngularExactDelta * 0.5f
						- OverlapRadialOut * CandidateEmbedCm;
					FHitResult CandidateStartHit(1.0f);
					FHitResult CandidateMidHit(1.0f);
					FHitResult CandidateEndHit(1.0f);
					FIntVector CandidateMidKey(INDEX_NONE, INDEX_NONE, INDEX_NONE);
					const ERedPlanetTerrainQueryResult CandidateStartResult =
						QueryAngularExactPose(
							CandidateStartRoot,
							AngularExactStartRotation,
							CandidateStartHit,
							nullptr);
					const ERedPlanetTerrainQueryResult CandidateMidResult =
						QueryAngularExactPose(
							CandidateStartRoot + AngularExactDelta * 0.5f,
							AngularExactMidRotation,
							CandidateMidHit,
							&CandidateMidKey);
					const ERedPlanetTerrainQueryResult CandidateEndResult =
						QueryAngularExactPose(
							CandidateStartRoot + AngularExactDelta,
							AngularExactTargetRotation,
							CandidateEndHit,
							nullptr);
					bAngularExactPoseFound =
						CandidateStartResult == ERedPlanetTerrainQueryResult::NoHit
						&& !CandidateStartHit.bBlockingHit
						&& !CandidateStartHit.bStartPenetrating
						&& CandidateMidResult == ERedPlanetTerrainQueryResult::Hit
						&& CandidateMidHit.bBlockingHit
						&& CandidateMidHit.bStartPenetrating
						&& CandidateMidHit.PenetrationDepth > UE_KINDA_SMALL_NUMBER
						&& CandidateEndResult == ERedPlanetTerrainQueryResult::NoHit
						&& !CandidateEndHit.bBlockingHit
						&& !CandidateEndHit.bStartPenetrating;
					if (bAngularExactPoseFound)
					{
						AngularExactStartRoot = CandidateStartRoot;
						AngularExactEmbedCm = CandidateEmbedCm;
						AngularExactStartHit = CandidateStartHit;
						AngularExactMidHit = CandidateMidHit;
						AngularExactEndHit = CandidateEndHit;
						AngularExactMidKey = CandidateMidKey;
					}
				}
			}

			if (AngularStaticControl)
			{
				AngularStaticControl->SetCollisionEnabled(ECollisionEnabled::NoCollision);
			}
			Blocker->SetCollisionEnabled(ECollisionEnabled::NoCollision);
			if (!bAngularExactPoseFound)
			{
				// Keep later failure diagnostics away from the planet origin if the bounded
				// support/contact search could not construct its exact-only control.
				AngularExactStartRoot = AngularStartRoot;
			}
			bool bAngularExactNativeClear = bAngularExactPoseFound;
			for (int32 PoseIndex = 0; PoseIndex < 3; ++PoseIndex)
			{
				const float Alpha = PoseIndex * 0.5f;
				const FQuat PoseRotation = PoseIndex == 0
					? AngularExactStartRotation
					: (PoseIndex == 1
						? AngularExactMidRotation
						: AngularExactTargetRotation);
				const FVector PoseRoot = AngularExactStartRoot
					+ AngularExactDelta * Alpha;
				const FVector PoseHull = PoseRoot
					+ PoseRotation.RotateVector(AngularRootToHullLocal);
				const FQuat PoseHullRotation = (
					PoseRotation * AngularHullRelativeRotation).GetNormalized();
				bAngularExactNativeClear &=
					!TestWorld->OverlapBlockingTestByChannel(
						PoseHull,
						PoseHullRotation,
						LiveHull->GetCollisionObjectType(),
						LiveBoxShape,
						AngularHullParams,
						AngularHullResponses);
			}

			Fighter->SetActorLocationAndRotation(
				AngularExactStartRoot,
				AngularExactStartRotation,
				false,
				nullptr,
				ETeleportType::TeleportPhysics);
			RootSphere->UpdateBounds();
			RootSphere->UpdateOverlaps();
			LiveHull->UpdateBounds();
			LiveHull->UpdateOverlaps();
			TArray<FHitResult> AngularExactRootNativeHits;
			TestWorld->ComponentSweepMulti(
				AngularExactRootNativeHits,
				RootSphere,
				AngularExactStartRoot,
				AngularExactStartRoot + AngularExactDelta,
				AngularExactStartRotation,
				AngularRootParams);
			const FHitResult* AngularExactRootNativeHit =
				AngularExactRootNativeHits.FindByPredicate(
					[](const FHitResult& Candidate)
					{
						return Candidate.bBlockingHit;
					});
			FHitResult AngularExactRootTerrainHit(1.0f);
			const ERedPlanetTerrainQueryResult AngularExactRootTerrainResult =
				RedPlanetTerrainQuery::Sweep(
					TestWorld,
					PlanetCenter,
					AngularExactStartRoot,
					AngularExactStartRoot + AngularExactDelta,
					AngularExactStartRotation,
					RootSphere->GetCollisionShape(),
					AngularExactRootTerrainHit);
			const bool bAngularExactRootRouteClear =
				AngularExactRootNativeHit == nullptr
				&& AngularExactRootTerrainResult == ERedPlanetTerrainQueryResult::NoHit
				&& !AngularExactRootTerrainHit.bBlockingHit
				&& !AngularExactRootTerrainHit.bStartPenetrating;

			UPrimitiveComponent* StableAngularExactComponent = nullptr;
			FVector StableAngularExactNormal = FVector::ZeroVector;
			FIntVector StableAngularExactKey(INDEX_NONE, INDEX_NONE, INDEX_NONE);
			bool bAngularExactBlockedStable = bAngularExactPoseFound
				&& bAngularExactNativeClear
				&& bAngularExactRootRouteClear;
			for (int32 Repeat = 0;
				Repeat < AngularExactBlockedRepeats && bAngularExactBlockedStable;
				++Repeat)
			{
				Fighter->SetActorLocationAndRotation(
					AngularExactStartRoot,
					AngularExactStartRotation,
					false,
					nullptr,
					ETeleportType::TeleportPhysics);
				RootSphere->UpdateBounds();
				RootSphere->UpdateOverlaps();
				LiveHull->UpdateBounds();
				LiveHull->UpdateOverlaps();
				ProductionMovement->Velocity = FVector::ZeroVector;
				const FTransform ActorBefore = Fighter->GetActorTransform();
				const FTransform RootBefore = RootSphere->GetComponentTransform();
				const FTransform HullBefore = LiveHull->GetComponentTransform();
				const FTransform WitnessBefore =
					ResponseWitnessMesh->GetComponentTransform();
				FHitResult AngularExactBlockedHit(1.0f);
				const bool bAngularExactMoved =
					ProductionMovement->SafeMoveUpdatedComponent(
						AngularExactDelta,
						AngularExactTargetRotation,
						true,
						AngularExactBlockedHit);
				ACLMPlanetChunk* ExactHitChunk =
					Cast<ACLMPlanetChunk>(AngularExactBlockedHit.GetActor());
				const FIntVector ExactHitKey = ExactHitChunk
					? Private::ResolveActorChunkKey(TestPlanet, ExactHitChunk)
					: FIntVector(INDEX_NONE, INDEX_NONE, INDEX_NONE);
				if (Repeat == 0)
				{
					StableAngularExactComponent = AngularExactBlockedHit.GetComponent();
					StableAngularExactNormal = AngularExactBlockedHit.Normal;
					StableAngularExactKey = ExactHitKey;
				}
				bAngularExactBlockedStable &= !bAngularExactMoved
					&& AngularExactBlockedHit.bBlockingHit
					&& !AngularExactBlockedHit.bStartPenetrating
					&& ExactHitChunk
					&& ExactHitChunk->GetOwner() == TestPlanet
					&& AngularExactBlockedHit.GetComponent()
						== StableAngularExactComponent
					&& ExactHitKey == StableAngularExactKey
					&& FMath::IsNearlyZero(AngularExactBlockedHit.Time, 1.0e-6f)
					&& FMath::IsNearlyZero(AngularExactBlockedHit.Distance, 0.001f)
					&& FVector::DotProduct(
						AngularExactBlockedHit.Normal.GetSafeNormal(),
						StableAngularExactNormal.GetSafeNormal()) > 0.9999f
					&& Fighter->GetActorTransform().Equals(ActorBefore, 0.001)
					&& RootSphere->GetComponentTransform().Equals(RootBefore, 0.001)
					&& LiveHull->GetComponentTransform().Equals(HullBefore, 0.001)
					&& ResponseWitnessMesh->GetComponentTransform().Equals(
						WitnessBefore, 0.001);
			}

			Fighter->SetActorLocationAndRotation(
				AngularExactStartRoot,
				AngularExactStartRotation,
				false,
				nullptr,
				ETeleportType::TeleportPhysics);
			RootSphere->UpdateBounds();
			RootSphere->UpdateOverlaps();
			LiveHull->UpdateBounds();
			LiveHull->UpdateOverlaps();
			const FTransform AngularExactMoveWithActorBefore =
				Fighter->GetActorTransform();
			const FTransform AngularExactMoveWithHullBefore =
				LiveHull->GetComponentTransform();
			ProductionMovement->MoveWithPlanetCollision(
				AngularExactDelta,
				AngularExactTargetRotation,
				1.0f / 60.0f);
			const bool bAngularExactMoveWithDidNotSlide =
				Fighter->GetActorTransform().Equals(
					AngularExactMoveWithActorBefore, 0.001)
				&& LiveHull->GetComponentTransform().Equals(
					AngularExactMoveWithHullBefore, 0.001);

			// Route-specific attribution control: keep the identical exact-only angular
			// corridor and deliberately make PlanetGen resolution return NoMatchingPlanet.
			// Because the native fitted-box and root routes above are independently clear,
			// the complete transform must now commit. This proves the real-center veto came
			// from the exact terrain proxy branch rather than an incidental native blocker.
			Fighter->SetActorLocationAndRotation(
				AngularExactStartRoot,
				AngularExactStartRotation,
				false,
				nullptr,
				ETeleportType::TeleportPhysics);
			RootSphere->UpdateBounds();
			RootSphere->UpdateOverlaps();
			LiveHull->UpdateBounds();
			LiveHull->UpdateOverlaps();
			ProductionMovement->Velocity = FVector::ZeroVector;
			const FVector SavedAngularExactPlanetCenter =
				ProductionMovement->PlanetCenter;
			ProductionMovement->PlanetCenter = SavedAngularExactPlanetCenter
				+ OverlapTangent * 10000.0f;
			const FVector AngularExactMidRoot = AngularExactStartRoot
				+ AngularExactDelta * 0.5f;
			const FVector AngularExactMidHull = AngularExactMidRoot
				+ AngularExactMidRotation.RotateVector(AngularRootToHullLocal);
			FHitResult AngularExactNoMatchingQueryHit(1.0f);
			const ERedPlanetTerrainQueryResult AngularExactNoMatchingQueryResult =
				RedPlanetTerrainQuery::Sweep(
					TestWorld,
					ProductionMovement->PlanetCenter,
					AngularExactMidHull,
					AngularExactMidHull,
					AngularExactMidHullRotation,
					LiveBoxShape,
					AngularExactNoMatchingQueryHit);
			FHitResult AngularExactNoMatchingMoveHit(1.0f);
			const bool bAngularExactNoMatchingMoved =
				ProductionMovement->SafeMoveUpdatedComponent(
					AngularExactDelta,
					AngularExactTargetRotation,
					true,
					AngularExactNoMatchingMoveHit);
			ProductionMovement->PlanetCenter = SavedAngularExactPlanetCenter;
			const FVector AngularExactExpectedEndHull =
				AngularExactStartRoot + AngularExactDelta
				+ AngularExactTargetRotation.RotateVector(AngularRootToHullLocal);
			const FQuat AngularExactExpectedEndHullRotation = (
				AngularExactTargetRotation
					* AngularHullRelativeRotation).GetNormalized();
			const bool bAngularExactNoMatchingCounterfactual =
				AngularExactNoMatchingQueryResult
					== ERedPlanetTerrainQueryResult::NoMatchingPlanet
				&& !AngularExactNoMatchingQueryHit.bBlockingHit
				&& !AngularExactNoMatchingQueryHit.bStartPenetrating
				&& bAngularExactNoMatchingMoved
				&& !AngularExactNoMatchingMoveHit.bBlockingHit
				&& !AngularExactNoMatchingMoveHit.bStartPenetrating
				&& Fighter->GetActorLocation().Equals(
					AngularExactStartRoot + AngularExactDelta, 0.05f)
				&& Fighter->GetActorQuat().Equals(
					AngularExactTargetRotation, 1.0e-6f)
				&& LiveHull->GetComponentLocation().Equals(
					AngularExactExpectedEndHull, 0.05f)
				&& LiveHull->GetComponentQuat().Equals(
					AngularExactExpectedEndHullRotation, 1.0e-6f);
			bAngularCorridorValid &= bAngularExactPoseFound
				&& AngularExactMidHit.GetComponent()
					== AngularExactContactHit.GetComponent()
				&& AngularExactMidKey == AngularExactContactKey
				&& bAngularExactNativeClear
				&& bAngularExactRootRouteClear
				&& bAngularExactBlockedStable
				&& bAngularExactMoveWithDidNotSlide
				&& bAngularExactNoMatchingCounterfactual;

			// Pure-rotation exact corridor: remove the tangent translation from the same
			// measured support window. Actual start/end boxes remain clear, the true middle
			// pose touches only owned streamed PlanetGen terrain, and all native/root routes
			// stay clear. A shifted-centre replay must commit the identical rotation.
			const FVector AngularPureExactStartRoot = bAngularExactPoseFound
				? AngularExactContactRoot
					- OverlapRadialOut * AngularExactEmbedCm
				: AngularStartRoot;
			FHitResult AngularPureExactStartHit(1.0f);
			FHitResult AngularPureExactMidHit(1.0f);
			FHitResult AngularPureExactEndHit(1.0f);
			FIntVector AngularPureExactMidKey(INDEX_NONE, INDEX_NONE, INDEX_NONE);
			const ERedPlanetTerrainQueryResult AngularPureExactStartResult =
				QueryAngularExactPose(
					AngularPureExactStartRoot,
					AngularExactStartRotation,
					AngularPureExactStartHit,
					nullptr);
			const ERedPlanetTerrainQueryResult AngularPureExactMidResult =
				QueryAngularExactPose(
					AngularPureExactStartRoot,
					AngularExactMidRotation,
					AngularPureExactMidHit,
					&AngularPureExactMidKey);
			const ERedPlanetTerrainQueryResult AngularPureExactEndResult =
				QueryAngularExactPose(
					AngularPureExactStartRoot,
					AngularExactTargetRotation,
					AngularPureExactEndHit,
					nullptr);
			ACLMPlanetChunk* AngularPureExactMidChunk =
				Cast<ACLMPlanetChunk>(AngularPureExactMidHit.GetActor());
			bool bAngularPureExactNativeClear = bAngularExactPoseFound;
			for (int32 PoseIndex = 0; PoseIndex < 3; ++PoseIndex)
			{
				const FQuat PoseRotation = PoseIndex == 0
					? AngularExactStartRotation
					: (PoseIndex == 1
						? AngularExactMidRotation
						: AngularExactTargetRotation);
				const FVector PoseHull = AngularPureExactStartRoot
					+ PoseRotation.RotateVector(AngularRootToHullLocal);
				const FQuat PoseHullRotation = (
					PoseRotation * AngularHullRelativeRotation).GetNormalized();
				bAngularPureExactNativeClear &=
					!TestWorld->OverlapBlockingTestByChannel(
						PoseHull,
						PoseHullRotation,
						LiveHull->GetCollisionObjectType(),
						LiveBoxShape,
						AngularHullParams,
						AngularHullResponses);
			}
			Fighter->SetActorLocationAndRotation(
				AngularPureExactStartRoot,
				AngularExactStartRotation,
				false,
				nullptr,
				ETeleportType::TeleportPhysics);
			RootSphere->UpdateBounds();
			RootSphere->UpdateOverlaps();
			LiveHull->UpdateBounds();
			LiveHull->UpdateOverlaps();
			TArray<FHitResult> AngularPureExactRootNativeHits;
			TestWorld->ComponentSweepMulti(
				AngularPureExactRootNativeHits,
				RootSphere,
				AngularPureExactStartRoot,
				AngularPureExactStartRoot,
				AngularExactStartRotation,
				AngularRootParams);
			const FHitResult* AngularPureExactRootNativeHit =
				AngularPureExactRootNativeHits.FindByPredicate(
					[](const FHitResult& Candidate)
					{
						return Candidate.bBlockingHit;
					});
			FHitResult AngularPureExactRootTerrainHit(1.0f);
			const ERedPlanetTerrainQueryResult AngularPureExactRootTerrainResult =
				RedPlanetTerrainQuery::Sweep(
					TestWorld,
					PlanetCenter,
					AngularPureExactStartRoot,
					AngularPureExactStartRoot,
					AngularExactStartRotation,
					RootSphere->GetCollisionShape(),
					AngularPureExactRootTerrainHit);
			const bool bAngularPureExactRootClear =
				AngularPureExactRootNativeHit == nullptr
				&& AngularPureExactRootTerrainResult
					== ERedPlanetTerrainQueryResult::NoHit
				&& !AngularPureExactRootTerrainHit.bBlockingHit
				&& !AngularPureExactRootTerrainHit.bStartPenetrating;

			UPrimitiveComponent* StableAngularPureExactComponent = nullptr;
			FVector StableAngularPureExactNormal = FVector::ZeroVector;
			FIntVector StableAngularPureExactKey(INDEX_NONE, INDEX_NONE, INDEX_NONE);
			bool bAngularPureExactBlockedStable =
				AngularPureExactStartResult == ERedPlanetTerrainQueryResult::NoHit
				&& !AngularPureExactStartHit.bBlockingHit
				&& !AngularPureExactStartHit.bStartPenetrating
				&& AngularPureExactMidResult == ERedPlanetTerrainQueryResult::Hit
				&& AngularPureExactMidHit.bBlockingHit
				&& AngularPureExactMidHit.bStartPenetrating
				&& AngularPureExactMidHit.PenetrationDepth > UE_KINDA_SMALL_NUMBER
				&& AngularPureExactMidChunk
				&& AngularPureExactMidChunk->GetOwner() == TestPlanet
				&& AngularPureExactEndResult == ERedPlanetTerrainQueryResult::NoHit
				&& !AngularPureExactEndHit.bBlockingHit
				&& !AngularPureExactEndHit.bStartPenetrating
				&& bAngularPureExactNativeClear
				&& bAngularPureExactRootClear;
			for (int32 Repeat = 0;
				Repeat < AngularExactBlockedRepeats
					&& bAngularPureExactBlockedStable;
				++Repeat)
			{
				Fighter->SetActorLocationAndRotation(
					AngularPureExactStartRoot,
					AngularExactStartRotation,
					false,
					nullptr,
					ETeleportType::TeleportPhysics);
				RootSphere->UpdateBounds();
				RootSphere->UpdateOverlaps();
				LiveHull->UpdateBounds();
				LiveHull->UpdateOverlaps();
				ProductionMovement->Velocity = FVector::ZeroVector;
				const FTransform ActorBefore = Fighter->GetActorTransform();
				const FTransform RootBefore = RootSphere->GetComponentTransform();
				const FTransform HullBefore = LiveHull->GetComponentTransform();
				const FTransform WitnessBefore =
					ResponseWitnessMesh->GetComponentTransform();
				FHitResult AngularPureExactBlockedHit(1.0f);
				const bool bAngularPureExactMoved =
					ProductionMovement->SafeMoveUpdatedComponent(
						FVector::ZeroVector,
						AngularExactTargetRotation,
						true,
						AngularPureExactBlockedHit);
				ACLMPlanetChunk* ExactHitChunk =
					Cast<ACLMPlanetChunk>(AngularPureExactBlockedHit.GetActor());
				const FIntVector ExactHitKey = ExactHitChunk
					? Private::ResolveActorChunkKey(TestPlanet, ExactHitChunk)
					: FIntVector(INDEX_NONE, INDEX_NONE, INDEX_NONE);
				if (Repeat == 0)
				{
					StableAngularPureExactComponent =
						AngularPureExactBlockedHit.GetComponent();
					StableAngularPureExactNormal = AngularPureExactBlockedHit.Normal;
					StableAngularPureExactKey = ExactHitKey;
				}
				bAngularPureExactBlockedStable &= !bAngularPureExactMoved
					&& AngularPureExactBlockedHit.bBlockingHit
					&& !AngularPureExactBlockedHit.bStartPenetrating
					&& ExactHitChunk
					&& ExactHitChunk->GetOwner() == TestPlanet
					&& AngularPureExactBlockedHit.GetComponent()
						== StableAngularPureExactComponent
					&& ExactHitKey == StableAngularPureExactKey
					&& FMath::IsNearlyZero(
						AngularPureExactBlockedHit.Time, 1.0e-6f)
					&& FMath::IsNearlyZero(
						AngularPureExactBlockedHit.Distance, 0.001f)
					&& AngularPureExactBlockedHit.TraceStart.Equals(
						AngularPureExactStartRoot, 0.01f)
					&& AngularPureExactBlockedHit.TraceEnd.Equals(
						AngularPureExactStartRoot, 0.01f)
					&& FVector::DotProduct(
						AngularPureExactBlockedHit.Normal.GetSafeNormal(),
						StableAngularPureExactNormal.GetSafeNormal()) > 0.9999f
					&& Fighter->GetActorTransform().Equals(ActorBefore, 0.001)
					&& RootSphere->GetComponentTransform().Equals(RootBefore, 0.001)
					&& LiveHull->GetComponentTransform().Equals(HullBefore, 0.001)
					&& ResponseWitnessMesh->GetComponentTransform().Equals(
						WitnessBefore, 0.001);
			}

			Fighter->SetActorLocationAndRotation(
				AngularPureExactStartRoot,
				AngularExactStartRotation,
				false,
				nullptr,
				ETeleportType::TeleportPhysics);
			RootSphere->UpdateBounds();
			RootSphere->UpdateOverlaps();
			LiveHull->UpdateBounds();
			LiveHull->UpdateOverlaps();
			const FTransform AngularPureExactMoveWithActorBefore =
				Fighter->GetActorTransform();
			const FTransform AngularPureExactMoveWithHullBefore =
				LiveHull->GetComponentTransform();
			ProductionMovement->MoveWithPlanetCollision(
				FVector::ZeroVector,
				AngularExactTargetRotation,
				1.0f / 60.0f);
			const bool bAngularPureExactMoveWithDidNotSlide =
				Fighter->GetActorTransform().Equals(
					AngularPureExactMoveWithActorBefore, 0.001)
				&& LiveHull->GetComponentTransform().Equals(
					AngularPureExactMoveWithHullBefore, 0.001);

			Fighter->SetActorLocationAndRotation(
				AngularPureExactStartRoot,
				AngularExactStartRotation,
				false,
				nullptr,
				ETeleportType::TeleportPhysics);
			RootSphere->UpdateBounds();
			RootSphere->UpdateOverlaps();
			LiveHull->UpdateBounds();
			LiveHull->UpdateOverlaps();
			ProductionMovement->Velocity = FVector::ZeroVector;
			const FVector SavedAngularPureExactPlanetCenter =
				ProductionMovement->PlanetCenter;
			ProductionMovement->PlanetCenter = SavedAngularPureExactPlanetCenter
				+ OverlapTangent * 10000.0f;
			const FVector AngularPureExactMidHull = AngularPureExactStartRoot
				+ AngularExactMidRotation.RotateVector(AngularRootToHullLocal);
			FHitResult AngularPureExactNoMatchingQueryHit(1.0f);
			const ERedPlanetTerrainQueryResult AngularPureExactNoMatchingQueryResult =
				RedPlanetTerrainQuery::Sweep(
					TestWorld,
					ProductionMovement->PlanetCenter,
					AngularPureExactMidHull,
					AngularPureExactMidHull,
					AngularExactMidHullRotation,
					LiveBoxShape,
					AngularPureExactNoMatchingQueryHit);
			FHitResult AngularPureExactNoMatchingMoveHit(1.0f);
			const bool bAngularPureExactNoMatchingMoved =
				ProductionMovement->SafeMoveUpdatedComponent(
					FVector::ZeroVector,
					AngularExactTargetRotation,
					true,
					AngularPureExactNoMatchingMoveHit);
			ProductionMovement->PlanetCenter = SavedAngularPureExactPlanetCenter;
			const FVector AngularPureExactExpectedHull = AngularPureExactStartRoot
				+ AngularExactTargetRotation.RotateVector(AngularRootToHullLocal);
			const FQuat AngularPureExactExpectedHullRotation = (
				AngularExactTargetRotation
					* AngularHullRelativeRotation).GetNormalized();
			const bool bAngularPureExactNoMatchingCounterfactual =
				AngularPureExactNoMatchingQueryResult
					== ERedPlanetTerrainQueryResult::NoMatchingPlanet
				&& !AngularPureExactNoMatchingQueryHit.bBlockingHit
				&& !AngularPureExactNoMatchingQueryHit.bStartPenetrating
				&& bAngularPureExactNoMatchingMoved
				&& !AngularPureExactNoMatchingMoveHit.bBlockingHit
				&& !AngularPureExactNoMatchingMoveHit.bStartPenetrating
				&& Fighter->GetActorLocation().Equals(
					AngularPureExactStartRoot, 0.05f)
				&& Fighter->GetActorQuat().Equals(
					AngularExactTargetRotation, 1.0e-6f)
				&& LiveHull->GetComponentLocation().Equals(
					AngularPureExactExpectedHull, 0.05f)
				&& LiveHull->GetComponentQuat().Equals(
					AngularPureExactExpectedHullRotation, 1.0e-6f);
			const bool bAngularPureExactValid = bAngularPureExactBlockedStable
				&& bAngularPureExactMoveWithDidNotSlide
				&& bAngularPureExactNoMatchingCounterfactual;
			bAngularCorridorValid &= bAngularPureExactValid;

			// Native-only legacy/static-body fallback: deliberately make the exact PlanetGen
			// lookup return NoMatchingPlanet while retaining the identical clear native route.
			Fighter->SetActorLocationAndRotation(
				AngularStartRoot,
				AngularStartRotation,
				false,
				nullptr,
				ETeleportType::TeleportPhysics);
			RootSphere->UpdateBounds();
			RootSphere->UpdateOverlaps();
			LiveHull->UpdateBounds();
			LiveHull->UpdateOverlaps();
			const FVector SavedAngularPlanetCenter = ProductionMovement->PlanetCenter;
			ProductionMovement->PlanetCenter = SavedAngularPlanetCenter
				+ OverlapTangent * 10000.0f;
			FHitResult AngularNoMatchingControlHit(1.0f);
			const ERedPlanetTerrainQueryResult AngularNoMatchingControlResult =
				RedPlanetTerrainQuery::Sweep(
					TestWorld,
					ProductionMovement->PlanetCenter,
					LiveHull->GetComponentLocation(),
					LiveHull->GetComponentLocation(),
					LiveHull->GetComponentQuat(),
					LiveHull->GetCollisionShape(),
					AngularNoMatchingControlHit);
			const bool bAngularNoMatchingControlProved =
				AngularNoMatchingControlResult
					== ERedPlanetTerrainQueryResult::NoMatchingPlanet
				&& !AngularNoMatchingControlHit.bBlockingHit
				&& !AngularNoMatchingControlHit.bStartPenetrating;
			FHitResult AngularNoMatchingHit(1.0f);
			const bool bAngularNoMatchingMoved =
				ProductionMovement->SafeMoveUpdatedComponent(
					AngularDelta,
					AngularTargetRotation,
					true,
					AngularNoMatchingHit);
			ProductionMovement->PlanetCenter = SavedAngularPlanetCenter;
			const bool bAngularNoMatchingFallbackClear =
				bAngularNoMatchingControlProved
				&& bAngularNoMatchingMoved
				&& !AngularNoMatchingHit.bBlockingHit
				&& !AngularNoMatchingHit.bStartPenetrating
				&& Fighter->GetActorLocation().Equals(
					AngularStartRoot + AngularDelta, 0.05f)
				&& Fighter->GetActorQuat().Equals(
					AngularTargetRotation, 1.0e-6f);

			FHitResult AngularFinalExactHit(1.0f);
			const ERedPlanetTerrainQueryResult AngularFinalExactResult =
				RedPlanetTerrainQuery::Sweep(
					TestWorld,
					PlanetCenter,
					LiveHull->GetComponentLocation(),
					LiveHull->GetComponentLocation(),
					LiveHull->GetComponentQuat(),
					LiveBoxShape,
					AngularFinalExactHit);
			const bool bAngularFinalNativeBlocked =
				TestWorld->OverlapBlockingTestByChannel(
					LiveHull->GetComponentLocation(),
					LiveHull->GetComponentQuat(),
					LiveHull->GetCollisionObjectType(),
					LiveBoxShape,
					AngularHullParams,
					AngularHullResponses);
			bAngularCorridorValid &= bAngularBlockedStable
				&& bAngularMoveWithDidNotSlide
				&& bAngularClearStable
				&& bAngularNoMatchingFallbackClear
				&& AngularFinalExactResult == ERedPlanetTerrainQueryResult::NoHit
				&& !AngularFinalExactHit.bBlockingHit
				&& !AngularFinalExactHit.bStartPenetrating
				&& !bAngularFinalNativeBlocked
				&& FighterPackage->IsDirty() == bExpectedPackageDirty;

			if (AngularStaticControl)
			{
				AngularStaticControl->SetCollisionEnabled(ECollisionEnabled::NoCollision);
			}
			if (AngularStaticActor)
			{
				AngularStaticActor->Destroy();
			}
			Blocker->SetBoxExtent(AngularSavedDynamicExtent, false);
			Blocker->SetCollisionEnabled(AngularSavedDynamicCollision);
			Blocker->SetWorldTransform(AngularSavedDynamicTransform);
			Blocker->UpdateBounds();
			Blocker->UpdateOverlaps();
			bValid &= Test->TestTrue(
				TEXT("Production fitted hull rejects an arc-only static contact and commits the identical clear angular request"),
				bAngularCorridorValid);
			if (bAngularCorridorValid)
			{
				UE_LOG(LogTemp, Display,
					TEXT("RED_FUSED_ACTIVE_TERRAIN_PRODUCTION_FIGHTER_HULL_PURE_ROTATION_PASS angle_deg=%.3f translation_cm=0.000 segments=3 native=WorldStatic dynamic=ignored native_blocked_repeats=%d native_clear_repeats=%d exact=midarc_blocked exact_depth_cm=%.6f exact_repeats=%d exact_key=(%d,%d,%d) exact_counterfactual=commit root=clear slide=suppressed clear_wrapper=commit final=clear"),
					AngularRotationDegrees,
					AngularPureBlockedRepeats,
					AngularPureClearRepeats,
					AngularPureExactMidHit.PenetrationDepth,
					AngularExactBlockedRepeats,
					StableAngularPureExactKey.X,
					StableAngularPureExactKey.Y,
					StableAngularPureExactKey.Z);
				UE_LOG(LogTemp, Display,
					TEXT("RED_FUSED_ACTIVE_TERRAIN_PRODUCTION_FIGHTER_HULL_ANGULAR_CORRIDOR_PASS angle_deg=%.3f translation_cm=%.3f segments=3 corner_clearance_cm=%.6f blocked_repeats=%d clear_repeats=%d native=WorldStatic dynamic=ignored exact=midarc_blocked exact_translation_cm=%.3f exact_support_clearance_cm=%.6f exact_embed_cm=%.6f exact_depth_cm=%.6f exact_repeats=%d exact_key=(%d,%d,%d) exact_counterfactual=commit legacy=native_clear root=clear slide=suppressed final=clear"),
					AngularRotationDegrees,
					AngularTranslationCm,
					AngularCornerClearanceCm,
					AngularBlockedRepeats,
					AngularClearRepeats,
					AngularExactTranslationCm,
					AngularExactArcSupportClearanceCm,
					AngularExactEmbedCm,
					AngularExactMidHit.PenetrationDepth,
					AngularExactBlockedRepeats,
					StableAngularExactKey.X,
					StableAngularExactKey.Y,
					StableAngularExactKey.Z);
			}
			Fighter->Destroy();
			bValid &= Test->TestEqual(
				TEXT("Loading, querying, and destroying the transient fighter preserves its Blueprint package dirty state"),
				FighterPackage->IsDirty(), bExpectedPackageDirty);

			if (bValid)
			{
				UE_LOG(LogTemp, Display,
					TEXT("RED_FUSED_ACTIVE_TERRAIN_LIVE_FIGHTER_HULL_QUERY_PASS class=%s center_cm=(%.2f,%.2f,%.2f) half_extent_cm=(%.2f,%.2f,%.2f) visible_meshes=%d box_distance_cm=%.6f sphere_distance_cm=%.6f expected_lead_cm=%.6f observed_lead_cm=%.6f key=(%d,%d,%d) repeats=8"),
					*FighterClass->GetPathName(),
					LiveRelativeCenter.X,
					LiveRelativeCenter.Y,
					LiveRelativeCenter.Z,
					LiveScaledHalfExtent.X,
					LiveScaledHalfExtent.Y,
					LiveScaledHalfExtent.Z,
					IncludedVisibleMeshCount,
					DirectHit.Distance,
					RootHit.Distance,
					ExpectedLiveBoxLeadCm,
					ObservedLiveBoxLeadCm,
					DirectKey.X,
					DirectKey.Y,
					DirectKey.Z);
			}
			else
			{
				UE_LOG(LogTemp, Error,
					TEXT("RED_FUSED_ACTIVE_TERRAIN_LIVE_FIGHTER_HULL_QUERY_FAIL class=%s center_cm=(%.2f,%.2f,%.2f) half_extent_cm=(%.2f,%.2f,%.2f) box_hit=%d box_distance_cm=%.6f sphere_hit=%d sphere_distance_cm=%.6f raw_hits=%d"),
					*FighterClass->GetPathName(),
					LiveRelativeCenter.X,
					LiveRelativeCenter.Y,
					LiveRelativeCenter.Z,
					LiveScaledHalfExtent.X,
					LiveScaledHalfExtent.Y,
					LiveScaledHalfExtent.Z,
					bDirectHit ? 1 : 0,
					DirectHit.Distance,
					bRootHit ? 1 : 0,
					RootHit.Distance,
					RawTerrainHits.Num());
			}

			return bValid;
		}

		bool ValidateVehicleSurfaceIntegration(const FHitResult& BaselineTerrainHit)
		{
			UWorld* TestWorld = World.Get();
			ACLMPlanet* TestPlanet = Planet.Get();
			UBoxComponent* Blocker = WorldDynamicBlocker.Get();
			if (!TestWorld || !TestPlanet || !Blocker)
			{
				return Test->TestTrue(
					TEXT("The vehicle surface-query fixture remains valid"), false);
			}

			const FVector Center = TestPlanet->GetActorLocation();
			const FVector RadialUp = (BaselineTerrainHit.ImpactPoint - Center).GetSafeNormal();
			const FVector VehicleLocation = BaselineTerrainHit.ImpactPoint + RadialUp * 5000.0f;
			const FVector BlockerLocation = BaselineTerrainHit.ImpactPoint + RadialUp * 2500.0f;
			Blocker->SetWorldLocation(BlockerLocation, false, nullptr, ETeleportType::TeleportPhysics);
			Blocker->UpdateBounds();
			Blocker->UpdateOverlaps();

			FActorSpawnParameters SpawnParameters;
			SpawnParameters.ObjectFlags |= RF_Transient;
			SpawnParameters.SpawnCollisionHandlingOverride =
				ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
			ARedShip* Ship = TestWorld->SpawnActor<ARedShip>(
				ARedShip::StaticClass(),
				FTransform(FRotationMatrix::MakeFromZX(RadialUp, SeamDirection).ToQuat(), VehicleLocation),
				SpawnParameters);
			ARedShuttleBase* Shuttle = TestWorld->SpawnActor<ARedShuttleBase>(
				ARedShuttleBase::StaticClass(),
				FTransform(FRotationMatrix::MakeFromZX(RadialUp, SeamDirection).ToQuat(), VehicleLocation),
				SpawnParameters);

			bool bValid = true;
			bValid &= Test->TestNotNull(TEXT("The actor fixture spawns an ARedShip"), Ship);
			bValid &= Test->TestNotNull(TEXT("The actor fixture spawns an ARedShuttleBase"), Shuttle);
			if (!Ship || !Shuttle)
			{
				if (Ship) { Ship->Destroy(); }
				if (Shuttle) { Shuttle->Destroy(); }
				return false;
			}

			Ship->SetActorTickEnabled(false);
			Ship->SetActorEnableCollision(false);
			Shuttle->SetActorTickEnabled(false);
			Shuttle->SetActorEnableCollision(false);
			TArray<UActorComponent*> ProbeComponents;
			Ship->GetComponents(ProbeComponents);
			Shuttle->GetComponents(ProbeComponents);
			for (UActorComponent* Component : ProbeComponents)
			{
				if (Component)
				{
					Component->SetComponentTickEnabled(false);
				}
			}

			URedShipMovementComponent* Movement =
				Cast<URedShipMovementComponent>(Ship->GetMovementComponent());
			bValid &= Test->TestNotNull(TEXT("ARedShip owns its production movement component"), Movement);
			if (Movement)
			{
				Movement->PlanetCenter = Center;
				Movement->PlanetRadius = TestPlanet->PlanetRadius;
			}

			FHitResult ShipLandingHit;
			FVector ShipRadialUp = FVector::ZeroVector;
			const bool bShipLandingHit = Movement
				&& Ship->QueryLandingSurface(ShipLandingHit, ShipRadialUp);
			bValid &= Test->TestTrue(
				TEXT("ARedShip landing query reaches active PlanetGen terrain"), bShipLandingHit);
			bValid &= Test->TestTrue(
				TEXT("ARedShip landing query reports the dominant radial up"),
				bShipLandingHit && FVector::DotProduct(ShipRadialUp, RadialUp) > 0.9999f);
			bValid &= Test->TestTrue(
				TEXT("ARedShip landing query ignores the closer arbitrary WorldDynamic blocker"),
				bShipLandingHit && ShipLandingHit.GetComponent() != Blocker);
			bValid &= Test->TestTrue(
				TEXT("ARedShip landing query returns the same active terrain component"),
				bShipLandingHit
					&& ShipLandingHit.GetComponent() == BaselineTerrainHit.GetComponent());
			bValid &= Test->TestTrue(
				TEXT("ARedShip landing query returns the same radial terrain impact"),
				bShipLandingHit
					&& FVector::Dist(ShipLandingHit.ImpactPoint, BaselineTerrainHit.ImpactPoint) <= 2.0f);

			FCollisionQueryParams RawParams(SCENE_QUERY_STAT(RedVehicleSurfaceRawControl), true);
			RawParams.AddIgnoredActor(Ship);
			RawParams.AddIgnoredActor(Shuttle);
			FHitResult RawVehicleHit;
			const bool bRawVehicleHit = bShipLandingHit && TestWorld->LineTraceSingleByObjectType(
				RawVehicleHit,
				ShipLandingHit.TraceStart,
				ShipLandingHit.TraceEnd,
				FCollisionObjectQueryParams(ECC_WorldDynamic),
				RawParams);
			bValid &= Test->TestTrue(
				TEXT("The equivalent raw ship trace hits the closer dynamic blocker"),
				bRawVehicleHit && RawVehicleHit.GetComponent() == Blocker);
			bValid &= Test->TestTrue(
				TEXT("The closer blocker precedes the actor-selected terrain"),
				bRawVehicleHit && bShipLandingHit
					&& RawVehicleHit.Distance < ShipLandingHit.Distance);

			FVector ShuttleHitPoint = FVector::ZeroVector;
			FVector ShuttleHitNormal = FVector::ZeroVector;
			const bool bShuttleSurfaceHit = Shuttle->QueryPlanetSurface(
				VehicleLocation, ShuttleHitPoint, ShuttleHitNormal);
			bValid &= Test->TestTrue(
				TEXT("ARedShuttleBase surface query reaches active PlanetGen terrain"),
				bShuttleSurfaceHit);
			bValid &= Test->TestTrue(
				TEXT("ARedShuttleBase surface query ignores the closer dynamic blocker"),
				bShuttleSurfaceHit
					&& FVector::Dist(ShuttleHitPoint, BaselineTerrainHit.ImpactPoint) <= 2.0f);
			bValid &= Test->TestTrue(
				TEXT("ARedShuttleBase returns a usable outward surface normal"),
				bShuttleSurfaceHit && FVector::DotProduct(ShuttleHitNormal, RadialUp) > 0.5f);

			URedShipCollisionDriver* Driver = Ship->FindComponentByClass<URedShipCollisionDriver>();
			bValid &= Test->TestNotNull(TEXT("ARedShip owns its production collision driver"), Driver);
			if (Movement && Driver)
			{
				Movement->Velocity = -RadialUp * 20000.0f;
				Driver->MaxLeadDistance = 1000000.0f;
				Driver->InvokerRadius = 0.0f;
				Driver->GovernorCookAheadTime = 1.0f;
				Driver->BackstopLookAheadTime = 1.0f;
				Driver->BackstopBrakeFraction = 1.0f;
				Driver->GovernorMinSpeed = 100.0f;

				FHitResult ExpectedBackstopHit;
				const ERedPlanetTerrainQueryResult ExpectedBackstopResult =
					RedPlanetTerrainQuery::LineTrace(
						TestWorld,
						Center,
						VehicleLocation,
						VehicleLocation - RadialUp * 20000.0f,
						ExpectedBackstopHit);
				Driver->TickComponent(0.016f, LEVELTICK_All, nullptr);
				const float ExpectedCap = FMath::Max(ExpectedBackstopHit.Distance, 100.0f);
				bValid &= Test->TestTrue(
					TEXT("The ship governor's exact terrain backstop query succeeds"),
					ExpectedBackstopResult == ERedPlanetTerrainQueryResult::Hit);
				bValid &= Test->TestTrue(
					TEXT("The ship governor brakes from terrain distance, not the closer blocker"),
					ExpectedBackstopResult == ERedPlanetTerrainQueryResult::Hit
						&& FMath::IsNearlyEqual(Driver->QuerySpeedCap(), ExpectedCap, 2.0f));
			}

			if (Movement)
			{
				bValid &= ValidateShipRootPhysicalSweep(
					Ship, Movement, BaselineTerrainHit, RadialUp);
			}

			if (PassiveShip.Get() != Ship)
			{
				Ship->Destroy();
			}
			Shuttle->Destroy();
			return bValid;
		}

		bool ValidateShipRootPhysicalSweep(
			ARedShip* Ship,
			URedShipMovementComponent* Movement,
			const FHitResult& BaselineTerrainHit,
			const FVector& RadialUp)
		{
			UWorld* TestWorld = World.Get();
			ACLMPlanet* TestPlanet = Planet.Get();
			UBoxComponent* DynamicBlocker = WorldDynamicBlocker.Get();
			USphereComponent* RootSphere = Ship
				? Cast<USphereComponent>(Ship->GetRootComponent())
				: nullptr;
			bool bValid = true;
			bValid &= Test->TestNotNull(
				TEXT("The physical ship fixture uses its production sphere root"), RootSphere);
			if (!TestWorld || !TestPlanet || !DynamicBlocker || !Ship || !Movement || !RootSphere)
			{
				return false;
			}

			Ship->SetActorEnableCollision(true);
			RootSphere->SetCollisionEnabled(ECollisionEnabled::QueryAndPhysics);
			RootSphere->UpdateBounds();
			RootSphere->UpdateOverlaps();
			Movement->SetUpdatedComponent(RootSphere);
			Movement->Velocity = FVector::ZeroVector;

			const float RootRadius = RootSphere->GetScaledSphereRadius();
			bValid &= Test->TestTrue(
				TEXT("The production ship root radius is 260 cm"),
				FMath::IsNearlyEqual(RootRadius, 260.0f, 0.1f));
			bValid &= Test->TestEqual(
				TEXT("The production ship root uses QueryAndPhysics"),
				RootSphere->GetCollisionEnabled(), ECollisionEnabled::QueryAndPhysics);
			bValid &= Test->TestTrue(
				TEXT("The production ship root has a physics state"),
				RootSphere->IsPhysicsStateCreated());
			bValid &= Test->TestEqual(
				TEXT("The production ship root is Vehicle collision"),
				RootSphere->GetCollisionObjectType(), ECC_Vehicle);
			bValid &= Test->TestEqual(
				TEXT("The production ship root ignores generic WorldDynamic actors"),
				RootSphere->GetCollisionResponseToChannel(ECC_WorldDynamic), ECR_Ignore);
			bValid &= Test->TestEqual(
				TEXT("The production ship root preserves native WorldStatic blocking"),
				RootSphere->GetCollisionResponseToChannel(ECC_WorldStatic), ECR_Block);
			const FVector SurfacePoint = BaselineTerrainHit.ImpactPoint;
			const FVector Start = SurfacePoint + RadialUp * (RootRadius + 5000.0f);
			// Continue far enough beneath the near surface that the existing hemisphere helper's
			// Time < 0.5 contract remains meaningful without tracing through the whole planet.
			const FVector End = SurfacePoint - RadialUp * (RootRadius + 10000.0f);
			const FVector Delta = End - Start;
			const FQuat Rotation = Ship->GetActorQuat();
			const FCollisionShape RootShape = FCollisionShape::MakeSphere(RootRadius);
			DynamicBlocker->SetWorldLocation(
				SurfacePoint + RadialUp * 2500.0f,
				false, nullptr, ETeleportType::TeleportPhysics);
			DynamicBlocker->UpdateBounds();
			DynamicBlocker->UpdateOverlaps();

			FHitResult ExactTerrainHit(1.0f);
			FIntVector ExactTerrainKey;
			const ERedPlanetTerrainQueryResult ExactTerrainResult =
				RedPlanetTerrainQuery::Sweep(
					TestWorld,
					TestPlanet->GetActorLocation(),
					Start,
					End,
					Rotation,
					RootShape,
					ExactTerrainHit,
					&ExactTerrainKey);
			bValid &= Test->TestTrue(
				TEXT("The production root-radius exact terrain sweep hits the cooked seam"),
				ExactTerrainResult == ERedPlanetTerrainQueryResult::Hit
					&& ExactTerrainHit.bBlockingHit);
			bValid &= ValidateActiveTerrainHit(
				TEXT("Production root-radius seam sweep"),
				ExactTerrainHit,
				ExactTerrainKey,
				SeamDirection);

			FCollisionQueryParams RawDynamicParams(
				SCENE_QUERY_STAT(RedShipPhysicalWorldDynamicControl), true);
			RawDynamicParams.AddIgnoredActor(Ship);
			FHitResult RawDynamicHit(1.0f);
			const bool bRawDynamicHit = TestWorld->SweepSingleByObjectType(
				RawDynamicHit,
				Start,
				End,
				Rotation,
				FCollisionObjectQueryParams(ECC_WorldDynamic),
				RootShape,
				RawDynamicParams);
			bValid &= Test->TestTrue(
				TEXT("A raw root-radius WorldDynamic sweep sees the deliberate closer blocker"),
				bRawDynamicHit && RawDynamicHit.GetComponent() == DynamicBlocker);
			bValid &= Test->TestTrue(
				TEXT("The generic dynamic blocker is closer than exact terrain"),
				bRawDynamicHit && ExactTerrainHit.bBlockingHit
					&& RawDynamicHit.Distance < ExactTerrainHit.Distance);

			FActorSpawnParameters StaticSpawnParameters;
			StaticSpawnParameters.ObjectFlags |= RF_Transient;
			StaticSpawnParameters.Name = MakeUniqueObjectName(
				TestWorld, AActor::StaticClass(), TEXT("RED_ShipPhysicalWorldStaticControl"));
			AActor* StaticActor = TestWorld->SpawnActor<AActor>(
				AActor::StaticClass(), FTransform::Identity, StaticSpawnParameters);
			UBoxComponent* StaticWall = StaticActor
				? NewObject<UBoxComponent>(
					StaticActor, TEXT("RED_ShipPhysicalWorldStaticBox"), RF_Transient)
				: nullptr;
			bValid &= Test->TestNotNull(
				TEXT("The native WorldStatic ship control spawns"), StaticWall);
			if (StaticActor && StaticWall)
			{
				StaticActor->SetRootComponent(StaticWall);
				StaticActor->AddInstanceComponent(StaticWall);
				StaticWall->SetBoxExtent(FVector(1000.0f, 1000.0f, 100.0f), false);
				StaticWall->SetCollisionEnabled(ECollisionEnabled::QueryAndPhysics);
				StaticWall->SetCollisionObjectType(ECC_WorldStatic);
				StaticWall->SetCollisionResponseToAllChannels(ECR_Ignore);
				StaticWall->SetCollisionResponseToChannel(ECC_Vehicle, ECR_Block);
				StaticWall->SetGenerateOverlapEvents(false);
				StaticWall->RegisterComponent();
				StaticWall->SetWorldTransform(FTransform(
					FRotationMatrix::MakeFromZ(RadialUp).ToQuat(),
					SurfacePoint + RadialUp * 1500.0f));
				StaticWall->UpdateBounds();
				StaticWall->UpdateOverlaps();

				Ship->SetActorLocation(Start, false, nullptr, ETeleportType::TeleportPhysics);
				FHitResult NativeStaticHit(1.0f);
				RootSphere->MoveComponent(
					Delta, Rotation, true, &NativeStaticHit,
					MOVECOMP_NoFlags, ETeleportType::None);
				const FVector NativeStaticLocation = RootSphere->GetComponentLocation();
				bValid &= Test->TestTrue(
					TEXT("Native ship movement stops on the WorldStatic control"),
					NativeStaticHit.bBlockingHit
						&& NativeStaticHit.GetComponent() == StaticWall);

				Ship->SetActorLocation(Start, false, nullptr, ETeleportType::TeleportPhysics);
				Movement->Velocity = FVector::ZeroVector;
				FHitResult HybridStaticHit(1.0f);
				Movement->SafeMoveUpdatedComponent(Delta, Rotation, true, HybridStaticHit);
				bValid &= Test->TestTrue(
					TEXT("Terrain-aware ship movement preserves the nearer native WorldStatic hit"),
					HybridStaticHit.bBlockingHit
						&& HybridStaticHit.GetComponent() == StaticWall);
				bValid &= Test->TestTrue(
					TEXT("The native static hit lies between the distractor and terrain"),
					bRawDynamicHit && NativeStaticHit.bBlockingHit
						&& RawDynamicHit.Distance < NativeStaticHit.Distance
						&& NativeStaticHit.Distance < ExactTerrainHit.Distance);
				UE_LOG(LogTemp, Display,
					TEXT("RED_SHIP_PHYSICAL_STATIC nativeTime=%.6f hybridTime=%.6f nativeDist=%.3f hybridDist=%.3f fullDist=%.3f"),
					NativeStaticHit.Time,
					HybridStaticHit.Time,
					NativeStaticHit.Distance,
					HybridStaticHit.Distance,
					Delta.Size());
				bValid &= Test->TestTrue(
					TEXT("The hybrid path preserves native static hit time in full-delta space"),
					FMath::IsNearlyEqual(HybridStaticHit.Time, NativeStaticHit.Time, 1.0e-3f));
				bValid &= Test->TestTrue(
					TEXT("The hybrid path stays within the conservative native pullback bound"),
					FVector::Dist(
						RootSphere->GetComponentLocation(), NativeStaticLocation) <= 20.0f);
			}

			if (StaticWall)
			{
				StaticWall->SetCollisionEnabled(ECollisionEnabled::NoCollision);
			}
			if (StaticActor)
			{
				StaticActor->Destroy();
			}

			Ship->SetActorLocation(Start, false, nullptr, ETeleportType::TeleportPhysics);
			Movement->Velocity = FVector::ZeroVector;
			FHitResult PhysicalTerrainHit(1.0f);
			Movement->SafeMoveUpdatedComponent(Delta, Rotation, true, PhysicalTerrainHit);
			const FVector PhysicalFinalLocation = RootSphere->GetComponentLocation();
			bValid &= Test->TestTrue(
				TEXT("The production ship root physically stops on exact active terrain"),
				PhysicalTerrainHit.bBlockingHit
					&& !PhysicalTerrainHit.bStartPenetrating
					&& PhysicalTerrainHit.GetComponent() == ExactTerrainHit.GetComponent()
					&& PhysicalTerrainHit.GetComponent() != DynamicBlocker);
			bValid &= Test->TestTrue(
				TEXT("The physical terrain hit preserves exact full-sweep time"),
				FMath::IsNearlyEqual(PhysicalTerrainHit.Time, ExactTerrainHit.Time, 1.0e-4f));
			bValid &= Test->TestTrue(
				TEXT("The physical terrain hit preserves exact distance"),
				FMath::IsNearlyEqual(
					PhysicalTerrainHit.Distance, ExactTerrainHit.Distance, 2.0f));
			bValid &= Test->TestTrue(
				TEXT("The physical terrain hit preserves exact root location"),
				FVector::Dist(PhysicalTerrainHit.Location, ExactTerrainHit.Location) <= 2.0f
					&& FVector::Dist(PhysicalFinalLocation, ExactTerrainHit.Location) <= 2.0f);
			bValid &= Test->TestTrue(
				TEXT("The physical terrain hit preserves exact impact point"),
				FVector::Dist(
					PhysicalTerrainHit.ImpactPoint, ExactTerrainHit.ImpactPoint) <= 2.0f);
			bValid &= Test->TestTrue(
				TEXT("The physical terrain hit preserves the original trace endpoints"),
				PhysicalTerrainHit.TraceStart.Equals(Start, 1.0f)
					&& PhysicalTerrainHit.TraceEnd.Equals(End, 1.0f));
			bValid &= Test->TestTrue(
				TEXT("The physical ship root remains outside the terrain surface"),
				FVector::DotProduct(
					PhysicalFinalLocation - PhysicalTerrainHit.ImpactPoint,
					PhysicalTerrainHit.ImpactNormal) >= RootRadius - 2.0f);
			bValid &= Test->TestTrue(
				TEXT("The physical seam contact has an outward terrain normal"),
				FVector::DotProduct(PhysicalTerrainHit.ImpactNormal, RadialUp) > 0.5f);
			bValid &= Test->TestTrue(
				TEXT("The physical seam move never exceeds its requested displacement"),
				FVector::Dist(Start, PhysicalFinalLocation) <= Delta.Size() + 1.0f);

			// Prove that the production movement path can recover from an initial exact-terrain
			// overlap at the active +X/+Y cube seam. This is intentionally one SafeMove call:
			// test-side retries would hide an incomplete production depenetration path.
			constexpr float InitialEmbedDepthCm = 50.0f;
			constexpr float InitialTangentDistanceCm = 100.0f;
			constexpr int32 InitialOverlapRepeatCount = 4;
			const FVector ContactOut =
				(ExactTerrainHit.Location - ExactTerrainHit.ImpactPoint).GetSafeNormal();
			const FVector PenetratingStart =
				ExactTerrainHit.Location - ContactOut * InitialEmbedDepthCm;
			const FVector TangentReference =
				FMath::Abs(FVector::DotProduct(ContactOut, FVector::UpVector)) < 0.9f
					? FVector::UpVector
					: FVector::ForwardVector;
			const FVector TangentDirection =
				FVector::CrossProduct(ContactOut, TangentReference).GetSafeNormal();
			const FVector RequestedDelta =
				TangentDirection * InitialTangentDistanceCm;
			bValid &= Test->TestTrue(
				TEXT("The exact seam contact supplies a finite outward direction"),
				!ContactOut.ContainsNaN()
					&& !ContactOut.IsNearlyZero()
					&& FVector::DotProduct(ContactOut, RadialUp) > 0.5f
					&& !TangentDirection.ContainsNaN()
					&& !TangentDirection.IsNearlyZero()
					&& FMath::Abs(FVector::DotProduct(
						RequestedDelta, ContactOut)) <= 0.5f);

			FHitResult InitialOverlapHit(1.0f);
			FIntVector InitialOverlapKey(INDEX_NONE, INDEX_NONE, INDEX_NONE);
			for (int32 RepeatIndex = 0;
				RepeatIndex < InitialOverlapRepeatCount;
				++RepeatIndex)
			{
				FHitResult RepeatHit(1.0f);
				FIntVector RepeatKey(INDEX_NONE, INDEX_NONE, INDEX_NONE);
				const ERedPlanetTerrainQueryResult RepeatResult =
					RedPlanetTerrainQuery::Sweep(
						TestWorld,
						TestPlanet->GetActorLocation(),
						PenetratingStart,
						PenetratingStart,
						Rotation,
						RootShape,
						RepeatHit,
						&RepeatKey);
				bValid &= Test->TestTrue(
					FString::Printf(
						TEXT("Initial exact seam overlap repeat %d reports penetration"),
						RepeatIndex),
					RepeatResult == ERedPlanetTerrainQueryResult::Hit
						&& RepeatHit.bBlockingHit
						&& RepeatHit.bStartPenetrating);
				bValid &= Test->TestTrue(
					FString::Printf(
						TEXT("Initial exact seam overlap repeat %d starts at time zero"),
						RepeatIndex),
					FMath::IsNearlyZero(RepeatHit.Time, 1.0e-6f)
						&& RepeatHit.Distance <= 0.01f
						&& FVector::Dist(RepeatHit.Location, PenetratingStart) <= 1.0f);
				bValid &= Test->TestTrue(
					FString::Printf(
						TEXT("Initial exact seam overlap repeat %d has a bounded outward MTD"),
						RepeatIndex),
					RepeatHit.PenetrationDepth >= 5.0f
						&& RepeatHit.PenetrationDepth <= 75.0f
						&& FVector::DotProduct(RepeatHit.Normal, ContactOut) > 0.99f
						&& FVector::DotProduct(RepeatHit.Normal, RadialUp) > 0.5f);
				bValid &= ValidateActiveTerrainHit(
					FString::Printf(
						TEXT("Initial production ship overlap repeat %d"),
						RepeatIndex),
					RepeatHit,
					RepeatKey,
					SeamDirection);

				if (RepeatIndex == 0)
				{
					InitialOverlapHit = RepeatHit;
					InitialOverlapKey = RepeatKey;
				}
				else
				{
					bValid &= Test->TestTrue(
						TEXT("Repeated exact seam overlaps choose one deterministic chunk"),
						RepeatKey == InitialOverlapKey
							&& RepeatHit.GetComponent()
								== InitialOverlapHit.GetComponent());
					bValid &= Test->TestTrue(
						TEXT("Repeated exact seam overlaps preserve depth and normal"),
						FMath::IsNearlyEqual(
							RepeatHit.PenetrationDepth,
							InitialOverlapHit.PenetrationDepth,
							0.01f)
							&& FVector::DotProduct(
								RepeatHit.Normal,
								InitialOverlapHit.Normal) > 0.9999f);
				}
			}

			const FVector ExpectedInitialAdjustment =
				Movement->GetPenetrationAdjustment(InitialOverlapHit);
			bValid &= Test->TestTrue(
				TEXT("The production movement component computes a finite exact-terrain MTD"),
				!ExpectedInitialAdjustment.ContainsNaN()
					&& !ExpectedInitialAdjustment.IsNearlyZero()
					&& FVector::DotProduct(
						ExpectedInitialAdjustment.GetSafeNormal(),
						InitialOverlapHit.Normal) > 0.999f
					&& ExpectedInitialAdjustment.Size()
						>= InitialOverlapHit.PenetrationDepth
					&& ExpectedInitialAdjustment.Size()
						<= InitialOverlapHit.PenetrationDepth + 1.0f);

			Ship->SetActorLocation(
				PenetratingStart, false, nullptr, ETeleportType::TeleportPhysics);
			RootSphere->UpdateBounds();
			RootSphere->UpdateOverlaps();
			Movement->Velocity = FVector::ZeroVector;
			FHitResult ResolvedHit(1.0f);
			const bool bResolvedMove = Movement->SafeMoveUpdatedComponent(
				RequestedDelta, Rotation, true, ResolvedHit);
			const FVector ResolvedLocation = RootSphere->GetComponentLocation();
			const float OutwardDisplacement = FVector::DotProduct(
				ResolvedLocation - PenetratingStart, ContactOut);
			const float TangentDisplacement = FVector::DotProduct(
				ResolvedLocation - PenetratingStart, TangentDirection);
			const FVector ExpectedResolvedLocation = PenetratingStart
				+ ExpectedInitialAdjustment + RequestedDelta;
			bValid &= Test->TestTrue(
				TEXT("One production SafeMove resolves and retries the initial seam overlap"),
				bResolvedMove
					&& !ResolvedHit.bStartPenetrating
					&& !ResolvedHit.bBlockingHit
					&& FMath::IsNearlyEqual(ResolvedHit.Time, 1.0f, 1.0e-6f));
			bValid &= Test->TestTrue(
				TEXT("Initial-overlap recovery leaves the actor and root synchronized"),
				!ResolvedLocation.ContainsNaN()
					&& FVector::Dist(
						Ship->GetActorLocation(), ResolvedLocation) <= 1.0f);
			bValid &= Test->TestTrue(
				TEXT("Initial-overlap recovery applies the MTD without discarding the tangent move"),
				OutwardDisplacement
					>= ExpectedInitialAdjustment.Size() - 2.0f
					&& FMath::IsNearlyEqual(
						TangentDisplacement, InitialTangentDistanceCm, 2.0f)
					&& FVector::Dist(
						ResolvedLocation, ExpectedResolvedLocation) <= 5.0f
					&& FVector::Dist(PenetratingStart, ResolvedLocation) <= 400.0f);

			FHitResult FinalOverlapProbe(1.0f);
			const ERedPlanetTerrainQueryResult FinalProbeResult =
				RedPlanetTerrainQuery::Sweep(
					TestWorld,
					TestPlanet->GetActorLocation(),
					ResolvedLocation,
					ResolvedLocation + ContactOut,
					Rotation,
					RootShape,
					FinalOverlapProbe);
			bValid &= Test->TestTrue(
				TEXT("The recovered ship root is not penetrating any exact active terrain"),
				FinalProbeResult != ERedPlanetTerrainQueryResult::NoMatchingPlanet
					&& !FinalOverlapProbe.bStartPenetrating);
			if (bValid)
			{
				UE_LOG(LogTemp, Display,
					TEXT("RED_SHIP_INITIAL_OVERLAP_PASS repeats=%d depth_cm=%.6f initial_adjustment_cm=%.6f outward_displacement_cm=%.6f tangent_displacement_cm=%.6f endpoint_error_cm=%.6f final_probe=%d"),
					InitialOverlapRepeatCount,
					InitialOverlapHit.PenetrationDepth,
					ExpectedInitialAdjustment.Size(),
					OutwardDisplacement,
					TangentDisplacement,
					FVector::Dist(ResolvedLocation, ExpectedResolvedLocation),
					static_cast<int32>(FinalProbeResult));
			}

			if (bValid)
			{
				bValid &= PreparePassiveZeroInputShip(
					Ship,
					Movement,
					RootSphere,
					PenetratingStart,
					Rotation,
					RootShape,
					ContactOut,
					TangentDirection,
					InitialOverlapHit,
					ExpectedInitialAdjustment,
					InitialOverlapRepeatCount);
			}
			if (!bValid)
			{
				Ship->SetActorEnableCollision(false);
			}
			return bValid;
		}

		bool PreparePassiveZeroInputShip(
			ARedShip* Ship,
			URedShipMovementComponent* Movement,
			USphereComponent* RootSphere,
			const FVector& PenetratingStart,
			const FQuat& Rotation,
			const FCollisionShape& RootShape,
			const FVector& ContactOut,
			const FVector& TangentDirection,
			const FHitResult& InitialOverlapHit,
			const FVector& ExpectedAdjustment,
			int32 RepeatCount)
		{
			UWorld* TestWorld = World.Get();
			ACLMPlanet* TestPlanet = Planet.Get();
			bool bValid = true;
			bValid &= Test->TestNotNull(
				TEXT("The passive zero-input fixture retains its production ship"), Ship);
			bValid &= Test->TestNotNull(
				TEXT("The passive zero-input fixture retains its production movement component"),
				Movement);
			bValid &= Test->TestNotNull(
				TEXT("The passive zero-input fixture retains its production root sphere"),
				RootSphere);
			bValid &= Test->TestTrue(
				TEXT("The passive zero-input fixture has a valid PIE world and planet"),
				TestWorld && TestPlanet);
			bValid &= Test->TestTrue(
				TEXT("Only one passive zero-input fixture is prepared"),
				!PassiveShip.IsValid());
			if (!bValid || !TestWorld || !TestPlanet || !Ship || !Movement || !RootSphere)
			{
				return false;
			}

			Ship->SetActorTickEnabled(false);
			TArray<UActorComponent*> ShipComponents;
			Ship->GetComponents(ShipComponents);
			for (UActorComponent* Component : ShipComponents)
			{
				if (Component)
				{
					Component->SetComponentTickEnabled(false);
				}
				if (UPrimitiveComponent* Primitive = Cast<UPrimitiveComponent>(Component);
					Primitive && Primitive != RootSphere)
				{
					Primitive->SetCollisionEnabled(ECollisionEnabled::NoCollision);
				}
			}

			Ship->SetActorEnableCollision(true);
			RootSphere->SetCollisionEnabled(ECollisionEnabled::QueryAndPhysics);
			RootSphere->SetGenerateOverlapEvents(false);
			Movement->SetUpdatedComponent(RootSphere);
			Movement->PlanetCenter = TestPlanet->GetActorLocation();
			Movement->PlanetRadius = TestPlanet->PlanetRadius;
			// Keep the legacy analytic datum clamp safely below this authored terrain overlap.
			// That makes a missing exact-terrain correction fail instead of producing a false pass.
			Movement->MinimumSurfaceClearance = 1.0f;
			Movement->Velocity = FVector::ZeroVector;

			Ship->SetActorLocation(
				PenetratingStart, false, nullptr, ETeleportType::TeleportPhysics);
			RootSphere->UpdateBounds();
			RootSphere->UpdateOverlaps();

			FHitResult PreparedOverlapHit(1.0f);
			const ERedPlanetTerrainQueryResult PreparedOverlapResult =
				RedPlanetTerrainQuery::Sweep(
					TestWorld,
					TestPlanet->GetActorLocation(),
					PenetratingStart,
					PenetratingStart,
					Rotation,
					RootShape,
					PreparedOverlapHit);
			bValid &= Test->TestTrue(
				TEXT("The passive fixture begins inside exact active terrain"),
				PreparedOverlapResult == ERedPlanetTerrainQueryResult::Hit
					&& PreparedOverlapHit.bBlockingHit
					&& PreparedOverlapHit.bStartPenetrating);
			bValid &= Test->TestTrue(
				TEXT("The passive fixture begins above the analytic datum clamp"),
				FVector::Dist(PenetratingStart, TestPlanet->GetActorLocation())
					> TestPlanet->PlanetRadius
						+ Movement->MinimumSurfaceClearance + 10.0f);
			bValid &= Test->TestTrue(
				TEXT("The passive fixture is authoritative, unpossessed, and has zero input"),
				Ship->HasAuthority()
					&& Ship->GetController() == nullptr
					&& Movement->GetLastMoveInput().IsNearlyZero()
					&& Movement->GetLastRotationInput().IsNearlyZero()
					&& Movement->Velocity.IsNearlyZero());
			bValid &= Test->TestTrue(
				TEXT("The passive fixture preserves the deterministic overlap MTD"),
				FMath::IsNearlyEqual(
					PreparedOverlapHit.PenetrationDepth,
					InitialOverlapHit.PenetrationDepth,
					0.01f)
					&& FVector::DotProduct(
						PreparedOverlapHit.Normal,
						InitialOverlapHit.Normal) > 0.9999f);
			if (!bValid)
			{
				Ship->SetActorEnableCollision(false);
				RootSphere->SetCollisionEnabled(ECollisionEnabled::NoCollision);
				return false;
			}

			PassiveShip = Ship;
			PassiveMovement = Movement;
			PassiveRootSphere = RootSphere;
			PassiveRootShape = RootShape;
			PassiveRotation = Rotation;
			PassivePenetratingStart = PenetratingStart;
			PassiveExpectedAdjustment = ExpectedAdjustment;
			PassiveContactOut = ContactOut;
			PassiveTangentDirection = TangentDirection;
			PassiveOverlapRepeatCount = RepeatCount;
			PassiveInitialDepthCm = InitialOverlapHit.PenetrationDepth;

			// Enable only the production movement component. The latent phase observes actual PIE
			// world ticks; no test-side TickComponent call is permitted to clear the overlap.
			Movement->SetComponentTickEnabled(true);
			return true;
		}

		bool ValidateActiveTerrainHit(
			const FString& Label,
			const FHitResult& Hit,
			const FIntVector& ChunkKey,
			const FVector& ExpectedSide) const
		{
			ACLMPlanet* TestPlanet = Planet.Get();
			ACLMPlanetChunk* Chunk = Cast<ACLMPlanetChunk>(Hit.GetActor());
			UProceduralMeshComponent* Mesh =
				Chunk ? Chunk->FindComponentByClass<UProceduralMeshComponent>() : nullptr;
			bool bValid = true;
			bValid &= Test->TestTrue(Label + TEXT(" reports a blocking hit"), Hit.bBlockingHit);
			bValid &= Test->TestNotNull(Label + TEXT(" reports an ACLMPlanetChunk"), Chunk);
			bValid &= Test->TestTrue(
				Label + TEXT(" chunk is owned by the queried planet"),
				Chunk && Chunk->GetOwner() == TestPlanet);
			bValid &= Test->TestTrue(
				Label + TEXT(" chunk is active and fully built"),
				Chunk && Chunk->bActive && !Chunk->bBuilding);
			bValid &= Test->TestTrue(
				Label + TEXT(" chunk has terrain collision enabled"),
				Chunk && Chunk->IsTerrainCollisionEnabled());
			bValid &= Test->TestNotNull(Label + TEXT(" chunk has a procedural terrain mesh"), Mesh);
			bValid &= Test->TestTrue(
				Label + TEXT(" reports the exact owned procedural mesh"),
				Mesh && Hit.GetComponent() == Mesh);
			bValid &= Test->TestTrue(
				Label + TEXT(" ignores the arbitrary WorldDynamic blocker"),
				Hit.GetComponent() != WorldDynamicBlocker.Get());
			if (Mesh)
			{
				bValid &= Test->TestEqual(
					Label + TEXT(" mesh uses QueryAndPhysics collision"),
					Mesh->GetCollisionEnabled(), ECollisionEnabled::QueryAndPhysics);
				bValid &= Test->TestEqual(
					Label + TEXT(" mesh remains WorldDynamic"),
					Mesh->GetCollisionObjectType(), ECC_WorldDynamic);
				bValid &= Test->TestTrue(
					Label + TEXT(" mesh has a created physics state"),
					Mesh->IsPhysicsStateCreated());
				bValid &= Test->TestNotNull(
					Label + TEXT(" mesh retains its cooked surface section"),
					Mesh->GetProcMeshSection(0));
			}
			if (Chunk && TestPlanet)
			{
				bValid &= Test->TestTrue(
					Label + TEXT(" returns the exact active chunk key"),
					Private::ResolveActorChunkKey(TestPlanet, Chunk) == ChunkKey);
			}

			const FVector ImpactDirection = TestPlanet
				? (Hit.ImpactPoint - TestPlanet->GetActorLocation()).GetSafeNormal()
				: FVector::ZeroVector;
			bValid &= Test->TestTrue(
				Label + TEXT(" returns the nearest cooked hemisphere"),
				FVector::DotProduct(ImpactDirection, ExpectedSide.GetSafeNormal()) > 0.9f
					&& Hit.Time < 0.5f);
			return bValid;
		}

		bool ValidateStableLineSelection(
			const FHitResult& BaselineHit,
			const FIntVector& BaselineKey) const
		{
			bool bStable = true;
			for (int32 Repeat = 0; Repeat < 32; ++Repeat)
			{
				FHitResult RepeatedHit;
				FIntVector RepeatedKey;
				const bool bHit = Planet->LineTraceActiveTerrain(
					RepeatedHit, PositiveStart, NegativeStart, &RepeatedKey);
				bStable &= bHit
					&& RepeatedKey == BaselineKey
					&& RepeatedHit.GetActor() == BaselineHit.GetActor()
					&& RepeatedHit.GetComponent() == BaselineHit.GetComponent()
					&& FMath::IsNearlyEqual(RepeatedHit.Distance, BaselineHit.Distance, 0.01f);
			}
			return Test->TestTrue(
				TEXT("Repeated exact-seam active-terrain line traces select one stable component/key"),
				bStable);
		}

		bool ValidateStableSweepSelection(
			const FString& ShapeLabel,
			const FHitResult& BaselineHit,
			const FIntVector& BaselineKey,
			const FCollisionShape& SweepShape,
			const FQuat& SweepRotation) const
		{
			bool bStable = true;
			for (int32 Repeat = 0; Repeat < 8; ++Repeat)
			{
				FHitResult RepeatedHit;
				FIntVector RepeatedKey;
				const bool bHit = Planet->SweepActiveTerrain(
					RepeatedHit, PositiveStart, NegativeStart, SweepRotation,
					SweepShape, &RepeatedKey);
				bStable &= bHit
					&& RepeatedKey == BaselineKey
					&& RepeatedHit.GetActor() == BaselineHit.GetActor()
					&& RepeatedHit.GetComponent() == BaselineHit.GetComponent()
					&& FMath::IsNearlyEqual(RepeatedHit.Distance, BaselineHit.Distance, 0.01f);
			}
			return Test->TestTrue(
				*FString::Printf(
					TEXT("Repeated exact-seam active-terrain %s sweeps select one stable component/key"),
					*ShapeLabel),
				bStable);
		}

		bool ValidateRotatedBoxCandidateExpansion(
			const FHitResult& BaselineHit,
			const FIntVector& BaselineKey,
			const FCollisionShape& BoxShape,
			const FVector& BoxHalfExtent,
			const FQuat& BoxRotation)
		{
			UWorld* TestWorld = World.Get();
			ACLMPlanet* TestPlanet = Planet.Get();
			UProceduralMeshComponent* TargetMesh =
				Cast<UProceduralMeshComponent>(BaselineHit.GetComponent());
			if (!TestWorld || !TestPlanet || !TargetMesh)
			{
				return Test->TestTrue(
					TEXT("The rotated-box candidate-expansion fixture remains valid"), false);
			}

			const FVector RotatedWorldExtent =
				BoxRotation.GetAxisX().GetAbs() * BoxHalfExtent.X
				+ BoxRotation.GetAxisY().GetAbs() * BoxHalfExtent.Y
				+ BoxRotation.GetAxisZ().GetAbs() * BoxHalfExtent.Z;
			const FVector ExpansionGain = RotatedWorldExtent - BoxHalfExtent;
			TArray<int32> CandidateAxes = {0, 1, 2};
			CandidateAxes.Sort([&ExpansionGain](const int32 A, const int32 B)
			{
				return ExpansionGain[A] > ExpansionGain[B];
			});

			const float SavedBoundsScale = TargetMesh->BoundsScale;
			TargetMesh->SetBoundsScale(1.0f);
			const FBox TightBounds = TargetMesh->Bounds.GetBox();
			const FBox NaiveExpandedBounds = TightBounds.ExpandBy(BoxHalfExtent);
			const FBox RotatedExpandedBounds = TightBounds.ExpandBy(RotatedWorldExtent);
			const FVector ContactOut =
				(BaselineHit.Location - BaselineHit.ImpactPoint).GetSafeNormal();
			const FVector EmbeddedCenter = BaselineHit.Location - ContactOut * 50.0f;

			bool bFound = false;
			bool bRawTargetOverlap = false;
			bool bStable = false;
			bool bOutsideRawBounds = false;
			bool bOutsideNaiveBounds = false;
			bool bInsideRotatedBounds = false;
			int32 SelectedAxis = INDEX_NONE;
			int32 SelectedSide = 0;
			float SelectedMarginCm = 0.0f;
			FVector SelectedCenter = FVector::ZeroVector;
			FHitResult SelectedHit;
			FIntVector SelectedKey(INDEX_NONE, INDEX_NONE, INDEX_NONE);
			const TArray<float> MarginsCm = {5.0f, 25.0f, 50.0f};

			for (const int32 Axis : CandidateAxes)
			{
				if (ExpansionGain[Axis] <= MarginsCm[0] + 1.0f)
				{
					continue;
				}

				const double PositiveBoundaryDistance = FMath::Abs(
					TightBounds.Max[Axis] - BaselineHit.ImpactPoint[Axis]);
				const double NegativeBoundaryDistance = FMath::Abs(
					BaselineHit.ImpactPoint[Axis] - TightBounds.Min[Axis]);
				const int32 PreferredSide = PositiveBoundaryDistance <= NegativeBoundaryDistance
					? 1
					: -1;

				for (int32 SidePass = 0; SidePass < 2 && !bFound; ++SidePass)
				{
					const int32 Side = SidePass == 0 ? PreferredSide : -PreferredSide;
					for (const float MarginCm : MarginsCm)
					{
						if (MarginCm >= ExpansionGain[Axis] - 1.0f)
						{
							continue;
						}

						FVector CandidateCenter = EmbeddedCenter;
						CandidateCenter[Axis] = Side > 0
							? TightBounds.Max[Axis] + BoxHalfExtent[Axis] + MarginCm
							: TightBounds.Min[Axis] - BoxHalfExtent[Axis] - MarginCm;
						const bool bCandidateOutsideRaw = !TightBounds.IsInsideOrOn(CandidateCenter);
						const bool bCandidateOutsideNaive =
							!NaiveExpandedBounds.IsInsideOrOn(CandidateCenter);
						const bool bCandidateInsideRotated =
							RotatedExpandedBounds.IsInsideOrOn(CandidateCenter);
						if (!bCandidateOutsideRaw
							|| !bCandidateOutsideNaive
							|| !bCandidateInsideRotated)
						{
							continue;
						}

						FCollisionQueryParams RawParams(
							SCENE_QUERY_STAT(RedFusedRotatedBoxCandidateExpansionRaw), true);
						RawParams.bTraceComplex = true;
						RawParams.bFindInitialOverlaps = true;
						if (WorldDynamicBlocker.IsValid())
						{
							RawParams.AddIgnoredComponent(WorldDynamicBlocker.Get());
						}
						TArray<FHitResult> RawHits;
						TestWorld->SweepMultiByObjectType(
							RawHits,
							CandidateCenter,
							CandidateCenter,
							BoxRotation,
							FCollisionObjectQueryParams(ECC_WorldDynamic),
							BoxShape,
							RawParams);
						const bool bCandidateRawTargetOverlap = RawHits.ContainsByPredicate(
							[TargetMesh](const FHitResult& Hit)
							{
								return Hit.GetComponent() == TargetMesh
									&& Hit.bBlockingHit
									&& Hit.bStartPenetrating;
							});
						if (!bCandidateRawTargetOverlap)
						{
							continue;
						}

						FHitResult CandidateHit;
						FIntVector CandidateKey(INDEX_NONE, INDEX_NONE, INDEX_NONE);
						const bool bCandidateHit = TestPlanet->SweepActiveTerrain(
							CandidateHit,
							CandidateCenter,
							CandidateCenter,
							BoxRotation,
							BoxShape,
							&CandidateKey);
						if (!bCandidateHit
							|| !CandidateHit.bBlockingHit
							|| !CandidateHit.bStartPenetrating
							|| CandidateHit.GetComponent() != TargetMesh
							|| CandidateKey != BaselineKey)
						{
							continue;
						}

						bFound = true;
						bRawTargetOverlap = true;
						bOutsideRawBounds = bCandidateOutsideRaw;
						bOutsideNaiveBounds = bCandidateOutsideNaive;
						bInsideRotatedBounds = bCandidateInsideRotated;
						SelectedAxis = Axis;
						SelectedSide = Side;
						SelectedMarginCm = MarginCm;
						SelectedCenter = CandidateCenter;
						SelectedHit = CandidateHit;
						SelectedKey = CandidateKey;

						bStable = true;
						for (int32 Repeat = 0; Repeat < 8; ++Repeat)
						{
							FHitResult RepeatedHit;
							FIntVector RepeatedKey(INDEX_NONE, INDEX_NONE, INDEX_NONE);
							const bool bRepeatedHit = TestPlanet->SweepActiveTerrain(
								RepeatedHit,
								CandidateCenter,
								CandidateCenter,
								BoxRotation,
								BoxShape,
								&RepeatedKey);
							bStable &= bRepeatedHit
								&& RepeatedHit.bBlockingHit
								&& RepeatedHit.bStartPenetrating
								&& FMath::IsNearlyZero(RepeatedHit.Time, 1.0e-6f)
								&& RepeatedHit.GetComponent() == TargetMesh
								&& RepeatedKey == BaselineKey;
						}
						break;
					}
				}
				if (bFound)
				{
					break;
				}
			}

			TargetMesh->SetBoundsScale(SavedBoundsScale);

			bool bValid = true;
			bValid &= Test->TestTrue(
				TEXT("The rotated box has an axis whose world expansion exceeds its naive local extent"),
				SelectedAxis != INDEX_NONE);
			bValid &= Test->TestTrue(
				TEXT("A cooked target overlap exists outside its raw and naive bounds but inside its rotated bounds"),
				bFound
					&& bRawTargetOverlap
					&& bOutsideRawBounds
					&& bOutsideNaiveBounds
					&& bInsideRotatedBounds);
			bValid &= Test->TestTrue(
				TEXT("The off-centre zero-length box query selects the expanded target component/key"),
				bFound
					&& SelectedHit.bBlockingHit
					&& SelectedHit.bStartPenetrating
					&& FMath::IsNearlyZero(SelectedHit.Time, 1.0e-6f)
					&& SelectedHit.GetComponent() == TargetMesh
					&& SelectedKey == BaselineKey);
			bValid &= Test->TestTrue(
				TEXT("Repeated off-centre rotated-box overlaps keep one stable component/key"),
				bStable);
			bValid &= Test->TestTrue(
				TEXT("The candidate-expansion fixture restores the production mesh bounds scale"),
				FMath::IsNearlyEqual(TargetMesh->BoundsScale, SavedBoundsScale));

			if (bValid)
			{
				UE_LOG(LogTemp, Display,
					TEXT("RED_FUSED_ACTIVE_TERRAIN_BOX_BROADPHASE_PASS axis=%d side=%d margin_cm=%.1f center=(%.3f,%.3f,%.3f) naive_extent=(%.3f,%.3f,%.3f) rotated_extent=(%.3f,%.3f,%.3f) key=(%d,%d,%d) repeats=8"),
					SelectedAxis,
					SelectedSide,
					SelectedMarginCm,
					SelectedCenter.X,
					SelectedCenter.Y,
					SelectedCenter.Z,
					BoxHalfExtent.X,
					BoxHalfExtent.Y,
					BoxHalfExtent.Z,
					RotatedWorldExtent.X,
					RotatedWorldExtent.Y,
					RotatedWorldExtent.Z,
					SelectedKey.X,
					SelectedKey.Y,
					SelectedKey.Z);
			}
			return bValid;
		}

		bool ValidateRotatedBoxAdjacentContactHandoff(
			UPrimitiveComponent* PrimaryComponent,
			const FIntVector& PrimaryKey,
			const FVector& ResolvedCenter,
			const FVector& PrimaryNormal,
			const FVector& RadialOut,
			const FCollisionShape& BoxShape,
			const FQuat& BoxRotation)
		{
			UWorld* TestWorld = World.Get();
			ACLMPlanet* TestPlanet = Planet.Get();
			const int32 ChunksPerFace = Private::GetChunksPerFace(TestPlanet);
			if (!TestWorld || !TestPlanet || !PrimaryComponent || ChunksPerFace <= 0)
			{
				return Test->TestTrue(
					TEXT("The rotated-box adjacent-manifold fixture remains valid"), false);
			}

			const FVector PlanetCenter = TestPlanet->GetActorLocation();
			const FVector OwnerChunkDirection =
				Private::GetChunkCenterDirection(ChunksPerFace, PrimaryKey);
			const FVector DesiredInteriorDirection = FVector::VectorPlaneProject(
				OwnerChunkDirection, RadialOut);
			const FVector RequestedDirection = FVector::VectorPlaneProject(
				DesiredInteriorDirection, PrimaryNormal).GetSafeNormal();
			const double RequestedDistanceCm = 100.0;
			const FVector RequestedDelta = RequestedDirection * RequestedDistanceCm;
			const FVector RequestedEnd = ResolvedCenter + RequestedDelta;

			FHitResult DirectHit;
			FIntVector DirectKey(INDEX_NONE, INDEX_NONE, INDEX_NONE);
			const bool bDirectHit = TestPlanet->SweepActiveTerrain(
				DirectHit,
				ResolvedCenter,
				RequestedEnd,
				BoxRotation,
				BoxShape,
				&DirectKey);

			FHitResult AdapterHit;
			FIntVector AdapterKey(INDEX_NONE, INDEX_NONE, INDEX_NONE);
			const ERedPlanetTerrainQueryResult AdapterResult =
				RedPlanetTerrainQuery::Sweep(
					TestWorld,
					PlanetCenter,
					ResolvedCenter,
					RequestedEnd,
					BoxRotation,
					BoxShape,
					AdapterHit,
					&AdapterKey);

			FCollisionQueryParams RawParams(
				SCENE_QUERY_STAT(RedFusedRotatedBoxAdjacentManifoldRaw), true);
			RawParams.bTraceComplex = true;
			RawParams.bFindInitialOverlaps = true;
			if (WorldDynamicBlocker.IsValid())
			{
				RawParams.AddIgnoredComponent(WorldDynamicBlocker.Get());
			}
			TArray<FHitResult> RawHits;
			TestWorld->SweepMultiByObjectType(
				RawHits,
				ResolvedCenter,
				RequestedEnd,
				BoxRotation,
				FCollisionObjectQueryParams(ECC_WorldDynamic),
				BoxShape,
				RawParams);
			FHitResult RawSelectedHit;
			const bool bRawSelectedHit = bDirectHit && RawHits.ContainsByPredicate(
				[&DirectHit, &RawSelectedHit](const FHitResult& Hit)
				{
					if (Hit.GetComponent() == DirectHit.GetComponent()
						&& Hit.bBlockingHit
						&& !Hit.bStartPenetrating)
					{
						RawSelectedHit = Hit;
						return true;
					}
					return false;
				});

			const FIntVector ExpectedPrimaryKey(
				static_cast<int32>(EPlanetGenMacroCubeFace::PositiveX), 5, 2);
			const FIntVector ExpectedSecondaryKey(
				static_cast<int32>(EPlanetGenMacroCubeFace::PositiveY), 0, 3);
			const FVector SecondaryNormal = DirectHit.Normal.GetSafeNormal();
			const FVector SecondaryRadial =
				(DirectHit.ImpactPoint - PlanetCenter).GetSafeNormal();

			bool bStable = bDirectHit
				&& AdapterResult == ERedPlanetTerrainQueryResult::Hit;
			for (int32 Repeat = 0; Repeat < 8; ++Repeat)
			{
				FHitResult RepeatedDirectHit;
				FIntVector RepeatedDirectKey(INDEX_NONE, INDEX_NONE, INDEX_NONE);
				const bool bRepeatedDirectHit = TestPlanet->SweepActiveTerrain(
					RepeatedDirectHit,
					ResolvedCenter,
					RequestedEnd,
					BoxRotation,
					BoxShape,
					&RepeatedDirectKey);

				FHitResult RepeatedAdapterHit;
				FIntVector RepeatedAdapterKey(INDEX_NONE, INDEX_NONE, INDEX_NONE);
				const ERedPlanetTerrainQueryResult RepeatedAdapterResult =
					RedPlanetTerrainQuery::Sweep(
						TestWorld,
						PlanetCenter,
						ResolvedCenter,
						RequestedEnd,
						BoxRotation,
						BoxShape,
						RepeatedAdapterHit,
						&RepeatedAdapterKey);

				bStable &= bRepeatedDirectHit
					&& RepeatedAdapterResult == ERedPlanetTerrainQueryResult::Hit
					&& RepeatedDirectHit.bBlockingHit
					&& RepeatedAdapterHit.bBlockingHit
					&& !RepeatedDirectHit.bStartPenetrating
					&& !RepeatedAdapterHit.bStartPenetrating
					&& RepeatedDirectKey == DirectKey
					&& RepeatedAdapterKey == DirectKey
					&& RepeatedDirectHit.GetComponent() == DirectHit.GetComponent()
					&& RepeatedAdapterHit.GetComponent() == DirectHit.GetComponent()
					&& RepeatedDirectHit.FaceIndex == DirectHit.FaceIndex
					&& RepeatedAdapterHit.FaceIndex == DirectHit.FaceIndex
					&& FMath::IsNearlyEqual(
						RepeatedDirectHit.Distance, DirectHit.Distance, 0.01f)
					&& FMath::IsNearlyEqual(
						RepeatedAdapterHit.Distance, DirectHit.Distance, 0.01f)
					&& FMath::IsNearlyEqual(
						RepeatedDirectHit.Time, DirectHit.Time, 1.0e-5f)
					&& FMath::IsNearlyEqual(
						RepeatedAdapterHit.Time, DirectHit.Time, 1.0e-5f)
					&& FVector::Dist(
						RepeatedDirectHit.Location, DirectHit.Location) <= 0.1f
					&& FVector::Dist(
						RepeatedAdapterHit.Location, DirectHit.Location) <= 0.1f
					&& FVector::Dist(
						RepeatedDirectHit.ImpactPoint, DirectHit.ImpactPoint) <= 0.1f
					&& FVector::Dist(
						RepeatedAdapterHit.ImpactPoint, DirectHit.ImpactPoint) <= 0.1f
					&& FVector::DotProduct(
						RepeatedDirectHit.Normal.GetSafeNormal(), SecondaryNormal) > 0.9999f
					&& FVector::DotProduct(
						RepeatedAdapterHit.Normal.GetSafeNormal(), SecondaryNormal) > 0.9999f;
			}

			struct FContactPlane
			{
				FIntVector Key;
				FVector Normal;
			};
			auto KeyLess = [](const FIntVector& A, const FIntVector& B)
			{
				return A.X != B.X ? A.X < B.X
					: (A.Y != B.Y ? A.Y < B.Y : A.Z < B.Z);
			};
			auto ProjectAgainstCanonicalPlanes =
				[&KeyLess](const FVector& Delta, TArray<FContactPlane> Planes)
			{
				Planes.Sort([&KeyLess](const FContactPlane& A, const FContactPlane& B)
				{
					return KeyLess(A.Key, B.Key);
				});
				FVector Projected = Delta;
				for (int32 Pass = 0; Pass < 8; ++Pass)
				{
					for (const FContactPlane& Plane : Planes)
					{
						const float NormalComponent = FVector::DotProduct(
							Projected, Plane.Normal);
						if (NormalComponent < 0.0f)
						{
							Projected -= Plane.Normal * NormalComponent;
						}
					}
				}
				return Projected;
			};

			TArray<FContactPlane> CanonicalPlanes = {
				{PrimaryKey, PrimaryNormal.GetSafeNormal()},
				{DirectKey, SecondaryNormal}
			};
			CanonicalPlanes.Sort([&KeyLess](const FContactPlane& A, const FContactPlane& B)
			{
				return KeyLess(A.Key, B.Key);
			});
			const FVector ProjectedDelta = ProjectAgainstCanonicalPlanes(
				RequestedDelta, CanonicalPlanes);
			TArray<FContactPlane> ReversedPlanes = CanonicalPlanes;
			if (ReversedPlanes.Num() == 2)
			{
				ReversedPlanes.Swap(0, 1);
			}
			const FVector ReversedProjectedDelta = ProjectAgainstCanonicalPlanes(
				RequestedDelta, ReversedPlanes);
			const double RetainedFraction = ProjectedDelta.Size()
				/ FMath::Max(RequestedDelta.Size(), UE_DOUBLE_KINDA_SMALL_NUMBER);
			const FVector OwnerwardDirection = DesiredInteriorDirection.GetSafeNormal();

			bool bValid = true;
			bValid &= Test->TestTrue(
				TEXT("The adjacent-manifold fixture recreates the finite ownerward request"),
				!RequestedDirection.IsNearlyZero()
					&& !RequestedDelta.ContainsNaN()
					&& FMath::IsNearlyEqual(RequestedDelta.Size(), RequestedDistanceCm, 0.001)
					&& FMath::Abs(FVector::DotProduct(
						RequestedDirection, PrimaryNormal.GetSafeNormal())) <= 1.0e-4f);
			bValid &= Test->TestTrue(
				TEXT("The direct exact query reports the real adjacent-face box contact"),
				bDirectHit
					&& DirectHit.bBlockingHit
					&& !DirectHit.bStartPenetrating
					&& FMath::IsNearlyZero(DirectHit.PenetrationDepth, 0.01f)
					&& DirectKey == ExpectedSecondaryKey
					&& DirectKey != PrimaryKey
					&& DirectHit.GetComponent() != PrimaryComponent
					&& Private::IsOwnedPlanetChunk(DirectHit, TestPlanet)
					&& FMath::IsFinite(DirectHit.Time)
					&& DirectHit.Time > 0.0f
					&& DirectHit.Time < 1.0f
					&& FMath::IsFinite(DirectHit.Distance)
					&& DirectHit.Distance > 0.0f
					&& DirectHit.Distance < RequestedDistanceCm
					&& FVector::DotProduct(SecondaryNormal, SecondaryRadial) > 0.999f);
			bValid &= Test->TestTrue(
				TEXT("The project adapter preserves the adjacent-face contact"),
				AdapterResult == ERedPlanetTerrainQueryResult::Hit
					&& AdapterHit.bBlockingHit
					&& !AdapterHit.bStartPenetrating
					&& FMath::IsNearlyZero(AdapterHit.PenetrationDepth, 0.01f)
					&& AdapterKey == DirectKey
					&& AdapterHit.GetComponent() == DirectHit.GetComponent()
					&& AdapterHit.FaceIndex == DirectHit.FaceIndex
					&& FMath::IsNearlyEqual(AdapterHit.Time, DirectHit.Time, 1.0e-5f)
					&& FMath::IsNearlyEqual(AdapterHit.Distance, DirectHit.Distance, 0.01f)
					&& FVector::Dist(AdapterHit.Location, DirectHit.Location) <= 0.1f
					&& FVector::Dist(AdapterHit.ImpactPoint, DirectHit.ImpactPoint) <= 0.1f
					&& FVector::DotProduct(
						AdapterHit.Normal.GetSafeNormal(), SecondaryNormal) > 0.9999f);
			bValid &= Test->TestTrue(
				TEXT("Filtered raw Chaos agrees with the selected adjacent component"),
				bRawSelectedHit
					&& RawSelectedHit.GetComponent() == DirectHit.GetComponent()
					&& FMath::IsNearlyEqual(
						RawSelectedHit.Distance, DirectHit.Distance, 0.01f)
					&& FVector::DotProduct(
						RawSelectedHit.Normal.GetSafeNormal(), SecondaryNormal) > 0.9999f);
			bValid &= Test->TestTrue(
				TEXT("Eight adjacent-face direct and adapter queries preserve one contact"),
				bStable);
			bValid &= Test->TestTrue(
				TEXT("The persistent manifold keeps the two canonical terrain keys"),
				CanonicalPlanes.Num() == 2
					&& CanonicalPlanes[0].Key == ExpectedPrimaryKey
					&& CanonicalPlanes[1].Key == ExpectedSecondaryKey
					&& PrimaryKey == ExpectedPrimaryKey
					&& FVector::DotProduct(
						CanonicalPlanes[0].Normal, CanonicalPlanes[1].Normal) > 0.999f);
			const double RequestedPrimaryDot = FVector::DotProduct(
				RequestedDelta, PrimaryNormal.GetSafeNormal());
			const double RequestedSecondaryDot = FVector::DotProduct(
				RequestedDelta, SecondaryNormal);
			bValid &= Test->TestTrue(
				TEXT("The distinct adjacent contact follows an exact-clear tangent start"),
				FMath::Abs(RequestedPrimaryDot) <= 0.01
					&& FMath::IsFinite(RequestedSecondaryDot)
					&& DirectHit.Time > 0.0f
					&& DirectHit.Distance > 0.0f
					&& DirectKey != PrimaryKey
					&& DirectHit.GetComponent() != PrimaryComponent);
			bValid &= Test->TestTrue(
				TEXT("Canonical contact projection is finite and order-stable for the response gate"),
				!ProjectedDelta.ContainsNaN()
					&& !ProjectedDelta.IsNearlyZero()
					&& RetainedFraction >= 0.95f
					&& FVector::DotProduct(ProjectedDelta, CanonicalPlanes[0].Normal) >= -1.0e-4f
					&& FVector::DotProduct(ProjectedDelta, CanonicalPlanes[1].Normal) >= -1.0e-4f
					&& FVector::DotProduct(ProjectedDelta, OwnerwardDirection) > 0.0f
					&& FVector::Dist(ProjectedDelta, ReversedProjectedDelta) <= 0.001f);

			if (bValid)
			{
				UE_LOG(LogTemp, Display,
					TEXT("RED_FUSED_ACTIVE_TERRAIN_BOX_ADJACENT_CONTACT_PASS primary_key=(%d,%d,%d) secondary_key=(%d,%d,%d) distance_cm=%.6f time=%.9f requested_primary_dot=%.9f requested_secondary_dot=%.9f planes=2 retained_fraction=%.6f repeats=8"),
					PrimaryKey.X,
					PrimaryKey.Y,
					PrimaryKey.Z,
					DirectKey.X,
					DirectKey.Y,
					DirectKey.Z,
					DirectHit.Distance,
					DirectHit.Time,
					RequestedPrimaryDot,
					RequestedSecondaryDot,
					RetainedFraction);
			}
			return bValid;
		}

		bool ValidateRotatedBoxDepenetration(
			const FHitResult& ContactHit,
			const FIntVector& ContactKey,
			const FCollisionShape& BoxShape,
			const FQuat& BoxRotation)
		{
			UWorld* TestWorld = World.Get();
			ACLMPlanet* TestPlanet = Planet.Get();
			UPrimitiveComponent* TargetComponent = ContactHit.GetComponent();
			if (!TestWorld || !TestPlanet || !TargetComponent)
			{
				return Test->TestTrue(
					TEXT("The rotated-box depenetration fixture remains valid"), false);
			}

			const FVector PlanetCenter = TestPlanet->GetActorLocation();
			const FVector RadialOut =
				(ContactHit.ImpactPoint - PlanetCenter).GetSafeNormal();
			const float EmbedDepthCm = 50.0f;
			const float PullbackCm = 2.0f;
			const FVector EmbeddedCenter = ContactHit.Location - RadialOut * EmbedDepthCm;

			FCollisionQueryParams RawParams(
				SCENE_QUERY_STAT(RedFusedRotatedBoxDepenetrationRaw), true);
			RawParams.bTraceComplex = true;
			RawParams.bFindInitialOverlaps = true;
			if (WorldDynamicBlocker.IsValid())
			{
				RawParams.AddIgnoredComponent(WorldDynamicBlocker.Get());
			}

			TArray<FHitResult> RawHits;
			TestWorld->SweepMultiByObjectType(
				RawHits,
				EmbeddedCenter,
				EmbeddedCenter,
				BoxRotation,
				FCollisionObjectQueryParams(ECC_WorldDynamic),
				BoxShape,
				RawParams);
			FHitResult RawTargetHit;
			const bool bRawTargetHit = RawHits.ContainsByPredicate(
				[TargetComponent, &RawTargetHit](const FHitResult& Hit)
				{
					if (Hit.GetComponent() == TargetComponent
						&& Hit.bBlockingHit
						&& Hit.bStartPenetrating)
					{
						RawTargetHit = Hit;
						return true;
					}
					return false;
				});

			FHitResult DirectHit;
			FIntVector DirectKey(INDEX_NONE, INDEX_NONE, INDEX_NONE);
			const bool bDirectHit = TestPlanet->SweepActiveTerrain(
				DirectHit,
				EmbeddedCenter,
				EmbeddedCenter,
				BoxRotation,
				BoxShape,
				&DirectKey);
			FHitResult AdapterHit;
			FIntVector AdapterKey(INDEX_NONE, INDEX_NONE, INDEX_NONE);
			const ERedPlanetTerrainQueryResult AdapterResult =
				RedPlanetTerrainQuery::Sweep(
					TestWorld,
					PlanetCenter,
					EmbeddedCenter,
					EmbeddedCenter,
					BoxRotation,
					BoxShape,
					AdapterHit,
					&AdapterKey);

			const bool bFiniteDepth = bDirectHit
				&& FMath::IsFinite(DirectHit.PenetrationDepth)
				&& DirectHit.PenetrationDepth > UE_KINDA_SMALL_NUMBER;
			const bool bFiniteNormal = bDirectHit
				&& FMath::IsFinite(DirectHit.Normal.X)
				&& FMath::IsFinite(DirectHit.Normal.Y)
				&& FMath::IsFinite(DirectHit.Normal.Z)
				&& !DirectHit.Normal.IsNearlyZero();
			const FVector DepenetrationNormal = DirectHit.Normal.GetSafeNormal();

			bool bStable = bDirectHit && bFiniteDepth && bFiniteNormal;
			for (int32 Repeat = 0; Repeat < 8; ++Repeat)
			{
				FHitResult RepeatedHit;
				FIntVector RepeatedKey(INDEX_NONE, INDEX_NONE, INDEX_NONE);
				const bool bRepeatedHit = TestPlanet->SweepActiveTerrain(
					RepeatedHit,
					EmbeddedCenter,
					EmbeddedCenter,
					BoxRotation,
					BoxShape,
					&RepeatedKey);
				bStable &= bRepeatedHit
					&& RepeatedHit.bBlockingHit
					&& RepeatedHit.bStartPenetrating
					&& RepeatedHit.GetComponent() == TargetComponent
					&& RepeatedKey == ContactKey
					&& FMath::IsFinite(RepeatedHit.PenetrationDepth)
					&& FMath::IsNearlyEqual(
						RepeatedHit.PenetrationDepth, DirectHit.PenetrationDepth, 0.01f)
					&& FVector::DotProduct(
						RepeatedHit.Normal.GetSafeNormal(), DepenetrationNormal) > 0.9999f;
			}

			const FVector Adjustment = DepenetrationNormal
				* (DirectHit.PenetrationDepth + PullbackCm);
			const float MaxBoundedAdjustment = BoxShape.GetExtent().GetMax() * 2.0f
				+ PullbackCm;
			const bool bBoundedOutwardAdjustment = bFiniteDepth
				&& bFiniteNormal
				&& FMath::IsFinite(Adjustment.SizeSquared())
				&& !Adjustment.IsNearlyZero()
				&& Adjustment.Size() <= MaxBoundedAdjustment
				&& FVector::DotProduct(DepenetrationNormal, RadialOut) > 0.9f;
			const FVector ResolvedCenter = EmbeddedCenter + Adjustment;

			FHitResult ResolvedHit;
			FIntVector ResolvedKey(INDEX_NONE, INDEX_NONE, INDEX_NONE);
			const ERedPlanetTerrainQueryResult ResolvedResult =
				RedPlanetTerrainQuery::Sweep(
					TestWorld,
					PlanetCenter,
					ResolvedCenter,
					ResolvedCenter,
					BoxRotation,
					BoxShape,
					ResolvedHit,
					&ResolvedKey);

			bool bValid = true;
			bValid &= Test->TestTrue(
				TEXT("Raw Chaos reports the selected cooked box start penetration"),
				bRawTargetHit
					&& FMath::IsFinite(RawTargetHit.PenetrationDepth)
					&& RawTargetHit.PenetrationDepth > UE_KINDA_SMALL_NUMBER);
			bValid &= Test->TestTrue(
				TEXT("The exact rotated-box overlap returns a finite usable MTD"),
				bDirectHit
					&& DirectHit.bBlockingHit
					&& DirectHit.bStartPenetrating
					&& DirectHit.GetComponent() == TargetComponent
					&& DirectKey == ContactKey
					&& bFiniteDepth
					&& bFiniteNormal
					&& bBoundedOutwardAdjustment);
			bValid &= Test->TestTrue(
				TEXT("Raw Chaos and the exact query agree on the rotated-box MTD"),
				bRawTargetHit
					&& bDirectHit
					&& FMath::IsNearlyEqual(
						RawTargetHit.PenetrationDepth, DirectHit.PenetrationDepth, 0.01f)
					&& FVector::DotProduct(
						RawTargetHit.Normal.GetSafeNormal(), DepenetrationNormal) > 0.9999f);
			bValid &= Test->TestTrue(
				TEXT("The project adapter preserves the rotated-box MTD and owned key"),
				AdapterResult == ERedPlanetTerrainQueryResult::Hit
					&& AdapterHit.bBlockingHit
					&& AdapterHit.bStartPenetrating
					&& AdapterHit.GetComponent() == TargetComponent
					&& AdapterKey == ContactKey
					&& FMath::IsNearlyEqual(
						AdapterHit.PenetrationDepth, DirectHit.PenetrationDepth, 0.01f)
					&& FVector::DotProduct(
						AdapterHit.Normal.GetSafeNormal(), DepenetrationNormal) > 0.9999f);
			bValid &= Test->TestTrue(
				TEXT("Eight rotated-box start-overlap queries preserve one MTD/component/key"),
				bStable);
			bValid &= Test->TestTrue(
				TEXT("One bounded rotated-box MTD plus pullback clears exact terrain"),
				bBoundedOutwardAdjustment
					&& ResolvedResult == ERedPlanetTerrainQueryResult::NoHit
					&& !ResolvedHit.bBlockingHit
					&& !ResolvedHit.bStartPenetrating);
			if (bBoundedOutwardAdjustment
				&& ResolvedResult == ERedPlanetTerrainQueryResult::NoHit)
			{
				bValid &= ValidateRotatedBoxAdjacentContactHandoff(
					TargetComponent,
					ContactKey,
					ResolvedCenter,
					DepenetrationNormal,
					RadialOut,
					BoxShape,
					BoxRotation);
			}
			if (bValid)
			{
				UE_LOG(LogTemp, Display,
					TEXT("RED_FUSED_ACTIVE_TERRAIN_BOX_MTD_PASS embed_cm=%.3f depth_cm=%.6f adjustment_cm=%.6f normal_dot_radial=%.6f key=(%d,%d,%d) repeats=8"),
					EmbedDepthCm,
					DirectHit.PenetrationDepth,
					Adjustment.Size(),
					FVector::DotProduct(DepenetrationNormal, RadialOut),
					DirectKey.X,
					DirectKey.Y,
					DirectKey.Z);
			}
			return bValid;
		}

		bool WaitOrFail(const FString& Detail)
		{
			if (FPlatformTime::Seconds() - StartedAtSeconds <= Private::PhaseTimeoutSeconds)
			{
				return false;
			}
			return Fail(FString::Printf(
				TEXT("Timed out waiting for %s."), *Detail));
		}

		bool WaitForPassiveOrFail()
		{
			if (FPlatformTime::Seconds() - PassiveStageStartedAtSeconds
				<= Private::PhaseTimeoutSeconds)
			{
				return false;
			}
			return Fail(
				TEXT("Timed out waiting for four authoritative passive zero-input world ticks."));
		}

		bool Fail(const FString& Message)
		{
			Test->AddError(Message);
			return Finish();
		}

		bool Finish()
		{
			if (PassiveMovement.IsValid())
			{
				PassiveMovement->SetComponentTickEnabled(false);
			}
			if (PassiveRootSphere.IsValid())
			{
				PassiveRootSphere->SetCollisionEnabled(ECollisionEnabled::NoCollision);
			}
			if (PassiveShip.IsValid())
			{
				PassiveShip->SetActorEnableCollision(false);
				PassiveShip->Destroy();
			}
			if (Planet.IsValid())
			{
				Planet->AdditionalStreamingSources = OriginalAdditionalStreamingSources;
			}
			if (WorldDynamicBlocker.IsValid())
			{
				WorldDynamicBlocker->SetCollisionEnabled(ECollisionEnabled::NoCollision);
			}
			if (WorldDynamicBlockerActor.IsValid())
			{
				WorldDynamicBlockerActor->Destroy();
			}
			for (const TWeakObjectPtr<ATargetPoint>& Source : StreamingSources)
			{
				if (Source.IsValid())
				{
					Source->Destroy();
				}
			}
			Stage = EStage::Finished;
			return true;
		}

		FAutomationTestBase* Test = nullptr;
		TWeakObjectPtr<UWorld> World;
		TWeakObjectPtr<ACLMPlanet> Planet;
		TArray<TWeakObjectPtr<ATargetPoint>> StreamingSources;
		TArray<TObjectPtr<AActor>> OriginalAdditionalStreamingSources;
		TWeakObjectPtr<AActor> WorldDynamicBlockerActor;
		TWeakObjectPtr<UBoxComponent> WorldDynamicBlocker;
		TWeakObjectPtr<ARedShip> PassiveShip;
		TWeakObjectPtr<URedShipMovementComponent> PassiveMovement;
		TWeakObjectPtr<USphereComponent> PassiveRootSphere;
		FCollisionShape PassiveRootShape;
		FQuat PassiveRotation = FQuat::Identity;
		FVector PassivePenetratingStart = FVector::ZeroVector;
		FVector PassiveExpectedAdjustment = FVector::ZeroVector;
		FVector PassiveContactOut = FVector::UpVector;
		FVector PassiveTangentDirection = FVector::ForwardVector;
		FVector PassiveResolvedLocation = FVector::ZeroVector;
		EStage Stage = EStage::WaitForWorld;
		double StartedAtSeconds = 0.0;
		double PassiveStageStartedAtSeconds = 0.0;
		double PassiveLastObservedWorldSeconds = 0.0;
		double PassiveFirstResolvedWorldSeconds = 0.0;
		int32 PassiveOverlapRepeatCount = 0;
		int32 PassiveObservedWorldTicks = 0;
		float PassiveInitialDepthCm = 0.0f;
		float PassiveOutwardDisplacementCm = 0.0f;
		float PassiveTangentDisplacementCm = 0.0f;
		float PassiveExpectedLocationErrorCm = 0.0f;
		float PassiveMaxSettleDriftCm = 0.0f;
		FVector SeamDirection = FVector::ForwardVector;
		FVector PositiveStart = FVector::ZeroVector;
		FVector NegativeStart = FVector::ZeroVector;
	};

	IMPLEMENT_SIMPLE_AUTOMATION_TEST(
		FRedPlanetFusedTerrainContinuityTest,
		"RedMMO.Planet.FusedTerrain.RuntimeTerrainCollisionContinuity",
		EAutomationTestFlags::EditorContext | EAutomationTestFlags::ProductFilter)

	bool FRedPlanetFusedTerrainContinuityTest::RunTest(const FString& Parameters)
	{
		(void)Parameters;
		// The purchased Cascade jetpack blueprint unconditionally updates two emitter return values.
		// NullRHI deliberately does not create those emitters, so PIE reports the same headless-only
		// Accessed-None warning/error pair before this terrain test begins. Scope the suppression to
		// that exact property; every other PIE error still fails the test.
		AddExpectedErrorPlain(
			TEXT("Accessed None trying to read (real) property CallFunc_SpawnEmitterAttached_ReturnValue"),
			EAutomationExpectedErrorFlags::Contains,
			-1);
		if (!AutomationOpenMap(Private::FusedPrototypeMap, true))
		{
			AddError(TEXT("AutomationOpenMap rejected the fused-prototype map."));
			return false;
		}

		ADD_LATENT_AUTOMATION_COMMAND(FRedFusedTerrainContinuityCommand(this));
		ADD_LATENT_AUTOMATION_COMMAND(FEndPlayMapCommand());
		return true;
	}

	IMPLEMENT_SIMPLE_AUTOMATION_TEST(
		FRedPlanetFusedAllCubeBoundariesTest,
		"RedMMO.Planet.FusedTerrain.RuntimeAllCubeBoundaries",
		EAutomationTestFlags::EditorContext | EAutomationTestFlags::ProductFilter)

	bool FRedPlanetFusedAllCubeBoundariesTest::RunTest(const FString& Parameters)
	{
		(void)Parameters;
		AddExpectedErrorPlain(
			TEXT("Accessed None trying to read (real) property CallFunc_SpawnEmitterAttached_ReturnValue"),
			EAutomationExpectedErrorFlags::Contains,
			-1);
		if (!AutomationOpenMap(Private::FusedPrototypeMap, true))
		{
			AddError(TEXT("AutomationOpenMap rejected the fused-prototype map."));
			return false;
		}

		ADD_LATENT_AUTOMATION_COMMAND(FRedFusedAllCubeBoundaryCommand(this));
		ADD_LATENT_AUTOMATION_COMMAND(FEndPlayMapCommand());
		return true;
	}

	IMPLEMENT_SIMPLE_AUTOMATION_TEST(
		FRedPlanetFusedActiveTerrainQueryTest,
		"RedMMO.Planet.FusedTerrain.RuntimeActiveTerrainQuery",
		EAutomationTestFlags::EditorContext | EAutomationTestFlags::ProductFilter)

	bool FRedPlanetFusedActiveTerrainQueryTest::RunTest(const FString& Parameters)
	{
		(void)Parameters;
		AddExpectedErrorPlain(
			TEXT("Accessed None trying to read (real) property CallFunc_SpawnEmitterAttached_ReturnValue"),
			EAutomationExpectedErrorFlags::Contains,
			-1);
		if (!AutomationOpenMap(Private::FusedPrototypeMap, true))
		{
			AddError(TEXT("AutomationOpenMap rejected the fused-prototype map."));
			return false;
		}

		ADD_LATENT_AUTOMATION_COMMAND(FRedFusedActiveTerrainQueryCommand(this));
		ADD_LATENT_AUTOMATION_COMMAND(FEndPlayMapCommand());
		return true;
	}
}

#endif // WITH_DEV_AUTOMATION_TESTS && WITH_EDITOR

#else
// Stock Marketplace PlanetGen 1.7 lacks TerrainStamp/MacroHeightfield fork APIs.
// These automation suites are compiled out until Plugins/PlanetGenPinned_* is restored.
#endif