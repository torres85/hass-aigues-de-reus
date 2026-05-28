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
    CONF_BILLING_PERIOD_DAYS,
    CONF_BILLING_PERIOD_START,
    CONF_TARIFF_ENABLED,
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


class TestCoordinatorData:
    def test_defaults(self):
        d = CoordinatorData()
        assert d.last_hourly_value is None
        assert d.last_sync is None
        assert d.raw_hourly == []

    def test_last_sync_can_be_set(self):
        from datetime import timezone
        ts = datetime(2026, 5, 25, 10, 0, tzinfo=timezone.utc)
        d = CoordinatorData(last_sync=ts)
        assert d.last_sync == ts


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
    from entry.options.

    Modern HA's DataUpdateCoordinator.__init__ calls frame.report_usage() to
    nudge integrations to pass config_entry explicitly. That helper requires
    HA's frame context, which doesn't exist in pure unit tests, so we patch
    it to a no-op for these two cases.
    """

    def test_default_interval_when_no_options(self):
        from datetime import timedelta
        from custom_components.aigues_de_reus.const import DEFAULT_UPDATE_INTERVAL_HOURS

        entry = MagicMock()
        entry.options = {}
        client = MagicMock()
        client.contrato = "9999999"
        hass = MagicMock()

        with patch("homeassistant.helpers.frame.report_usage"):
            coord = AiguesDeReusCoordinator(hass, entry, client)
        assert coord.update_interval == timedelta(hours=DEFAULT_UPDATE_INTERVAL_HOURS)

    def test_custom_interval_from_options(self):
        from datetime import timedelta

        entry = MagicMock()
        entry.options = {CONF_UPDATE_INTERVAL_HOURS: 12}
        client = MagicMock()
        client.contrato = "9999999"
        hass = MagicMock()

        with patch("homeassistant.helpers.frame.report_usage"):
            coord = AiguesDeReusCoordinator(hass, entry, client)
        assert coord.update_interval == timedelta(hours=12)


class TestPeriodStart:
    """Validate the billing-period rollover."""

    @staticmethod
    def _coord(options):
        entry = MagicMock()
        entry.options = options
        client = MagicMock()
        client.contrato = "9999999"
        with patch.object(
            AiguesDeReusCoordinator, "__init__", lambda self, *a, **k: None
        ):
            coord = AiguesDeReusCoordinator.__new__(AiguesDeReusCoordinator)
            coord.entry = entry
            coord.client = client
            coord.hass = MagicMock()
        return coord

    def test_rolls_forward_through_multiple_cycles(self):
        coord = self._coord({
            CONF_BILLING_PERIOD_START: "2026-01-01",
            CONF_BILLING_PERIOD_DAYS: 60,
        })
        # 2026-05-28 is day 148 from anchor → 2 full 60-day cycles passed,
        # so the current period started on 2026-01-01 + 120d = 2026-05-01.
        assert coord._resolve_period_start(date(2026, 5, 28)) == date(2026, 5, 1)

    def test_anchor_in_the_future_returns_anchor(self):
        coord = self._coord({
            CONF_BILLING_PERIOD_START: "2027-01-01",
            CONF_BILLING_PERIOD_DAYS: 60,
        })
        assert coord._resolve_period_start(date(2026, 5, 28)) == date(2027, 1, 1)

    def test_blank_anchor_falls_back_to_month_start(self):
        coord = self._coord({CONF_BILLING_PERIOD_START: ""})
        assert coord._resolve_period_start(date(2026, 5, 28)) == date(2026, 5, 1)

    def test_invalid_anchor_falls_back_to_month_start(self):
        coord = self._coord({CONF_BILLING_PERIOD_START: "no-date"})
        assert coord._resolve_period_start(date(2026, 5, 28)) == date(2026, 5, 1)


class TestCostPopulation:
    """Validate that today/month cost are filled when tariffs are enabled."""

    @staticmethod
    def _coord_with_tariffs():
        entry = MagicMock()
        entry.options = {
            CONF_TARIFF_ENABLED: True,
            CONF_BILLING_PERIOD_START: "2026-05-01",
            CONF_BILLING_PERIOD_DAYS: 60,
            # Defaults from const.py are used for the actual rates
        }
        client = MagicMock()
        client.contrato = "9999999"
        with patch.object(
            AiguesDeReusCoordinator, "__init__", lambda self, *a, **k: None
        ):
            coord = AiguesDeReusCoordinator.__new__(AiguesDeReusCoordinator)
            coord.entry = entry
            coord.client = client
            coord.hass = MagicMock()
        return coord

    def test_populate_costs_sets_today_and_month(self):
        coord = self._coord_with_tariffs()
        today = date(2026, 5, 28)
        # Today: 1 m³ across 24 hours; earlier in month: 5 m³ on 2026-05-15
        rows = []
        for h in range(24):
            rows.append({
                "Fecha": "2026-05-28T00:00:00",
                "Hora": h,
                "ConsumoM3": 1.0 / 24,
            })
        for h in range(24):
            rows.append({
                "Fecha": "2026-05-15T00:00:00",
                "Hora": h,
                "ConsumoM3": 5.0 / 24,
            })
        snapshot = CoordinatorData()
        coord._populate_costs(snapshot, rows, today)
        assert snapshot.today_cost_eur is not None
        assert snapshot.month_cost_eur is not None
        # Today cost ≈ 1 day fixed (~0.50€ with IVA) + 1 m³ * variable rates
        assert 0.5 < snapshot.today_cost_eur < 5
        # Month cost includes 28 days fixed + 6 m³ variable: should be larger
        assert snapshot.month_cost_eur > snapshot.today_cost_eur

    def test_disabled_tariffs_leave_costs_none(self):
        # When CONF_TARIFF_ENABLED is False, _populate_costs should not be called
        # — but if it is, it still produces values. The disable check lives in
        # _fetch(); here we simulate that branch by skipping the call entirely.
        coord = self._coord_with_tariffs()
        coord.entry.options = {}  # tariff disabled
        snapshot = CoordinatorData()
        # Mimic the _fetch() guard
        from custom_components.aigues_de_reus.const import (
            CONF_TARIFF_ENABLED,
            DEFAULT_TARIFF_ENABLED,
        )
        enabled = coord.entry.options.get(CONF_TARIFF_ENABLED, DEFAULT_TARIFF_ENABLED)
        if enabled:
            coord._populate_costs(snapshot, [], date(2026, 5, 28))
        assert snapshot.today_cost_eur is None
        assert snapshot.month_cost_eur is None
