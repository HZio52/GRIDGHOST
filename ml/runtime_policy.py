from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from xgboost import XGBClassifier


LABELS = [
    "ATTACK",
    "DEFEND",
    "HOLD",
    "CONSERVE",
]


FEATURES = [
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


TOP_PROBABILITY_THRESHOLD = 0.55
TOP_TWO_MARGIN_THRESHOLD = 0.15


@dataclass
class PolicyResult:
    recommendation: str
    predicted_action: str

    top_probability: float
    second_probability: float
    probability_margin: float

    probabilities: dict[str, float]

    reassess: bool
    reassess_reason: str | None


class GridGhostPolicy:

    def __init__(
        self,
        model_path: str,
    ) -> None:

        self.model = XGBClassifier()

        self.model.load_model(
            model_path
        )

    def predict(
        self,
        state: dict,
    ) -> PolicyResult:

        missing = [
            feature
            for feature in FEATURES
            if feature not in state
        ]

        if missing:
            raise ValueError(
                f"Missing GRIDGHOST features: {missing}"
            )

        row = pd.DataFrame(
            [
                {
                    feature: state[feature]
                    for feature in FEATURES
                }
            ],
            columns=FEATURES,
        )

        probabilities = (
            self.model.predict_proba(
                row
            )[0]
        )

        probabilities = np.asarray(
            probabilities,
            dtype=np.float64,
        )

        probabilities = (
            probabilities
            / probabilities.sum()
        )

        ranked_indices = np.argsort(
            probabilities
        )[::-1]

        top_index = int(
            ranked_indices[0]
        )

        second_index = int(
            ranked_indices[1]
        )

        top_probability = float(
            probabilities[top_index]
        )

        second_probability = float(
            probabilities[second_index]
        )

        margin = (
            top_probability
            - second_probability
        )

        predicted_action = (
            LABELS[top_index]
        )

        reassess = False
        reassess_reason = None

        if (
            top_probability
            < TOP_PROBABILITY_THRESHOLD
        ):
            reassess = True

            reassess_reason = (
                "TOP_PROBABILITY_BELOW_THRESHOLD"
            )

        elif (
            margin
            < TOP_TWO_MARGIN_THRESHOLD
        ):
            reassess = True

            reassess_reason = (
                "TOP_TWO_ACTIONS_TOO_CLOSE"
            )

        recommendation = (
            "REASSESS"
            if reassess
            else predicted_action
        )

        probability_map = {
            label: float(
                probabilities[index]
            )
            for index, label
            in enumerate(LABELS)
        }

        return PolicyResult(
            recommendation=recommendation,
            predicted_action=predicted_action,

            top_probability=top_probability,
            second_probability=second_probability,
            probability_margin=float(
                margin
            ),

            probabilities=probability_map,

            reassess=reassess,
            reassess_reason=(
                reassess_reason
            ),
        )


if __name__ == "__main__":

    policy = GridGhostPolicy(
        "models/gridghost_core_tuned.json"
    )

    example_state = {
        "own_speed_kph": 261.0,
        "rival_speed_kph": 273.0,
        "speed_delta_kph": -12.0,
        "gap_s": 0.112,
        "gap_rate_s_per_s": 0.0,

        "own_energy_mj": 2.4,
        "energy_uncertainty_mj": 0.08,

        "recovery_kw": 95.0,
        "recovery_uncertainty_kw": 8.0,
    }

    result = policy.predict(
        example_state
    )

    print()
    print("=" * 72)
    print("GRIDGHOST RUNTIME POLICY")
    print("=" * 72)

    print(
        f"Recommendation : "
        f"{result.recommendation}"
    )

    print(
        f"Predicted      : "
        f"{result.predicted_action}"
    )

    print(
        f"Top probability: "
        f"{result.top_probability:.4f}"
    )

    print(
        f"Runner-up      : "
        f"{result.second_probability:.4f}"
    )

    print(
        f"Margin         : "
        f"{result.probability_margin:.4f}"
    )

    print(
        f"REASSESS       : "
        f"{result.reassess}"
    )

    print(
        f"Reason         : "
        f"{result.reassess_reason}"
    )

    print()

    print("Probabilities:")

    for (
        label,
        probability,
    ) in result.probabilities.items():

        print(
            f"  {label:10s}: "
            f"{probability:.4f}"
        )