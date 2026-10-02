/* Replay of a target's movement without a map (decision 3): /api/v1/replay gives stations, fused track points and
   bearings in metres east/north around the stations; this page draws them on a canvas and plays the time. */
(() => {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const canvas = $("replay-canvas");
  const ctx = canvas.getContext("2d");
  const COLORS = ["#2563eb", "#d97706", "#059669", "#db2777", "#7c3aed", "#0891b2", "#65a30d", "#dc2626"];
  const TRACK_COLOR = "#111827";
  const RAY_M = 6000;              // rays drawn this long (beyond the 5 km fusion range)
  const RAY_HOLD_US = 1500000;     // a bearing is shown for this long after it was heard
  const GRID_STEPS = [25, 50, 100, 200, 500, 1000, 2000, 5000, 10000];

  let data = null;
  let byStation = new Map();       // station_id -> bearings sorted by time
  let t = 0;
  let playing = false;
  let lastFrame = 0;
  let lastWidth = 0;
  const view = { cx: 0, cy: 0, s: 0.1 };   // centre (m) and scale (px per m)
  let coverage = null;             // blind zones of the station geometry (/api/v1/geometry/coverage), pre-rendered

  const colorOf = (sid) => {
    const i = data ? data.stations.findIndex((s) => s.station_id === sid) : 0;
    return COLORS[(i < 0 ? sid : i) % COLORS.length];
  };

  // ---- sources -------------------------------------------------------------------------------------------------
  const fmtUtc = (us) => new Date(us / 1000).toISOString().replace("T", " ").slice(0, 21);

  async function loadSources() {
    const sel = $("replay-source");
    try {
      const res = await fetch("/api/v1/replay/sources");
      if (!res.ok) throw new Error(res.status);
      const src = await res.json();
      sel.innerHTML = '<option value="">— выберите —</option>';
      const tg = document.createElement("optgroup");
      tg.label = "Общие треки";
      for (const tr of src.tracks) {
        if (tr.first_time_us == null) continue;
        const o = document.createElement("option");
        o.value = "track_id=" + encodeURIComponent(tr.track_id);
        o.textContent = `${fmtUtc(tr.first_time_us)} · станции ${tr.stations.join(", ")} · ${tr.points} точек`;
        tg.appendChild(o);
      }
      if (tg.children.length) sel.appendChild(tg);
      const eg = document.createElement("optgroup");
      eg.label = "События";
      for (const ev of src.events) {
        const o = document.createElement("option");
        o.value = "system_event_id=" + encodeURIComponent(ev.system_event_id);
        o.textContent = `${fmtUtc(ev.created_time_us)} · ${ev.event_type === "AIR_ALERT" ? "тревога" : "предупреждение"} · ` +
          `${ev.classification_label || "?"} · станции ${ev.stations.join(", ")}`;
        eg.appendChild(o);
      }
      if (eg.children.length) sel.appendChild(eg);
      if (!tg.children.length && !eg.children.length) sel.innerHTML = '<option value="">нет треков и событий</option>';
    } catch (e) {
      sel.innerHTML = '<option value="">не удалось загрузить список</option>';
    }
    const q = new URLSearchParams(location.search);
    const pre = q.get("track") ? "track_id=" + encodeURIComponent(q.get("track"))
      : q.get("event") ? "system_event_id=" + encodeURIComponent(q.get("event")) : "";
    if (pre) {
      if (![...sel.options].some((o) => o.value === pre)) {
        const o = document.createElement("option");
        o.value = pre; o.textContent = decodeURIComponent(pre.split("=")[1]);
        sel.appendChild(o);
      }
      sel.value = pre;
      load(pre);
    }
  }

  async function load(query) {
    stop();
    if (!query) return;
    $("replay-empty").textContent = "Загрузка…";
    $("replay-empty").hidden = false;
    const res = await fetch("/api/v1/replay?" + query);
    if (!res.ok) {
      const msg = await res.json().catch(() => ({}));
      $("replay-empty").textContent = "Не удалось загрузить: " + (msg.detail || res.status);
      data = null; enableControls(false); draw();
      return;
    }
    data = await res.json();
    byStation = new Map();
    for (const b of data.bearings) {
      if (!byStation.has(b.station_id)) byStation.set(b.station_id, []);
      byStation.get(b.station_id).push(b);
    }
    for (const list of byStation.values()) list.sort((a, b) => a.t_us - b.t_us);
    const empty = !data.stations.length && !data.tracks.length;
    $("replay-empty").textContent = empty ? "В этом окне нет станций с координатами и точек." : "";
    $("replay-empty").hidden = !empty;
    const slider = $("replay-slider");
    slider.min = data.window.first_us;
    slider.max = data.window.last_us;
    slider.step = 100000;
    t = data.window.first_us;
    slider.value = t;
    enableControls(!empty);
    fit();
    draw();
    loadCoverage();
  }

  // ---- blind zones of the station geometry (decision 5) --------------------------------------------------------
  async function loadCoverage() {
    const on = $("replay-geometry").checked;
    $("replay-geometry-opts").hidden = !on;
    coverage = null;
    if (!on || !data || !data.origin || !data.stations.length) { $("replay-geo-share").textContent = ""; draw(); return; }
    const sig = data.bearings.map((b) => b.sigma_deg).filter((v) => v > 0).sort((a, b) => a - b);
    const q = new URLSearchParams({
      station_ids: data.stations.map((s) => s.station_id).join(","),
      range_m: Math.min(Math.max(Number($("replay-geo-range").value) || 2000, 100), 5000),
      height_m: Math.min(Math.max(Number($("replay-geo-height").value) || 0, 0), 5000),
      sigma_deg: sig.length ? sig[sig.length >> 1] : 3,
      origin_lat: data.origin.lat, origin_lon: data.origin.lon, origin_alt: data.origin.alt_msl_m,
    });
    const res = await fetch("/api/v1/geometry/coverage?" + q);
    if (!res.ok) { $("replay-geo-share").textContent = "Не удалось рассчитать зоны."; draw(); return; }
    const g = await res.json();
    const off = document.createElement("canvas");
    off.width = g.nx; off.height = g.ny;
    const octx = off.getContext("2d");
    const img = octx.createImageData(g.nx, g.ny);
    for (let i = 0; i < g.ny; i++) {
      for (let j = 0; j < g.nx; j++) {
        const k = i * g.nx + j, o = ((g.ny - 1 - i) * g.nx + j) * 4;      // row 0 is the southmost
        const c = g.codes.charCodeAt(k) - 48;
        let rgba = [0, 0, 0, 0];
        if (c === 1) rgba = [100, 116, 139, 40];
        else if (c === 2) rgba = [220, 38, 38, 60];
        else if (c === 3) {
          const err = g.h_err_m[k] == null ? g.max_error_m : g.h_err_m[k];
          rgba = [5, 150, 105, Math.round(25 + 55 * (1 - Math.min(err / g.max_error_m, 1)))];
        }
        img.data.set(rgba, o);
      }
    }
    octx.putImageData(img, 0, 0);
    coverage = { g, off };
    const pc = (v) => Math.round(v * 100) + " %";
    $("replay-geo-share").textContent = `Доля площади: точка ${pc(g.share.position)}, слепая геометрия ` +
      `${pc(g.share.blind_geometry)}, одна станция ${pc(g.share.single_station)}, не слышно ${pc(g.share.out_of_range)} ` +
      `(сигма ${Number(g.sigma_deg).toFixed(1)}°).`;
    draw();
  }

  function drawCoverage() {
    if (!coverage) return;
    const { g, off } = coverage;
    const left = sx(g.e0 - g.step_m / 2), top = sy(g.n0 - g.step_m / 2 + g.ny * g.step_m);
    ctx.save();
    ctx.imageSmoothingEnabled = false;
    ctx.drawImage(off, left, top, g.nx * g.step_m * view.s, g.ny * g.step_m * view.s);
    // the hearing zone of every station: a circle of the range at the target's height (2 km by the specification)
    const r = Math.sqrt(Math.max(g.range_m * g.range_m - g.height_m * g.height_m, 0)) * view.s;
    ctx.setLineDash([6, 5]);
    ctx.lineWidth = 1.2;
    ctx.font = "11px system-ui, sans-serif";
    for (const s of data.stations) {
      const x = sx(s.e), y = sy(s.n);
      ctx.strokeStyle = colorOf(s.station_id);
      ctx.globalAlpha = 0.8;
      ctx.beginPath(); ctx.arc(x, y, r, 0, 2 * Math.PI); ctx.stroke();
      ctx.globalAlpha = 1;
      ctx.fillStyle = colorOf(s.station_id);
      ctx.fillText(label(g.range_m), x + 4, y - r - 4);
    }
    ctx.restore();
  }

  function enableControls(on) {
    for (const id of ["replay-play", "replay-back", "replay-fwd", "replay-slider"]) $(id).disabled = !on;
  }

  // ---- view ----------------------------------------------------------------------------------------------------
  function resize() {
    const dpr = window.devicePixelRatio || 1;
    const w = canvas.clientWidth, h = canvas.clientHeight;
    if (lastWidth && w) view.s *= w / lastWidth;     // keep the same part of the plane in view
    lastWidth = w;
    canvas.width = Math.round(w * dpr);
    canvas.height = Math.round(h * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    draw();
  }

  function fit() {
    if (!data) return;
    const xs = [], ys = [];
    // with the station zones shown, the whole circles are fitted in
    const zr = $("replay-geometry").checked ? Math.min(Math.max(Number($("replay-geo-range").value) || 2000, 100), 5000) : 0;
    for (const s of data.stations) { xs.push(s.e - zr, s.e + zr); ys.push(s.n - zr, s.n + zr); }
    for (const tr of data.tracks) for (const p of tr.points) { xs.push(p.e); ys.push(p.n); }
    if (!xs.length) { xs.push(0); ys.push(0); }
    const minx = Math.min(...xs), maxx = Math.max(...xs), miny = Math.min(...ys), maxy = Math.max(...ys);
    const spanx = Math.max(maxx - minx, 400), spany = Math.max(maxy - miny, 400);
    view.cx = (minx + maxx) / 2;
    view.cy = (miny + maxy) / 2;
    view.s = (zr ? 0.92 : 0.8) * Math.min(canvas.clientWidth / spanx, canvas.clientHeight / spany);
  }

  const sx = (e) => canvas.clientWidth / 2 + (e - view.cx) * view.s;
  const sy = (n) => canvas.clientHeight / 2 - (n - view.cy) * view.s;

  // ---- state at time t -----------------------------------------------------------------------------------------
  function bearingAt(list, time) {
    let lo = 0, hi = list.length - 1, best = -1;
    while (lo <= hi) {
      const mid = (lo + hi) >> 1;
      if (list[mid].t_us <= time) { best = mid; lo = mid + 1; } else hi = mid - 1;
    }
    if (best < 0 || time - list[best].t_us > RAY_HOLD_US) return null;
    return list[best];
  }

  function pointAt(tr, time) {
    const pts = tr.points;
    if (!pts.length || time < pts[0].t_us || time > pts[pts.length - 1].t_us) return null;
    let i = 1;
    while (i < pts.length && pts[i].t_us < time) i++;
    if (i >= pts.length) return pts[pts.length - 1];
    const a = pts[i - 1], b = pts[i];
    const w = (time - a.t_us) / Math.max(b.t_us - a.t_us, 1);
    const mix = (k) => a[k] + w * (b[k] - a[k]);
    return { ...a, e: mix("e"), n: mix("n"), alt_msl_m: mix("alt_msl_m"), u: mix("u"), h_err_m: mix("h_err_m"), ve: mix("ve"),
             vn: mix("vn"), speed_mps: mix("speed_mps"), crossing_deg: mix("crossing_deg") };
  }

  // ---- drawing -------------------------------------------------------------------------------------------------
  function draw() {
    const w = canvas.clientWidth, h = canvas.clientHeight;
    ctx.clearRect(0, 0, w, h);
    ctx.fillStyle = "#f8fafc";
    ctx.fillRect(0, 0, w, h);
    if (data) drawCoverage();
    drawGrid(w, h);
    if (!data) return;
    drawBearings();
    drawStations();
    const current = drawTracks();
    drawNorth(w);
    updatePanel(current);
  }

  function drawGrid(w, h) {
    const step = GRID_STEPS.find((m) => m * view.s >= 70) || GRID_STEPS[GRID_STEPS.length - 1];
    const e0 = view.cx - w / 2 / view.s, e1 = view.cx + w / 2 / view.s;
    const n0 = view.cy - h / 2 / view.s, n1 = view.cy + h / 2 / view.s;
    ctx.lineWidth = 1;
    ctx.font = "11px system-ui, sans-serif";
    ctx.fillStyle = "#64748b";
    for (let e = Math.ceil(e0 / step) * step; e <= e1; e += step) {
      ctx.strokeStyle = e === 0 ? "#cbd5e1" : "#e2e8f0";
      ctx.beginPath(); ctx.moveTo(sx(e) + 0.5, 0); ctx.lineTo(sx(e) + 0.5, h); ctx.stroke();
      ctx.fillText(label(e), sx(e) + 3, h - 6);
    }
    for (let n = Math.ceil(n0 / step) * step; n <= n1; n += step) {
      ctx.strokeStyle = n === 0 ? "#cbd5e1" : "#e2e8f0";
      ctx.beginPath(); ctx.moveTo(0, sy(n) + 0.5); ctx.lineTo(w, sy(n) + 0.5); ctx.stroke();
      ctx.fillText(label(n), 4, sy(n) - 3);
    }
    // scale bar
    const px = step * view.s;
    ctx.strokeStyle = "#334155"; ctx.lineWidth = 2;
    ctx.beginPath(); ctx.moveTo(w - 20 - px, h - 30); ctx.lineTo(w - 20, h - 30); ctx.stroke();
    ctx.fillStyle = "#334155";
    ctx.fillText(label(step), w - 20 - px, h - 36);
  }

  const label = (m) => (Math.abs(m) >= 1000 ? (m / 1000).toFixed(m % 1000 ? 1 : 0) + " км" : m + " м");

  function drawNorth(w) {
    const x = w - 28, y = 34;
    ctx.fillStyle = "#334155";
    ctx.beginPath(); ctx.moveTo(x, y - 16); ctx.lineTo(x - 6, y); ctx.lineTo(x + 6, y); ctx.closePath(); ctx.fill();
    ctx.font = "bold 12px system-ui, sans-serif";
    ctx.fillText("С", x - 4, y + 14);
  }

  function drawStations() {
    ctx.font = "12px system-ui, sans-serif";
    for (const s of data.stations) {
      const x = sx(s.e), y = sy(s.n);
      ctx.fillStyle = colorOf(s.station_id);
      ctx.strokeStyle = "#fff"; ctx.lineWidth = 2;
      ctx.beginPath(); ctx.moveTo(x, y - 9); ctx.lineTo(x - 8, y + 6); ctx.lineTo(x + 8, y + 6); ctx.closePath();
      ctx.fill(); ctx.stroke();
      ctx.fillStyle = "#0f172a";
      ctx.fillText("ст. " + s.station_id, x + 10, y + 4);
    }
  }

  function drawBearings() {
    for (const s of data.stations) {
      const b = bearingAt(byStation.get(s.station_id) || [], t);
      if (!b) continue;
      const a = (b.azimuth_deg * Math.PI) / 180, sg = (Math.max(b.sigma_deg, 0.5) * Math.PI) / 180;
      const x = sx(s.e), y = sy(s.n), r = RAY_M * view.s;
      const col = colorOf(s.station_id);
      ctx.globalAlpha = 0.13;
      ctx.fillStyle = col;
      ctx.beginPath(); ctx.moveTo(x, y);
      ctx.lineTo(x + r * Math.sin(a - sg), y - r * Math.cos(a - sg));
      ctx.lineTo(x + r * Math.sin(a + sg), y - r * Math.cos(a + sg));
      ctx.closePath(); ctx.fill();
      ctx.globalAlpha = 0.9;
      ctx.strokeStyle = col; ctx.lineWidth = 1.5;
      ctx.beginPath(); ctx.moveTo(x, y); ctx.lineTo(x + r * Math.sin(a), y - r * Math.cos(a)); ctx.stroke();
      ctx.globalAlpha = 1;
    }
  }

  function drawTracks() {
    let current = null;
    for (const tr of data.tracks) {
      const past = tr.points.filter((p) => p.t_us <= t);
      // the whole track faint, the part already flown solid
      ctx.strokeStyle = "rgba(17,24,39,.18)"; ctx.lineWidth = 1; ctx.setLineDash([4, 4]);
      polyline(tr.points); ctx.setLineDash([]);
      ctx.strokeStyle = TRACK_COLOR; ctx.lineWidth = 2;
      polyline(past);
      ctx.fillStyle = TRACK_COLOR;
      for (const p of past) { ctx.beginPath(); ctx.arc(sx(p.e), sy(p.n), 1.8, 0, 2 * Math.PI); ctx.fill(); }
      const p = pointAt(tr, t);
      if (!p) continue;
      const x = sx(p.e), y = sy(p.n);
      ctx.strokeStyle = "rgba(220,38,38,.55)"; ctx.fillStyle = "rgba(220,38,38,.10)"; ctx.lineWidth = 1;
      ctx.beginPath(); ctx.arc(x, y, Math.max(p.h_err_m * view.s, 3), 0, 2 * Math.PI); ctx.fill(); ctx.stroke();
      ctx.strokeStyle = "#dc2626"; ctx.lineWidth = 2;          // where it will be in 10 s
      ctx.beginPath(); ctx.moveTo(x, y); ctx.lineTo(x + p.ve * 10 * view.s, y - p.vn * 10 * view.s); ctx.stroke();
      ctx.fillStyle = "#dc2626";
      ctx.beginPath(); ctx.arc(x, y, 5, 0, 2 * Math.PI); ctx.fill();
      ctx.fillStyle = "#0f172a"; ctx.font = "12px system-ui, sans-serif";
      const tag = `${Math.round(p.u)} м · ${Math.round(p.speed_mps * 3.6)} км/ч`;
      const tw = ctx.measureText(tag).width;
      ctx.fillText(tag, x + 9 + tw > canvas.clientWidth - 4 ? x - 9 - tw : x + 9, y - 8);
      if (!current) current = p;
    }
    if (current && $("replay-follow").checked) { view.cx = current.e; view.cy = current.n; }
    return current;
  }

  function polyline(pts) {
    if (pts.length < 2) return;
    ctx.beginPath(); ctx.moveTo(sx(pts[0].e), sy(pts[0].n));
    for (const p of pts.slice(1)) ctx.lineTo(sx(p.e), sy(p.n));
    ctx.stroke();
  }

  // ---- panel ---------------------------------------------------------------------------------------------------
  function updatePanel(p) {
    $("ro-utc").textContent = fmtUtc(t);
    $("ro-rel").textContent = ((t - data.window.first_us) / 1e6).toFixed(1) + " с";
    const set = (id, v) => { $(id).textContent = v; };
    if (p) {
      set("ro-alt", `${Math.round(p.u)} м ±${Math.round(p.v_err_m)} над станциями (${Math.round(p.alt_msl_m)} м над морем)`);
      set("ro-speed", `${p.speed_mps.toFixed(1)} м/с · ${Math.round(p.speed_mps * 3.6)} км/ч`);
      set("ro-course", p.speed_mps > 0.5 ? `${Math.round(p.course_deg)}°` : "—");
      set("ro-err", `±${Math.round(p.h_err_m)} м`);
      set("ro-stations", p.stations.join(", "));
      set("ro-crossing", `${Math.round(p.crossing_deg)}°`);
    } else {
      for (const id of ["ro-alt", "ro-speed", "ro-course", "ro-err", "ro-stations", "ro-crossing"]) set(id, "—");
    }
    const ul = $("ro-bearings");
    ul.innerHTML = "";
    for (const s of data.stations) {
      const b = bearingAt(byStation.get(s.station_id) || [], t);
      const li = document.createElement("li");
      const dot = document.createElement("span");
      dot.className = "replay-dot"; dot.style.background = colorOf(s.station_id);
      li.appendChild(dot);
      li.appendChild(document.createTextNode(b
        ? ` ст. ${s.station_id}: ${b.azimuth_deg.toFixed(1)}° (±${b.sigma_deg.toFixed(1)}), угол места ${b.elevation_deg.toFixed(1)}°`
        : ` ст. ${s.station_id}: не слышит`));
      ul.appendChild(li);
    }
    if (!data.stations.length) ul.innerHTML = '<li class="text-muted">—</li>';
  }

  // ---- playback ------------------------------------------------------------------------------------------------
  function setTime(v) {
    if (!data) return;
    t = Math.min(Math.max(v, data.window.first_us), data.window.last_us);
    $("replay-slider").value = t;
    draw();
  }

  function frame(now) {
    if (!playing) return;
    const dt = lastFrame ? now - lastFrame : 0;
    lastFrame = now;
    setTime(t + dt * 1000 * Number($("replay-speed").value));
    if (t >= data.window.last_us) { stop(); return; }
    requestAnimationFrame(frame);
  }

  function play() {
    if (!data) return;
    if (t >= data.window.last_us) t = data.window.first_us;
    playing = true; lastFrame = 0;
    $("replay-play").textContent = "❚❚ Пауза";
    requestAnimationFrame(frame);
  }

  function stop() {
    playing = false;
    $("replay-play").textContent = "▶ Пуск";
  }

  // ---- input ---------------------------------------------------------------------------------------------------
  $("replay-source").addEventListener("change", (e) => load(e.target.value));
  $("replay-play").addEventListener("click", () => (playing ? stop() : play()));
  $("replay-back").addEventListener("click", () => setTime(t - 1e6));
  $("replay-fwd").addEventListener("click", () => setTime(t + 1e6));
  $("replay-slider").addEventListener("input", (e) => { stop(); setTime(Number(e.target.value)); });
  $("replay-follow").addEventListener("change", draw);
  $("replay-geometry").addEventListener("change", loadCoverage);
  $("replay-geo-range").addEventListener("change", loadCoverage);
  $("replay-geo-height").addEventListener("change", loadCoverage);
  document.addEventListener("keydown", (e) => {
    const tag = document.activeElement ? document.activeElement.tagName : "";
    if (!data || ["INPUT", "SELECT", "TEXTAREA", "BUTTON"].includes(tag)) return;   // their own keys stay theirs
    if (e.key === " ") { e.preventDefault(); playing ? stop() : play(); }
    else if (e.key === "ArrowLeft") setTime(t - 1e6);
    else if (e.key === "ArrowRight") setTime(t + 1e6);
  });
  canvas.addEventListener("wheel", (e) => {
    e.preventDefault();
    const r = canvas.getBoundingClientRect();
    const mx = e.clientX - r.left, my = e.clientY - r.top;
    const we = view.cx + (mx - canvas.clientWidth / 2) / view.s, wn = view.cy - (my - canvas.clientHeight / 2) / view.s;
    view.s *= e.deltaY < 0 ? 1.15 : 1 / 1.15;
    view.cx = we - (mx - canvas.clientWidth / 2) / view.s;
    view.cy = wn + (my - canvas.clientHeight / 2) / view.s;
    draw();
  }, { passive: false });
  let drag = null;
  canvas.addEventListener("pointerdown", (e) => { drag = { x: e.clientX, y: e.clientY, cx: view.cx, cy: view.cy }; canvas.setPointerCapture(e.pointerId); });
  canvas.addEventListener("pointermove", (e) => {
    if (!drag) return;
    view.cx = drag.cx - (e.clientX - drag.x) / view.s;
    view.cy = drag.cy + (e.clientY - drag.y) / view.s;
    draw();
  });
  canvas.addEventListener("pointerup", () => { drag = null; });
  canvas.addEventListener("dblclick", () => { fit(); draw(); });
  new ResizeObserver(resize).observe(canvas);

  loadSources();
})();
