"""Reading suggestions from the Energy dashboard's settings."""

from custom_components.battery_sizer.suggest import suggestions_from_preferences

PREFERENCES = {
    "energy_sources": [
        {
            "type": "grid",
            "flow_from": [
                {
                    "stat_energy_from": "sensor.grid_in",
                    "entity_energy_price": "sensor.price_total",
                }
            ],
            "flow_to": [
                {
                    "stat_energy_to": "sensor.grid_out",
                    "entity_energy_price": "sensor.spot",
                }
            ],
            "cost_adjustment_day": 0,
        },
        {"type": "solar", "stat_energy_from": "sensor.pv_total"},
    ],
    "device_consumption": [],
}


def test_grid_and_solar_and_prices() -> None:
    assert suggestions_from_preferences(PREFERENCES) == {
        "import_statistic": "sensor.grid_in",
        "export_statistic": "sensor.grid_out",
        "buy_price_statistic": "sensor.price_total",
        "sell_price_statistic": "sensor.spot",
        "solar_statistic": "sensor.pv_total",
        "source": "grid",
    }


def test_a_battery_suggests_the_inverter() -> None:
    preferences = {
        **PREFERENCES,
        "energy_sources": [
            *PREFERENCES["energy_sources"],
            {
                "type": "battery",
                "stat_energy_from": "sensor.bat_out",
                "stat_energy_to": "sensor.bat_in",
            },
        ],
    }
    assert suggestions_from_preferences(preferences)["source"] == "inverter"


def test_nothing_set_up() -> None:
    assert suggestions_from_preferences(None) == {}
    assert suggestions_from_preferences({"energy_sources": []}) == {}


def test_fixed_prices_are_not_statistics() -> None:
    preferences = {
        "energy_sources": [
            {
                "type": "grid",
                "flow_from": [
                    {
                        "stat_energy_from": "sensor.grid_in",
                        "entity_energy_price": None,
                        "number_energy_price": 2.5,
                    }
                ],
                "flow_to": [],
            }
        ]
    }
    assert suggestions_from_preferences(preferences) == {
        "import_statistic": "sensor.grid_in",
        "source": "grid",
    }
