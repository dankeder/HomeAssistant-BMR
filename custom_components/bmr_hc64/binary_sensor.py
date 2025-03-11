"""Binary sensor entities for BMR HC64 heating controller."""

from __future__ import annotations

import logging

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import BmrUpdateCoordinator
from .config_flow import BmrConfigEntry
from .const import DOMAIN, MANUFACTURER, MODEL

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BmrConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up BMR HC64 binary sensors from a config entry."""
    coordinator: BmrUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    assert entry.unique_id

    async_add_entities(
        [
            BmrControllerHDO(
                coordinator,
                controller_name=entry.title,
                controller_unique_id=entry.unique_id,
            )
        ]
    )


class BmrControllerHDO(CoordinatorEntity[BmrUpdateCoordinator], BinarySensorEntity):  # type: ignore  # noqa: PGH003
    """Binary sensor for reporting HDO (low/high electricity tariff)."""

    def __init__(
        self,
        coordinator: BmrUpdateCoordinator,
        controller_name: str,
        controller_unique_id: str,
    ) -> None:  # type: ignore  # noqa: PGH003
        """Binary sensor for reporting HDO (low/high electricity tariff)."""
        super().__init__(coordinator)
        self._attr_name = f"{coordinator.device_name} HDO"
        self._attr_unique_id = f"{self._attr_unique_id}-binary-sensor-hdo"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, controller_unique_id)},
            name=controller_name,
            manufacturer=MANUFACTURER,
            model=MODEL,
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._attr_is_on = self.coordinator.data.hdo
        self.async_write_ha_state()
