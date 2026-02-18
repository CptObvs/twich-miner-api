"""
Log cleanup and rotation service for miner instances.
Manages log file sizes and age to prevent disk space issues.
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.core.config import settings

logger = logging.getLogger(__name__)


class LogCleanupManager:
    """Manages log file cleanup and rotation for miner instances."""

    # Configuration
    MAX_LOG_FILE_SIZE = settings.OUTPUT_LOG_MAX_SIZE_BYTES  # 2 MB per instance output.log
    LOG_RETENTION_DAYS = 7  # Keep logs for 7 days
    CHECK_INTERVAL_HOURS = 24  # Run cleanup every 24 hours

    @staticmethod
    def trim_log_file_to_size(log_file: Path, max_size_bytes: int = MAX_LOG_FILE_SIZE) -> bool:
        """
        Trim a log file in-place to max_size_bytes by removing old bytes from the beginning.

        Keeps the newest content and tries to cut at the next newline boundary to avoid
        starting with a partial line.
        """
        if not log_file.exists() or max_size_bytes <= 0:
            return False

        file_size = log_file.stat().st_size
        if file_size <= max_size_bytes:
            return False

        keep_from = file_size - max_size_bytes

        with open(log_file, "rb+") as f:
            f.seek(keep_from)
            data = f.read()

            newline_idx = data.find(b"\n")
            if 0 <= newline_idx < len(data) - 1:
                data = data[newline_idx + 1:]

            f.seek(0)
            f.write(data)
            f.truncate()

        return True

    @staticmethod
    def cleanup_old_logs(max_age_days: int = LOG_RETENTION_DAYS):
        """
        Delete log files older than max_age_days.
        
        Args:
            max_age_days: Delete logs older than this many days (default: 7)
        """
        if not settings.INSTANCES_DIR.exists():
            return

        cutoff_time = datetime.now(timezone.utc) - timedelta(days=max_age_days)
        deleted_count = 0
        total_size_freed = 0

        for instance_dir in settings.INSTANCES_DIR.iterdir():
            if not instance_dir.is_dir():
                continue

            logs_dir = instance_dir / "logs"
            if not logs_dir.exists():
                continue

            for log_file in logs_dir.glob("*.log"):
                try:
                    # Get file modification time
                    mtime = datetime.fromtimestamp(
                        log_file.stat().st_mtime, tz=timezone.utc
                    )

                    if mtime < cutoff_time:
                        file_size = log_file.stat().st_size
                        log_file.unlink()
                        deleted_count += 1
                        total_size_freed += file_size
                        logger.info(
                            f"Deleted old log: {log_file.relative_to(settings.INSTANCES_DIR)} "
                            f"(age: {(datetime.now(timezone.utc) - mtime).days} days, "
                            f"size: {file_size / 1024:.1f} KB)"
                        )
                except Exception as e:
                    logger.error(f"Error deleting log file {log_file}: {e}")

        if deleted_count > 0:
            logger.info(
                f"Log cleanup complete: Deleted {deleted_count} files, "
                f"freed {total_size_freed / 1024 / 1024:.1f} MB"
            )

    @staticmethod
    def rotate_large_logs(max_size_bytes: int = MAX_LOG_FILE_SIZE):
        """
        Trim miner log files in-place to max_size_bytes.
        
        Args:
            max_size_bytes: Rotate logs larger than this size (default: 10 MB)
        """
        if not settings.INSTANCES_DIR.exists():
            return

        trimmed_count = 0

        for instance_dir in settings.INSTANCES_DIR.iterdir():
            if not instance_dir.is_dir():
                continue

            logs_dir = instance_dir / "logs"
            if not logs_dir.exists():
                continue

            for log_file in logs_dir.glob("*.log"):
                try:
                    if LogCleanupManager.trim_log_file_to_size(log_file, max_size_bytes=max_size_bytes):
                        trimmed_count += 1
                        logger.info(
                            f"Trimmed log in place: {log_file.name} "
                            f"(max: {max_size_bytes / 1024 / 1024:.1f} MB)"
                        )
                except Exception as e:
                    logger.error(f"Error trimming log file {log_file}: {e}")

        if trimmed_count > 0:
            logger.info(f"Log maintenance complete: trimmed={trimmed_count}")

    @classmethod
    async def cleanup_task(cls):
        """Periodic cleanup task. Runs every CHECK_INTERVAL_HOURS hours."""
        while True:
            try:
                logger.debug("Running log cleanup task...")
                cls.rotate_large_logs()
                cls.cleanup_old_logs()
                logger.debug("Log cleanup task complete")
            except Exception as e:
                logger.error(f"Error in log cleanup task: {e}")

            # Sleep until next run
            await asyncio.sleep(cls.CHECK_INTERVAL_HOURS * 3600)

    @classmethod
    def start_cleanup_task(cls):
        """Start the periodic cleanup task in the background."""
        asyncio.create_task(cls.cleanup_task())
        logger.info("Log cleanup task started")


# Singleton instance
log_cleanup = LogCleanupManager()
