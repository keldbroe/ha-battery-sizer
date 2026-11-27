# Changelog

## 0.1.1

### Fixed

- **Blank setup page.** After choosing a data source, the **Energy statistics** page showed only its title and **Submit**. The frontend did not render Home Assistant's statistic picker inside the setup dialog. The energy and price fields are now drop-downs filled from the recorder:
  - Energy fields list cumulative kWh statistics, ElOverblik's external statistics included.
  - Price fields list statistics per kWh.
  - A statistic id can still be typed in.

### Changed

- The README is in Danish and English, Danish first.

## 0.1.0

- First release:
  - The calculation engine.
  - Setup and options with typed-in prices.
  - Three strategies: own consumption, solar and sale, and trading.
  - Expansion of an existing battery.
  - Sensors with the recommended size, savings, payback and net present value.
