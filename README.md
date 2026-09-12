# Race Strategy Lab - complete local application (v2)

A working energy-and-overtake decision workspace for the TrackShift team. Includes a browser dashboard and Python backend in one project. Visual direction uses racing red, white and black inspired by TGR Haas F1 Team's public website. This is an independent prototype, not their official software or a reproduction of a private pit-wall system.

## Windows: easiest start

1. Extract the ZIP into a new folder. Keep the earlier backend as a backup.
2. Open the extracted `trackshift-application` folder.
3. Double-click **START_WINDOWS.bat**. Python 3.12 and an internet connection for the first dependency installation are required.
4. When `Application startup complete` appears, open **http://127.0.0.1:8000**.
5. Keep the terminal open while using the application. Ctrl+C stops it.

Unlike v1, the root `/` now opens the actual dashboard. No Node.js, frontend build, API key, model download, cloud account or paid service is required to run the synthetic demonstration.

If your previous server still uses port 8000, stop it first using Ctrl+C. Alternatively use the manual start command with `--port 8001` and open http://127.0.0.1:8001.

## Windows: manual commands

Open a PowerShell terminal **inside the folder containing this README**:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000. No environment activation is required. Do not paste the commands into a Python interactive prompt.

For Linux/macOS use `python3.12 -m venv .venv` and replace `.\.venv\Scripts\python.exe` with `.venv/bin/python`.

## A complete walkthrough

### 1. Pit wall

The application checks the backend connection, loads the first synthetic scenario and calculates a plan. The page displays the recommended first action, an explanation, energy forecast, conservative finish, action sequence and rival-pace weights. The pit wall also has an **ML CANDIDATE** panel (prediction, probabilities, deterministic-shield verdict) and a local two-voice radio call on Evaluate / Save; both use cached model output and on-device audio, with no network TTS.

- Change the scenario: Close fight / Protect the reserve / Pressure from behind / Wait for the window / Caution period / Stale telemetry.
- Edit speed, signed gap, energy, data age, track status, terminal buffer or horizon.
- Click **Evaluate plan**. Edited values are marked as changed until re-evaluated.
- Read all four candidate rows, including rejection reasons.
- Click **Save decision** to recompute and persist the current input and result in SQLite.
- Click **Export JSON** to download the current evaluated request/result together.

The gap sign is important: positive means the rival is ahead; negative means behind. A gap proxy crossing zero does not prove a pass.

### 2. Replay and JSON import

Click **Next frame** to process the bundled 12-snapshot observation replay. Bayesian weights carry across frames. **Reset** clears the replay cursor and belief. Historical observations are not changed by recommendations.

The file selector accepts a JSON file up to 2 MB in these shapes:

```json
{"state":{"timestamp_s":1,"own_speed_kph":300,"rival_speed_kph":302,"gap_s":0.7,"own_energy_mj":2.4,"track_status":"GREEN"}}
```

Or `{ "states": [state1, state2, ...] }`, with up to 2,000 strictly increasing timestamps. It also accepts the exported `{ "request": ..., "result": ... }` format. Invalid data displays an error instead of a fabricated result.

The file `data/close_fight_s07.json` is ready to import. `data/scenarios.json` is the scenario catalog, not a replay upload; it holds named requests for the application's scenario menu.

### 3. Scenario lab

Uses the CURRENT pit-wall inputs. Choose a seed and click **Run comparison**. The backend runs 60 simulated seconds by default (15 x 4-second steps) using the same rival environment for three controllers:

- Multi-stage planner
- Reserve-aware HOLD baseline
- Greedy one-stage planner

Compare final energy, signed gap, reserve violations and action switches. Same inputs and seed reproduce outcomes, excluding runtime measurements. If a controller abstains, the simulator applies CONSERVE and labels that frame as a fallback. This is a controlled synthetic test, not proof of real-world racing benefit.

### 4. Evidence & history

Inspect the model contract and model-policy constraints. Refresh saved evaluations, then click **Inspect** to reload an exact saved request and output. SQLite records survive server restarts. The history view returns the most recent 30 evaluations by default; the API supports up to 100 per request.

