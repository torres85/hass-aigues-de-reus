"""Tests for the AiguesDeReusCoordinator."""
from __future__ import annotations

from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.aigues_de_reus.coordinator import (
    AiguesDeReusCoordinator,
    CoordinatorData,
)
from custom_components.aigues_de_reus.const import (
    CONF_BACKFILL_DAYS,
    CONF_UPDATE_INTERVAL_HOURS,
    DOMAIN,
)


class TestRowParsing:
    def test_row_date_valid(self):
        d = AiguesDeReusCoordinator._row_date(
            {"Fecha": "2026-05-21T00:00:00"}
        )
        assert d == date(2026, 5, 21)

    def test_row_date_invalid(self):
        assert AiguesDeReusCoordinator._row_date({"Fecha": "garbage"}) is None
        assert AiguesDeReusCoordinator._row_date({}) is None
        assert AiguesDeReusCoordinator._row_date({"Fecha": None}) is None

    def test_row_datetime_combines_hour(self):
        dt = AiguesDeReusCoordinator._row_datetime(
            {"Fecha": "2026-05-21T00:00:00", "Hora": 14}
        )
        assert dt is not None
        assert dt.date() == date(2026, 5, 21)
        assert dt.hour == 14

    def test_row_datetime_handles_missing_hour(self):
        dt = AiguesDeReusCoordinator._row_datetime(
            {"Fecha": "2026-05-21T00:00:00"}
        )
        assert dt.hour == 0


class TestStatisticImport:
    """Validate the running_sum / cutoff logic — the bug we fought.

    These don't actually call HA's recorder; they patch
    async_add_external_statistics and inspect what would have been written.
    """

    @pytest.fixture
    def make_coordinator(self):
        def _make(options=None):
            entry = MagicMock()
            entry.options = options or {}
            entry.entry_id = "test_entry"
            client = MagicMock()
            client.contrato = "9999999"
            with patch.object(
                AiguesDeReusCoordinator, "__init__", lambda self, *a, **k: None
            ):
                coord = AiguesDeReusCoordinator.__new__(AiguesDeReusCoordinator)
                coord.entry = entry
                coord.client = client
                coord.hass = MagicMock()
                coord._statistic_id = (
                    f"{DOMAIN}:water_consumption_{client.contrato}".lower()
                )
                coord._force_backfill = False
            return coord
        return _make

    @staticmethod
    def _make_rows(start_day: int, end_day: int, hours_with_value: range = range(24)):
        rows = []
        for day in range(start_day, end_day + 1):
            for h in range(24):
                rows.append({
                    "Contrato": 9999999,
                    "Contador": "X11AB000001",
                    "Fecha": f"2026-05-{day:02d}T00:00:00",
                    "Hora": h,
                    "ConsumoM3": 0.01 if h in hours_with_value else None,
                    "HorasLecturas": 1.0,
                })
        return rows

    @pytest.mark.asyncio
    async def test_full_rebuild_resets_running_sum_to_zero(self, make_coordinator):
        """Backfill must NOT inherit a previous sum — it starts from zero."""
        coord = make_coordinator()

        rows = self._make_rows(1, 3)  # 3 days * 24h, all with value=0.01

        with patch(
            "custom_components.aigues_de_reus.coordinator.async_add_external_statistics"
        ) as mock_add:
            await coord._async_import_statistics(rows, full_rebuild=True)

        assert mock_add.called
        _hass, _meta, stats = mock_add.call_args[0]
        # All 72 hours have a value, sum starts at 0 and accumulates
        assert len(stats) == 72
        assert stats[0]["sum"] == pytest.approx(0.01)
        assert stats[-1]["sum"] == pytest.approx(0.72)
        # Order is monotonic ascending
        for prev, curr in zip(stats, stats[1:]):
            assert prev["start"] < curr["start"]

    @pytest.mark.asyncio
    async def test_full_rebuild_skips_null_values(self, make_coordinator):
        coord = make_coordinator()
        rows = self._make_rows(1, 1, hours_with_value=range(8, 20))  # 12 hours
        with patch(
            "custom_components.aigues_de_reus.coordinator.async_add_external_statistics"
        ) as mock_add:
            await coord._async_import_statistics(rows, full_rebuild=True)

        stats = mock_add.call_args[0][2]
        assert len(stats) == 12

    @pytest.mark.asyncio
    async def test_incremental_appends_after_cutoff(self, make_coordinator):
        """Normal cycle: only hours strictly after the last stored stat are added."""
        coord = make_coordinator()

        # Pretend recorder already has stats up to 2026-05-22 hour 12, sum=5.0
        cutoff = datetime(2026, 5, 22, 12, 0, tzinfo=timezone.utc)
        coord._async_last_stat_entry = AsyncMock(return_value={
            "start": cutoff.timestamp(),
            "sum": 5.0,
        })

        # 3 days of new data — most should be dropped, only after cutoff kept
        rows = self._make_rows(20, 23)

        with patch(
            "custom_components.aigues_de_reus.coordinator.async_add_external_statistics"
        ) as mock_add:
            await coord._async_import_statistics(rows, full_rebuild=False)

        stats = mock_add.call_args[0][2]
        # Each kept stat starts strictly after the cutoff
        for s in stats:
            assert s["start"] > cutoff
        # Sum continues from 5.0, doesn't reset
        assert stats[0]["sum"] > 5.0

    @pytest.mark.asyncio
    async def test_no_rows_does_nothing(self, make_coordinator):
        coord = make_coordinator()
        with patch(
            "custom_components.aigues_de_reus.coordinator.async_add_external_statistics"
        ) as mock_add:
            await coord._async_import_statistics([], full_rebuild=True)
        assert not mock_add.called

    @pytest.mark.asyncio
    async def test_only_null_values_does_nothing(self, make_coordinator):
        coord = make_coordinator()
        rows = self._make_rows(1, 1, hours_with_value=range(0))  # all null
        with patch(
            "custom_components.aigues_de_reus.coordinator.async_add_external_statistics"
        ) as mock_add:
            await coord._async_import_statistics(rows, full_rebuild=True)
        assert not mock_add.called


class TestForceBackfillFlag:
    @pytest.mark.asyncio
    async def test_async_force_backfill_sets_flag_and_refreshes(self):
        with patch.object(
            AiguesDeReusCoordinator, "__init__", lambda self, *a, **k: None
        ):
            coord = AiguesDeReusCoordinator.__new__(AiguesDeReusCoordinator)
            coord._force_backfill = False
            coord.async_request_refresh = AsyncMock()

            await coord.async_force_backfill()

        assert coord._force_backfill is True
        coord.async_request_refresh.assert_awaited_once()


class TestOptionsRespected:
    """Confirm the coordinator reads update_interval_hours / backfill_days
    from entry.options."""

    def test_default_interval_when_no_options(self):
        from datetime import timedelta
        from custom_components.aigues_de_reus.const import DEFAULT_UPDATE_INTERVAL_HOURS

        entry = MagicMock()
        entry.options = {}
        client = MagicMock()
        client.contrato = "9999999"
        hass = MagicMock()

        coord = AiguesDeReusCoordinator(hass, entry, client)
        assert coord.update_interval == timedelta(hours=DEFAULT_UPDATE_INTERVAL_HOURS)

    def test_custom_interval_from_options(self):
        from datetime import timedelta

        entry = MagicMock()
        entry.options = {CONF_UPDATE_INTERVAL_HOURS: 12}
        client = MagicMock()
        client.contrato = "9999999"
        hass = MagicMock()

        coord = AiguesDeReusCoordinator(hass, entry, client)
        assert coord.update_interval == timedelta(hours=12)
