#!/usr/bin/env python3
"""Generate the PCB-MAIN Rev.A pre-route constraint manifest.

The manifest classifies every non-empty native net and applies the accepted EVT
public-stackup geometry. It is a controlled Review-B input, not evidence that
the board is routed or manufacturable.
"""
from __future__ import annotations

import argparse
import csv
import io
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from audit_pcb_main_native_schematic_rev_a import expected_components  # noqa: E402

OUT = ROOT / "hardware" / "PCB_MAIN_ROUTING_AUTHORITY_REV_A.csv"
STATUS = "PRE_ROUTE_CONSTRAINT_CONTROLLED_ROUTING_NOT_COMPLETE"
PCB_RULES = "hardware/kicad/PCB_RULES.md"

FIELDS = [
    "Net_Name",
    "Route_Class",
    "Reference_Domain",
    "Topology",
    "Impedance_Target",
    "Geometry_Rule",
    "Pair_Group",
    "Pair_Mate",
    "Length_Group",
    "Length_Rule",
    "Layer_Rule",
    "Via_Rule",
    "Priority",
    "Source_Authority",
    "Status",
]

CLASS_NETS = {
    "RETURN_PLANE": {
        "GND_DIGITAL", "GND_MIC", "GND_MODEM",
    },
    "RF_50OHM": {
        "CELL_RF", "CELL_RF_ANT",
        "GNSS_RF_ANT_BIASED", "GNSS_RF_DC_BLOCK", "GNSS_RF_FILTERED",
        "LORA_RF_ANT", "LORA_RF_MODULE",
    },
    "USB_90OHM_DIFF": {
        "USB_DM_CONN", "USB_DM_U1", "USB_DP_CONN", "USB_DP_U1",
        "CELL_USB_DM_TP", "CELL_USB_DM_U8", "CELL_USB_DP_TP", "CELL_USB_DP_U8",
    },
    "MODEM_BURST_POWER": {
        "3V8_MODEM", "3V8_MODEM_BB", "3V8_MODEM_RF",
    },
    "SWITCH_NODE": {"SMPS_SW"},
    "POWER_RAIL": {
        "1V8_MIC", "3V3_DIGITAL", "CELL_USB_VBUS", "CELL_USIM_VDD_1V8",
        "GNSS_ANT_BIAS_RAW", "GNSS_ANT_SWITCHED", "SIM1_VDD_CONN",
        "SIM2_VDD_CONN", "U8_VDD_EXT_1V8", "USB_VBUS_CONN", "VCORE_1V1", "VREF+",
    },
    "EDGE_CLOCK": {
        "AAD_CFG", "AAD_CFG_1V8_FANOUT", "AAD_CFG_1V8_U7", "CELL_USIM_CLK_1V8",
        "GNSS_PPS_U1", "GNSS_PPS_U9", "LORA_SCK_U1", "LORA_SCK_U10", "LSE_IN",
        "NOR_CLK_U1", "NOR_CLK_U2", "NRF_SWCLK", "PDM_CLK",
        "PDM_CLK_1V8_FANOUT", "PDM_CLK_1V8_U7", "SD_CK_CARD", "SD_CK_U1",
        "SIM1_CLK_CONN", "SIM1_CLK_MUX", "SIM2_CLK_CONN", "SIM2_CLK_MUX", "SWCLK",
    },
    "EDGE_DATA": {
        "CELL_USIM_DATA_1V8", "CELL_USIM_RST_1V8",
        "LORA_MISO_U1", "LORA_MISO_U10", "LORA_MOSI_U1", "LORA_MOSI_U10",
        "LORA_NSS_U1", "LORA_NSS_U10", "NOR_NCS_U2",
        "NOR_IO0_U1", "NOR_IO0_U2", "NOR_IO1_U1", "NOR_IO1_U2",
        "NOR_IO2_U1", "NOR_IO2_U2", "NOR_IO3_U1", "NOR_IO3_U2",
        "PDM_DATA1", "PDM_DATA1_1V8", "PDM_DATA2", "PDM_DATA2_1V8",
        "PDM_DATA3", "PDM_DATA3_1V8", "PDM_DATA4", "PDM_DATA4_1V8",
        "SD_CMD_CARD", "SD_CMD_U1", "SD_D0_CARD", "SD_D0_U1", "SD_D1_CARD",
        "SD_D1_U1", "SD_D2_CARD", "SD_D2_U1", "SD_D3_CARD", "SD_D3_U1",
        "SIM1_DATA_CONN", "SIM1_DATA_MUX", "SIM1_RST_CONN", "SIM1_RST_MUX",
        "SIM2_DATA_CONN", "SIM2_DATA_MUX", "SIM2_RST_CONN", "SIM2_RST_MUX",
    },
    "I2C_OPEN_DRAIN": {
        "I2C2_SCL_BUS", "I2C2_SCL_U1", "I2C2_SDA_BUS", "I2C2_SDA_U1",
    },
    "UART_SIGNAL": {
        "BLE_RX_U1", "BLE_RX_U11", "BLE_TX_U1", "BLE_TX_U11",
        "GNSS_RX_U1", "GNSS_RX_U9", "GNSS_TX_U1", "GNSS_TX_U9",
        "CELL_DBG_RXD_TP", "CELL_DBG_RXD_U8", "CELL_DBG_TXD_TP", "CELL_DBG_TXD_U8",
        "CELL_RX_U16", "CELL_TX_U16", "U8_MAIN_RXD_1V8", "U8_MAIN_TXD_1V8",
        "TEST_UART_RX_TP", "TEST_UART_RX_U1", "TEST_UART_TX_TP", "TEST_UART_TX_U1",
    },
    "MIC_WAKE_SIGNAL": {
        "MIC_WAKE", "MIC_WAKE1", "MIC_WAKE12_OR_1V8", "MIC_WAKE2", "MIC_WAKE3",
        "MIC_WAKE34_OR_1V8", "MIC_WAKE4", "MIC_WAKE_OR_1V8",
    },
    "ANALOG_SENSE_BIAS": {
        "CELL_DBG_VREF_TP", "GNSS_ANT_DETECT", "GNSS_ANT_DIV", "GNSS_ANT_GATE",
        "GNSS_ANT_OFF_N", "GNSS_ANT_SHORT_N", "USB_CC1", "USB_CC2", "USB_SHIELD",
        "USB_VBUS_SENSE",
    },
    "MODEM_SIM_CONTROL": {
        "CELL_DTR_U16", "CELL_PWRKEY_CMD", "CELL_RESET_N_CMD", "CELL_RI_U16",
        "CELL_STATUS_U16", "CELL_USB_BOOT_1V8", "Q1_BASE", "Q2_BASE", "Q3_BASE",
        "SIM1_DET", "SIM2_DET", "SIM_MUX_EN", "SIM_MUX_SEL", "U13_EN_N",
        "U8_MAIN_DTR_1V8", "U8_MAIN_RI_1V8", "U8_PWRKEY_N", "U8_RESET_N",
        "U8_STATUS_1V8",
    },
    "FIXTURE_DEBUG": {
        "BOOT0", "CELL_USB_BOOT_TP", "NRF_SWDIO", "NRST", "REV_STRAP0",
        "REV_STRAP1", "SWDIO",
    },
    "LOW_SPEED_CONTROL": {
        "ACCEL_INT", "BLE_DFU_REQ", "BLE_EN", "EN_AUX", "EN_MODEM", "FAULT",
        "HW_REV0", "HW_REV1", "LORA_BUSY", "LORA_DIO1", "LORA_RESET_N",
        "LORA_RXEN", "LORA_TXEN", "NRF_RESET_N", "PWR_FAULT", "PWR_GOOD",
        "SD_DET", "TAMPER_IN_CONN", "TAMPER_IN_U1",
    },
}

