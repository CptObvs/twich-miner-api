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
    MAX_LOG_FILE_SIZE = 10 * 1024 * 1024  # 10 MB per file
    LOG_RETENTION_DAYS = 7  # Keep logs for 7 days
    CHECK_INTERVAL_HOURS = 24  # Run cleanup every 24 hours

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
        Rotate log files that exceed max_size_bytes.
        Renames old log to .1, .2, etc. and creates fresh log.
        
        Args:
            max_size_bytes: Rotate logs larger than this size (default: 10 MB)
        """
        if not settings.INSTANCES_DIR.exists():
            return

        rotated_count = 0

        for instance_dir in settings.INSTANCES_DIR.iterdir():
            if not instance_dir.is_dir():
                continue

            logs_dir = instance_dir / "logs"
            if not logs_dir.exists():
                continue

            # Only rotate primary log file, not already-rotated ones (.1.log, .2.log, etc.)
            log_file = logs_dir / "output.log"
            if log_file.exists():
                try:
                    file_size = log_file.stat().st_size

                    if file_size > max_size_bytes:
                        # Find next available rotation number
                        rotation_num = 1
                        while (logs_dir / f"output.{rotation_num}.log").exists():
                            rotation_num += 1

                        rotated_file = logs_dir / f"output.{rotation_num}.log"
                        log_file.rename(rotated_file)
                        rotated_count += 1

                        logger.info(
                            f"Rotated log: {log_file.name} -> {rotated_file.name} "
                            f"(size: {file_size / 1024 / 1024:.1f} MB)"
                        )
                except Exception as e:
                    logger.error(f"Error rotating log file {log_file}: {e}")

        if rotated_count > 0:
            logger.info(f"Log rotation complete: Rotated {rotated_count} files")

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
