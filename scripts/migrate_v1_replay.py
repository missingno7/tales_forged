#!/usr/bin/env python3
"""Retimestamp a legacy PortForge Amiga PAL-v1 journal for PAL-v3.

The v1 profile accidentally used 910 master ticks per scanline. The corrected
PAL timeline uses 1816. This tool preserves each event's emulated wall-clock
position, upgrades the replay envelope to v2, and binds the caller-supplied
v3 launch identity. The resulting journal is only a migration candidate until
the oracle completes it without an execution frontier.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


OLD_LINE_TICKS = 910
NEW_LINE_TICKS = 1816
OLD_MACHINE = "pf-amiga-a500-ocs-pal-v1"
NEW_MACHINE = "pf-amiga-a500-ocs-pal-v3"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--launch-sha256", required=True)
    options = parser.parse_args()

    replay = json.loads(options.source.read_text(encoding="utf-8"))
    if (
        replay.get("format") != "portforge-amiga-replay-v1"
        or replay.get("machine_model") != OLD_MACHINE
        or not isinstance(replay.get("events"), list)
    ):
        raise SystemExit("source is not a legacy PAL-v1 Amiga replay")
    launch = options.launch_sha256.lower()
    if len(launch) != 64 or any(ch not in "0123456789abcdef" for ch in launch):
        raise SystemExit("--launch-sha256 must be a lowercase SHA-256 digest")

    migrated_events = []
    for event in replay["events"]:
        migrated = dict(event)
        tick = migrated.get("master_tick")
        if not isinstance(tick, int) or tick < 0:
            raise SystemExit("event master_tick must be a non-negative integer")
        migrated["master_tick"] = (
            tick * NEW_LINE_TICKS + OLD_LINE_TICKS // 2
        ) // OLD_LINE_TICKS
        migrated_events.append(migrated)

    migrated_replay = {
        "events": migrated_events,
        "format": "portforge-amiga-replay-v2",
        "launch_sha256": launch,
        "machine_model": NEW_MACHINE,
        "program_sha256": replay["program_sha256"],
    }
    options.destination.parent.mkdir(parents=True, exist_ok=True)
    options.destination.write_text(
        json.dumps(migrated_replay, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        f"migrated {len(migrated_events)} events: "
        f"{options.source} -> {options.destination}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
