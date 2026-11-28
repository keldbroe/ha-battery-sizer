// Batteri-beregner (DK): sidebar panel with charts.
// Plain web component, no libraries: Home Assistant may run offline.

const STRATEGIES = ["self_consumption", "solar_trading", "grid_trading"];
const COLORS = {
  self_consumption: "#2e86de",
  solar_trading: "#e5a00d",
  grid_trading: "#27ae60",
};
const VERDICT_COLORS = {
  pays_off: "var(--success-color, #43a047)",
  does_not_pay_off: "var(--error-color, #db4437)",
  no_gain: "var(--disabled-text-color, #9e9e9e)",
};

const TEXT = {
  da: {
    title: "Batteri-beregner",
    calculate: "Beregn igen",
    calculating: "Beregner …",
    loading: "Henter resultat …",
    none: "Batteri-beregner er ikke sat op. Tilføj integrationen under Indstillinger → Enheder og tjenester.",
    waiting: "Beregningen er ikke færdig endnu. Den tager typisk under et minut efter start.",
    failed: "Seneste beregning fejlede",
    period: "Data",
    hours: "timer",
    calculated: "Beregnet",
    existing: "Nuværende batteri",
    strategies: {
      self_consumption: "Eget forbrug",
      solar_trading: "Sol og salg",
      grid_trading: "Handel",
    },
    verdicts: {
      pays_off: "Betaler sig",
      does_not_pay_off: "Betaler sig ikke",
      no_gain: "Ingen gevinst",
    },
    recommended: "Anbefalet batteri",
    recommendedExpansion: "Anbefalet udvidelse",
    closest: "Bedste bud",
    savings: "Besparelse pr. år",
    extraSavings: "Ekstra besparelse pr. år",
    payback: "Tilbagebetalingstid",
    npv: "Nutidsværdi",
    investment: "Investering",
    cycles: "Cyklusser pr. år",
    years: "år",
    beyondLifetime: "længere end levetiden",
    bySize: "Efter batteristørrelse",
    byExpansion: "Efter udvidelse",
    monthlySavings: "Besparelse pr. måned (typisk år)",
    monthlyExtra: "Ekstra besparelse pr. måned (typisk år)",
    energy: "Energi gennem batteriet pr. måned",
    delivered: "Leveret til hjemmet",
    sold: "Solgt fra batteriet",
    fromGrid: "Ladet fra nettet",
    lifetime: "Levetid",
    table: "Alle størrelser",
    size: "Størrelse",
    added: "Udvidelse",
    noData: "Ingen data",
    months: ["jan", "feb", "mar", "apr", "maj", "jun", "jul", "aug", "sep", "okt", "nov", "dec"],
    note: "Tallene for en størrelse, der ikke betaler sig, viser hvor langt den er fra at betale sig.",
    assumptions: "Forudsætninger",
    save: "Gem og beregn",
    saving: "Gemmer …",
    undo: "Fortryd",
    recalculating: "Beregner med de nye værdier …",
    adminOnly: "Kun en administrator kan ændre værdierne.",
    outOfRange: "Skal være mellem {min} og {max}",
    notNumber: "Skriv et tal",
    changed: "ændret",
    moreInfo: "Forklaring",
    unusedExpansion: "Bruges ikke, når du har et batteri (udvidelse).",
    unusedNew: "Bruges kun, når du har et batteri (udvidelse).",
  },
  en: {
    title: "Battery sizer",
    calculate: "Calculate again",
    calculating: "Calculating …",
    loading: "Loading the result …",
    none: "Battery sizer is not set up. Add the integration under Settings → Devices & services.",
    waiting: "The calculation has not finished yet. It usually takes less than a minute after start.",
    failed: "The last calculation failed",
    period: "Data",
    hours: "hours",
    calculated: "Calculated",
    existing: "Current battery",
    strategies: {
      self_consumption: "Own consumption",
      solar_trading: "Solar and sale",
      grid_trading: "Trading",
    },
    verdicts: {
      pays_off: "Pays off",
      does_not_pay_off: "Does not pay off",
      no_gain: "No gain",
    },
    recommended: "Recommended battery",
    recommendedExpansion: "Recommended expansion",
    closest: "Closest option",
    savings: "Savings per year",
    extraSavings: "Extra savings per year",
    payback: "Payback time",
    npv: "Net present value",
    investment: "Investment",
    cycles: "Cycles per year",
    years: "years",
    beyondLifetime: "longer than the lifetime",
    bySize: "By battery size",
    byExpansion: "By expansion",
    monthlySavings: "Savings per month (typical year)",
    monthlyExtra: "Extra savings per month (typical year)",
    energy: "Energy through the battery per month",
    delivered: "Delivered to the home",
    sold: "Sold from the battery",
    fromGrid: "Charged from the grid",
    lifetime: "Lifetime",
    table: "All sizes",
    size: "Size",
    added: "Expansion",
    noData: "No data",
    months: ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
    note: "For a size that does not pay off, the numbers show how far it is from paying off.",
    assumptions: "Assumptions",
    save: "Save and calculate",
    saving: "Saving …",
    undo: "Undo",
    recalculating: "Calculating with the new values …",
    adminOnly: "Only an administrator can change the values.",
    outOfRange: "Must be between {min} and {max}",
    notNumber: "Enter a number",
    changed: "changed",
    moreInfo: "Explanation",
    unusedExpansion: "Not used when you have a battery (expansion).",
    unusedNew: "Only used when you have a battery (expansion).",
  },
};

const METRICS = ["net_present_value", "annual_savings", "payback_years"];

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[c]);
}

function niceStep(range, target) {
  const raw = range / Math.max(1, target);
  const power = Math.pow(10, Math.floor(Math.log10(raw)));
  for (const factor of [1, 2, 2.5, 5, 10]) {
    if (raw <= factor * power) return factor * power;
  }
  return 10 * power;
}

function ticks(min, max, target = 5) {
  if (min === max) {
    const pad = Math.abs(min) || 1;
    min -= pad;
    max += pad;
  }
  const step = niceStep(max - min, target);
  const start = Math.floor(min / step) * step;
  const end = Math.ceil(max / step) * step;
  const out = [];
  for (let v = start; v <= end + step / 1e6; v += step) out.push(Math.round(v / step) * step);
  return out;
}

class BatterySizerPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._data = null;
    this._entryIndex = 0;
    this._metric = "net_present_value";
    this._strategy = null;
    this._busy = false;
    this._loading = false;
    this._statusSeen = {};
    this._settings = null;
    this._draft = {};
    this._settingsOpen = false;
    this._saving = false;
    this._saveError = null;
    this._pendingSince = undefined;
    this._openHelp = new Set();
  }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    if (first) {
      this._fetch();
      return;
    }
    // Fetch again when a calculation has finished.
    const entries = this._data?.entries || [];
    for (const entry of entries) {
      const id = entry.status_entity;
      if (!id) continue;
      const state = hass.states[id];
      const stamp = state ? `${state.state}|${state.last_updated}` : "";
      if (this._statusSeen[id] !== undefined && this._statusSeen[id] !== stamp) {
        this._fetch();
      }
      this._statusSeen[id] = stamp;
    }
    this._updateMenuButton();
  }

  get hass() {
    return this._hass;
  }

  set narrow(narrow) {
    this._narrow = narrow;
    this._updateMenuButton();
  }

  set panel(panel) {
    this._panel = panel;
  }

  connectedCallback() {
    this._render();
    // Charts are drawn at their real width, so text keeps its size on a phone.
    this._resize = new ResizeObserver(() => {
      const width = this._contentWidth();
      if (width && Math.abs(width - (this._width || 0)) > 24) {
        this._width = width;
        this._render();
      }
    });
    this._resize.observe(this);
  }

  disconnectedCallback() {
    this._resize?.disconnect();
  }

  _contentWidth() {
    const width = this.clientWidth || window.innerWidth || 0;
    // Page padding plus card padding and border.
    const pad = width <= 600 ? 24 : 32;
    return Math.min(1200, width) - pad - 34;
  }

  get _chartWidth() {
    return Math.max(280, Math.round(this._width || this._contentWidth() || 720));
  }

  get _compact() {
    return this._chartWidth < 520;
  }

  get _t() {
    const language = (this._hass?.locale?.language || this._hass?.language || "en").toLowerCase();
    return language.startsWith("da") || language.startsWith("nb") || language.startsWith("no")
      ? TEXT.da
      : TEXT.en;
  }

  get _locale() {
    return this._hass?.locale?.language || this._hass?.language || "da";
  }

  _number(value, digits = 0) {
    if (value === null || value === undefined || Number.isNaN(value)) return "–";
    return new Intl.NumberFormat(this._locale, {
      minimumFractionDigits: digits,
      maximumFractionDigits: digits,
    }).format(value);
  }

  _kr(value) {
    return value === null || value === undefined ? "–" : `${this._number(value)} kr`;
  }

  _kwh(value) {
    return value === null || value === undefined ? "–" : `${this._number(value, 1)} kWh`;
  }

  async _fetch() {
    if (!this._hass || this._loading) return;
    this._loading = true;
    try {
      const previous = this._data;
      const data = await this._hass.callWS({ type: "battery_sizer/results" });
      if (this._pendingSince !== undefined) {
        // While the entry reloads, keep showing the last result.
        const entry = data.entries[this._entryIndex] || data.entries[0];
        const done = entry?.result && entry.result.calculated_at !== this._pendingSince;
        const failed = entry && !entry.last_run_succeeded && entry.error;
        if (done || failed) {
          this._pendingSince = undefined;
        } else if (previous) {
          for (const item of data.entries) {
            const old = previous.entries.find((e) => e.entry_id === item.entry_id);
            if (!item.result && old?.result) item.result = old.result;
          }
        }
      }
      this._data = data;
      if (!this._settings) await this._fetchSettings();
      this._error = null;
      for (const entry of this._data.entries) {
        const state = entry.status_entity && this._hass.states[entry.status_entity];
        if (entry.status_entity) {
          this._statusSeen[entry.status_entity] = state ? `${state.state}|${state.last_updated}` : "";
        }
      }
    } catch (err) {
      this._error = err?.message || String(err);
    } finally {
      this._loading = false;
    }
    this._render();
  }

  async _fetchSettings() {
    try {
      this._settings = await this._hass.callWS({
        type: "battery_sizer/settings",
        language: this._locale,
      });
    } catch (err) {
      this._settings = null;
    }
  }

  _decimalSeparator() {
    return new Intl.NumberFormat(this._locale).format(1.5).includes(",") ? "," : ".";
  }

  _formatInput(value) {
    if (value === null || value === undefined || value === "") return "";
    return new Intl.NumberFormat(this._locale, { useGrouping: false, maximumFractionDigits: 3 }).format(value);
  }

  _parseInput(text) {
    let clean = String(text).trim().replace(/\s/g, "");
    if (!clean) return NaN;
    if (this._decimalSeparator() === ",") clean = clean.replace(/\./g, "").replace(",", ".");
    else clean = clean.replace(/,/g, "");
    const value = Number(clean);
    return Number.isFinite(value) ? value : NaN;
  }

  _fieldError(field, text) {
    const t = this._t;
    const value = this._parseInput(text);
    if (Number.isNaN(value)) return t.notNumber;
    if ((field.min !== null && value < field.min) || (field.max !== null && value > field.max)) {
      return t.outOfRange.replace("{min}", this._formatInput(field.min)).replace("{max}", this._formatInput(field.max));
    }
    return null;
  }

  // Fields the calculation ignores in the current mode: the system price is
  // for a new system, the expansion cost for adding to a battery.
  _unusedFields(entry) {
    const field = this._settingsFor(entry)?.groups.flatMap((g) => g.fields).find((f) => f.key === "existing_kwh");
    if (!field) return { keys: [], note: "" };
    const text = this._draft.existing_kwh;
    let existing = field.value;
    if (text !== undefined && !this._fieldError(field, text)) existing = this._parseInput(text);
    return existing > 0
      ? { keys: ["system_price", "system_battery_kwh"], note: this._t.unusedExpansion }
      : { keys: ["expansion_cost"], note: this._t.unusedNew };
  }

  _applyUnused(entry) {
    const { keys, note } = this._unusedFields(entry);
    this.shadowRoot.querySelectorAll(".field[data-key]").forEach((el) => {
      const unused = keys.includes(el.dataset.key);
      el.classList.toggle("unused", unused);
      el.querySelector(".field-unused").textContent = unused ? note : "";
    });
  }

  _helpHtml(text) {
    // The help texts come from the integration's translations: escape them,
    // then allow **bold** and paragraphs.
    return escapeHtml(text)
      .replace(/\*\*(.+?)\*\*/g, "<b>$1</b>")
      .split(/\n\n+/)
      .map((part) => `<p>${part.replace(/\n/g, "<br>")}</p>`)
      .join("");
  }

  _settingsFor(entry) {
    return this._settings?.entries?.[entry.entry_id];
  }

  _draftValues(entry) {
    const settings = this._settingsFor(entry);
    const values = {};
    let valid = true;
    if (!settings) return { values, valid: false };
    for (const group of settings.groups) {
      for (const field of group.fields) {
        const text = this._draft[field.key];
        if (text === undefined) continue;
        if (this._fieldError(field, text)) {
          valid = false;
          continue;
        }
        const value = this._parseInput(text);
        if (value !== field.value) values[field.key] = value;
      }
    }
    return { values, valid };
  }

  async _save(entry) {
    const { values, valid } = this._draftValues(entry);
    if (!valid || !Object.keys(values).length || this._saving) return;
    this._saving = true;
    this._saveError = null;
    this._render();
    const before = entry.result?.calculated_at ?? null;
    try {
      await this._hass.callWS({ type: "battery_sizer/update_settings", entry_id: entry.entry_id, values });
      this._draft = {};
      this._pendingSince = before;
      await this._fetchSettings();
      this._poll(Date.now());
    } catch (err) {
      const key = err?.code === "invalid_settings" ? err.message : null;
      this._saveError = (key && this._settings?.errors?.[key]) || err?.message || String(err);
    } finally {
      this._saving = false;
    }
    this._render();
  }

  _poll(started) {
    clearTimeout(this._pollTimer);
    if (this._pendingSince === undefined) return;
    if (Date.now() - started > 180000) {
      this._pendingSince = undefined;
      this._render();
      return;
    }
    this._pollTimer = setTimeout(async () => {
      await this._fetch();
      this._poll(started);
    }, 2000);
  }

  _updateSaveState(entry) {
    const root = this.shadowRoot;
    const { values, valid } = this._draftValues(entry);
    const count = Object.keys(values).length;
    const save = root.getElementById("save");
    const undo = root.getElementById("undo");
    if (save) save.disabled = !valid || !count || this._saving || !this._settings?.can_edit;
    if (undo) undo.disabled = !Object.keys(this._draft).length;
  }

  async _calculate() {
    if (this._busy) return;
    this._busy = true;
    this._render();
    try {
      await this._hass.callService("battery_sizer", "calculate", {});
    } catch (err) {
      this._error = err?.message || String(err);
    } finally {
      this._busy = false;
    }
    await this._fetch();
  }

  _updateMenuButton() {
    const button = this.shadowRoot?.querySelector("ha-menu-button");
    if (button) {
      button.hass = this._hass;
      button.narrow = this._narrow;
    }
  }

  // ---------- rendering ----------

  _render() {
    if (!this.shadowRoot) return;
    const t = this._t;
    const entries = this._data?.entries;
    let body;
    if (this._error && !entries) {
      body = `<div class="card message error">${escapeHtml(this._error)}</div>`;
    } else if (!entries) {
      body = `<div class="card message">${t.loading}</div>`;
    } else if (!entries.length) {
      body = `<div class="card message">${t.none}</div>`;
    } else {
      const entry = entries[Math.min(this._entryIndex, entries.length - 1)];
      body = this._entryHtml(entry, entries);
    }
    this.shadowRoot.innerHTML = `
      <style>${STYLE}</style>
      <div class="toolbar">
        <ha-menu-button></ha-menu-button>
        <div class="title">${t.title}</div>
        <button class="action" id="calculate" ${this._busy ? "disabled" : ""}>
          ${this._busy ? t.calculating : t.calculate}
        </button>
      </div>
      <div class="content">${body}</div>
    `;
    this._updateMenuButton();
    this._bind();
  }

  _bind() {
    const root = this.shadowRoot;
    root.getElementById("calculate")?.addEventListener("click", () => this._calculate());
    root.querySelectorAll("[data-entry]").forEach((el) =>
      el.addEventListener("click", () => {
        this._entryIndex = Number(el.dataset.entry);
        this._render();
      })
    );
    root.querySelectorAll("[data-metric]").forEach((el) =>
      el.addEventListener("click", () => {
        this._metric = el.dataset.metric;
        this._render();
      })
    );
    const entries = this._data?.entries || [];
    const entry = entries[Math.min(this._entryIndex, entries.length - 1)];
    root.getElementById("assumptions")?.addEventListener("toggle", (ev) => {
      this._settingsOpen = ev.target.open;
    });
    root.querySelectorAll("input[data-field]").forEach((input) => {
      input.addEventListener("input", () => {
        const key = input.dataset.field;
        const field = this._settingsFor(entry)?.groups.flatMap((g) => g.fields).find((f) => f.key === key);
        if (!field) return;
        this._draft[key] = input.value;
        const error = this._fieldError(field, input.value);
        const value = this._parseInput(input.value);
        const wrap = input.closest(".field");
        wrap.classList.toggle("invalid", !!error);
        wrap.classList.toggle("changed", !error && value !== field.value);
        wrap.querySelector(".field-error").textContent = error || "";
        if (key === "existing_kwh") this._applyUnused(entry);
        this._updateSaveState(entry);
      });
      input.addEventListener("keydown", (ev) => {
        if (ev.key === "Enter") this._save(entry);
      });
    });
    root.querySelectorAll("button[data-help]").forEach((button) =>
      button.addEventListener("click", (ev) => {
        ev.preventDefault();
        const key = button.dataset.help;
        const open = !this._openHelp.has(key);
        if (open) this._openHelp.add(key);
        else this._openHelp.delete(key);
        const wrap = button.closest(".field");
        wrap.classList.toggle("help-open", open);
        button.setAttribute("aria-expanded", String(open));
      })
    );
    root.getElementById("save")?.addEventListener("click", () => this._save(entry));
    root.getElementById("undo")?.addEventListener("click", () => {
      this._draft = {};
      this._saveError = null;
      this._render();
    });
    if (entry) this._updateSaveState(entry);
    root.querySelectorAll("[data-strategy]").forEach((el) =>
      el.addEventListener("click", () => {
        this._strategy = el.dataset.strategy;
        this._render();
      })
    );
  }

  _entryHtml(entry, entries) {
    const t = this._t;
    const picker =
      entries.length > 1
        ? `<div class="tabs">${entries
            .map(
              (e, i) =>
                `<button class="tab ${i === this._entryIndex ? "active" : ""}" data-entry="${i}">${escapeHtml(e.title)}</button>`
            )
            .join("")}</div>`
        : "";
    const failed = !entry.last_run_succeeded && entry.error
      ? `<div class="card message error"><b>${t.failed}:</b> ${escapeHtml(entry.error)}</div>`
      : "";
    const result = entry.result;
    if (!result) {
      return `${picker}${failed}${this._assumptionsHtml(entry)}<div class="card message">${t.waiting}</div>`;
    }
    const strategies = STRATEGIES.filter((s) => result.strategies[s]);
    if (!this._strategy || !strategies.includes(this._strategy)) {
      this._strategy =
        strategies.find((s) => result.strategies[s].verdict === "pays_off") || strategies[0];
    }
    return `
      ${picker}
      ${failed}
      ${this._infoHtml(entry, result)}
      ${this._assumptionsHtml(entry)}
      <div class="cards">${strategies.map((s) => this._strategyCard(entry, s, result.strategies[s])).join("")}</div>
      <div class="card">
        <div class="card-head">
          <h2>${entry.expansion ? t.byExpansion : t.bySize}</h2>
          <div class="tabs small">${METRICS.map(
            (m) =>
              `<button class="tab ${m === this._metric ? "active" : ""}" data-metric="${m}">${this._metricName(m, entry)}</button>`
          ).join("")}</div>
        </div>
        ${this._sizeChart(entry, result, strategies)}
        ${this._legend(strategies)}
      </div>
      <div class="card">
        <h2>${entry.expansion ? t.monthlyExtra : t.monthlySavings}</h2>
        ${this._monthlyChart(result, strategies)}
        ${this._legend(strategies, (s) => this._kwh(this._shownKwh(result.strategies[s])))}
      </div>
      <div class="card">
        <div class="card-head">
          <h2>${t.energy}</h2>
          ${this._strategyTabs(strategies)}
        </div>
        ${this._energyChart(result.strategies[this._strategy])}
      </div>
      <div class="card">
        <div class="card-head">
          <h2>${t.table}</h2>
          ${this._strategyTabs(strategies)}
        </div>
        ${this._tableHtml(entry, result.strategies[this._strategy])}
        <p class="note">${t.note}</p>
      </div>
    `;
  }

  _infoHtml(entry, result) {
    const t = this._t;
    const date = (iso) =>
      iso ? new Date(iso).toLocaleDateString(this._locale, { year: "numeric", month: "short", day: "numeric" }) : "–";
    const when = new Date(result.calculated_at).toLocaleString(this._locale, {
      dateStyle: "medium",
      timeStyle: "short",
    });
    const existing = entry.expansion
      ? `<span><b>${t.existing}:</b> ${this._kwh(result.existing_kwh)}</span>`
      : "";
    return `<div class="info">
      <span><b>${t.period}:</b> ${date(result.first)} – ${date(result.last)} (${this._number(result.hours)} ${t.hours})</span>
      ${existing}
      <span><b>${t.calculated}:</b> ${escapeHtml(when)}</span>
    </div>`;
  }

  _unit(unit) {
    if (unit === "år") return this._t.years;
    return unit || "";
  }

  _assumptionsHtml(entry) {
    const t = this._t;
    const settings = this._settingsFor(entry);
    if (!settings) return "";
    const canEdit = !!this._settings.can_edit;
    const fields = settings.groups.flatMap((g) => g.fields);
    const pick = (key) => fields.find((f) => f.key === key);
    const summary = ["existing_kwh", "power_kw", "battery_price_per_kwh", "lifetime_years"]
      .map(pick)
      .filter((f) => f && !(f.key === "existing_kwh" && !f.value))
      .map((f) => `${this._formatInput(f.value)} ${this._unit(f.unit)}`)
      .join(" · ");
    const pending = this._pendingSince !== undefined;
    const unused = this._unusedFields(entry);
    const groups = settings.groups
      .map(
        (group) => `<fieldset>
          <legend>${escapeHtml(group.title)}</legend>
          <div class="fields">${group.fields
            .map((field) => {
              const text = this._draft[field.key];
              const shown = text !== undefined ? text : this._formatInput(field.value);
              const error = text !== undefined ? this._fieldError(field, text) : null;
              const changed = text !== undefined && !error && this._parseInput(text) !== field.value;
              const isUnused = unused.keys.includes(field.key);
              const helpOpen = this._openHelp.has(field.key);
              const help = field.help || field.description || "";
              const classes = [
                "field",
                error ? "invalid" : "",
                changed ? "changed" : "",
                isUnused ? "unused" : "",
                helpOpen ? "help-open" : "",
              ].join(" ");
              return `<div class="${classes}" data-key="${field.key}">
                <div class="field-head">
                  <label class="field-label" for="f-${field.key}">${escapeHtml(field.label)}</label>
                  ${help
                    ? `<button type="button" class="info" data-help="${field.key}" aria-expanded="${helpOpen}"
                        aria-controls="h-${field.key}" title="${t.moreInfo}" aria-label="${t.moreInfo}: ${escapeHtml(field.label)}">i</button>`
                    : ""}
                </div>
                <span class="input-wrap">
                  <input id="f-${field.key}" data-field="${field.key}" type="text" inputmode="decimal" autocomplete="off"
                    value="${escapeHtml(shown)}" ${canEdit && !pending ? "" : "disabled"}>
                  ${field.unit ? `<span class="unit">${escapeHtml(this._unit(field.unit))}</span>` : ""}
                </span>
                <span class="field-error">${error ? escapeHtml(error) : ""}</span>
                <span class="field-unused">${isUnused ? escapeHtml(unused.note) : ""}</span>
                ${help ? `<div class="field-help" id="h-${field.key}">${this._helpHtml(help)}</div>` : ""}
              </div>`;
            })
            .join("")}</div>
        </fieldset>`
      )
      .join("");
    return `<details class="card assumptions" id="assumptions" ${this._settingsOpen || pending ? "open" : ""}>
      <summary>
        <span class="summary-title">${t.assumptions}</span>
        <span class="summary-values">${escapeHtml(summary)}</span>
      </summary>
      ${pending ? `<div class="banner">${t.recalculating}</div>` : ""}
      ${this._saveError ? `<div class="banner error">${escapeHtml(this._saveError)}</div>` : ""}
      ${canEdit ? "" : `<p class="note">${t.adminOnly}</p>`}
      ${groups}
      ${canEdit
        ? `<div class="form-actions">
            <button class="secondary" id="undo">${t.undo}</button>
            <button class="primary" id="save">${this._saving ? t.saving : t.save}</button>
          </div>`
        : ""}
    </details>`;
  }

  _metricName(metric, entry) {
    const t = this._t;
    if (metric === "net_present_value") return t.npv;
    if (metric === "payback_years") return t.payback;
    return entry.expansion ? t.extraSavings : t.savings;
  }

  _shownKwh(outcome) {
    return outcome.verdict === "pays_off" ? outcome.recommended_kwh : outcome.candidate_kwh;
  }

  _strategyCard(entry, strategy, o) {
    const t = this._t;
    const verdict = o.verdict;
    const sizeLabel =
      verdict === "pays_off" ? (entry.expansion ? t.recommendedExpansion : t.recommended) : t.closest;
    const payback =
      o.payback_years === null || o.payback_years === undefined
        ? "–"
        : `${this._number(o.payback_years, 1)} ${t.years}${
            o.payback_within_lifetime ? "" : ` <span class="muted">(${t.beyondLifetime})</span>`
          }`;
    const kwh = this._shownKwh(o);
    const sizeText = kwh === null || kwh === undefined ? "–" : `${entry.expansion ? "+" : ""}${this._kwh(kwh)}`;
    return `<div class="card strategy" style="--accent:${COLORS[strategy]}">
      <div class="strategy-head">
        <h2>${t.strategies[strategy]}</h2>
        <span class="badge" style="background:${VERDICT_COLORS[verdict]}">${t.verdicts[verdict]}</span>
      </div>
      <div class="big">${sizeText}</div>
      <div class="label">${sizeLabel}</div>
      <dl>
        <dt>${entry.expansion ? t.extraSavings : t.savings}</dt><dd>${this._kr(o.annual_savings)}</dd>
        <dt>${t.payback}</dt><dd>${payback}</dd>
        <dt>${t.npv}</dt><dd class="${(o.net_present_value ?? 0) < 0 ? "negative" : ""}">${this._kr(o.net_present_value)}</dd>
        <dt>${t.investment}</dt><dd>${this._kr(o.investment)}</dd>
        <dt>${t.cycles}</dt><dd>${this._number(o.cycles_per_year)}</dd>
      </dl>
    </div>`;
  }

  _strategyTabs(strategies) {
    const t = this._t;
    return `<div class="tabs small">${strategies
      .map(
        (s) =>
          `<button class="tab ${s === this._strategy ? "active" : ""}" data-strategy="${s}" style="--accent:${COLORS[s]}">${t.strategies[s]}</button>`
      )
      .join("")}</div>`;
  }

  _legend(strategies, extra) {
    const t = this._t;
    return `<div class="legend">${strategies
      .map(
        (s) =>
          `<span><i style="background:${COLORS[s]}"></i>${t.strategies[s]}${extra ? ` · ${extra(s)}` : ""}</span>`
      )
      .join("")}</div>`;
  }

  _rowValue(row, metric) {
    if (metric === "payback_years") {
      return row.annual_savings > 0 ? row.investment / row.annual_savings : null;
    }
    return row[metric];
  }

  _sizeChart(entry, result, strategies) {
    const t = this._t;
    const metric = this._metric;
    const series = strategies.map((s) => ({
      strategy: s,
      shown: this._shownKwh(result.strategies[s]),
      points: result.strategies[s].sizes
        .map((row) => ({ x: row.kwh, y: this._rowValue(row, metric) }))
        .filter((p) => p.y !== null && p.y !== undefined && Number.isFinite(p.y)),
    }));
    const all = series.flatMap((s) => s.points);
    if (!all.length) return `<div class="empty">${t.noData}</div>`;
    const lifetime = entry.lifetime_years;
    let ys = all.map((p) => p.y);
    if (metric === "payback_years") {
      // Very long payback times would flatten everything else.
      const cap = Math.max(lifetime ? lifetime * 2 : 30, 5);
      ys = ys.map((y) => Math.min(y, cap));
    }
    const yMin = Math.min(0, ...ys);
    const yMax = Math.max(0, ...ys, metric === "payback_years" && lifetime ? lifetime : 0);
    const yTicks = ticks(yMin, yMax, this._compact ? 4 : 5);
    const xs = all.map((p) => p.x);
    const xTicks = ticks(Math.min(0, ...xs), Math.max(...xs), this._compact ? 4 : 6).filter((x) => x >= 0);
    const chart = this._frame(xTicks, yTicks, (v) => this._axisValue(v, metric), (v) => this._number(v, v % 1 ? 1 : 0));
    const { sx, sy } = chart;
    const clampY = (y) => Math.max(yTicks[0], Math.min(yTicks[yTicks.length - 1], y));
    let marks = "";
    if (yTicks[0] < 0) {
      marks += `<line class="zero" x1="${sx(xTicks[0])}" x2="${sx(xTicks[xTicks.length - 1])}" y1="${sy(0)}" y2="${sy(0)}"/>`;
    }
    if (metric === "payback_years" && lifetime) {
      marks += `<line class="limit" x1="${sx(xTicks[0])}" x2="${sx(xTicks[xTicks.length - 1])}" y1="${sy(lifetime)}" y2="${sy(lifetime)}"/>
        <text class="limit-label" x="${sx(xTicks[0]) + 6}" y="${sy(lifetime) - 6}" text-anchor="start">${t.lifetime} ${this._number(lifetime)} ${t.years}</text>`;
    }
    for (const s of series) {
      if (!s.points.length) continue;
      const path = s.points
        .map((p, i) => `${i ? "L" : "M"}${sx(p.x).toFixed(1)},${sy(clampY(p.y)).toFixed(1)}`)
        .join(" ");
      marks += `<path d="${path}" fill="none" stroke="${COLORS[s.strategy]}" stroke-width="${this._compact ? 2 : 2.5}" stroke-linejoin="round" stroke-linecap="round"/>`;
      for (const p of s.points) {
        const isShown = p.x === s.shown;
        if (!isShown && this._compact && s.points.length > 12) continue;
        marks += `<circle cx="${sx(p.x).toFixed(1)}" cy="${sy(clampY(p.y)).toFixed(1)}" r="${isShown ? (this._compact ? 5 : 6) : 3}"
          fill="${isShown ? COLORS[s.strategy] : "var(--card-background-color, #fff)"}"
          stroke="${COLORS[s.strategy]}" stroke-width="${this._compact ? 1.5 : 2}">
          <title>${t.strategies[s.strategy]} · ${this._kwh(p.x)}: ${this._valueText(p.y, metric)}</title></circle>`;
      }
    }
    return chart.svg(marks, entry.expansion ? `${t.added} (kWh)` : `${t.size} (kWh)`);
  }

  _axisValue(value, metric) {
    if (metric === "payback_years") return this._number(value, value % 1 ? 1 : 0);
    const abs = Math.abs(value);
    if (abs >= 1e6) return `${this._number(value / 1e6, 1)} mio`;
    if (abs >= 1e4) return `${this._number(value / 1e3)}k`;
    return this._number(value);
  }

  _valueText(value, metric) {
    if (metric === "payback_years") return `${this._number(value, 1)} ${this._t.years}`;
    return this._kr(Math.round(value));
  }

  _monthlyChart(result, strategies) {
    const t = this._t;
    const groups = t.months.map((label, index) => ({
      label,
      bars: strategies.map((s) => ({
        strategy: s,
        value: result.strategies[s].monthly?.[index]?.savings ?? null,
      })),
    }));
    const values = groups.flatMap((g) => g.bars.map((b) => b.value)).filter((v) => v !== null);
    if (!values.length) return `<div class="empty">${t.noData}</div>`;
    const yTicks = ticks(Math.min(0, ...values), Math.max(0, ...values), this._compact ? 4 : 5);
    const chart = this._bandFrame(groups.map((g) => g.label), yTicks, (v) => this._axisValue(v, "kr"));
    const { band, sy } = chart;
    let marks = "";
    const width = band.width / (strategies.length + (this._compact ? 0.4 : 0.8));
    groups.forEach((group, gi) => {
      group.bars.forEach((bar, bi) => {
        if (bar.value === null) return;
        const x = band.start(gi) + width * (this._compact ? 0.2 : 0.4) + bi * width;
        const y0 = sy(0);
        const y1 = sy(bar.value);
        marks += `<rect x="${x.toFixed(1)}" y="${Math.min(y0, y1).toFixed(1)}" width="${(width - 2).toFixed(1)}"
          height="${Math.max(1, Math.abs(y1 - y0)).toFixed(1)}" rx="${this._compact ? 1 : 2}" fill="${COLORS[bar.strategy]}">
          <title>${t.strategies[bar.strategy]} · ${group.label}: ${this._kr(Math.round(bar.value))}</title></rect>`;
      });
    });
    if (yTicks[0] < 0) {
      marks += `<line class="zero" x1="${chart.left}" x2="${chart.right}" y1="${sy(0)}" y2="${sy(0)}"/>`;
    }
    return chart.svg(marks);
  }

  _energyChart(outcome) {
    const t = this._t;
    const rows = outcome?.monthly || [];
    if (!rows.some((r) => r.delivered_kwh !== null)) return `<div class="empty">${t.noData}</div>`;
    const parts = [
      { key: "delivered_kwh", label: t.delivered, color: COLORS[this._strategy] },
      { key: "sold_kwh", label: t.sold, color: "var(--secondary-text-color, #727272)" },
    ];
    const totals = rows.map((r) => parts.reduce((sum, p) => sum + (r[p.key] || 0), 0));
    const grid = rows.map((r) => r.charged_grid_kwh || 0);
    const yTicks = ticks(0, Math.max(1, ...totals, ...grid), this._compact ? 4 : 5);
    const chart = this._bandFrame(t.months, yTicks, (v) => this._number(v));
    const { band, sy } = chart;
    let marks = "";
    const width = band.width * 0.6;
    rows.forEach((row, i) => {
      let base = 0;
      const x = band.start(i) + (band.width - width) / 2;
      for (const part of parts) {
        const value = row[part.key] || 0;
        if (value <= 0) continue;
        const y1 = sy(base + value);
        const y0 = sy(base);
        marks += `<rect x="${x.toFixed(1)}" y="${y1.toFixed(1)}" width="${width.toFixed(1)}" height="${Math.max(0.5, y0 - y1).toFixed(1)}"
          fill="${part.color}" opacity="${part.key === "sold_kwh" ? 0.55 : 1}">
          <title>${t.months[i]} · ${part.label}: ${this._kwh(value)}</title></rect>`;
        base += value;
      }
    });
    const hasGrid = grid.some((v) => v > 0.05);
    if (hasGrid) {
      const path = grid
        .map((v, i) => `${i ? "L" : "M"}${(band.start(i) + band.width / 2).toFixed(1)},${sy(v).toFixed(1)}`)
        .join(" ");
      marks += `<path d="${path}" fill="none" stroke="var(--primary-text-color, #212121)" stroke-width="2" stroke-dasharray="5 4"/>`;
      grid.forEach((v, i) => {
        marks += `<circle cx="${(band.start(i) + band.width / 2).toFixed(1)}" cy="${sy(v).toFixed(1)}" r="2.5" fill="var(--primary-text-color, #212121)">
          <title>${t.months[i]} · ${t.fromGrid}: ${this._kwh(v)}</title></circle>`;
      });
    }
    const legend = `<div class="legend">
      ${parts.map((p) => `<span><i style="background:${p.color};opacity:${p.key === "sold_kwh" ? 0.55 : 1}"></i>${p.label}</span>`).join("")}
      ${hasGrid ? `<span><i class="dash"></i>${t.fromGrid}</span>` : ""}
    </div>`;
    return chart.svg(marks, "kWh") + legend;
  }

  _tableHtml(entry, outcome) {
    const t = this._t;
    if (!outcome?.sizes?.length) return `<div class="empty">${t.noData}</div>`;
    const shown = this._shownKwh(outcome);
    const rows = outcome.sizes
      .map((row) => {
        const payback = row.annual_savings > 0 ? row.investment / row.annual_savings : null;
        const beyond = row.payback_years === null && payback !== null;
        return `<tr class="${row.kwh === shown ? "shown" : ""}">
          <td>${entry.expansion ? "+" : ""}${this._kwh(row.kwh)}</td>
          <td>${this._kr(row.annual_savings)}</td>
          <td>${this._kr(row.investment)}</td>
          <td>${payback === null ? "–" : `${this._number(payback, 1)}${beyond ? " *" : ""}`}</td>
          <td class="${row.net_present_value < 0 ? "negative" : ""}">${this._kr(row.net_present_value)}</td>
          <td>${this._number(row.cycles_per_year)}</td>
        </tr>`;
      })
      .join("");
    return `<div class="table-wrap"><table>
      <thead><tr>
        <th>${entry.expansion ? t.added : t.size}</th>
        <th>${entry.expansion ? t.extraSavings : t.savings}</th>
        <th>${t.investment}</th>
        <th>${t.payback} (${t.years})</th>
        <th>${t.npv}</th>
        <th>${t.cycles}</th>
      </tr></thead>
      <tbody>${rows}</tbody>
    </table></div>
    <p class="note">* ${t.beyondLifetime}</p>`;
  }

  // ---------- chart frames ----------

  _frame(xTicks, yTicks, yLabel, xLabel) {
    const W = this._chartWidth, H = this._compact ? 230 : 300;
    const left = this._compact ? 44 : 56, right = W - 10, top = 14, bottom = H - 40;
    const [x0, x1] = [xTicks[0], xTicks[xTicks.length - 1]];
    const [y0, y1] = [yTicks[0], yTicks[yTicks.length - 1]];
    const sx = (x) => left + ((x - x0) / (x1 - x0 || 1)) * (right - left);
    const sy = (y) => bottom - ((y - y0) / (y1 - y0 || 1)) * (bottom - top);
    const grid =
      yTicks
        .map(
          (v) => `<line class="grid" x1="${left}" x2="${right}" y1="${sy(v)}" y2="${sy(v)}"/>
            <text class="axis" x="${left - 8}" y="${sy(v) + 4}" text-anchor="end">${yLabel(v)}</text>`
        )
        .join("") +
      xTicks
        .map((v) => `<text class="axis" x="${sx(v)}" y="${bottom + 18}" text-anchor="middle">${xLabel(v)}</text>`)
        .join("");
    return {
      sx,
      sy,
      svg: (marks, caption) => `<svg viewBox="0 0 ${W} ${H}" role="img" preserveAspectRatio="xMidYMid meet">
        ${grid}${marks}
        ${caption ? `<text class="axis caption" x="${(left + right) / 2}" y="${H - 4}" text-anchor="middle">${caption}</text>` : ""}
      </svg>`,
    };
  }

  _bandFrame(labels, yTicks, yLabel) {
    const W = this._chartWidth, H = this._compact ? 220 : 280;
    const left = this._compact ? 44 : 56, right = W - 10, top = 26, bottom = H - 30;
    const [y0, y1] = [yTicks[0], yTicks[yTicks.length - 1]];
    const sy = (y) => bottom - ((y - y0) / (y1 - y0 || 1)) * (bottom - top);
    const bandWidth = (right - left) / labels.length;
    const band = { width: bandWidth, start: (i) => left + i * bandWidth };
    const grid =
      yTicks
        .map(
          (v) => `<line class="grid" x1="${left}" x2="${right}" y1="${sy(v)}" y2="${sy(v)}"/>
            <text class="axis" x="${left - 8}" y="${sy(v) + 4}" text-anchor="end">${yLabel(v)}</text>`
        )
        .join("") +
      labels
        .map(
          (l, i) =>
            `<text class="axis" x="${band.start(i) + bandWidth / 2}" y="${bottom + 18}" text-anchor="middle">${
              bandWidth < 34 ? l.slice(0, 1).toUpperCase() : l
            }</text>`
        )
        .join("");
    return {
      band,
      sy,
      left,
      right,
      svg: (marks, caption) => `<svg viewBox="0 0 ${W} ${H}" role="img" preserveAspectRatio="xMidYMid meet">
        ${grid}${marks}
        ${caption ? `<text class="axis" x="${left - 8}" y="${top - 14}" text-anchor="end">${caption}</text>` : ""}
      </svg>`,
    };
  }
}

