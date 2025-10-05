"""Climate entities for BMR HC64 Heating Regulation."""

import logging
from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .config_flow import (
    CONF_AUTO_MODE_DAILY_SCHEDULES,
    CONF_AUTO_MODE_DAILY_SCHEDULES_STARTING_DAY,
    CONF_AWAY_TEMPERATURE,
    CONF_CIRCUIT_ID,
    CONF_CIRCUIT_NAME,
    CONF_ENABLE_COOLING,
    CONF_MANUAL_MODE_SCHEDULE,
    CONF_MAX_TEMPERATURE,
    CONF_MIN_TEMPERATURE,
    BmrConfigEntry,
)
from .const import DOMAIN, MANUFACTURER, MODEL
from .coordinator import BmrUpdateCoordinator

# Normal mode
CLIMATE_PRESET_NONE = "none"

# Away mode
CLIMATE_PRESET_AWAY = "away"


_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BmrConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up BMR HC64 switch entities from a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]

    assert entry.unique_id

    for subentry_id, subentry in entry.subentries.items():
        assert subentry.unique_id
        async_add_entities(
            [
                BmrClimateEntity(
                    coordinator=coordinator,
                    # Controller-specific settings are taken from "entry"; the entry
                    # corresponds to the controller device
                    controller_unique_id=entry.unique_id,
                    away_temperature=entry.data[CONF_AWAY_TEMPERATURE],
                    enable_cooling=entry.data[CONF_ENABLE_COOLING],
                    # Circuit-specific settings are taken from "subentry"; the
                    # subentry corresponds to the heating circuit
                    circuit_unique_id=subentry.unique_id,
                    circuit_id=subentry.data[CONF_CIRCUIT_ID],
                    circuit_name=subentry.data[CONF_CIRCUIT_NAME],
                    circuit_manual_mode_schedule=subentry.data[
                        CONF_MANUAL_MODE_SCHEDULE
                    ],
                    circuit_auto_mode_daily_schedules=subentry.data[
                        CONF_AUTO_MODE_DAILY_SCHEDULES
                    ],
                    circuit_auto_mode_daily_schedules_starting_day=subentry.data[
                        CONF_AUTO_MODE_DAILY_SCHEDULES_STARTING_DAY
                    ],
                    circuit_min_temperature=subentry.data[CONF_MIN_TEMPERATURE],
                    circuit_max_temperature=subentry.data[CONF_MAX_TEMPERATURE],
                )
            ],
            config_subentry_id=subentry_id,
        )


