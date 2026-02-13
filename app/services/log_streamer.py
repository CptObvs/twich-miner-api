"""
Tails miner log files and streams them to WebSocket clients.
"""

import asyncio
from pathlib import Path

from app.core.config import settings


async def tail_log(
    instance_id: str,
    history_lines: int | None = None,
):
    """
    Async generator that yields log lines from a miner instance.
    First yields the last `history_lines` lines, then follows new output.
    
    Args:
        instance_id: The instance ID
        history_lines: Number of historical lines to send (default: complete file)
    """
    log_file = settings.INSTANCES_DIR / instance_id / "logs" / "output.log"

    # Wait for log file to exist (might take a moment after starting)
    for _ in range(30):  # Wait up to 30 seconds
        if log_file.exists():
            break
        yield "[system] Waiting for miner to produce output...\n"
        await asyncio.sleep(1)
    else:
        yield "[system] Log file not found. Is the miner running?\n"
        return

    # Send historical lines
    with open(log_file, "r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()
        history = lines if history_lines is None else lines[-history_lines:]
        for line in history:
            yield line

        # Now follow new lines (like tail -f)
        while True:
            line = f.readline()
            if line:
                yield line
            else:
                await asyncio.sleep(0.3)
