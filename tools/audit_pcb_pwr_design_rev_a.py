#!/usr/bin/env python3
"""Independent calculation and freeze audit for EVT-PRE-20 PCB-PWR Rev.A.

This is the first control contour for PCB-PWR and deliberately does not import any
future schematic/PCB generator. Numeric expectations are read from a machine-readable
controlled baseline and independently recomputed here. The audit can authorize native
capture, but it can never authorize FOR_MANUFACTURE while release_open_items remain.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def close(actual: float, expected: float, abs_tol: float, label: str) -> None:
    if not math.isclose(actual, expected, rel_tol=0.0, abs_tol=abs_tol):
        raise RuntimeError(
            f"{label}: actual={actual:.12g}, expected={expected:.12g}, tol={abs_tol:.12g}"
        )


def read_freeze(path: Path) -> dict[str, dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    require(rows, f"empty component freeze: {path}")
    by_id: dict[str, dict[str, str]] = {}
    for row in rows:
        cid = row.get("Component_ID", "").strip()
        require(cid, f"component freeze row without Component_ID: {row}")
        require(cid not in by_id, f"duplicate Component_ID in freeze: {cid}")
        by_id[cid] = row
    return by_id


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--baseline",
        type=Path,
        default=ROOT / "hardware" / "POWER_DESIGN_BASELINE_REV_A.json",
    )
    ap.add_argument(
        "--freeze",
        type=Path,
        default=ROOT / "hardware" / "POWER_COMPONENT_FREEZE_REV_A.csv",
    )
    ap.add_argument(
        "--calc-doc",
        type=Path,
        default=ROOT / "hardware" / "POWER_DESIGN_CALC_REV_A.md",
    )
    ap.add_argument(
        "--output",
        type=Path,
        default=ROOT / "artifacts" / "kicad-native" / "PCB-PWR" / "design_audit.json",
    )
    args = ap.parse_args()

    baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
    freeze = read_freeze(args.freeze)
    calc_doc = args.calc_doc.read_text(encoding="utf-8")
    checks: list[dict[str, object]] = []

    def record(name: str, **data: object) -> None:
        checks.append({"check": name, "status": "PASS", **data})

    require(baseline["configuration"] == "EVT-PRE-20 Rev.A", "configuration mismatch")
    require(
        baseline["status"] == "CAPTURE_BASELINE_NOT_FOR_MANUFACTURE",
        "PCB-PWR baseline must remain explicitly NOT FOR MANUFACTURE",
    )
    record("baseline_identity", configuration=baseline["configuration"], status=baseline["status"])

    # Cross-check exact component identities against the separate component-freeze file.
    expected_mpns = {
        "PWR-REV-CTL": baseline["reverse_protection"]["controller_mpn"],
        "PWR-REV-FET": baseline["reverse_protection"]["mosfet_mpn"],
        "U-PWR1": baseline["buck_3v8"]["mpn"],
        "U-PWR2": baseline["buck_3v3"]["mpn"],
        "U-PWR3": baseline["mic_ldo"]["mpn"],
        "U-MON-01": baseline["current_monitor"]["mpn"],
    }
    for cid, mpn in expected_mpns.items():
        require(cid in freeze, f"missing frozen component {cid}")
        require(freeze[cid]["MPN"].strip() == mpn, f"{cid} MPN mismatch: {freeze[cid]['MPN']} != {mpn}")
    require("PWR-TVS-01" in freeze and "CANDIDATE" in freeze["PWR-TVS-01"]["Status"], "TVS must remain candidate until surge profile freeze")
    require("PWR-FUSE-01" in freeze and "CANDIDATE" in freeze["PWR-FUSE-01"]["Status"], "PCB fuse must remain candidate until coordination test")
    record("component_freeze_crosscheck", exact_mpns=expected_mpns)

    # The human calculation record is a separate controlled representation. Make drift
    # between it and the machine baseline blocking before schematic capture starts.
    required_doc_tokens = [
        "CAPTURE BASELINE - NOT FOR MANUFACTURE",
        "LM74700QDBVRQ1",
        "CSD18540Q5B",
        "LMR604403SRAKR",
        "TPS7A2018PDBVR",
        "INA226AIDGSR",
        "400 kHz",
        "4.7 uH",
        "86.6 kOhm",
        "35.7 kOhm",
        "10 mOhm",
        "2560",
    ]
    missing_tokens = [token for token in required_doc_tokens if token not in calc_doc]
    require(not missing_tokens, f"POWER_DESIGN_CALC_REV_A.md drift/missing controlled tokens: {missing_tokens}")
    record("human_calc_record_crosscheck", tokens=len(required_doc_tokens))

    inp = baseline["input"]
    rev = baseline["reverse_protection"]
    b38 = baseline["buck_3v8"]
    b33 = baseline["buck_3v3"]
    modem = baseline["modem"]
    ldo = baseline["mic_ldo"]
    mon = baseline["current_monitor"]

    require(inp["working_min_v"] < inp["working_max_v"], "invalid provisional battery working window")
    require(rev["controller_vin_min_v"] <= inp["working_min_v"] <= rev["controller_vin_max_v"], "battery low end outside LM74700 controller range")
    require(rev["controller_vin_min_v"] <= inp["working_max_v"] <= rev["controller_vin_max_v"], "battery high end outside LM74700 controller range")
    require(b38["vin_min_v"] <= inp["working_min_v"] and inp["working_max_v"] <= b38["vin_max_v"], "battery working window outside LMR60440 range")
    require(not inp["actual_battery_bms_limits_frozen"], "unexpected claim that battery/BMS limits are frozen")
    require(not inp["transient_envelope_frozen"], "unexpected claim that transient envelope is frozen")
    record("input_window", working_v=[inp["working_min_v"], inp["working_max_v"]], release_limits_frozen=False)

    require(rev["mosfet_vds_v"] >= 60.0, "reverse MOSFET VDS margin changed below 60 V")
    require(rev["mosfet_rds_on_max_mohm_at_10v"] <= 2.2, "reverse MOSFET Rds(on) exceeds baseline")
    record("reverse_protection_ratings", controller_vin_max_v=rev["controller_vin_max_v"], mosfet_vds_v=rev["mosfet_vds_v"])

    # LMR60440 3.8-V adjustable rail: recompute independently from VFB and divider.
    rfbt = float(b38["rfbt_ohm"])
    rfbb = float(b38["rfbb_ohm"])
    vfb = float(b38["vfb_typ_v"])
    calculated_vout = vfb * (1.0 + rfbt / rfbb)
    close(calculated_vout, 3.8011204481792717, 1e-9, "3V8 divider recomputation")
    require(abs(calculated_vout - b38["target_vout_v"]) <= 0.005, "3V8 nominal divider error exceeds 5 mV capture target")
    require(modem["vbat_min_v"] < calculated_vout < modem["vbat_max_v"], "3V8 nominal outside BG95-M3 VBAT range")
    require(b38["adjustable_min_v"] <= calculated_vout <= b38["adjustable_max_v"], "3V8 target outside LMR60440 adjustable range")
    record(
        "buck_3v8_feedback",
        vout_calculated_v=calculated_vout,
        low_margin_v=calculated_vout - modem["vbat_min_v"],
        high_margin_v=modem["vbat_max_v"] - calculated_vout,
    )

    # TI 400-kHz application baseline cross-checks.
    close(float(b38["switching_frequency_hz"]), 400000.0, 0.1, "3V8 switching frequency")
    close(float(b38["rt_ohm"]), 86600.0, 0.1, "3V8 RT")
    close(float(b38["inductor_h"]), 4.7e-6, 1e-12, "3V8 inductance")
    require(float(b38["cout_effective_min_f"]) >= 54e-6, "3V8 effective COUT below 54 uF")
    require(float(b38["cin_min_f"]) >= 4.7e-6, "3V8 CIN below 4.7 uF")
    close(float(b38["cboot_f"]), 100e-9, 1e-12, "3V8 CBOOT")
    require(float(b38["cboot_voltage_min_v"]) >= 10.0, "3V8 CBOOT voltage rating below 10 V")
    require(float(b38["inductor_isat_min_a"]) >= 6.0, "3V8 inductor Isat target below 6 A")
    require(float(b38["inductor_irms_min_a"]) >= 4.5, "3V8 inductor Irms target below 4.5 A")
    record("buck_3v8_passives", frequency_hz=b38["switching_frequency_hz"], rt_ohm=b38["rt_ohm"], inductor_h=b38["inductor_h"])

    # The two BG95 supply domains can reach the documented peaks. For capture sizing,
    # verify the arithmetic sum remains below the dedicated 4-A converter rating.
    modem_peak_sum = float(modem["vbat_bb_peak_a"]) + float(modem["vbat_rf_peak_a"])
    require(modem_peak_sum <= float(b38["current_a"]), "BG95 documented peak-domain sum exceeds 3V8 converter rating")
    require(modem["star_split_required"], "BG95 VBAT_BB/VBAT_RF star split must remain required")
    require(float(modem["local_bulk_bb_min_f"]) >= 100e-6, "BG95 BB bulk below 100 uF capture baseline")
    require(float(modem["local_bulk_rf_min_f"]) >= 100e-6, "BG95 RF bulk below 100 uF capture baseline")
    record("bg95_peak_current_headroom", peak_sum_a=modem_peak_sum, converter_rating_a=b38["current_a"], headroom_a=float(b38["current_a"]) - modem_peak_sum)

    close(float(b33["fixed_output_v"]), 3.3, 1e-9, "3V3 fixed output")
    close(float(b33["switching_frequency_hz"]), 400000.0, 0.1, "3V3 switching frequency")
    close(float(b33["rt_ohm"]), 86600.0, 0.1, "3V3 RT")
    close(float(b33["inductor_h"]), 4.7e-6, 1e-12, "3V3 inductance")
    require(float(b33["cout_effective_min_f"]) >= 54e-6, "3V3 effective COUT below 54 uF")
    record("buck_3v3_fixed_mode", output_v=b33["fixed_output_v"], mpn=b33["mpn"])

    close(float(ldo["input_v"]), 3.3, 1e-9, "mic LDO input")
    close(float(ldo["output_v"]), 1.8, 1e-9, "mic LDO output")
    require(float(ldo["current_a"]) >= 0.3, "mic LDO rating below 300 mA")
    require(float(ldo["cin_effective_min_f"]) >= 1e-6, "mic LDO effective CIN below 1 uF")
    require(float(ldo["cout_effective_min_f"]) >= 1e-6, "mic LDO effective COUT below 1 uF")
    record("mic_ldo", output_v=ldo["output_v"], current_a=ldo["current_a"])

    # INA226 independent range and calibration calculations.
    ishunt = float(mon["expected_current_max_a"])
    rshunt = float(mon["shunt_ohm"])
    vshunt = ishunt * rshunt
    pshunt = ishunt * ishunt * rshunt
    min_current_lsb = ishunt / 32768.0
    max_representable_current = float(mon["current_lsb_a"]) * 32767.0
    cal = 0.00512 / (float(mon["current_lsb_a"]) * rshunt)
    power_lsb = 25.0 * float(mon["current_lsb_a"])
    require(vshunt < float(mon["shunt_input_abs_max_v"]), "INA226 5-A shunt voltage exceeds input range")
    require(pshunt <= 0.25, "10-mOhm shunt dissipation unexpectedly exceeds 0.25 W at 5 A")
    require(float(mon["shunt_power_rating_min_w"]) >= 4.0 * pshunt, "shunt rating has less than 4x nominal power margin")
    require(float(mon["current_lsb_a"]) >= min_current_lsb, "chosen INA226 Current_LSB is too small for 5-A range")
    require(max_representable_current >= ishunt, "chosen INA226 Current_LSB cannot represent 5 A")
    close(cal, float(mon["calibration_register"]), 1e-9, "INA226 CAL")
    close(power_lsb, float(mon["power_lsb_w"]), 1e-12, "INA226 Power_LSB")
    record(
        "ina226_calibration",
        vshunt_at_5a_v=vshunt,
        pshunt_at_5a_w=pshunt,
        minimum_current_lsb_a=min_current_lsb,
        selected_current_lsb_a=mon["current_lsb_a"],
        max_representable_current_a=max_representable_current,
        calibration=cal,
        power_lsb_w=power_lsb,
    )

    required_open = {
        "battery_bms_voltage_limits",
        "mppt_transient_envelope",
        "tvs_final_value_and_pulse_coordination",
        "pcb_fuse_final_value_and_fault_energy_coordination",
        "inductor_exact_mpn_and_thermal_margin",
        "mlcc_and_bulk_exact_mpn_with_dc_bias_and_cold_esr",
        "shunt_exact_mpn_and_kelvin_layout",
        "reverse_mosfet_soa_and_gate_transient_review",
        "plus70c_thermal_test",
        "minus40c_cold_start_test",
        "load_step_and_bg95_pulse_test",
        "standby_s0_measurement",
        "emc_emi_evidence",
        "review_a",
        "review_b",
    }
    open_items = set(baseline.get("release_open_items", []))
    require(required_open.issubset(open_items), f"release blocker set weakened: missing {sorted(required_open - open_items)}")
    record("manufacturing_release_blockers_preserved", count=len(open_items))

    result = {
        "configuration": baseline["configuration"],
        "audit": "PCB-PWR Rev.A independent calculation/freeze audit",
        "capture_gate": "PASS_NATIVE_CAPTURE_ALLOWED",
        "manufacturing_release": "BLOCKED_NOT_FOR_MANUFACTURE",
        "checks": checks,
        "derived": {
            "buck_3v8_nominal_v": calculated_vout,
            "bg95_peak_domain_sum_a": modem_peak_sum,
            "ina226_vshunt_at_5a_v": vshunt,
            "ina226_pshunt_at_5a_w": pshunt,
            "ina226_min_current_lsb_a": min_current_lsb,
            "ina226_calibration": cal,
            "ina226_power_lsb_w": power_lsb,
        },
        "release_open_items": sorted(open_items),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print("PCB-PWR independent calculation/freeze audit PASS")
    print(f"3V8 nominal={calculated_vout:.6f} V; BG95 peak sum={modem_peak_sum:.3f} A")
    print(f"INA226: Vshunt={vshunt:.6f} V Pshunt={pshunt:.6f} W CAL={cal:.1f}")
    print(f"Manufacturing release remains BLOCKED with {len(open_items)} open controls")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
