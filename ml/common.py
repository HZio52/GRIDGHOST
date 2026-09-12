from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.model_selection import GroupShuffleSplit
from sklearn.utils.class_weight import compute_sample_weight
from ml.config import FEATURES, LABEL_TO_ID


def load_xy(path: Path):
    df = pd.read_csv(path)
    missing = [c for c in FEATURES + ["action", "source_group"] if c not in df.columns]
    if missing:
        raise ValueError(f"Missing columns: {missing}")
    df = df.dropna(subset=FEATURES + ["action", "source_group"]).reset_index(drop=True)
    X = df[FEATURES].astype(float)
    y = df.action.map(LABEL_TO_ID)
    if y.isna().any():
        raise ValueError("Unknown action label present")
    return df, X, y.astype(int), df.source_group.astype(str)


def group_split(df, X, y, groups, seed=42):
    gss = GroupShuffleSplit(n_splits=1, test_size=0.20, random_state=seed)
    trainval_idx, test_idx = next(gss.split(X, y, groups))
    X_tv, y_tv, g_tv = X.iloc[trainval_idx], y.iloc[trainval_idx], groups.iloc[trainval_idx]
    gss2 = GroupShuffleSplit(n_splits=1, test_size=0.20, random_state=seed+1)
    tr_rel, va_rel = next(gss2.split(X_tv, y_tv, g_tv))
    train_idx = trainval_idx[tr_rel]
    val_idx = trainval_idx[va_rel]
    return train_idx, val_idx, test_idx


def balanced_weights(y):
    return compute_sample_weight(class_weight="balanced", y=y)


def save_json(obj, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2), encoding="utf-8")
