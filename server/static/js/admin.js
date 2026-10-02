/* Administration page: accounts (users.manage), station visibility (scopes.manage), the audit log (audit.read) and its
   switch (audit.control).  Every change asks for a code of the second factor (X-Second-Factor) and goes to the log. */
(() => {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const root = $("admin");
  const perms = new Set((root.dataset.permissions || "").split(",").filter(Boolean));
  const me = root.dataset.me;
  const ROLE_NAMES = { viewer: "наблюдатель", operator: "оператор", engineer: "инженер", admin: "администратор безопасности",
                       service: "сервисная", superuser: "суперпользователь" };
  const GRANTABLE = ["viewer", "operator", "engineer", "admin", "service"];
  const SCOPES = ["read", "audio.listen", "audio.request", "analysis.run", "dataset.edit", "station.command",
                  "station.firmware", "keys.rotate", "users.manage", "scopes.manage", "audit.read"];

  const el = (tag, attrs = {}, ...children) => {
    const e = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (k === "class") e.className = v;
      else if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
      else if (v !== undefined && v !== null && v !== false) e.setAttribute(k, v === true ? "" : v);
    }
    for (const c of children.flat()) e.append(c instanceof Node ? c : document.createTextNode(String(c)));
    return e;
  };
  const roleText = (roles) => roles.map((r) => ROLE_NAMES[r] || r).join(", ");
  const when = (t) => (t ? new Date(t * 1000).toISOString().replace("T", " ").slice(0, 19) : "—");

  function fail(message) {
    const box = $("admin-error");
    box.textContent = message;
    box.hidden = !message;
  }

  async function api(method, path, body, code) {
    const headers = { "content-type": "application/json" };
    if (code) headers["x-second-factor"] = code;
    const res = await fetch(path, { method, headers, body: body === undefined ? undefined : JSON.stringify(body),
                                    credentials: "same-origin" });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : `ошибка ${res.status}`);
    return data;
  }

  // A change: the dialog asks for the code (and anything extra), then the request is made.
  function confirmChange(text, extra) {
    return new Promise((resolve) => {
      const dialog = $("confirm-dialog");
      $("confirm-text").textContent = text;
      const box = $("confirm-extra");
      box.replaceChildren(...(extra || []));
      $("confirm-code").value = "";
      dialog.onclose = () => resolve(dialog.returnValue === "ok" ? $("confirm-code").value.replace(/\s/g, "") : null);
      dialog.showModal();
      (box.querySelector("input") || $("confirm-code")).focus();
    });
  }

  async function change(text, method, path, body, extra, makeBody) {
    const code = await confirmChange(text, extra);
    if (code === null) return null;
    try {
      fail("");
      return await api(method, path, makeBody ? makeBody() : body, code);
    } catch (e) {
      fail(e.message);
      return null;
    }
  }

  // ---- accounts ------------------------------------------------------------------------------------------------
  function roleBoxes(prefix, chosen) {
    return GRANTABLE.map((r) => el("label", { class: "admin-check" },
      el("input", { type: "checkbox", name: `${prefix}-role`, value: r, checked: chosen.includes(r) }), ` ${ROLE_NAMES[r]}`));
  }
  const checked = (scope, name) => [...scope.querySelectorAll(`input[name="${name}"]:checked`)].map((i) => i.value);

  async function loadAccounts() {
    if (!perms.has("users.manage")) return;
    let list;
    try {
      list = await api("GET", "/api/v1/admin/accounts");
    } catch (e) {
      fail(e.message);
      return;
    }
    const body = $("accounts-body");
    body.replaceChildren(...list.map((a) => {
      const state = [a.disabled ? "отключена" : "активна", a.must_change ? "ждёт смены пароля" : "",
                     a.second_factor ? "второй фактор есть" : (a.totp_at_login ? "второй фактор при входе" : "")].filter(Boolean);
      const where = [a.tenants.length ? `участки: ${a.tenants.join(", ")}` : "", a.stations.length ? `станции: ${a.stations.join(", ")}` : ""]
        .filter(Boolean).join("; ") || "все";
      const locked = a.superuser || a.name === me;
      const actions = locked ? [el("span", { class: "admin-note" }, a.superuser ? "управляет только сам" : "это вы")] : [
        el("button", { class: "btn btn-sm btn-outline-primary", type: "button", onclick: () => editRoles(a) }, "Роли"),
        el("button", { class: "btn btn-sm btn-outline-primary", type: "button", onclick: () => setDisabled(a) },
           a.disabled ? "Включить" : "Отключить"),
        el("button", { class: "btn btn-sm btn-outline-primary", type: "button", onclick: () => resetPassword(a) }, "Сброс пароля"),
        el("button", { class: "btn btn-sm btn-outline-primary", type: "button", onclick: () => resetTotp(a) }, "Сброс 2FA"),
        el("button", { class: "btn btn-sm btn-outline-primary", type: "button", onclick: () => logoutAll(a) }, "Завершить сессии"),
        el("button", { class: "btn btn-sm btn-outline-primary", type: "button", onclick: () => issueToken(a) }, "Токен"),
        el("button", { class: "btn btn-sm btn-outline-primary admin-danger", type: "button", onclick: () => removeAccount(a) }, "Удалить"),
      ];
      const tokens = a.tokens.map((t) => el("div", { class: "admin-token" },
        `токен ${t.id} «${t.label}»: ${(t.scopes || ["все права учётной записи"]).join(", ")}${t.expires ? `, до ${when(t.expires)}` : ""} `,
        locked ? "" : el("button", { class: "btn btn-sm btn-link admin-link", type: "button", onclick: () => revokeToken(t) }, "отозвать")));
      return el("tr", { class: a.disabled ? "admin-disabled" : "" },
        el("td", {}, a.name), el("td", {}, roleText(a.roles)), el("td", {}, state.join(", ")), el("td", {}, where),
        el("td", {}, String(a.sessions)), el("td", {}, el("div", { class: "admin-actions" }, actions, tokens)));
    }));
  }

  async function editRoles(a) {
    const boxes = roleBoxes("edit", a.roles);
    const done = await change(`Роли учётной записи ${a.name}:`, "PUT", `/api/v1/admin/accounts/${a.name}`, null,
      [el("div", { class: "admin-roles" }, boxes)], () => ({ roles: checked($("confirm-extra"), "edit-role") }));
    if (done) refresh();
  }

  async function setDisabled(a) {
    const done = await change(`${a.disabled ? "Включить" : "Отключить"} учётную запись ${a.name}?`, "PUT",
      `/api/v1/admin/accounts/${a.name}`, { disabled: !a.disabled });
    if (done) refresh();
  }

  async function resetPassword(a) {
    const input = el("input", { class: "form-control", type: "password", minlength: 12, autocomplete: "new-password" });
    const done = await change(`Временный пароль для ${a.name} (при входе пользователь сменит его):`, "POST",
      `/api/v1/admin/accounts/${a.name}/password`, null, [input], () => ({ password: input.value }));
    if (done) refresh();
  }

  async function resetTotp(a) {
    const done = await change(`Сбросить второй фактор ${a.name}? Новый ключ будет выдан при следующем входе.`, "POST",
      `/api/v1/admin/accounts/${a.name}/totp-reset`, {});
    if (done) refresh();
  }

  async function logoutAll(a) {
    const done = await change(`Завершить все сессии ${a.name}?`, "POST", `/api/v1/admin/accounts/${a.name}/logout`, {});
    if (done) refresh();
  }

  async function removeAccount(a) {
    const done = await change(`Удалить учётную запись ${a.name} и её токены?`, "DELETE", `/api/v1/admin/accounts/${a.name}`);
    if (done) refresh();
  }

  async function issueToken(a) {
    const label = el("input", { class: "form-control", placeholder: "назначение" });
    const days = el("input", { class: "form-control", type: "number", min: 1, max: 3650, placeholder: "срок, дней (пусто: бессрочно)" });
    const scopes = SCOPES.map((s) => el("label", { class: "admin-check" },
      el("input", { type: "checkbox", name: "token-scope", value: s, checked: s === "read" }), ` ${s}`));
    const done = await change(`Токен для скриптов учётной записи ${a.name} (не больше её прав):`, "POST",
      `/api/v1/admin/accounts/${a.name}/tokens`, null, [label, days, el("div", { class: "admin-roles" }, scopes)],
      () => ({ label: label.value, scopes: checked($("confirm-extra"), "token-scope"), expires_days: days.value ? Number(days.value) : null }));
    if (done) {
      window.prompt(`Токен ${done.id} показывается один раз. Скопируйте его:`, done.token);
      refresh();
    }
  }

  async function revokeToken(t) {
    const done = await change(`Отозвать токен ${t.id} «${t.label}»?`, "DELETE", `/api/v1/admin/tokens/${t.id}`);
    if (done) refresh();
  }

  if (perms.has("users.manage")) {
    $("new-roles").replaceChildren(...roleBoxes("new", ["operator"]));
    $("account-new").addEventListener("submit", async (ev) => {
      ev.preventDefault();
      const form = ev.target;
      const body = { name: form.name.value.trim(), password: form.password.value, roles: checked(form, "new-role") };
      const done = await change(`Создать учётную запись ${body.name} (${roleText(body.roles)})?`, "POST", "/api/v1/admin/accounts", body);
      if (done) {
        form.reset();
        $("new-roles").replaceChildren(...roleBoxes("new", ["operator"]));
        refresh();
      }
    });
  }

  // ---- visibility ----------------------------------------------------------------------------------------------
  async function loadScopes() {
    if (!perms.has("scopes.manage")) return;
    let list;
    try {
      list = await api("GET", "/api/v1/access/accounts");
    } catch (e) {
      fail(e.message);
      return;
    }
    $("scopes-body").replaceChildren(...list.map((a) => {
      const tenants = el("input", { class: "form-control form-control-sm", value: a.tenants.join(", ") });
      const stations = el("input", { class: "form-control form-control-sm", value: a.stations.join(", ") });
      const save = el("button", { class: "btn btn-sm btn-outline-primary", type: "button", onclick: async () => {
        const body = { tenants: tenants.value.split(",").map((s) => s.trim()).filter(Boolean),
                       stations: stations.value.split(",").map((s) => s.trim()).filter(Boolean).map(Number) };
        if (body.stations.some((n) => !Number.isInteger(n) || n <= 0)) { fail("Станции: номера через запятую."); return; }
        try {
          fail("");
          await api("PUT", `/api/v1/access/accounts/${a.name}/scope`, body);
          refresh();
        } catch (e) { fail(e.message); }
      } }, "Сохранить");
      return el("tr", {}, el("td", {}, a.name), el("td", {}, roleText(a.roles)), el("td", {}, tenants), el("td", {}, stations), el("td", {}, save));
    }));
    if (!list.length) $("scopes-body").replaceChildren(el("tr", {}, el("td", { colspan: 5, class: "text-muted" }, "нет учётных записей для настройки")));
  }

  // ---- audit ---------------------------------------------------------------------------------------------------
  async function loadAudit() {
    if (!perms.has("audit.read")) return;
    const q = new URLSearchParams({ limit: $("audit-limit").value });
    if ($("audit-actor").value.trim()) q.set("actor", $("audit-actor").value.trim());
    let data, logging;
    try {
      [data, logging] = await Promise.all([api("GET", "/api/v1/admin/audit?" + q), api("GET", "/api/v1/admin/audit-logging")]);
    } catch (e) {
      fail(e.message);
      return;
    }
    $("audit-chain").textContent = data.intact ? `Цепочка записей цела (${data.checked})` : `Цепочка НАРУШЕНА после записи ${data.checked}`;
    $("audit-chain").classList.toggle("admin-broken", !data.intact);
    $("admin-audit-off").hidden = logging.enabled;
    const label = logging.enabled ? "Журнал действий включён" : `Журнал действий выключен (${logging.changed_by}, ${when(logging.changed_at)})`;
    if ($("audit-logging")) {
      $("audit-logging").checked = logging.enabled;
      $("audit-logging").parentElement.lastChild.textContent = " " + label;
    }
    if ($("audit-logging-state")) $("audit-logging-state").textContent = label;
    $("audit-body").replaceChildren(...data.records.slice().reverse().map((r) => el("tr", {},
      el("td", {}, when(r.at)), el("td", {}, r.actor), el("td", {}, `${r.via}, ${r.address}`), el("td", {}, r.action),
      el("td", {}, r.target), el("td", {}, r.result), el("td", { class: "admin-detail" }, r.detail === "{}" ? "" : r.detail))));
  }

  if ($("audit-logging")) {
    $("audit-logging").addEventListener("change", async (ev) => {
      const enabled = ev.target.checked;
      ev.target.checked = !enabled;                     // until confirmed
      const done = await change(enabled ? "Включить журнал действий?" :
        "Выключить журнал действий? Входы и изменения перестанут записываться; само выключение будет записано.",
        "PUT", "/api/v1/admin/audit-logging", { enabled });
      if (done) refresh();
    });
  }
  if ($("audit-refresh")) $("audit-refresh").addEventListener("click", loadAudit);

  function refresh() {
    loadAccounts();
    loadScopes();
    loadAudit();
  }
  refresh();
})();
