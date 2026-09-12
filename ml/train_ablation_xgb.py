from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ml import config


CORE = [
    "own_speed_kph",
    "rival_speed_kph",
    "speed_delta_kph",
    "gap_s",
    "gap_rate_s_per_s",
    "own_energy_mj",
    "energy_uncertainty_mj",
    "recovery_kw",
    "recovery_uncertainty_kw",
]


BRAKE = [
    "own_brake",
    "rival_brake",
]


THROTTLE = [
    "own_throttle",
    "rival_throttle",
    "throttle_delta",
]


TEMPORAL = [
    "own_accel_kph_s",
    "rival_accel_kph_s",
    "speed_delta_roll_mean",
    "speed_delta_roll_std",
]


POWERTRAIN = [
    "own_rpm",
    "rival_rpm",
    "rpm_delta",
    "own_gear",
    "rival_gear",
    "own_drs",
    "rival_drs",
]


FEATURE_SETS = {
    "core": CORE,
    "core_brake": CORE + BRAKE,
    "core_throttle": CORE + THROTTLE,
    "core_temporal": CORE + TEMPORAL,
    "core_powertrain": CORE + POWERTRAIN,
    "full": (
        CORE
        + BRAKE
        + THROTTLE
        + TEMPORAL
        + POWERTRAIN
    ),
}


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--variant",
        required=True,
        choices=FEATURE_SETS.keys(),
    )

    parser.add_argument(
        "--data",
        type=Path,
        required=True,
    )

    parser.add_argument(
        "--model",
        type=Path,
        required=True,
    )

    parser.add_argument(
        "--reports",
        type=Path,
        required=True,
    )

    args = parser.parse_args()

    selected = FEATURE_SETS[args.variant]

    config.FEATURES = selected

    print("=" * 70)
    print("GRIDGHOST FEATURE ABLATION")
    print("=" * 70)
    print(f"Variant       : {args.variant}")
    print(f"Feature count : {len(selected)}")

    for feature in selected:
        print(f"  - {feature}")

    print("=" * 70)

    # train_xgb has its own argparse parser.
    # Give it only the arguments it expects.
    sys.argv = [
        "train_xgb",
        "--data",
        str(args.data),
        "--model",
        str(args.model),
        "--reports",
        str(args.reports),
    ]

    from ml.train_xgb import main as train_main

    train_main()


if __name__ == "__main__":
    main()