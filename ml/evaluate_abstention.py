from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from sklearn.metrics import (
    accuracy_score,
    f1_score,
)


LABELS = [
    "ATTACK",
    "DEFEND",
    "HOLD",
    "CONSERVE",
]


PROBABILITY_COLUMNS = [
    "prob_ATTACK",
    "prob_DEFEND",
    "prob_HOLD",
    "prob_CONSERVE",
]


def evaluate_subset(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    accepted: np.ndarray,
) -> dict:

    total = len(y_true)

    accepted_rows = int(
        np.sum(accepted)
    )

    rejected_rows = (
        total - accepted_rows
    )

    if accepted_rows == 0:
        return {
            "total_rows": total,
            "accepted_rows": 0,
            "rejected_rows": rejected_rows,
            "coverage": 0.0,
            "abstain_rate": 1.0,
            "accuracy": None,
            "macro_f1": None,
        }

    accepted_y = (
        y_true[accepted]
    )

    accepted_pred = (
        y_pred[accepted]
    )

    return {
        "total_rows":
            int(total),

        "accepted_rows":
            accepted_rows,

        "rejected_rows":
            int(rejected_rows),

        "coverage":
            float(
                accepted_rows / total
            ),

        "abstain_rate":
            float(
                rejected_rows / total
            ),

        "accuracy":
            float(
                accuracy_score(
                    accepted_y,
                    accepted_pred,
                )
            ),

        "macro_f1":
            float(
                f1_score(
                    accepted_y,
                    accepted_pred,
                    average="macro",
                    labels=list(
                        range(len(LABELS))
                    ),
                    zero_division=0,
                )
            ),
    }


