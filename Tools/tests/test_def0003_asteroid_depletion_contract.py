import hashlib
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ASTEROID_HEADER = ROOT / "Source/RedMMO/RedMineableAsteroid.h"
ASTEROID_CPP = ROOT / "Source/RedMMO/RedMineableAsteroid.cpp"
SCENERY_CPP = ROOT / "Source/RedMMO/RedSpaceScenery.cpp"
BOLT_CPP = ROOT / "Source/RedMMO/RedBolt.cpp"
PICKUP_HEADER = ROOT / "Source/RedMMO/RedResourcePickup.h"
PICKUP_CPP = ROOT / "Source/RedMMO/RedResourcePickup.cpp"
EXPLOSION_HEADER = ROOT / "Source/RedMMO/RedShipExplosionFX.h"
EXPLOSION_CPP = ROOT / "Source/RedMMO/RedShipExplosionFX.cpp"
BUILD_RULES = ROOT / "Source/RedMMO/RedMMO.Build.cs"
PLAYER_HEADER = ROOT / "Source/RedMMO/RedPlayerCharacter.h"
PLAYER_CPP = ROOT / "Source/RedMMO/RedPlayerCharacter.cpp"
RED_HUD_HEADER = ROOT / "Source/RedMMO/RedHUD.h"
RED_HUD_CPP = ROOT / "Source/RedMMO/RedHUD.cpp"
PIXEL_HUD_HEADER = (
    ROOT / "Plugins/RedHUD/Source/RedHUDRuntime/Public/RedHUDWidget.h"
)
PIXEL_HUD_CPP = (
    ROOT / "Plugins/RedHUD/Source/RedHUDRuntime/Private/RedHUDWidget.cpp"
)
TWO_CLIENT_PIE_TEST = (
    ROOT / "Source/RedMMO/Tests/RedDEF0003TwoClientPIETests.cpp"
)
ACTUAL_FIELD_PIE_TEST = (
    ROOT / "Source/RedMMO/Tests/RedDEF0003ActualFieldPIETests.cpp"
)
ACTUAL_FIELD_TWO_CLIENT_CULL_PIE_TEST = (
    ROOT
    / "Source/RedMMO/Tests/RedDEF0003ActualFieldTwoClientCullPIETests.cpp"
)
ACTUAL_FIELD_TWO_CLIENT_DEPLETION_PIE_TEST = (
    ROOT
    / "Source/RedMMO/Tests/RedDEF0003ActualFieldTwoClientDepletionPIETests.cpp"
)
ACTUAL_FIELD_LATE_JOIN_PIE_TEST = (
    ROOT / "Source/RedMMO/Tests/RedDEF0003ActualFieldLateJoinPIETests.cpp"
)
DEFECT = ROOT / "ProjectKnowledge/defects/DEF-0003-asteroid-depletion-disappears.yaml"
ROLLBACK = Path(
    "D:/RedMMOTitanWindowsData/Rollback/BeforeDEF0003Depletion_20260722_1241"
)
AUDIO_ROLLBACK = Path(
    "D:/RedMMOTitanWindowsData/Rollback/BeforeDEF0003Audio_20260723_1348"
)
RUNTIME_LOG = Path(
    "D:/RedMMOTitanWindowsData/Diagnostics/ShipSurfaceRuntime_20260721_040045/runtime.log"
)
EXPECTED_RUNTIME_LOG_SHA256 = (
    "FC452ECD48BF9AE2077448B5BFD48D267A349594568D465B302CB14A8BB25D95"
)


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="strict")


