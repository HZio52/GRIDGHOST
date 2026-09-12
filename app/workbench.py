import json

from datetime import (
    datetime,
    timezone,
)

from pathlib import Path

from fastapi import (
    Depends,
    HTTPException,
    Query,
)

from fastapi.responses import (
    FileResponse,
)

from fastapi.staticfiles import (
    StaticFiles,
)

from .hybrid import (
    hybrid_plan,
    ml_health,
)

from .planner import (
    PlanRequest,
    CompareRequest,
    compare,
)


ROOT = Path(
    __file__
).resolve().parents[1]


def mount_workbench(
    app,
    authorize,
    store,
):

    app.mount(
        "/assets",
        StaticFiles(
            directory=ROOT / "web"
        ),
        name="assets",
    )

    # --------------------------------------------------------
    # FRONTEND
    # --------------------------------------------------------

    @app.get(
        "/",
        include_in_schema=False,
    )
    def home():

        return FileResponse(
            ROOT
            / "web"
            / "index.html"
        )

    # --------------------------------------------------------
    # SCENARIOS
    # --------------------------------------------------------

    @app.get(
        "/v2/scenarios",
        dependencies=[
            Depends(authorize)
        ],
    )
    def scenarios():

        return json.loads(
            (
                ROOT
                / "data"
                / "scenarios.json"
            ).read_text()
        )

    # --------------------------------------------------------
    # ML STATUS
    # --------------------------------------------------------

    @app.get(
        "/v2/ml-health",
        dependencies=[
            Depends(authorize)
        ],
    )
    def model_health():

        return ml_health()

    # --------------------------------------------------------
    # HYBRID PLAN
    #
    # XGBoost:
    # candidate generator
    #
    # deterministic V2 planner:
    # feasibility / safety shield
    # --------------------------------------------------------

    @app.post(
        "/v2/plan",
        dependencies=[
            Depends(authorize)
        ],
    )
    def evaluate(
        body: PlanRequest,
        save: bool = False,
        db=Depends(store),
    ):

        result = hybrid_plan(
            body
        )

        if save:

            with db.connect() as connection:

                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS evaluations (
                        id INTEGER PRIMARY KEY,
                        created TEXT,
                        input TEXT,
                        output TEXT
                    )
                    """
                )

                cursor = connection.execute(
                    """
                    INSERT INTO evaluations
                    (created, input, output)
                    VALUES (?, ?, ?)
                    """,
                    (
                        datetime.now(
                            timezone.utc
                        ).isoformat(),

                        body.model_dump_json(),

                        json.dumps(
                            result
                        ),
                    ),
                )

                result[
                    "evaluation_id"
                ] = cursor.lastrowid

        return result

    # --------------------------------------------------------
    # DETERMINISTIC SYNTHETIC COMPARISON
    #
    # Deliberately unchanged.
    # This remains the existing scenario comparison
    # rather than mixing ML into the benchmark plant.
    # --------------------------------------------------------

    @app.post(
        "/v2/compare",
        dependencies=[
            Depends(authorize)
        ],
    )
    def simulation(
        body: CompareRequest,
    ):

        try:

            return compare(
                body
            )

        except ValueError as exc:

            raise HTTPException(
                422,
                str(exc),
            ) from exc

    # --------------------------------------------------------
    # HISTORY
    # --------------------------------------------------------

    @app.get(
        "/v2/history",
        dependencies=[
            Depends(authorize)
        ],
    )
    def history(
        limit: int = Query(
            30,
            ge=1,
            le=100,
        ),
        db=Depends(store),
    ):

        with db.connect() as connection:

            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS evaluations (
                    id INTEGER PRIMARY KEY,
                    created TEXT,
                    input TEXT,
                    output TEXT
                )
                """
            )

            records = connection.execute(
                """
                SELECT *
                FROM evaluations
                ORDER BY id DESC
                LIMIT ?
                """,
                (
                    limit,
                ),
            ).fetchall()

        return [
            {
                "id":
                    record["id"],

                "created":
                    record["created"],

                "input":
                    json.loads(
                        record["input"]
                    ),

                "output":
                    json.loads(
                        record["output"]
                    ),
            }
            for record in records
        ]