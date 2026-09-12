LABELS = ["ATTACK", "DEFEND", "HOLD", "CONSERVE"]
LABEL_TO_ID = {name: i for i, name in enumerate(LABELS)}
ID_TO_LABEL = {i: name for name, i in LABEL_TO_ID.items()}

FEATURES = [
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
