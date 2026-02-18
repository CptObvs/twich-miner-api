from __future__ import annotations

import re
from pathlib import Path
from dataclasses import dataclass
from time import monotonic

from app.services.log_streamer import get_instance_log_file

STREAMER_DETAILS_RE = re.compile(r"Streamer\(username=([^,]+),[^)]*channel_points=([^)]+)\)")
STREAMER_INLINE_RE = re.compile(r"\s•\s([^()]+?)\s\(([^)]+)\)$")


@dataclass
class PointsSnapshotCacheEntry:
    timestamp: float
    history_lines: int
    points_by_streamer: dict[str, str]


_points_snapshot_cache: dict[str, PointsSnapshotCacheEntry] = {}


def _iter_lines_reverse(file_path: Path, chunk_size: int = 8192):
    with open(file_path, "rb") as file:
        file.seek(0, 2)
        position = file.tell()
        buffer = b""

        while position > 0:
            read_size = min(chunk_size, position)
            position -= read_size
            file.seek(position)
            chunk = file.read(read_size)
            buffer = chunk + buffer

            parts = buffer.split(b"\n")
            buffer = parts[0]
            for raw_line in reversed(parts[1:]):
                if not raw_line:
                    continue
                yield raw_line.decode("utf-8", errors="replace")

        if buffer:
            yield buffer.decode("utf-8", errors="replace")


def _normalize_channel_points(raw_value: str) -> str | None:
    normalized = raw_value.strip()
    return normalized or None


def _extract_snapshot(line: str) -> tuple[str, str] | None:
    details = STREAMER_DETAILS_RE.search(line)
    if details:
        username = details.group(1).strip().lower()
        channel_points = _normalize_channel_points(details.group(2))
        if channel_points is not None:
            return username, channel_points

    inline = STREAMER_INLINE_RE.search(line)
    if inline:
        username = inline.group(1).strip().lower()
        channel_points = _normalize_channel_points(inline.group(2))
        if channel_points is not None:
            return username, channel_points

    return None


def collect_instance_points_snapshot(
    instance_id: str,
    history_lines: int = 2000,
    expected_streamers: set[str] | None = None,
) -> dict[str, str]:
    log_file = get_instance_log_file(instance_id)
    if log_file is None or not log_file.exists():
        return {}

    points_by_streamer: dict[str, str] = {}
    expected = {name.strip().lower() for name in expected_streamers or set() if name.strip()}
    target_count = len(expected)
    scanned_lines = 0

    for line in _iter_lines_reverse(log_file):
        scanned_lines += 1
        if scanned_lines > history_lines:
            break

        snapshot = _extract_snapshot(line)
        if snapshot is None:
            continue
        username, points = snapshot
        if username in points_by_streamer:
            continue
        if expected and username not in expected:
            continue

        points_by_streamer[username] = points
        if target_count > 0 and len(points_by_streamer) >= target_count:
            break

    return points_by_streamer


def get_instance_points_snapshot(
    instance_id: str,
    *,
    history_lines: int = 2000,
    refresh: bool = False,
    max_age_seconds: int = 30,
    expected_streamers: set[str] | None = None,
) -> dict[str, str]:
    now = monotonic()
    cached = _points_snapshot_cache.get(instance_id)

    if (
        not refresh
        and cached is not None
        and cached.history_lines == history_lines
        and now - cached.timestamp <= max_age_seconds
    ):
        if expected_streamers:
            expected = {name.strip().lower() for name in expected_streamers if name.strip()}
            return {
                streamer: points
                for streamer, points in cached.points_by_streamer.items()
                if streamer in expected
            }
        return dict(cached.points_by_streamer)

    fresh = collect_instance_points_snapshot(instance_id, history_lines=history_lines)
    _points_snapshot_cache[instance_id] = PointsSnapshotCacheEntry(
        timestamp=now,
        history_lines=history_lines,
        points_by_streamer=dict(fresh),
    )

    if expected_streamers:
        expected = {name.strip().lower() for name in expected_streamers if name.strip()}
        return {
            streamer: points
            for streamer, points in fresh.items()
            if streamer in expected
        }

    return fresh
