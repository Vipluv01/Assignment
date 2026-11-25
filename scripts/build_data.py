"""Convert the original Attendee Dataset workbook into the JSON the app loads.

Usage:  python scripts/build_data.py ["data/original/Attendee Dataset.xlsx"]
Needs:  pip install openpyxl   (build-time only; the app itself does not need it)

The conversion is deliberately dumb: every source row is copied as-is, duplicates
included. All cleaning (de-duplicating import retries, as-of filtering, external-only
counting) happens in growth/engine.py so there is one place to audit.
"""
import datetime as dt
import json
import pathlib
import sys

import openpyxl

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "data/original/Attendee Dataset.xlsx"
OUT = ROOT / "growth/data/attendee.json"

SHEETS = {
    "Event": "event",
    "Targets": "targets",
    "Campaigns": "campaigns",
    "Daily Marketing": "daily",
    "People": "people",
    "Interest and Engagement": "interactions",
    "Registrations": "registrations",
    "Registration History": "registration_history",
    "Check-ins": "checkins",
}


def cell(v):
    if isinstance(v, dt.datetime):
        return v.strftime("%Y-%m-%dT%H:%M:%S")  # source timestamps are IST wall-clock
    if isinstance(v, dt.date):
        return v.isoformat()
    return v


def main():
    wb = openpyxl.load_workbook(SRC, read_only=True, data_only=True)
    out = {}
    for sheet, key in SHEETS.items():
        rows = wb[sheet].iter_rows(values_only=True)
        cols = [c for c in next(rows) if c is not None]
        data = [[cell(v) for v in r[: len(cols)]] for r in rows if any(v is not None for v in r)]
        out[key] = {"cols": cols, "rows": data}
        print(f"{key:22s} {len(data):6d} rows")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, separators=(",", ":"), ensure_ascii=False))
    print("wrote", OUT, f"{OUT.stat().st_size/1e6:.2f} MB")


if __name__ == "__main__":
    main()
