"""The BMR HC64 integration.

BMR HC64 is controller of a heating regulators for residential buildings.

URL: https://www.bmr.cz/
"""

from __future__ import annotations

import logging

from pybmr import Bmr  # type: ignore  # noqa: PGH003

from homeassistant.const import (
    CONF_PASSWORD,
    CONF_TIMEOUT,
    CONF_URL,
    CONF_USERNAME,
    Platform,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import (
    ConfigEntryAuthFailed,
    ConfigEntryError,
    ConfigEntryNotReady,
)
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .config_flow import BmrConfigEntry
from .const import DOMAIN
from .coordinator import BmrUpdateCoordinator

_PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.CLIMATE,
    Platform.SENSOR,
    Platform.SWITCH,
]

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.empty_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the BMR HC64 integration."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: BmrConfigEntry) -> bool:
    """Set up BMR HC64 from a config entry."""

    bmr = Bmr(
        entry.data[CONF_URL],
        entry.data[CONF_USERNAME],
        entry.data[CONF_PASSWORD],
        entry.data[CONF_TIMEOUT],
    )

    try:
        await hass.async_add_executor_job(bmr.getUniqueId)
    except TimeoutError as e:
        raise ConfigEntryNotReady(
            f"Timed out while connecting to {entry.data[CONF_URL]}"
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
            if dt_now.date() == dt_ago.date() and dt_now.date() == dt_ahead.date():
                # We aren't within 15 minutes of midnight
                raise ConfigEntryAuthFailed(e.args[0]) from e
        raise ConfigEntryError("Unexpected error") from e

    coordinator = BmrUpdateCoordinator(hass, entry, bmr)

    # Fetch initial data so we have data when entities subscribe
    #
    # If the refresh fails, async_config_entry_first_refresh will
    # raise ConfigEntryNotReady and setup will try again later
    #
    # If you do not want to retry setup on failure, use
    # coordinator.async_refresh() instead
    #
    await coordinator.async_config_entry_first_refresh()

    # Store the coordinator in hass.data
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    await hass.config_entries.async_forward_entry_setups(entry, _PLATFORMS)

    return True


async def async_reload_entry(hass: HomeAssistant, entry: BmrConfigEntry) -> None:
    """Handle an options update."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: BmrConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, _PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
