from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from sklearn.metrics import (
    accuracy_score,
    f1_score,
    log_loss,
)
from sklearn.model_selection import StratifiedGroupKFold
from xgboost import XGBClassifier


LABELS = [
    "ATTACK",
    "DEFEND",
    "HOLD",
    "CONSERVE",
]


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


FULL = [
    "own_speed_kph",
    "rival_speed_kph",
    "speed_delta_kph",
    "gap_s",
    "gap_rate_s_per_s",
    "own_accel_kph_s",
    "rival_accel_kph_s",
    "own_throttle",
    "rival_throttle",
    "throttle_delta",
    "own_brake",
    "rival_brake",
    "own_rpm",
    "rival_rpm",
    "rpm_delta",
    "own_gear",
    "rival_gear",
    "own_drs",
    "rival_drs",
    "speed_delta_roll_mean",
    "speed_delta_roll_std",
    "own_energy_mj",
    "energy_uncertainty_mj",
    "recovery_kw",
    "recovery_uncertainty_kw",
]


FEATURE_SETS = {
    "core": CORE,
    "core_brake": CORE + BRAKE,
    "core_throttle": CORE + THROTTLE,
    "core_temporal": CORE + TEMPORAL,
    "core_powertrain": CORE + POWERTRAIN,
    "full": FULL,
}


def build_model():
    return XGBClassifier(
        objective="multi:softprob",
        num_class=len(LABELS),

        n_estimators=500,
        max_depth=5,
        learning_rate=0.05,

        subsample=0.85,
        colsample_bytree=0.85,

        tree_method="hist",
        eval_metric="mlogloss",

        random_state=42,
        n_jobs=-1,
    )


