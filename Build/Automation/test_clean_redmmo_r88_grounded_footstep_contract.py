from pathlib import Path


HEADER = Path(r"D:\RedMMOTitanWindowsData\Projects\RedMMO\Source\RedMMO\Public\RedPlayerCharacter.h")
SOURCE = Path(r"D:\RedMMOTitanWindowsData\Projects\RedMMO\Source\RedMMO\Private\RedPlayerCharacter.cpp")


def require(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise AssertionError(f"missing {label}: {needle}")


header = HEADER.read_text(encoding="utf-8")
source = SOURCE.read_text(encoding="utf-8")

for needle, label in (
    ("GetGroundedFootstepEventCount", "event telemetry"),
    ("GetGroundedFootstepAudioSpawnCount", "audio telemetry"),
    ("IsGroundedFootstepEligible", "grounded eligibility API"),
    ("GroundedFootstepEventCount", "event counter"),
    ("GroundedFootstepAudioSpawnCount", "audio counter"),
    ("FootstepStrideCm", "distance cadence"),
):
    require(header, needle, label)

for needle, label in (
    ("/Game/SoStylized/Sounds/Step/SC_Steps_Dirt.SC_Steps_Dirt", "approved sound path"),
    ("ConstructorHelpers::FObjectFinder<USoundBase>", "cook-visible sound reference"),
    ("UpdateGroundedFootsteps(DeltaSeconds)", "tick integration"),
    ("Movement->IsMovingOnGround()", "grounded gate"),
    ("IsHidden()", "ship hidden gate"),
    ("GetActorEnableCollision()", "ship collision gate"),
    ("FVector::VectorPlaneProject", "radial tangent distance"),
    ("AccumulatedGroundedFootstepDistanceCm", "distance accumulator"),
    ("UGameplayStatics::SpawnSoundAtLocation", "audio spawn"),
    ("RED_GROUNDED_FOOTSTEP", "runtime log marker"),
    ("ResetGroundedFootstepCadence();", "possession cadence reset"),
):
    require(source, needle, label)

if source.count("ResetGroundedFootstepCadence();") < 3:
    raise AssertionError("cadence reset must cover begin play, ship entry, and ship exit")

print("R88 grounded footstep source contract: PASS")
