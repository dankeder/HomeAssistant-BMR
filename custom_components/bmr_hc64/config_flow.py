"""Config flow for the BMR HC64 integration."""

from __future__ import annotations

from collections.abc import Mapping
import logging
from typing import Any

from pybmr import Bmr  # type: ignore  # noqa: PGH003
import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    ConfigSubentryFlow,
    SubentryFlowResult,
)
from homeassistant.const import (
    CONF_NAME,
    CONF_PASSWORD,
    CONF_TIMEOUT,
    CONF_URL,
    CONF_USERNAME,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.selector import (
    BooleanSelector,  # type: ignore  # noqa: PGH003
    NumberSelector,  # type: ignore  # noqa: PGH003
    NumberSelectorConfig,
    NumberSelectorMode,
    TextSelector,  # type: ignore  # noqa: PGH003
    TextSelectorConfig,
    TextSelectorType,
)

from .const import DOMAIN

type BmrConfigEntry = ConfigEntry[Bmr]

_LOGGER = logging.getLogger(__name__)

DEFAULT_AWAY_TEMPERATURE = 18.0
DEFAULT_MIN_TEMPERATURE = 18.0
DEFAULT_MAX_TEMPERATURE = 24.0
MIN_ALLOWED_TEMPERATURE = 7.0
MAX_ALLOWED_TEMPERATURE = 35.0

CONF_CIRCUITS = "circuits"
CONF_CIRCUIT_NAME = "circuit_name"
CONF_CIRCUIT_ID = "circuit_id"
CONF_AWAY_TEMPERATURE = "away_temperature"
CONF_ENABLE_COOLING = "enable_cooling"
CONF_MIN_TEMPERATURE = "min_temperature"
CONF_MAX_TEMPERATURE = "max_temperature"
CONF_AUTO_MODE_DAILY_SCHEDULES = "auto_mode_daily_schedules"
CONF_AUTO_MODE_DAILY_SCHEDULES_STARTING_DAY = "auto_mode_daily_schedules_starting_day"
CONF_MANUAL_MODE_SCHEDULE = "manual_mode_schedule"


def STEP_USER_DATA_SCHEMA(suggested_values: dict[str, Any] | None = None) -> vol.Schema:
    """Return the schema for the ConfigFlow "user" step.

    The optional parameter `suggested_values` is used to pre-fill the form with previously configured values.
    """
    if suggested_values is None:
        suggested_values = {}
    return vol.Schema(
        {
            vol.Required(
                CONF_NAME,
                description={"suggested_value": suggested_values.get(CONF_NAME)},
            ): TextSelector(),
            vol.Required(
                CONF_URL,
                description={"suggested_value": suggested_values.get(CONF_URL)},
            ): TextSelector(TextSelectorConfig(type=TextSelectorType.URL)),
            vol.Required(
                CONF_USERNAME,
                description={"suggested_value": suggested_values.get(CONF_USERNAME)},
            ): TextSelector(),
            vol.Required(CONF_PASSWORD): TextSelector(
                TextSelectorConfig(type=TextSelectorType.PASSWORD)
            ),
            vol.Optional(
                CONF_TIMEOUT,
                default=30,
                description={"suggested_value": suggested_values.get(CONF_TIMEOUT)},
            ): NumberSelector(
                NumberSelectorConfig(min=1, step=1, mode=NumberSelectorMode.BOX)
            ),
            vol.Optional(
                CONF_AWAY_TEMPERATURE,
                default=DEFAULT_AWAY_TEMPERATURE,
                description={
                    "suggested_value": suggested_values.get(CONF_AWAY_TEMPERATURE)
                },
            ): NumberSelector(
                NumberSelectorConfig(
                    min=MIN_ALLOWED_TEMPERATURE,
                    max=MAX_ALLOWED_TEMPERATURE,
                    mode=NumberSelectorMode.BOX,
                ),
            ),
            vol.Optional(
                CONF_ENABLE_COOLING,
                default=False,
                description={
                    "suggested_value": suggested_values.get(CONF_ENABLE_COOLING)
                },
            ): BooleanSelector(),
        }
    )


def CIRCUIT_SCHEMA(suggested_values: dict[str, Any] | None = None) -> vol.Schema:
    """Return the schema for the ConfigFlow "add_circuit" step.

    The optional parameter `suggested_values` is used to pre-fill the form with previously configured values.
    """
    if suggested_values is None:
        suggested_values = {}
    return vol.Schema(
        {
            vol.Required(
                CONF_CIRCUIT_NAME,
                description={
                    "suggested_value": suggested_values.get(CONF_CIRCUIT_NAME)
                },
            ): TextSelector(),
            vol.Required(
                CONF_CIRCUIT_ID,
                description={"suggested_value": suggested_values.get(CONF_CIRCUIT_ID)},
            ): TextSelector(TextSelectorConfig(type=TextSelectorType.NUMBER)),
            vol.Optional(
                CONF_MIN_TEMPERATURE,
                default=DEFAULT_MIN_TEMPERATURE,
                description={
                    "suggested_value": suggested_values.get(CONF_MIN_TEMPERATURE)
                },
            ): NumberSelector(
                NumberSelectorConfig(
                    min=MIN_ALLOWED_TEMPERATURE,
                    max=MAX_ALLOWED_TEMPERATURE,
                    mode=NumberSelectorMode.BOX,
                )
            ),
            vol.Optional(
                CONF_MAX_TEMPERATURE,
                default=DEFAULT_MAX_TEMPERATURE,
                description={
                    "suggested_value": suggested_values.get(CONF_MAX_TEMPERATURE)
                },
            ): NumberSelector(
                NumberSelectorConfig(
                    min=MIN_ALLOWED_TEMPERATURE,
                    max=MAX_ALLOWED_TEMPERATURE,
                    mode=NumberSelectorMode.BOX,
                )
            ),
            # Specify which BMR HC64 schedules will be used when in
            # HVACMode.AUTO. It's possible to specify multiple schedules (up to
            # 21); if multiple schedules are specified they are used in a
            # round-robin fashion (one every day, switching to the next one at 00:00).
            #
            # The schedule that the controller will start with is specified by
            # CONF_STARTING_DAY.
            vol.Required(
                CONF_AUTO_MODE_DAILY_SCHEDULES,
                description={
                    "suggested_value": suggested_values.get(
                        CONF_AUTO_MODE_DAILY_SCHEDULES
                    )
                },
            ): TextSelector(
                TextSelectorConfig(type=TextSelectorType.NUMBER, multiple=True),
            ),
            # Allows specifying which of the the schedules defined in
            # CONF_DAILY_SCHEDULES will be picked as the first schedule in
            # HVACMode.AUTO mode. Defaults to the first schedule.
            vol.Optional(
                CONF_AUTO_MODE_DAILY_SCHEDULES_STARTING_DAY,
                default=1,
                description={
                    "suggested_value": suggested_values.get(
                        CONF_AUTO_MODE_DAILY_SCHEDULES_STARTING_DAY
                    )
                },
            ): NumberSelector(
                NumberSelectorConfig(min=1, max=21, mode=NumberSelectorMode.BOX)
            ),
            vol.Required(
                CONF_MANUAL_MODE_SCHEDULE,
                description={
                    "suggested_value": suggested_values.get(CONF_MANUAL_MODE_SCHEDULE)
                },
            ): NumberSelector(
                NumberSelectorConfig(
                    min=0,
                    max=63,
                    mode=NumberSelectorMode.BOX,
                )
            ),
        }
    )


def check_connection(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, str]:
    """Validate the user input allows us to connect.

    Data has the keys from STEP_USER_DATA_SCHEMA with values provided by the user.
    """
    bmr = Bmr(
        data[CONF_URL], data[CONF_USERNAME], data[CONF_PASSWORD], data[CONF_TIMEOUT]
    )

    try:
        unique_id = bmr.getUniqueId()
    except TimeoutError as e:
        raise CannotConnect from e
    except Exception as e:
        if e.args[0] == "Authentication failed, check username/password":
            raise InvalidAuth(e) from e
        raise
    else:
        # Return info that you want to store in the config entry.
        return {
            "unique_id": unique_id,
        }


class BmrConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for BMR HC64."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                info = await self.hass.async_add_executor_job(
                    check_connection, self.hass, user_input
                )
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                title = user_input.pop(CONF_NAME)
                await self.async_set_unique_id(info["unique_id"])
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=title, data=user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA(),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle reconfiguration of the controller."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                info = await self.hass.async_add_executor_job(
                    check_connection, self.hass, user_input
                )
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                title = user_input.pop(CONF_NAME)
                await self.async_set_unique_id(info["unique_id"])
                self._abort_if_unique_id_mismatch()
                return self.async_update_reload_and_abort(
                    entry,
                    title=title,
                    data_updates=user_input,
                )

        # Pre-fill values from the existing configuration
        suggested_values: dict[str, Any] = {
            CONF_NAME: entry.title,
            CONF_URL: entry.data[CONF_URL],
            CONF_USERNAME: entry.data[CONF_USERNAME],
            CONF_TIMEOUT: entry.data[CONF_TIMEOUT],
            CONF_AWAY_TEMPERATURE: entry.data[CONF_AWAY_TEMPERATURE],
            CONF_ENABLE_COOLING: entry.data[CONF_ENABLE_COOLING],
        }

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=STEP_USER_DATA_SCHEMA(suggested_values),
            errors=errors,
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Perform reauth upon authentication error."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show a dialog that informs user that reauth is required."""
        if user_input is None:
            return self.async_show_form(
                step_id="reauth_confirm", data_schema=vol.Schema({})
            )
        return await self.async_step_reconfigure()

    @classmethod
    @callback
    def async_get_supported_subentry_types(
        cls, config_entry: BmrConfigEntry
    ) -> dict[str, type[ConfigSubentryFlow]]:
        """Return supported ConfigSubentryFlow handlers."""
        return {
            CONF_CIRCUITS: CircuitSubentryFlowHandler,
        }


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""


