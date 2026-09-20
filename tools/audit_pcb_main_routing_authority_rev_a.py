#!/usr/bin/env python3
"""Independently audit PCB-MAIN Rev.A routing-constraint coverage.

This control proves that every native net has an explicit reviewed routing
classification and that the authoritative board is the exact accepted bounded
RF-P0 successor to the OctoSPI/R8 subgate.  A PASS does not claim
completion of signal or power routing, Review B, CAM, or manufacturing release.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path, PurePosixPath
from typing import Any

from kiutils.board import Board

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from audit_pcb_main_native_schematic_rev_a import expected_components  # noqa: E402

DEFAULT_BOARD = ROOT / "hardware/kicad/native/PCB-MAIN/PCB-MAIN.kicad_pcb"
DEFAULT_AUTHORITY = ROOT / "hardware/PCB_MAIN_ROUTING_AUTHORITY_REV_A.csv"
DEFAULT_STATUS = ROOT / "hardware/PCB_MAIN_CAPTURE_STATUS_REV_A.json"
GROUND_CANDIDATE = (
    ROOT
    / "hardware/kicad/candidates/PCB-MAIN-GROUND-DOMAIN-001"
    / "PCB-MAIN_GROUND_DOMAIN_CANDIDATE_REV_A.kicad_pcb"
)
GROUND_APPLICATION = (
    ROOT / "hardware/reviews/PCB_MAIN_GROUND_DOMAIN_ROUTING_APPLICATION_REV_A.json"
)
SIGNAL_CANDIDATE = (
    ROOT
    / "hardware/kicad/candidates/PCB-MAIN-SIGNAL-HARD-NETS-001"
    / "PCB-MAIN_SIGNAL_HARD_NETS_CANDIDATE_REV_A.kicad_pcb"
)
SIGNAL_APPLICATION = (
    ROOT / "hardware/reviews/PCB_MAIN_SIGNAL_HARD_NETS_ROUTING_APPLICATION_REV_A.json"
)
OCTOSPI_CANDIDATE = (
    ROOT
    / "hardware/kicad/candidates/PCB-MAIN-OCTOSPI-R8-ECO-002"
    / "PCB-MAIN_OCTOSPI_R8_ECO_CANDIDATE_REV_A.kicad_pcb"
)
OCTOSPI_APPLICATION = (
    ROOT / "hardware/reviews/PCB_MAIN_OCTOSPI_R8_ECO_002_APPLICATION_REV_A.json"
)
RF_CANDIDATE = (
    ROOT
    / "hardware/kicad/candidates/PCB-MAIN-RF-P0-001"
    / "PCB-MAIN_RF_P0_CANDIDATE_REV_A.kicad_pcb"
)
RF_APPLICATION = ROOT / "hardware/reviews/PCB_MAIN_RF_P0_ROUTING_APPLICATION_REV_A.json"
RF_REMEDIATION_COMPOSED = (
    ROOT / "hardware/kicad/candidates/PCB-MAIN-RF-REMEDIATION-APPLICATION-001/"
    "PCB-MAIN_RF_REMEDIATION_COMPOSED_REV_A.kicad_pcb"
)
RF_RETURN_APPLICATION = (
    ROOT / "hardware/reviews/PCB_MAIN_RF_RETURN_001_APPLICATION_REV_A.json"
)
GNSS_APPLICATION = (
    ROOT / "hardware/reviews/PCB_MAIN_GNSS_RF_ECO_001_APPLICATION_REV_A.json"
)
USB_SOURCE_APPLICATION = (
    ROOT / "hardware/reviews/PCB_MAIN_USB_SOURCE_ROUTING_001_APPLICATION_REV_A.json"
)
USB_CELL_MODEM_APPLICATION = (
    ROOT / "hardware/reviews/PCB_MAIN_USB_CELL_MODEM_ROUTING_001_APPLICATION_REV_A.json"
)
USB_CELL_FIXTURE_APPLICATION = (
    ROOT / "hardware/reviews/PCB_MAIN_USB_CELL_FIXTURE_ROUTING_001_APPLICATION_REV_A.json"
)

STATE = (
    "PASS_CONSTRAINT_COVERAGE_ACCEPTED_RF_REMEDIATIONS_USB_MCU_SOURCE_"
    "CELL_MODEM_AND_CELL_FIXTURE_APPLIED"
)
ROW_STATUS = "PRE_ROUTE_CONSTRAINT_CONTROLLED_ROUTING_NOT_COMPLETE"
STACKUP_STATE = "OPEN_REQUIRED_BEFORE_NUMERIC_RF_USB_GEOMETRY"
GROUND_CANDIDATE_SHA256 = (
    "9c8abfabc18fa22b53c94b6b4d7946dbe1dfab797fbff9d00d7c3408aece1b9e"
)
SIGNAL_CANDIDATE_SHA256 = (
    "7dea2fdce607dbf7df2205e74b188d45e2def07c5329bacb4f9503ddcf7ae6f3"
)
OCTOSPI_CANDIDATE_SHA256 = (
    "04a0c7e37068d00fbe53b48fd19063b015b6b5c04e9aaafb3b01bbced0d7a99f"
)
RF_CANDIDATE_SHA256 = (
    "9557f74faa21105bdcdfb859cf5380f93e441aa8f863a7bad3bdb671a930c040"
)
RF_REMEDIATION_SHA256 = (
    "f8797a1055ead6c37dca4db08700a24f6f658327e60a0730ec0f766d7c78f4f9"
)
ACTIVE_BOARD_SHA256 = (
    "2dd9bdf218b7b595458d63dc1732ea6ba7f42a2092712b20b53e649823ef7273"
)
USB_SOURCE_BOARD_SHA256 = (
    "76f7a6ef35b3f168e8b32f1ff97e650404546e6b839ddd7fdde9a061ede3d7a5"
)
USB_CELL_MODEM_BOARD_SHA256 = (
    "4e93ca089047ffb84e0f2667897cb9a04d580e925f3c39ed37cec22e4820a5b5"
)

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

# This map is intentionally duplicated rather than imported from the generator:
# generator drift must be caught by a separately maintained expectation.
EXPECTED_CLASS_NETS = {
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

EXPECTED_CLASS_COUNTS = {
    name: len(nets) for name, nets in EXPECTED_CLASS_NETS.items()
}

EXPECTED_DOMAIN_COUNTS = {
    "CROSS_GND_DIGITAL_GND_MIC_REVIEW_B": 7,
    "CROSS_GND_DIGITAL_GND_MODEM_REVIEW_B": 11,
    "GND_DIGITAL": 109,
    "GND_MIC": 6,
    "GND_MODEM": 47,
    "RETURN_AT_LOAD_PER_GROUND_AUTHORITY": 2,
    "SELF": 3,
    "SHIELD_COUPLING_NETWORK_REVIEW_B": 1,
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

TOPOLOGY = {
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
}

LENGTH_GROUPS = [
    ("OCTOSPI_U1", ("NOR_CLK_U1", "NOR_IO0_U1", "NOR_IO1_U1", "NOR_IO2_U1", "NOR_IO3_U1", "NOR_NCS_U2")),
    ("OCTOSPI_U2", ("NOR_CLK_U2", "NOR_IO0_U2", "NOR_IO1_U2", "NOR_IO2_U2", "NOR_IO3_U2", "NOR_NCS_U2")),
    ("SDIO_U1", ("SD_CK_U1", "SD_CMD_U1", "SD_D0_U1", "SD_D1_U1", "SD_D2_U1", "SD_D3_U1")),
    ("SDIO_CARD", ("SD_CK_CARD", "SD_CMD_CARD", "SD_D0_CARD", "SD_D1_CARD", "SD_D2_CARD", "SD_D3_CARD")),
    ("LORA_SPI_U1", ("LORA_SCK_U1", "LORA_MISO_U1", "LORA_MOSI_U1", "LORA_NSS_U1")),
    ("LORA_SPI_U10", ("LORA_SCK_U10", "LORA_MISO_U10", "LORA_MOSI_U10", "LORA_NSS_U10")),
    ("PDM_DIGITAL", ("PDM_CLK", "PDM_DATA1", "PDM_DATA2", "PDM_DATA3", "PDM_DATA4")),
    ("PDM_MIC_SIDE", ("PDM_CLK_1V8_FANOUT", "PDM_DATA1_1V8", "PDM_DATA2_1V8", "PDM_DATA3_1V8", "PDM_DATA4_1V8")),
]


def require(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def relative(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path.resolve())


def expected_class_by_net() -> dict[str, str]:
    result: dict[str, str] = {}
    for route_class, nets in EXPECTED_CLASS_NETS.items():
        for net in nets:
            require(net not in result, f"independent route-class expectation overlaps at {net}")
            result[net] = route_class
    return result


def expected_domain(net: str, route_class: str) -> str:
    if route_class == "RETURN_PLANE":
        return "SELF"
    if route_class == "MODEM_BURST_POWER":
        return "GND_MODEM"
    if net in {"1V8_MIC", "3V3_DIGITAL"}:
        return "RETURN_AT_LOAD_PER_GROUND_AUTHORITY"
    if net in {
        "CELL_USB_VBUS", "CELL_USIM_VDD_1V8", "SIM1_VDD_CONN",
        "SIM2_VDD_CONN", "U8_VDD_EXT_1V8",
    }:
        return "GND_MODEM"
    if route_class == "POWER_RAIL":
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


def expected_geometry(net: str, route_class: str) -> str:
    if route_class == "RETURN_PLANE":
        return "PLANE_GEOMETRY_AND_VOID_REVIEW_B"
    if route_class == "RF_50OHM":
        return "NO_NUMERIC_WIDTH_UNTIL_FACTORY_STACKUP"
    if route_class == "USB_90OHM_DIFF":
        return "NO_NUMERIC_WIDTH_OR_GAP_UNTIL_FACTORY_STACKUP"
    if net == "3V8_MODEM_BB":
        return "MIN_EQUIVALENT_WIDTH_0.60_MM_WIDEN_IF_LONG"
    if net == "3V8_MODEM_RF":
        return "MIN_EQUIVALENT_WIDTH_2.70_MM_NO_NECKDOWN"
    if net == "3V8_MODEM":
        return "STAR_TRUNK_WIDTH_FROM_CURRENT_AND_DC_DROP_REVIEW"
    if route_class == "SWITCH_NODE":
        return "SHORTEST_PRACTICAL_NO_PLANE_NO_TEST_STUB"
    if route_class == "POWER_RAIL":
        return "WIDTH_FROM_LOAD_CURRENT_DC_DROP_AND_THERMAL_REVIEW"
    return "FABRICATOR_MINIMUMS_AND_REVIEW_B"


def expected_length_group(net: str) -> str:
    if net in USB_PAIRS:
        return USB_PAIRS[net][0]
    return ";".join(name for name, members in LENGTH_GROUPS if net in members)


def expected_source_authority(net: str, route_class: str) -> str:
    sources = ["hardware/kicad/PCB_RULES.md"]
    if route_class == "RETURN_PLANE":
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
            or route_class == "FIXTURE_DEBUG"):
        sources.append("hardware/PCB_MAIN_CONNECTOR_FIXTURE_AUTHORITY_REV_A.md")
    if len(sources) == 1:
        sources.append("hardware/PCB_MAIN_MCU_PIN_AUTHORITY_REV_A.md")
    if route_class in {
        "RF_50OHM", "USB_90OHM_DIFF", "MODEM_BURST_POWER", "EDGE_CLOCK", "EDGE_DATA",
    }:
        sources.append("hardware/PCB_MAIN_PASSIVE_SUPPORT_AUTHORITY_REV_A.md")
    return ";".join(dict.fromkeys(sources))


def validate_source_paths(row: dict[str, str]) -> None:
    sources = row["Source_Authority"].split(";")
    require(len(sources) >= 2 and len(sources) == len(set(sources)),
            f"{row['Net_Name']}: source authority list is incomplete or duplicated")
    for source in sources:
        pure = PurePosixPath(source)
        require(not pure.is_absolute() and ".." not in pure.parts,
                f"{row['Net_Name']}: source path escapes repository: {source}")
        path = ROOT.joinpath(*pure.parts)
        require(path.is_file(), f"{row['Net_Name']}: source authority is missing: {source}")


def validate_row(row: dict[str, str], route_class: str) -> None:
    net = row["Net_Name"]
    require(row["Route_Class"] == route_class,
            f"{net}: route class {row['Route_Class']} != {route_class}")
    require(row["Reference_Domain"] == expected_domain(net, route_class),
            f"{net}: reference-domain rule drift")
    require(row["Topology"] == TOPOLOGY[route_class], f"{net}: topology rule drift")

    impedance = (
        "50_OHM_SINGLE_ENDED_FACTORY_STACKUP_PENDING"
        if route_class == "RF_50OHM"
        else "90_OHM_DIFFERENTIAL_FACTORY_STACKUP_PENDING"
        if route_class == "USB_90OHM_DIFF"
        else "NOT_CONTROLLED_IMPEDANCE"
    )
    require(row["Impedance_Target"] == impedance, f"{net}: impedance target drift")
    require(row["Geometry_Rule"] == expected_geometry(net, route_class),
            f"{net}: geometry rule drift")

    pair_group, pair_mate = USB_PAIRS.get(net, ("", ""))
    require((row["Pair_Group"], row["Pair_Mate"]) == (pair_group, pair_mate),
            f"{net}: differential-pair binding drift")
    length_group = expected_length_group(net)
    require(row["Length_Group"] == length_group, f"{net}: length-group rule drift")
    length_rule = (
        "PAIR_SKEW_LIMIT_REQUIRES_FINAL_STACKUP_AND_SI_REVIEW"
        if pair_group
        else "GROUP_SKEW_BUDGET_REQUIRES_TIMING_AND_SI_REVIEW"
        if length_group
        else "MINIMIZE_SERIES_PATH_NO_TEE"
        if route_class == "RF_50OHM"
        else "NOT_APPLICABLE"
    )
    require(row["Length_Rule"] == length_rule, f"{net}: length rule drift")

    layer_rule = "SIGNAL_LAYER_WITH_CONTINUOUS_LOCAL_REFERENCE"
    via_rule = "MINIMIZE_TRANSITIONS"
    if route_class == "RETURN_PLANE":
        layer_rule = "DEDICATED_DOMAIN_PLANE_GEOMETRY_REVIEW_B"
        via_rule = "STITCH_WITHIN_DOMAIN_NEVER_JOIN_DOMAINS_ON_PCB_MAIN"
    elif route_class == "RF_50OHM":
        layer_rule = "SAME_OUTER_LAYER_CHAIN_OVER_UNINTERRUPTED_REFERENCE"
        via_rule = "ZERO_SIGNAL_VIA_TARGET_JUSTIFY_ANY_AND_ADD_RETURN_VIAS"
    elif route_class == "USB_90OHM_DIFF":
        layer_rule = "PAIR_ON_ONE_LAYER_OVER_UNINTERRUPTED_REFERENCE"
        via_rule = "MATCHED_PAIR_TRANSITIONS_WITH_ADJACENT_RETURN_VIAS"
    elif route_class == "SWITCH_NODE":
        layer_rule = "F_CU_LOCAL_KEEP_OUT_OF_RF_GNSS_AUDIO_AREAS"
        via_rule = "NO_VIA_TARGET"
    elif route_class in {"EDGE_CLOCK", "EDGE_DATA"}:
        via_rule = "MINIMIZE_TRANSITIONS_RETURN_VIA_AT_EACH_LAYER_CHANGE"
    require(row["Layer_Rule"] == layer_rule, f"{net}: layer rule drift")
    require(row["Via_Rule"] == via_rule, f"{net}: via rule drift")

    priority = (
        "P0" if route_class in {
            "RETURN_PLANE", "RF_50OHM", "USB_90OHM_DIFF",
            "MODEM_BURST_POWER", "SWITCH_NODE",
        }
        else "P1" if route_class in {
            "POWER_RAIL", "EDGE_CLOCK", "EDGE_DATA", "I2C_OPEN_DRAIN",
            "UART_SIGNAL", "MIC_WAKE_SIGNAL", "MODEM_SIM_CONTROL",
            "ANALOG_SENSE_BIAS",
        }
        else "P2"
    )
    require(row["Priority"] == priority, f"{net}: routing priority drift")
    require(row["Status"] == ROW_STATUS, f"{net}: release-boundary status drift")
    require(row["Source_Authority"] == expected_source_authority(net, route_class),
            f"{net}: source-authority binding drift")
    validate_source_paths(row)


def expected_status_control(
    board_sha256: str,
    authority_sha256: str,
) -> dict[str, Any]:
    return {
        "state": STATE,
        "board_sha256": board_sha256,
        "authority_sha256": authority_sha256,
        "net_count": 186,
        "class_counts": EXPECTED_CLASS_COUNTS,
        "reference_domain_counts": EXPECTED_DOMAIN_COUNTS,
        "rf_50ohm_net_count": 7,
        "usb_90ohm_pair_count": 4,
        "cross_domain_review_net_count": 18,
        "trace_items": 1023,
        "copper_zones": 8,
        "ground_domain_subgate": "APPLIED_EXACT_ACCEPTED_CANDIDATE",
        "signal_hard_nets_subgate": "APPLIED_EXACT_ACCEPTED_CANDIDATE",
        "octospi_r8_eco_002_subgate": "APPLIED_EXACT_ACCEPTED_CANDIDATE",
        "rf_p0_subgate": "APPLIED_EXACT_ACCEPTED_CANDIDATE",
        "cellular_l2_return_subgate": "APPLIED_EXACT_ACCEPTED_ZONE",
        "gnss_rf_placement_routeability_subgate": "APPLIED_EXACT_ACCEPTED_DELTA",
        "combined_rf_remediation_gate": "PASS_COMMIT_BOUND_KICAD9_DRC_AND_FILLED_L2_REFERENCES",
        "usb_source_termination_placement_subgate":
        "APPLIED_EXACT_ACCEPTED_R91_R92_DELTA_COMMIT_BOUND_GATE_PASS",
        "usb_mcu_source_routing_subgate":
        "APPLIED_EXACT_ACCEPTED_CANDIDATE_COMMIT_BOUND_GATE_PASS",
        "usb_cell_modem_routing_subgate":
        "APPLIED_EXACT_ACCEPTED_CANDIDATE_COMMIT_BOUND_GATE_PASS",
        "usb_cell_fixture_routing_subgate":
        "APPLIED_EXACT_ACCEPTED_CANDIDATE_COMMIT_BOUND_GATE_PENDING",
        "factory_stackup": STACKUP_STATE,
        "routing_complete": False,
        "manufacturing_release": False,
    }


def audit(board_path: Path, authority_path: Path, status_path: Path | None) -> dict[str, Any]:
    board_path = board_path.resolve()
    authority_path = authority_path.resolve()
    require(board_path.is_file(), f"native board is missing: {board_path}")
    require(authority_path.is_file(), f"routing authority is missing: {authority_path}")
    require(GROUND_CANDIDATE.is_file(),
            f"accepted ground-domain candidate is missing: {GROUND_CANDIDATE}")
    require(GROUND_APPLICATION.is_file(),
            f"ground-domain application record is missing: {GROUND_APPLICATION}")
    require(SIGNAL_CANDIDATE.is_file(),
            f"accepted signal candidate is missing: {SIGNAL_CANDIDATE}")
    require(SIGNAL_APPLICATION.is_file(),
            f"signal application record is missing: {SIGNAL_APPLICATION}")
    require(OCTOSPI_CANDIDATE.is_file(),
            f"accepted OctoSPI candidate is missing: {OCTOSPI_CANDIDATE}")
    require(OCTOSPI_APPLICATION.is_file(),
            f"OctoSPI application record is missing: {OCTOSPI_APPLICATION}")
    require(RF_CANDIDATE.is_file(),
            f"accepted RF candidate is missing: {RF_CANDIDATE}")
    require(RF_APPLICATION.is_file(),
            f"RF application record is missing: {RF_APPLICATION}")

    with authority_path.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        require(reader.fieldnames == FIELDS,
                f"routing authority fields differ: {reader.fieldnames}")
        rows = list(reader)
    require(len(rows) == 186, f"expected 186 routing rows, got {len(rows)}")
    names = [row["Net_Name"] for row in rows]
    require(all(names) and len(names) == len(set(names)),
            "routing authority contains blank or duplicate net names")
    require(names == sorted(names), "routing authority rows are not sorted by native net name")

    board = Board.from_file(str(board_path), encoding="utf-8")
    board_nets = {
        str(net.name) for net in board.nets
        if int(net.number) != 0 and str(net.name)
    }
    schematic_nets = {
        pin["native"]
        for component in expected_components().values()
        if component["on_board"]
        for pin in component["pins"].values()
        if pin["native"] != "NC"
    }
    require(len(board_nets) == 186, f"native board net count is {len(board_nets)}, expected 186")
    require(board_nets == schematic_nets,
            "native board net set differs from reviewed schematic authority")

    expected_by_net = expected_class_by_net()
    require(set(expected_by_net) == board_nets,
            "independent route-class expectation differs from native board net set")
    require(set(names) == board_nets,
            f"routing authority net coverage drift: missing={sorted(board_nets-set(names))} "
            f"extra={sorted(set(names)-board_nets)}")

    by_net = {row["Net_Name"]: row for row in rows}
    for net in names:
        validate_row(by_net[net], expected_by_net[net])

    class_counts = dict(sorted(Counter(row["Route_Class"] for row in rows).items()))
    expected_class_counts = dict(sorted(EXPECTED_CLASS_COUNTS.items()))
    require(class_counts == expected_class_counts,
            f"route-class inventory drift: {class_counts}")
    domain_counts = dict(sorted(Counter(row["Reference_Domain"] for row in rows).items()))
    require(domain_counts == EXPECTED_DOMAIN_COUNTS,
            f"reference-domain inventory drift: {domain_counts}")

    for net, (pair_group, mate) in USB_PAIRS.items():
        require(USB_PAIRS[mate] == (pair_group, net),
                f"{net}: independent USB pair map is not symmetric")
        require(by_net[net]["Route_Class"] == "USB_90OHM_DIFF",
                f"{net}: USB pair is not in USB_90OHM_DIFF")
    usb_groups = sorted({pair_group for pair_group, _ in USB_PAIRS.values()})
    require(len(usb_groups) == 4, "expected four isolated USB differential-pair groups")

    rf_nets = sorted(EXPECTED_CLASS_NETS["RF_50OHM"])
    require(all(by_net[net]["Via_Rule"].startswith("ZERO_SIGNAL_VIA_TARGET")
                for net in rf_nets), "RF zero-signal-via target drift")
    require({by_net[net]["Reference_Domain"] for net in {"CELL_RF", "CELL_RF_ANT"}}
            == {"GND_MODEM"}, "cellular RF reference domain drift")
    require({by_net[net]["Reference_Domain"] for net in set(rf_nets)-{"CELL_RF", "CELL_RF_ANT"}}
            == {"GND_DIGITAL"}, "GNSS/LoRa RF reference domain drift")

    require(set(CROSS_MODEM_DIGITAL) == {
        net for net, row in by_net.items()
        if row["Reference_Domain"] == "CROSS_GND_DIGITAL_GND_MODEM_REVIEW_B"
    }, "modem/digital cross-domain review set drift")
    require(set(CROSS_MIC_DIGITAL) == {
        net for net, row in by_net.items()
        if row["Reference_Domain"] == "CROSS_GND_DIGITAL_GND_MIC_REVIEW_B"
    }, "microphone/digital cross-domain review set drift")

    trace_items = len(board.traceItems)
    copper_zones = len(board.zones)
    require(trace_items == 1023 and copper_zones == 8,
            "authoritative board does not contain the accepted RF remediations")
    board_digest = sha256(board_path)
    require(board_digest == ACTIVE_BOARD_SHA256,
            "authoritative board SHA-256 differs from the accepted USB placement successor")
    require(sha256(GROUND_CANDIDATE) == GROUND_CANDIDATE_SHA256,
            "accepted ground-domain candidate hash drift")
    require(sha256(SIGNAL_CANDIDATE) == SIGNAL_CANDIDATE_SHA256 and
            sha256(OCTOSPI_CANDIDATE) == OCTOSPI_CANDIDATE_SHA256 and
            sha256(RF_CANDIDATE) == RF_CANDIDATE_SHA256 and
            sha256(RF_REMEDIATION_COMPOSED) == RF_REMEDIATION_SHA256,
            "accepted routing predecessor identity drift")
    application = json.loads(GROUND_APPLICATION.read_text(encoding="utf-8"))
    require(application.get("decision") == "ACCEPT_GROUND_DOMAIN_ROUTING_SUBGATE"
            and application.get("status") ==
            "APPLIED_ACCEPTED_GROUND_DOMAIN_SUBGATE_ROUTING_ENGINEERING_CONTINUES"
            and application.get("reviewed_candidate_board_sha256") ==
            GROUND_CANDIDATE_SHA256,
            "ground-domain application decision or candidate binding differs")
    require(application.get("applied") == {
                "board": "hardware/kicad/native/PCB-MAIN/PCB-MAIN.kicad_pcb",
                "board_sha256": GROUND_CANDIDATE_SHA256,
                "exact_candidate_byte_identity": True,
                "track_segments": 319,
                "track_length_mm": 226.515879672367,
                "vias": 254,
                "copper_zones": 3,
                "mounting_rule_areas": 4,
                "committed_zone_fill_state":
                "UNFILLED_CI_AND_REVIEW_TOOLS_MUST_REFILL_BEFORE_DRC",
                "native_connectivity_baseline_to_candidate": [718, 464],
                "new_comparative_drc_error_counts": {},
            }, "ground-domain application geometry or release boundary differs")
    signal_application = json.loads(SIGNAL_APPLICATION.read_text(encoding="utf-8"))
    require(signal_application.get("decision") ==
            "ACCEPT_SIGNAL_HARD_NETS_ROUTING_SUBGATE" and
            signal_application.get("status") ==
            "APPLIED_ACCEPTED_SIGNAL_HARD_NETS_SUBGATE_ROUTING_ENGINEERING_CONTINUES" and
            signal_application.get("reviewed_candidate_board_sha256") ==
            SIGNAL_CANDIDATE_SHA256 and
            signal_application.get("applied", {}).get("board_sha256") ==
            SIGNAL_CANDIDATE_SHA256 and
            signal_application.get("applied", {}).get("exact_candidate_byte_identity") is True and
            signal_application.get("review_b_complete") is False and
            signal_application.get("cam_or_manufacturing_release") is False,
            "signal application decision, geometry, or release boundary differs")
    octospi_application = json.loads(OCTOSPI_APPLICATION.read_text(encoding="utf-8"))
    require(octospi_application.get("decision") ==
            "ACCEPT_LIMITED_OCTOSPI_R8_PLACEMENT_ECO_AND_ROUTING_SUBGATE" and
            octospi_application.get("status") ==
            "APPLIED_ACCEPTED_OCTOSPI_R8_ECO_002_SUBGATE_ROUTING_ENGINEERING_CONTINUES" and
            octospi_application.get("historical_baseline", {}).get("board_sha256") ==
            SIGNAL_CANDIDATE_SHA256 and
            octospi_application.get("reviewed_candidate_board_sha256") ==
            OCTOSPI_CANDIDATE_SHA256 and
            octospi_application.get("applied", {}).get("board_sha256") ==
            OCTOSPI_CANDIDATE_SHA256 and
            octospi_application.get("applied", {}).get("exact_candidate_byte_identity") is True and
            octospi_application.get("routing_complete") is False and
            octospi_application.get("review_b_complete") is False and
            octospi_application.get("cam_or_manufacturing_release") is False,
            "OctoSPI application decision, geometry, or release boundary differs")
    rf_application = json.loads(RF_APPLICATION.read_text(encoding="utf-8"))
    require(rf_application.get("decision") == "ACCEPT_RF_P0_ROUTING_SUBGATE" and
            rf_application.get("status") ==
            "APPLIED_ACCEPTED_RF_P0_ROUTING_SUBGATE_REMAINING_ROUTING_AND_REVIEWS_OPEN" and
            rf_application.get("historical_baseline", {}).get("board_sha256") ==
            OCTOSPI_CANDIDATE_SHA256 and
            rf_application.get("reviewed_candidate_board_sha256") ==
            RF_CANDIDATE_SHA256 and
            rf_application.get("applied", {}).get("board_sha256") ==
            RF_CANDIDATE_SHA256 and
            rf_application.get("applied", {}).get("exact_candidate_byte_identity") is True and
            rf_application.get("routing_complete") is False and
            rf_application.get("review_b_complete") is False and
            rf_application.get("cam_or_manufacturing_release") is False,
            "RF application decision, geometry, or release boundary differs")
    rf_return_application = json.loads(
        RF_RETURN_APPLICATION.read_text(encoding="utf-8")
    )
    gnss_application = json.loads(GNSS_APPLICATION.read_text(encoding="utf-8"))
    usb_source_application = json.loads(
        USB_SOURCE_APPLICATION.read_text(encoding="utf-8")
    )
    usb_cell_modem_application = json.loads(
        USB_CELL_MODEM_APPLICATION.read_text(encoding="utf-8")
    )
    usb_cell_fixture_application = json.loads(
        USB_CELL_FIXTURE_APPLICATION.read_text(encoding="utf-8")
    )
    require(
        rf_return_application.get("decision") ==
        "ACCEPT_CELLULAR_L2_RETURN_PLANE_SUBGATE"
        and rf_return_application.get("applied_intermediate", {}).get(
            "exact_candidate_byte_identity"
        ) is True
        and gnss_application.get("decision") ==
        "ACCEPT_GNSS_RF_PLACEMENT_ROUTEABILITY_SUBGATE"
        and gnss_application.get("applied", {}).get("board_sha256") ==
        RF_REMEDIATION_SHA256
        and gnss_application.get("applied", {}).get(
            "exact_composed_board_byte_identity"
        ) is True
        and gnss_application.get("routing_complete") is False
        and gnss_application.get("review_b_complete") is False
        and gnss_application.get("cam_or_manufacturing_release") is False,
        "RF remediation application decision, composition, or boundary differs",
    )
    require(
        usb_source_application.get("decision") ==
        "ACCEPT_USB_MCU_SOURCE_ROUTING_SUBGATE"
        and usb_source_application.get("applied", {}).get("board_sha256") ==
        USB_SOURCE_BOARD_SHA256
        and usb_source_application.get("applied", {}).get(
            "exact_candidate_byte_identity"
        ) is True
        and usb_source_application.get("review_b_complete") is False
        and usb_source_application.get("manufacturing_release") is False,
        "USB MCU source-routing application boundary differs",
    )
    require(
        usb_cell_modem_application.get("decision") ==
        "ACCEPT_USB_CELL_MODEM_ROUTING_SUBGATE"
        and usb_cell_modem_application.get("predecessor", {}).get(
            "board_sha256"
        ) == USB_SOURCE_BOARD_SHA256
        and usb_cell_modem_application.get("applied", {}).get("board_sha256") ==
        USB_CELL_MODEM_BOARD_SHA256
        and usb_cell_modem_application.get("applied", {}).get(
            "exact_candidate_byte_identity"
        ) is True
        and usb_cell_modem_application.get("review_b_complete") is False
        and usb_cell_modem_application.get("manufacturing_release") is False,
        "USB cellular-modem routing application boundary differs",
    )
    require(
        usb_cell_fixture_application.get("decision") ==
        "ACCEPT_USB_CELL_FIXTURE_ROUTING_SUBGATE"
        and usb_cell_fixture_application.get("predecessor", {}).get(
            "board_sha256"
        ) == usb_cell_modem_application.get("applied", {}).get("board_sha256")
        and usb_cell_fixture_application.get("applied", {}).get("board_sha256") ==
        ACTIVE_BOARD_SHA256
        and usb_cell_fixture_application.get("applied", {}).get(
            "exact_candidate_byte_identity"
        ) is True
        and usb_cell_fixture_application.get("review_b_complete") is False
        and usb_cell_fixture_application.get("manufacturing_release") is False,
        "USB cellular-fixture routing application boundary differs",
    )

    authority_digest = sha256(authority_path)
    control = expected_status_control(board_digest, authority_digest)
    if status_path is not None:
        status_path = status_path.resolve()
        require(status_path.is_file(), f"capture status is missing: {status_path}")
        status = json.loads(status_path.read_text(encoding="utf-8"))
        evidence = status.get("review_b", {}).get("evidence", {})
        expected_traceability = {
            "routing_authority": "hardware/PCB_MAIN_ROUTING_AUTHORITY_REV_A.csv",
            "routing_authority_record": "hardware/PCB_MAIN_ROUTING_AUTHORITY_REV_A.md",
            "routing_authority_generator": "tools/generate_pcb_main_routing_authority_rev_a.py",
            "routing_authority_audit": "tools/audit_pcb_main_routing_authority_rev_a.py",
            "routing_constraint_status": (
                "PASS_ALL_186_NETS_CLASSIFIED_RF_REMEDIATION_REPEAT_REVIEW_PASS_"
                "USB_MCU_SOURCE_CELL_MODEM_AND_CELL_FIXTURE_APPLIED_FACTORY_"
                "STACKUP_AND_MAIN_CONNECTOR_ROUTING_PENDING"
            ),
        }
        require(all(evidence.get(key) == value
                    for key, value in expected_traceability.items()),
                "PCB_MAIN_CAPTURE_STATUS routing authority traceability differs")
        actual_control = evidence.get("routing_constraint_control")
        require(actual_control == control,
                "PCB_MAIN_CAPTURE_STATUS routing_constraint_control differs from audit")

    return {
        "schema": "dioneya-pcb-main-routing-authority-audit-v1",
        "state": STATE,
        "board": {
            "path": relative(board_path),
            "sha256": board_digest,
            "net_count": len(board_nets),
            "trace_items": trace_items,
            "copper_zones": copper_zones,
        },
        "authority": {
            "path": relative(authority_path),
            "sha256": authority_digest,
            "row_count": len(rows),
        },
        "class_counts": class_counts,
        "reference_domain_counts": domain_counts,
        "rf_50ohm_nets": rf_nets,
        "usb_pair_groups": {
            group: sorted(net for net, binding in USB_PAIRS.items() if binding[0] == group)
            for group in usb_groups
        },
        "cross_domain_review_nets": {
            "modem_digital": sorted(CROSS_MODEM_DIGITAL),
            "microphone_digital": sorted(CROSS_MIC_DIGITAL),
        },
        "factory_stackup_status": STACKUP_STATE,
        "ground_domain_subgate": "APPLIED_EXACT_ACCEPTED_CANDIDATE",
        "signal_hard_nets_subgate": "APPLIED_EXACT_ACCEPTED_CANDIDATE",
        "octospi_r8_eco_002_subgate": "APPLIED_EXACT_ACCEPTED_CANDIDATE",
        "rf_p0_subgate": "APPLIED_EXACT_ACCEPTED_CANDIDATE",
        "cellular_l2_return_subgate": "APPLIED_EXACT_ACCEPTED_ZONE",
        "gnss_rf_placement_routeability_subgate": "APPLIED_EXACT_ACCEPTED_DELTA",
        "combined_rf_remediation_gate": "PASS_COMMIT_BOUND_KICAD9_DRC_AND_FILLED_L2_REFERENCES",
        "usb_cell_fixture_routing_subgate":
        "APPLIED_EXACT_ACCEPTED_CANDIDATE_COMMIT_BOUND_GATE_PENDING",
        "routing_complete": False,
        "manufacturing_release": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--board", type=Path, default=DEFAULT_BOARD)
    parser.add_argument("--authority", type=Path, default=DEFAULT_AUTHORITY)
    parser.add_argument("--status", type=Path, default=DEFAULT_STATUS)
    parser.add_argument("--no-status-check", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    report = audit(
        args.board,
        args.authority,
        None if args.no_status_check else args.status,
    )
    rendered = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        output = args.output.resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8")
    print("PCB-MAIN routing authority audit: PASS")
    print(
        "nets=186 classes=15 rf_50ohm=7 usb_pairs=4 "
        "trace_items=1023 copper_zones=8 ground_subgate=applied "
        "signal_hard_nets_subgate=applied octospi_r8_eco_002_subgate=applied "
        "rf_p0_subgate=applied rf_remediations=applied "
        "routing_complete=false"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
