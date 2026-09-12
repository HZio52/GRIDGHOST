"""All numerical units are explicit.

Defaults are demonstration policy, not FIA rules.
"""

from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)


class StrictModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        allow_inf_nan=False,
    )


class Policy(StrictModel):

    version: Literal["demo-v1"] = "demo-v1"

    horizon_s: float = Field(
        8,
        ge=1,
        le=20,
    )

    step_s: float = Field(
        0.5,
        ge=0.1,
        le=1,
    )

    capacity_mj: float = Field(
        4,
        gt=0,
        le=20,
    )

    reserve_mj: float = Field(
        0.6,
        ge=0,
        le=20,
    )

    max_deploy_kw: float = Field(
        120,
        ge=0,
        le=500,
    )

    max_recovery_kw: float = Field(
        50,
        ge=0,
        le=500,
    )

    energy_price_s_per_mj: float = Field(
        0.15,
        ge=0,
        le=20,
    )

    uncertainty_penalty: float = Field(
        0.5,
        ge=0,
        le=10,
    )

    max_data_age_s: float = Field(
        5,
        gt=0,
        le=60,
    )

    min_quality: float = Field(
        0.7,
        ge=0,
        le=1,
    )

    speed_gain_mps_per_kw: float = Field(
        0.04,
        ge=0,
        le=0.2,
    )

    pace_sigma_mps: float = Field(
        3,
        ge=0.5,
        le=20,
    )

    min_score_margin_s: float = Field(
        0.005,
        ge=0,
        le=1,
    )

    @model_validator(mode="after")
    def check_reserve(self):

        if self.reserve_mj >= self.capacity_mj:
            raise ValueError(
                "reserve_mj must be below capacity_mj"
            )

        return self


class State(StrictModel):

    timestamp_s: float = Field(
        ge=0,
        description=(
            "Monotonic seconds on this replay/run clock"
        ),
    )

    own_speed_kph: float = Field(
        ge=0,
        le=450,
    )

    rival_speed_kph: float = Field(
        ge=0,
        le=450,
    )

    gap_s: float = Field(
        ge=-30,
        le=30,
        description=(
            "Positive: rival ahead. "
            "Negative: rival behind"
        ),
    )

    # Added for the 9-feature GRIDGHOST ML policy.
    #
    # Existing callers remain compatible because the default
    # is zero. Real adapters should calculate and provide this
    # from synchronized gap observations whenever possible.
    gap_rate_s_per_s: float = Field(
        0.0,
        ge=-20,
        le=20,
        description=(
            "Rate of change of signed gap in seconds "
            "per second. Use derived telemetry when "
            "available; zero is only a compatibility "
            "fallback."
        ),
    )

    own_energy_mj: float = Field(
        ge=0,
        le=20,
    )

    energy_uncertainty_mj: float = Field(
        0.1,
        ge=0,
        le=5,
    )

    recovery_kw: float = Field(
        10,
        ge=0,
        le=500,
    )

    recovery_uncertainty_kw: float = Field(
        5,
        ge=0,
        le=500,
    )

    data_age_s: float = Field(
        0,
        ge=0,
        le=86400,
    )

    quality: float = Field(
        1,
        ge=0,
        le=1,
        description=(
            "Caller-assigned data quality, "
            "not calibrated confidence"
        ),
    )

    track_status: Literal[
        "GREEN",
        "YELLOW",
        "RED",
        "SC",
        "VSC",
        "UNKNOWN",
    ] = "UNKNOWN"

    speed_source: Literal[
        "synthetic",
        "openf1",
        "user_supplied",
    ] = "synthetic"

    gap_source: Literal[
        "synthetic",
        "openf1_adjacent_interval",
        "user_supplied",
    ] = "synthetic"

    energy_source: Literal[
        "simulated",
        "user_supplied",
        "measured",
    ] = "simulated"

    status_source: Literal[
        "synthetic",
        "user_supplied",
    ] = "synthetic"


class Belief(StrictModel):

    slow: float = Field(
        1 / 3,
        ge=0,
        le=1,
    )

    neutral: float = Field(
        1 / 3,
        ge=0,
        le=1,
    )

    fast: float = Field(
        1 / 3,
        ge=0,
        le=1,
    )

    updates: int = Field(
        0,
        ge=0,
    )

    @model_validator(mode="after")
    def normalized(self):

        total = (
            self.slow
            + self.neutral
            + self.fast
        )

        if abs(total - 1) > 1e-6:
            raise ValueError(
                "Belief probabilities must sum to one"
            )

        return self


class DecisionRequest(StrictModel):

    state: State

    policy: Policy = Field(
        default_factory=Policy
    )

    belief: Belief = Field(
        default_factory=Belief
    )


class RunCreate(StrictModel):

    name: str = Field(
        "close_fight_s07",
        min_length=1,
        max_length=100,
    )

    policy: Policy = Field(
        default_factory=Policy
    )


class ReplayRequest(StrictModel):

    states: list[State] = Field(
        min_length=1,
        max_length=2000,
    )

    policy: Policy = Field(
        default_factory=Policy
    )


class Candidate(StrictModel):

    action: str

    deploy_kw: float

    expected_energy_mj: float

    worst_case_energy_mj: float

    expected_gap_s: float

    gap_std_s: float

    progress_s: float

    score_s: float

    valid: bool

    rejection_reasons: list[str]


class Decision(StrictModel):

    recommendation: str

    status: Literal[
        "advisory",
        "abstain",
    ]

    reason: str

    candidates: list[Candidate]

    belief: Belief

    score_margin_s: float

    engine_latency_ms: float

    model_version: str = "demo-v1"

    constraints_status: str = (
        "model_policy; FIA rules not verified"
    )

    uncertainty_label: str = (
        "scenario spread; "
        "not calibrated success probability"
    )

    provenance: dict[str, str]