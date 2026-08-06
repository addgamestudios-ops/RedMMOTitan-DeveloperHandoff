from pathlib import Path


ROOT = Path(r"D:\RedMMOTitanWindowsData\Projects\RedMMO\Source\RedMMO")
HEADER = (ROOT / "Public" / "RedPPGGameplayGameMode.h").read_text(encoding="utf-8")
SOURCE = (ROOT / "Private" / "RedPPGGameplayGameMode.cpp").read_text(encoding="utf-8")


def method_body(signature: str) -> str:
    start = SOURCE.index(signature)
    brace = SOURCE.index("{", start)
    depth = 0
    for index in range(brace, len(SOURCE)):
        if SOURCE[index] == "{":
            depth += 1
        elif SOURCE[index] == "}":
            depth -= 1
            if depth == 0:
                return SOURCE[brace + 1 : index]
    raise AssertionError(f"unterminated method: {signature}")


def test_authority_lifecycle_is_independent_of_optional_starter_ship() -> None:
    begin = method_body("void ARedPPGGameplayGameMode::BeginPlay()")
    publish = method_body("bool ARedPPGGameplayGameMode::TryPublishHomeCelestialFrame()")
    spawn = method_body("void ARedPPGGameplayGameMode::TrySpawnStarterShip()")
    assert begin.index("TryPublishHomeCelestialFrame();") < begin.index("TrySpawnStarterShip();")
    assert "!HasAuthority()" in publish and "!GetWorld()" in publish
    assert "bSpawnStarterShip" not in publish and "StarterShipClass" not in publish
    assert "!bSpawnStarterShip" in spawn and "!StarterShipClass" in spawn


def test_producer_uses_exact_unique_ppg_frame_and_server_registry_contract() -> None:
    publish = method_body("bool ARedPPGGameplayGameMode::TryPublishHomeCelestialFrame()")
    required = (
        "ResolveUniqueHomeBody(GetWorld(), Frame, false)",
        "Registration.StableId = Frame.StableId",
        "Registration.World = GetWorld()",
        "Registration.Authority = Spawner",
        "Registration.Center = Frame.Center",
        "Registration.NominalRadiusCm = Frame.NominalRadius",
        "Registration.Revision = NextRevision",
        "RedCelestialFrames::RegisterOrUpdate(Registration)",
        "RedCelestialFrames::ResolveExact(GetWorld(), Frame.StableId, Snapshot)",
    )
    for token in required:
        assert token in publish
    assert "PublishedHomeFrameRevision + 1" in publish
    assert "PublishedHomeFrameRevision == MAX_uint64" in publish
    assert "PublishedHomeFrameAuthority.Get() != Spawner" in publish
    assert "PublishedHomeFrameId != Frame.StableId" in publish


def test_transient_retry_is_bounded_and_ambiguity_fails_closed() -> None:
    publish = method_body("bool ARedPPGGameplayGameMode::TryPublishHomeCelestialFrame()")
    retry = method_body("void ARedPPGGameplayGameMode::ScheduleHomeFramePublishRetry")
    assert "EBodyResolveResult::NoBody" in publish
    assert "EBodyResolveResult::NotReady" in publish
    assert "else" in publish and "failed closed" in publish
    assert "MaxPublishAttempts = 1200" in retry
    assert "HomeFramePublishAttempts >= MaxPublishAttempts" in retry


def test_known_frame_mutation_republishes_and_teardown_is_exact_revision() -> None:
    spawn = method_body("void ARedPPGGameplayGameMode::TrySpawnStarterShip()")
    generation = method_body("void ARedPPGGameplayGameMode::HandlePlanetGenerationFinished()")
    end = method_body("void ARedPPGGameplayGameMode::EndPlay")
    teardown = method_body("void ARedPPGGameplayGameMode::UnpublishHomeCelestialFrame()")
    assert spawn.index("SetNewFloatingWorldOrigin") < spawn.index("TryPublishHomeCelestialFrame();")
    assert "TryPublishHomeCelestialFrame();" in generation
    assert "ClearTimer(HomeFramePublishRetryTimer)" in end
    assert "UnpublishHomeCelestialFrame();" in end
    assert "RedCelestialFrames::Unregister(" in teardown
    assert "PublishedHomeFrameId, PublishedHomeFrameRevision" in teardown
    assert "EndingWorld->IsBeingCleanedUp() || EndingWorld->IsCleanedUp()" in end
    assert "RedCelestialFrames::RemoveWorld(EndingWorld)" in end


def test_header_retains_explicit_value_snapshot_state() -> None:
    for token in (
        "PublishedHomeFrameAuthority",
        "PublishedHomeFrameId",
        "PublishedHomeFrameCenter",
        "PublishedHomeFrameRadiusCm",
        "PublishedHomeFrameRevision",
        "HomeFramePublishRetryTimer",
    ):
        assert token in HEADER


if __name__ == "__main__":
    tests = [value for name, value in globals().items() if name.startswith("test_")]
    for test in tests:
        test()
    print(f"PASS: {len(tests)} clean PPG celestial-frame producer contract tests")
