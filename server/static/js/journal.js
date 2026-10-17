(() => {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const root = $("journal");
  const canConfirm = root?.dataset.canConfirm === "true";
  const dispositions = {
    pending: "Ожидает решения",
    confirmed_target: "Цель подтверждена",
    false_alarm: "Ложная тревога",
    technical_event: "Техническое событие",
  };
  const targetTypes = {
    uav_piston: "БПЛА с ДВС", uav_electric: "Электрический БПЛА", uav_jet: "Реактивный БПЛА",
    aircraft: "Самолёт", helicopter: "Вертолёт", other: "Другая цель", unknown: "Тип не определён",
    PISTON_UAV: "БПЛА с ДВС", ELECTRIC_UAV: "Электрический БПЛА", JET_UAV: "Реактивный БПЛА",
  };
  let entries = [], nextBefore = null, nextBeforeId = null, opened = new Set(), loading = false;

  function el(tag, className, value) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (value !== undefined) node.textContent = String(value);
    return node;
  }
  function fmtTime(us) { return us ? new Date(us / 1000).toLocaleString("ru-RU") : "-"; }
  function fmtDuration(e) {
    const end = e.ended_us || e.last_activity_us;
    if (!end || !e.started_us) return "-";
    const seconds = Math.max(0, Math.round((end - e.started_us) / 1e6));
    if (seconds < 60) return seconds + " с";
    if (seconds < 3600) return Math.floor(seconds / 60) + " мин " + seconds % 60 + " с";
    return Math.floor(seconds / 3600) + " ч " + Math.floor(seconds % 3600 / 60) + " мин";
  }
  function currentDisposition(e) { return e.decision?.disposition || "pending"; }
  function targetName(e) {
    const c = e.class || {};
    const raw = c.type || c.code || c.label || "unknown";
    return targetTypes[raw] || raw.replaceAll("_", " ");
  }
  function confidence(e) {
    const n = Number((e.class || {}).type_confidence ?? (e.class || {}).confidence);
    return Number.isFinite(n) ? Math.round(n * 100) + " %" : "-";
  }
  function visible() {
    const tenant = $("journal-tenant").value, decision = $("journal-decision").value;
    const level = $("journal-level").value, query = $("journal-search").value.trim().toLocaleLowerCase("ru");
    return entries.filter((e) => {
      if (tenant && e.tenant !== tenant) return false;
      if (decision && currentDisposition(e) !== decision) return false;
      if (level && e.level !== level) return false;
      if (!query) return true;
      const text = [e.alert_id, e.tenant, ...(e.stations || []), ...(e.tracks || []), targetName(e), e.decision?.actor,
        e.decision?.comment, dispositions[currentDisposition(e)]].filter(Boolean).join(" ").toLocaleLowerCase("ru");
      return text.includes(query);
    });
  }
  function summary() {
    const counts = { pending: 0, confirmed_target: 0, false_alarm: 0, technical_event: 0 };
    entries.forEach((e) => { counts[currentDisposition(e)] += 1; });
    $("journal-total").textContent = entries.length;
    $("journal-pending").textContent = counts.pending;
    $("journal-confirmed").textContent = counts.confirmed_target;
    $("journal-false").textContent = counts.false_alarm;
    $("journal-technical").textContent = counts.technical_event;
  }
  function tenants() {
    const select = $("journal-tenant"), current = select.value;
    select.replaceChildren(new Option("Все доступные", ""));
    [...new Set(entries.map((e) => e.tenant).filter(Boolean))].sort().forEach((t) => select.add(new Option(t, t)));
    select.value = [...select.options].some((o) => o.value === current) ? current : "";
  }
  function field(label, value) {
    const box = el("div", "journal-field"); box.append(el("dt", "", label), el("dd", "", value)); return box;
  }
  function badgeCell(className, value) {
    const td = el("td", ""); td.appendChild(el("span", "journal-badge " + className, value)); return td;
  }
  function decisionForm(e, host) {
    if (!canConfirm) return;
    const form = el("form", "journal-decision-form");
    const title = el("h3", "", e.decision ? "Исправить решение" : "Решение оператора");
    const selectLabel = el("label", "", "Результат");
    const select = el("select", "form-control"); select.name = "disposition"; select.required = true;
    select.add(new Option("Выберите результат", ""));
    Object.entries(dispositions).filter(([key]) => key !== "pending").forEach(([key, label]) => select.add(new Option(label, key)));
    if (e.decision) select.value = e.decision.disposition;
    selectLabel.appendChild(select);
    const commentLabel = el("label", "journal-comment", "Комментарий");
    const comment = el("textarea", "form-control"); comment.name = "comment"; comment.maxLength = 2000; comment.rows = 3;
    comment.placeholder = "Обоснование обязательно для ложной тревоги и технического события";
    if (e.decision) comment.value = e.decision.comment || "";
    commentLabel.appendChild(comment);
    const note = el("p", "journal-form-note", "Изменение создаст новую ревизию. Предыдущие решения сохраняются.");
    const button = el("button", "btn btn-primary btn-sm", "Записать решение"); button.type = "submit";
    form.append(title, selectLabel, commentLabel, note, button);
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const disposition = select.value, text = comment.value.trim();
      if (!disposition) { select.focus(); return; }
      if (["false_alarm", "technical_event"].includes(disposition) && !text) { comment.setCustomValidity("Укажите обоснование"); comment.reportValidity(); return; }
      comment.setCustomValidity("");
      if (!confirm(`Записать решение «${dispositions[disposition]}» для ${e.alert_id}?`)) return;
      button.disabled = true; button.textContent = "Запись...";
      try {
        const response = await fetch(`/api/v1/journal/${encodeURIComponent(e.alert_id)}/decision`, {
          method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ disposition, comment: text }),
        });
        const body = await response.json().catch(() => ({}));
        if (!response.ok) throw Error(body.detail || `HTTP ${response.status}`);
        e.decision = body.decision; opened.add(e.alert_id); render();
      } catch (error) {
        $("journal-error").textContent = "Не удалось записать решение: " + error.message; $("journal-error").hidden = false;
        button.disabled = false; button.textContent = "Записать решение";
      }
    });
    host.appendChild(form);
  }
  async function loadHistory(e, host) {
    const current = host.querySelector(".journal-history");
    if (current?.dataset.loaded === "true") return;
    try {
      const response = await fetch(`/api/v1/journal/${encodeURIComponent(e.alert_id)}`, { cache: "no-store" });
      if (!response.ok) throw Error(response.status);
      const full = await response.json(), history = current || el("div", "journal-history");
      history.replaceChildren(el("h3", "", "История решений"));
      if (!full.decisions?.length) history.appendChild(el("p", "journal-muted", "Решение ещё не записано."));
      else {
        const list = el("ol", "");
        full.decisions.slice().reverse().forEach((d) => {
          const item = el("li", "");
          item.appendChild(el("strong", "", dispositions[d.disposition] || d.disposition));
          item.appendChild(document.createTextNode(`, ${d.actor}, ${fmtTime(d.decided_us)}`));
          if (d.comment) item.appendChild(el("p", "", d.comment));
          list.appendChild(item);
        });
        history.appendChild(list);
      }
      history.dataset.loaded = "true";
      if (!current) host.appendChild(history);
    } catch (_) {
      if (current) current.textContent = "Не удалось загрузить историю решений.";
    }
  }
  function detailRow(e) {
    const tr = el("tr", "journal-details"), td = el("td", ""); td.colSpan = 8;
    const panel = el("div", "journal-details-panel");
    const facts = el("dl", "journal-facts");
    facts.append(field("Идентификатор", e.alert_id), field("Начало", fmtTime(e.started_us)),
      field("Завершение", e.ended_us ? fmtTime(e.ended_us) : "Эпизод активен"), field("Продолжительность", fmtDuration(e)),
      field("Станции", (e.stations || []).join(", ") || "-"), field("Класс", targetName(e) + ", " + confidence(e)));
    panel.appendChild(facts);
    const tracks = el("div", "journal-track-links");
    tracks.appendChild(el("strong", "", "Сопровождение: "));
    if (!e.tracks?.length) tracks.appendChild(document.createTextNode("общий трек не сформирован"));
    else e.tracks.forEach((id, index) => {
      if (index) tracks.appendChild(document.createTextNode(", "));
      const a = el("a", "", id); a.href = "/replay?track=" + encodeURIComponent(id); tracks.appendChild(a);
    });
    panel.appendChild(tracks);
    const history = el("div", "journal-history", "Загрузка истории..."); panel.appendChild(history);
    decisionForm(e, panel); td.appendChild(panel); tr.appendChild(td);
    loadHistory(e, panel); return tr;
  }
  function render() {
    const body = $("journal-body"); body.replaceChildren();
    const rows = visible();
    if (!rows.length) { const tr = el("tr", ""); const td = el("td", "journal-empty", "По выбранным условиям тревог нет."); td.colSpan = 8; tr.appendChild(td); body.appendChild(tr); return; }
    rows.forEach((e) => {
      const state = currentDisposition(e), tr = el("tr", `journal-row journal-row-${state}`); tr.tabIndex = 0;
      tr.setAttribute("role", "button"); tr.setAttribute("aria-expanded", opened.has(e.alert_id) ? "true" : "false");
      tr.append(el("td", "journal-time", fmtTime(e.started_us)), el("td", "", e.tenant || "-"),
        badgeCell(`journal-level-${e.level}`, e.level === "alert" ? "Тревога" : "Уточнение координат"),
        el("td", "", targetName(e)), el("td", "", (e.stations || []).join(", ") || "-"),
        el("td", "", e.tracks?.length || 0), badgeCell(`journal-decision-${state}`, dispositions[state]),
        el("td", "", e.decision?.actor || "-"));
      const toggle = () => { opened.has(e.alert_id) ? opened.delete(e.alert_id) : opened.add(e.alert_id); render(); };
      tr.addEventListener("click", toggle);
      tr.addEventListener("keydown", (event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); toggle(); } });
      body.appendChild(tr);
      if (opened.has(e.alert_id)) body.appendChild(detailRow(e));
    });
    document.querySelectorAll(".journal-details-panel").forEach((panel) => panel.addEventListener("click", (e) => e.stopPropagation()));
  }
  async function load(append = false) {
    if (loading) return; loading = true; $("journal-refresh").disabled = true; $("journal-error").hidden = true;
    const suffix = append && nextBefore ? `&before_us=${nextBefore}&before_id=${encodeURIComponent(nextBeforeId || "")}` : "";
    try {
      const response = await fetch("/api/v1/journal?limit=200" + suffix, { cache: "no-store" });
      if (!response.ok) throw Error(`HTTP ${response.status}`);
      const body = await response.json();
      entries = append ? entries.concat(body.entries || []) : (body.entries || []);
      nextBefore = body.next_before_us; nextBeforeId = body.next_before_id;
      tenants(); summary(); render(); $("journal-more").hidden = !nextBefore;
      $("journal-updated").textContent = "Обновлено " + new Date().toLocaleTimeString("ru-RU");
    } catch (error) {
      $("journal-error").textContent = "Не удалось загрузить журнал: " + error.message; $("journal-error").hidden = false;
      $("journal-updated").textContent = "Данные не обновлены";
    } finally { loading = false; $("journal-refresh").disabled = false; }
  }
  ["journal-tenant", "journal-decision", "journal-level"].forEach((id) => $(id).addEventListener("change", render));
  $("journal-search").addEventListener("input", render);
  $("journal-reset").addEventListener("click", () => {
    $("journal-tenant").value = ""; $("journal-decision").value = ""; $("journal-level").value = ""; $("journal-search").value = ""; render();
  });
  document.querySelectorAll(".journal-stat").forEach((button) => button.addEventListener("click", () => {
    $("journal-decision").value = button.dataset.quick || ""; render();
  }));
  $("journal-refresh").addEventListener("click", () => load(false));
  $("journal-more").addEventListener("click", () => load(true));
  load(false);
})();