def main() -> None:

    parser = argparse.ArgumentParser(
        description=(
            "Evaluate uncertainty and abstention "
            "rules for GRIDGHOST."
        )
    )

    parser.add_argument(
        "--oof",
        type=Path,
        required=True,
    )

    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(
            "reports/ml/core_abstention"
        ),
    )

    args = parser.parse_args()

    if not args.oof.exists():
        raise FileNotFoundError(
            f"OOF file not found: {args.oof}"
        )

    args.output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    df = pd.read_csv(
        args.oof
    )

    required = {
        "actual",
        *PROBABILITY_COLUMNS,
    }

    missing = sorted(
        required - set(df.columns)
    )

    if missing:
        raise ValueError(
            f"Missing columns: {missing}"
        )

    label_to_id = {
        label: index
        for index, label
        in enumerate(LABELS)
    }

    y_true = (
        df["actual"]
        .map(label_to_id)
        .astype(int)
        .to_numpy()
    )

    probabilities = (
        df[PROBABILITY_COLUMNS]
        .to_numpy(
            dtype=np.float64
        )
    )

    probabilities = (
        probabilities
        / probabilities.sum(
            axis=1,
            keepdims=True,
        )
    )

    y_pred = np.argmax(
        probabilities,
        axis=1,
    )

    # ========================================================
    # UNCERTAINTY MEASURES
    # ========================================================

    sorted_probs = np.sort(
        probabilities,
        axis=1,
    )

    top_probability = (
        sorted_probs[:, -1]
    )

    second_probability = (
        sorted_probs[:, -2]
    )

    probability_margin = (
        top_probability
        - second_probability
    )

    entropy = -np.sum(
        probabilities
        * np.log(
            np.clip(
                probabilities,
                1e-12,
                1.0,
            )
        ),
        axis=1,
    )

    normalized_entropy = (
        entropy
        / np.log(len(LABELS))
    )

    correct = (
        y_pred == y_true
    )

    # ========================================================
    # BASELINE
    # ========================================================

    baseline_accuracy = float(
        accuracy_score(
            y_true,
            y_pred,
        )
    )

    baseline_macro_f1 = float(
        f1_score(
            y_true,
            y_pred,
            average="macro",
        )
    )

    print()
    print("=" * 76)
    print("GRIDGHOST UNCERTAINTY / ABSTENTION ANALYSIS")
    print("=" * 76)

    print(
        f"Rows              : {len(df)}"
    )

    print(
        f"Baseline accuracy : "
        f"{baseline_accuracy:.6f}"
    )

    print(
        f"Baseline Macro-F1 : "
        f"{baseline_macro_f1:.6f}"
    )

    print()

    # ========================================================
    # TOP-PROBABILITY THRESHOLDS
    # ========================================================

    probability_thresholds = [
        0.40,
        0.45,
        0.50,
        0.55,
        0.60,
        0.65,
        0.70,
        0.75,
        0.80,
        0.85,
        0.90,
        0.95,
    ]

    probability_results = []

    print("=" * 76)
    print("TOP-PROBABILITY GATE")
    print("=" * 76)

    for threshold in probability_thresholds:

        accepted = (
            top_probability
            >= threshold
        )

        result = evaluate_subset(
            y_true,
            y_pred,
            accepted,
        )

        result[
            "threshold"
        ] = threshold

        probability_results.append(
            result
        )

        accuracy = result[
            "accuracy"
        ]

        if accuracy is None:
            accuracy_text = "N/A"
        else:
            accuracy_text = (
                f"{accuracy:.4f}"
            )

        print(
            f"P >= {threshold:.2f} | "
            f"Coverage={result['coverage']:.3f} | "
            f"Abstain={result['abstain_rate']:.3f} | "
            f"Accuracy={accuracy_text}"
        )

    # ========================================================
    # TOP-1 / TOP-2 MARGIN GATE
    # ========================================================

    margin_thresholds = [
        0.00,
        0.05,
        0.10,
        0.15,
        0.20,
        0.25,
        0.30,
        0.35,
        0.40,
        0.50,
        0.60,
    ]

    margin_results = []

    print()
    print("=" * 76)
    print("TOP-1 / TOP-2 MARGIN GATE")
    print("=" * 76)

    for threshold in margin_thresholds:

        accepted = (
            probability_margin
            >= threshold
        )

        result = evaluate_subset(
            y_true,
            y_pred,
            accepted,
        )

        result[
            "threshold"
        ] = threshold

        margin_results.append(
            result
        )

        accuracy = result[
            "accuracy"
        ]

        if accuracy is None:
            accuracy_text = "N/A"
        else:
            accuracy_text = (
                f"{accuracy:.4f}"
            )

        print(
            f"Gap >= {threshold:.2f} | "
            f"Coverage={result['coverage']:.3f} | "
            f"Abstain={result['abstain_rate']:.3f} | "
            f"Accuracy={accuracy_text}"
        )

    # ========================================================
    # COMBINED GRID
    # ========================================================

    combined_results = []

    probability_grid = [
        0.50,
        0.55,
        0.60,
        0.65,
        0.70,
        0.75,
        0.80,
        0.85,
    ]

    margin_grid = [
        0.05,
        0.10,
        0.15,
        0.20,
        0.25,
        0.30,
    ]

    for probability_threshold in probability_grid:

        for margin_threshold in margin_grid:

            accepted = (
                (
                    top_probability
                    >= probability_threshold
                )
                &
                (
                    probability_margin
                    >= margin_threshold
                )
            )

            result = evaluate_subset(
                y_true,
                y_pred,
                accepted,
            )

            result[
                "probability_threshold"
            ] = probability_threshold

            result[
                "margin_threshold"
            ] = margin_threshold

            combined_results.append(
                result
            )

    combined_df = pd.DataFrame(
        combined_results
    )

    # ========================================================
    # ROW-LEVEL DIAGNOSTICS
    # ========================================================

    diagnostic_df = df.copy()

    diagnostic_df[
        "top_probability"
    ] = top_probability

    diagnostic_df[
        "second_probability"
    ] = second_probability

    diagnostic_df[
        "probability_margin"
    ] = probability_margin

    diagnostic_df[
        "normalized_entropy"
    ] = normalized_entropy

    diagnostic_df[
        "correct"
    ] = correct

    diagnostics_path = (
        args.output_dir
        / "uncertainty_rows.csv"
    )

    diagnostic_df.to_csv(
        diagnostics_path,
        index=False,
    )

    # ========================================================
    # SAVE TABLES
    # ========================================================

    probability_path = (
        args.output_dir
        / "probability_gate.csv"
    )

    pd.DataFrame(
        probability_results
    ).to_csv(
        probability_path,
        index=False,
    )

    margin_path = (
        args.output_dir
        / "margin_gate.csv"
    )

    pd.DataFrame(
        margin_results
    ).to_csv(
        margin_path,
        index=False,
    )

    combined_path = (
        args.output_dir
        / "combined_gate.csv"
    )

    combined_df.to_csv(
        combined_path,
        index=False,
    )

    # ========================================================
    # BEST CANDIDATES BY MINIMUM COVERAGE
    # ========================================================

    candidates = []

    for minimum_coverage in [
        0.95,
        0.90,
        0.85,
        0.80,
        0.70,
        0.60,
    ]:

        eligible = combined_df[
            combined_df[
                "coverage"
            ] >= minimum_coverage
        ].copy()

        if eligible.empty:
            continue

        best = eligible.sort_values(
            [
                "accuracy",
                "macro_f1",
            ],
            ascending=False,
        ).iloc[0]

        candidates.append(
            {
                "minimum_coverage":
                    minimum_coverage,

                "probability_threshold":
                    float(
                        best[
                            "probability_threshold"
                        ]
                    ),

                "margin_threshold":
                    float(
                        best[
                            "margin_threshold"
                        ]
                    ),

                "coverage":
                    float(
                        best[
                            "coverage"
                        ]
                    ),

                "abstain_rate":
                    float(
                        best[
                            "abstain_rate"
                        ]
                    ),

                "accuracy":
                    float(
                        best[
                            "accuracy"
                        ]
                    ),

                "macro_f1":
                    float(
                        best[
                            "macro_f1"
                        ]
                    ),
            }
        )

    report = {
        "model":
            "GRIDGHOST Tuned Core XGBoost",

        "probability_source":
            "raw grouped OOF probabilities",

        "rows":
            int(len(df)),

        "baseline_accuracy":
            baseline_accuracy,

        "baseline_macro_f1":
            baseline_macro_f1,

        "recommended_interpretation": (
            "Rows failing the uncertainty gate "
            "should produce REASSESS rather than "
            "forcing ATTACK/DEFEND/HOLD/CONSERVE."
        ),

        "candidate_rules":
            candidates,

        "warning": (
            "Thresholds are derived from bootstrap "
            "teacher-policy OOF data and require "
            "validation on unseen race/session data."
        ),
    }

    report_path = (
        args.output_dir
        / "abstention_report.json"
    )

    with report_path.open(
        "w",
        encoding="utf-8",
    ) as handle:
        json.dump(
            report,
            handle,
            indent=2,
        )

    # ========================================================
    # PRINT CANDIDATES
    # ========================================================

    print()
    print("=" * 76)
    print("BEST COMBINED CANDIDATES")
    print("=" * 76)

    for item in candidates:

        print(
            f"Min coverage "
            f"{item['minimum_coverage']:.0%} | "
            f"P>={item['probability_threshold']:.2f} | "
            f"Gap>={item['margin_threshold']:.2f} | "
            f"Actual coverage={item['coverage']:.3f} | "
            f"Accuracy={item['accuracy']:.4f} | "
            f"Macro-F1={item['macro_f1']:.4f}"
        )

    print()
    print(
        f"Report      -> {report_path}"
    )

    print(
        f"Probability -> {probability_path}"
    )

    print(
        f"Margin      -> {margin_path}"
    )

    print(
        f"Combined    -> {combined_path}"
    )

    print(
        f"Rows        -> {diagnostics_path}"
    )


if __name__ == "__main__":
    main()