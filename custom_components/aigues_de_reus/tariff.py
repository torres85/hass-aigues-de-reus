"""Tariff / cost calculation for Aigües de Reus.

Pure module — no Home Assistant deps so it can be unit-tested in isolation.
The model mirrors the structure of a real Reus invoice:

  total = water + sewer + canon + iva
  water  = fixed_eur_per_day * days   + sum(tier_price * m3_in_tier)
  sewer  = idem with sewer rates
  canon  = idem with canon rates  (NOT subject to IVA)
  iva    = iva_rate * (water + sewer)

Tiers are encoded as ``((limit_m3, eur_per_m3), ...)`` ordered by ascending
``limit_m3``. ``limit_m3 == 0`` means "no limit / open-ended" — used either
as the only tier (single flat rate) or as the last tier to absorb everything
above the previous threshold.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .const import (
    CONF_CANON_FIXED_EUR_PER_DAY,
    CONF_CANON_TIER1_EUR_PER_M3,
    CONF_CANON_TIER1_LIMIT_M3,
    CONF_CANON_TIER2_EUR_PER_M3,
    CONF_CANON_TIER2_LIMIT_M3,
    CONF_CANON_TIER3_EUR_PER_M3,
    CONF_IVA_RATE,
    CONF_SEWER_FIXED_EUR_PER_DAY,
    CONF_SEWER_TIER1_EUR_PER_M3,
    CONF_SEWER_TIER1_LIMIT_M3,
    CONF_SEWER_TIER2_EUR_PER_M3,
    CONF_SEWER_TIER2_LIMIT_M3,
    CONF_SEWER_TIER3_EUR_PER_M3,
    CONF_WATER_FIXED_EUR_PER_DAY,
    CONF_WATER_TIER1_EUR_PER_M3,
    CONF_WATER_TIER1_LIMIT_M3,
    CONF_WATER_TIER2_EUR_PER_M3,
    CONF_WATER_TIER2_LIMIT_M3,
    CONF_WATER_TIER3_EUR_PER_M3,
    DEFAULT_CANON_FIXED_EUR_PER_DAY,
    DEFAULT_CANON_TIER1_EUR_PER_M3,
    DEFAULT_CANON_TIER1_LIMIT_M3,
    DEFAULT_CANON_TIER2_EUR_PER_M3,
    DEFAULT_CANON_TIER2_LIMIT_M3,
    DEFAULT_CANON_TIER3_EUR_PER_M3,
    DEFAULT_IVA_RATE,
    DEFAULT_SEWER_FIXED_EUR_PER_DAY,
    DEFAULT_SEWER_TIER1_EUR_PER_M3,
    DEFAULT_SEWER_TIER1_LIMIT_M3,
    DEFAULT_SEWER_TIER2_EUR_PER_M3,
    DEFAULT_SEWER_TIER2_LIMIT_M3,
    DEFAULT_SEWER_TIER3_EUR_PER_M3,
    DEFAULT_WATER_FIXED_EUR_PER_DAY,
    DEFAULT_WATER_TIER1_EUR_PER_M3,
    DEFAULT_WATER_TIER1_LIMIT_M3,
    DEFAULT_WATER_TIER2_EUR_PER_M3,
    DEFAULT_WATER_TIER2_LIMIT_M3,
    DEFAULT_WATER_TIER3_EUR_PER_M3,
)


Tier = tuple[float, float]  # (limit_m3, eur_per_m3); limit==0 ⇒ no upper bound


@dataclass(frozen=True)
class TariffConfig:
    water_fixed_per_day: float
    water_tiers: tuple[Tier, ...]
    sewer_fixed_per_day: float
    sewer_tiers: tuple[Tier, ...]
    canon_fixed_per_day: float
    canon_tiers: tuple[Tier, ...]
    iva_rate: float

    @classmethod
    def from_options(cls, options: dict[str, Any]) -> "TariffConfig":
        return cls(
            water_fixed_per_day=float(
                options.get(CONF_WATER_FIXED_EUR_PER_DAY, DEFAULT_WATER_FIXED_EUR_PER_DAY)
            ),
            water_tiers=_build_tiers(
                options,
                (CONF_WATER_TIER1_LIMIT_M3, CONF_WATER_TIER1_EUR_PER_M3),
                (CONF_WATER_TIER2_LIMIT_M3, CONF_WATER_TIER2_EUR_PER_M3),
                (None, CONF_WATER_TIER3_EUR_PER_M3),
                defaults=(
                    (DEFAULT_WATER_TIER1_LIMIT_M3, DEFAULT_WATER_TIER1_EUR_PER_M3),
                    (DEFAULT_WATER_TIER2_LIMIT_M3, DEFAULT_WATER_TIER2_EUR_PER_M3),
                    (None, DEFAULT_WATER_TIER3_EUR_PER_M3),
                ),
            ),
            sewer_fixed_per_day=float(
                options.get(CONF_SEWER_FIXED_EUR_PER_DAY, DEFAULT_SEWER_FIXED_EUR_PER_DAY)
            ),
            sewer_tiers=_build_tiers(
                options,
                (CONF_SEWER_TIER1_LIMIT_M3, CONF_SEWER_TIER1_EUR_PER_M3),
                (CONF_SEWER_TIER2_LIMIT_M3, CONF_SEWER_TIER2_EUR_PER_M3),
                (None, CONF_SEWER_TIER3_EUR_PER_M3),
                defaults=(
                    (DEFAULT_SEWER_TIER1_LIMIT_M3, DEFAULT_SEWER_TIER1_EUR_PER_M3),
                    (DEFAULT_SEWER_TIER2_LIMIT_M3, DEFAULT_SEWER_TIER2_EUR_PER_M3),
                    (None, DEFAULT_SEWER_TIER3_EUR_PER_M3),
                ),
            ),
            canon_fixed_per_day=float(
                options.get(CONF_CANON_FIXED_EUR_PER_DAY, DEFAULT_CANON_FIXED_EUR_PER_DAY)
            ),
            canon_tiers=_build_tiers(
                options,
                (CONF_CANON_TIER1_LIMIT_M3, CONF_CANON_TIER1_EUR_PER_M3),
                (CONF_CANON_TIER2_LIMIT_M3, CONF_CANON_TIER2_EUR_PER_M3),
                (None, CONF_CANON_TIER3_EUR_PER_M3),
                defaults=(
                    (DEFAULT_CANON_TIER1_LIMIT_M3, DEFAULT_CANON_TIER1_EUR_PER_M3),
                    (DEFAULT_CANON_TIER2_LIMIT_M3, DEFAULT_CANON_TIER2_EUR_PER_M3),
                    (None, DEFAULT_CANON_TIER3_EUR_PER_M3),
                ),
            ),
            iva_rate=float(options.get(CONF_IVA_RATE, DEFAULT_IVA_RATE)),
        )


@dataclass
class CostBreakdown:
    water: float = 0.0
    sewer: float = 0.0
    canon: float = 0.0
    iva: float = 0.0

    @property
    def total(self) -> float:
        return self.water + self.sewer + self.canon + self.iva


def _build_tiers(
    options: dict[str, Any],
    *spec: tuple[str | None, str],
    defaults: tuple[tuple[float | None, float], ...],
) -> tuple[Tier, ...]:
    """Build the tiers tuple from flat option keys.

    Each ``spec`` entry is ``(limit_key_or_None, price_key)``. A tier is kept
    only if its price > 0. The last tier may pass ``None`` as limit_key — it
    will always be the open-ended catch-all (limit=0).
    """
    tiers: list[Tier] = []
    for (lim_key, price_key), (def_lim, def_price) in zip(spec, defaults):
        price = float(options.get(price_key, def_price))
        if price <= 0:
            continue
        if lim_key is None:
            limit = 0.0
        else:
            limit = float(options.get(lim_key, def_lim if def_lim is not None else 0.0))
        tiers.append((limit, price))
    if not tiers:
        return ((0.0, 0.0),)
    # Tiers with limit==0 sort to the end so the catch-all is always last.
    tiers.sort(key=lambda t: (t[0] == 0.0, t[0]))
    return tuple(tiers)


def _marginal_tier_cost(
    m3: float, cum_before: float, tiers: tuple[Tier, ...]
) -> float:
    """Cost of consuming `m3` more m³, when the running cumulative consumption
    before this slice is `cum_before`. Tiers are ordered by limit ascending,
    with the last tier acting as catch-all when its limit is 0.
    """
    if m3 <= 0 or not tiers:
        return 0.0
    remaining = m3
    pos = cum_before
    cost = 0.0
    for i, (limit, price) in enumerate(tiers):
        is_last = i == len(tiers) - 1
        if limit <= 0 or is_last:
            cost += remaining * price
            return cost
        if pos >= limit:
            continue
        room = limit - pos
        used = min(room, remaining)
        cost += used * price
        remaining -= used
        pos += used
        if remaining <= 0:
            return cost
    return cost


def calculate_cost(
    m3: float,
    days: float,
    config: TariffConfig,
    *,
    cum_m3_before: float = 0.0,
    include_fixed: bool = True,
) -> CostBreakdown:
    """Cost (€) of consuming `m3` over `days`, with running position
    `cum_m3_before` driving tier crossings.

    `include_fixed=False` is useful when the caller has already applied the
    fixed quotas elsewhere (e.g. spread across calendar days).
    """
    water_var = _marginal_tier_cost(m3, cum_m3_before, config.water_tiers)
    sewer_var = _marginal_tier_cost(m3, cum_m3_before, config.sewer_tiers)
    canon_var = _marginal_tier_cost(m3, cum_m3_before, config.canon_tiers)

    water_fix = config.water_fixed_per_day * days if include_fixed else 0.0
    sewer_fix = config.sewer_fixed_per_day * days if include_fixed else 0.0
    canon_fix = config.canon_fixed_per_day * days if include_fixed else 0.0

    water = water_fix + water_var
    sewer = sewer_fix + sewer_var
    canon = canon_fix + canon_var
    iva = config.iva_rate * (water + sewer)

    return CostBreakdown(water=water, sewer=sewer, canon=canon, iva=iva)
