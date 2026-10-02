"""The superuser skif_root (docs/SERVER_ACCESS_CONTROL_2026-10-02.md, §7 and §8): one account, created by the server with the
default password, which the first login must change and then enrol the second factor; every permission and every
station; the switch of the audit log of actions, whose switching is always recorded."""
import io
import json
import re
import time

import pytest

from station import operator_auth as oa
from tests.test_operator_auth import ORIGIN, PASSWORD, auth, client, login  # noqa: F401

ROOT = oa.SUPERUSER_NAME
NEW = "a long root password"


def field(page: str, name: str) -> str:
    return re.search(rf'name="{name}" value="([^"]*)"', page).group(1)


def first_login(c, new_password: str = NEW):
    """Default password, a new one, the second factor: (the secret, the final answer)."""
    r = login(c, ROOT, oa.SUPERUSER_DEFAULT_PASSWORD)
    assert r.status_code == 200 and 'action="/login/password"' in r.text and oa.COOKIE_NAME not in r.cookies
    r = c.post("/login/password", data={"step": field(r.text, "step"), "new_password": new_password, "repeat": new_password},
               headers=ORIGIN)
    assert r.status_code == 200 and 'action="/login/totp"' in r.text
    secret = re.search(r'id="totp-secret">([A-Z2-7 ]+)<', r.text).group(1).replace(" ", "")
    step = int(time.time() // oa.TOTP_STEP_S)
    done = c.post("/login/totp", data={"step": field(r.text, "step"), "code": oa.totp_code(secret, step)}, headers=ORIGIN)
    return secret, done


def test_one_superuser_created_by_the_server_and_protected(auth):
    store, _ = auth
    root = store.user(ROOT)
    assert root["roles"] == [oa.SUPERUSER_ROLE] and root["must_change"] and root["totp_at_login"] and not root.get("totp")
    assert oa.verify_password(oa.SUPERUSER_DEFAULT_PASSWORD, root["password"])
    assert root["permissions"] == set(oa.PERMISSIONS) | {oa.AUDIT_CONTROL}
    for bad in (lambda: store.add_user(ROOT, "viewer", PASSWORD), lambda: store.add_user("other", "superuser", PASSWORD),
                lambda: store.set_roles("anna", "superuser"), lambda: store.set_roles(ROOT, "viewer"),
                lambda: store.remove_user(ROOT), lambda: store.set_disabled(ROOT, True),
                lambda: store.set_scope(ROOT, ["north"], [])):
        store.add_user("anna", "operator", PASSWORD) if store.user("anna") is None else None
        with pytest.raises(ValueError):
            bad()
    # a hand-edited file: the superuser role is taken from anyone else, skif_root gets it back, unlimited and enabled
    data = json.loads(store.path.read_text())
    data["users"]["anna"]["roles"] = ["operator", "superuser"]
    data["users"][ROOT].update(roles=["viewer"], stations=[17], disabled=True)
    store.path.write_text(json.dumps(data))
    oa.current_store()
    assert store.user("anna")["roles"] == ["operator"]
    assert store.user(ROOT)["roles"] == [oa.SUPERUSER_ROLE] and not store.user(ROOT).get("disabled")
    assert store.user(ROOT)["stations"] == []
    records = [(r["actor"], r["action"]) for r in oa.current_state().audit_records()]
    assert records[0] == ("system", "superuser-created") and records[-1] == ("system", "superuser-repaired")


def test_first_login_changes_the_password_and_enrols_the_second_factor(auth):
    store, app = auth
    c = client(app)
    r = login(c, ROOT, oa.SUPERUSER_DEFAULT_PASSWORD)
    step = field(r.text, "step")
    assert c.get("/api/v1/events").status_code == 401                   # the default password opens no session
    for new, repeat in (("short", "short"), (NEW, NEW + "x"), (oa.SUPERUSER_DEFAULT_PASSWORD, oa.SUPERUSER_DEFAULT_PASSWORD)):
        assert c.post("/login/password", data={"step": step, "new_password": new, "repeat": repeat}, headers=ORIGIN).status_code == 400
    assert c.post("/login/password", data={"step": step + "x", "new_password": NEW, "repeat": NEW}, headers=ORIGIN).status_code == 401
    assert c.post("/login/totp", data={"step": step, "code": "123456"}, headers=ORIGIN).status_code == 401   # another step
    assert c.post("/login/password", data={"step": step, "new_password": NEW, "repeat": NEW},
                  headers={"origin": "https://evil.example"}).status_code == 403
    secret, done = first_login(client(app))
    assert done.status_code == 303 and oa.COOKIE_NAME in done.cookies
    root = store.user(ROOT)
    assert not root.get("must_change") and not root.get("totp_at_login") and root["totp"] == secret
    assert login(client(app), ROOT, oa.SUPERUSER_DEFAULT_PASSWORD).status_code == 401   # the default is gone
    # the step of the first browser is stale now: its password version changed
    assert c.post("/login/password", data={"step": step, "new_password": NEW + "!", "repeat": NEW + "!"},
                  headers=ORIGIN).status_code == 401
    step_now = int(time.time() // oa.TOTP_STEP_S)
    assert login(client(app), ROOT, NEW).status_code == 401             # from now on: password and code
    assert login(client(app), ROOT, NEW, code=oa.totp_code(secret, step_now + 1)).status_code == 303
    records = [(r["actor"], r["action"], r["result"]) for r in oa.current_state().audit_records()]
    assert (ROOT, "passwd", "ok") in records and (ROOT, "totp-enroll", "ok") in records


def test_a_wrong_enrolment_code_keeps_the_step(auth):
    _, app = auth
    c = client(app)
    r = login(c, ROOT, oa.SUPERUSER_DEFAULT_PASSWORD)
    r = c.post("/login/password", data={"step": field(r.text, "step"), "new_password": NEW, "repeat": NEW}, headers=ORIGIN)
    secret = re.search(r'id="totp-secret">([A-Z2-7 ]+)<', r.text).group(1).replace(" ", "")
    step = int(time.time() // oa.TOTP_STEP_S)
    near = {oa.totp_code(secret, step + d) for d in (-1, 0, 1, 2)}
    wrong = next(f"{n:06d}" for n in range(10) if f"{n:06d}" not in near)
    again = c.post("/login/totp", data={"step": field(r.text, "step"), "code": wrong}, headers=ORIGIN)
    assert again.status_code == 401 and secret[:4] in again.text        # the same secret, shown again
    ok = c.post("/login/totp", data={"step": field(again.text, "step"), "code": oa.totp_code(secret, step)}, headers=ORIGIN)
    assert ok.status_code == 303
    oa.current_store().set_totp(ROOT, None)                             # a reset on the server's shell...
    r = login(client(app), ROOT, NEW)
    assert r.status_code == 200 and 'action="/login/totp"' in r.text    # ...enrols anew at the next login


def test_superuser_may_do_everything_and_sees_every_station(auth):
    store, app = auth
    _, done = first_login(c := client(app))
    assert done.status_code == 303
    key = {"public_key": "00" * 32}
    for method, path, body in (("POST", "/api/v1/stations/17/network-config", {"server_host": "example.org"}),
                               ("POST", "/api/v1/stations/17/command-key-rotation", key),
                               ("POST", "/dataset/delete", None),
                               ("GET", "/api/v1/stations/17/events/5/audio", None),
                               ("GET", "/api/v1/admin/audit-logging", None)):
        assert c.request(method, path, json=body, headers=ORIGIN).status_code != 403, path
    store.add_user("anna", "operator", PASSWORD)
    store.set_scope("anna", ["north"], [17])
    names = [a["name"] for a in c.get("/api/v1/access/accounts").json()]
    assert "anna" in names and ROOT not in names                       # nobody limits the superuser
    _, token = store.issue_token(ROOT, "script", scopes=",".join(oa.PERMISSIONS))
    h = {"authorization": f"Bearer {token}"}
    assert c.get("/api/v1/admin/audit-logging", headers=h).status_code == 200
    assert c.put("/api/v1/admin/audit-logging", json={"enabled": False}, headers=h).status_code == 403   # never a token


def test_the_audit_log_of_actions_can_be_switched_off_and_the_switching_shows(auth):
    store, app = auth
    root_secret, done = first_login(root := client(app))
    step_up = {**ORIGIN, "x-second-factor": oa.totp_code(root_secret, int(time.time() // oa.TOTP_STEP_S))}
    store.add_user("anna", "operator", PASSWORD)
    adm_secret = oa.new_totp_secret()
    store.add_user("ada", "admin", PASSWORD)
    store.set_totp("ada", adm_secret)
    ada = client(app)
    assert login(ada, "ada", code=oa.totp_code(adm_secret, int(time.time() // oa.TOTP_STEP_S))).status_code == 303
    assert ada.get("/api/v1/admin/audit-logging").json()["enabled"] is True
    assert ada.put("/api/v1/admin/audit-logging", json={"enabled": False}, headers=ORIGIN).status_code == 403
    assert root.put("/api/v1/admin/audit-logging", json={"enabled": False}, headers=ORIGIN).status_code == 403   # no code
    state = oa.current_state()
    before = len(state.audit_records(1000))
    off = root.put("/api/v1/admin/audit-logging", json={"enabled": False}, headers=step_up)
    assert off.status_code == 200 and off.json()["enabled"] is False and off.json()["changed_by"] == ROOT
    anna = client(app)
    login(anna, "anna")                                                 # not recorded: a login...
    anna.post("/api/v1/stations/17/audio-request", json={"event_id": 5}, headers=ORIGIN)   # ...and a change
    login(client(app), "anna", "wrong password!")                       # recorded: a failed login...
    client(app).post("/api/v1/stations/17/audio-request", json={"event_id": 5},
                     headers={**ORIGIN, "authorization": "Bearer " + store.issue_token("anna", "x")[1]})   # ...a refusal
    assert ada.get("/api/v1/admin/audit-logging").json()["enabled"] is False
    on = root.put("/api/v1/admin/audit-logging", json={"enabled": True},
                  headers={**ORIGIN, "x-second-factor": oa.totp_code(root_secret, int(time.time() // oa.TOTP_STEP_S))})
    assert on.status_code == 200 and on.json()["enabled"] is True
    rows = [(r["actor"], r["action"], r["target"], r["result"]) for r in state.audit_records(1000)][before:]
    assert rows[0] == (ROOT, "audit-logging", "off", "ok")
    assert ("anna", "login", "", "failed") in rows and any(r[0] == "anna" and r[3] == "403" for r in rows)
    assert ("anna", "login", "", "ok") not in rows and not any(r[0] == "anna" and r[3] == "200" for r in rows)
    assert (ROOT, "audit-logging", "on", "ok") in rows and rows[-1][0] == ROOT
    assert state.audit_verify()[0]


def test_cli_keeps_the_superuser_and_switches_the_audit_log(tmp_path, monkeypatch, capsys):
    path = tmp_path / "ops.json"
    cli = ["--accounts", str(path)]
    assert oa.main([*cli, "list"]) == 0
    assert ROOT in json.loads(capsys.readouterr().out)["users"]
    for argv in (["remove-user", ROOT], ["disable", ROOT], ["set-roles", ROOT, "--roles", "viewer"],
                 ["set-roles", ROOT, "--roles", "superuser"]):
        assert oa.main([*cli, *argv]) == 2, argv
    monkeypatch.setattr("sys.stdin", io.StringIO(PASSWORD + "\n"))
    assert oa.main([*cli, "add-user", "eve", "--role", "superuser", "--password-stdin"]) == 2
    assert oa.main([*cli, "audit-logging", "off"]) == 0
    assert json.loads(capsys.readouterr().out)["enabled"] is False
    monkeypatch.setattr("sys.stdin", io.StringIO(PASSWORD + "\n"))
    assert oa.main([*cli, "add-user", "eve", "--role", "operator", "--password-stdin"]) == 0   # not recorded
    assert oa.main([*cli, "audit-logging", "on"]) == 0
    capsys.readouterr()
    assert oa.main([*cli, "audit"]) == 0
    lines = capsys.readouterr().out.splitlines()
    actions = [(line.split()[5], line.split()[6]) for line in lines]
    assert actions == [("superuser-created", ROOT), ("audit-logging", "off"), ("audit-logging", "on")]
