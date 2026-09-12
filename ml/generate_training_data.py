from __future__ import annotations

import argparse
from pathlib import Path
import sys
import numpy as np
import pandas as pd

# Run from the GRIDGHOST project root so app/ is importable.
from app.schemas import Belief, Policy, State
from app.planner import PlanRequest, Planning, plan
from ml.config import LABELS


def clamp(x, lo, hi):
    return float(np.clip(x, lo, hi))


def sample_gap(rng: np.random.Generator) -> float:
    bucket = rng.choice(["attack", "defend", "wide"], p=[0.37, 0.32, 0.31])
    if bucket == "attack":
        return float(rng.uniform(0.05, 1.5))
    if bucket == "defend":
        return float(rng.uniform(-1.5, -0.05))
    return float(rng.uniform(-3.0, 3.0))


def sample_energy(rng: np.random.Generator) -> float:
    bucket = rng.choice(["low", "mid", "high"], p=[0.25, 0.45, 0.30])
    if bucket == "low":
        return float(rng.uniform(0.68, 1.30))
    if bucket == "mid":
        return float(rng.uniform(1.30, 2.60))
    return float(rng.uniform(2.60, 4.0))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--features", type=Path, default=Path("data/ml/openf1_features.csv"))
    ap.add_argument("--output", type=Path, default=Path("data/ml/training.csv"))
    ap.add_argument("--rows", type=int, default=20000)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    base = pd.read_csv(args.features)
    if base.empty:
        raise SystemExit("Feature file is empty")
    rng = np.random.default_rng(args.seed)
    policy = Policy()
    planning = Planning()
    belief = Belief()
    rows = []
    counts = {x: 0 for x in LABELS}
    attempts = 0
    max_attempts = args.rows * 3

    while len(rows) < args.rows and attempts < max_attempts:
        attempts += 1
        src_i = int(rng.integers(0, len(base)))
        b = base.iloc[src_i]
        own_speed = clamp(float(b.own_speed_kph) + rng.normal(0, 12), 40, 350)
        base_delta = float(b.speed_delta_kph) if pd.notna(b.speed_delta_kph) else 0.0
        speed_delta = clamp(base_delta + rng.normal(0, 8), -60, 60)
        rival_speed = clamp(own_speed - speed_delta, 30, 350)
        gap = sample_gap(rng)
        energy = sample_energy(rng)
        energy_unc = float(rng.uniform(0.05, 0.25))
        recovery = float(rng.uniform(0, 45))
        recovery_unc = float(rng.uniform(0, min(15, recovery + 1e-6)))

        state = State(
            timestamp_s=float(attempts), own_speed_kph=own_speed, rival_speed_kph=rival_speed,
            gap_s=gap, own_energy_mj=energy, energy_uncertainty_mj=energy_unc,
            recovery_kw=recovery, recovery_uncertainty_kw=recovery_unc,
            data_age_s=0, quality=1, track_status="GREEN",
            speed_source="openf1", gap_source="openf1_adjacent_interval",
            energy_source="simulated", status_source="synthetic",
        )
        result = plan(PlanRequest(state=state, policy=policy, belief=belief, planning=planning))
        label = result["recommendation"]
        if label not in counts:
            continue

        # Perturb telemetry-only context. It is not used by the teacher, but lets the
        # training schema already match the future real-data pipeline.
        own_throttle = clamp(float(b.own_throttle) + rng.normal(0, 8), 0, 100)
        rival_throttle = clamp(float(b.rival_throttle) + rng.normal(0, 8), 0, 100)
        own_rpm = clamp(float(b.own_rpm) + rng.normal(0, 350), 1000, 16000)
        rival_rpm = clamp(float(b.rival_rpm) + rng.normal(0, 350), 1000, 16000)
        gap_rate = float(np.clip(float(b.gap_rate_s_per_s) + rng.normal(0, 0.06), -1.5, 1.5))
        own_acc = float(np.clip(float(b.own_accel_kph_s) + rng.normal(0, 5), -150, 150))
        rival_acc = float(np.clip(float(b.rival_accel_kph_s) + rng.normal(0, 5), -150, 150))
        roll_mean = float(np.clip(float(b.speed_delta_roll_mean) + rng.normal(0, 4), -60, 60))
        roll_std = max(0.0, float(b.speed_delta_roll_std) + float(rng.normal(0, 1)))

        rows.append({
            "own_speed_kph": own_speed, "rival_speed_kph": rival_speed,
            "speed_delta_kph": own_speed-rival_speed, "gap_s": gap,
            "gap_rate_s_per_s": gap_rate, "own_accel_kph_s": own_acc,
            "rival_accel_kph_s": rival_acc, "own_throttle": own_throttle,
            "rival_throttle": rival_throttle, "throttle_delta": own_throttle-rival_throttle,
            "own_brake": int(b.own_brake), "rival_brake": int(b.rival_brake),
            "own_rpm": own_rpm, "rival_rpm": rival_rpm, "rpm_delta": own_rpm-rival_rpm,
            "own_gear": int(b.own_gear), "rival_gear": int(b.rival_gear),
            "own_drs": int(b.own_drs), "rival_drs": int(b.rival_drs),
            "speed_delta_roll_mean": roll_mean, "speed_delta_roll_std": roll_std,
            "own_energy_mj": energy, "energy_uncertainty_mj": energy_unc,
            "recovery_kw": recovery, "recovery_uncertainty_kw": recovery_unc,
            "action": label, "source_group": src_i,
            "label_source": "gridghost_v2_teacher",
        })
        counts[label] += 1

    if len(rows) < args.rows:
        raise SystemExit(f"Only generated {len(rows)} usable rows after {attempts} attempts")
    out = pd.DataFrame(rows)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(args.output, index=False)
    print(f"Generated {len(out):,} labelled rows -> {args.output}")
    print(out.action.value_counts().to_string())
    print("IMPORTANT: these are teacher/planner labels, not real TGR Haas strategy labels.")

if __name__ == "__main__":
    main()
