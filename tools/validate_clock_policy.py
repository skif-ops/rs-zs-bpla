#!/usr/bin/env python3
"""Cross-check EVT-PRE-20 Rev.A clock policy across configuration, hardware and firmware."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def main() -> None:
    baseline = text("config/EVT_PRE_20_BASELINE.yaml")
    target = text("firmware/targets/evt_pre_20/target_status.yaml")
    capture = text("hardware/kicad/REV_A_CAPTURE_SPEC.md")
    policy = text("hardware/CLOCKING_REV_A.md")
    decisions = text("docs/DECISION_LOG.csv")
    bom = text("hardware/EVT_PRE_20_BOM_DRAFT.csv")

    policy_id = "REV_A_INTERNAL_HSI_MSI_PLL_NO_HSE"
    sit = "SiT1552AI-JE-DCC-32.768D"

    require(policy_id in baseline, "baseline clock policy id mismatch")
    require(policy_id in target, "firmware target clock policy id mismatch")
    require(policy_id in capture, "KiCad capture spec clock policy id mismatch")
    require("external_hse_crystal_or_oscillator: false" in baseline, "baseline still allows external HSE")
    require("external_hse: DISABLED_NOT_FITTED" in target, "firmware target still allows external HSE")
    require("no external HSE crystal or HSE oscillator" in policy, "clock policy does not explicitly prohibit HSE")
    require("DEC-016" in decisions and "MSI HSI and PLL" in decisions and ",LOCKED," in decisions, "DEC-016 clock decision is missing or not locked")
    require(sit in baseline, "baseline 32.768 kHz reference mismatch")
    require(sit in target, "firmware target 32.768 kHz reference mismatch")
    require(sit in policy, "hardware clock policy 32.768 kHz reference mismatch")
    require(sit in bom, "BOM does not contain the selected SiT1552 reference")
    require("USB_CLOCK" in target and "PDM_SAMPLE_RATE" in target and "PPS_TIMESTAMPING" in target, "target clock validation matrix incomplete")
    require("Do not place an HSE footprint" in capture, "KiCad Rev.A still permits an HSE footprint")

    print("EVT-PRE-20 Rev.A clock policy cross-check: PASS")


if __name__ == "__main__":
    main()
