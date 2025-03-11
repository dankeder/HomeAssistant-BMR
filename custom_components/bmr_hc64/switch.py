"""Switch entities for BMR HC64 heating controller."""

from datetime import datetime
import logging
from typing import Any

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .config_flow import CONF_CIRCUIT_ID, BmrConfigEntry
from .const import DOMAIN, MANUFACTURER, MODEL
from .coordinator import BmrUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BmrConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up BMR HC64 switch entities from a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]

    assert entry.unique_id

    async_add_entities(
        [
            BmrControllerAwayModeSwitch(
                coordinator,
                controller_name=entry.title,
                controller_unique_id=entry.unique_id,
            ),
            BmrControllerPowerSwitch(
                coordinator,
                controller_name=entry.title,
                controller_unique_id=entry.unique_id,
                circuit_ids=[
                    subentry.data[CONF_CIRCUIT_ID]
                    for subentry in entry.subentries.values()
                ],
            ),
        ]
    )


class BmrControllerAwayModeSwitch(  # type: ignore  # noqa: PGH003
    CoordinatorEntity[BmrUpdateCoordinator], SwitchEntity
):  # type: ignore  # noqa: PGH003
    """Switch entity for toggling the "away mode" of the heating controller.

    In HC64 the same functionality is called "low mode". The "away mode" this is
    a controller-wide toggle - turning it on means that all heating circuits
    will be switched to the "away mode" ("low mode").  When the controller is in
    "low mode" target temperature of all circuits is set to a predefined
    temperature and no schedules are taken into account.
    """

    def __init__(
        self,
        coordinator: BmrUpdateCoordinator,
        controller_name: str,
        controller_unique_id: str,
    ) -> None:
        """Initialize the BmrControllerAwayModeSwitch entity."""
        super().__init__(coordinator)
        self._away_temperature: float | None = None
        self._away_start_date: datetime | None = None

        self._attr_name = f"{coordinator.device_name} Away Mode"
        self._attr_device_class = SwitchDeviceClass.SWITCH
        self._attr_unique_id = f"{controller_unique_id}-away-mode-switch"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, controller_unique_id)},
            name=controller_name,
            manufacturer=MANUFACTURER,
            model=MODEL,
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:  # type: ignore  # noqa: PGH003
        """Return the extra state attributes."""
        return {
            "away_temperature": self._away_temperature,
            "away_start_date": self._away_start_date,
        }

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._attr_is_on = self.coordinator.data.low_mode.get("enabled")
        self._away_temperature = self.coordinator.data.low_mode.get("temperature")
        self._away_start_date = self.coordinator.data.low_mode.get("start_date")
        self.async_write_ha_state()

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the Away mode."""
        _LOGGER.debug("Turn on Away mode")

        # Add all circuits to the low mode assignments
        await self.hass.async_add_executor_job(
            self.coordinator.bmr.setLowModeAssignments,  # type: ignore  # noqa: PGH003
            [int(circuit.id) for circuit in self.coordinator.data.circuits.values()],
            True,
        )

        # Turn on the Away mode
        await self.hass.async_add_executor_job(self.coordinator.bmr.setLowMode, True)  # type: ignore  # noqa: PGH003

        # Update the state
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the Away mode."""
        _LOGGER.debug("Turn off Away mode")

        # Add all circuits to the low mode assignments
        await self.hass.async_add_executor_job(
            self.coordinator.bmr.setLowModeAssignments,  # type: ignore  # noqa: PGH003
            [int(circuit.id) for circuit in self.coordinator.data.circuits.values()],
            False,
        )

        # Turn off the Away mode
        await self.hass.async_add_executor_job(self.coordinator.bmr.setLowMode, False)  # type: ignore  # noqa: PGH003

        # Update the state
        await self.coordinator.async_request_refresh()


class BmrControllerPowerSwitch(CoordinatorEntity[BmrUpdateCoordinator], SwitchEntity):  # type: ignore  # noqa: PGH003
    """Turn heating on/off (in HC64 called "summer mode").

    This is a global state of the controller, not specific to a particular
    circuit.
    """

    def __init__(
        self,
        coordinator: BmrUpdateCoordinator,
        controller_name: str,
        controller_unique_id: str,
        circuit_ids: list[str],
    ) -> None:
        """Initialize the BmrControllerAwayModeSwitch entity."""
        super().__init__(coordinator)
        self._circuit_ids = circuit_ids

        self._attr_name = f"{coordinator.device_name} Power Switch"
        self._attr_device_class = SwitchDeviceClass.SWITCH
        self._attr_unique_id = f"{controller_unique_id}-power-switch"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, controller_unique_id)},
            name=controller_name,
            manufacturer=MANUFACTURER,
            model=MODEL,
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._attr_is_on = not (
            self.coordinator.data.summer_mode
            and all(
                self.coordinator.data.summer_mode_assignments[int(circuit_id)]
                for circuit_id in self._circuit_ids
            )
        )
        self.async_write_ha_state()

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the power on.

        Turn the summer mode off and remove circuits from the summer
        mode assignments.
        """
        _LOGGER.debug("Turn on Power")

        # Turn off the Summer mode
        await self.hass.async_add_executor_job(
            self.coordinator.bmr.setSummerMode,  # type: ignore  # noqa: PGH003
            False,
        )

        # Remove all circuits from the summer mode assignments
        await self.hass.async_add_executor_job(
            self.coordinator.bmr.setSummerModeAssignments,  # type: ignore  # noqa: PGH003
            [int(circuit.id) for circuit in self.coordinator.data.circuits.values()],
            False,
        )

        # Update the state
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the power off.

        Turn the summer mode on and add circuits to the summer mode assignments.
        """
        _LOGGER.debug("Turn off Power")

        # Turn on the Summer mode
        await self.hass.async_add_executor_job(
            self.coordinator.bmr.setSummerMode,  # type: ignore  # noqa: PGH003
            True,  # type: ignore  # noqa: PGH003
        )

        # Add all circuits to the summer mode assignments
        await self.hass.async_add_executor_job(
            self.coordinator.bmr.setSummerModeAssignments,  # type: ignore  # noqa: PGH003
            [int(circuit.id) for circuit in self.coordinator.data.circuits.values()],
            True,
        )

        # Update the state
        await self.coordinator.async_request_refresh()
