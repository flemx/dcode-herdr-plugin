#!/usr/bin/env python3
"""Report Deep Agents Code (dcode) lifecycle state to herdr.

Invoked by dcode hooks with the event payload as JSON on stdin. Translates
each event into a `herdr pane report-agent` / `release-agent` call so herdr
shows dcode as idle, working, or blocked and can resume the thread after a
herdr server restart.

Outside herdr (HERDR_ENV != 1) this is a no-op. It never writes to stdout,
because stdout from a SessionStart or UserPromptSubmit hook becomes model
context, and it always exits 0 so it can never block dcode.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

SOURCE = "dcode"
AGENT = "dcode"
RESUME_CMD = "dcode"

_SAFE_ID = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")

_BLOCKING_NOTIFICATIONS = {
    "permission_prompt",
    "agent_needs_input",
    "elicitation_dialog",
}
_UNBLOCKING_NOTIFICATIONS = {"elicitation_response", "elicitation_complete"}


def _state_for(payload: dict) -> str | None:
    """Map a dcode hook payload to a herdr state, "release", or None."""
    event = payload.get("hook_event_name")
    if event == "SessionStart":
        return "idle"
    if event in ("UserPromptSubmit", "PostToolUse"):
        return "working"
    if event == "PermissionRequest":
        return "blocked"
    if event == "Notification":
        kind = payload.get("notification_type")
        if kind in _BLOCKING_NOTIFICATIONS:
            return "blocked"
        if kind in _UNBLOCKING_NOTIFICATIONS:
            return "working"
        if kind == "agent_completed":
            return "idle"
        return None
    if event == "SessionEnd":
        # clear/resume are followed by a SessionStart for the new thread, so
        # keep the pane held and let that report replace the session.
        if payload.get("reason") in ("clear", "resume"):
            return None
        return "release"
    return None


def _dedupe_path(data_dir: str | None, pane_id: str) -> Path | None:
    if not data_dir or not _SAFE_ID.match(pane_id):
        return None
    return Path(data_dir) / f"herdr-{pane_id.replace(':', '_')}.state"


def _already_reported(path: Path | None, key: str) -> bool:
    if path is None:
        return False
    try:
        return path.read_text() == key
    except OSError:
        return False


def _remember(path: Path | None, key: str) -> None:
    if path is None:
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(key)
    except OSError:
        pass


def main() -> None:
    if os.environ.get("HERDR_ENV") != "1":
        return
    herdr = os.environ.get("HERDR_BIN_PATH")
    pane_id = os.environ.get("HERDR_PANE_ID")
    if not herdr or not pane_id:
        return

    payload = json.load(sys.stdin)
    if not isinstance(payload, dict):
        return
    state = _state_for(payload)
    if state is None:
        return

    session_id = payload.get("session_id")
    if not isinstance(session_id, str) or not _SAFE_ID.match(session_id):
        session_id = None

    data_dir = sys.argv[1] if len(sys.argv) > 1 else None
    dedupe = _dedupe_path(data_dir, pane_id)
    key = f"{state}:{session_id or ''}"
    # SessionStart always reports so a new or resumed thread re-claims the pane.
    if payload.get("hook_event_name") != "SessionStart" and _already_reported(
        dedupe, key
    ):
        return

    # Nanosecond timestamps keep --seq increasing across dcode restarts.
    seq = str(time.time_ns())
    common = ["--source", SOURCE, "--agent", AGENT, "--seq", seq]
    if state == "release":
        argv = [herdr, "pane", "release-agent", pane_id, *common]
    else:
        argv = [herdr, "pane", "report-agent", pane_id, *common, "--state", state]
        if session_id:
            argv += ["--agent-session-id", session_id, "--", RESUME_CMD, "-r", session_id]

    # Fire and forget: herdr must never slow dcode down. Stale reports that
    # arrive late are dropped by herdr because their --seq is lower.
    subprocess.Popen(
        argv,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
        close_fds=True,
    )
    _remember(dedupe, "" if state == "release" else key)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
