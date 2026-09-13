"""Historical OpenF1 data adapter for GRIDGHOST.

Important design rules:

- Never infer battery/energy from OpenF1.
- Never infer arbitrary pairwise gaps.
- Only use observations available at or before the current frame.
- Only accept interval data when the two selected drivers are adjacent.
- Derive gap rate causally from previously accepted gap observations.
"""

from __future__ import annotations

import bisect
import math
import time

from datetime import datetime

import httpx

from .schemas import State


def _car_num(sample, key, default=0.0, lo=0.0, hi=100.0):
    if not sample:
        return default
    raw = sample.get(key)
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(value):
        return default
    return min(hi, max(lo, value))


BASE_URL = "https://api.openf1.org/v1"

ENDPOINTS = {
    "sessions",
    "car_data",
    "intervals",
    "position",
    "race_control",
    "laps",
    "weather",
    "stints",
}


# ============================================================
# TIME HELPERS
# ============================================================

def epoch(value: str) -> float:
    """
    Convert an ISO-8601 timestamp into Unix seconds.
    """

    result = datetime.fromisoformat(
        value.replace(
            "Z",
            "+00:00",
        )
    )

    if result.tzinfo is None:
        raise ValueError(
            "Use timezone-aware ISO timestamps"
        )

    return result.timestamp()


# ============================================================
# OPENF1 HTTP CLIENT
# ============================================================

class OpenF1Client:

    def __init__(
        self,
        transport=None,
    ):
        self.transport = transport
        self.last_request = 0.0

    def fetch(
        self,
        endpoint,
        params,
    ):

        if endpoint not in ENDPOINTS:
            raise ValueError(
                "Endpoint not allowed"
            )

        with httpx.Client(
            base_url=BASE_URL + "/",
            timeout=30,
            transport=self.transport,
        ) as client:

            for attempt in range(3):

                # Conservative pacing:
                # fewer than ~30 calls/min including retries.
                time.sleep(
                    max(
                        0.0,
                        2.1
                        - (
                            time.monotonic()
                            - self.last_request
                        ),
                    )
                )

                self.last_request = (
                    time.monotonic()
                )

                response = client.get(
                    endpoint,
                    params=params,
                )

                if (
                    response.status_code
                    in (
                        429,
                        500,
                        502,
                        503,
                        504,
                    )
                    and attempt < 2
                ):

                    try:
                        delay = float(
                            response.headers.get(
                                "Retry-After",
                                2 ** attempt,
                            )
                        )

                    except ValueError:
                        delay = (
                            2 ** attempt
                        )

                    time.sleep(
                        min(
                            30,
                            max(
                                0,
                                delay,
                            ),
                        )
                    )

                    continue

                response.raise_for_status()

                data = response.json()

                if (
                    not isinstance(
                        data,
                        list,
                    )
                    or any(
                        not isinstance(
                            row,
                            dict,
                        )
                        for row in data
                    )
                ):
                    raise ValueError(
                        "Expected a JSON array "
                        "of objects"
                    )

                if len(data) > 50000:
                    raise ValueError(
                        "Too many records; "
                        "reduce requested time window"
                    )

                return data

        raise RuntimeError(
            "Request failed"
        )


# ============================================================
# CAUSAL TIME SERIES
# ============================================================

class Series:

    def __init__(
        self,
        rows,
    ):

        self.rows = sorted(
            rows,
            key=lambda row: epoch(
                row["date"]
            ),
        )

        self.times = [
            epoch(
                row["date"]
            )
            for row in self.rows
        ]

    def before(
        self,
        timestamp,
    ):
        """
        Return the most recent observation at or before
        timestamp.

        This intentionally never uses future information.
        """

        index = (
            bisect.bisect_right(
                self.times,
                timestamp,
            )
            - 1
        )

        if index < 0:
            return None

        return (
            self.rows[index],
            timestamp
            - self.times[index],
        )


# ============================================================
# GAP RATE
# ============================================================

