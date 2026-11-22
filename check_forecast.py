#!/usr/bin/env python3
"""Check a forecast file before you push it.

Usage:  python check_forecast.py forecasts/my_forecast.csv.gz [--challenge CONFIG ...]

Checks the things a challenge rejects a file for: the columns it needs, one model, dates
after each reference date, missing predictions, one family, the parameters of the family
and duplicate rows. The file name does not matter: a challenge identifies a forecast by its
model_id and reference_datetime columns.

One file can go to several challenges, and each keeps only the rows that belong to it. Give
--challenge the challenge's challenge_configuration.yaml (a path or an https:// address),
once for each challenge you submit to, and the rows each challenge would keep and drop are
listed, with the reason. A row is kept when its project_id label is empty or the challenge's,
its variable and duration are forecast by a target group, and its site is one of that group's
sites.

Exit status 0 means no problem was found; 1 means there was one (printed). Needs pandas and
pyyaml.
"""
import argparse
import sys
from pathlib import Path
from urllib.parse import urljoin

import pandas as pd
import yaml

NEED = ["model_id", "reference_datetime", "datetime", "duration", "site_id", "variable",
        "family", "parameter", "prediction"]


def check(path):
    """Return (summary, problems, forecast) for one forecast file."""
    d = pd.read_csv(path)
    missing = [c for c in NEED if c not in d.columns]
    if missing:
        return "", [f"missing columns: {missing}"], d

    problems = []
    if d["model_id"].nunique() != 1:
        problems.append(f"one model_id per file, found {list(d['model_id'].unique())}")
    reference = pd.to_datetime(d["reference_datetime"])
    if (pd.to_datetime(d["datetime"]) <= reference).any():
        problems.append("datetime must be after its reference_datetime")
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
    keys = ["reference_datetime", "site_id", "datetime", "variable", "duration", "parameter"]
    if "project_id" in d.columns:
        keys.append("project_id")
    if d.duplicated(keys).any():
        problems.append("duplicate rows (reference_datetime, site, datetime, variable, "
                        "duration, parameter)")

    summary = (f"{len(d)} rows, {d['site_id'].nunique()} sites, {d['variable'].nunique()} variables, "
               f"{d['parameter'].nunique()} parameters or members, "
               f"{reference.dt.date.nunique()} reference date(s)")
    return summary, problems, d


def load_text(source):
    if source.startswith(("http://", "https://")):
        import urllib.request
        with urllib.request.urlopen(source) as response:
            return response.read().decode()
    return Path(source).read_text()


def challenge_rules(source):
    """(project_id, {(variable, duration): set of site ids}, min reference date) of a challenge."""
    config = yaml.safe_load(load_text(source))
    sites_cfg = config.get("sites") or {}
    sites_url = sites_cfg.get("metadata_url") or (config.get("catalog_config") or {}).get(
        "site_metadata_url")
    if not sites_url.startswith(("http://", "https://")) and not Path(sites_url).is_absolute():
        base = source if source.startswith("http") else str(Path(source).resolve())
        sites_url = urljoin(base, sites_url) if source.startswith("http") else str(
            Path(base).parent / sites_url)
    sites = pd.read_csv(sites_url)
    id_column = (sites_cfg.get("columns") or {}).get("site_id", "field_site_id")
    allowed = {}
    for name, group in (config.get("target_groups") or {}).items():
        column = group.get("sites_column") or name.lower()
        members = set(sites.loc[sites[column].astype(str).isin(["1", "True", "true"]), id_column]
                      .astype(str))
        for variable, duration in zip(group["variable"], group["duration"]):
            allowed.setdefault((variable, duration), set()).update(members)
    minimum = (config.get("submissions") or {}).get("min_reference_date")
    return config["project_id"], allowed, (pd.Timestamp(minimum) if minimum else None)


def rows_kept(d, project_id, allowed, minimum):
    """Which rows of the forecast a challenge keeps, and why it drops the others."""
    reason = pd.Series("", index=d.index)
    if "project_id" in d.columns:
        other = d["project_id"].notna() & (d["project_id"] != project_id)
        reason[other & (reason == "")] = "labelled for another challenge"
    if minimum is not None:
        early = pd.to_datetime(d["reference_datetime"]).dt.tz_localize(None) < minimum
        reason[early & (reason == "")] = f"reference date before {minimum.date()}"
    pairs = list(zip(d["variable"], d["duration"]))
    known = pd.Series([pair in allowed for pair in pairs], index=d.index)
    reason[~known & (reason == "")] = "variable and duration are not forecast by this challenge"
    at_site = pd.Series([site in allowed.get(pair, ()) for site, pair
                         in zip(d["site_id"].astype(str), pairs)], index=d.index)
    reason[~at_site & (reason == "")] = "site is not one of this challenge's sites for the variable"
    return reason


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("file")
    parser.add_argument("--challenge", action="append", default=[], metavar="CONFIG",
                        help="a challenge's challenge_configuration.yaml (path or https:// "
                             "address); repeat for each challenge")
    args = parser.parse_args()

    summary, problems, d = check(args.file)
    if summary:
        print(summary)
    for source in args.challenge:
        if problems and not summary:
            break
        project_id, allowed, minimum = challenge_rules(source)
        reason = rows_kept(d, project_id, allowed, minimum)
        kept = int((reason == "").sum())
        print(f"{project_id}: keeps {kept} of {len(d)} rows")
        if kept == 0:
            problems.append(f"{project_id} would keep none of the rows")
        for why, n in reason[reason != ""].value_counts().items():
            print(f"  drops {n}: {why}")
    if problems:
        print("PROBLEMS:\n- " + "\n- ".join(problems))
        sys.exit(1)
    print("no problems found")


if __name__ == "__main__":
    main()