USB_PAIRS = {
    "USB_DM_U1": ("USB_MAIN_MCU_SEGMENT", "USB_DP_U1"),
    "USB_DP_U1": ("USB_MAIN_MCU_SEGMENT", "USB_DM_U1"),
    "USB_DM_CONN": ("USB_MAIN_CONNECTOR_SEGMENT", "USB_DP_CONN"),
    "USB_DP_CONN": ("USB_MAIN_CONNECTOR_SEGMENT", "USB_DM_CONN"),
    "CELL_USB_DM_U8": ("USB_CELL_MODEM_SEGMENT", "CELL_USB_DP_U8"),
    "CELL_USB_DP_U8": ("USB_CELL_MODEM_SEGMENT", "CELL_USB_DM_U8"),
    "CELL_USB_DM_TP": ("USB_CELL_FIXTURE_SEGMENT", "CELL_USB_DP_TP"),
    "CELL_USB_DP_TP": ("USB_CELL_FIXTURE_SEGMENT", "CELL_USB_DM_TP"),
}

CROSS_MODEM_DIGITAL = {
    "CELL_DTR_U16", "CELL_PWRKEY_CMD", "CELL_RESET_N_CMD", "CELL_RI_U16",
    "CELL_RX_U16", "CELL_STATUS_U16", "CELL_TX_U16", "SIM1_DET", "SIM2_DET",
    "SIM_MUX_EN", "SIM_MUX_SEL",
}
CROSS_MIC_DIGITAL = {
    "AAD_CFG_1V8_FANOUT", "MIC_WAKE_OR_1V8", "PDM_CLK_1V8_FANOUT",
    "PDM_DATA1_1V8", "PDM_DATA2_1V8", "PDM_DATA3_1V8", "PDM_DATA4_1V8",
}


