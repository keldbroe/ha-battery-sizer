"""Units of the statistics: energy is read in kWh, prices turned into kr/kWh."""

from __future__ import annotations

# What one unit of energy in a price's denominator is in kWh.
_ENERGY_KWH = {"wh": 0.001, "kwh": 1.0, "mwh": 1000.0}
# What one unit of currency is in kroner. Other currencies are not converted:
# the result would depend on an exchange rate the history does not have.
_CURRENCY_KR = {"": 1.0, "kr": 1.0, "kr.": 1.0, "dkk": 1.0, "øre": 0.01, "ore": 0.01}


class UnsupportedPriceUnit(ValueError):
    """A price statistic is in a unit that cannot be turned into kr/kWh."""

    def __init__(self, statistic: str, unit: str | None) -> None:
        """Remember which statistic and unit."""
        super().__init__(f"{statistic}: {unit or 'no unit'}")
        self.statistic = statistic
        self.unit = unit


def price_factor(unit: str | None) -> float | None:
    """Return what to multiply a price by to get kr/kWh, or None if unknown.

    ``DKK/kWh`` and ``kr/kWh`` are kept, ``DKK/MWh`` is divided by 1000,
    ``øre/kWh`` by 100. A price in euro or another currency gives None.
    """
    if not unit or "/" not in unit:
        return None
    currency, energy = (part.strip().lower() for part in unit.rsplit("/", 1))
    per_kwh = _ENERGY_KWH.get(energy)
    in_kr = _CURRENCY_KR.get(currency)
    if per_kwh is None or in_kr is None:
        return None
    return in_kr / per_kwh
