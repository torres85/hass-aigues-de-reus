"""Sensors for Aigües de Reus."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, UnitOfVolume
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_CONTADOR, CONF_CONTRATO, CONF_DIRECCION, DOMAIN, MANUFACTURER
from .coordinator import AiguesDeReusCoordinator, CoordinatorData


@dataclass(frozen=True, kw_only=True)
class AdrSensorDescription(SensorEntityDescription):
    """Describes an Aigües de Reus sensor."""

    value_fn: Callable[[CoordinatorData], float | datetime | None]
    last_reset_fn: Callable[[CoordinatorData], datetime | None] | None = None


SENSORS: tuple[AdrSensorDescription, ...] = (
    AdrSensorDescription(
        key="hourly_consumption",
        translation_key="hourly_consumption",
        name="Darrer consum horari",
        device_class=SensorDeviceClass.WATER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfVolume.CUBIC_METERS,
        suggested_display_precision=4,
        value_fn=lambda d: d.last_hourly_value,
    ),
    AdrSensorDescription(
        key="daily_consumption",
        translation_key="daily_consumption",
        name="Consum d'avui",
        device_class=SensorDeviceClass.WATER,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfVolume.CUBIC_METERS,
        suggested_display_precision=3,
        value_fn=lambda d: d.today_consumption_m3,
    ),
    AdrSensorDescription(
        key="monthly_consumption",
        translation_key="monthly_consumption",
        name="Consum d'aquest mes",
        device_class=SensorDeviceClass.WATER,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfVolume.CUBIC_METERS,
        suggested_display_precision=3,
        value_fn=lambda d: d.month_consumption_m3,
    ),
    AdrSensorDescription(
        key="meter_reading",
        translation_key="meter_reading",
        name="Lectura del comptador",
        device_class=SensorDeviceClass.WATER,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfVolume.CUBIC_METERS,
        suggested_display_precision=3,
        value_fn=lambda d: d.last_meter_reading,
    ),
    AdrSensorDescription(
        key="last_sync",
        translation_key="last_sync",
        name="Última sincronització",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.last_sync,
    ),
    AdrSensorDescription(
        key="last_reading",
        translation_key="last_reading",
        name="Última lectura",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.last_hourly_at,
    ),
    AdrSensorDescription(
        key="daily_cost",
        translation_key="daily_cost",
        name="Cost d'avui",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement="EUR",
        suggested_display_precision=2,
        value_fn=lambda d: d.today_cost_eur,
    ),
    AdrSensorDescription(
        key="monthly_cost",
        translation_key="monthly_cost",
        name="Cost d'aquest mes",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement="EUR",
        suggested_display_precision=2,
        value_fn=lambda d: d.month_cost_eur,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensors from a config entry."""
    coordinator: AiguesDeReusCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        AdrSensor(coordinator, entry, desc) for desc in SENSORS
    )


class AdrSensor(CoordinatorEntity[AiguesDeReusCoordinator], SensorEntity):
    """An Aigües de Reus sensor."""

    _attr_has_entity_name = True
    entity_description: AdrSensorDescription

    def __init__(
        self,
        coordinator: AiguesDeReusCoordinator,
        entry: ConfigEntry,
        description: AdrSensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._entry = entry
        contrato = entry.data[CONF_CONTRATO]
        self._attr_unique_id = f"{contrato}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, contrato)},
            name=f"Aigües de Reus — Contracte {contrato}",
            manufacturer=MANUFACTURER,
            model=entry.data.get(CONF_CONTADOR) or "Comptador digital",
            configuration_url="https://www.aiguesdereus.cat/es-es/Oficina-Virtual",
            suggested_area=entry.data.get(CONF_DIRECCION) or None,
        )

    @property
    def native_value(self) -> float | datetime | None:
        if self.coordinator.data is None:
            return None
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self.coordinator.data is None:
            return None
        if self.entity_description.key == "hourly_consumption":
            ts = self.coordinator.data.last_hourly_at
            return {"last_hour": ts.isoformat() if ts else None}
        if self.entity_description.key == "meter_reading":
            ts = self.coordinator.data.last_meter_reading_at
            return {"reading_at": ts.isoformat() if ts else None}
        return None
