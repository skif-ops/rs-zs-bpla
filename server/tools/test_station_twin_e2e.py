#!/usr/bin/env python3
"""Station twin end-to-end scenarios against the Muhoed twin server (CI: the firmware job runs it through CTest,
`station_twin_e2e`, with ZS_STATION_TWIN pointing at the freshly built binary).

Runs zs_station_twin with the Python server twin on the pipe and checks the server-side report:
  1. a drone fly-by is detected, published over GSM, acknowledged, no duplicates; the event carries the on-board
     bearing of the 3+1 array (DOA within 5 deg of the rendered plane wave); the tracking window keeps the detector
     running in the session and the bearings of the track reach the server as batches on the bearing topic (ICD
     addendum H: one track, time order, following the target); the audio prehistory ring holds the
     seconds around the event, including the post-event window; the server asks for the event's audio
     (CMD_REQUEST_AUDIO, both segments) right after the receipt, the station waits for the post-event window, uploads
     both segments chunk by chunk and acknowledges with the chunk count; the server stores them through the bridge's
     ingest (station.audio_ingest: parts in SQLite, SHA-256, WAV) and the ACK closes the request in the store;
  1b. the same with a station that no longer knows its events (as after a reboot): the request carries the event
     time the server has from the detection, and the station uploads by it;
  2. a burst of events during a GSM outage goes out over LoRa (30 % loss both ways) once the link is marked
     degraded, every event is delivered exactly once, and a GSM probe restores the link when the network returns.
  3. remote commands (ICD addendum D): the server signs CMD_SET_PARAMS and CMD_REBOOT, the station verifies them
     against its wall clock, executes, acknowledges; the reboot happens after its ACK, the parameters survive it,
     and the same reboot redelivered is answered from the journal without a second reset.
  4. a required self-test fails at boot: the station reports it in a session at once (self_test_ok false, the failed
     test in the detector map), takes commands, and keeps the detector off although a drone flies by;
  4b. the failure is transient: the test repeated after the boot session passes, detection resumes and the drone
     is delivered; the server sees the verdict go from false to true.
  5. command key rotation (ICD addendum E): CMD_ROTATE_COMMAND_KEY signed by the current key installs the next one;
     the bridge's keyring signs the following command with the next key, which promotes it on the station in the
     same session; a command signed by the old key is refused afterwards; the next heartbeat reports the new key.
  6. firmware update over MQTT (ICD addendum F): CMD_UPDATE_FIRMWARE with a release signed by the test release key;
     the station fetches the image chunk by chunk (fwreq -> the bridge's serve_request -> fw; one request lost on the
     way is asked again after its timeout), checks it, acknowledges OK with the chunk count, installs it by a bank
     swap, boots it on trial through the real boot guard and confirms it after the session; the heartbeat reports
     the new version on trial and the old one in the other bank; the command redelivered during the download does not
     restart it.  A station already running that version refuses it.
  6b. the new image hangs at start: the early IWDG resets it three times, the boot guard swaps back, the old image
     runs again and the heartbeat reports the rollback.
  7. remote network configuration (ICD addendum G): CMD_SET_NETWORK_CONFIG moves the station to the broker's second
     name and port; the station acknowledges under the old configuration, ends that session, brings the modem up with
     the new one in the same S3, commits it once the session is online and reports it in the heartbeat over the new
     endpoint.
  7b. a configuration whose host does not resolve: three failed bring-ups, rollback to the stored configuration, the
     station comes back over the old endpoint and its heartbeat reports the failed version.
  8. model package (ICD addendum I): the same command with a manifest of target 3 for package m5 of the built-in
     model; nine chunks from the model repository into the free slot, ACK OK, the package is active without a reset,
     and after a CMD_REBOOT it is loaded from the store again: the heartbeat model text goes from c46 to m5.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

SERVER_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = SERVER_ROOT.parent
TWIN = Path(os.environ.get("ZS_STATION_TWIN", REPO_ROOT / "firmware" / "build" / "zs_station_twin"))
SERVER_CMD = f"{sys.executable} -m twin.twin_server"


def run(args: list[str], commands: str = "", audio: str = "", redeliver: bool = False, **extra: str) -> tuple[str, dict]:
    env = dict(os.environ, ZS_TWIN_COMMANDS=commands, ZS_TWIN_AUDIO=audio, ZS_TWIN_AUDIO_REDELIVER="1" if redeliver else "", **extra)
    out = subprocess.run([str(TWIN), *args, "--server", SERVER_CMD], cwd=SERVER_ROOT, capture_output=True, text=True, timeout=900, env=env)
    if out.returncode != 0:
        sys.stderr.write(out.stdout[-4000:] + out.stderr[-2000:])
        raise SystemExit(f"twin exited with {out.returncode}: {args}")
    report_line = [l for l in out.stdout.splitlines() if l.startswith("SERVER ")]
    assert report_line, "no server report"
    return out.stdout, json.loads(report_line[-1][7:])


def main() -> int:
    try:
        import cbor2  # noqa: F401 - the server twin needs the protocol dependencies (server/requirements-protocol.lock.txt)
    except ImportError:
        print("SKIP: server protocol dependencies not installed (pip install -r server/requirements-protocol.lock.txt)")
        return 77
    if not TWIN.exists():
        print(f"SKIP: {TWIN} not built")
        return 77
    # --expect-post-audio: the prehistory ring holds >= 25 s recorded after the event although the station went to S3
    # and S0 (the post-event capture window of addendum B)
    log, r = run(["--scene", "drone", "--seconds", "140", "--seed", "3", "--receipt-latency", "2000", "--expect-events", "1", "--expect-delivered", "1",
                  "--expect-post-audio", "25", "--expect-bearing-error", "5", "--expect-streamed", "4"], audio="both", redeliver=True)
    assert r["detections"] >= 1 and r["duplicates"] == 0 and r["decode_errors"] == 0, r
    assert "session done -> COMMS_DONE" in log
    rec_line = next(l for l in log.splitlines() if "twin: rec committed" in l)
    assert "overruns 0 errors 0" in rec_line, rec_line
    # audio: one request, both segments assembled (SHA-256 checked by the AudioAssembler), ACK OK = chunk count
    (req,) = r["audio_requested"]
    event = next(e for e in r["events"] if e["event_id"] == req["event_id"])
    segs = {s["segment"]: s for s in r["audio_segments"]}
    assert set(segs) == {"pre", "post"} and all(s["event_id"] == event["event_id"] for s in segs.values()), r["audio_segments"]
    # the request was redelivered after the first chunk (QoS 1): the running upload is neither restarted nor doubled
    assert [c["command_id"] for c in r["commands_sent"]].count(req["command_id"]) == 2, r["commands_sent"]
    (ack,) = [a for a in r["acks"] if a["command_id"] == req["command_id"]]
    assert ack["result"] == 0 and ack["detail"] == r["audio_chunks"] and r["audio_duplicates"] == 0, (ack, r["audio_chunks"])
    assert log.count("audio: request for event") == 1, "a redelivery must not start a second upload"
    assert "accepted (segment 2, station time)" in log                 # the station's own table serves its events
    # the server side ran the bridge's ingest: the request is closed in the store and no part is left over
    assert r["audio_store"] == {"acked": True, "ack_result": 0, "ack_detail": r["audio_chunks"], "pending_parts": 0}, r["audio_store"]
    # the on-board bearing (3+1 array, zs_bearing) reaches the server as the event's DOA, next to the rendered truth
    truth = next(l for l in log.splitlines() if "station: event" in l and "doa valid" in l)
    truth_az = float(truth.split("truth az ")[1].split()[0])
    first = next(e for e in r["events"] if e["doa"])
    assert first["tdoa_valid"] and abs((first["doa"]["azimuth_deg"] - truth_az + 180) % 360 - 180) < 5.0, (first, truth)
    # the bearing stream of the tracking window: one track (the first event), in time order, the target moving east
    stream = r["bearings"]
    streamed = int(next(l for l in log.splitlines() if "bearings streamed" in l).split("bearings streamed ")[1].split()[0])
    assert r["bearing_batches"] >= 2 and len(stream) == streamed >= 4, (r["bearing_batches"], len(stream), streamed)
    assert {b["track_event_id"] for b in stream} == {first["event_id"]}, stream
    assert [b["time_us"] for b in stream] == sorted(b["time_us"] for b in stream)
    assert stream[-1]["azimuth_deg"] > stream[0]["azimuth_deg"] and "track: window closed (target lost)" in log, stream
    pre, post = segs["pre"], segs["post"]
    # continuous audio on both sides: the pre segment is everything the station heard since it woke for this target
    # (the ring holds nothing of S0_SLEEP, and a run of records ends at that gap), the post segment the window after
    wake_s = max(float(l[1:l.index("]")]) for l in log.splitlines()
                 if "-> S1_LISTEN" in l and float(l[1:l.index("]")]) * 1e6 + 1.8e15 <= event["time_us"])
    assert pre["seconds"] >= 2 and post["seconds"] >= 25, segs
    assert pre["start_time_us"] <= 1.8e15 + (wake_s + 1.0) * 1e6, (pre, wake_s)       # pre starts at the wake
    assert pre["start_time_us"] + pre["seconds"] * 1e6 > event["time_us"] - 1e6       # pre reaches the event
    assert post["start_time_us"] <= event["time_us"] < post["start_time_us"] + 1e6     # post starts at the event
    print(f"scenario 1 (drone over GSM): detections {r['detections']}, heartbeats {r['heartbeats']}, duplicates {r['duplicates']}; "
          f"prehistory: {rec_line.split('around the first event: ')[1]}; audio upload: {r['audio_chunks']} chunks, "
          f"pre {pre['seconds']:.0f} s + post {post['seconds']:.0f} s assembled, ACK OK; DOA az {first['doa']['azimuth_deg']:.1f} "
          f"(truth {truth_az:.1f}) sigma {first['doa']['sigma_deg']:.1f} deg; bearing stream {len(stream)} samples in "
          f"{r['bearing_batches']} batches, az {stream[0]['azimuth_deg']:.1f} -> {stream[-1]['azimuth_deg']:.1f}")

    log, r = run(["--scene", "drone", "--seconds", "140", "--seed", "3", "--receipt-latency", "2000", "--expect-events", "1",
                  "--expect-delivered", "1", "--forget-events"], audio="both")
    segs = {s["segment"]: s for s in r["audio_segments"]}
    assert set(segs) == {"pre", "post"} and r["audio_store"]["ack_result"] == 0, (r["audio_segments"], r["audio_store"])
    assert "accepted (segment 2, server time)" in log, "the upload did not run on the server's event time"
    event = next(e for e in r["events"] if e["event_id"] == r["audio_requested"][0]["event_id"])
    assert segs["post"]["start_time_us"] <= event["time_us"] < segs["post"]["start_time_us"] + 1e6
    print(f"scenario 1b (event table lost): served by the server's event time, pre {segs['pre']['seconds']:.0f} s + "
          f"post {segs['post']['seconds']:.0f} s")

    # 1600 s: the boot session starts just before the outage and runs into the S3 watchdog, which shifts the whole
    # degraded -> probe cycle by three minutes; the probe after the network returns lands at ~1450 s
    log, r = run(["--scene", "quiet", "--seconds", "1600", "--seed", "3", "--gsm-outage", "5", "1200", "--lora", "--lora-loss", "0.3",
                  "--degraded-after", "2", "--gsm-probe-s", "300", "--inject-events", "12", "30", "--expect-delivered", "12"])
    assert r["lora_detections"] == 12 and r["unique_event_ids"] == 12 and r["decode_errors"] == 0, r
    assert r["duplicates"] == r["lora_frames"] - 12 or r["duplicates"] == 0, r   # a late duplicate frame is deduped, never double-counted
    assert "DEGRADED" in log and "link healthy again" in log, "degraded -> LoRa -> probe -> healthy cycle missing"
    print(f"scenario 2 (LoRa during a GSM outage): lora frames {r['lora_frames']}, delivered {r['lora_detections']}, duplicates {r['duplicates']}")

    # the boot session delivers the queue (no event needed); after the commanded reboot the station connects again
    log, r = run(["--scene", "quiet", "--seconds", "90", "--seed", "3", "--expect-commands", "2", "--expect-reboots", "1"],
                 commands="set_params,reboot,reboot_again")
    sent, acks = r["commands_sent"], r["acks"]
    assert [c["command"] for c in sent] == ["CMD_SET_PARAMS", "CMD_REBOOT", "CMD_REBOOT"], sent
    assert len(acks) == 3 and all(a["result"] == 0 for a in acks), acks                  # OK, OK, stored OK
    assert [a["command_id"] for a in acks] == [c["command_id"] for c in sent], (acks, sent)
    assert acks[2] == acks[1], "the redelivered reboot must be answered with the journal's ACK, unchanged"
    assert "command: SET_PARAMS applied, params v1 (heartbeat 900 s, mic 1, dwell 5 s)" in log
    assert log.count("command: REBOOT in 10 s") == 1 and "twin: REBOOT by command, params v1 reloaded" in log
    reboot_line = next(l for l in log.splitlines() if "twin: REBOOT by command" in l)
    assert log.index("command: REBOOT in 10 s") < log.index(reboot_line)
    after_reboot = log[log.index(reboot_line):]
    assert "session done -> COMMS_DONE" in after_reboot, "the station must connect right after the reboot (boot session)"
    assert r["heartbeats"] >= 2, r["heartbeats"]                       # one per boot
    assert r["last_heartbeat"]["detector"]["params_version"] == 1, r["last_heartbeat"]   # the server sees the set in force
    print(f"scenario 3 (remote commands): sent {len(sent)}, acks {[a['result'] for a in acks]}, one reboot, params survived it, "
          f"reconnected after the reboot ({r['heartbeats']} heartbeats)")

    # the microphone test fails for the whole run: reachable, commandable, but no detection despite the fly-by
    log, r = run(["--scene", "drone", "--seconds", "140", "--seed", "3", "--selftest-fail-until", "100000", "--expect-commands", "1"],
                 commands="set_params")
    assert r["heartbeats"] >= 1 and r["heartbeat_self_test_ok"][0] is False, r["heartbeat_self_test_ok"]
    assert r["last_heartbeat"]["detector"]["selftest_failed_tests"] == 1 << 4, r["last_heartbeat"]   # mic_capture (id 4)
    assert [a["result"] for a in r["acks"]] == [0], r["acks"]                                         # SET_PARAMS OK
    assert r["detections"] == 0 and "events emitted 0" in log and "-> S1_LISTEN" not in log and "-> S2_DSP" not in log
    assert "selftest runs 2 recoveries 0" in log, "the test must be repeated after the session, once"
    print(f"scenario 4 (failed self-test): reported at boot (mask 0x{r['last_heartbeat']['detector']['selftest_failed_tests']:04x}), "
          f"command acked, detector off: {r['detections']} detections")

    # a transient failure: the retest after the boot session passes and the fly-by is detected and delivered
    log, r = run(["--scene", "drone", "--seconds", "140", "--seed", "3", "--selftest-fail-until", "5", "--receipt-latency", "2000",
                  "--expect-events", "1", "--expect-delivered", "1"])
    assert "selftest: recovered, detection resumes" in log and "recoveries 1" in log
    oks = r["heartbeat_self_test_ok"]
    assert oks[0] is False and oks[-1] is True, oks
    assert r["last_heartbeat"]["detector"]["selftest_failed_tests"] == 0 and r["detections"] >= 1, r["last_heartbeat"]
    print(f"scenario 4b (transient self-test failure): recovered after the boot session, heartbeats {oks}, detections {r['detections']}")

    # rotation in the boot session; an injected event at 60 s brings a second session whose heartbeat shows the result
    log, r = run(["--scene", "quiet", "--seconds", "120", "--seed", "3", "--inject-events", "1", "60", "--expect-delivered", "1",
                  "--expect-commands", "2"], commands="rotate_key,set_params,reboot_by_old_key")
    ids, sent, acks = r["key_ids"], r["commands_sent"], r["acks"]
    assert [(c["command"], c["key_id"]) for c in sent] == [("CMD_ROTATE_COMMAND_KEY", ids["current"]), ("CMD_SET_PARAMS", ids["next"]),
                                                           ("CMD_REBOOT", ids["current"])], sent
    assert [(a["command_id"], a["result"]) for a in acks] == [(sent[0]["command_id"], 0), (sent[1]["command_id"], 0)], acks   # no ACK for the old key
    assert "next key installed, both trusted" in log and "next key promoted, old key dropped" in log
    assert "command: REBOOT" not in log and "command keys 1 (rotations 1 promotions 1)" in log
    assert r["heartbeats"] >= 2 and r["last_heartbeat"]["detector"]["command_key_id"] == ids["next"], r["last_heartbeat"]
    assert r["last_heartbeat"]["detector"]["command_next_key_id"] is None
    print(f"scenario 5 (command key rotation): {ids['current']} -> {ids['next']} in one session, old key refused after it, "
          f"heartbeat reports {r['last_heartbeat']['detector']['command_key_id']}")

    # firmware update: v1 -> v2 (40 chunks), the third request lost on the way
    log, r = run(["--scene", "quiet", "--seconds", "150", "--seed", "3", "--fw-version", "1", "--expect-fw-version", "2",
                  "--expect-fw-state", "0"], commands="update_firmware", ZS_TWIN_FW_DROP="3", ZS_TWIN_FW_REDELIVER="1")
    f, (ack,) = r["firmware"], r["acks"]
    # the command redelivered during the download (QoS 1): the running download is neither restarted nor doubled
    assert [c["command_id"] for c in r["commands_sent"]] == [ack["command_id"]] * 2, r["commands_sent"]
    assert log.count("fw: update to v2 accepted") == 1, "a redelivery must not start a second download"
    assert f["release_version"] == 2 and f["chunks"] == 40 and f["served"] == 40 and f["dropped"] == 1 and f["requests"] == 41, f
    assert ack["result"] == 0 and ack["detail"] == 40, ack
    assert "fw: update to v2 accepted (40000 bytes, running v1)" in log and "fw: v2 armed for trial, installing" in log
    assert "twin: RESET (install): running v2 from bank 2, boot trial (attempt 1)" in log and "fw: v2 confirmed" in log
    assert log.index("fw: v2 armed for trial") > log.index("fw: download finished, result 0 detail 40")
    det = r["last_heartbeat"]["detector"]
    assert (det["fw_version"], det["fw_state"], det["fw_other_version"]) == (2, "TRIAL", 1), det   # the boot session of v2
    assert "installs 1 trial boots 1 iwdg resets 0 rollbacks 0 confirms 1" in log
    print(f"scenario 6 (firmware update): v1 -> v2, {f['chunks']} chunks ({f['requests']} requests, {f['dropped']} lost and asked again), "
          f"ACK OK, bank swap, trial, confirmed; heartbeat v{det['fw_version']} {det['fw_state']} (other bank v{det['fw_other_version']})")
    log, r = run(["--scene", "quiet", "--seconds", "60", "--seed", "3", "--fw-version", "2", "--expect-fw-version", "2"],
                 commands="update_firmware")
    assert [(a["result"], a["detail"]) for a in r["acks"]] == [(1, 4)] and r["firmware"]["requests"] == 0, (r["acks"], r["firmware"])
    print("scenario 6 (same version): REJECTED 4 (version not newer), nothing fetched")

    # the new image hangs at start: three IWDG resets on trial, then the guard swaps back to v1
    log, r = run(["--scene", "quiet", "--seconds", "240", "--seed", "3", "--fw-version", "1", "--ota-hang-version", "2",
                  "--expect-fw-version", "1", "--expect-fw-state", "4"], commands="update_firmware")
    assert [(a["result"], a["detail"]) for a in r["acks"]] == [(0, 40)], r["acks"]
    assert log.count("twin: RESET (IWDG)") == 3 and "not confirmed after 3 attempts -> ROLLBACK" in log
    assert "running v1 from bank 1, boot normal" in log and "fw: v2 confirmed" not in log
    rollback_at = log.index("-> ROLLBACK")
    assert "session done -> COMMS_DONE" in log[rollback_at:], "the old image must connect again after the rollback"
    det = r["last_heartbeat"]["detector"]
    assert (det["fw_version"], det["fw_state"], det["fw_other_version"]) == (1, "ROLLED_BACK", 2), det
    print(f"scenario 6b (image hangs at start): 3 IWDG resets on trial, rollback to v{det['fw_version']}, "
          f"heartbeat {det['fw_state']} (other bank v{det['fw_other_version']})")

    # remote network configuration: muhoed.twin:8883 -> muhoed2.twin:443 (the same twin behind its second name)
    log, r = run(["--scene", "quiet", "--seconds", "120", "--seed", "3", "--expect-net-version", "2", "--expect-net-state", "0"],
                 commands="set_network")
    (sent,), (ack,) = r["commands_sent"], r["acks"]
    assert sent["command"] == "CMD_SET_NETWORK_CONFIG" and (ack["command_id"], ack["result"], ack["detail"]) == (sent["command_id"], 0, 0), (sent, ack)
    assert log.index("net: switching to configuration v2") > log.index("command: SET_NETWORK_CONFIG -> result 0")
    assert log.index("net: v2 CONFIRMED (online with muhoed2.twin:443)") < log.index("session done -> COMMS_DONE")
    assert "stored v2; broker opens muhoed.twin 1 muhoed2.twin 1, failed endpoints 0" in log
    det = r["last_heartbeat"]["detector"]
    assert (det["net_config_version"], det["net_state"], det["net_failed_version"]) == (2, "STABLE", 0), det
    print(f"scenario 7 (network configuration): ACK under v1, switch in the same S3, online over muhoed2.twin:443, stored; "
          f"heartbeat v{det['net_config_version']} {det['net_state']}")

    # a host no DNS knows: three failed bring-ups, rollback, back over the old endpoint
    log, r = run(["--scene", "quiet", "--seconds", "200", "--seed", "3", "--expect-net-version", "1", "--expect-net-state", "3"],
                 commands="set_network_bad")
    assert [(a["result"], a["detail"]) for a in r["acks"]] == [(0, 0)], r["acks"]
    assert log.count("DNS failure") == 3 and "net: v2 failed 3 bring-ups, ROLLED BACK to v1" in log and "CONFIRMED" not in log
    assert "session done -> COMMS_DONE" in log[log.index("ROLLED BACK"):], "the old configuration must connect again"
    assert "stored v1; broker opens muhoed.twin 2 muhoed2.twin 0, failed endpoints 3" in log
    det = r["last_heartbeat"]["detector"]
    assert (det["net_config_version"], det["net_state"], det["net_failed_version"]) == (1, "ROLLED_BACK", 2), det
    print(f"scenario 7b (unreachable configuration): 3 failed bring-ups, rollback to v{det['net_config_version']}, "
          f"heartbeat {det['net_state']} (failed v{det['net_failed_version']})")

    # model package m5 (addendum I), then a reboot: the store brings it back
    log, r = run(["--scene", "quiet", "--seconds", "90", "--seed", "3", "--expect-reboots", "1"], commands="update_model,reboot")
    m, acks = r["model"], r["acks"]
    assert m["release_version"] == 5 and m["chunks"] == 9 and m["requests"] == 9, m
    assert [(a["result"], a["detail"]) for a in acks] == [(0, 9), (0, 0)], acks
    assert "model: update to m5 accepted (8520 bytes, active m0)" in log and "model: m5 active" in log
    assert log.index("model: m5 active") > log.index("fw: download finished, result 0 detail 9"), "active only after the OK ACK"
    assert "twin: model m5 loaded from the store" in log and "twin: RESET" not in log
    assert r["heartbeat_model_ver"] == ["c46", "m5"], r["heartbeat_model_ver"]
    assert r["last_heartbeat"]["detector"]["fw_state"] == "IDLE", "a model download is not a firmware state"
    print(f"scenario 8 (model package): m5 in {m['chunks']} chunks, ACK OK, active without a reset, reloaded after the reboot; "
          f"heartbeat model {' -> '.join(r['heartbeat_model_ver'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
