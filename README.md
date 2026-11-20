# Example submission to the template challenge

A complete, working example of submitting forecasts to a challenge **from a
GitHub repository**, built on the
challenge template (`eco4cast/challenge-template`;
project `templatecast`: daily surface water temperature at three lakes, up to
30 days ahead). Copy it as the starting point for your own model.

There is nothing to upload and no key to ask for. The challenge reads new files
from this repository, which only has to be **public**.

```
challenge-model.yaml   which model this repository submits, and its metadata
forecasts/             the forecast files: <theme>-<reference date>-<model_id>.csv.gz
forecast.R             makes a forecast and writes the file (R)
forecast.py            the same forecast, in Python only
gefs_weather.py        reads weather (any GEFS variables) from dynamical.org (Python)
requirements.txt       the Python packages it needs
.github/workflows/     optional: run forecast.R (or forecast.py) every day and commit the file
```

## The model

A regression of water temperature on air temperature, driven by an ensemble weather
forecast, so the forecast is an **ensemble** of 31 members:

1. **Weather from dynamical.org.** `gefs_weather.py` reads daily weather at each lake (by
   default the 2 m air temperature; see *Choosing weather variables* for the other 26) from
   two [dynamical.org](https://dynamical.org) datasets of the NCEP Global Ensemble Forecast
   System (GEFS):
   - the weather the lakes had over the past year, to fit the model, from the
     [**NOAA GEFS analysis**](https://dynamical.org/catalog/noaa-gefs-analysis/): the model's
     best estimate of past weather, one 3-hourly time series since 2000;
   - each member's forecast of the weather to come, from the
     [**NOAA GEFS forecast, 35 day**](https://dynamical.org/catalog/noaa-gefs-forecast-35-day/):
     31 members (a control and 30 perturbed), run every day at 00 UTC out to 35 days.

   Both are the same model, so a relationship fitted to the analysis carries over to the forecast.
2. **Fit.** At each lake, `lm(water temperature ~ air temperature)` over the past year.
3. **Forecast.** Each GEFS member's air temperature goes through the regression, plus a
   random draw from the regression's residuals, to make one member of the water temperature
   forecast (`family = ensemble`, the member number is the `parameter`). The weather
   uncertainty comes from the 31 GEFS members and the model's own from the residuals.

```sh
pip install -r requirements.txt     # Python: icechunk, xarray, zarr, pystac, numpy, pandas, boto3
Rscript forecast.R                  # R: readr and dplyr
python forecast.py                  # or the same model in Python only
```

It writes `forecasts/lakes-<GEFS run date>-example_lake_model.csv.gz`. The file in this
repository is for the 2026-11-19 run. The model is a simple one on purpose: replace the
"Forecast" section of `forecast.R` with your own (other GEFS variables, a better regression, a
process model) and keep the rest.

### Python only

`forecast.py` is the same model written in Python, for people who do not use R. It uses
`gefs_weather.py` directly (`import gefs_weather`), fits the regressions with NumPy, and
writes the same file, with the same environment variables (`REFERENCE_DATE`, `TARGETS_URL`,
`SITES_URL`, `TRAIN_DAYS`, `WEATHER_VARIABLES`, `S3_KEY` and `S3_SECRET`). With a private
bucket it reads the targets through `boto3` with the key, so it needs no extra program. The
two versions give the same regressions; the 31 members differ only in their random draws.
They write the same file name, so use one of them for a given model. To run the Python one
every day use `.github/workflows/forecast-python.yml` instead of `forecast.yml`; it needs
no container and no R.

### Choosing weather variables

GEFS has 27 variables (air temperature at 2 m and 80 m, humidity, wind components at 10, 80
and 100 m and gusts, pressure, precipitation rate, cloud cover, precipitable water, short-
and long-wave radiation, categorical rain/snow/ice, and more), the same in the analysis and
the forecast. Name the ones you want and both the Python script and `forecast.R` follow:

```sh
python3 gefs_weather.py list                      # every variable: name, units, how a step is defined

# R: the regression uses whatever you list (comma separated, one coefficient each)
WEATHER_VARIABLES=temperature_2m,downward_short_wave_radiation_flux_surface,wind_u_10m \
  Rscript forecast.R

# Python, by hand: the weather the lakes had, and each ensemble member's forecast
python3 gefs_weather.py history  sites.csv history.csv  --date 2026-10-31 --days 365 \
  --variables temperature_2m relative_humidity_2m
python3 gefs_weather.py forecast sites.csv forecast.csv --date 2026-11-20 --horizon 30 \
  --variables temperature_2m relative_humidity_2m
```

`sites.csv` needs `site_id`, `latitude` and `longitude` columns (the template challenge's
`sites.csv` works). Each variable comes back as a column of daily values: the 3- or 6-hourly
steps of each UTC day are averaged, except `maximum_temperature_2m` and
`minimum_temperature_2m`, which take the day's max and min. Add `:max`, `:min`, `:mean` or
`:sum` to a name to choose, e.g. `temperature_2m:max`, which comes back as the column
`temperature_2m_max`. Values keep the dataset's units: for example `precipitation_surface` is
a rate in kg m-2 s-1 (mm per second), so multiply its daily mean by 86400 for mm per day.
A name that is not a GEFS variable stops with a list of close matches. Only the grid cells at
your sites are downloaded, so more variables add a second or two each.

### Reading weather forecasts from dynamical.org

dynamical.org publishes weather datasets as cloud-optimized
[Zarr](https://zarr.dev) in an [Icechunk](https://icechunk.io) repository on public storage.
There is no account or key, and you only download the part you ask for. The dataset's
[STAC](https://stac.dynamical.org/noaa-gefs-forecast-35-day/collection.json) record gives
the address, and `xarray` opens it lazily:

```python
import icechunk, pystac, xarray as xr

catalog = pystac.Catalog.from_file("https://stac.dynamical.org/catalog.json")

def open_dataset(name):
    asset = catalog.get_child(name).assets["icechunk-https"]
    repo = icechunk.Repository.open(icechunk.http_storage(asset.href))
    return xr.open_zarr(repo.readonly_session("main").store, chunks=None)

# Air temperature (deg C) at the cell nearest a lake.
forecast = open_dataset("noaa-gefs-forecast-35-day")   # init_time x ensemble_member x lead_time x lat x lon
forecast["temperature_2m"].sel(latitude=29.68, longitude=-82.01, method="nearest")

analysis = open_dataset("noaa-gefs-analysis")           # time x lat x lon
analysis["temperature_2m"].sel(latitude=29.68, longitude=-82.01, method="nearest").sel(time="2026-10")
```

In the forecast, `init_time` is the day of the run, `ensemble_member` runs 0-30, `lead_time` is
3-hourly out to 10 days and 6-hourly after, and the grid is 0.25 degrees. The analysis is
3-hourly on the same grid; a year at one lake takes a second or two. The dataset also has other
variables (wind, humidity, radiation, precipitation, ...): print `ds` to see them. R
has no Icechunk reader, so `forecast.R` calls the small Python script and reads the CSV it
writes. The newest run takes a few hours to be added after 00 UTC; the script uses the latest
complete one and the file is named for it.

Weather data: NOAA NWS NCEP GEFS (forecast and analysis), processed by dynamical.org
([CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)).

## What the challenge needs from you

1. **Forecast files** in the folder named in `challenge-model.yaml`
   (`forecasts/`). The name is `<theme>-<YYYY-MM-DD>-<model_id>.csv` or `.csv.gz`:
   `lakes` is this challenge's theme, the date is the day the forecast starts
   from, and the model id must match `challenge-model.yaml`. Columns:
   `project_id`, `model_id`, `reference_datetime`, `datetime`, `duration`,
   `site_id`, `variable`, `family`, `parameter` and `prediction`. A `normal`
   forecast has a `mu` and a `sigma` row for every site and date; an ensemble
   (as here) uses `family = ensemble` or `sample` with the member number as `parameter`.
2. **`challenge-model.yaml`** at the top of the repository. It names the
   challenge (`templatecast`) and each model, and answers the questions of the
   model registration form; the challenge builds the model's catalog entry from
   it, and re-reads it when it changes. Leave out any question you do not want to
   answer.
3. **Registration.** Open the **Register a forecast repository** issue form on the
   challenge repository and give this repository's address. A bot checks it,
   adds it to the list of repositories the challenge reads, and closes the issue.

After that, every new file is checked the next time the challenge processes
submissions. What happened to each file, with the reason for any rejection, is
published at
`<forecasts bucket>/submission_results/example_lake_model.csv` (the challenge's
"How to forecast" page gives the address).

## Things to know

- A file is read **the first time it is seen**; editing it later has no effect.
  Add a new file for a new reference date instead.
- Only the repository registered for a `model_id` can submit as it, and a model id
  belongs to the first repository that registered it.
- A model id containing `example` is a test model: it is processed like any
  other but kept out of the challenge's catalog and analyses. This
  example uses one so that it can be tried safely. Pick your own id to be
  included.
- `challenge-model.yaml`'s `code_url` still says `YOUR-ACCOUNT`; set it to this
  repository's address when you publish it.

## If the challenge's bucket is private

By default `forecast.R` reads the targets by their public URL. If the challenge keeps
its bucket private, ask its organizers for a **read-only key**, then set two
environment variables and nothing else changes:

```sh
export S3_KEY=<key id> S3_SECRET=<application key>
Rscript forecast.R        # also needs the minioclient and openssl packages
```

The script then reads the same address through the S3 API with the key: it downloads
the targets file to a temporary folder and reads that. This uses the MinIO client
(`mc`). `minioclient::install_mc()` no longer works, because MinIO has withdrawn the
download it uses (HTTP 410 Gone), so `forecast.R` installs the last release from
GitHub instead and checks its SHA-256. In GitHub Actions add the
two values as repository secrets named `S3_KEY` and `S3_SECRET` (Settings → Secrets and
variables → Actions → New repository secret); the workflow passes them on. Never commit
a key. The workflow commits each new forecast with the repository's built-in token, so
it needs no other secret; if the push is refused, set **Settings → Actions → General →
Workflow permissions** to *Read and write permissions*.

## Making a forecast every day

`.github/workflows/forecast.yml` (or `forecast-python.yml`, for `forecast.py`) installs Python and the packages in `requirements.txt`, runs
`forecast.R` and commits the new file. Its
schedule is commented out: switch it on once the repository is registered and
the challenge's targets are published, since the forecast needs them. (Without
the schedule you can run it from the Actions tab.) Anything else that puts a
new file in `forecasts/` works as well: a cron job, a pipeline, a commit by hand.