class CircuitSubentryFlowHandler(ConfigSubentryFlow):
    """Handle the subentrry flow for configuring a heating circuit."""

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Handle options flow."""
        return await self.async_step_add_circuit()

    async def async_step_add_circuit(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Handle options flow."""
        if user_input is not None:
            return self.async_create_entry(
                title=user_input[CONF_CIRCUIT_NAME],
                data=user_input,
                unique_id=f"circuit-{user_input[CONF_CIRCUIT_ID]}",
            )

        return self.async_show_form(step_id="add_circuit", data_schema=CIRCUIT_SCHEMA())

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Handle options flow."""
        return await self.async_step_reconfigure_circuit()

    async def async_step_reconfigure_circuit(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Handle reconfiguration of the circuit."""
        entry = self._get_reconfigure_entry()
        subentry = self._get_reconfigure_subentry()
        errors: dict[str, str] = {}
        if user_input is not None:
            return self.async_update_and_abort(
                entry,
                subentry,
                title=user_input[CONF_CIRCUIT_NAME],
                data_updates=user_input,
                unique_id=f"circuit-{user_input[CONF_CIRCUIT_ID]}",
            )

        # Pre-fill values from the existing configuration
        suggested_values = {
            CONF_CIRCUIT_ID: subentry.data[CONF_CIRCUIT_ID],
            CONF_CIRCUIT_NAME: subentry.data[CONF_CIRCUIT_NAME],
            CONF_MIN_TEMPERATURE: subentry.data[CONF_MIN_TEMPERATURE],
            CONF_MAX_TEMPERATURE: subentry.data[CONF_MAX_TEMPERATURE],
            CONF_AUTO_MODE_DAILY_SCHEDULES: subentry.data[
                CONF_AUTO_MODE_DAILY_SCHEDULES
            ],
            CONF_AUTO_MODE_DAILY_SCHEDULES_STARTING_DAY: subentry.data[
                CONF_AUTO_MODE_DAILY_SCHEDULES_STARTING_DAY
            ],
            CONF_MANUAL_MODE_SCHEDULE: subentry.data[CONF_MANUAL_MODE_SCHEDULE],
        }

        return self.async_show_form(
            step_id="reconfigure_circuit",
            data_schema=CIRCUIT_SCHEMA(suggested_values),
            errors=errors,
        )
