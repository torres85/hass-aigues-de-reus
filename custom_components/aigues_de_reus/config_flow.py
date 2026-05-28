"""Config flow for Aigües de Reus."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback

from .api import AiguesDeReusClient, AuthError
from .const import (
    CONF_BACKFILL_DAYS,
    CONF_BILLING_PERIOD_DAYS,
    CONF_BILLING_PERIOD_START,
    CONF_CANON_FIXED_EUR_PER_DAY,
    CONF_CANON_TIER1_EUR_PER_M3,
    CONF_CANON_TIER1_LIMIT_M3,
    CONF_CANON_TIER2_EUR_PER_M3,
    CONF_CANON_TIER2_LIMIT_M3,
    CONF_CANON_TIER3_EUR_PER_M3,
    CONF_CODIGO_CLIENTE,
    CONF_CONTADOR,
    CONF_CONTRATO,
    CONF_DIRECCION,
    CONF_IVA_RATE,
    CONF_NIF,
    CONF_PASSWORD,
    CONF_SEWER_FIXED_EUR_PER_DAY,
    CONF_SEWER_TIER1_EUR_PER_M3,
    CONF_SEWER_TIER1_LIMIT_M3,
    CONF_SEWER_TIER2_EUR_PER_M3,
    CONF_SEWER_TIER2_LIMIT_M3,
    CONF_SEWER_TIER3_EUR_PER_M3,
    CONF_TARIFF_ENABLED,
    CONF_UPDATE_INTERVAL_HOURS,
    CONF_WATER_FIXED_EUR_PER_DAY,
    CONF_WATER_TIER1_EUR_PER_M3,
    CONF_WATER_TIER1_LIMIT_M3,
    CONF_WATER_TIER2_EUR_PER_M3,
    CONF_WATER_TIER2_LIMIT_M3,
    CONF_WATER_TIER3_EUR_PER_M3,
    DEFAULT_BACKFILL_DAYS,
    DEFAULT_BILLING_PERIOD_DAYS,
    DEFAULT_BILLING_PERIOD_START,
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
    DEFAULT_TARIFF_ENABLED,
    DEFAULT_UPDATE_INTERVAL_HOURS,
    DEFAULT_WATER_FIXED_EUR_PER_DAY,
    DEFAULT_WATER_TIER1_EUR_PER_M3,
    DEFAULT_WATER_TIER1_LIMIT_M3,
    DEFAULT_WATER_TIER2_EUR_PER_M3,
    DEFAULT_WATER_TIER2_LIMIT_M3,
    DEFAULT_WATER_TIER3_EUR_PER_M3,
    DOMAIN,
    MAX_BACKFILL_DAYS,
    MAX_UPDATE_INTERVAL_HOURS,
    MIN_BACKFILL_DAYS,
    MIN_UPDATE_INTERVAL_HOURS,
)

_LOGGER = logging.getLogger(__name__)

USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_NIF): str,
        vol.Required(CONF_PASSWORD): str,
    }
)


class AiguesDeReusConfigFlow(ConfigFlow, domain=DOMAIN):
    """Config flow."""

    VERSION = 1

    def __init__(self) -> None:
        self._nif: str | None = None
        self._password: str | None = None
        self._contracts: list[Any] = []

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return AiguesDeReusOptionsFlow()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            client = AiguesDeReusClient(
                user_input[CONF_NIF], user_input[CONF_PASSWORD]
            )
            try:
                await client.async_login()
                contracts = await client.async_get_contracts()
            except AuthError:
                errors["base"] = "invalid_auth"
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Error inesperat al login")
                errors["base"] = "cannot_connect"
            else:
                if not contracts:
                    errors["base"] = "no_contracts"
                else:
                    self._nif = user_input[CONF_NIF]
                    self._password = user_input[CONF_PASSWORD]
                    self._contracts = contracts
                    if len(contracts) == 1:
                        await client.async_close()
                        return await self._create_entry(contracts[0])
                    await client.async_close()
                    return await self.async_step_contract()
            await client.async_close()

        return self.async_show_form(
            step_id="user", data_schema=USER_SCHEMA, errors=errors
        )

    async def async_step_contract(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            chosen = next(
                c for c in self._contracts if c.contrato == user_input[CONF_CONTRATO]
            )
            return await self._create_entry(chosen)

        options = {
            c.contrato: f"{c.contrato} — {c.direccion or 'Sense adreça'}"
            for c in self._contracts
            if c.codigo_cliente and c.contador  # only fully-known contracts
        }
        if not options:
            return self.async_abort(reason="no_usable_contracts")

        return self.async_show_form(
            step_id="contract",
            data_schema=vol.Schema({vol.Required(CONF_CONTRATO): vol.In(options)}),
        )

    async def _create_entry(self, contract: Any) -> ConfigFlowResult:
        await self.async_set_unique_id(f"{self._nif}_{contract.contrato}")
        self._abort_if_unique_id_configured()
        return self.async_create_entry(
            title=f"Aigües de Reus ({contract.contrato})",
            data={
                CONF_NIF: self._nif,
                CONF_PASSWORD: self._password,
                CONF_CODIGO_CLIENTE: contract.codigo_cliente,
                CONF_CONTRATO: contract.contrato,
                CONF_CONTADOR: contract.contador,
                CONF_DIRECCION: contract.direccion or "",
            },
        )


def _validate_iso_date_or_empty(value: Any) -> str:
    """Voluptuous validator: accept "" or a YYYY-MM-DD string."""
    if value is None or value == "":
        return ""
    if not isinstance(value, str):
        raise vol.Invalid("Has de ser una data en format YYYY-MM-DD")
    try:
        from datetime import date as _date

        _date.fromisoformat(value)
    except ValueError as err:
        raise vol.Invalid("Format de data no vàlid (esperat YYYY-MM-DD)") from err
    return value


_NON_NEG_FLOAT = vol.All(vol.Coerce(float), vol.Range(min=0))


class AiguesDeReusOptionsFlow(OptionsFlow):
    """Allow tweaking poll cadence, backfill window and tariff/cost setup."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current = self.config_entry.options

        def _opt(key: str, default: Any) -> Any:
            return current.get(key, default)

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_UPDATE_INTERVAL_HOURS,
                    default=_opt(
                        CONF_UPDATE_INTERVAL_HOURS, DEFAULT_UPDATE_INTERVAL_HOURS
                    ),
                ): vol.All(
                    vol.Coerce(int),
                    vol.Range(
                        min=MIN_UPDATE_INTERVAL_HOURS,
                        max=MAX_UPDATE_INTERVAL_HOURS,
                    ),
                ),
                vol.Required(
                    CONF_BACKFILL_DAYS,
                    default=_opt(CONF_BACKFILL_DAYS, DEFAULT_BACKFILL_DAYS),
                ): vol.All(
                    vol.Coerce(int),
                    vol.Range(min=MIN_BACKFILL_DAYS, max=MAX_BACKFILL_DAYS),
                ),
                # --- Cost / tariff configuration ---
                vol.Required(
                    CONF_TARIFF_ENABLED,
                    default=_opt(CONF_TARIFF_ENABLED, DEFAULT_TARIFF_ENABLED),
                ): bool,
                vol.Required(
                    CONF_BILLING_PERIOD_START,
                    default=_opt(
                        CONF_BILLING_PERIOD_START, DEFAULT_BILLING_PERIOD_START
                    ),
                ): _validate_iso_date_or_empty,
                vol.Required(
                    CONF_BILLING_PERIOD_DAYS,
                    default=_opt(
                        CONF_BILLING_PERIOD_DAYS, DEFAULT_BILLING_PERIOD_DAYS
                    ),
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=365)),
                vol.Required(
                    CONF_IVA_RATE,
                    default=_opt(CONF_IVA_RATE, DEFAULT_IVA_RATE),
                ): vol.All(vol.Coerce(float), vol.Range(min=0, max=1)),
                # Water
                vol.Required(
                    CONF_WATER_FIXED_EUR_PER_DAY,
                    default=_opt(
                        CONF_WATER_FIXED_EUR_PER_DAY,
                        DEFAULT_WATER_FIXED_EUR_PER_DAY,
                    ),
                ): _NON_NEG_FLOAT,
                vol.Required(
                    CONF_WATER_TIER1_EUR_PER_M3,
                    default=_opt(
                        CONF_WATER_TIER1_EUR_PER_M3,
                        DEFAULT_WATER_TIER1_EUR_PER_M3,
                    ),
                ): _NON_NEG_FLOAT,
                vol.Required(
                    CONF_WATER_TIER1_LIMIT_M3,
                    default=_opt(
                        CONF_WATER_TIER1_LIMIT_M3, DEFAULT_WATER_TIER1_LIMIT_M3
                    ),
                ): _NON_NEG_FLOAT,
                vol.Required(
                    CONF_WATER_TIER2_EUR_PER_M3,
                    default=_opt(
                        CONF_WATER_TIER2_EUR_PER_M3,
                        DEFAULT_WATER_TIER2_EUR_PER_M3,
                    ),
                ): _NON_NEG_FLOAT,
                vol.Required(
                    CONF_WATER_TIER2_LIMIT_M3,
                    default=_opt(
                        CONF_WATER_TIER2_LIMIT_M3, DEFAULT_WATER_TIER2_LIMIT_M3
                    ),
                ): _NON_NEG_FLOAT,
                vol.Required(
                    CONF_WATER_TIER3_EUR_PER_M3,
                    default=_opt(
                        CONF_WATER_TIER3_EUR_PER_M3,
                        DEFAULT_WATER_TIER3_EUR_PER_M3,
                    ),
                ): _NON_NEG_FLOAT,
                # Sewer
                vol.Required(
                    CONF_SEWER_FIXED_EUR_PER_DAY,
                    default=_opt(
                        CONF_SEWER_FIXED_EUR_PER_DAY,
                        DEFAULT_SEWER_FIXED_EUR_PER_DAY,
                    ),
                ): _NON_NEG_FLOAT,
                vol.Required(
                    CONF_SEWER_TIER1_EUR_PER_M3,
                    default=_opt(
                        CONF_SEWER_TIER1_EUR_PER_M3,
                        DEFAULT_SEWER_TIER1_EUR_PER_M3,
                    ),
                ): _NON_NEG_FLOAT,
                vol.Required(
                    CONF_SEWER_TIER1_LIMIT_M3,
                    default=_opt(
                        CONF_SEWER_TIER1_LIMIT_M3, DEFAULT_SEWER_TIER1_LIMIT_M3
                    ),
                ): _NON_NEG_FLOAT,
                vol.Required(
                    CONF_SEWER_TIER2_EUR_PER_M3,
                    default=_opt(
                        CONF_SEWER_TIER2_EUR_PER_M3,
                        DEFAULT_SEWER_TIER2_EUR_PER_M3,
                    ),
                ): _NON_NEG_FLOAT,
                vol.Required(
                    CONF_SEWER_TIER2_LIMIT_M3,
                    default=_opt(
                        CONF_SEWER_TIER2_LIMIT_M3, DEFAULT_SEWER_TIER2_LIMIT_M3
                    ),
                ): _NON_NEG_FLOAT,
                vol.Required(
                    CONF_SEWER_TIER3_EUR_PER_M3,
                    default=_opt(
                        CONF_SEWER_TIER3_EUR_PER_M3,
                        DEFAULT_SEWER_TIER3_EUR_PER_M3,
                    ),
                ): _NON_NEG_FLOAT,
                # Cànon
                vol.Required(
                    CONF_CANON_FIXED_EUR_PER_DAY,
                    default=_opt(
                        CONF_CANON_FIXED_EUR_PER_DAY,
                        DEFAULT_CANON_FIXED_EUR_PER_DAY,
                    ),
                ): _NON_NEG_FLOAT,
                vol.Required(
                    CONF_CANON_TIER1_EUR_PER_M3,
                    default=_opt(
                        CONF_CANON_TIER1_EUR_PER_M3,
                        DEFAULT_CANON_TIER1_EUR_PER_M3,
                    ),
                ): _NON_NEG_FLOAT,
                vol.Required(
                    CONF_CANON_TIER1_LIMIT_M3,
                    default=_opt(
                        CONF_CANON_TIER1_LIMIT_M3, DEFAULT_CANON_TIER1_LIMIT_M3
                    ),
                ): _NON_NEG_FLOAT,
                vol.Required(
                    CONF_CANON_TIER2_EUR_PER_M3,
                    default=_opt(
                        CONF_CANON_TIER2_EUR_PER_M3,
                        DEFAULT_CANON_TIER2_EUR_PER_M3,
                    ),
                ): _NON_NEG_FLOAT,
                vol.Required(
                    CONF_CANON_TIER2_LIMIT_M3,
                    default=_opt(
                        CONF_CANON_TIER2_LIMIT_M3, DEFAULT_CANON_TIER2_LIMIT_M3
                    ),
                ): _NON_NEG_FLOAT,
                vol.Required(
                    CONF_CANON_TIER3_EUR_PER_M3,
                    default=_opt(
                        CONF_CANON_TIER3_EUR_PER_M3,
                        DEFAULT_CANON_TIER3_EUR_PER_M3,
                    ),
                ): _NON_NEG_FLOAT,
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
