"""The Aigües de Reus integration."""
from __future__ import annotations

import logging

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv

from .api import AiguesDeReusClient
from .const import (
    CONF_CODIGO_CLIENTE,
    CONF_CONTADOR,
    CONF_CONTRATO,
    CONF_NIF,
    CONF_PASSWORD,
    DOMAIN,
    SERVICE_FORCE_BACKFILL,
)
from .coordinator import AiguesDeReusCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR]

FORCE_BACKFILL_SCHEMA = vol.Schema(
    {vol.Optional("entry_id"): cv.string}
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Aigües de Reus from a config entry."""
    client = AiguesDeReusClient(
        entry.data[CONF_NIF],
        entry.data[CONF_PASSWORD],
        codigo_cliente=entry.data[CONF_CODIGO_CLIENTE],
        contrato=entry.data[CONF_CONTRATO],
        contador=entry.data[CONF_CONTADOR],
    )

    coordinator = AiguesDeReusCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    if not hass.services.has_service(DOMAIN, SERVICE_FORCE_BACKFILL):
        async def _handle_force_backfill(call: ServiceCall) -> None:
            entry_id = call.data.get("entry_id")
            coordinators = hass.data.get(DOMAIN, {})
            targets: list[AiguesDeReusCoordinator]
            if entry_id:
                if entry_id not in coordinators:
                    raise ValueError(f"Unknown entry_id {entry_id}")
                targets = [coordinators[entry_id]]
            else:
                targets = list(coordinators.values())
            for c in targets:
                await c.async_force_backfill()

        hass.services.async_register(
            DOMAIN,
            SERVICE_FORCE_BACKFILL,
            _handle_force_backfill,
            schema=FORCE_BACKFILL_SCHEMA,
        )

    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload entry when options change so the new interval takes effect."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        coordinator: AiguesDeReusCoordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.client.async_close()
        if not hass.data[DOMAIN]:
            hass.services.async_remove(DOMAIN, SERVICE_FORCE_BACKFILL)
    return unload_ok