def native_nets() -> list[str]:
    return sorted({
        pin["native"]
        for component in expected_components().values()
        if component["on_board"]
        for pin in component["pins"].values()
        if pin["native"] != "NC"
    })


def route_class(net: str) -> str:
    matches = [name for name, members in CLASS_NETS.items() if net in members]
    if len(matches) != 1:
        raise RuntimeError(f"{net}: expected one route class, got {matches}")
    return matches[0]


def reference_domain(net: str, cls: str) -> str:
    if cls == "RETURN_PLANE":
        return "SELF"
    if cls == "MODEM_BURST_POWER":
        return "GND_MODEM"
    if net in {"1V8_MIC", "3V3_DIGITAL"}:
        return "RETURN_AT_LOAD_PER_GROUND_AUTHORITY"
    if net in {
        "CELL_USB_VBUS", "CELL_USIM_VDD_1V8", "SIM1_VDD_CONN",
        "SIM2_VDD_CONN", "U8_VDD_EXT_1V8",
    }:
        return "GND_MODEM"
    if cls == "POWER_RAIL":
        return "GND_DIGITAL"
    if net == "USB_SHIELD":
        return "SHIELD_COUPLING_NETWORK_REVIEW_B"
    if net in CROSS_MODEM_DIGITAL:
        return "CROSS_GND_DIGITAL_GND_MODEM_REVIEW_B"
    if net in CROSS_MIC_DIGITAL:
        return "CROSS_GND_DIGITAL_GND_MIC_REVIEW_B"
    if (net.startswith(("CELL_", "U8_", "SIM1_", "SIM2_", "SIM_MUX", "U13_"))
            or net in {"Q1_BASE", "Q2_BASE", "Q3_BASE"}):
        return "GND_MODEM"
    if net.startswith("MIC_WAKE") and net != "MIC_WAKE":
        return "GND_MIC"
    return "GND_DIGITAL"


