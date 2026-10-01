#!/usr/bin/env python3
"""Acceptance metrics of a trial (decision 5, docs/ACCEPTANCE_METRICS.md).

    python tools/acceptance_metrics.py report --db data/zs_bpla.sqlite3 --trial trial.json \
        [--json report.json] [--md report.md] [--audio-cal-dbfs -32.4] [--max-range 3000] [--assoc-range 3000] \
        [--pd-threshold 0.8] [--sigma-deg 3]
    python tools/acceptance_metrics.py calibrate --wav calibrator_94db.wav

``report`` reads the server's event store (detections, bearings, fused tracks, uploaded audio) over the trial window
and the ground truth file (``dioneya.trial/1``) and writes the metrics as JSON and as a Markdown report (stdout when
neither file is given).  ``calibrate`` measures the level of a recording of a 94 dB SPL calibrator made by the station
(CMD_REQUEST_AUDIO with the calibrator on the microphone port): the dBFS it prints is ``--audio-cal-dbfs``.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SERVER = Path(__file__).resolve().parents[1]


def _modules():
    if str(SERVER) not in sys.path:
        sys.path.insert(0, str(SERVER))
    from station import acceptance
    from station.store import EventStore
    return acceptance, EventStore


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    rep = sub.add_parser("report", help="metrics of a trial")
    rep.add_argument("--db", required=True, help="event store of the server (sqlite)")
    rep.add_argument("--trial", required=True, help="ground truth, dioneya.trial/1 JSON")
    rep.add_argument("--json", help="write the metrics here")
    rep.add_argument("--md", help="write the report here")
    rep.add_argument("--audio-cal-dbfs", type=float, help="dBFS of the 94 dB SPL calibrator through the station (calibrate)")
    rep.add_argument("--max-range", type=float, default=3000.0, help="opportunity: the target came this close (m)")
    rep.add_argument("--assoc-range", type=float, default=3000.0, help="a report belongs to a pass within this range (m)")
    rep.add_argument("--pd-threshold", type=float, default=0.8)
    rep.add_argument("--sigma-deg", type=float, help="bearing sigma for the geometry (default: median of the trial)")
    cal = sub.add_parser("calibrate", help="level of a calibrator recording")
    cal.add_argument("--wav", required=True)
    args = ap.parse_args(argv)
    acceptance, EventStore = _modules()

    if args.cmd == "calibrate":
        level = acceptance.wav_level_dbfs(args.wav)
        if level is None:
            print("recording too short or silent", file=sys.stderr)
            return 2
        print(f"{level:.1f} dBFS for 94 dB SPL: --audio-cal-dbfs {level:.1f}")
        return 0

    db = Path(args.db)
    if not db.is_file():
        print(f"no event store at {db}", file=sys.stderr)
        return 2
    store = EventStore(db)
    try:
        trial = acceptance.load_trial(args.trial, store)
    except (OSError, ValueError, KeyError) as exc:
        print(f"trial file: {exc}", file=sys.stderr)
        return 2
    crit = acceptance.Criteria(max_range_m=args.max_range, assoc_range_m=args.assoc_range, pd_threshold=args.pd_threshold,
                               sigma_deg=args.sigma_deg, audio_cal_dbfs_at_94=args.audio_cal_dbfs)
    result = acceptance.evaluate(store, trial, crit)
    text = acceptance.markdown(result)
    if args.json:
        Path(args.json).write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    if args.md:
        Path(args.md).write_text(text, encoding="utf-8")
    if not args.json and not args.md:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
