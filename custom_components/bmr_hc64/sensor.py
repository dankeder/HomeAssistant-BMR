"""Sensor entities for BMR HC64 heating controller."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import cached_property
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import BmrUpdateCoordinator
from .config_flow import CONF_CIRCUIT_ID, CONF_CIRCUIT_NAME, BmrConfigEntry
from .const import DOMAIN, MANUFACTURER, MODEL

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BmrConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up BMR HC64 sensors from a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]

    assert entry.unique_id

    for subentry_id, subentry in entry.subentries.items():
        assert subentry.unique_id
        async_add_entities(
            [
                BmrCircuitTemperature(
                    coordinator,
                    entry.unique_id,
                    subentry.unique_id,
                    subentry.data[CONF_CIRCUIT_ID],
                    subentry.data[CONF_CIRCUIT_NAME],
                ),
                BmrCircuitTargetTemperature(
                    coordinator,
                    entry.unique_id,
                    subentry.unique_id,
                    subentry.data[CONF_CIRCUIT_ID],
                    subentry.data[CONF_CIRCUIT_NAME],
                ),
            ],
            config_subentry_id=subentry_id,
        )


class BmrCircuitTemperature(CoordinatorEntity[BmrUpdateCoordinator], SensorEntity):  # type: ignore  # noqa: PGH003
    """Sensor for reporting the current temperature in BMR HC64 heating circuit."""

    def __init__(
        self,
        coordinator: BmrUpdateCoordinator,
        controller_unique_id: str,
        circuit_unique_id: str,
        circuit_id: str,
        circuit_name: str,
    ) -> None:
        """Initialize the BMR HC64 circuit temperature sensor."""
        super().__init__(coordinator)
        self._circuit_id = circuit_id
        self._circuit_name = circuit_name
        self._circuit_state = None
        self._attr_name = f"{coordinator.device_name} {self._circuit_name} Temperature"
        self._attr_unique_id = f"{controller_unique_id}-{circuit_unique_id}-temperature"
        self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, circuit_unique_id)},
            name=circuit_name,
            via_device=(DOMAIN, controller_unique_id),
            manufacturer=MANUFACTURER,
            model=MODEL,
        )

    @cached_property
    def extra_state_attributes(self) -> dict[str, str | bool | float | None]:
        """Return the extra state attributes of the sensor."""
        if self._circuit_state is None:
            return {}
        return {
            "enabled": self._circuit_state.enabled,
            "user_offset": self._circuit_state.user_offset,
            "max_offset": self._circuit_state.max_offset,
            "warning": self._circuit_state.warning,
            "heating": self._circuit_state.heating,
            "cooling": self._circuit_state.cooling,
            "low_mode": self._circuit_state.low_mode,
            "summer_mode": self._circuit_state.summer_mode,
        }

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._circuit_state = self.coordinator.data.circuits[self._circuit_id]
        self._attr_native_value = self._circuit_state.temperature
        self.async_write_ha_state()


class BmrCircuitTargetTemperature(  # type: ignore  # noqa: PGH003
    CoordinatorEntity[BmrUpdateCoordinator], SensorEntity
):
    """Sensor for reporting the current temperature in BMR HC64 heating circuit."""

    def __init__(
        self,
        coordinator: BmrUpdateCoordinator,
        controller_unique_id: str,
        circuit_unique_id: str,
        circuit_id: str,
        circuit_name: str,
    ) -> None:
        """Initialize the BMR HC64 circuit target temperature sensor."""
        super().__init__(coordinator)
        self._circuit_id = circuit_id
        self._circuit_name = circuit_name
        self._circuit_state = None
        self._attr_name = (
            f"{coordinator.device_name} {self._circuit_name} Target Temperature"
        )
        self._attr_native_unit_of_measurement = "°C"
        self._attr_device_class = SensorDeviceClass.TEMPERATURE
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_unique_id = (
            f"{controller_unique_id}-{circuit_unique_id}-target-temperature"
        )
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, circuit_unique_id)},
            name=circuit_name,
            via_device=(DOMAIN, controller_unique_id),
            manufacturer=MANUFACTURER,
            model=MODEL,
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:  # type: ignore  # noqa: PGH003
        """Return the extra state attributes of the sensor."""
        if self._circuit_state is None:
            return {}
        return {
            "enabled": self._circuit_state.enabled,
            "user_offset": self._circuit_state.user_offset,
            "max_offset": self._circuit_state.max_offset,
            "warning": self._circuit_state.warning,
            "heating": self._circuit_state.heating,
            "cooling": self._circuit_state.cooling,
            "low_mode": self._circuit_state.low_mode,
            "summer_mode": self._circuit_state.summer_mode,
        }

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._circuit_state = self.coordinator.data.circuits[self._circuit_id]
        self._attr_native_value = self._circuit_state.target_temperature
        self.async_write_ha_state()