def source_authority(net: str, cls: str) -> str:
    sources = [PCB_RULES]
    if cls == "RETURN_PLANE":
        sources.append("hardware/PCB_MAIN_GROUND_DOMAIN_AUTHORITY_REV_A.md")
    if net.startswith(("CELL_", "U8_")) or net in {
        "3V8_MODEM", "3V8_MODEM_BB", "3V8_MODEM_RF", "Q1_BASE", "Q2_BASE",
    }:
        sources.append("hardware/PCB_MAIN_CELLULAR_AUTHORITY_REV_A.md")
    if net.startswith(("SIM1_", "SIM2_", "SIM_MUX", "U13_")) or net == "Q3_BASE":
        sources.append("hardware/PCB_MAIN_DUAL_SIM_AUTHORITY_REV_A.md")
    if net.startswith("GNSS_"):
        sources.append("hardware/PCB_MAIN_GNSS_AUTHORITY_REV_A.md")
    if net.startswith("LORA_"):
        sources.append("hardware/PCB_MAIN_LORA_AUTHORITY_REV_A.md")
    if net.startswith(("BLE_", "NRF_")):
        sources.append("hardware/PCB_MAIN_BLE_AUTHORITY_REV_A.md")
    if net.startswith(("PDM_", "MIC_", "AAD_")) or net == "1V8_MIC":
        sources.append("hardware/PCB_MAIN_AUDIO_LOGIC_AUTHORITY_REV_A.md")
    if net.startswith(("NOR_", "I2C2_")) or net == "ACCEL_INT":
        sources.append("hardware/PCB_MAIN_STORAGE_SENSOR_AUTHORITY_REV_A.md")
    if (net.startswith(("SD_", "USB_", "TEST_", "TAMPER_"))
            or cls == "FIXTURE_DEBUG"):
        sources.append("hardware/PCB_MAIN_CONNECTOR_FIXTURE_AUTHORITY_REV_A.md")
    if len(sources) == 1:
        sources.append("hardware/PCB_MAIN_MCU_PIN_AUTHORITY_REV_A.md")
    if cls in {"RF_50OHM", "USB_90OHM_DIFF", "MODEM_BURST_POWER", "EDGE_CLOCK", "EDGE_DATA"}:
        sources.append("hardware/PCB_MAIN_PASSIVE_SUPPORT_AUTHORITY_REV_A.md")
    return ";".join(dict.fromkeys(sources))


def length_group(net: str) -> str:
    if net in USB_PAIRS:
        return USB_PAIRS[net][0]
    groups = [
        ("OCTOSPI_U1", ("NOR_CLK_U1", "NOR_IO0_U1", "NOR_IO1_U1", "NOR_IO2_U1", "NOR_IO3_U1", "NOR_NCS_U2")),
        ("OCTOSPI_U2", ("NOR_CLK_U2", "NOR_IO0_U2", "NOR_IO1_U2", "NOR_IO2_U2", "NOR_IO3_U2", "NOR_NCS_U2")),
        ("SDIO_U1", ("SD_CK_U1", "SD_CMD_U1", "SD_D0_U1", "SD_D1_U1", "SD_D2_U1", "SD_D3_U1")),
        ("SDIO_CARD", ("SD_CK_CARD", "SD_CMD_CARD", "SD_D0_CARD", "SD_D1_CARD", "SD_D2_CARD", "SD_D3_CARD")),
        ("LORA_SPI_U1", ("LORA_SCK_U1", "LORA_MISO_U1", "LORA_MOSI_U1", "LORA_NSS_U1")),
        ("LORA_SPI_U10", ("LORA_SCK_U10", "LORA_MISO_U10", "LORA_MOSI_U10", "LORA_NSS_U10")),
        ("PDM_DIGITAL", ("PDM_CLK", "PDM_DATA1", "PDM_DATA2", "PDM_DATA3", "PDM_DATA4")),
        ("PDM_MIC_SIDE", ("PDM_CLK_1V8_FANOUT", "PDM_DATA1_1V8", "PDM_DATA2_1V8", "PDM_DATA3_1V8", "PDM_DATA4_1V8")),
    ]
    memberships = [name for name, members in groups if net in members]
    return ";".join(memberships)


