"""Unit tests for the pure tariff/cost calculator."""
from __future__ import annotations

import pytest

from custom_components.aigues_de_reus.const import (
    CONF_CANON_FIXED_EUR_PER_DAY,
    CONF_CANON_TIER1_EUR_PER_M3,
    CONF_CANON_TIER1_LIMIT_M3,
    CONF_CANON_TIER2_EUR_PER_M3,
    CONF_IVA_RATE,
    CONF_SEWER_FIXED_EUR_PER_DAY,
    CONF_SEWER_TIER1_EUR_PER_M3,
    CONF_WATER_FIXED_EUR_PER_DAY,
    CONF_WATER_TIER1_EUR_PER_M3,
)
from custom_components.aigues_de_reus.tariff import (
    TariffConfig,
    _marginal_tier_cost,
    calculate_cost,
)


class TestMarginalTierCost:
    def test_single_flat_tier(self):
        tiers = ((0.0, 0.5),)
        assert _marginal_tier_cost(10, 0, tiers) == pytest.approx(5.0)
        assert _marginal_tier_cost(3, 7, tiers) == pytest.approx(1.5)

    def test_two_tier_no_crossing(self):
        # 0..10 @ 0.40, >10 @ 0.80
        tiers = ((10.0, 0.40), (0.0, 0.80))
        assert _marginal_tier_cost(5, 0, tiers) == pytest.approx(2.0)

    def test_two_tier_crosses_threshold(self):
        # cum_before=8, consume 5 more → 2 m³ at 0.40 + 3 m³ at 0.80
        tiers = ((10.0, 0.40), (0.0, 0.80))
        assert _marginal_tier_cost(5, 8, tiers) == pytest.approx(2 * 0.40 + 3 * 0.80)

    def test_two_tier_entirely_past_threshold(self):
        tiers = ((10.0, 0.40), (0.0, 0.80))
        assert _marginal_tier_cost(5, 12, tiers) == pytest.approx(5 * 0.80)

    def test_three_tier_walk(self):
        # 0..5 @ 0.10, 5..10 @ 0.20, >10 @ 0.30
        tiers = ((5.0, 0.10), (10.0, 0.20), (0.0, 0.30))
        # consume 12 from 0: 5*0.1 + 5*0.2 + 2*0.3 = 0.5 + 1.0 + 0.6 = 2.1
        assert _marginal_tier_cost(12, 0, tiers) == pytest.approx(2.1)

    def test_zero_m3_is_zero(self):
        assert _marginal_tier_cost(0, 5, ((10.0, 0.5),)) == 0.0

    def test_negative_m3_is_zero(self):
        assert _marginal_tier_cost(-3, 5, ((10.0, 0.5),)) == 0.0


