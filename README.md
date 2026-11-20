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
forecast.R             makes a forecast and writes the file
gefs_air_temperature.py  reads the weather forecast from dynamical.org (Python)
requirements.txt       the Python packages it needs
.github/workflows/     optional: runs forecast.R every day and commits the file
```

## The model

A regression of water temperature on air temperature, driven by an ensemble weather
forecast, so the forecast is an **ensemble** of 31 members:

1. **Weather from dynamical.org.** `gefs_air_temperature.py` reads daily mean 2 m air
   temperature at each lake from the **NOAA GEFS forecast, 35 day** dataset on
   [dynamical.org](https://dynamical.org/catalog/noaa-gefs-forecast-35-day/): the NCEP
   Global Ensemble Forecast System's 31 members (a control and 30 perturbed), run every day
   at 00 UTC and kept since 2020, out to 35 days. It gets the weather the lakes had over
   the past year (to fit the model) and each member's forecast of the weather to come.
2. **Fit.** At each lake, `lm(water temperature ~ air temperature)` over the past year.
3. **Forecast.** Each GEFS member's air temperature goes through the regression, plus a
   random draw from the regression's residuals, to make one member of the water temperature
   forecast (`family = ensemble`, the member number is the `parameter`). The weather
   uncertainty comes from the 31 GEFS members and the model's own from the residuals.

```sh
pip install -r requirements.txt     # Python: icechunk, xarray, zarr, pystac, numpy, pandas
Rscript forecast.R                  # R: readr and dplyr
```

It writes `forecasts/lakes-<GEFS run date>-example_lake_model.csv.gz`. The file in this
repository is for the 2026-11-19 run. The model is a simple one on purpose: replace the
"Forecast" section of `forecast.R` with your own (other GEFS variables, a better regression, a
process model) and keep the rest.

### Reading weather forecasts from dynamical.org

dynamical.org publishes weather datasets as cloud-optimized
[Zarr](https://zarr.dev) in an [Icechunk](https://icechunk.io) repository on public storage.
There is no account or key, and you only download the part you ask for. The dataset's
[STAC](https://stac.dynamical.org/noaa-gefs-forecast-35-day/collection.json) record gives
the address, and `xarray` opens it lazily:

```python
import icechunk, pystac, xarray as xr

catalog = pystac.Catalog.from_file("https://stac.dynamical.org/catalog.json")
asset = catalog.get_child("noaa-gefs-forecast-35-day").assets["icechunk-https"]
repo = icechunk.Repository.open(icechunk.http_storage(asset.href))
ds = xr.open_zarr(repo.readonly_session("main").store, chunks=None)

# air temperature (deg C) at the cell nearest a lake: init_time x ensemble_member x lead_time
ds["temperature_2m"].sel(latitude=29.68, longitude=-82.01, method="nearest")
```

`init_time` is the day of the run, `ensemble_member` runs 0-30, `lead_time` is 3-hourly out to
10 days and 6-hourly after, and the grid is 0.25 degrees. The dataset also has other
variables (wind, humidity, radiation, precipitation, ...): print `ds` to see them. R
has no Icechunk reader, so `forecast.R` calls the small Python script and reads the CSV it
writes. The newest run takes a few hours to be added after 00 UTC; the script uses the latest
complete one and the file is named for it.

Weather data: NOAA NWS NCEP GEFS, processed by dynamical.org
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

`.github/workflows/forecast.yml` installs Python and the packages in `requirements.txt`, runs
`forecast.R` and commits the new file. Its
schedule is commented out: switch it on once the repository is registered and
the challenge's targets are published, since the forecast needs them. (Without
the schedule you can run it from the Actions tab.) Anything else that puts a
new file in `forecasts/` works as well: a cron job, a pipeline, a commit by hand.