class BmrClimateEntity(CoordinatorEntity[BmrUpdateCoordinator], ClimateEntity):  # type: ignore  # noqa: PGH003
    """Climate entity for controlling a BMR HC64 heating circuit.

    This class supports the following HVAC modes:

    - HVACMode.OFF - Turn off the heating circuit. The heating circuit will be
      assigned to the "summer mode" and the summer mode will be turned on.

    - HVACMode.AUTO - Automatic mode. BMR HC64 controller will manage the
      temperature automatically according to its configuration (schedules). The
      settings configured in BMR HC 64 controller web UI will take effect.

    - HVACMode.HEAT, HVACMode.COOL, HVACMode.HEAT_COOL - Set the heating circuit
      to heat (or cool) to the specified target temperature.  In BMR HC64
      controller the heating circuit will be switched to a special "override
      schedule". The "override schedule" will be configured to the constant target
      temperature. HVACMode.COOL and HVACMode.HEAT_COOL is for water-based
      circuits that can also cool (untested).

      NOTE: Make sure to remove all circuits from summer mode when using
      the plugin for the first time. Otherwise any circuits assigned to the
      summer mode will be also turned off when the user switches a
      circuit into the HVACMode.OFF mode.

      NOTE #2: The HC64 controller may be very slow to catch up so updates after
      changing something (such as HVAC mode) may take a while to show in Home
      Assistant UI. Even several minutes.
    """

    def __init__(
        self,
        coordinator: BmrUpdateCoordinator,
        controller_unique_id: str,
        circuit_unique_id: str,
        circuit_id: str,
        circuit_name: str,
        circuit_manual_mode_schedule: str,
        circuit_auto_mode_daily_schedules: list[int],
        circuit_auto_mode_daily_schedules_starting_day: int,
        away_temperature: float,
        circuit_min_temperature: float,
        circuit_max_temperature: float,
        enable_cooling: bool = False,
    ) -> None:
        """Initialize the climate entity for a BMR HC64 heating circuit."""
        super().__init__(coordinator)
        self._circuit_id = circuit_id
        self._circuit_name = circuit_name
        self._circuit_state = None
        self._circuit_manual_mode_schedule = circuit_manual_mode_schedule
        self._circuit_auto_mode_daily_schedules = circuit_auto_mode_daily_schedules
        self._circuit_auto_mode_daily_schedules_starting_day = (
            circuit_auto_mode_daily_schedules_starting_day
        )
        self._away_temperature = away_temperature
        self._summer_mode = None
        self._summer_mode_assignments = {}
        self._low_mode = None
        self._low_mode_assignments = {}
        self._enable_cooling = enable_cooling

        self._attr_name = f"{coordinator.device_name} {self._circuit_name}"
        self._attr_unique_id = f"{controller_unique_id}-{circuit_unique_id}-climate"
        self._attr_temperature_unit = UnitOfTemperature.CELSIUS
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, circuit_unique_id)},
            name=circuit_name,
            via_device=(DOMAIN, controller_unique_id),
            manufacturer=MANUFACTURER,
            model=MODEL,
        )
        self._attr_supported_features = (
            ClimateEntityFeature.TARGET_TEMPERATURE
            | ClimateEntityFeature.PRESET_MODE
            | ClimateEntityFeature.TURN_ON
            | ClimateEntityFeature.TURN_OFF
        )
        self._attr_preset_modes = [CLIMATE_PRESET_NONE, CLIMATE_PRESET_AWAY]
        self._attr_min_temp = circuit_min_temperature
        self._attr_max_temp = circuit_max_temperature

        if self._enable_cooling:
            self._attr_hvac_modes = [
                HVACMode.AUTO,
                HVACMode.COOL,
                HVACMode.HEAT,
                HVACMode.HEAT_COOL,
                HVACMode.OFF,
            ]
        else:
            self._attr_hvac_modes = [HVACMode.AUTO, HVACMode.HEAT, HVACMode.OFF]
        self._attr_preset_mode = None
        self._attr_hvac_mode = None
        self._attr_hvac_action = None
        self._current_temperature = None
        self._target_temperature = None

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._circuit_state = self.coordinator.data.circuits[self._circuit_id]
        self._summer_mode = self.coordinator.data.summer_mode
        self._summer_mode_assignments = self.coordinator.data.summer_mode_assignments
        self._low_mode = self.coordinator.data.low_mode
        self._low_mode_assignments = self.coordinator.data.low_mode_assignments
        self._update_preset_mode()
        self._update_hvac_mode()
        self._update_hvac_action()
        self._update_current_temperature()
        self._update_target_temperature()
        self.async_write_ha_state()

    def _update_preset_mode(self) -> None:
        """Update the value of "preset_mode"."""
        if self._low_mode is None:
            self._attr_preset_mode = None
        elif self._low_mode["enabled"]:
            self._attr_preset_mode = CLIMATE_PRESET_AWAY
        else:
            self._attr_preset_mode = CLIMATE_PRESET_NONE

    def _update_hvac_mode(self) -> None:
        """Update the value of "hvac_mode".

        Sets HVACMode.OFF if the summer mode for the circuit is turned
        on. Summer mode essentially means the circuit is turned off.

        Sets HVACMode.HEAT or HVACMode.HEAT_COOL if the user manually
        overrode the target temperature. The override works by reassigning
        the circuit to a special "override" schedule specified in the
        configuration. The target temperature for the "override" schedule
        is set by the self.set_temperature() method.

        Sets HVACMode.AUTO if the BMR HC64 controller is managing target
        temperature automatically according to its configuration (schedules).
        """
        if (
            self._circuit_state is None
            or self._summer_mode is None
            or self._summer_mode_assignments is None  # type: ignore  # noqa: PGH003
        ):
            self._attr_hvac_mode = None
        elif self._summer_mode_assignments[int(self._circuit_id)]:  # type: ignore  # noqa: PGH003
            self._attr_hvac_mode = HVACMode.OFF
        elif [
            int(self._circuit_manual_mode_schedule)
        ] == self._circuit_state.schedules.get(  # type: ignore  # noqa: PGH003
            "day_schedules"
        ):
            self._attr_hvac_mode = (
                HVACMode.HEAT_COOL if self._enable_cooling else HVACMode.HEAT
            )
        else:
            self._attr_hvac_mode = HVACMode.AUTO

    def _update_hvac_action(self) -> None:
        """Update value of "hvac_action".

        The "hvac_action" indicates what is the climate device currently doing
        (cooling, heating, idle, etc.).
        """
        if (
            self._circuit_state is None
            or self._summer_mode is None
            or self._summer_mode_assignments is None  # type: ignore  # noqa: PGH003
        ):
            self._attr_hvac_action = None
        elif (
            self._summer_mode_assignments[int(self._circuit_id)]  # type: ignore  # noqa: PGH003
        ):
            self._attr_hvac_action = HVACAction.OFF
        elif self._circuit_state.heating:
            self._attr_hvac_action = HVACAction.HEATING
        elif self._circuit_state.cooling:
            self._attr_hvac_action = HVACAction.COOLING
        else:
            self._attr_hvac_action = HVACAction.IDLE

    def _update_current_temperature(self) -> None:
        """Update the value of "current_temperature"."""
        if self._circuit_state is None:
            self._attr_current_temperature = None
        else:
            self._attr_current_temperature = self._circuit_state.temperature

    def _update_target_temperature(self) -> None:
        """Update the value of "target_temperature"."""
        if self._circuit_state is None:
            self._attr_target_temperature = None
        else:
            self._attr_target_temperature = self._circuit_state.target_temperature

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set HVAC mode."""
        if hvac_mode == HVACMode.OFF:
            # Turn on the HVAC_MODE_OFF. This will turn off the heating/cooling
            # of the given circuit. This works by:
            #
            # - Adding the circuit to summer mode
            # - Turning the summer mode ON
            #
            # NOTE: Sometimes (usually) there are also other circuits assigned
            # to summer mode, especially if this plugin is used for the first
            # time. If there are also other circutis assigned to summer mode
            # and summer mode is turned on they will be turned off too. Make
            # sure to remove any circuits from the summer mode manually when
            # using the plugin for the first time.
            await self.hass.async_add_executor_job(
                self.coordinator.bmr.setSummerModeAssignments,  # type: ignore  # noqa: PGH003
                [int(self._circuit_id)],
                True,
            )
            if not (
                await self.hass.async_add_executor_job(
                    self.coordinator.bmr.getSummerMode
                )
            ):
                await self.hass.async_add_executor_job(
                    self.coordinator.bmr.setSummerMode,  # type: ignore  # noqa: PGH003
                    True,
                )
        else:
            # Turn HVAC_MODE_OFF off and restore normal operation.
            #
            # - Remove the circuit from the summer mode assignments
            # - If there aren't any circuits assigned to summer mode anymore
            #   turn the summer mode OFF.
            await self.hass.async_add_executor_job(
                self.coordinator.bmr.setSummerModeAssignments,  # type: ignore  # noqa: PGH003
                [int(self._circuit_id)],
                False,
            )
            if not any(
                await self.hass.async_add_executor_job(
                    self.coordinator.bmr.getSummerModeAssignments
                )
            ):
                await self.hass.async_add_executor_job(
                    self.coordinator.bmr.setSummerMode,  # type: ignore  # noqa: PGH003
                    False,
                )

        if hvac_mode in (HVACMode.HEAT, HVACMode.HEAT_COOL):
            # Turn on the HVAC_MODE_HEAT. This will assign the "override"
            # schedule to the circuit. The "override" schedule is used for
            # setting the custom target temperature (see set_temperature()
            # below).
            await self.hass.async_add_executor_job(
                self.coordinator.bmr.setCircuitSchedules,  # type: ignore  # noqa: PGH003
                int(self._circuit_id),
                [int(self._circuit_manual_mode_schedule)],
            )
        else:
            # Turn off the HVAC_MODE_HEAT/HVAC_MODE_HEAT_COOL and restore
            # normal operation.
            #
            # - Assign normal schedules to the circuit
            await self.hass.async_add_executor_job(
                self.coordinator.bmr.setCircuitSchedules,  # type: ignore  # noqa: PGH003
                int(self._circuit_id),
                [int(x) for x in self._circuit_auto_mode_daily_schedules],
                int(self._circuit_auto_mode_daily_schedules_starting_day),  # type: ignore  # noqa: PGH003
            )

        if hvac_mode == HVACMode.AUTO:
            # Turn on the HVACMode.AUTO. Currently this is no-op, as the
            # normal operation is restored in the else branches above.
            pass

        # Update the state
        await self.coordinator.async_request_refresh()

    async def async_set_preset_mode(self, preset_mode: str) -> None:  # type: ignore  # noqa: PGH003
        """Set preset mode."""
        if preset_mode == CLIMATE_PRESET_AWAY:
            # Add the circuit into "low mode" assignments and turn on the "low mode"
            await self.hass.async_add_executor_job(
                self.coordinator.bmr.setLowModeAssignments,  # type: ignore  # noqa: PGH003
                [int(self._circuit_id)],
                True,
            )
            if not (
                await self.hass.async_add_executor_job(self.coordinator.bmr.getLowMode)
            )["enabled"]:
                await self.hass.async_add_executor_job(
                    self.coordinator.bmr.setLowMode,  # type: ignore  # noqa: PGH003
                    True,
                    self._away_temperature,
                )
        else:
            # Remove the circuit from "low mode" assignments.  If this was the
            # last circuit in the "low mode" then turn off the "low mode" as
            # well.
            await self.hass.async_add_executor_job(
                self.coordinator.bmr.setLowModeAssignments,  # type: ignore  # noqa: PGH003
                [int(self._circuit_id)],
                False,
            )
            if not any(
                await self.hass.async_add_executor_job(
                    self.coordinator.bmr.getLowModeAssignments
                )
            ):
                await self.hass.async_add_executor_job(
                    self.coordinator.bmr.setLowMode,  # type: ignore  # noqa: PGH003
                    False,
                )

        # Update the state
        await self.coordinator.async_request_refresh()

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set new target temperature for the circuit.

        This works by modifying the special "override" schedule and assigning
        the schedule to the circuit.

        This is being done to avoid overwriting the normal schedule used
        for HVAC_MODE_AUTO.
        """
        temperature = kwargs.get(ATTR_TEMPERATURE)
        await self.hass.async_add_executor_job(
            self.coordinator.bmr.setSchedule,  # type: ignore  # noqa: PGH003
            int(self._circuit_manual_mode_schedule),
            f"{self._circuit_name} override",
            [{"time": "00:00", "temperature": temperature}],
        )
        if self.hvac_mode not in (HVACMode.HEAT, HVACMode.HEAT_COOL):
            if self._enable_cooling:
                await self.async_set_hvac_mode(HVACMode.HEAT_COOL)
            else:
                await self.async_set_hvac_mode(HVACMode.HEAT)

        # Update the state
        await self.coordinator.async_request_refresh()
