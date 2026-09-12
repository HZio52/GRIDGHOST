from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from scipy.optimize import minimize_scalar
from sklearn.metrics import (
    accuracy_score,
    log_loss,
)


LABELS = [
    "ATTACK",
    "DEFEND",
    "HOLD",
    "CONSERVE",
]


MARGIN_COLUMNS = [
    "margin_ATTACK",
    "margin_DEFEND",
    "margin_HOLD",
    "margin_CONSERVE",
]


PROBABILITY_COLUMNS = [
    "prob_ATTACK",
    "prob_DEFEND",
    "prob_HOLD",
    "prob_CONSERVE",
]


# ============================================================
# HELPERS
# ============================================================

def softmax(logits: np.ndarray) -> np.ndarray:

    logits = np.asarray(
        logits,
        dtype=np.float64,
    )

    logits = (
        logits
        - np.max(
            logits,
            axis=1,
            keepdims=True,
        )
    )

    exp_values = np.exp(logits)

    return (
        exp_values
        / exp_values.sum(
            axis=1,
            keepdims=True,
        )
    )


def apply_temperature(
    margins: np.ndarray,
    temperature: float,
) -> np.ndarray:

    if temperature <= 0:
        raise ValueError(
            "Temperature must be positive."
        )

    return softmax(
        margins / temperature
    )


def multiclass_brier(
    y_true: np.ndarray,
    probabilities: np.ndarray,
) -> float:

    one_hot = np.zeros_like(
        probabilities,
        dtype=np.float64,
    )

    one_hot[
        np.arange(len(y_true)),
        y_true,
    ] = 1.0

    return float(
        np.mean(
            np.sum(
                (
                    probabilities
                    - one_hot
                )
                ** 2,
                axis=1,
            )
        )
    )


def top_label_ece(
    y_true: np.ndarray,
    probabilities: np.ndarray,
    bins: int = 15,
) -> float:

    predicted = np.argmax(
        probabilities,
        axis=1,
    )

    confidence = np.max(
        probabilities,
        axis=1,
    )

    correct = (
        predicted == y_true
    ).astype(np.float64)

    edges = np.linspace(
        0.0,
        1.0,
        bins + 1,
    )

    ece = 0.0

    for index in range(bins):

        lower = edges[index]
        upper = edges[index + 1]

        if index == bins - 1:
            mask = (
                (confidence >= lower)
                & (confidence <= upper)
            )
        else:
            mask = (
                (confidence >= lower)
                & (confidence < upper)
            )

        count = int(
            np.sum(mask)
        )

        if count == 0:
            continue

        bin_accuracy = float(
            np.mean(
                correct[mask]
            )
        )

        bin_confidence = float(
            np.mean(
                confidence[mask]
            )
        )

        weight = (
            count / len(y_true)
        )

        ece += weight * abs(
            bin_accuracy
            - bin_confidence
        )

    return float(ece)


def fit_temperature(
    margins: np.ndarray,
    y_true: np.ndarray,
) -> float:

    def objective(
        log_temperature: float,
    ) -> float:

        temperature = float(
            np.exp(
                log_temperature
            )
        )

        probabilities = (
            apply_temperature(
                margins,
                temperature,
            )
        )

        return float(
            log_loss(
                y_true,
                probabilities,
                labels=list(
                    range(len(LABELS))
                ),
            )
        )

    result = minimize_scalar(
        objective,
        bounds=(
            np.log(0.05),
            np.log(10.0),
        ),
        method="bounded",
        options={
            "xatol": 1e-7,
        },
    )

    if not result.success:
        raise RuntimeError(
            "Temperature optimization failed: "
            f"{result.message}"
        )

    return float(
        np.exp(
            result.x
        )
    )


# ============================================================
# MAIN
# ============================================================

