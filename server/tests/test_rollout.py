"""station/rollout.py: a release goes to the canary stations first and to the rest only after they confirmed it, at
most max_in_flight stations at a time; ACKs, expired commands and heartbeats move the stations; failures pause the
rollout; resume, skip, cancel and revert; the journal; the operator routes and their permission
(docs/SERVER_OTA_ROLLOUT_2026-10-03.md)."""
import hashlib
import json
import time

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient

from station import firmware_codec as fw
from station import rollout as ro
from station.operator_auth import STATION_FIRMWARE, required_permission
from station.schemas import DetectorHealth, HeartbeatMessage, StationPosition
from station.store import EventStore

RELEASE = fw.ReleaseSigner(Ed25519PrivateKey.from_private_bytes(bytes(range(65, 97))))
MINUTE_US = 60_000_000


def image(version: int, size: int = 3000) -> bytes:
    stream = b"".join(hashlib.sha256(b"rollout-image" + i.to_bytes(4, "big")).digest() for i in range((size + 31) // 32))
    out = bytearray(stream[:size])
    out[fw.FW_INFO_OFFSET:fw.FW_INFO_OFFSET + fw.FW_INFO_BYTES] = fw.build_fw_info(fw.TARGET_STM32_APP, version)
    return bytes(out)


def heartbeat(store: EventStore, station_id: int, fw_version: int, state: str = "IDLE", other: int = 0, time_us: int | None = None):
    hb = HeartbeatMessage(station_id=station_id, time_us=time_us or int(time.time() * 1e6), station=StationPosition(lat_e7=0, lon_e7=0, alt_dm=0),
                          detector=DetectorHealth(fw_version=fw_version, fw_state=state, fw_other_version=other))
    store.upsert_station(hb)


def ack(store: EventStore, station_id: int, command_id: str, result: int = 0, detail: int = 40):
    assert store.ack_command(station_id, command_id, result, detail) == "acked"


def commands_of(store: EventStore, station_id: int):
    with store._conn() as c:
        return [dict(r) for r in c.execute("SELECT * FROM commands WHERE station_id=? ORDER BY created_us", (station_id,))]


@pytest.fixture
def world(tmp_path):
    store = EventStore(tmp_path / "events.sqlite3")
    repo = fw.ReleaseRepository(tmp_path / "firmware")
    repo.add(image(6), RELEASE)
    runner = ro.RolloutRunner(ro.RolloutSettings(tick_s=0, command_attempts=2, max_in_flight=2, confirm_timeout_s=60))
    for s in (1, 2, 3, 4, 5):
        heartbeat(store, s, 5)
    return store, repo, runner


def station_states(r):
    return {s["station_id"]: s["state"] for s in r["stations"]}


def test_canary_then_the_waves_then_completed(world):
    store, repo, runner = world
    r = runner.create(store, repo, version=6, stations=[1, 2, 3, 4, 5], canary=[1], actor="ivan")
    assert r["state"] == "canary" and station_states(r) == {1: "pending", 2: "pending", 3: "pending", 4: "pending", 5: "pending"}
    assert r["journal"][0]["event"] == "created" and r["journal"][0]["actor"] == "ivan"
    # the first tick commands the canary station only
    assert runner.tick(store, repo)["commanded"] == 1
    r = runner.get(store, r["rollout_id"])
    assert station_states(r)[1] == "commanded" and all(v == "pending" for k, v in station_states(r).items() if k != 1)
    (cmd,) = commands_of(store, 1)
    assert cmd["command"] == fw.UPDATE_COMMAND and cmd["payload"] == json.dumps(repo.get(6).command_payload(), ensure_ascii=False)
    assert commands_of(store, 2) == []
    # ACK OK: downloaded and installed; the heartbeats of the trial and then of the confirmed image
    ack(store, 1, cmd["command_id"])
    runner.tick(store, repo)
    assert station_states(runner.get(store, r["rollout_id"]))[1] == "installed"
    heartbeat(store, 1, 6, "TRIAL", other=5)
    runner.tick(store, repo)
    r = runner.get(store, r["rollout_id"])
    assert station_states(r)[1] == "trial" and r["state"] == "canary" and commands_of(store, 2) == []
    heartbeat(store, 1, 6, "IDLE", other=5)
    moved = runner.tick(store, repo)
    r = runner.get(store, r["rollout_id"])
    assert station_states(r)[1] == "confirmed" and r["state"] == "running"
    assert moved["commanded"] == 2 and station_states(r)[2] == station_states(r)[3] == "commanded" and station_states(r)[4] == "pending"   # max_in_flight 2
    assert [j["event"] for j in r["journal"]] == ["created", "commanded", "installed", "trial", "confirmed", "canary_passed", "commanded", "commanded"]
    assert r["stations"][0]["from_version"] == 5
    # the main wave, two at a time
    for s in (2, 3):
        ack(store, s, commands_of(store, s)[0]["command_id"])
        heartbeat(store, s, 6)
    assert runner.tick(store, repo)["commanded"] == 2
    r = runner.get(store, r["rollout_id"])
    assert station_states(r) == {1: "confirmed", 2: "confirmed", 3: "confirmed", 4: "commanded", 5: "commanded"}
    for s in (4, 5):
        ack(store, s, commands_of(store, s)[0]["command_id"])
        heartbeat(store, s, 6)
    runner.tick(store, repo)
    r = runner.get(store, r["rollout_id"])
    assert r["state"] == "completed" and r["counts"] == {"confirmed": 5}
    assert r["journal"][-1]["event"] == "completed" and r["journal"][-1]["detail"] == {"confirmed": 5}
    assert runner.list(store)[0]["counts"] == {"confirmed": 5} and runner.list(store, [9]) == [] and runner.list(store, [4])
    assert runner.tick(store, repo) == {"rollouts": 0, "commanded": 0, "moved": 0, "paused": 0, "completed": 0}


def test_failures_pause_resume_skip_and_cancel(world):
    store, repo, runner = world
    r = runner.create(store, repo, version=6, stations=[1, 2, 3], canary=[1], max_in_flight=5)
    runner.tick(store, repo)
    ack(store, 1, commands_of(store, 1)[0]["command_id"], result=2, detail=2)          # FAILED 2: SHA-256 of the image
    runner.tick(store, repo)
    r = runner.get(store, r["rollout_id"])
    assert r["state"] == "paused" and r["reason"].startswith("1 failure(s): 1 failed") and station_states(r)[1] == "failed"
    assert r["stations"][0]["detail"] == {"ack": "FAILED", "detail": 2}
    assert r["journal"][-1]["event"] == "paused" and r["journal"][-1]["detail"]["auto"] is True and r["journal"][-1]["actor"] == "runner"
    assert runner.tick(store, repo)["commanded"] == 0                                   # paused: nothing more is commanded
    with pytest.raises(ro.RolloutError, match="rollout not found"):
        runner.resume(store, "no-such")
    with pytest.raises(ro.RolloutError, match="rollout is paused"):
        runner.pause(store, r["rollout_id"])
    # resumed: the failed canary station still holds the canary wave; skipping it lets the main wave go
    r = runner.resume(store, r["rollout_id"], actor="ivan")
    assert r["state"] == "canary" and r["failures_seen"] == 1
    assert runner.tick(store, repo)["commanded"] == 0
    r = runner.skip(store, r["rollout_id"], 1, actor="ivan", reason="bench unit")
    assert station_states(r)[1] == "skipped"
    assert runner.tick(store, repo)["commanded"] == 2
    r = runner.get(store, r["rollout_id"])
    assert r["state"] == "running" and station_states(r) == {1: "skipped", 2: "commanded", 3: "commanded"}
    # station 2 installs it and its boot guard rolls it back: a new failure pauses again
    ack(store, 2, commands_of(store, 2)[0]["command_id"])
    heartbeat(store, 2, 5, "ROLLED_BACK", other=6)
    runner.tick(store, repo)
    r = runner.get(store, r["rollout_id"])
    assert r["state"] == "paused" and station_states(r)[2] == "rolled_back" and "2 rolled_back" in r["reason"]
    # cancelled: pending stations are skipped, the one in flight is still followed to its end
    r = runner.cancel(store, r["rollout_id"], actor="ivan", reason="enough")
    assert r["state"] == "cancelled" and r["reason"] == "enough"
    ack(store, 3, commands_of(store, 3)[0]["command_id"])
    heartbeat(store, 3, 6)
    assert runner.tick(store, repo)["moved"] == 2                                       # installed, then confirmed
    r = runner.get(store, r["rollout_id"])
    assert r["state"] == "cancelled" and station_states(r) == {1: "skipped", 2: "rolled_back", 3: "confirmed"}
    with pytest.raises(ro.RolloutError, match="already cancelled"):
        runner.cancel(store, r["rollout_id"])


def test_already_rejected_unreachable_and_timeouts(world):
    store, repo, runner = world
    heartbeat(store, 4, 6)                                                              # already runs the release
    r = runner.create(store, repo, version=6, stations=[2, 3, 4, 5], canary_count=0, max_in_flight=10)
    assert r["state"] == "running"
    now = int(time.time() * 1e6)
    assert runner.tick(store, repo, now_us=now) == {"rollouts": 1, "commanded": 3, "moved": 1, "paused": 0, "completed": 0}
    r = runner.get(store, r["rollout_id"])
    assert station_states(r) == {2: "commanded", 3: "commanded", 4: "already", 5: "commanded"} and commands_of(store, 4) == []
    # REJECTED 4 (version not newer) with a heartbeat that shows the release: not a failure
    heartbeat(store, 2, 6)
    ack(store, 2, commands_of(store, 2)[0]["command_id"], result=1, detail=4)
    # REJECTED 4 without such a heartbeat: a failure (the station runs something else)
    ack(store, 3, commands_of(store, 3)[0]["command_id"], result=1, detail=4)
    runner.tick(store, repo, now_us=now + 1)
    r = runner.get(store, r["rollout_id"])
    assert station_states(r)[2] == "already" and station_states(r)[3] == "failed" and r["state"] == "paused"
    r = runner.resume(store, r["rollout_id"])
    # station 5 never answers: the command expires, is given again (command_attempts 2), then the station is unreachable
    later = now + 16 * MINUTE_US
    runner.tick(store, repo, now_us=later)
    r = runner.get(store, r["rollout_id"])
    assert station_states(r)[5] == "commanded" and r["stations"][-1]["attempts"] == 2 and len(commands_of(store, 5)) == 2
    assert commands_of(store, 5)[1]["payload"] == commands_of(store, 5)[0]["payload"]
    runner.tick(store, repo, now_us=later + 16 * MINUTE_US)
    r = runner.get(store, r["rollout_id"])
    assert station_states(r)[5] == "unreachable" and r["state"] == "completed"
    assert r["counts"] == {"already": 2, "failed": 1, "unreachable": 1}
    # a station that installed the release and never came back: the confirm timeout
    repo.add(image(7), RELEASE)
    heartbeat(store, 1, 6)
    r = runner.create(store, repo, version=7, stations=[1], canary_count=0)
    runner.tick(store, repo, now_us=now)
    ack(store, 1, commands_of(store, 1)[0]["command_id"])
    runner.tick(store, repo, now_us=now + 1)
    assert station_states(runner.get(store, r["rollout_id"]))[1] == "installed"
    runner.tick(store, repo, now_us=now + 2 * MINUTE_US)
    r = runner.get(store, r["rollout_id"])
    assert station_states(r)[1] == "unreachable" and r["stations"][0]["detail"]["last"] == "installed" and r["state"] == "completed"


def test_revert_needs_a_newer_release_and_reaches_the_commanded_stations(world):
    store, repo, runner = world
    r = runner.create(store, repo, version=6, stations=[1, 2, 3], canary=[1], actor="ivan")
    runner.tick(store, repo)
    ack(store, 1, commands_of(store, 1)[0]["command_id"])
    heartbeat(store, 1, 6)
    runner.tick(store, repo)                                                            # canary passed, 2 and 3 commanded
    assert station_states(runner.get(store, r["rollout_id"])) == {1: "confirmed", 2: "commanded", 3: "commanded"}
    with pytest.raises(ro.RolloutError, match="not newer"):
        runner.revert(store, r["rollout_id"], repo, revert_version=5)
    with pytest.raises(ro.RolloutError, match="not in the firmware repository"):
        runner.revert(store, r["rollout_id"], repo, revert_version=7)
    repo.add(image(7), RELEASE)                                                         # the earlier image, signed as 7
    new = runner.revert(store, r["rollout_id"], repo, revert_version=7, actor="ivan", reason="false alarms")
    old = runner.get(store, r["rollout_id"])
    assert old["state"] == "cancelled" and old["revert_version"] == 7 and old["reason"] == "reverted to 7: false alarms"
    assert old["journal"][-1]["event"] == "reverted" and old["journal"][-1]["detail"]["revert_rollout_id"] == new["rollout_id"]
    assert new["version"] == 7 and new["state"] == "running" and station_states(new) == {1: "pending", 2: "pending", 3: "pending"}
    assert new["journal"][-1] == {**new["journal"][-1], "event": "reverts", "detail": {"rollout_id": r["rollout_id"], "version": 6}}
    assert runner.tick(store, repo)["commanded"] == 2                                   # max_in_flight 2 of the reverted rollout
    with pytest.raises(ro.RolloutError, match="still in rollout"):
        runner.create(store, repo, version=7, stations=[2])
    repo.add(image(8), RELEASE)
    with pytest.raises(ro.RolloutError, match="no station was commanded"):
        runner.revert(store, runner.create(store, repo, version=7, stations=[4])["rollout_id"], repo, revert_version=8)


def test_create_rules(world):
    store, repo, runner = world
    with pytest.raises(ro.RolloutError, match="not in the firmware repository"):
        runner.create(store, repo, version=9, stations=[1])
    with pytest.raises(ro.RolloutError, match="every canary station must be in stations"):
        runner.create(store, repo, version=6, stations=[1, 2], canary=[3])
    with pytest.raises(ro.RolloutError, match="at least one station"):
        runner.create(store, repo, version=6, stations=[])
    with pytest.raises(ro.RolloutError, match="not a station id"):
        runner.create(store, repo, version=6, stations=[0])
    r = runner.create(store, repo, version=6, stations=[1, 1, 2], canary_count=5)       # duplicates folded, all canary
    assert [s["wave"] for s in r["stations"]] == ["canary", "canary"] and r["max_in_flight"] == 2 and r["max_failures"] == 1
    assert ro.RolloutSettings.from_env({"ZS_ROLLOUT_TICK_S": "0", "ZS_ROLLOUT_MAX_IN_FLIGHT": "4"}).as_dict() == {
        "tick_s": 0.0, "command_attempts": 4, "max_in_flight": 4, "max_failures": 1, "confirm_timeout_s": 7200.0}
    with pytest.raises(ValueError, match="ZS_ROLLOUT_MAX_FAILURES must be at least 1"):
        ro.RolloutSettings.from_env({"ZS_ROLLOUT_MAX_FAILURES": "0"})


def test_operator_routes_and_permission(tmp_path, monkeypatch):
    from app import app
    import station.router as router

    store = EventStore(tmp_path / "events.sqlite3")
    repo_dir = tmp_path / "firmware"
    fw.ReleaseRepository(repo_dir).add(image(6), RELEASE)
    monkeypatch.setattr(router, "store", store)
    monkeypatch.setenv("ZS_FIRMWARE_DIR", str(repo_dir))
    monkeypatch.setattr(router.rollout_runner, "settings", ro.RolloutSettings(tick_s=0))
    heartbeat(store, 17, 5)
    client = TestClient(app)
    assert client.get("/api/v1/firmware/rollouts").json() == []
    bad = client.post("/api/v1/firmware/rollouts", json={"version": 9, "stations": [17]})
    assert bad.status_code == 409 and "not in the firmware repository" in bad.json()["detail"]
    assert client.post("/api/v1/firmware/rollouts", json={"version": 6, "stations": []}).status_code == 422
    made = client.post("/api/v1/firmware/rollouts", json={"version": 6, "stations": [17, 18], "canary": [17]})
    assert made.status_code == 200 and made.json()["state"] == "canary" and len(made.json()["stations"]) == 2 and made.json()["created_by"] == ""  # the bench: no account
    rid = made.json()["rollout_id"]
    assert client.get("/api/v1/firmware/rollouts").json()[0]["rollout_id"] == rid
    assert client.get("/api/v1/firmware/rollouts/none").status_code == 404
    paused = client.post(f"/api/v1/firmware/rollouts/{rid}/pause", json={"reason": "wait"})
    assert paused.status_code == 200 and paused.json()["state"] == "paused" and paused.json()["reason"] == "wait"
    assert client.post(f"/api/v1/firmware/rollouts/{rid}/pause").status_code == 409
    assert client.post(f"/api/v1/firmware/rollouts/{rid}/resume").json()["state"] == "canary"
    assert client.post(f"/api/v1/firmware/rollouts/{rid}/stations/18/skip", json={"reason": "later"}).json()["stations"][1]["state"] == "skipped"
    assert client.post(f"/api/v1/firmware/rollouts/{rid}/revert", json={"version": 7}).status_code == 409
    done = client.post(f"/api/v1/firmware/rollouts/{rid}/cancel")
    assert done.status_code == 200 and done.json()["state"] == "cancelled"
    assert client.get(f"/api/v1/firmware/rollouts/{rid}").json()["journal"][-1]["event"] == "cancelled"
    assert client.get("/api/v1/health").json()["rollouts"]["settings"]["tick_s"] == 0
    for path in ("/api/v1/firmware/rollouts", f"/api/v1/firmware/rollouts/{rid}/pause", f"/api/v1/firmware/rollouts/{rid}/resume",
                 f"/api/v1/firmware/rollouts/{rid}/cancel", f"/api/v1/firmware/rollouts/{rid}/revert", f"/api/v1/firmware/rollouts/{rid}/stations/18/skip"):
        assert required_permission("POST", path) == STATION_FIRMWARE, path
    assert required_permission("GET", "/api/v1/firmware/rollouts") == "read"