const STYLE = `
  :host {
    display: block;
    min-height: 100vh;
    background: var(--primary-background-color, #fafafa);
    color: var(--primary-text-color, #212121);
    font-family: var(--paper-font-body1_-_font-family, Roboto, "Segoe UI", sans-serif);
  }
  .toolbar {
    display: flex;
    align-items: center;
    gap: 8px;
    height: var(--header-height, 56px);
    padding: 0 12px;
    background: var(--app-header-background-color, var(--primary-color, #03a9f4));
    color: var(--app-header-text-color, #fff);
    border-bottom: var(--app-header-border-bottom, none);
    position: sticky;
    top: 0;
    z-index: 2;
  }
  .title { flex: 1; font-size: 20px; font-weight: 400; margin-left: 4px; }
  .action {
    border: 1px solid currentColor;
    background: transparent;
    color: inherit;
    border-radius: 18px;
    padding: 6px 14px;
    font: inherit;
    font-size: 14px;
    cursor: pointer;
  }
  .action:disabled { opacity: 0.6; cursor: default; }
  .content { max-width: 1200px; margin: 0 auto; padding: 16px; box-sizing: border-box; }
  .card {
    background: var(--ha-card-background, var(--card-background-color, #fff));
    border-radius: var(--ha-card-border-radius, 12px);
    border: 1px solid var(--ha-card-border-color, var(--divider-color, #e0e0e0));
    box-shadow: var(--ha-card-box-shadow, none);
    padding: 16px;
    margin-bottom: 16px;
    box-sizing: border-box;
    min-width: 0;
  }
  .message { line-height: 1.5; }
  .error { border-color: var(--error-color, #db4437); }
  h2 { font-size: 16px; font-weight: 500; margin: 0 0 8px; }
  .card-head { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 8px; margin-bottom: 8px; }
  .card-head h2 { margin: 0; }
  .info {
    display: flex; flex-wrap: wrap; gap: 6px 20px;
    color: var(--secondary-text-color, #727272);
    font-size: 14px;
    margin: 0 4px 16px;
  }
  .info b { color: var(--primary-text-color, #212121); font-weight: 500; }
  .cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 16px; margin-bottom: 16px; }
  .cards .card { margin-bottom: 0; }
  .strategy { border-top: 4px solid var(--accent); }
  .strategy-head { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
  .strategy-head h2 { margin: 0; }
  .badge { color: #fff; font-size: 12px; font-weight: 500; padding: 3px 10px; border-radius: 12px; white-space: nowrap; }
  .big { font-size: 32px; font-weight: 400; margin-top: 12px; }
  .label { color: var(--secondary-text-color, #727272); font-size: 13px; margin-bottom: 12px; }
  dl { display: grid; grid-template-columns: 1fr auto; gap: 6px 12px; margin: 0; font-size: 14px; }
  dt { color: var(--secondary-text-color, #727272); }
  dd { margin: 0; text-align: right; font-variant-numeric: tabular-nums; }
  .negative { color: var(--error-color, #db4437); }
  .muted { color: var(--secondary-text-color, #727272); font-size: 12px; }
  .tabs { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 12px; }
  .tabs.small { margin-bottom: 0; }
  .tab {
    border: 1px solid var(--divider-color, #e0e0e0);
    background: transparent;
    color: var(--primary-text-color, #212121);
    border-radius: 16px;
    padding: 5px 12px;
    font: inherit;
    font-size: 13px;
    cursor: pointer;
  }
  .tab.active {
    background: var(--accent, var(--primary-color, #03a9f4));
    border-color: var(--accent, var(--primary-color, #03a9f4));
    color: #fff;
  }
  svg { width: 100%; height: auto; display: block; overflow: visible; max-width: 100%; }
  .grid { stroke: var(--divider-color, #e0e0e0); stroke-width: 1; }
  .zero { stroke: var(--secondary-text-color, #727272); stroke-width: 1.5; }
  .limit { stroke: var(--secondary-text-color, #727272); stroke-width: 1.5; stroke-dasharray: 6 5; }
  .limit-label { fill: var(--secondary-text-color, #727272); font-size: 12px; }
  .axis { fill: var(--secondary-text-color, #727272); font-size: 12px; }
  .legend { display: flex; flex-wrap: wrap; gap: 6px 18px; font-size: 13px; color: var(--secondary-text-color, #727272); margin-top: 8px; }
  .legend i { display: inline-block; width: 12px; height: 12px; border-radius: 3px; margin-right: 6px; vertical-align: -1px; }
  .legend i.dash { height: 0; border-top: 2px dashed var(--primary-text-color, #212121); border-radius: 0; width: 16px; vertical-align: 3px; }
  .empty { color: var(--secondary-text-color, #727272); padding: 24px 0; text-align: center; }
  .table-wrap { overflow-x: auto; }
  table { width: 100%; border-collapse: collapse; font-size: 14px; font-variant-numeric: tabular-nums; }
  th, td { padding: 8px 10px; text-align: right; border-bottom: 1px solid var(--divider-color, #e0e0e0); white-space: nowrap; }
  th:first-child, td:first-child { text-align: left; }
  th { color: var(--secondary-text-color, #727272); font-weight: 500; }
  tr.shown td { font-weight: 600; background: rgba(127, 127, 127, 0.08); }
  .note { color: var(--secondary-text-color, #727272); font-size: 12px; margin: 8px 0 0; }
  details.assumptions > summary {
    list-style: none;
    cursor: pointer;
    display: flex;
    flex-wrap: wrap;
    align-items: baseline;
    gap: 4px 12px;
  }
  details.assumptions > summary::-webkit-details-marker { display: none; }
  details.assumptions > summary::before {
    content: "▸";
    color: var(--secondary-text-color, #727272);
    transition: transform 0.15s;
    display: inline-block;
  }
  details.assumptions[open] > summary::before { transform: rotate(90deg); }
  .summary-title { font-size: 16px; font-weight: 500; }
  .summary-values { color: var(--secondary-text-color, #727272); font-size: 14px; }
  fieldset { border: 0; padding: 0; margin: 16px 0 0; min-width: 0; }
  legend { font-weight: 500; font-size: 14px; padding: 0; margin-bottom: 8px; }
  .fields { display: grid; grid-template-columns: repeat(auto-fill, minmax(230px, 1fr)); gap: 12px 16px; }
  .field { display: flex; flex-direction: column; gap: 4px; min-width: 0; }
  .field-label { font-size: 13px; color: var(--secondary-text-color, #727272); }
  .input-wrap {
    display: flex;
    align-items: center;
    border: 1px solid var(--divider-color, #e0e0e0);
    border-radius: 8px;
    background: var(--secondary-background-color, transparent);
    padding: 0 10px;
  }
  .input-wrap:focus-within { border-color: var(--primary-color, #03a9f4); }
  .field.changed .input-wrap { border-color: var(--primary-color, #03a9f4); box-shadow: inset 3px 0 0 var(--primary-color, #03a9f4); }
  .field.invalid .input-wrap { border-color: var(--error-color, #db4437); }
  input {
    flex: 1;
    min-width: 0;
    border: 0;
    background: transparent;
    color: var(--primary-text-color, #212121);
    font: inherit;
    font-size: 16px;
    padding: 9px 0;
    outline: none;
    font-variant-numeric: tabular-nums;
  }
  input:disabled { color: var(--secondary-text-color, #727272); }
  .unit { color: var(--secondary-text-color, #727272); font-size: 14px; margin-left: 6px; white-space: nowrap; }
  .field-error { color: var(--error-color, #db4437); font-size: 12px; min-height: 0; }
  .field-error:empty { display: none; }
  .field-head { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
  .info {
    flex: none;
    width: 20px;
    height: 20px;
    border-radius: 50%;
    border: 1px solid var(--secondary-text-color, #727272);
    background: transparent;
    color: var(--secondary-text-color, #727272);
    font: italic 600 12px/1 Georgia, "Times New Roman", serif;
    cursor: pointer;
    padding: 0;
    display: inline-flex;
    align-items: center;
    justify-content: center;
  }
  .info:hover, .field.help-open .info {
    border-color: var(--primary-color, #03a9f4);
    color: var(--text-primary-color, #fff);
    background: var(--primary-color, #03a9f4);
  }
  .field-help {
    display: none;
    color: var(--primary-text-color, #212121);
    font-size: 13px;
    line-height: 1.45;
    background: rgba(127, 127, 127, 0.1);
    border-radius: 8px;
    padding: 8px 10px;
  }
  .field-help p { margin: 0 0 6px; }
  .field-help p:last-child { margin-bottom: 0; }
  .field.help-open .field-help { display: block; }
  .field-unused { color: var(--secondary-text-color, #727272); font-size: 12px; font-style: italic; }
  .field-unused:empty { display: none; }
  .field.unused .input-wrap { opacity: 0.5; }
  .field.unused .field-label { opacity: 0.7; }
  .form-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 16px; flex-wrap: wrap; }
  .form-actions button {
    border-radius: 18px;
    padding: 8px 18px;
    font: inherit;
    font-size: 14px;
    cursor: pointer;
    border: 1px solid var(--primary-color, #03a9f4);
  }
  .form-actions .primary { background: var(--primary-color, #03a9f4); color: var(--text-primary-color, #fff); }
  .form-actions .secondary { background: transparent; color: var(--primary-color, #03a9f4); }
  .form-actions button:disabled { opacity: 0.45; cursor: default; }
  .banner {
    margin-top: 12px;
    padding: 10px 12px;
    border-radius: 8px;
    font-size: 14px;
    background: rgba(127, 127, 127, 0.1);
  }
  .banner.error { color: var(--error-color, #db4437); background: rgba(219, 68, 55, 0.08); }
  @media (max-width: 600px) {
    .content { padding: 12px; }
    .title { font-size: 18px; }
    .big { font-size: 28px; }
  }
`;

customElements.define("battery-sizer-panel", BatterySizerPanel);
