# Changelog

## 0.1.2

### Changed

- **No more "Unknown" when nothing pays off.** The recommended size (or expansion) still shows 0 kWh, but savings, payback and net present value now show the numbers for the closest option tried (the one with the highest net present value). Its size is in the `candidate_kwh` attribute.
- Payback is shown even when it is longer than the battery's lifetime. The payback sensor's `within_lifetime` attribute says whether it pays back in time.

### Added

- A **verdict** sensor per strategy: *Pays off*, *Does not pay off* or *No gain*.

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
