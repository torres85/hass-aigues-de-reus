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
    CONF_CODIGO_CLIENTE,
    CONF_CONTADOR,
    CONF_CONTRATO,
    CONF_DIRECCION,
    CONF_NIF,
    CONF_PASSWORD,
    CONF_UPDATE_INTERVAL_HOURS,
    DEFAULT_BACKFILL_DAYS,
    DEFAULT_UPDATE_INTERVAL_HOURS,
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


class AiguesDeReusOptionsFlow(OptionsFlow):
    """Allow tweaking poll cadence and backfill window."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current = self.config_entry.options
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_UPDATE_INTERVAL_HOURS,
                    default=current.get(
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
                    default=current.get(CONF_BACKFILL_DAYS, DEFAULT_BACKFILL_DAYS),
                ): vol.All(
                    vol.Coerce(int),
                    vol.Range(min=MIN_BACKFILL_DAYS, max=MAX_BACKFILL_DAYS),
                ),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
