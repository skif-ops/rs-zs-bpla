"""The /admin page and its API (station/admin_api.py, docs/SERVER_ACCESS_CONTROL_2026-10-02.md §9): each part for the
permission it needs, account changes from a browser session confirmed by the second factor, nobody manages their own
account or skif_root, a token never carries more than its issuer may do, and the audit log with its chain check."""
from station import operator_auth as oa
from tests.test_operator_auth import ORIGIN, PASSWORD, auth, client, code_now, enrolled, login  # noqa: F401
from tests.test_superuser import NEW, field, first_login

API = "/api/v1/admin"


def session(app, store, name: str, roles: str):
    secret = enrolled(store, name, roles) if set(roles.split(",")) & oa.SECOND_FACTOR_ROLES else None
    if secret is None:
        store.add_user(name, roles, PASSWORD)
    c = client(app)
    assert login(c, name, code=code_now(secret) if secret else "").status_code == 303
    return c, secret


def confirm(secret: str) -> dict:
    return {**ORIGIN, "x-second-factor": code_now(secret)}


def test_the_page_shows_the_parts_the_account_may_use(auth):
    store, app = auth
    adm, _ = session(app, store, "ada", "admin")
    eng, _ = session(app, store, "eve", "engineer")
    ops, _ = session(app, store, "ops", "operator")
    page = adm.get("/admin").text
    assert 'id="panel-accounts"' in page and 'id="panel-scopes"' in page and 'id="panel-audit"' in page
    assert 'id="audit-logging"' not in page                              # the switch is the superuser's
    page = eng.get("/admin").text
    assert 'id="panel-scopes"' in page and 'id="panel-accounts"' not in page and 'id="panel-audit"' not in page
    assert "нет прав администрирования" in ops.get("/admin").text
    assert 'href="/admin"' in adm.get("/single").text and 'href="/admin"' not in ops.get("/single").text
    root = client(app)
    first_login(root)
    assert 'id="audit-logging"' in root.get("/admin").text


