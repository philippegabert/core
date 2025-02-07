"""Support for WaterHeater devices of (EMEA/EU) Honeywell TCC systems."""
from __future__ import annotations

import logging

from evohomeasync2.schema.const import (
    SZ_ACTIVE_FAULTS,
    SZ_DHW_ID,
    SZ_OFF,
    SZ_ON,
    SZ_STATE_STATUS,
    SZ_TEMPERATURE_STATUS,
)

from homeassistant.components.water_heater import (
    WaterHeaterEntity,
    WaterHeaterEntityFeature,
)
from homeassistant.const import (
    PRECISION_TENTHS,
    PRECISION_WHOLE,
    STATE_OFF,
    STATE_ON,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
import homeassistant.util.dt as dt_util

from . import EvoChild
from .const import DOMAIN, EVO_FOLLOW, EVO_PERMOVER

_LOGGER = logging.getLogger(__name__)

STATE_AUTO = "auto"

HA_STATE_TO_EVO = {STATE_AUTO: "", STATE_ON: SZ_ON, STATE_OFF: SZ_OFF}
EVO_STATE_TO_HA = {v: k for k, v in HA_STATE_TO_EVO.items() if k != ""}

STATE_ATTRS_DHW = [SZ_DHW_ID, SZ_ACTIVE_FAULTS, SZ_STATE_STATUS, SZ_TEMPERATURE_STATUS]


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Create a DHW controller."""
    if discovery_info is None:
        return

    broker = hass.data[DOMAIN]["broker"]

    _LOGGER.debug(
        "Adding: DhwController (%s), id=%s",
        broker.tcs.hotwater.TYPE,
        broker.tcs.hotwater.dhwId,
    )

    new_entity = EvoDHW(broker, broker.tcs.hotwater)

    async_add_entities([new_entity], update_before_add=True)


class EvoDHW(EvoChild, WaterHeaterEntity):
    """Base for a Honeywell TCC DHW controller (aka boiler)."""

    _attr_name = "DHW controller"
    _attr_icon = "mdi:thermometer-lines"
    _attr_operation_list = list(HA_STATE_TO_EVO)
    _attr_temperature_unit = UnitOfTemperature.CELSIUS

    def __init__(self, evo_broker, evo_device) -> None:
        """Initialize an evohome DHW controller."""
        super().__init__(evo_broker, evo_device)

        self._attr_unique_id = evo_device.dhwId
        self._evo_id = evo_device.dhwId

        self._attr_precision = (
            PRECISION_TENTHS if evo_broker.client_v1 else PRECISION_WHOLE
        )
        self._attr_supported_features = (
            WaterHeaterEntityFeature.AWAY_MODE | WaterHeaterEntityFeature.OPERATION_MODE
        )

    @property
    def current_operation(self) -> str:
        """Return the current operating mode (Auto, On, or Off)."""
        if self._evo_device.mode == EVO_FOLLOW:
            return STATE_AUTO
        return EVO_STATE_TO_HA[self._evo_device.state]

    @property
    def is_away_mode_on(self):
        """Return True if away mode is on."""
        is_off = EVO_STATE_TO_HA[self._evo_device.state] == STATE_OFF
        is_permanent = self._evo_device.mode == EVO_PERMOVER
        return is_off and is_permanent

    async def async_set_operation_mode(self, operation_mode: str) -> None:
        """Set new operation mode for a DHW controller.

        Except for Auto, the mode is only until the next SetPoint.
        """
        if operation_mode == STATE_AUTO:
            await self._evo_broker.call_client_api(self._evo_device.reset_mode())
        else:
            await self._update_schedule()
            until = dt_util.parse_datetime(self.setpoints.get("next_sp_from", ""))
            until = dt_util.as_utc(until) if until else None

            if operation_mode == STATE_ON:
                await self._evo_broker.call_client_api(
                    self._evo_device.set_on(until=until)
                )
            else:  # STATE_OFF
                await self._evo_broker.call_client_api(
                    self._evo_device.set_off(until=until)
                )

    async def async_turn_away_mode_on(self) -> None:
        """Turn away mode on."""
        await self._evo_broker.call_client_api(self._evo_device.set_off())

    async def async_turn_away_mode_off(self) -> None:
        """Turn away mode off."""
        await self._evo_broker.call_client_api(self._evo_device.reset_mode())

    async def async_turn_on(self):
        """Turn on."""
        await self._evo_broker.call_client_api(self._evo_device.set_on())

    async def async_turn_off(self):
        """Turn off."""
        await self._evo_broker.call_client_api(self._evo_device.set_off())

    async def async_update(self) -> None:
        """Get the latest state data for a DHW controller."""
        await super().async_update()

        for attr in STATE_ATTRS_DHW:
            self._device_state_attrs[attr] = getattr(self._evo_device, attr)
