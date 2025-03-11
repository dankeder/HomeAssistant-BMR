"""Update coordinator for BMR HC64 integration."""

from dataclasses import dataclass
from datetime import timedelta
import logging
from typing import Any

from pybmr import Bmr  # type: ignore  # noqa: PGH003

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_URL
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import (
    ConfigEntryAuthFailed,
    ConfigEntryError,
    ConfigEntryNotReady,
)
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .config_flow import CONF_CIRCUIT_ID, CONF_CIRCUIT_NAME
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# Max difference between two subsequent circuit temperature measurements
MAX_TEMPERATURE_DELTA = 5.0


@dataclass
class CircuitState:
    """State of a BMR HC64 heating circuit."""

    # ID of the circuit (internal to the controller)
    id: int

    # Internal name of the circuit as configured in the BMR HC64 controller
    name: str

    # Friendly name of the circuit, it will be used in Home Assistant UI
    friendly_name: str

    # Whether the circuit is enabled
    enabled: bool | None

    # User-defined target temperature offset of the circuit
    user_offset: float | None

    # Maxiumum allowed target temperature offset of the circuit
    max_offset: float | None

    # Whether the circuit is in warning state
    warning: bool | None

    # Whether the circuit is heating
    heating: bool | None

    # Whether the circuit is cooling (only for water-based circuits)
    cooling: bool | None

    # Whether the circuit is in low mode (low target temperature, e.g. when people are away)
    low_mode: bool | None

    # Whether the circuit is in "summer" mode (heating is off during the summer)
    summer_mode: bool | None

    # Current temperature of the heating circuit
    temperature: float | None

    # Target temperature of the heating circuit
    target_temperature: float | None

    #  Schedules of the heating circuit
    schedules: dict[str, Any] | None


@dataclass
class BmrControllerState:
    """State of the BMR HC64 controller."""

    circuits: dict[str, CircuitState]
    hdo: bool | None
    unique_id: str | None
    low_mode: dict[str, Any]
    low_mode_assignments: list[bool]
    summer_mode: bool | None
    summer_mode_assignments: list[bool]