def function_body(source: str, signature: str) -> str:
    start = source.index(signature)
    opening = source.index("{", start)
    depth = 0
    for index in range(opening, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[start : index + 1]
    raise AssertionError(f"unterminated function: {signature}")


class Def0003AsteroidDepletionContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.header = read(ASTEROID_HEADER)
        cls.asteroid = read(ASTEROID_CPP)
        cls.scenery = read(SCENERY_CPP)
        cls.bolt = read(BOLT_CPP)
        cls.pickup_header = read(PICKUP_HEADER)
        cls.pickup = read(PICKUP_CPP)
        cls.explosion_header = read(EXPLOSION_HEADER)
        cls.explosion = read(EXPLOSION_CPP)
        cls.build_rules = read(BUILD_RULES)
        cls.player_header = read(PLAYER_HEADER)
        cls.player = read(PLAYER_CPP)
        cls.red_hud_header = read(RED_HUD_HEADER)
        cls.red_hud = read(RED_HUD_CPP)
        cls.pixel_hud_header = read(PIXEL_HUD_HEADER)
        cls.pixel_hud = read(PIXEL_HUD_CPP)
        cls.two_client_pie = read(TWO_CLIENT_PIE_TEST)
        cls.actual_field_pie = read(ACTUAL_FIELD_PIE_TEST)
        cls.actual_field_two_client_cull_pie = read(
            ACTUAL_FIELD_TWO_CLIENT_CULL_PIE_TEST
        )
        cls.actual_field_two_client_depletion_pie = read(
            ACTUAL_FIELD_TWO_CLIENT_DEPLETION_PIE_TEST
        )
        cls.actual_field_late_join_pie = read(ACTUAL_FIELD_LATE_JOIN_PIE_TEST)
        cls.defect = read(DEFECT)
        cls.runtime = read(RUNTIME_LOG)

    def test_runtime_reaches_authoritative_zero_ore(self):
        self.assertEqual(
            hashlib.sha256(RUNTIME_LOG.read_bytes()).hexdigest().upper(),
            EXPECTED_RUNTIME_LOG_SHA256,
        )
        events = re.findall(
            r"Asteroid mined: RedMineableAsteroid_23 .*? extracted=(\d+) remaining=(\d+)",
            self.runtime,
        )
        self.assertEqual(
            events,
            [
                ("990", "5010"),
                ("990", "4020"),
                ("990", "3030"),
                ("990", "2040"),
                ("990", "1050"),
                ("990", "60"),
                ("60", "0"),
            ],
        )

    def test_mining_mutation_is_authority_owned_and_ore_is_replicated(self):
        mining = function_body(
            self.asteroid, "float ARedMineableAsteroid::RegisterMiningHit"
        )
        for token in (
            "!HasAuthority()",
            "OreRemaining <= 0.f",
            "FMath::Min(OreRemaining, MiningStrength * 18.f)",
            "OreRemaining = FMath::Max(0.f, OreRemaining - Extracted);",
            "FlushNetDormancy();",
            "ForceNetUpdate();",
        ):
            self.assertIn(token, mining)

        self.assertIn("ReplicatedUsing = OnRep_OreRemaining", self.header)
        replication = function_body(
            self.asteroid,
            "void ARedMineableAsteroid::GetLifetimeReplicatedProps",
        )
        self.assertIn("DOREPLIFETIME(ARedMineableAsteroid, OreRemaining);", replication)

    def test_depleted_relevancy_retains_terminal_state_with_existing_distance_gate(self):
        self.assertIn(
            "virtual bool IsNetRelevantFor(const AActor* RealViewer,"
            " const AActor* ViewTarget,",
            self.header,
        )
        relevance = function_body(
            self.asteroid,
            "bool ARedMineableAsteroid::IsNetRelevantFor",
        )
        for token in (
            "Super::IsNetRelevantFor(RealViewer, ViewTarget, SrcLocation)",
            "ERedMineableAsteroidDepletionPhase::Depleted",
            "return RootComponent && IsWithinNetRelevancyDistance(SrcLocation);",
        ):
            self.assertIn(token, relevance)
        for forbidden in (
            "bAlwaysRelevant = true",
            "SetActorEnableCollision(true)",
            "SetNetCullDistanceSquared",
        ):
            self.assertNotIn(forbidden, relevance)

        constructor = function_body(
            self.asteroid,
            "ARedMineableAsteroid::ARedMineableAsteroid",
        )
        self.assertIn("bAlwaysRelevant = false;", constructor)
        self.assertIn(
            "SetNetCullDistanceSquared(FMath::Square(5000000.f));",
            constructor,
        )

    def test_zero_ore_enters_one_way_authority_owned_transition(self):
        mining = function_body(
            self.asteroid, "float ARedMineableAsteroid::RegisterMiningHit"
        )
        begin = function_body(
            self.asteroid, "void ARedMineableAsteroid::BeginDepletion"
        )
        for token in (
            "DepletionState.Phase != ERedMineableAsteroidDepletionPhase::Active",
            "BeginDepletion(MiningInstigator);",
        ):
            self.assertIn(token, mining)
        for token in (
            "!HasAuthority()",
            "DepletionState.Phase = ERedMineableAsteroidDepletionPhase::Depleting;",
            "DepletionState.StartedServerTimeSeconds = GetSynchronizedServerTimeSeconds();",
            "++DepletionState.Sequence;",
            "ApplyDepletionPresentation();",
        ):
            self.assertIn(token, begin)

    def test_staged_transition_has_delay_and_durable_late_join_result(self):
        for token in (
            "ERedMineableAsteroidDepletionPhase",
            "Active",
            "Depleting",
            "Depleted",
            "StartedServerTimeSeconds",
            "PresentationDurationSeconds",
            "Sequence",
            "bRewardSpawned",
            "bRewardGranted",
            "ReplicatedUsing = OnRep_DepletionState",
            "FTimerHandle DepletionTimer",
        ):
            self.assertIn(token, self.header)

        presentation = function_body(
            self.asteroid, "void ARedMineableAsteroid::ApplyDepletionPresentation"
        )
        for token in (
            "SetActorEnableCollision(false);",
            "SetActorHiddenInGame(false);",
            "SetActorHiddenInGame(true);",
            "GetSynchronizedServerTimeSeconds()",
            "SynchronizedNow < 0.f",
            "&ARedMineableAsteroid::ApplyDepletionPresentation, 0.05f",
            "GetWorldTimerManager().SetTimer",
        ):
            self.assertIn(token, presentation)

        clock = function_body(
            self.asteroid,
            "float ARedMineableAsteroid::GetSynchronizedServerTimeSeconds",
        )
        self.assertIn("GameState->GetServerWorldTimeSeconds()", clock)
        self.assertIn("HasAuthority() ? World->GetTimeSeconds() : -1.f", clock)

        finish = function_body(
            self.asteroid, "void ARedMineableAsteroid::FinishDepletion"
        )
        self.assertIn("DepletionState.Sequence != ExpectedSequence", finish)
        self.assertIn(
            "DepletionState.Phase = ERedMineableAsteroidDepletionPhase::Depleted;",
            finish,
        )
        self.assertNotIn("Destroy()", self.asteroid)

        replication = function_body(
            self.asteroid,
            "void ARedMineableAsteroid::GetLifetimeReplicatedProps",
        )
        self.assertIn("DOREPLIFETIME(ARedMineableAsteroid, DepletionState);", replication)

    def test_sequence_stays_unsigned_and_is_not_blueprint_exposed(self):
        sequence_property = re.search(
            r"UPROPERTY\((?P<specifiers>[^)]*)\)\s*"
            r"uint32\s+Sequence\s*=\s*0\s*;",
            self.header,
        )
        self.assertIsNotNone(sequence_property)
        specifiers = sequence_property.group("specifiers")
        self.assertIn("VisibleInstanceOnly", specifiers)
        self.assertNotIn("BlueprintReadOnly", specifiers)
        self.assertNotIn("BlueprintReadWrite", specifiers)
        self.assertIn(
            "void FinishDepletion(uint32 ExpectedSequence);",
            self.header,
        )
        self.assertEqual(
            self.asteroid.count("++DepletionState.Sequence;"),
            2,
        )
        presentation = function_body(
            self.asteroid, "void ARedMineableAsteroid::ApplyDepletionPresentation"
        )
        self.assertIn(
            "FinishDepletion(DepletionState.Sequence);",
            presentation,
        )
        self.assertRegex(
            presentation,
            r"FinishDelegate\.BindUObject\("
            r"[\s\S]*?&ARedMineableAsteroid::FinishDepletion,"
            r"\s*DepletionState\.Sequence\);",
        )

        outer_state_property = re.search(
            r"UPROPERTY\((?P<specifiers>[^)]*"
            r"ReplicatedUsing\s*=\s*OnRep_DepletionState[^)]*)\)\s*"
            r"FRedMineableAsteroidDepletionState\s+DepletionState\s*;",
            self.header,
            flags=re.DOTALL,
        )
        self.assertIsNotNone(outer_state_property)
        self.assertIn(
            "BlueprintReadOnly",
            outer_state_property.group("specifiers"),
        )

    def test_destruction_and_reward_handoffs_are_authority_owned_and_idempotent(self):
        begin = function_body(
            self.asteroid, "void ARedMineableAsteroid::BeginDepletion"
        )
        self.assertNotIn("SpawnForDepletedAsteroid", begin)
        self.assertIn("TrySpawnDepletionReward(MiningInstigator);", begin)

        finish = function_body(
            self.asteroid, "void ARedMineableAsteroid::FinishDepletion"
        )
        self.assertIn("ARedShipExplosionFX::SpawnForDepletedAsteroid(", finish)
        self.assertLess(
            finish.index("ApplyDepletionPresentation();"),
            finish.index("SpawnForDepletedAsteroid"),
        )
        self.assertIn("ExplosionStartedServerTimeSeconds", finish)

        reward = function_body(
            self.asteroid, "void ARedMineableAsteroid::TrySpawnDepletionReward"
        )
        for token in (
            "!HasAuthority()",
            "DepletionState.bRewardSpawned",
            "SpawnActorDeferred<ARedResourcePickup>",
            "Reward->InitResource",
            "FinishSpawningActor",
            "DepletionState.bRewardSpawned = true;",
            "RewardPlayer->AddResource",
            "DepletionState.bRewardGranted = true;",
            "/*bInCollectible=*/!DepletionState.bRewardGranted",
        ):
            self.assertIn(token, reward)

        impact = function_body(self.bolt, "void ARedBolt::OnHit")
        self.assertIn("MineableAsteroid->RegisterMiningHit(", impact)
        self.assertNotRegex(
            impact,
            r"(?:const\s+)?float\s+\w+\s*=\s*MineableAsteroid->RegisterMiningHit",
        )

    def test_reward_pickup_is_replicated_finite_range_and_authority_consumed_once(self):
        for token in (
            "ReplicatedUsing = OnRep_ResourceDefinition",
            "FVector_NetQuantizeNormal RadialUp",
            "bool bConsumed = false",
            "bool bCollectible = true",
        ):
            self.assertIn(token, self.pickup_header)
        for token in (
            "bReplicates = true;",
            "bAlwaysRelevant = false;",
            "SetNetCullDistanceSquared(FMath::Square(1500000.f));",
        ):
            self.assertIn(token, self.pickup)

        collection = function_body(
            self.pickup, "void ARedResourcePickup::OnCollectOverlap"
        )
        self.assertLess(collection.index("!HasAuthority()"), collection.index("Player->AddResource"))
        self.assertLess(collection.index("!bCollectible"), collection.index("Player->AddResource"))
        self.assertLess(collection.index("bConsumed = true;"), collection.index("Player->AddResource"))
        self.assertLess(
            collection.index("SetCollisionEnabled(ECollisionEnabled::NoCollision);"),
            collection.index("Player->AddResource"),
        )

        replication = function_body(
            self.pickup,
            "void ARedResourcePickup::GetLifetimeReplicatedProps",
        )
        for field in ("ResourceType", "Amount", "bCollectible", "RadialUp"):
            self.assertIn(f"DOREPLIFETIME(ARedResourcePickup, {field});", replication)

        initialize = function_body(
            self.pickup, "void ARedResourcePickup::InitResource"
        )
        self.assertIn("InitialLifeSpan = 4.f;", initialize)
        self.assertIn("ApplyCollectionState();", initialize)
        collection_state = function_body(
            self.pickup, "void ARedResourcePickup::ApplyCollectionState"
        )
        self.assertIn("HasAuthority() && bCollectible && !bConsumed", collection_state)
        self.assertIn("ECollisionEnabled::NoCollision", collection_state)

    def test_reward_inventory_is_authority_owned_replicated_and_refreshes_owner_hud(self):
        for field in ("ResStone", "ResIron", "ResCrystal"):
            self.assertRegex(
                self.player_header,
                rf"ReplicatedUsing\s*=\s*OnRep_Resources[\s\S]*?int32\s+{field}\s*=\s*0;",
            )

        add_resource = function_body(
            self.player, "void ARedPlayerCharacter::AddResource"
        )
        self.assertLess(add_resource.index("!HasAuthority()"), add_resource.index("ResCrystal"))
        self.assertIn("UpdateHUDResources();", add_resource)
        self.assertIn("ForceNetUpdate();", add_resource)
        on_rep = function_body(
            self.player, "void ARedPlayerCharacter::OnRep_Resources"
        )
        self.assertIn("UpdateHUDResources();", on_rep)

        replication = function_body(
            self.player,
            "void ARedPlayerCharacter::GetLifetimeReplicatedProps",
        )
        for field in ("ResStone", "ResIron", "ResCrystal"):
            self.assertIn(f"DOREPLIFETIME(ARedPlayerCharacter, {field});", replication)

    def test_direct_credit_reward_audio_is_exactly_once_and_local_owner_only(self):
        expected_asset = (
            "/Game/Vefects/Sand_VFX/Audio/"
            "SFX_Vefects_Sand_Rock_Hit_02_Cue."
            "SFX_Vefects_Sand_Rock_Hit_02_Cue"
        )
        self.assertIn(expected_asset, self.pickup)
        self.assertIn("DidStartLocalRewardSound", self.pickup_header)
        self.assertIn("GetRewardSoundAssetPath", self.pickup_header)
        self.assertIn("virtual void OnRep_Instigator() override;", self.pickup_header)

        playback = function_body(
            self.pickup, "void ARedResourcePickup::TryStartLocalRewardSound"
        )
        for token in (
            "bLocalRewardSoundStarted",
            "bCollectible",
            "GetNetMode() == NM_DedicatedServer",
            "GetInstigator()",
            "RewardInstigator->IsLocallyControlled()",
            "UGameplayStatics::SpawnSound2D",
            "bLocalRewardSoundStarted = IsValid(RewardSoundComponent);",
        ):
            self.assertIn(token, playback)
        self.assertLess(
            playback.index("RewardInstigator->IsLocallyControlled()"),
            playback.index("UGameplayStatics::SpawnSound2D"),
        )

        for signature in (
            "void ARedResourcePickup::InitResource",
            "void ARedResourcePickup::BeginPlay",
            "void ARedResourcePickup::OnRep_ResourceDefinition",
            "void ARedResourcePickup::OnRep_Instigator",
        ):
            self.assertIn("TryStartLocalRewardSound();", function_body(self.pickup, signature))
        instigator_rep = function_body(
            self.pickup, "void ARedResourcePickup::OnRep_Instigator"
        )
        self.assertLess(
            instigator_rep.index("Super::OnRep_Instigator();"),
            instigator_rep.index("TryStartLocalRewardSound();"),
        )
        self.assertNotIn("SpawnSound", function_body(
            self.player, "void ARedPlayerCharacter::OnRep_Resources"
        ))

    def test_destruction_audio_retains_exact_cue_and_exposes_local_start_proof(self):
        expected_asset = (
            "/Game/Vefects/Sand_VFX/Audio/"
            "SFX_Vefects_Sand_Rock_Eruption_Hit_Cue."
            "SFX_Vefects_Sand_Rock_Eruption_Hit_Cue"
        )
        self.assertIn(expected_asset, self.explosion)
        self.assertIn("DidStartLocalExplosionSound", self.explosion_header)
        self.assertIn("GetExplosionSoundAssetPath", self.explosion_header)
        primary = function_body(
            self.explosion, "void ARedShipExplosionFX::SpawnPrimaryCosmetics"
        )
        self.assertIn("UGameplayStatics::SpawnSoundAtLocation", primary)
        self.assertIn(
            "bLocalExplosionSoundStarted = IsValid(ExplosionSoundComponent);",
            primary,
        )
        self.assertNotIn("UGameplayStatics::PlaySoundAtLocation", primary)

    def test_real_gpu_depletion_harness_is_explicit_non_shipping_and_bounded(self):
        flag = 'FParse::Param(FCommandLine::Get(), TEXT("RedDEF0003DepletionAutoCapture"))'
        self.assertIn(flag, self.player)
        self.assertLess(self.player.index("#if !UE_BUILD_SHIPPING"), self.player.index(flag))
        for token in (
            "RedDEF0003AuditAsteroid",
            "Asteroid->SetFlags(RF_Transient);",
            "Asteroid->OreCapacity = 18.f;",
            "Asteroid->DepletionPresentationSeconds = 2.f;",
            "Asteroid->RegisterMiningHit(1.f, WeakThis.Get())",
            "Explosion->GetOwner() != Asteroid",
            "It->GetOwner() == Asteroid",
            "RED_DEF0003_BEFORE",
            "RED_DEF0003_BEGIN",
            "RED_DEF0003_MID",
            "RED_DEF0003_RESULT",
            "acceptancePass=%d",
            "RED_DEF0003_COMPLETE requesting_clean_exit=1",
            "FScreenshotRequest::RequestScreenshot",
            "Filename, true, false, false, FIntRect(), true",
            "FPlatformMisc::RequestExit(false);",
        ):
            self.assertIn(token, self.player)

    def test_visual_harness_proves_surface_absence_then_uses_credible_deep_space_framing(self):
        flag = 'FParse::Param(FCommandLine::Get(), TEXT("RedDEF0003DepletionAutoCapture"))'
        start = self.player.index(flag)
        harness = self.player[start:self.player.index("#endif", start)]
        for token in (
            "RED_DEF0008_SURFACE",
            'ScheduleDEF0003Capture(6.1f, TEXT("Surface"))',
            "ViewAltitudeCm < RedPlanetPresentationTuning::AtmosphereHeightCm",
            "ProductionFieldCount == 24",
            "AuditAsteroidCount == 0",
            "DeepSpaceAsteroidInnerAltitudeCm",
            "DeepSpaceAsteroidOuterAltitudeCm",
            "PlanetCenter + Up * (SurfaceRadius + TargetAltitudeCm)",
            "AsteroidRenderCullDistanceCm",
            "FramingRadius * 10.f",
            "AngularDiameterDegrees >= 3.f",
            "AngularDiameterDegrees <= 14.f",
            'TEXT("SpaceBefore")',
            'TEXT("SpaceReward")',
            'TEXT("SpaceAfter")',
            "PristineProductionMembers == 24",
            "productionUnaffected=%d",
            "staticMesh=%s voxel=0",
        ):
            self.assertIn(token, harness)
        for forbidden in (
            "PawnLocation + Up * 12000.f + Forward * 10000.f",
            "SetPresentationCullDistance(0.f)",
            "FramingRadius * 4.2f",
        ):
            self.assertNotIn(forbidden, harness)
        self.assertLess(
            harness.index('ScheduleDEF0003Capture(6.1f, TEXT("Surface"))'),
            harness.index("SpawnActorDeferred<ARedMineableAsteroid>"),
        )
        self.assertLess(
            harness.index("SpawnActorDeferred<ARedMineableAsteroid>"),
            harness.index('TEXT("SpaceBefore")'),
        )

    def test_visual_harness_has_optional_native_ultrawide_mid_fade_gate(self):
        flag = 'FParse::Param(FCommandLine::Get(), TEXT("RedDEF0003DepletionAutoCapture"))'
        start = self.player.index(flag)
        harness = self.player[start:self.player.index("#endif", start)]
        for token in (
            "RedDEF0004UltrawideReceiptAudit",
            "RED_DEF0004_ULTRAWIDE_FADE",
            "ViewportWidth == 3440",
            "ViewportHeight == 1440",
            "ViewportAspect > 2.30f",
            "MiningResultSeconds > 0.0f",
            "MiningResultSeconds < 0.70f",
            'MiningResultText == TEXT("IRON  +6")',
            'ScheduleDEF0003Capture(13.46f, TEXT("SpaceFade"))',
            "&& *UltrawideFadePassed",
            "ultrawideAudit=%d",
            "ultrawideFade=%d",
        ):
            self.assertIn(token, harness)
        fade = harness.index("RED_DEF0004_ULTRAWIDE_FADE pass=%d")
        result = harness.index("RED_DEF0003_RESULT acceptancePass=%d")
        self.assertLess(fade, result)

    def test_two_client_pie_gate_uses_one_process_and_real_network_worlds(self):
        for token in (
            "PIE_ListenServer",
            "SetPlayNumberOfClients(2)",
            "SetRunUnderOneProcess(true)",
            "bLaunchSeparateServer = false",
            "bAllowOnlineSubsystem = false",
            "Worlds.PIEWorldCount != 2",
            "Worlds.ListenServerCount != 1",
            "Worlds.ClientCount != 1",
            "PlayerIdentitiesMatch(Players)",
            "GetPlayerId()",
            "RedMMO.Mining.DEF0003.TwoClientPIEParity",
        ):
            self.assertIn(token, self.two_client_pie)

    def test_two_client_pie_gate_checks_competing_hits_remote_state_and_visuals(self):
        for token in (
            "Asteroid->RegisterMiningHit(1.f, Players.RemoteServerPawn)",
            "Asteroid->RegisterMiningHit(1.f, Players.HostPawn)",
            "FrameBefore == FrameAfter",
            "AggregateDelta == 6 && RemoteDelta == 6 && HostDelta == 0",
            "ProxyAsteroid->DepletionState.Sequence == 1",
            "ProxyAsteroid->DepletionState.Sequence == 2",
            "ClientExplosion.SimulatingDebris >= 8",
            "ServerReceipts == 1 && ClientReceipts == 1",
            "QueryRemoteHUD(",
            "QueryHostHUD(",
            'RemoteHUDText == TEXT("IRON  +6")',
            "RemoteHUDSeconds > 0.0f",
            "HostHUDText.IsEmpty()",
            "AwaitReceiptExpiry",
            "!bRemoteHUDVisible",
            "RemoteHUDSeconds <= 0.0f",
            "CaptureRemoteClientWindow",
            "DEF0003_MP_Remote_SpaceReward.png",
            "DEF0003_MP_Remote_SpaceExplosion.png",
            "DEF0003_MP_Remote_SpaceAfter.png",
            "RED_DEF0003_MP_REWARD",
            "RED_DEF0003_MP_RECEIPT_EXPIRED",
            "RED_DEF0003_MP_RESULT acceptancePass=1",
            "RED_DEF0003_MP_COMPLETE pieEnded=1",
            "steamTransport=0",
        ):
            self.assertIn(token, self.two_client_pie)

    def test_two_client_remote_receipt_gate_uses_deep_space_production_presentation(
        self,
    ):
        source = self.two_client_pie
        for token in (
            "MiningResultLifetimeSeconds = 3.25f",
            "RedGravity::FindMeshPlanet",
            "PlanetCenter + Up * (SurfaceRadius + TargetAltitudeCm)",
            "DeepSpaceAsteroidInnerAltitudeCm",
            "DeepSpaceAsteroidOuterAltitudeCm",
            "AsteroidRenderCullDistanceCm",
            "SetActorScale3D(FVector::OneVector)",
            "FramingRadius * 10.f",
            "AngularDiameterDegrees >= 3.f",
            "AngularDiameterDegrees <= 14.f",
            "ExpectedRemotePawnLocation",
            "RemotePawnTargetDistanceCm",
            "Movement->DisableMovement()",
            "ForceNetUpdate()",
            "GetProductionFieldStats",
            "ProductionStats.Count",
            "ProductionStats.Pristine",
            "DEF0003_MP_Remote_SpaceBefore.png",
            "staticMesh=%s voxel=0",
            "deepSpace=1",
            "atmosphericTarget=0",
            "remoteOwnerReceipt=1",
            "transientMiningReceipt=1",
            "receiptExpired=1",
            "persistentResourceTally=0",
            "productionField=24",
            "pristineProduction=24",
            "productionUnaffected=1",
            "cutoffOverridden=0",
            "scaleOverridden=0",
            "evidenceClass=automation",
        ):
            self.assertIn(token, source)
        for forbidden in (
            "+ Up * 3000.f + Forward * 9000.f",
            "SetActorScale3D(FVector(3.f))",
            "SetPresentationCullDistance(0.f)",
            "Radius * 4.2f",
        ):
            self.assertNotIn(forbidden, source)

        before = source.index("RED_DEF0003_MP_BEFORE")
        reward = source.index("RED_DEF0003_MP_REWARD")
        final = source.index("RED_DEF0003_MP_FINAL")
        expired = source.index("RED_DEF0003_MP_RECEIPT_EXPIRED")
        result = source.index("RED_DEF0003_MP_RESULT acceptancePass=1")
        self.assertLess(before, reward)
        self.assertLess(reward, final)
        self.assertLess(final, expired)
        self.assertLess(expired, result)

    def test_field_members_have_authority_initialized_immutable_replicated_identity(self):
        for token in (
            "bool InitializeStableMemberId(FName InStableMemberId);",
            "FName GetStableMemberId() const { return StableMemberId; }",
            "BlueprintReadOnly, Replicated",
            "FName StableMemberId = NAME_None;",
        ):
            self.assertIn(token, self.header)

        initialize = function_body(
            self.asteroid,
            "bool ARedMineableAsteroid::InitializeStableMemberId",
        )
        for token in (
            "!HasAuthority()",
            "InStableMemberId.IsNone()",
            "!StableMemberId.IsNone()",
            "StableMemberId == InStableMemberId",
            "StableMemberId = InStableMemberId;",
        ):
            self.assertIn(token, initialize)
        self.assertEqual(initialize.count("StableMemberId = InStableMemberId;"), 1)

        begin = function_body(self.asteroid, "void ARedMineableAsteroid::BeginPlay")
        self.assertIn("StableMemberId.IsNone()", begin)
        self.assertIn("StableMemberId.ToString()", begin)
        replication = function_body(
            self.asteroid,
            "void ARedMineableAsteroid::GetLifetimeReplicatedProps",
        )
        self.assertIn(
            "DOREPLIFETIME(ARedMineableAsteroid, StableMemberId);",
            replication,
        )

    def test_mars_field_spawns_atomic_named_members_with_canonical_ids(self):
        build = function_body(self.scenery, "void ARedSpaceScenery::BuildScenery")
        for token in (
            "constexpr int32 MineableCount = 24;",
            "FRandomStream MineableAsteroidStream(0x4F524531)",
            'TEXT("RedMineableAsteroid_%02d")',
            "Params.Owner = this;",
            "Params.bDeferConstruction = true;",
            'TEXT("asteroid-field.red.mars.deep-space/0x4F524531/%02d")',
            "Mineable->InitializeStableMemberId(StableMemberId)",
            'Mineable->Tags.AddUnique(TEXT("RedMarsMineableBelt"));',
            "AsteroidRenderCullDistanceCm",
            "UGameplayStatics::FinishSpawningActor(Mineable, SpawnTransform);",
        ):
            self.assertIn(token, build)
        self.assertLess(
            build.index("Mineable->InitializeStableMemberId(StableMemberId)"),
            build.index("UGameplayStatics::FinishSpawningActor(Mineable, SpawnTransform);"),
        )
        self.assertLess(
            build.index('Mineable->Tags.AddUnique(TEXT("RedMarsMineableBelt"));'),
            build.index("UGameplayStatics::FinishSpawningActor(Mineable, SpawnTransform);"),
        )

    def test_actual_field_pie_gate_uses_real_member_identity_range_and_depletion(self):
        for token in (
            "RedMMO.Mining.DEF0003.ActualGeneratedFieldMemberPIE",
            "PIE_Standalone",
            "SetPlayNumberOfClients(1)",
            "StableMemberId(TargetOrdinal)",
            "ResolveFieldCohort",
            "ReplayExpectedTransform",
            "Target->GetStableMemberId() == TargetId",
            "Target->GetOwner() == Scenery",
            "!Target->HasAnyFlags(RF_Transient)",
            "RockMesh->WasRecentlyRendered(1.5f)",
            "RockMesh->LDMaxDrawDistance",
            "RockMesh->CachedMaxDrawDistance",
            "TraceExactTarget",
            "Target->RegisterMiningHit(55.f, Runtime.Pawn)",
            "CountOtherPristineMembers",
            "DEF0003_Field_Before.png",
            "DEF0003_Field_Transition.png",
            "DEF0003_Field_Explosion.png",
            "RED_DEF0003_FIELD_RESULT acceptancePass=1",
            "actualFieldMember=1",
            "stableIdentity=1",
            "playerControlledTravel=0",
            "projectileDelivery=0",
            "steamTransport=0",
            "RED_DEF0003_FIELD_COMPLETE pieEnded=1",
        ):
            self.assertIn(token, self.actual_field_pie)
        for forbidden in (
            "SpawnActorDeferred<ARedMineableAsteroid>",
            "OreCapacity = 18.f",
            "SetPresentationCullDistance(0.f)",
            "SetActorScale3D(FVector(3.f))",
        ):
            self.assertNotIn(forbidden, self.actual_field_pie)

    def test_actual_field_two_client_gate_proves_uncustomized_peer_culling(self):
        source = self.actual_field_two_client_cull_pie
        for token in (
            "RedMMO.Mining.DEF0003.ActualFieldTwoClientCullPIE",
            "PIE_ListenServer",
            "SetPlayNumberOfClients(2)",
            "SetRunUnderOneProcess(true)",
            "RequestParams.bAllowOnlineSubsystem = false;",
            "TargetStableIdText",
            "asteroid-field.red.mars.deep-space/0x4F524531/23",
            "ResolveAuthorityField",
            "FindUniqueStableMember",
            "TaggedCount == MineableCount",
            "TargetStateIsUnchanged",
            "TargetCullDistanceCm",
            "GetPresentationCullDistance()",
            "LDMaxDrawDistance",
            "CachedMaxDrawDistance",
            'TEXT("r.ViewDistanceScale")',
            "GetLastRenderTimeOnScreen()",
            "WasRecentlyRendered(",
            "ReferenceIsRendering",
            "TraceExactTarget",
            "ProjectWorldLocationToScreen",
            "NearCenterDistanceCm",
            "FarCenterDistanceCm",
            "GetNetCullDistanceSquared()",
            "ActualNetCullDistanceCm",
            "ProjectedTargetDiameterPx",
            "DEF0003_Field_MP_Server_Near.png",
            "DEF0003_Field_MP_Client_Near.png",
            "DEF0003_Field_MP_Server_Far.png",
            "DEF0003_Field_MP_Client_Far.png",
            "RED_DEF0003_FIELD_MP_CULL_INITIAL_FAR pass=1",
            "RED_DEF0003_FIELD_MP_CULL_NEAR pass=1",
            "RED_DEF0003_FIELD_MP_CULL_CLIENT_FAR pass=1",
            "RED_DEF0003_FIELD_MP_CULL_SERVER_FAR pass=1",
            "RED_DEF0003_FIELD_MP_CULL_RESULT acceptancePass=1",
            "actualFieldMember=1",
            "stableIdentity=1",
            "reciprocalNearFarCull=1",
            "cutoffOverridden=0",
            "mining=0",
            "playerControlledTravel=0",
            "projectileDelivery=0",
            "steamTransport=0",
            "RED_DEF0003_FIELD_MP_CULL_COMPLETE pieEnded=1",
        ):
            self.assertIn(token, source)

        for forbidden in (
            "SpawnActorDeferred<ARedMineableAsteroid>",
            "SpawnActor<ARedMineableAsteroid>",
            "RegisterMiningHit(",
            "Target->SetActorScale3D",
            "Target->SetPresentationCullDistance",
            "AuthorityTarget->SetPresentationCullDistance",
            "ProxyTarget->SetPresentationCullDistance",
            "PresentationCullDistanceCm =",
            "Target->SetCachedMaxDrawDistance",
            "AuthorityTarget->SetCachedMaxDrawDistance",
            "ProxyTarget->SetCachedMaxDrawDistance",
            "Target->LDMaxDrawDistance =",
            "AuthorityTarget->LDMaxDrawDistance =",
            "ProxyTarget->LDMaxDrawDistance =",
            "Target->CachedMaxDrawDistance =",
            "AuthorityTarget->CachedMaxDrawDistance =",
            "ProxyTarget->CachedMaxDrawDistance =",
        ):
            self.assertNotIn(forbidden, source)

        self.assertEqual(source.count("SetCullDistance("), 1)
        self.assertIn("ReferenceMesh->SetCullDistance(0.f);", source)

    def test_actual_field_two_client_depletion_gate_proves_reward_hud_and_peer_parity(
        self,
    ):
        source = self.actual_field_two_client_depletion_pie
        for token in (
            "RedMMO.Mining.DEF0003.ActualFieldTwoClientDepletionPIE",
            "PIE_ListenServer",
            "SetPlayNumberOfClients(2)",
            "SetRunUnderOneProcess(true)",
            "RequestParams.bAllowOnlineSubsystem = false;",
            "TargetStableIdText",
            "asteroid-field.red.mars.deep-space/0x4F524531/23",
            "ResolveAuthorityField",
            "FindUniqueStableMember",
            "TaggedCount == MineableCount",
            "CountOtherPristineMembers",
            "MineableCount - 1",
            '#include "../RedBolt.h"',
            '#include "UObject/StructOnScope.h"',
            "InvokeClientServerFireRPC",
            "FUNC_Net | FUNC_NetServer | FUNC_NetReliable",
            "ClientPawn->GetLocalRole() != ROLE_AutonomousProxy",
            "ClientPawn->GetWorld()->GetNetMode() != NM_Client",
            "ClientPawn->ProcessEvent(",
            "ExpectedProjectileExtraction = 180.f",
            "ProjectileStandOffDistanceCm = 12000.f",
            "PathHit.GetActor() != AuthorityTarget",
            "PathDistanceCm > 18000.f",
            "RED_DEF0003_FIELD_MP_PROJECTILE_RPC_SUBMIT pass=1",
            "RED_DEF0003_FIELD_MP_PROJECTILE_DELIVERY pass=1",
            "ownerInstigatorParity=1",
            "for (int32 HitIndex = 0; HitIndex < 5; ++HitIndex)",
            "RegisterMiningHit(55.f, Players.RemoteServerPawn)",
            "RegisterMiningHit(55.f, Players.HostPawn)",
            "FrameBefore == FrameAfter",
            "AggregateDelta == 6 && RemoteDelta == 6 && HostDelta == 0",
            "FMath::IsNearlyEqual(TotalExtracted, InitialCapacity)",
            "FMath::IsNearlyEqual(RemoteFinalExtracted, 870.f)",
            "ProxyTarget->DepletionState.Sequence == 1",
            "ProxyTarget->DepletionState.Sequence == 2",
            "ServerReceipts == 1 && ClientReceipts == 1",
            "ServerExplosion.Count == 1",
            "ClientExplosion.Count == 1",
            "ClientExplosion.SimulatingDebris >= 8",
            "QueryRemoteHUD",
            'HUDText == TEXT("IRON  +6")',
            "QueryRemoteHUD(Players, 0",
            "DEF0003_Field_MP_Depletion_Before.png",
            "DEF0003_Field_MP_Depletion_Transition.png",
            "DEF0003_Field_MP_Depletion_Explosion.png",
            "RED_DEF0003_FIELD_MP_DEPLETION_RESULT acceptancePass=1",
            "actualFieldMember=1",
            "stableIdentity=1",
            "exactOnceReward=1",
            "resourceTotalsParity=1",
            "transientMiningReceipt=1",
            "persistentResourceTally=0",
            "pristinePeers=23",
            "cutoffOverridden=0",
            "testTeleport=1",
            "playerControlledTravel=0",
            "projectileDelivery=1",
            "clientOriginatedRPC=1",
            "physicalFireInput=0",
            "steamTransport=0",
            "RED_DEF0003_FIELD_MP_DEPLETION_COMPLETE pieEnded=1",
        ):
            self.assertIn(token, source)

        for forbidden in (
            "SpawnActorDeferred<ARedMineableAsteroid>",
            "SpawnActor<ARedMineableAsteroid>",
            "Target->SetActorScale3D",
            "AuthorityTarget->SetActorScale3D",
            "ProxyTarget->SetActorScale3D",
            "Target->SetPresentationCullDistance",
            "AuthorityTarget->SetPresentationCullDistance",
            "ProxyTarget->SetPresentationCullDistance",
            "PresentationCullDistanceCm =",
            "Target->SetCachedMaxDrawDistance",
            "AuthorityTarget->SetCachedMaxDrawDistance",
            "ProxyTarget->SetCachedMaxDrawDistance",
            "Target->LDMaxDrawDistance =",
            "AuthorityTarget->LDMaxDrawDistance =",
            "ProxyTarget->LDMaxDrawDistance =",
            "Target->CachedMaxDrawDistance =",
            "AuthorityTarget->CachedMaxDrawDistance =",
            "ProxyTarget->CachedMaxDrawDistance =",
            "ServerFire_Implementation",
        ):
            self.assertNotIn(forbidden, source)

    def test_actual_field_two_client_gate_requires_rendered_destruction_pixels(
        self,
    ):
        source = self.actual_field_two_client_depletion_pie
        for token in (
            'TEXT("PrimaryPIEClientIndex")',
            "SetPropertyValue_InContainer(PlaySettings, 1)",
            "GetPrimaryPIEClientIndex() != 1",
            "AwaitDestructionPixels",
            "CaptureRemoteClientViewport",
            "Viewport->ReadPixels",
            "ProjectWorldLocationToScreen",
            "WasRecentlyRendered(0.25f)",
            "FlashLuminousPixels < 1000",
            "FlashWarmPixels < 100",
            "HotPixelMatched >= 3",
            "CountMovingHotPieces",
            "MovingHotPieces >= 3",
            "CountChangedPixelsInRect",
            "DebrisChangedPixels >= 256",
            "LateLuminousPixels",
            "LateWarmPixels",
            "DEF0003_Field_MP_Depletion_Debris_A.png",
            "DEF0003_Field_MP_Depletion_Debris_B.png",
            "destructionPixels=1",
            "flashPixels=1",
            "debrisPixels=1",
            "debrisMotion=1",
        ):
            self.assertIn(token, source)

        self.assertIn(
            "DestructionCameraDistanceCm = 30000.f",
            source,
        )
        self.assertNotIn("SetPresentationCullDistance(0.f)", source)

    def test_actual_field_two_client_audio_gate_records_owner_routing_and_wav(self):
        source = self.actual_field_two_client_depletion_pie
        for token in (
            '#include "AudioMixerBlueprintLibrary.h"',
            "UAudioMixerBlueprintLibrary::StartRecordingOutput",
            "UAudioMixerBlueprintLibrary::StopRecordingOutput",
            "EAudioRecordingExportType::WavFile",
            "GetReceiptAudioStats",
            "ServerRewardAudio.SoundStarted == 0",
            "ClientRewardAudio.SoundStarted == 1",
            "ServerRewardAudio.LocallyControlledInstigator == 0",
            "ClientRewardAudio.LocallyControlledInstigator == 1",
            "ServerExplosion.SoundStarted == 1",
            "ClientExplosion.SoundStarted == 1",
            "AnalyzePcmWav",
            "Wav.PeakAbsoluteSample >= 256",
            "Wav.ActiveSampleCount >= 1000",
            "MinimumCapturedAudioSeconds = 1.5",
            "DurationSeconds >= MinimumCapturedAudioSeconds",
            "RED_DEF0003_FIELD_MP_DEPLETION_AUDIO_CAPTURE",
            "SessionDirectoryName",
            "FDateTime::UtcNow().ToString",
            "FPlatformProcess::GetCurrentProcessId()",
            "FGuid::NewGuid().ToString(EGuidFormats::Digits)",
            'TEXT("Automation")',
            'TEXT("EnableGameSound")',
            'TEXT("CreateAudioDeviceForEveryPlayer")',
            'TEXT("SoloAudioInFirstPIEClient")',
            "SetPropertyValue_InContainer",
            "IsCreateAudioDeviceForEveryPlayer()",
            "EnsurePIEAudioIsUnmuted",
            "FAudioDeviceHandle",
            "ServerAudio.GetDeviceID() == ClientAudio.GetDeviceID()",
            "ClientAudio->IsAudioDeviceMuted()",
            "ClientAudio->GetPrimaryVolume()",
            "audioDeviceIds=%u/%u",
            "TogglePlayAllDeviceAudio",
            "IsPlayAllDeviceAudio",
            "RestorePIEAudioOverride",
            "ULevelEditorMiscSettings",
            "bAllowBackgroundAudio",
            "FApp::GetVolumeMultiplier()",
            "bRestoreAllowBackgroundAudio",
            "backgroundAudioOverride=%d",
            "pieAudioDeviceUnmuted=1",
            "evidenceClass=automation",
            "rewardAudioOwnerComponent=1",
            "destructionAudioComponents=1",
            "separatePIEAudioDevices=1",
            "clientMixerWavNonSilent=1",
            "independentPlayerListening=0",
            "mixQuality=0",
            "packageAudio=0",
        ):
            self.assertIn(token, source)
        self.assertIn('"AudioMixer"', self.build_rules)
        self.assertLess(
            self.build_rules.index("if (Target.bBuildEditor)"),
            self.build_rules.index('"AudioMixer"'),
        )

    def test_actual_field_late_join_gate_uses_true_bounded_client_connections(self):
        source = self.actual_field_late_join_pie
        for token in (
            "GEditor->RequestLateJoin();",
            "PlaySettings->SetPlayNumberOfClients(1);",
            "PlaySettings->SetRunUnderOneProcess(true);",
            "RequestParams.bAllowOnlineSubsystem = false;",
            "Worlds.ServerPIEInstance != 0",
            "Worlds.ClientPIEInstance != 1",
            "PlayerIdentitiesMatch(Players)",
            "DuringJoinPresentationSeconds = 8.f",
            "ExplosionNetworkCullDistanceCm = 1500000.f",
            "AsteroidNetworkCullDistanceCm = 5000000.f",
            "MissingProxyDiagnosticSeconds = 1.0",
            "RED_DEF0003_FIELD_LATE_JOIN_DEPLETING",
            "RED_DEF0003_FIELD_LATE_JOIN_REPLAY_INSIDE",
            "RED_DEF0003_FIELD_LATE_JOIN_REPLAY_OUTSIDE",
            "RED_DEF0003_FIELD_LATE_JOIN_DURABLE",
            "RED_DEF0003_FIELD_LATE_JOIN_MISSING_PROXY",
            "RED_DEF0003_FIELD_LATE_JOIN_RESULT acceptancePass=1",
            "topology=in_process_listen_plus_true_late_client",
            "RedMMO.Mining.DEF0003.ActualFieldLateJoinPIE.DuringDepleting",
            "RedMMO.Mining.DEF0003.ActualFieldLateJoinPIE.InsideReplayWindow",
            "RedMMO.Mining.DEF0003.ActualFieldLateJoinPIE.OutsideReplayWindow",
            "RedMMO.Mining.DEF0003.ActualFieldLateJoinPIE.DurableAfterTransientExpiry",
        ):
            self.assertIn(token, source)

        self.assertIn(
            "FXAgeAtFirstObservation > ClientFXWindow",
            source,
        )
        self.assertIn(
            "ClientFX.SimulatingDebris == 0",
            source,
        )
        self.assertIn(
            "ClientFX.SimulatingDebris >= 8",
            source,
        )
        for forbidden in (
            "SpawnActorDeferred<ARedMineableAsteroid>",
            "SpawnActor<ARedMineableAsteroid>",
            "Target->SetActorScale3D",
            "ClientTarget->SetActorScale3D",
            "Target->SetPresentationCullDistance",
            "ClientTarget->SetPresentationCullDistance",
            "SetPresentationCullDistance(0.f)",
        ):
            self.assertNotIn(forbidden, source)

    def test_resource_totals_are_inventory_only_and_mining_receipt_is_transient(self):
        update = function_body(
            self.player, "void ARedPlayerCharacter::UpdateHUDResources"
        )
        self.assertIn("UpdateReplacementHUDResources", update)
        self.assertIn("ResStone, ResIron, ResCrystal", update)
        self.assertNotIn("ActiveHUDWidget->SetResourceTally", update)

        add_resource = function_body(
            self.player, "void ARedPlayerCharacter::AddResource"
        )
        for token in (
            "PresentResourceCreditLocal(Type, Add);",
            "ClientPresentResourceCredit(Type, Add);",
            "UpdateHUDResources();",
            "ForceNetUpdate();",
        ):
            self.assertIn(token, add_resource)

        for token in (
            "void UpdateReplacementHUDResources(int32 Stone, int32 Iron, int32 Crystal);",
            "bool QueryReplacementHUDResources(",
            "void ShowReplacementHUDMiningResult(uint8 ResourceType, int32 Amount);",
            "bool QueryReplacementHUDMiningResult(",
        ):
            self.assertIn(token, self.red_hud_header)
        self.assertIn(
            "PixelExactHUDWidget->SetResourceTally(Stone, Iron, Crystal);",
            self.red_hud,
        )
        self.assertIn(
            "PixelExactHUDWidget->GetResourceTallyState(",
            self.red_hud,
        )
        self.assertIn("OutText.IsEmpty()", self.red_hud)
        self.assertIn("!bOutVisible", self.red_hud)
        self.assertIn("PixelExactHUDWidget->ShowMiningResult(", self.red_hud)
        self.assertIn("PixelExactHUDWidget->GetMiningResultState(", self.red_hud)
        self.assertIn(
            "Character->ResStone, Character->ResIron, Character->ResCrystal",
            self.red_hud,
        )

        for token in (
            "void SetResourceTally(int32 Stone, int32 Iron, int32 Crystal);",
            "bool GetResourceTallyState(",
            "void ShowMiningResult(",
            "bool GetMiningResultState(",
            "TObjectPtr<UImage> MiningResultArt",
            "FTimerHandle MiningResultFadeTimer",
        ):
            self.assertIn(token, self.pixel_hud_header)
        for token in (
            "T_REDHUD_BuffRow_01",
            'TEXT("MINING YIELD")',
            "MiningResultLifetimeSeconds",
            "MiningResultFadeSeconds",
            "MiningResultArtFadeSeconds",
            "MiningResultFadeTimer",
            "AdvanceMiningResultFade",
            "const float FadeElapsed",
            "Widget == MiningResultArt ? ArtOpacity : LiveOpacity",
            "SetLiveGroupVisibility(MiningResultWidgets, false)",
        ):
            self.assertIn(token, self.pixel_hud)
        fade = function_body(
            self.pixel_hud, "void URedHUDWidget::AdvanceMiningResultFade"
        )
        self.assertLess(
            fade.index("ArtOpacity = 1.0f - FMath::SmoothStep"),
            fade.index("LiveOpacity = FMath::SmoothStep"),
        )
        self.assertLess(
            fade.index("Widget == MiningResultArt ? ArtOpacity : LiveOpacity"),
            fade.index("SetLiveGroupVisibility(MiningResultWidgets, false)"),
        )
        for forbidden in (
            "ResourceTallyText",
            'TEXT("STONE %d   IRON %d   CRYSTAL %d")',
            "NativeTick",
        ):
            self.assertNotIn(forbidden, self.pixel_hud_header + self.pixel_hud)

        self.assertIn(
            "bRuntimePassed && *BeginHUDPassed",
            self.player,
        )
        self.assertIn(
            "&& !bPersistentTallyVisible",
            self.player,
        )
        self.assertIn(
            "&& !bMiningResultVisible",
            self.player,
        )
        restart = function_body(
            self.player, "void ARedPlayerCharacter::PawnClientRestart"
        )
        self.assertIn("TryCreateLocalHUD();", restart)
        self.assertIn("UpdateHUDResources();", restart)

    def test_asteroid_explosion_uses_short_lived_finite_relevancy_factory(self):
        self.assertIn("SpawnForDepletedAsteroid", self.explosion_header)
        asteroid_factory = function_body(
            self.explosion,
            "ARedShipExplosionFX* ARedShipExplosionFX::SpawnForDepletedAsteroid",
        )
        self.assertIn("/*bInAlwaysRelevant=*/false", asteroid_factory)
        self.assertIn("/*NetCullDistanceCm=*/1500000.f", asteroid_factory)
        self.assertIn("/*LifeSpanSeconds=*/5.f", asteroid_factory)

        shared_factory = function_body(
            self.explosion,
            "ARedShipExplosionFX* ARedShipExplosionFX::SpawnForDestroyedActor",
        )
        self.assertIn("Explosion->bAlwaysRelevant = bInAlwaysRelevant;", shared_factory)
        self.assertIn("Explosion->SetNetCullDistanceSquared", shared_factory)
        self.assertIn("Explosion->InitialLifeSpan", shared_factory)
        self.assertIn("PresentationStartedServerTimeSeconds", shared_factory)
        self.assertIn("PresentationReplayWindowSeconds", shared_factory)

        presentation = function_body(
            self.explosion,
            "void ARedShipExplosionFX::TryStartPresentation",
        )
        self.assertIn("GetServerWorldTimeSeconds()", presentation)
        self.assertIn("Elapsed > PresentationReplayWindowSeconds", presentation)
        self.assertIn("SetActorTickEnabled(false);", presentation)
        self.assertIn("SpawnPrimaryCosmetics();", presentation)

        replication = function_body(
            self.explosion,
            "void ARedShipExplosionFX::GetLifetimeReplicatedProps",
        )
        self.assertIn(
            "DOREPLIFETIME(ARedShipExplosionFX, PresentationStartedServerTimeSeconds);",
            replication,
        )
        self.assertIn(
            "DOREPLIFETIME(ARedShipExplosionFX, PresentationReplayWindowSeconds);",
            replication,
        )

    def test_byte_exact_rollback_contains_every_touched_source_identity(self):
        expected = {
            "Source/RedMMO/RedMineableAsteroid.h": "7EF8E19B7D20CB6ABD186A7E460B6859CB0045D4F09571B7CC5DC88E1E735805",
            "Source/RedMMO/RedMineableAsteroid.cpp": "1D3B1BFD63239F3DF0CF52BE835573109BA7D18AAB8E099A9AABDEBEE17A0988",
            "Source/RedMMO/RedResourcePickup.h": "0E414C6B51A5B7F0AE956DF6A773264E37F2FA295A10F26EFCC1AED44A268FB2",
            "Source/RedMMO/RedResourcePickup.cpp": "84EC69D9843249CC5358295E431A0C9859ABA7ECBCDA43A4C47B6BF3CD61522B",
            "Source/RedMMO/RedShipExplosionFX.h": "00658A2775F7CC192F8A02A23B1440DFF1C6D4AFE144BA4FFAF37F4D3E2961E4",
            "Source/RedMMO/RedShipExplosionFX.cpp": "B0EC6C44288FEC71C33FF7788CEFBE48780BF3CF38D646E110977C680393547A",
            "Source/RedMMO/RedPlayerCharacter.h": "A0EAF0C0B450E13BF7D4C4A7B2A9A9E8DB2F75E50728D11FD7768197359F4A87",
            "Source/RedMMO/RedPlayerCharacter.cpp": "3609B8407C32035D892C67EB65DBB7BF59BC850FF28E67CD1C85B9322743C405",
        }
        manifest = read(ROLLBACK / "manifest.yaml")
        for relative, expected_sha in expected.items():
            snapshot = ROLLBACK / relative
            self.assertTrue(snapshot.is_file(), relative)
            self.assertEqual(
                hashlib.sha256(snapshot.read_bytes()).hexdigest().upper(), expected_sha
            )
            self.assertIn(relative, manifest)
            self.assertIn(expected_sha, manifest)

    def test_audio_slice_has_exact_prechange_rollback_boundary(self):
        expected = {
            "RedResourcePickup.h": "7762C6C57FF52812EF360CC75FAA60B038A8E5FA2E255C7E9CB3A55475B4B193",
            "RedResourcePickup.cpp": "8E180200D225E056E8B6E82DD43DA9644A2C4228781546B1159C04886AF0F240",
            "RedShipExplosionFX.h": "ABA5060EB49E14F34490E8FFC22F511C21730C4895FDD53F9F7941BC6BAD9F25",
            "RedShipExplosionFX.cpp": "DD399450AF609AC33AC5A55AB2936D457F2A2A5C021113E13224747915E818EF",
            "RedMMO.Build.cs": "0C4757AD6BD0C49EBFC68D684C8786592561B447DB1CF96B6289C3A7A055AB78",
            "RedDEF0003ActualFieldTwoClientDepletionPIETests.cpp": "515C57A4F396C694D26192AEFC1C8634600BB3BBB39CCD56D81EA664AA842EB4",
            "test_def0003_asteroid_depletion_contract.py": "D5E8F2D311EAF7B43E6BB3431CF59CD2B661C7F0342EFD4869004315C69D039D",
        }
        manifest = read(AUDIO_ROLLBACK / "MANIFEST.txt")
        for filename, expected_sha in expected.items():
            snapshot = AUDIO_ROLLBACK / filename
            self.assertTrue(snapshot.is_file(), filename)
            self.assertEqual(
                hashlib.sha256(snapshot.read_bytes()).hexdigest().upper(),
                expected_sha,
            )
            self.assertIn(f"{filename}|", manifest)
            self.assertIn(expected_sha, manifest)

    def test_defect_records_actual_field_two_client_late_join_and_audio_passes(self):
        self.assertIn(
            "status: implemented_awaiting_runtime_acceptance",
            self.defect,
        )
        self.assertIn("current_target_links:", self.defect)
        self.assertIn("one_client_real_gpu_acceptance:", self.defect)
        for token in (
            "actual_field_two_client_depletion_runtime_acceptance:",
            "2026-07-23-def-0003-actual-field-two-client-depletion-real-gpu.yaml",
            "remote inventory and visible replacement HUD both read STONE 0, IRON 6, CRYSTAL 0",
            "simultaneous client-originated final-hit RPC arrival",
            "Active, Depleting, and Depleted phase, collision, hidden state, and sequence matched on authority and remote client",
            "actual_field_late_join_multiplayer_acceptance:",
            "2026-07-23-def-0003-actual-field-late-join-multiplayer.yaml",
            "a true late client received Depleting sequence 1 with synchronized remaining time",
            "after explosion and receipt expiry a true late client received hidden collision-disabled Depleted sequence 2",
            "destruction_reward_audio_automation_acceptance:",
            "2026-07-23-def-0003-destruction-reward-audio-automation.yaml",
            "Client 1 master output was valid stereo PCM16 at 48 kHz",
            "server-restart persistence or respawn semantics",
        ):
            self.assertIn(token, self.defect)
        self.assertNotIn(
            "prove actual-field two-client stable-ID, depletion, reward, and HUD parity",
            self.defect,
        )
        self.assertNotIn(
            "prove late join observes the correct depleting, depleted, or explicitly respawned state",
            self.defect,
        )
        self.assertNotIn("status: closed", self.defect)


if __name__ == "__main__":
    unittest.main()
