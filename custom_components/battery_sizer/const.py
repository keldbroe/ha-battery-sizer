"""Constants for Batteri-beregner (DK)."""

from __future__ import annotations

DOMAIN = "battery_sizer"
NAME = "Batteri-beregner (DK)"
VERSION = "0.1.1"

# Where the hourly energy comes from.
CONF_SOURCE = "source"
SOURCE_GRID = "grid"  # bought from / sold to the grid
SOURCE_INVERTER = "inverter"  # the home's load and the solar production
CONF_IMPORT = "import_statistic"
CONF_EXPORT = "export_statistic"
CONF_LOAD = "load_statistic"
CONF_SOLAR = "solar_statistic"

# Prices.
CONF_BUY_PRICE = "buy_price_statistic"
CONF_SELL_PRICE = "sell_price_statistic"
CONF_SELL_DEDUCTION = "sell_deduction"

# The battery and inverter.
CONF_EXISTING_KWH = "existing_kwh"
CONF_POWER_KW = "power_kw"
CONF_USABLE_PCT = "usable_pct"
CONF_EFFICIENCY_PCT = "efficiency_pct"
CONF_GRID_LIMIT_KW = "grid_limit_kw"

# What it costs and how long it lasts.
CONF_BATTERY_PRICE = "battery_price_per_kwh"
CONF_SYSTEM_PRICE = "system_price"
CONF_SYSTEM_KWH = "system_battery_kwh"
CONF_EXPANSION_COST = "expansion_cost"
CONF_LIFETIME_YEARS = "lifetime_years"
CONF_CYCLE_LIFE = "cycle_life"
CONF_DISCOUNT_PCT = "discount_pct"

# Which sizes to try and how much history to use.
CONF_MAX_KWH = "max_kwh"
CONF_STEP_KWH = "step_kwh"
CONF_HISTORY_YEARS = "history_years"

DEFAULTS: dict[str, float] = {
    CONF_SELL_DEDUCTION: 0.05,
    CONF_EXISTING_KWH: 0.0,
    CONF_POWER_KW: 5.0,
    CONF_USABLE_PCT: 90.0,
    CONF_EFFICIENCY_PCT: 90.0,
    CONF_GRID_LIMIT_KW: 0.0,
    CONF_BATTERY_PRICE: 2500.0,
    CONF_SYSTEM_PRICE: 0.0,
    CONF_SYSTEM_KWH: 0.0,
    CONF_EXPANSION_COST: 0.0,
    CONF_LIFETIME_YEARS: 15.0,
    CONF_CYCLE_LIFE: 6000.0,
    CONF_DISCOUNT_PCT: 3.0,
    CONF_MAX_KWH: 30.0,
    CONF_STEP_KWH: 2.5,
    CONF_HISTORY_YEARS: 3.0,
}

SERVICE_CALCULATE = "calculate"
