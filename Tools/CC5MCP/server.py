"""External, stdio-only MCP server for the CC5 filesystem bridge."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from .protocol import (
    DEFAULT_CONFIG_PATH,
    BridgeConfig,
    BridgeError,
    QueueBridgeClient,
    validate_version_name,
)


CONFIG_PATH = Path(DEFAULT_CONFIG_PATH)

mcp = FastMCP(
    "RedMMO Character Creator 5",
    instructions=(
        "Local-only CC5 bridge. It can inspect one explicitly selected avatar, "
        "list shaping sliders, set only config-approved shaping morphs, apply "
        "named two-part body/head presets, and save a new .ccProject version "
        "under the configured D: output root. It cannot execute code, access "
        "the network, load assets, export files, or overwrite."
    ),
)


def _client() -> QueueBridgeClient:
    return QueueBridgeClient(BridgeConfig.from_file(CONFIG_PATH))


def _safe_tool_result(callback: Any) -> dict[str, Any]:
    try:
        return {"ok": True, "result": callback()}
    except BridgeError as exc:
        return {"ok": False, "error": {"code": exc.code, "message": exc.message}}
    except Exception:
        return {
            "ok": False,
            "error": {
                "code": "bridge_internal_error",
                "message": "The local CC5 bridge failed without exposing host details.",
            },
        }


@mcp.tool()
def cc5_get_bridge_status() -> dict[str, Any]:
    """Report whether the in-CC5 bridge has a fresh local heartbeat."""

    return _safe_tool_result(lambda: _client().read_status())


@mcp.tool()
def cc5_inspect_active_character() -> dict[str, Any]:
    """Inspect the one avatar explicitly selected in Character Creator 5."""

    return _safe_tool_result(
        lambda: _client().call("inspect_active_character", {})
    )


@mcp.tool()
def cc5_list_active_character_morphs(
    category: str = "",
    offset: int = 0,
    limit: int = 100,
) -> dict[str, Any]:
    """List CC shaping sliders for the one selected avatar, with pagination."""

    return _safe_tool_result(
        lambda: _client().call(
            "list_active_character_morphs",
            {"category": category, "offset": offset, "limit": limit},
        )
    )


@mcp.tool()
def cc5_set_approved_morph(
    expected_character_id: str,
    expected_project_identity: str,
    morph_alias: str,
    value: float,
) -> dict[str, Any]:
    """Set one locally allowlisted CC shaping slider by its safe alias."""

    def invoke() -> dict[str, Any]:
        client = _client()
        rule = client.config.morph_allowlist.get(morph_alias)
        if rule is None:
            raise BridgeError(
                "morph_not_approved",
                "That morph alias is not approved in the local bridge config.",
            )
        numeric = float(value)
        if not rule.minimum <= numeric <= rule.maximum:
            raise BridgeError(
                "morph_value_denied",
                f"Value must be between {rule.minimum} and {rule.maximum}.",
            )
        return client.call(
            "set_approved_morph",
            {
                "expected_character_id": expected_character_id,
                "expected_project_identity": expected_project_identity,
                "morph_alias": morph_alias,
                "value": numeric,
            },
        )

    return _safe_tool_result(invoke)


@mcp.tool()
def cc5_apply_approved_linked_preset(
    expected_character_id: str,
    expected_project_identity: str,
    preset_alias: str,
) -> dict[str, Any]:
    """Apply one named allowlisted body/head morph pair to its approved avatar."""

    def invoke() -> dict[str, Any]:
        client = _client()
        preset = client.config.linked_presets.get(preset_alias)
        if preset is None:
            raise BridgeError(
                "linked_preset_not_approved",
                "That linked preset is not approved in the local bridge config.",
            )
        return client.call(
            "apply_approved_linked_preset",
            {
                "expected_character_id": expected_character_id,
                "expected_project_identity": expected_project_identity,
                "preset_alias": preset_alias,
                "expected_preset_digest": preset.definition_digest,
            },
        )

    return _safe_tool_result(invoke)


@mcp.tool()
def cc5_save_project_as(
    expected_project_identity: str,
    version_name: str,
) -> dict[str, Any]:
    """Publish a named no-overwrite .ccProject snapshot under the fixed D: root."""

    def invoke() -> dict[str, Any]:
        validate_version_name(version_name)
        return _client().call(
            "save_project_as",
            {
                "expected_project_identity": expected_project_identity,
                "version_name": version_name,
            },
        )

    return _safe_tool_result(invoke)


def _forbid_extra_tool_arguments() -> None:
    """Fail closed if the pinned FastMCP argument model accepts unknown fields."""

    try:
        registered = mcp._tool_manager._tools
    except AttributeError as exc:
        raise RuntimeError(
            "The pinned MCP SDK tool-validation surface changed."
        ) from exc
    for tool in registered.values():
        argument_model = tool.fn_metadata.arg_model
        argument_model.model_config["extra"] = "forbid"
        argument_model.model_rebuild(force=True)
        tool.parameters = argument_model.model_json_schema(by_alias=True)
        if tool.parameters.get("additionalProperties") is not False:
            raise RuntimeError(
                "The pinned MCP SDK did not enforce strict tool arguments."
            )


_forbid_extra_tool_arguments()


def main() -> None:
    # This bridge intentionally exposes only stdio. There is no HTTP/SSE mode.
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
