/* The stations page: every station's state from GET /api/v1/stations/health (station/health.py), in a table that
   sorts by any column (click the header; again for the other direction) and filters by any column (the field under
   the header; the summary cards above filter by state, level or problem).  A row opens into the full heartbeat.
   The data is re-read every minute (a heartbeat comes through the MQTT bridge, a separate process, so there is no
   live push for it) and the silence is recomputed from the server's clock. */
(function () {
  "use strict";
  const REFRESH_MS = 60000;
  const STATE_TEXT = { online: "на связи", late: "опаздывает", lost: "потеряна", never: "не выходила" };
  const LEVEL_RANK = { ok: 0, info: 1, warn: 2, alarm: 3 };
  const STATE_RANK = { online: 0, never: 1, late: 2, lost: 3 };
  const TRUST_TEXT = { GNSS_TIME_TRUSTED: "время GNSS", HOLDOVER: "удержание", GNSS_TIME_SUSPECT: "сомнительно",
                       UNSYNCED: "нет синхр.", UNKNOWN: "неизвестно" };
  const FW_TEXT = { IDLE: "", DOWNLOADING: "загрузка", INSTALL_PENDING: "установка", TRIAL: "проверка", ROLLED_BACK: "откат" };
  const $ = (id) => document.getElementById(id);

  const fmt = {
    num: (v, digits) => (v === null || v === undefined || Number.isNaN(v)) ? "" : Number(v).toFixed(digits || 0),
    ago: (s) => {
      if (s === null || s === undefined) return "";
      if (s < 90) return Math.round(s) + " с назад";
      const m = Math.round(s / 60);
      if (m < 90) return m + " мин назад";
      const h = Math.floor(s / 3600), mm = Math.round((s % 3600) / 60);
      if (h < 48) return h + " ч " + (mm ? mm + " мин " : "") + "назад";
      return Math.round(s / 86400) + " сут назад";
    },
    stamp: (us) => us ? new Date(us / 1000).toLocaleString("ru-RU") : "",
    uptime: (s) => {
      if (s === null || s === undefined) return "";
      const d = Math.floor(s / 86400), h = Math.floor((s % 86400) / 3600), m = Math.floor((s % 3600) / 60);
      return (d ? d + " сут " : "") + (h || d ? h + " ч " : "") + m + " мин";
    },
  };

  // ---- the columns: label, value for sorting/filtering, cell text (or node) ---------------------------------------
  const columns = [
    { key: "station_id", label: "Станция", num: true, value: (r) => r.station_id },
    { key: "serial", label: "Серийный №", value: (r) => r.serial || "" },
    { key: "tenant", label: "Участок", value: (r) => r.tenant || "" },
    { key: "state", label: "Состояние", value: (r) => STATE_TEXT[r.state] || r.state,
      sort: (r) => STATE_RANK[r.state] * 10 + LEVEL_RANK[r.level],
      cell: (r) => el("span", "st-badge st-" + r.state, STATE_TEXT[r.state] || r.state) },
    { key: "seen", label: "Heartbeat", num: true, value: (r) => r.silence_s === null ? "" : fmt.ago(r.silence_s),
      sort: (r) => r.silence_s === null ? Infinity : r.silence_s,
      cell: (r) => { const s = el("span", "", r.silence_s === null ? "никогда" : fmt.ago(r.silence_s)); s.title = fmt.stamp(r.received_us); return s; } },
    { key: "battery", label: "Батарея", num: true, value: (r) => r.power.battery_pct, sort: (r) => r.power.battery_pct ?? -1,
      cell: (r) => r.power.battery_pct === null ? "" : el("span", "", r.power.battery_pct + " %" + (r.power.battery_mv ? " · " + fmt.num(r.power.battery_mv / 1000, 2) + " В" : "")) },
    { key: "solar", label: "Солнце, В", num: true, value: (r) => r.power.solar_mv === null ? "" : fmt.num(r.power.solar_mv / 1000, 2), sort: (r) => r.power.solar_mv ?? -1 },
    { key: "temp", label: "t, °C", num: true, value: (r) => fmt.num(r.power.temperature_c, 1), sort: (r) => r.power.temperature_c ?? -999 },
    { key: "gnss", label: "GNSS", value: (r) => r.gnss.fix_type === null ? "" : (r.gnss.fix_type ? "fix " + r.gnss.fix_type : "нет fix") + " · " + (r.gnss.satellites ?? 0) + " сп." + (r.gnss.pps_ok ? " · PPS" : ""),
      sort: (r) => (r.gnss.fix_type || 0) * 100 + (r.gnss.satellites || 0) },
    { key: "time", label: "Время", value: (r) => TRUST_TEXT[r.gnss.time_trust] || r.gnss.time_trust || "" },
    { key: "link", label: "Связь", value: (r) => (r.route.transport || "") + (r.route.rssi_dbm !== null && r.route.rssi_dbm !== undefined ? " " + r.route.rssi_dbm + " дБм" : "") + (r.cellular && r.cellular.registered_operator ? " · " + r.cellular.registered_operator : ""),
      sort: (r) => r.route.rssi_dbm ?? -999 },
    { key: "firmware", label: "Прошивка", value: (r) => (r.versions.firmware_ver || "") + (r.versions.fw_version ? " (#" + r.versions.fw_version + ")" : "") + (FW_TEXT[r.versions.fw_state] ? " · " + FW_TEXT[r.versions.fw_state] : "") },
    { key: "model", label: "Модель", value: (r) => r.versions.model_ver || "" },
    { key: "uptime", label: "Работает", num: true, value: (r) => fmt.uptime(r.detector.uptime_s), sort: (r) => r.detector.uptime_s ?? -1 },
    { key: "problems", label: "Требует внимания", wrap: true, value: (r) => r.problems.map((p) => p.text).join("; "),
      sort: (r) => LEVEL_RANK[r.level] * 100 + r.problems.length,
      cell: (r) => { const box = el("span", "st-problems"); r.problems.forEach((p) => box.appendChild(el("span", "st-problem st-" + p.level, p.text))); return box; } },
  ];

  function el(tag, cls, text) {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined && text !== null) node.textContent = String(text);
    return node;
  }

  // ---- state ------------------------------------------------------------------------------------------------------
  let data = { stations: [], summary: {}, thresholds: {}, now_us: 0 };
  let receivedAt = 0;                    // Date.now() when the data arrived: the silence grows from there
  let sortKey = "state", sortDesc = true;
  let filters = {};                      // column key -> lower-case text
  let quick = "";                        // the summary card filter: state:x, level:x, problem:x
  let selectedTenant = "";
  let viewMode = "cards";
  const open = new Set();                // station ids with the details row open

  function quickMatch(r) {
    if (!quick) return true;
    const [kind, value] = quick.split(":");
    if (kind === "state") return r.state === value;
    if (kind === "level") return r.level === value;
    if (kind === "problem") {
      if (value === "gnss") return r.problems.some((p) => /^(gnss_|position_|time_)/.test(p.code));
      if (value === "updating") return r.problems.some((p) => p.code === "fw_update" || p.code === "net_trial");
      return r.problems.some((p) => p.code === value);
    }
    return true;
  }

  function visible() {
    const elapsed = (Date.now() - receivedAt) / 1000;
    const rows = data.stations.map((r) => r.silence_s === null ? r : Object.assign({}, r, { silence_s: r.silence_s + elapsed }));
    const col = columns.find((c) => c.key === sortKey) || columns[0];
    const keyOf = col.sort || col.value;
    const out = rows.filter((r) => (!selectedTenant || r.tenant === selectedTenant) && quickMatch(r) && columns.every((c) => {
      const f = filters[c.key];
      return !f || String(c.value(r) ?? "").toLowerCase().includes(f);
    }));
    out.sort((a, b) => {
      let x = keyOf(a), y = keyOf(b);
      if (typeof x === "string" || typeof y === "string") { x = String(x ?? ""); y = String(y ?? ""); return x.localeCompare(y, "ru", { numeric: true }); }
      return (x ?? -Infinity) - (y ?? -Infinity);
    });
    if (sortDesc) out.reverse();
    return out;
  }

  // ---- rendering --------------------------------------------------------------------------------------------------
  function renderHead() {
    const head = $("st-head"), filt = $("st-filters");
    head.replaceChildren(); filt.replaceChildren();
    columns.forEach((c) => {
      const th = el("th", "st-sortable" + (c.num ? " st-num-col" : ""), c.label);
      if (c.key === sortKey) th.appendChild(el("span", "st-arrow", sortDesc ? " ▼" : " ▲"));
      th.addEventListener("click", () => { if (sortKey === c.key) sortDesc = !sortDesc; else { sortKey = c.key; sortDesc = c.key === "state" || c.key === "problems"; } renderHead(); renderBody(); });
      head.appendChild(th);
      const td = el("th", "st-filter");
      const input = el("input", "form-control form-control-sm");
      input.type = "search"; input.placeholder = "фильтр"; input.value = filters[c.key] || ""; input.setAttribute("aria-label", "Фильтр: " + c.label);
      input.addEventListener("input", () => { filters[c.key] = input.value.trim().toLowerCase(); renderBody(); });
      td.appendChild(input); filt.appendChild(td);
    });
  }

  function detailRow(r) {
    const tr = el("tr", "st-details");
    const td = el("td"); td.colSpan = columns.length;
    const panel = el("div", "st-panel");
    const grid = el("div", "st-grid");
    const block = (title, pairs) => {
      const box = el("div", "st-block"); box.appendChild(el("h3", "", title));
      const dl = el("dl");
      pairs.forEach(([k, v]) => { if (v === null || v === undefined || v === "") return; dl.appendChild(el("dt", "", k)); dl.appendChild(el("dd", "", v)); });
      if (dl.childElementCount) { box.appendChild(dl); grid.appendChild(box); }
    };
    const yes = (v) => v === null || v === undefined ? "" : (v ? "да" : "нет");
    block("Станция", [["Номер", r.station_id], ["Серийный номер", r.serial], ["Партия", r.lot], ["Участок", r.tenant],
      ["В реестре", r.registry_status], ["Аппаратура", r.versions.hardware_rev],
      ["Положение", r.position ? fmt.num(r.position.lat, 5) + ", " + fmt.num(r.position.lon, 5) + " · " + fmt.num(r.position.alt_m, 0) + " м" : ""],
      ["Источник положения", r.position && r.position.source], ["Точность положения, м", r.position && r.position.accuracy_m]]);
    block("Связь", [["Последний heartbeat получен", fmt.stamp(r.received_us)], ["Время станции в нём", fmt.stamp(r.time_us)],
      ["Транспорт", r.route.transport], ["RSSI, дБм", r.route.rssi_dbm], ["SNR, дБ", r.route.snr_db], ["Переходов", r.route.hop_count],
      ["Оператор", r.cellular && r.cellular.registered_operator], ["APN", r.cellular && r.cellular.apn],
      ["Технология", r.cellular && r.cellular.access_technology], ["IMSI", r.cellular && r.cellular.imsi_redacted], ["ICCID", r.cellular && r.cellular.iccid_redacted]]);
    block("Питание", [["Заряд, %", r.power.battery_pct], ["Батарея, мВ", r.power.battery_mv], ["Солнечная панель, мВ", r.power.solar_mv],
      ["Температура, °C", r.power.temperature_c], ["Ток батареи, мА", r.power.battery_current_ma], ["Мощность, мВт", r.power.battery_power_mw]]);
    block("GNSS", [["Фиксация", r.gnss.fix_type], ["Спутники", r.gnss.satellites], ["HDOP", r.gnss.hdop], ["PPS", yes(r.gnss.pps_ok)],
      ["Доверие ко времени", r.gnss.time_trust], ["Доверие к положению", r.gnss.position_trust], ["Помеха", yes(r.gnss.jam)], ["Подмена", yes(r.gnss.spoof)]]);
    block("Версии", [["Прошивка", r.versions.firmware_ver], ["Образ (fw_version)", r.versions.fw_version], ["Состояние обновления", r.versions.fw_state],
      ["Другой банк", r.versions.fw_other_version], ["Модель", r.versions.model_ver], ["Параметры (версия)", r.versions.params_version],
      ["Сетевая настройка (версия)", r.versions.net_config_version], ["Состояние сетевой настройки", r.versions.net_state],
      ["Неудачная сетевая настройка", r.versions.net_failed_version], ["Ключ команд", r.versions.command_key_id]]);
    block("Детектор", [["Работает", fmt.uptime(r.detector.uptime_s)], ["Загрузка №", r.detector.boot_id], ["Причина перезагрузки", r.detector.reset_cause],
      ["Пропущено задач watchdog", r.detector.watchdog_missed_tasks], ["Самотесты (маска)", r.detector.selftest_failed_tests],
      ["Не доставлено", r.detector.outbox_pending], ["Окон", r.detector.windows], ["Окон потеряно", r.detector.windows_dropped],
      ["Событий отправлено", r.detector.events_emitted], ["Событий отклонено", r.detector.events_refused],
      ["Присутствие", r.detector.presence_level], ["Окно, макс. мс", r.detector.window_max_ms],
      ["Самотест", yes(r.self_test_ok)], ["Флаги", r.fault_flags.join(", ")]]);
    panel.appendChild(grid);
    if (r.heartbeat) {
      const pre = el("details", "st-raw"); pre.appendChild(el("summary", "", "Heartbeat целиком"));
      pre.appendChild(el("pre", "", JSON.stringify(r.heartbeat, null, 2))); panel.appendChild(pre);
    }
    panel.addEventListener("click", (e) => e.stopPropagation());   // reading the details does not close them
    td.appendChild(panel);
    tr.appendChild(td);
    return tr;
  }

  function renderOverview(rows) {
    const overview = $("st-overview");
    overview.replaceChildren();
    rows.forEach((r) => {
      const card = el("button", "st-station-card st-level-" + r.level);
      card.type = "button";
      card.setAttribute("aria-label", "Станция " + r.station_id + ", " + (STATE_TEXT[r.state] || r.state) + ". Открыть подробности");
      const top = el("span", "st-station-top");
      top.appendChild(el("strong", "", "№ " + r.station_id));
      top.appendChild(el("span", "st-badge st-" + r.state, STATE_TEXT[r.state] || r.state));
      card.appendChild(top);
      card.appendChild(el("span", "st-station-tenant", r.tenant || "Без участка"));
      card.appendChild(el("span", "st-station-seen", r.silence_s === null ? "Heartbeat: никогда" : "Heartbeat: " + fmt.ago(r.silence_s)));
      const metrics = el("span", "st-station-metrics");
      metrics.appendChild(el("span", "", "Батарея: " + (r.power.battery_pct === null ? "—" : r.power.battery_pct + " %")));
      metrics.appendChild(el("span", "", "GNSS: " + (r.gnss.fix_type ? "fix " + r.gnss.fix_type : "нет fix")));
      card.appendChild(metrics);
      const problem = r.problems.length ? r.problems[0].text + (r.problems.length > 1 ? " · ещё " + (r.problems.length - 1) : "") : "Замечаний нет";
      card.appendChild(el("span", "st-station-problem", problem));
      card.addEventListener("click", () => {
        open.add(r.station_id);
        setView("table");
        const row = [...$("st-body").querySelectorAll(".st-row")].find((node) => Number(node.dataset.id) === r.station_id);
        if (row) row.scrollIntoView({ behavior: "smooth", block: "center" });
      });
      overview.appendChild(card);
    });
  }

  function setView(mode) {
    viewMode = mode;
    $("st-overview").hidden = mode !== "cards";
    $("st-table-wrap").hidden = mode !== "table";
    for (const choice of ["cards", "table"]) {
      const button = $("st-view-" + choice);
      const active = mode === choice;
      button.classList.toggle("st-view-active", active);
      button.setAttribute("aria-pressed", String(active));
    }
    renderBody();
  }

  function renderBody() {
    const body = $("st-body"); body.replaceChildren();
    const rows = visible();
    renderOverview(rows);
    rows.forEach((r) => {
      const tr = el("tr", "st-row st-level-" + r.level);
      tr.dataset.id = r.station_id;
      columns.forEach((c) => {
        const td = el("td", (c.num ? "st-num-col" : "") + (c.wrap ? " st-wrap-cell" : ""));
        const v = c.cell ? c.cell(r) : c.value(r);
        if (v instanceof Node) td.appendChild(v); else td.textContent = v ?? "";
        tr.appendChild(td);
      });
      tr.addEventListener("click", () => { if (open.has(r.station_id)) open.delete(r.station_id); else open.add(r.station_id); renderBody(); });
      body.appendChild(tr);
      if (open.has(r.station_id)) body.appendChild(detailRow(r));
    });
    $("st-empty").hidden = rows.length > 0;
    $("st-shown").textContent = "показано " + rows.length + " из " + data.stations.length;
  }

  function renderSummary() {
    const pool = selectedTenant ? data.stations.filter((r) => r.tenant === selectedTenant) : data.stations;
    const s = selectedTenant ? {
      total: pool.length,
      online: pool.filter((r) => r.state === "online").length,
      late: pool.filter((r) => r.state === "late").length,
      lost: pool.filter((r) => r.state === "lost").length,
      never: pool.filter((r) => r.state === "never").length,
      alarm: pool.filter((r) => r.level === "alarm").length,
      warn: pool.filter((r) => r.level === "warn").length,
      battery_low: pool.filter((r) => r.problems.some((p) => p.code === "battery_low")).length,
      gnss: pool.filter((r) => r.problems.some((p) => /^(gnss_|position_|time_)/.test(p.code))).length,
      updating: pool.filter((r) => r.problems.some((p) => p.code === "fw_update" || p.code === "net_trial")).length,
    } : (data.summary || {});
    document.querySelectorAll("#st-summary .st-num").forEach((n) => { n.textContent = s[n.dataset.key] ?? "–"; });
    document.querySelectorAll("#st-summary .st-card").forEach((b) => b.classList.toggle("st-active", b.dataset.filter === quick));
    const hours = (v) => v ? (v / 3600).toLocaleString("ru-RU", { maximumFractionDigits: 1 }) + " ч" : "";
    if (data.thresholds.late_s) { $("st-late").textContent = hours(data.thresholds.late_s); $("st-lost").textContent = hours(data.thresholds.lost_s); }
  }

  // ---- loading ----------------------------------------------------------------------------------------------------
  async function load() {
    $("st-status").textContent = "Обновление…";
    try {
      const res = await fetch("/api/v1/stations/health", { headers: { accept: "application/json" }, cache: "no-store" });
      if (!res.ok) throw new Error("HTTP " + res.status);
      data = await res.json(); receivedAt = Date.now();
      const tenantSelect = $("st-tenant");
      const tenants = [...new Set(data.stations.map((r) => r.tenant).filter(Boolean))].sort();
      tenantSelect.replaceChildren(new Option("Все доступные", ""));
      tenants.forEach((tenant) => tenantSelect.add(new Option(tenant === "bench" ? "bench · испытания" : tenant, tenant)));
      if (selectedTenant && !tenants.includes(selectedTenant)) selectedTenant = "";
      tenantSelect.value = selectedTenant;
      $("st-status").textContent = "Данные на " + new Date(data.now_us / 1000).toLocaleTimeString("ru-RU");
      $("st-status").classList.remove("st-error");
    } catch (err) {
      $("st-status").textContent = "Не удалось обновить: " + err.message;
      $("st-status").classList.add("st-error");
    }
    renderSummary(); renderBody();
  }

  document.querySelectorAll("#st-summary .st-card").forEach((b) => b.addEventListener("click", () => {
    quick = quick === b.dataset.filter ? "" : b.dataset.filter; renderSummary(); renderBody();
  }));
  $("st-reset").addEventListener("click", () => { filters = {}; quick = ""; renderHead(); renderSummary(); renderBody(); });
  $("st-tenant").addEventListener("change", (event) => { selectedTenant = event.target.value; renderSummary(); renderBody(); });
  $("st-view-cards").addEventListener("click", () => setView("cards"));
  $("st-view-table").addEventListener("click", () => setView("table"));
  $("st-refresh").addEventListener("click", load);
  document.addEventListener("visibilitychange", () => { if (!document.hidden) load(); });

  renderHead();
  setView("cards");
  load();
  setInterval(() => { if (!document.hidden) load(); else renderBody(); }, REFRESH_MS);
})();
