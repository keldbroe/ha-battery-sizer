# Batteri-beregner (DK)

Home Assistant integration that recommends a home battery size from your own hourly data and Danish electricity prices. Everything comes from sensors and long-term statistics already in Home Assistant. No external service is called.

> **Status:** the calculation engine is done and tested. The Home Assistant integration (setup, panel and sensors) and the add-on come next.

## What it calculates

For a range of battery sizes, every hour of your history is simulated, and the size that pays best is recommended. There are three strategies:

| Strategy | The battery charges from | It discharges to |
| --- | --- | --- |
| **Own consumption** | Solar surplus only | The home's own purchases, most expensive hours first |
| **Solar and sale** | Solar surplus only | The home, or sale to the grid, whichever pays more |
| **Trading** | Solar surplus and the grid | The home and sale to the grid |

- **Own consumption** covers the most expensive hours first. In winter, when there is little surplus, the cheap hours are simply bought from the grid.
- **Trading** reflects the Danish asymmetry. Power from the grid costs the full price, with tariffs, taxes and VAT. Power sold earns the spot price minus a small fee and has no VAT. Trading therefore only pays off when the spread is large.

## How the simulation decides

Day-ahead prices for tomorrow are published around 13:00. Every day at 13:00 the simulation plans until the end of the next day and carries out the first 24 hours.

Within that plan, energy is moved from a *source* to a later *sink*, best gain first:
- **Sources:** solar surplus (worth its sell price), the grid (full buy price), and what is already stored.
- **Sinks:** the home's purchases (buy price) and sale (sell price).

Each move is checked against power, usable capacity, round-trip efficiency, the main fuse and battery wear. Wear is the price per kWh divided by the cycle life. It stops the battery from cycling for less than it wears.

A typical year averages each calendar month and adds the twelve, so months that appear more often in the data do not count more.

## Economics

- **Inputs:** price per kWh, fixed cost, lifetime in years and cycles (whichever comes first), and a discount rate.
- **Outputs per size:** investment, annual savings, cycles per year, payback time and net present value.
- **Recommendation:** the size with the highest net present value. No size is recommended if none pays off.

## Data

| What | Typical sensor |
| --- | --- |
| Bought from and sold to the grid | ElOverblik (`eloverblik_dk`) or the inverter |
| Home load and solar production (best when a battery already exists) | The inverter, e.g. Solarman |
| Buy price with everything included | Energi Data Service |
| Spot price for selling | Nord Pool |

## Development

```bash
python3.13 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
ruff check .
ruff format --check .
pytest
```

The engine in `custom_components/battery_sizer/engine/` has no Home Assistant imports. The add-on will use it too.

## License

MIT. See [LICENSE](LICENSE).
