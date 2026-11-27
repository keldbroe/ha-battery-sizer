"""Setup and options: pick the statistics and type in what is missing.

The same four pages are used when setting up and when changing the values
later: where the energy comes from, the prices, the battery, and what it
costs.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant.components.recorder.statistics import async_list_statistic_ids
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_BATTERY_PRICE,
    CONF_BUY_PRICE,
    CONF_CYCLE_LIFE,
    CONF_DISCOUNT_PCT,
    CONF_EFFICIENCY_PCT,
    CONF_EXISTING_KWH,
    CONF_EXPANSION_COST,
    CONF_EXPORT,
    CONF_GRID_LIMIT_KW,
    CONF_HISTORY_YEARS,
    CONF_IMPORT,
    CONF_LIFETIME_YEARS,
    CONF_LOAD,
    CONF_MAX_KWH,
    CONF_POWER_KW,
    CONF_SELL_DEDUCTION,
    CONF_SELL_PRICE,
    CONF_SOLAR,
    CONF_SOURCE,
    CONF_STEP_KWH,
    CONF_SYSTEM_KWH,
    CONF_SYSTEM_PRICE,
    CONF_USABLE_PCT,
    DEFAULTS,
    DOMAIN,
    NAME,
    SOURCE_GRID,
    SOURCE_INVERTER,
)
from .settings import Settings, SettingsError

ENERGY_UNITS = frozenset({"Wh", "kWh", "MWh"})
PRICE_PER = frozenset({"kWh", "MWh"})


async def statistic_choices(hass: Any, kind: str) -> list[selector.SelectOptionDict]:
    """List the recorder's statistics that fit an energy or a price field.

    A plain drop-down is used instead of Home Assistant's statistic picker,
    which some frontends cannot show inside a setup dialog. Energy fields
    list cumulative statistics in Wh, kWh or MWh (sensors and external
    statistics such as ElOverblik's); price fields list statistics per kWh
    or MWh. A statistic id can also be typed in.
    """
    try:
        rows = await async_list_statistic_ids(hass)
    except Exception:
        return []
    choices: list[selector.SelectOptionDict] = []
    for row in rows:
        statistic_id = str(row.get("statistic_id") or "")
        unit = str(
            row.get("statistics_unit_of_measurement")
            or row.get("display_unit_of_measurement")
            or ""
        )
        if not statistic_id:
            continue
        if kind == "energy":
            fits = unit in ENERGY_UNITS and bool(row.get("has_sum"))
        else:
            fits = "/" in unit and unit.rsplit("/", 1)[-1] in PRICE_PER
        if not fits:
            continue
        name = row.get("name")
        label = f"{name} ({statistic_id})" if name else statistic_id
        choices.append({"value": statistic_id, "label": f"{label} · {unit}"})
    return sorted(choices, key=lambda choice: choice["label"].lower())


def _statistic(choices: list[selector.SelectOptionDict]) -> selector.SelectSelector:
    return selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=choices,
            mode=selector.SelectSelectorMode.DROPDOWN,
            custom_value=True,
            sort=False,
        )
    )


def _number(
    minimum: float, maximum: float, step: float, unit: str | None = None
) -> selector.NumberSelector:
    config = selector.NumberSelectorConfig(
        min=minimum,
        max=maximum,
        step=step,
        mode=selector.NumberSelectorMode.BOX,
    )
    if unit is not None:
        config["unit_of_measurement"] = unit
    return selector.NumberSelector(config)


def source_schema() -> vol.Schema:
    """Page 1: where the hourly energy comes from."""
    return vol.Schema(
        {
            vol.Required(CONF_SOURCE): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[SOURCE_INVERTER, SOURCE_GRID],
                    translation_key=CONF_SOURCE,
                    mode=selector.SelectSelectorMode.LIST,
                )
            )
        }
    )


def energy_schema(
    source: str, choices: list[selector.SelectOptionDict] | None = None
) -> vol.Schema:
    """Page 2: the energy statistics for the chosen source."""
    field = _statistic(choices or [])
    if source == SOURCE_INVERTER:
        return vol.Schema(
            {
                vol.Required(CONF_LOAD): field,
                vol.Required(CONF_SOLAR): field,
            }
        )
    return vol.Schema(
        {
            vol.Required(CONF_IMPORT): field,
            vol.Optional(CONF_EXPORT): field,
        }
    )


def prices_schema(choices: list[selector.SelectOptionDict] | None = None) -> vol.Schema:
    """Page 3: buy and sell price statistics, and what is kept back on sale."""
    field = _statistic(choices or [])
    return vol.Schema(
        {
            vol.Required(CONF_BUY_PRICE): field,
            vol.Required(CONF_SELL_PRICE): field,
            vol.Required(CONF_SELL_DEDUCTION): _number(-2, 2, 0.001, "kr/kWh"),
        }
    )


def battery_schema() -> vol.Schema:
    """Page 4: the battery you have (if any) and the inverter."""
    return vol.Schema(
        {
            vol.Required(CONF_EXISTING_KWH): _number(0, 500, 0.1, "kWh"),
            vol.Required(CONF_POWER_KW): _number(0.5, 100, 0.1, "kW"),
            vol.Required(CONF_USABLE_PCT): _number(50, 100, 1, "%"),
            vol.Required(CONF_EFFICIENCY_PCT): _number(50, 100, 1, "%"),
            vol.Required(CONF_GRID_LIMIT_KW): _number(0, 200, 0.1, "kW"),
        }
    )


def costs_schema() -> vol.Schema:
    """Page 5: what the battery costs, how long it lasts, what to try."""
    return vol.Schema(
        {
            vol.Required(CONF_BATTERY_PRICE): _number(0, 50_000, 1, "kr/kWh"),
            vol.Required(CONF_SYSTEM_PRICE): _number(0, 2_000_000, 1, "kr"),
            vol.Required(CONF_SYSTEM_KWH): _number(0, 500, 0.1, "kWh"),
            vol.Required(CONF_EXPANSION_COST): _number(0, 500_000, 1, "kr"),
            vol.Required(CONF_LIFETIME_YEARS): _number(1, 40, 1, "år"),
            vol.Required(CONF_CYCLE_LIFE): _number(100, 50_000, 100),
            vol.Required(CONF_DISCOUNT_PCT): _number(-5, 20, 0.1, "%"),
            vol.Required(CONF_MAX_KWH): _number(1, 500, 0.5, "kWh"),
            vol.Required(CONF_STEP_KWH): _number(0.5, 100, 0.5, "kWh"),
            vol.Required(CONF_HISTORY_YEARS): _number(0.25, 10, 0.25, "år"),
        }
    )


class _Pages:
    """The shared pages; ``_values`` collects what has been entered."""

    _values: dict[str, Any]

    def _form(self, step_id: str, schema: vol.Schema, errors: dict[str, str]):
        suggested = {**DEFAULTS, **self._values}
        return self.async_show_form(  # type: ignore[attr-defined]
            step_id=step_id,
            data_schema=self.add_suggested_values_to_schema(  # type: ignore[attr-defined]
                schema, suggested
            ),
            errors=errors,
        )

    async def async_step_source(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose the inverter (load and solar) or the grid meter."""
        if user_input is not None:
            self._values.update(user_input)
            return await self.async_step_energy()
        return self._form("source", source_schema(), {})

    async def async_step_energy(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Pick the energy statistics."""
        source = str(self._values.get(CONF_SOURCE) or SOURCE_GRID)
        if user_input is not None:
            for key in (CONF_IMPORT, CONF_EXPORT, CONF_LOAD, CONF_SOLAR):
                self._values.pop(key, None)
            self._values.update(user_input)
            return await self.async_step_prices()
        choices = await statistic_choices(self.hass, "energy")  # type: ignore[attr-defined]
        return self._form("energy", energy_schema(source, choices), {})

    async def async_step_prices(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Pick the price statistics."""
        if user_input is not None:
            self._values.update(user_input)
            return await self.async_step_battery()
        choices = await statistic_choices(self.hass, "price")  # type: ignore[attr-defined]
        return self._form("prices", prices_schema(choices), {})

    async def async_step_battery(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Type in the battery and inverter."""
        errors: dict[str, str] = {}
        if user_input is not None:
            self._values.update(user_input)
            try:
                Settings.from_mapping(self._values).battery()
            except SettingsError as err:
                errors["base"] = err.key
            else:
                return await self.async_step_costs()
        return self._form("battery", battery_schema(), errors)

    async def async_step_costs(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Type in prices and lifetime, then save."""
        errors: dict[str, str] = {}
        if user_input is not None:
            self._values.update(user_input)
            try:
                Settings.from_mapping(self._values).validate()
            except SettingsError as err:
                errors["base"] = err.key
            else:
                return self._finish()
        return self._form("costs", costs_schema(), errors)

    def _finish(self) -> ConfigFlowResult:
        raise NotImplementedError


class BatterySizerConfigFlow(_Pages, ConfigFlow, domain=DOMAIN):
    """Set up Batteri-beregner."""

    VERSION = 1

    def __init__(self) -> None:
        """Start with the default values."""
        self._values = {}

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> BatterySizerOptionsFlow:
        """Change the values later."""
        return BatterySizerOptionsFlow()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Start with the source of the energy data."""
        return await self.async_step_source(user_input)

    def _finish(self) -> ConfigFlowResult:
        return self.async_create_entry(title=NAME, data={}, options=dict(self._values))


class BatterySizerOptionsFlow(_Pages, OptionsFlow):
    """Change any value; the calculation runs again on save."""

    def __init__(self) -> None:
        """Values are loaded from the entry when the flow starts."""
        self._values = {}

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Start from the entry's current values."""
        current: Mapping[str, Any] = {
            **self.config_entry.data,
            **self.config_entry.options,
        }
        self._values = dict(current)
        return await self.async_step_source()

    def _finish(self) -> ConfigFlowResult:
        return self.async_create_entry(title="", data=dict(self._values))
