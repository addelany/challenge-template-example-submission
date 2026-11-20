#!/usr/bin/env python3
"""Check a forecast file before you push it.

Usage:  python check_forecast.py forecasts/lakes-2026-11-20-example_lake_model.csv.gz

Checks the things the challenge rejects a file for: the name, the columns, one model and one
project, the reference date, dates after it, missing predictions, one family, the
parameters of the family and duplicate rows. It does not know the challenge's variables,
sites or horizons: compare those with its "How to forecast" page. Exit status 0 means no
problem was found; 1 means there was one (printed). Needs pandas.
"""
import re
import sys

import pandas as pd

NEED = ["project_id", "model_id", "reference_datetime", "datetime", "duration",
        "site_id", "variable", "family", "parameter", "prediction"]


def check(path):
    """Return (summary, problems) for one forecast file."""
    name = path.replace("\\", "/").split("/")[-1]
    match = re.fullmatch(r"([^-]+)-(\d{4}-\d{2}-\d{2})-(.+)\.csv(\.gz)?", name)
    if not match:
        return "", ["the name must be <theme>-<YYYY-MM-DD>-<model_id>.csv or .csv.gz"]
    _, ref_date, model_id = match.group(1), match.group(2), match.group(3)

    d = pd.read_csv(path)
    missing = [c for c in NEED if c not in d.columns]
    if missing:
        return "", [f"missing columns: {missing}"]

    problems = []
    if list(d["model_id"].unique()) != [model_id]:
        problems.append(f"model_id in the file {list(d['model_id'].unique())} is not the one "
                        f"in the name ({model_id})")
    if d["project_id"].nunique() != 1:
        problems.append("more than one project_id")
    if (pd.to_datetime(d["reference_datetime"]).dt.strftime("%Y-%m-%d") != ref_date).any():
        problems.append(f"reference_datetime must be {ref_date}, the date in the name")
    if (pd.to_datetime(d["datetime"]) <= pd.Timestamp(ref_date)).any():
        problems.append("datetime must be after the reference date")
    if d["prediction"].isna().any():
        problems.append("prediction has missing values")
    if d["family"].nunique() != 1:
        problems.append("one family per file")
    elif d["family"].iloc[0] == "normal":
        if set(d["parameter"].astype(str)) != {"mu", "sigma"}:
            problems.append("a normal forecast needs the parameters mu and sigma")
    elif d["family"].iloc[0] in ("ensemble", "sample"):
        if d["parameter"].nunique() > 500:
            problems.append("more than 500 ensemble members")
    if d.duplicated(["site_id", "datetime", "variable", "parameter"]).any():
        problems.append("duplicate rows (site, datetime, variable, parameter)")

    summary = (f"{len(d)} rows, {d['site_id'].nunique()} sites, "
               f"{d['parameter'].nunique()} parameters or members, "
               f"{pd.to_datetime(d['datetime']).nunique()} days after {ref_date}")
    return summary, problems


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    summary, problems = check(sys.argv[1])
    if summary:
        print(summary)
    if problems:
        print("PROBLEMS:\n- " + "\n- ".join(problems))
        sys.exit(1)
    print("no problems found")
