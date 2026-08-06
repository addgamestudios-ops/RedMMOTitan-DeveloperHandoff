#include "../RedMMOEditorTools.h"

#if WITH_DEV_AUTOMATION_TESTS && WITH_EDITOR

#include "../RedGravityBodies.h"
#include "../RedPlanetTerrainQuery.h"
#include "PlanetGen/CLMPlanet.h"

#include "Editor.h"
#include "Engine/StaticMeshActor.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "GameFramework/PlayerStart.h"
#include "Misc/AutomationTest.h"
#include "Misc/PackageName.h"
#include "Subsystems/EditorActorSubsystem.h"
#include "Tests/AutomationEditorCommon.h"
#include "UObject/Package.h"

namespace RedMMO::EditorPlacementTests
{
	namespace Private
	{
		constexpr TCHAR TestMapPackage[] =
			TEXT("/Game/RedMMO/Maps/Tests/RedPlanetGen_50km_FusedPrototype_Night_T02");
		constexpr float SurfaceOffsetCm = 17.5f;
		constexpr double TerrainTimeoutSeconds = 45.0;

		FVector ComputeTangentHeading(const AActor* Actor, const FVector& RadialUp)
		{
			FVector Heading = FVector::VectorPlaneProject(
				Actor->GetActorForwardVector(), RadialUp).GetSafeNormal();
			if (Heading.IsNearlyZero())
			{
				const FVector Right = FVector::VectorPlaneProject(
					Actor->GetActorRightVector(), RadialUp).GetSafeNormal();
				Heading = FVector::CrossProduct(Right, RadialUp).GetSafeNormal();
			}
			if (Heading.IsNearlyZero())
			{
				FVector Unused;
				RadialUp.FindBestAxisVectors(Heading, Unused);
			}
			return Heading;
		}

		class FRedRadialSelectionSnapCommand final : public IAutomationLatentCommand
		{
		public:
			explicit FRedRadialSelectionSnapCommand(FAutomationTestBase* InTest)
				: Test(InTest)
			{
			}

			virtual ~FRedRadialSelectionSnapCommand() override
			{
				Cleanup();
			}

			virtual bool Update() override
			{
				if (!bPrepared)
				{
					return Prepare();
				}

				UWorld* CurrentWorld = World.Get();
				ACLMPlanet* CurrentPlanet = Planet.Get();
				AStaticMeshActor* CurrentProbe = Probe.Get();
				if (!CurrentWorld || !CurrentPlanet || !CurrentProbe)
				{
					Test->AddError(TEXT("Editor placement fixture became invalid while terrain was building."));
					Cleanup();
					return true;
				}

				FVector PlanetCenter = FVector::ZeroVector;
				float DatumRadius = 0.0f;
				float PeakRadius = 0.0f;
				const bool bHasPlanetFrame = RedGravity::FindMeshPlanet(
					CurrentWorld, PlanetCenter, DatumRadius, &PeakRadius);
				const FVector RadialUp = bHasPlanetFrame
					? (CurrentProbe->GetActorLocation() - PlanetCenter).GetSafeNormal()
					: FVector::ZeroVector;
				FHitResult ExpectedHit;
				const ERedPlanetTerrainQueryResult QueryResult = bHasPlanetFrame && !RadialUp.IsNearlyZero()
					? RedPlanetTerrainQuery::LineTrace(
						CurrentWorld,
						PlanetCenter,
						PlanetCenter + RadialUp * (PeakRadius + 5000.0f),
						PlanetCenter + RadialUp * DatumRadius,
						ExpectedHit)
					: ERedPlanetTerrainQueryResult::NoMatchingPlanet;

				if (QueryResult != ERedPlanetTerrainQueryResult::Hit)
				{
					if (FPlatformTime::Seconds() - StartedAtSeconds < TerrainTimeoutSeconds)
					{
						return false;
					}
					Test->AddError(TEXT("Timed out waiting for exact active PlanetGen terrain in the T02 editor fixture."));
					Cleanup();
					return true;
				}

				RunSnapAndUndo(PlanetCenter, RadialUp, ExpectedHit);
				Cleanup();
				return true;
			}

