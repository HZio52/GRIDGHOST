from __future__ import annotations
import argparse, json
from pathlib import Path
import pandas as pd
from xgboost import XGBClassifier
from ml.config import FEATURES, LABELS


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", type=Path, default=Path("models/gridghost_xgb_tuned.json"))
    ap.add_argument("--features", type=Path, default=Path("data/ml/openf1_features.csv"))
    ap.add_argument("--row", type=int, default=0)
    ap.add_argument("--energy", type=float, default=2.4)
    ap.add_argument("--recovery", type=float, default=10.0)
    args = ap.parse_args()
    df = pd.read_csv(args.features)
    row = df.iloc[args.row].copy()
    row["own_energy_mj"] = args.energy
    row["energy_uncertainty_mj"] = 0.1
    row["recovery_kw"] = args.recovery
    row["recovery_uncertainty_kw"] = 5.0
    X = pd.DataFrame([{c: float(row[c]) for c in FEATURES}])
    model = XGBClassifier()
    model.load_model(args.model)
    probs = model.predict_proba(X)[0]
    result = {LABELS[i]: float(probs[i]) for i in range(len(LABELS))}
    print(json.dumps({"recommendation": max(result, key=result.get), "probabilities": result}, indent=2))

if __name__ == "__main__":
    main()
