# Batteri-beregner (DK)

Home Assistant integration that recommends a home battery size from your own hourly data and Danish electricity prices. Everything comes from sensors and long-term statistics already in Home Assistant. No external service is called.

> **Status:** the integration (setup, calculation and sensors) works and is tested. A panel with charts and the add-on come next.

## Install with HACS

1. In HACS, choose **Custom repositories** and add `https://github.com/keldbroe/ha-battery-sizer` as an integration.
2. Download **Batteri-beregner (DK)** and restart Home Assistant.
3. Go to **Settings → Devices & services → Add integration → Batteri-beregner (DK)**.

## Set it up

Setup has five short pages. Everything can be changed later under **Configure**.

1. **Data source.**
   - **Inverter:** the home's load and the solar production. Use this if you already have a battery, because the grid meter shows what the existing battery does.
   - **Grid meter:** bought and sold, for example ElOverblik.
2. **Energy statistics.** Pick them in the statistics picker. External statistics such as `eloverblik_dk:energy_…` can be picked too.
3. **Prices.**
   - **Buy price:** with everything included, for example Energi Data Service.
   - **Sell price:** the spot price, for example Nord Pool.
   - **Deducted on sale:** what your supplier and the grid keep per kWh sold.
4. **Battery and inverter.**
   - **Existing battery:** 0 if none. Otherwise the calculation is about expanding it.
   - **Inverter power**, **usable capacity**, **round-trip efficiency** and the **main fuse limit**.
5. **Prices and lifetime.**
   - **Battery price** per kWh.
   - **System price incl. battery** and the battery size it includes.
   - **Expansion cost.**
   - **Lifetime** in years and cycles, and an **interest rate**.
   - Which **sizes** to try, and how much **history** to use.

The calculation runs in the background after setup, once a day, after every change, and when you press **Calculate again** or call the `battery_sizer.calculate` action. It needs at least 30 days that have both energy and prices.

## Sensors

For each strategy (own consumption, solar and sale, trading):

| Sensor | Shows |
| --- | --- |
| Recommended battery / recommended expansion | kWh. 0 when no size pays off. The `sizes` attribute lists every size tried with savings, investment, payback, net present value and cycles, for your own charts. |
| Savings per year | kr per year for the recommended size, or the extra savings from the expansion |
| Payback time | Years |
| Net present value | kr over the lifetime |

**Last calculation** (diagnostic) shows when the calculation ran, how many hours it used, and the error if a run failed.

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

## Prices you type in

| Field | Used for |
| --- | --- |
| **Battery price** (kr per kWh) | Every extra kWh, in a new system or an expansion |
| **System price incl. battery** (kr) and **its battery size** (kWh) | A new system. What it costs besides its battery is the system price minus that battery at the battery price. Other sizes cost that plus their capacity at the battery price. |
| **Expansion cost** (kr) | A one-off cost for fitting extra modules to an existing battery |
| **Existing battery** (kWh) | 0 for no battery. Otherwise the calculation is about an *expansion*. |

## New system or expansion

- **New system:** each size's investment is compared with its savings against no battery.
- **Expansion of an existing battery:** the existing battery is already paid for. Only the *extra* savings from the larger battery count, against the price of the extra modules and the expansion cost. The expansion lasts as long as the larger battery, by years or cycles, whichever ends first.

  Use the inverter's home load and solar production as data. The grid meters already show the effect of the existing battery, which would then be counted twice.

## Economics

- **Inputs:** the prices above, lifetime in years and cycles (whichever comes first), and a discount rate.
- **Outputs per size:** investment, annual savings, cycles per year, payback time and net present value.
- **Recommendation:** the size, or the expansion, with the highest net present value. Nothing is recommended if nothing pays off.

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
