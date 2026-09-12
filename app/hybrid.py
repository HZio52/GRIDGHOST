from __future__ import annotations

import os

from functools import lru_cache
from pathlib import Path
from time import perf_counter

from ml.runtime_policy import (
    GridGhostPolicy,
    TOP_PROBABILITY_THRESHOLD,
    TOP_TWO_MARGIN_THRESHOLD,
)

from .planner import (
    PlanRequest,
    plan,
)


ROOT = Path(
    __file__
).resolve().parents[1]


DEFAULT_MODEL_PATH = (
    ROOT
    / "models"
    / "gridghost_core_tuned.json"
)


def resolve_model_path() -> Path:
    """
    Resolve the XGBoost model used by the hybrid policy.

    GRIDGHOST_ML_MODEL may be:
    - absolute path
    - project-relative path

    Default:
    models/gridghost_core_tuned.json
    """

    configured = os.getenv(
        "GRIDGHOST_ML_MODEL"
    )

    if configured:

        path = Path(configured)

        if not path.is_absolute():
            path = ROOT / path

        return path.resolve()

    return DEFAULT_MODEL_PATH.resolve()


@lru_cache(maxsize=1)
def get_ml_policy() -> GridGhostPolicy:
    """
    Load the model once per backend process.
    """

    model_path = resolve_model_path()

    if not model_path.exists():

        raise FileNotFoundError(
            "GRIDGHOST ML model not found: "
            f"{model_path}"
        )

    return GridGhostPolicy(
        str(model_path)
    )


def build_ml_state(
    state,
) -> dict[str, float]:
    """
    Convert the API State schema into the exact
    9-feature representation expected by the
    frozen GRIDGHOST Core XGBoost model.
    """

    return {
        "own_speed_kph":
            float(
                state.own_speed_kph
            ),

        "rival_speed_kph":
            float(
                state.rival_speed_kph
            ),

        # Training definition:
        # own speed - rival speed
        "speed_delta_kph":
            float(
                state.own_speed_kph
                - state.rival_speed_kph
            ),

        "gap_s":
            float(
                state.gap_s
            ),

        "gap_rate_s_per_s":
            float(
                state.gap_rate_s_per_s
            ),

        "own_energy_mj":
            float(
                state.own_energy_mj
            ),

        "energy_uncertainty_mj":
            float(
                state.energy_uncertainty_mj
            ),

        "recovery_kw":
            float(
                state.recovery_kw
            ),

        "recovery_uncertainty_kw":
            float(
                state.recovery_uncertainty_kw
            ),
    }


def ml_result_payload(
    result,
    state,
) -> dict:
    """
    Serialize the runtime policy result for API/UI use.
    """

    gap_rate_source = (
        "request_or_adapter"
        if (
            "gap_rate_s_per_s"
            in state.model_fields_set
        )
        else
        "default_zero"
    )

    return {
        "status": "ok",

        "model": (
            "gridghost_core_tuned"
        ),

        "model_role": (
            "candidate_generator"
        ),

        "predicted_action":
            result.predicted_action,

        "recommendation":
            result.recommendation,

        "reassess":
            result.reassess,

        "reassess_reason":
            result.reassess_reason,

        "top_probability":
            result.top_probability,

        "second_probability":
            result.second_probability,

        "probability_margin":
            result.probability_margin,

        "probabilities":
            result.probabilities,

        "thresholds": {
            "minimum_top_probability":
                TOP_PROBABILITY_THRESHOLD,

            "minimum_top_two_margin":
                TOP_TWO_MARGIN_THRESHOLD,
        },

        "probability_label": (
            "raw model probability; "
            "not proven real-race confidence"
        ),

        "gap_rate_source":
            gap_rate_source,
    }