class TestCalculateCost:
    def test_invoice_golden(self):
        """Reproduce the user's real invoice within rounding tolerance.

        Invoice: 12 m³ over 59 days, 11.02–10.04.2026.
        We use the rate from the invoice itself for the cànon tier 1
        (0,4936 — the rate that was active for 8 of the 12 m³ before the
        DOGC 9632 change). The integration's *default* uses the post-change
        rate (0,5232); this test pins the inputs to match the invoice.
        """
        cfg = TariffConfig(
            water_fixed_per_day=0.2640,
            water_tiers=((0.0, 0.4384),),
            sewer_fixed_per_day=0.1340,
            sewer_tiers=((0.0, 0.0755),),
            canon_fixed_per_day=0.0329,
            # Mid-period rate change ⇒ blended effective price for 12 m³:
            # 8*0,4936 + 4*0,5232 = 6,04€  →  effective 0,5033 €/m³
            canon_tiers=((0.0, 6.04 / 12),),
            iva_rate=0.10,
        )
        b = calculate_cost(m3=12, days=59, config=cfg)
        # Expected components from the invoice
        assert b.water == pytest.approx(15.58 + 5.26, abs=0.02)
        assert b.sewer == pytest.approx(7.91 + 0.91, abs=0.02)
        assert b.canon == pytest.approx(1.94 + 6.04, abs=0.02)
        assert b.iva == pytest.approx(2.97, abs=0.02)
        assert b.total == pytest.approx(40.61, abs=0.05)

    def test_iva_does_not_apply_to_canon(self):
        cfg = TariffConfig(
            water_fixed_per_day=0,
            water_tiers=((0.0, 1.0),),
            sewer_fixed_per_day=0,
            sewer_tiers=((0.0, 1.0),),
            canon_fixed_per_day=0,
            canon_tiers=((0.0, 1.0),),
            iva_rate=0.10,
        )
        b = calculate_cost(m3=10, days=0, config=cfg)
        assert b.water == pytest.approx(10.0)
        assert b.sewer == pytest.approx(10.0)
        assert b.canon == pytest.approx(10.0)
        # IVA only over water+sewer = 20.0
        assert b.iva == pytest.approx(2.0)
        assert b.total == pytest.approx(32.0)

    def test_include_fixed_false_skips_quotes(self):
        cfg = TariffConfig(
            water_fixed_per_day=10,
            water_tiers=((0.0, 0.5),),
            sewer_fixed_per_day=10,
            sewer_tiers=((0.0, 0.5),),
            canon_fixed_per_day=10,
            canon_tiers=((0.0, 0.5),),
            iva_rate=0.0,
        )
        b = calculate_cost(m3=2, days=5, config=cfg, include_fixed=False)
        # Only variable part: 2 * 0.5 each
        assert b.water == 1.0
        assert b.sewer == 1.0
        assert b.canon == 1.0

    def test_cum_m3_before_drives_tier_crossing(self):
        cfg = TariffConfig(
            water_fixed_per_day=0,
            water_tiers=((10.0, 0.40), (0.0, 0.80)),
            sewer_fixed_per_day=0,
            sewer_tiers=((0.0, 0.0),),
            canon_fixed_per_day=0,
            canon_tiers=((0.0, 0.0),),
            iva_rate=0.0,
        )
        # Already used 8 m³, now consume 5 more
        b = calculate_cost(m3=5, days=0, config=cfg, cum_m3_before=8)
        assert b.water == pytest.approx(2 * 0.40 + 3 * 0.80)


class TestTariffConfigFromOptions:
    def test_defaults_when_options_empty(self):
        cfg = TariffConfig.from_options({})
        # Defaults from const.py — primer tram only, single flat rate
        assert cfg.water_fixed_per_day == pytest.approx(0.2640)
        assert cfg.water_tiers == ((0.0, 0.4384),)
        assert cfg.sewer_tiers == ((0.0, 0.0755),)
        assert cfg.canon_tiers == ((0.0, 0.5232),)
        assert cfg.iva_rate == pytest.approx(0.10)

    def test_three_canon_tiers(self):
        cfg = TariffConfig.from_options({
            CONF_CANON_FIXED_EUR_PER_DAY: 0.0329,
            CONF_CANON_TIER1_EUR_PER_M3: 0.50,
            CONF_CANON_TIER1_LIMIT_M3: 18.0,
            CONF_CANON_TIER2_EUR_PER_M3: 1.20,
            # No tier 3 set ⇒ tier 2 is the open-ended last
        })
        # tier 1 has limit, tier 2 is the catch-all
        assert cfg.canon_tiers == ((18.0, 0.50), (0.0, 1.20))

    def test_zero_price_tier_dropped(self):
        # Sewer with everything zeroed — calculator should still get a tier
        cfg = TariffConfig.from_options({
            CONF_SEWER_FIXED_EUR_PER_DAY: 0.0,
            CONF_SEWER_TIER1_EUR_PER_M3: 0.0,
        })
        # When all tiers are zero we get a placeholder ((0.0, 0.0),)
        assert cfg.sewer_tiers == ((0.0, 0.0),)

    def test_overrides_iva(self):
        cfg = TariffConfig.from_options({CONF_IVA_RATE: 0.21})
        assert cfg.iva_rate == pytest.approx(0.21)

    def test_overrides_water_fixed_and_tier(self):
        cfg = TariffConfig.from_options({
            CONF_WATER_FIXED_EUR_PER_DAY: 0.30,
            CONF_WATER_TIER1_EUR_PER_M3: 0.55,
        })
        assert cfg.water_fixed_per_day == pytest.approx(0.30)
        assert cfg.water_tiers == ((0.0, 0.55),)
