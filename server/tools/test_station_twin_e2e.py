#!/usr/bin/env python3
"""Station twin end-to-end scenarios against the Muhoed twin server (CI: the firmware job runs it through CTest,
`station_twin_e2e`, with ZS_STATION_TWIN pointing at the freshly built binary).

Runs zs_station_twin with the Python server twin on the pipe and checks the server-side report:
  1. a drone fly-by is detected, published over GSM, acknowledged, no duplicates; the audio prehistory ring holds the
     seconds around the event, including the post-event window; the server asks for the event's audio
     (CMD_REQUEST_AUDIO, both segments) right after the receipt, the station waits for the post-event window, uploads
     both segments chunk by chunk and acknowledges with the chunk count; the server stores them through the bridge's
     ingest (station.audio_ingest: parts in SQLite, SHA-256, WAV) and the ACK closes the request in the store;
  2. a burst of events during a GSM outage goes out over LoRa (30 % loss both ways) once the link is marked
     degraded, every event is delivered exactly once, and a GSM probe restores the link when the network returns.
  3. remote commands (ICD addendum D): the server signs CMD_SET_PARAMS and CMD_REBOOT, the station verifies them
     against its wall clock, executes, acknowledges; the reboot happens after its ACK, the parameters survive it,
     and the same reboot redelivered is answered from the journal without a second reset.
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


def run(args: list[str], commands: str = "", audio: str = "", redeliver: bool = False) -> tuple[str, dict]:
    env = dict(os.environ, ZS_TWIN_COMMANDS=commands, ZS_TWIN_AUDIO=audio, ZS_TWIN_AUDIO_REDELIVER="1" if redeliver else "")
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
                  "--expect-post-audio", "25"], audio="both", redeliver=True)
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
    # the server side ran the bridge's ingest: the request is closed in the store and no part is left over
    assert r["audio_store"] == {"acked": True, "ack_result": 0, "ack_detail": r["audio_chunks"], "pending_parts": 0}, r["audio_store"]
    pre, post = segs["pre"], segs["post"]
    assert pre["seconds"] >= 10 and post["seconds"] >= 25, segs                        # continuous audio on both sides
    assert pre["start_time_us"] + pre["seconds"] * 1e6 > event["time_us"] - 1e6       # pre reaches the event
    assert post["start_time_us"] <= event["time_us"] < post["start_time_us"] + 1e6     # post starts at the event
    print(f"scenario 1 (drone over GSM): detections {r['detections']}, heartbeats {r['heartbeats']}, duplicates {r['duplicates']}; "
          f"prehistory: {rec_line.split('around the first event: ')[1]}; audio upload: {r['audio_chunks']} chunks, "
          f"pre {pre['seconds']:.0f} s + post {post['seconds']:.0f} s assembled, ACK OK")

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
    return 0


if __name__ == "__main__":
    sys.exit(main())
