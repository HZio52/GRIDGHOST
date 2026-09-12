"""Deterministic, short-horizon scenario planner with a discrete Bayesian pace filter.
This is an educational response model, not validated vehicle dynamics.
"""
from time import perf_counter
import numpy as np
from .schemas import Belief, Candidate, Decision, DecisionRequest, Policy, State

# Relative to HOLD. All values are author-selected demonstration assumptions.
ACTIONS = {'ATTACK': (120., 0.8), 'DEFEND': (80., 0.4),
           'HOLD': (40., 0.0), 'CONSERVE': (0., 0.0)}
PACE_OFFSETS = np.array([-2., 0., 2.])  # m/s slow, neutral, fast scenarios

def update_belief(prior: Belief, state: State, policy: Policy) -> Belief:
    # Forgetting prevents permanent certainty from correlated observations.
    p = np.array([prior.slow, prior.neutral, prior.fast]) * 0.9 + 0.1/3
    observed = (state.rival_speed_kph - state.own_speed_kph) / 3.6
    logp = np.log(p) - 0.5 * ((observed - PACE_OFFSETS) / policy.pace_sigma_mps)**2
    logp -= logp.max()
    weights = np.exp(logp)
    weights /= weights.sum()
    return Belief(slow=float(weights[0]), neutral=float(weights[1]),
                  fast=float(weights[2]), updates=prior.updates + 1)

def simulate(state: State, policy: Policy, belief: Belief, action: str) -> Candidate:
    deploy, rival_response = ACTIONS[action]
    weights = np.array([belief.slow, belief.neutral, belief.fast])
    own_v = state.own_speed_kph/3.6
    reference_v = max(own_v, 1.)
    distance = np.full(3, state.gap_s * reference_v)
    energy = state.own_energy_mj
    worst = max(0., energy - state.energy_uncertainty_mj)
    expected_recovery = min(state.recovery_kw, policy.max_recovery_kw)
    worst_recovery = min(max(0., state.recovery_kw - state.recovery_uncertainty_kw),
                         policy.max_recovery_kw)
    minimum_energy = worst
    elapsed = 0.
    while elapsed < policy.horizon_s - 1e-9:
        dt = min(policy.step_s, policy.horizon_s - elapsed)
        # 1 kW*s = 1 kJ = 0.001 MJ. Account for bounds after every substep.
        energy = min(policy.capacity_mj, energy + (expected_recovery - deploy)*dt/1000)
        worst = min(policy.capacity_mj, worst + (worst_recovery - deploy)*dt/1000)
        minimum_energy = min(minimum_energy, worst)
        # Pace scenarios are forecast from own speed, conditioned on observed relative speed.
        # Do not add observed rival delta again: that would double-count the evidence.
        own_future_v = max(0., own_v + policy.speed_gain_mps_per_kw*(deploy - 40))
        rival_future_v = np.maximum(0., own_v + PACE_OFFSETS + rival_response*np.array([0., 1., 3.]))
        distance += (rival_future_v - own_future_v) * dt
        elapsed += dt
    gaps = distance/reference_v
    mean_gap = float(weights @ gaps)
    std_gap = float(np.sqrt(weights @ ((gaps - mean_gap)**2)))
    progress = state.gap_s - mean_gap
    score = progress - policy.energy_price_s_per_mj*(state.own_energy_mj-energy) \
        - policy.uncertainty_penalty*std_gap
    reasons = []
    if deploy > policy.max_deploy_kw:
        reasons.append('deployment_power_limit')
    if minimum_energy < policy.reserve_mj - 1e-9:
        reasons.append('reserve_breach_in_worst_energy_case')
    if action == 'ATTACK' and not 0 < state.gap_s <= 1.5:
        reasons.append('attack_requires_rival_ahead_within_1.5s')
    if action == 'DEFEND' and not -1.5 <= state.gap_s < 0:
        reasons.append('defend_requires_rival_behind_within_1.5s')
    return Candidate(action=action, deploy_kw=deploy, expected_energy_mj=energy,
        worst_case_energy_mj=worst, expected_gap_s=mean_gap, gap_std_s=std_gap,
        progress_s=progress, score_s=score, valid=not reasons, rejection_reasons=reasons)

def decide(request: DecisionRequest) -> Decision:
    started = perf_counter()
    s, p, prior = request.state, request.policy, request.belief
    gates = []
    if s.own_energy_mj > p.capacity_mj: gates.append('energy exceeds configured capacity')
    if s.data_age_s > p.max_data_age_s: gates.append('stale data')
    if s.quality < p.min_quality: gates.append('low input quality')
    if s.track_status != 'GREEN': gates.append('track status is not confirmed GREEN')
    if s.own_speed_kph < 30: gates.append('outside supported moving-car regime')
    # Untrusted observations must not change belief or produce numerical candidate forecasts.
    belief = prior if gates else update_belief(prior, s, p)
    candidates = [] if gates else [simulate(s, p, belief, a) for a in ACTIONS]
    valid = sorted((c for c in candidates if c.valid), key=lambda c: c.score_s, reverse=True)
    action, status, margin = 'NO_RECOMMENDATION', 'abstain', 0.
    if gates:
        reason = '; '.join(gates) + '; request engineer review'
    elif not valid:
        reason = 'No action satisfies model-policy constraints; request engineer review'
    else:
        best = valid[0]
        margin = best.score_s - valid[1].score_s if len(valid) > 1 else 0.
        hold = next((c for c in valid if c.action == 'HOLD'), None)
        if len(valid) > 1 and margin < p.min_score_margin_s and hold:
            best = hold
        action, status = best.action, 'advisory'
        reason = (f'{action}: model score {best.score_s:.3f}s; '
                  f'worst-case energy {best.worst_case_energy_mj:.3f} MJ; '
                  f'reserve {p.reserve_mj:.3f} MJ. Engineer approval required for execution.')
    return Decision(recommendation=action, status=status, reason=reason,
        candidates=candidates, belief=belief, score_margin_s=margin,
        engine_latency_ms=(perf_counter()-started)*1000,
        provenance={'speed': s.speed_source, 'gap': s.gap_source,
                    'energy': s.energy_source, 'track_status': s.status_source,
                    'response_coefficients': 'unvalidated demonstration assumptions'})
