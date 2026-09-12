from ml import config

# GRIDGHOST ablation study:
# Smallest race-state + energy feature set.

CORE_FEATURES = [
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

# Patch only this Python process.
# The real ml/config.py file is NOT changed.
config.FEATURES = CORE_FEATURES

# Import only after replacing FEATURES so train_xgb uses
# the core feature set while retaining the same training logic.
from ml.train_xgb import main


if __name__ == "__main__":
    main()