def main() -> None:

    parser = argparse.ArgumentParser(
        description=(
            "Temperature calibration for "
            "GRIDGHOST tuned Core XGBoost."
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
            "reports/ml/core_calibration"
        ),
    )

    parser.add_argument(
        "--bins",
        type=int,
        default=15,
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

    required_columns = {
        "actual",
        "predicted",
        "fold",
        *MARGIN_COLUMNS,
        *PROBABILITY_COLUMNS,
    }

    missing = sorted(
        required_columns
        - set(df.columns)
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

    y = (
        df["actual"]
        .map(label_to_id)
        .astype(int)
        .to_numpy()
    )

    folds = (
        df["fold"]
        .astype(int)
        .to_numpy()
    )

    margins = (
        df[MARGIN_COLUMNS]
        .to_numpy(
            dtype=np.float64
        )
    )

    raw_probabilities = (
        df[PROBABILITY_COLUMNS]
        .to_numpy(
            dtype=np.float64
        )
    )

    raw_probabilities = (
        raw_probabilities
        / raw_probabilities.sum(
            axis=1,
            keepdims=True,
        )
    )

    calibrated_probabilities = (
        np.zeros_like(
            raw_probabilities,
            dtype=np.float64,
        )
    )

    fold_results = []

    print()
    print("=" * 72)
    print("GRIDGHOST TEMPERATURE CALIBRATION")
    print("=" * 72)

    print(
        f"Rows  : {len(df)}"
    )

    print(
        f"Folds : {sorted(np.unique(folds))}"
    )

    print()

    # ========================================================
    # CROSS-FITTED CALIBRATION
    # ========================================================

    for fold in sorted(
        np.unique(folds)
    ):

        calibration_mask = (
            folds != fold
        )

        evaluation_mask = (
            folds == fold
        )

        temperature = (
            fit_temperature(
                margins[
                    calibration_mask
                ],
                y[
                    calibration_mask
                ],
            )
        )

        fold_calibrated = (
            apply_temperature(
                margins[
                    evaluation_mask
                ],
                temperature,
            )
        )

        calibrated_probabilities[
            evaluation_mask
        ] = fold_calibrated

        raw_fold = (
            raw_probabilities[
                evaluation_mask
            ]
        )

        fold_y = (
            y[
                evaluation_mask
            ]
        )

        raw_loss = log_loss(
            fold_y,
            raw_fold,
            labels=list(
                range(len(LABELS))
            ),
        )

        calibrated_loss = log_loss(
            fold_y,
            fold_calibrated,
            labels=list(
                range(len(LABELS))
            ),
        )

        raw_ece = top_label_ece(
            fold_y,
            raw_fold,
            bins=args.bins,
        )

        calibrated_ece = (
            top_label_ece(
                fold_y,
                fold_calibrated,
                bins=args.bins,
            )
        )

        fold_result = {
            "fold": int(fold),
            "temperature": float(
                temperature
            ),
            "raw_log_loss": float(
                raw_loss
            ),
            "calibrated_log_loss": float(
                calibrated_loss
            ),
            "raw_ece": float(
                raw_ece
            ),
            "calibrated_ece": float(
                calibrated_ece
            ),
        }

        fold_results.append(
            fold_result
        )

        print(
            f"Fold {fold}: "
            f"T={temperature:.6f}  "
            f"RawLL={raw_loss:.6f}  "
            f"CalLL={calibrated_loss:.6f}  "
            f"RawECE={raw_ece:.6f}  "
            f"CalECE={calibrated_ece:.6f}"
        )

    # ========================================================
    # OVERALL CROSS-FITTED RESULTS
    # ========================================================

    raw_predictions = np.argmax(
        raw_probabilities,
        axis=1,
    )

    calibrated_predictions = np.argmax(
        calibrated_probabilities,
        axis=1,
    )

    raw_accuracy = accuracy_score(
        y,
        raw_predictions,
    )

    calibrated_accuracy = (
        accuracy_score(
            y,
            calibrated_predictions,
        )
    )

    raw_log_loss = log_loss(
        y,
        raw_probabilities,
        labels=list(
            range(len(LABELS))
        ),
    )

    calibrated_log_loss = log_loss(
        y,
        calibrated_probabilities,
        labels=list(
            range(len(LABELS))
        ),
    )

    raw_brier = multiclass_brier(
        y,
        raw_probabilities,
    )

    calibrated_brier = (
        multiclass_brier(
            y,
            calibrated_probabilities,
        )
    )

    raw_ece = top_label_ece(
        y,
        raw_probabilities,
        bins=args.bins,
    )

    calibrated_ece = (
        top_label_ece(
            y,
            calibrated_probabilities,
            bins=args.bins,
        )
    )

    # ========================================================
    # FINAL TEMPERATURE
    # ========================================================

    # This value is fitted using all OOF predictions and can
    # later be applied to the final full-data model margins.

    final_temperature = (
        fit_temperature(
            margins,
            y,
        )
    )

    # ========================================================
    # SAVE CALIBRATED OOF DATA
    # ========================================================

    calibrated_df = df.copy()

    calibrated_df[
        "cal_prob_ATTACK"
    ] = calibrated_probabilities[:, 0]

    calibrated_df[
        "cal_prob_DEFEND"
    ] = calibrated_probabilities[:, 1]

    calibrated_df[
        "cal_prob_HOLD"
    ] = calibrated_probabilities[:, 2]

    calibrated_df[
        "cal_prob_CONSERVE"
    ] = calibrated_probabilities[:, 3]

    calibrated_df[
        "cal_predicted"
    ] = [
        LABELS[index]
        for index in calibrated_predictions
    ]

    predictions_path = (
        args.output_dir
        / "calibrated_oof_predictions.csv"
    )

    calibrated_df.to_csv(
        predictions_path,
        index=False,
    )

    # ========================================================
    # SAVE REPORT
    # ========================================================

    report = {
        "method":
            "multiclass temperature scaling",

        "labels":
            LABELS,

        "rows":
            int(len(df)),

        "calibration_evaluation":
            (
                "cross-fitted using existing "
                "grouped OOF folds"
            ),

        "ece_bins":
            int(args.bins),

        "raw": {
            "accuracy":
                float(raw_accuracy),

            "log_loss":
                float(raw_log_loss),

            "brier":
                float(raw_brier),

            "top_label_ece":
                float(raw_ece),
        },

        "calibrated": {
            "accuracy":
                float(
                    calibrated_accuracy
                ),

            "log_loss":
                float(
                    calibrated_log_loss
                ),

            "brier":
                float(
                    calibrated_brier
                ),

            "top_label_ece":
                float(
                    calibrated_ece
                ),
        },

        "final_temperature":
            float(
                final_temperature
            ),

        "fold_results":
            fold_results,

        "deployment_note": (
            "For inference, obtain raw multiclass "
            "XGBoost margins, divide every class "
            "margin by final_temperature, then "
            "apply softmax. Do not apply "
            "temperature scaling directly to "
            "already-softmaxed probabilities."
        ),

        "warning": (
            "Calibration is based on bootstrap "
            "teacher-policy OOF predictions. "
            "A fresh unseen race/session is still "
            "required for external validation."
        ),
    }

    report_path = (
        args.output_dir
        / "temperature_calibration.json"
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

    pd.DataFrame(
        fold_results
    ).to_csv(
        args.output_dir
        / "calibration_folds.csv",
        index=False,
    )

    # ========================================================
    # DISPLAY RESULT
    # ========================================================

    print()
    print("=" * 72)
    print("CROSS-FITTED CALIBRATION RESULT")
    print("=" * 72)

    print(
        f"Raw accuracy        : "
        f"{raw_accuracy:.6f}"
    )

    print(
        f"Calibrated accuracy : "
        f"{calibrated_accuracy:.6f}"
    )

    print()

    print(
        f"Raw log loss        : "
        f"{raw_log_loss:.6f}"
    )

    print(
        f"Calibrated log loss : "
        f"{calibrated_log_loss:.6f}"
    )

    print()

    print(
        f"Raw Brier           : "
        f"{raw_brier:.6f}"
    )

    print(
        f"Calibrated Brier    : "
        f"{calibrated_brier:.6f}"
    )

    print()

    print(
        f"Raw ECE             : "
        f"{raw_ece:.6f}"
    )

    print(
        f"Calibrated ECE      : "
        f"{calibrated_ece:.6f}"
    )

    print()

    print(
        f"Final temperature   : "
        f"{final_temperature:.8f}"
    )

    print()
    print(
        f"Report -> {report_path}"
    )

    print(
        f"OOF    -> {predictions_path}"
    )


if __name__ == "__main__":
    main()