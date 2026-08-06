"""Static C++ and filename inventory only; Blueprint graphs are not decoded."""

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

REDHUD_SOURCE = ROOT / "Plugins/RedHUD/Source"
WIDGET_H = REDHUD_SOURCE / "RedHUDRuntime/Public/RedHUDWidget.h"
WIDGET_CPP = REDHUD_SOURCE / "RedHUDRuntime/Private/RedHUDWidget.cpp"
LAYOUT_CPP = REDHUD_SOURCE / "RedHUDRuntime/Private/RedHUDLayout.cpp"
TYPES_H = REDHUD_SOURCE / "RedHUDRuntime/Public/RedHUDTypes.h"

REDMMO_SOURCE = ROOT / "Source/RedMMO"
GAME_INSTANCE_H = REDMMO_SOURCE / "RedGameInstance.h"
GAME_INSTANCE_CPP = REDMMO_SOURCE / "RedGameInstance.cpp"
PLAYER_H = REDMMO_SOURCE / "RedPlayerCharacter.h"
PLAYER_CPP = REDMMO_SOURCE / "RedPlayerCharacter.cpp"

VIBE_SOURCE = ROOT / "Plugins/VibeMMOUIKit/Source/VibeMMOUIKit"
VIBE_LAYOUT_H = VIBE_SOURCE / "Public/Data/VibeMMOHUDLayoutTypes.h"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="strict")