## Verify the installation

Keep the server running and open a second terminal in the same folder:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m scripts.demo
.\.venv\Scripts\python.exe -m scripts.benchmark_v2
```

Health returns `status: ok`. This version's automated Python suite contains **40 passing tests**. The legacy CLI demo still exercises all 12 v1 snapshots and exports `data/latest_decisions.csv`. The v2 benchmark writes `docs/benchmark_v2.json`.

Validation evidence is in docs/VALIDATION.md. A browser in this environment could not access localhost, so real rendered browser QA is not claimed. DOM interaction integration checks are separately labelled.

## What the planner does

Read docs/MODEL_V2.md for exact details. It updates three rival-pace weights, searches bounded action sequences, checks energy at every stage, protects a terminal buffer, checks deployment budget, and selects the highest-scoring retained plan. Only the first action is recommended for the current observation. Send a new observation to plan again.

The default lookahead is 24 seconds; this is longer than v1's 8-second single-action calculation, but it is not a full-race optimizer. The search is approximate. Fixed racing coefficients and the rival response hypotheses are demonstrator assumptions, not trained or validated vehicle parameters.

## API

Interactive documentation: http://127.0.0.1:8000/docs

| Method | Route | Purpose |
|---|---|---|
| GET | / | Integrated dashboard |
| GET | /health | Liveness |
| GET | /v2/scenarios | Six labelled synthetic scenarios |
| POST | /v2/plan | Multi-stage planning; optional `?save=true` |
| POST | /v2/compare | Seeded closed-loop simulator comparison |
| GET | /v2/history | Recent persisted evaluations, `limit=1..100` |
| GET | /openapi.json | Full field schema |

All earlier `/v1/...` endpoints remain available, including stored runs, observation replay and CSV export. `docs/openapi.json` describes this release. The old 16-page PDF describes v1 and is kept under docs/legacy/ for reference only.

## Configuration and local access

No API key is set by default because this is a localhost demonstration. To require one, set `API_KEY` before starting the server, then enter that key in the dashboard's **API key** dialog. The browser keeps it in memory, not local storage. Set `DATABASE_PATH` to choose the SQLite location. Python reads process environment variables; it does not automatically load .env.

Example PowerShell:

```powershell
$env:API_KEY="your-own-long-random-secret"
$env:DATABASE_PATH="data/strategy.sqlite3"
```

The frontend and API share an origin, so default operation needs no CORS configuration. Docker Compose files are included, with frontend assets copied into the image. Docker and Windows execution were not verified in this Linux environment.

## Historical data

The OpenF1 CLI adapter from v1 remains available. See docs/DATA_AND_MODEL.md and `python -m scripts.fetch_openf1 --help`. The prior external request returned HTTP 404, so no verified real-data replay is included. Do not describe the bundled inputs as real telemetry.

Rival battery is unknown. Own energy and recovery values are supplied/simulated. Automatic circuit geometry, tyre physics, fuel models, live team telemetry and verified FIA regulations are not included. The dashboard is functional end to end within this explicit prototype scope.

## Before presenting

Read docs/CHALLENGE_ALIGNMENT.md. The reference site's rules require disclosure of significant reused code. This release extends the earlier AI-assisted backend prototype; disclose that reuse and your team's contributions accurately. No submission has been made on your behalf.

## Troubleshooting

- `.venv\Scripts\python.exe` not found: enter the correct project folder and create the environment first.
- `404` at `/`: you are probably running the old backend. Stop it and start this extracted project.
- `Address already in use`: stop the old process or use port 8001.
- `NO_RECOMMENDATION`: inspect the reason; flags, stale data, or infeasible constraints deliberately abstain.
- `401`: enter the configured API key. For the default demo, leave it blank.
- `422`: input does not match the schema; read the displayed field error.
- API docs blank while offline: Swagger's CDN assets need connectivity; the dashboard's own assets are bundled and do not.