def derive_gap_rate(
    current_gap_s: float,
    current_timestamp_s: float,
    previous_gap_s: float | None,
    previous_timestamp_s: float | None,
) -> float:
    """
    Calculate signed gap change causally.

    gap_rate_s_per_s > 0:
        signed gap is increasing.

    gap_rate_s_per_s < 0:
        signed gap is decreasing.

    The first accepted observation has no previous gap,
    therefore its rate is 0.0.

    We clip extreme values to the range used by the current
    GRIDGHOST bootstrap data pipeline. This protects the ML
    model from pathological interval jumps.
    """

    if (
        previous_gap_s is None
        or previous_timestamp_s is None
    ):
        return 0.0

    dt = (
        current_timestamp_s
        - previous_timestamp_s
    )

    if dt <= 1e-9:
        return 0.0

    raw_rate = (
        current_gap_s
        - previous_gap_s
    ) / dt

    if not math.isfinite(
        raw_rate
    ):
        return 0.0

    return float(
        max(
            -1.5,
            min(
                1.5,
                raw_rate,
            ),
        )
    )


# ============================================================
# NORMALIZER / RUNTIME DATA ADAPTER
# ============================================================

def normalize(
    raw,
    own,
    rival,
    energy_mj,
    assume_green=False,
):
    """
    Convert raw OpenF1 observations into GRIDGHOST State rows.

    Only previous/current observations are joined.

    Pairwise gap handling:
    - selected drivers must be adjacent;
    - the interval belongs to the driver behind;
    - signed gap is positive when rival is ahead;
    - signed gap is negative when rival is behind.

    Energy:
    OpenF1 does not provide GRIDGHOST battery state.
    energy_mj is therefore a caller-selected simulated snapshot
    unless replaced later by approved measured/team telemetry.
    """

    if own == rival:
        raise ValueError(
            "Choose two distinct drivers"
        )

    required_streams = (
        "car_data",
        "position",
        "intervals",
    )

    missing_streams = [
        name
        for name in required_streams
        if name not in raw
    ]

    if missing_streams:
        raise ValueError(
            "Raw OpenF1 payload is missing: "
            f"{missing_streams}"
        )

    streams = {}

    for kind in required_streams:

        rows = raw.get(
            kind,
            [],
        )

        for driver in (
            own,
            rival,
        ):

            streams[
                kind,
                driver,
            ] = Series(
                [
                    row
                    for row in rows
                    if (
                        row.get(
                            "driver_number"
                        )
                        == driver
                    )
                ]
            )

    own_rows = streams[
        "car_data",
        own,
    ].rows

    states = []

    skipped = 0

    last_car_sample_t = (
        -math.inf
    )

    # Previous ACCEPTED pair-gap observation.
    #
    # This is deliberately separate from raw interval updates:
    # only a gap that has passed all adjacency/data checks may
    # contribute to the next ML gap-rate feature.
    previous_gap_s = None

    previous_gap_timestamp_s = None

    speed_deltas = []

    for row in own_rows:

        date = row.get(
            "date"
        )

        if not date:
            skipped += 1
            continue

        t = epoch(
            date
        )

        # OpenF1 car telemetry can arrive several times/second.
        # Do not repeatedly treat near-identical samples as
        # independent strategic observations.
        if (
            t
            - last_car_sample_t
            < 1.0
        ):
            continue

        last_car_sample_t = t

        # ----------------------------------------------------
        # Retrieve latest rival speed and positions.
        # ----------------------------------------------------

        rival_car = streams[
            "car_data",
            rival,
        ].before(t)

        own_position = streams[
            "position",
            own,
        ].before(t)

        rival_position = streams[
            "position",
            rival,
        ].before(t)

        if not all(
            (
                rival_car,
                own_position,
                rival_position,
            )
        ):
            skipped += 1
            continue

        own_position_value = (
            own_position[0].get(
                "position"
            )
        )

        rival_position_value = (
            rival_position[0].get(
                "position"
            )
        )

        if (
            not isinstance(
                own_position_value,
                int,
            )
            or not isinstance(
                rival_position_value,
                int,
            )
        ):
            skipped += 1
            continue

        position_delta = (
            own_position_value
            - rival_position_value
        )

        # Only adjacent cars have a meaningful direct interval.
        if abs(
            position_delta
        ) != 1:
            skipped += 1
            continue

        # If own position number is larger,
        # own car is behind.
        behind_driver = (
            own
            if position_delta == 1
            else rival
        )

        interval = streams[
            "intervals",
            behind_driver,
        ].before(t)

        if interval is None:
            skipped += 1
            continue

        interval_value = (
            interval[0].get(
                "interval"
            )
        )

        if (
            isinstance(
                interval_value,
                bool,
            )
            or not isinstance(
                interval_value,
                (
                    float,
                    int,
                ),
            )
            or not math.isfinite(
                interval_value
            )
            or not (
                0
                <= interval_value
                <= 30
            )
        ):
            skipped += 1
            continue

        own_speed = row.get(
            "speed"
        )

        rival_speed = (
            rival_car[0].get(
                "speed"
            )
        )

        if (
            own_speed is None
            or rival_speed is None
        ):
            skipped += 1
            continue

        # ----------------------------------------------------
        # Signed pair gap
        # ----------------------------------------------------

        signed_gap_s = (
            float(
                interval_value
            )
            if position_delta == 1
            else -float(
                interval_value
            )
        )

        # ----------------------------------------------------
        # Causal gap rate
        # ----------------------------------------------------

        gap_rate_s_per_s = (
            derive_gap_rate(
                current_gap_s=
                    signed_gap_s,

                current_timestamp_s=
                    t,

                previous_gap_s=
                    previous_gap_s,

                previous_timestamp_s=
                    previous_gap_timestamp_s,
            )
        )

        # ----------------------------------------------------
        # Observation freshness
        # ----------------------------------------------------

        age = max(
            rival_car[1],
            own_position[1],
            rival_position[1],
            interval[1],
        )

        # ----------------------------------------------------
        # Pedals, DRS, rolling speed delta
        # ----------------------------------------------------

        rival_sample = rival_car[0]
        delta_kph = float(own_speed) - float(rival_speed)
        speed_deltas.append(delta_kph)
        if len(speed_deltas) > 5:
            speed_deltas.pop(0)
        roll_mean = sum(speed_deltas) / len(speed_deltas)
        if len(speed_deltas) >= 2:
            roll_var = sum(
                (item - roll_mean) ** 2
                for item in speed_deltas
            ) / (len(speed_deltas) - 1)
            roll_std = math.sqrt(max(0.0, roll_var))
        else:
            roll_std = 0.0

        # ----------------------------------------------------
        # Build validated GRIDGHOST state
        # ----------------------------------------------------

        state = State(
            timestamp_s=t,

            own_speed_kph=
                own_speed,

            rival_speed_kph=
                rival_speed,

            gap_s=
                signed_gap_s,

            gap_rate_s_per_s=
                gap_rate_s_per_s,

            own_throttle=
                _car_num(row, "throttle"),

            rival_throttle=
                _car_num(rival_sample, "throttle"),

            own_brake=
                _car_num(row, "brake"),

            rival_brake=
                _car_num(rival_sample, "brake"),

            own_drs=
                int(_car_num(row, "drs", 0, 0, 20)),

            rival_drs=
                int(_car_num(rival_sample, "drs", 0, 0, 20)),

            speed_delta_roll_mean=
                roll_mean,

            speed_delta_roll_std=
                roll_std,

            own_energy_mj=
                energy_mj,

            data_age_s=
                min(
                    age,
                    86400,
                ),

            track_status=(
                "GREEN"
                if assume_green
                else "UNKNOWN"
            ),

            speed_source=
                "openf1",

            gap_source=
                "openf1_adjacent_interval",

            energy_source=
                "simulated",

            status_source=
                "user_supplied",
        )

        states.append(
            state.model_dump()
        )

        # Update history only AFTER this frame has passed
        # all validation checks.
        previous_gap_s = (
            signed_gap_s
        )

        previous_gap_timestamp_s = (
            t
        )

    return {
        "states":
            states,

        "skipped_frames":
            skipped,

        "notes": [
            (
                "Energy is a fixed simulated snapshot "
                "at each frame."
            ),
            (
                "Track status is UNKNOWN unless "
                "explicitly assumed GREEN for a demo."
            ),
            (
                "Only adjacent-driver intervals are "
                "used; no arbitrary pair gap is inferred."
            ),
            (
                "gap_rate_s_per_s is derived only from "
                "previously accepted pair-gap observations."
            ),
            (
                "No future observations are joined."
            ),
            (
                "Historical observations do not change "
                "in response to recommendations."
            ),
        ],
    }