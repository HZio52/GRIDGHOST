# Data and mathematical model - implementation reference

## Actual inputs versus available inputs

Implemented public importer: own/rival speed from car_data; positions and numeric adjacent intervals. Other OpenF1 fields (throttle, brake, RPM, gear, DRS, weather, lap times) may be available but are **not used by this model**. No tyre, fuel, aerodynamic, braking-physics or lap-time model is implemented.

Own energy, its uncertainty, recovery power and its uncertainty are supplied scenario inputs. The bundled data is synthetic. OpenF1 imports retain simulated energy. Rival battery is never inferred. Track status is supplied explicitly; the importer defaults UNKNOWN and requires an explicit demo override for GREEN. Source labels are declarations, not independent verification.

## Exact equations

All defaults below are author-selected demo policy values. No current FIA rule document was validated.

1. Observed relative speed x = (rival_speed_kph - own_speed_kph) / 3.6, in m/s.
2. Three pace hypotheses have means mu = [-2, 0, 2] m/s relative to own current speed.
3. Before updating, q_j = 0.9*p_j + 0.1/3. This forgets some old evidence.
4. Likelihood L_j = exp(-0.5*((x-mu_j)/sigma)^2), with sigma = 3 m/s.
5. Posterior p'_j = q_j*L_j / sum(q_k*L_k). Implementation uses logs for stability. Fixed means/sigma are not trained; posterior weights change. Observations can be confounded by corners, traffic and driver actions; these are pace hypotheses, not rival intent labels or battery states.
6. Action power: ATTACK 120, DEFEND 80, HOLD 40, CONSERVE 0 kW.
7. Rival response multipliers: ATTACK 0.8, DEFEND 0.4, HOLD/CONSERVE 0. Multiply these by [0, 1, 3] across slow/neutral/fast scenarios.
8. Own predicted speed = max(0, own_current_mps + 0.04*(action_power - 40)). This is a crude steady response assumption, not a vehicle acceleration model.
9. Rival scenario speed = max(0, own_current_mps + mu_j + action_response_j). Observed relative speed already influenced the posterior; adding it again would double-count it.
10. Initial signed distance = gap_s * max(own_current_mps, 1). This approximate conversion is not a geometric track distance. Positive gap means rival ahead.
11. For each step: distance_j += (rival_speed_j - own_speed)*dt. The default horizon is 8 s, step 0.5 s. Divide final distance by reference speed to get the future gap proxy.
12. Expected energy: E_next = min(capacity, E + (recovery - deployment)*dt/1000), in MJ. Recovery is capped at max_recovery_kw.
13. Conservative energy starts at max(0, E - energy_uncertainty). Recovery becomes min(max(0, recovery - recovery_uncertainty), recovery_cap). Track the minimum energy across the whole horizon, including the initial state. Negative forecast balances indicate an infeasible energy demand, not an actual negative battery charge.
14. Mean gap = sum(p'_j*gap_j). Gap spread = sqrt(sum(p'_j*(gap_j - mean_gap)^2)). This covers only the three assumed pace scenarios, not all real-world uncertainty.
15. Progress = current_gap - mean_gap. It measures approximate local relative progress, not completed overtaking or lap-time gain.
16. Score (seconds-equivalent) = progress - 0.15*(current_energy - expected_energy) - 0.5*gap_spread. The 0.15 is seconds/MJ. Negative consumption rewards energy recovery.
17. Reject action if configured deployment cap is exceeded or minimum conservative energy < reserve. ATTACK requires 0 < gap <= 1.5 s; DEFEND requires -1.5 <= gap < 0. These windows are demo eligibility rules.
18. Pick highest-scoring valid action. If two best scores differ by <0.005 s and HOLD is valid, use HOLD to avoid unnecessary switching. No valid action -> NO_RECOMMENDATION. Bad freshness, low quality, non-GREEN status, unsupported low speed, or energy over capacity -> abstain without updating belief.

The 0.6 MJ reserve, 4 MJ capacity, power levels, windows, speed coefficient, priors and score weights are demonstrator settings. Change and validate them with evidence before applying to any actual car, circuit or regulation year.

## Latency boundaries

engine_latency_ms covers calculation in decide(), not JSON validation or SQLite writes. X-Processing-Time-Ms covers HTTP middleware through creation of the response; it does not include remote source delay or full client network time. scripts/benchmark.py reports standalone engine and in-process TestClient distributions, with and without SQLite. These are not live F1 timing measurements.

## Evidence needed next

Calibrate power-to-speed response against controlled simulator runs with known inputs. Compare predictions on held-out scenarios using gap MAE/RMSE; validate energy against known simulator energy; measure uncertainty coverage; compare decisions against always-HOLD and a simple reserve rule under the SAME closed-loop simulator seeds. Report reserve violations, energy, progress, and action-switch counts. Public replay alone cannot establish causal gains because the alternative action was never executed. The source's collection cadence and delivery age must also be measured on the actual live setup.

## Primary references (checked 12 September 2026)

- OpenF1 API fields and data access: https://openf1.org/docs/
- OpenF1 source service context: https://openf1.org/
- HTTPX requests and JSON: https://www.python-httpx.org/quickstart/
- NumPy arrays and numerical operations: https://numpy.org/doc/stable/user/whatisnumpy.html
- FastAPI API development: https://fastapi.tiangolo.com/tutorial/

These references document interfaces and libraries; they do not validate our custom racing response coefficients. The custom equations above are fully specified implementation assumptions.