		private:
			bool Prepare()
			{
				if (!GEditor)
				{
					Test->AddError(TEXT("GEditor is unavailable."));
					return true;
				}

				UWorld* EditorWorld = GEditor->GetEditorWorldContext().World();
				if (!EditorWorld || EditorWorld->WorldType != EWorldType::Editor
					|| EditorWorld->GetOutermost()->GetName() != TestMapPackage)
				{
					Test->AddError(FString::Printf(
						TEXT("Expected editor test map %s, found %s."),
						TestMapPackage,
						EditorWorld ? *EditorWorld->GetOutermost()->GetName() : TEXT("<null>")));
					return true;
				}

				ACLMPlanet* FoundPlanet = nullptr;
				AStaticMeshActor* FoundProbe = nullptr;
				APlayerStart* FoundNegativeControl = nullptr;
				for (TActorIterator<ACLMPlanet> It(EditorWorld); It; ++It)
				{
					FoundPlanet = *It;
					break;
				}
				for (TActorIterator<AStaticMeshActor> It(EditorWorld); It; ++It)
				{
					if (It->GetActorLabel().StartsWith(TEXT("RedOasisRock"))
						&& !It->GetAttachParentActor()
						&& It->GetStaticMeshComponent()
						&& It->GetStaticMeshComponent()->GetStaticMesh())
					{
						FoundProbe = *It;
						break;
					}
				}
				for (TActorIterator<APlayerStart> It(EditorWorld); It; ++It)
				{
					FoundNegativeControl = *It;
					break;
				}

				if (!FoundPlanet || !FoundProbe || !FoundNegativeControl)
				{
					Test->AddError(TEXT("T02 fixture is missing its PlanetGen actor, oasis rock, or PlayerStart control."));
					return true;
				}

				World = EditorWorld;
				Planet = FoundPlanet;
				Probe = FoundProbe;
				NegativeControl = FoundNegativeControl;
				WorldPackage = EditorWorld->GetOutermost();
				bWorldWasDirty = WorldPackage.IsValid() && WorldPackage->IsDirty();
				OriginalMaxChunksPerFace = FoundPlanet->MaxChunksPerFace;
				OriginalResolution = FoundPlanet->Resolution;
				bOriginalEnableFoliage = FoundPlanet->bEnableFoliage;
				bOriginalEnableGrass = FoundPlanet->bEnableGrass;

				FoundPlanet->MaxChunksPerFace = 1;
				FoundPlanet->Resolution = 8;
				FoundPlanet->bEnableFoliage = false;
				FoundPlanet->bEnableGrass = false;
				FoundPlanet->PreviewPlanet();

				StartedAtSeconds = FPlatformTime::Seconds();
				bPrepared = true;
				return false;
			}

			void RunSnapAndUndo(
				const FVector& PlanetCenter,
				const FVector& RadialUp,
				const FHitResult& ExpectedHit)
			{
				AStaticMeshActor* CurrentProbe = Probe.Get();
				APlayerStart* CurrentNegativeControl = NegativeControl.Get();
				UEditorActorSubsystem* ActorSubsystem =
					GEditor->GetEditorSubsystem<UEditorActorSubsystem>();
				if (!CurrentProbe || !CurrentNegativeControl || !ActorSubsystem)
				{
					Test->AddError(TEXT("Selection fixture is unavailable."));
					return;
				}

				const FTransform OriginalProbeTransform = CurrentProbe->GetActorTransform();
				const FTransform OriginalControlTransform = CurrentNegativeControl->GetActorTransform();
				const FVector ExpectedHeading = ComputeTangentHeading(CurrentProbe, RadialUp);
				const FVector OriginalScale = CurrentProbe->GetActorScale3D();
				const FVector ExpectedLocation = ExpectedHit.ImpactPoint + RadialUp * SurfaceOffsetCm;

				ActorSubsystem->SetSelectedLevelActors({CurrentProbe, CurrentNegativeControl});
				const TArray<AActor*> SelectedActors = ActorSubsystem->GetSelectedLevelActors();
				Test->TestTrue(TEXT("Static-mesh probe is selected"), SelectedActors.Contains(CurrentProbe));
				Test->TestTrue(TEXT("Non-static negative control is selected"),
					SelectedActors.Contains(CurrentNegativeControl));

				const FString Result =
					URedMMOEditorTools::SnapSelectedStaticMeshActorsToPlanetSurface(SurfaceOffsetCm);
				Test->TestTrue(TEXT("Radial snap reports success"), Result.StartsWith(TEXT("OK:")));
				Test->AddInfo(Result);

				const FVector SnappedUp = CurrentProbe->GetActorQuat().RotateVector(FVector::UpVector);
				const FVector SnappedHeading = FVector::VectorPlaneProject(
					CurrentProbe->GetActorForwardVector(), RadialUp).GetSafeNormal();
				Test->TestTrue(TEXT("Origin is on exact terrain plus requested offset"),
					FVector::Distance(CurrentProbe->GetActorLocation(), ExpectedLocation) <= 0.1f);
				Test->TestTrue(TEXT("Local Z aligns to radial up"),
					FVector::DotProduct(SnappedUp, RadialUp) >= 0.99999f);
				Test->TestTrue(TEXT("Tangent heading is preserved"),
					FVector::DotProduct(SnappedHeading, ExpectedHeading) >= 0.99999f);
				Test->TestTrue(TEXT("Scale is unchanged"),
					CurrentProbe->GetActorScale3D().Equals(OriginalScale, KINDA_SMALL_NUMBER));
				Test->TestTrue(TEXT("Non-static selected actor is unchanged"),
					CurrentNegativeControl->GetActorTransform().Equals(OriginalControlTransform, 0.001f));

				const FText ExpectedTransactionName = NSLOCTEXT(
					"RedMMOEditorTools", "SnapSelectedStaticMeshesToPlanet", "Snap selected meshes to planet");
				Test->TestFalse(TEXT("Snap transaction has closed"), GEditor->IsTransactionActive());
				Test->TestTrue(TEXT("Snap is the latest undo transaction"),
					GEditor->GetTransactionName().EqualTo(ExpectedTransactionName));
				Test->TestTrue(TEXT("Undo transaction succeeds"), GEditor->UndoTransaction());

				const FTransform RestoredProbeTransform = CurrentProbe->GetActorTransform();
				Test->TestTrue(TEXT("Undo restores probe location"),
					FVector::Distance(
						RestoredProbeTransform.GetLocation(), OriginalProbeTransform.GetLocation()) <= 0.1f);
				Test->TestTrue(TEXT("Undo restores probe rotation"),
					RestoredProbeTransform.GetRotation().Equals(
						OriginalProbeTransform.GetRotation(), 0.00001f));
				Test->TestTrue(TEXT("Undo restores probe scale"),
					RestoredProbeTransform.GetScale3D().Equals(
						OriginalProbeTransform.GetScale3D(), KINDA_SMALL_NUMBER));
				Test->TestTrue(TEXT("Negative control remains unchanged after Undo"),
					CurrentNegativeControl->GetActorTransform().Equals(OriginalControlTransform, 0.001f));
			}

