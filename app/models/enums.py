"""
Enum definitions for the application.
"""

from enum import Enum


class UserRole(str, Enum):
    """User role enumeration."""
    ADMIN = "admin"
    USER = "user"


class InstanceState(str, Enum):
    """Miner instance lifecycle states."""
    STOPPED = "stopped"
    RUNNING = "running"
    STOPPING = "stopping"


class MinerType(str, Enum):
    """Miner implementation type."""
    TwitchDropsMiner = "TwitchDropsMiner"
    TwitchPointsMinerV2 = "TwitchPointsMinerV2"
