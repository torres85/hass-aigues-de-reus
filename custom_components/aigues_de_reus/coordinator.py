"""DataUpdateCoordinator for Aigües de Reus."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any

from homeassistant.components.recorder.models import StatisticData, StatisticMetaData
from homeassistant.components.recorder.statistics import (
    async_add_external_statistics,
    get_last_statistics,
)
from homeassistant.components.recorder import get_instance
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfVolume
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import AiguesDeReusClient, AiguesDeReusError, AuthError
from .const import (
    CONF_BACKFILL_DAYS,
    CONF_UPDATE_INTERVAL_HOURS,
    DEFAULT_BACKFILL_DAYS,
    DEFAULT_UPDATE_INTERVAL_HOURS,
    DOMAIN,
    HISTORICAL_DAYS,
)

_LOGGER = logging.getLogger(__name__)


@dataclass
class CoordinatorData:
    """Snapshot exposed to entities."""

    last_hourly_value: float | None = None
    last_hourly_at: datetime | None = None
    today_consumption_m3: float | None = None
    month_consumption_m3: float | None = None
    last_meter_reading: float | None = None
    last_meter_reading_at: datetime | None = None
    last_sync: datetime | None = None
    raw_hourly: list[dict[str, Any]] = field(default_factory=list)


class AiguesDeReusCoordinator(DataUpdateCoordinator[CoordinatorData]):
    """Polls the API and pushes hourly statistics into the recorder."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: AiguesDeReusClient,
    ) -> None:
        interval_hours = entry.options.get(
            CONF_UPDATE_INTERVAL_HOURS, DEFAULT_UPDATE_INTERVAL_HOURS
        )
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(hours=interval_hours),
        )
        self.entry = entry
        self.client = client
        self._statistic_id = (
            f"{DOMAIN}:water_consumption_{client.contrato}".lower()
        )
        self._force_backfill = False

    @property
    def statistic_id(self) -> str:
        return self._statistic_id

    async def async_force_backfill(self) -> None:
        """Trigger a full backfill on the next refresh."""
        self._force_backfill = True
        await self.async_request_refresh()

    async def _async_update_data(self) -> CoordinatorData:
        try:
            return await self._fetch()
        except AuthError as err:
            raise UpdateFailed(f"Auth: {err}") from err
        except AiguesDeReusError as err:
            raise UpdateFailed(str(err)) from err

    async def _fetch(self) -> CoordinatorData:
        today = dt_util.now().date()

        # On first run (no statistics yet), or when explicitly forced via
        # service, backfill the configured backfill window. Otherwise just
        # refresh the last HISTORICAL_DAYS days.
        configured_backfill = self.entry.options.get(
            CONF_BACKFILL_DAYS, DEFAULT_BACKFILL_DAYS
        )
        last_stat_start = await self._async_last_stat_start()
        is_backfill = self._force_backfill or last_stat_start is None
        if is_backfill:
            backfill_days = configured_backfill
            self._force_backfill = False
            _LOGGER.info(
                "Aigües de Reus: backfill de %d dies", backfill_days
            )
        else:
            backfill_days = HISTORICAL_DAYS

        days = [today - timedelta(days=i) for i in range(backfill_days, -1, -1)]

        hourly_rows: list[dict[str, Any]] = []
        for d in days:
            try:
                rows = await self.client.async_get_consumo_por_hora(d)
            except AiguesDeReusError as err:
                _LOGGER.warning("No s'ha pogut llegir consum de %s: %s", d, err)
                continue
            hourly_rows.extend(rows)
            # Be polite to the portal during backfill
            if backfill_days > HISTORICAL_DAYS:
                await asyncio.sleep(0.3)

        # Monthly
        month_rows: list[dict[str, Any]] = []
        try:
            month_rows = await self.client.async_get_consumo_mensual(
                today.year, today.month
            )
        except AiguesDeReusError as err:
            _LOGGER.warning("Consum mensual fallit: %s", err)

        # Latest reading
        last_reading: float | None = None
        last_reading_at: datetime | None = None
        for d in days[::-1]:
            try:
                lect = await self.client.async_get_lecturas_diarias(d)
            except AiguesDeReusError:
                continue
            if lect:
                # Pick last non-null reading from list
                for row in lect:
                    val = row.get("Lectura") or row.get("LecturaM3")
                    if val is not None:
                        last_reading = float(val)
                        ts = row.get("Fecha")
                        if ts:
                            try:
                                last_reading_at = dt_util.as_local(
                                    datetime.fromisoformat(ts)
                                )
                            except ValueError:
                                last_reading_at = None
                if last_reading is not None:
                    break

        # Push hourly stats to recorder
        await self._async_import_statistics(hourly_rows, full_rebuild=is_backfill)

        # Compose snapshot
        snapshot = CoordinatorData(raw_hourly=hourly_rows)
        snapshot.last_meter_reading = last_reading
        snapshot.last_meter_reading_at = last_reading_at

        # Today's accumulated
        today_total = 0.0
        any_today = False
        for row in hourly_rows:
            row_date = self._row_date(row)
            if row_date != today:
                continue
            v = row.get("ConsumoM3")
            if v is None:
                continue
            today_total += float(v)
            any_today = True
        snapshot.today_consumption_m3 = today_total if any_today else None

        # Month total
        if month_rows:
            month_total = sum(
                float(r["ConsumoM3"]) for r in month_rows if r.get("ConsumoM3") is not None
            )
            snapshot.month_consumption_m3 = round(month_total, 4)

        # Last hourly value (most recent non-null)
        for row in sorted(
            hourly_rows,
            key=lambda r: (self._row_date(r) or date.min, r.get("Hora") or 0),
            reverse=True,
        ):
            if row.get("ConsumoM3") is None:
                continue
            snapshot.last_hourly_value = float(row["ConsumoM3"])
            snapshot.last_hourly_at = self._row_datetime(row)
            break

        snapshot.last_sync = dt_util.utcnow()
        return snapshot

    @staticmethod
    def _row_date(row: dict[str, Any]) -> date | None:
        f = row.get("Fecha")
        if not f:
            return None
        try:
            return datetime.fromisoformat(f).date()
        except ValueError:
            return None

    @staticmethod
    def _row_datetime(row: dict[str, Any]) -> datetime | None:
        d = AiguesDeReusCoordinator._row_date(row)
        if d is None:
            return None
        h = int(row.get("Hora") or 0)
        return dt_util.as_local(
            datetime.combine(d, datetime.min.time()).replace(hour=h)
        )

    async def _async_last_stat_entry(self) -> dict[str, Any] | None:
        instance = get_instance(self.hass)
        last_stats = await instance.async_add_executor_job(
            get_last_statistics, self.hass, 1, self._statistic_id, True, {"sum"}
        )
        if last_stats and last_stats.get(self._statistic_id):
            return last_stats[self._statistic_id][0]
        return None

    async def _async_last_stat_start(self) -> datetime | None:
        entry = await self._async_last_stat_entry()
        if entry is None:
            return None
        ts = entry.get("start")
        if isinstance(ts, (int, float)):
            return datetime.fromtimestamp(ts, tz=timezone.utc)
        if isinstance(ts, str):
            return datetime.fromisoformat(ts)
        return None

    async def _async_import_statistics(
        self,
        hourly_rows: list[dict[str, Any]],
        *,
        full_rebuild: bool = False,
    ) -> None:
        """Import hourly water consumption into long-term statistics so the
        Energy dashboard can chart history retroactively.

        On a normal cycle we only append hours after the last stored stat.
        On a backfill (full_rebuild=True) we re-emit the entire window with
        sum=0 at the start; async_add_external_statistics upserts by
        (statistic_id, start) so existing rows get replaced.
        """
        if not hourly_rows:
            return

        rows_sorted = sorted(
            (r for r in hourly_rows if r.get("ConsumoM3") is not None),
            key=lambda r: (
                AiguesDeReusCoordinator._row_date(r) or date.min,
                int(r.get("Hora") or 0),
            ),
        )
        if not rows_sorted:
            return

        if full_rebuild:
            running_sum = 0.0
            cutoff: datetime | None = None
        else:
            last_entry = await self._async_last_stat_entry()
            running_sum = (
                float(last_entry.get("sum") or 0.0) if last_entry else 0.0
            )
            cutoff = None
            if last_entry is not None:
                ts = last_entry.get("start")
                if isinstance(ts, (int, float)):
                    cutoff = datetime.fromtimestamp(ts, tz=timezone.utc)
                elif isinstance(ts, str):
                    cutoff = datetime.fromisoformat(ts)

        stats: list[StatisticData] = []
        for row in rows_sorted:
            start = self._row_datetime(row)
            if start is None:
                continue
            start_utc = dt_util.as_utc(start).replace(minute=0, second=0, microsecond=0)
            if cutoff is not None and start_utc <= cutoff:
                continue
            value = float(row["ConsumoM3"])
            running_sum += value
            stats.append(
                StatisticData(start=start_utc, state=value, sum=running_sum)
            )

        if not stats:
            return

        metadata = StatisticMetaData(
            has_mean=False,
            has_sum=True,
            name=f"Consum d'aigua ({self.client.contrato})",
            source=DOMAIN,
            statistic_id=self._statistic_id,
            unit_of_measurement=UnitOfVolume.CUBIC_METERS,
        )
        async_add_external_statistics(self.hass, metadata, stats)
        _LOGGER.info(
            "Imported %d hourly water statistics (full_rebuild=%s, first=%s, last=%s)",
            len(stats),
            full_rebuild,
            stats[0]["start"].isoformat(),
            stats[-1]["start"].isoformat(),
        )
