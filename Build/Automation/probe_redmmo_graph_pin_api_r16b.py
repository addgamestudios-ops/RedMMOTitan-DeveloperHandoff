"""Read-only UE 5.8 BlueprintGraphPin API probe for R16B."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import unreal


RESULT = Path(
    r"D:\RedMMOTitanWindowsData\Diagnostics\RedMMO_R16B_GroundedFootsteps_20260803_004400"
    r"\probe_redmmo_graph_pin_api_r16b_result.json"
)
_EXIT = {"handle": None}


def schedule_exit(delay: float = 3.0) -> None:
    started = time.monotonic()

    def tick(_delta: float) -> None:
        if time.monotonic() - started < delay:
            return
        handle = _EXIT.get("handle")
        if handle is not None:
            try:
                unreal.unregister_slate_post_tick_callback(handle)
            except Exception:
                pass
            _EXIT["handle"] = None
        unreal.SystemLibrary.quit_editor()

    _EXIT["handle"] = unreal.register_slate_post_tick_callback(tick)


payload = {
    "schema": "redmmo.r16b.graph_pin_api_probe.v1",
    "methods": {},
}
for name in (
    "break_all_pin_links",
    "break_link_to",
    "try_create_connection",
    "list_connected_pins",
    "get_owning_node",
):
    member = getattr(unreal.BlueprintGraphPin, name, None)
    payload["methods"][name] = {
        "exists": member is not None,
        "doc": str(getattr(member, "__doc__", "")) if member is not None else None,
    }

RESULT.parent.mkdir(parents=True, exist_ok=True)
with RESULT.open("x", encoding="utf-8") as stream:
    json.dump(payload, stream, indent=2, sort_keys=True)
    stream.write("\n")
    stream.flush()
    os.fsync(stream.fileno())

unreal.log("REDMMO_R16B_GRAPH_PIN_API_PROBE PASS")
schedule_exit()