class BmrUpdateCoordinator(DataUpdateCoordinator[BmrControllerState]):
    """Class to manage fetching BMR HC64 data from the API."""

    def __init__(
        self, hass: HomeAssistant, config_entry: ConfigEntry[Bmr], bmr: Bmr
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            config_entry=config_entry,
            # Polling interval. Will only be polled if there are subscribers.
            update_interval=timedelta(seconds=60),
            # Set always_update to `False` if the data returned from the
            # api can be compared via `__eq__` to avoid duplicate updates
            # being dispatched to listeners
            always_update=True,
        )
        self.bmr = bmr

    @property
    def device_name(self) -> str:
        """Device name for the controller."""
        assert self.config_entry is not None
        return self.config_entry.title

    async def _async_update_data(self) -> BmrControllerState:
        """Fetch state data of the BMR HC64 controller."""
        assert self.config_entry is not None

        try:
            # Fetch data from the BMR HC64 device
            unique_id = await self.hass.async_add_executor_job(self.bmr.getUniqueId)
            hdo = await self.hass.async_add_executor_job(self.bmr.getHDO)
            low_mode: dict[str, Any] = await self.hass.async_add_executor_job(
                self.bmr.getLowMode
            )
            low_mode_assignments: list[bool] = await self.hass.async_add_executor_job(
                self.bmr.getLowModeAssignments
            )
            summer_mode = await self.hass.async_add_executor_job(self.bmr.getSummerMode)
            summer_mode_assignments: list[
                bool
            ] = await self.hass.async_add_executor_job(
                self.bmr.getSummerModeAssignments
            )

            circuits: dict[str, CircuitState] = {}
            for subentry in self.config_entry.subentries.values():
                # Access configuration data from config_entry
                circuit_id = subentry.data[CONF_CIRCUIT_ID]
                circuit_name = subentry.data[CONF_CIRCUIT_NAME]

                circuit_data: dict[str, Any] = await self.hass.async_add_executor_job(  # type: ignore  # noqa: PGH003
                    self.bmr.getCircuit,  # type: ignore  # noqa: PGH003
                    int(circuit_id),  # type: ignore  # noqa: PGH003
                )  # type: ignore  # noqa: PGH003

                circuit_schedules: dict[
                    str, Any
                ] = await self.hass.async_add_executor_job(  # type: ignore  # noqa: PGH003
                    self.bmr.getCircuitSchedules,  # type: ignore  # noqa: PGH003
                    int(circuit_id),  # type: ignore  # noqa: PGH003
                )

                # Sanity checks of the new circuit state
                previous_circuit_state = (
                    self.data.circuits.get(circuit_id) if self.data else None
                )
                if self.sanity_check_circuit_state(
                    circuit_data, previous_circuit_state
                ):
                    circuits[circuit_id] = CircuitState(
                        id=circuit_data.get("id"),  # type: ignore  # noqa: PGH003
                        name=circuit_data.get("name"),  # type: ignore  # noqa: PGH003
                        friendly_name=circuit_name,  # type: ignore  # noqa: PGH003
                        enabled=circuit_data.get("enabled"),  # type: ignore  # noqa: PGH003
                        user_offset=circuit_data.get("user_offset"),  # type: ignore  # noqa: PGH003
                        max_offset=circuit_data.get("max_offset"),  # type: ignore  # noqa: PGH003
                        warning=circuit_data.get("warning"),  # type: ignore  # noqa: PGH003
                        heating=circuit_data.get("heating"),  # type: ignore  # noqa: PGH003
                        cooling=circuit_data.get("cooling"),  # type: ignore  # noqa: PGH003
                        low_mode=circuit_data.get("low_mode"),  # type: ignore  # noqa: PGH003
                        summer_mode=circuit_data.get("summer_mode"),  # type: ignore  # noqa: PGH003
                        temperature=circuit_data.get("temperature"),  # type: ignore  # noqa: PGH003
                        target_temperature=circuit_data.get("target_temperature"),  # type: ignore  # noqa: PGH003
                        schedules=circuit_schedules,  # type: ignore  # noqa: PGH003
                    )

            return BmrControllerState(
                unique_id=unique_id,
                hdo=hdo,
                low_mode=low_mode,
                low_mode_assignments=low_mode_assignments,
                summer_mode=summer_mode,
                summer_mode_assignments=summer_mode_assignments,
                circuits=circuits,
            )

        except TimeoutError as e:
            raise ConfigEntryNotReady(
                f"Timed out while connecting to {self.config_entry.data[CONF_URL]}"
            ) from e
        except Exception as e:
            if e.args[0] == "Authentication failed, check username/password":
                # Clocks need to be synchronized because the authentication
                # uses the current "day". If it's around midnight and the
                # controller has a different day than Home Assistant because of
                # a clock desync authentication will fail. Let's ignore auth
                # failures that occur within 15 minutes around midnight.
                dt_now = datetime.now()
                dt_ago = dt_now - timedelta(minutes=15)
                dt_ahead = dt_now + timedelta(minutes=15)
                if (dt_now.date() == dt_ago.date() and dt_now.date() == dt_ahead.date()):
                    # We aren't within 15 minutes of midnight
                    raise ConfigEntryAuthFailed(e.args[0]) from e
            raise ConfigEntryError("Unexpected error") from e

    def sanity_check_circuit_state(
        self, circuit_data: dict[str, Any], previous_circuit_state: CircuitState | None
    ) -> bool:
        """Perform sanity checks on the data returned by BMR HC64 controller."""

        # Check if the previous state is available; it is undefined if this is the first time data is fetched
        if previous_circuit_state is None:
            return True

        # Check whether the circuit IDs are the same
        if circuit_data["id"] != previous_circuit_state.id:
            _LOGGER.warning("BMR HC64 sanity check failed: Circuit IDs don't match")
            return False

        # Check if the circuit temperature is defined
        if circuit_data["temperature"] is None:
            _LOGGER.warning(
                "BMR HC64 sanity check failed: Circuit temperature is undefined"
            )
            return False

        # Check if the temperature delta is too big
        if previous_circuit_state.temperature is not None and abs(
            circuit_data["temperature"] - previous_circuit_state.temperature
            >= MAX_TEMPERATURE_DELTA
        ):
            _LOGGER.warning(
                "BMR HC64 sanity check failed: Circuit temperature difference compared to its previous value is too big"
            )
            return False

        return True
