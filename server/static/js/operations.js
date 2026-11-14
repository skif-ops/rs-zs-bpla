/* Operator overview. Both APIs apply the account's station scope on the server. */
(() => {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const svgNS = "http://www.w3.org/2000/svg";
  const stateText = { online: "на связи", late: "опаздывает", lost: "потеряна", never: "не выходила" };
  const severity = { alarm: 3, warn: 2, info: 1, ok: 0 };
  let health = null, sources = null, tenant = "", loading = false;

  function el(tag, className, value) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (value !== undefined) node.textContent = String(value);
    return node;
  }
  function svg(tag, attrs = {}) {
    const node = document.createElementNS(svgNS, tag);
    Object.entries(attrs).forEach(([name, value]) => node.setAttribute(name, String(value)));
    return node;
  }
  function nameOf(r) {
    const twin = /^DIO-TWIN-(\d{3})$/.exec(r.serial || "");
    if (r.tenant === "bench" && twin && r.station_id === 9000 + Number(twin[1]))
      return "Двойник " + String(Number(twin[1])).padStart(2, "0") + " · ID " + r.station_id;
    return "Станция " + r.station_id;
  }
  function ago(s) {
    if (s == null) return "heartbeat не получен";
    if (s < 90) return Math.round(s) + " с назад";
    if (s < 5400) return Math.round(s / 60) + " мин назад";
    if (s < 172800) return Math.round(s / 3600) + " ч назад";
    return Math.round(s / 86400) + " сут назад";
  }
  function status(r) {
    if (r.state === "lost" || r.level === "alarm") return "alarm";
    if (r.state === "late" || r.level === "warn") return "warn";
    if (r.state === "never") return "unknown";
    return "ok";
  }
  function visible() { return (health?.stations || []).filter((r) => !tenant || r.tenant === tenant); }
  function visibleEvents() {
    const rows = sources?.events || [];
    if (!tenant) return rows;
    const ids = new Set(visible().map((r) => r.station_id));
    return rows.filter((e) => e.stations?.some((id) => ids.has(id)));
  }
  function visibleTracks() {
    const rows = sources?.tracks || [];
    if (!tenant) return rows;
    const ids = new Set(visible().map((r) => r.station_id));
    return rows.filter((t) => t.stations?.some((id) => ids.has(id)));
  }
  function drawSummary(rows, events) {
    $("ops-total").textContent = rows.length;
    $("ops-online").textContent = rows.filter((r) => r.state === "online").length;
    $("ops-attention").textContent = rows.filter((r) => status(r) === "alarm" || status(r) === "warn").length;
    $("ops-events-count").textContent = sources ? events.length : "—";
  }
  function drawMap(rows) {
    const map = $("ops-map"), empty = $("ops-map-empty");
    map.replaceChildren();
    for (let x = 80; x < 800; x += 80) map.appendChild(svg("line", { x1: x, y1: 0, x2: x, y2: 420, class: "ops-grid-line" }));
    for (let y = 60; y < 420; y += 60) map.appendChild(svg("line", { x1: 0, y1: y, x2: 800, y2: y, class: "ops-grid-line" }));
    const north = svg("text", { x: 760, y: 32, class: "ops-north" }); north.textContent = "↑ С"; map.appendChild(north);
    const located = rows.filter((r) => Number.isFinite(Number(r.position?.lat)) && Number.isFinite(Number(r.position?.lon)) &&
      r.position?.lat != null && r.position?.lon != null);
    if (!located.length) {
      empty.textContent = rows.length ? "У станций пока нет координат. Их состояние доступно в списке справа." : "В этом участке нет станций.";
      empty.hidden = false; return;
    }
    empty.hidden = true;
    const midLat = located.reduce((sum, r) => sum + Number(r.position.lat), 0) / located.length;
    const cos = Math.max(Math.cos(midLat * Math.PI / 180), 0.01);
    const points = located.map((r) => ({ r, x: Number(r.position.lon) * cos, y: Number(r.position.lat) }));
    const xs = points.map((p) => p.x), ys = points.map((p) => p.y);
    const minX = Math.min(...xs), maxX = Math.max(...xs), minY = Math.min(...ys), maxY = Math.max(...ys);
    const scale = Math.min(650 / Math.max(maxX - minX, 0.00005), 335 / Math.max(maxY - minY, 0.00005));
    const labels = points.length <= 12;
    for (const p of points) {
      const x = 400 + (p.x - (minX + maxX) / 2) * scale;
      const y = 210 - (p.y - (minY + maxY) / 2) * scale;
      const g = svg("g", { class: "ops-map-point ops-map-" + status(p.r), tabindex: 0, role: "link",
        "aria-label": nameOf(p.r) + ", " + (stateText[p.r.state] || p.r.state) + ". Открыть список станций" });
      const title = svg("title"); title.textContent = nameOf(p.r) + " · " + (stateText[p.r.state] || p.r.state); g.appendChild(title);
      g.appendChild(svg("circle", { cx: x, cy: y, r: 10 }));
      if (labels || status(p.r) !== "ok") {
        const text = svg("text", { x: x + 14, y: y + 5 }); text.textContent = String(p.r.station_id); g.appendChild(text);
      }
      const open = () => { location.href = "/stations"; };
      g.addEventListener("click", open);
      g.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); open(); } });
      map.appendChild(g);
    }
    if (located.length < rows.length) {
      const note = svg("text", { x: 18, y: 397, class: "ops-map-note" });
      note.textContent = "Без координат: " + (rows.length - located.length); map.appendChild(note);
    }
  }
  function drawAttention(rows) {
    const box = $("ops-attention-list"); box.replaceChildren();
    const attention = rows.filter((r) => status(r) === "alarm" || status(r) === "warn")
      .sort((a, b) => severity[b.level] - severity[a.level] || (b.silence_s ?? 0) - (a.silence_s ?? 0));
    if (!attention.length) { box.appendChild(el("p", "ops-list-empty", "По последним данным критичных замечаний нет.")); return; }
    attention.slice(0, 8).forEach((r) => {
      const a = el("a", "ops-attention-row ops-row-" + status(r)); a.href = "/stations";
      const top = el("span", "ops-row-top"); top.appendChild(el("strong", "", nameOf(r)));
      top.appendChild(el("span", "", stateText[r.state] || r.state)); a.appendChild(top);
      a.appendChild(el("span", "ops-row-reason", r.problems?.[0]?.text || (r.state === "lost" ? "Нет связи" : "Требуется проверка")));
      a.appendChild(el("small", "", (r.tenant || "Без участка") + " · " + ago(r.silence_s)));
      box.appendChild(a);
    });
    if (attention.length > 8) box.appendChild(el("p", "ops-list-more", "Ещё " + (attention.length - 8) + " — в полном списке станций."));
  }
  function drawEvents(events, tracks) {
    const box = $("ops-events-list"); box.replaceChildren();
    if (!sources) { box.appendChild(el("p", "ops-list-empty", "Не удалось получить события. Повторите обновление.")); return; }
    const items = [
      ...events.map((e) => ({ kind: "event", time: e.created_time_us || 0, data: e })),
      ...tracks.map((t) => ({ kind: "track", time: t.first_time_us || 0, data: t })),
    ].sort((a, b) => b.time - a.time).slice(0, 8);
    if (!items.length) { box.appendChild(el("p", "ops-list-empty", "Пока нет тревог, предупреждений и треков. Данные связи станций показаны выше.")); return; }
    items.forEach((item) => {
      const d = item.data, a = el("a", "ops-event-row" + (d.event_type === "AIR_ALERT" ? " ops-event-alarm" : ""));
      a.href = item.kind === "event" ? "/replay?event=" + encodeURIComponent(d.system_event_id) : "/replay?track=" + encodeURIComponent(d.track_id);
      a.appendChild(el("span", "ops-event-type", item.kind === "track" ? "Трек" : d.event_type === "AIR_ALERT" ? "Тревога" : "Предупреждение"));
      a.appendChild(el("strong", "", item.kind === "track" ? d.track_id : d.classification_label || "Цель не определена"));
      a.appendChild(el("span", "", (d.stations?.length ? "Станции " + d.stations.join(", ") : "Без списка станций") +
        (item.kind === "track" ? " · " + (d.points || 0) + " точек" : "")));
      a.appendChild(el("time", "", item.time ? new Date(item.time / 1000).toLocaleString("ru-RU") : "Время неизвестно"));
      box.appendChild(a);
    });
  }
  function draw() {
    const rows = visible(), events = visibleEvents();
    drawSummary(rows, events); drawMap(rows); drawAttention(rows); drawEvents(events, visibleTracks());
  }
  function updateTenantOptions() {
    const select = $("ops-tenant"), current = select.value;
    select.replaceChildren(new Option("Все доступные", ""));
    [...new Set(health.stations.map((r) => r.tenant).filter(Boolean))].sort().forEach((t) => select.add(new Option(t, t)));
    select.value = [...select.options].some((o) => o.value === current) ? current : "";
    tenant = select.value;
  }
  async function refresh() {
    if (loading) return;
    loading = true; $("ops-refresh").disabled = true;
    const results = await Promise.allSettled([
      fetch("/api/v1/stations/health", { cache: "no-store" }).then((r) => { if (!r.ok) throw Error(r.status); return r.json(); }),
      fetch("/api/v1/replay/sources", { cache: "no-store" }).then((r) => { if (!r.ok) throw Error(r.status); return r.json(); }),
    ]);
    const failures = [];
    if (results[0].status === "fulfilled") health = results[0].value;
    else { health = null; failures.push("состояние станций"); }
    if (results[1].status === "fulfilled") sources = results[1].value;
    else { sources = null; failures.push("события"); }
    if (health) updateTenantOptions();
    if (health) draw();
    else {
      ["ops-total", "ops-online", "ops-attention", "ops-events-count"].forEach((id) => $(id).textContent = "—");
      $("ops-map-empty").textContent = "Нет данных о станциях"; $("ops-map-empty").hidden = false;
      $("ops-attention-list").replaceChildren(el("p", "ops-list-empty", "Не удалось получить состояние станций."));
      drawEvents(sources?.events || [], sources?.tracks || []);
    }
    const error = $("ops-error"); error.hidden = !failures.length;
    if (failures.length) error.textContent = "Не удалось обновить " + failures.join(" и ") + ". Повторите попытку. Пустые показатели не означают нормальное состояние.";
    $("ops-updated").textContent = failures.length ? "Часть данных недоступна" : "Обновлено " + new Date().toLocaleTimeString("ru-RU");
    loading = false; $("ops-refresh").disabled = false;
  }
  $("ops-tenant").addEventListener("change", (e) => { tenant = e.target.value; if (health) draw(); });
  $("ops-refresh").addEventListener("click", refresh);
  refresh(); setInterval(refresh, 60000);
})();
