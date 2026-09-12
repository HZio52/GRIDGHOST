# V2 model and boundaries

The v1 Bayesian filter and basic gate logic remain in app/engine.py. The new app/planner.py adds Planning, PlanRequest, CompareRequest, plan(), and compare(). All software inputs are validated using Pydantic.

## Search

Each first action (ATTACK, DEFEND, HOLD, CONSERVE) gets its own bounded beam. Default: 6 stages of 4 seconds, up to 8 stages of 5 seconds through the API. Each node tracks three signed gap scenarios, expected energy, conservative energy, cumulative deployment, action sequence and trace.

Keep up to 12 nodes per stage: the 11 highest-scoring nodes plus the most energy-rich node (or the next score-ranked node if already retained). Keeping the energy-rich branch avoids pruning a potentially feasible conservation continuation solely because of its short-term score. This is still approximate, not a proof of the global optimum or of infeasibility when no plan is found.

Before search, the v1 gates check fresh/quality/track/moving-car/capacity input. Invalid observations do not update the belief. Valid observations update slow/neutral/fast weights using the v1 Gaussian likelihood and 10% forgetting mix.

## Per-stage dynamics

Power levels: ATTACK 120, DEFEND 80, HOLD 40, CONSERVE 0 kW. Rival response multipliers: .8, .4, 0, 0 respectively. Relative pace hypotheses: [-2, 0, +2] m/s. Own delta = .04*(power-40) m/s. Rival extra response = action multiplier * [0, 1, 3].

Relative speed = pace hypothesis + rival response - own delta.
Gap_next = gap + relative_speed * stage_s / max(own_speed_kph/3.6, 1).

E_next = min(capacity, E + (min(recovery, recovery_cap)-power)*stage_s/1000).
Conservative energy starts at max(0, E-energy_uncertainty) and uses recovery reduced by its uncertainty, clipped to [0,recovery_cap].

These are local linear response assumptions. They do not model acceleration, braking, tyres, track geometry, aerodynamics or completed overtakes. Instantaneous pace observations are confounded by circuit position and other drivers. “Fast” is a weighted scenario, not inferred driver intent or battery state.

## Constraints

- Power <= configured deployment cap.
- Energy deployment accumulated over THIS plan <= deployment_budget_mj (default 2 MJ).
- Minimum conservative energy >= reserve at each step, including the initial state.
- Final conservative energy >= reserve + terminal_buffer_mj (default .6 + .25 MJ).
- ATTACK: weighted gap strictly positive and <=1.5 s, and current stage's supplied attack window is true.
- DEFEND: weighted gap negative and >=-1.5 s.

The deployment budget resets with each planning request; it is not a race-lap energy counter and must not be presented as one. Stage eligibility uses mean gap, not a guarantee under every rival scenario. A plan is not an instruction to execute autonomously.

## Scoring

score_s = initial_gap - weighted_final_gap
          - energy_price_s_per_mj*(initial_energy - final_expected_energy)
          - uncertainty_penalty*weighted_gap_standard_deviation
          - switch_cost_s*number_of_action_switches.

Default weights: .15 s/MJ, .5, .015 s/switch. Select the highest score among retained complete valid plans. Return the first action and the full hypothetical sequence. NO_RECOMMENDATION means a gate failed or no retained complete feasible plan was found. The new planner does not use v1's near-tie HOLD preference.

The shaded uncertainty in v1 documentation is a three-scenario spread, not a calibrated probability. V2 charts show expected and conservative energy; no interval coverage or overtake-success probability is claimed.

## Simulation comparison

Three controllers receive identical seeded cumulative Gaussian rival drift. The simulator uses 90% of the forecast's own power-response coefficient and a fixed action-specific rival response, so it is not identical to the planning model. It remains a closely related synthetic plant, not independent validation. Energy uses the same simplified conservation equation.

The planner replans each tick, the HOLD baseline conserves when its next conservative reserve check fails, and the greedy planner uses a one-stage horizon with zero terminal buffer. A planner abstention causes a clearly labelled CONSERVE simulator fallback. Metrics are final energy, signed gap proxy, observed reserve violations, and action switches. No controller is guaranteed to win every case.

Limit: supplied future attack-window arrays are relative to each request and repeat unchanged in the current comparison harness; they are not a continuously advancing circuit schedule. Use the all-open default for baseline comparisons. Closed track-status or stale/low-quality inputs are rejected by the comparison API.

## Needed for stronger claims

Calibrated vehicle response data, independent simulator validation, held-out outcomes, measured energy, real track alignment, explicit verified FIA clauses, operating deadlines, and proper deployed user access controls. No neural model is trained in this release.
