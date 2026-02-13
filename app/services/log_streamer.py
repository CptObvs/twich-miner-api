"""
Tails miner log files and streams them to WebSocket clients.
"""

import asyncio
from pathlib import Path

from app.core.config import settings


async def tail_log(
    instance_id: str,
    history_lines: int = 100,
    max_file_lines: int = 1000,
):
    """
    Async generator that yields log lines from a miner instance.
    First yields the last `history_lines` lines, then follows new output.
    
    Args:
        instance_id: The instance ID
        history_lines: Number of historical lines to send (default: 100)
        max_file_lines: Maximum lines to keep in log file (default: 1000)
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

    # Trim log file if it exceeds max_file_lines
    try:
        with open(log_file, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        
        if len(lines) > max_file_lines:
            # Keep only the last max_file_lines lines
            lines = lines[-max_file_lines:]
            with open(log_file, "w", encoding="utf-8", errors="replace") as f:
                f.writelines(lines)
    except Exception as e:
        yield f"[system] Warning: Could not trim log file: {e}\n"

    # Send historical lines
    with open(log_file, "r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()
        # Send last N lines as history
        for line in lines[-history_lines:]:
            yield line

        # Now follow new lines (like tail -f)
        while True:
            line = f.readline()
            if line:
                yield line
            else:
                await asyncio.sleep(0.3)
