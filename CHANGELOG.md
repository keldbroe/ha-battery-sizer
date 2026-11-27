# Changelog

## 0.3.0

### Added

- **Change the assumptions in the panel.** A new *Forudsætninger* (Assumptions) section lists the battery, inverter, prices, lifetime, interest and sizes to try. **Save and calculate** stores them and calculates again; the last result stays on screen until the new one is ready.
  - Labels, help texts and limits are the same as in the setup, in your language.
  - Values are checked as you type, and decimal commas work.
  - Only an administrator can save; others see the values read-only.
- Websocket commands `battery_sizer/settings` and `battery_sizer/update_settings` (admin only).

## 0.2.0

### Added

- **Panel with charts** in the sidebar (*Batteri-beregner*):
  - a card per strategy with the verdict and the key numbers
  - net present value, savings and payback by size, with the lifetime marked
  - savings per month of a typical year
  - energy through the battery per month (to the home, sold, charged from the grid)
  - a table of every size, and a **Calculate again** button
- Danish and English, follows the Home Assistant theme (light and dark), works on a phone. No external libraries, so it works offline.
- Websocket command `battery_sizer/results` with the full result, including the month-by-month figures.

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