def row_for(net: str) -> dict[str, str]:
    cls = route_class(net)
    topology = {
        "RETURN_PLANE": "DOMAIN_PLANE_NO_PCB_MAIN_NET_TIE",
        "RF_50OHM": "SERIES_CHAIN_NO_STUB",
        "USB_90OHM_DIFF": "DIFFERENTIAL_SERIES_SEGMENT",
        "MODEM_BURST_POWER": "STAR_FEED_SHORT_WIDE_BRANCH",
        "SWITCH_NODE": "LOCAL_POINT_TO_POINT_NO_TEST_STUB",
        "POWER_RAIL": "PLANE_OR_SHORT_WIDE_BRANCH",
        "EDGE_CLOCK": "SOURCE_SERIES_SEGMENT_OR_CONTROLLED_FANOUT",
        "EDGE_DATA": "SOURCE_SERIES_SEGMENT_OR_POINT_TO_POINT",
        "I2C_OPEN_DRAIN": "OPEN_DRAIN_MULTI_DROP",
        "UART_SIGNAL": "POINT_TO_POINT_SERIES_SEGMENT",
        "MIC_WAKE_SIGNAL": "POINT_TO_POINT_OR_CONTROLLED_OR_TREE",
        "ANALOG_SENSE_BIAS": "POINT_TO_POINT_OR_SUPERVISOR_NETWORK",
        "MODEM_SIM_CONTROL": "POINT_TO_POINT_FAIL_CLOSED_CONTROL",
        "FIXTURE_DEBUG": "POINT_TO_POINT_FIXTURE_ONLY",
        "LOW_SPEED_CONTROL": "POINT_TO_POINT_OR_STATIC_STRAP",
    }[cls]
    impedance = {
        "RF_50OHM": "50_OHM_SINGLE_ENDED_EVT_STACKUP_ACCEPTED",
        "USB_90OHM_DIFF": "90_OHM_DIFFERENTIAL_EVT_STACKUP_ACCEPTED",
    }.get(cls, "NOT_CONTROLLED_IMPEDANCE")
    geometry = "FABRICATOR_MINIMUMS_AND_REVIEW_B"
    if cls == "RETURN_PLANE":
        geometry = "PLANE_GEOMETRY_AND_VOID_REVIEW_B"
    elif cls == "RF_50OHM":
        geometry = "WIDTH_0P1509MM_JLC06161H_3313_L1_OVER_L2"
    elif cls == "USB_90OHM_DIFF":
        geometry = "WIDTH_0P1537MM_GAP_0P2032MM_JLC06161H_3313_L1_OVER_L2"
    elif net == "3V8_MODEM_BB":
        geometry = "MIN_EQUIVALENT_WIDTH_0.60_MM_WIDEN_IF_LONG"
    elif net == "3V8_MODEM_RF":
        geometry = "MIN_EQUIVALENT_WIDTH_2.70_MM_NO_NECKDOWN"
    elif net == "3V8_MODEM":
        geometry = "STAR_TRUNK_WIDTH_FROM_CURRENT_AND_DC_DROP_REVIEW"
    elif cls == "SWITCH_NODE":
        geometry = "SHORTEST_PRACTICAL_NO_PLANE_NO_TEST_STUB"
    elif cls == "POWER_RAIL":
        geometry = "WIDTH_FROM_LOAD_CURRENT_DC_DROP_AND_THERMAL_REVIEW"

    pair_group, pair_mate = USB_PAIRS.get(net, ("", ""))
    group = length_group(net)
    length_rule = "NOT_APPLICABLE"
    if pair_group:
        length_rule = "PAIR_SKEW_LIMIT_REQUIRES_SI_REVIEW"
    elif group:
        length_rule = "GROUP_SKEW_BUDGET_REQUIRES_TIMING_AND_SI_REVIEW"
    elif cls == "RF_50OHM":
        length_rule = "MINIMIZE_SERIES_PATH_NO_TEE"

    layer_rule = "SIGNAL_LAYER_WITH_CONTINUOUS_LOCAL_REFERENCE"
    via_rule = "MINIMIZE_TRANSITIONS"
    if cls == "RETURN_PLANE":
        layer_rule = "DEDICATED_DOMAIN_PLANE_GEOMETRY_REVIEW_B"
        via_rule = "STITCH_WITHIN_DOMAIN_NEVER_JOIN_DOMAINS_ON_PCB_MAIN"
    elif cls == "RF_50OHM":
        layer_rule = "SAME_OUTER_LAYER_CHAIN_OVER_UNINTERRUPTED_REFERENCE"
        via_rule = "ZERO_SIGNAL_VIA_TARGET_JUSTIFY_ANY_AND_ADD_RETURN_VIAS"
    elif cls == "USB_90OHM_DIFF":
        layer_rule = "PAIR_ON_ONE_LAYER_OVER_UNINTERRUPTED_REFERENCE"
        via_rule = "MATCHED_PAIR_TRANSITIONS_WITH_ADJACENT_RETURN_VIAS"
    elif cls == "SWITCH_NODE":
        layer_rule = "F_CU_LOCAL_KEEP_OUT_OF_RF_GNSS_AUDIO_AREAS"
        via_rule = "NO_VIA_TARGET"
    elif cls in {"EDGE_CLOCK", "EDGE_DATA"}:
        via_rule = "MINIMIZE_TRANSITIONS_RETURN_VIA_AT_EACH_LAYER_CHANGE"

    priority = "P0" if cls in {
        "RETURN_PLANE", "RF_50OHM", "USB_90OHM_DIFF", "MODEM_BURST_POWER", "SWITCH_NODE"
    } else "P1" if cls in {
        "POWER_RAIL", "EDGE_CLOCK", "EDGE_DATA", "I2C_OPEN_DRAIN", "UART_SIGNAL",
        "MIC_WAKE_SIGNAL", "MODEM_SIM_CONTROL", "ANALOG_SENSE_BIAS",
    } else "P2"
    return {
        "Net_Name": net,
        "Route_Class": cls,
        "Reference_Domain": reference_domain(net, cls),
        "Topology": topology,
        "Impedance_Target": impedance,
        "Geometry_Rule": geometry,
        "Pair_Group": pair_group,
        "Pair_Mate": pair_mate,
        "Length_Group": group,
        "Length_Rule": length_rule,
        "Layer_Rule": layer_rule,
        "Via_Rule": via_rule,
        "Priority": priority,
        "Source_Authority": source_authority(net, cls),
        "Status": STATUS,
    }


def render() -> str:
    nets = native_nets()
    assigned = [net for members in CLASS_NETS.values() for net in members]
    duplicates = sorted({net for net in assigned if assigned.count(net) > 1})
    if duplicates:
        raise RuntimeError(f"routing class overlap: {duplicates}")
    if set(assigned) != set(nets):
        raise RuntimeError(
            "routing class coverage drift: "
            f"missing={sorted(set(nets) - set(assigned))} "
            f"extra={sorted(set(assigned) - set(nets))}"
        )
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(row_for(net) for net in nets)
    return stream.getvalue()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=OUT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    output = args.output.resolve()
    expected = render()
    if args.check:
        if not output.is_file() or output.read_text(encoding="utf-8") != expected:
            print(f"PCB-MAIN routing authority drift: {output}", file=sys.stderr)
            return 1
        print("PCB-MAIN routing authority generator: PASS (186 nets)")
        return 0
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(expected, encoding="utf-8", newline="")
    print(f"PCB-MAIN routing authority written: {output}")
    print("nets=186 status=PRE_ROUTE_CONSTRAINT_CONTROLLED_ROUTING_NOT_COMPLETE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
