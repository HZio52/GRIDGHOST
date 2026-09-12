# Release validation - v2

## Passed

- Python suite: 40 tests passed. See test-results.txt (two upstream deprecation warnings).
- Existing v1 calculations, validation, audit storage, concurrency and adapter tests remain passing.
- V2 tests: complete-plan energy constraints, terminal buffer, future windows, conservation-branch retention, deterministic planning/comparison, gate behavior, root dashboard route, asset response, saved evaluation reload after restart, API key and bad-input handling.
- The real application JavaScript ran against a real local Uvicorn server using a minimal DOM test double. Initial evaluation, caution abstention, save, history, replay, controller comparison, and SVG generation passed. See ui-logic-check.txt and scripts/check_ui_logic.mjs.
- JavaScript syntax validation passed with node --check.
- The valid close-fight planning benchmark includes 200 requests after 10 warmups; exact measurements are in benchmark_v2.json. Runtime is machine-specific and excludes source/network delay.

### ML validation

- Tuned core XGBoost, 5-fold grouped out-of-fold evaluation on 50,000 rows: 81.5% accuracy (`reports/ml/core_tuned_oof/metrics.json`, `accuracy` 0.81482).
- Uncertainty gate (0.85 minimum-coverage rule): ~86% accuracy at 85.2% coverage when allowed to abstain on the most ambiguous 14.8% of cases (`reports/ml/core_abstention/abstention_report.json`: coverage 0.85246, abstain_rate 0.14754, accuracy 0.8629).
- Methodology: grouped cross-validation on source groups, then multiclass temperature scaling fitted on the same grouped OOF folds (`reports/ml/core_calibration/temperature_calibration.json`). The ML layer is a candidate generator only; it never bypasses the deterministic feasibility shield. Teacher-policy bootstrap, not real-race outcome validation.

## Not claimed

- Browser screenshot review, responsive rendering, keyboard navigation and native file dialogs were not executed. The provided cloud browser returned ERR_BLOCKED_BY_CLIENT for the local URL. The DOM double is not a rendering engine.
- Windows launcher execution and Docker image build were not executed here.
- Historical OpenF1 downloading was not reverified; the earlier smoke returned HTTP 404.
- No FIA compliance certification, calibrated racing dynamics, private battery estimator, full-race optimization, or real racing outcome improvement is claimed.

## Quick laptop check

1. Start the app and open `/`; confirm the red/white/black dashboard and Backend connected label.
2. Switch through all six scenarios and check the reason for each result.
3. Edit energy and evaluate. Confirm the input-changed badge clears only after calculation.
4. Save, switch to Evidence & history, refresh and inspect the saved row.
5. Advance replay and reset it. Import data/close_fight_s07.json.
6. Export one decision JSON and import it again.
7. Run Scenario lab twice with the same seed; outcomes should match (runtime can differ).
8. Narrow the browser to phone width and use keyboard Tab to reach controls.
9. Stop/restart the backend and confirm saved history remains.

Node.js is optional only for the developer-side JS logic checker. Normal application use requires Python 3.12 alone.
