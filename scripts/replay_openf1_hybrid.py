from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from app.hybrid import hybrid_plan
from app.openf1 import normalize
from app.planner import PlanRequest
from app.schemas import Belief


def main() -> None:

    parser = argparse.ArgumentParser(
        description=(
            "Replay historical OpenF1 observations "
            "through the GRIDGHOST hybrid ML + "
            "deterministic shield pipeline."
        )
    )

    parser.add_argument(
        "--input",
        type=Path,
        required=True,
        help=(
            "Raw OpenF1 JSON containing car_data, "
            "position and intervals."
        ),
    )

    parser.add_argument(
        "--energy-mj",
        type=float,
        default=2.4,
        help=(
            "Simulated starting energy snapshot. "
            "OpenF1 does not provide GRIDGHOST "
            "battery energy."
        ),
    )

    parser.add_argument(
        "--assume-green",
        action="store_true",
        help=(
            "Treat track status as GREEN for this "
            "historical demo replay."
        ),
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help=(
            "Maximum replay frames. "
            "0 means all available states."
        ),
    )

    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(
            "reports/openf1_hybrid_replay"
        ),
    )

    args = parser.parse_args()

    # ============================================================
    # LOAD INPUT
    # ============================================================

    if not args.input.exists():

        raise FileNotFoundError(
            f"Input file not found: {args.input}"
        )

    payload = json.loads(
        args.input.read_text(
            encoding="utf-8"
        )
    )

    required_metadata = [
        "own_driver_number",
        "rival_driver_number",
    ]

    missing_metadata = [
        item
        for item in required_metadata
        if item not in payload
    ]

    if missing_metadata:

        raise ValueError(
            "Input file is missing metadata: "
            f"{missing_metadata}"
        )

    own_driver = int(
        payload[
            "own_driver_number"
        ]
    )

    rival_driver = int(
        payload[
            "rival_driver_number"
        ]
    )

    # ============================================================
    # VERIFY REQUIRED RAW STREAMS
    # ============================================================

    print()
    print("=" * 76)
    print("GRIDGHOST OFFLINE OPENF1 HYBRID REPLAY")
    print("=" * 76)

    print(
        f"Input          : {args.input}"
    )

    print(
        f"Own driver     : {own_driver}"
    )

    print(
        f"Rival driver   : {rival_driver}"
    )

    print(
        f"Simulated energy: "
        f"{args.energy_mj:.3f} MJ"
    )

    print(
        f"Assume GREEN   : "
        f"{args.assume_green}"
    )

    print()

    stream_counts = {}

    for stream in (
        "car_data",
        "position",
        "intervals",
    ):

        rows = payload.get(
            stream,
            []
        )

        stream_counts[
            stream
        ] = len(rows)

        print(
            f"{stream:12s}: "
            f"{len(rows)} rows"
        )

    # ------------------------------------------------------------
    # We deliberately refuse to bypass position verification.
    # ------------------------------------------------------------

    if not payload.get(
        "position"
    ):

        print()
        print("=" * 76)
        print("REPLAY CANNOT START YET")
        print("=" * 76)

        print()
        print(
            "This raw capture has no OpenF1 position records."
        )

        print()
        print(
            "GRIDGHOST will not assume that an interval "
            "belongs to the selected rival without proving "
            "the two drivers were adjacent."
        )

        print()
        print(
            "The replay script itself is ready."
        )

        print(
            "Once the enriched file contains position rows, "
            "run this same command again."
        )

        return

    # ============================================================
    # DATA ADAPTER
    # ============================================================

    adapted = normalize(
        raw=payload,
        own=own_driver,
        rival=rival_driver,
        energy_mj=args.energy_mj,
        assume_green=args.assume_green,
    )

    states = adapted[
        "states"
    ]

    if args.limit > 0:

        states = states[
            :args.limit
        ]

    print()
    print("=" * 76)
    print("ADAPTER RESULT")
    print("=" * 76)

    print(
        f"Accepted states : "
        f"{len(states)}"
    )

    print(
        f"Skipped frames  : "
        f"{adapted['skipped_frames']}"
    )

    if not states:

        print()
        print(
            "No valid adjacent-driver states were produced."
        )

        print(
            "Nothing will be sent to the hybrid policy."
        )

        return

    # ============================================================
    # OUTPUT SETUP
    # ============================================================

    args.output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    decisions = []

    current_belief = Belief()

    counts = {
        "ATTACK": 0,
        "DEFEND": 0,
        "HOLD": 0,
        "CONSERVE": 0,
        "REASSESS": 0,
        "NO_RECOMMENDATION": 0,
    }

    advisory_count = 0
    abstain_count = 0

    ml_reassess_count = 0
    shield_rejection_count = 0
    precheck_abstain_count = 0

    # ============================================================
    # REPLAY
    # ============================================================

    print()
    print("=" * 76)
    print("HYBRID REPLAY")
    print("=" * 76)

    for index, state_data in enumerate(
        states,
        start=1,
    ):

        request = PlanRequest(
            state=state_data,
            belief=current_belief,
        )

        result = hybrid_plan(
            request
        )

        # --------------------------------------------------------
        # Preserve Bayesian belief through the historical replay.
        # --------------------------------------------------------

        belief_data = result.get(
            "belief"
        )

        if belief_data:

            current_belief = Belief(
                **belief_data
            )

        recommendation = result.get(
            "recommendation",
            "NO_RECOMMENDATION",
        )

        status = result.get(
            "status",
            "abstain",
        )

        counts.setdefault(
            recommendation,
            0,
        )

        counts[
            recommendation
        ] += 1

        if status == "advisory":
            advisory_count += 1
        else:
            abstain_count += 1

        ml_policy = result.get(
            "ml_policy",
            {},
        )

        shield = result.get(
            "shield",
            {},
        )

        if (
            ml_policy.get(
                "reassess"
            )
            is True
        ):
            ml_reassess_count += 1

        if (
            shield.get(
                "reason"
            )
            == "deterministic_constraint_rejection"
        ):
            shield_rejection_count += 1

        if (
            ml_policy.get(
                "status"
            )
            == "skipped"
        ):
            precheck_abstain_count += 1

        row = {
            "frame":
                index,

            "timestamp_s":
                state_data[
                    "timestamp_s"
                ],

            "own_speed_kph":
                state_data[
                    "own_speed_kph"
                ],

            "rival_speed_kph":
                state_data[
                    "rival_speed_kph"
                ],

            "speed_delta_kph":
                (
                    state_data[
                        "own_speed_kph"
                    ]
                    -
                    state_data[
                        "rival_speed_kph"
                    ]
                ),

            "gap_s":
                state_data[
                    "gap_s"
                ],

            "gap_rate_s_per_s":
                state_data[
                    "gap_rate_s_per_s"
                ],

            "recommendation":
                recommendation,

            "status":
                status,

            "deterministic_recommendation":
                result.get(
                    "deterministic_recommendation"
                ),

            "ml_predicted_action":
                ml_policy.get(
                    "predicted_action"
                ),

            "ml_top_probability":
                ml_policy.get(
                    "top_probability"
                ),

            "ml_probability_margin":
                ml_policy.get(
                    "probability_margin"
                ),

            "ml_reassess":
                ml_policy.get(
                    "reassess"
                ),

            "shield_passed":
                shield.get(
                    "passed"
                ),

            "shield_reason":
                shield.get(
                    "reason"
                ),

            "hybrid_latency_ms":
                result.get(
                    "hybrid_latency_ms"
                ),

            "reason":
                result.get(
                    "reason"
                ),
        }

        decisions.append(
            row
        )

        print(
            f"Frame {index:03d} | "
            f"gap={row['gap_s']:+.3f}s | "
            f"gap_rate="
            f"{row['gap_rate_s_per_s']:+.3f} | "
            f"ML="
            f"{row['ml_predicted_action']} | "
            f"FINAL="
            f"{recommendation} | "
            f"{status}"
        )

    # ============================================================
    # SAVE CSV
    # ============================================================

    csv_path = (
        args.output_dir
        / "decisions.csv"
    )

    with csv_path.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as handle:

        writer = csv.DictWriter(
            handle,
            fieldnames=list(
                decisions[0].keys()
            ),
        )

        writer.writeheader()

        writer.writerows(
            decisions
        )

    # ============================================================
    # SAVE JSON
    # ============================================================

    json_path = (
        args.output_dir
        / "decisions.json"
    )

    json_path.write_text(
        json.dumps(
            decisions,
            indent=2,
        ),
        encoding="utf-8",
    )

    # ============================================================
    # SUMMARY
    # ============================================================

    total = len(
        decisions
    )

    summary = {
        "input_file":
            str(
                args.input
            ),

        "own_driver":
            own_driver,

        "rival_driver":
            rival_driver,

        "energy_source":
            "simulated",

        "simulated_energy_mj":
            args.energy_mj,

        "assume_green":
            args.assume_green,

        "raw_stream_counts":
            stream_counts,

        "adapter": {
            "accepted_states":
                len(states),

            "skipped_frames":
                adapted[
                    "skipped_frames"
                ],

            "notes":
                adapted[
                    "notes"
                ],
        },

        "replay": {
            "frames":
                total,

            "advisory_frames":
                advisory_count,

            "abstain_frames":
                abstain_count,

            "advisory_rate":
                (
                    advisory_count
                    / total
                    if total
                    else 0.0
                ),

            "ml_reassess_frames":
                ml_reassess_count,

            "shield_rejection_frames":
                shield_rejection_count,

            "precheck_abstain_frames":
                precheck_abstain_count,

            "recommendation_counts":
                counts,
        },

        "model_note": (
            "XGBoost is a bootstrap teacher-policy "
            "imitation model, not independently validated "
            "real-race strategy intelligence."
        ),

        "replay_note": (
            "Historical observations are fixed and do not "
            "change in response to recommendations."
        ),
    }

    summary_path = (
        args.output_dir
        / "summary.json"
    )

    summary_path.write_text(
        json.dumps(
            summary,
            indent=2,
        ),
        encoding="utf-8",
    )

    # ============================================================
    # DISPLAY SUMMARY
    # ============================================================

    print()
    print("=" * 76)
    print("REPLAY SUMMARY")
    print("=" * 76)

    print(
        f"Frames             : "
        f"{total}"
    )

    print(
        f"Advisory           : "
        f"{advisory_count}"
    )

    print(
        f"Abstain            : "
        f"{abstain_count}"
    )

    print(
        f"ML REASSESS        : "
        f"{ml_reassess_count}"
    )

    print(
        f"Shield rejections  : "
        f"{shield_rejection_count}"
    )

    print(
        f"Precheck abstains  : "
        f"{precheck_abstain_count}"
    )

    print()

    for action, count in counts.items():

        if count:

            print(
                f"{action:18s}: "
                f"{count}"
            )

    print()
    print(
        f"CSV     -> {csv_path}"
    )

    print(
        f"JSON    -> {json_path}"
    )

    print(
        f"Summary -> {summary_path}"
    )


if __name__ == "__main__":
    main()