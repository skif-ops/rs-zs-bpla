from __future__ import annotations

import argparse
import csv
import math
import sys
from pathlib import Path


DEFAULT_FREQUENCIES_HZ = (100.0, 160.0, 250.0, 400.0, 630.0, 1000.0, 2000.0, 4000.0)


def atmospheric_absorption_db_per_m(
    frequency_hz: float,
    temperature_c: float,
    relative_humidity_percent: float,
    pressure_kpa: float,
) -> float:
    temperature_k = temperature_c + 273.15
    reference_temperature_k = 293.15
    triple_point_k = 273.16
    pressure_ratio = pressure_kpa / 101.325
    saturation_pressure_ratio = 10 ** (
        -6.8346 * (triple_point_k / temperature_k) ** 1.261 + 4.6151
    )
    molar_humidity_percent = (
        relative_humidity_percent * saturation_pressure_ratio / pressure_ratio
    )
    oxygen_relaxation_hz = pressure_ratio * (
        24.0
        + 4.04e4
        * molar_humidity_percent
        * (0.02 + molar_humidity_percent)
        / (0.391 + molar_humidity_percent)
    )
    nitrogen_relaxation_hz = (
        pressure_ratio
        * (temperature_k / reference_temperature_k) ** -0.5
        * (
            9.0
            + 280.0
            * molar_humidity_percent
            * math.exp(
                -4.17
                * ((temperature_k / reference_temperature_k) ** (-1.0 / 3.0) - 1.0)
            )
        )
    )
    frequency_squared = frequency_hz**2
    classical_loss = (
        1.84e-11
        * pressure_ratio**-1
        * (temperature_k / reference_temperature_k) ** 0.5
    )
    molecular_loss = (temperature_k / reference_temperature_k) ** -2.5 * (
        0.01275
        * math.exp(-2239.1 / temperature_k)
        / (oxygen_relaxation_hz + frequency_squared / oxygen_relaxation_hz)
        + 0.1068
        * math.exp(-3352.0 / temperature_k)
        / (nitrogen_relaxation_hz + frequency_squared / nitrogen_relaxation_hz)
    )
    return 8.686 * frequency_squared * (classical_loss + molecular_loss)


def propagation_loss_db(
    frequency_hz: float,
    distance_m: float,
    reference_distance_m: float,
    temperature_c: float,
    relative_humidity_percent: float,
    pressure_kpa: float,
) -> tuple[float, float, float]:
    spreading_db = 20.0 * math.log10(distance_m / reference_distance_m)
    absorption_db = atmospheric_absorption_db_per_m(
        frequency_hz,
        temperature_c,
        relative_humidity_percent,
        pressure_kpa,
    ) * (distance_m - reference_distance_m)
    return spreading_db, absorption_db, spreading_db + absorption_db


def parse_frequencies(value: str) -> tuple[float, ...]:
    frequencies = tuple(float(item.strip()) for item in value.split(",") if item.strip())
    if not frequencies or any(frequency <= 0 for frequency in frequencies):
        raise argparse.ArgumentTypeError("frequencies must be positive comma-separated values")
    return frequencies


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Free-field acoustic range budget with atmospheric absorption."
    )
    parser.add_argument("--distance-m", type=float, default=2000.0)
    parser.add_argument("--reference-distance-m", type=float, default=1.0)
    parser.add_argument("--source-level-db-spl", type=float, default=70.0)
    parser.add_argument("--temperature-c", type=float, default=15.0)
    parser.add_argument("--relative-humidity-percent", type=float, default=70.0)
    parser.add_argument("--pressure-kpa", type=float, default=101.325)
    parser.add_argument(
        "--frequencies-hz",
        type=parse_frequencies,
        default=DEFAULT_FREQUENCIES_HZ,
        help="Comma-separated frequencies, default: 100,160,250,400,630,1000,2000,4000",
    )
    parser.add_argument("--csv", type=Path, help="Optional CSV output path")
    return parser


def validate_args(args: argparse.Namespace) -> None:
    if args.distance_m <= args.reference_distance_m or args.reference_distance_m <= 0:
        raise ValueError("distance must exceed a positive reference distance")
    if not 0 <= args.relative_humidity_percent <= 100:
        raise ValueError("relative humidity must be between 0 and 100 percent")
    if args.pressure_kpa <= 0:
        raise ValueError("pressure must be positive")


def main() -> int:
    args = build_parser().parse_args()
    try:
        validate_args(args)
    except ValueError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    rows: list[dict[str, str]] = []
    for frequency_hz in args.frequencies_hz:
        spreading_db, absorption_db, total_loss_db = propagation_loss_db(
            frequency_hz,
            args.distance_m,
            args.reference_distance_m,
            args.temperature_c,
            args.relative_humidity_percent,
            args.pressure_kpa,
        )
        rows.append(
            {
                "frequency_hz": f"{frequency_hz:g}",
                "geometric_spreading_db": f"{spreading_db:.2f}",
                "atmospheric_absorption_db": f"{absorption_db:.2f}",
                "total_propagation_loss_db": f"{total_loss_db:.2f}",
                "estimated_received_level_db_spl": f"{args.source_level_db_spl - total_loss_db:.2f}",
            }
        )

    fieldnames = list(rows[0])
    writer = csv.DictWriter(sys.stdout, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)

    if args.csv:
        args.csv.parent.mkdir(parents=True, exist_ok=True)
        with args.csv.open("w", newline="", encoding="utf-8-sig") as output:
            file_writer = csv.DictWriter(output, fieldnames=fieldnames)
            file_writer.writeheader()
            file_writer.writerows(rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
