from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import httpx

from app.openf1 import OpenF1Client, epoch


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Add OpenF1 position records to an existing "
            "two-car GRIDGHOST JSON capture."
        )
    )

    parser.add_argument(
        "--input",
        type=Path,
        required=True,
        help="Existing GRIDGHOST/OpenF1 JSON file.",
    )

    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Output JSON containing position data.",
    )

    parser.add_argument(
        "--padding-s",
        type=float,
        default=5.0,
        help=(
            "Seconds added before and after the existing "
            "car_data time window."
        ),
    )

    args = parser.parse_args()

    # ============================================================
    # LOAD INPUT
    # ============================================================

    if not args.input.exists():
        raise FileNotFoundError(
            f"Input file not found: {args.input}"
        )

    payload = json.loads(
        args.input.read_text(
            encoding="utf-8"
        )
    )

    car_data = payload.get(
        "car_data",
        [],
    )

    if not car_data:
        raise ValueError(
            "Input JSON contains no car_data."
        )

    required_metadata = [
        "session_key",
        "own_driver_number",
        "rival_driver_number",
    ]

    missing_metadata = [
        field
        for field in required_metadata
        if field not in payload
    ]

    if missing_metadata:
        raise ValueError(
            "Input JSON is missing required metadata: "
            f"{missing_metadata}"
        )

    session_key = int(
        payload["session_key"]
    )

    own_driver = int(
        payload["own_driver_number"]
    )

    rival_driver = int(
        payload["rival_driver_number"]
    )

    if own_driver == rival_driver:
        raise ValueError(
            "Own driver and rival driver must be different."
        )

    # ============================================================
    # DETERMINE TIME WINDOW
    # ============================================================

    timestamps = []

    for row in car_data:
        date = row.get("date")

        if not date:
            continue

        try:
            timestamps.append(
                epoch(date)
            )
        except Exception:
            continue

    if not timestamps:
        raise ValueError(
            "car_data contains no usable timestamps."
        )

    start_epoch = (
        min(timestamps)
        - args.padding_s
    )

    end_epoch = (
        max(timestamps)
        + args.padding_s
    )

    # ============================================================
    # DISPLAY REQUEST INFORMATION
    # ============================================================

    print()
    print("=" * 72)
    print("GRIDGHOST OPENF1 POSITION ENRICHMENT")
    print("=" * 72)

    print(
        f"Input file    : {args.input}"
    )

    print(
        f"Output file   : {args.output}"
    )

    print(
        f"Session       : {session_key}"
    )

    print(
        f"Own driver    : {own_driver}"
    )

    print(
        f"Rival driver  : {rival_driver}"
    )

    print(
        f"Padding       : {args.padding_s:.1f} s"
    )

    print()

    # ============================================================
    # OPENF1 CLIENT
    # ============================================================

    client = OpenF1Client()

    all_positions = []

    # ============================================================
    # FETCH POSITION FOR BOTH DRIVERS
    # ============================================================

    for driver in (
        own_driver,
        rival_driver,
    ):

        print(
            f"Fetching position data "
            f"for driver {driver}..."
        )

        try:
            rows = client.fetch(
                "position",
                {
                    "session_key":
                        session_key,

                    "driver_number":
                        driver,
                },
            )

        except httpx.HTTPStatusError as exc:

            status_code = (
                exc.response.status_code
            )

            # ----------------------------------------------------
            # OpenF1 live-session restriction
            # ----------------------------------------------------

            if status_code == 401:

                try:
                    response_data = (
                        exc.response.json()
                    )

                    detail = response_data.get(
                        "detail",
                        "Unauthorized request."
                    )

                except Exception:
                    detail = (
                        "Unauthorized request."
                    )

                print()
                print("=" * 72)
                print(
                    "OPENF1 ACCESS CURRENTLY RESTRICTED"
                )
                print("=" * 72)

                print()
                print(
                    f"OpenF1 returned HTTP {status_code}."
                )

                print()
                print(
                    "Server message:"
                )

                print(
                    detail
                )

                print()
                print(
                    "Nothing is wrong with GRIDGHOST, "
                    "Python, or your virtual environment."
                )

                print()
                print(
                    "OpenF1 is refusing the API request "
                    "at the server level."
                )

                print()
                print(
                    "Your original input file has NOT "
                    "been modified."
                )

                print(
                    "The enriched output file has NOT "
                    "been written."
                )

                print()
                print(
                    "Wait until unauthenticated historical "
                    "access becomes available again, or "
                    "use authenticated OpenF1 access."
                )

                print()
                print(
                    "You can check the endpoint with:"
                )

                print(
                    "curl.exe -s -o NUL -w "
                    '"%{http_code}`n" '
                    '"https://api.openf1.org/v1/position'
                    f'?session_key={session_key}'
                    f'&driver_number={driver}"'
                )

                print()
                print(
                    "When that command returns 200, "
                    "run this enrichment script again."
                )

                return

            # ----------------------------------------------------
            # Other HTTP errors
            # ----------------------------------------------------

            print()
            print("=" * 72)
            print("OPENF1 HTTP ERROR")
            print("=" * 72)

            print(
                f"Status code : {status_code}"
            )

            print(
                f"URL         : {exc.request.url}"
            )

            try:
                print(
                    f"Response    : "
                    f"{exc.response.text}"
                )
            except Exception:
                pass

            return

        except httpx.RequestError as exc:

            print()
            print("=" * 72)
            print("OPENF1 NETWORK ERROR")
            print("=" * 72)

            print()
            print(
                "The OpenF1 server could not be reached."
            )

            print(
                f"Details: {exc}"
            )

            print()
            print(
                "Check your internet connection and "
                "try again later."
            )

            return

        except Exception as exc:

            print()
            print("=" * 72)
            print("UNEXPECTED ERROR")
            print("=" * 72)

            print(
                f"{type(exc).__name__}: {exc}"
            )

            return

        # ========================================================
        # FILTER TO CURRENT CAPTURE TIME WINDOW
        # ========================================================

        filtered = []

        for row in rows:

            date = row.get(
                "date"
            )

            if not date:
                continue

            try:
                timestamp = epoch(
                    date
                )

            except Exception:
                continue

            if (
                start_epoch
                <= timestamp
                <= end_epoch
            ):
                filtered.append(
                    row
                )

        print(
            f"  downloaded : {len(rows)}"
        )

        print(
            f"  retained   : {len(filtered)}"
        )

        all_positions.extend(
            filtered
        )

    # ============================================================
    # SORT
    # ============================================================

    all_positions.sort(
        key=lambda row: epoch(
            row["date"]
        )
    )

    # ============================================================
    # VERIFY BOTH DRIVERS
    # ============================================================

    position_drivers = sorted(
        {
            int(row["driver_number"])
            for row in all_positions
            if row.get(
                "driver_number"
            ) is not None
        }
    )

    print()
    print(
        f"Position drivers found: "
        f"{position_drivers}"
    )

    missing_drivers = [
        driver
        for driver in (
            own_driver,
            rival_driver,
        )
        if driver not in position_drivers
    ]

    if missing_drivers:

        print()
        print("=" * 72)
        print("POSITION DATA INCOMPLETE")
        print("=" * 72)

        print(
            "Missing position data for driver(s): "
            f"{missing_drivers}"
        )

        print()
        print(
            "Output file will NOT be written because "
            "GRIDGHOST needs both drivers to verify "
            "adjacency safely."
        )

        return

    # ============================================================
    # BUILD OUTPUT
    # ============================================================

    output = dict(
        payload
    )

    output[
        "position"
    ] = all_positions

    output[
        "position_enrichment"
    ] = {
        "source":
            "OpenF1 position endpoint",

        "session_key":
            session_key,

        "drivers": [
            own_driver,
            rival_driver,
        ],

        "padding_s":
            float(
                args.padding_s
            ),

        "created_utc":
            datetime.now(
                timezone.utc
            ).isoformat(),

        "position_rows":
            len(
                all_positions
            ),

        "position_drivers":
            position_drivers,
    }

    # ============================================================
    # WRITE ONLY AFTER SUCCESS
    # ============================================================

    args.output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    args.output.write_text(
        json.dumps(
            output,
            indent=2,
        ),
        encoding="utf-8",
    )

    # ============================================================
    # RESULT
    # ============================================================

    print()
    print("=" * 72)
    print("ENRICHMENT SUCCESSFUL")
    print("=" * 72)

    print(
        f"Position rows : "
        f"{len(all_positions)}"
    )

    print(
        f"Drivers       : "
        f"{position_drivers}"
    )

    print(
        f"Saved         : "
        f"{args.output}"
    )

    print()

    if all_positions:
        print(
            "First position record:"
        )

        print(
            json.dumps(
                all_positions[0],
                indent=2,
            )
        )


if __name__ == "__main__":
    main()