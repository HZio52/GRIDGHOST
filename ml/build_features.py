from __future__ import annotations

import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd


def _to_dt(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"], utc=True, errors="raise")
    return df.sort_values("date")


def build_features(input_json: Path) -> pd.DataFrame:
    payload = json.loads(input_json.read_text(encoding="utf-8"))
    own_no = int(payload["own_driver_number"])
    rival_no = int(payload["rival_driver_number"])

    car = _to_dt(pd.DataFrame(payload["car_data"]))
    own = car[car.driver_number == own_no].copy()
    rival = car[car.driver_number == rival_no].copy()
    if own.empty or rival.empty:
        raise ValueError("Both own_driver_number and rival_driver_number need car_data records")

    own = own.rename(columns={
        "speed": "own_speed_kph", "throttle": "own_throttle", "brake": "own_brake",
        "rpm": "own_rpm", "n_gear": "own_gear", "drs": "own_drs",
    })
    rival = rival.rename(columns={
        "speed": "rival_speed_kph", "throttle": "rival_throttle", "brake": "rival_brake",
        "rpm": "rival_rpm", "n_gear": "rival_gear", "drs": "rival_drs",
    })

    own_cols = ["date","own_speed_kph","own_throttle","own_brake","own_rpm","own_gear","own_drs"]
    rival_cols = ["date","rival_speed_kph","rival_throttle","rival_brake","rival_rpm","rival_gear","rival_drs"]
    merged = pd.merge_asof(
        own[own_cols].sort_values("date"),
        rival[rival_cols].sort_values("date"),
        on="date", direction="nearest", tolerance=pd.Timedelta("600ms")
    )

    intervals = payload.get("intervals") or []
    if intervals:
        iv = _to_dt(pd.DataFrame(intervals))
        iv = iv[iv.driver_number == own_no][["date", "interval"]].rename(columns={"interval":"gap_s"})
        merged = pd.merge_asof(
            merged.sort_values("date"), iv.sort_values("date"),
            on="date", direction="backward", tolerance=pd.Timedelta("10s")
        )
    else:
        merged["gap_s"] = np.nan

    merged = merged.dropna(subset=["rival_speed_kph"]).reset_index(drop=True)
    t0 = merged["date"].iloc[0]
    merged["timestamp_s"] = (merged["date"] - t0).dt.total_seconds()
    dt = merged["timestamp_s"].diff().replace(0, np.nan)

    merged["speed_delta_kph"] = merged["own_speed_kph"] - merged["rival_speed_kph"]
    merged["throttle_delta"] = merged["own_throttle"] - merged["rival_throttle"]
    merged["rpm_delta"] = merged["own_rpm"] - merged["rival_rpm"]
    merged["own_accel_kph_s"] = merged["own_speed_kph"].diff() / dt
    merged["rival_accel_kph_s"] = merged["rival_speed_kph"].diff() / dt
    merged["gap_rate_s_per_s"] = merged["gap_s"].diff() / dt
    merged["speed_delta_roll_mean"] = merged["speed_delta_kph"].rolling(5, min_periods=1).mean()
    merged["speed_delta_roll_std"] = merged["speed_delta_kph"].rolling(5, min_periods=2).std()

    # Values unavailable in public OpenF1 are deliberately left for the bootstrap generator.
    merged["own_energy_mj"] = np.nan
    merged["energy_uncertainty_mj"] = np.nan
    merged["recovery_kw"] = np.nan
    merged["recovery_uncertainty_kw"] = np.nan
    merged["source_group"] = np.arange(len(merged), dtype=int)
    merged["session_key"] = payload.get("session_key")
    merged["own_driver_number"] = own_no
    merged["rival_driver_number"] = rival_no

    numeric = merged.select_dtypes(include=[np.number]).columns
    merged[numeric] = merged[numeric].replace([np.inf, -np.inf], np.nan)
    # Only temporal derivative fields are safe to fill with 0 at the beginning.
    for c in ["own_accel_kph_s", "rival_accel_kph_s", "gap_rate_s_per_s", "speed_delta_roll_std"]:
        merged[c] = merged[c].fillna(0.0)
    return merged


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--input", required=True, type=Path)
    p.add_argument("--output", default=Path("data/ml/openf1_features.csv"), type=Path)
    args = p.parse_args()
    df = build_features(args.input)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(args.output, index=False)
    print(f"Wrote {len(df):,} aligned feature rows -> {args.output}")
    print(df[["timestamp_s","own_speed_kph","rival_speed_kph","gap_s","speed_delta_kph"]].head(10).to_string(index=False))

if __name__ == "__main__":
    main()
