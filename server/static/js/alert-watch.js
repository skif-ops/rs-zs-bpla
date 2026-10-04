/* A fresh alert at level 'alert' takes the operator to live tracking. Warnings never force navigation. */
(() => {
  "use strict";
  const name = document.body.dataset.operatorName || "operator";
  const key = "muhoed-alert-cursor:" + name;
  const seenKey = "muhoed-opened-alerts:" + name;
  let hasBaseline = sessionStorage.getItem(key) !== null;
  let cursor = Number(sessionStorage.getItem(key)) || 0;
  let opened;
  try { opened = JSON.parse(sessionStorage.getItem(seenKey) || "[]"); } catch { opened = []; }
  if (!Array.isArray(opened)) opened = [];
  let retries = 0, socket = null, retryTimer = null, pollBusy = false, lastFrameAt = 0;
  const badge = document.getElementById("alert-channel-status");
  function status(text, kind = "") {
    if (!badge) return;
    badge.textContent = "Оповещения: " + text;
    badge.className = "alert-channel-status" + (kind ? " is-" + kind : "");
  }

  function onMessage(msg) {
    if (msg.schema !== "dioneya.alert/1") return;
    if (Number.isSafeInteger(msg.seq) && msg.seq > cursor) {
      cursor = msg.seq; hasBaseline = true; sessionStorage.setItem(key, String(cursor));
    }
    window.dispatchEvent(new CustomEvent("muhoed:alert-message", { detail: msg }));
    if (!((msg.type === "alert.start" || msg.type === "alert.update") && msg.alert?.level === "alert" && msg.alert_id)) return;
    const created = Date.parse(msg.created);
    if (!Number.isFinite(created) || Math.abs(Date.now() - created) > 150000) return;
    if (opened.includes(msg.alert_id)) return;
    opened.push(msg.alert_id); opened = opened.slice(-30);
    sessionStorage.setItem(seenKey, JSON.stringify(opened));
    const params = new URLSearchParams({ live: "1", alert: msg.alert_id, tenant: msg.tenant || "" });
    const track = msg.alert.tracks?.[0];
    if (track) params.set("track", track);
    const started = Date.parse(msg.alert.started || msg.time);
    if (Number.isFinite(started)) params.set("since", String(started * 1000));
    const stations = (msg.alert.stations || []).map((s) => Number(s.station_id)).filter(Number.isSafeInteger);
    if (stations.length) params.set("stations", stations.join(","));
    const target = "/replay?" + params;
    if (location.pathname !== "/replay" || new URLSearchParams(location.search).get("alert") !== msg.alert_id)
      location.assign(target);
  }
  function connect() {
    if (socket && (socket.readyState === 0 || socket.readyState === 1)) return;
    const params = new URLSearchParams({ heartbeat_s: "10" });
    if (hasBaseline) params.set("after_seq", String(cursor));
    try { socket = new WebSocket((location.protocol === "https:" ? "wss://" : "ws://") + location.host + "/api/v1/alerts/stream?" + params); }
    catch { scheduleReconnect(); return; }
    socket.addEventListener("open", () => { retries = 0; lastFrameAt = Date.now(); status("на связи"); });
    socket.addEventListener("message", (e) => { lastFrameAt = Date.now(); try { onMessage(JSON.parse(e.data)); } catch { /* malformed frame */ } });
    socket.addEventListener("close", (e) => {
      if (e.code === 4401 || e.code === 4403) { status("нужен повторный вход", "disconnected"); return; }
      status("резервный опрос", "polling");
      poll(); scheduleReconnect();
    });
  }
  function scheduleReconnect() {
    if (document.hidden || retryTimer) return;
    retryTimer = setTimeout(() => { retryTimer = null; connect(); }, Math.min(30000, 1000 * 2 ** Math.min(retries++, 5)));
  }
  async function poll() {
    if (pollBusy || document.hidden || (socket && socket.readyState === 1)) return;
    pollBusy = true;
    try {
      const res = await fetch("/api/v1/alerts?after_seq=" + cursor + "&limit=200", { cache: "no-store" });
      if (!res.ok) throw Error(res.status);
      const data = await res.json();
      (data.messages || []).forEach(onMessage);
      if (Number.isSafeInteger(data.next_after_seq) && data.next_after_seq > cursor) {
        cursor = data.next_after_seq; sessionStorage.setItem(key, String(cursor)); hasBaseline = true;
      }
      status("резервный опрос", "polling");
    } catch { status("нет связи", "disconnected"); }
    finally { pollBusy = false; }
  }
  async function start() {
    if (!hasBaseline) {
      try {
        const res = await fetch("/api/v1/alerts/head", { cache: "no-store" });
        if (res.ok) {
          const head = await res.json();
          if (Number.isSafeInteger(head.seq) && head.seq >= 0) {
            cursor = head.seq; hasBaseline = true; sessionStorage.setItem(key, String(cursor));
          }
        }
      } catch { /* live stream can still receive new messages */ }
    }
    connect();
  }
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden && (!socket || socket.readyState === WebSocket.CLOSED)) { connect(); poll(); }
  });
  setInterval(poll, 5000);
  setInterval(() => {
    if (socket && socket.readyState === 1 && Date.now() - lastFrameAt > 30000) socket.close();
  }, 5000);
  start();
})();