def braced_body(source: str, signature_pattern: str) -> str:
    match = re.search(signature_pattern, source, re.MULTILINE)
    if not match:
        raise AssertionError(f"signature not found: {signature_pattern}")
    opening = source.index("{", match.end())
    depth = 0
    for index in range(opening, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[match.start() : index + 1]
    raise AssertionError(f"unterminated body: {signature_pattern}")


def compiled_source_paths(root: Path) -> list[Path]:
    return sorted(
        path
        for path in root.rglob("*")
        if path.is_file() and path.suffix.lower() in {".h", ".cpp"}
    )


def compiled_source_text(root: Path) -> str:
    return "\n".join(read(path) for path in compiled_source_paths(root))


class Def0004ReplacementHUDPartyInventoryContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.widget_h = read(WIDGET_H)
        cls.widget_cpp = read(WIDGET_CPP)
        cls.layout_cpp = read(LAYOUT_CPP)
        cls.types_h = read(TYPES_H)
        cls.game_instance_h = read(GAME_INSTANCE_H)
        cls.game_instance_cpp = read(GAME_INSTANCE_CPP)
        cls.player_h = read(PLAYER_H)
        cls.player_cpp = read(PLAYER_CPP)
        cls.redmmo_source = compiled_source_text(REDMMO_SOURCE)
        cls.vibe_layout_h = read(VIBE_LAYOUT_H)
        cls.vibe_source = compiled_source_text(VIBE_SOURCE)

    def test_party_panel_is_exactly_three_supplied_art_rows_and_layout_only(self):
        artwork = braced_body(
            self.widget_cpp, r"void\s+URedHUDWidget::BuildArtwork\s*\("
        )
        resolution = braced_body(
            self.widget_cpp,
            r"TArray\s*<\s*UWidget\s*\*\s*>\s+URedHUDWidget::ResolveHUDElementWidgets\s*\(",
        )
        expected_rows = {
            ("PartyRow01", "T_REDHUD_PartyRow_01"),
            ("PartyRow02", "T_REDHUD_PartyRow_02"),
            ("PartyRow03", "T_REDHUD_PartyRow_03"),
        }
        constructed_rows = set(
            re.findall(
                r'AddImage\s*\(\s*TEXT\("(PartyRow\d+)"\)\s*,\s*'
                r'TEXT\("[^"]*/(T_REDHUD_PartyRow_\d+)\.',
                artwork,
            )
        )
        self.assertEqual(constructed_rows, expected_rows)
        resolved_rows = set(
            re.findall(r'AddArt\s*\(\s*TEXT\("(PartyRow\d+)"\)\s*\)', resolution)
        )
        self.assertEqual(resolved_rows, {name for name, _ in expected_rows})
        for name, _ in expected_rows:
            self.assertIn(name, self.layout_cpp)
        self.assertIn("EVibeMMOHUDElement::PartyPanel", resolution)
        self.assertNotIn("PartyLiveWidgets", resolution)

    def test_known_compiled_visibility_paths_keep_baked_party_members_fail_closed(self):
        dormant_helper = braced_body(
            self.widget_cpp, r"bool\s+IsDormantLiveDataArtName\s*\("
        )
        for name in ("PartyRow01", "PartyRow02", "PartyRow03"):
            self.assertIn(name, dormant_helper)

        live_mode = braced_body(
            self.widget_cpp, r"void\s+URedHUDWidget::SetLiveDataMode\s*\("
        )
        self.assertIn("!IsDormantLiveDataArtName(Pair.Key)", live_mode)
        self.assertIn("ESlateVisibility::Collapsed", live_mode)

        generic_visibility = braced_body(
            self.widget_cpp, r"void\s+URedHUDWidget::SetElementVisible\s*\("
        )
        self.assertIn(
            "bLiveDataMode && bVisible && !IsDormantLiveDataArtName(ElementName)",
            generic_visibility,
        )
        self.assertIn("ESlateVisibility::Collapsed", generic_visibility)
        self.assertEqual(self.widget_cpp.count("IsDormantLiveDataArtName("), 3)

        apply_layout = braced_body(
            self.widget_cpp, r"void\s+URedHUDWidget::ApplyHUDLayout\s*\("
        )
        self.assertLess(
            apply_layout.index("SetLiveDataMode(bLiveDataMode)"),
            apply_layout.index("ApplyHUDElementLayout(Element)"),
        )

    def test_redhud_has_no_fabricated_party_state_setter_cache_or_snapshot_field(self):
        consumer = self.widget_h + self.widget_cpp + self.types_h
        for absent_identifier in (
            "FRedHUDPartyState",
            "FRedHUDPartyMember",
            "SetPartyState",
            "SetPartyMember",
            "PartyLiveWidgets",
            "CachedParty",
            "PartyRevision",
        ):
            self.assertNotIn(absent_identifier, consumer)

        snapshot = braced_body(self.types_h, r"struct\s+FRedHUDSnapshot\b")
        self.assertNotRegex(snapshot, r"(?i)\bparty\b|\bsquad\b|\broster\b")

    def test_redmmo_has_no_authoritative_or_replicated_party_model(self):
        for absent_identifier in (
            "PartyId",
            "PartyID",
            "PartyMembers",
            "SquadId",
            "SquadID",
            "SquadMembers",
            "OnRep_Party",
            "OnRep_Squad",
            "ServerCreateParty",
            "ServerJoinParty",
            "ServerLeaveParty",
            "PartyRevision",
        ):
            self.assertNotIn(absent_identifier, self.redmmo_source)

        source_names = {path.name.lower() for path in compiled_source_paths(REDMMO_SOURCE)}
        self.assertFalse(any("playerstate" in name for name in source_names))
        self.assertFalse(any("gamestate" in name for name in source_names))

    def test_combat_team_and_enemy_clone_flags_are_not_party_membership(self):
        team_helper = braced_body(
            self.player_cpp, r"FGenericTeamId\s+GetExplicitGrappleTeam\s*\("
        )
        self.assertIn("IGenericTeamAgentInterface", team_helper)
        self.assertIn("return FGenericTeamId::NoTeam;", team_helper)
        self.assertIn(
            "class REDMMO_API ARedPlayerCharacter : public ACharacter",
            self.player_h,
        )
        self.assertNotIn("IGenericTeamAgentInterface", self.player_h)
        self.assertNotIn("FGenericTeamId", self.player_h)

        grapple_target = braced_body(
            self.player_cpp,
            r"bool\s+ARedPlayerCharacter::IsValidGrapplePlayerTarget\s*\(",
        )
        self.assertIn("MyTeam.GetId() != FGenericTeamId::NoTeam.GetId()", grapple_target)
        self.assertIn("TheirTeam.GetId() != FGenericTeamId::NoTeam.GetId()", grapple_target)
        self.assertIn("MyTeam.GetId() == TheirTeam.GetId()", grapple_target)
        self.assertNotIn("Party", team_helper + grapple_target)

        self.assertIn("bool bIsEnemy = false;", self.player_h)
        self.assertNotRegex(self.player_h, r"(?i)party[^\n]*(?:bIsEnemy)|bIsEnemy[^\n]*party")

    def test_session_counts_and_friend_overlay_are_not_a_party_roster(self):
        summary = braced_body(
            self.game_instance_h, r"struct\s+REDMMO_API\s+FRedSessionResultSummary\b"
        )
        for aggregate in ("OwnerName", "CurrentPlayers", "MaxPlayers", "bJoinable"):
            self.assertIn(aggregate, summary)
        for absent_member_data in (
            "Members",
            "PlayerIds",
            "PlayerIDs",
            "PartyId",
            "LeaderId",
            "MemberHealth",
        ):
            self.assertNotIn(absent_member_data, summary)

        invite = braced_body(
            self.game_instance_cpp,
            r"void\s+URedGameInstance::InviteSteamFriends\s*\(",
        )
        self.assertIn("ShowInviteUI(LocalUserNum, NAME_GameSession)", invite)
        self.assertNotRegex(invite, r"(?i)party|roster|member(?:s|ids?)?")
        self.assertIn(
            "Summary.MaxPlayers - Result.Session.NumOpenPublicConnections",
            self.game_instance_cpp,
        )
        for absent_roster_api in (
            "IOnlineFriends",
            "GetFriendsInterface",
            "RegisterPlayers",
            "GetRegisteredPlayers",
        ):
            self.assertNotIn(absent_roster_api, self.redmmo_source)

    def test_vibe_and_bounded_content_filenames_supply_layout_and_art_only(self):
        layout_enum = braced_body(
            self.vibe_layout_h, r"enum\s+class\s+EVibeMMOHUDElement\b"
        )
        self.assertIn("PartyPanel", layout_enum)
        for absent_identifier in (
            "PartyId",
            "PartyMembers",
            "PartyRevision",
            "SetPartyState",
        ):
            self.assertNotIn(absent_identifier, self.vibe_source)

        matching_content = []
        for relative_root in (Path("Content/RedMMO"), Path("Content/UI")):
            for path in (ROOT / relative_root).rglob("*"):
                if path.is_file() and re.search(
                    r"party|squad|roster|raid", path.name, re.IGNORECASE
                ):
                    matching_content.append(path.relative_to(ROOT).as_posix())
        self.assertEqual(
            sorted(matching_content),
            [
                "Content/UI/RedHUD/Textures/ExactLayoutSprites/T_REDHUD_PartyList_Exact.uasset",
                "Content/UI/RedHUD/Textures/HighResSprites/T_REDHUD_PartyList.uasset",
                "Content/UI/RedHUD/Textures/IndividualSprites/T_REDHUD_PartyRow_01.uasset",
                "Content/UI/RedHUD/Textures/IndividualSprites/T_REDHUD_PartyRow_02.uasset",
                "Content/UI/RedHUD/Textures/IndividualSprites/T_REDHUD_PartyRow_03.uasset",
            ],
        )


if __name__ == "__main__":
    unittest.main()