def test_accounts_are_managed_from_a_session_confirmed_by_the_second_factor(auth):
    store, app = auth
    adm, secret = session(app, store, "ada", "admin")
    body = {"name": "nina", "roles": ["operator"], "password": "temporary password 1"}
    assert adm.post(f"{API}/accounts", json=body, headers=ORIGIN).status_code == 403          # no code
    assert adm.post(f"{API}/accounts", json=body, headers={**ORIGIN, "x-second-factor": "12ab56"}).status_code == 403
    assert store.user("nina") is None
    assert adm.post(f"{API}/accounts", json=body, headers=confirm(secret)).status_code == 200
    assert store.user("nina")["must_change"]
    r = login(client(app), "nina", "temporary password 1")             # the first login sets her own password
    assert r.status_code == 200 and 'action="/login/password"' in r.text
    eng = {"name": "egor", "roles": ["engineer"], "password": "temporary password 2"}
    assert adm.post(f"{API}/accounts", json=eng, headers=confirm(secret)).status_code == 200
    c = client(app)
    r = login(c, "egor", "temporary password 2")
    r = c.post("/login/password", data={"step": field(r.text, "step"), "new_password": NEW, "repeat": NEW}, headers=ORIGIN)
    assert r.status_code == 200 and 'action="/login/totp"' in r.text    # an engineer enrols the second factor there
    listing = {a["name"]: a for a in adm.get(f"{API}/accounts").json()}
    assert set(listing) >= {"ada", "nina", "egor", oa.SUPERUSER_NAME} and listing["ada"]["sessions"] == 1
    assert "password" not in str(listing) and "totp\"" not in str(listing)
    # roles, disabling, resets, sessions
    assert adm.put(f"{API}/accounts/nina", json={"roles": ["viewer", "operator"]}, headers=confirm(secret)).status_code == 200
    assert store.user("nina")["roles"] == ["viewer", "operator"]
    assert adm.put(f"{API}/accounts/nina", json={"roles": ["superuser"]}, headers=confirm(secret)).status_code == 422
    assert adm.put(f"{API}/accounts/nina", json={"roles": ["engineer"]}, headers=confirm(secret)).status_code == 200
    assert store.user("nina")["totp_at_login"]                           # a new engineer enrols at the next login
    nina_session = client(app)
    store.set_password("nina", PASSWORD)
    store.set_roles("nina", "operator")
    assert login(nina_session, "nina").status_code == 303
    assert adm.put(f"{API}/accounts/nina", json={"disabled": True}, headers=confirm(secret)).status_code == 200
    assert nina_session.get("/api/v1/events").status_code == 401          # disabled: her sessions are gone
    assert adm.put(f"{API}/accounts/nina", json={"disabled": False}, headers=confirm(secret)).status_code == 200
    assert adm.post(f"{API}/accounts/nina/password", json={"password": "short"}, headers=confirm(secret)).status_code == 422
    assert adm.post(f"{API}/accounts/nina/password", json={"password": "another temporary 3"},
                    headers=confirm(secret)).status_code == 200
    assert store.user("nina")["must_change"]
    assert adm.post(f"{API}/accounts/egor/totp-reset", json={}, headers=confirm(secret)).status_code == 200
    assert store.user("egor")["totp_at_login"] and not store.user("egor").get("totp")
    assert adm.post(f"{API}/accounts/nina/logout", json={}, headers=confirm(secret)).json()["sessions_closed"] == 0
    # tokens: never more than the issuer may do
    r = adm.post(f"{API}/accounts/nina/tokens", json={"label": "report", "scopes": ["read"]}, headers=confirm(secret))
    assert r.status_code == 200 and r.json()["token"].startswith(oa.TOKEN_PREFIX)
    assert adm.post(f"{API}/accounts/egor/tokens", json={"scopes": ["station.command"]}, headers=confirm(secret)).status_code == 403
    assert adm.delete(f"{API}/tokens/{r.json()['id']}", headers=confirm(secret)).status_code == 200
    assert adm.delete(f"{API}/tokens/{r.json()['id']}", headers=confirm(secret)).status_code == 404
    # not one's own account, not the superuser
    for method, path, payload in (("PUT", f"{API}/accounts/ada", {"disabled": True}), ("DELETE", f"{API}/accounts/ada", None),
                                  ("PUT", f"{API}/accounts/{oa.SUPERUSER_NAME}", {"disabled": True}),
                                  ("POST", f"{API}/accounts/{oa.SUPERUSER_NAME}/password", {"password": "x" * 20})):
        assert adm.request(method, path, json=payload, headers=confirm(secret)).status_code == 403, path
    assert adm.delete(f"{API}/accounts/nina", headers=confirm(secret)).status_code == 200
    assert store.user("nina") is None
    assert adm.delete(f"{API}/accounts/nobody", headers=confirm(secret)).status_code == 404


def test_tokens_and_other_roles_cannot_administer(auth):
    store, app = auth
    adm, secret = session(app, store, "ada", "admin")
    eng, eng_secret = session(app, store, "eve", "engineer")
    _, token = store.issue_token("ada", "script", scopes="read,users.manage,audit.read")
    h = {"authorization": f"Bearer {token}", "x-second-factor": code_now(secret)}
    body = {"name": "tom", "roles": ["viewer"], "password": "temporary password 4"}
    assert client(app).get(f"{API}/accounts", headers=h).status_code == 200       # a token may read
    assert client(app).post(f"{API}/accounts", json=body, headers=h).status_code == 403   # but not change
    assert eng.get(f"{API}/accounts").status_code == 403                           # an engineer: visibility only
    assert eng.post(f"{API}/accounts", json=body, headers=confirm(eng_secret)).status_code == 403
    assert eng.get(f"{API}/audit").status_code == 403
    assert adm.post(f"{API}/accounts", json=body, headers=confirm(secret)).status_code == 200


def test_the_audit_log_and_its_chain(auth):
    store, app = auth
    adm, secret = session(app, store, "ada", "admin")
    adm.post(f"{API}/accounts", json={"name": "tom", "roles": ["viewer"], "password": "temporary password 4"},
             headers=confirm(secret))
    data = adm.get(f"{API}/audit", params={"limit": 50}).json()
    assert data["intact"] and data["checked"] >= 3
    actions = [(r["actor"], r["action"], r["result"]) for r in data["records"]]
    assert ("ada", "login", "ok") in actions and ("ada", f"POST {API}/accounts", "200") in actions
    only = adm.get(f"{API}/audit", params={"actor": "system"}).json()["records"]
    assert only and all(r["actor"] == "system" for r in only)
    assert adm.get(f"{API}/audit-logging").json()["enabled"] is True