			void Cleanup()
			{
				if (bCleaned)
				{
					return;
				}
				bCleaned = true;

				if (GEditor)
				{
					if (UEditorActorSubsystem* ActorSubsystem =
						GEditor->GetEditorSubsystem<UEditorActorSubsystem>())
					{
						ActorSubsystem->SelectNothing();
					}
				}

				if (ACLMPlanet* CurrentPlanet = Planet.Get())
				{
					CurrentPlanet->ClearPlanet();
					CurrentPlanet->MaxChunksPerFace = OriginalMaxChunksPerFace;
					CurrentPlanet->Resolution = OriginalResolution;
					CurrentPlanet->bEnableFoliage = bOriginalEnableFoliage;
					CurrentPlanet->bEnableGrass = bOriginalEnableGrass;
				}
				if (UPackage* Package = WorldPackage.Get())
				{
					Package->SetDirtyFlag(bWorldWasDirty);
				}
			}

			FAutomationTestBase* Test = nullptr;
			TWeakObjectPtr<UWorld> World;
			TWeakObjectPtr<ACLMPlanet> Planet;
			TWeakObjectPtr<AStaticMeshActor> Probe;
			TWeakObjectPtr<APlayerStart> NegativeControl;
			TWeakObjectPtr<UPackage> WorldPackage;
			int32 OriginalMaxChunksPerFace = 0;
			int32 OriginalResolution = 0;
			bool bOriginalEnableFoliage = false;
			bool bOriginalEnableGrass = false;
			bool bWorldWasDirty = false;
			bool bPrepared = false;
			bool bCleaned = false;
			double StartedAtSeconds = 0.0;
		};
	}

	IMPLEMENT_SIMPLE_AUTOMATION_TEST(
		FRedRadialSelectionSnapTest,
		"RedMMO.EditorTools.RadialSelectionSnap",
		EAutomationTestFlags::EditorContext | EAutomationTestFlags::ProductFilter)

	bool FRedRadialSelectionSnapTest::RunTest(const FString& Parameters)
	{
		(void)Parameters;
		const FString MapFilename = FPackageName::LongPackageNameToFilename(
			Private::TestMapPackage, FPackageName::GetMapPackageExtension());
		ADD_LATENT_AUTOMATION_COMMAND(FEditorLoadMap(MapFilename));
		ADD_LATENT_AUTOMATION_COMMAND(Private::FRedRadialSelectionSnapCommand(this));
		return true;
	}
}

#endif // WITH_DEV_AUTOMATION_TESTS && WITH_EDITOR
