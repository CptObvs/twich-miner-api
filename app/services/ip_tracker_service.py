"""
IP Tracker Service
==================
Tracks every unique IP that connects to the API.
Uses an in-memory dict for fast per-request recording and flushes to DB every 30 s.
GeoIP lookups are done asynchronously via ipwho.is (free, no key required).
"""

import asyncio
import json
import logging
import urllib.request
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("uvicorn.error")

_LOOPBACK = {"127.0.0.1", "::1", "0.0.0.0", "localhost"}


class IPTrackerService:
    def __init__(self) -> None:
        # ip_address -> entry dict
        self._ips: dict[str, dict] = {}
        # IPs that need to be flushed to DB
        self._dirty: set[str] = set()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def load_from_db(self, db: AsyncSession) -> None:
        """Load existing IP records from DB into memory on startup."""
        result = await db.execute(
            text(
                "SELECT ip_address, country, country_code, first_seen, last_seen, request_count "
                "FROM connected_ips"
            )
        )
        for row in result.fetchall():
            self._ips[row[0]] = {
                "ip_address": row[0],
                "country": row[1],
                "country_code": row[2],
                "first_seen": row[3],
                "last_seen": row[4],
                "request_count": row[5],
            }
        logger.debug(f"IPTracker: loaded {len(self._ips)} IPs from DB")

    def record(self, ip: str) -> None:
        """Record a request from the given IP (sync, called per-request)."""
        if ip in _LOOPBACK or ip.startswith("127."):
            return

        now = datetime.now(timezone.utc).isoformat()

        if ip not in self._ips:
            self._ips[ip] = {
                "ip_address": ip,
                "country": None,
                "country_code": None,
                "first_seen": now,
                "last_seen": now,
                "request_count": 1,
            }
            # Fire GeoIP lookup without blocking the request
            asyncio.create_task(self._lookup_country(ip))
        else:
            self._ips[ip]["last_seen"] = now
            self._ips[ip]["request_count"] += 1

        self._dirty.add(ip)

    async def flush(self, db: AsyncSession) -> None:
        """Upsert all dirty IPs into the DB."""
        if not self._dirty:
            return

        dirty = self._dirty.copy()
        self._dirty.clear()

        for ip in dirty:
            entry = self._ips.get(ip)
            if not entry:
                continue
            await db.execute(
                text("""
                    INSERT INTO connected_ips
                        (ip_address, country, country_code, first_seen, last_seen, request_count)
                    VALUES
                        (:ip, :country, :country_code, :first_seen, :last_seen, :count)
                    ON CONFLICT(ip_address) DO UPDATE SET
                        last_seen     = excluded.last_seen,
                        request_count = excluded.request_count,
                        country       = COALESCE(excluded.country, connected_ips.country),
                        country_code  = COALESCE(excluded.country_code, connected_ips.country_code)
                """),
                {
                    "ip": entry["ip_address"],
                    "country": entry["country"],
                    "country_code": entry["country_code"],
                    "first_seen": entry["first_seen"],
                    "last_seen": entry["last_seen"],
                    "count": entry["request_count"],
                },
            )

        await db.commit()

    async def get_all(self, db: AsyncSession) -> list[dict]:
        """Return all tracked IPs ordered by last seen (most recent first)."""
        result = await db.execute(
            text(
                "SELECT ip_address, country, country_code, first_seen, last_seen, request_count "
                "FROM connected_ips ORDER BY last_seen DESC"
            )
        )
        return [
            {
                "ip_address": row[0],
                "country": row[1],
                "country_code": row[2],
                "first_seen": row[3],
                "last_seen": row[4],
                "request_count": row[5],
            }
            for row in result.fetchall()
        ]

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _lookup_country(self, ip: str) -> None:
        try:
            data = await asyncio.to_thread(self._fetch_geoip_sync, ip)
            if data and ip in self._ips:
                self._ips[ip]["country"] = data.get("country")
                self._ips[ip]["country_code"] = data.get("country_code")
                self._dirty.add(ip)
        except Exception as exc:
            logger.debug(f"IPTracker: GeoIP lookup failed for {ip}: {exc}")

    @staticmethod
    def _fetch_geoip_sync(ip: str) -> dict | None:
        try:
            req = urllib.request.Request(
                f"https://ipwho.is/{ip}",
                headers={"User-Agent": "TwitchMinerAPI/1.0"},
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read())
                if data.get("success"):
                    return {
                        "country": data.get("country"),
                        "country_code": data.get("country_code"),
                    }
        except Exception:
            pass
        return None


ip_tracker_service = IPTrackerService()
