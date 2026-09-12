from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd
import shap
from xgboost import XGBClassifier

from ml.config import FEATURES, LABELS


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--model",
        type=Path,
        required=True,
    )

    parser.add_argument(
        "--features",
        type=Path,
        required=True,
    )

    parser.add_argument(
        "--row",
        type=int,
        required=True,
    )

    parser.add_argument(
        "--energy",
        type=float,
        default=2.4,
    )

    parser.add_argument(
        "--recovery",
        type=float,
        default=10.0,
    )

    args = parser.parse_args()

    # ---------------------------------------------------------
    # 1. Load telemetry features
    # ---------------------------------------------------------

    df = pd.read_csv(args.features)

    if args.row < 0 or args.row >= len(df):
        raise IndexError(
            f"Row {args.row} is outside dataset range "
            f"0-{len(df) - 1}"
        )

    row = df.iloc[args.row].copy()

    # ---------------------------------------------------------
    # 2. Add the same synthetic energy information used by
    #    ml.predict so explanation == actual prediction input
    # ---------------------------------------------------------

    row["own_energy_mj"] = args.energy
    row["energy_uncertainty_mj"] = 0.1
    row["recovery_kw"] = args.recovery
    row["recovery_uncertainty_kw"] = 5.0

    # ---------------------------------------------------------
    # 3. Check all trained features exist
    # ---------------------------------------------------------

    missing = [
        feature
        for feature in FEATURES
        if feature not in row.index
    ]

    if missing:
        raise ValueError(
            f"Missing model features: {missing}"
        )

    X = pd.DataFrame(
        [
            {
                feature: float(row[feature])
                for feature in FEATURES
            }
        ]
    )

    # ---------------------------------------------------------
    # 4. Load trained XGBoost model
    # ---------------------------------------------------------

    model = XGBClassifier()
    model.load_model(args.model)

    # ---------------------------------------------------------
    # 5. Make prediction
    # ---------------------------------------------------------

    probabilities = model.predict_proba(X)[0]

    prediction_index = int(probabilities.argmax())
    prediction = LABELS[prediction_index]

    print()
    print("=" * 70)
    print("GRIDGHOST ML PREDICTION")
    print("=" * 70)

    for index, action in enumerate(LABELS):
        print(
            f"{action:10s} "
            f"{probabilities[index] * 100:8.2f}%"
        )

    print()
    print(f"RECOMMENDATION : {prediction}")
    print(
        f"CONFIDENCE     : "
        f"{probabilities[prediction_index] * 100:.2f}%"
    )

    # ---------------------------------------------------------
    # 6. SHAP explanation
    # ---------------------------------------------------------

    print()
    print("=" * 70)
    print("CALCULATING SHAP EXPLANATION")
    print("=" * 70)

    explainer = shap.TreeExplainer(model)

    explanation = explainer(X)

    values = explanation.values

    # Multiclass XGBoost normally:
    # (rows, features, classes)
    if values.ndim == 3:
        shap_values = values[
            0,
            :,
            prediction_index,
        ]

    # Binary/single-output fallback
    elif values.ndim == 2:
        shap_values = values[0]

    else:
        raise RuntimeError(
            "Unexpected SHAP output shape: "
            f"{values.shape}"
        )

    result = pd.DataFrame(
        {
            "feature": FEATURES,
            "value": X.iloc[0].values,
            "shap": shap_values,
        }
    )

    result["absolute_shap"] = (
        result["shap"].abs()
    )

    result = result.sort_values(
        "absolute_shap",
        ascending=False,
    )

    # ---------------------------------------------------------
    # 7. Print top contributing factors
    # ---------------------------------------------------------

    print()
    print("=" * 70)
    print(f"TOP REASONS FOR {prediction}")
    print("=" * 70)

    for _, item in result.head(10).iterrows():

        if item["shap"] > 0:
            effect = f"SUPPORTS {prediction}"
        else:
            effect = f"OPPOSES {prediction}"

        print(
            f"{item['feature']:30s}"
            f"value={item['value']:10.3f}   "
            f"{effect:20s} "
            f"SHAP={item['shap']:+.4f}"
        )

    print()
    print("=" * 70)
    print("CURRENT INPUT STATE")
    print("=" * 70)

    important_inputs = [
        "own_speed_kph",
        "rival_speed_kph",
        "speed_delta_kph",
        "gap_s",
        "gap_rate_s_per_s",
        "own_throttle",
        "rival_throttle",
        "own_brake",
        "rival_brake",
        "own_energy_mj",
        "recovery_kw",
    ]

    for feature in important_inputs:
        if feature in X.columns:
            print(
                f"{feature:30s}"
                f"{float(X.iloc[0][feature]):10.3f}"
            )

    print()
    print(
        "NOTE: own_energy_mj and recovery values are "
        "currently simulated inputs, not OpenF1 battery telemetry."
    )


if __name__ == "__main__":
    main()