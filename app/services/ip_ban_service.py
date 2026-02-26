"""
IP Ban Service
==============
Tracks 404 hits per IP using a sliding window. After 10 hits within 5 minutes
the IP is banned for 1 hour. Bans are persisted to the database and cached
in memory for fast lookups.
"""

import logging
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import BannedIP

logger = logging.getLogger("uvicorn.error")

_LOOPBACK = {"127.0.0.1", "::1", "localhost"}
_WINDOW_SECONDS = 300   # 5 minutes
_HIT_THRESHOLD = 10
_BAN_HOURS = 1


class IPBanService:
    def __init__(self) -> None:
        self._banned: dict[str, datetime] = {}
        self._404_hits: dict[str, deque[datetime]] = defaultdict(deque)

    # ------------------------------------------------------------------
    # Startup

    async def load_from_db(self, db: AsyncSession) -> None:
        """Load active bans from DB into memory on startup."""
        now = datetime.now(timezone.utc)
        result = await db.execute(select(BannedIP))
        for row in result.scalars().all():
            banned_until = row.banned_until
            if banned_until.tzinfo is None:
                banned_until = banned_until.replace(tzinfo=timezone.utc)
            if banned_until > now:
                self._banned[row.ip_address] = banned_until
        logger.info("IP ban service: loaded %d active ban(s) from DB", len(self._banned))

    # ------------------------------------------------------------------
    # Check

    def is_banned(self, ip: str) -> bool:
        """Sync check — returns True if the IP is currently banned."""
        if ip in _LOOPBACK:
            return False
        banned_until = self._banned.get(ip)
        if banned_until is None:
            return False
        now = datetime.now(timezone.utc)
        if banned_until.tzinfo is None:
            banned_until = banned_until.replace(tzinfo=timezone.utc)
        if now >= banned_until:
            del self._banned[ip]
            return False
        return True

    # ------------------------------------------------------------------
    # Record

    async def record_404(self, ip: str, db: AsyncSession) -> None:
        """Record a 404 hit for an IP. Bans the IP if the threshold is reached."""
        if ip in _LOOPBACK:
            return

        now = datetime.now(timezone.utc)
        window_start = now - timedelta(seconds=_WINDOW_SECONDS)
        hits = self._404_hits[ip]

        # Prune hits outside the window
        while hits and hits[0] < window_start:
            hits.popleft()

        hits.append(now)

        if len(hits) >= _HIT_THRESHOLD:
            banned_until = now + timedelta(hours=_BAN_HOURS)
            hit_count = len(hits)
            self._banned[ip] = banned_until
            self._404_hits.pop(ip, None)
            await self._persist_ban(ip, now, banned_until, hit_count, db)
            logger.warning(
                "IP ban service: banned %s for %dh after %d 404 hits in %ds",
                ip, _BAN_HOURS, hit_count, _WINDOW_SECONDS,
            )

    async def _persist_ban(
        self,
        ip: str,
        banned_at: datetime,
        banned_until: datetime,
        hit_count: int,
        db: AsyncSession,
    ) -> None:
        # Upsert: delete existing row (if any) then insert fresh
        await db.execute(delete(BannedIP).where(BannedIP.ip_address == ip))
        db.add(BannedIP(
            ip_address=ip,
            banned_at=banned_at,
            banned_until=banned_until,
            hit_count=hit_count,
        ))
        await db.commit()

    # ------------------------------------------------------------------
    # Admin helpers

    async def get_active_bans(self, db: AsyncSession) -> list[BannedIP]:
        """Return all bans whose banned_until is in the future."""
        now = datetime.now(timezone.utc)
        result = await db.execute(select(BannedIP))
        rows = result.scalars().all()
        active = []
        for row in rows:
            banned_until = row.banned_until
            if banned_until.tzinfo is None:
                banned_until = banned_until.replace(tzinfo=timezone.utc)
            if banned_until > now:
                active.append(row)
        return active

    async def ban(self, ip: str, duration_hours: int, db: AsyncSession) -> None:
        """Manually ban an IP for the given duration."""
        if ip in _LOOPBACK:
            return
        now = datetime.now(timezone.utc)
        banned_until = now + timedelta(hours=duration_hours)
        self._banned[ip] = banned_until
        self._404_hits.pop(ip, None)
        await self._persist_ban(ip, now, banned_until, 0, db)
        logger.info("IP ban service: manually banned %s for %dh", ip, duration_hours)

    async def unban(self, ip: str, db: AsyncSession) -> bool:
        """Remove a ban for the given IP. Returns True if a ban was found."""
        result = await db.execute(select(BannedIP).where(BannedIP.ip_address == ip))
        row = result.scalar_one_or_none()
        if row is None:
            return False
        await db.delete(row)
        await db.commit()
        self._banned.pop(ip, None)
        self._404_hits.pop(ip, None)
        return True


ip_ban_service = IPBanService()
