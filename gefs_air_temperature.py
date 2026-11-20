#!/usr/bin/env python3
"""Daily 2 m air temperature at points, from the NOAA GEFS 35-day forecast on dynamical.org.

dynamical.org publishes weather datasets as Icechunk repositories (cloud-optimized Zarr)
that anyone can read over HTTPS, with no account. The dataset used here is "NOAA GEFS
forecast, 35 day": the 31-member GEFS ensemble (members 0-30), initialized every day at
00 UTC from 2020-10-01 to today, at 3-hourly steps for the first 10 days and 6-hourly after,
out to 35 days, on a 0.25 degree grid. Catalog page: https://dynamical.org/catalog/noaa-gefs-forecast-35-day/
Data: NOAA NWS NCEP GEFS, processed by dynamical.org (CC BY 4.0).

Two modes, each writing a CSV:

  history   the weather each day, for fitting a model. For each day, the average of the
            forecast initialized that day over its first 24 hours (steps 0-21 h) and over
            all members, which is as close to observed weather as GEFS gets.
            Columns: site_id, date, air_temperature

  forecast  the ensemble forecast of daily mean air temperature, one value per member and
            day, for the days after the initialization date.
            Columns: site_id, init_date, ensemble_member, date, air_temperature

Both read only the grid cell nearest each site, so they download a few megabytes. Needs:
  pip install icechunk xarray zarr pystac numpy pandas        (see requirements.txt)
"""
import argparse
import sys

import numpy as np
import pandas as pd
import pystac
import xarray as xr
import icechunk

STAC_CATALOG = "https://stac.dynamical.org/catalog.json"
DATASET = "noaa-gefs-forecast-35-day"


def open_gefs():
    """Open the dataset lazily. Nothing is downloaded until values are loaded."""
    catalog = pystac.Catalog.from_file(STAC_CATALOG)
    asset = catalog.get_child(DATASET).assets["icechunk-https"]
    repo = icechunk.Repository.open(icechunk.http_storage(asset.href))
    session = repo.readonly_session("main")
    return xr.open_zarr(session.store, chunks=None)


def point(temperature, site):
    """The series at the grid cell nearest a site (longitudes run -180 to 179.75)."""
    return temperature.sel(latitude=site.latitude, longitude=site.longitude, method="nearest")


def history(ds, sites, end, days):
    """Daily air temperature for the `days` days up to `end`, from each day's first 24 hours."""
    start = end - pd.Timedelta(days=days - 1)
    rows = []
    for site in sites.itertuples():
        series = point(ds["temperature_2m"], site)
        series = series.sel(init_time=slice(start, end),
                            lead_time=slice(pd.Timedelta(0), pd.Timedelta(hours=21)))
        daily = series.load().mean(["ensemble_member", "lead_time"]).to_series()
        daily = daily.dropna()
        rows.append(pd.DataFrame({
            "site_id": site.site_id,
            "date": daily.index.normalize().strftime("%Y-%m-%d"),
            "air_temperature": daily.values,
        }))
    return pd.concat(rows, ignore_index=True)


def forecast(ds, sites, init_date, horizon):
    """Daily air temperature for each ensemble member, for `horizon` days after the run.

    The newest run is still being added to the dataset for a few hours after 00 UTC, so
    a run that is not complete yet is skipped for the one before it.
    """
    first = sites.iloc[0]
    for back in range(4):
        init = init_date - pd.Timedelta(days=back)
        if init not in ds["init_time"].values:
            continue
        last_step = point(ds["temperature_2m"], first).sel(init_time=init).isel(lead_time=-1)
        if not np.isnan(last_step.load()).any():
            break
    else:
        sys.exit(f"No complete GEFS run found on or before {init_date.date()}.")
    print(f"Using the GEFS run initialized {init} ({back} day(s) before {init_date.date()})",
          file=sys.stderr)

    rows = []
    for site in sites.itertuples():
        run = point(ds["temperature_2m"], site).sel(init_time=init).load()
        # Each step's valid time is the run's start plus its lead time; group the steps by day.
        valid = pd.DatetimeIndex(init + run["lead_time"].values)
        run = run.assign_coords(date=("lead_time", valid.normalize()))
        daily = run.groupby("date").mean("lead_time").to_dataframe(name="air_temperature")
        # (to_dataframe also carries the dataset's other coordinates; keep what we need.)
        daily = daily.reset_index()[["ensemble_member", "date", "air_temperature"]]
        daily = daily[(daily["date"] > init) & (daily["date"] <= init + pd.Timedelta(days=horizon))]
        daily.insert(0, "site_id", site.site_id)
        daily.insert(1, "init_date", init.strftime("%Y-%m-%d"))
        daily["date"] = daily["date"].dt.strftime("%Y-%m-%d")
        rows.append(daily.dropna())
    return pd.concat(rows, ignore_index=True)[
        ["site_id", "init_date", "ensemble_member", "date", "air_temperature"]]


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("mode", choices=["history", "forecast"])
    parser.add_argument("sites", help="CSV with site_id, latitude and longitude columns")
    parser.add_argument("out", help="CSV to write")
    parser.add_argument("--date", required=True, help="last day (history) or run date (forecast), YYYY-MM-DD")
    parser.add_argument("--days", type=int, default=120, help="history: how many days back")
    parser.add_argument("--horizon", type=int, default=30, help="forecast: days ahead")
    args = parser.parse_args()

    sites = pd.read_csv(args.sites)[["site_id", "latitude", "longitude"]]
    date = pd.Timestamp(args.date)
    ds = open_gefs()
    if args.mode == "history":
        result = history(ds, sites, date, args.days)
    else:
        result = forecast(ds, sites, date, args.horizon)
    result.to_csv(args.out, index=False)
    print(f"Wrote {len(result)} rows to {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