def main():

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--data",
        type=Path,
        required=True,
    )

    parser.add_argument(
        "--folds",
        type=int,
        default=5,
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=Path(
            "reports/ml/ablation_cv_50k.csv"
        ),
    )

    args = parser.parse_args()

    df = pd.read_csv(args.data)

    # ---------------------------------------------------------
    # Validate dataset
    # ---------------------------------------------------------

    required = {
        "action",
        "source_group",
    }

    missing = required - set(df.columns)

    if missing:
        raise ValueError(
            f"Missing required columns: {missing}"
        )

    label_to_id = {
        label: i
        for i, label in enumerate(LABELS)
    }

    y = (
        df["action"]
        .map(label_to_id)
        .astype(int)
        .to_numpy()
    )

    groups = df["source_group"].to_numpy()

    print()
    print("=" * 72)
    print("GRIDGHOST GROUPED FEATURE ABLATION")
    print("=" * 72)

    print(f"Rows          : {len(df)}")
    print(
        f"Source groups : "
        f"{df['source_group'].nunique()}"
    )
    print(f"CV folds      : {args.folds}")

    print()

    splitter = StratifiedGroupKFold(
        n_splits=args.folds,
        shuffle=True,
        random_state=42,
    )

    summary_rows = []
    detailed_rows = []

    # ---------------------------------------------------------
    # Test every feature family
    # ---------------------------------------------------------

    for variant, features in FEATURE_SETS.items():

        print()
        print("=" * 72)
        print(
            f"{variant.upper()} "
            f"({len(features)} features)"
        )
        print("=" * 72)

        missing_features = [
            feature
            for feature in features
            if feature not in df.columns
        ]

        if missing_features:
            raise ValueError(
                f"{variant} missing features: "
                f"{missing_features}"
            )

        X = df[features]

        macro_scores = []
        accuracy_scores = []
        loss_scores = []

        class_scores = {
            label: []
            for label in LABELS
        }

        for fold, (
            train_idx,
            val_idx,
        ) in enumerate(
            splitter.split(
                X,
                y,
                groups,
            ),
            start=1,
        ):

            X_train = X.iloc[train_idx]
            X_val = X.iloc[val_idx]

            y_train = y[train_idx]
            y_val = y[val_idx]

            train_groups = set(
                groups[train_idx]
            )

            val_groups = set(
                groups[val_idx]
            )

            overlap = (
                train_groups
                & val_groups
            )

            if overlap:
                raise RuntimeError(
                    "GROUP LEAKAGE DETECTED: "
                    f"{overlap}"
                )

            model = build_model()

            model.fit(
                X_train,
                y_train,
                verbose=False,
            )

            pred = model.predict(X_val)

            probabilities = (
                model.predict_proba(X_val)
            )

            macro = f1_score(
                y_val,
                pred,
                average="macro",
            )

            accuracy = accuracy_score(
                y_val,
                pred,
            )

            loss = log_loss(
                y_val,
                probabilities,
                labels=list(
                    range(len(LABELS))
                ),
            )

            per_class = f1_score(
                y_val,
                pred,
                labels=list(
                    range(len(LABELS))
                ),
                average=None,
                zero_division=0,
            )

            macro_scores.append(macro)
            accuracy_scores.append(accuracy)
            loss_scores.append(loss)

            for index, label in enumerate(
                LABELS
            ):
                class_scores[label].append(
                    per_class[index]
                )

            detailed_rows.append(
                {
                    "variant": variant,
                    "fold": fold,
                    "feature_count": len(
                        features
                    ),
                    "train_rows": len(
                        train_idx
                    ),
                    "validation_rows": len(
                        val_idx
                    ),
                    "train_groups": len(
                        train_groups
                    ),
                    "validation_groups": len(
                        val_groups
                    ),
                    "macro_f1": macro,
                    "accuracy": accuracy,
                    "log_loss": loss,
                    "attack_f1": (
                        per_class[0]
                    ),
                    "defend_f1": (
                        per_class[1]
                    ),
                    "hold_f1": (
                        per_class[2]
                    ),
                    "conserve_f1": (
                        per_class[3]
                    ),
                }
            )

            print(
                f"Fold {fold}: "
                f"Macro-F1={macro:.5f}  "
                f"Accuracy={accuracy:.5f}  "
                f"LogLoss={loss:.5f}"
            )

        # -----------------------------------------------------
        # Aggregate
        # -----------------------------------------------------

        mean_macro = float(
            np.mean(macro_scores)
        )

        std_macro = float(
            np.std(macro_scores)
        )

        mean_accuracy = float(
            np.mean(accuracy_scores)
        )

        mean_loss = float(
            np.mean(loss_scores)
        )

        result = {
            "variant": variant,
            "feature_count": len(features),

            "macro_f1_mean": mean_macro,
            "macro_f1_std": std_macro,

            "accuracy_mean": mean_accuracy,
            "log_loss_mean": mean_loss,

            "attack_f1_mean": float(
                np.mean(
                    class_scores["ATTACK"]
                )
            ),

            "defend_f1_mean": float(
                np.mean(
                    class_scores["DEFEND"]
                )
            ),

            "hold_f1_mean": float(
                np.mean(
                    class_scores["HOLD"]
                )
            ),

            "conserve_f1_mean": float(
                np.mean(
                    class_scores["CONSERVE"]
                )
            ),
        }

        summary_rows.append(result)

        print()
        print(
            f"MEAN Macro-F1 : "
            f"{mean_macro:.5f}"
        )

        print(
            f"STD Macro-F1  : "
            f"{std_macro:.5f}"
        )

    # ---------------------------------------------------------
    # Save results
    # ---------------------------------------------------------

    summary = pd.DataFrame(
        summary_rows
    )

    summary = summary.sort_values(
        "macro_f1_mean",
        ascending=False,
    )

    args.output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    summary.to_csv(
        args.output,
        index=False,
    )

    detail_path = (
        args.output.parent
        / "ablation_cv_50k_folds.csv"
    )

    pd.DataFrame(
        detailed_rows
    ).to_csv(
        detail_path,
        index=False,
    )

    json_path = (
        args.output.parent
        / "ablation_cv_50k.json"
    )

    with json_path.open(
        "w",
        encoding="utf-8",
    ) as handle:
        json.dump(
            summary.to_dict(
                orient="records"
            ),
            handle,
            indent=2,
        )

    print()
    print("=" * 72)
    print("FINAL CROSS-VALIDATION RANKING")
    print("=" * 72)

    print(
        summary[
            [
                "variant",
                "feature_count",
                "macro_f1_mean",
                "macro_f1_std",
                "accuracy_mean",
                "log_loss_mean",
                "hold_f1_mean",
                "conserve_f1_mean",
            ]
        ].to_string(
            index=False
        )
    )

    print()
    print(
        f"Summary saved -> {args.output}"
    )

    print(
        f"Fold results -> {detail_path}"
    )

    print(
        f"JSON results -> {json_path}"
    )


if __name__ == "__main__":
    main()