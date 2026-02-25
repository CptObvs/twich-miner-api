"""
Extracts channel points per streamer from V2 miner Docker container log lines.

Scans the provided lines in reverse, stopping at the most recent "Start session:"
boundary to avoid counting points from previous sessions.
"""

from __future__ import annotations

import re

# Matches log lines like:  "rainbow6 (22.57k points) is Offline!"
#                           "peonyia (1.37k points) - Reason: WATCH."
# Groups: (1) streamer name, (2) points string e.g. "22.57k"
POINTS_RE = re.compile(r'\b([a-z0-9_]+)\s+\((\d+(?:[.,]\d+)?[km]?) points\)', re.IGNORECASE)

SESSION_RE = re.compile(r'Start session:', re.IGNORECASE)

MAX_SCAN_LINES = 2000


def extract_points_from_lines(
    lines: list[str],
    expected_streamers: set[str] | None = None,
) -> dict[str, str]:
    """
    Scan log lines (most recent last) to extract the latest channel points per streamer.
    Stops scanning when a "Start session:" boundary is encountered (working backwards).
    """
    points: dict[str, str] = {}
    expected = {n.strip().lower() for n in (expected_streamers or set()) if n.strip()}
    target = len(expected)
    scanned = 0

    for line in reversed(lines):
        scanned += 1
        if scanned > MAX_SCAN_LINES:
            break

        if SESSION_RE.search(line):
            break

        m = POINTS_RE.search(line)
        if m:
            name = m.group(1).lower()
            pts = m.group(2)
            if name not in points:
                if not expected or name in expected:
                    points[name] = pts
                    if target and len(points) >= target:
                        break

    return points
