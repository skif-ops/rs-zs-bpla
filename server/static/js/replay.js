/* Replay of a target's movement without a map (decision 3): /api/v1/replay gives stations, fused track points and
   bearings in metres east/north around the stations; this page draws them on a canvas and plays the time. */
(() => {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const canvas = $("replay-canvas");
  const ctx = canvas.getContext("2d");
  const COLORS = ["#2563eb", "#d97706", "#059669", "#db2777", "#7c3aed", "#0891b2", "#65a30d", "#dc2626"];
  const TARGET_COLORS = ["#dc2626", "#7c3aed", "#059669", "#d97706", "#0891b2", "#db2777"];
  const RAY_M = 6000;              // rays drawn this long (beyond the 5 km fusion range)
  const RAY_HOLD_US = 1500000;     // a bearing is shown for this long after it was heard
  const LIVE_TRACK_HOLD_US = 3000000; // concurrently updated targets can differ by a few fusion ticks
  const LIVE_ACTIVITY_HOLD_MS = 4000; // same current-alert window as the station status page
  const LIVE_BEARING_HOLD_MS = 6000;  // a fresh associated bearing keeps a target while fusion catches up
  const LIVE_VISUAL_FADE_MS = 1500;   // a silent target fades instead of leaving one frozen final frame
  const LIVE_SEARCH_HOLD_MS = 8000;   // after the last evidence, distinguish a short search from quiet monitoring
  const LIVE_MAX_PIPELINE_MS = 15000; // acoustic travel at 5 km plus bounded fusion time
  const LIVE_EPISODE_GAP_US = 7000000; // a quiet interval separates adjacent controlled or real flight episodes
  const GRID_STEPS = [25, 50, 100, 200, 500, 1000, 2000, 5000, 10000];

  let data = null;
  let byStation = new Map();       // station_id -> bearings sorted by time
  let t = 0;
  let playing = false;
  let lastFrame = 0;
  let lastWidth = 0;
  const view = { cx: 0, cy: 0, s: 0.1 };   // centre (m) and scale (px per m)
  let coverage = null;             // blind zones of the station geometry (/api/v1/geometry/coverage), pre-rendered
  let coverageRequest = 0;         // rejects a response calculated for an older live geometry
  let coveragePendingKey = "";
  const pageQuery = new URLSearchParams(location.search);
  const liveAlertId = pageQuery.get("live") === "1" ? pageQuery.get("alert") : null;
  let liveActive = !!liveAlertId;
  let liveFollowing = liveActive;
  let liveLoading = false;
  let liveSince = Number(pageQuery.get("since")) || Date.now() * 1000 - 5 * 60 * 1e6;
  let livePrerollUs = pageQuery.get("segment") === "1" ? 2e6 : 15e6;
  let liveLastTrackUs = 0;
  let liveEpisodeStartUs = liveSince;
  const liveTrackUntil = new Map();       // track_id -> local receipt-time expiry
  const liveTrackLastPoint = new Map();   // track_id -> newest point already observed by this page
  const liveTrackLastBearing = new Map(); // track_id -> newest associated bearing time (station arrival time)
  const TARGET_CLASS_NAMES = {
    uav_piston: "Поршневой БПЛА",
    uav_jet: "Реактивный БПЛА",
    uav_electric: "Электрический БПЛА",
    aircraft: "Самолёт",
    helicopter: "Вертолёт",
    other: "Воздушная цель",
    unknown: "Тип уточняется",
  };
  let liveLastEvidenceAt = 0;             // newest point receipt or bearing time, in browser milliseconds
  let liveHasConfirmedTrack = !!pageQuery.get("track"); // confirmation persists through short calculation gaps
  let liveStations = pageQuery.get("stations") || "";
  let liveTenant = pageQuery.get("tenant") || "";

  const colorOf = (sid) => {
    const i = data ? data.stations.findIndex((s) => s.station_id === sid) : 0;
    return COLORS[(i < 0 ? sid : i) % COLORS.length];
  };

  // ---- sources -------------------------------------------------------------------------------------------------
  const fmtUtc = (us) => Number.isFinite(Number(us)) ? new Date(Number(us) / 1000).toISOString().replace("T", " ").slice(0, 21) : "—";

  function liveQuery() {
    const until = Date.now() * 1000;
    const since = Math.max(Math.min(liveSince - livePrerollUs, until - 1e6), until - 29 * 60 * 1e6);
    const q = new URLSearchParams({ since_us: String(Math.round(since)), until_us: String(Math.round(until)) });
    // The account scope already limits the operator to the bench tenant.  Do
    // not freeze the request to the stations present in alert.start: more
    // stations and tracks may join the same alert episode later.
    return q.toString();
  }

  function liveDefaults() {
    $("replay-speed").value = "1";
    $("replay-follow").checked = true;
    $("replay-geometry").checked = true;
  }

  function beginLiveEpisode(startUs, clearScene) {
    liveEpisodeStartUs = startUs;
    liveSince = startUs;
    livePrerollUs = 2e6;
    liveFollowing = true;
    liveLastTrackUs = 0;
    liveTrackUntil.clear(); liveTrackLastPoint.clear(); liveTrackLastBearing.clear();
    liveLastEvidenceAt = 0;
    liveHasConfirmedTrack = false;
    if (!clearScene) return;
    data = null; byStation = new Map(); invalidateCoverage();
    $("replay-empty").textContent = "Начинается новый эпизод…";
    $("replay-empty").hidden = false;
    draw();
  }

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
    if (liveActive) {
      liveDefaults();
      const o = document.createElement("option");
      o.value = "live"; o.textContent = "Текущая тревога" + (liveTenant ? " · " + liveTenant : "");
      sel.prepend(o); sel.value = "live";
      $("replay-live-state").hidden = false;
      $("replay-context").textContent = "Тревога на участке " + (liveTenant || "—") + ". Данные обновляются автоматически; север вверху, восток справа.";
      $("replay-source-help").textContent = "Поступающие пеленги и точки показываются автоматически. Для просмотра истории выберите другую запись.";
      $("replay-now").hidden = false;
      load(liveQuery());
      setInterval(refreshLive, 4000);
      return;
    }
    const pre = pageQuery.get("track") ? "track_id=" + encodeURIComponent(pageQuery.get("track"))
      : pageQuery.get("event") ? "system_event_id=" + encodeURIComponent(pageQuery.get("event")) : "";
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

  async function load(query, updating = false) {
    if (!updating) stop();
    if (!query) return;
    if (!updating) { $("replay-empty").textContent = "Загрузка…"; $("replay-empty").hidden = false; }
    let res;
    try { res = await fetch("/api/v1/replay?" + query, { cache: "no-store" }); }
    catch { res = null; }
    if (!res) {
      if (!updating) { $("replay-empty").textContent = "Не удалось связаться с сервером."; data = null; enableControls(false); draw(); }
      else $("replay-live-state").textContent = "● Связь с сервером потеряна";
      return;
    }
    if (!res.ok) {
      const msg = await res.json().catch(() => ({}));
      if (!updating) { $("replay-empty").textContent = "Не удалось загрузить: " + (msg.detail || res.status); data = null; enableControls(false); draw(); }
      else $("replay-live-state").textContent = "● Не удалось обновить сопровождение";
      return;
    }
    const hadPositions = !!(data && (data.stations.length || data.tracks.length));
    data = await res.json();
    if (liveActive) $("replay-live-state").textContent = "● Тревога · обновляется";
    if (liveActive) {
      const newest = Number(data.window.target_last_us) || 0;
      const episodeFirst = Number(data.window.episode_first_us) || 0;
      if (episodeFirst) {
        const delta = episodeFirst - liveEpisodeStartUs;
        // The API reconstructs the boundary from persisted points.  This is
        // the recovery path when a loaded page missed the boundary WebSocket
        // message (for example while another tab was open or fusion was busy).
        if (delta > LIVE_EPISODE_GAP_US) beginLiveEpisode(episodeFirst, false);
        else if (Math.abs(delta) <= LIVE_EPISODE_GAP_US) liveEpisodeStartUs = episodeFirst;
      }
      liveLastTrackUs = Math.max(liveLastTrackUs, newest);
      const now = Date.now();
      const newestBearingByTrack = new Map();
      for (const bearing of data.bearings) {
        if (!bearing.track_id) continue;
        newestBearingByTrack.set(bearing.track_id,
          Math.max(newestBearingByTrack.get(bearing.track_id) || 0, Number(bearing.t_us) || 0));
      }
      for (const track of data.tracks) {
        const pointUs = Number(track.points[track.points.length - 1]?.t_us) || 0;
        const previous = liveTrackLastPoint.get(track.track_id) || 0;
        // Several targets are fused on neighbouring ticks.  Only the tracks at the live edge of the window are
        // current; older tracks remain in the response for history and must not reappear as active.
        const ageMs = now - pointUs / 1000;
        if (pointUs && ageMs >= 0 && ageMs <= LIVE_MAX_PIPELINE_MS
          && pointUs >= newest - LIVE_TRACK_HOLD_US && pointUs > previous) {
          liveTrackUntil.set(track.track_id, now + LIVE_ACTIVITY_HOLD_MS);
          liveLastEvidenceAt = Math.max(liveLastEvidenceAt, now);
          liveHasConfirmedTrack = true;
        }
        if (pointUs > previous) liveTrackLastPoint.set(track.track_id, pointUs);
        // Multi-target fusion can publish points in bursts even while the stations keep sending bearings.  The
        // replay response relates every bearing to its fused target; use that independent evidence to bridge the
        // calculation gap.  The expiry is based on the bearing timestamp, so a stopped target is never prolonged by
        // repeatedly fetching the same historical sample.
        const bearingUs = newestBearingByTrack.get(track.track_id) || 0;
        const previousBearing = liveTrackLastBearing.get(track.track_id) || 0;
        const bearingAgeMs = now - bearingUs / 1000;
        if (bearingUs > previousBearing && bearingAgeMs >= -2000 && bearingAgeMs <= LIVE_MAX_PIPELINE_MS) {
          liveTrackLastBearing.set(track.track_id, bearingUs);
          liveTrackUntil.set(track.track_id, Math.max(liveTrackUntil.get(track.track_id) || 0,
            bearingUs / 1000 + LIVE_BEARING_HOLD_MS));
          liveLastEvidenceAt = Math.max(liveLastEvidenceAt, bearingUs / 1000);
        }
      }
    }
    byStation = new Map();
    for (const b of data.bearings) {
      if (!byStation.has(b.station_id)) byStation.set(b.station_id, []);
      byStation.get(b.station_id).push(b);
    }
    for (const list of byStation.values()) list.sort((a, b) => a.t_us - b.t_us);
    const empty = !data.stations.length && !data.tracks.length && !data.bearings.length;
    $("replay-empty").textContent = empty ? (liveActive ? "Ожидаем пеленги и точки трека по этой тревоге." : "В этой записи пока нет пеленгов и точек с координатами.") : "";
    $("replay-empty").hidden = !empty;
    const slider = $("replay-slider");
    const first = data.window.first_us ?? data.window.since_us;
    const last = data.window.last_us ?? data.window.until_us;
    data.window.first_us = first; data.window.last_us = last;
    slider.min = first;
    slider.max = last;
    slider.step = 100000;
    t = liveActive && liveFollowing ? (data.window.target_last_us ?? last)
      : updating ? Math.min(Math.max(t, first), last) : first;
    slider.value = t;
    $("replay-time-start").textContent = fmtUtc(first).slice(11, 19);
    $("replay-time-end").textContent = fmtUtc(last).slice(11, 19);
    $("replay-selection-title").textContent = liveActive ? "Тревога · " + (liveTenant || "участок") :
      $("replay-source").selectedOptions[0]?.textContent || "Сопровождение";
    enableControls(!empty);
    if (!updating || !hadPositions) fit();
    // A live response can introduce a new station group and a new local ENU origin.  Keep the coverage raster tied
    // to that exact geometry even during background refreshes; a page switch must never be required to restore it.
    loadCoverage();
    draw();
  }

  async function refreshLive() {
    if (!liveActive || liveLoading) return;
    liveLoading = true;
    try { await load(liveQuery(), true); } finally { liveLoading = false; }
  }

  // ---- blind zones of the station geometry (decision 5) --------------------------------------------------------
  function invalidateCoverage() {
    coverageRequest += 1;
    coveragePendingKey = "";
    coverage = null;
  }

  function coverageSpec() {
    if (!$('replay-geometry').checked || !data || !data.origin || !data.stations.length) return null;
    const range = Math.min(Math.max(Number($("replay-geo-range").value) || 2000, 100), 5000);
    const height = Math.min(Math.max(Number($("replay-geo-height").value) || 0, 0), 5000);
    const sigmas = data.bearings.map((b) => b.sigma_deg).filter((v) => v > 0).sort((a, b) => a - b);
    const sigma = Math.round((sigmas.length ? sigmas[sigmas.length >> 1] : 3) * 10) / 10;
    const stations = data.stations.map((station) => ({ ...station }));
    const origin = { ...data.origin };
    // The endpoint's raster uses the supplied origin, while the outlined circles use station ENU coordinates.
    // Both therefore belong to one immutable snapshot.  The key also prevents a request on every four-second poll.
    const key = JSON.stringify({
      station_ids: stations.map((station) => station.station_id),
      station_enu: stations.map((station) => [station.station_id, station.e, station.n]),
      origin: [origin.lat, origin.lon, origin.alt_msl_m], range, height, sigma,
    });
    return { key, range, height, sigma, stations, origin };
  }

  async function loadCoverage() {
    const on = $("replay-geometry").checked;
    $("replay-geometry-opts").hidden = !on;
    const spec = coverageSpec();
    if (!spec) {
      invalidateCoverage();
      $("replay-geo-share").textContent = "";
      draw();
      return;
    }
    if (coverage?.key === spec.key || coveragePendingKey === spec.key) return;
    const requestId = ++coverageRequest;
    coveragePendingKey = spec.key;
    coverage = null;
    $("replay-geo-share").textContent = "Расчёт зон…";
    draw();
    const q = new URLSearchParams({
      station_ids: spec.stations.map((station) => station.station_id).join(","),
      range_m: spec.range,
      height_m: spec.height,
      sigma_deg: spec.sigma,
      origin_lat: spec.origin.lat, origin_lon: spec.origin.lon, origin_alt: spec.origin.alt_msl_m,
    });
    let res;
    try { res = await fetch("/api/v1/geometry/coverage?" + q, { cache: "no-store" }); }
    catch { res = null; }
    // The operator may already be watching another station group.  Never combine an old raster with new circles.
    if (requestId !== coverageRequest || coverageSpec()?.key !== spec.key) return;
    coveragePendingKey = "";
    if (!res || !res.ok) { $("replay-geo-share").textContent = "Не удалось рассчитать зоны."; draw(); return; }
    const g = await res.json();
    if (requestId !== coverageRequest || coverageSpec()?.key !== spec.key) return;
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
    coverage = { g, off, key: spec.key, stations: spec.stations };
    const pc = (v) => Math.round(v * 100) + " %";
    $("replay-geo-share").textContent = `Доля площади: точка ${pc(g.share.position)}, слепая геометрия ` +
      `${pc(g.share.blind_geometry)}, одна станция ${pc(g.share.single_station)}, не слышно ${pc(g.share.out_of_range)} ` +
      `(сигма ${Number(g.sigma_deg).toFixed(1)}°).`;
    draw();
  }

  function drawCoverage() {
    if (!coverage) return;
    const { g, off, stations } = coverage;
    const left = sx(g.e0 - g.step_m / 2), top = sy(g.n0 - g.step_m / 2 + g.ny * g.step_m);
    ctx.save();
    ctx.imageSmoothingEnabled = false;
    ctx.drawImage(off, left, top, g.nx * g.step_m * view.s, g.ny * g.step_m * view.s);
    // the hearing zone of every station: a circle of the range at the target's height (2 km by the specification)
    const r = Math.sqrt(Math.max(g.range_m * g.range_m - g.height_m * g.height_m, 0)) * view.s;
    ctx.setLineDash([6, 5]);
    ctx.lineWidth = 1.2;
    ctx.font = "11px system-ui, sans-serif";
    for (const s of stations) {
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
  function bearingsAt(list, time) {
    // One station can report one bearing stream per target.  Keep the newest sample from every stream instead of
    // keeping only the station's newest sample, which hid all but one target.
    const latest = new Map();
    for (const b of list) {
      if (b.t_us > time) break;
      if (time - b.t_us <= RAY_HOLD_US) latest.set(b.bearing_key || String(b.track_event_id), b);
    }
    return [...latest.values()];
  }

  function bearingTargetIndex(bearing) {
    return bearing.track_id ? data.tracks.findIndex((track) => track.track_id === bearing.track_id) : -1;
  }

  function bearingColor(bearing) {
    const index = bearingTargetIndex(bearing);
    return index >= 0 ? TARGET_COLORS[index % TARGET_COLORS.length] : colorOf(bearing.station_id);
  }

  function pointAt(tr, time) {
    const pts = tr.points;
    if (!pts.length || time < pts[0].t_us) return null;
    // In live mode the newest targets are fused in separate ticks.  Keep a target on its latest point for a
    // short interval so all simultaneous targets remain visible at one common target-time cursor.
    if (time > pts[pts.length - 1].t_us)
      return liveActive && time - pts[pts.length - 1].t_us <= LIVE_TRACK_HOLD_US ? pts[pts.length - 1] : null;
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
    const now = Date.now();
    const active = data ? data.tracks.map((tr, index) => {
      const until = liveTrackUntil.get(tr.track_id) || 0;
      const freshness = !liveActive ? 1 : Math.max(0, Math.min(1, (until - now) / LIVE_VISUAL_FADE_MS));
      return { tr, index, point: pointAt(tr, t), freshness };
    }).filter((x) => x.point && (!liveActive || (liveTrackUntil.get(x.tr.track_id) || 0) > now)) : [];
    if (active.length && $("replay-follow").checked) focusActiveTargets(active);
    ctx.clearRect(0, 0, w, h);
    ctx.fillStyle = "#f8fafc";
    ctx.fillRect(0, 0, w, h);
    if (data) drawCoverage();
    drawGrid(w, h);
    if (!data) return;
    drawBearings(active);
    drawStations();
    const current = drawTracks(active);
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

  function targetClassification(track) {
    const klass = track.class || {};
    const known = !!klass.code && klass.code !== "unknown";
    const exactType = klass.type && klass.type !== "UNKNOWN" ? klass.type : null;
    const identified = known || !!exactType;
    const className = TARGET_CLASS_NAMES[klass.code] || (known && klass.label && klass.label !== "UNKNOWN" ? klass.label : TARGET_CLASS_NAMES.unknown);
    const classConfidence = Number.isFinite(Number(klass.confidence)) ? Number(klass.confidence) : 0;
    const typeConfidence = Number.isFinite(Number(klass.type_confidence)) ? Number(klass.type_confidence) : classConfidence;
    const confidence = Math.max(0, Math.min(1, exactType ? typeConfidence : classConfidence));
    const typeStatus = String(klass.type_status || "").toUpperCase();
    const status = !identified ? "не определена"
      : exactType && typeStatus === "STABLE" ? "подтверждено"
        : exactType && typeStatus === "PROVISIONAL" ? "предварительно"
          : confidence >= 0.8 ? "подтверждено" : confidence >= 0.55 ? "предварительно" : "низкая";
    return {
      label: exactType || className,
      confidence: identified ? `${Math.round(confidence * 100)}% · ${status}` : status,
    };
  }

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

  function drawBearings(active) {
    // The replay response deliberately retains history.  In live mode rays must disappear with the current targets,
    // using the same four-second receipt-time window that clears the station alarm badges.
    if (liveActive && !active.length) return;
    for (const s of data.stations) {
      for (const b of bearingsAt(byStation.get(s.station_id) || [], t)) {
        const a = (b.azimuth_deg * Math.PI) / 180, sg = (Math.max(b.sigma_deg, 0.5) * Math.PI) / 180;
        const x = sx(s.e), y = sy(s.n), r = RAY_M * view.s;
        const col = bearingColor(b);
        const targetIndex = bearingTargetIndex(b);
        const freshness = liveActive && targetIndex >= 0
          ? (active.find((item) => item.index === targetIndex)?.freshness || 0)
          : Math.max(0, ...active.map((item) => item.freshness));
        ctx.globalAlpha = 0.13 * freshness;
        ctx.fillStyle = col;
        ctx.beginPath(); ctx.moveTo(x, y);
        ctx.lineTo(x + r * Math.sin(a - sg), y - r * Math.cos(a - sg));
        ctx.lineTo(x + r * Math.sin(a + sg), y - r * Math.cos(a + sg));
        ctx.closePath(); ctx.fill();
        ctx.globalAlpha = 0.9 * freshness;
        ctx.strokeStyle = col; ctx.lineWidth = 1.5;
        ctx.beginPath(); ctx.moveTo(x, y); ctx.lineTo(x + r * Math.sin(a), y - r * Math.cos(a)); ctx.stroke();
        ctx.globalAlpha = 1;
      }
    }
  }

  function drawTracks(active) {
    const visible = liveActive ? active : data.tracks.map((tr, index) => ({ tr, index, point: pointAt(tr, t) }));
    for (const item of visible) {
      const { index, tr } = item;
      const color = TARGET_COLORS[index % TARGET_COLORS.length];
      const past = tr.points.filter((p) => p.t_us <= t);
      const opacity = item.freshness ?? 1;
      // the whole track faint, the part already flown solid
      ctx.globalAlpha = 0.25 * opacity; ctx.strokeStyle = color; ctx.lineWidth = 1; ctx.setLineDash([4, 4]);
      polyline(tr.points); ctx.setLineDash([]);
      ctx.globalAlpha = opacity; ctx.strokeStyle = color; ctx.lineWidth = 2;
      polyline(past);
      ctx.fillStyle = color;
      for (const p of past) { ctx.beginPath(); ctx.arc(sx(p.e), sy(p.n), 1.8, 0, 2 * Math.PI); ctx.fill(); }
      const p = item.point;
      if (!p) continue;
      const x = sx(p.e), y = sy(p.n);
      ctx.globalAlpha = 0.10 * opacity; ctx.fillStyle = color;
      ctx.beginPath(); ctx.arc(x, y, Math.max(p.h_err_m * view.s, 3), 0, 2 * Math.PI); ctx.fill();
      ctx.globalAlpha = 0.55 * opacity; ctx.strokeStyle = color; ctx.lineWidth = 1; ctx.stroke();
      ctx.globalAlpha = opacity; ctx.strokeStyle = color; ctx.lineWidth = 2;          // where it will be in 10 s
      ctx.beginPath(); ctx.moveTo(x, y); ctx.lineTo(x + p.ve * 10 * view.s, y - p.vn * 10 * view.s); ctx.stroke();
      ctx.fillStyle = color;
      ctx.beginPath(); ctx.arc(x, y, 5, 0, 2 * Math.PI); ctx.fill();
      ctx.fillStyle = "#0f172a"; ctx.font = "12px system-ui, sans-serif";
      const prefix = active.length > 1 ? `цель ${active.findIndex((x) => x.tr.track_id === tr.track_id) + 1} · ` : "";
      const classification = targetClassification(tr);
      const tag = `${prefix}${classification.label} · ${Math.round(p.u)} м · ${Math.round(p.speed_mps * 3.6)} км/ч`;
      const tw = ctx.measureText(tag).width;
      ctx.fillText(tag, x + 9 + tw > canvas.clientWidth - 4 ? x - 9 - tw : x + 9, y - 8);
      ctx.globalAlpha = 1;
    }
    return active;
  }

  function focusActiveTargets(active) {
    if (active.length === 1) {
      view.cx = active[0].point.e;
      view.cy = active[0].point.n;
      return;
    }
    const stationIds = new Set(active.flatMap((item) => item.point.stations || []));
    const xs = active.map((item) => item.point.e);
    const ys = active.map((item) => item.point.n);
    for (const station of data.stations) {
      if (stationIds.has(station.station_id)) { xs.push(station.e); ys.push(station.n); }
    }
    const minx = Math.min(...xs), maxx = Math.max(...xs), miny = Math.min(...ys), maxy = Math.max(...ys);
    const spanx = Math.max(maxx - minx, 600), spany = Math.max(maxy - miny, 600);
    view.cx = (minx + maxx) / 2;
    view.cy = (miny + maxy) / 2;
    view.s = 0.72 * Math.min(canvas.clientWidth / spanx, canvas.clientHeight / spany);
  }

  function polyline(pts) {
    if (pts.length < 2) return;
    ctx.beginPath(); ctx.moveTo(sx(pts[0].e), sy(pts[0].n));
    for (const p of pts.slice(1)) ctx.lineTo(sx(p.e), sy(p.n));
    ctx.stroke();
  }

  // ---- panel ---------------------------------------------------------------------------------------------------
  function updatePanel(active) {
    if (liveActive) {
      if (active.length) {
        const targetText = ` · целей сейчас: ${active.length}`;
        $("replay-live-state").textContent = "● Тревога · сопровождение" + targetText;
        $("replay-selection-title").textContent = "Тревога · " + (liveTenant || "участок") + targetText;
      } else {
        const recentlySeen = liveLastEvidenceAt && Date.now() - liveLastEvidenceAt <= LIVE_SEARCH_HOLD_MS;
        $("replay-live-state").textContent = recentlySeen && !liveHasConfirmedTrack
          ? "● Тревога · уточнение координат"
          : recentlySeen ? "● Поиск целей · анализ продолжается"
            : "● Контроль участка · активных целей нет";
        $("replay-selection-title").textContent = "Тревога · " + (liveTenant || "участок") + " · активных целей нет";
      }
    }
    $("ro-utc").textContent = fmtUtc(t);
    $("replay-current-time").textContent = fmtUtc(t) + " UTC";
    const relativeStart = liveActive && liveEpisodeStartUs ? liveEpisodeStartUs : data.window.first_us;
    $("ro-rel").textContent = (Math.max(0, t - relativeStart) / 1e6).toFixed(1) + " с";
    const targetBody = $("replay-target-body");
    targetBody.replaceChildren();
    if (!active.length) {
      const row = document.createElement("tr");
      const cell = document.createElement("td");
      cell.colSpan = 9; cell.className = "text-muted"; cell.textContent = "Активных целей в текущий момент нет";
      row.appendChild(cell); targetBody.appendChild(row);
    }
    active.forEach((item, position) => {
      const p = item.point;
      const row = document.createElement("tr");
      const target = document.createElement("th");
      target.scope = "row";
      const dot = document.createElement("span");
      dot.className = "replay-dot"; dot.style.background = TARGET_COLORS[item.index % TARGET_COLORS.length];
      target.appendChild(dot);
      target.appendChild(document.createTextNode(` Цель ${position + 1}`));
      row.appendChild(target);
      const classification = targetClassification(item.tr);
      const values = [
        classification.label,
        classification.confidence,
        `${Math.round(p.u)} м ±${Math.round(p.v_err_m)}`,
        `${p.speed_mps.toFixed(1)} м/с · ${Math.round(p.speed_mps * 3.6)} км/ч`,
        p.speed_mps > 0.5 ? `${Math.round(p.course_deg)}°` : "—",
        `±${Math.round(p.h_err_m)} м`,
        p.stations.join(", "),
        `${Math.round(p.crossing_deg)}°`,
      ];
      for (const value of values) {
        const cell = document.createElement("td"); cell.textContent = value; row.appendChild(cell);
      }
      targetBody.appendChild(row);
    });
    const ul = $("ro-bearings");
    ul.innerHTML = "";
    for (const s of data.stations) {
      const current = liveActive && !active.length ? [] : bearingsAt(byStation.get(s.station_id) || [], t);
      if (!current.length) {
        const li = document.createElement("li");
        li.textContent = `ст. ${s.station_id}: не слышит`;
        ul.appendChild(li);
        continue;
      }
      for (const b of current) {
        const target = bearingTargetIndex(b);
        const li = document.createElement("li");
        const dot = document.createElement("span");
        dot.className = "replay-dot"; dot.style.background = bearingColor(b);
        li.appendChild(dot);
        li.appendChild(document.createTextNode(
          ` ст. ${s.station_id}${target >= 0 ? ` → цель ${target + 1}` : ""}: ` +
          `${b.azimuth_deg.toFixed(1)}° (±${b.sigma_deg.toFixed(1)}), угол места ${b.elevation_deg.toFixed(1)}°`,
        ));
        ul.appendChild(li);
      }
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

  function userSetTime(v) {
    if (liveActive) liveFollowing = false;
    stop(); setTime(v);
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
  $("replay-source").addEventListener("change", (e) => {
    liveActive = e.target.value === "live";
    if (liveActive) { liveDefaults(); liveFollowing = true; $("replay-live-state").hidden = false; $("replay-now").hidden = false; load(liveQuery()); }
    else { $("replay-live-state").hidden = true; $("replay-now").hidden = true; load(e.target.value); }
  });
  $("replay-play").addEventListener("click", () => { if (liveActive) liveFollowing = false; playing ? stop() : play(); });
  $("replay-back").addEventListener("click", () => userSetTime(t - 1e6));
  $("replay-fwd").addEventListener("click", () => userSetTime(t + 1e6));
  $("replay-slider").addEventListener("input", (e) => userSetTime(Number(e.target.value)));
  $("replay-now").addEventListener("click", () => {
    liveFollowing = true; stop();
    if (data) setTime(data.window.target_last_us ?? data.window.last_us);
    refreshLive();
  });
  $("replay-follow").addEventListener("change", draw);
  $("replay-geometry").addEventListener("change", loadCoverage);
  $("replay-geo-range").addEventListener("change", loadCoverage);
  $("replay-geo-height").addEventListener("change", loadCoverage);
  document.addEventListener("keydown", (e) => {
    const tag = document.activeElement ? document.activeElement.tagName : "";
    if (!data || ["INPUT", "SELECT", "TEXTAREA", "BUTTON"].includes(tag)) return;   // their own keys stay theirs
    if (e.key === " ") { e.preventDefault(); if (liveActive) liveFollowing = false; playing ? stop() : play(); }
    else if (e.key === "ArrowLeft") userSetTime(t - 1e6);
    else if (e.key === "ArrowRight") userSetTime(t + 1e6);
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

  window.addEventListener("muhoed:alert-message", (event) => {
    const msg = event.detail;
    if (!liveActive || msg.alert_id !== liveAlertId) return;
    if (msg.type === "alert.end") {
      liveTrackUntil.clear(); liveTrackLastPoint.clear(); liveTrackLastBearing.clear();
      liveLastEvidenceAt = 0;
      liveHasConfirmedTrack = false;
      liveActive = false;
      $("replay-live-state").textContent = "● Тревога завершена · активных целей нет";
      $("replay-now").hidden = true;
      data = null; byStation = new Map(); invalidateCoverage();
      $("replay-empty").textContent = "Тревога завершилась.";
      $("replay-empty").hidden = false;
      draw();
      return;
    }
    if (msg.type === "track.update" && msg.live_current === true) {
      const pointUs = Date.parse(msg.time) * 1000;
      if (Number.isFinite(pointUs) && liveLastTrackUs && pointUs - liveLastTrackUs > LIVE_EPISODE_GAP_US) {
        beginLiveEpisode(pointUs, true);
      }
      if (Number.isFinite(pointUs)) {
        const receivedAt = Date.now();
        liveLastTrackUs = Math.max(liveLastTrackUs, pointUs);
        liveTrackLastPoint.set(msg.track.track_id, Math.max(liveTrackLastPoint.get(msg.track.track_id) || 0, pointUs));
        liveTrackUntil.set(msg.track.track_id, receivedAt + LIVE_ACTIVITY_HOLD_MS);
        liveLastEvidenceAt = Math.max(liveLastEvidenceAt, receivedAt);
        liveHasConfirmedTrack = true;
      }
    } else if (msg.type === "track.end" && msg.track?.track_id) {
      liveTrackUntil.delete(msg.track.track_id);
      liveTrackLastPoint.delete(msg.track.track_id);
      liveTrackLastBearing.delete(msg.track.track_id);
      draw();
    }
    if (msg.type === "bearing" || msg.type === "alert.update") liveLastEvidenceAt = Date.now();
    if (msg.alert?.stations?.length) liveStations = msg.alert.stations.map((s) => s.station_id).join(",");
    if (msg.type === "alert.update" || msg.type === "track.update" || msg.type === "bearing") refreshLive();
  });

  document.addEventListener("visibilitychange", () => {
    if (!document.hidden && liveActive) refreshLive();
  });

  setInterval(() => {
    if (!liveActive || !data) return;
    const now = Date.now();
    let expired = false, fading = false;
    for (const [trackId, until] of liveTrackUntil) {
      if (until <= now) { liveTrackUntil.delete(trackId); expired = true; }
      else if (until - now < LIVE_ACTIVITY_HOLD_MS - LIVE_VISUAL_FADE_MS) fading = true;
    }
    if (expired || fading) draw();
  }, 500);

  loadSources();
})();
