"""Turning price units into kr/kWh."""

import pytest

from custom_components.battery_sizer.units import price_factor


@pytest.mark.parametrize(
    ("unit", "factor"),
    [
        ("DKK/kWh", 1.0),
        ("kr/kWh", 1.0),
        ("dkk/kwh", 1.0),
        ("DKK/MWh", 0.001),
        ("øre/kWh", 0.01),
        ("DKK/Wh", 1000.0),
        ("/kWh", 1.0),
    ],
)
def test_known_units(unit: str, factor: float) -> None:
    assert price_factor(unit) == pytest.approx(factor)


@pytest.mark.parametrize(
    "unit", ["EUR/MWh", "€/kWh", "SEK/kWh", "kWh", "", None, "DKK/h"]
)
def test_unknown_units(unit) -> None:
    assert price_factor(unit) is None