def hybrid_plan(
    body: PlanRequest,
) -> dict:
    """
    GRIDGHOST hybrid advisory architecture.

    1. Run the existing deterministic V2 planner.
       This supplies:
       - input gates
       - reserve constraints
       - deployment limits
       - attack/defend windows
       - terminal energy constraint
       - candidate feasibility

    2. Run the tuned XGBoost policy as the
       candidate action generator.

    3. Apply the ML uncertainty gate.

    4. Allow the ML action only when the
       deterministic planner has found that
       first action feasible.

    The ML model never bypasses the existing
    deterministic constraints.
    """

    started = perf_counter()

    # --------------------------------------------------------
    # STEP 1 — deterministic planner / shield
    # --------------------------------------------------------

    deterministic = plan(body)

    result = dict(
        deterministic
    )

    result[
        "hybrid_version"
    ] = "gridghost-hybrid-v1"

    result[
        "decision_architecture"
    ] = (
        "xgboost_candidate"
        "+uncertainty_gate"
        "+deterministic_shield"
    )

    result[
        "deterministic_recommendation"
    ] = deterministic.get(
        "recommendation"
    )

    # --------------------------------------------------------
    # If deterministic pre-checks already abstained,
    # do not even ask the ML model to override them.
    # --------------------------------------------------------

    if (
        deterministic.get("status")
        != "advisory"
    ):

        result[
            "ml_policy"
        ] = {
            "status": "skipped",
            "reason": (
                "Deterministic pre-check "
                "or feasibility layer abstained."
            ),
        }

        result[
            "shield"
        ] = {
            "passed": False,
            "reason": (
                "deterministic_precheck_abstained"
            ),
        }

        result[
            "hybrid_latency_ms"
        ] = (
            perf_counter()
            - started
        ) * 1000

        return result

    # --------------------------------------------------------
    # STEP 2 — ML candidate
    # --------------------------------------------------------

    try:

        policy = get_ml_policy()

        features = build_ml_state(
            body.state
        )

        ml_result = policy.predict(
            features
        )

    except Exception as exc:

        # Fail safe.
        # We do not silently pretend an ML recommendation
        # exists when the model cannot run.

        result.update(
            recommendation="REASSESS",
            status="abstain",
            reason=(
                "ML candidate generator unavailable: "
                f"{type(exc).__name__}: {exc}. "
                "Engineer review required."
            ),
        )

        result[
            "ml_policy"
        ] = {
            "status": "error",
            "error_type":
                type(exc).__name__,
            "message":
                str(exc),
        }

        result[
            "shield"
        ] = {
            "passed": False,
            "reason": (
                "ml_policy_unavailable"
            ),
        }

        result[
            "hybrid_latency_ms"
        ] = (
            perf_counter()
            - started
        ) * 1000

        return result

    result[
        "ml_policy"
    ] = ml_result_payload(
        ml_result,
        body.state,
    )

    # --------------------------------------------------------
    # STEP 3 — uncertainty / abstention gate
    # --------------------------------------------------------

    if ml_result.reassess:

        result.update(
            recommendation="REASSESS",
            status="abstain",
            reason=(
                "ML policy abstained because the "
                "current state is ambiguous. "
                f"Top probability "
                f"{ml_result.top_probability:.3f}; "
                f"top-two margin "
                f"{ml_result.probability_margin:.3f}. "
                "Engineer review required."
            ),
        )

        result[
            "shield"
        ] = {
            "passed": False,
            "reason": (
                "ml_uncertainty_gate"
            ),
        }

        result[
            "hybrid_latency_ms"
        ] = (
            perf_counter()
            - started
        ) * 1000

        return result

    ml_action = (
        ml_result.predicted_action
    )

    # --------------------------------------------------------
    # STEP 4 — find deterministic candidate corresponding
    # to the ML-selected first action.
    # --------------------------------------------------------

    candidates = (
        deterministic.get(
            "candidates",
            [],
        )
    )

    matching_candidate = next(
        (
            candidate
            for candidate in candidates
            if (
                candidate.get("action")
                == ml_action
            )
        ),
        None,
    )

    if matching_candidate is None:

        result.update(
            recommendation="REASSESS",
            status="abstain",
            reason=(
                f"ML selected {ml_action}, but "
                "the deterministic planner did "
                "not produce a matching candidate. "
                "Engineer review required."
            ),
        )

        result[
            "shield"
        ] = {
            "passed": False,
            "action": ml_action,
            "reason": (
                "candidate_missing"
            ),
        }

        result[
            "hybrid_latency_ms"
        ] = (
            perf_counter()
            - started
        ) * 1000

        return result

    # --------------------------------------------------------
    # STEP 5 — deterministic feasibility authority
    # --------------------------------------------------------

    if not matching_candidate.get(
        "valid",
        False,
    ):

        rejection_reasons = (
            matching_candidate.get(
                "rejection_reasons",
                [],
            )
        )

        result.update(
            recommendation="REASSESS",
            status="abstain",
            reason=(
                f"ML selected {ml_action}, but "
                "the deterministic shield rejected "
                "that action. "
                "Engineer review required."
            ),
        )

        result[
            "shield"
        ] = {
            "passed": False,
            "action": ml_action,
            "reason": (
                "deterministic_constraint_rejection"
            ),
            "rejection_reasons":
                rejection_reasons,
        }

        result[
            "hybrid_latency_ms"
        ] = (
            perf_counter()
            - started
        ) * 1000

        return result

    # --------------------------------------------------------
    # STEP 6 — final advisory
    # --------------------------------------------------------

    result.update(
        recommendation=ml_action,
        status="advisory",
        reason=(
            f"{ml_action} selected by the tuned "
            "GRIDGHOST XGBoost policy "
            f"(model probability "
            f"{ml_result.top_probability:.3f}, "
            f"top-two margin "
            f"{ml_result.probability_margin:.3f}) "
            "and accepted by the deterministic "
            "scenario-planner constraints. "
            "Engineer approval required for execution."
        ),
    )

    result[
        "shield"
    ] = {
        "passed": True,

        "validated_action":
            ml_action,

        "deterministic_preferred_action":
            deterministic.get(
                "recommendation"
            ),

        "validated_candidate":
            matching_candidate,

        "authority": (
            "deterministic feasibility constraints"
        ),
    }

    result[
        "hybrid_latency_ms"
    ] = (
        perf_counter()
        - started
    ) * 1000

    return result


def ml_health() -> dict:

    model_path = resolve_model_path()

    payload = {
        "model_file":
            model_path.name,

        "model_exists":
            model_path.exists(),

        "feature_count":
            9,

        "uncertainty_gate": {
            "top_probability":
                TOP_PROBABILITY_THRESHOLD,

            "top_two_margin":
                TOP_TWO_MARGIN_THRESHOLD,
        },
    }

    if not model_path.exists():

        payload[
            "status"
        ] = "missing"

        return payload

    try:

        get_ml_policy()

        payload[
            "status"
        ] = "ready"

    except Exception as exc:

        payload[
            "status"
        ] = "error"

        payload[
            "error"
        ] = (
            f"{type(exc).__name__}: "
            f"{exc}"
        )

    return payload